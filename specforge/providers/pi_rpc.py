"""Pi RPC Client -- communicates with Pi via JSON-RPC subprocess.

Spawns `pi --mode rpc --no-session` and exchanges JSON messages
over stdin/stdout. Uses the user's existing Claude/Max plan auth.
"""

from __future__ import annotations

import json
import os
import platform
import subprocess
import threading
import time
from queue import Empty, Queue

from specforge.utils.console import console


def _find_pi_command() -> str:
    """Find the Pi executable path."""
    system = platform.system()

    if system == "Windows":
        # Check npm global install
        appdata = os.environ.get("APPDATA", "")
        pi_cmd = os.path.join(appdata, "npm", "pi.cmd")
        if os.path.exists(pi_cmd):
            return pi_cmd

    # Try PATH
    import shutil
    pi_path = shutil.which("pi")
    if pi_path:
        return pi_path

    raise FileNotFoundError(
        "Pi not found. Install with: npm i -g @mariozechner/pi-coding-agent\n"
        "Then run: pi  (to set up authentication)"
    )


class PiRpcClient:
    """Client for Pi's RPC mode subprocess."""

    def __init__(self, timeout: int = 300):
        self.proc: subprocess.Popen | None = None
        self.events: Queue = Queue()
        self.timeout = timeout
        self._reader_thread: threading.Thread | None = None
        self._pi_cmd: str = ""

    def start(self) -> None:
        """Start Pi in RPC mode."""
        self._pi_cmd = _find_pi_command()
        console.print(f"  [info]Starting Pi RPC ({self._pi_cmd})...[/info]")

        self.proc = subprocess.Popen(
            [self._pi_cmd, "--mode", "rpc", "--no-session"],
            stdin=subprocess.PIPE,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
            encoding="utf-8",
            errors="replace",
            bufsize=1,
        )

        # Background thread to read events
        self._reader_thread = threading.Thread(target=self._read_events, daemon=True)
        self._reader_thread.start()

        # Wait for Pi to initialize
        time.sleep(2)
        console.print("  [info]Pi RPC ready[/info]")

    def _read_events(self) -> None:
        """Read JSON events from Pi's stdout."""
        if not self.proc or not self.proc.stdout:
            return
        for line in self.proc.stdout:
            line = line.strip()
            if not line:
                continue
            try:
                event = json.loads(line)
                self.events.put(event)
            except json.JSONDecodeError:
                pass  # Skip non-JSON lines

    def _send(self, command: dict) -> None:
        """Send a JSON command to Pi."""
        if not self.proc or not self.proc.stdin:
            raise RuntimeError("Pi RPC not started")
        self.proc.stdin.write(json.dumps(command) + "\n")
        self.proc.stdin.flush()

    def prompt(self, message: str, timeout: int | None = None) -> str:
        """Send a prompt and collect the full text response.

        Args:
            message: The prompt text to send.
            timeout: Response timeout in seconds (default: self.timeout).

        Returns:
            The full text response from Claude.
        """
        if not self.proc:
            raise RuntimeError("Pi RPC not started. Call start() first.")

        timeout = timeout or self.timeout

        # Drain any leftover events
        while not self.events.empty():
            try:
                self.events.get_nowait()
            except Empty:
                break

        self._send({"type": "prompt", "message": message})

        # Collect response text
        full_text = ""
        start = time.time()

        while time.time() - start < timeout:
            try:
                event = self.events.get(timeout=2)
            except Empty:
                # Check if process is still alive
                if self.proc.poll() is not None:
                    raise RuntimeError(f"Pi process exited with code {self.proc.returncode}")
                continue

            event_type = event.get("type")

            if event_type == "message_update":
                delta = event.get("assistantMessageEvent", {})
                if delta.get("type") == "text_delta":
                    full_text += delta["delta"]

            elif event_type == "agent_end":
                return full_text

            elif event_type == "response" and not event.get("success", True):
                error = event.get("error", "Unknown error")
                raise RuntimeError(f"Pi RPC error: {error}")

        raise TimeoutError(f"Pi RPC timed out after {timeout}s")

    def stop(self) -> None:
        """Stop the Pi subprocess."""
        if self.proc:
            try:
                self.proc.terminate()
                self.proc.wait(timeout=5)
            except (subprocess.TimeoutExpired, OSError):
                self.proc.kill()
            self.proc = None
            console.print("  [info]Pi RPC stopped[/info]")

"""Tests for venv-based dependency isolation in the Tester agent."""

import os
import sys
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

from specforge.agents.tester import _create_venv, _get_venv_python, _install_dependencies, _run_pytest


class TestGetVenvPython:
    def test_windows_path(self):
        with patch("os.name", "nt"):
            result = _get_venv_python("/project")
            assert "Scripts" in result
            assert result.endswith("python.exe")

    @pytest.mark.skipif(os.name == "nt", reason="PosixPath not available on Windows")
    def test_unix_path(self):
        with patch("os.name", "posix"):
            result = _get_venv_python("/project")
            assert "bin" in result
            assert result.endswith("python")


class TestCreateVenv:
    @patch("subprocess.run")
    def test_creates_venv(self, mock_run, tmp_path):
        mock_run.return_value = MagicMock(returncode=0, stdout="", stderr="")
        success, msg = _create_venv(str(tmp_path))
        assert success
        assert "created" in msg.lower()
        # Verify it called python -m venv
        call_args = mock_run.call_args[0][0]
        assert "-m" in call_args
        assert "venv" in call_args

    def test_skips_existing_venv(self, tmp_path):
        venv_dir = tmp_path / ".venv"
        venv_dir.mkdir()
        success, msg = _create_venv(str(tmp_path))
        assert success
        assert "already exists" in msg.lower()

    @patch("subprocess.run")
    def test_reports_failure(self, mock_run, tmp_path):
        mock_run.return_value = MagicMock(returncode=1, stdout="", stderr="error creating venv")
        success, msg = _create_venv(str(tmp_path))
        assert not success
        assert "Failed" in msg


class TestInstallDependencies:
    @patch("specforge.agents.tester._create_venv")
    @patch("subprocess.run")
    def test_installs_into_venv(self, mock_run, mock_venv, tmp_path):
        # Create requirements.txt
        (tmp_path / "requirements.txt").write_text("fastapi\nuvicorn\n")
        mock_venv.return_value = (True, "Venv created")
        mock_run.return_value = MagicMock(returncode=0, stdout="", stderr="")

        success, msg = _install_dependencies(str(tmp_path))
        assert success
        assert "venv" in msg.lower()

        # Verify pip was called with venv python
        call_args = mock_run.call_args[0][0]
        assert ".venv" in call_args[0]  # First arg should be venv python path
        assert "pytest" in call_args  # Should also install test deps

    def test_no_requirements(self, tmp_path):
        success, msg = _install_dependencies(str(tmp_path))
        assert success
        assert "No requirements.txt" in msg


class TestRunPytest:
    @patch("subprocess.run")
    def test_uses_venv_python(self, mock_run, tmp_path):
        mock_run.return_value = MagicMock(returncode=0, stdout="1 passed", stderr="")

        # Create a fake venv python so it's detected
        venv_python = Path(_get_venv_python(str(tmp_path)))
        venv_python.parent.mkdir(parents=True, exist_ok=True)
        venv_python.write_text("")  # Create the file so Path.exists() returns True

        returncode, output = _run_pytest(str(tmp_path))

        call_args = mock_run.call_args[0][0]
        assert ".venv" in call_args[0]  # Should use venv python

    @patch("subprocess.run")
    def test_falls_back_to_system_python(self, mock_run, tmp_path):
        mock_run.return_value = MagicMock(returncode=0, stdout="1 passed", stderr="")

        # No venv exists
        returncode, output = _run_pytest(str(tmp_path))

        call_args = mock_run.call_args[0][0]
        assert call_args[0] == "python"  # Falls back to system python

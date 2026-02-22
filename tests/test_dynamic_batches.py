"""Tests for dynamic batch generation in the Coder agent."""

import pytest

from specforge.agents.coder import (
    _build_batch_system_prompt,
    _build_dynamic_batches,
    _extract_endpoint_groups,
    _has_auth_endpoints,
)


def _make_endpoint(path, method="GET", tags=None, auth="none", summary=""):
    return {
        "path": path,
        "method": method,
        "tags": tags or [],
        "auth": auth,
        "summary": summary,
    }


def _make_model(name, table_name, fields=None):
    return {
        "name": name,
        "table_name": table_name,
        "fields": fields or [{"name": "id", "type": "integer"}],
    }


def _make_design(endpoints=None, database_models=None, dependencies=None, env_variables=None):
    return {
        "project_name": "test-project",
        "description": "Test project",
        "dependencies": dependencies or ["fastapi", "uvicorn", "sqlmodel"],
        "endpoints": endpoints or [],
        "database_models": database_models or [],
        "env_variables": env_variables or [],
        "docker": {"port": 8000, "base_image": "python:3.12-slim"},
        "middlewares": [],
        "additional_notes": "",
    }


# ── P0-A: Dynamic batch tests ──────────────────────────────────────


class TestExtractEndpointGroups:
    def test_groups_by_tag(self):
        endpoints = [
            _make_endpoint("/tasks", tags=["tasks"]),
            _make_endpoint("/tasks/{id}", tags=["tasks"]),
            _make_endpoint("/users", tags=["users"]),
        ]
        groups = _extract_endpoint_groups({"endpoints": endpoints})
        assert "tasks" in groups
        assert "users" in groups
        assert len(groups["tasks"]) == 2
        assert len(groups["users"]) == 1

    def test_groups_by_path_segment(self):
        endpoints = [
            _make_endpoint("/tasks"),
            _make_endpoint("/tasks/{id}"),
            _make_endpoint("/users/me"),
        ]
        groups = _extract_endpoint_groups({"endpoints": endpoints})
        assert "tasks" in groups
        assert "users" in groups

    def test_skips_api_prefix(self):
        endpoints = [
            _make_endpoint("/api/v1/products"),
            _make_endpoint("/api/v1/products/{id}"),
        ]
        groups = _extract_endpoint_groups({"endpoints": endpoints})
        assert "products" in groups
        assert "api" not in groups

    def test_empty_endpoints(self):
        groups = _extract_endpoint_groups({"endpoints": []})
        assert groups == {}

    def test_root_path_fallback(self):
        endpoints = [_make_endpoint("/")]
        groups = _extract_endpoint_groups({"endpoints": endpoints})
        assert "root" in groups


class TestBuildDynamicBatches:
    def test_todo_app(self):
        """SystemDesign with /tasks/* endpoints → generates routers/tasks.py, test_tasks.py"""
        design = _make_design(
            endpoints=[
                _make_endpoint("/tasks", "POST", tags=["tasks"], summary="Create task"),
                _make_endpoint("/tasks", "GET", tags=["tasks"], summary="List tasks"),
                _make_endpoint("/tasks/{id}", "DELETE", tags=["tasks"], summary="Delete task"),
            ],
            database_models=[_make_model("Task", "tasks")],
        )
        batches = _build_dynamic_batches(design)

        assert len(batches) == 4
        assert batches[0]["name"] == "core"
        assert batches[1]["name"] == "routers"
        assert batches[2]["name"] == "tests"
        assert batches[3]["name"] == "infra"

        # Router batch should mention tasks.py
        assert "routers/tasks.py" in batches[1]["instruction"]
        # Should NOT mention links.py or admin.py (old hardcoded names)
        assert "links.py" not in batches[1]["instruction"]
        assert "admin.py" not in batches[1]["instruction"]

        # Test batch should mention test_tasks.py
        assert "test_tasks.py" in batches[2]["instruction"]
        # Always has test_health.py
        assert "test_health.py" in batches[2]["instruction"]

    def test_multi_router(self):
        """SystemDesign with multiple endpoint groups → multiple routers and test files."""
        design = _make_design(
            endpoints=[
                _make_endpoint("/users", "POST", tags=["users"]),
                _make_endpoint("/users/{id}", "GET", tags=["users"]),
                _make_endpoint("/products", "GET", tags=["products"]),
                _make_endpoint("/products/{id}", "GET", tags=["products"]),
                _make_endpoint("/orders", "POST", tags=["orders"]),
            ],
        )
        batches = _build_dynamic_batches(design)

        router_instruction = batches[1]["instruction"]
        assert "routers/users.py" in router_instruction
        assert "routers/products.py" in router_instruction
        assert "routers/orders.py" in router_instruction

        test_instruction = batches[2]["instruction"]
        assert "test_users.py" in test_instruction
        assert "test_products.py" in test_instruction
        assert "test_orders.py" in test_instruction

    def test_with_auth(self):
        """Endpoints with auth_required → includes app/auth.py."""
        design = _make_design(
            endpoints=[
                _make_endpoint("/tasks", "POST", tags=["tasks"], auth="jwt"),
                _make_endpoint("/health", "GET", tags=["health"]),
            ],
        )
        batches = _build_dynamic_batches(design)

        core_instruction = batches[0]["instruction"]
        assert "app/auth.py" in core_instruction

    def test_no_auth(self):
        """No auth endpoints → no app/auth.py in core batch."""
        design = _make_design(
            endpoints=[
                _make_endpoint("/tasks", "GET", tags=["tasks"]),
                _make_endpoint("/health", "GET", tags=["health"]),
            ],
        )
        batches = _build_dynamic_batches(design)

        core_instruction = batches[0]["instruction"]
        assert "app/auth.py" not in core_instruction

    def test_always_has_health(self):
        """Health test file is always included even without explicit health endpoint."""
        design = _make_design(
            endpoints=[
                _make_endpoint("/tasks", "GET", tags=["tasks"]),
            ],
        )
        batches = _build_dynamic_batches(design)

        # Router batch should add a health router
        assert "health" in batches[1]["instruction"].lower()
        # Test batch always has test_health.py
        assert "test_health.py" in batches[2]["instruction"]

    def test_core_batch_lists_models(self):
        """Core batch instruction should describe the actual database models."""
        design = _make_design(
            database_models=[
                _make_model("Task", "tasks", [{"name": "id"}, {"name": "title"}, {"name": "done"}]),
                _make_model("User", "users", [{"name": "id"}, {"name": "email"}]),
            ],
        )
        batches = _build_dynamic_batches(design)

        core_instruction = batches[0]["instruction"]
        assert "Task" in core_instruction
        assert "User" in core_instruction

    def test_infra_batch_uses_dependencies(self):
        """Infra batch should list actual dependencies from SystemDesign."""
        design = _make_design(
            dependencies=["fastapi", "uvicorn", "sqlmodel", "redis"],
        )
        batches = _build_dynamic_batches(design)

        infra_instruction = batches[3]["instruction"]
        assert "fastapi" in infra_instruction
        assert "redis" in infra_instruction


# ── P0-B: Prompt generation tests ──────────────────────────────────


class TestBuildBatchSystemPrompt:
    def test_includes_sqlmodel_tips_when_present(self):
        design = _make_design(dependencies=["fastapi", "sqlmodel"])
        prompt = _build_batch_system_prompt(design)
        assert "SQLModel" in prompt
        assert "foreign_key" in prompt

    def test_no_sqlmodel_tips_when_absent(self):
        design = _make_design(dependencies=["fastapi", "sqlalchemy"])
        prompt = _build_batch_system_prompt(design)
        assert "SQLModel rules" not in prompt
        assert "SQLAlchemy" in prompt

    def test_includes_auth_lib_when_present(self):
        design = _make_design(dependencies=["fastapi", "python-jose", "passlib"])
        prompt = _build_batch_system_prompt(design)
        assert "python-jose" in prompt
        assert "passlib" in prompt

    def test_no_hardcoded_libraries(self):
        """Prompt should NOT hardcode specific libraries — they come from SystemDesign."""
        design = _make_design(dependencies=["fastapi", "sqlalchemy", "pyjwt"])
        prompt = _build_batch_system_prompt(design)
        # Should not mention sqlmodel or python-jose since they're not in deps
        assert "SQLModel rules" not in prompt
        assert "python-jose" not in prompt

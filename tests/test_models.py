"""Tests for SpecForge Pydantic models."""

import pytest

from specforge.models import (
    AgentState,
    AuthType,
    DatabaseField,
    DatabaseModel,
    DockerConfig,
    Endpoint,
    EnvVariable,
    FieldType,
    HttpMethod,
    Middleware,
    RequestSchema,
    ResponseSchema,
    SchemaField,
    SystemDesign,
    TestResult,
)


class TestEndpoint:
    def test_basic_endpoint(self):
        ep = Endpoint(
            method=HttpMethod.GET,
            path="/health",
            summary="Health check",
        )
        assert ep.method == HttpMethod.GET
        assert ep.path == "/health"
        assert ep.auth == AuthType.NONE
        assert ep.rate_limited is False

    def test_auth_endpoint(self):
        ep = Endpoint(
            method=HttpMethod.POST,
            path="/api/links",
            summary="Create link",
            auth=AuthType.JWT,
            rate_limited=True,
            tags=["links"],
        )
        assert ep.auth == AuthType.JWT
        assert ep.rate_limited is True
        assert "links" in ep.tags

    def test_endpoint_with_schemas(self):
        ep = Endpoint(
            method=HttpMethod.POST,
            path="/api/shorten",
            summary="Shorten URL",
            request_body=RequestSchema(
                fields=[
                    SchemaField(name="url", type=FieldType.STRING, description="URL to shorten"),
                    SchemaField(name="slug", type=FieldType.STRING, is_required=False),
                ]
            ),
            response=ResponseSchema(
                fields=[
                    SchemaField(name="short_code", type=FieldType.STRING),
                    SchemaField(name="short_url", type=FieldType.STRING),
                ]
            ),
        )
        assert len(ep.request_body.fields) == 2
        assert ep.request_body.fields[1].is_required is False
        assert len(ep.response.fields) == 2


class TestDatabaseModel:
    def test_basic_model(self):
        model = DatabaseModel(
            name="Link",
            table_name="links",
            description="URL shortener links",
            fields=[
                DatabaseField(name="id", type=FieldType.INTEGER, primary_key=True),
                DatabaseField(name="url", type=FieldType.STRING),
                DatabaseField(name="short_code", type=FieldType.STRING, unique=True, indexed=True),
            ],
        )
        assert model.name == "Link"
        assert len(model.fields) == 3
        assert model.fields[0].primary_key is True
        assert model.fields[2].unique is True


class TestSystemDesign:
    def test_full_design(self):
        design = SystemDesign(
            project_name="url-shortener",
            description="URL shortener service",
            dependencies=["fastapi", "sqlmodel", "uvicorn"],
            endpoints=[
                Endpoint(method=HttpMethod.GET, path="/health", summary="Health check"),
            ],
            database_models=[
                DatabaseModel(name="Link", table_name="links", fields=[]),
            ],
            env_variables=[
                EnvVariable(name="JWT_SECRET", description="JWT signing secret"),
            ],
            docker=DockerConfig(port=8000),
            middlewares=[
                Middleware(name="RateLimiter", description="Rate limiting"),
            ],
        )
        assert design.project_name == "url-shortener"
        assert len(design.endpoints) == 1
        assert len(design.database_models) == 1
        assert len(design.env_variables) == 1
        assert design.docker.port == 8000

    def test_serialization_roundtrip(self):
        design = SystemDesign(
            project_name="test",
            description="test project",
        )
        data = design.model_dump()
        design2 = SystemDesign.model_validate(data)
        assert design2.project_name == "test"
        assert design2.python_version == "3.12"


class TestTestResult:
    def test_passing(self):
        result = TestResult(passed=True, total_tests=10, passed_tests=10)
        assert result.passed is True
        assert result.failed_tests == 0

    def test_failing(self):
        result = TestResult(
            passed=False,
            total_tests=10,
            passed_tests=7,
            failed_tests=3,
            failure_details=["test_x FAILED", "test_y FAILED", "test_z FAILED"],
            feedback="Fix the assertions",
        )
        assert result.passed is False
        assert len(result.failure_details) == 3


class TestDockerConfig:
    def test_defaults(self):
        config = DockerConfig()
        assert config.base_image == "python:3.12-slim"
        assert config.port == 8000
        assert len(config.volumes) == 1

"""Pydantic models for SpecForge system design and agent state."""

from __future__ import annotations

from enum import Enum
from typing import Any, TypedDict

from pydantic import BaseModel, Field


# ── System Design Models ─────────────────────────────────────────────


class HttpMethod(str, Enum):
    GET = "GET"
    POST = "POST"
    PUT = "PUT"
    PATCH = "PATCH"
    DELETE = "DELETE"


class FieldType(str, Enum):
    STRING = "string"
    INTEGER = "integer"
    FLOAT = "float"
    BOOLEAN = "boolean"
    DATETIME = "datetime"
    TEXT = "text"
    JSON = "json"


class AuthType(str, Enum):
    NONE = "none"
    JWT = "jwt"
    API_KEY = "api_key"
    JWT_OR_API_KEY = "jwt_or_api_key"


class SchemaField(BaseModel):
    """A field in a request/response schema."""

    name: str = Field(description="Field name")
    type: FieldType = Field(description="Field data type")
    is_required: bool = Field(default=True, description="Whether the field is required")
    description: str = Field(default="", description="Field description")
    default_value: Any = Field(default=None, description="Default value if any")


class RequestSchema(BaseModel):
    """Request body schema for an endpoint."""

    fields: list[SchemaField] = Field(default_factory=list, description="Request body fields")


class ResponseSchema(BaseModel):
    """Response schema for an endpoint."""

    fields: list[SchemaField] = Field(default_factory=list, description="Response body fields")
    is_list: bool = Field(default=False, description="Whether response is a list of items")


class Endpoint(BaseModel):
    """A single API endpoint."""

    method: HttpMethod = Field(description="HTTP method")
    path: str = Field(description="URL path (e.g. /api/links)")
    summary: str = Field(description="Short description of what this endpoint does")
    description: str = Field(default="", description="Detailed description")
    auth: AuthType = Field(default=AuthType.NONE, description="Authentication requirement")
    rate_limited: bool = Field(default=False, description="Whether this endpoint is rate limited")
    request_body: RequestSchema | None = Field(default=None, description="Request body schema")
    response: ResponseSchema = Field(default_factory=ResponseSchema, description="Response schema")
    tags: list[str] = Field(default_factory=list, description="OpenAPI tags for grouping")


class DatabaseField(BaseModel):
    """A column/field in a database table."""

    name: str = Field(description="Column name")
    type: FieldType = Field(description="Column data type")
    primary_key: bool = Field(default=False, description="Is this the primary key?")
    nullable: bool = Field(default=False, description="Can this be null?")
    unique: bool = Field(default=False, description="Unique constraint?")
    indexed: bool = Field(default=False, description="Should this be indexed?")
    default_value: Any = Field(default=None, description="Default value")
    description: str = Field(default="", description="Field description")


class DatabaseModel(BaseModel):
    """A database table/model."""

    name: str = Field(description="Model class name (e.g. Link)")
    table_name: str = Field(description="Database table name (e.g. links)")
    description: str = Field(default="", description="What this table stores")
    fields: list[DatabaseField] = Field(default_factory=list, description="Table columns")
    relationships: list[str] = Field(
        default_factory=list, description="Relationship descriptions (e.g. 'Link has many ClickEvents')"
    )


class EnvVariable(BaseModel):
    """An environment variable the generated service needs."""

    name: str = Field(description="Variable name (e.g. JWT_SECRET)")
    description: str = Field(description="What this variable is for")
    default_value: str = Field(default="", description="Default value (empty if mandatory)")
    is_mandatory: bool = Field(default=True, description="Whether this must be set")
    example: str = Field(default="", description="Example value")


class DockerConfig(BaseModel):
    """Docker configuration for the generated service."""

    base_image: str = Field(default="python:3.12-slim", description="Docker base image")
    port: int = Field(default=8000, description="Exposed port")
    volumes: list[str] = Field(
        default_factory=lambda: ["./data:/app/data"], description="Volume mounts"
    )
    environment_files: list[str] = Field(
        default_factory=lambda: [".env"], description="Env files to load"
    )


class Middleware(BaseModel):
    """A middleware or cross-cutting concern."""

    name: str = Field(description="Middleware name (e.g. RateLimiter, CORSMiddleware)")
    description: str = Field(description="What it does")
    config: dict[str, Any] = Field(default_factory=dict, description="Configuration parameters")


class SystemDesign(BaseModel):
    """Complete system design produced by the Architect agent."""

    project_name: str = Field(description="Project name (e.g. url-shortener)")
    description: str = Field(description="Brief project description")
    python_version: str = Field(default="3.12", description="Target Python version")
    dependencies: list[str] = Field(
        default_factory=list,
        description="Python package dependencies (e.g. ['fastapi', 'sqlmodel', 'uvicorn'])",
    )
    endpoints: list[Endpoint] = Field(default_factory=list, description="All API endpoints")
    database_models: list[DatabaseModel] = Field(
        default_factory=list, description="All database models"
    )
    env_variables: list[EnvVariable] = Field(
        default_factory=list, description="Required environment variables"
    )
    docker: DockerConfig = Field(default_factory=DockerConfig, description="Docker configuration")
    middlewares: list[Middleware] = Field(
        default_factory=list, description="Middlewares and cross-cutting concerns"
    )
    additional_notes: str = Field(
        default="",
        description="Any additional architecture notes, patterns, or implementation guidance",
    )


# ── Agent State (for LangGraph) ─────────────────────────────────────


class TestRunResult(BaseModel):
    """Result from running tests on generated code."""

    __test__ = False  # Prevent pytest from collecting this as a test class

    passed: bool = Field(description="Whether all tests passed")
    total_tests: int = Field(default=0, description="Total number of tests")
    passed_tests: int = Field(default=0, description="Number of passed tests")
    failed_tests: int = Field(default=0, description="Number of failed tests")
    error_tests: int = Field(default=0, description="Number of errored tests")
    output: str = Field(default="", description="Full pytest output")
    failure_details: list[str] = Field(
        default_factory=list, description="Details of each failure"
    )
    feedback: str = Field(
        default="", description="LLM-generated feedback for the Coder to fix issues"
    )


class AgentState(TypedDict, total=False):
    """LangGraph state passed between agents."""

    # Input
    spec_text: str  # Raw markdown spec
    output_dir: str  # Where to write generated files

    # Run configuration (thread-safe provider access)
    run_config: Any  # RunConfig instance — uses Any to stay JSON-friendly for LangGraph

    # Architect output
    system_design: dict  # SystemDesign as dict (JSON-serializable for LangGraph)

    # Coder output
    generated_files: dict[str, str]  # {filepath: content}

    # Tester output
    test_result: dict  # TestRunResult as dict

    # Verification
    verification: dict  # VerificationReport as dict

    # Control flow
    iteration: int  # Current iteration (1-based)
    max_iterations: int  # Max iterations allowed
    status: str  # "in_progress", "success", "max_iterations_reached"
    errors: list[str]  # Accumulated error messages

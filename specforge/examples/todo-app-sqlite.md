# Todo App API

A simple but complete task management REST API with user accounts and project organization.

## Features

### User Management
- Register with email and password
- Login to get JWT token
- View/update own profile

### Projects
- Create, list, update, delete projects
- Each project belongs to a user
- Projects have a name, description, and color label

### Tasks
- Create, list, update, delete tasks within a project
- Fields: title, description, due_date, priority (low/medium/high), status (todo/in_progress/done)
- Filter tasks by status or priority
- Mark task as complete (shortcut endpoint)
- Tasks belong to a project and are created by a user

### Tags
- Create and list tags
- Assign/remove tags to/from tasks (many-to-many)
- Filter tasks by tag

## Tech Stack
- **Framework**: FastAPI with async endpoints
- **Database**: SQLite via SQLModel (async with aiosqlite)
- **Auth**: JWT tokens (python-jose), password hashing (passlib with bcrypt)
- **Validation**: Pydantic v2 schemas

## API Endpoints

### Auth
- `POST /auth/register` — Create new user account
- `POST /auth/login` — Login, returns JWT access token

### Users
- `GET /users/me` — Get current user profile (auth required)
- `PATCH /users/me` — Update current user profile (auth required)

### Projects
- `POST /projects` — Create project (auth required)
- `GET /projects` — List user's projects (auth required)
- `GET /projects/{id}` — Get project detail (auth required)
- `PUT /projects/{id}` — Update project (auth required)
- `DELETE /projects/{id}` — Delete project and its tasks (auth required)

### Tasks
- `POST /projects/{project_id}/tasks` — Create task in project (auth required)
- `GET /projects/{project_id}/tasks` — List tasks in project, with optional `?status=` and `?priority=` filters (auth required)
- `GET /tasks/{id}` — Get task detail (auth required)
- `PUT /tasks/{id}` — Update task (auth required)
- `PATCH /tasks/{id}/complete` — Mark task as done (auth required)
- `DELETE /tasks/{id}` — Delete task (auth required)

### Tags
- `POST /tags` — Create tag (auth required)
- `GET /tags` — List all tags (auth required)
- `POST /tasks/{id}/tags/{tag_id}` — Add tag to task (auth required)
- `DELETE /tasks/{id}/tags/{tag_id}` — Remove tag from task (auth required)

### Health
- `GET /health` — Health check (no auth)

## Database Models

### User
| Field | Type | Constraints |
|-------|------|------------|
| id | integer | primary key, auto-increment |
| email | string | unique, indexed, not null |
| hashed_password | string | not null |
| display_name | string | nullable |
| created_at | datetime | default now |

### Project
| Field | Type | Constraints |
|-------|------|------------|
| id | integer | primary key, auto-increment |
| name | string | not null |
| description | text | nullable |
| color | string | default "#3B82F6" |
| user_id | integer | foreign key → users.id, not null |
| created_at | datetime | default now |

### Task
| Field | Type | Constraints |
|-------|------|------------|
| id | integer | primary key, auto-increment |
| title | string | not null |
| description | text | nullable |
| status | string | enum: todo/in_progress/done, default "todo" |
| priority | string | enum: low/medium/high, default "medium" |
| due_date | datetime | nullable |
| project_id | integer | foreign key → projects.id, not null |
| user_id | integer | foreign key → users.id, not null |
| created_at | datetime | default now |
| updated_at | datetime | auto-update |

### Tag
| Field | Type | Constraints |
|-------|------|------------|
| id | integer | primary key, auto-increment |
| name | string | unique, not null |

### TaskTag (join table)
| Field | Type | Constraints |
|-------|------|------------|
| task_id | integer | foreign key → tasks.id, primary key |
| tag_id | integer | foreign key → tags.id, primary key |

## Environment Variables
| Variable | Description | Default |
|----------|-------------|---------|
| DATABASE_URL | SQLite path | sqlite+aiosqlite:///./data/todo.db |
| JWT_SECRET | Secret for signing tokens | (required) |
| JWT_ALGORITHM | Token algorithm | HS256 |
| JWT_EXPIRE_MINUTES | Token expiry | 60 |

## Docker
- Base image: `python:3.12-slim`
- Port: 8000
- Volume: `./data:/app/data` (for SQLite persistence)

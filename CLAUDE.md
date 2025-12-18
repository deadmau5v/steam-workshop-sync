# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Project Overview

Steam Workshop Sync is a continuous monitoring and synchronization tool that tracks Steam Workshop items for a specified game and stores them in a PostgreSQL database. The application runs in a continuous loop, scraping workshop pages, parsing item metadata, and persisting data with automatic retry logic for resilience.

## Core Architecture

### Data Flow

1. **Main Loop** (`main.py`): Orchestrates the continuous monitoring cycle
   - Paginates through workshop pages with configurable delays
   - Coordinates between spider and database layers
   - Handles error recovery and logging

2. **Spider Layer** (`spiders/workshop.py`): HTTP client with retry logic
   - `Wrokshop.get_new_items(page)`: Fetches workshop browse pages
   - `Wrokshop.get_items_info(item)`: Fetches detailed item information
   - Uses decorator-based retry mechanism with exponential backoff for HTTP errors

3. **Parser Layer** (`parsers/workshop.py`): HTML extraction
   - `WorkshopParser.parser_items_card()`: Extracts item cards and pagination from browse pages
   - `WorkshopParser.parser_items_info()`: Extracts detailed metadata from item detail pages
   - Uses BeautifulSoup for HTML parsing and html2text for description conversion

4. **Database Layer** (`database.py`): SQLModel/SQLAlchemy persistence
   - `save_workshop_item()`: Upsert single item with `exist_ok` flag
   - `save_workshop_items()`: Batch save with error handling
   - Uses SQLModel with PostgreSQL backend

### Models (`models/workshop.py`)

- `WorkshopItem`: SQLModel table representing workshop items with fields: id, url, title, coverview_url, author, author_profile, rating, description, file_size, created_at, updated_at, synced_at
- `Pagination`: Pydantic model for page metadata

### Utilities

- `utils/retry.py`: Decorator `@retry_on_error()` with configurable retry strategies per HTTP status code
- `utils/formater.py`: Date parsing utilities
- `utils/log.py`: Logger configuration

## Environment Configuration

Required environment variables (see `.env.example`):
- `STEAM_WORKSHOP_SYNC_DATABASE_URL`: PostgreSQL connection string (required)
- `STEAM_WORKSHOP_SYNC_APP_ID`: Steam game app ID to monitor (required)
- `STEAM_WORKSHOP_SYNC_TIMEOUT`: Request timeout in seconds (default: 30)
- `STEAM_WORKSHOP_SYNC_PAGE_DELAY`: Delay between pages in seconds (default: 5.0)
- `STEAM_WORKSHOP_SYNC_CYCLE_DELAY`: Delay between monitoring cycles in seconds (default: 60.0)
- `STEAM_WORKSHOP_SYNC_REQUEST_DELAY`: Delay between individual requests in seconds (default: 1.0)

## Development Commands

This project uses `uv` for Python dependency management and `make` for task automation.

### Local Development

```bash
# Install dependencies and run migrations
make dev-setup
# or manually:
uv sync
uv run alembic upgrade head

# Run the application locally
make dev-run
# or manually:
uv run python main.py
```

### Database Migrations

```bash
# Create a new migration
make dev-migrate msg="description of changes"
# or manually:
uv run alembic revision --autogenerate -m "description"

# Apply migrations
make dev-upgrade
# or manually:
uv run alembic upgrade head

# Rollback one migration
make dev-downgrade
# or manually:
uv run alembic downgrade -1

# View migration history
uv run alembic history

# View current migration version
uv run alembic current
```

### Docker Operations

```bash
# Initialize environment file
make init

# Build Docker image
make build

# Start services (postgres + application)
make up

# View application logs
make logs

# View all service logs
make logs-all

# Check service status
make ps

# Enter application container
make shell

# Enter PostgreSQL container
make db-shell

# Stop services
make down

# Stop services and remove volumes
make clean

# Restart application service
make restart
```

## Deployment

The project supports Docker deployment with automatic multi-architecture builds (amd64/arm64) via GitHub Actions. See `DEPLOYMENT.md` for detailed CI/CD setup.

## Important Implementation Notes

### Spider Retry Logic

The spider uses a sophisticated retry decorator that handles different HTTP status codes with different strategies:
- 429 (Too Many Requests): Unlimited retries with exponential backoff
- 5xx errors: Limited retries (default 3)
- Exponential backoff: Base 5s, max 300s

When modifying HTTP request logic, ensure the `@retry_on_error` decorator remains applied to prevent request failures from crashing the monitoring loop.

### Database Upsert Behavior

The `save_workshop_item()` function uses the `exist_ok` parameter to control update behavior:
- `exist_ok=True`: Updates existing records with new data
- `exist_ok=False`: Returns existing record without updating

The application always uses `exist_ok=True` to ensure items are kept up-to-date.

### Pagination Handling

The main loop first fetches page 1 to determine total pages, then iterates through remaining pages. This two-step approach ensures the loop doesn't make unnecessary requests when only one page exists.

### Typo in Class Name

Note: `Wrokshop` class in `spiders/workshop.py` has a typo (should be "Workshop"). This is the existing class name used throughout the codebase.

## Database Schema

The `workshop_items` table (managed via Alembic migrations in `alembic/versions/`) stores:
- Primary key: `id` (Steam Workshop item ID)
- Indexed fields: `title`, `author`
- Timestamps: `created_at`, `updated_at` (from Steam), `synced_at` (local sync time)
- Optional fields: `rating`, `description`, `file_size`

## Code Style

The project uses `ruff` for linting (configured in `pyproject.toml`). Run linting before committing changes if needed.

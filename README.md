# GitHub Stargazer Crawler

**Author:** Bilal Asif Burney

A high-performance, asynchronous GitHub crawler designed to fetch star counts for 100,000 repositories using the GitHub GraphQL API. 

## 🏗️ Architecture & Engineering Practices

This application is strictly divided into distinct layers to enforce the **Separation of Concerns (SoC)**:

* **Domain Layer (`src/domain/`)**: Contains pure, **immutable** Pydantic models representing core business entities (e.g., `RepositoryEntity`). It has zero dependencies on external libraries or frameworks.
* **Infrastructure Layer (`src/infrastructure/`)**: Handles all external I/O. 
    * **Anti-Corruption Layer (ACL)**: GitHub's GraphQL responses are deeply nested. The ACL translates raw, volatile API JSON into our pure, immutable Domain models, preventing external data structures from leaking into our business logic.
    * **Database**: Utilizes asynchronous SQLAlchemy with PostgreSQL for high-throughput database operations.
* **Application Layer (`src/application/`)**: Orchestrates the crawling process, managing rate limits, exponential backoff, and database transactions.

## 🔄 Crawling Strategy

GitHub's GraphQL search API returns at most **1,000 results per query**. To reach 100,000 repositories, the crawler partitions the star-count space into sub-ranges (e.g., `stars:10..500`, `stars:501..1000`, etc.) and adaptively splits any range that exceeds the 1,000-result cap.

### Rate Limit Handling
* **Primary rate limit**: The GraphQL `rateLimit` response field is checked after every request. When remaining points drop below 10, the crawler sleeps until the reset time.
* **Secondary rate limit**: HTTP 403 responses with a `Retry-After` header (GitHub's abuse detection) are respected — the crawler sleeps for the specified duration before retrying.
* **Inter-request delay**: A 0.5-second delay between requests prevents triggering secondary rate limits.
* **Exponential backoff**: Server errors (500/502/503/504) and network failures are retried with exponential backoff up to 5 attempts.

## 📅 Daily Scheduling

The GitHub Actions workflow runs on a daily cron schedule (`0 6 * * *` — 06:00 UTC) to keep star counts fresh. It can also be triggered manually via `workflow_dispatch` or on pushes/PRs to `main`.

## 🗄️ Database Schema

The schema uses a `metadata JSONB` column for forward-compatible flexibility (future fields like issues, PRs, languages can be added without migrations) and a `crawled_at` timestamp to track when each row was last refreshed. The upsert only updates rows where `stars` or `updated_at` have changed, keeping writes efficient for daily re-crawls.

## 🚀 Tech Stack
* **Language**: Python 3.12+
* **Concurrency**: `asyncio`, `aiohttp` (for max network throughput during the `crawl-stars` step).
* **Database**: PostgreSQL 15, `SQLAlchemy` (v2.0 Async), `asyncpg`.
* **Tooling**: `uv` (Astral) for lightning-fast dependency resolution in CI/CD.

## ⚙️ Local Setup

1.  **Install uv:** `curl -LsSf https://astral.sh/uv/install.sh | sh`
2.  **Clone & Sync:**
    ```bash
    git clone <your-repo-url>
    cd github-crawler
    uv sync
    ```
3.  **Environment Variables:** Copy `.env.example` to `.env` and add your GitHub Personal Access Token.
4.  **Database:** Spin up a local Postgres instance and run the schema initialization:
    ```bash
    psql -h localhost -U postgres -f setup.sql
    ```
5.  **Run the Crawler:**
    ```bash
    uv run python -m src.main
    ```
6.  **Run Tests:**
    ```bash
    uv run python -m unittest discover -s tests
    ```
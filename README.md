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
    uv run python src/main.py
    ```
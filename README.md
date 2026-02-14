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

GitHub's GraphQL search API returns at most **1,000 results per query**. To reach 100,000 repositories, the crawler partitions the star-count space into sub-ranges (e.g., `stars:10..500`, `stars:501..1000`, etc.) and adaptively splits any range that exceeds the 1,000-result cap. Up to 3 star-ranges are crawled **concurrently** using `asyncio.gather` for maximum throughput.

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

## 📝 Design Questions

### What I would do differently to scale this to 500 million repositories

Right now, the crawler is a single Python process that runs once a day on a GitHub Actions runner, writing to one PostgreSQL instance. That works fine for 100,000 repositories, but 500 million is 5,000× more data. Here's what I'd change:

1. **Multiple GitHub tokens and parallel workers.** The GitHub GraphQL API gives you 5,000 points per hour per token. At ~1 point per request fetching 25 repos, that's roughly 125,000 repos/hour per token. To crawl 500 million repos in a reasonable time, I'd need many tokens and many worker processes running in parallel. I'd use a task queue like Celery or AWS SQS where each worker picks up a star-range to crawl, so they don't step on each other.

2. **Distribute the star-range partitioning.** Right now the crawler uses a single in-memory `deque` of star ranges. At 500M scale, I'd move this queue into a shared system (like Redis or a database table) so multiple workers can pull ranges, mark them as "in progress," and handle failures gracefully. If a worker crashes, the range goes back to the queue.

3. **Database scaling.** A single PostgreSQL instance doing upserts for 500 million rows would be very slow. I'd consider:
   - **Partitioning** the `github_repositories` table by star range (e.g., `stars 0-100`, `100-1000`, `1000+`) so writes and reads are spread across smaller partitions.
   - **Batch sizes.** Instead of upserting 25 rows at a time, I'd buffer larger batches (1,000-5,000 rows) before flushing to the database to reduce round-trip overhead.
   - **Connection pooling** with PgBouncer or similar, since many workers would be hitting the database concurrently.
   - Eventually, if PostgreSQL can't keep up, I might look at a distributed database or at least read replicas.

4. **Don't run on GitHub Actions.** A 5-hour Actions runner won't cut it for 500M repos. I'd move the crawlers to dedicated VMs or containers (EC2, ECS, Kubernetes) that can run for days and be scaled up or down as needed.

5. **Incremental / delta crawls.** Crawling all 500M repos every day is wasteful since most repos don't change daily. I'd track the `updated_at` timestamp and use GitHub's "recently updated" search ordering to only re-crawl repos that have actually changed. For the initial full crawl, I'd do it once and then switch to incremental mode.

6. **Better monitoring and checkpointing.** At this scale, crashes are guaranteed. I'd add structured logging, metrics (Prometheus/Datadog), and persistent checkpointing so the crawl can resume from where it left off instead of starting over. Right now, if the process crashes halfway through, there's no way to know which ranges were already done.

7. **Rate limit coordination.** With multiple workers sharing tokens, I'd need a centralized rate limit tracker (e.g., a Redis counter) so workers don't accidentally exceed the limit by all checking their own local counters independently.

### How the schema would evolve for more metadata (issues, PRs, commits, comments, reviews, CI checks)

Right now the schema is a single flat table:

```sql
github_repositories (
    id VARCHAR PRIMARY KEY,
    name, owner, stars, updated_at, crawled_at, metadata JSONB
)
```

This works for star counts, but if I want to store issues, pull requests, PR comments, reviews, commits, and CI checks, I'd need to normalize the schema into separate tables with proper relationships. Here's how I'd approach it:

#### Proposed Schema

```sql
-- The existing table stays mostly the same
CREATE TABLE github_repositories (
    id VARCHAR PRIMARY KEY,
    name VARCHAR NOT NULL,
    owner VARCHAR NOT NULL,
    stars INTEGER NOT NULL,
    updated_at TIMESTAMPTZ,
    crawled_at TIMESTAMPTZ DEFAULT NOW()
);

-- Issues and PRs are separate entities linked to a repo
CREATE TABLE github_issues (
    id VARCHAR PRIMARY KEY,          -- GitHub GraphQL Node ID
    repo_id VARCHAR NOT NULL REFERENCES github_repositories(id),
    number INTEGER NOT NULL,
    title TEXT,
    state VARCHAR NOT NULL,          -- OPEN, CLOSED
    author VARCHAR,
    created_at TIMESTAMPTZ,
    updated_at TIMESTAMPTZ,
    crawled_at TIMESTAMPTZ DEFAULT NOW(),
    UNIQUE(repo_id, number)
);

-- Pull requests extend issues with extra fields
CREATE TABLE github_pull_requests (
    id VARCHAR PRIMARY KEY,
    repo_id VARCHAR NOT NULL REFERENCES github_repositories(id),
    number INTEGER NOT NULL,
    title TEXT,
    state VARCHAR NOT NULL,          -- OPEN, CLOSED, MERGED
    author VARCHAR,
    merge_commit_sha VARCHAR,
    created_at TIMESTAMPTZ,
    updated_at TIMESTAMPTZ,
    merged_at TIMESTAMPTZ,
    crawled_at TIMESTAMPTZ DEFAULT NOW(),
    UNIQUE(repo_id, number)
);

-- Comments on issues or PRs
CREATE TABLE github_comments (
    id VARCHAR PRIMARY KEY,
    issue_id VARCHAR REFERENCES github_issues(id),
    pr_id VARCHAR REFERENCES github_pull_requests(id),
    author VARCHAR,
    body TEXT,
    created_at TIMESTAMPTZ,
    updated_at TIMESTAMPTZ,
    crawled_at TIMESTAMPTZ DEFAULT NOW(),
    CHECK (issue_id IS NOT NULL OR pr_id IS NOT NULL)
);

-- PR review comments are different from regular comments
CREATE TABLE github_reviews (
    id VARCHAR PRIMARY KEY,
    pr_id VARCHAR NOT NULL REFERENCES github_pull_requests(id),
    author VARCHAR,
    state VARCHAR NOT NULL,          -- APPROVED, CHANGES_REQUESTED, COMMENTED
    body TEXT,
    submitted_at TIMESTAMPTZ,
    crawled_at TIMESTAMPTZ DEFAULT NOW()
);

-- Commits inside a PR
CREATE TABLE github_pr_commits (
    id VARCHAR PRIMARY KEY,          -- commit SHA
    pr_id VARCHAR NOT NULL REFERENCES github_pull_requests(id),
    message TEXT,
    author VARCHAR,
    committed_at TIMESTAMPTZ,
    crawled_at TIMESTAMPTZ DEFAULT NOW()
);

-- CI checks on a commit
CREATE TABLE github_checks (
    id VARCHAR PRIMARY KEY,
    commit_id VARCHAR NOT NULL REFERENCES github_pr_commits(id),
    name VARCHAR NOT NULL,
    status VARCHAR,                  -- QUEUED, IN_PROGRESS, COMPLETED
    conclusion VARCHAR,              -- SUCCESS, FAILURE, etc.
    started_at TIMESTAMPTZ,
    completed_at TIMESTAMPTZ,
    crawled_at TIMESTAMPTZ DEFAULT NOW()
);
```

#### Handling efficient updates (the "10 comments today, 20 tomorrow" problem)

The key insight is that each entity (comment, review, check, etc.) has its own unique GitHub Node ID. By using this as the primary key, the same `ON CONFLICT DO UPDATE` pattern I already use for repositories works for every table:

```sql
INSERT INTO github_comments (id, pr_id, author, body, created_at, updated_at, crawled_at)
VALUES (...)
ON CONFLICT (id) DO UPDATE
SET body = EXCLUDED.body,
    updated_at = EXCLUDED.updated_at,
    crawled_at = NOW()
WHERE github_comments.updated_at IS DISTINCT FROM EXCLUDED.updated_at;
```

So if a PR had 10 comments yesterday and gets 10 more today:
- The 10 existing comments hit the `ON CONFLICT` path. If their `updated_at` hasn't changed, the `WHERE` clause prevents any actual row update (minimal rows affected).
- The 10 new comments are clean inserts.
- This means only the genuinely new or edited comments cause writes.

#### How I'd crawl incrementally

For each repository, I'd store when each "sub-resource" was last crawled (the `crawled_at` column). When re-crawling:
1. Fetch the repo's issues/PRs sorted by `updated_at DESC` from the API.
2. Stop paginating once I hit an issue/PR whose `updated_at` is older than my last `crawled_at` for that repo — everything after that point hasn't changed.
3. For each updated issue/PR, re-fetch its comments and reviews the same way.

This way, a daily re-crawl only touches the things that actually changed, and the upsert pattern ensures we don't do unnecessary database writes even if we accidentally re-fetch something we already have.
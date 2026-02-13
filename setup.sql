-- Create the main repositories table
CREATE TABLE IF NOT EXISTS github_repositories (
    id VARCHAR PRIMARY KEY,             -- Using GitHub's GraphQL Node ID
    name VARCHAR NOT NULL,
    owner VARCHAR NOT NULL,
    stars INTEGER NOT NULL,
    updated_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP,
    metadata JSONB DEFAULT '{}'::jsonb  -- Flexible column for future metadata
);

-- Index for potential future queries sorting by stars or querying by owner
CREATE INDEX IF NOT EXISTS idx_github_repositories_stars ON github_repositories(stars DESC);
CREATE INDEX IF NOT EXISTS idx_github_repositories_owner ON github_repositories(owner);
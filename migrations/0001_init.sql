-- settings table (single row key-values)
CREATE TABLE IF NOT EXISTS settings (
  key TEXT PRIMARY KEY,
  value TEXT NOT NULL
);

INSERT OR IGNORE INTO settings (key, value) VALUES ('submissions_open', '0');

-- submissions queue
CREATE TABLE IF NOT EXISTS submissions (
  id TEXT PRIMARY KEY,
  created_at TEXT NOT NULL,
  artist_name TEXT NOT NULL,
  track_title TEXT NOT NULL,
  genre TEXT NOT NULL,
  track_url TEXT NOT NULL,
  notes TEXT,
  priority INTEGER NOT NULL DEFAULT 0,         -- for paid skip-the-line later
  paid INTEGER NOT NULL DEFAULT 0,             -- 0/1

  status TEXT NOT NULL DEFAULT 'NEW',          -- NEW | IN_REVIEW | SCORED
  claimed_by TEXT,                             -- "mike-desktop"
  claimed_at TEXT
);

-- scores (one final score per submission)
CREATE TABLE IF NOT EXISTS scores (
  submission_id TEXT PRIMARY KEY,
  scored_at TEXT NOT NULL,
  scored_by TEXT NOT NULL,

  lyrics INTEGER NOT NULL,
  delivery INTEGER NOT NULL,
  production INTEGER NOT NULL,
  originality INTEGER NOT NULL,
  replay INTEGER NOT NULL,

  total INTEGER NOT NULL,
  approved INTEGER NOT NULL,                   -- 0/1
  notes TEXT,

  FOREIGN KEY (submission_id) REFERENCES submissions(id)
);

-- helpful index for queue ordering
CREATE INDEX IF NOT EXISTS idx_submissions_queue
ON submissions(status, priority, created_at);

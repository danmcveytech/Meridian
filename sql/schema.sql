PRAGMA foreign_keys=ON;
CREATE TABLE workspace(name TEXT NOT NULL, source TEXT NOT NULL);
CREATE TABLE accounts(account TEXT PRIMARY KEY, region TEXT NOT NULL);
CREATE TABLE staging(account TEXT REFERENCES accounts, month TEXT, units INTEGER,
  balance REAL, prior_days INTEGER, next_late INTEGER, next_units INTEGER);
CREATE INDEX stage_key ON staging(account,month);
CREATE VIEW clean AS
WITH numbered AS (
  SELECT *, ROW_NUMBER() OVER(PARTITION BY account,month ORDER BY rowid) AS revision
  FROM staging
)
SELECT account, month, units, balance, prior_days, next_late, next_units
FROM numbered WHERE revision=1 AND units>=0 AND balance>=0;
CREATE TABLE reports(objective TEXT PRIMARY KEY, result TEXT NOT NULL, brief TEXT);

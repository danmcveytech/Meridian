SELECT COUNT(*) AS raw_rows,
  COUNT(*)-(SELECT COUNT(*) FROM (SELECT DISTINCT account,month FROM staging)) AS duplicate_rows,
  SUM(prior_days IS NULL) AS missing_days,
  SUM(units<0 OR balance<0) AS invalid_rows,
  (SELECT COUNT(*) FROM clean) AS clean_rows FROM staging;

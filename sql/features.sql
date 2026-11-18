WITH history AS (
  SELECT c.*, a.region,
    AVG(units) OVER(PARTITION BY c.account ORDER BY month
      ROWS BETWEEN 2 PRECEDING AND CURRENT ROW) AS recent_units
  FROM clean c JOIN accounts a ON a.account=c.account
)
SELECT * FROM history ORDER BY month,account;

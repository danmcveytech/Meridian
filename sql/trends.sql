SELECT month, SUM(units) AS units, COUNT(*) AS accounts,
  SUM(balance) AS balance,
  ROUND(100.0*SUM(CASE WHEN next_late=1 THEN 1 ELSE 0 END)/NULLIF(COUNT(next_late),0),1) AS late_pct
FROM clean GROUP BY month ORDER BY month;

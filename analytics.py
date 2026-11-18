"""Shared ingestion, diagnostics, temporal evaluation and production-style batch scoring."""
import csv
import math
import re
import sqlite3
from datetime import datetime
from pathlib import Path
import numpy as np
import pandas as pd
from sklearn.compose import ColumnTransformer
from sklearn.impute import SimpleImputer
from sklearn.inspection import permutation_importance
from sklearn.linear_model import LogisticRegression, Ridge
from sklearn.metrics import average_precision_score, mean_absolute_error
from sklearn.pipeline import make_pipeline
from sklearn.preprocessing import OneHotEncoder, StandardScaler
from generate import FIELDS, ROOT

OBJECTIVES = {"collections": ("Collections priority", "next_late"),
              "demand": ("Demand planning", "next_units")}
FEATURES = ["units","recent_units","balance","prior_days","region"]
LABELS = ["Current units","Three-period average units","Outstanding balance","Prior days overdue","Region"]


def sql(name):
    return (ROOT/"sql"/(name+".sql")).read_text()


def number(value, integer=False, optional=False):
    if optional and value == "":
        return None
    n = float(value)
    if not math.isfinite(n) or abs(n)>1e9 or (integer and not n.is_integer()):
        raise ValueError("Use finite numbers within range and whole numbers for counts.")
    return int(n) if integer else n


def ingest(db, stream, name, source):
    db.executescript(sql("schema"))
    reader = csv.DictReader(stream)
    if reader.fieldnames != FIELDS:
        raise ValueError("CSV headers must match the downloadable sample, in order.")
    regions = {}
    for i,r in enumerate(reader, 2):
        try:
            if i>50001 or None in r or None in r.values():
                raise ValueError("Maximum 50,000 complete rows.")
            account, region = r["account"].strip(), r["region"].strip()
            if not re.fullmatch(r"[A-Za-z0-9_-]{1,48}",account) or not 1<=len(region)<=48:
                raise ValueError("Invalid account ID or region.")
            if regions.setdefault(account,region) != region:
                raise ValueError("Region must be consistent within an account.")
            month = datetime.strptime(r["month"],"%Y-%m").strftime("%Y-%m")
            units = number(r["units"],True)
            balance = number(r["balance"])
            days = number(r["prior_days"],True,True)
            late = number(r["next_late"],True,True)
            future = number(r["next_units"],True,True)
            if late not in (0,1,None) or (future is not None and future<0) or (days is not None and days<0):
                raise ValueError("Invalid outcome or days overdue.")
            db.execute("INSERT OR IGNORE INTO accounts VALUES (?,?)",(account,region))
            db.execute("INSERT INTO staging VALUES (?,?,?,?,?,?,?)",(account,month,units,balance,days,late,future))
        except (ValueError,OverflowError) as exc:
            raise ValueError(f"CSV row {i}: {exc}") from exc
    if not regions:
        raise ValueError("CSV contains no data.")
    db.execute("INSERT INTO workspace VALUES (?,?)",(name,source))


def records(db, name):
    return pd.read_sql_query(sql(name),db).to_dict("records")


def run(db, objective):
    title, target = OBJECTIVES[objective]
    frame = pd.read_sql_query(sql("features"),db)
    if frame.empty:
        raise ValueError("No usable snapshots.")
    latest = frame.month.max()
    history = frame.loc[(frame.month<latest) & frame[target].notna()]
    months = sorted(history.month.unique())
    if len(months)<4:
        raise ValueError("Provide at least four labelled historical months and a later scoring month.")
    cut = months[max(1,int(len(months)*.75))]
    train = history.loc[history.month<cut]
    test = history.loc[history.month>=cut]
    scoring = frame.loc[frame.month==latest].copy()
    classify = objective=="collections"
    if classify and min(train[target].nunique(),test[target].nunique())<2:
        raise ValueError("Collections requires both outcomes in training and holdout.")
    transform = ColumnTransformer([
        ("numeric",make_pipeline(SimpleImputer(strategy="median",keep_empty_features=True),
                                 StandardScaler()),FEATURES[:-1]),
        ("region",OneHotEncoder(handle_unknown="ignore"),["region"])])
    model = make_pipeline(transform,LogisticRegression(max_iter=500) if classify else Ridge(alpha=5))
    X,y = train[FEATURES],train[target]
    model.fit(X,y)
    def predict(est, rows):
        return est.predict_proba(rows[FEATURES])[:,1] if classify else np.maximum(0,est.predict(rows[FEATURES]))
    metric = average_precision_score if classify else mean_absolute_error
    score = metric(test[target],predict(model,test))
    baseline_predictions = np.full(len(test), y.mean()) if classify else test.units
    reference = metric(test[target],baseline_predictions)
    impacts = permutation_importance(model,test[FEATURES],test[target],n_repeats=4,random_state=42,
                                      scoring="average_precision" if classify else "neg_mean_absolute_error")
    forecast_method = None
    if not classify and reference <= score:
        forecast_method = "Repeat current month’s units"
        scoring["prediction"] = scoring.units
    else:
        if not classify:
            forecast_method = "Ridge regression"
        model.fit(history[FEATURES],history[target])
        scoring["prediction"] = predict(model,scoring)
    rank = scoring.sort_values(["prediction","account"],ascending=[False,True])
    trends = records(db,"trends")
    for r in trends:
        if pd.isna(r["late_pct"]):
            r["late_pct"]=None
    return dict(title=title,objective=objective,latest=latest,first_test=cut,last_test=months[-1],
                train=len(train),test=len(test),score=round(score,4),baseline=round(reference,4),
                metric="Average precision" if classify else "Mean absolute error",accounts=len(scoring),
                estimate=round(float(scoring.prediction.sum()),1),balance=round(float(scoring.balance.sum()),2),
                drivers=sorted([dict(name=label,value=round(float(v),4)) for label,v in
                                zip(LABELS,impacts.importances_mean)],key=lambda d:-d["value"]),
                predictions=rank[["account","region","prediction"]].round(4).to_dict("records"),
                quality=records(db,"quality")[0],trends=trends,
                **({"forecast_method":forecast_method} if not classify else {}))

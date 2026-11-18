# Meridian

Meridian is a local analytics app for wholesale collections and demand planning. It loads a monthly account CSV into SQLite, evaluates forecasts on later months, and shows account-level results in a dashboard with CSV export and a print view.

## Run locally

Use Python 3.11 or 3.12. From the project folder on Windows:

```powershell
py -3.12 -m venv .venv
.\.venv\Scripts\python -m pip install -r requirements.txt
.\.venv\Scripts\python app.py
```

On macOS or Linux:

```bash
python3 -m venv .venv
.venv/bin/python -m pip install -r requirements.txt
.venv/bin/python app.py
```

Open [localhost:8000](http://127.0.0.1:8000), enter a workspace name, and choose the wholesale demo or upload a CSV. Open **Model & quality** for the holdout comparison and data checks. Switch objectives from the dashboard. Use **Export CSV** for account-level predictions or **Print report** to save a PDF.

Live briefs require `SNWOLLEY_API_KEY` in the server's environment before launch. The dashboard and saved collections brief work without a key. See [configuration](.env.example).

## Demo results

The demo follows 180 fictional wholesale accounts in four Ghanaian cities from January 2024 through June 2025. The January–May 2025 snapshots form the evaluation holdout. The June snapshots are used to forecast July.

| Objective | Model | Baseline | Forecast used |
| --- | --- | --- | --- |
| Collections | 0.4969 average precision | 0.1765 average precision for a constant training late rate | Logistic regression ranks 179 accounts and estimates 39.0 late accounts in total. |
| Demand | 8.3388 mean absolute error | 8.1531 mean absolute error for repeating the snapshot month's units | The baseline gives a July forecast of 15,535 units. |

The collection total is the sum of predicted probabilities. Demand uses ridge regression if it improves on the baseline and uses the baseline on ties. These scores describe the synthetic dataset. A deployment would need validation on real account history and checks for forecast error, drift, and collections precision at the team's outreach capacity.

## Upload format

Use the [sample CSV](data/wholesale.csv) as a template. Headers must appear in this order:

| Column | Meaning |
| --- | --- |
| `account` | Stable pseudonymous ID using letters, digits, underscores, or hyphens |
| `region` | One region per account |
| `month` | Snapshot month in YYYY-MM format |
| `units` | Whole units ordered in the snapshot month |
| `balance` | Outstanding receivables in GHS |
| `prior_days` | Days overdue on the previous completed invoice, optional |
| `next_late` | Whether the following month's invoice paid late (0 or 1) |
| `next_units` | Whole units ordered in the following month |

Leave unknown outcomes blank. Supply at least four labelled historical months plus a later scoring month. Collections also needs both outcomes in the training and holdout slices. The limit is 5 MB and 50,000 rows.

The SQLite staging table preserves raw observations. The clean view keeps the first row per account and month and drops negative balances or volumes. The first-row rule assumes duplicates are retransmissions. The rolling volume feature uses the last three available observations, which may span more than three months. The demo assumes historical labels are available at the forecast cutoff. For slower invoice settlement, exclude labels that had not yet matured at each cutoff.

## Management brief

The Snwolley adapter sends forecast totals, evaluation metrics, feature importance and data-quality counts. Account IDs, region labels, workspace names, and individual records stay local. The app shows the evidence next to the brief so users can check dates, figures, and recommendations. The [saved collections brief](data/review-brief.txt) demonstrates the output.

## Development

```text
python generate.py --seed 42
python -m unittest -v
```

Use the virtual environment's Python for both commands. The generator rebuilds the sample CSV. The [evaluation notebook](notebooks/evaluation.ipynb) runs both objectives. The [SQL directory](sql/) contains the schema, feature queries, and data-quality checks. See the [architecture note](docs/Architecture.pdf) and [sample report](docs/Sample_Collections_Report.pdf) for the system layout and example output.

Meridian runs on a trusted local machine. The browser cookie grants access to its workspace. A new workspace replaces that cookie. Shared deployment would require user accounts, durable workspace storage, and job and rate-limit coordination across workers.

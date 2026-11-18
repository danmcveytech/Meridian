"""Generate a reproducible panel of month-end wholesale account snapshots."""
import argparse
import csv
from pathlib import Path
import numpy as np

FIELDS = "account region month units balance prior_days next_late next_units".split()
ROOT = Path(__file__).resolve().parent


def generate(path, seed=42, customers=180, months=18):
    rng = np.random.default_rng(seed)
    rows = []
    for i in range(customers):
        region = rng.choice(["Accra", "Kumasi", "Tamale", "Takoradi"])
        scale = rng.lognormal(4.2, .55)
        risk = rng.normal()
        units = int(rng.poisson(scale))
        days = int(max(0, rng.normal(8 + 4*risk, 6)))
        for t in range(months):
            month = f"{2024+t//12}-{1+t%12:02d}"
            balance = round(units*rng.uniform(9, 23)*rng.uniform(.2, 1.2), 2)
            prob = 1/(1+np.exp(-(-3.2 + .16*days + .0005*balance + .4*risk)))
            late = int(rng.random() < prob)
            upcoming = int(rng.poisson(.58*units + .42*scale*(1+.15*np.sin((t+1)*np.pi/6))))
            rows.append([f"C{i+1:04}",region,month,units,balance,days if rng.random()>.045 else "",
                         late if t<months-1 else "",upcoming if t<months-1 else ""])
            days = int(max(0, rng.normal(16 if late else 4, 5)))
            units = upcoming
    extras = [r.copy() for r in rows[::107]]
    for r in rows[31::211]:
        r[4] = -abs(r[4])-1
    with Path(path).open("w", newline="", encoding="utf8") as f:
        writer = csv.writer(f)
        writer.writerow(FIELDS)
        writer.writerows(rows + extras)


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--seed", type=int, default=42)
    parser.add_argument("--output", default=ROOT/"data"/"wholesale.csv")
    args = parser.parse_args()
    generate(args.output, args.seed)

"""Aggregate-only interpretation request to the assignment endpoint."""
import json
import os
import re
from datetime import date, timedelta
from urllib.error import HTTPError, URLError
from urllib.request import Request, build_opener, HTTPRedirectHandler

ENDPOINT = "https://v1.snwolley.ai/v1/chat/completions/assignment"


class NoRedirect(HTTPRedirectHandler):
    def redirect_request(self, *args):
        return None


class AgentError(Exception):
    pass


def evidence(r):
    next_month=(date.fromisoformat(r["latest"]+"-01").replace(day=28)+timedelta(days=4)).strftime("%Y-%m")
    return {"E1": {"objective":r["title"],"snapshot_month":r["latest"],"forecast_month":next_month,"accounts":r["accounts"],
                   "expected_late_accounts" if r["objective"]=="collections" else "forecast_units":r["estimate"],
                   **({"forecast_method":r["forecast_method"]} if "forecast_method" in r else {})},
            "E2": {**{k:r[k] for k in ["metric","score","baseline","first_test","last_test"]},
                   "test_account_month_rows":r["test"],"evaluation_training_rows":r["train"],
                   "baseline_method":"training late rate" if r["objective"]=="collections" else "repeat last month units"},
            "E3": {"most_influential_feature":r["drivers"][0]["name"],
                   "holdout_permutation_importance":r["drivers"][0]["value"]},
            "E4": {"raw_rows":r["quality"]["raw_rows"],"all_usable_snapshots_including_scoring":r["quality"]["clean_rows"]}}


def narrative(payload):
    if isinstance(payload,str):
        return payload.strip()
    if isinstance(payload,dict):
        for key in ("choices","message","content","response","answer","reply","text","data","output"):
            if key in payload:
                value=narrative(payload[key])
                if value:
                    return value
    if isinstance(payload,list) and payload:
        return narrative(payload[0])
    return ""


def generate_brief(r):
    key=os.getenv("SNWOLLEY_API_KEY","").strip()
    if not key:
        raise AgentError("Set SNWOLLEY_API_KEY on the server, then generate the brief.")
    prompt=("Write a concise management brief in plain text using only the evidence supplied. "
            "Explain the forecast, compare the model against its baseline and recommend one reversible action. "
            "Cite the relevant evidence IDs in square brackets. Acknowledge uncertainty. "
            "Distinguish scoring month from forecast month, rows from distinct accounts, and usable rows from training rows. Do not infer sign from permutation importance. Treat feature importance as association. Avoid invented numbers, causes, guarantees or savings. "
            "If a forecast method is supplied, identify it as the source of the forecast. Feature importance describes the fitted model only. "
            "Average precision is higher-is-better; mean absolute error is lower-is-better. Evidence: "+
            json.dumps(evidence(r)))
    req=Request(ENDPOINT,data=json.dumps({"message":prompt,"stream":False}).encode(),
                headers={"X-API-Key":key,"Content-Type":"application/json"})
    try:
        with build_opener(NoRedirect()).open(req,timeout=25) as response:
            body=response.read(65537)
        if len(body)>65536:
            raise AgentError("Agent response exceeded the size limit.")
        brief=narrative(json.loads(body))
        if not brief or len(brief)>10000:
            raise AgentError("Agent returned an unreadable brief. Try again.")
        if not all(re.search(r"\[[^\]]*\b"+tag+r"\b[^\]]*\]",brief) for tag in ("E1","E2")):
            raise AgentError("Draft omitted forecast or evaluation citations. Generate again.")
        return brief
    except HTTPError as e:
        if e.code==429:
            delay=e.headers.get("Retry-After","60")
            raise AgentError(f"Agent rate limit reached. Retry in {delay if delay.isdigit() else '60'} seconds.") from None
        raise AgentError("The agent rejected the request. Check the server key." if e.code==401
                         else f"Agent returned HTTP {e.code}. Try again later.") from None
    except (URLError,TimeoutError,ValueError,OSError):
        raise AgentError("Agent unavailable or returned invalid JSON. Local analysis is available.") from None

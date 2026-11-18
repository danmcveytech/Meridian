import io
from contextlib import closing
import json
import logging
import os
from pathlib import Path
import secrets
import sqlite3
from threading import Lock
from weakref import WeakValueDictionary
from fastapi import FastAPI, Request, HTTPException
from fastapi.responses import FileResponse, JSONResponse
from fastapi.staticfiles import StaticFiles
from starlette.concurrency import run_in_threadpool
from analytics import ROOT, OBJECTIVES, ingest, run
from agent import generate_brief, AgentError, evidence

app=FastAPI(title="Meridian Analytics",docs_url=None,redoc_url=None)
STORE=Path(os.getenv("MERIDIAN_STORE",ROOT/".workspaces"))
STORE.mkdir(mode=0o700,parents=True,exist_ok=True)
app.mount("/assets",StaticFiles(directory=ROOT/"static"),name="assets")
logger=logging.getLogger("uvicorn.error")
brief_locks=WeakValueDictionary()
brief_locks_guard=Lock()


@app.middleware("http")
async def guard(request,call_next):
    if request.method=="POST" and request.headers.get("X-Meridian")!="workspace":
        return JSONResponse({"detail":"Invalid request origin."},403)
    result=await call_next(request)
    result.headers.update({"Cache-Control":"no-store","X-Content-Type-Options":"nosniff",
                           "Referrer-Policy":"no-referrer","X-Frame-Options":"DENY"})
    return result


@app.get("/")
def index():
    return FileResponse(ROOT/"templates/index.html")


@app.get("/sample.csv")
def sample():
    return FileResponse(ROOT/"data/wholesale.csv",filename="wholesale.csv")


def session_path(request):
    token=request.cookies.get("meridian","")
    if len(token)!=64 or any(c not in "0123456789abcdef" for c in token):
        raise HTTPException(401,"Create a workspace first.")
    path=STORE/(token+".db")
    if not path.is_file():
        raise HTTPException(401,"Workspace expired.")
    return path


def create_workspace(body,name,objective,custom):
    token=secrets.token_hex(32)
    path=STORE/(token+".db")
    try:
        with closing(sqlite3.connect(path)) as db, db:
            stream=io.StringIO(body.decode("utf-8-sig")) if custom else (ROOT/"data/wholesale.csv").open()
            with stream:
                ingest(db,stream,name,"Uploaded CSV" if custom else "Synthetic demo")
            result=run(db,objective)
            db.execute("INSERT INTO reports VALUES (?,?,NULL)",(objective,json.dumps(result)))
    except BaseException:
        path.unlink(missing_ok=True)
        raise
    logger.info("Workspace created with objective %s",objective)
    return token


@app.post("/api/workspace")
async def create(request:Request,name:str,objective:str="collections",custom:bool=False):
    name=name.strip()
    if not 1<=len(name)<=70 or objective not in OBJECTIVES:
        raise HTTPException(422,"Enter a business name and choose a supported objective.")
    body=bytearray()
    async for part in request.stream():
        if len(body)+len(part)>5_000_000:
            raise HTTPException(413,"CSV limit is 5 MB.")
        body.extend(part)
    try:
        token=await run_in_threadpool(create_workspace,body,name,objective,custom)
    except (ValueError,UnicodeError) as e:
        raise HTTPException(422,str(e))
    result=JSONResponse({"objective":objective})
    result.set_cookie("meridian",token,httponly=True,samesite="strict",secure=os.getenv("COOKIE_SECURE")=="1",max_age=2592000)
    return result


def load_report(db,objective):
    if objective not in OBJECTIVES:
        raise HTTPException(422,"Unknown objective.")
    row=db.execute("SELECT result,brief FROM reports WHERE objective=?",(objective,)).fetchone()
    if row:
        cached=json.loads(row[0])
        if objective!="demand" or "forecast_method" in cached:
            return cached,row[1]
    try:
        r=run(db,objective)
    except ValueError as e:
        raise HTTPException(422,str(e))
    # Replace legacy demand forecasts and their briefs without overwriting a concurrent refresh.
    db.execute(
        """INSERT INTO reports VALUES (?,?,NULL)
           ON CONFLICT(objective) DO UPDATE SET result=excluded.result, brief=NULL
           WHERE reports.result=?""",
        (objective,json.dumps(r),row[0] if row else None),
    )
    result,brief=db.execute("SELECT result,brief FROM reports WHERE objective=?",(objective,)).fetchone()
    return json.loads(result),brief


@app.get("/api/report")
def report(request:Request,objective:str=""):
    with closing(sqlite3.connect(session_path(request))) as db, db:
        if not objective:
            objective=db.execute("SELECT objective FROM reports ORDER BY rowid LIMIT 1").fetchone()[0]
        r,brief=load_report(db,objective)
        name,source=db.execute("SELECT * FROM workspace").fetchone()
    return {**r,"name":name,"source":source,"brief":brief,"evidence":evidence(r)}


@app.get("/api/sample-brief")
def sample_brief(request:Request):
    with closing(sqlite3.connect(session_path(request))) as db, db:
        r,_=load_report(db,"collections")
        source=db.execute("SELECT source FROM workspace").fetchone()[0]
    saved=json.loads((ROOT/"data/review-evidence.json").read_text())
    if source!="Synthetic demo" or evidence(r)!=saved:
        raise HTTPException(409,"Saved example belongs to the original demo dataset.")
    return {"brief":(ROOT/"data/review-brief.txt").read_text()}


@app.post("/api/brief")
def brief(request:Request,objective:str):
    path=session_path(request)
    with brief_locks_guard:
        lock=brief_locks.get((path,objective))
        if lock is None:
            lock=Lock()
            brief_locks[path,objective]=lock
    with lock:
        with closing(sqlite3.connect(path)) as db, db:
            r,existing=load_report(db,objective)
            if existing:
                return {"brief":existing}
        try:
            output=generate_brief(r)
        except AgentError as e:
            logger.warning("Agent brief unavailable for %s",objective)
            raise HTTPException(503,str(e))
        with closing(sqlite3.connect(path)) as db, db:
            db.execute("UPDATE reports SET brief=? WHERE objective=?",(output,objective))
    return {"brief":output}


if __name__=="__main__":
    import uvicorn
    uvicorn.run(app,host="127.0.0.1",port=8000,access_log=False)

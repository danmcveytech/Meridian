import io
import json
import sqlite3
import unittest
from concurrent.futures import ThreadPoolExecutor
from contextlib import closing
from threading import Barrier, BrokenBarrierError
from types import SimpleNamespace
from unittest.mock import patch
from tempfile import TemporaryDirectory
import app
from analytics import OBJECTIVES, ROOT, ingest, run
from agent import generate_brief, evidence, AgentError


class PipelineTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.db=sqlite3.connect(":memory:")
        with (ROOT/"data/wholesale.csv").open() as f:
            ingest(cls.db,f,"Demo","Synthetic demo")
        cls.r=run(cls.db,"collections")

    def test_quality_and_temporal_split(self):
        r=self.r
        self.assertEqual(r["quality"]["clean_rows"],3224)
        self.assertEqual(r["train"]+r["test"]+r["accounts"],3224)
        self.assertLess(r["last_test"],r["latest"])
        self.assertGreater(r["score"],r["baseline"])
        self.assertTrue(all(0<=p["prediction"]<=1 for p in r["predictions"]))

    def test_demand(self):
        r=run(self.db,"demand")
        self.assertAlmostEqual(r["baseline"],8.1531,places=3)
        self.assertEqual(len(r["predictions"]),r["accounts"])
        expected=dict(self.db.execute("SELECT account,units FROM clean WHERE month=?",(r["latest"],)))
        self.assertEqual({p["account"]:p["prediction"] for p in r["predictions"]},expected)
        self.assertEqual(r["estimate"],sum(expected.values()))
        self.assertEqual(evidence(r)["E1"]["forecast_method"],r["forecast_method"])

    def test_bad_csv(self):
        with self.assertRaises(ValueError):
            ingest(sqlite3.connect(":memory:"),io.StringIO("bad\n1\n"),"Demo","Uploaded")

    def test_workspace_isolation(self):
        with TemporaryDirectory() as tmp, patch.object(app,"STORE",app.Path(tmp)):
            a=app.create_workspace(b"","One","collections",False)
            b=app.create_workspace(b"","Two","demand",False)
            self.assertNotEqual(a,b)
            for token,name in [(a,"One"),(b,"Two")]:
                with closing(sqlite3.connect(app.STORE/(token+".db"))) as db:
                    self.assertEqual(db.execute("SELECT name FROM workspace").fetchone()[0],name)

    def test_concurrent_briefs_share_one_generation(self):
        with TemporaryDirectory() as tmp, patch.object(app,"STORE",app.Path(tmp)):
            token=app.create_workspace(b"","Demo","collections",False)
            request=SimpleNamespace(cookies={"meridian":token})
            start=Barrier(2,timeout=5)
            overlap=Barrier(2,timeout=.5)

            def generate(_):
                try:
                    overlap.wait()
                except BrokenBarrierError:
                    pass
                return "Test brief [E1] [E2]"

            def request_brief(_):
                start.wait()
                return app.brief(request,"collections")

            with patch("app.generate_brief",side_effect=generate) as agent, ThreadPoolExecutor(2) as pool:
                first,second=pool.map(request_brief,range(2))
                self.assertEqual(first,second)
                agent.assert_called_once()

    def test_legacy_demand_forecast_and_brief_are_refreshed(self):
        with TemporaryDirectory() as tmp, patch.object(app,"STORE",app.Path(tmp)):
            token=app.create_workspace(b"","Demo","demand",False)
            path=app.STORE/(token+".db")
            with closing(sqlite3.connect(path)) as db, db:
                result=json.loads(db.execute("SELECT result FROM reports WHERE objective='demand'").fetchone()[0])
                del result["forecast_method"]
                result["estimate"]=15623.6
                db.execute("UPDATE reports SET result=?, brief='Old forecast'",(json.dumps(result),))
            request=SimpleNamespace(cookies={"meridian":token})
            r=app.report(request,"demand")
            self.assertEqual(r["estimate"],15535)
            self.assertIsNone(r["brief"])
            self.assertEqual(app.report(request,"demand"),r)

    def test_agent_contract(self):
        with patch.dict("os.environ",{"SNWOLLEY_API_KEY":"test-only"}),patch("agent.build_opener") as opener:
            opener.return_value.open.return_value.__enter__.return_value.read.return_value=json.dumps(
                {"choices":[{"message":{"content":"Review the queue [E1] and the holdout [E2]."}}]}).encode()
            self.assertIn("[E1]",generate_brief(self.r))
            req=opener.return_value.open.call_args.args[0]
            body=json.loads(req.data)
            self.assertFalse(body["stream"])
            self.assertNotIn("C0001",body["message"])
            self.assertEqual(evidence(self.r)["E1"]["forecast_month"],"2025-07")
            with patch.dict("os.environ",{"SNWOLLEY_API_KEY":""}),self.assertRaises(AgentError):
                generate_brief(self.r)

#!/usr/bin/env python3
"""Check baseline isolation, resource arithmetic and PBS generation safeguards."""
import contextlib
import io
import json
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest
from unittest.mock import patch

import analyze
import make_jobs


class WorkflowTests(unittest.TestCase):
    def record(self,variant="mpi",cores=2,seconds=2,**values):
        r=dict(cluster="TEST_ONLY",cpu_model="CPU-A",source_hash="source-A",build_signature="build-A",
            problem="polynomial",mode="benchmark",n=64,max_iters=100,check_interval=0,tolerance=1e-8,
            profile=False,family="strong",variant=variant,nodes=1,ranks=cores,threads=1,cores=cores,
            solve_seconds_max=seconds,iterations=100,final_residual=0.5,relative_error_l2=0.5,converged=False)
        r.update(values)
        return r

    def test_serial_baseline_isolation(self):
        baseline=self.record("serial",1,8)
        matching=self.record("mpi",2,2)
        wrong_cpu=self.record("hybrid",2,2,cpu_model="CPU-B")
        wrong_work=self.record("overlap",2,2,max_iters=200)
        wrong_code=self.record("mpi",4,1,source_hash="source-B")
        rows=analyze.summarize([baseline,matching,wrong_cpu,wrong_work,wrong_code])
        matched=next(r for r in rows if r["variant"]=="mpi" and r["source_hash"]=="source-A")
        self.assertEqual(matched["speedup"],4)
        self.assertEqual(matched["efficiency"],2)
        for r in rows:
            if r["cpu_model"]=="CPU-B" or r["max_iters"]==200 or r["source_hash"]=="source-B":
                self.assertEqual(r["speedup"],"")

    def test_weak_workload_guard(self):
        base=self.record(cores=1,seconds=2,family="weak",n=64)
        correct=self.record(cores=4,seconds=3,family="weak",n=128)
        wrong=self.record(cores=8,seconds=3,family="weak",n=128)
        rows=analyze.summarize([base,correct,wrong])
        self.assertAlmostEqual(next(r for r in rows if r["cores"]==4)["weak_efficiency"],2/3)
        self.assertEqual(next(r for r in rows if r["cores"]==8)["weak_efficiency"],"")

    def test_all_job_presets_and_guard(self):
        with tempfile.TemporaryDirectory(prefix="p3-job-test-") as tmp:
            root=Path(tmp)
            (root/"configs").mkdir()
            example=make_jobs.ROOT/"configs"/"cluster.env.example"
            original=example.read_text()
            (root/"configs"/"cluster.env").write_text(original)
            (root/"configs"/"site_modules.sh").write_text("# test-only module stub\n")
            with patch.object(make_jobs,"ROOT",root):
                with self.assertRaisesRegex(RuntimeError,"SITE_CONFIRMED"):
                    make_jobs.load_config()
                # Synthetic settings ONLY for generation/syntax tests; never submit.
                (root/"configs"/"cluster.env").write_text(original.replace("SITE_CONFIRMED=0","SITE_CONFIRMED=1")
                    .replace("QUEUE=UNSET","QUEUE=syntax_test_only")
                    .replace("MPI_PBS_INTEGRATED=0","MPI_PBS_INTEGRATED=1"))
                counts={"smoke":1,"verify":1,"strong":10,"weak":5,"mix":8,"comm":16,"check":6}
                for preset,expected in counts.items():
                    with patch.object(sys,"argv",["make_jobs","--preset",preset,"--n","64"]):
                        with contextlib.redirect_stdout(io.StringIO()): make_jobs.main()
                    folder=next((root/"jobs"/"generated").glob(preset+"-*"))
                    jobs=json.loads((folder/"manifest.json").read_text())
                    self.assertEqual(len(jobs),expected)
                    for j in jobs:
                        self.assertLessEqual(j["ppn"]*j["threads"],8)
                        subprocess.run(["bash","-n",j["script"]],check=True)
                        text=Path(j["script"]).read_text()
                        self.assertIn("#PBS -l place=scatter",text)
                        self.assertNotIn("--oversubscribe",text)


if __name__=="__main__": unittest.main()

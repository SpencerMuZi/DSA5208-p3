#!/usr/bin/env python3
"""Numerical validation; no third-party Python packages required."""
import argparse
import csv
import json
import math
import os
from pathlib import Path
import shlex
import subprocess
import sys
from datetime import datetime, timezone

ROOT = Path(__file__).resolve().parents[1]


def launcher_command(template, ranks, threads, ranks_per_node=None):
    values = dict(ranks=ranks, threads=threads, ranks_per_node=ranks_per_node or ranks)
    return [token.format(**values) for token in shlex.split(template)]


def read_grid(path):
    with path.open(newline="") as f:
        rows = list(csv.DictReader(f))
    values = [float(r["u"]) for r in rows]
    if not values or not all(math.isfinite(x) for x in values):
        raise RuntimeError(f"invalid grid: {path}")
    return [(int(r["i"]), int(r["j"])) for r in rows], values


def run(command, folder, name, threads=1, expected_code=0):
    env = os.environ.copy()
    env.update(OMP_NUM_THREADS=str(threads), OMP_DYNAMIC="FALSE")
    result = subprocess.run(command, cwd=ROOT, env=env, text=True,
                            capture_output=True, timeout=180)
    (folder / f"{name}.command.json").write_text(json.dumps(command, indent=2)+"\n")
    (folder / f"{name}.stdout.txt").write_text(result.stdout)
    (folder / f"{name}.stderr.txt").write_text(result.stderr)
    if result.returncode != expected_code:
        raise RuntimeError(f"{name}: exit {result.returncode}, expected {expected_code}; see {folder}")
    if expected_code == 1:
        return None
    records = [json.loads(s) for s in result.stdout.splitlines() if s.startswith('{"variant":')]
    if len(records) != 1:
        raise RuntimeError(f"{name}: expected one result JSON")
    r = records[0]
    for key in ("final_residual", "relative_error_l2", "error_max", "solve_seconds_max"):
        if not math.isfinite(r[key]):
            raise RuntimeError(f"{name}: non-finite {key}")
    return r


def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--serial-only", action="store_true")
    p.add_argument("--launcher", default="mpirun -np {ranks}")
    p.add_argument("--max-cores", type=int, default=4)
    p.add_argument("--output", type=Path)
    args = p.parse_args()
    if args.max_cores < 1:
        p.error("max-cores must be positive")
    stamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%S%fZ")
    folder = args.output or ROOT / "results" / "validation" / stamp
    folder.mkdir(parents=True, exist_ok=False)
    outcomes = []
    serial = str(ROOT / "bin" / "jacobi_serial")
    parallel = str(ROOT / "bin" / "jacobi_parallel")
    # Include uneven decomposition and local row counts of one or two.
    for n in (1, 3, 4, 5, 17, 31, 64):
        ref_path = folder / f"serial_n{n}.csv"
        fixed = ["--n", str(n), "--iters", "37", "--check", "0"]
        r = run([serial, *fixed, "--dump", str(ref_path)], folder, f"serial_n{n}")
        if r["iterations"] != 37:
            raise RuntimeError("benchmark did not execute exactly 37 iterations")
        coords, ref = read_grid(ref_path)
        if len(ref) != n*n:
            raise RuntimeError("wrong grid dimensions")
        if args.serial_only:
            continue
        for ranks in (1, 2, 3, 4):
            if ranks > n:
                continue
            for variant in ("mpi", "hybrid", "overlap"):
                for threads in ((1,) if variant == "mpi" else (1, 2, 4, 8)):
                    if ranks*threads > args.max_cores:
                        continue
                    name = f"{variant}_n{n}_p{ranks}_t{threads}"
                    output = folder / f"{name}.csv"
                    cmd = launcher_command(args.launcher, ranks, threads) + [parallel,
                        *fixed, "--variant", variant, "--threads", str(threads),
                        "--dump", str(output)]
                    result = run(cmd, folder, name, threads)
                    other_coords, actual = read_grid(output)
                    if coords != other_coords or result["iterations"] != 37:
                        raise RuntimeError(f"{name}: grid layout or iterations mismatch")
                    max_diff = max(abs(a-b) for a,b in zip(ref,actual))
                    relative_diff = math.sqrt(sum((a-b)**2 for a,b in zip(ref,actual)) /
                                              sum(a*a for a in ref))
                    if max_diff > 1e-12 or relative_diff > 1e-11:
                        raise RuntimeError(f"{name}: serial comparison failed: {max_diff}, {relative_diff}")
                    outcomes.append(dict(test=name, max_diff=max_diff,
                                         relative_diff=relative_diff, passed=True))
    for n in (17, 31):
        options = ["--n", str(n), "--mode", "solve", "--iters", "50000",
                   "--tol", "1e-8", "--check", "10"]
        r = run([serial, *options], folder, f"serial_solve_n{n}")
        if not r["converged"] or r["final_residual"] > 1e-8 or r["relative_error_l2"] > 2e-8:
            raise RuntimeError("serial analytic validation failed")
        outcomes.append(dict(test=f"serial_solve_n{n}", result=r, passed=True))
        if not args.serial_only:
            for variant in ("mpi", "hybrid", "overlap"):
                ranks = min(3, args.max_cores)
                threads = 2 if variant != "mpi" and ranks*2 <= args.max_cores else 1
                name = f"{variant}_solve_n{n}"
                cmd = launcher_command(args.launcher,ranks,threads) + [parallel,*options,
                    "--variant",variant,"--threads",str(threads)]
                other = run(cmd,folder,name,threads)
                if not other["converged"] or other["final_residual"] > 1e-8 or other["relative_error_l2"] > 2e-8:
                    raise RuntimeError(f"{name}: analytic validation failed")
                outcomes.append(dict(test=name,result=other,passed=True))
    # Refuse to silently report an unconverged solve as success.
    r = run([serial,"--n","31","--mode","solve","--iters","1"],folder,
            "unconverged_solve",expected_code=2)
    if r["converged"]:
        raise RuntimeError("unconverged test unexpectedly converged")
    outcomes.append(dict(test="unconverged_solve_exit_2",passed=True))
    run([serial,"--n","0"],folder,"invalid_n",expected_code=1)
    outcomes.append(dict(test="reject_invalid_n",passed=True))
    if not args.serial_only and args.max_cores >= 2:
        run(launcher_command(args.launcher,2,1)+[parallel,"--n","1"],folder,
            "reject_empty_partitions",expected_code=1)
        outcomes.append(dict(test="reject_empty_partitions",passed=True))
    summary = dict(scope="serial_only" if args.serial_only else "serial_and_MPI_OpenMP",
                   passed=True, checks=len(outcomes), cases=outcomes)
    (folder / "summary.json").write_text(json.dumps(summary,indent=2)+"\n")
    print(f"PASS: {len(outcomes)} checks; evidence: {folder}")


if __name__ == "__main__":
    try:
        main()
    except Exception as e:
        print(f"FAIL: {e}",file=sys.stderr)
        sys.exit(1)

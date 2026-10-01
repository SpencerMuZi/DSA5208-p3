#!/usr/bin/env python3
"""Run one configuration, recording every repetition and its provenance."""
import argparse
from collections import Counter
from datetime import datetime, timezone
import hashlib
import json
import math
import os
from pathlib import Path
import platform
import subprocess
import sys
import uuid

from validate import ROOT, launcher_command


def source_hash():
    digest = hashlib.sha256()
    for path in sorted([ROOT / "Makefile", *ROOT.glob("src/*"), *ROOT.glob("scripts/*.py"),
                        *ROOT.glob("scripts/*.sh")]):
        digest.update(str(path.relative_to(ROOT)).encode())
        digest.update(path.read_bytes())
    return digest.hexdigest()


def cpu_model():
    path = Path("/proc/cpuinfo")
    if path.exists():
        for line in path.read_text().splitlines():
            if line.startswith("model name"):
                return line.partition(":")[2].strip()
    return platform.processor() or platform.machine()


def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--variant",choices=("serial","mpi","hybrid","overlap"),required=True)
    p.add_argument("--n",type=int,required=True)
    p.add_argument("--iters",type=int,default=1000)
    p.add_argument("--mode",choices=("benchmark","solve"),default="benchmark")
    p.add_argument("--check",type=int,default=0)
    p.add_argument("--tol",type=float,default=1e-8)
    p.add_argument("--ranks",type=int,default=1)
    p.add_argument("--threads",type=int,default=1)
    p.add_argument("--ranks-per-node",type=int)
    p.add_argument("--nodes",type=int,default=1)
    p.add_argument("--repeats",type=int,default=5)
    p.add_argument("--launcher",default="mpirun -np {ranks}")
    p.add_argument("--cluster",default="LOCAL_UNOFFICIAL")
    p.add_argument("--family",default="development")
    p.add_argument("--profile",action="store_true")
    p.add_argument("--output",type=Path)
    p.add_argument("--timeout",type=int,default=3600)
    args = p.parse_args()
    if min(args.ranks,args.threads,args.nodes,args.repeats,args.timeout) < 1:
        p.error("ranks, threads, nodes, repeats, timeout must be positive")
    if args.variant == "serial" and (args.ranks != 1 or args.threads != 1 or args.nodes != 1):
        p.error("serial requires ranks=threads=nodes=1")
    if args.variant == "mpi" and args.threads != 1:
        p.error("mpi requires threads=1")
    ppn = args.ranks_per_node or args.ranks // args.nodes
    if ppn*args.nodes != args.ranks:
        p.error("uniform ranks_per_node*nodes must equal ranks")
    if args.cluster in ("Atlas","Vanda") and not (os.environ.get("PBS_JOBID") or os.environ.get("SLURM_JOB_ID")):
        p.error("official cluster label requires a scheduler allocation")
    stamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%S%fZ")
    run_id = stamp + "-" + uuid.uuid4().hex[:8]
    folder = args.output or ROOT / "results" / "raw" / run_id
    folder.mkdir(parents=True,exist_ok=False)
    binary = ROOT / "bin" / ("jacobi_serial" if args.variant == "serial" else "jacobi_parallel")
    command = [] if args.variant == "serial" else launcher_command(args.launcher,args.ranks,args.threads,ppn)
    command += [str(binary),"--variant",args.variant,"--n",str(args.n),"--iters",str(args.iters),
                "--mode",args.mode,"--check",str(args.check),"--tol",str(args.tol),
                "--threads",str(args.threads)]
    if args.profile:
        command.append("--profile")
    env = os.environ.copy()
    env.update(OMP_NUM_THREADS=str(args.threads),OMP_DYNAMIC="FALSE")
    hosts=[]
    nodefile = os.environ.get("PBS_NODEFILE")
    if nodefile and Path(nodefile).exists():
        hosts=sorted(set(Path(nodefile).read_text().splitlines()))
    metadata = dict(run_id=run_id,date_utc=stamp,cluster=args.cluster,family=args.family,
                    nodes=args.nodes,ranks_per_node=ppn,hosts=hosts,
                    cpu_model=cpu_model(),source_hash=source_hash(),command=command,
                    binary_sha256=hashlib.sha256(binary.read_bytes()).hexdigest(),
                    job_id=os.environ.get("PBS_JOBID",os.environ.get("SLURM_JOB_ID","local")),
                    binding={k:env.get(k,"") for k in ("OMP_PLACES","OMP_PROC_BIND","OMP_DYNAMIC")})
    if hosts and len(hosts)!=args.nodes:
        raise RuntimeError(f"allocation contains {len(hosts)} hosts, expected {args.nodes}")
    build_info = ROOT / "results" / "build" / "build.txt"
    if args.cluster in ("Atlas","Vanda") and not build_info.exists():
        raise RuntimeError("official runs require results/build/build.txt from scripts/build.sh")
    if build_info.exists():
        metadata["build_info"] = build_info.read_text()
        # Ignore timestamp/hostname lines while retaining compiler versions and flags.
        signature_lines=metadata["build_info"].splitlines()[2:]
        metadata["build_signature"]=hashlib.sha256('\n'.join(signature_lines).encode()).hexdigest()
    else:
        metadata["build_signature"]="UNRECORDED"
    (folder/"metadata.json").write_text(json.dumps(metadata,indent=2)+"\n")
    # All MPI configurations record actual host/thread placement using the same launcher.
    if args.variant != "serial":
        topology_cmd = launcher_command(args.launcher,args.ranks,args.threads,ppn)+[str(ROOT/"bin"/"hello_hybrid")]
        topo=subprocess.run(topology_cmd,cwd=ROOT,env=env,capture_output=True,text=True,timeout=120)
        (folder/"topology.command.json").write_text(json.dumps(topology_cmd,indent=2)+"\n")
        (folder/"topology.stdout.jsonl").write_text(topo.stdout)
        (folder/"topology.stderr.txt").write_text(topo.stderr)
        if topo.returncode:
            raise RuntimeError("topology launch failed")
        records=[json.loads(s) for s in topo.stdout.splitlines() if s.startswith('{"rank":')]
        if len(records)!=args.ranks or any(r["threads"]!=args.threads for r in records):
            raise RuntimeError("actual ranks/threads differ from requested configuration")
        if sorted(r["rank"] for r in records)!=list(range(args.ranks)):
            raise RuntimeError("topology rank IDs are missing or duplicated")
        if len(set(r["host"] for r in records))!=args.nodes:
            raise RuntimeError("actual MPI host count differs from requested nodes")
        if any(count!=ppn for count in Counter(r["host"] for r in records).values()):
            raise RuntimeError("actual ranks per host differ from requested uniform layout")
    with (folder/"measurements.jsonl").open("w") as output:
        # Warm-up repeats the identical workload. Each invocation allocates a fresh zero grid.
        for repeat in range(args.repeats+1):
            process=subprocess.run(command,cwd=ROOT,env=env,text=True,capture_output=True,timeout=args.timeout)
            label="warmup" if repeat==0 else f"repeat-{repeat}"
            (folder/f"{label}.stdout.txt").write_text(process.stdout)
            (folder/f"{label}.stderr.txt").write_text(process.stderr)
            if process.returncode:
                raise RuntimeError(f"{label}: solver exit {process.returncode}; see {folder}")
            result=[json.loads(s) for s in process.stdout.splitlines() if s.startswith('{"variant":')]
            if len(result)!=1:
                raise RuntimeError(f"{label}: expected exactly one result JSON")
            record=result[0]
            if any(not math.isfinite(record[k]) for k in ("solve_seconds_max","final_residual","relative_error_l2","error_max")):
                raise RuntimeError("non-finite numerical result")
            if record["ranks"]!=args.ranks or record["threads"]!=args.threads:
                raise RuntimeError("solver rank/thread count mismatch")
            if args.mode=="benchmark" and record["iterations"]!=args.iters:
                raise RuntimeError("fixed-work benchmark iteration count mismatch")
            if args.mode=="solve" and not record["converged"]:
                raise RuntimeError("unconverged solve must not be included as a completed solve")
            if repeat:
                record.update(metadata)
                record["repeat"]=repeat
                output.write(json.dumps(record)+"\n")
                output.flush()
                print(f"{label}: {record['solve_seconds_max']:.6f}s residual={record['final_residual']:.3e}")
    (folder/"COMPLETE").write_text("All requested repetitions completed.\n")
    print(f"Evidence: {folder}")


if __name__ == "__main__":
    try:
        main()
    except Exception as e:
        print(f"ERROR: {e}",file=sys.stderr)
        sys.exit(1)

#!/usr/bin/env python3
"""Generate reviewable PBS scripts; this program never submits jobs."""
import argparse
from datetime import datetime, timezone
import json
from pathlib import Path
import re
import shlex
import subprocess
import sys

from validate import ROOT


def load_config():
    config = ROOT / "configs" / "cluster.env"
    if not config.exists():
        raise RuntimeError("copy configs/cluster.env.example to configs/cluster.env and fill site settings")
    # Source trusted local shell settings without eval-ing text inside Python.
    names = ("SITE_CONFIRMED", "CLUSTER_NAME", "SCHEDULER", "QUEUE", "PROJECT_CODE",
             "PROJECT_FLAG", "MPI_FLAVOR", "MPI_PBS_INTEGRATED", "MAX_CPUS_PER_NODE",
             "MEMORY_PER_NODE", "WALLTIME", "OMP_PLACES", "OMP_PROC_BIND")
    script = 'set -eu\nsource "$1"\n' + ''.join('printf "%s\\0" "${'+n+'-}"\n' for n in names)
    result=subprocess.run(["bash","-c",script,"config",str(config)],capture_output=True,check=True)
    fields=result.stdout.decode().split('\0')[:-1]
    c=dict(zip(names,fields))
    if c["SITE_CONFIRMED"]!="1":
        raise RuntimeError("SITE_CONFIRMED=0: verify site-specific settings first")
    if c["SCHEDULER"]!="PBS":
        raise RuntimeError("this generator targets PBS; do not use it on a Slurm site")
    if c["CLUSTER_NAME"] not in ("Atlas","Vanda"):
        raise RuntimeError("CLUSTER_NAME must be Atlas or Vanda")
    if c["MPI_FLAVOR"]!="openmpi" or c["MPI_PBS_INTEGRATED"]!="1":
        raise RuntimeError("verify Open MPI/PBS integration or adapt launcher with TA before generating jobs")
    if c["QUEUE"]=="UNSET":
        raise RuntimeError("set QUEUE to the approved queue, or empty only if default routing is approved")
    for name in ("QUEUE","PROJECT_CODE"):
        if c[name] and not re.fullmatch(r"[A-Za-z0-9_.@-]+",c[name]):
            raise RuntimeError(f"invalid PBS token for {name}")
    if c["PROJECT_FLAG"] not in ("-P","-A"):
        raise RuntimeError("PROJECT_FLAG must be -P or -A")
    if not re.fullmatch(r"[1-9][0-9]*(mb|gb)",c["MEMORY_PER_NODE"],re.I):
        raise RuntimeError("MEMORY_PER_NODE must be e.g. 2gb")
    if not re.fullmatch(r"[0-9]+:[0-5][0-9]:[0-5][0-9]",c["WALLTIME"]):
        raise RuntimeError("WALLTIME must use HH:MM:SS")
    if c["OMP_PLACES"] not in ("cores","threads") or c["OMP_PROC_BIND"] not in ("close","spread"):
        raise RuntimeError("use OMP_PLACES=cores|threads and OMP_PROC_BIND=close|spread")
    if int(c["MAX_CPUS_PER_NODE"])<1:
        raise RuntimeError("MAX_CPUS_PER_NODE must be positive")
    if not (ROOT/"configs"/"site_modules.sh").exists():
        raise RuntimeError("copy and fill configs/site_modules.sh first")
    return c


def main():
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument("--preset",choices=("smoke","verify","strong","weak","mix","comm","check"),required=True)
    p.add_argument("--n",type=int,default=512)
    p.add_argument("--iters",type=int,default=1000)
    p.add_argument("--repeats",type=int,default=5)
    p.add_argument("--cpus-per-node",type=int,default=8)
    p.add_argument("--nodes-list",default="1,2")
    p.add_argument("--single-node-cores",default="1,2,4,8")
    p.add_argument("--mix-threads",default="1,2,4,8")
    p.add_argument("--strong-threads",type=int,default=2)
    p.add_argument("--profile",action="store_true")
    args=p.parse_args()
    c=load_config()
    if min(args.n,args.iters,args.repeats,args.cpus_per_node)<1:
        p.error("n, iters, repeats, cpus-per-node must be positive")
    if args.cpus_per_node>int(c["MAX_CPUS_PER_NODE"]):
        p.error("cpus-per-node exceeds approved MAX_CPUS_PER_NODE")
    def ints(value):
        result=sorted(set(map(int,value.split(','))))
        if not result or min(result)<1: p.error("lists must contain positive integers")
        return result
    nodes_list=ints(args.nodes_list)
    cores_list=ints(args.single_node_cores)
    threads_list=ints(args.mix_threads)
    jobs=[]
    def add(variant,nodes,ppn,threads,n=None,mode="benchmark",check=0):
        n=args.n if n is None else n
        if ppn*threads>int(c["MAX_CPUS_PER_NODE"]):
            p.error("configuration exceeds MAX_CPUS_PER_NODE")
        if nodes*ppn>n:
            p.error("configuration has more ranks than interior rows")
        jobs.append(dict(variant=variant,nodes=nodes,ppn=ppn,threads=threads,n=n,mode=mode,check=check))
    if args.preset=="smoke":
        add("overlap",2,1,2,n=31)
    elif args.preset=="verify":
        add("verify",1,4,1,n=31)
    elif args.preset=="strong":
        add("serial",1,1,1)
        for cores in cores_list:
            if cores>args.cpus_per_node: p.error("single-node-cores exceeds cpus-per-node")
            add("mpi",1,cores,1)
        for nodes in nodes_list:
            if nodes>1: add("mpi",nodes,args.cpus_per_node,1)
        if args.strong_threads<1 or args.cpus_per_node%args.strong_threads:
            p.error("strong-threads must be positive and divide cpus-per-node")
        for cores in cores_list:
            if cores>=args.strong_threads and cores%args.strong_threads==0:
                add("hybrid",1,cores//args.strong_threads,args.strong_threads)
        for nodes in nodes_list:
            if nodes>1:
                add("hybrid",nodes,args.cpus_per_node//args.strong_threads,args.strong_threads)
    elif args.preset=="weak":
        # n is the reference single-core grid; n² / cores approximately constant.
        for cores in cores_list:
            if cores>args.cpus_per_node: p.error("single-node-cores exceeds cpus-per-node")
            add("mpi",1,cores,1,n=round(args.n*cores**0.5))
        for nodes in nodes_list:
            if nodes>1: add("mpi",nodes,args.cpus_per_node,1,n=round(args.n*(nodes*args.cpus_per_node)**0.5))
    elif args.preset in ("mix","comm"):
        for nodes in nodes_list:
            for threads in threads_list:
                if args.cpus_per_node%threads: p.error("mix-threads must divide cpus-per-node")
                ppn=args.cpus_per_node//threads
                variants=("hybrid","overlap") if args.preset=="comm" else (("mpi",) if threads==1 else ("hybrid",))
                for variant in variants: add(variant,nodes,ppn,threads)
    else:
        for nodes in nodes_list:
            for check in (1,10,50):
                add("hybrid",nodes,args.cpus_per_node//2,2,n=args.n,mode="solve",check=check)
        if args.cpus_per_node%2: p.error("check preset requires even cpus-per-node")
    stamp=datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%S%fZ")
    folder=ROOT/"jobs"/"generated"/(args.preset+"-"+stamp)
    folder.mkdir(parents=True)
    manifest=[]
    launcher="mpirun -np {ranks} --map-by ppr:{ranks_per_node}:node:PE={threads} --bind-to core -x OMP_NUM_THREADS -x OMP_PLACES -x OMP_PROC_BIND"
    for number,j in enumerate(jobs,1):
        name=f"p3-{args.preset}-{number}"
        directives=["#!/bin/bash",f"#PBS -N {name}","#PBS -j oe",
          f"#PBS -l select={j['nodes']}:ncpus={j['ppn']*j['threads']}:mpiprocs={j['ppn']}:ompthreads={j['threads']}:mem={c['MEMORY_PER_NODE']}",
          "#PBS -l place=scatter",f"#PBS -l walltime={c['WALLTIME']}"]
        if c["QUEUE"]: directives.append(f"#PBS -q {c['QUEUE']}")
        if c["PROJECT_CODE"]: directives.append(f"#PBS {c['PROJECT_FLAG']} {c['PROJECT_CODE']}")
        lines=directives+["set -euo pipefail",f"cd {shlex.quote(str(ROOT))}",
            "source configs/site_modules.sh",f"export OMP_PLACES={c['OMP_PLACES']}",
            f"export OMP_PROC_BIND={c['OMP_PROC_BIND']}","export OMP_DYNAMIC=FALSE",
            f"export OMP_NUM_THREADS={j['threads']}",
            'test -n "${PBS_JOBID:-}"', 'test -f "${PBS_NODEFILE:-}"',
            'printf "JOB_ID=%s\\n" "$PBS_JOBID"',
            'sort "$PBS_NODEFILE" | uniq -c',"hostname","date -u",
            'if command -v lscpu >/dev/null 2>&1; then lscpu; fi',
            "mpirun --version",'if type module >/dev/null 2>&1; then module -t list 2>&1; fi']
        if j["variant"]=="verify":
            command=["python3","scripts/validate.py","--max-cores","4","--launcher",
                     "mpirun -np {ranks} --map-by slot:PE={threads} --bind-to core"]
        else:
            command=["python3","scripts/benchmark.py","--variant",j["variant"],"--n",str(j["n"]),
                     "--iters",str(args.iters),"--mode",j["mode"],"--check",str(j["check"]),
                     "--nodes",str(j["nodes"]),"--ranks",str(j["nodes"]*j["ppn"]),
                     "--ranks-per-node",str(j["ppn"]),"--threads",str(j["threads"]),
                     "--repeats",str(args.repeats),"--cluster",c["CLUSTER_NAME"],
                     "--family",args.preset,"--launcher",launcher]
            if args.profile: command.append("--profile")
        lines.append(shlex.join(command))
        path=folder/(name+".pbs")
        path.write_text('\n'.join(lines)+'\n')
        manifest.append(dict(script=str(path),**j))
    (folder/"manifest.json").write_text(json.dumps(manifest,indent=2)+"\n")
    print(f"Generated {len(jobs)} jobs: {folder}")
    print("Review each .pbs, then submit using qsub. No jobs have been submitted.")
    for j in manifest: print(j["script"])


if __name__=="__main__":
    try: main()
    except Exception as e:
        print(f"ERROR: {e}",file=sys.stderr)
        sys.exit(1)

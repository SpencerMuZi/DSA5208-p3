#!/usr/bin/env python3
"""Generate portable PBS jobs using the resource rules recorded on Atlas.

No jobs are submitted. Core solver and original scripts are unchanged.
"""
import argparse,json,shlex
from datetime import datetime,timezone
from pathlib import Path

ROOT=Path(__file__).resolve().parents[2]
LAUNCHER='mpirun -np {ranks} --map-by ppr:{ranks_per_node}:node:PE={threads} --bind-to core -x OMP_NUM_THREADS -x OMP_PLACES -x OMP_PROC_BIND -x OMP_DYNAMIC'

def main():
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument('--study',required=True,choices=['validate','strong','weak','mix','comm'])
    p.add_argument('--n',type=int,default=1024)
    p.add_argument('--base-n',type=int,default=256)
    p.add_argument('--iters',type=int,default=5000)
    p.add_argument('--repeats',type=int,default=5)
    p.add_argument('--queue',default='parallel')
    p.add_argument('--walltime')
    p.add_argument('--output',type=Path)
    a=p.parse_args()
    if min(a.n,a.base_n,a.iters,a.repeats)<1:p.error('positive sizes, iterations and repeats required')
    import re
    if not re.fullmatch(r'[A-Za-z0-9_.-]+',a.queue):p.error('invalid queue name')
    wall=a.walltime or ('01:00:00' if a.study=='validate' else '00:10:00')
    if not re.fullmatch(r'\d+:[0-5]\d:[0-5]\d',wall):p.error('walltime must be HH:MM:SS')
    specifications=[]
    def add(label,nodes,ppn,t,n,variants):
        if nodes*ppn>n:p.error('ranks cannot exceed interior rows')
        specifications.append(dict(label=label,nodes=nodes,ppn=ppn,threads=t,n=n,variants=variants))
    if a.study=='validate':add('validate',1,4,1,31,['validate'])
    elif a.study=='strong':
        add('serial',1,1,1,a.n,['serial'])
        for c in [1,2,4,8,16]:add(f'mpi-c{c}',2 if c==16 else 1,8 if c==16 else c,1,a.n,['mpi'])
        for c in [2,4,8,16]:add(f'hybrid-c{c}',2 if c==16 else 1,4 if c==16 else c//2,2,a.n,['hybrid'])
    elif a.study=='weak':
        for c in [1,2,4,8,16]:add(f'weak-c{c}',2 if c==16 else 1,8 if c==16 else c,1,round(a.base_n*c**0.5),['mpi'])
    elif a.study=='mix':
        for nodes in [1,2]:
            for t in [1,2,4,8]:add(f'mix-n{nodes}-t{t}',nodes,8//t,t,a.n,['mpi' if t==1 else 'hybrid'])
    else:
        for nodes in [1,2]:add(f'comm-pair-n{nodes}',nodes,4,2,a.n,['hybrid','overlap'])
    stamp=datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%S%fZ')
    out=a.output or ROOT/'jobs/portable/generated'/f'{a.study}-N{a.n}-{stamp}'
    out.mkdir(parents=True,exist_ok=False)
    for s in specifications:
        allocated=12 if s['nodes']==1 else 8
        lines=['#!/bin/bash',f"#PBS -N p3-{s['label']}",f'#PBS -q {a.queue}',
            f"#PBS -l select={s['nodes']}:ncpus={allocated}:mpiprocs={s['ppn']}:ompthreads={s['threads']}:mem=2gb:node_pool=par12",
            '#PBS -l place=scatter',f'#PBS -l walltime={wall}','#PBS -j oe',
            'set -euo pipefail','cd "${PBS_O_WORKDIR:?Submit from the source root}"',
            'source configs/site_modules.sh','export OMP_PLACES=cores','export OMP_PROC_BIND=close',
            'export OMP_DYNAMIC=FALSE',f"export OMP_NUM_THREADS={s['threads']}",
            'test -f results/build/build.txt','test -n "${PBS_JOBID:-}"','hostname','date -u',
            'sort "$PBS_NODEFILE" | uniq -c']
        if a.study=='validate':
            cmd=['python3','scripts/validate.py','--max-cores','4','--launcher','mpirun -np {ranks} --map-by slot:PE={threads} --bind-to core']
            lines.append(shlex.join(cmd))
        else:
            for variant in s['variants']:
                cmd=['python3','scripts/benchmark.py','--variant',variant,'--n',str(s['n']),
                    '--iters',str(a.iters),'--repeats',str(a.repeats),'--mode','benchmark','--check','0',
                    '--ranks',str(s['nodes']*s['ppn']),'--ranks-per-node',str(s['ppn']),
                    '--nodes',str(s['nodes']),'--threads',str(s['threads']),
                    '--cluster','Atlas','--family',a.study,'--launcher',LAUNCHER]
                if variant=='serial':
                    lines.append("serial_cpu=$(python3 -c 'import os; print(min(os.sched_getaffinity(0)))')")
                    lines.append('taskset -c "$serial_cpu" '+shlex.join(cmd))
                else:lines.append(shlex.join(cmd))
        path=out/(s['label']+'.pbs');path.write_text('\n'.join(lines)+'\n')
        s.update(script=str(path),allocated_cpus=s['nodes']*allocated,used_cores=s['nodes']*s['ppn']*s['threads'])
    (out/'manifest.json').write_text(json.dumps(specifications,indent=2)+'\n')
    print(f'Generated {len(specifications)} PBS jobs: {out}')
    print('Review resources and site permissions, then qsub individual scripts. No jobs were submitted.')

if __name__=='__main__':main()

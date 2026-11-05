#!/usr/bin/env python3
"""Pin each Open MPI local rank inside the physical cores allowed by PBS."""
import argparse,os
from pathlib import Path

def physical_core(cpu):
    root=Path('/sys/devices/system/cpu')/f'cpu{cpu}'/'topology'
    return tuple(int((root/name).read_text()) for name in ['physical_package_id','core_id'])

def rank_cpus(allowed,threads,local_rank,local_size,key=physical_core):
    if threads<1 or local_size<1 or not 0<=local_rank<local_size:raise ValueError('invalid local rank/thread count')
    cores={}
    for cpu in sorted(allowed):cores.setdefault(key(cpu),cpu)
    ordered=[cores[k] for k in sorted(cores)]
    if len(ordered)<threads*local_size:raise ValueError('PBS affinity has too few distinct physical cores')
    return ordered[local_rank*threads:(local_rank+1)*threads]

def main():
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('--threads',type=int,required=True);p.add_argument('command',nargs=argparse.REMAINDER);a=p.parse_args()
    command=a.command[1:] if a.command[:1]==['--'] else a.command
    if not command:p.error('executable required after --')
    if not os.environ.get('PBS_JOBID'):p.error('PBS allocation required')
    try:rank=int(os.environ['OMPI_COMM_WORLD_LOCAL_RANK']);size=int(os.environ['OMPI_COMM_WORLD_LOCAL_SIZE'])
    except (KeyError,ValueError):p.error('Open MPI local rank/size required')
    cpus=rank_cpus(os.sched_getaffinity(0),a.threads,rank,size)
    os.sched_setaffinity(0,cpus)
    env=os.environ.copy();env.update(OMP_NUM_THREADS=str(a.threads),OMP_DYNAMIC='FALSE',OMP_PROC_BIND='close',OMP_PLACES=','.join('{'+str(cpu)+'}' for cpu in cpus))
    os.execvpe(command[0],command,env)
if __name__=='__main__':main()

#!/usr/bin/env python3
"""GPU numerical checks in an existing allocation; no job submission."""
import argparse,json,math,subprocess,sys
from pathlib import Path
from datetime import datetime,timezone
from validate import ROOT,run,read_grid,launcher_command

def main():
    p=argparse.ArgumentParser();p.add_argument('--gpus',type=int,choices=[1,2],default=1)
    p.add_argument('--launcher',default='mpirun -np {ranks} --map-by ppr:{ranks_per_node}:node:PE=1 --bind-to core')
    p.add_argument('--nodes',type=int,default=1);p.add_argument('--output',type=Path);a=p.parse_args()
    if a.gpus%a.nodes:p.error('uniform GPUs per node required')
    folder=a.output or ROOT/'results/validation'/('cuda-'+datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%S%fZ'))
    folder.mkdir(parents=True,exist_ok=False);cases=[];serial=str(ROOT/'bin/jacobi_serial');cuda=str(ROOT/'bin/jacobi_cuda')
    for n in [1,3,5,17,31]:
        fixed=['--dim','2','--n',str(n),'--mode','benchmark','--iters','37','--check','0']
        reference=folder/f'serial-{n}.csv';run([serial,*fixed,'--dump',str(reference)],folder,f'serial-{n}')
        for ranks in sorted({1,a.gpus}):
            if ranks>n or ranks<a.nodes:continue
            grid=folder/f'cuda-{n}-{ranks}.csv'
            launch=launcher_command(a.launcher,ranks,1,ranks//a.nodes)
            r=run(launch+[cuda,*fixed,'--variant','cuda','--dump',str(grid)],folder,f'cuda-{n}-{ranks}')
            cr,ref=read_grid(reference,2,n);cg,actual=read_grid(grid,2,n)
            delta=max(abs(x-y) for x,y in zip(ref,actual));relative=math.sqrt(sum((x-y)**2 for x,y in zip(ref,actual))/sum(x*x for x in ref))
            if cr!=cg or delta>1e-12 or relative>1e-11 or r['backend']!='cuda' or r['gpu_count']!=ranks:raise ValueError('GPU fixed-work grid mismatch')
            cases.append({'purpose':'GPU update/halo/partition','n':n,'ranks':ranks,'max_diff':delta,'relative_diff':relative,'passed':True})
    for n in [17,31]:
        launch=launcher_command(a.launcher,a.gpus,1,a.gpus//a.nodes)
        r=run(launch+[cuda,'--variant','cuda','--dim','2','--n',str(n),'--mode','solve','--iters','50000','--check','10','--tol','1e-8'],folder,f'solve-{n}')
        if not r['converged'] or r['final_residual']>1e-8 or r['relative_error_l2']>2e-8:raise ValueError('GPU manufactured-solution check failed')
        cases.append({'purpose':'independent manufactured solution','n':n,'result':r,'passed':True})
    summary={'scope':'real_GPU_execution','passed':True,'checks':len(cases),'cases':cases}
    (folder/'summary.json').write_text(json.dumps(summary,indent=2)+'\n');print('PASS:',len(cases),'GPU cases;',folder)
if __name__=='__main__':
    try:main()
    except Exception as e:print('ERROR:',e,file=sys.stderr);sys.exit(1)

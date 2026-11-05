#!/usr/bin/env python3
"""Measure fixed-work solver loops in a PBS allocation, retaining every repetition."""
import argparse
from collections import Counter
from datetime import datetime, timezone
import hashlib
import json
import math
import os
from pathlib import Path
import statistics
import subprocess
import uuid
from validate import ROOT, launcher_command
from pin_rank import physical_core

LAUNCH = ('mpirun -np {ranks} --map-by ppr:{ranks_per_node}:node --bind-to none '
          '-x OMP_NUM_THREADS -x OMP_PLACES -x OMP_PROC_BIND -x OMP_DYNAMIC '
          'python3 scripts/pin_rank.py --threads {threads} --')

def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument('--variants', default='mpi', help='One variant, or comma-separated paired variants')
    p.add_argument('--dim', type=int, choices=[2, 3], default=2)
    p.add_argument('--n', type=int, required=True)
    p.add_argument('--iters', type=int, required=True)
    p.add_argument('--ranks', type=int, default=1)
    p.add_argument('--threads', type=int, default=1)
    p.add_argument('--nodes', type=int, default=1)
    p.add_argument('--ranks-per-node', type=int)
    p.add_argument('--host-threads', type=int, default=8)
    p.add_argument('--repeats', type=int, default=5)
    p.add_argument('--timeout', type=int, default=3600)
    p.add_argument('--launcher', default=LAUNCH)
    p.add_argument('--output', type=Path)
    a = p.parse_args()
    variants = a.variants.split(',')
    allowed = {'serial', 'mpi', 'hybrid', 'overlap', 'cuda'}
    if not os.environ.get('PBS_JOBID'):
        p.error('Run inside a PBS compute allocation')
    if len(set(variants)) != len(variants) or not set(variants) <= allowed:
        p.error('Choose distinct variants from serial,mpi,hybrid,overlap,cuda')
    if min(a.n, a.iters, a.ranks, a.threads, a.nodes, a.repeats, a.timeout, a.host_threads) < 1:
        p.error('Sizes, resource counts, repeats and timeout must be positive')
    ppn = a.ranks_per_node or a.ranks
    if ppn < 1 or ppn * a.nodes != a.ranks or a.ranks > a.n:
        p.error('Uniform rank/node layout and ranks <= N required')
    gpu_pair = 'cuda' in variants and len(variants) > 1
    if gpu_pair and (set(variants) != {'serial', 'hybrid', 'cuda'} or a.ranks != 1 or a.nodes != 1):
        p.error('GPU comparison requires serial,hybrid,cuda on one node with one GPU rank')
    if 'cuda' in variants and a.dim != 2:
        p.error('CUDA implements dimension 2')
    folder = a.output or ROOT / 'results' / ('run-' + datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%SZ') + '-' + uuid.uuid4().hex[:8])
    folder.mkdir(parents=True, exist_ok=False)
    sessions = {}
    for variant in variants:
        ranks = 1 if variant == 'serial' else a.ranks
        threads = 1 if variant in ['serial', 'mpi', 'cuda'] else a.host_threads if gpu_pair else a.threads
        binary = ROOT / 'bin' / ('jacobi_serial' if variant == 'serial' else 'jacobi_cuda' if variant == 'cuda' else 'jacobi_parallel')
        env = dict(os.environ, OMP_NUM_THREADS=str(threads), OMP_PLACES='cores', OMP_PROC_BIND='close', OMP_DYNAMIC='FALSE')
        if variant == 'serial':
            cpu = min(os.sched_getaffinity(0))
            launch = ['taskset', '-c', str(cpu)]
            topology = [dict(rank=0, host=os.uname().nodename, threads=1, thread_physical_cores=[':'.join(map(str, physical_core(cpu)))])]
        else:
            launch = launcher_command(a.launcher, ranks, threads, ppn)
            probe = [str(binary), '--topology'] if variant == 'cuda' else [str(ROOT / 'bin/hello_hybrid')]
            result = subprocess.run(launch + probe, cwd=ROOT, env=env, capture_output=True, text=True, timeout=a.timeout)
            (folder / (variant + '-topology.stdout.txt')).write_text(result.stdout)
            (folder / (variant + '-topology.stderr.txt')).write_text(result.stderr)
            if result.returncode:
                raise RuntimeError('Topology command failed: ' + variant)
            topology = [json.loads(line) for line in result.stdout.splitlines() if line.startswith('{"rank":')]
            if sorted(t['rank'] for t in topology) != list(range(ranks)):
                raise ValueError('Missing/duplicate ranks in topology')
            hosts = Counter(t['host'] for t in topology)
            if len(hosts) != a.nodes or any(n != ppn for n in hosts.values()):
                raise ValueError('Actual node/rank layout differs from request')
        cores = set()
        devices = set()
        for t in topology:
            masks = t.get('thread_physical_cores', [])
            if t['threads'] != threads or len(masks) != threads:
                raise ValueError('Actual thread count differs from request')
            for mask in masks:
                key = (t['host'], mask)
                if not mask or ',' in mask or 'unavailable' in mask or key in cores:
                    raise ValueError('Missing or overlapping physical CPU binding')
                cores.add(key)
            if variant == 'cuda':
                key = (t['host'], t['gpu_uuid'])
                if key in devices:
                    raise ValueError('Multiple ranks selected the same GPU')
                devices.add(key)
        command = launch + [str(binary), '--variant', variant, '--dim', str(a.dim), '--n', str(a.n), '--iters', str(a.iters), '--mode', 'benchmark', '--check', '0', '--threads', str(threads)]
        sessions[variant] = dict(command=command, env=env, topology=topology, binary_sha256=hashlib.sha256(binary.read_bytes()).hexdigest(), rows=[])
    metadata = dict(job_id=os.environ['PBS_JOBID'], arguments=vars(a) | {'output': str(folder)}, variants={v: {k: s[k] for k in ['command', 'topology', 'binary_sha256']} for v, s in sessions.items()})
    (folder / 'metadata.json').write_text(json.dumps(metadata, indent=2) + '\n')
    def execute(variant, repeat):
        s = sessions[variant]
        result = subprocess.run(s['command'], cwd=ROOT, env=s['env'], capture_output=True, text=True, timeout=a.timeout)
        label = variant + ('-warmup' if repeat == 0 else '-repeat-' + str(repeat))
        (folder / (label + '.stdout.txt')).write_text(result.stdout)
        (folder / (label + '.stderr.txt')).write_text(result.stderr)
        if result.returncode:
            raise RuntimeError(label + ': solver failed')
        rows = [json.loads(line) for line in result.stdout.splitlines() if line.startswith('{"variant":')]
        if len(rows) != 1:
            raise ValueError(label + ': expected one solver result')
        r = rows[0]
        if (r['variant'], r['dim'], r['n'], r['iterations']) != (variant, a.dim, a.n, a.iters) or r['check_interval'] != 0 or r['profile']:
            raise ValueError(label + ': workload mismatch')
        if not math.isfinite(r['solve_seconds_max']) or r['solve_seconds_max'] <= 0:
            raise ValueError(label + ': invalid elapsed time')
        if repeat:
            r.update(repeat=repeat, binary_sha256=s['binary_sha256'], job_id=os.environ['PBS_JOBID'])
            s['rows'].append(r)
            with (folder / 'measurements.jsonl').open('a') as f:
                f.write(json.dumps(r) + '\n')
    for v in variants:
        execute(v, 0)
    order = []
    for repeat in range(1, a.repeats + 1):
        shift = (repeat - 1) % len(variants)
        sequence = variants[shift:] + variants[:shift]
        order.append(sequence)
        for v in sequence:
            execute(v, repeat)
    summaries = []
    for v, s in sessions.items():
        values = [r['solve_seconds_max'] for r in s['rows']]
        summaries.append(dict(variant=v, samples=len(values), median_seconds=statistics.median(values), min_seconds=min(values), max_seconds=max(values)))
    (folder / 'run_order.json').write_text(json.dumps(order, indent=2) + '\n')
    (folder / 'summary.json').write_text(json.dumps(summaries, indent=2) + '\n')
    (folder / 'COMPLETE').write_text('All requested warm-ups and measured repetitions completed.\n')
    print(json.dumps(summaries, indent=2))
    print('Results:', folder)

if __name__ == '__main__':
    main()

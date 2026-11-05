# Parallel Poisson Solver

C++17, double-precision Jacobi iteration for 2D and 3D Poisson equations with zero Dirichlet boundaries. Implementations: true serial, MPI, MPI+OpenMP, nonblocking MPI+OpenMP, and 2D CUDA.

Li Yaqi, Lin Jialiang, Li Chongkai.

## Build

Requirements: C++17 compiler, MPI, OpenMP, Python 3.9+, and Bash. CUDA 12.9 is used for the A40 target (`sm_86`); change `NVCCFLAGS` for other GPUs. Python scripts use only the standard library.

On Vanda, run builds inside a PBS compute allocation:

```bash
source scripts/environment.sh
bash scripts/build.sh cpu
# With a GPU allocation:
bash scripts/build.sh gpu
```

On another Linux MPI/OpenMP system, load its compiler/runtime and run `make cpu`. CUDA builds require `CUDA_HOME` and Open MPI's `mpicxx --showme:incdirs`. Override Make variables for other MPI distributions. The serial executable has no OpenMP dependency.

## Run and validate

```bash
bin/jacobi_serial --variant serial --dim 3 --n 17 --iters 50000 --mode solve --check 10 --tol 1e-8
```

In a four-core Vanda allocation, the launcher below binds ranks/threads to distinct physical cores within PBS affinity:

```bash
export OMP_NUM_THREADS=1 OMP_PLACES=cores OMP_PROC_BIND=close OMP_DYNAMIC=FALSE
launch='mpirun -np {ranks} --map-by ppr:{ranks_per_node}:node --bind-to none -x OMP_NUM_THREADS -x OMP_PLACES -x OMP_PROC_BIND -x OMP_DYNAMIC python3 scripts/pin_rank.py --threads {threads} --'
python3 scripts/validate.py --dim 2 --max-cores 4 --launcher "$launch"
python3 scripts/validate.py --dim 3 --max-cores 4 --launcher "$launch"
```

Expected suites: 131 checks in 2D and 93 in 3D, covering grid comparisons, an independent stencil reference, manufactured solutions and error paths. In a one-GPU allocation after the GPU build:

```bash
python3 scripts/validate_cuda.py --gpus 1 --launcher "$launch"
```

This performs seven GPU checks. MPI/hybrid/overlap accept dimensions 2 and 3; CUDA accepts dimension 2 and one distinct GPU per MPI rank. Ranks cannot exceed N. All physical CPU threads are explicitly checked by the benchmark launcher.

## Benchmark on Vanda

From this source directory, substitute your project:

```bash
qsub -P personal-YOUR_ACCOUNT jobs/cpu.pbs
qsub -P personal-YOUR_ACCOUNT jobs/gpu.pbs
```

Use a separate clean source directory for each simultaneous job. PBS templates build on their allocated node. They use the `auto` route; `batch_cpu` and `batch_gpu` are not direct submission queues.

`scripts/benchmark.py` excludes one warm-up and retains five fresh-process repetitions by default. A comma-separated `--variants` list rotates execution order within one allocation. Results, commands, topology, binary hashes and min/median/max summaries are written under `results/`. A `COMPLETE` marker is written only after all requested samples finish.

Examples inside matching allocations:

```bash
# True serial baseline:
python3 scripts/benchmark.py --variants serial --dim 2 --n 4096 --iters 5000
# Four CPU cores: two ranks, two OpenMP threads per rank:
python3 scripts/benchmark.py --variants hybrid --dim 3 --n 256 --iters 200 --ranks 2 --threads 2
# Same-allocation blocking / overlap comparison:
python3 scripts/benchmark.py --variants hybrid,overlap --dim 2 --n 8192 --iters 5000 --ranks 2 --threads 2
# Same-allocation one-GPU / CPU comparison (36 allocated host CPUs):
python3 scripts/benchmark.py --variants serial,hybrid,cuda --dim 2 --n 1024 --iters 5000 --host-threads 8
```

For 256-core MPI, change the CPU PBS resource line to `select=8:ncpus=32:mpiprocs=32:ompthreads=1:mem=16gb:node_pool=cpu_node` and pass `--ranks 256 --threads 1 --nodes 8 --ranks-per-node 32`. For a two-thread hybrid layout, use `mpiprocs=16:ompthreads=2`, ranks=128 and ranks-per-node=16. Keep N/K fixed for strong scaling. For 2D weak scaling, use N=round(256*sqrt(P)), K=5000 and P=1,2,4,...,256.

N counts interior points per coordinate. `benchmark` executes exactly K iterations with no in-loop residual checks; `solve` stops at its residual tolerance and exits 2 if the cap is insufficient. Large fixed-work runs can report `converged=false`. CPU/GPU primary times cover solver loops, excluding launch, initialization and final verification. CUDA synchronizes device work before stopping timing. Its `end_to_end_seconds_max` field covers grid setup through final device-to-host transfer, excluding process launch, device selection and final verification.

The numerical source files match the measured solvers. Build/run helpers are packaged for direct use. `CHECKSUMS.json` covers distributed files; generated results and binaries are not included.

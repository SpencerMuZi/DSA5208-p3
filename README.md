# DSA5208 Project 3: MPI + OpenMP Jacobi solver

Li Yaqi, Lin Jialiang, Li Chongkai.

C++17 implementations of a 2D Poisson solver: serial, MPI, blocking MPI/OpenMP (`hybrid`) and nonblocking MPI/OpenMP (`overlap`). Input is a manufactured problem with exact solution `u=x(1-x)y(1-y)`, zero boundaries and a zero initial guess.

## Build

Requires Make, a C++17 compiler, MPI and OpenMP. Python 3.9+ is required for scripts.

On Linux with GCC and MPI installed:

```bash
make all
```

For the serial target alone: `make serial`. On macOS with Apple Clang: `make serial CXX=clang++`.

The recorded Atlas environment is GCC 12.3.0, Open MPI 4.1.5, Python 3.11.3 and binutils 2.40. On Atlas:

```bash
bash -l scripts/build.sh
```

`configs/site_modules.sh` loads that toolchain. Adapt module paths for another cluster. Flags: `-O3 -std=c++17 -Wall -Wextra -Wpedantic`, with `-fopenmp` for parallel programs. Build records are written to `results/build/`.

## Run

Run MPI commands in a compute allocation or on a local development machine:

```bash
bin/jacobi_serial --n 17 --mode solve --iters 50000 --check 10 --tol 1e-8
bin/jacobi_serial --n 1024 --mode benchmark --iters 5000 --check 0
mpirun -np 4 bin/jacobi_parallel --variant mpi --threads 1 --n 1024 --iters 5000 --check 0
mpirun -np 4 bin/jacobi_parallel --variant hybrid --threads 2 --n 1024 --iters 5000 --check 0
mpirun -np 4 bin/jacobi_parallel --variant overlap --threads 2 --n 1024 --iters 5000 --check 0
```

`--n` counts interior points per dimension; ranks must not exceed N. `--mode benchmark` executes exactly `--iters` sweeps. `--mode solve` stops at the relative residual tolerance or iteration limit; it requires `--check` greater than zero. The default mode is benchmark. `--dump grid.csv` exports the final interior grid; create its parent directory first. `--help` lists all options.

Stdout is one JSON result. Exit status is 0 for a completed benchmark or converged solve, 2 for an unconverged solve, and 1 for invalid input. The report's 5000-sweep timings are fixed-work measurements; the large grids have not converged.

## Validate

```bash
python3 scripts/validate.py --serial-only
python3 scripts/validate.py --max-cores 4 --launcher 'mpirun -np {ranks} --map-by slot:PE={threads} --bind-to core'
```

The full suite checks serial/parallel grids, uneven partitions, one/two-row ranks, manufactured-solution convergence and error exits. Outputs are written under `results/validation/`. 

## Atlas PBS jobs

From this source directory, after building:

```bash
python3 jobs/portable/generate_jobs.py --study validate --output jobs/validate
cat jobs/validate/validate.pbs
qsub jobs/validate/validate.pbs
```

Generate the experimental matrix:

```bash
python3 jobs/portable/generate_jobs.py --study strong --n 512
python3 jobs/portable/generate_jobs.py --study strong --n 1024
python3 jobs/portable/generate_jobs.py --study weak --base-n 256
python3 jobs/portable/generate_jobs.py --study mix --n 1024
python3 jobs/portable/generate_jobs.py --study comm --n 1024
```

The generator prints each output directory and writes its manifest. Inspect resource directives, then submit individual `.pbs` files with `qsub` from the source root (`PBS_O_WORKDIR`). Output directories must be new. Defaults are 5000 sweeps, one warm-up and five measured runs; `--walltime HH:MM:SS` overrides the time limit.

Templates use the recorded `parallel` queue and `par12` node pool, reserving 12 CPUs on one node or 8 CPUs per node on two nodes. Application cores are counted separately. MPI binds ranks to cores; OpenMP uses `OMP_PLACES=cores`, `OMP_PROC_BIND=close` and `OMP_DYNAMIC=FALSE`. Adapt these recorded settings if site configuration changes. Check PBS output and each result directory's `COMPLETE` marker.

## Analyze new measurements

```bash
python3 scripts/analyze.py --input results/raw --output results/summary --official-only
```

`scripts/benchmark.py` records one warm-up and five measured repetitions by default. Solver-loop timing includes halo exchange and thread synchronization; initialization, process launch and final verification are excluded. Strong-scaling speedup uses a matching serial baseline; weak scaling uses its own one-core reference. Efficiency counts application cores, not reserved CPUs.

The solver, Makefile and original scripts retain the experimental fingerprint `465f973ecc1da585034e511423c9021bd58f1007a24e2262acbc509bec145d45`. Use `jobs/portable/generate_jobs.py` for Atlas PBS jobs. The generic `scripts/make_jobs.py` requires a configured `configs/cluster.env`; its defaults are not the recorded Atlas queue settings. `scripts/test_workflow.py` tests that generic generator and analysis safeguards. `scripts/package.py` is an older development utility; its full-report packaging mode is not used by this code-only repository.

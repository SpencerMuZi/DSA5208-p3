# DSA5208 Project 3 — C++ / MPI / OpenMP Jacobi solver

这是可运行的项目起步包：serial、MPI、MPI+OpenMP、非阻塞 MPI+OpenMP 四个版本，验证脚本、PBS 作业生成器和三人操作指南。

先读 `docs/总实施方案.md`，再按角色读 `docs/A_操作指南_Windows.md`、`docs/B_操作指南_Windows.md`、`docs/C_操作指南_Mac.md`。共同部署步骤在 `docs/共同部署与命令说明.md`。本地验证范围见 `docs/验证记录.md`。

账号/队列/模块与正式实验尚未完成。这里没有 Atlas/Vanda 性能数据，也没有最终 PDF。现有图表和本地日志（如有）只能用于开发验证。

## Repository

GitHub repository: [SpencerMuZi/DSA5208-p3](https://github.com/SpencerMuZi/DSA5208-p3)。仓库目前为 private；协作者需要被授予访问权限。

```bash
git clone https://github.com/SpencerMuZi/DSA5208-p3.git
cd DSA5208-p3
```

仓库根目录就是指南中的 Project3 根目录。需要分发给没有 Git 的组员时，运行 `python3 scripts/package.py --kind source`，生成指南使用的 ZIP。仓库跟踪代码、指南和配置示例；生成结果、二进制、.venv、私有集群配置和 dist 分发包留在本地，正式证据在完成实验后按交付说明归档。

## Dependencies and build

- C++17 compiler and Make.
- MPI C++ wrapper `mpicxx`, and OpenMP runtime.
- Python 3.9+ for scripts; only optional plotting needs matplotlib.
- PBS + Open MPI integrated with PBS for the supplied cluster job generator.

Linux with GCC/MPI already loaded:

```bash
make all
```

On a cluster, configure `configs/site_modules.sh` from the example and use:

```bash
bash -l scripts/build.sh
```

If the MPI wrapper uses another compiler, choose a matching serial compiler and compiler flags. Do not mix binaries built using different MPI installations. The site generator intentionally refuses unknown/unconfirmed cluster settings.

## Program options

```bash
bin/jacobi_serial --help
bin/jacobi_parallel --help
```

| Option | Meaning |
|---|---|
| `--n 64` | Interior grid size N×N; boundaries are additional zero-valued points |
| `--variant serial/mpi/hybrid/overlap` | Implementation; use the corresponding binary |
| `--mode benchmark/solve` | Fixed work / residual stopping |
| `--iters 1000` | Fixed iterations, or maximum iterations in solve mode |
| `--check 0` | Disable timed residual checks in benchmark mode |
| `--check 10` | Check every 10 iterations; solve always checks the last allowed iteration |
| `--tol 1e-8` | Relative L2 residual tolerance |
| `--threads 2` | OpenMP threads per rank; MPI-only requires 1 |
| `--dump path.csv` | Write interior grid after timing; parent folder must exist |
| `--profile` | Enable per-phase timing, only for separate diagnostic runs |

Problem: `-Δu=f` on `[0,1]²`, zero boundaries, `u*=x(1-x)y(1-y)`, `f=2[x(1-x)+y(1-y)]`, initial guess zero. The sampled polynomial is an exact solution of the five-point discrete problem up to floating-point error.

Stdout contains one JSON result. Exit 0 means normal completion; solve mode exits 2 when the maximum iterations end without convergence. Invalid input exits 1 (MPI launchers may translate application abort status). Benchmark does not require convergence.

## Quick local / allocated-node checks

These commands require a local development machine or a scheduler-allocated compute node. Do not launch benchmarks directly on a cluster login node.

```bash
bin/jacobi_serial --n 17 --mode solve --iters 50000 --tol 1e-8 --check 10
mpirun -np 2 bin/jacobi_parallel --variant mpi --n 31 --iters 100 --check 0
mpirun -np 2 bin/jacobi_parallel --variant hybrid --threads 2 --n 31 --iters 100 --check 0
mpirun -np 2 bin/jacobi_parallel --variant overlap --threads 2 --n 31 --iters 100 --check 0
python3 scripts/validate.py --serial-only
python3 scripts/validate.py --max-cores 4 --launcher 'mpirun -np {ranks}'
```

The last command's simple launcher is for local development; on a cluster use the generator's `verify` job with approved binding.

## Cluster jobs

```bash
cp configs/cluster.env.example configs/cluster.env
cp configs/site_modules.sh.example configs/site_modules.sh
nano configs/cluster.env
nano configs/site_modules.sh
bash -l scripts/build.sh
python3 scripts/make_jobs.py --preset smoke --iters 100 --repeats 3
```

Fill confirmed site settings first, review the printed `.pbs` file and submit it with `qsub PATH`. No job is submitted by the generator. Subsequent presets: `verify`, `strong`, `weak`, `mix`, `comm`, `check`. See the Chinese guides for resource choices and exact command sequences.

Each benchmark performs an untimed identical warm-up, then fresh-process repetitions. MPI topology is recorded before timing. Solve timing covers only the iteration loop, including checks inside it; process launch, grid construction, final verification and dump are excluded. Each run is valid for aggregation only after its `COMPLETE` marker exists.

## Analysis and packaging

Basic summary uses the Python standard library:

```bash
python3 scripts/analyze.py --official-only
```

For plots, install plotting packages in a local virtual environment:

```bash
python3 -m venv .venv
source .venv/bin/activate
python -m pip install -r requirements-analysis.txt
python scripts/analyze.py --official-only --plots
python -m pip freeze > report/analysis_requirements_lock.txt
```

Grouping prevents comparison across different CPU models, code hashes, compiler records or numerical workloads. Blank speedup means a matching serial baseline is missing. Weak scaling uses constant points per core within rounding tolerance and fixed iteration work.

```bash
python3 scripts/package.py --kind source
python3 scripts/package.py --kind full
python3 scripts/package.py --kind full --final
```

Source packages contain guides/code/templates; full packages additionally contain results, figures and generated jobs. Local private settings, binaries and virtual environments are excluded. Final packaging requires a real `report/report.pdf`, completed `report/team.csv`, and a completed official multi-node run. It is a basic consistency check; the team must still review report quality, results and Canvas requirements.

## Implementation limits

- One-dimensional row decomposition; at least one interior row per MPI rank.
- OpenMP parallel regions are created per update/check. Fine-grained overhead may limit small cases.
- Vector allocation/zero initialization is serial; NUMA first-touch optimization is not implemented.
- The nonblocking version overlaps local interior computation with halo exchange, but MPI progress and performance gains are implementation dependent.
- Residual checks refresh current halos and perform a global sum; their full cost is included when inside timing.
- Phase maxima can come from different ranks; do not sum them as an exact total-time decomposition.
- The job generator currently targets confirmed Open MPI/PBS configurations. Other site launchers need adaptation and topology verification.

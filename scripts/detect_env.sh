#!/usr/bin/env bash
set -euo pipefail
cd "$(dirname "$0")/.."
mkdir -p results/environment
stamp=$(date -u +%Y%m%dT%H%M%SZ)
destination="results/environment/detect-${stamp}.txt"
{
    date -u
    hostname
    uname -a
    for program in g++ clang++ mpicxx mpirun python3 make qsub qstat sbatch srun; do
        command -v "$program" || true
    done
    if type module >/dev/null 2>&1; then
        module -t list 2>&1 || true
        module -t avail 2>&1 || true
    fi
    if command -v qstat >/dev/null 2>&1; then qstat -Q 2>&1 || true; fi
    if command -v lscpu >/dev/null 2>&1; then lscpu; fi
    if command -v mpicxx >/dev/null 2>&1; then mpicxx --version 2>&1 || true; fi
    if command -v mpirun >/dev/null 2>&1; then mpirun --version 2>&1 || true; fi
    python3 --version
} > "$destination"
cat "$destination"
printf 'Saved: %s\n' "$destination"

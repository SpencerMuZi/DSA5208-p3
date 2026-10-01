#!/usr/bin/env bash
set -euo pipefail
cd "$(dirname "$0")/.."
if [[ -f configs/site_modules.sh ]]; then source configs/site_modules.sh; fi
mkdir -p results/build
{
    date -u
    hostname
    printf 'SERIAL_CXX=%s\n' "${SERIAL_CXX:-g++}"
    printf 'MPI_CXX=%s\n' "${MPI_CXX:-mpicxx}"
    printf 'CXXFLAGS=%s\n' "${PROJECT_CXXFLAGS:--O3 -std=c++17 -Wall -Wextra -Wpedantic}"
    printf 'OPENMP_FLAGS=%s\n' "${PROJECT_OPENMP_FLAGS:--fopenmp}"
    printf 'LDFLAGS=%s\n' "${PROJECT_LDFLAGS:-}"
    "${SERIAL_CXX:-g++}" --version
    "${MPI_CXX:-mpicxx}" --version
    mpirun --version
    if type module >/dev/null 2>&1; then module -t list 2>&1; fi
} > results/build/build.txt 2>&1
# Rebuild after module/flag changes; Make does not track compiler flags as dependencies.
make clean
make all CXX="${SERIAL_CXX:-g++}" MPICXX="${MPI_CXX:-mpicxx}" \
    CXXFLAGS="${PROJECT_CXXFLAGS:--O3 -std=c++17 -Wall -Wextra -Wpedantic}" \
    OPENMP_FLAGS="${PROJECT_OPENMP_FLAGS:--fopenmp}" LDFLAGS="${PROJECT_LDFLAGS:-}" \
    2>&1 | tee results/build/compile.txt

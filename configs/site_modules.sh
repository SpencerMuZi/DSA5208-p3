#!/usr/bin/env bash
case $- in
    *u*) set +u; source /app1/ebenv; set -u ;;
    *) source /app1/ebenv ;;
esac
module purge
module load GCC/12.3.0
module load OpenMPI/4.1.5-GCC-12.3.0
module load Python/3.11.3-GCCcore-12.3.0

export SERIAL_CXX=g++
export MPI_CXX=mpicxx
export PROJECT_CXXFLAGS='-O3 -std=c++17 -Wall -Wextra -Wpedantic'
export PROJECT_OPENMP_FLAGS='-fopenmp'
export PROJECT_LDFLAGS=''

# Ensure the loaded toolchain takes precedence over system defaults.
export PATH="${EBROOTPYTHON:?}/bin:${EBROOTOPENMPI:?}/bin:${EBROOTGCCCORE:?}/bin:$PATH"
hash -r
export SERIAL_CXX="${EBROOTGCCCORE}/bin/g++"
export MPI_CXX="${EBROOTOPENMPI}/bin/mpicxx"

# Use the loaded binutils for assembler and linker.
export PATH="${EBROOTBINUTILS:?}/bin:$PATH"
export PROJECT_CXXFLAGS="-O3 -std=c++17 -Wall -Wextra -Wpedantic -B${EBROOTBINUTILS}/bin/"
hash -r

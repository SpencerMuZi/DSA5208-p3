#!/usr/bin/env bash
# Vanda compiler and runtime environment.
case $- in
    *u*) set +u; source /app1/ebenv; set -u ;;
    *) source /app1/ebenv ;;
esac
module purge
export LD_LIBRARY_PATH="/opt/pbs/lib${LD_LIBRARY_PATH:+:$LD_LIBRARY_PATH}"
module load GCC/13.3.0 OpenMPI/5.0.3-GCC-13.3.0 Python/3.12.3-GCCcore-13.3.0
export CUDA_HOME=/cm/shared/apps/nvhpc/26.1/Linux_x86_64/26.1/cuda/12.9
export PATH="$CUDA_HOME/bin:${EBROOTPYTHON:?}/bin:${EBROOTOPENMPI:?}/bin:${EBROOTGCCCORE:?}/bin:$PATH"
export OMP_PLACES=cores OMP_PROC_BIND=close OMP_DYNAMIC=FALSE
hash -r

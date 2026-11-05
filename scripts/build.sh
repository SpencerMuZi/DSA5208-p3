#!/usr/bin/env bash
set -euo pipefail
cd "$(dirname "$0")/.."
target=${1:-cpu}
case "$target" in cpu|gpu) ;; *) echo 'Usage: bash scripts/build.sh [cpu|gpu]' >&2; exit 1 ;; esac
make cpu
if [[ "$target" == gpu ]]; then
    : "${CUDA_HOME:?Set CUDA_HOME to the CUDA toolkit directory}"
    test -f "$CUDA_HOME/lib64/libcudart.so"
    includes=''
    for directory in $(mpicxx --showme:incdirs); do includes+=" -I$directory"; done
    make cuda MPI_CUDA_INCLUDES="$includes" \
        CUDA_LDFLAGS="-L$CUDA_HOME/lib64 -Wl,-rpath,$CUDA_HOME/lib64"
fi

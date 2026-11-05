CXX = g++
MPICXX = mpicxx
CXXFLAGS = -O3 -std=c++17 -Wall -Wextra -Wpedantic
OPENMP_FLAGS = -fopenmp
LDFLAGS =

.PHONY: all cpu serial parallel clean
all: serial parallel
cpu: serial parallel
serial: bin/jacobi_serial
parallel: bin/jacobi_parallel bin/hello_hybrid

bin:
	mkdir -p bin

bin/jacobi_serial: src/serial.cpp src/common.hpp | bin
	$(CXX) $(CXXFLAGS) src/serial.cpp -o $@ $(LDFLAGS)

bin/jacobi_parallel: src/parallel.cpp src/common.hpp src/parallel_3d.hpp | bin
	$(MPICXX) $(CXXFLAGS) $(OPENMP_FLAGS) src/parallel.cpp -o $@ $(LDFLAGS)

bin/hello_hybrid: src/hello_hybrid.cpp src/common.hpp src/topology.hpp | bin
	$(MPICXX) $(CXXFLAGS) $(OPENMP_FLAGS) src/hello_hybrid.cpp -o $@ $(LDFLAGS)

clean:
	rm -f bin/jacobi_serial bin/jacobi_parallel bin/hello_hybrid bin/jacobi_cuda bin/cuda.o

# CUDA is optional; CPU-only make all remains usable without a CUDA toolkit.
NVCC = nvcc
NVCCFLAGS = -O3 -std=c++17 --fmad=false -arch=sm_86
MPI_CUDA_INCLUDES =
CUDA_LDFLAGS =
.PHONY: cuda
cuda: bin/jacobi_cuda
bin/cuda.o: src/cuda.cu src/common.hpp src/topology.hpp | bin
	$(NVCC) $(NVCCFLAGS) -DOMPI_SKIP_MPICXX=1 $(MPI_CUDA_INCLUDES) -ccbin $(CXX) -c src/cuda.cu -o $@
bin/jacobi_cuda: bin/cuda.o
	$(MPICXX) $(CXXFLAGS) bin/cuda.o -o $@ $(CUDA_LDFLAGS) -lcudart

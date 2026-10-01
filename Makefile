CXX = g++
MPICXX = mpicxx
CXXFLAGS = -O3 -std=c++17 -Wall -Wextra -Wpedantic
OPENMP_FLAGS = -fopenmp
LDFLAGS =

.PHONY: all serial parallel clean
all: serial parallel
serial: bin/jacobi_serial
parallel: bin/jacobi_parallel bin/hello_hybrid

bin:
	mkdir -p bin

bin/jacobi_serial: src/serial.cpp src/common.hpp | bin
	$(CXX) $(CXXFLAGS) src/serial.cpp -o $@ $(LDFLAGS)

bin/jacobi_parallel: src/parallel.cpp src/common.hpp | bin
	$(MPICXX) $(CXXFLAGS) $(OPENMP_FLAGS) src/parallel.cpp -o $@ $(LDFLAGS)

bin/hello_hybrid: src/hello_hybrid.cpp src/common.hpp | bin
	$(MPICXX) $(CXXFLAGS) $(OPENMP_FLAGS) src/hello_hybrid.cpp -o $@ $(LDFLAGS)

clean:
	rm -f bin/jacobi_serial bin/jacobi_parallel bin/hello_hybrid

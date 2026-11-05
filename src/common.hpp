#pragma once
#include <algorithm>
#include <chrono>
#include <cmath>
#include <cstddef>
#include <fstream>
#include <iomanip>
#include <iostream>
#include <limits>
#include <sstream>
#include <stdexcept>
#include <string>
#include <vector>

struct Options {
    int dim = 2;
    int n = 64;
    int iters = 1000;
    int check = 10;
    int threads = 1;
    double tol = 1e-8;
    std::string mode = "benchmark";
    std::string variant;
    std::string dump;
    bool profile = false;
    bool help = false;
};

inline int parse_int(const std::string& s) {
    std::size_t used = 0;
    long long v = std::stoll(s, &used);
    if (used != s.size() || v < 0 || v > std::numeric_limits<int>::max())
        throw std::invalid_argument("invalid nonnegative integer: " + s);
    return static_cast<int>(v);
}

// Each executable explicitly opts in to dimensions it actually implements.
inline Options parse_options(int argc, char** argv, const std::string& default_variant,
                             int max_dim = 2, bool allow_cuda = false) {
    Options o;
    o.variant = default_variant;
    for (int i = 1; i < argc; ++i) {
        std::string key = argv[i];
        if (key == "--help") { o.help = true; continue; }
        if (key == "--profile") { o.profile = true; continue; }
        if (i + 1 >= argc) throw std::invalid_argument("missing value for " + key);
        std::string value = argv[++i];
        if (key == "--dim") o.dim = parse_int(value);
        else if (key == "--n") o.n = parse_int(value);
        else if (key == "--iters") o.iters = parse_int(value);
        else if (key == "--check") o.check = parse_int(value);
        else if (key == "--threads") o.threads = parse_int(value);
        else if (key == "--tol") {
            std::size_t used = 0;
            o.tol = std::stod(value, &used);
            if (used != value.size()) throw std::invalid_argument("invalid tolerance");
        }
        else if (key == "--mode") o.mode = value;
        else if (key == "--variant") o.variant = value;
        else if (key == "--dump") o.dump = value;
        else throw std::invalid_argument("unknown option: " + key);
    }
    if (o.dim != 2 && o.dim != 3)
        throw std::invalid_argument("dim must be 2 or 3");
    if (o.dim > max_dim)
        throw std::invalid_argument("this binary does not yet implement the requested dimension");
    if (o.n < 1 || o.n > 20000 || o.iters < 1 || o.threads < 1)
        throw std::invalid_argument("require 1<=n<=20000, iters>=1, threads>=1");
    if (!std::isfinite(o.tol) || o.tol <= 0)
        throw std::invalid_argument("tol must be finite and positive");
    if (o.mode != "benchmark" && o.mode != "solve")
        throw std::invalid_argument("mode must be benchmark or solve");
    if (o.mode == "solve" && o.check == 0)
        throw std::invalid_argument("solve mode requires check>=1");
    if (o.variant != "serial" && o.variant != "mpi" &&
        o.variant != "hybrid" && o.variant != "overlap" && !(allow_cuda && o.variant == "cuda"))
        throw std::invalid_argument("variant unsupported by this executable");
    return o;
}

inline void print_help() {
    std::cout << "Options: --dim 2|3 (default 2; supported dimensions depend on binary)\n"
              << "         --n N --iters K --mode benchmark|solve --check Q\n"
              << "         --tol EPS --threads T --variant serial|mpi|hybrid|overlap (CUDA binary: cuda)\n"
              << "         --dump PATH --profile --help\n"
              << "N counts INTERIOR points per dimension; boundary values are zero.\n"
              << "benchmark: exactly K iterations; check=0 disables timed residual checks.\n"
              << "solve: relative L2 residual stopping; final iteration always checked.\n";
}

inline double exact(double x, double y) { return x * (1-x) * y * (1-y); }
inline double forcing(double x, double y) { return 2 * (x*(1-x) + y*(1-y)); }
inline double exact(double x, double y, double z) {
    return x*(1-x)*y*(1-y)*z*(1-z);
}
inline double forcing(double x, double y, double z) {
    const double ax=x*(1-x), ay=y*(1-y), az=z*(1-z);
    return 2*(ay*az+ax*az+ax*ay);
}

inline std::size_t checked_product(std::size_t a, std::size_t b) {
    if (b != 0 && a > std::numeric_limits<std::size_t>::max()/b)
        throw std::length_error("grid size multiplication overflow");
    return a*b;
}

inline std::size_t grid_cells(std::size_t side, int dim) {
    if (dim != 2 && dim != 3) throw std::invalid_argument("dim must be 2 or 3");
    std::size_t cells=checked_product(side,side);
    if (dim == 3) cells=checked_product(cells,side);
    // Check both vector capacity and aggregate bytes for the three main grids.
    checked_product(checked_product(cells,sizeof(double)),3);
    if (cells > std::vector<double>().max_size())
        throw std::length_error("grid exceeds vector capacity");
    return cells;
}

inline std::string json_string(const std::string& s) {
    std::ostringstream out;
    out << '"';
    for (unsigned char c : s) {
        if (c == '"' || c == '\\') out << '\\' << c;
        else if (c == '\n') out << "\\n";
        else if (c == '\r') out << "\\r";
        else if (c == '\t') out << "\\t";
        else if (c < 32) out << "\\u" << std::hex << std::setw(4)
                             << std::setfill('0') << static_cast<int>(c) << std::dec;
        else out << c;
    }
    out << '"';
    return out.str();
}

struct Result {
    std::string backend = "cpu";
    int gpu_count = 0;
    std::string gpu_model;
    double end_to_end_seconds = 0;
    int ranks = 1;
    int threads = 1;
    int iterations = 0;
    double seconds = 0;
    double residual = 0;
    double error_l2 = 0;
    double error_max = 0;
    double post_seconds = 0;
    double wait_seconds = 0;
    double compute_seconds = 0;
    double check_seconds = 0;
    bool converged = false;
};

inline void print_result(const Options& o, const Result& r) {
    std::cout << std::setprecision(17)
      << "{\"variant\":" << json_string(o.variant)
      << ",\"dim\":" << o.dim << ",\"backend\":" << json_string(r.backend)
      << ",\"problem\":\"polynomial\",\"n\":" << o.n
      << ",\"mode\":" << json_string(o.mode)
      << ",\"max_iters\":" << o.iters << ",\"iterations\":" << r.iterations
      << ",\"check_interval\":" << o.check << ",\"tolerance\":" << o.tol
      << ",\"ranks\":" << r.ranks << ",\"threads\":" << r.threads
      << ",\"cores\":" << r.ranks*r.threads
      << ",\"solve_seconds_max\":" << r.seconds
      << ",\"final_residual\":" << r.residual
      << ",\"relative_error_l2\":" << r.error_l2
      << ",\"error_max\":" << r.error_max
      << ",\"converged\":" << (r.converged ? "true" : "false")
      << ",\"profile\":" << (o.profile ? "true" : "false")
      << ",\"post_seconds_max\":" << r.post_seconds
      << ",\"wait_seconds_max\":" << r.wait_seconds
      << ",\"compute_seconds_max\":" << r.compute_seconds
      << ",\"check_seconds_max\":" << r.check_seconds;
    if (r.backend == "cuda")
        std::cout << ",\"gpu_count\":" << r.gpu_count
                  << ",\"gpu_model\":" << json_string(r.gpu_model)
                  << ",\"end_to_end_seconds_max\":" << r.end_to_end_seconds;
    std::cout << "}\n";
}

// Interior-only 3D grid in z/y/x order, with x contiguous. Indices are 1-based.
inline void dump_grid(const std::string& path, int n, const std::vector<double>& grid);
inline void dump_grid(const std::string& path, int n, const std::vector<double>& grid, int dim) {
    if (dim == 2) { dump_grid(path,n,grid); return; }
    if (dim != 3) throw std::invalid_argument("dim must be 2 or 3");
    if (path.empty()) return;
    if (grid.size() != grid_cells(static_cast<std::size_t>(n),dim))
        throw std::invalid_argument("wrong 3D dump grid size");
    std::ofstream out(path);
    if (!out) throw std::runtime_error("cannot open dump path: " + path);
    out << "x,y,z,u\n" << std::setprecision(17);
    std::size_t at=0;
    for (int z=1; z<=n; ++z) for (int y=1; y<=n; ++y) for (int x=1; x<=n; ++x)
        out << x << ',' << y << ',' << z << ',' << grid[at++] << '\n';
    if (!out) throw std::runtime_error("failed while writing dump: " + path);
}

inline void dump_grid(const std::string& path, int n, const std::vector<double>& grid) {
    if (path.empty()) return;
    std::ofstream out(path);
    if (!out) throw std::runtime_error("cannot open dump path: " + path);
    out << "i,j,u\n" << std::setprecision(17);
    for (int i=0; i<n; ++i)
        for (int j=0; j<n; ++j)
            out << i+1 << ',' << j+1 << ',' << grid[static_cast<std::size_t>(i)*n+j] << '\n';
    if (!out) throw std::runtime_error("failed while writing dump: " + path);
}

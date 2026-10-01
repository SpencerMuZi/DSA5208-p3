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

inline Options parse_options(int argc, char** argv, const std::string& default_variant) {
    Options o;
    o.variant = default_variant;
    for (int i = 1; i < argc; ++i) {
        std::string key = argv[i];
        if (key == "--help") { o.help = true; continue; }
        if (key == "--profile") { o.profile = true; continue; }
        if (i + 1 >= argc) throw std::invalid_argument("missing value for " + key);
        std::string value = argv[++i];
        if (key == "--n") o.n = parse_int(value);
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
    if (o.n < 1 || o.n > 20000 || o.iters < 1 || o.threads < 1)
        throw std::invalid_argument("require 1<=n<=20000, iters>=1, threads>=1");
    if (!std::isfinite(o.tol) || o.tol <= 0)
        throw std::invalid_argument("tol must be finite and positive");
    if (o.mode != "benchmark" && o.mode != "solve")
        throw std::invalid_argument("mode must be benchmark or solve");
    if (o.mode == "solve" && o.check == 0)
        throw std::invalid_argument("solve mode requires check>=1");
    if (o.variant != "serial" && o.variant != "mpi" &&
        o.variant != "hybrid" && o.variant != "overlap")
        throw std::invalid_argument("variant must be serial, mpi, hybrid, or overlap");
    return o;
}

inline void print_help() {
    std::cout << "Options: --n N --iters K --mode benchmark|solve --check Q\n"
              << "         --tol EPS --threads T --variant serial|mpi|hybrid|overlap\n"
              << "         --dump PATH --profile --help\n"
              << "N counts INTERIOR points per dimension; boundary values are zero.\n"
              << "benchmark: exactly K iterations; check=0 disables timed residual checks.\n"
              << "solve: relative L2 residual stopping; final iteration always checked.\n";
}

inline double exact(double x, double y) { return x * (1-x) * y * (1-y); }
inline double forcing(double x, double y) { return 2 * (x*(1-x) + y*(1-y)); }

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
      << ",\"check_seconds_max\":" << r.check_seconds << "}\n";
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

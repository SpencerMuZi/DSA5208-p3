#include "common.hpp"

// Kept separate from the original 2D loop to preserve its arithmetic order.
static Result solve_3d(const Options& o) {
    const std::size_t stride=static_cast<std::size_t>(o.n)+2;
    const std::size_t plane=checked_product(stride,stride);
    const std::size_t cells=grid_cells(stride,3);
    const double h=1.0/(o.n+1), h2=h*h;
    std::vector<double> old(cells,0), next(cells,0), rhs(cells,0);
    double rhs_sq=0;
    for (int z=1; z<=o.n; ++z) for (int y=1; y<=o.n; ++y) for (int x=1; x<=o.n; ++x) {
        const std::size_t at=static_cast<std::size_t>(z)*plane+static_cast<std::size_t>(y)*stride+x;
        const double f=forcing(x*h,y*h,z*h);
        rhs[at]=f;
        rhs_sq+=f*f;
    }
    auto residual=[&]() {
        double sum=0;
        for (int z=1; z<=o.n; ++z) for (int y=1; y<=o.n; ++y) for (int x=1; x<=o.n; ++x) {
            const std::size_t at=static_cast<std::size_t>(z)*plane+static_cast<std::size_t>(y)*stride+x;
            const double au=(6*old[at]-old[at-plane]-old[at+plane]
                             -old[at-stride]-old[at+stride]-old[at-1]-old[at+1])/h2;
            const double v=rhs[at]-au;
            sum+=v*v;
        }
        return std::sqrt(sum/rhs_sq);
    };
    Result r;
    const auto start=std::chrono::steady_clock::now();
    for (int step=0; step<o.iters; ++step) {
        auto begin_compute=std::chrono::steady_clock::time_point{};
        if (o.profile) begin_compute=std::chrono::steady_clock::now();
        for (int z=1; z<=o.n; ++z) for (int y=1; y<=o.n; ++y) for (int x=1; x<=o.n; ++x) {
            const std::size_t at=static_cast<std::size_t>(z)*plane+static_cast<std::size_t>(y)*stride+x;
            next[at]=(old[at-plane]+old[at+plane]+old[at-stride]+old[at+stride]
                      +old[at-1]+old[at+1]+h2*rhs[at])/6.0;
        }
        old.swap(next);
        if (o.profile) r.compute_seconds+=std::chrono::duration<double>(
            std::chrono::steady_clock::now()-begin_compute).count();
        r.iterations=step+1;
        if ((o.check>0 && r.iterations%o.check==0) || (o.mode=="solve" && r.iterations==o.iters)) {
            auto begin_check=std::chrono::steady_clock::time_point{};
            if (o.profile) begin_check=std::chrono::steady_clock::now();
            r.residual=residual();
            if (o.profile) r.check_seconds+=std::chrono::duration<double>(
                std::chrono::steady_clock::now()-begin_check).count();
            if (o.mode=="solve" && r.residual<=o.tol) break;
        }
    }
    r.seconds=std::chrono::duration<double>(std::chrono::steady_clock::now()-start).count();
    // Initialization, final residual/error and CSV export are outside solver timing.
    r.residual=residual();
    r.converged=(r.residual<=o.tol);
    double err_sq=0, exact_sq=0;
    std::vector<double> interior;
    if (!o.dump.empty()) interior.reserve(grid_cells(static_cast<std::size_t>(o.n),3));
    for (int z=1; z<=o.n; ++z) for (int y=1; y<=o.n; ++y) for (int x=1; x<=o.n; ++x) {
        const std::size_t at=static_cast<std::size_t>(z)*plane+static_cast<std::size_t>(y)*stride+x;
        const double value=old[at], truth=exact(x*h,y*h,z*h), err=value-truth;
        err_sq+=err*err;
        exact_sq+=truth*truth;
        r.error_max=std::max(r.error_max,std::abs(err));
        if (!o.dump.empty()) interior.push_back(value);
    }
    r.error_l2=std::sqrt(err_sq/exact_sq);
    dump_grid(o.dump,o.n,interior,3);
    return r;
}

int main(int argc, char** argv) {
    try {
        Options o = parse_options(argc, argv, "serial", 3);
        if (o.help) { print_help(); return 0; }
        if (o.variant != "serial" || o.threads != 1)
            throw std::invalid_argument("serial binary requires variant=serial, threads=1");
        if (o.dim == 3) {
            const Result r=solve_3d(o);
            print_result(o,r);
            return (o.mode=="solve" && !r.converged) ? 2 : 0;
        }
        const int stride = o.n + 2;
        const double h = 1.0/(o.n+1), h2 = h*h;
        const std::size_t cells = grid_cells(static_cast<std::size_t>(stride),2);
        std::vector<double> old(cells,0), next(cells,0), rhs(cells,0);
        double rhs_sq = 0;
        for (int i=1; i<=o.n; ++i) for (int j=1; j<=o.n; ++j) {
            double f = forcing(i*h,j*h);
            rhs[static_cast<std::size_t>(i)*stride+j] = f;
            rhs_sq += f*f;
        }
        auto residual = [&]() {
            double sum = 0;
            for (int i=1; i<=o.n; ++i) for (int j=1; j<=o.n; ++j) {
                std::size_t z=static_cast<std::size_t>(i)*stride+j;
                double au=(4*old[z]-old[z-stride]-old[z+stride]-old[z-1]-old[z+1])/h2;
                double v=rhs[z]-au;
                sum+=v*v;
            }
            return std::sqrt(sum/rhs_sq);
        };
        Result r;
        auto start = std::chrono::steady_clock::now();
        for (int k=1; k<=o.iters; ++k) {
            auto begin_compute = std::chrono::steady_clock::time_point{};
            if (o.profile) begin_compute = std::chrono::steady_clock::now();
            for (int i=1; i<=o.n; ++i) for (int j=1; j<=o.n; ++j) {
                std::size_t z=static_cast<std::size_t>(i)*stride+j;
                next[z]=0.25*(old[z-stride]+old[z+stride]+old[z-1]+old[z+1]+h2*rhs[z]);
            }
            old.swap(next);
            if (o.profile) r.compute_seconds += std::chrono::duration<double>(
                std::chrono::steady_clock::now()-begin_compute).count();
            r.iterations=k;
            if ((o.check>0 && k%o.check==0) || (o.mode=="solve" && k==o.iters)) {
                auto begin_check = std::chrono::steady_clock::time_point{};
                if (o.profile) begin_check = std::chrono::steady_clock::now();
                r.residual=residual();
                if (o.profile) r.check_seconds += std::chrono::duration<double>(
                    std::chrono::steady_clock::now()-begin_check).count();
                if (o.mode=="solve" && r.residual<=o.tol) break;
            }
        }
        r.seconds=std::chrono::duration<double>(std::chrono::steady_clock::now()-start).count();
        // The unconditional final residual and error verification are outside timing.
        r.residual=residual();
        r.converged=(r.residual<=o.tol);
        double err_sq=0, exact_sq=0;
        std::vector<double> interior;
        if (!o.dump.empty()) interior.reserve(static_cast<std::size_t>(o.n)*o.n);
        for (int i=1; i<=o.n; ++i) for (int j=1; j<=o.n; ++j) {
            double value=old[static_cast<std::size_t>(i)*stride+j];
            double truth=exact(i*h,j*h), err=value-truth;
            err_sq+=err*err;
            exact_sq+=truth*truth;
            r.error_max=std::max(r.error_max,std::abs(err));
            if (!o.dump.empty()) interior.push_back(value);
        }
        r.error_l2=std::sqrt(err_sq/exact_sq);
        dump_grid(o.dump,o.n,interior);
        print_result(o,r);
        return (o.mode=="solve" && !r.converged) ? 2 : 0;
    } catch (const std::exception& e) {
        std::cerr << "ERROR: " << e.what() << '\n';
        return 1;
    }
}

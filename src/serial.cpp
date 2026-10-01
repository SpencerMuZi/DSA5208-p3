#include "common.hpp"

int main(int argc, char** argv) {
    try {
        Options o = parse_options(argc, argv, "serial");
        if (o.help) { print_help(); return 0; }
        if (o.variant != "serial" || o.threads != 1)
            throw std::invalid_argument("serial binary requires variant=serial, threads=1");
        const int stride = o.n + 2;
        const double h = 1.0/(o.n+1), h2 = h*h;
        const std::size_t cells = static_cast<std::size_t>(stride)*stride;
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

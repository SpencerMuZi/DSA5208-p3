#include "common.hpp"
#include <mpi.h>
#include <omp.h>

int main(int argc, char** argv) {
    int provided=0;
    MPI_Init_thread(&argc,&argv,MPI_THREAD_FUNNELED,&provided);
    int rank=0,size=0;
    MPI_Comm_rank(MPI_COMM_WORLD,&rank);
    MPI_Comm_size(MPI_COMM_WORLD,&size);
    try {
        Options o=parse_options(argc,argv,"mpi");
        if (o.help) { if (rank==0) print_help(); MPI_Finalize(); return 0; }
        if (provided<MPI_THREAD_FUNNELED) throw std::runtime_error("MPI lacks THREAD_FUNNELED");
        if (o.variant=="serial") throw std::invalid_argument("use serial binary for variant=serial");
        if (o.variant=="mpi" && o.threads!=1) throw std::invalid_argument("mpi variant requires threads=1");
        if (size>o.n) throw std::invalid_argument("ranks must not exceed interior row count n");
        const bool threaded=o.variant!="mpi";
        const bool overlap=o.variant=="overlap";
        omp_set_dynamic(0);
        omp_set_num_threads(o.threads);
        int actual_threads=1;
        #pragma omp parallel if(threaded)
        {
            #pragma omp single
            actual_threads=omp_get_num_threads();
        }
        int min_threads=0,max_threads=0;
        MPI_Allreduce(&actual_threads,&min_threads,1,MPI_INT,MPI_MIN,MPI_COMM_WORLD);
        MPI_Allreduce(&actual_threads,&max_threads,1,MPI_INT,MPI_MAX,MPI_COMM_WORLD);
        if (min_threads!=o.threads || max_threads!=o.threads)
            throw std::runtime_error("actual OpenMP thread count differs from requested threads");
        const int base=o.n/size, remainder=o.n%size;
        const int rows=base+(rank<remainder ? 1 : 0);
        const int offset=rank*base+std::min(rank,remainder);
        const int stride=o.n+2;
        const int up=rank==0 ? MPI_PROC_NULL : rank-1;
        const int down=rank+1==size ? MPI_PROC_NULL : rank+1;
        const double h=1.0/(o.n+1),h2=h*h;
        std::vector<double> old(static_cast<std::size_t>(rows+2)*stride,0);
        std::vector<double> next(old.size(),0),rhs(old.size(),0);
        double local_rhs_sq=0;
        // Fill RHS in parallel; vector zero-initialization above is serial.
        #pragma omp parallel for if(threaded) schedule(static) reduction(+:local_rhs_sq)
        for (int i=1; i<=rows; ++i) for (int j=1; j<=o.n; ++j) {
            std::size_t z=static_cast<std::size_t>(i)*stride+j;
            rhs[z]=forcing((offset+i)*h,j*h);
            local_rhs_sq+=rhs[z]*rhs[z];
        }
        double rhs_sq=0;
        MPI_Allreduce(&local_rhs_sq,&rhs_sq,1,MPI_DOUBLE,MPI_SUM,MPI_COMM_WORLD);
        auto exchange_blocking=[&]() {
            MPI_Sendrecv(old.data()+stride+1,o.n,MPI_DOUBLE,up,101,
                         old.data()+static_cast<std::size_t>(rows+1)*stride+1,o.n,MPI_DOUBLE,down,101,
                         MPI_COMM_WORLD,MPI_STATUS_IGNORE);
            MPI_Sendrecv(old.data()+static_cast<std::size_t>(rows)*stride+1,o.n,MPI_DOUBLE,down,102,
                         old.data()+1,o.n,MPI_DOUBLE,up,102,
                         MPI_COMM_WORLD,MPI_STATUS_IGNORE);
        };
        auto update=[&](int first,int last) {
            #pragma omp parallel for if(threaded) schedule(static)
            for (int i=first; i<=last; ++i) for (int j=1; j<=o.n; ++j) {
                std::size_t z=static_cast<std::size_t>(i)*stride+j;
                next[z]=0.25*(old[z-stride]+old[z+stride]+old[z-1]+old[z+1]+h2*rhs[z]);
            }
        };
        auto residual=[&]() {
            // The residual uses the CURRENT iterate and therefore fresh halos.
            exchange_blocking();
            double local=0,total=0;
            #pragma omp parallel for if(threaded) schedule(static) reduction(+:local)
            for (int i=1; i<=rows; ++i) for (int j=1; j<=o.n; ++j) {
                std::size_t z=static_cast<std::size_t>(i)*stride+j;
                double au=(4*old[z]-old[z-stride]-old[z+stride]-old[z-1]-old[z+1])/h2;
                double v=rhs[z]-au;
                local+=v*v;
            }
            MPI_Allreduce(&local,&total,1,MPI_DOUBLE,MPI_SUM,MPI_COMM_WORLD);
            return std::sqrt(total/rhs_sq);
        };
        Result r;
        r.ranks=size;
        r.threads=actual_threads;
        MPI_Barrier(MPI_COMM_WORLD);
        double start=MPI_Wtime();
        for (int k=1; k<=o.iters; ++k) {
            double phase=o.profile ? MPI_Wtime() : 0;
            if (!overlap) {
                exchange_blocking();
                if (o.profile) { r.wait_seconds+=MPI_Wtime()-phase; phase=MPI_Wtime(); }
                update(1,rows);
                if (o.profile) r.compute_seconds+=MPI_Wtime()-phase;
            } else {
                MPI_Request requests[4];
                MPI_Irecv(old.data()+1,o.n,MPI_DOUBLE,up,102,MPI_COMM_WORLD,&requests[0]);
                MPI_Irecv(old.data()+static_cast<std::size_t>(rows+1)*stride+1,o.n,MPI_DOUBLE,down,101,
                          MPI_COMM_WORLD,&requests[1]);
                MPI_Isend(old.data()+stride+1,o.n,MPI_DOUBLE,up,101,MPI_COMM_WORLD,&requests[2]);
                MPI_Isend(old.data()+static_cast<std::size_t>(rows)*stride+1,o.n,MPI_DOUBLE,down,102,
                          MPI_COMM_WORLD,&requests[3]);
                if (o.profile) { r.post_seconds+=MPI_Wtime()-phase; phase=MPI_Wtime(); }
                if (rows>2) update(2,rows-1);
                if (o.profile) { r.compute_seconds+=MPI_Wtime()-phase; phase=MPI_Wtime(); }
                MPI_Waitall(4,requests,MPI_STATUSES_IGNORE);
                if (o.profile) { r.wait_seconds+=MPI_Wtime()-phase; phase=MPI_Wtime(); }
                update(1,1);
                if (rows>1) update(rows,rows);
                if (o.profile) r.compute_seconds+=MPI_Wtime()-phase;
            }
            old.swap(next);
            r.iterations=k;
            if ((o.check>0 && k%o.check==0) || (o.mode=="solve" && k==o.iters)) {
                phase=o.profile ? MPI_Wtime() : 0;
                r.residual=residual();
                if (o.profile) r.check_seconds+=MPI_Wtime()-phase;
                if (o.mode=="solve" && r.residual<=o.tol) break;
            }
        }
        double elapsed=MPI_Wtime()-start;
        MPI_Allreduce(&elapsed,&r.seconds,1,MPI_DOUBLE,MPI_MAX,MPI_COMM_WORLD);
        // Verification, final residual and any gather/dump are outside solve timing.
        r.residual=residual();
        r.converged=(r.residual<=o.tol);
        double err_sq=0,truth_sq=0,max_err=0;
        #pragma omp parallel for if(threaded) schedule(static) reduction(+:err_sq,truth_sq) reduction(max:max_err)
        for (int i=1; i<=rows; ++i) for (int j=1; j<=o.n; ++j) {
            double truth=exact((offset+i)*h,j*h);
            double err=old[static_cast<std::size_t>(i)*stride+j]-truth;
            err_sq+=err*err;
            truth_sq+=truth*truth;
            max_err=std::max(max_err,std::abs(err));
        }
        double local_sums[2]={err_sq,truth_sq},global_sums[2];
        MPI_Allreduce(local_sums,global_sums,2,MPI_DOUBLE,MPI_SUM,MPI_COMM_WORLD);
        MPI_Allreduce(&max_err,&r.error_max,1,MPI_DOUBLE,MPI_MAX,MPI_COMM_WORLD);
        r.error_l2=std::sqrt(global_sums[0]/global_sums[1]);
        double parts[4]={r.post_seconds,r.wait_seconds,r.compute_seconds,r.check_seconds},max_parts[4];
        MPI_Allreduce(parts,max_parts,4,MPI_DOUBLE,MPI_MAX,MPI_COMM_WORLD);
        r.post_seconds=max_parts[0]; r.wait_seconds=max_parts[1];
        r.compute_seconds=max_parts[2]; r.check_seconds=max_parts[3];
        if (!o.dump.empty()) {
            // n<=20000 ensures n*n and all MPI_Gatherv int counts fit int.
            std::vector<double> local(static_cast<std::size_t>(rows)*o.n);
            for (int i=1; i<=rows; ++i)
                std::copy_n(old.data()+static_cast<std::size_t>(i)*stride+1,o.n,
                            local.data()+static_cast<std::size_t>(i-1)*o.n);
            std::vector<int> counts(size),displs(size);
            for (int p=0; p<size; ++p) {
                counts[p]=(base+(p<remainder ? 1 : 0))*o.n;
                displs[p]=(p*base+std::min(p,remainder))*o.n;
            }
            std::vector<double> grid;
            if (rank==0) grid.resize(static_cast<std::size_t>(o.n)*o.n);
            MPI_Gatherv(local.data(),rows*o.n,MPI_DOUBLE,grid.data(),counts.data(),displs.data(),
                        MPI_DOUBLE,0,MPI_COMM_WORLD);
            if (rank==0) dump_grid(o.dump,o.n,grid);
        }
        if (rank==0) print_result(o,r);
        int status=(o.mode=="solve" && !r.converged) ? 2 : 0;
        MPI_Finalize();
        return status;
    } catch (const std::exception& e) {
        if (rank==0) std::cerr << "ERROR: " << e.what() << '\n';
        MPI_Abort(MPI_COMM_WORLD,1);
        return 1;
    }
}

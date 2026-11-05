#pragma once

// Included after common.hpp, mpi.h and omp.h. MPI calls stay on the main thread.
inline Result solve_parallel_3d(const Options& o, int rank, int size, int threads) {
    const bool threaded=o.variant!="mpi", overlap=o.variant=="overlap";
    const int base=o.n/size, rem=o.n%size;
    const int nz=base+(rank<rem), offset=rank*base+std::min(rank,rem);
    const int up=rank==0 ? MPI_PROC_NULL : rank-1;
    const int down=rank+1==size ? MPI_PROC_NULL : rank+1;
    const std::size_t stride=static_cast<std::size_t>(o.n)+2;
    const std::size_t plane=checked_product(stride,stride);
    if (plane>static_cast<std::size_t>(std::numeric_limits<int>::max()))
        throw std::length_error("3D halo plane exceeds MPI int count");
    const int count=static_cast<int>(plane);
    const std::size_t cells=checked_product(static_cast<std::size_t>(nz)+2,plane);
    checked_product(checked_product(cells,sizeof(double)),3);
    if (cells>std::vector<double>().max_size())
        throw std::length_error("3D local allocation exceeds vector capacity");
    const std::size_t interior_plane=checked_product(o.n,o.n);
    const std::size_t interior_cells=checked_product(interior_plane,o.n);
    // Gatherv uses int counts/displacements; benchmarks without dumps need no gather.
    if (!o.dump.empty() && interior_cells>static_cast<std::size_t>(std::numeric_limits<int>::max()))
        throw std::length_error("3D dump exceeds MPI_Gatherv int count limit");
    std::vector<double> old(cells,0),next(cells,0),rhs(cells,0);
    const double h=1.0/(o.n+1), h2=h*h;
    double local_rhs_sq=0,rhs_sq=0;
    #pragma omp parallel for collapse(2) if(threaded) schedule(static) reduction(+:local_rhs_sq)
    for (int z=1; z<=nz; ++z) for (int y=1; y<=o.n; ++y)
        for (int x=1; x<=o.n; ++x) {
            const std::size_t at=z*plane+y*stride+x;
            rhs[at]=forcing(x*h,y*h,(offset+z)*h);
            local_rhs_sq+=rhs[at]*rhs[at];
        }
    MPI_Allreduce(&local_rhs_sq,&rhs_sq,1,MPI_DOUBLE,MPI_SUM,MPI_COMM_WORLD);
    auto exchange=[&]() {
        MPI_Sendrecv(old.data()+plane,count,MPI_DOUBLE,up,101,
                     old.data()+(nz+1)*plane,count,MPI_DOUBLE,down,101,
                     MPI_COMM_WORLD,MPI_STATUS_IGNORE);
        MPI_Sendrecv(old.data()+nz*plane,count,MPI_DOUBLE,down,102,
                     old.data(),count,MPI_DOUBLE,up,102,
                     MPI_COMM_WORLD,MPI_STATUS_IGNORE);
    };
    auto update=[&](int first,int last) {
        #pragma omp parallel for collapse(2) if(threaded) schedule(static)
        for (int z=first; z<=last; ++z) for (int y=1; y<=o.n; ++y)
            for (int x=1; x<=o.n; ++x) {
                const std::size_t at=z*plane+y*stride+x;
                next[at]=(old[at-plane]+old[at+plane]+old[at-stride]+old[at+stride]
                         +old[at-1]+old[at+1]+h2*rhs[at])/6.0;
            }
    };
    auto residual=[&]() {
        exchange(); // Residual must use halos from the current iterate.
        double local=0,total=0;
        #pragma omp parallel for collapse(2) if(threaded) schedule(static) reduction(+:local)
        for (int z=1; z<=nz; ++z) for (int y=1; y<=o.n; ++y)
            for (int x=1; x<=o.n; ++x) {
                const std::size_t at=z*plane+y*stride+x;
                const double au=(6*old[at]-old[at-plane]-old[at+plane]
                    -old[at-stride]-old[at+stride]-old[at-1]-old[at+1])/h2;
                const double v=rhs[at]-au;
                local+=v*v;
            }
        MPI_Allreduce(&local,&total,1,MPI_DOUBLE,MPI_SUM,MPI_COMM_WORLD);
        return std::sqrt(total/rhs_sq);
    };
    Result r;
    r.ranks=size; r.threads=threads;
    MPI_Barrier(MPI_COMM_WORLD);
    const double start=MPI_Wtime();
    for (int step=0; step<o.iters; ++step) {
        double phase=o.profile ? MPI_Wtime() : 0;
        if (!overlap) {
            exchange();
            if (o.profile) { r.wait_seconds+=MPI_Wtime()-phase; phase=MPI_Wtime(); }
            update(1,nz);
            if (o.profile) r.compute_seconds+=MPI_Wtime()-phase;
        } else {
            MPI_Request requests[4];
            MPI_Irecv(old.data(),count,MPI_DOUBLE,up,102,MPI_COMM_WORLD,&requests[0]);
            MPI_Irecv(old.data()+(nz+1)*plane,count,MPI_DOUBLE,down,101,MPI_COMM_WORLD,&requests[1]);
            MPI_Isend(old.data()+plane,count,MPI_DOUBLE,up,101,MPI_COMM_WORLD,&requests[2]);
            MPI_Isend(old.data()+nz*plane,count,MPI_DOUBLE,down,102,MPI_COMM_WORLD,&requests[3]);
            if (o.profile) { r.post_seconds+=MPI_Wtime()-phase; phase=MPI_Wtime(); }
            if (nz>2) update(2,nz-1);
            if (o.profile) { r.compute_seconds+=MPI_Wtime()-phase; phase=MPI_Wtime(); }
            MPI_Waitall(4,requests,MPI_STATUSES_IGNORE);
            if (o.profile) { r.wait_seconds+=MPI_Wtime()-phase; phase=MPI_Wtime(); }
            update(1,1);
            if (nz>1) update(nz,nz);
            if (o.profile) r.compute_seconds+=MPI_Wtime()-phase;
        }
        old.swap(next);
        r.iterations=step+1;
        if ((o.check>0 && r.iterations%o.check==0) || (o.mode=="solve" && r.iterations==o.iters)) {
            phase=o.profile ? MPI_Wtime() : 0;
            r.residual=residual();
            if (o.profile) r.check_seconds+=MPI_Wtime()-phase;
            if (o.mode=="solve" && r.residual<=o.tol) break;
        }
    }
    const double elapsed=MPI_Wtime()-start;
    MPI_Allreduce(&elapsed,&r.seconds,1,MPI_DOUBLE,MPI_MAX,MPI_COMM_WORLD);
    // Final verification and dump are excluded from the timed solver loop.
    r.residual=residual(); r.converged=r.residual<=o.tol;
    double err_sq=0,truth_sq=0,max_err=0;
    #pragma omp parallel for collapse(2) if(threaded) schedule(static) reduction(+:err_sq,truth_sq) reduction(max:max_err)
    for (int z=1; z<=nz; ++z) for (int y=1; y<=o.n; ++y)
        for (int x=1; x<=o.n; ++x) {
            const double truth=exact(x*h,y*h,(offset+z)*h);
            const double err=old[z*plane+y*stride+x]-truth;
            err_sq+=err*err; truth_sq+=truth*truth;
            max_err=std::max(max_err,std::abs(err));
        }
    double sums[2]={err_sq,truth_sq},totals[2];
    MPI_Allreduce(sums,totals,2,MPI_DOUBLE,MPI_SUM,MPI_COMM_WORLD);
    MPI_Allreduce(&max_err,&r.error_max,1,MPI_DOUBLE,MPI_MAX,MPI_COMM_WORLD);
    r.error_l2=std::sqrt(totals[0]/totals[1]);
    double parts[4]={r.post_seconds,r.wait_seconds,r.compute_seconds,r.check_seconds},max_parts[4];
    MPI_Allreduce(parts,max_parts,4,MPI_DOUBLE,MPI_MAX,MPI_COMM_WORLD);
    r.post_seconds=max_parts[0]; r.wait_seconds=max_parts[1];
    r.compute_seconds=max_parts[2]; r.check_seconds=max_parts[3];
    if (!o.dump.empty()) {
        std::vector<double> local(checked_product(nz,interior_plane)),grid;
        for (int z=1; z<=nz; ++z) for (int y=1; y<=o.n; ++y)
            std::copy_n(old.data()+z*plane+y*stride+1,o.n,
                        local.data()+(z-1)*interior_plane+static_cast<std::size_t>(y-1)*o.n);
        std::vector<int> counts(size),displs(size);
        for (int p=0; p<size; ++p) {
            counts[p]=static_cast<int>((base+(p<rem))*interior_plane);
            displs[p]=static_cast<int>((p*base+std::min(p,rem))*interior_plane);
        }
        if (rank==0) grid.resize(interior_cells);
        MPI_Gatherv(local.data(),static_cast<int>(local.size()),MPI_DOUBLE,
                    grid.data(),counts.data(),displs.data(),MPI_DOUBLE,0,MPI_COMM_WORLD);
        if (rank==0) dump_grid(o.dump,o.n,grid,3);
    }
    return r;
}

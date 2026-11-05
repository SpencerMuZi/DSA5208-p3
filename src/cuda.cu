#include "common.hpp"
#include "topology.hpp"
#include <mpi.h>
#include <cuda_runtime.h>
#include <set>

static void cu(cudaError_t e) {
    if (e!=cudaSuccess) throw std::runtime_error(std::string("CUDA: ")+cudaGetErrorString(e));
}
struct DeviceArray {
    double* p=nullptr;
    explicit DeviceArray(std::size_t count) { cu(cudaMalloc(reinterpret_cast<void**>(&p),checked_product(count,sizeof(double)))); }
    ~DeviceArray() { if(p) cudaFree(p); }
    DeviceArray(const DeviceArray&)=delete;
    DeviceArray& operator=(const DeviceArray&)=delete;
};
__global__ void jacobi_update(const double* old,double* next,const double* rhs,int n,int rows,int stride,double h2) {
    int x=blockIdx.x*blockDim.x+threadIdx.x+1;
    int y=blockIdx.y*blockDim.y+threadIdx.y+1;
    if (x<=n && y<=rows) {
        std::size_t z=static_cast<std::size_t>(y)*stride+x;
        next[z]=0.25*(old[z-stride]+old[z+stride]+old[z-1]+old[z+1]+h2*rhs[z]);
    }
}
static void print_topology(const std::string& local,int rank,int size) {
    int length=static_cast<int>(local.size());
    std::vector<int> lengths(size),offsets(size);
    MPI_Gather(&length,1,MPI_INT,lengths.data(),1,MPI_INT,0,MPI_COMM_WORLD);
    int total=0;
    if(rank==0) for(int p=0;p<size;++p) { offsets[p]=total;total+=lengths[p]; }
    std::vector<char> data(total);
    MPI_Gatherv(local.data(),length,MPI_CHAR,data.data(),lengths.data(),offsets.data(),MPI_CHAR,0,MPI_COMM_WORLD);
    if(rank==0) for(int p=0;p<size;++p) std::cout<<std::string(data.data()+offsets[p],lengths[p])<<'\n';
}
int main(int argc,char** argv) {
    int provided=0,rank=0,size=0;
    MPI_Init_thread(&argc,&argv,MPI_THREAD_FUNNELED,&provided);
    MPI_Comm_rank(MPI_COMM_WORLD,&rank); MPI_Comm_size(MPI_COMM_WORLD,&size);
    try {
        bool topology=false; std::vector<char*> args;
        for(int i=0;i<argc;++i) {
            if(std::string(argv[i])=="--topology") topology=true; else args.push_back(argv[i]);
        }
        Options o=parse_options(static_cast<int>(args.size()),args.data(),"cuda",2,true);
        if(o.help) { if(rank==0) { print_help();std::cout<<"CUDA: --topology prints rank/device mapping; dim=2, threads=1 only.\n"; } MPI_Finalize();return 0; }
        if(provided<MPI_THREAD_FUNNELED) throw std::runtime_error("MPI lacks THREAD_FUNNELED");
        if(o.variant!="cuda" || o.threads!=1 || o.profile) throw std::invalid_argument("CUDA requires variant=cuda, threads=1, profile=false");
        if(size>o.n && !topology) throw std::invalid_argument("ranks must not exceed n");
        MPI_Comm shared; MPI_Comm_split_type(MPI_COMM_WORLD,MPI_COMM_TYPE_SHARED,rank,MPI_INFO_NULL,&shared);
        int local_rank=0,local_size=0;MPI_Comm_rank(shared,&local_rank);MPI_Comm_size(shared,&local_size);
        int count=0;cu(cudaGetDeviceCount(&count));if(count<1) throw std::runtime_error("no visible CUDA device");
        // PBS may expose one device per rank, or the whole node's device list.
        int device=count==1 ? 0 : local_rank;
        if(device>=count) throw std::runtime_error("more node-local ranks than visible GPUs");
        cu(cudaSetDevice(device));
        cudaDeviceProp prop;cu(cudaGetDeviceProperties(&prop,device));
        char bus[32]={};cu(cudaDeviceGetPCIBusId(bus,sizeof(bus),device));
        std::ostringstream uuid;
        uuid<<std::hex<<std::setfill('0');for(unsigned char c:prop.uuid.bytes) uuid<<std::setw(2)<<static_cast<unsigned>(c);
        std::string gpu_uuid=uuid.str();
        std::vector<char> identifiers(static_cast<std::size_t>(local_size)*33);
        MPI_Allgather(gpu_uuid.c_str(),33,MPI_CHAR,identifiers.data(),33,MPI_CHAR,shared);
        std::set<std::string> unique;
        for(int p=0;p<local_size;++p) unique.insert(std::string(identifiers.data()+p*33,32));
        if(static_cast<int>(unique.size())!=local_size) throw std::runtime_error("multiple local ranks selected the same physical GPU");
        char host[MPI_MAX_PROCESSOR_NAME];int host_len=0;MPI_Get_processor_name(host,&host_len);
        auto masks=local_cpu_masks();
        if(topology) {
            std::ostringstream s;
            s<<"{\"rank\":"<<rank<<",\"size\":"<<size<<",\"host\":"<<json_string(std::string(host,host_len))
             <<",\"threads\":1,\"local_rank\":"<<local_rank<<",\"visible_gpu_count\":"<<count
             <<",\"device\":"<<device<<",\"gpu_uuid\":"<<json_string(gpu_uuid)<<",\"gpu_bus\":"<<json_string(bus)
             <<",\"gpu_model\":"<<json_string(prop.name)<<",\"gpu_memory_bytes\":"<<prop.totalGlobalMem
             <<",\"mpi_thread_support\":"<<provided<<",\"cpu_model\":"<<json_string(local_cpu_model())
             <<",\"thread_cpu_masks\":["<<json_string(masks.first)<<"],\"thread_physical_cores\":["<<json_string(masks.second)<<"]}";
            print_topology(s.str(),rank,size);MPI_Comm_free(&shared);MPI_Finalize();return 0;
        }
        MPI_Comm_free(&shared);
        const double e2e_start=MPI_Wtime();
        const int base=o.n/size,rem=o.n%size,rows=base+(rank<rem),offset=rank*base+std::min(rank,rem),stride=o.n+2;
        const int up=rank==0?MPI_PROC_NULL:rank-1, down=rank+1==size?MPI_PROC_NULL:rank+1;
        const std::size_t cells=checked_product(static_cast<std::size_t>(rows)+2,static_cast<std::size_t>(stride));
        const std::size_t bytes=checked_product(cells,sizeof(double)),row_bytes=static_cast<std::size_t>(o.n)*sizeof(double);
        const double h=1.0/(o.n+1),h2=h*h;
        std::vector<double> rhs(cells,0),host_grid(cells,0),send_top(o.n),send_bottom(o.n),recv_top(o.n,0),recv_bottom(o.n,0);
        double local_rhs=0,rhs_sq=0;
        for(int i=1;i<=rows;++i) for(int j=1;j<=o.n;++j) {
            auto z=static_cast<std::size_t>(i)*stride+j;rhs[z]=forcing((offset+i)*h,j*h);local_rhs+=rhs[z]*rhs[z];
        }
        MPI_Allreduce(&local_rhs,&rhs_sq,1,MPI_DOUBLE,MPI_SUM,MPI_COMM_WORLD);
        DeviceArray old(cells),next(cells),forcing_device(cells);
        cu(cudaMemset(old.p,0,bytes));cu(cudaMemset(next.p,0,bytes));
        cu(cudaMemcpy(forcing_device.p,rhs.data(),bytes,cudaMemcpyHostToDevice));
        auto exchange=[&]() {
            if(size==1) return;
            // Synchronous staging makes old's produced values ready before MPI reads.
            cu(cudaMemcpy(send_top.data(),old.p+stride+1,row_bytes,cudaMemcpyDeviceToHost));
            cu(cudaMemcpy(send_bottom.data(),old.p+static_cast<std::size_t>(rows)*stride+1,row_bytes,cudaMemcpyDeviceToHost));
            MPI_Sendrecv(send_top.data(),o.n,MPI_DOUBLE,up,101,recv_bottom.data(),o.n,MPI_DOUBLE,down,101,MPI_COMM_WORLD,MPI_STATUS_IGNORE);
            MPI_Sendrecv(send_bottom.data(),o.n,MPI_DOUBLE,down,102,recv_top.data(),o.n,MPI_DOUBLE,up,102,MPI_COMM_WORLD,MPI_STATUS_IGNORE);
            if(up!=MPI_PROC_NULL) cu(cudaMemcpy(old.p+1,recv_top.data(),row_bytes,cudaMemcpyHostToDevice));
            if(down!=MPI_PROC_NULL) cu(cudaMemcpy(old.p+static_cast<std::size_t>(rows+1)*stride+1,recv_bottom.data(),row_bytes,cudaMemcpyHostToDevice));
        };
        auto residual=[&]() {
            exchange();cu(cudaMemcpy(host_grid.data(),old.p,bytes,cudaMemcpyDeviceToHost));
            double local=0,total=0;
            for(int i=1;i<=rows;++i) for(int j=1;j<=o.n;++j) {
                auto z=static_cast<std::size_t>(i)*stride+j;
                double au=(4*host_grid[z]-host_grid[z-stride]-host_grid[z+stride]-host_grid[z-1]-host_grid[z+1])/h2;
                double v=rhs[z]-au;local+=v*v;
            }
            MPI_Allreduce(&local,&total,1,MPI_DOUBLE,MPI_SUM,MPI_COMM_WORLD);return std::sqrt(total/rhs_sq);
        };
        Result r;r.backend="cuda";r.ranks=size;r.threads=1;r.gpu_count=size;r.gpu_model=prop.name;
        const dim3 block(32,8),grid((o.n+31)/32,(rows+7)/8);
        cu(cudaDeviceSynchronize());MPI_Barrier(MPI_COMM_WORLD);double start=MPI_Wtime();
        for(int step=0;step<o.iters;++step) {
            exchange();jacobi_update<<<grid,block>>>(old.p,next.p,forcing_device.p,o.n,rows,stride,h2);cu(cudaGetLastError());
            std::swap(old.p,next.p);r.iterations=step+1;
            if((o.check>0 && r.iterations%o.check==0) || (o.mode=="solve" && r.iterations==o.iters)) {
                r.residual=residual();if(o.mode=="solve" && r.residual<=o.tol) break;
            }
        }
        cu(cudaDeviceSynchronize());double elapsed=MPI_Wtime()-start;
        MPI_Allreduce(&elapsed,&r.seconds,1,MPI_DOUBLE,MPI_MAX,MPI_COMM_WORLD);
        cu(cudaMemcpy(host_grid.data(),old.p,bytes,cudaMemcpyDeviceToHost));
        double e2e=MPI_Wtime()-e2e_start;
        MPI_Allreduce(&e2e,&r.end_to_end_seconds,1,MPI_DOUBLE,MPI_MAX,MPI_COMM_WORLD);
        r.residual=residual();r.converged=r.residual<=o.tol;
        double e=0,t=0,m=0;
        for(int i=1;i<=rows;++i) for(int j=1;j<=o.n;++j) {
            double truth=exact((offset+i)*h,j*h),err=host_grid[static_cast<std::size_t>(i)*stride+j]-truth;
            e+=err*err;t+=truth*truth;m=std::max(m,std::abs(err));
        }
        double local[2]={e,t},global[2];MPI_Allreduce(local,global,2,MPI_DOUBLE,MPI_SUM,MPI_COMM_WORLD);
        MPI_Allreduce(&m,&r.error_max,1,MPI_DOUBLE,MPI_MAX,MPI_COMM_WORLD);r.error_l2=std::sqrt(global[0]/global[1]);
        if(!o.dump.empty()) {
            std::vector<double> packed(static_cast<std::size_t>(rows)*o.n),all;
            for(int i=1;i<=rows;++i)std::copy_n(host_grid.data()+static_cast<std::size_t>(i)*stride+1,o.n,packed.data()+static_cast<std::size_t>(i-1)*o.n);
            std::vector<int> counts(size),displs(size);
            for(int p=0;p<size;++p){counts[p]=(base+(p<rem))*o.n;displs[p]=(p*base+std::min(p,rem))*o.n;}
            if(rank==0)all.resize(grid_cells(o.n,2));
            MPI_Gatherv(packed.data(),rows*o.n,MPI_DOUBLE,all.data(),counts.data(),displs.data(),MPI_DOUBLE,0,MPI_COMM_WORLD);
            if(rank==0)dump_grid(o.dump,o.n,all);
        }
        if(rank==0)print_result(o,r);
        int status=(o.mode=="solve"&&!r.converged)?2:0;MPI_Finalize();return status;
    } catch(const std::exception& e) {
        std::cerr<<"rank "<<rank<<" ERROR: "<<e.what()<<'\n';MPI_Abort(MPI_COMM_WORLD,1);return 1;
    }
}

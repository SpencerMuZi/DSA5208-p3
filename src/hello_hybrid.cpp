#include "common.hpp"
#include "topology.hpp"
#include <mpi.h>
#include <omp.h>
#ifdef __linux__
#include <sched.h>
#endif

int main(int argc,char** argv) {
    int provided=0,rank=0,size=0;
    MPI_Init_thread(&argc,&argv,MPI_THREAD_FUNNELED,&provided);
    MPI_Comm_rank(MPI_COMM_WORLD,&rank);
    MPI_Comm_size(MPI_COMM_WORLD,&size);
    if (provided<MPI_THREAD_FUNNELED) MPI_Abort(MPI_COMM_WORLD,1);
    char hostname[MPI_MAX_PROCESSOR_NAME]; int len=0;
    MPI_Get_processor_name(hostname,&len);
    std::vector<std::string> masks(omp_get_max_threads()), physical(omp_get_max_threads());
    int actual=1;
    #pragma omp parallel
    {
        int thread=omp_get_thread_num();
        #pragma omp single
        actual=omp_get_num_threads();
        auto mask=local_cpu_masks();
        masks[thread]=mask.first;
        physical[thread]=mask.second;
    }
    std::ostringstream s;
    s << "{\"rank\":" << rank << ",\"size\":" << size << ",\"host\":"
      << json_string(std::string(hostname,len)) << ",\"threads\":" << actual
      << ",\"mpi_thread_support\":" << provided << ",\"thread_cpu_masks\":[";
    for (int t=0;t<actual;++t) { if (t) s << ','; s << json_string(masks[t]); }
    s << "],\"thread_physical_cores\":[";
    for (int t=0;t<actual;++t) { if(t) s<<','; s<<json_string(physical[t]); }
    s << "],\"cpu_model\":" << json_string(local_cpu_model()) << "}";
    std::string local=s.str();
    int local_len=static_cast<int>(local.size());
    std::vector<int> lengths(size),offsets(size);
    MPI_Gather(&local_len,1,MPI_INT,lengths.data(),1,MPI_INT,0,MPI_COMM_WORLD);
    int total=0;
    if (rank==0) for(int p=0;p<size;++p) { offsets[p]=total; total+=lengths[p]; }
    std::vector<char> buffer(total);
    MPI_Gatherv(local.data(),local_len,MPI_CHAR,buffer.data(),lengths.data(),offsets.data(),MPI_CHAR,0,MPI_COMM_WORLD);
    if (rank==0) for(int p=0;p<size;++p)
        std::cout << std::string(buffer.data()+offsets[p],lengths[p]) << '\n';
    MPI_Finalize();
    return 0;
}

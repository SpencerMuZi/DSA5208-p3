#pragma once
#include "common.hpp"
#include <set>
#include <utility>
#ifdef __linux__
#include <sched.h>
#endif

inline std::string local_cpu_model() {
    std::ifstream f("/proc/cpuinfo"); std::string s;
    while (std::getline(f,s)) if (s.rfind("model name",0)==0) {
        auto p=s.find(':'); return s.substr(p+2);
    }
    return "unavailable";
}
inline std::string topology_value(int cpu,const std::string& leaf) {
    std::ifstream f("/sys/devices/system/cpu/cpu"+std::to_string(cpu)+"/topology/"+leaf);
    std::string value; if (!(f>>value)) return "unavailable"; return value;
}
inline std::pair<std::string,std::string> local_cpu_masks() {
    std::ostringstream logical,physical; std::set<std::string> cores;
#ifdef __linux__
    cpu_set_t set; CPU_ZERO(&set);
    if (sched_getaffinity(0,sizeof(set),&set)!=0) return {"unavailable","unavailable"};
    bool first=true;
    for (int c=0;c<CPU_SETSIZE;++c) if (CPU_ISSET(c,&set)) {
        if (!first) logical<<',';
        logical<<c; first=false;
        cores.insert(topology_value(c,"physical_package_id")+":"+topology_value(c,"core_id"));
    }
    first=true;
    for (const auto& c:cores) { if (!first) physical<<','; physical<<c; first=false; }
#else
    logical<<"unavailable"; physical<<"unavailable";
#endif
    return {logical.str(),physical.str()};
}

# C 操作指南：Mac、OpenMP、集群配置、实验与汇总

你的目标：核实集群环境、解释 OpenMP 配置、取得 weak/mix 结果、汇总 A/B 的证据、生成图表并整合报告。A/B 也独立申请账号，不让你一个人承担全部运行。

本机 Mac Terminal 用 zsh，SSH 后 Linux bash。正式编译/计算统一在 Atlas/Vanda；本机只做上传、结果分析与写作，不必安装本地 MPI。

## C1. 上传同一源码包

把 ZIP 放 Downloads，Terminal 逐行执行：

```bash
command -v ssh
command -v scp
read -r 'HpcUser?个人 NUSNET ID: '
read -r 'HpcHost?课程确认的 Atlas/Vanda 登录主机: '
RemoteDir=DSA5208_P3_C
ZipPath="$HOME/Downloads/DSA5208_Project3_source.zip"
shasum -a 256 "$ZipPath"
ssh "${HpcUser}@${HpcHost}" "mkdir -p $RemoteDir"
scp "$ZipPath" "${HpcUser}@${HpcHost}:${RemoteDir}/source.zip"
ssh "${HpcUser}@${HpcHost}"
```

进入 Linux 后：

```bash
cd "$HOME/DSA5208_P3_C"
python3 -m zipfile -e source.zip .
cd Project3
bash -l scripts/detect_env.sh
type module
module avail
command -v qsub
qstat -Q
```

若 module/qsub 不存在，先按学校说明修正登录环境，不继续提交。把官方确认的 module、queue、project 和资源上限告诉 A/B。不要从 `qstat -Q` 推断权限，也不要把登录节点 lscpu 当成计算节点规格。

## C2. 配置与编译

```bash
cp configs/site_modules.sh.example configs/site_modules.sh
cp configs/cluster.env.example configs/cluster.env
nano configs/site_modules.sh
source configs/site_modules.sh
mpicxx --showme:command
mpicxx --version
mpirun --version
nano configs/cluster.env
bash -l scripts/build.sh
cat results/build/build.txt
```

如何填字段见共同指南第 5 节。串行编译器后端应与 mpicxx 对应，默认 GCC/Open MPI/-fopenmp。其他 MPI 的启动参数不能混用；提供的作业生成器仅支持经过确认的 Open MPI/PBS。

将确认参数作为团队环境说明记录，但每个人维护本人 configs 文件。不要把密码或 token 写进配置。

## C3. 你需要理解的 OpenMP 代码

```bash
nl -ba src/parallel.cpp
nl -ba src/hello_hybrid.cpp
```

重点：

- `threaded=variant!=mpi`：纯 MPI 的循环串行，hybrid/overlap 启用 OpenMP。
- `omp_set_dynamic(0)` 和 `omp_set_num_threads`：要求固定线程数；actual_threads 与请求不同会报错。
- `parallel for schedule(static)`：按本地行分配线程，因为各点工作量相近。
- 残差与解析误差使用 OpenMP reduction；然后主线程做 MPI Allreduce。
- MPI_THREAD_FUNNELED 只允许初始化 MPI 的线程调用 MPI，本实现把 MPI 调用放在 parallel 区域外。
- 每次 update 建立并行区；很小的本地工作量可能受 OpenMP 开销限制。
- 数组 zero initialization 是串行；当前没有并行 NUMA first touch，不在报告里声称已经优化。

资源关系：每节点 `ncpus = ranks_per_node × threads_per_rank`，总使用核数 `nodes × ranks_per_node × threads_per_rank`。`ompthreads=2` 是资源/环境声明，不自动保证两个线程落在两个独立物理核，必须检查绑定和实际 CPU masks。

作业启动使用：

```text
mpirun -np p --map-by ppr:ppn:node:PE=t --bind-to core
```

这段是参数结构说明，真实 p/ppn/t 由生成脚本填入。OMP_PLACES=cores 和 OMP_PROC_BIND=close 配合 MPI 为每 rank 分配 t 个核心。官方 module 需正确接入 PBS allocation。

## C4. smoke 与 verify

```bash
python3 scripts/make_jobs.py --preset smoke --iters 100 --repeats 3
JOB_DIR=$(ls -td jobs/generated/smoke-* | head -n 1)
cat "$JOB_DIR/p3-smoke-1.pbs"
JOB_ID=$(qsub "$JOB_DIR/p3-smoke-1.pbs")
qstat -f "$JOB_ID"
```

完成后：

```bash
RUN_DIR=$(ls -td results/raw/* | head -n 1)
cat "$RUN_DIR/topology.stdout.jsonl"
cat "$RUN_DIR/metadata.json"
cat "$RUN_DIR/COMPLETE"
```

两 host、2 ranks、每 rank 2 threads；Linux masks 应当符合实际配额与 core topology。两个线程的 mask 可能含 SMT sibling CPU IDs，需要用计算节点 `lscpu -e` 等官方认可方式解释，不能仅按逗号数量当物理核。

```bash
python3 scripts/make_jobs.py --preset verify
JOB_DIR=$(ls -td jobs/generated/verify-* | head -n 1)
cat "$JOB_DIR/p3-verify-1.pbs"
JOB_ID=$(qsub "$JOB_DIR/p3-verify-1.pbs")
qstat -f "$JOB_ID"
```

结束后检查 PASS：

```bash
tail -n 80 p3-verify-1.o*
VALIDATION_DIR=$(ls -td results/validation/* | head -n 1)
cat "$VALIDATION_DIR/summary.json"
```

与 A/B 确认三人的 source ZIP hash 相同、编译版本/flags 一致，再开展正式矩阵。

## C5. weak scaling

与 A 确认正式迭代数；下面示例为 10000 轮。每节点使用 8 核，需要实际批准。

```bash
python3 scripts/make_jobs.py --preset weak --n 256 --iters 10000 --repeats 5 --cpus-per-node 8 --single-node-cores 1,2,4,8 --nodes-list 1,2
JOB_DIR=$(ls -td jobs/generated/weak-* | head -n 1)
cat "$JOB_DIR/manifest.json"
for script in "$JOB_DIR"/*.pbs; do
    cat "$script"
done
```

这里 N=256 是单核参考尺寸，后续 N=round(256√C)，使每核内部点数约恒定。总核数 1/2/4/8/16，5 个配置。它测固定工作量/核和固定轮数，不测各网格达到同精度的时间。

审核后提交：

```bash
for script in "$JOB_DIR"/*.pbs; do
    qsub "$script"
done
qstat -u "$USER"
```

若 5 次测量加 warmup 超过 walltime，先调整时限/问题/轮数再重新生成；不能把被调度器杀掉的半份数据当完整配置。

## C6. 固定资源的 rank/thread 配比

```bash
python3 scripts/make_jobs.py --preset mix --n 1024 --iters 10000 --repeats 5 --cpus-per-node 8 --nodes-list 1,2 --mix-threads 1,2,4,8
JOB_DIR=$(ls -td jobs/generated/mix-* | head -n 1)
cat "$JOB_DIR/manifest.json"
for script in "$JOB_DIR"/*.pbs; do
    cat "$script"
done
```

每节点 8 核的组合：8p×1t、4p×2t、2p×4t、1p×8t。单节点组总 8 核，双节点组总 16 核；两组分别讨论，不能把 nodes 改变当成单纯线程改变。

确认后按课程提交限制运行：

```bash
for script in "$JOB_DIR"/*.pbs; do
    qsub "$script"
done
```

需要检查 topology 的 host 数、thread count 与各线程 masks；不只依赖 manifest。保存每个完成 run 的 source_hash/build_signature，让 A 的 serial/MPI/hybrid strong 和你的 mix 可追溯。

## C7. 可选收敛检查间隔实验

四版本正确、主矩阵齐全后再做：

```bash
python3 scripts/make_jobs.py --preset check --n 64 --iters 200000 --repeats 5 --cpus-per-node 8 --nodes-list 1
JOB_DIR=$(ls -td jobs/generated/check-* | head -n 1)
cat "$JOB_DIR/manifest.json"
for script in "$JOB_DIR"/*.pbs; do
    cat "$script"
done
for script in "$JOB_DIR"/*.pbs; do
    qsub "$script"
done
```

三配置 q=1/10/50，相同容差 1e-8。达到最大轮数却不收敛会失败，不生成 COMPLETE。看总秒数、停止迭代数和最终残差；检查频率低可能延迟停止，因此不能只比较单轮时间。

## C8. 下载自己的结果和源码

集群：

```bash
tar -czf ../C_results.tar.gz results jobs/generated
sha256sum ../C_results.tar.gz
exit
```

Mac 本机：

```bash
scp "${HpcUser}@${HpcHost}:${RemoteDir}/C_results.tar.gz" "$HOME/Downloads/C_results.tar.gz"
shasum -a 256 "$HOME/Downloads/C_results.tar.gz"
mkdir -p "$HOME/Documents/DSA5208_P3_LOCAL"
python3 -m zipfile -e "$HOME/Downloads/DSA5208_Project3_source.zip" "$HOME/Documents/DSA5208_P3_LOCAL"
cd "$HOME/Documents/DSA5208_P3_LOCAL/Project3"
tar -xzf "$HOME/Downloads/C_results.tar.gz"
```

本机的项目目录已有 src/scripts/docs；解压结果加入 results/jobs。不要在本机为官方结果重编译/重跑求解器以冒充原有数据。

## C9. 导入 A/B 的原始数据

A/B 将归档和 hash 给你，存到 Downloads。先核对两份 hash 与他们在集群打印的值一致：

```bash
shasum -a 256 "$HOME/Downloads/A_results.tar.gz"
shasum -a 256 "$HOME/Downloads/B_results.tar.gz"
mkdir -p results/imported/A results/imported/B
tar -xzf "$HOME/Downloads/A_results.tar.gz" -C results/imported/A
tar -xzf "$HOME/Downloads/B_results.tar.gz" -C results/imported/B
mkdir -p results/raw
cp -R results/imported/A/results/raw/. results/raw/
cp -R results/imported/B/results/raw/. results/raw/
```

run_id 使用时间和随机 ID，正常不会碰撞；有同名目录先核对相同文件而不是覆盖不同结果。各人原始 environment/build/validation/jobs 都保留在 imported 目录。analyze 默认只扫描顶层 results/raw，避免 imported 备份导致重复统计。

## C10. 汇总与图表（Mac 本机）

不安装额外包也可先汇总：

```bash
python3 scripts/analyze.py --official-only
head -n 30 results/summary/summary.csv
```

检查：strong 每 N 10 配置，weak 5 配置，mix 8 配置，核心 comm 4 配置；各正式配置 5 samples。profile 诊断会另列。只统计完整 runs；失败、试跑不悄悄删除，应保留到 results/pilot 或说明目录。

创建本机虚拟环境生成图：

```bash
python3 -m venv .venv
source .venv/bin/activate
python -m pip install -r requirements-analysis.txt
python scripts/analyze.py --official-only --plots
python -m pip freeze > report/analysis_requirements_lock.txt
ls figures
```

figures 同时生成 PNG/PDF；误差条为重复测量 min/max 范围。脚本按 cluster、CPU、source、build 与问题参数分组，缺基线 speedup 留空。如果同图需要比较但来源不同，补跑匹配基线或分开讨论，不能强行拼图。

## C11. 报告、README、AI 记录

1. 从 `report/报告写作模板.md` 建立实际报告，用 Word/其他编辑器写作并导出 PDF 到 `report/report.pdf`。当前不含最终 PDF。
2. 填 `report/team.csv` 三人真实姓名/ID。
3. 更新 `report/AI_USAGE.md`：本包大量代码/指南由 AI 辅助生成，写清真实范围，以及小组独立验证/修改。
4. 收 A 的算法/正确性/strong 与 B 的 MPI/通信章节，你负责环境、OpenMP、weak/mix 和整体讨论。
5. README 记录实际使用的 module、队列、资源、提交/复现流程；原始 PBS 的绝对路径属当时环境，新用户用 make_jobs 重生成当前目录的脚本。
6. 所有图的数字来自 raw→summary 脚本，注明 benchmark 固定轮数、solve 容差、N、使用核数、节点布局。

必要时进度报告在 10-30 之前发给教师，内容包括算法、四版本状态、验证、初步集群曲线与具体困惑。发送由你们自行完成。

## C12. 独立复现、打包与提交

把最终源码分发给 A，从新的干净目录编译/verify/关键作业。收到复现证据后先生成完整预审包：

```bash
python scripts/package.py --kind full
```

完成报告与名字，再生成最终包：

```bash
python scripts/package.py --kind full --final
shasum -a 256 dist/DSA5208_Project3_full.zip
ls -lh report/report.pdf dist/DSA5208_Project3_full.zip
python -m zipfile -l dist/DSA5208_Project3_full.zip
```

final 检查只核对 PDF 文件头、姓名占位符和完成的官方多节点 run，不能替代你们审阅科学内容。最终包排除密码配置、bin 和 .venv，包含代码、指南、结果和报告。

11-12 提交 Canvas：单独 PDF 与源码/README ZIP，具体按课程上传界面。如果文件大小超限制，保留关键原始证据并依据教师要求调整，不能删掉报告所用数字的依据。另一人下载 Canvas 文件，核对 SHA256/内容和提交状态。

你的完成标准：环境可复现、MPI/OpenMP 资源与实际 topology 相符、weak/mix/通信/strong 数据来源清楚、PDF 信息完整、README 从干净目录可用、AI 说明真实。

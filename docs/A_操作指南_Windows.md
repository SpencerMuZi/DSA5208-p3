# A 操作指南：Windows、串行、正确性与强扩展

你的目标：理解并验收算法与正确性，取得同一集群上的串行时间和 strong-scaling 数据，撰写算法/验证章节。C 负责统一环境和最终分析，但你应当独立部署和重跑 verify。

本机用 Windows PowerShell；SSH 后用 Linux bash。不要在 PowerShell 中执行 `source`、`export` 或 Linux 的路径命令。

## A1. 下载、申请账号、上传

1. 下载 `DSA5208_Project3_source.zip` 到 Downloads。
2. 按 `共同部署与命令说明.md` 第 1 节申请个人账号，取得课程允许的登录主机和 CPU 资源。
3. 打开 PowerShell，逐行执行：

```powershell
Get-Command ssh
Get-Command scp
$HpcUser = Read-Host '个人 NUSNET ID'
$HpcHost = Read-Host '课程确认的 Atlas/Vanda 登录主机'
$RemoteDir = 'DSA5208_P3_A'
$ZipPath = Join-Path $env:USERPROFILE 'Downloads\DSA5208_Project3_source.zip'
Get-FileHash $ZipPath -Algorithm SHA256
ssh "${HpcUser}@${HpcHost}" "mkdir -p $RemoteDir"
scp $ZipPath "${HpcUser}@${HpcHost}:${RemoteDir}/source.zip"
ssh "${HpcUser}@${HpcHost}"
```

最后一行后进入集群。下面逐行执行：

```bash
cd "$HOME/DSA5208_P3_A"
python3 -m zipfile -e source.zip .
cd Project3
bash -l scripts/detect_env.sh
```

前三行进入/解压源码，最后一行记录登录环境。把检测输出和遇到的账号问题交给 C，但不交密码。

## A2. 环境配置和编译

从课程/C 获得已经核实的 module、queue/project 参数，自己填写到本人的两个配置文件中，不照抄对方的目录路径。

```bash
cp configs/site_modules.sh.example configs/site_modules.sh
cp configs/cluster.env.example configs/cluster.env
nano configs/site_modules.sh
nano configs/cluster.env
bash -l scripts/build.sh
ls -l bin
cat results/build/build.txt
```

配置字段和 nano 操作见共同指南第 5 节。编译应成功生成三个可执行文件；串行执行文件不链接 MPI/OpenMP。不要在登录节点直接跑正式 benchmark。

## A3. 必须阅读的串行代码

```bash
nl -ba src/common.hpp
nl -ba src/serial.cpp
```

`nl -ba` 给每行标号，便于三人讨论。按这个顺序理解：

1. `parse_options`：N、iters、mode、check、tol 约束；N 是内部网格点。
2. `forcing`/`exact`：构造方程和解；边界均为零。
3. `old/next/rhs`：每维 N+2，包含两侧边界。
4. `rhs_sq`：相对残差分母，固定问题中非零。
5. `residual`：`A_h u=(4u-邻居和)/h²`，计算 `sqrt(sum((f-A_hu)²)/sum(f²))`。
6. `k` 循环：从 old 读取，写 next，再 `old.swap(next)`。
7. benchmark 执行恰好 iters 轮；solve 每 check 轮检查，最后允许的一轮也检查。
8. `r.seconds`：只统计求解循环；最终独立残差、解析解误差和 dump 在计时外。
9. solve 未收敛返回 2；不能把“正常输出了一条 JSON”当成收敛。

你应能在报告中独立推导：u=x(1-x)y(1-y)；`-u_xx=2y(1-y)`、`-u_yy=2x(1-x)`，因此 f 等于两项之和。它在 x、y 方向均为二次多项式，五点中心差分的离散解可直接验证。

## A4. 双节点 smoke 与全版本 verify

先按共同指南第 7 节提交 smoke，确认两 host、两 rank、每 rank 两线程。然后执行：

```bash
python3 scripts/make_jobs.py --preset verify
JOB_DIR=$(ls -td jobs/generated/verify-* | head -n 1)
cat "$JOB_DIR/p3-verify-1.pbs"
JOB_ID=$(qsub "$JOB_DIR/p3-verify-1.pbs")
printf '%s\n' "$JOB_ID"
qstat -f "$JOB_ID"
```

完成后：

```bash
tail -n 80 p3-verify-1.o*
VALIDATION_DIR=$(ls -td results/validation/* | head -n 1)
cat "$VALIDATION_DIR/summary.json"
```

应看到 PASS。将 validation 文件夹路径和 summary 发给 B/C。关注不整除、每 rank 一行/两行和 solve 解析解测试，不只看检查数量。

错误出现时，summary 可能尚未生成；查看该目录的 stderr 和 command.json，找出失败用例。修复后重新验证并分发同一源码版本。

## A5. 先预跑确定时间长度

以下以课程允许每节点至少 8 核、两个节点为前提，C 已将 MAX_CPUS_PER_NODE 配正确。若批准的是 4 核，改 `--cpus-per-node 4 --single-node-cores 1,2,4`，三人统一调整实验表。

```bash
python3 scripts/make_jobs.py --preset strong --n 512 --iters 1000 --repeats 3 --cpus-per-node 8 --single-node-cores 1,2,4,8 --nodes-list 1,2
JOB_DIR=$(ls -td jobs/generated/strong-* | head -n 1)
cat "$JOB_DIR/manifest.json"
cat "$JOB_DIR/p3-strong-1.pbs"
cat "$JOB_DIR/p3-strong-6.pbs"
```

生成 10 个配置：serial、MPI 1/2/4/8 核单节点、MPI 16 核双节点；再加每 rank 两线程的 hybrid 2/4/8/16 核。第 6 个脚本仍是最大核数的 MPI 端点。这里的 8 核是实验资源选择，不是机器硬件规格。

先提交 serial 与最大核数两个端点，估计 walltime 和最短测量：

```bash
qsub "$JOB_DIR/p3-strong-1.pbs"
qsub "$JOB_DIR/p3-strong-6.pbs"
qstat -u "$USER"
```

作业结束后查看原始 stdout：

```bash
ls -lt p3-strong-*.o*
tail -n 80 p3-strong-*.o*
```

若最快配置 `solve_seconds_max` 太短，增加 iters，比如先试 10000。确认较慢配置的总耗时（1 次 warmup + repeats 次）仍在 walltime 内。与 B/C 约定正式轮数，所有 strong/mix/comm 对照使用同一轮数。

预跑 family 同为 strong；正式分析时避免把预跑混入正式结果。将其保留到单独位置：

```bash
mkdir -p results/pilot/raw
```

把确认属于本次预跑的两个 run 目录移入该目录，逐个用真实路径执行 `mv`；不要移动未核实的全部 raw 结果。之后正式实验的 `results/raw` 只放正式 runs。

## A6. 正式 strong 两档网格

以下示例冻结为 10000 轮；如果预跑决定其他数值，A/B/C 同时替换。先做 N=512：

```bash
python3 scripts/make_jobs.py --preset strong --n 512 --iters 10000 --repeats 5 --cpus-per-node 8 --single-node-cores 1,2,4,8 --nodes-list 1,2
JOB_DIR=$(ls -td jobs/generated/strong-* | head -n 1)
cat "$JOB_DIR/manifest.json"
for script in "$JOB_DIR"/*.pbs; do
    cat "$script"
done
```

确认资源和配额后逐个/少量提交；允许批量提交时：

```bash
for script in "$JOB_DIR"/*.pbs; do
    qsub "$script"
done
```

N=1024 同样执行：

```bash
python3 scripts/make_jobs.py --preset strong --n 1024 --iters 10000 --repeats 5 --cpus-per-node 8 --single-node-cores 1,2,4,8 --nodes-list 1,2
JOB_DIR=$(ls -td jobs/generated/strong-* | head -n 1)
cat "$JOB_DIR/manifest.json"
for script in "$JOB_DIR"/*.pbs; do
    qsub "$script"
done
qstat -u "$USER"
```

预跑已验证且仅 N 改变时仍核对资源/时限，不超课程提交限制。有时间再加 2048，但先交付两档完整结果。

## A7. 汇总与检查基线

```bash
python3 scripts/analyze.py --official-only
head -n 20 results/summary/summary.csv
```

检查每档 N 有 10 个配置、5 个 measured samples，serial 基线与 MPI/hybrid 来源/CPU/编译参数匹配。强扩展 speedup/efficiency 不应为空；若 CPU model 不同，C 需通过批准的相同 CPU 资源约束补跑，不能手填速度。

你主要解释：网格越小越容易被通信/线程/同步开销限制；随着核数增长，本地计算量减少，边界与归约成本比例增加。只有数据支持的趋势才写成结论。

## A8. 写作与交接

提交给 C：

- 算法说明和构造解推导。
- validation summary 与代表性误差/残差/迭代数表。
- N=512/1024 的完整 strong 原始结果。
- 你实际做过的修改、验证和 AI 使用记录。

集群命令：

```bash
tar -czf ../A_results.tar.gz results jobs/generated
sha256sum ../A_results.tar.gz
exit
```

回到原来的 PowerShell：

```powershell
scp "${HpcUser}@${HpcHost}:${RemoteDir}/A_results.tar.gz" "$env:USERPROFILE\Downloads\A_results.tar.gz"
Get-FileHash "$env:USERPROFILE\Downloads\A_results.tar.gz" -Algorithm SHA256
```

不要把本机开发记录或 login node 数据描述为集群 compute-node 结果。

## A9. 最终独立复现

C 给出最终源码 ZIP 后，另建 `DSA5208_P3_A_FINAL` 目录，重复上传、解压、确认模块、编译和 verify；不要直接复用旧 bin。提交一次关键配置并与报告核对。向 C 返回真实复现日志、源码 hash、是否成功。

你的完成标准：能解释算法、正确性证据齐全、两档 strong 带真实 serial 基线、交接 hash 匹配、最终版本从干净目录可运行。

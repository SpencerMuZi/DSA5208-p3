# B 操作指南：Windows、MPI 与通信实验

你的目标：理解分区、halo 和非阻塞 MPI，验收通信正确性，取得固定布局下 hybrid/overlap 的比较数据，撰写 MPI 设计与通信性能章节。

Windows PowerShell 负责上传/SSH，SSH 后 Linux bash 负责部署和提交。主开发目录固定 `DSA5208_P3_B`。

## B1. 账号、下载和上传

先独立申请 HPC 账号，取得登录主机与课程 CPU 权限。ZIP 放 Downloads，PowerShell 逐行执行：

```powershell
Get-Command ssh
Get-Command scp
$HpcUser = Read-Host '个人 NUSNET ID'
$HpcHost = Read-Host '课程确认的 Atlas/Vanda 登录主机'
$RemoteDir = 'DSA5208_P3_B'
$ZipPath = Join-Path $env:USERPROFILE 'Downloads\DSA5208_Project3_source.zip'
Get-FileHash $ZipPath -Algorithm SHA256
ssh "${HpcUser}@${HpcHost}" "mkdir -p $RemoteDir"
scp $ZipPath "${HpcUser}@${HpcHost}:${RemoteDir}/source.zip"
ssh "${HpcUser}@${HpcHost}"
```

进入集群后：

```bash
cd "$HOME/DSA5208_P3_B"
python3 -m zipfile -e source.zip .
cd Project3
bash -l scripts/detect_env.sh
cp configs/site_modules.sh.example configs/site_modules.sh
cp configs/cluster.env.example configs/cluster.env
nano configs/site_modules.sh
nano configs/cluster.env
bash -l scripts/build.sh
```

实际配置由课程信息和 C 核实后填写，细节见共同指南第 5 节。保留 build.txt 和 compile.txt。

## B2. 逐段阅读 MPI 代码

```bash
nl -ba src/parallel.cpp
nl -ba src/hello_hybrid.cpp
```

重点理解：

1. `MPI_Init_thread(...FUNNELED...)`：主线程调用 MPI。所有 MPI 调用在 OpenMP 并行循环外。
2. `base=N/size`、`remainder=N%size`：前 remainder 个 rank 多分一行。
3. `offset=rank*base+min(rank,remainder)`：本地第一行在全局的位置。
4. `up/down`：首/末 rank 用 MPI_PROC_NULL，无邻居时保留物理边界零。
5. 本地 i=0 和 i=rows+1 是 halo，i=1..rows 是拥有的真实内部行。
6. 每条消息发送 N 个内部列；左右物理边界不需要通信。
7. `residual` 检查 old 的当前解，先刷新 halo，再 Allreduce；所有 rank 在同一轮决定退出。
8. 只在用户指定 dump 时最后 Gatherv 全网格，不每轮 gather。

### 阻塞交换的两个 tag

```text
tag 101：向 up 发送第一条内部行，同时从 down 接收其第一条内部行到 bottom halo
tag 102：向 down 发送最后内部行，同时从 up 接收其最后内部行到 top halo
```

MPI_Sendrecv 使配对发送/接收可执行，不使用“所有 rank 先 blocking send 再 recv”的易死锁顺序。

### 非阻塞交换每一轮的顺序

```text
Irecv top halo from up tag102
Irecv bottom halo from down tag101
Isend first row to up tag101
Isend last row to down tag102
计算 i=2..rows-1（有这些行时）
Waitall
计算 i=1 和 i=rows（rows=1 时只算一次）
交换 old/next
```

old 作为发送数据，next 作为输出，在发送未完成时不能修改 old；在接收未完成时不能读取 halo。内部行读取的邻居都在本地，不依赖正在接收的数据。

可以画三 rank 的条带分区示意图写进报告，展示上下 halo 和全局 row offset。必须明确本项目是行分区，尚未实现二维块分区。

## B3. 先跑双节点 smoke

```bash
python3 scripts/make_jobs.py --preset smoke --iters 100 --repeats 3
JOB_DIR=$(ls -td jobs/generated/smoke-* | head -n 1)
cat "$JOB_DIR/p3-smoke-1.pbs"
JOB_ID=$(qsub "$JOB_DIR/p3-smoke-1.pbs")
qstat -f "$JOB_ID"
```

完成后：

```bash
tail -n 80 p3-smoke-1.o*
RUN_DIR=$(ls -td results/raw/* | head -n 1)
cat "$RUN_DIR/topology.stdout.jsonl"
cat "$RUN_DIR/COMPLETE"
```

真正成功：两个不同 host，rank 数=2，每 rank threads=2，COMPLETE 存在。B 将 topology 交给 C，作为跨节点实现证据；smoke 时间只是预跑，不计入正式通信比较。

## B4. 完整数值验证

```bash
python3 scripts/make_jobs.py --preset verify
JOB_DIR=$(ls -td jobs/generated/verify-* | head -n 1)
cat "$JOB_DIR/p3-verify-1.pbs"
JOB_ID=$(qsub "$JOB_DIR/p3-verify-1.pbs")
qstat -f "$JOB_ID"
```

结束后：

```bash
tail -n 80 p3-verify-1.o*
VALIDATION_DIR=$(ls -td results/validation/* | head -n 1)
cat "$VALIDATION_DIR/summary.json"
```

关注 N=3,p=3；N=4,p=4；N=5,p=3 等短分区和余数分区。每次修改消息 tag、buffer 地址、Waitall 次序或边缘循环都重跑关键验证。先修正确性，再讨论性能。

## B5. 正式通信实验：保持其他条件一致

与 A/C 确认同一 source hash、编译器、N、iters、每节点资源。下面示例 N=1024、10000 轮、每节点 8 核、每 rank 2 threads。

```bash
python3 scripts/make_jobs.py --preset comm --n 1024 --iters 10000 --repeats 5 --cpus-per-node 8 --nodes-list 1,2 --mix-threads 2
JOB_DIR=$(ls -td jobs/generated/comm-* | head -n 1)
cat "$JOB_DIR/manifest.json"
for script in "$JOB_DIR"/*.pbs; do
    cat "$script"
done
```

四个配置：

| 配置 | nodes | ranks | threads/rank | 使用核数 |
|---|---:|---:|---:|---:|
| hybrid，单节点 | 1 | 4 | 2 | 8 |
| overlap，单节点 | 1 | 4 | 2 | 8 |
| hybrid，双节点 | 2 | 8 | 2 | 16 |
| overlap，双节点 | 2 | 8 | 2 | 16 |

资源检查后，逐个或按批准的批量限制提交：

```bash
for script in "$JOB_DIR"/*.pbs; do
    qsub "$script"
done
qstat -u "$USER"
```

确认每个完成目录有 5 次实测、topology 和 COMPLETE。baseline 是同 nodes/ranks/threads 的 hybrid，而不是另一配置的最快时间。正式 comm 的 check=0，避免残差额外 halo/归约掩盖主要更新通信比较。

## B6. 独立诊断：不是正式时间的替代品

发现 overlap 快/慢的趋势后，可生成另一套启用 profile 的作业：

```bash
python3 scripts/make_jobs.py --preset comm --n 1024 --iters 10000 --repeats 3 --cpus-per-node 8 --nodes-list 1,2 --mix-threads 2 --profile
JOB_DIR=$(ls -td jobs/generated/comm-* | head -n 1)
cat "$JOB_DIR/manifest.json"
for script in "$JOB_DIR"/*.pbs; do
    qsub "$script"
done
```

输出字段含义：

- post_seconds_max：提交非阻塞操作的时间。
- wait_seconds_max：Sendrecv / Waitall 的调用等待时间。
- compute_seconds_max：更新循环时间。
- check_seconds_max：残差通信/计算/归约时间，check=0 时循环内为零。

这些是各 rank 分项累计再分别取最大值，不能简单相加。非阻塞传输可能发生在 compute 区间；Waitall 仅表示尚未完成部分的等待。profile 有额外计时开销，不能和 profile=false 的正式时间混在一个对照里。

没有真正测量通信进展/网络带宽时，只能写“可能受 MPI progress 或消息延迟影响”，不能声称已证明某原因。

## B7. 汇总、写作与交接

```bash
python3 scripts/analyze.py --official-only
head -n 20 results/summary/summary.csv
```

向 C 交付：通信代码解释、分区/消息图、4 配置正式记录、可选 profile 记录、MPI 设计和性能讨论。跟 A 的 strong 基线不是同一 family 时不需要为 comm 填 serial speedup，直接比较同资源配置的秒数和相对改善。

集群归档：

```bash
tar -czf ../B_results.tar.gz results jobs/generated
sha256sum ../B_results.tar.gz
exit
```

PowerShell 本机下载：

```powershell
scp "${HpcUser}@${HpcHost}:${RemoteDir}/B_results.tar.gz" "$env:USERPROFILE\Downloads\B_results.tar.gz"
Get-FileHash "$env:USERPROFILE\Downloads\B_results.tar.gz" -Algorithm SHA256
```

你的完成标准：所有 MPI 用例正确、能解释 tag 和 buffer 生命周期、真实双节点 topology、同布局阻塞/非阻塞对照完整、结论不预设非阻塞一定更快。

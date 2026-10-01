# ABC 顺序汇总操作指南

更新：2026-10-01。A/B 用 Windows，C 用 Mac。**全员先按本文件的阶段顺序执行，再打开各自指南查看具体操作。**

本文件说明“现在轮到谁、谁可以同时做、什么时候必须等前一步、完成后交什么”。A1、B1、C1 等编号均指原有个人指南的小节；不重新给个人任务编号。例如 C4 指 C 指南的“smoke 与 verify”，不是第四天。

配套文件：[A 指南](A_操作指南_Windows.md)、[B 指南](B_操作指南_Windows.md)、[C 指南](C_操作指南_Mac.md)、[共同部署命令](共同部署与命令说明.md)、[总实施方案](总实施方案.md)。

目前已具备起步代码和本地验证记录；三人的集群账号、正式部署与性能实验仍待完成。下面是需要你们执行的流程，不表示这些步骤已经完成。

## 一、先看这张总顺序表

| 阶段 | 谁先做 / 同时做 | 对应个人指南 | 完成后进入下一步的条件 |
|---|---|---|---|
| S0 | ABC 共同准备，各自申请账号和上传 | A1；B1 前半；C1 | 同一源码包，个人账号申请已推进；可登录者已上传 |
| S1 | A、B、C 分头读负责的代码，可与账号申请同时进行 | A3；B2；C3 | 明白各自算法/通信/线程部分，统一接口和问题定义 |
| S2 | C 先核实并配置集群；A/B 再按核实信息配置编译 | C2 → A2、B1 后半 | 三人编译成功，环境可比较 |
| S3 | C 先跑通 smoke/verify；A/B 再独立跑通 | C4 → A4、B3/B4 | 真实双节点 topology + 正确性 PASS |
| S4 | A 先做性能端点预跑；B/C 同时核对实验方案 | A5；B5/C5/C6 的方案部分 | 时间长度、资源和 walltime 有实测依据 |
| S5 | ABC 一起冻结源代码、编译配置和实验参数 | 本文件 S5 | 三人使用同一正式版本和明确实验协议 |
| S6 | A、B、C 可以分别运行正式矩阵 | A6；B5；C5/C6 | 20 + 4 + 13 个核心配置完成，次数与证据齐全 |
| S7 | ABC 各自检查记录；必要时有针对性补跑 | A7；B7；C10 的检查部分 | 没有缺配置、错误 topology 或基线问题 |
| S8 | A/B 交结果给 C；C 同时下载自己的结果 | A8；B7；C8 | 三份归档 hash 校验一致 |
| S9 | C 导入、汇总、绘图；A/B 配合核查数字 | C9/C10 | 图表可追溯，基线和对照有效 |
| S10 | ABC 同时写各自章节，再由 C 整合 | A8；B7；C11 | 完整报告、README、AI 说明、三人信息 |
| S11 | C 分发最终源码；A 在干净目录独立复现，B 复核通信结论 | A9；C12 | 最终代码可复现，报告数字与代码/日志一致 |
| S12 | C 打包/上传；A 或 B 下载核查 | C12 | Canvas 文件、内容、提交状态确认正确 |

表中配置数量对应“每节点使用 8 核、最多两节点”的初版矩阵。课程若批准不同资源，先修改协议和矩阵，不能照抄数量。

## S0：ABC 共同准备，各自完成账号与文件上传

**可以同时进行，互相不用等。**

ABC 共同确定角色、姓名/学号和沟通方式。仓库是 private，A/B 若没有访问权限，由仓库所有者通过 GitHub 设置授予协作者权限；也可以先分发同一份源码 ZIP。账号密码不共享。

三人使用同一个版本的 `DSA5208_Project3_source.zip`。A 执行 A1；B 执行 B1 的下载/上传/解压部分；C 执行 C1。各自向课程/学校申请个人 HPC 账号。

各自上传到自己的目录：

```text
A：DSA5208_P3_A/Project3
B：DSA5208_P3_B/Project3
C：DSA5208_P3_C/Project3
```

成功登录者先执行环境探测。未取得账号的人直接进入 S1 的代码阅读，不等待其他人的账号，但还不能执行本人集群步骤。

**交给 C：**源码 ZIP SHA256、是否能 SSH、detect_env 输出、账号/权限错误。C 整理团队状态，不收集密码。

## S1：A3、B2、C3 同时阅读代码并确认理解

**无需等待 HPC 权限，可以和 S0 并行。**

| A 做 A3 | B 做 B2 | C 做 C3 |
|---|---|---|
| 串行更新、双数组、残差、构造解析解 | 分区、全局 offset、halo、消息 tag、Waitall | OpenMP 循环、reduction、线程数、MPI 线程支持、亲和性 |

代码已经提供，先理解并验证现有版本。确有问题再修改，不需要三人各自重写一套算法。

三人用一次共同讨论确认：N 是内部点数，初值/边界相同，benchmark 与 solve 不同，统一用 double；每 rank 至少一行；报告中分别讨论计算、通信和全局收敛检查。

**交付：**A 写算法/解析解草稿，B 画行分区与消息示意，C 写资源公式和 OpenMP 设计草稿。发现代码问题时先统一修改并重新分发，不在三个目录悄悄各改各的。

## S2：C2 先确认环境，再 A2 和 B1 后半配置编译

**需要学校账号与课程资源信息；A/B 配置依赖 C 已核实的环境说明。**

C 向课程资料/TA 确认以下值：Atlas/Vanda、登录主机、PBS、CPU 队列、project code/flag、compiler/Open MPI 模块、PBS 集成启动方式、节点/核/内存/时限限制。

C 完成 C2，填写本人的 `configs/site_modules.sh` 和 `configs/cluster.env`，编译成功后，把已确认的值分享给 A/B。账号先开通的 A/B 也可以协助查资料，不必把信息核实全部压在 C 身上。

A 完成 A2；B 返回 B1 的配置/编译部分。每个人在自己的集群目录执行：

```bash
bash -l scripts/build.sh
ls -l bin
cat results/build/build.txt
```

三人核对 compiler、MPI、优化参数和模块组合。`bin` 中应有 jacobi_serial、jacobi_parallel、hello_hybrid。

**进入 S3 的条件：**C 已编译成功且资源信息可用。A/B 的账号若还在等待，C 可以先进入 S3；A/B 后续补做，不能把 C 的日志写成自己的操作。

## S3：C4 先跑 smoke 和 verify，随后 A4、B3/B4 独立重跑

C 先跑小作业，优先发现调度器、Open MPI/PBS 和 binding 的部署问题。

C 在集群登录节点、项目根目录执行：

```bash
python3 scripts/make_jobs.py --preset smoke --iters 100 --repeats 3
JOB_DIR=$(ls -td jobs/generated/smoke-* | head -n 1)
cat "$JOB_DIR/p3-smoke-1.pbs"
JOB_ID=$(qsub "$JOB_DIR/p3-smoke-1.pbs")
qstat -f "$JOB_ID"
```

等实际运行完成后，按 C4 检查两条 rank 记录、两个不同 host、每 rank 两线程和 COMPLETE。然后生成/提交 verify：

```bash
python3 scripts/make_jobs.py --preset verify
JOB_DIR=$(ls -td jobs/generated/verify-* | head -n 1)
cat "$JOB_DIR/p3-verify-1.pbs"
JOB_ID=$(qsub "$JOB_DIR/p3-verify-1.pbs")
qstat -f "$JOB_ID"
```

verify 结束后必须有 PASS 和 summary.json。C 把通过的环境说明及问题修复交给 A/B。

接着 A 做 A4（含 smoke）；B 做 B3/B4。A/B 此时可以同时跑，各自保存本人证据。C 不必再重复 C4。

**等待条件：**正式矩阵负责人必须在自己的环境中通过 smoke/verify。有错先修，不能用他人的 PASS 替代自己未验证的环境。

## S4：A5 先预跑；B/C 同时准备实验与写作材料

A 做 A5：只提交 serial 和最大核数 MPI 两个端点，判断求解循环测量长度及整个作业的 walltime。

```bash
python3 scripts/make_jobs.py --preset strong --n 512 --iters 1000 --repeats 3 --cpus-per-node 8 --single-node-cores 1,2,4,8 --nodes-list 1,2
JOB_DIR=$(ls -td jobs/generated/strong-* | head -n 1)
cat "$JOB_DIR/manifest.json"
cat "$JOB_DIR/p3-strong-1.pbs"
cat "$JOB_DIR/p3-strong-6.pbs"
qsub "$JOB_DIR/p3-strong-1.pbs"
qsub "$JOB_DIR/p3-strong-6.pbs"
```

以上仅适用于已批准的 8 核/节点示例资源。预跑若太短，统一增加迭代数；若总时限不足，先修正 walltime/范围。

同时：B 检查 B5 的四组通信对照保持同布局；C 检查 C5/C6 的 weak/mix 参数和线程资源，草拟环境与计时说明。B/C 可生成脚本审查，但在 S5 前不启动完整正式矩阵。

**交付：**A 把端点时间、建议正式迭代数、节点/CPU 信息交给 B/C。三人确认各实验也有足够的测量持续时间；需要时对最快的混合配置补一个小预跑。

## S5：ABC 一起冻结正式实验协议，再各自开跑

此阶段完成一次共同确认，而不是三人各自选择参数。

| 项目 | 初版建议 / 必须记录的值 |
|---|---|
| 正式源码 | 同一 ZIP / Git commit，记录 source_hash |
| 集群与 CPU | 同一集群；需要直接比较的配置用同类计算节点 CPU |
| compiler/MPI/flags | 实际 module、版本、-O3 和 OpenMP 配置一致 |
| strong | N=512/1024，serial+MPI+hybrid，固定轮数，check=0 |
| comm/mix | N=1024，与 strong 统一轮数，check=0 |
| weak | 单核 N=256，N 随 √C 增大，固定轮数，check=0 |
| repeats | 正式每配置 5 次 measured + 1 次 warmup |
| 资源 | 示例每节点用 8 核，单/双节点；以实际批准为准 |
| profile | 正式主矩阵 false；诊断另做 |
| 计时 | 求解循环，MPI 取各 rank elapsed 最大值 |

在三人项目根目录核对源代码 hash：

```bash
python3 -c "import sys; sys.path.insert(0, 'scripts'); from benchmark import source_hash; print(source_hash())"
```

C 将最终协议写入 `report/实验协议.md` 并分享给 A/B，记录预跑确定的真实值。若编译环境或 CPU 不同，先解决比较口径/补基线，不能仅因为 source_hash 一样就认为全部测量可比。

三人把 smoke 和性能预跑从顶层 `results/raw` 移到 `results/pilot/raw`，保留原始证据，只让正式矩阵进入后续汇总。逐个核对并移动实际目录，不批量误移正式结果。

**进入 S6 的条件：**协议已确认，负责人的 smoke/verify 已通过。正式期间改变 C++、Makefile 或测量/分析脚本，会改变 source_hash；需要重新评估并补跑受影响的基线。文档修订通常不改变 source_hash，但仍应记录。

## S6：A6、B5、C5/C6 可以同时执行正式实验

下面假设预跑确定正式 10000 轮。若协议写其他值，三人一起替换。各人在本人的集群 Linux 项目目录逐行执行：

```bash
FORMAL_ITERS=10000
```

### A6：两档 strong，共 20 个配置

```bash
python3 scripts/make_jobs.py --preset strong --n 512 --iters "$FORMAL_ITERS" --repeats 5 --cpus-per-node 8 --single-node-cores 1,2,4,8 --nodes-list 1,2
```

按 A6 审核并提交这一批，再生成另一档：

```bash
python3 scripts/make_jobs.py --preset strong --n 1024 --iters "$FORMAL_ITERS" --repeats 5 --cpus-per-node 8 --single-node-cores 1,2,4,8 --nodes-list 1,2
```

每档 10 个配置，包含真正 serial 基线、MPI 1/2/4/8/16 核和每 rank 两线程 hybrid 2/4/8/16 核。

### B5：四组通信对照，共 4 个配置

```bash
python3 scripts/make_jobs.py --preset comm --n 1024 --iters "$FORMAL_ITERS" --repeats 5 --cpus-per-node 8 --nodes-list 1,2 --mix-threads 2
```

按 B5 审核/提交 hybrid 与 overlap 的单节点、双节点对照。仅变通信方式，同一对照的 nodes/ranks/threads 均相同。

### C5/C6：weak 5 个配置，mix 8 个配置

```bash
python3 scripts/make_jobs.py --preset weak --n 256 --iters "$FORMAL_ITERS" --repeats 5 --cpus-per-node 8 --single-node-cores 1,2,4,8 --nodes-list 1,2
```

先按 C5 审核/提交，再生成 mix：

```bash
python3 scripts/make_jobs.py --preset mix --n 1024 --iters "$FORMAL_ITERS" --repeats 5 --cpus-per-node 8 --nodes-list 1,2 --mix-threads 1,2,4,8
```

按 C6 审核/提交。每个矩阵生成后，先取它对应的 JOB_DIR 并提交，避免再生成下一批时用错“最新目录”。

**可以并行的是三人的工作，不是无上限同时提交所有作业。** 遵守个人/课程共享配额，必要时三人约定轮流提交。排队时可以写章节，彼此不必等所有作业结束。

## S7：ABC 各自验收；可选扩展放在核心结果之后

A 做 A7；B 做 B7 的检查部分；C 按 C10 的数量/记录要求检查自己的 weak/mix。

每个正式 run 检查：COMPLETE、5 次 measured、topology、参数、source/build、实际 CPU、最终残差。benchmark 固定轮数不一定收敛，不能据此误报失败或收敛；solve 则必须达到容差。

发现缺少某个配置或失败，原负责人补跑，保留失败记录。只针对问题补跑，不反复重做已足够的数据。

核心 37 个配置齐全后，可选 B6 profile 诊断、C7 q=1/10/50 检查频率实验。它们可以同时进行，不占用解决主矩阵缺项的时间。

**交给 C：**各人结果清单，标明哪些是正式、预跑、profile、可选 solve；不要让 C 靠目录名猜测。

## S8：A8、B7、C8 同时下载并交接结果

三人在集群各自按个人指南归档本人 results 和 jobs/generated；A/B 在 Windows 下载，C 在 Mac 下载。每份归档都核对集群与本机的 SHA256。

```text
A → C：A_results.tar.gz + hash + 配置清单 + 算法/验证草稿
B → C：B_results.tar.gz + hash + 配置清单 + MPI/通信草稿
C 自己：C_results.tar.gz + hash + weak/mix 清单
```

C 将三份原始归档保留，按 C8/C9 建立本机汇总目录。A/B 完成交接后继续写章节，不用等待绘图完成。

## S9：C9/C10 汇总绘图；A/B 核对与补测

C 导入 A/B 原始结果，默认只从 `results/raw` 汇总，避免 imported 备份重复计算：

```bash
python3 scripts/analyze.py --official-only
```

C 检查 37 个核心配置与重复次数，并反馈问题：A 负责 strong/serial/验证，B 负责通信配对，C 负责 weak/mix。若 speedup 空白，核实 CPU/source/build/workload/family 后，由原负责人补匹配基线；不能手工填数。

确认汇总有效后，按 C10 的本机 venv 步骤生成图：

```bash
python scripts/analyze.py --official-only --plots
```

**交付：**summary、图表和“每图使用哪些配置/原始目录”的说明。A 看算法/误差和基线，B 看 hybrid/overlap 是否同资源，C 看 weak 的每核点数和 mix 的线程/节点分组。

## S10：ABC 同时写作，C11 最后整合

| A 写 | B 写 | C 写 / 整合 |
|---|---|---|
| 算法、解析解、正确性、strong | MPI 分区、halo、非阻塞设计、通信对照 | 环境、OpenMP、计时、weak/mix、总体结论和限制 |

三人都更新真实贡献与 AI 使用记录。C 汇入章节、图表、参考资料，填写 team.csv，完善 README，并导出 `report/report.pdf`。

等待全员审核后才进入最终复现：算法与实现相符；benchmark/solve 口径清楚；图表来自真实 Atlas/Vanda；姓名/学号完整；没有把本机开发数据当正式结果。

## S11：C 分发最终版本，A9 干净目录复现，B 复核

C 生成最终源码分发包：

```bash
python3 scripts/package.py --kind source
```

A 按 A9 用新目录 `DSA5208_P3_A_FINAL` 上传/解压，填入已确认配置，重新编译，跑 verify 与一个关键配置。不要复用旧 bin。B 核对最终代码中的消息/Waitall 与报告描述，以及通信图使用的资源布局。

这次独立复现的 smoke/性能试跑要标记为复现证据，保存在独立结果目录；除非明确决定增加正式样本，不并入原来的五次测量均值/中位数。

**交给 C：**最终版本 hash、真实复现日志、是否 PASS、发现的问题。若只修文档，可继续；若改数值/测量代码，重新验证并检查是否需补正式数据。

## S12：C12 打包上传，A/B 另一人核查

C 从已经汇总并完成报告的目录执行：

```bash
python3 scripts/package.py --kind full --final
```

C 上传 Canvas 的 PDF 与源码/README 包；A 或 B 从 Canvas 下载并检查文件内容/hash、三人信息和提交状态。目标 2026-11-12 完成，作业要求为 11-13 之前，精确时刻以 Canvas 为准。

进度不确定时，可在 10-30 之前由团队自行发进度报告给教师；不需要等待完整正式矩阵，可在 S4–S6 已有可审阅结果时发出。

## 二、遇到卡点，谁继续做什么

| 卡点 | 暂停哪一步 | 其他人可继续做 |
|---|---|---|
| 某人账号未开通 | 该人的集群操作 | S1 读代码、数学/设计草稿；已开通者先做 C4 路线 |
| C 的 smoke 配置失败 | 依赖该配置的正式作业 | A/B 读代码、检查配置、排查；不扩大矩阵 |
| verify 数值失败 | 对应代码版本的正式矩阵 | 定位错误、保留失败证据、章节草稿 |
| 作业排队 | 等结果检查，不反复提交同配置 | 报告、README、已有结果核查 |
| A 的基线缺项 | 相应 speedup 图 | B/C 的完整矩阵和不依赖该基线的分析 |
| source/build/CPU 不匹配 | 相应比较结论 | 分开记录，补匹配实验，其余合法对照继续 |
| 实验超时 | 该配置 | 保存失败日志、修正时限后重跑，其他配置继续 |

**实际执行主线：ABC 准备 → ABC 分头读代码 → C 确认环境 → ABC 编译 → C 首次验证 → A/B 独立验证 → A 预跑 → ABC 冻结协议 → ABC 分头正式实验 → ABC 验收交接 → C 汇总 → ABC 写作 → A 独立复现 → C 提交、另一人核查。**

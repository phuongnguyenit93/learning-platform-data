# Choosing Batch Capacity Based on Deadlines and Budgets

Batch processing handles a finite set of work such as report aggregation, ETL, media rendering, simulation computing, image processing, or batch training. Unlike interactive APIs, batches can usually run over longer windows and split into many tasks. However, batches still have deadlines, budget limits, and data quality requirements. Choosing too little compute causes jobs to miss deadlines; choosing too much may finish early while wasting money or overloading databases, storage, and networks.

Capacity selection is a balancing act across **workload volume**, **available time**, **per-worker capability**, **parallelizability**, **capacity reliability**, and **total pipeline cost**. Do not start by asking "how many VMs do I need?"—instead determine when the batch must finish, how much data there is, how much CPU/memory/I/O each unit consumes, what can run in parallel, and what happens when a worker fails or is reclaimed.

In the `CLOUD_CORE_SERVICES_COMPUTE` module, this lesson connects choices of CPU, memory, networking, VMs, containers, serverless, and interruptible compute to batch operational goals. You will build capacity estimates from benchmarks, verify deadline feasibility, compare configurations, and tune to budget rather than simply maximizing instance counts.

After this lesson, you will be able to:

- Decompose a deadline into queue wait, provisioning, execution, output commit, and buffer.
- Estimate compute demand from data volume and measured processing times.
- Calculate required workers/vCPUs accounting for utilization and parallel efficiency.
- Select CPU, memory, GPU, storage, and network resources based on actual bottlenecks.
- Compare VMs, containers, serverless, on-demand, committed capacity, and spot/interruptible capacity.
- Build a cost model covering compute, storage, networking, orchestration, retries, and idle time.
- Design autoscaling, checkpointing, retries, and backpressure to meet deadlines when capacity fluctuates.
- Benchmark, load-test, and choose a configuration that satisfies both deadlines and budgets.

## 1. Starting from deadlines and budgets

The first two constraints are when the run must complete and the maximum amount you can spend per run or operational period.

### A deadline is more than compute time

Total elapsed time from batch creation until outputs are accepted may include:

1. **Queue wait:** time waiting for the scheduler or capacity.
2. **Provisioning:** creating VMs/containers/functions, attaching networks, and provisioning storage.
3. **Startup:** pulling images, bootstrapping, loading models, or warming caches.
4. **Execution:** data processing duration.
5. **Commit/output:** writing results, publishing events, building manifests, and checking checksums.
6. **Validation:** verifying quality and completeness.
7. **Buffer:** headroom for stragglers, retries, interruptions, and load variance.

Therefore:

\[
T_{\text{total}} =
T_{\text{queue}} + T_{\text{provision}} + T_{\text{startup}} +
T_{\text{execution}} + T_{\text{commit}} + T_{\text{validation}}
\]

Remaining execution time available for compute:

\[
T_{\text{execution,budget}} =
T_{\text{deadline}} - T_{\text{other stages}} - T_{\text{buffer}}
\]

For example, a batch must finish before 06:00. The schedule starts at 05:00, but queue/provision/startup takes 4 minutes, commit and validation take 5 minutes, and buffer is 6 minutes. The execution budget is only 45 minutes. Sizing capacity against the full 60 minutes yields an overly optimistic estimate.

### Budgets need an explicit scope

Budgets can be defined per:

- Single batch run.
- Day or month.
- Pipeline or workload group.
- Direct compute cost.
- Total cloud cost including compute, storage, networking, logging, and dependent services.

Know whether the budget is a hard cap (must never be exceeded) or a target (may be exceeded in exceptional situations to protect deadlines). If deadline and budget cannot both be met simultaneously, state the trade-off explicitly: reduce data scope, change algorithms, extend the deadline, accept cheaper capacity with interruption risk, or request additional budget.

### Goal definition table

| Question | Example | Impact on capacity |
|---|---|---|
| When does the batch start? | 01:00 daily | Defines the execution window |
| When is the deadline? | 03:00 | Total time constraint |
| How much execution budget remains? | 90 minutes after subtracting startup/commit/buffer | Compute duration limit |
| How much data is there? | 500 GB or 20 million records | Defines work volume |
| Budget per run? | \$12 USD | Caps cost/run |
| What happens if late? | Delayed report, no transaction impact | Determines deadline priority |
| What if capacity is scarce? | Can fall back to on-demand | Defines fallback policy |
| Can it rerun? | Yes, checkpointed by partition | Enables spot/interruptible capacity |

## 2. Profiling the workload before choosing instances

A workload profile describes actual work characteristics rather than just an application name.

Information to gather:

- Total records, files, objects, partitions, or tasks.
- Input and output data sizes.
- CPU time or wall-clock time per unit.
- Peak memory and working set.
- Storage read/write, IOPS, throughput, and request counts.
- Network bytes, packet rates, and cross-zone/region transfers.
- Fraction of tasks that can run in parallel.
- Initialization, warm-up, and shutdown times.
- Task duration distribution, including the slowest tasks.
- Error, retry, and interruption rates.
- Sequential steps and inter-step dependencies.
- Checkpointing, idempotency, and recovery capabilities.

### Bottleneck classification

| Workload type | Symptoms | Capacity to prioritize |
|---|---|---|
| CPU-bound | CPU near saturation; adding CPU improves throughput | More vCPUs, suitable CPU clock/architecture |
| Memory-bound | Large working set, heavy paging/OOM or GC | Large RAM, memory bandwidth, heap tuning |
| I/O-bound | Low CPU while waiting on disk/object storage | Storage throughput/IOPS, batch I/O, caching |
| Network-bound | Low CPU, high data transfer wait times | Network bandwidth, locality, parallel transfers |
| GPU/accelerator-bound | CPU waiting on accelerator, high kernel utilization | Appropriate GPU/accelerator, VRAM, and data pipeline |
| Coordination-bound | Adding workers barely increases throughput | Reduce locks, shuffles, serialization, and communication |
| Dependency-bound | Database/API throttles rate | Pools, quotas, batch queries, backpressure, and dependency capacity |

Do not choose high-CPU machines for a workload throttled by database connections or networking. Adding compute in that case raises cost without improving throughput.

### CPU time vs. wall-clock time

CPU time is total time CPUs spend actively executing; wall-clock time is how long the user waits. A task running 10 minutes with 4 busy cores consumes roughly 40 core-minutes, whereas if it mostly waits on networking, CPU time is much lower.

When benchmarking, record all of:

- Wall-clock duration.
- CPU utilization and CPU time.
- Peak/working-set memory.
- I/O wait and network wait.
- Throughput (records/second, GB/minute, tasks/hour).
- Error/retry rate.

## 3. Estimating total compute demand

You can start by measuring a reference configuration and extrapolating carefully.

### CPU-work method

Suppose each record consumes an average of \(s\) CPU-seconds and there are \(N\) records:

\[
W_{\text{CPU}} = N \times s
\]

To convert to CPU core-hours:

\[
W_{\text{CPU,core-hours}} =
\frac{N \times s}{3600}
\]

For example, 12 million records at an average of 0.08 CPU-second per record:

\[
W_{\text{CPU}} =
12{,}000{,}000 \times 0.08
= 960{,}000\ \text{CPU-seconds}
\]

Equivalent to roughly 266.7 core-hours. This is ideal measured CPU work before accounting for overhead, skew, retries, and parallel efficiency.

### Measured-throughput method

If a worker of a given configuration processes \(r\) records/second under representative load, ideal processing time for \(N\) records across \(P\) workers is:

\[
T_{\text{ideal}} = \frac{N}{P \times r}
\]

In practice, throughput rarely scales linearly due to coordination, I/O, locks, networking, cache contention, and task skew. Model this with parallel efficiency \(\eta\):

\[
T_{\text{execution}} \approx
\frac{N}{P \times r \times \eta}
\]

Where \(\eta\) lies between 0 and 1. This is an estimation model; measure \(\eta\) across multiple parallelism levels.

### Estimating required vCPUs

Given total CPU demand \(W_{\text{CPU}}\) core-hours, execution window \(D\) hours, target utilization \(U\), and parallel efficiency \(\eta\):

\[
V_{\text{required}} \approx
\frac{W_{\text{CPU}}}{D \times U \times \eta}
\]

For example, total work is 2 core-hours, execution window is 15 minutes (0.25 hours), target utilization is 70%, and parallel efficiency is 80%:

\[
V_{\text{required}} =
\frac{2}{0.25 \times 0.70 \times 0.80}
\approx 14.29\ \text{vCPU}
\]

You can start testing with 16 total vCPUs. Using four 4-vCPU workers gives 16 nominal vCPUs. Then benchmark to verify whether throughput, memory, and dependencies keep up.

This formula fits CPU-bound workloads. For I/O-bound, GPU-bound, or dependency-bound workloads, build a bottleneck-specific model and benchmark end-to-end.

### Do not extrapolate linearly too far

Doubling a worker's CPU does not necessarily double processing speed. Causes include:

- Sequential algorithms that cannot parallelize.
- Memory bandwidth or cache becoming the bottleneck.
- Storage/network not scaling proportionally.
- Databases/APIs capping request rates.
- Coordination and shuffling growing with worker count.
- Uneven task sizes.
- Larger instances having different per-vCPU performance than smaller ones.

Always benchmark at several capacity points and plot throughput vs. cost to spot diminishing returns.

## 4. Decomposing and parallelizing batches

Adding workers only helps when work can be divided and distributed. Before adding capacity, look for ways to shrink the sequential portion.

### Partitioning

Split inputs into independent partitions by key, range, object, or shard. Each task gets a stable ID, input version, and isolated output.

For example, 20 million records can split into 200 partitions of 100,000 records each. The scheduler dispatches partitions to workers; once a worker finishes, it picks up the next partition.

Avoid overly large partitions that run long and make retries expensive; overly small partitions create scheduling, metadata, and connection overhead.

### Fan-out/fan-in

- Fan-out: spawn many independent tasks from one batch.
- Fan-in: aggregate results after tasks finish.

Maintain a manifest tracking task status (`PENDING`/`RUNNING`/`COMPLETED`/`FAILED`), attempt counts, output references, and checksums. Fan-in should read only validly committed outputs.

### Task skew and stragglers

If 90 partitions finish in 5 minutes while 10 partitions take 30 minutes, the batch still has to wait on the slow tasks. Adding workers will not fix an oversized partition or skewed data.

Mitigations:

- Partition by estimated work weight rather than raw record counts.
- Measure duration per partition and key.
- Use dynamic work stealing.
- Use speculative execution for slow tasks when side effects are idempotent.
- Prevent two workers from writing the same final output without commits/fencing.

### Amdahl's Law

If the sequential fraction of work is \(f\), maximum speedup with \(P\) workers under an ideal model is:

\[
Speedup(P) = \frac{1}{f + \frac{1-f}{P}}
\]

If 20% of the pipeline is sequential (\(f=0.2\)), even infinite workers yield at most a 5x speedup. Thus, optimizing sequential stages—input loading, merging, validation, and committing—can deliver greater gains than adding VMs.

## 5. Choosing CPUs and instance shapes

The right CPU depends on computational characteristics, not vCPU count alone.

### General-purpose

Suitable for balanced CPU/memory workloads, moderate ETL, orchestration, auxiliary APIs, and mixed jobs.

### Compute-optimized

Suitable for CPU-bound tasks such as compression, encryption, numerical computing, simulation, and data transforms. Compare per-vCPU performance, clock speeds, architecture, and hourly pricing.

### Memory-optimized

Suitable for large joins, in-memory aggregations, caches, graph processing, and workloads with large working sets. Account for memory bandwidth and heap/runtime limits.

### GPU/accelerator

Suitable for ML batch training/inference, image/video processing, or workloads with accelerator-supported kernels. GPUs do not automatically speed up every workload. Account for data loading time, CPU preprocessing, VRAM, batch size, and actual utilization.

### ARM vs. x86

Compare by application performance and binary/dependency compatibility, not price alone. Check multi-arch container images, native libraries, compiler flags, runtimes, and licensing.

### One large worker or many small workers?

| Choice | Pros | Limitations |
|---|---|---|
| Few large workers | Less task coordination, can leverage large RAM and process big partitions | Larger failure domain, coarser scaling granularity, harder to fully utilize |
| Many small workers | Easy horizontal scaling, smaller task failure blast radius, diverse capacity pools | More connections, network traffic, scheduler overhead, and coordination |
| Mixed workers | Match distinct shapes to distinct stages | Higher pipeline complexity, requires routing and capacity policies |

Choose based on partition size, memory footprint, parallelism, quotas, and real pricing. No single configuration is optimal for every stage.

## 6. Memory, storage, and network are also capacity

A batch can fail even with ample CPU if memory or I/O falls short.

### Memory

Estimate memory from:

- Per-task working set.
- Concurrent tasks per worker.
- Runtime/heap overhead.
- Buffers, shuffles, caches, and serialization.
- Off-heap native memory.
- OS, agent, and container overhead.
- Peak memory rather than average alone.

If one task needs a 3 GiB working set and a worker runs 4 tasks concurrently, you need at least ~12 GiB for tasks plus overhead and headroom. Benchmark peak memory and test for OOMs.

### Storage

Distinguish between:

- Ephemeral/local disks for scratch, shuffle, and temporary outputs.
- Persistent block storage for data tied to volume lifecycles.
- Object storage for durable inputs/outputs shared across workers.
- Shared file storage for workloads requiring filesystem semantics.

Evaluate throughput, IOPS, queue depth, latency, file counts, and metadata operations. Lots of small files can bottleneck on request/metadata rates despite low total byte volume.

### Network

Measure bytes/second, packet rates, latency, and cross-zone/cross-region transfers. If every worker downloads the same huge dataset, scaling out can inflate egress and saturate source storage.

Optimize via data locality, partitioning, compression, caching, batched transfers, and avoiding unnecessary shuffles. Include data transfer fees in the cost model.

## 7. Choosing compute models: VMs, containers, or serverless

| Model | Best fit when | Considerations |
|---|---|---|
| VM/instance group | Long jobs needing custom OS/runtime, local disks, or GPUs; strict instance family control | Boot time, patching, capacity reservations, autoscaling, and shutdown |
| Containers on an orchestrator | Packageable tasks needing schedulers, queue workers, and diverse node pools | Pod startup, image pulls, requests/limits, node capacity, and orchestration overhead |
| Serverless functions | Short, event-driven tasks with clear runtime/concurrency bounds | Execution duration limits, memory/CPU coupling, cold starts, payload limits, and quotas |
| Managed batch service | Built-in queues, job definitions, retries, scheduling, and capacity management needed | Scheduler semantics, quotas, pricing, retries, and customization limits |
| Managed data processing | ETL/SQL/stream/batch with specialized engines | Per-worker/slot/data pricing, startup, and minimum billing units |

A single batch can combine models: a managed scheduler creates jobs, containers process partitions, functions handle short events, and databases/object storage hold state.

### Startup time vs. job duration

For a 20-second job, a 90-second VM boot consumes most of the deadline. For a 6-hour job, a 90-second startup is negligible. Evaluate compute shapes and platforms across the full lifecycle, not solely by hourly CPU rates.

### Minimum billing and scale-to-zero

Serverless or managed services may bill per request, duration, memory/CPU, or processing unit. VMs generally bill by allocated time under provider rounding/commitment rules. Check minimum billing, startup, idle, and storage charges before comparing.

## 8. Choosing stable vs. interruptible capacity

Common options:

- **On-demand:** pay-as-you-go capacity; flexible, though unit price is usually higher than committed options.
- **Reserved/committed use/savings plans:** trade usage or spend commitments for discounted rates; less flexible if workloads shift.
- **Spot/preemptible/interruptible:** leverage excess capacity at lower prices, subject to reclamation.
- **Capacity reservations/dedicated capacity:** reserve or guarantee allocation per provider product terms; may incur extra charges.
- **Hybrid pools:** combine stable baseline capacity with cheap/interruptible capacity for elastic bursts.

### When to use spot for batches?

Suitable when:

- Jobs split into independent partitions.
- Workers have safe checkpoints and output commits.
- Retries/idempotency are engineered.
- Replacement capacity exists or deadlines have sufficient margin.
- No unique state lives solely on the instance.
- Tasks can shift to on-demand if needed.

Avoid placing an entire deadline-critical batch on spot without fallback. Interruption rates and replacement availability vary by region, instance family, and time of day; never assume spot is always available.

### Capacity mix model

One approach:

- Stable on-demand/committed baseline guaranteeing minimum throughput.
- Spot pool for retryable workload slices.
- On-demand burst or reservations to rescue deadlines if spot dries up.
- Queues holding pending tasks and re-dispatching them when workers are reclaimed.

Ratios across pools should reflect historical interruption rates, pricing, provisioning time, quotas, and acceptable deadline miss rates.

## 9. Cost model for a single batch run

Cost is more than vCPUs multiplied by hourly price. Account for all billed resources and durations.

\[
C_{\text{total}} =
C_{\text{compute}} + C_{\text{storage}} + C_{\text{network}} +
C_{\text{managed services}} + C_{\text{observability}} +
C_{\text{retry/waste}}
\]

### Compute cost

For worker type \(i\):

\[
C_{\text{compute}} = \sum_i N_i \times T_i \times P_i
\]

Where:

- \(N_i\): number of workers.
- \(T_i\): billed duration per worker (hours).
- \(P_i\): hourly price per worker.

If workers bill by vCPU/memory/requests, substitute the corresponding billing units. Include boot, idle, draining, and rounding caused by billing granularity.

### Storage and network costs

May include:

- GB-months of volumes/object storage.
- Provisioned IOPS/throughput.
- Read/write request counts.
- Snapshots and backup retention.
- Cross-zone/cross-region data transfers.
- Internet egress or NAT processing.
- Managed service data processing charges.

### Retry and interruption costs

If a job re-runs 10% of its work due to interruptions, total compute no longer equals ideal completion time. Measure wasted compute and checkpoint/recovery overhead.

This can be modeled as:

\[
C_{\text{effective}} =
C_{\text{successful work}} + C_{\text{retries}} + C_{\text{idle}}
\]

Never compare spot vs. on-demand hourly rates alone. Compare cost per successful batch or cost per million validated records.

### Opportunity cost of missing a deadline

Late batches can cause business consequences such as delayed reports, stalled downstream data, or SLA breaches. When quantifiable, factor that cost into capacity decisions. A slightly pricier compute configuration may have lower expected total cost if it significantly lowers deadline miss risk.

## 10. Optimizing under deadline and budget constraints

The problem can be framed as:

- Minimize total cost.
- Subject to completion time not exceeding the deadline.
- Subject to memory/storage/network capacities not being exceeded.
- Subject to availability, quotas, security, and data locality.
- Subject to on-time completion probability meeting an acceptable threshold.

Do not pick the cheapest configuration based purely on average benchmarks. Account for duration variance, task skew, capacity availability, interruptions, and retries.

### Cost-performance frontier

For each configuration, measure:

- Total cost.
- p50/p90/p95 completion times.
- Throughput.
- Failure/retry rates.
- Peak resource utilization.
- Cost per successful unit.

Configuration A may be cheapest yet miss the deadline. Configuration B may be faster yet blow the budget. Configuration C satisfies both constraints with comfortable buffer.

### Batch SLOs

Set targets such as:

- 99% of batches finish before 05:45.
- Per-run cost stays under \$15 USD under normal conditions.
- Retry rate below 3%.
- Zero lost committed partitions.
- Fallback capacity available within a defined window.

SLOs ground capacity decisions in probabilities rather than a single benchmark run.

## 11. Calculation example: batch due within 30 minutes

A batch processes 12,000 records. Benchmarking on a 4-vCPU worker shows each record averages 0.6 CPU-seconds. Total CPU demand:

\[
12{,}000 \times 0.6 = 7{,}200\ \text{CPU-seconds}
= 2\ \text{core-hours}
\]

Total deadline is 30 minutes. Subtracting 4 minutes for provisioning/startup, 3 minutes for output commit/validation, and 3 minutes buffer leaves 20 minutes of execution budget. Assume 70% target utilization and 80% parallel efficiency.

\[
V_{\text{required}} =
\frac{2}{(20/60) \times 0.70 \times 0.80}
\approx 10.72\ \text{vCPU}
\]

On CPU alone, 12 vCPUs is an initial estimate; 16 vCPUs adds headroom for benchmarking and skew. Still, verify memory, storage, and dependencies before finalizing.

Using illustrative pricing:

| Configuration | Nominal capacity | Illustrative price | Estimated execution | Notes |
|---|---:|---:|---:|---|
| 3 workers × 4 vCPU | 12 vCPU | \$0.24 USD/worker-hour | ~17.9 minutes per CPU model | Tight against 20-minute execution budget, thin margin |
| 4 workers × 4 vCPU | 16 vCPU | \$0.24 USD/worker-hour | ~13.4 minutes | Better margin; compute cost ~\$0.21 USD for 13.4 minutes |
| 2 workers × 8 vCPU | 16 vCPU | \$0.43 USD/worker-hour | Needs large-shape benchmark | May cut coordination overhead, though price/perf depends on CPU and memory |

Prices are purely illustrative to demonstrate the math and do not represent actual provider rate cards. Execution estimates also assume parallel efficiency holds at 80%. If the database only permits 5 concurrent queries, 16 vCPUs will not scale throughput proportionally.

Base final decisions on full-pipeline benchmarks. If 4 × 4 vCPUs hits the p95 deadline under budget, choose it. If p95 still misses, investigate bottlenecks before adding more workers.

## 12. Fixed-budget example: picking the cheapest option meeting the deadline

A pipeline must process 2 TB of data before 04:00. Maximum compute and storage budget is \$20 USD per run. Three configurations were benchmarked:

| Configuration | p95 duration | Compute cost | Storage/network | Total cost | Meets deadline? |
|---|---:|---:|---:|---:|---|
| 4 on-demand workers | 95 minutes | \$12 USD | \$3 USD | \$15 USD | No |
| 8 mixed on-demand/spot workers | 55 minutes | \$13 USD | \$3.50 USD | \$16.50 USD | Yes |
| 12 on-demand workers | 38 minutes | \$22 USD | \$4 USD | \$26 USD | Yes, over budget |

In this example, the 8-worker setup is the right choice because it satisfies both deadline and budget. The 4-worker setup is cheaper but misses the deadline; the 12-worker setup is faster but exceeds budget.

Also check spot interruption rates. If the 55-minute p95 already incorporates historical retries and interruptions, the result is trustworthy. Otherwise, run fault-injection tests or reserve on-demand fallback.

## 13. Probabilistic deadlines: use p90/p95 instead of averages

Batch task durations vary. Averages can hide a cluster of slow tasks, causing missed deadlines.

Track:

- p50: typical experience.
- p90/p95: vast majority of runs.
- p99: tail latency or rare long runs.
- Max: worst observed, not worst possible.

For strict deadlines, choose capacity from multi-run distributions plus appropriate buffer. A batch averaging 40 minutes with a 75-minute p95 will not reliably meet a 60-minute deadline.

### Tails and stragglers

With many partitions, batch completion depends on the final task. If 1,000 partitions run in parallel, just a few ultra-slow partitions can drag out the entire batch.

How to handle them:

- Track duration per partition/key.
- Balance partition sizes.
- Let workers pull the next task upon finishing.
- Use speculative copies for straggler tasks when output commits are idempotent.
- Reduce data skew in joins/group-bys.
- Split long and short stages to scale them independently.

## 14. Autoscaling by queue depth and deadline

Autoscaling should react to both remaining work volume and remaining time until the deadline.

Useful metrics:

- Queue depth.
- Oldest message age.
- Estimated remaining work.
- Average/p95 task duration.
- Worker throughput.
- Deadline slack (remaining time minus estimated execution).
- Worker startup time and capacity availability.
- Error/retry/interruption rates.

### Deadline slack

\[
Slack = T_{\text{deadline remaining}} -
T_{\text{estimated work remaining}}
\]

If slack approaches zero, scale capacity up or trigger fallback. If slack is generous, you can scale workers down to save money as long as the deadline stays safe.

### Estimating workers from queue depth

With \(Q\) remaining tasks, each worker averaging \(r\) tasks/second, \(D\) seconds remaining, and target utilization \(U\):

\[
N_{\text{workers}} \geq
\left\lceil \frac{Q}{r \times D \times U} \right\rceil
\]

Use measured throughput for the same task type. If multiple task types exist, calculate per queue/partition or total CPU demand rather than blending an unrepresentative average rate.

### Scale-out and scale-in

Scale-out must account for provisioning and startup lag. Spinning up workers after deadline slack hits zero will not save the deadline.

Scale-in should:

- Stop picking up new tasks on workers marked for removal.
- Finish short tasks or checkpoint long tasks.
- Release leases/visibility timeouts cleanly.
- Flush committed outputs.
- Drain and terminate.
- Never delete workers holding unique unpersisted state.

Use cooldowns/hysteresis to avoid flapping when queue depth oscillates.

## 15. Checkpoints, retries, and interruptible compute

If batches run on spot/preemptible capacity, workers can be reclaimed. Safe resumability lowers cost without losing data.

The design should include:

- Stable task IDs.
- Input versions/checksums.
- Idempotency keys for side effects.
- Durable checkpoints external to the instance.
- Deterministic output keys or manifest commits.
- Leases/visibility timeouts and fencing if workers overlap.
- Retries with exponential backoff and jitter.
- Dead-letter queues for permanently failing tasks.
- Interruption handlers to stop accepting new tasks and checkpoint within notice windows.

Never rely solely on shutdown notices. Instances can vanish abruptly; periodic checkpoints and idempotency are the primary safety net.

### Choosing a checkpoint interval

Checkpointing too infrequently increases rework on failure; checkpointing too often adds I/O and storage overhead. Measure:

- Time to write a checkpoint.
- Time to restore.
- Expected lost work between checkpoints.
- Storage/transaction costs.
- Impact on batch throughput.

For partitioned batches, committing per partition can be simpler than continuous checkpoints mid-task. For long ML training or simulations, time-based or step-based checkpoints are often better suited.

## 16. Dependency limits and backpressure

Compute capacity cannot exceed dependency capacity without causing bottlenecks.

For example, 20 workers reading one database with 30 connections each can open up to 600 connections. If the database only supports 150 connections for batch work, adding workers causes timeouts, retries, and lower throughput.

Account for end-to-end capacity:

- Database connections and query throughput.
- Object storage request rates and bandwidth.
- Message broker partitions/consumer counts.
- API rate limits and quotas.
- NAT gateway/egress ports.
- Shared cache throughput.
- DNS resolver capacity.
- Cross-zone/region network bandwidth.

Measures:

- Cap concurrency in workers and functions.
- Enforce fleet-wide connection pool ceilings.
- Batch reads/writes instead of constant tiny requests.
- Apply backpressure based on dependency saturation.
- Use queues as buffers decoupling producer/consumer rates.
- Use retry budgets instead of synchronized retries.
- Separate stages so slow dependencies do not stall all compute.

### Pipeline capacity equals its tightest bottleneck

A pipeline may have 100 vCPUs while the database handles only 5,000 records/second. Actual throughput cannot exceed that database ceiling without changing queries, partitioning, or data access patterns.

Monitor per-stage throughput rather than looking solely at cluster-wide CPU utilization.

## 17. Benchmarking and load testing to finalize configurations

Formulas provide only a starting estimate. Actual benchmarks confirm performance and cost.

### Benchmark preparation

- Use data representative in both size and distribution.
- Include cold starts, image pulls, and data warm-up if present in production.
- Use identical code, runtime, and dependency versions.
- Record instance types, vCPUs, memory, disk, and networking.
- Run multiple trials across varying concurrency levels.
- Measure p50/p95 durations, throughput, errors, retries, and resource utilization.
- Calculate cost per successful batch.

### Test matrix

| Test | Variable changed | What to learn |
|---|---|---|
| Baseline | 1 reference worker/shape | Initial throughput and resource profile |
| Scale CPU | Fixed workers, vary vCPU/shape | Per-worker efficiency |
| Scale horizontal | Increase worker count | Parallel efficiency and coordination overhead |
| Scale memory | Increase RAM/heap | OOM/GC behavior and throughput |
| Storage | Vary IOPS/throughput/cache | I/O bottlenecks |
| Network | Vary locality/transfer concurrency | Network saturation and egress costs |
| Spot mix | Add interruptible capacity | Interruptions, retries, and cost per success |
| Deadline test | Run full batch during peak hours | p95 completion and buffer margin |
| Failure test | Kill workers mid-task | Checkpoints, retries, and data integrity |

### Controlled benchmarking procedure

1. Pick a baseline small enough yet capable of running the full pipeline.
2. Run with representative data and capture metrics.
3. Increase one variable at a time.
4. Identify the point where throughput gains fall behind cost increases.
5. Repeat to gather p50/p95 distributions.
6. Test dependency limits and interruptions.
7. Compare along the cost/deadline frontier.
8. Lock the configuration with buffer and reserve quotas.

Never compare two configurations across runs with differing inputs, cache states, or dependency loads without recording the differences.

## 18. Capacity budgeting per stage

Different stages may need different compute shapes. You do not have to run one monolithic pool for the entire pipeline.

ETL example:

| Stage | Characteristics | Appropriate capacity |
|---|---|---|
| Extract | High I/O requests, low CPU | Moderate workers, strong networking, bounded concurrency |
| Transform | High CPU/memory | Compute-optimized or memory-optimized per profile |
| Shuffle/join | High network and memory | Network throughput, memory, and partitioning strategy |
| Load | Database-bound | Fewer workers, batch writes, capped connection pools |
| Validate | Low CPU, sequential logic | Small workers or serverless tasks |

Scaling each stage by its own queue and bottleneck avoids over-provisioning CPUs on stages waiting on a database.

### Buffer capacity

Reserve headroom for:

- Worker failures or interruptions.
- Straggler partitions.
- Provisioning delays.
- Data volume growth.
- Fluctuating quotas/spot availability.
- Rising dependency latency.

Headroom is not always a fixed percentage. Derive it from historical variance and the cost of missing deadlines.

## 19. Cost optimization strategies

### Optimize algorithms before buying more compute

Reduce computation, avoid redundant data reads, push filters/aggregations down where appropriate, and minimize serialization and shuffling. An algorithmic improvement cutting CPU demand by 30% can be cheaper than adding workers.

### Optimize data locality

Place compute in the same region/zone as data when appropriate. Avoid unnecessary cross-region transfers. If workloads repeatedly read the same dataset, consider caching or staging in suitable storage.

### Optimize shape and utilization

- Benchmark price/throughput instead of hourly price alone.
- Avoid oversized workers running underutilized.
- Avoid too many tiny workers creating coordination overhead.
- Autoscale based on remaining work.
- Shut down capacity when queues empty.
- Pick batch sizes that reduce scheduling overhead.

### Optimize commitments

Use committed capacity for steady baselines, and on-demand or spot for bursts. Do not over-commit if batch volumes fluctuate seasonally or by event.

### Track cost per successful unit

Useful metrics:

- USD/batch.
- USD/million records.
- USD/GB transformed.
- USD/rendered minute.
- USD/training step or epoch.
- Cost of retries/interruptions.
- Cost of idle capacity.

Cost per successful unit lets you compare configurations fairly even when one finishes faster using more resources.

## 20. Capacity selection scenarios

### Scenario A: nightly report with a hard deadline

A batch aggregates data before business open. Inputs are stable, CPU-bound, and partitionable. The deadline is critical, though data does not need completing in minutes.

Strategy:

- Benchmark throughput per vCPU.
- Pick an on-demand baseline sufficient to meet the p95 deadline.
- Optionally use spot for retryable partitions.
- Keep on-demand fallback when deadline slack shrinks.
- Checkpoint per partition and validate manifests before publishing.

### Scenario B: large ETL with a tight budget

Multi-TB inputs, relatively wide deadline, retryable workload.

Strategy:

- Optimize filter pushdowns and data locality.
- Provision adequate storage/network throughput.
- Use broad spot pools across multiple instance families/zones.
- Cap concurrency to protect storage and databases.
- Checkpoint per partition, route failures to DLQ, and scale by queue depth.
- Measure cost per GB processed, not compute cost alone.

### Scenario C: media rendering with a tight deadline

Rendering jobs have independent tasks, though some frames are very heavy and outputs must commit cleanly.

Strategy:

- Benchmark by frame/scene type.
- Use GPUs if the pipeline genuinely accelerates on them.
- Split tasks into balanced segments.
- Keep stable capacity for work that cannot retry quickly.
- Use spot for segments with checkpoints or isolated outputs.
- Monitor stragglers and apply controlled speculative execution.

### Scenario D: event-driven batch with unpredictable volume

Daily job volume swings dramatically.

Strategy:

- Use queues as buffers.
- Autoscale by oldest message age and estimated remaining work.
- Keep a small baseline if low startup latency is required.
- Scale bursts with on-demand/spot per policy.
- Rate-limit dependencies.
- Set budget/max-concurrency caps and alert when slack drops.

### Scenario E: long, GPU-intensive ML training

Runs for hours, GPUs are costly, and interruptions lose progress without checkpoints.

Strategy:

- Benchmark GPU utilization and data loader throughput.
- Tune batch size, mixed precision, and input pipelines where appropriate.
- Persist model, optimizer, scheduler, and RNG states.
- Checkpoint by time or step count.
- Use stable capacity for critical deadlines; spot for resumable runs.
- Account for idle GPU costs when CPU data pipelines cannot feed data fast enough.

## 21. Capacity decision workflow

Follow this sequential workflow:

1. **Lock deadlines:** define start time, deadline, and time reserved for queue/provision/commit/buffer.
2. **Lock budgets:** hard caps, target costs, and ancillary expenses.
3. **Profile workloads:** input volumes, CPU, memory, I/O, network, dependencies, and task distributions.
4. **Identify bottlenecks:** CPU, memory, storage, network, GPU, or dependencies.
5. **Decompose workloads:** partitions, stages, checkpoints, and idempotency.
6. **Build baselines:** benchmark on a simple configuration.
7. **Estimate capacity:** calculate workers/vCPUs and verify quotas.
8. **Benchmark shapes:** measure throughput, p95, and cost.
9. **Select capacity mix:** stable baseline, bursts, spot/fallback.
10. **Configure autoscaling:** queue/deadline-aware, concurrency caps, and cooldowns.
11. **Test failures:** worker loss, interruptions, dependency throttling, and retries.
12. **Monitor production:** deadline misses, cost per success, retries, saturation, and adjust.

### Decision matrix

| If priority is | Direction to choose |
|---|---|
| Strict hard deadline | Stable capacity, headroom, quotas/reservations, and fallback |
| Hard budget, flexible deadline | Spot/interruptible, queues, checkpoints, and autoscaling |
| Volatile workload | Small baseline + burst capacity |
| CPU-bound | Compute-optimized after benchmarking |
| Memory-bound | Memory-optimized and working-set controls |
| I/O-bound | Storage throughput, caching, and data locality |
| Dependency-bound | Cap workers/concurrency, optimize dependencies |
| Long jobs, hard to rerun | Stable capacity and frequent checkpoints |
| Small, idempotent tasks | Broad spot pools and controlled retries |

## 22. Operations, observability, and alerting

Capacity plans must be continuously reconciled against production outcomes.

### Metrics to monitor

**Deadlines and throughput**

- Batch start/end times.
- End-to-end duration and execution duration.
- Queue wait and provisioning times.
- Records/GB/tasks processed per second.
- Remaining work and deadline slack.
- p50/p90/p95/p99 completion durations.
- Deadline success rate.

**Compute**

- vCPU utilization, CPU throttling, and run queues.
- Memory peaks, OOMs, page faults, and GC.
- GPU utilization, VRAM, and accelerator idle time.
- Disk throughput, IOPS, latency, and disk pressure.
- Network throughput, packet drops, and retransmissions.

**Reliability**

- Worker failures/interruptions.
- Retry counts, task attempts, and duplicate suppressions.
- Checkpoint duration/restore time.
- DLQ depth and oldest task age.
- Dependency timeouts/throttling.
- Partition stragglers and speculative task counts.

**Cost**

- Compute cost per batch.
- Storage/network/managed-service costs.
- Idle worker time.
- Retry/wasted compute.
- Cost per successful record/GB/task.
- Forecasted cost vs. budget.

### Useful alerts

- Deadline slack drops below safe thresholds.
- Projected completion exceeds deadline.
- Queue age grows continuously.
- Slow worker startup or provisioning.
- Rising retry/interruption rates.
- Database connections approaching quota.
- Storage/network saturation.
- Cost forecast exceeds budget.
- Spot capacity drops while fallback is insufficient.

Alerts should tie to concrete actions: add workers, switch to fallback, reduce concurrency, pause producers, or notify owners. Avoid alerting solely on high CPU if high CPU is the desired steady state and the batch is progressing on schedule.

## 23. Common mistakes

**Dividing the deadline by worker count to estimate duration.** Ignores startup, commits, parallel efficiency, task skew, and dependencies. Measure end-to-end throughput instead.

**Counting compute prices only.** Storage requests, network egress, NAT, logs, retries, and idle capacity can raise total cost substantially.

**Adding workers when the database is saturated.** Generates extra connections and retries without increasing throughput. Cap concurrency and optimize dependencies first.

**Committing to deadlines using averages.** Tail tasks and capacity variance can cause missed deadlines. Track p95/p99 and add buffers.

**Running entire uncheckpointed workloads on spot.** Interruptions can wipe out hours of progress. Use spot only when jobs can retry or have solid fallback.

**Picking instances by vCPU while ignoring memory/network.** Workers can run low CPU yet OOM or stall on I/O. Benchmark the full resource profile.

**Partitions too large or too small.** Large partitions make retries expensive; tiny partitions create scheduling and metadata overhead. Benchmark to choose granularity.

**Scaling out too late.** If provisioning takes 5 minutes and deadline slack is only 2 minutes, adding workers cannot rescue the batch. Forecast remaining work early.

**Ignoring quotas and capacity availability.** Autoscalers may request workers while the cloud cannot provision enough instances/accelerators. Verify quotas and fallback before run time.

**Omitting output validation duration.** Compute finishing before data is committed or verified does not equal a successful batch.

**Not measuring cost per successful batch.** A cheap configuration with heavy retries can cost more than a stable configuration.

## 24. Batch capacity selection checklist

### Deadlines and budgets

- [ ] End-to-end deadline is clearly defined.
- [ ] Queue, provisioning, startup, commit, validation, and buffer times are subtracted.
- [ ] Whether the budget is a hard cap or target is defined.
- [ ] Compute, storage, network, managed service, logging, and retry costs are included.
- [ ] Criteria exist for resolving deadline vs. budget conflicts.

### Workload profile

- [ ] Input volume, size, and data distribution are measured.
- [ ] CPU time and wall-clock time are distinguished.
- [ ] Peak/working-set memory is measured.
- [ ] Storage IOPS/throughput and network throughput are measured.
- [ ] Dependency quotas and connection limits are identified.
- [ ] Task skew and sequential portions are identified.

### Capacity and architecture

- [ ] Primary bottleneck is identified.
- [ ] Worker shapes and worker counts are benchmarked.
- [ ] Parallel efficiency estimate exists.
- [ ] Partition size and checkpoint interval are appropriate.
- [ ] VM/container/serverless/managed batch are compared across lifecycles.
- [ ] Quotas, accelerators, and capacity reservations are verified.
- [ ] Headroom or fallback aligned with deadlines exists.

### Cost and reliability

- [ ] Cost per successful batch/unit is calculated.
- [ ] Spot/interruptible is used only for retryable tasks.
- [ ] Idempotency, checkpoints, and DLQs are tested.
- [ ] Autoscaling accounts for queue depth, remaining work, and deadline slack.
- [ ] Retries/backoff do not trigger retry storms.
- [ ] Dependencies have backpressure and concurrency caps.

### Operations

- [ ] Dashboards cover deadlines, throughput, resources, and cost.
- [ ] Alerts exist for deadline slack and budget forecasts.
- [ ] Tested under representative load and p95/p99 targets.
- [ ] Tested worker failures/interruptions.
- [ ] Runbooks exist for shifting capacity/fallback.
- [ ] Estimates vs. actuals are compared after runs and models updated.

## 25. Self-check

1. Why must a batch deadline subtract queue, provisioning, startup, commit, and validation times?
2. Distinguish CPU time from wall-clock time and explain when each metric is useful.
3. With 12 core-hours of total CPU demand, a 1-hour execution window, 75% target utilization, and 80% parallel efficiency, roughly how many vCPUs are needed?
4. Why does adding workers not always speed up a batch linearly?
5. Which parallelization limit does Amdahl's Law help identify?
6. When should you pick compute-optimized, memory-optimized, or GPU instances?
7. Why do hard-deadline batches typically need stable capacity or fallback alongside spot?
8. What expenses besides hourly VM pricing belong in a cost model?
9. How can queue depth and deadline slack work together to drive autoscaling?
10. Why is p95 completion duration more useful than averages when committing to deadlines?
11. If throughput fails to rise when adding workers, which dependencies and bottlenecks should be checked?
12. Build a capacity plan for a 5-million-record batch that must finish within 45 minutes on a fixed budget, covering benchmarks, worker count, capacity mix, cost, and fallback.

Choosing batch capacity is an engineering decision grounded in measured data and real constraints. By decomposing deadlines, profiling workloads, estimating compute demand, benchmarking multiple shapes, and accounting for all costs, teams can select capacity that hits both deadlines and budgets. Capacity mixes, remaining-work autoscaling, checkpoints, and backpressure keep plans resilient as data volumes, prices, and capacity availability evolve.
# Choosing Batch Capacity Based on Deadlines and Budgets

## 1. Why balance deadlines and budgets?

Batch processing handles a set of work within a time window: end-of-day data aggregation, report generation, video transcoding, model training, invoicing, data synchronization, or test suites. Unlike interactive APIs, batches can usually be queued and run in the background. Still, they have deadlines: reports must be ready before business hours, data must finish processing before the next cycle, or results must complete before a business milestone.

Adding machines, CPUs, or GPUs usually shortens runtime, yet raises costs and can bottleneck storage, networks, databases, or quotas. Provisioning too little capacity saves money upfront, yet risks missing deadlines, piling up backlogs, and disrupting downstream work. Therefore, capacity planning must answer three questions together:

- How much work exists and what resources does each unit consume?
- How much capacity is needed to finish before the deadline with reasonable headroom?
- Does that capacity fit within budget and dependency limits?

The goal is not running fastest at any price. The goal is finishing on time at an appropriate cost, with plans ready when load spikes, workers fail, or capacity becomes unavailable.

In the **CLOUD_CORE_SERVICES_COMPUTE** module, this lesson connects VM, container, serverless, CPU, memory, networking, and accelerator choices to background processing, autoscaling, and operational cost optimization.

After this lesson, learners will be able to:

- Classify batches by deadline, priority, volume, and partitionability.
- Estimate CPU, RAM, GPU, storage, networking, and processing times.
- Calculate required worker capacity from throughput and available time.
- Distinguish scale-up, scale-out, parallelism, and scaling limits.
- Choose VMs, containers, managed batch services, or serverless appropriately.
- Budget for compute, storage, networking, retries, and reserves.
- Combine stable capacity with Spot/Preemptible capacity when workloads allow.
- Design queues, autoscaling, checkpointing, retries, and deadline monitoring.
- Evaluate cost per completed unit of work.

## 2. Defining batch requirements

### 2.1. Business deadlines vs. processing time

A deadline is the final cutoff when results must be ready. Distinguish deadlines from pure compute time. A batch may wait for inputs, wait for capacity, download data, initialize containers, process, write outputs, and validate results.

Time from batch submission to completion can be modeled as:

\[
T_{total}=T_{queue}+T_{provision}+T_{data}+T_{compute}+T_{finalize}
\]

Where:

- \(T_{queue}\): wait time in the queue or scheduler.
- \(T_{provision}\): time to provision VMs/nodes/containers/functions and initialize runtimes.
- \(T_{data}\): time to read inputs, load models, or sync data.
- \(T_{compute}\): core processing duration.
- \(T_{finalize}\): writing outputs, committing manifests, validating, and notifying results.

If the deadline is \(D\), actual time available for compute is only:

\[
T_{compute,budget}=D-T_{queue}-T_{provision}-T_{data}-T_{finalize}-T_{reserve}
\]

\(T_{reserve}\) is headroom for variance and failures. If the result is negative or tiny, the current capacity setup cannot meet the deadline; reduce overhead, change processing strategies, increase budget, or renegotiate the deadline.

### 2.2. Hard deadlines vs. soft deadlines

| Deadline type | Meaning | Capacity strategy |
|---|---|---|
| Hard | Missing the deadline violates business, contractual, or regulatory commitments | Keep reserve capacity, high priority, control dependencies, and maintain fallback |
| Soft | Can slip within acceptable limits | Queue up, leverage cheaper capacity, scale elastically with backlog |
| Windowed | Must complete within a recurring window, e.g., overnight | Schedule by hour, avoid contention with other workloads |
| Freshness-based | Data must not exceed a staleness threshold | Monitor backlog age and data timestamps, not just job duration |

A single batch can have multiple milestones: inputs must arrive before 01:00, processing must finish before 05:00, and reports must publish before 06:00. Define deadlines for every phase to avoid spending the entire window on compute.

### 2.3. Prioritizing and classifying work

Not every task in a batch carries the same priority. Tasks can be classified as:

- Critical: must finish before a hard deadline.
- High: directly impacts users or downstream systems.
- Normal: should finish on schedule, can tolerate minor delays.
- Best-effort: can wait for cheap capacity or run during off-peak hours.

Schedulers should support priorities, deadlines, fairness, and per-group resource limits. If all jobs share one queue at equal priority, giant jobs can block small or critical workloads.

### 2.4. Quantifying workload volume

Record:

- Counts of records, files, messages, partitions, or tasks.
- Input and output sizes.
- Average, p95, and p99 processing time per unit.
- Task failure, retry, and rerun rates.
- Parallelism level and inter-task dependencies.
- Resources needed per worker: vCPU, RAM, GPU, disk, and network.
- Batch frequency and data growth trends.

Do not rely solely on average times when task distributions are skewed. A few massive files or tough partitions can become stragglers dictating when the batch actually finishes.

### 2.5. Distinguishing independent batches vs. dependency-driven batches

Batches made of independent tasks distribute easily across workers. Batches with dependencies must execute as a DAG: one step must finish before another starts, or multiple branches must converge before publishing results.

With DAGs, overall batch deadlines depend on the critical path, not the sum of all task durations. Account for inter-step wait times, synchronization, and barriers.

## 3. Measuring the workload's resource profile

### 3.1. CPU-bound

CPU-bound workloads perform heavy computation with minimal I/O waits—such as compression, encryption, numerical analysis, compilation, or image processing. Adding vCPUs increases throughput if the application has enough parallelism and avoids memory bandwidth or lock contention limits.

Measure CPU utilization, CPU throttling, run queues, context switches, per-task duration, and throughput. Low CPU utilization may indicate workers are waiting on storage/networking rather than needing more CPU.

### 3.2. Memory-bound

Workloads like large dataframe processing, joins, sorts, or caching require substantial RAM. Insufficient RAM triggers swapping, OOMs, or disk spills, sharply inflating runtimes.

Measure peak resident memory, memory per task, page faults, swap, OOM events, and memory bandwidth if available. Scaling parallelism typically scales total RAM with concurrent task counts; do not size from one worker's average memory alone.

### 3.3. I/O-bound and network-bound

ETL, data copying, object processing, or multi-source queries can bottleneck on IOPS, storage throughput, network bandwidth, latency, or API quotas. Adding workers can pit more requests against one backend and lower aggregate throughput.

Measure read/write MB/s, IOPS, queue depth, network throughput, packet loss, connection counts, request latency, and throttling. Co-locate workers near data when possible to cut cross-zone/region transfers and latency.

### 3.4. GPUs and accelerators

ML, rendering, or simulation workloads may require GPUs/accelerators. Measure actual GPU busy time, VRAM, memory bandwidth, data loader throughput, interconnects, and CPU-to-GPU data copy times.

Low GPU utilization often stems from CPUs failing to feed data fast enough or slow storage. Adding GPUs in that situation raises cost without raising throughput.

### 3.5. Benchmarking on representative configurations

Benchmarks should use production-like data sizes and distributions. Test several concurrency levels and record:

- Completion throughput, not just started tasks.
- p50/p95/p99 durations and final task completion time.
- CPU, RAM, GPU, disk, and network utilization.
- Errors, retries, OOMs, and throttling.
- Compute and dependency costs over the exact measurement window.

Do not extrapolate linearly from a tiny test run if the workload involves caches, shuffles, locks, quotas, or shared bottlenecks.

## 4. Estimating capacity from throughput

### 4.1. Simple throughput model

Let:

- \(Q\): number of work units to complete.
- \(r_w\): measured throughput of one worker in the chosen shape, in tasks/second.
- \(N\): number of concurrent workers.
- \(\eta\): composite scaling efficiency, reflecting parallel overhead and contention.
- \(T\): available compute time.

Approximate capacity:

\[
Q_{capacity}=N\times r_w\times \eta\times T
\]

To finish the batch:

\[
N_{required}=\left\lceil\frac{Q}{r_w\times\eta\times T}\right\rceil
\]

\(\eta\) should be measured from benchmarks at the target parallelism level. Never default it to 1; orchestration overhead, shuffling, networking, and locking reduce efficiency as worker counts grow.

### 4.2. CPU-seconds model

Given estimated total CPU demand \(W_{cpu}\) vCPU-seconds, \(V\) vCPUs per worker, target utilization \(u\), parallel efficiency \(\eta\), and available compute time \(T\) seconds:

\[
N_{required}=\left\lceil\frac{W_{cpu}}{V\times u\times\eta\times T}\right\rceil
\]

This model suits CPU-bound workloads with reliably measured CPU demand. For I/O-bound, memory-bound, or GPU-bound workloads, budget each respective resource separately and use the most constrained capacity limit.

### 4.3. Worker count calculation example

A batch has 24,000 tasks. Benchmarks show each task consumes an average of 30 vCPU-seconds. Total demand:

\[
W_{cpu}=24,000\times30=720,000\text{ vCPU-seconds}
\]

Deadline is 2 hours. Reserve 10 minutes for provisioning, data loading, finalization, and buffer, leaving 110 minutes of compute time, or 6,600 seconds. Each worker has 4 vCPUs; target utilization is 70%; estimated parallel efficiency is 80%.

\[
N_{required}=\left\lceil\frac{720,000}{4\times0.70\times0.80\times6,600}\right\rceil=49
\]

Roughly 49 workers are needed under this model. This is a starting point for testing; verify memory, I/O, networking, quotas, and task distributions. If the 24,000 tasks include a few very long jobs, add capacity or split partitions to avoid stragglers.

### 4.4. Sizing capacity under continuous new arrivals

If a batch receives additional tasks while processing, let \(\lambda\) be task arrival rate and \(\mu\) be total pool completion rate. Backlogs shrink only when:

\[
\mu>\lambda
\]

If current backlog is \(B\) tasks, approximate drain time under steady rates is:

\[
T_{drain}=\frac{B}{\mu-\lambda}
\]

If \(\mu\leq\lambda\), the queue cannot drain sustainably. Add capacity, throttle intake rates, or adjust schedules/priorities.

### 4.5. Handling uneven tasks and stragglers

A batch may finish almost completely while a few tail tasks drag on much longer. Use balanced partitions, dynamic work stealing, speculative execution, or split large tasks. Note that speculative execution duplicates work, raising cost and requiring idempotent outputs.

Monitor final task times, partition size skew, and per-worker throughput. If 95% of tasks finish early while the last 5% drag on, adding workers likely will not help unless those tasks can be split smaller.

## 5. Parallelism and scaling efficiency

### 5.1. Splitting work into parallel units

Common forms of parallelism:

- Data parallelism: split data into independent partitions.
- Task parallelism: run different steps simultaneously.
- Pipeline parallelism: run different stages concurrently on different slices of data.
- Model/compute parallelism: split calculations or models across multiple CPUs/GPUs.

Choose decomposition based on data structure and dependencies. Overly small partitions inflate scheduling overhead; overly large ones hurt load balancing and raise rework on failure.

### 5.2. Amdahl's Law

Amdahl's Law describes speedup limits when only part of the work can run in parallel. If the sequential fraction is \(s\) and worker count is \(N\), ideal speedup is approximately:

\[
S(N)=\frac{1}{s+\frac{1-s}{N}}
\]

If 10% of work is strictly sequential, even infinite workers yield at most a 10x speedup. Real-world coordination, synchronization, and I/O overhead push actual speedup lower.

### 5.3. Scale-up vs. scale-out

**Scale-up** increases resources on a single worker, e.g., from 4 to 16 vCPUs or adding RAM. Useful when single tasks need large memory, have substantial sequential logic, or resist distribution.

**Scale-out** increases worker count to process more partitions in parallel. Suits independent tasks, though bounded by parallelism, dependencies, and network/storage limits.

Both can be combined: size workers large enough to run individual tasks efficiently, then scale out across independent tasks. Never assume bigger or more workers is automatically better.

### 5.4. Identifying saturation points

Increase workers incrementally and observe throughput. If doubling workers from 16 to 32 barely lifts throughput while latency, I/O, or errors climb, the system has likely saturated a dependency or sequential bottleneck.

Set operating points below saturation to preserve headroom. Rely on representative benchmarks and production load rather than treating peak short-test throughput as sustainable capacity.

### 5.5. Synchronization and communication costs

Distributed batches require data transfers, shuffles, barriers, or result aggregation. Network and serialization overhead can outweigh compute savings. Group data into sensible partitions, compress where beneficial, and minimize worker-to-worker chatter.

For multi-node GPUs, inspect interconnects and topology. Adding nodes across slow interconnects can lengthen total runtime.

## 6. Capacity budgeting

### 6.1. Compute budgets

Compute cost depends on worker count, shape, runtime, and pricing tier. Simple model:

\[
C_{compute}=N\times P_{worker-hour}\times H
\]

Where \(P_{worker-hour}\) is hourly worker price and \(H\) is runtime hours. If workers span multiple shapes or regional/tier prices, compute each group separately and sum them.

With autoscaling, compute from actual capacity-time:

\[
C_{compute}=\sum_{i=1}^{k}N_i\times P_i\times H_i
\]

### 6.2. Total batch cost

Compute is only one slice. Total cost may include:

\[
C_{total}=C_{compute}+C_{storage}+C_{network}+C_{orchestration}+C_{retry}+C_{observability}
\]

Where:

- Storage: inputs, outputs, checkpoints, temporary data, and snapshots.
- Network: data transfers, cross-zone/region traffic, NAT, or egress.
- Orchestration: schedulers, control planes, queues, and managed service fees.
- Retry: re-executed compute, dependency calls, and intermediate storage.
- Observability: logs, metrics, traces, and retention.

Include costs of temporary data retained after batch completion and standby capacity held during wait windows.

### 6.3. Calculating maximum workers from budget

If remaining compute budget is \(B_c\), hourly price per worker is \(P\), and expected duration is \(H\), maximum workers within budget is:

\[
N_{budget}=\left\lfloor\frac{B_c}{P\times H}\right\rfloor
\]

If \(N_{required}>N_{budget}\), the plan cannot satisfy both deadline and budget under current assumptions. Reduce resource costs, optimize algorithms, raise efficiency, use cheaper capacity, split batches across windows, or adjust the deadline. Never quietly under-provision capacity and let batches miss deadlines.

### 6.4. Cost example

Suppose 49 workers are needed at an illustrative \$0.20 USD/hour running for 110 minutes:

\[
C_{compute}=49\times0.20\times\frac{110}{60}\approx17.97\text{ USD}
\]

If storage, networking, queues, and observability add an estimated \$8 USD, projected total is ~\$25.97 USD. Add reserves for retries and variance if budgets require high predictability.

\$0.20 USD/hour is illustrative only, not a cloud quote. Real planning must use exact regional, instance type, OS, license, and commitment pricing at execution time.

### 6.5. Cost per completed unit

To compare configurations, use:

\[
C_{unit}=\frac{C_{total}}{Q_{completed}}
\]

For instance, cost per million records, per video, per partition, or per training run. Cheaper workers that run longer, retry heavily, or miss deadlines can yield a higher cost per completed unit.

### 6.6. Budgets and deadlines form a feasible region

Capacity must be large enough to meet the deadline without exceeding the budget. Visualize three zones:

- Below minimum capacity: batch misses the deadline.
- Inside the feasible region: batch meets the deadline within budget.
- Above needed capacity: deadline improves little while costs rise.

The goal is picking the lowest point inside the feasible region that maintains adequate headroom and acceptable risk.

## 7. Choosing compute types for batches

### 7.1. VMs and instance groups

VMs fit batches needing OS control, native binaries, GPU drivers, local disks, or specialized networking. Instance groups/autoscaling groups can scale machines by queue or schedule.

Pros:

- Full control over CPU/RAM shapes, accelerators, and OS.
- Fits long jobs or software needing customized environments.
- Can use Spot/Preemptible capacity to cut costs if interruptible.

Factors to calculate:

- Boot time, agent setup, and data loading.
- Capacity quotas, zonal availability, and image maintenance.
- Idle time before jobs arrive or after completion.
- Draining, checkpointing, and replacing failed VMs.

### 7.2. Containers and Kubernetes Jobs

Containers package applications/runtimes consistently; Kubernetes Jobs manage completion counts and parallel Pods. Well-suited to multi-task batches needing resource requests/limits, diverse node pools, or queue/scheduler integration.

Pros:

- Declare CPU/RAM/GPU and parallelism per workload.
- Target dedicated node pools for high-memory, GPU, or Spot.
- Reuse cluster images, policies, and telemetry.

Factors to calculate:

- Image pull, scheduling, and node scale-out times.
- Pending Pods due to resource exhaustion, taints, or quotas.
- Idle cluster/node and control plane costs.
- Job retries, `backoffLimit`, `activeDeadlineSeconds`, and ephemeral storage.

Example Kubernetes Job:

```yaml
apiVersion: batch/v1
kind: Job
metadata:
  name: nightly-etl
spec:
  completions: 24000
  parallelism: 49
  backoffLimit: 3
  activeDeadlineSeconds: 6600
  ttlSecondsAfterFinished: 86400
  template:
    spec:
      restartPolicy: Never
      containers:
        - name: etl
          image: registry.example.com/data/etl@sha256:0123456789abcdef...
          resources:
            requests:
              cpu: "4"
              memory: "8Gi"
            limits:
              cpu: "4"
              memory: "8Gi"
```

Illustrative manifest. `completions: 24000` and `parallelism: 49` fit when each Pod processes one completion unit; if a Pod handles multiple partitions, adjust accordingly. `activeDeadlineSeconds` applies to active Job duration per Kubernetes semantics, not individual Pod duration. Add provisioning and finalization times to overall orchestration deadlines.

### 7.3. Managed batch services

Managed batch services supply queues, schedulers, compute environments, job definitions, retries, and capacity allocation. Ideal when focusing on job logic rather than building schedulers and lifecycles yourself.

Check:

- Supported instance/accelerator types and regions.
- Maximum vCPUs, quotas, and allocation strategies.
- Job priorities, dependencies, retries, and timeout semantics.
- Spot/On-Demand mixes and fallback.
- Orchestration, storage, log, and network fees.
- How to detect stuck, failed, or deadline-exceeded jobs.

### 7.4. Serverless functions and workflows

Serverless fits short, event-driven, granular tasks that do not need long-lived workers. Workflow orchestration coordinates multi-step execution and retries via state machines.

Pros include zero infrastructure management and per-invocation scaling. Limitations may include max execution duration, concurrency quotas, cold starts, ephemeral storage limits, payload caps, and invocation costs under heavy retries.

If a batch involves long tasks or huge data, split into small functions, use queues, or offload heavy compute to containers/VMs.

### 7.5. Quick selection table

| Requirement | Usually suitable option | Points to check |
|---|---|---|
| Short, event-driven tasks | Serverless functions | Max duration, concurrency, retries, and request pricing |
| Many independent container tasks | Kubernetes Job or managed batch | Scheduling, node capacity, image pulls, and parallelism |
| Long jobs, custom drivers/native libs | VMs/instance groups | Boot times, images, quotas, and lifecycle |
| GPU training/rendering | GPU VMs, GPU node pools, or managed batch | VRAM, drivers, interconnects, and checkpoints |
| Volatile, interruption-tolerant workloads | Spot/Preemptible pool + stable capacity | Interruptions, retries, checkpoints, and fallback |
| Multi-step dependent pipelines | Workflow orchestration + queues/compute | State, deadlines, retries, and idempotency |

## 8. Combining stable and flexible capacity

### 8.1. Stable baseline

For hard-deadline batches, hold a slice of stable capacity to guarantee minimum progress. Use Spot/Preemptible or flexible capacity for extra throughput when available.

Never treat pricing-discount commitments as capacity reservations if the product only commits pricing. Count capacity as reserved only when specific service terms guarantee allocation.

### 8.2. Splitting by priority

For example, a batch with two tiers:

- Critical partitions: run on stable capacity to guarantee baseline deliverables.
- Flexible partitions: run on Spot or cheaper capacity; retryable if reclaimed.

Schedulers should cap how many flexible jobs can fall back onto stable capacity so critical workloads are not overwhelmed.

### 8.3. Handling interruptions

For Spot/Preemptible workers:

- Persist checkpoints and intermediate results off-instance.
- Use stable task IDs and idempotent outputs.
- On interruption notice, stop taking new tasks and checkpoint if time permits.
- On abrupt loss, leases/heartbeats detect dead workers and queues re-dispatch tasks.
- Diversify instance types and zones to improve capacity availability.

Never depend solely on interruption notices; workers can vanish without enough time for graceful shutdown.

### 8.4. When flexible capacity is unavailable

Wait in queue, slow job intake, shift a slice to stable pools if budget allows, or adjust deadlines. Avoid tight loops constantly requesting unavailable capacity when quotas or stock are exhausted.

### 8.5. Cost comparison accounting for interruptions

Total cost of flexible capacity must include:

- Reworked computation.
- Checkpointing and storage operations.
- Time waiting for replacement capacity.
- Stable fallback during Spot shortages.
- Orchestration and interruption monitoring overhead.

A low hourly rate does not guarantee a low cost per completed task.

## 9. Queues, schedulers, and autoscaling

### 9.1. Queues as buffers

Queues decouple job intake from execution. They absorb bursts and let schedulers dispatch tasks by priority, deadline, or resource requirements.

Queues need capacity caps, retention, dead-letter policies, and message age metrics. If producers enqueue faster than capacity processes over sustained periods, backlogs grow and deadlines slip.

### 9.2. Scaling by backlog and deadline

Queue depth only shows pending item counts. Predicting deadlines requires knowing current throughput, remaining time, and new arrival rates.

Useful metrics:

- Queue depth and oldest task age.
- Arrival rate and completion rate.
- Estimated work remaining (CPU/GPU seconds or task-seconds).
- Deadline slack of near-due jobs.
- Worker utilization and startup lag.
- Dependency saturation and retry rates.

Autoscalers should add capacity when estimated work remaining exceeds processing capacity in the remaining window. When dependencies saturate, adding workers may not help; reduce concurrency or resolve the bottleneck.

### 9.3. Estimating drain time

With backlog \(B\), current throughput \(\mu\) tasks/second, and arrival rate \(\lambda\), approximate drain time is \(B/(\mu-\lambda)\) when \(\mu>\lambda\). Use throughput measured under current load, not idealized single-worker benchmark numbers.

### 9.4. Bounded scale-out

Set `max workers` based on:

- Deadlines and target throughput.
- Database connection budgets and API rate limits.
- Storage/network capacity.
- CPU/RAM/GPU quotas and node capacities.
- Cost budgets.
- Available parallelizable tasks.

If the autoscaler hits max workers while the queue keeps growing, alert early and follow runbooks: request approved quota increases, trim inputs, prioritize critical jobs, or adjust deadlines.

### 9.5. Scale-in and batch teardown

As queues shrink, scale workers down in steps to avoid oscillation. Before terminating workers, stop accepting new tasks, finish or checkpoint active tasks, and flush results. Verify outputs are committed before deleting temporary resources.

After the batch, reclaim unneeded capacity while retaining logs, metrics, manifests, and artifacts per retention policy. Never delete checkpoints before confirming the batch completed and is recoverable.

## 10. Designing tasks for efficient capacity use

### 10.1. Choosing partition size

Overly small partitions create scheduler, network, and metadata overhead; overly large ones cut parallelism and increase rework. Benchmark several sizes to find the sweet spot.

A practical rule of thumb: tasks should be long enough that compute far outweighs startup/dispatch overhead, yet short enough that a single failure does not forfeit excessive progress.

### 10.2. Idempotency and output commits

Workers can retry after timeouts or interruptions. Give every task a stable ID and safely repeatable output commits. Write outputs to temporary locations, verify checksums, then atomically update manifests/commit markers. Prevent two workers from overwriting the same output uncoordinated.

### 10.3. Checkpointing

For long tasks, save periodic checkpoints to durable storage. Pick intervals balancing write overhead against potential lost compute. Checkpoints need versions, checksums, and code/input metadata to prevent resuming under incompatible versions.

### 10.4. Retries and dead-lettering

Separate transient errors, data errors, and code bugs. Retry transient failures with backoff and jitter; route poison tasks to a dead-letter queue after bounded attempts. Never retry forever—it wastes money and blocks queue draining.

### 10.5. Handling stragglers

Watch for tasks lagging far behind the median. Split large tasks, rebalance partitions, or apply speculative execution for idempotent work. Enable speculative execution only when duplicate compute costs less than the value of cutting tail latency.

## 11. Managing resources and dependencies

### 11.1. RAM and concurrency

If each task uses \(M_t\) RAM and a worker has \(M_w\) RAM, approximate memory-bound max concurrent tasks is:

\[
K_{memory}=\left\lfloor\frac{M_w-M_{reserve}}{M_t}\right\rfloor
\]

Where \(M_{reserve}\) covers runtime, caches, agents, and overhead. Actual concurrency must respect the tightest bound across CPU, RAM, GPU, I/O, and dependencies.

### 11.2. Databases and connection pools

Batch workers can open huge numbers of connections when scaling out. With \(N\) workers each holding a max pool of \(P\), potential connections reach \(N\times P\). Cap workers against database connection budgets and co-resident workloads.

Shrinking pools or adding connection proxies helps manage connections, though it cannot make a database execute more queries than its real capacity. Monitor pool wait times, query latency, locks, and throughput.

### 11.3. API quotas and rate limits

If each task calls external APIs, sum requests across task counts, calls per task, and retries. Use shared token buckets or rate limiters so aggregate traffic stays within quotas. Respect `Retry-After`, backoff, and retry budgets.

### 11.4. Storage and networking

Measure read/write throughput, IOPS, network transfers, and egress costs. Shuffle-heavy batches can saturate networks; writing outputs to distant regions adds latency and fees. Place workers near data and choose fitting formats/partitions.

### 11.5. GPUs and accelerators

GPU workers can be expensive and scarce. Ensure batches supply enough tasks to saturate GPUs, data loaders do not starve accelerators, and checkpointing does not eat too much runtime. Consider stable GPUs for hard deadlines and Spot GPUs for checkpointed runs.

## 12. Deadline headroom and risk management

### 12.1. Headroom

Never plan right on the razor's edge of average throughput. Leave headroom for input spikes, long tasks, node failures, retries, provisioning delays, and dependency slowdowns. Base headroom on historical variance and acceptable risk.

### 12.2. Percentiles instead of averages alone

For strict deadlines, use p95/p99 task durations and throughput rather than averages alone. Test peak-volume days, slow dependencies, and constrained capacity regions.

### 12.3. Failure scenarios

Simulate:

- Partial worker failures or Spot reclamations.
- Node pools failing to scale due to quotas or IP exhaustion.
- Slow databases or connection exhaustion.
- Object storage throttling.
- Large partitions turning into stragglers.
- Temporary scheduler or queue disruptions.
- Retry storms inflating backlogs.

Verify whether the batch still meets its deadline or degrades gracefully by priority. If not, revise baselines, deadlines, or business workflows.

### 12.4. Competing batches

When multiple batches run concurrently, total capacity cannot be planned in isolation. Enforce per-queue/tenant quotas, priorities, fairness, and fleet-wide worker caps. Prevent low-priority batches from starving critical batches near their deadlines of GPUs, databases, or bandwidth.

## 13. Complete planning example

### 13.1. Context

A system processes 24,000 data partitions every night. The deadline window is 02:00–04:00 (2 hours). The batch needs 10 minutes for initialization, metadata loading, finalization, and publishing; add 10 minutes reserve. Benchmarks measure 30 vCPU-seconds per partition. Workers have 4 vCPUs; target utilization is 70%; scaling efficiency is 80%.

### 13.2. Capacity calculation

Available compute time:

\[
T=120-10-10=100\text{ minutes}=6,000\text{ seconds}
\]

Total CPU demand:

\[
W=24,000\times30=720,000\text{ vCPU-seconds}
\]

Worker count:

\[
N=\left\lceil\frac{720,000}{4\times0.70\times0.80\times6,000}\right\rceil=54
\]

Initial plan needs roughly 54 workers of 4 vCPUs during the compute window. Next, load-test 54 workers to verify throughput, memory, storage, and database behavior; if actual efficiency falls below 80%, recalculate.

### 13.3. Budget calculation

Assume an illustrative rate of \$0.20 USD per worker-hour. Compute cost:

\[
C=54\times0.20\times\frac{100}{60}=18\text{ USD}
\]

With a \$20 USD compute budget, \$2 USD headroom remains for extra capacity; storage, networking, and orchestration must come from separate budgets or be deducted before sizing workers. If the entire batch budget is \$20 USD all-in, subtract ancillary costs before calculating worker capacity.

### 13.4. Capacity plan

- Hold 20 stable workers to guarantee baseline progress.
- Scale up to 34 additional Spot workers when capacity permits.
- Route critical jobs to stable workers first; run flexible partitions on Spot.
- When Spot is reclaimed, queues retain remaining tasks; the scheduler falls back partially onto stable capacity only within budget/headroom limits.
- Monitor queue age, estimated work remaining, and deadline slack.

This plan holds only if 20 stable workers satisfy minimum deliverables or flexible work can slip its deadline. If all 24,000 partitions must strictly finish within 2 hours even during a total Spot outage, the stable baseline must cover that full scenario.

### 13.5. After the first run

Compare projections against actuals: provisioning lag, throughput, p95/p99 task durations, retries, interruptions, cost, and publish times. Update the capacity model with observed numbers rather than keeping initial assumptions.

## 14. Common mistakes

- **Sizing capacity from average CPU:** ignores RAM, I/O, networking, and GPUs.
- **Spending the entire deadline on compute:** forgets queues, provisioning, data transfers, and finalization.
- **Assuming linear throughput scaling:** ignores sequential steps, synchronization, and bottlenecks.
- **Ignoring tail tasks:** stragglers make batches late even when most tasks finish early.
- **Oversized workers:** wastes resources if tasks cannot exploit internal parallelism.
- **Too many workers:** triggers contention on databases, storage, networks, or API quotas.
- **Counting only compute costs:** forgets storage, egress, retries, orchestration, and observability.
- **Treating Spot availability as guaranteed:** capacity can vanish or be reclaimed.
- **No stable fallback:** critical batches miss deadlines during Spot shortages.
- **No checkpoints/idempotency:** retries lose progress or create duplicate outputs.
- **Scaling on raw queue depth alone:** ignores deadlines, throughput, and dependency saturation.
- **No budget guardrails:** autoscalers run up unexpected bills.
- **Not benchmarking representative data:** misestimates when real inputs grow or skew.
- **Never updating models:** traffic and runtimes drift while capacity plans stagnate.

## 15. Batch capacity selection checklist

### Requirements and workloads

- [ ] Business deadlines, run windows, and priorities are defined.
- [ ] Task counts, input/output sizes, and duration distributions are measured.
- [ ] Independent tasks, DAG dependencies, and parallelizable slices are identified.
- [ ] CPU, RAM, GPU, storage, and network bottlenecks are classified.
- [ ] Benchmarked on representative data with p50/p95/p99 recorded.

### Capacity and scheduling

- [ ] Queue, provisioning, data transfer, finalization, and reserves are subtracted from deadlines.
- [ ] Worker count is calculated from throughput or resource demand.
- [ ] Parallel efficiency and saturation points are verified.
- [ ] Workers are sized for RAM, GPU, IOPS, networking, and dependency quotas.
- [ ] Priorities, queues, retries, checkpoints, and idempotency are configured.
- [ ] Stable baseline and Spot/Preemptible criteria are defined.

### Budgets

- [ ] Compute, storage, networking, orchestration, retries, and observability are budgeted.
- [ ] Pricing matches actual regions, instance types, and billing models.
- [ ] Cost per completed unit is calculated.
- [ ] Max workers, quotas, and budget alerts are set.
- [ ] Contingency plans exist when needed capacity exceeds budget.

### Operations

- [ ] Queue age, throughput, estimated work remaining, and deadline slack are monitored.
- [ ] Alerts trigger when worker pools hit max while backlogs still grow.
- [ ] Worker failures, interruptions, dependency throttling, and quota exhaustion are tested.
- [ ] Scale-in drains cleanly without deleting uncommitted outputs/checkpoints.
- [ ] Post-batch reports capture duration, cost, errors, and actual capacity.
- [ ] Models are updated periodically as volumes, code, or cloud pricing change.

## 16. Conclusion

Choosing batch capacity balances workload volume, available time, parallel efficiency, and budget. Start with business deadlines, then measure resource profiles and throughput on representative data. Subtract queue, provisioning, data loading, finalization, and reserve times before calculating worker counts. Use benchmarks to uncover parallel efficiency, saturation points, and straggler impacts.

Next, select VMs, containers, managed batch, or serverless based on task duration, runtime needs, and orchestration style. Sum total costs across compute, storage, networking, orchestration, retries, and observability, comparing options by cost per completed unit. To save money, pair a stable baseline with Spot/Preemptible capacity for interruptible tasks, backed by checkpoints, idempotency, and fallback.

Autoscaling should track backlogs, estimated remaining work, and deadline slack while respecting database, storage, network, quota, and budget limits. Reconciling actual metrics after each batch keeps the capacity model accurate so systems hit deadlines within predictable, controlled budgets.

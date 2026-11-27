# Evaluating Completion Time, Parallel Efficiency, and Cluster-Wide Cost

A High-Performance Computing (HPC) cluster may leverage tens or thousands of CPU cores, GPUs, large memory, and high-speed networking. However, high node or core counts do not automatically yield faster or cheaper results. As a cluster scales out, data exchange, synchronization, scheduler wait time, resource initialization, and non-parallelizable work can erode returns.

Evaluating HPC requires answering three questions simultaneously: how long does it take to obtain a valid result, how efficiently are parallel resources utilized, and what is the total cluster-wide cost? A strong configuration must hit deadlines and result quality at an appropriate cost—factoring in networking, storage, software, wait times, and idle capacity.

This lesson belongs to the **CLOUD_CORE_SERVICES_COMPUTE** module, **High-Performance Computing** chapter. It covers how to measure time-to-solution, speedup, strong/weak scaling, parallel efficiency, profiling, fair benchmarking, and cluster-wide cost modeling to select CPU/GPU configurations, node counts, interconnects, and runtime targets.

## 1. Cluster-Wide HPC Evaluation

An isolated benchmark can reveal how fast a kernel executes, but cannot capture the full end-to-end experience of an HPC workload. Users typically care about the span from submitting a job to receiving usable results.

Typical lifecycle stages:

1. Submit the job and wait for the scheduler to allocate resources.
2. Provision or boot nodes, containers, and runtimes.
3. Stage inputs from object/file storage to nodes.
4. Load data, initialize MPI/GPUs, and distribute processes.
5. Execute computation and data exchanges.
6. Checkpoint, write outputs, and synchronize results.
7. Run post-processing, validate correctness, and publish results.

~~~mermaid
flowchart LR
    A["Submit job"] --> B["Queue / scheduling"]
    B --> C["Provision cluster"]
    C --> D["Stage input"]
    D --> E["Initialize runtime"]
    E --> F["Parallel compute"]
    F --> G["Checkpoint / output"]
    G --> H["Validate result"]
    H --> I["Result available"]
~~~

Measuring only the compute step risks overlooking queue wait, provisioning, data staging, and post-processing. For short jobs, non-compute phases can make up a substantial share of total runtime.

### 1.1. Measurement Scope Must Match the Goal

| Goal | Appropriate measurement scope |
|---|---|
| Comparing algorithms | Compute-phase runtime under identical inputs and conditions |
| Comparing node counts | End-to-end runtime and compute time at each cluster scale |
| Evaluating an HPC service | Submit-to-result, including queueing, provisioning, and data movement |
| Evaluating cost | Billable duration across all involved resources and services |
| Checking deadlines | Completion time for valid results under realistic load |
| Checking serving capacity | Throughput or jobs completed within a time window |

Never mix different measurement scopes in the same comparison table. If reporting compute time, explicitly state that queue and provisioning times are excluded.

## 2. Time-to-Solution and Completion Time

Time-to-solution (TTS) is the elapsed time from a defined starting milestone until a valid, usable result is available. From a user perspective, the start milestone is typically job submission; the end milestone is when outputs are durably persisted and pass required validation.

~~~text
TTS =
  T_queue
  + T_provision
  + T_stage_in
  + T_initialize
  + T_compute
  + T_checkpoint_and_stage_out
  + T_validate
~~~

Depending on the workload, certain stages may overlap. Avoid mechanically summing parallel task durations; measure elapsed wall-clock time from start to end and use breakdowns for explanation.

### 2.1. Wall-Clock Time vs. CPU Time

- **Wall-clock time:** actual elapsed time from start to finish.
- **CPU time:** total time CPUs actively execute processes/threads.
- **GPU active time:** time GPUs spend running kernels or tracked device work.
- **Queue wait:** time a job waits for resources before starting.
- **Elapsed job time:** time a job spends in the `running` state per the scheduler; may include initialization, I/O, and cleanup.

An MPI job running 64 ranks for 10 minutes may consume nearly 640 rank-minutes of CPU time if ranks stay continuously active, yet wall-clock time remains around 10 minutes. CPU time and wall-clock time answer different questions.

### 2.2. Start and End Milestones

For fair comparisons, define upfront:

- Start: submission timestamp, allocation start, or main process launch.
- End: computation finished, output committed, or result validated.
- Is container/image pull time included?
- Are checkpointing and output writes included?
- Is queue wait time included?
- Are retries or post-failure restarts included?

For scientific problems, a result is only complete when it satisfies accuracy or error tolerances. A fast run producing wrong results is not a completed solution.

### 2.3. Deadlines and Percentiles

Do not rely solely on averages. For production workloads, track p50, p90, p95, and p99 of TTS. When meeting deadlines matters, p95/p99 and deadline-miss rates are usually far more informative than averages.

For batch jobs, test across diverse load conditions: idle vs. busy cluster, small/medium/large inputs, warm vs. cold caches, solo vs. concurrent runs, and moments when the scheduler has ample vs. scarce nodes.

## 3. Throughput and Completion Time Are Not the Same

Latency/TTS describes how long a single job takes to complete. Throughput describes how many jobs or work units complete per unit time.

Example:

- One job running on 16 nodes finishes in 8 minutes.
- Four concurrent jobs running on 4 nodes each may finish in 15 minutes per job, yet produce more total solutions within the same hour.

If the goal is getting one large simulation done as soon as possible, optimizing latency takes priority. If the goal is processing thousands of independent simulations, cluster-wide throughput and solutions per dollar matter more.

### 3.1. Cluster Throughput

~~~text
Throughput = Valid completed jobs / Measurement interval
~~~

When jobs vary in size, jobs/hour can mislead. Use timesteps/second, cells/second, molecule-steps/second, or domain-specific work units instead.

### 3.2. Batch Scheduling

Independent jobs can run as job arrays or batches. In such cases, giving each job more nodes is often less effective than running many smaller jobs concurrently.

Clarify the optimization target: earliest completion for one huge job, total daily completed jobs, lowest cost per solution, highest deadline-compliance rate, or a balance among latency, throughput, and cost.

## 4. Speedup and Parallel Efficiency

Speedup measures how much faster execution becomes when using multiple parallel resources compared to a baseline.

~~~text
S(p) = T(1) / T(p)
~~~

Where `T(1)` is baseline runtime on one defined resource unit, and `T(p)` is runtime for the same problem on `p` resource units; `p` may denote cores, ranks, GPUs, or nodes and must be stated explicitly.

If a problem takes 120 minutes on 1 node and 20 minutes on 6 nodes, node speedup is 6x—assuming identical node configurations and consistent measurement scope.

### 4.1. Parallel Efficiency

~~~text
E(p) = S(p) / p
     = T(1) / (p * T(p))
~~~

If `p = 6` and speedup is 4.8, efficiency is 0.8 (80%). That means speedup reached 80% of ideal linear scaling at that scale.

Efficiency is not CPU utilization percentage. A job can keep CPUs near 100% across all nodes yet have low efficiency due to baseline overhead, communication, or algorithmic scaling. Conversely, an I/O- or synchronization-heavy workload may show lower CPU utilization while progressing as designed.

### 4.2. Strong Scaling

Strong scaling holds problem size fixed and increases resource count. The question is: for the exact same input, how much does adding nodes shorten runtime?

| Node count | Runtime | Speedup | Efficiency |
|---:|---:|---:|---:|
| 1 | 120 minutes | 1.00x | 100% |
| 2 | 66 minutes | 1.82x | 91% |
| 4 | 38 minutes | 3.16x | 79% |
| 8 | 25 minutes | 4.80x | 60% |
| 16 | 20 minutes | 6.00x | 38% |

In this example, adding nodes still reduces runtime, but marginal returns diminish. Scaling from 8 to 16 nodes saves only 5 minutes while doubling node count.

### 4.3. Weak Scaling

Weak scaling increases problem size proportionally with resource count to hold work per resource nearly constant. The goal is seeing whether the cluster can scale total work volume while keeping runtime roughly stable.

| Node count | Total input size | Input/node | Runtime |
|---:|---:|---:|---:|
| 1 | 10 million cells | 10 million | 12 minutes |
| 2 | 20 million cells | 10 million | 13 minutes |
| 4 | 40 million cells | 10 million | 14 minutes |
| 8 | 80 million cells | 10 million | 17 minutes |

Rising runtime as node count grows reflects communication, synchronization, I/O, or load imbalance overhead. Strong weak-scaling numbers do not mean a fixed input will run faster when adding nodes.

### 4.4. The Baseline Must Be Defined

If a large problem cannot fit on a single node, the baseline can be the smallest meaningful configuration, such as 2 nodes. Document clearly that speedup is computed relative to 2 nodes—never call it absolute single-node speedup.

Never compare speedup across machines with differing CPUs, memory, GPUs, or compilers without normalizing baselines and explaining differences.

## 5. Parallel Limits: Amdahl and Gustafson

Not every part of a program can be split across cores. Sequential sections, communication, and synchronization cap speedup.

### 5.1. Amdahl's Law

If fraction `f` of work is parallelizable and the remaining `1 - f` is sequential, ideal speedup with `p` workers is:

~~~text
S(p) = 1 / ((1 - f) + f/p)
~~~

For example, if 90% of work is parallelizable and 10% is sequential, as `p` grows very large, maximum speedup approaches 10x. Adding nodes beyond that cannot accelerate the sequential fraction.

This model assumes a fixed sequential portion and omits full details of communication, contention, or data-size changes. It exposes fundamental limits rather than replacing benchmarks.

### 5.2. Gustafson's Law

In many HPC workloads, when more resources become available, teams solve larger problems in roughly the same time. Gustafson considers scaled workloads rather than fixed inputs.

~~~text
S_G(p) = p - alpha * (p - 1)
~~~

Where `alpha` is the sequential time fraction in the parallel run under the model. The formula captures the potential to grow problem scale alongside worker count under suitable sequential-fraction assumptions.

### 5.3. Implications for Cluster Selection

- Use strong scaling when you need to shorten runtime for a fixed problem.
- Use weak scaling when you need to handle larger problems as cluster capacity grows.
- If sequential work dominates, optimize the algorithm or pipeline before buying more nodes.
- If communication dominates, revisit partitioning, topology, and interconnects.
- If I/O dominates, optimize data layout and storage paths.

## 6. Parallel Execution Overhead

Actual parallel runtime can be modeled simply as:

~~~text
T(p) = T_parallel_work(p)
     + T_serial
     + T_communication
     + T_synchronization
     + T_imbalance
     + T_runtime_overhead
~~~

These components may overlap; the expression categorizes root causes. Raising `p` shrinks parallel work time but can inflate communication, synchronization, and runtime overhead.

### 6.1. Communication

In MPI, ranks exchange data via point-to-point or collective operations such as broadcast, reduce, all-reduce, and all-to-all. As rank counts rise, peer counts or exchanged byte volumes can climb sharply.

Communication is affected by interconnect latency and bandwidth, rank count and communication pattern, message size, node topology and placement, network congestion, NUMA, and CPU-to-NIC/GPU paths.

### 6.2. Synchronization

Barriers, locks, collective operations, and inter-step dependencies force workers to wait on one another. If one rank lags, other ranks stall at synchronization points.

Use profilers or MPI tracing to quantify collective wait times, lock contention, and imbalance rather than looking only at average CPU utilization.

### 6.3. Load Imbalance

If one node receives more data or harder work, it becomes a straggler. Remaining nodes finish early yet must wait on the slowest node before advancing.

Mitigations:

- Partition data more evenly.
- Use dynamic scheduling for workloads with variable task times.
- Avoid overly tiny partitions that inflate scheduler overhead.
- Track execution time per rank/task.
- Place data close to the compute resources processing it.

## 7. Evaluating CPU, GPU, and Interconnect

HPC typically combines CPUs, GPUs, and high-speed networking. Core or GPU counts are only input specs; measure whether the workload actually exploits them.

### 7.1. CPU

Monitor:

- Actually allocated and utilized cores/threads.
- Per-node and per-rank CPU utilization.
- IPC, cache misses, and memory bandwidth where tools support them.
- NUMA locality and remote memory accesses.
- CPU throttling or oversubscription.

A node with many cores yet low memory bandwidth may run no faster than a node with fewer cores for memory-bound workloads.

### 7.2. GPU

Monitor:

- GPU utilization and kernel duration.
- Memory utilization and memory bandwidth.
- Host-to-device / device-to-host transfers.
- Kernel launch overhead.
- GPU occupancy and multiprocessor utilization.
- Time waiting on CPU or communication.

Low GPU utilization can stem from small batches, tiny kernels, data transfers, or CPUs failing to feed data fast enough. Adding GPUs without boosting data-feeding capacity raises costs with little impact on TTS.

### 7.3. Interconnect

Measure bandwidth and latency with benchmarks matching the actual network fabric. For MPI, test both point-to-point and collective operations, intra-node and inter-node.

Never substitute theoretical network benchmark figures for real application runs. Application communication patterns, message sizes, and topology can produce performance far different from synthetic tests.

## 8. Profiling and Bottleneck Analysis

Benchmarks show which configuration is faster; profiling explains why.

Tool categories to use:

- CPU profilers and hardware performance counters.
- GPU profilers and tracers.
- MPI profilers/tracers.
- Per-node system monitoring.
- Storage latency/throughput metrics.
- Scheduler accounting and job state history.
- Application-level timers around each phase.

### 8.1. Breaking Down Application Time

Add timestamps or timers around major phases:

~~~python
from time import perf_counter

start = perf_counter()
load_input()
t_input = perf_counter()

initialize_solver()
t_init = perf_counter()

solve()
t_solve = perf_counter()

write_output()
t_output = perf_counter()

print({
    "input_seconds": t_input - start,
    "initialize_seconds": t_init - t_input,
    "solve_seconds": t_solve - t_init,
    "output_seconds": t_output - t_solve,
    "total_seconds": t_output - start,
})
~~~

In MPI programs, clocks across nodes may skew. To measure elapsed time of a parallel phase, use a monotonic clock per process and gather the max/critical-path duration; never subtract wall-clock timestamps across unsynchronized hosts.

### 8.2. Critical Path Time Is What Matters

A parallel phase may comprise many tasks. Phase completion time is typically dictated by the slowest task, not the sum or average of all tasks.

Record minimum, median, and maximum duration across ranks; barrier/collective wait time; communication time; bytes sent/received; I/O time; and work distribution across nodes.

Averages can mask a severely lagging rank; maximums and percentiles expose stragglers.

## 9. Fair and Reproducible Benchmarking

A benchmark result is only meaningful when inputs, software, configuration, and run conditions are documented.

### 9.1. Fix the Workload

Record:

- Input dataset, size, and checksum.
- Application version and commit.
- Compiler, flags, and math libraries.
- MPI implementation and version.
- Container image digest or package checksum.
- CPU/GPU models, memory, and interconnect.
- Node, core/rank/thread/GPU counts.
- Scheduler partition, placement, and binding.
- Precision, tolerance, and correctness criteria.

### 9.2. Warm-Up and Iteration Counts

Some applications need warm-up for JIT compilation, cache population, GPU context initialization, or connection setup. Separate warm-up from timed runs if measuring steady-state runtime; if measuring cold-start/TTS, keep initialization inside the timed scope.

Run multiple iterations and report the median and dispersion. In noisy environments, report p95 or confidence intervals. Never discard slow runs without an identified, documented cause.

### 9.3. Do Not Change Multiple Variables at Once

During experiments, vary one deliberate factor group at a time:

- Node count.
- Ranks per node.
- Threads per rank.
- GPUs per node.
- CPU/GPU type.
- Network topology.
- Storage tier.
- Compiler/MPI tuning.

Changing node count, compiler, inputs, and storage simultaneously makes it impossible to isolate what drove improvements.

### 9.4. Correctness Verification

Every configuration must produce outputs meeting quality standards. In numerical simulations, parallel runs can alter summation orders in floating-point reductions; use predefined scientific tolerances rather than demanding bitwise identity when the algorithm does not guarantee it.

Never accept a faster configuration if outputs are wrong, incomplete, or non-reproducible against requirements.

## 10. Cluster-Wide Cost Modeling

HPC cost is not just CPU/GPU pricing. A job can consume compute nodes, interconnects, storage, snapshots, data transfers, software licenses, schedulers, monitoring, and operational labor.

General model:

~~~text
C_cluster =
    C_compute
  + C_accelerator
  + C_network
  + C_storage
  + C_data_transfer
  + C_software_license
  + C_scheduler_and_services
  + C_support_and_operations
  + C_idle_capacity
~~~

In the cloud, some items are billed directly by usage; others sit inside managed services or licenses. On-premises, amortize server hardware, networking, storage, power, cooling, maintenance, and staffing over utilized time.

### 10.1. Compute Node-Hours

If node type `i` costs `r_i` per node-hour, with `n_i` nodes for billable duration `h_i`:

~~~text
C_compute = sum(n_i * r_i * h_i)
~~~

Use the provider's actual billable time. Some services bill from provisioning onward, per second/minute, per hour, or with minimum charges; queue time before node allocation may not accrue compute charges yet still impacts TTS. Allocated nodes waiting on I/O or sitting idle still accrue bills.

### 10.2. GPUs and Accelerators

GPUs are typically priced per node or per accelerator-hour. Distinguish bundled GPU-node pricing from standalone GPU pricing to avoid double-counting when node rates already include accelerators.

A GPU node can cost far more than a CPU node. Compare costs only across configurations producing valid results of equivalent quality. If GPU utilization is low or data transfers dominate runtime, accelerator spend may yield poor value.

### 10.3. Networking

Network costs can include:

- Premium interconnects or network tiers.
- Cross-zone / cross-region data transfer.
- Internet or external egress.
- Network appliances or private connectivity.
- Compute-to-storage traffic if billed separately.

Not every cloud bills every traffic type. Separate free intra-AZ traffic, cross-AZ traffic, cross-region traffic, and egress according to the specific service's pricing table.

### 10.4. Storage and I/O

Storage costs can cover provisioned capacity, used capacity, provisioned IOPS, throughput, request counts, snapshots, backups, and data retrieval.

HPC workloads often generate massive checkpoints or intermediate files. Checkpointing too often or retaining too many versions can drive steep storage and request bills. Include stage-in/stage-out transfer fees and compute time spent waiting on storage.

### 10.5. Licensing and Software

Commercial software may charge per core, socket, node, GPU, or runtime hour. A higher-core configuration can raise license fees even if compute pricing stays flat.

Include compilers, solvers, MPI distributions, visualization tools, scheduler plugins, and commercial libraries in the cost inventory. Check license terms for cloud execution, especially with autoscaling and ephemeral nodes.

## 11. Idle Capacity Cost and Utilization

Provisioned resources doing no useful work still incur costs. Common idle sources:

- Nodes provisioned before the job actually starts.
- Jobs holding allocations while waiting on one rank or dependency.
- Nodes oversized relative to the application's parallelism.
- GPUs starved of batches to stay busy.
- Clusters holding spare capacity during low-demand periods.
- Jobs finishing before nodes scale in or release.

### 11.1. Utilization

Track utilization across multiple layers:

- **Allocated utilization:** percentage of time resources are allocated to jobs by the scheduler.
- **CPU utilization:** percentage of time CPUs execute active work relative to capacity.
- **GPU utilization:** device activity percentage reported by GPU telemetry.
- **Memory utilization:** memory consumed relative to capacity.
- **Network utilization:** bandwidth used relative to link capacity.
- **Storage utilization:** actual IOPS/throughput relative to provisioned limits.

These metrics do not substitute for one another. A node at 100% allocated utilization can still have low CPU utilization because the job is stalled on network or storage.

### 11.2. Shared Cluster Cost Allocation

For multi-team shared clusters, establish chargeback or showback rules. Costs can be allocated by node-hours, GPU-hours, core-hours, memory-hours, storage consumption, network usage, or reservation shares.

Splitting costs purely by job count charges a tiny simulation team the same as a heavy GPU training team, distorting incentives.

### 11.3. Buffer Capacity

Spare buffer capacity trims queue wait times and helps meet deadlines, yet increases idle cost. Balance:

- Required SLA/deadline targets.
- Workload burstiness.
- Node startup or provisioning latency.
- Cost of holding warm capacity.
- Ability to share nodes across jobs.
- Feasibility of interruptible capacity for fault-tolerant jobs.

## 12. Cost per Solution and Economic Efficiency

A key metric is total cost per valid result:

~~~text
Cost per solution =
  Total cost attributable to workload
  / Number of validated solutions
~~~

For a job producing a single result, cost per solution approximates total cost attributed to that job. For multi-job batches, divide by validated outputs only—never count failed jobs or invalid outputs as successful solutions.

Additional metrics:

~~~text
Throughput per dollar = Valid work units completed / Total cost

Cost per node-hour = Total cluster cost / Allocated node-hours

Cost efficiency = Useful work / Total resource cost
~~~

Define useful work specifically to the application: timesteps, cell updates, simulations, training steps, or validated solutions. Never use a generic unit to compare fundamentally different workloads.

### 12.1. Deadline-Aware Cost

When one configuration is faster yet pricier, the choice depends on the value of time:

- If a hard deadline must be met, the faster configuration may be the only viable choice.
- If jobs can run overnight, a cheaper configuration may win.
- If running many independent jobs, optimizing throughput per dollar often beats optimizing single-job TTS.
- If queue wait exceeds compute time, adding nodes per job will not fix the main bottleneck.

Evaluate configurations along the Pareto frontier: configurations for which no other option is both faster and cheaper. Then pick the point matching deadline, budget, and quality constraints.

### 12.2. Cost per Solution Calculation Example

Suppose a CPU node costs 3 currency units per node-hour. A job produces one valid solution and requires a 30-minute allocation on 8 nodes. Allocated ancillary costs include storage 1.2, network 0.8, licenses 2.0, and scheduler/services 0.5.

~~~text
Compute cost = 8 * 3 * 0.5 = 12.0
Other cost   = 1.2 + 0.8 + 2.0 + 0.5 = 4.5
Total cost   = 12.0 + 4.5 = 16.5
Cost/solution = 16.5 / 1 = 16.5
~~~

A 16-node configuration finishes in 25 minutes:

~~~text
Compute cost = 16 * 3 * (25/60) = 20.0
Other cost   = 1.2 + 1.0 + 2.0 + 0.5 = 4.7
Total cost   = 20.0 + 4.7 = 24.7
Cost/solution = 24.7 / 1 = 24.7
~~~

The 16-node setup saves 5 minutes yet raises cost per solution from 16.5 to 24.7 units. If the deadline is under 25 minutes, 16 nodes may be necessary; if the deadline is 40 minutes, 8 nodes is more economical. These figures are illustrative and exclude queue wait if unbilled.

## 13. Comparing Configurations on the Pareto Frontier

HPC configuration involves at least two competing goals: minimizing TTS and minimizing cost. Represent each configuration as a pair:

~~~text
Configuration = (TTS, Cost per solution)
~~~

Configuration A dominates configuration B if A is no slower and no costlier than B, and strictly better on at least one criterion. Non-dominated configurations form the Pareto frontier.

Example:

| Configuration | TTS | Cost/solution | Notes |
|---|---:|---:|---|
| 4 CPU nodes | 50 minutes | 10 | Cheapest but slow |
| 8 CPU nodes | 30 minutes | 16 | Balanced |
| 16 CPU nodes | 25 minutes | 25 | Faster but pricey |
| 4 GPU nodes | 18 minutes | 21 | Both faster and cheaper than 16 CPU nodes in this example |
| 8 GPU nodes | 15 minutes | 34 | Fastest but expensive |

These numbers merely illustrate how to read the table. Because 4 GPU nodes are both faster and cheaper than 16 CPU nodes, 16 CPU nodes are dominated for this workload. Conclusions can shift for different inputs or quality criteria.

### 13.1. Applying Constraints Before Selecting

The Pareto frontier alone is not enough to decide. Factor in:

- Maximum deadline.
- Maximum budget.
- Precision or result quality.
- Memory capacity and memory bandwidth.
- GPU or license limits.
- Timely node availability.
- Data residency and security requirements.

Filter out configurations violating constraints first, then choose from the remaining set.

## 14. Optimizing Cost Without Sacrificing Performance

Effective cost optimization starts at the bottleneck. Picking cheaper nodes that double runtime can raise total cost. Conversely, a pricier node that finishes much sooner can reduce billable node-hours.

### 14.1. Right-Sizing Nodes

- Memory-bound workloads need sufficient RAM and memory bandwidth.
- Compute-bound workloads need high CPU/GPU throughput.
- Communication-bound workloads need strong interconnects and topology.
- I/O-bound workloads need matching storage throughput/IOPS.
- Low-parallelism workloads often perform better on fewer, stronger nodes.

Never select nodes purely by vCPU count. Inspect CPU generation, core clock, NUMA, RAM bandwidth, GPU memory, and network fabric.

### 14.2. Tuning Rank and Thread Counts

MPI rank and thread counts affect communication, memory footprint, and CPU binding. Some workloads prefer one rank per core; others prefer one rank per NUMA domain with multiple threads.

Run controlled experiments across combinations:

- One rank per node with many threads.
- Many ranks per node with fewer threads.
- One rank per GPU or application-aligned mapping.
- CPU binding and NUMA placement.

Avoid oversubscription where total threads exceed allocated cores unless the app is explicitly designed for it. Verify affinity so processes do not migrate unpredictably across NUMA nodes.

### 14.3. Reducing Data Movement

- Place inputs close to the cluster or stage onto local scratch before execution.
- Use data formats friendly to parallel access.
- Cut down small file reads/writes.
- Batch I/O into larger blocks where appropriate.
- Overlap communication and computation when the algorithm permits.
- Checkpoint strictly in line with RPO and risk tolerance.

Shrinking I/O time shortens TTS and cuts billable node-hours.

### 14.4. Rightsizing and Autoscaling

Schedulers and autoscalers can provision node counts matched to workload demand. Balance scale-up time against job duration and warm-capacity costs.

For tightly coupled MPI jobs, you cannot arbitrarily add nodes mid-computation unless the app supports dynamic process management. Scale between jobs, between stages, or across batches instead.

### 14.5. Reserved, On-Demand, and Interruptible Capacity

| Capacity type | Benefits | Risks/costs to weigh |
|---|---|---|
| On-demand | Available as needed, no long-term lock-in | Higher unit rates than committed tiers |
| Reserved/committed | Lower unit rates for steady baselines | Financial commitment and risk of unused capacity |
| Spot/preemptible | Lower pricing when spare capacity exists | Can be reclaimed; needs checkpoint/retry and fallback capacity |

Checkpointed HPC workloads and independent jobs suit interruptible capacity well. Tightly coupled MPI jobs or long runs unable to checkpoint suffer heavily when one node vanishes, so weigh interruption probability against rerun costs.

## 15. Checkpoints, Failures, and Rerun Costs

Checkpoints create recovery points for long jobs. They add I/O and may briefly pause computation, yet cut recomputed work when nodes or jobs fail.

Expected cost model:

~~~text
Expected total cost =
  Normal execution cost
  + Checkpoint cost
  + Expected restart cost
  + Recovery and data transfer cost
~~~

Checkpointing too frequently lets write overhead drag down efficiency. Checkpointing too rarely loses huge progress when failures strike.

### 15.1. Measuring Checkpoint Overhead

Track:

- Checkpoint creation duration.
- Checkpoint size.
- Storage throughput and latency.
- Resume duration.
- Checkpoint failure counts.
- Compute time lost to restarts.

Store checkpoints on storage that survives node loss. Local scratch works as a staging layer but should never hold the sole copy.

### 15.2. Accounting for Retry Costs

When a job fails, resources consumed before failure are still real costs. Total cost is not just the final successful attempt. Record attempt counts, wasted compute time, restored checkpoints, and discarded outputs.

For job arrays, retry only failed tasks instead of rerunning the entire batch when tasks are independent and write to distinct keys.

## 16. On-Premises vs. Cloud Cluster Costs

On-premises costs usually combine upfront CapEx with recurring OpEx. Cloud costs center on usage, reservations/commitments, and supporting services. Compare both models over identical utilization windows and service levels.

### 16.1. On-Premises Total Cost of Ownership

Components:

- CPU/GPU servers, memory, and accelerators.
- Switches, NICs, cabling, and fabric interconnects.
- Storage, controllers, and backups.
- Racks, power, UPS, and cooling.
- Licenses, support, and maintenance.
- Operations staff, hardware replacements, and upgrades.
- Opportunity cost of idle unused capacity.

Amortize CapEx over depreciation schedules and actual utilization. If a cluster sits utilized only 20% of the time, cost per useful compute hour can be high even after hardware is paid off.

### 16.2. Cloud HPC

Components:

- Compute nodes and GPU-hours.
- High-performance networking or placement groups if billed.
- Persistent disks, parallel file systems, object storage, and snapshots.
- Cross-region/AZ data transfers or egress.
- Software licenses and managed schedulers.
- Image registries, logging, monitoring, and support.
- Underutilized reservations/commitments.

Cloud removes upfront CapEx and enables burst scaling, though data staging, storage, and idle provisioned capacity can push bills higher than projected.

### 16.3. Comparing by Utilization

To compare fairly, calculate:

~~~text
Effective cost per useful node-hour =
  Total ownership or cloud cost
  / Useful node-hours delivered
~~~

Useful node-hours should reflect time resources genuinely deliver productive work under a consistent definition. On-premises, allocate depreciation, power, and operations across utilized hours; on the cloud, sum billable runtime and associated services.

## 17. Operational Dashboards and Metrics

HPC dashboards should link three layers: job progress, resource efficiency, and cost.

| Category | Metrics |
|---|---|
| Time-to-solution | Submit-to-result, queue wait, provisioning, stage-in/out, compute, validation |
| Parallel performance | Speedup, efficiency, strong/weak scaling, rank imbalance |
| CPU | Utilization, throttling, IPC, memory bandwidth, NUMA locality |
| GPU | Utilization, memory, kernel time, transfer time |
| Network | Bandwidth, latency, retransmissions, collective time |
| Storage | IOPS, throughput, latency, capacity, checkpoint duration |
| Scheduler | Allocated node-hours, pending jobs, idle allocation, job failures |
| Cost | Compute cost, GPU cost, storage, network, licenses, cost/solution |
| Quality | Valid result rate, precision/tolerance, retry counts |

### 17.1. Tagging Costs to Workloads

Attach metadata to every job: project, team, owner, experiment ID, application version, and cost center. This enables grouping costs by team and tracing anomalous cost spikes back to specific jobs.

On shared clusters, agree on rules for allocating scheduler, buffer capacity, network, and storage overhead. Clearly separate direct costs from shared allocated costs.

### 17.2. Alerting

Set alerts when:

- Jobs miss deadlines or TTS spikes abruptly.
- Parallel efficiency drops as node count scales.
- A rank/node becomes a straggler.
- GPU utilization stays persistently low.
- Network or storage latency climbs.
- Allocated node-hours exceed budget.
- Cost per solution rises above baseline.
- Retry or checkpoint failure rates spike.

## 18. Evaluation and Configuration Selection Workflow

A practical workflow follows these steps:

1. **Define objectives:** deadlines, throughput, quality, and budget.
2. **Select representative workloads:** inputs matching production size and patterns.
3. **Establish a baseline:** one node or the smallest meaningful configuration.
4. **Build a test matrix:** node counts, ranks/threads, CPU/GPU types, networking, and storage.
5. **Run repeated benchmarks:** separate warm-up from steady-state when appropriate.
6. **Verify outputs:** confirm precision, tolerance, and completeness.
7. **Compute speedup/efficiency:** against the baseline using the same measurement scope.
8. **Profile:** isolate serial work, communication, imbalance, and I/O.
9. **Calculate cluster-wide cost:** include compute, network, storage, licenses, and idle capacity.
10. **Plot the Pareto frontier:** prune configurations that are both slower and costlier.
11. **Select a configuration:** meet deadlines and budgets with safety margin.
12. **Monitor production:** reconcile live telemetry against benchmarks and re-evaluate as workloads evolve.

## 19. Practical Example: Choosing a Configuration for CFD Simulation

An engineering team runs a computational fluid dynamics (CFD) simulation on a cloud cluster. Each run uses the exact same mesh and convergence criteria. Results are valid only when the solver hits the residual tolerance and output files write completely.

The team tests strong scaling on a fixed input:

| Configuration | Compute time | TTS | Compute-time speedup |
|---|---:|---:|---:|
| 1 CPU node | 120 minutes | 132 minutes | 1.00x |
| 2 CPU nodes | 66 minutes | 78 minutes | 1.82x |
| 4 CPU nodes | 38 minutes | 50 minutes | 3.16x |
| 8 CPU nodes | 25 minutes | 37 minutes | 4.80x |
| 16 CPU nodes | 20 minutes | 32 minutes | 6.00x |

TTS includes 12 minutes of queue/provision/stage/validation under this example's assumptions. If those phases vary by configuration or cluster load, measure them per run rather than adding a constant.

In the cost calculation below, assume 5 of the 12 non-compute minutes are billable node provisioning time; the remaining 7 minutes are unbilled queue, staging, and validation. Storage, networking, and licenses are accounted for separately under ancillary costs.

### 19.1. Reading Parallel Efficiency

Relative to the single-node baseline:

- 4 nodes achieve ~3.16x speedup and ~79% efficiency.
- 8 nodes achieve 4.8x speedup and 60% efficiency.
- 16 nodes achieve 6x speedup and 37.5% efficiency.

Efficiency drops as nodes increase. Profiling reveals rising communication and barrier wait times at 16 nodes, signaling the team should revisit domain decomposition and collective operations before adding more nodes.

### 19.2. Cost Comparison

Assume a node rate of 3 currency units per node-hour and allocated ancillary costs per the example:

| Configuration | Compute cost | Ancillary cost | Total cost/solution |
|---|---:|---:|---:|
| 8 nodes, 30 billable min | 12.0 | 4.5 | 16.5 |
| 16 nodes, 25 billable min | 20.0 | 4.7 | 24.7 |

16 nodes shorten compute time yet markedly raise cost per solution. If a 40-minute deadline is acceptable, 8 nodes is far more economical. If the deadline is under 25 minutes, the team must consider 16 nodes or optimize the algorithm/communication to hit the deadline at lower cost.

### 19.3. Post-Benchmark Decision

The team selects 8 nodes as the default configuration for non-urgent runs. For hard-deadline experiments, 16 nodes are permitted under a dedicated policy. Before scaling further, the team experiments with partition tuning, reducing synchronization, and improving I/O; every change is re-benchmarked with identical inputs and convergence criteria.

This example uses hypothetical numbers to illustrate decision-making. In practice, use actual billable time, queue wait, and regional/contract pricing.

## 20. Selection Matrix by Workload Type

| Workload trait | Priority metrics | Configurations to test |
|---|---|---|
| Compute-bound | FLOP/s, speedup, CPU/GPU utilization | Core/GPU throughput, vectorization, rank/thread mapping |
| Memory-bound | Memory bandwidth, cache misses, NUMA | RAM bandwidth, memory capacity, NUMA placement |
| Communication-bound | MPI time, latency, collective duration | Interconnect, topology, rank placement, message aggregation |
| I/O-bound | Storage latency, throughput, IOPS | Parallel filesystem, local scratch, data layout |
| Embarrassingly parallel | Throughput, cost per job | Job arrays, many independent jobs, smaller nodes |
| Tightly coupled MPI | TTS, parallel efficiency, tail rank time | Homogeneous nodes, fast interconnect, stable placement |
| GPU-heavy | GPU kernel time, utilization, transfers | GPU memory, accelerator count, CPU feed rate |
| Long-running/checkpointed | Retry-aware TTS, checkpoint overhead, expected cost | Durable checkpoint storage, interruptible capacity where suitable |

This matrix is only a starting point. Benchmarking with representative inputs determines the right configuration.

## 21. Common Mistakes

- **Measuring only kernel time:** ignores queueing, provisioning, data staging, checkpointing, and validation.
- **Comparing mismatched measurement scopes:** one configuration includes I/O while another measures compute only.
- **Using CPU utilization instead of parallel efficiency:** these measure completely different aspects.
- **Omitting baselines:** speedup is meaningless if the baseline or unit `p` is undefined.
- **Confusing strong scaling with weak scaling:** each test answers a different question.
- **Assuming linear speedup:** serial fractions, communication, and synchronization curb gains.
- **Looking only at averages:** stragglers or lagging ranks remain hidden.
- **Benchmarking with unrepresentative inputs:** results fail to reflect production.
- **Skipping correctness checks:** faster configurations producing wrong outputs get counted as wins.
- **Counting only node prices:** ignores GPUs, networking, storage, licenses, transfers, and idle capacity.
- **Ignoring allocation duration:** nodes incur bills even while jobs stall on I/O or sit underutilized.
- **Optimizing single-job latency for batch workloads:** can reduce throughput and inflate cost per total solutions.
- **Running unrecoverable jobs on Spot:** retry bills can wipe out savings.
- **Ignoring checkpoint overhead:** overlooks both I/O cost and rerun costs upon failure.
- **Scaling node counts to fight queue wait:** asking for more nodes per job does not make the scheduler start jobs sooner.
- **Failing to archive benchmark metadata:** makes runs impossible to reproduce or explain differences across runs.

## 22. HPC Performance and Cost Evaluation Checklist

Before locking in a configuration, confirm:

- [ ] Defined start and end milestones for time-to-solution.
- [ ] Separated queueing, provisioning, stage-in/out, initialization, compute, and validation.
- [ ] Recorded inputs, checksums, application version, compiler, and MPI version.
- [ ] Recorded CPU/GPU models, memory, interconnect, node count, and rank/thread mapping.
- [ ] Baseline is meaningful and unit `p` is stated clearly.
- [ ] Strong scaling and weak scaling were tested for their intended goals.
- [ ] Speedup and parallel efficiency were computed from identical measurement scopes.
- [ ] Checked Amdahl limits and sequential work portions.
- [ ] Profiled communication, synchronization, imbalance, and I/O.
- [ ] Measured critical path, maximum rank duration, and tail latency.
- [ ] Repeated benchmarks and reported dispersion.
- [ ] Outputs satisfy precision/tolerance and completeness criteria.
- [ ] Costs include compute, accelerators, networking, storage, transfers, licenses, and services.
- [ ] Accounted for billable time, idle allocations, reservations, and retries.
- [ ] Cost per solution counts validated solutions only.
- [ ] Compared the Pareto frontier against deadlines and budgets.
- [ ] Dashboards, cost attribution, and production alerts are configured.
- [ ] Archived configurations and artifacts for benchmark reproducibility.

## 23. Key Takeaways

HPC evaluation must combine time-to-solution, parallel efficiency, and cluster-wide cost. TTS reflects elapsed time from submission to a valid result; speedup and parallel efficiency quantify returns from adding resources; strong scaling keeps problem size fixed, while weak scaling grows problem size with worker count.

As nodes scale out, sequential fractions, communication, synchronization, load imbalance, and I/O erode gains. Rely on profiling and repeated benchmarks with documented inputs, software, architectures, and correctness criteria. Cluster-wide costs must cover compute/GPUs, networking, storage, data transfers, licenses, schedulers, idle capacity, and retries. Ultimately, pick a configuration on the Pareto frontier that meets deadlines and quality standards at an acceptable cost per solution—never choose solely by core count or the speed of a single kernel.

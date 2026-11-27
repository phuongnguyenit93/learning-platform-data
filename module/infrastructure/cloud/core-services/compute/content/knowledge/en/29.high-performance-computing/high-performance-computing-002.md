# Scale-Up, Scale-Out, and Parallelizable Work

When a compute workload needs to process more data or finish faster, two common capacity expansion approaches exist. **Scale-up** increases the resources of a single machine or node—such as adding CPUs, memory, memory bandwidth, or accelerators. **Scale-out** distributes work across multiple nodes so aggregate capacity comes from the entire cluster. Both approaches only pay off when the workload can actually utilize the added resources.

A program does not automatically run twice as fast when the core count doubles. Part of the work may have to execute sequentially; parallel portions may need to exchange data, synchronize, or wait on I/O. As worker count increases, coordination overhead can sometimes exceed the compute savings gained. Therefore, choosing between scale-up and scale-out must be grounded in algorithm structure, parallelizability, memory and network limits, data partitioning strategies, and performance/cost targets.

This lesson belongs to the **High-Performance Computing** chapter of the **CLOUD_CORE_SERVICES_COMPUTE** module. The module helps learners explore cloud compute models—from virtual machines and containers to serverless; how to choose CPU, memory, networking, and security configurations; and how to deploy applications, scale under load, ensure availability, and optimize operating costs. In HPC, understanding scale-up, scale-out, and parallelizable work helps select suitable compute configurations, forecast performance, and avoid rising costs without corresponding runtime reductions.

## 1. What Are Scale-Up and Scale-Out?

### 1.1. Scale-up (vertical scaling)

Scale-up increases the capacity of an existing node or moves the workload to a larger node.

Resources that can be increased:
- Number of cores or vCPUs.
- Memory capacity and memory bandwidth.
- Speed or count of accelerators such as GPUs.
- I/O capacity and storage bandwidth.
- Node network bandwidth.
- CPU cache or NUMA memory access capabilities.

For example, a simulation running on a 16-core, 128 GiB RAM machine can be moved to a 64-core, 512 GiB RAM machine. If most of the runtime consists of computations parallelizable across cores, completion time can drop substantially.

Scale-up is typically simpler to program because data can reside in a shared memory space. However, it hits hardware ceilings, high large-node costs, discrete scaling steps, and can create a single point of failure.

### 1.2. Scale-out (horizontal scaling)

Scale-out distributes a workload across multiple nodes connected over a network. Each node has its own CPU, memory, and I/O devices; nodes exchange data via message passing, collective communication, shared storage, or framework distribution mechanisms.

Examples:
- Running a spatial domain simulation across 32 nodes.
- Splitting a dataset into multiple partitions for concurrent processing.
- Distributing inference batches across multiple GPU workers.
- Running many independent jobs on an HPC cluster.

Scale-out can expand total capacity beyond single-machine limits while leveraging commodity nodes. In return, the application must handle data partitioning, network communication, synchronization, node failures, and distributed outputs.

### 1.3. Quick Comparison

| Criterion | Scale-up | Scale-out |
|---|---|---|
| How capacity grows | Add resources within a single node | Add nodes to a cluster |
| Memory | Typically uses shared memory within the node | Each node has private memory, requiring data exchange |
| Communication | Threads, shared memory, local interconnect | Network, message passing, distributed storage |
| Application complexity | Typically lower if the program already supports multithreading | Typically higher due to partitioning and coordination |
| Limits | Hardware ceilings and high large-node cost | Network, synchronization, data distribution, and scheduler |
| Scalability | Grows in discrete machine configuration tiers | Can add many nodes, subject to parallel efficiency |
| Failures | A node failure can halt the entire job | Must handle node failures and distributed state |
| Best suited for | Workloads needing shared memory or centralized data | Workloads divisible into relatively independent parts |

Neither choice is universally superior. An HPC architecture frequently combines scale-up within each node and scale-out across nodes.

### 1.4. Scale-Up Inside, Scale-Out Outside

A cluster may consist of multiple large nodes, each with many CPU cores and one or more GPUs. The program uses threads or GPU kernels inside each node, then uses MPI or a distributed runtime across nodes.

This model is commonly called hybrid parallelism:
- Intra-node parallelism: leverages cores, threads, shared memory, and accelerators within a node.
- Inter-node parallelism: splits the workload across multiple nodes and exchanges data over the network.

Hybrid is not automatically faster. You must avoid thread oversubscription, memory bandwidth contention, and excessive message counts.

## 2. Identifying What Can Be Parallelized

### 2.1. Work Decomposition

Before adding cores or nodes, break the algorithm down into:
- Parts that must run sequentially.
- Parts that can run concurrently.
- Parts that require data exchange.
- Parts that must wait on results from other parts.
- Parts that read/write data.
- Initialization and teardown parts.

For example, a data analysis pipeline might consist of:
1. Reading input files.
2. Normalizing data.
3. Splitting data into partitions.
4. Computing on each partition.
5. Merging results.
6. Writing reports.

Step 4 can be highly parallel if partitions are independent. Step 5 may require reduction or shuffling. Steps 1 and 6 can become bottlenecks if storage lacks sufficient throughput.

### 2.2. Data Parallelism

Data parallelism divides data into multiple chunks and runs the same computation on each chunk.

Examples:
- Splitting an image into tiles for processing.
- Splitting a matrix into blocks.
- Splitting a dataset by range or partition.
- Splitting a simulation domain into subdomains.

This model works well when each data chunk can be processed independently or only needs to exchange data along certain boundaries.

### 2.3. Task Parallelism

Task parallelism splits work into distinct tasks that can execute concurrently.

For example, a pipeline has tasks:
- Decoding data.
- Computing features.
- Checking quality.
- Writing metadata.
- Generating previews.

Tasks can have different runtimes and resource profiles. The scheduler must balance load and manage dependencies among them.

### 2.4. Pipeline Parallelism

Pipeline parallelism breaks a workflow into stages, where each stage processes a piece of data and passes the result to the next stage.

Examples:
- Stage A reads and decodes.
- Stage B transforms.
- Stage C computes.
- Stage D writes output.

Once the pipeline is filled, multiple stages can process different items simultaneously. Throughput can increase, though single-item latency still depends on total time through all stages. The slowest stage limits the throughput of the entire pipeline.

### 2.5. Embarrassingly Parallel

A workload is called embarrassingly parallel when work units are nearly independent and require minimal communication.

Examples:
- Rendering individual frames independently.
- Running many simulations with different parameter sets.
- Processing individual files independently.
- Searching or evaluating many separate candidates.

These are typically strong candidates for scale-out because coordination overhead is low. However, you still need to aggregate results, manage input/output, distribute tasks, and handle task failures.

### 2.6. Data Dependencies and Task Graphs

Not every task can run in parallel. If step B requires the output of step A, B must wait for A. A workload can be represented as a directed acyclic graph (DAG) when there are no dependency cycles during that execution.

~~~mermaid
flowchart TD
    A["Read data"] --> B["Normalize"]
    B --> C1["Partition 1"]
    B --> C2["Partition 2"]
    B --> C3["Partition 3"]
    C1 --> D["Merge results"]
    C2 --> D
    C3 --> D
    D --> E["Write results"]
~~~

Partitions can run in parallel. The merge step must wait for all required partitions to finish. If one partition is much slower, it can dictate the completion time of the entire DAG.

## 3. Amdahl's Law: Limits from Sequential Portions

### 3.1. Formula

Amdahl's Law estimates the maximum speedup when part of a program can be parallelized while the rest must run sequentially.

Let:
- P be the fraction of runtime that can be parallelized, from 0 to 1.
- 1 − P be the sequential runtime fraction.
- N be the number of processing units.

Ideal speedup:

\[
S(N) = \frac{1}{(1-P) + \frac{P}{N}}
\]

The formula assumes the parallel portion divides evenly with zero communication, synchronization, initialization, or I/O overhead. Actual performance is typically lower.

### 3.2. Example with 90% Parallel Work

Suppose 90% of a program's runtime can run in parallel, while 10% must run sequentially.

| Cores | Ideal speedup | Parallel efficiency |
|---:|---:|---:|
| 1 | 1.00× | 100% |
| 2 | 1.82× | 91% |
| 4 | 3.08× | 77% |
| 8 | 4.71× | 59% |
| 16 | 6.40× | 40% |
| 32 | 7.80× | 24% |
| 64 | 8.77× | 14% |

Even when scaling from 8 to 64 cores, speedup increases only from about 4.71× to 8.77×. The sequential portion becomes a clear ceiling.

### 3.3. Limit as Core Count Approaches Infinity

As N approaches infinity, portion P can be processed almost instantaneously, but the sequential portion remains:

\[
S_{\max} = \frac{1}{1-P}
\]

If P = 0.9, maximum speedup is only 10×. If P = 0.99, the ideal ceiling is 100×.

This shows that optimizing the sequential portion can yield greater gains than continuing to add cores once a workload nears its Amdahl limit.

### 3.4. Finding Sequential Portions in a Program

Sequential bottlenecks can hide in:
- Data initialization and config loading.
- Parsing or serializing large datasets.
- Loops with loop-carried dependencies from previous iterations.
- Reduction or aggregation phases.
- Locks or critical sections.
- Writing checkpoints or metadata.
- A central service that every worker must call.

Use profilers and traces to find real bottlenecks. Do not just eyeball line counts or guess that the longest loop is the most time-consuming part.

## 4. Gustafson's Law and Growing Problem Sizes

### 4.1. Why Doesn't Amdahl Describe Every Workload?

Amdahl typically considers a fixed-size problem: as core count increases, we want to complete the exact same amount of work faster.

In HPC, when additional resources become available, users often want to solve larger problems:
- Simulate a spatial domain in finer detail.
- Increase model resolution.
- Use larger datasets.
- Increase sample counts or scenario counts.
- Increase scientific model size.

Gustafson describes the case where problem size scales with processing capacity.

### 4.2. Gustafson's Formula

Let:
- N be the number of processing units.
- α be the sequential fraction measured in the scaled parallel runtime.

Speedup under Gustafson's model:

\[
S_G(N) = N - \alpha(N-1)
\]

For example, with α = 0.05 and N = 32:

\[
S_G = 32 - 0.05 \times 31 = 30.45
\]

The ideal result shows that if the sequential fraction is small and the problem scales with resources, many nodes can be utilized effectively.

### 4.3. When to Use Amdahl vs. Gustafson?

| Question | Suitable model |
|---|---|
| Same dataset, adding cores to cut runtime? | Amdahl / strong scaling |
| Adding nodes to process a larger problem in similar time? | Gustafson / weak scaling |
| Adding nodes while data and communication also grow? | Real benchmarking required; both models are only estimates |
| Workload limited by I/O or network? | Must analyze non-CPU bottlenecks |

Do not use Gustafson's formula to claim a system is guaranteed to scale linearly. If exchanged data or synchronization costs grow rapidly with node count, performance will degrade.

## 5. Strong Scaling and Weak Scaling

### 5.1. Strong Scaling

Strong scaling keeps the problem size fixed and increases the number of processing units.

Example:
- The same 1 TB data simulation.
- Run across 8, 16, 32, and 64 nodes.
- Measure completion time and speedup.

Speedup:

\[
S(N) = \frac{T(1)}{T(N)}
\]

Parallel efficiency:

\[
E(N) = \frac{S(N)}{N}
\]

Where T(1) and T(N) must be measured with the same workload and under identical comparison conditions.

Strong scaling answers: how much can we shorten runtime by adding resources to the same problem?

### 5.2. Weak Scaling

Weak scaling increases problem size proportionally with the number of processing units, keeping the work per processing unit roughly constant.

Example:
- 1 node processes 10 million elements.
- 8 nodes process 80 million elements.
- 32 nodes process 320 million elements.

If completion time stays nearly constant as total data scales with node count, weak scaling is good.

### 5.3. Comparison

| Characteristic | Strong scaling | Weak scaling |
|---|---|---|
| Total problem size | Fixed | Grows with worker/node count |
| Goal | Reduce completion time | Increase problem size with roughly stable runtime |
| Key quantities | Speedup, efficiency | Runtime at each scale point |
| Common bottlenecks | Sequential fraction, communication, synchronization | Network, storage, partitioning, and global coordination |
| Use case | Shortening a specific simulation or analysis | Larger simulations, higher resolution |

### 5.4. When Does Strong Scaling Stop Paying Off?

If each node ends up processing only a tiny amount of data, initialization, communication, and synchronization overhead can dominate runtime. Adding nodes yields negligible speedup or even slows the program down.

The practical stopping point is where runtime savings or scale gains no longer offset resource and operational costs.

## 6. Parallelization Overhead

### 6.1. Communication Overhead

Workers need to exchange data:
- Sending inputs and receiving outputs.
- Exchanging boundaries between subdomains.
- Merging results.
- Synchronizing state.
- Distributing metadata and tasks.

Communication overhead depends on message size, message frequency, network topology, latency, and bandwidth.

### 6.2. Latency and Bandwidth

- **Latency:** time for a communication operation to begin producing results.
- **Bandwidth:** volume of data that can be transmitted per unit of time.

A workload sending many small messages can be latency-bound. A workload transferring large blocks can be bandwidth-bound.

Therefore, increasing network bandwidth does not solve everything. If the algorithm performs too many synchronous communication rounds, latency can remain the bottleneck.

### 6.3. Synchronization Overhead

Barriers or collective operations require workers to wait for one another. Even the fastest worker must wait for the slowest worker at the synchronization point.

Causes include:
- Uneven workload distribution.
- Nodes with differing performance.
- One partition containing more data.
- Slow I/O on one worker.
- Network congestion.
- One node experiencing contention.

Reducing barrier frequency and choosing sensible synchronization boundaries can improve performance.

### 6.4. Load Imbalance

If one worker receives 10% of the data yet takes 50% of the time to process it, the remaining workers sit waiting.

Imbalance can be reduced by:
- Static partitioning when workload cost is uniform and predictable.
- Dynamic scheduling when individual task runtimes are hard to predict.
- Work stealing when supported by the framework.
- Splitting tasks smaller for redistribution.
- Estimating task cost prior to scheduling.

Tasks that are too small inflate scheduling overhead; tasks that are too large hurt load-balancing flexibility.

### 6.5. Contention and False Sharing

In shared-memory parallelism:
- Multiple threads can contend for the same lock.
- Multiple cores can contend for memory bandwidth.
- False sharing occurs when threads update distinct variables that reside on the same cache line, increasing cache coherence traffic.
- NUMA remote memory access can be slower than local memory access.

Increasing thread count without analyzing memory locality can reduce throughput.

### 6.6. I/O Bottlenecks

A program can compute in parallel very well yet be limited by:
- Reading data from object storage.
- Many nodes concurrently reading one large file.
- The metadata server of a parallel file system.
- Concurrent checkpoint writes.
- Serialization or output aggregation phases.

Measure CPU time, memory stalls, network, and I/O separately. Adding CPUs when storage is already saturated rarely helps.

## 7. Parallel Programming Models

### 7.1. Shared-Memory Threading

Multiple threads run within a single process and share an address space.

Technology examples:
- POSIX threads.
- OpenMP.
- Runtime thread pools.
- Language task runtimes.

Advantages:
- Direct data sharing.
- Fast inter-thread communication.
- Well-suited for intra-node scale-up.

Challenges:
- Race conditions.
- Lock contention.
- Deadlocks.
- Memory visibility.
- False sharing.
- Hard to scale beyond a single node's limits.

### 7.2. Message Passing

Processes have private memory and exchange messages via a library or runtime. MPI is the standard model in HPC clusters.

Advantages:
- Scales across multiple nodes.
- Explicit data boundaries.
- Suits domain-partitioned simulations.

Challenges:
- Must serialize or pack data.
- Communication latency.
- Deadlocks from send/receive ordering.
- Synchronization and handling process failures.
- Difficult to debug when bugs only manifest at large scale.

### 7.3. GPUs and Accelerators

GPUs have many parallel execution units, fitting operations with vast independent elements and regular data structures.

GPUs are typically effective when:
- There is ample parallel work.
- Data can stay on the device long enough.
- Memory accesses have strong locality/coalescing.
- Host-device transfer overhead does not dominate.
- Kernels are large enough to amortize launch overhead.

Not every algorithm suits GPUs. Tasks with heavy branching, sequential dependencies, or small datasets may fail to achieve expected gains.

### 7.4. Hybrid MPI + OpenMP + GPU

A node can run multiple MPI ranks, with each rank using multiple OpenMP threads and one or more GPUs.

Illustrative configuration:
- 4 MPI ranks per node.
- Each rank uses 8 OpenMP threads.
- Each rank binds to one GPU.

Total CPU threads and GPUs must align with physical topology. If each rank spawns too many threads, oversubscription and memory contention can occur.

### 7.5. Distributed Data Frameworks

Some workloads do not need MPI directly. A distributed framework can:
- Split data into partitions.
- Schedule tasks.
- Manage shuffles.
- Retry failed tasks.
- Cache intermediate data.
- Aggregate results.

Frameworks reduce coordination boilerplate but do not eliminate network, serialization, skew, and storage costs.

## 8. Choosing Scale-Up vs. Scale-Out by Workload Traits

### 8.1. Workloads Needing Large Shared Memory

If an algorithm requires many threads accessing shared data structures and is hard to partition, a large node with high RAM may be appropriate.

Examples:
- Graph analytics with heavy random access.
- Certain simulation models holding global state.
- In-memory databases or solvers requiring shared memory.

Measure memory bandwidth, NUMA locality, and lock contention; increasing RAM capacity alone will not solve a bandwidth bottleneck.

### 8.2. Partitionable Workloads

If data can be split into blocks or subdomains and each node processes its own slice, scale-out can be effective.

Examples:
- CFD simulations dividing a spatial grid.
- Tiled image analysis.
- Partitioned data processing.
- Per-frame rendering.
- Multi-parameter model runs.

Evaluate boundary data volume and exchange frequency between partitions.

### 8.3. Compute-Bound Workloads

Compute-bound means runtime is primarily capped by arithmetic capacity. If the parallel compute fraction is high, adding cores or GPUs can yield benefits.

Check:
- CPU/GPU utilization.
- Instruction throughput.
- Vectorization.
- Kernel occupancy.
- Arithmetic intensity.
- Memory wait time.

### 8.4. Memory-Bound Workloads

Memory-bound means the workload is capped by memory access speed or latency.

Adding cores may not help if cores contend for the same memory bandwidth. Check:
- Memory bandwidth.
- Cache misses.
- Memory locality.
- NUMA placement.
- Working set size.
- Data layout and vectorization.

Scaling up to a node with higher memory bandwidth or refactoring data layout can help more than adding nodes.

### 8.5. Communication-Bound Workloads

If every compute step requires frequent inter-node data exchanges, scale-out may scale poorly. You need to:
- Reduce communication rounds.
- Coalesce small messages.
- Increase the compute-to-communication ratio.
- Choose a low-latency/high-bandwidth network.
- Place nodes close together topologically if the platform supports it.
- Reduce global synchronization.

### 8.6. Workloads with Many Independent Jobs

If there are many independent jobs, scaling out by job count is usually simpler than splitting a single job across multiple nodes.

Examples:
- 500 simulation parameter sets.
- 10,000 files to process.
- Multiple independent model trainings.
- Multiple batch inference jobs.

The scheduler can run each job on a single node or a small group of nodes. In that scenario, optimize cluster throughput, fairness, queue wait, and cost rather than single-job speedup alone.

## 9. Designing Data Partitioning

### 9.1. Domain Decomposition

In physics or scientific simulations, the problem domain is divided into subdomains. Each node computes one part and exchanges boundary data with neighboring nodes.

Example:
- A 3D grid split along the X/Y/Z axes.
- Each node updates its interior cells.
- At each timestep, nodes exchange halo/ghost cells with neighboring nodes.
- After exchanging, nodes proceed to the next compute step.

If subdomains have sides that are too small, the halo-to-interior ratio rises and communication overhead grows. If too large, fewer nodes are used and available capacity may go underutilized.

### 9.2. Key/Range Data Partitioning

For data workloads:
- Key partitioning speeds up key-based lookups.
- Range partitioning preserves contiguous data.
- Hash partitioning distributes evenly if keys are well distributed.
- Tenant partitioning isolates load.

Check for data skew. One hot key or partition can make one worker run far slower than others.

### 9.3. Replication and Shared Data

Some workloads require many nodes to read the same data. Options include:
- Replicating inputs to local storage.
- Using a parallel file system.
- Caching data on nodes.
- Using object storage with a matching request pattern.

Replication increases storage footprint and transfer cost; shared storage can bottleneck when many nodes read/write concurrently. Choose based on data size, locality, and I/O patterns.

## 10. Networking and Topology for Scale-Out HPC

### 10.1. Why Does Networking Matter?

In an HPC cluster, the network directly impacts:
- MPI point-to-point communication.
- Collective operations such as all-reduce.
- Halo exchanges between subdomains.
- Distributed training gradient synchronization.
- Parallel storage access.
- Checkpoints and intermediate data.

High network bandwidth moves large data volumes, while low latency cuts the cost of frequent small messages. Both matter for communication-heavy workloads.

### 10.2. Ethernet and High-Performance Interconnects

Standard Ethernet satisfies many workloads, particularly when communication is not the bottleneck. Latency-sensitive MPI or distributed training workloads can benefit from HPC interconnects such as InfiniBand or cloud-supported Ethernet/RDMA solutions.

Verify:
- Actual measured latency and bandwidth.
- RDMA or equivalent capability.
- MPI/runtime support.
- Node placement and topology.
- MTU and network configuration.
- Instance family and region compatibility.

Do not assume simply picking a high-bandwidth instance lets MPI automatically use RDMA. Drivers, libraries, images, schedulers, and platform settings must all align.

### 10.3. Placement and Locality

Placing nodes physically close together in the infrastructure lowers latency and stabilizes network performance. Some clouds offer placement groups, cluster placement, or dedicated HPC instance types.

In exchange, capacity may be scarcer and scale may be bounded by a single placement zone. Check quotas and node availability before launching large jobs.

## 11. Storage and Checkpointing in Distributed Workloads

### 11.1. Parallel File Systems

Parallel file systems allow multiple nodes to access shared data at high aggregate throughput when configured to match the workload.

Suitable for:
- Simulations reading/writing large files.
- Multiple nodes checkpointing concurrently.
- Large scientific datasets.
- Workloads needing shared filesystem semantics.

Inspect metadata operations, file counts, stripe sizes, locking, and concurrent client counts. Many small files can overload metadata servers even when raw bandwidth remains free.

### 11.2. Object Storage

Object storage suits large inputs/outputs, artifacts, long-term checkpoints, and finished results. However, its access patterns and semantics differ from filesystems.

Best practices:
- Use multipart uploads/downloads where appropriate.
- Batch small files if request overhead is high.
- Avoid multiple workers overwriting the same object key concurrently.
- Use manifests to track output partitions.
- Check SDK consistency and retry semantics.
- Use checksums to verify data integrity.

### 11.3. Distributed Checkpointing

Long-running jobs can checkpoint state to resume after node failures or time limits. In multi-node environments, a checkpoint must represent a consistent global state of the entire job.

Steps:
1. Synchronize workers at a safe point.
2. Write local or distributed state.
3. Record metadata on version, partitions, and iteration.
4. Complete all writes and verify them.
5. Publish the checkpoint manifest as a valid recovery point.

Never mark a checkpoint complete when only a subset of nodes has finished writing. When restoring, you must know exactly which files belong to the same checkpoint generation.

## 12. Measuring Performance and Scaling Efficiency

### 12.1. Baseline

Before scaling, measure the baseline:
- Runtime.
- CPU/GPU utilization.
- Memory usage and bandwidth.
- I/O throughput and latency.
- Network bytes/messages.
- Worker/node count.
- Output results and accuracy.

Never compare two configurations if inputs, code versions, compiler flags, or data conditions differ without documenting them.

### 12.2. Speedup

Speedup measures how many times faster a program runs compared to the baseline:

\[
S(N) = \frac{T(1)}{T(N)}
\]

Example:
- 1 node: 120 minutes.
- 4 nodes: 36 minutes.
- Speedup = 120/36 ≈ 3.33×.

Moving from 1 to 4 nodes gives an ideal speedup of 4×. Parallel efficiency is 3.33/4 ≈ 83.3%.

### 12.3. Parallel Efficiency

\[
E(N) = \frac{S(N)}{N}
\]

Efficiency indicates the proportion of ideal scaling achieved relative to resource growth. Low efficiency can stem from sequential portions, communication, synchronization, load imbalance, I/O, or contention.

Efficiency is not the sole metric for choosing a configuration. A job with lower efficiency at 64 nodes can still be economical if it finishes fast enough and meets budget constraints.

### 12.4. Cost Efficiency

Track:
- Cost per completed job.
- Cost per simulation timestep.
- Cost per processed TB.
- Cost per training epoch.
- Node-hours or GPU-hours.
- Queue wait time and cluster utilization.

A larger configuration may shorten runtime while raising total cost. Compare cost-to-solution: the total cost to produce a valid result within the required timeframe.

## 13. Architecture and Configuration Selection Process

1. Define the objective: shorten a single job or increase problem size.
2. Measure the baseline and profile the code.
3. Estimate the sequential and parallelizable fractions.
4. Identify whether the workload is compute-bound, memory-bound, I/O-bound, or communication-bound.
5. Test scale-up on a node with appropriate cores, RAM, memory bandwidth, or GPUs.
6. Test scale-out across progressively larger node counts.
7. Measure speedup, efficiency, communication, and cost.
8. Inspect data partitioning, load balance, and checkpointing.
9. Identify the scale-out point where diminishing returns begin.
10. Select the configuration meeting SLO and cost-to-solution targets.
11. Archive benchmarks, versions, inputs, and configurations for reproducibility.

~~~mermaid
flowchart TD
    A["Define goals and workload"]
    B["Profile baseline"]
    C["Find sequential parts and bottlenecks"]
    D{"Is shared memory or single node the limit?"}
    E["Test scale-up"]
    F["Partition data and algorithm"]
    G["Test scale-out"]
    H["Measure speedup, efficiency, network, and I/O"]
    I["Compare cost-to-solution"]
    J["Select config and save benchmark"]
    A --> B --> C --> D
    D -->|Yes| E --> H
    D -->|No| F --> G --> H
    H --> I --> J
~~~

## 14. Example: 3D Domain Decomposition Simulation

A CFD simulation updates 1 billion cells on a 3D grid. Each cell needs neighbor values for the next timestep.

### 14.1. Single-Node Scale-Up

Running on a many-core single node:
- Split the grid into tiles across threads.
- Use shared memory to exchange data within the node.
- Optimize NUMA placement.
- Leverage vectorization and high memory bandwidth.

The advantage is avoiding inter-node halo exchanges over the network. The limits are RAM capacity, bandwidth, and core count of a single machine.

### 14.2. Multi-Node Scale-Out

Splitting the grid into subdomains:
- Each node owns a portion of the cells.
- Each node updates its interior cells.
- At each timestep, nodes exchange halo/ghost cells with neighbors.
- After exchanging, nodes advance to the next step.

If subdomain edges are too small, halos become a large fraction of the data. As node count rises, compute per node shrinks while communication rounds still occur every timestep.

### 14.3. Evaluation

Measure at 1, 2, 4, 8, and 16 nodes:
- Interior compute time.
- Halo exchange time.
- Barrier wait time.
- Network bytes and message counts.
- Memory bandwidth.
- Total time per timestep.

If halo exchanges take 35% of runtime at 16 nodes, adding more nodes may yield poor speedup. You can improve scaling by enlarging subdomains, coalescing communication, optimizing topology, or running multiple timesteps before synchronizing if the algorithm permits.

Never alter update order or reduce synchronization if doing so compromises numerical correctness. Verify error bounds and algorithmic stability.

## 15. Scale-Out Risks and Mitigation

### 15.1. Node Failures

A node can fail mid-job. Mitigations:
- Periodic checkpointing.
- Saving state by generation.
- Defining retry/restart policies.
- Checking for incomplete outputs.
- Avoiding overwriting committed results.
- Configuring the scheduler to requeue on node loss.

### 15.2. Stragglers

A worker slower than the rest stalls barriers or DAGs. Track per-partition durations and diagnose root causes: data skew, noisy neighbors, memory pressure, network, or I/O.

### 15.3. Nondeterminism

Addition order in parallel reductions can vary across runs, causing minor discrepancies from floating-point rounding. Some algorithms are also sensitive to update ordering.

Clarify requirements:
- Bitwise reproducible results.
- Results within numerical tolerance.
- Results valid under statistical/business criteria.

If reproducibility is needed, use fixed-order reductions, explicit seeds, and recorded run configurations.

### 15.4. Scheduler and Cluster Contention

Concurrent scale-out jobs can contend for nodes, network, and storage. Mitigations:
- Workload-specific queues and partitions.
- Fair-share or priority policies.
- Reservations for critical jobs.
- Concurrency limits.
- Monitoring node utilization and queue wait times.
- Preventing one job from unnecessarily monopolizing the entire cluster.

## 16. Common Mistakes

**Assuming more cores always make a job faster.** Sequential fractions and overhead cap speedup. Measure Amdahl limits and profile.

**Choosing scale-out before analyzing the algorithm.** If data dependencies are tight or communication is excessive, adding nodes can slow execution down. Optimize decomposition first.

**Measuring only CPU utilization.** Workloads may be capped by memory, network, or storage. Measure all relevant subsystems.

**Confusing speedup with efficiency.** An 8× speedup on 16 nodes is still 50% efficiency. Evaluate both runtime and cost.

**Ignoring load imbalance.** Fast workers sit idle waiting for slow workers at barriers. Measure per-partition timings.

**Splitting tasks too small.** Scheduler and communication overhead can exceed compute cost. Pick appropriate task granularity.

**Using GPUs for every calculation.** Transfers, launches, and memory access patterns can make GPUs ineffective. Benchmark with real kernels and workloads.

**Assuming high network bandwidth is enough.** Workloads with many small messages are sensitive to latency and collective synchronization. Measure latency, message rate, and bandwidth.

**Adding nodes while keeping the same storage bottleneck.** Many nodes reading/writing concurrently can overwhelm filesystems or metadata servers.

**Ignoring NUMA and affinity.** Threads may access remote memory or contend for cores. Pin threads/processes according to topology.

**Inconsistent checkpoints.** Restoring partial node states can produce corrupt job state. Use complete checkpoint generations and manifests.

**Optimizing speedup while forgetting cost-to-solution.** The fastest configuration is not always the most economical. Compare total cost for an acceptable result.

## 17. HPC Scaling Design Checklist

### Workload and Algorithm

- [ ] Define whether the goal is strong scaling or weak scaling.
- [ ] Separate sequential and parallelizable portions.
- [ ] Identify data, task, or pipeline parallelism.
- [ ] Map the dependency graph and synchronization points.
- [ ] Verify correctness under partitioning.

### Scale-Up

- [ ] Measure CPU, core count, memory capacity, and memory bandwidth.
- [ ] Inspect NUMA, affinity, and memory locality.
- [ ] Evaluate GPUs/accelerators and data transfer costs.
- [ ] Measure contention, locks, and false sharing.
- [ ] Identify single-node capacity limits.

### Scale-Out

- [ ] Select data partitioning and load-balancing strategies.
- [ ] Measure communication latency, bandwidth, and message counts.
- [ ] Inspect network/interconnect and topology.
- [ ] Check storage throughput and metadata workloads.
- [ ] Implement checkpointing, restart, and node failure handling.
- [ ] Verify quotas, placement, and scheduler capacity.

### Benchmarks and Cost

- [ ] Save baseline metrics and benchmark conditions.
- [ ] Measure speedup and parallel efficiency.
- [ ] Run strong scaling and weak scaling where appropriate.
- [ ] Monitor I/O, network, synchronization, and stragglers.
- [ ] Compare cost-to-solution and completion time.
- [ ] Identify the cutoff where adding resources stops paying off.

## 18. Key Takeaways

- Scale-up increases resources within a single node; scale-out adds nodes and distributes work.
- HPC workloads commonly combine intra-node threads/GPUs with inter-node message passing.
- Sequential fractions, data dependencies, and communication costs must be analyzed before scaling.
- Amdahl's Law models speedup limits for fixed-size problems; Gustafson's Law models problems scaling with resources.
- Strong scaling keeps problem size constant; weak scaling grows problem size with worker count.
- Communication, synchronization, load imbalance, memory, and I/O can erase the benefits of adding nodes.
- Data parallelism, task parallelism, and pipeline parallelism fit different workload structures.
- Scale-out is effective when data is partitionable and coordination overhead stays controlled.
- HPC requires measuring both network latency and bandwidth alongside topology and interconnects.
- Distributed checkpoints must represent a consistent state of the entire job.
- Choose configurations based on speedup, efficiency, completion time, and cost-to-solution.

## Glossary

| Term | Meaning |
|---|---|
| Scale-up | Increasing resources on a single node or moving to a larger node. |
| Scale-out | Increasing node count and distributing a workload across multiple nodes. |
| Parallelism | Ability to execute multiple parts of work concurrently. |
| Serial fraction | Proportion of work that cannot execute in parallel under the evaluated model. |
| Amdahl's Law | Model estimating speedup limits for a fixed-size problem. |
| Gustafson's Law | Speedup model when problem size scales with processing unit count. |
| Strong scaling | Increasing resources while keeping problem size fixed. |
| Weak scaling | Scaling problem size proportionally with processing unit count. |
| Speedup | Ratio of baseline runtime to runtime on the new configuration. |
| Parallel efficiency | Speedup divided by the number of processing units used. |
| Data parallelism | Dividing data into parts to run the same operation in parallel. |
| Task parallelism | Running distinct tasks concurrently. |
| Pipeline parallelism | Splitting a workflow into stages processing different items simultaneously. |
| Embarrassingly parallel | Workload with nearly independent parts requiring minimal communication. |
| Domain decomposition | Splitting a problem domain into subdomains distributed across workers/nodes. |
| Halo/ghost cells | Boundary data exchanged between subdomains in simulations. |
| Communication overhead | Time and resource cost to exchange data between workers. |
| Synchronization | Coordinating execution timing or state across workers. |
| Load imbalance | Uneven work distribution forcing some workers to wait. |
| NUMA | Memory access architecture where latency/bandwidth depend on memory node locality. |
| False sharing | Threads updating separate variables on the same cache line, causing cache coherence traffic. |
| MPI | Message Passing Interface, standard for inter-process message communication in HPC. |
| OpenMP | API supporting shared-memory parallelism via compiler directives and runtime. |
| RDMA | Remote Direct Memory Access, remote memory access mechanism with low CPU overhead when supported. |
| Collective operation | Group communication operation such as broadcast, reduce, or all-reduce. |
| Straggler | Worker or partition running slower than the rest and delaying completion. |
| Checkpoint | Saved state used to recover or resume a job. |
| Cost-to-solution | Total cost to complete a problem to required standards. |

# HPC Workloads and Differences from Typical Web Services

High-Performance Computing (HPC) uses multiple CPU cores, GPUs, accelerators, memory, and high-speed networking to solve large computational problems within a reasonable time. Typical workloads include aerodynamic simulations, computational fluid dynamics, weather forecasting, molecular modeling, seismic analysis, materials simulation, scientific model training, and large-scale data processing.

HPC is organized differently from a typical web service. Web services usually receive many independent requests, optimize per-request latency, and scale by adding replicas. HPC typically runs a job consisting of many coordinated processes or workers across a set of nodes; performance depends on how well computations can be partitioned, data exchanged, synchronized, and resources utilized concurrently. Adding nodes does not necessarily make a job faster if communication or sequential portions become the bottleneck.

This lesson introduces HPC workload characteristics, parallelism models, CPU/GPU and node layouts, the roles of networking and storage, and performance metrics. After this lesson, you will be able to:

- Distinguish between HPC, web services, batch processing, and high-throughput computing.
- Identify compute-bound, memory-bound, communication-bound, and I/O-bound problems.
- Choose the appropriate parallelism model: shared-memory, distributed-memory, task parallelism, and data parallelism.
- Explain the roles of MPI, OpenMP, GPUs, and accelerators.
- Understand strong scaling, weak scaling, speedup, efficiency, and Amdahl's Law.
- Evaluate latency, bandwidth, FLOPS, memory bandwidth, IOPS, and job completion time.
- Select cloud compute, interconnect, storage, and scheduler configurations based on workload characteristics.
- Design benchmarks and profiling to locate bottlenecks before scaling out a cluster.

## 1. What Is HPC and What Types of Problems Does It Solve?

HPC focuses on completing a large computation or a set of scientific/engineering tasks by exploiting multiple resources in parallel. A job can run on a multi-socket machine, a multi-GPU node, or hundreds of nodes linked by a high-speed network.

Examples:

- **Fluid simulation:** divides space into grid cells; each process computes a subdomain and exchanges boundary values with neighboring processes.
- **Weather forecasting:** computes over spatial and temporal grids, iterating through multiple model steps; typically requires strong CPU/GPU performance, memory bandwidth, and interconnect.
- **Molecular simulation:** computes forces between particles or molecules; can use GPUs and algorithms that reduce the number of interactions.
- **Seismic analysis:** processes large data arrays, performs parallel reads/writes, and computes matrices.
- **Materials simulation:** uses numerical methods or quantum models; may require large memory, heavy linear algebra operations, and MPI communication.
- **Scientific model training:** distributes tensors and data across multiple GPUs; performance depends on compute, GPU memory, and gradient synchronization.

The common traits are high computational volume, the ability to divide work into parallel parts, and criteria for measuring completion time or result accuracy.

### HPC, Web Services, and High-Throughput Computing

| Characteristic | HPC job | Web service | High-throughput computing (HTC) |
|---|---|---|---|
| Unit of work | A large job or a group of coordinated processes | Request or user session | Many relatively independent jobs |
| Primary goal | Reduce completion time for a large computation | Respond to requests quickly and reliably | Complete many jobs within a given time window |
| Parallelism | Often requires intra-job coordination | Typically distributes requests across replicas | Distributes independent jobs across workers |
| Communication | MPI, collectives, shared memory, interconnect | HTTP/gRPC, cache, database | Queue, object storage, scheduler |
| Resources | CPU/GPU, memory bandwidth, network latency/bandwidth | Per-request CPU/RAM, network, and dependencies | Total throughput and cost per job |
| Orchestration | Batch scheduler, job allocation, topology-aware placement | Load balancer, autoscaler, orchestrator | Queue/scheduler, worker pool |
| Metrics | Time-to-solution, speedup, efficiency, FLOPS | p95/p99 latency, RPS, error rate | Jobs/hour, queue age, cost/job |

A system can combine these models. For example, an API receives simulation requests and places jobs into a queue; a web service manages job status, while an HPC cluster executes the computation. You should not apply the same autoscaling mechanism to both the API and the HPC jobs if they have different resource usage patterns.

## 2. Characteristics of HPC Workloads

Before choosing machines, identify which resource type limits the workload. The same number of CPU cores can yield very different results if one application requires heavy arithmetic, another needs continuous data reads, and another frequently exchanges data between nodes.

### Compute-bound

Compute-bound workloads spend most of their time executing arithmetic operations on the CPU or GPU. Examples include certain linear algebra kernels, numerical simulations, and signal processing. Key metrics to inspect include FLOPS, IPC, vectorization, utilization, clock behavior, and kernel duration.

Increasing core count or using GPUs can improve performance if the algorithm parallelizes well and data is supplied fast enough. If the kernel is limited by sequential dependencies or instruction latency, adding cores will not bring proportional gains.

### Memory-bound

Memory-bound workloads spend more time waiting for data from RAM than performing arithmetic. Applications traversing large arrays, sparse matrices, or non-contiguous memory accesses can be limited by memory bandwidth, cache misses, and NUMA locality.

Factors to examine:

- Memory bandwidth per socket or node.
- RAM capacity and working set size.
- Cache hit/miss rates and memory access patterns.
- NUMA placement and first-touch policy.
- Number of memory channels and DIMM speeds per instance configuration.

Adding CPU cores without increasing memory bandwidth can cause more cores to contend for the same resource.

### Communication-bound

Communication-bound workloads spend substantial time exchanging data between processes or nodes. Examples include domain-decomposed simulations, distributed training, and algorithms with frequent collective communication.

Network latency, bandwidth, topology, synchronization frequency, and message size can determine performance. A cluster with high FLOPS but a weak interconnect can still run slowly if processes constantly wait on one another.

### I/O-bound

I/O-bound workloads wait on reading or writing data to storage. Pipelines reading checkpoints, scientific datasets, or large outputs can be limited by throughput, IOPS, metadata operations, and large numbers of small files.

Distinguish between:

- Sequential throughput when reading/writing large files.
- IOPS and latency for many small or random operations.
- Metadata throughput when opening/closing vast numbers of files.
- Concurrent access capability across multiple nodes.
- Checkpoint and recovery times.

### Mixed Workloads

Many applications shift bottlenecks across phases. A job may be compute-bound during the equation-solving step, communication-bound during synchronization, and I/O-bound when writing checkpoints. Therefore, profile by phase rather than labeling a workload from a single overall metric.

## 3. Fundamental Parallelism Models

Parallelization means splitting a problem into parts that can execute concurrently while managing data dependencies and combining results. Not every computation can be partitioned arbitrarily.

### Data Parallelism

The same operation is performed across different portions of data. For example, splitting a matrix into blocks; each worker processes one portion and then combines the results. Data parallelism suits vector/matrix operations, image processing, grid simulations, and many machine learning workloads.

### Task Parallelism

Different tasks execute concurrently. For example, a pipeline has stages for data reading, preprocessing, simulation, and writing results; certain stages can overlap if they are not strictly dependent on one another.

### Shared-Memory Parallelism

Multiple threads run on cores within the same node and access a shared memory space. This approach generally has lower exchange overhead than inter-node communication, but requires managing race conditions, lock contention, false sharing, and locality.

OpenMP is a common model for shared-memory parallelism in C/C++ and Fortran. Threads can split loops or compute regions into parts that run in parallel.

### Distributed-Memory Parallelism

Each process has its own private memory space, typically running on a node or a group of cores. Processes exchange data via message passing, most commonly MPI in many HPC applications.

Distributed memory enables scaling across many nodes and aggregating cluster-wide memory, but communication and synchronization costs must be factored into the algorithm.

### Hybrid Parallelism

An application can combine MPI across nodes with OpenMP within each node, or MPI with GPU kernels. For example, each node runs one MPI rank; each rank uses multiple CPU threads and drives one or more GPUs. The hybrid model helps utilize intra-node resources and reduce the number of MPI processes, but ranks/threads must be placed in alignment with the topology.

~~~mermaid
flowchart TD
    J["An HPC job"] --> N1["Node 1"]
    J --> N2["Node 2"]
    N1 --> M1["MPI rank 0"]
    N1 --> M2["MPI rank 1"]
    N2 --> M3["MPI rank 2"]
    N2 --> M4["MPI rank 3"]
    M1 --> T1["OpenMP threads"]
    M2 --> T2["OpenMP threads"]
    M3 --> T3["OpenMP threads"]
    M4 --> T4["OpenMP threads"]
    M1 --> G1["GPU kernel"]
    M3 --> G2["GPU kernel"]
~~~

## 4. MPI, OpenMP, and Inter-Process Communication

### MPI

Message Passing Interface (MPI) is a programming standard that allows processes to exchange data. Common operations include:

- Point-to-point: sending/receiving messages between two ranks.
- Broadcast: one rank sends data to multiple ranks.
- Reduce: combines values from multiple ranks into a result.
- All-reduce: all ranks participate in the combine operation and receive the result.
- All-to-all: exchanges data between many pairs of ranks.
- Barrier: ranks wait for one another at a synchronization point.

Collective operations are convenient but can become bottlenecks if called too frequently or with large messages. When one rank runs slower, other ranks may be forced to wait at the collective.

### OpenMP

OpenMP provides directives and a runtime to divide code regions into threads. A common pattern is parallelizing independent loops:

~~~c
#include <omp.h>
#include <stddef.h>

void scale(double *a, size_t n, double factor) {
    #pragma omp parallel for
    for (size_t i = 0; i < n; ++i) {
        a[i] *= factor;
    }
}
~~~

This example is only suitable when each iteration writes to a distinct element and there are no dependencies between iterations. If multiple threads update a shared variable, an appropriate reduction or synchronization mechanism is required.

### MPI + OpenMP

Hybrid MPI/OpenMP typically partitions the data domain across ranks, then further divides each rank's domain among threads. Avoid oversubscription: the total number of threads created should not exceed the CPU cores allocated to the job unless explicitly intended.

For example, a node allocated 32 CPU cores might run 2 MPI ranks with 16 OpenMP threads each. This is only an initial baseline configuration; the optimal rank/thread split depends on cache, NUMA, data size, and communication patterns.

### GPU Programming

GPUs suit operations with massive element-level independence and enough work to amortize data transfer, kernel launch, and synchronization overhead. Common platforms include CUDA, HIP, OpenCL, SYCL, and high-level frameworks.

To achieve strong GPU performance:

- Keep data on the device long enough to minimize host-device transfers.
- Ensure kernels have sufficient parallel work and proper memory access coalescing.
- Avoid overly frequent CPU-GPU synchronization.
- Monitor GPU utilization, memory utilization, memory bandwidth, and kernel duration.
- Verify compatible drivers, runtimes, math libraries, and framework versions.

GPUs do not automatically speed up every application. Workloads with low parallelism, heavy branching, or continuous small data transfers may see no benefit from moving to GPUs.

## 5. Problem Partitioning and Data Exchange

A parallel algorithm must decide how to partition data, assign work, and combine results.

### Domain Decomposition

For spatial simulations, domain decomposition splits a grid into subdomains. Each MPI rank computes one subdomain, then exchanges halo/ghost cells at boundaries to update the next step.

Subdomain size affects the compute-to-communication ratio. If each rank holds only a tiny subdomain, the ratio of boundary data to interior data increases and exchange time can dominate.

### Partitioning and Load Balance

Work units should have roughly equal cost, or the scheduler should support dynamic distribution. If one rank handles a much more complex region, the remaining ranks will sit idle waiting at barriers or collectives.

Static partitioning works well when the cost of each part is predictable. Dynamic scheduling is useful when tasks have uneven execution times, though it introduces coordination overhead and can reduce locality.

### Overlapping Computation and Communication

Some MPI applications can use non-blocking communication to initiate data transfers and continue computing parts that do not depend on the in-flight data. Once the transfer completes, the application processes the boundary regions. Overlapping only pays off if the compute phase is long enough and the implementation/network stack supports efficient communication progression.

### Synchronization and Race Conditions

Barriers, locks, atomic operations, and collectives all carry overhead. Synchronizing too often reduces parallelism; incorrect synchronization causes race conditions, deadlocks, or wrong results. Data ownership and dependencies between steps must be clearly defined.

## 6. HPC Performance Metrics

HPC requires more metrics than CPU utilization. A job can show 100% CPU usage and still underperform due to memory stalls or rank imbalance.

| Metric | Meaning | When to monitor |
|---|---|---|
| Time-to-solution | Time from job start to a valid result | Primary metric for a job |
| Throughput | Number of jobs or work units completed over a period | Clusters running many jobs |
| FLOPS | Floating-point operations per second | Arithmetic compute kernels |
| Speedup | Ratio of sequential execution time to parallel execution time | Evaluating scaling |
| Parallel efficiency | Speedup divided by the number of processing elements | Evaluating resource utilization efficiency |
| Memory bandwidth | Data transfer rate between RAM and CPU/GPU | Memory-bound workloads |
| Network latency | Time to send/receive a small message | MPI communication with many messages |
| Network bandwidth | Volume of data transferred per second | Large messages and collectives |
| IOPS / storage throughput | Operations or bytes read/written per second | Checkpoints and datasets |
| Queue wait time | Time a job waits before receiving resources | Cluster user experience |
| Cost per solution | Compute/storage/network cost per valid result | Cloud cost optimization |

### FLOPS and Theoretical Limits

FLOPS measures floating-point operations per second. Peak FLOPS of a CPU/GPU is a theoretical ceiling based on core count, vector width, clock speed, and operations per cycle. Applications typically achieve lower numbers due to memory access, instruction dependencies, branching, communication, synchronization, and sequential sections.

Do not compare two systems solely by peak FLOPS. Measure sustained performance with representative kernels and datasets.

### Latency and Bandwidth

Latency is the time for an operation or message to start/complete according to a specific measurement method. Bandwidth is the amount of data transferred per unit of time. An application sending many small messages is usually latency-sensitive; an application exchanging fewer, very large messages is usually bandwidth-sensitive.

A high-bandwidth network is not necessarily suitable if latency or topology fails to match the communication pattern. Conversely, a low-latency network with low bandwidth can bottleneck large tensor or halo exchanges.

## 7. Speedup, Efficiency, and Amdahl's Law

### Speedup

Speedup compares execution time on a reference resource against execution time using multiple resources:

\[
S(N) = \frac{T(1)}{T(N)}
\]

Where \(T(1)\) is the runtime with one processing element under the chosen baseline; \(T(N)\) is the runtime with \(N\) processing elements.

For example, a job runs in 100 minutes on 1 node and 30 minutes on 4 nodes:

\[
S(4) = \frac{100}{30} \approx 3.33
\]

The ideal speedup is 4x, while the measured result reaches about 3.33x.

### Parallel Efficiency

Parallel efficiency:

\[
E(N) = \frac{S(N)}{N}
\]

With a speedup of 3.33 on 4 nodes:

\[
E(4) = \frac{3.33}{4} \approx 83.3\%
\]

Efficiency reveals the fraction of resources lost to sequential sections, communication, synchronization, imbalance, or overhead.

### Amdahl's Law

If the sequential portion accounts for fraction \(s\), and the remainder can be parallelized, the maximum speedup with \(N\) processing elements in a simplified model is:

\[
S(N) = \frac{1}{s + \frac{1-s}{N}}
\]

For example, if 10% of a program cannot be parallelized, even with a huge number of cores, speedup remains capped by the sequential fraction:

\[
\lim_{N \to \infty} S(N) = \frac{1}{s} = 10
\]

This law explains why adding cores cannot accelerate execution indefinitely. To improve scaling, optimize sequential portions, reduce synchronization, and minimize communication.

### Gustafson's Law

For workloads where the problem size grows with the number of processing elements, Gustafson's Law describes scaling by keeping runtime roughly constant while solving a larger problem:

\[
S_G(N) = N - s(N-1)
\]

Where \(s\) is the sequential fraction measured relative to the parallel runtime. This is a useful perspective for running larger simulations as more resources become available, rather than running the exact same input on more cores.

## 8. Strong Scaling and Weak Scaling

### Strong Scaling

Strong scaling keeps the problem size fixed, increases the number of processing elements, and measures completion time. The goal is to solve the same problem faster.

As node count grows, the computation per node shrinks, while communication, synchronization, and initialization overhead may not decrease proportionally. Consequently, efficiency typically degrades when scaling out too far.

### Weak Scaling

Weak scaling increases the problem size proportionally with the number of processing elements, keeping the workload per processing element nearly constant. The goal is to solve a larger problem in roughly the same time.

Weak scaling fits simulations that can expand their spatial domain or resolution. If runtime increases as node count grows, there may be communication overhead, contention, or I/O bottlenecks.

| Measurement | Problem size | Resource count | Goal |
|---|---|---|---|
| Strong scaling | Fixed | Increases | Reduce time-to-solution |
| Weak scaling | Scales with resources | Increases | Maintain runtime for a larger problem |

Do not compare strong scaling results against weak scaling results as if they were the same test. Document input size, rank/thread/GPU counts, topology, and measurement methodology clearly.

## 9. The Roofline Model and Identifying Compute Limits

The roofline model helps analyze whether an application is limited by compute throughput or memory bandwidth. A key quantity is arithmetic intensity:

\[
AI = \frac{\text{Number of operations}}{\text{Bytes of data moved}}
\]

If arithmetic intensity is low, the workload is likely memory-bandwidth-bound. If arithmetic intensity is high, the workload can approach the compute peak ceiling.

The simplified roofline model expresses approximate maximum attainable performance:

\[
P \le \min(P_{peak}, AI \times BW_{memory})
\]

Where \(P_{peak}\) is peak compute performance and \(BW_{memory}\) is memory bandwidth. Practical modeling must also account for caches, vectorization, instruction mix, and memory hierarchy behavior.

Roofline is not a single metric for hardware purchasing decisions. It helps determine whether to prioritize higher compute capability, better locality, reduced data movement, or algorithmic optimization.

## 10. Selecting CPU, GPU, Memory, and Nodes

### CPU

CPUs suit control logic, algorithms with complex dependencies, branch-heavy workloads, or code not yet ported to accelerators. When selecting an instance, check:

- Physical core count and vCPU count.
- Architecture, CPU generation, and instruction sets.
- Clock behavior under sustained load.
- Socket count, NUMA nodes, and caches.
- Memory channels and memory bandwidth.
- Core-to-price ratio and sustained performance.

Do not simply pick the instance with the most vCPUs. If an application uses OpenMP and is memory-bandwidth-bound, a node with fewer cores but higher RAM bandwidth may run faster.

### GPU and Accelerators

GPUs suit workloads with massive data parallelism and strong library support. Check:

- Number of GPUs, architecture, and framework compatibility.
- VRAM capacity and memory bandwidth.
- Intra-node GPU interconnect.
- Host-to-device transfer and PCIe/NVLink or equivalent topology.
- Drivers, runtimes, compilers, and math libraries.
- Performance at required precision: FP64, FP32, TF32, FP16, BF16, or integer.

A GPU with high FP16 throughput is not necessarily suited for scientific simulations requiring FP64. Choose accelerators based on the precision and accuracy requirements of the algorithm.

### Memory and NUMA

On multi-socket servers, each CPU socket usually has local and remote memory regions. Remote NUMA access can incur higher latency or lower bandwidth than local access. Thread pinning and allocating memory close to the CPU processing the data can improve performance.

Measure working set size, memory bandwidth, cache misses, and NUMA traffic. Inspect first-touch policies and how the runtime allocates threads.

### Single Node or Multi-Node?

A large single node avoids part of the network communication overhead but is bounded by the sockets, RAM, and accelerators within one machine. Multiple nodes provide greater aggregate resources but require a strong interconnect and well-designed distributed algorithms.

Choose the node count using strong/weak scaling benchmarks, not solely by total vCPUs or total GPUs.

## 11. Networking and Interconnect for HPC

HPC networking must support inter-process communication with low latency, high bandwidth, and the ability to handle many concurrent messages. Depending on the cloud provider and instance family, options may include high-speed Ethernet, HPC-optimized network adapters, or RDMA-capable fabrics.

### RDMA

Remote Direct Memory Access (RDMA) enables data transfers directly between machine memories with less CPU involvement than traditional network paths. RDMA can lower latency and CPU overhead for MPI communication, but requires coordinated support across instance type, network fabric, driver, kernel, and MPI library.

Not every high-bandwidth instance supports RDMA or the same semantics. Verify platform documentation for adapters, placement groups/topology, OS images, and supported libraries.

### Latency, Bandwidth, and Topology

For MPI:

- Low latency benefits high-frequency small messages and frequent collectives.
- High bandwidth benefits large messages, halo exchanges, and distributed tensors.
- Good topology reduces hop counts and contention between nodes.
- Close placement can improve communication if the platform provides topology-aware placement.

A cluster should benchmark all-reduce, point-to-point, and patterns close to the real application. Do not run only `iperf` or `ping` and assume MPI will achieve equivalent performance.

## 12. Storage and Data for HPC

HPC jobs may read large datasets, write frequent checkpoints, and produce high-volume outputs. Storage must be selected according to access patterns:

| Data type | Typically suitable storage model | Notes |
|---|---|---|
| Large datasets, read-heavy | Object storage or parallel file storage | Throughput, parallel reads, caching, and request costs |
| Shared input/output files | Parallel file system or shared file system | Metadata rate, concurrent clients, and locking |
| Temporary scratch | Local NVMe or ephemeral disk | High speed, but may be lost when the node stops |
| Checkpoints | Durable object/file storage | Atomic publish, versioning, write and recovery time |
| Final results | Durable object storage or file storage | Retention, integrity, and access permissions |

Never store the only copy of a checkpoint on local NVMe if a node can be terminated or the job may need to restart on a different node. Use local scratch for temporary data and push critical checkpoints/outputs to durable storage.

### Checkpoint and Restart

Long HPC jobs can run for hours or days. Checkpointing saves simulation or computation state so execution can resume after failures, maintenance, or allocation timeouts.

A checkpoint should record sufficient metadata:

- Code and compiler versions.
- Input dataset and parameters.
- Completed steps/time steps.
- Solver, model, or optimizer state.
- Partition scheme and rank/thread counts if compatibility requires them.
- Checksum and version to verify integrity.

Write checkpoints to a new file/key, verify them, and then update the active manifest. Never overwrite a known-good checkpoint before the new one finishes cleanly.

## 13. Batch Schedulers and HPC Resource Management

HPC clusters typically use a batch scheduler to queue jobs and allocate resources. Users specify CPU, memory, GPU, runtime, partition, or queue requirements; the scheduler decides when a job receives nodes.

Common concepts:

- **Job:** unit of work submitted to the cluster.
- **Partition/queue:** group of nodes or allocation policy.
- **Allocation:** resources granted to a job.
- **Task/rank:** process or execution unit within a job.
- **Walltime:** maximum allowed execution duration.
- **Fair-share/priority:** prioritization policy across users or projects.
- **Backfill:** running smaller jobs in schedule gaps without delaying higher-priority planned jobs.

Slurm is a widely used batch scheduler in HPC. An illustrative job script:

~~~bash
#!/bin/bash
#SBATCH --job-name=fluid-sim
#SBATCH --nodes=4
#SBATCH --ntasks-per-node=8
#SBATCH --cpus-per-task=4
#SBATCH --time=02:00:00
#SBATCH --partition=compute
#SBATCH --output=slurm-%j.out

module load compiler mpi
srun ./solver --input case.dat
~~~

This example requests 4 nodes, 8 MPI tasks per node, and 4 CPU threads per task. The total CPUs requested under this configuration is 4 × 8 × 4 = 128 cores/CPU slots depending on how the cluster defines and allocates resources. Ensure physical nodes have enough cores and that application thread settings match the allocation.

### Schedulers vs. Web Autoscalers

Web autoscalers typically react to request rates or replica CPU utilization. An HPC scheduler must grant a consistent allocation for a multi-node job, ensuring simultaneous resources and appropriate topology. Adding nodes to a cluster does not mean a running job automatically receives more nodes; many HPC jobs must be submitted with a fixed node/rank count.

Node pools can autoscale based on scheduler queue depth, but new nodes must join the cluster, load the runtime, and be recognized by the scheduler before jobs are dispatched to them.

## 14. Scheduler Metrics and Cluster Efficiency

Beyond single-job performance, cluster administrators must track utilization and the ability to serve multiple user groups.

| Metric | Meaning |
|---|---|
| Queue wait time | Time from submission until the job starts |
| Job turnaround time | Time from submission until the job completes |
| Utilization | Percentage of resources used over a time interval |
| Throughput | Number of jobs completed per hour/day |
| Node idle time | Time a node is allocated/running without doing useful work |
| Fragmentation | Free resources exist but lack the contiguous configuration needed to place waiting jobs |
| Failed/preempted jobs | Jobs that fail, are stopped, or must be resubmitted |
| Cost per job/result | Cost to complete a job or produce a valid result |

High utilization does not always equal high effectiveness. If jobs wait too long, run too slowly, or produce invalid outputs, the cluster can burn plenty of CPU without delivering timely results.

## 15. Benchmarking and Profiling HPC Workloads

Benchmarks must represent real inputs, algorithms, precision, compilers, and topology. A good microbenchmark can test an isolated component, but it does not replace an end-to-end benchmark.

### Benchmarking Workflow

1. Define the problem, input size, precision, and correctness criteria.
2. Choose a single-node or reference baseline configuration.
3. Pin compiler, flags, libraries, drivers, and code version.
4. Warm up the runtime, caches, or GPUs as appropriate.
5. Measure time per phase: compute, communication, I/O, and checkpointing.
6. Scale up cores, ranks, nodes, or GPUs incrementally.
7. Run strong scaling and weak scaling separately.
8. Repeat enough times to understand variance.
9. Record speedup, efficiency, throughput, cost, and result quality.
10. Profile bottlenecks and change only one parameter group at a time.

### Profiling

Common tool categories:

- CPU profilers to find hot functions, call stacks, and instruction bottlenecks.
- Hardware performance counters to measure cache misses, branches, memory bandwidth, and IPC.
- MPI profilers to inspect message times, collectives, and wait times.
- GPU profilers to measure kernel duration, occupancy, memory transfers, and utilization.
- I/O profilers to measure read/write throughput, metadata operations, and checkpoint times.

When analyzing profiles, separate time spent actively computing from time processes spend waiting on communication or storage. Low CPU utilization in an MPI job may indicate that processes are waiting on other ranks or on I/O.

### What a Benchmark Report Should Include

- CPU/GPU model, node type, node count, and topology.
- Rank, thread, GPU counts, and binding/pinning settings.
- Compiler, MPI, runtime, driver, and library versions.
- Input size, precision, and algorithm parameters.
- Time-to-solution and per-phase breakdown.
- Speedup, parallel efficiency, and strong/weak scaling data.
- Relevant network latency/bandwidth, memory bandwidth, and I/O metrics.
- Number of runs, variance, and environmental conditions.
- Cost per completed result.

## 16. Example: Distributed Fluid Simulation

A fluid simulation application partitions a spatial domain into a 3D grid. Each MPI rank holds a slice of the grid, computes update steps, and exchanges halo cells with neighboring ranks.

Suppose a baseline run on 1 node takes 120 minutes. When scaled to 4 nodes, the job takes 38 minutes:

\[
S(4) = \frac{120}{38} \approx 3.16
\]

\[
E(4) = \frac{3.16}{4} \approx 79\%
\]

The speedup is sublinear. The team needs to profile:

- Ratio of halo exchange time to compute time.
- Message counts and message sizes.
- Wait time at collectives/barriers.
- Load imbalance across grid subdomains.
- Memory bandwidth and NUMA placement.
- Checkpoint and output I/O.

If communication takes a large share, consider increasing subdomain size per rank, reducing synchronization frequency, overlapping compute/communication, or using a lower-latency interconnect. If memory-bound, improve data layout, locality, and vectorization. If load imbalance is high, repartition the domain or use an appropriate partitioning strategy.

Do not immediately conclude that more nodes are needed. Adding nodes can shrink each rank's subdomain and raise the boundary-to-interior exchange ratio, worsening performance.

## 17. Optimizing Performance and Cost on the Cloud

Cloud HPC enables on-demand cluster creation and selection across diverse CPU/GPU types, storage, and interconnects. However, high-performance resources are expensive, and provisioning/startup time is also part of the cost.

### Choosing Configurations by Bottleneck

| Bottleneck | Potential optimization directions |
|---|---|
| Compute-bound | CPUs/GPUs with matching throughput, vectorization, kernel optimization |
| Memory-bound | High RAM bandwidth, locality, NUMA binding, data layout |
| Communication-bound | Low-latency, high-bandwidth interconnect, topology-aware placement, fewer collectives |
| I/O-bound | Parallel storage, batching, caching, reducing small files and metadata operations |
| Load imbalance | Repartitioning, dynamic scheduling, or tuning task granularity |
| Startup/queue delay | Baseline warm capacity, optimized images/boot, scheduler policies, and reservations |

### Cost per Solution

A configuration that costs more per hour can still be cheaper overall if it completes the job significantly faster. The metric to compare is:

\[
CostPerSolution =
\frac{ComputeCost + StorageCost + NetworkCost + OtherCost}
{NumberOfValidResults}
\]

For example, configuration A costs 10 units/hour and runs for 4 hours, giving a total compute cost of 40. Configuration B costs 18 units/hour but finishes in 1.5 hours, giving a total compute cost of 27. If results and accuracy are equivalent, configuration B is more cost-effective despite the higher hourly rate.

Account for wait times, storage, data transfer, licensing, checkpoints, and idle resources. For periodic batch workloads, spinning up clusters before jobs and tearing them down afterward reduces cost, provided logs and outputs are persisted durably.

### Spot/Interruptible Capacity in HPC

Some batch workloads can run on preemptible capacity if they support checkpointing, retries, and scheduler node replacement. However, synchronous multi-node MPI jobs can be severely impacted if a single node is lost; the entire job may have to restart from a checkpoint. Weigh cost savings against rerun time, re-allocation probability, and deadlines.

Never place core orchestration components or stateful storage on preemptible capacity solely for lower pricing.

## 18. Correctness and Reproducibility

HPC optimizes for performance while ensuring scientific/engineering correctness. A change in compiler, precision, summation order, or parallel algorithm can alter outputs because floating-point arithmetic is not strictly associative.

### Determinism and Reproducibility

To ensure reproducibility:

- Record source commits and build artifacts.
- Record compiler, flags, MPI, runtime, drivers, and libraries.
- Save input datasets, seeds, parameters, and precision.
- Save rank/thread/GPU counts and topology configurations.
- Document aggregation methods and numerical tolerances.
- Store checkpoints/outputs with checksums and versions.

Floating-point results across different parallel configurations may exhibit minor differences due to reduction ordering. Define numerical tolerances and scientific acceptance criteria rather than relying strictly on byte-for-byte comparisons when the algorithm does not guarantee determinism.

### Testing

- Unit tests for kernels and core mathematical operations.
- Reference tests using small inputs with known results.
- Regression tests for outputs and tolerances.
- Conservation/invariant checks for physical simulations where applicable.
- Tests across varying rank/thread counts to uncover race conditions or partitioning bugs.
- Restart tests from checkpoints to verify recovery.

## 19. Common Mistakes

1. **Treating HPC like a web service:** using RPS and replica count as primary metrics for multi-node jobs.
2. **Assuming more cores are always faster:** ignoring sequential fractions, communication, and memory bottlenecks.
3. **Looking only at peak FLOPS:** failing to measure sustained performance on real workloads.
4. **Using GPUs for every computation:** overlooking transfers, branching, precision, and parallelism limits.
5. **CPU oversubscription:** spawning more threads/ranks than allocated cores.
6. **Ignoring NUMA and pinning:** letting threads access remote memory or contend for caches.
7. **Mismatched interconnect:** using standard networking for latency-sensitive MPI workloads without benchmarking.
8. **Over-partitioning domains:** inflating the communication-to-computation ratio.
9. **Not measuring load imbalance:** letting a single slow rank stall the entire job.
10. **Keeping checkpoints only on local disk:** losing restart capability when a node is replaced.
11. **Non-reproducible benchmarks:** changing compilers, inputs, or topologies between runs.
12. **Optimizing hourly unit price:** ignoring cost per solution and scheduler queue wait times.

## 20. HPC Workload Design and Evaluation Checklist

- [ ] Problem statement, input size, outputs, and correctness criteria are defined.
- [ ] Workload is identified as compute-bound, memory-bound, communication-bound, or I/O-bound per phase.
- [ ] Appropriate shared-memory, distributed-memory, data/task parallelism, or hybrid model is selected.
- [ ] MPI ranks, OpenMP threads, and GPUs match the resource allocation.
- [ ] CPU/GPU, RAM, NUMA, and precision fit the algorithm.
- [ ] Interconnect satisfies required latency, bandwidth, and topology.
- [ ] Storage satisfies throughput, IOPS, metadata, and checkpoint requirements.
- [ ] Scheduler has suitable queues, partitions, walltimes, and priorities.
- [ ] Durable checkpoints and restart tests are in place.
- [ ] Time-to-solution, speedup, efficiency, and throughput have been measured.
- [ ] Strong scaling and weak scaling have been executed properly.
- [ ] CPU, MPI, GPU, memory, and I/O have been profiled per phase.
- [ ] Benchmark report documents full hardware and software details.
- [ ] Correctness and reproducibility tests are implemented.
- [ ] Cost per solution and resource wait times have been calculated.
- [ ] Cluster cleanup and output preservation policies are in place after job completion.

## 21. Practice Exercise

A science team runs a simulation on a 3D grid. The 1-node baseline takes 90 minutes. On 4 nodes, runtime drops to 30 minutes. Scaling to 8 nodes reduces runtime only to 24 minutes. Profiling shows that 35% of the runtime at 8 nodes is spent in MPI communication and barriers, and memory bandwidth per node is nearly saturated.

1. Calculate speedup and parallel efficiency at 4 nodes and 8 nodes relative to the baseline.
2. Do the results show good strong scaling? Explain.
3. Why did doubling the node count from 4 to 8 not cut the runtime in half?
4. Which factors in domain decomposition, MPI communication, and load balance should be investigated?
5. If the workload is memory-bound, how much can adding CPU cores help?
6. Propose the metrics to collect in the next benchmark run.

Hint: 4-node speedup is 90/30 = 3, efficiency is 3/4 = 75%. 8-node speedup is 90/24 = 3.75, efficiency is 3.75/8 ≈ 46.9%. This is strong scaling because the problem size stays fixed. Communication/barriers and memory bandwidth saturation limit gains as nodes increase. Inspect subdomain size per rank, halo ratio, message counts/sizes, collectives, rank imbalance, NUMA, and memory access patterns. Track time-to-solution, phase times, MPI wait time, network latency/bandwidth, memory bandwidth, cache misses, and cost per solution.

## Conclusion

HPC solves large computational problems by coordinating CPUs, GPUs, memory, networking, and storage across one or more nodes. Unlike web services focused on request latency and replicas, HPC workloads typically involve long-running jobs, tightly coordinated processes, and significant communication costs. Performance must be evaluated via time-to-solution, speedup, parallel efficiency, FLOPS, memory bandwidth, network metrics, and cost per solution. Choosing the right parallelism model, hardware configuration, interconnect, scheduler, and checkpointing—and benchmarking and profiling phase by phase—enables scaling workloads on solid evidence rather than simply adding more nodes.

# Schedulers, Queues, and Job Resource Allocation

In High-Performance Computing (HPC), a computational job typically requires many CPU cores, large memory, GPUs, or high-speed network interconnects. Multiple research teams and applications share a single cluster, while node and device counts are finite. The **scheduler** orchestrates which jobs run, **queues** define policy groups and capacity pools a job can tap into, and **resource allocation** determines the exact nodes, CPUs, memory, GPUs, and runtime granted to each job.

These three components work together to raise cluster utilization, enforce fairness across users, and meet completion-time goals. A job may have to wait even when idle CPUs exist in the cluster, because the scheduler must locate enough simultaneous resources satisfying topology, partition, quota, or priority constraints.

## 1. Lifecycle of an HPC Job

A job typically transitions through the following states:

~~~mermaid
stateDiagram-v2
    [*] --> Submitted
    Submitted --> Pending
    Pending --> Eligible
    Eligible --> Running
    Running --> Completed
    Running --> Failed
    Running --> Timeout
    Pending --> Cancelled
    Eligible --> Cancelled
    Completed --> [*]
    Failed --> [*]
    Timeout --> [*]
    Cancelled --> [*]
~~~

- **Submitted:** the user submits the job specification and resource requests.
- **Pending:** the system has accepted the job but has not yet allocated resources.
- **Eligible:** the job satisfies initial prerequisites to be considered for scheduling; exact state names vary by scheduler.
- **Running:** the scheduler has allocated nodes and the job is executing.
- **Completed:** the program exited successfully as recorded by the scheduler.
- **Failed or Timeout:** the job exited with an error or exceeded its walltime limit.
- **Cancelled:** the user or administrator cancelled the job before completion.

Systems may include additional states such as held, suspended, configuring, or completing. Distinguish an accepted job from an allocated job: successful submission does not mean resources are ready.

A job specification typically contains: user/project, executable or container image, command, node count, task count, CPUs per task, memory, GPUs, maximum walltime, input/output paths, queue/partition, and placement constraints.

## 2. What Does the Scheduler Do?

The scheduler is the central orchestrator of the cluster. It tracks queued jobs, available resources, active nodes, user policies, and technical constraints. When an allocation opportunity opens, the scheduler picks an eligible job and assigns suitable resources.

A conceptual scheduling cycle:

~~~mermaid
flowchart TD
    A["Receive job and resource request"] --> B["Check permissions, quotas, and queue"]
    B --> C["Filter eligible jobs"]
    C --> D["Rank by priority / fair-share"]
    D --> E["Find matching nodes and resources"]
    E --> F{"Can allocate?"}
    F -- "Not yet" --> G["Keep job in queue"]
    G --> H["Wait for resources or policy changes"]
    H --> C
    F -- "Yes" --> I["Allocate nodes, CPU, RAM, GPU"]
    I --> J["Launch job"]
    J --> K["Monitor and reclaim resources upon exit"]
~~~

Core responsibilities:

1. Accept and validate job requests.
2. Determine whether the job is permitted to use the requested queue, partition, or resources.
3. Calculate remaining allocatable resources on each node.
4. Select jobs by priority, fair-share, submission time, and operational policy.
5. Select nodes based on CPU, memory, GPU, network topology, features, or data-locality constraints.
6. Launch the job and monitor runtime and state.
7. Reclaim resources when the job completes, fails, or is cancelled.

The scheduler does not make a program run faster by magically adding extra CPUs. It arbitrates resource access and enforces execution within cluster limits.

## 3. Queues, Partitions, and Usage Policies

A queue is where jobs wait to be processed. In many batch platforms, a queue is tied to a resource pool, priority tier, time limit, or access policy.

In Slurm, the standard concept is a **partition**. A partition defines a set of nodes and associated limits; users specify a partition when submitting jobs. One partition may serve short jobs, GPU jobs, interactive jobs, or long-running jobs. In some cloud batch services, a queue object carries its own scheduling policy and compute environment mappings.

Example categorization:

| Queue / partition | Workload type | Common policies |
|---|---|---|
| debug | Quick checks, script testing | Short time limit, few nodes |
| short | Fast-completing jobs | Low max walltime, prioritized for rapid turnaround |
| compute | CPU simulations or parallel processing | Many CPU cores, per-project node limits |
| gpu | Training or accelerated compute | GPU-equipped nodes, GPU count and driver/runtime limits |
| long | Extended simulations or analyses | High max walltime, potentially longer queue waits |
| high-memory | Jobs with large working sets | High-RAM nodes, concurrency limits |

Queue names only carry meaning relative to actual cluster configuration. One queue may share nodes with another queue or reserve dedicated nodes; inspect cluster configuration to understand resource boundaries.

### 3.1. Queue Limits

Common limits include:

- Maximum walltime per job.
- Maximum nodes, CPUs, GPUs, or memory per job.
- Maximum running and pending jobs per user or project.
- Maximum concurrent resource consumption.
- User groups authorized to submit.
- Node types or features a job may request.

Picking the wrong queue can cause a job to be rejected, stall in queue for hours, or lack access to needed node types. Select queues based on workload traits and verify limits before submitting.

### 3.2. Queues Do Not Mean Strict FIFO Order

Some queues process strictly first-come, first-served, but many schedulers use priority, fair-share, reservations, or backfill. Consequently, an earlier job is not guaranteed to run first. A smaller job submitted later may start earlier if it fits an open resource gap without delaying scheduled high-priority jobs.

## 4. Allocating CPUs, Nodes, and Tasks

In HPC, requested CPUs are typically expressed via node count, task count, CPUs per task, or cores per node. These declarations must align consistently with the application's execution model.

- **Node:** physical or virtual machine participating in the cluster.
- **CPU core:** compute unit allocated by the scheduler; accounting may count physical cores or hardware threads depending on configuration.
- **Task/rank:** a process or parallel execution unit, usually spawned by the MPI launcher.
- **CPU per task:** number of CPUs reserved for each task.
- **Node count:** number of nodes requested for the job.

For example, an MPI job uses 4 nodes with 16 ranks per node, totaling 64 ranks. If each rank uses one CPU core, the job needs at least 64 CPU cores. If each rank runs multithreaded with 4 threads, the requirement can reach 256 CPU cores depending on how the application and scheduler configure binding.

~~~text
MPI Job: 4 nodes x 16 ranks/node = 64 ranks

Node 1: ranks  0-15
Node 2: ranks 16-31
Node 3: ranks 32-47
Node 4: ranks 48-63

If each rank uses 1 CPU:
Total demand = 64 CPU cores

If each rank uses 4 threads:
Maximum total demand = 64 x 4 = 256 CPU cores
~~~

Never request an arbitrary CPU count and let the application spawn more threads than allocated CPUs. Oversubscription forces processes to contend for the same cores, drives up context switching, and degrades performance.

## 5. Allocating Memory, GPUs, and Specialized Resources

### 5.1. Memory

Jobs must request memory matching their working set, intermediate data, and concurrent processes. A job requesting 8 nodes at 64 GiB each may consume 512 GiB total, though declarations are typically per node or per CPU depending on the scheduler.

Requesting too little memory risks OOM kills or node-level job termination to protect system stability. Requesting too much prevents the scheduler from finding eligible nodes even if the program actually uses very little memory. Measure peak memory across representative test runs and add an appropriate safety margin.

### 5.2. GPUs

GPUs are scarce resources typically tied to specific node types, GPU models, VRAM sizes, and interconnect topologies. Jobs must declare GPU counts and may need to specify GPU models or node features.

Verify:

- GPUs per node and total GPUs needed for the job.
- VRAM required for the model and batch size.
- Compatible drivers, CUDA/ROCm, and libraries.
- GPU-to-GPU interconnects like NVLink or PCIe topology if bandwidth-sensitive.
- Sufficient host CPU and RAM for data loading, coordination, and preprocessing.
- Actual GPU utilization; avoid holding GPUs idle while the program stalls on I/O.

### 5.3. Network and Topology

Some MPI workloads require continuous inter-node communication. The scheduler may evaluate nodes within the same rack, fabric, or group sharing suitable network interconnects. For high-bandwidth, low-latency applications, placement topology directly affects runtime.

For partition-independent tasks, networking may matter less than CPU and I/O. For distributed simulations, selecting nodes purely by CPU count can yield poor performance if nodes sit far apart topologically.

## 6. Common Scheduling Algorithms and Policies

Schedulers typically combine multiple algorithms and policies. Exact implementation details vary by product and configuration.

### 6.1. FIFO and Priority Scheduling

**FIFO** evaluates jobs in submission order. It is straightforward, but a large job at the head of the queue can block smaller jobs behind it even when idle resources could accommodate those smaller jobs.

**Priority scheduling** assigns priority scores based on user, project, queue, QoS, queue wait time, or administrative policy. Higher-priority jobs are considered earlier, though still constrained by quotas and reservations. Raising priority for one group risks starving others.

### 6.2. Fair-Share

Fair-share distributes resources equitably across users or projects based on historical consumption and configured weights. Groups that consumed heavy resources recently see their relative priority lowered, while lighter consumers gain priority.

Fair-share does not necessarily split CPUs evenly at every single instant. Its goal is balancing usage over a time window so one project cannot continuously monopolize cluster capacity.

### 6.3. Backfill Scheduling

Backfill lets smaller or shorter jobs run in idle resource gaps, provided they finish before the estimated start time of a higher-priority waiting job. This boosts cluster utilization while protecting the schedule of prioritized jobs.

For example, job A needs 8 nodes and is projected to start in 20 minutes once a group of nodes frees up. Job B needs only 2 nodes with a 10-minute walltime limit. The scheduler can run B immediately if it is assured B will finish before A needs those nodes.

Backfill works best when jobs declare realistic walltime limits. If every job requests an excessively long walltime, the scheduler struggles to find safe backfill gaps. If requested walltime is shorter than actual runtime, jobs get timed out or disrupt the schedule.

### 6.4. Reservations and Preemption

**Reservations** set aside a pool of resources for a specific time window or user group, such as scheduled experiment sessions. Reservations guarantee capacity for critical work, though overall utilization drops if reserved nodes sit unused.

**Preemption** allows the scheduler to stop or suspend lower-priority jobs to free resources for higher-priority jobs. It is only effective when workloads can checkpoint, recover, or restart safely. Workloads without checkpointing can lose hours of completed computation.

## 7. Slurm Configuration and Job Submission Examples

Slurm is a widely used workload manager in HPC clusters. Jobs are typically described in batch scripts containing resource directives and execution commands.

Example MPI job running across 4 nodes, 16 tasks per node, requesting 64 GiB memory per node and a 45-minute walltime:

~~~bash
#!/bin/bash
#SBATCH --job-name=weather-sim
#SBATCH --partition=compute
#SBATCH --nodes=4
#SBATCH --ntasks-per-node=16
#SBATCH --cpus-per-task=1
#SBATCH --mem=64G
#SBATCH --time=00:45:00
#SBATCH --output=logs/%x-%j.out
#SBATCH --error=logs/%x-%j.err

module load mpi
srun ./weather-simulation input/config.yaml
~~~

Submit the job:

~~~bash
sbatch weather-sim.sbatch
~~~

In this example:

- The partition is `compute`.
- 4 nodes, 16 tasks per node, totaling 64 tasks.
- Each task requests one CPU.
- Memory is requested per node using illustrative Slurm syntax.
- Maximum runtime is 45 minutes.
- `stdout` and `stderr` are saved by job name and job ID.

Memory syntax and policies vary by cluster configuration. This example assumes the `logs` directory already exists; the scheduler does not create it automatically. For OpenMP or hybrid MPI/OpenMP applications, increase `cpus-per-task` and configure thread counts accordingly.

A GPU example requesting one node and two GPUs:

~~~bash
#!/bin/bash
#SBATCH --job-name=training
#SBATCH --partition=gpu
#SBATCH --nodes=1
#SBATCH --ntasks=1
#SBATCH --cpus-per-task=8
#SBATCH --mem=48G
#SBATCH --gres=gpu:2
#SBATCH --time=02:00:00
#SBATCH --output=logs/%x-%j.out

srun python train.py --config config.yaml
~~~

GPU resource names and request syntax depend on Slurm configuration; some clusters specify exact GPU models or custom GRES/TRES definitions. Always consult cluster documentation before submitting.

## 8. Monitoring Queues and Allocation Status

After submitting, monitor jobs and investigate if wait times drag on.

Common Slurm commands:

~~~bash
# View jobs for the current user
squeue -u "$USER"

# View nodes and partitions
sinfo

# View details of a specific job
scontrol show job JOB_ID

# View resource usage history after job completion
sacct -j JOB_ID --format=JobID,JobName,Partition,AllocCPUS,Elapsed,State,ExitCode,MaxRSS
~~~

Common job states:

| State | Common meaning | What to check |
|---|---|---|
| PENDING (PD) | Waiting for scheduling conditions | Pending reason, queue, quotas, nodes, and estimated start time |
| RUNNING (R) | Executing | CPU, memory, GPU, I/O, and logs |
| COMPLETING (CG) | Finishing and reclaiming resources | Process teardown, output files, and cleanup |
| COMPLETED (CD) | Job finished successfully per scheduler | Verify outputs and business/scientific results |
| FAILED (F) | Job terminated with error | Exit codes, logs, and runtime root causes |
| TIMEOUT (TO) | Exceeded walltime limit | Actual runtime and checkpoints |
| CANCELLED (CA) | Job was cancelled | User or policy cancellation and output state |

To see why a job is waiting, check the `Reason` field in `squeue` or `scontrol show job`. Common reasons include insufficient CPU, memory, or GPU, unavailable nodes, account limits, reservations, dependencies, or low priority. Never assume a job is stuck solely because it is `Pending`; read the reason reported by the scheduler.

After a job ends, compare `AllocCPUS`, `Elapsed`, and `MaxRSS` against requested resources. If many CPUs were allocated yet utilization was low, inspect whether the app scales adequately or waits on I/O. If `MaxRSS` nears the limit, raise memory or shrink batch size. If actual runtime is consistently far below the time limit, tightening walltime requests helps backfill.

## 9. Resource Allocation Analysis Example

Suppose a cluster has 10 identical nodes, each with 64 CPU cores and 256 GiB RAM. Raw capacity is 640 CPU cores and 2,560 GiB RAM. After subtracting OS and daemon overhead, the scheduler uses configured allocatable capacity.

Three jobs are waiting:

| Job | Nodes | CPUs per node | RAM per node | Estimated runtime |
|---|---:|---:|---:|---:|
| A - large simulation | 4 | 64 | 200 GiB | 3 hours |
| B - medium analysis | 2 | 32 | 96 GiB | 40 minutes |
| C - preprocessing | 1 | 8 | 32 GiB | 10 minutes |

If job A has top priority and requires four free nodes simultaneously, the scheduler must find four nodes satisfying both CPU and RAM. Other jobs can run on remaining nodes if quotas and policies permit. If four qualifying nodes are unavailable, A keeps waiting even if cluster-wide idle CPUs exceed 256 cores, because free resources may be fragmented across nodes or individual nodes may lack sufficient RAM.

If job C runs for 10 minutes on an idle node and finishes before A can be allocated, backfill can let C run early. If C requests 3 hours despite needing only 10 minutes, the scheduler cannot safely fit C into that gap.

This table demonstrates that allocation must satisfy CPU, RAM, node count, topology, quotas, and duration simultaneously. Looking solely at total idle CPUs is insufficient.

## 10. Utilization Efficiency and Request Tuning

Base resource requests on measurements, not the largest possible configuration.

- Run small benchmarks to measure CPU, memory, GPU, and I/O.
- Test multiple node/task sizes to find the efficient scaling point.
- Avoid requesting more nodes than the application can exploit.
- For MPI jobs, check inter-node communication performance and affinity/binding.
- For GPUs, check utilization, VRAM, and time spent waiting on data.
- For I/O-bound jobs, inspect storage and metadata throughput before adding CPUs.
- Declare realistic walltime limits with a reasonable buffer.
- Use job arrays or partitions for independent tasks rather than one needlessly serial mega-job.
- Use checkpoints to preserve progress on long or preemptible jobs.

Under-allocating makes jobs slow or fail. Over-allocating reduces job concurrency, lengthens queue wait times, and drives up cost. The goal is allocating just enough resources for target performance at high efficiency.

## 11. Allocation in Cloud HPC Environments

In the cloud, the scheduler can integrate with a compute fleet or autoscaling group to provision nodes when queues grow. This allows elastic scaling with load, at the cost of VM startup time, image loading, storage mounting, and network configuration.

Trade-offs to weigh:

- **On-demand capacity:** can add nodes when queues grow, though regional quotas and instance availability can cap provisioning.
- **Node startup latency:** jobs still wait while new machines are created and initialized.
- **Instance types:** match CPU, RAM, GPU, local NVMe, and networking to the job.
- **Spot/preemptible capacity:** cuts costs, though nodes can be reclaimed; jobs need checkpointing and retry logic.
- **Placement groups or topology:** improves networking for MPI workloads, though can restrict finding enough co-located nodes.
- **Idle cost:** keeping warm nodes ready trims wait times but raises costs when queues are empty.
- **Storage throughput:** many nodes reading the same data can bottleneck shared filesystems or object storage.

Cloud HPC should align queue policies, concurrency limits, autoscaling, and budgets. If jobs are short while nodes take several minutes to boot, tiny batches are inefficient; grouping tasks or maintaining a small warm pool cuts overhead.

## 12. Handling Long Queue Waits or Poor Runtime Performance

When a job is `Pending`, follow this sequence:

1. Read the status and pending reason from the scheduler.
2. Verify the queue/partition accepts the job type and user/project.
3. Compare requested CPU, RAM, GPU, and node counts against allocatable node capacity.
4. Check quotas, job limits, reservations, dependencies, and QoS.
5. Check whether nodes are drained, down, or constrained by features/topology.
6. If requests are too large, test a smaller footprint to isolate constraints.
7. If the cluster lacks capacity, coordinate with administrators on node pools or scheduling windows per policy.

When a job is `Running` but performing poorly:

- Check CPU utilization and CPU binding.
- Check peak memory, swap, and OOM errors.
- For GPUs, check GPU utilization, VRAM, and the data pipeline.
- Measure I/O wait, throughput, and read/write durations.
- Check network latency and inter-node communication overhead.
- Compare per-phase timings against the baseline.
- Verify whether the application actually scales as node count increases.

Never add nodes reflexively. If an application is stalled waiting on storage, adding CPUs inflates cost without improving completion time.

## 13. HPC Job Submission and Operations Checklist

- [ ] Select the right queue/partition for workload type and permissions.
- [ ] Determine node count, task count, CPUs per task, and application thread count.
- [ ] Estimate peak memory per node or per CPU using the scheduler's syntax.
- [ ] Declare accurate GPU counts, GPU types, and VRAM/topology constraints if needed.
- [ ] Set walltime limits based on benchmarks plus a reasonable buffer.
- [ ] Verify quotas, QoS, reservations, dependencies, and concurrency limits.
- [ ] Use pinned image/runtime and dependency versions.
- [ ] Verify input/output paths, permissions, and storage capacity.
- [ ] Monitor pending reasons, node allocations, logs, and metrics while running.
- [ ] Compare actual CPU, memory, GPU, and runtime against requested values.
- [ ] Maintain checkpoints or retry mechanisms for long or preemptible jobs.
- [ ] Verify outputs and final status before considering work complete.

The scheduler determines run order and placement based on policies and available resources; queues/partitions define resource scope and limits; allocations reserve the CPUs, RAM, GPUs, nodes, and runtime dedicated to a job. By declaring realistic requests, tracking pending reasons, and measuring post-run performance, operators can cut queue wait times, boost cluster utilization, and control cloud HPC costs.

# HPC, Cluster Networking, and Low-Latency Requirements

## 1. The Problem: Multiple Machines Only Help When Coordination Is Fast Enough

High Performance Computing (HPC) uses parallel compute resources to solve large problems such as aerodynamic simulations, molecular modeling, design optimization, or model training. When work is split across multiple machines, completion time also depends on data exchange, process synchronization, and reading/writing results.

In the **Specialized Workloads and Deployments** chapter of Oracle Cloud Infrastructure (OCI), this lesson aims to design an HPC cluster with networking matched to the application, deploy it within a controlled IAM scope, and measure performance and cost with empirical data. Operators must be able to answer:

- Does the application need more CPU, memory, GPUs, or inter-node interconnect?
- When does standard VCN networking suffice, and when is RDMA cluster networking needed?
- How do you verify the application is actually using the intended transport path?
- How does the cluster recover when a node fails?
- Up to how many nodes does scaling benefit schedule and budget goals?

Some HPC workloads also run well on a single large machine. Moving from one node to multiple nodes must be driven by memory limits, completion deadlines, or measured performance.

### Required Background

Learners should be familiar with tenancy, compartments, IAM policies, VCNs, subnets, NSGs, Compute instances, Object Storage, and Monitoring. For the hands-on section, basic Linux skills and an environment with Slurm and a compatible MPI distribution installed on nodes are required.

A **node** is a machine participating in the cluster. An **MPI rank** is a process in an MPI application. One node can run multiple ranks; each rank can in turn use multiple threads or a GPU. Node count, rank count, and core count are three distinct quantities.

## 2. Classifying Workloads Before Selecting Infrastructure

| Workload type | Communication pattern | What to prioritize |
| --- | --- | --- |
| Many independent simulations | Jobs barely communicate while running | Cost per result, wait time, queue scalability |
| Tightly coupled MPI | Boundary data exchange and repeated synchronization | Latency, latency jitter, inter-node bandwidth |
| High-memory analytics | Holding large datasets in RAM | Memory capacity and bandwidth; compare scale-up vs. scale-out |
| Distributed GPU training | Gradient or model state synchronization | Collective communication, GPU interconnects, and inter-node networking |
| I/O-heavy processing | Reading large datasets, many small files, or large checkpoints | Storage throughput, metadata, locality, and staging time |

For example, 1,000 independent Monte Carlo simulations can usually be split into separate jobs. Each job loads data once, computes, and writes results. Conversely, a solver decomposing a domain across many ranks may exchange halo regions at every time step. Using hundreds of cores alike, these two applications place vastly different demands on the network.

For loosely coupled workloads, a standard instance pool paired with a scheduler can work well. For tightly coupled workloads, evaluate RDMA and colocated cluster placement. The [HPC on OCI](https://docs.oracle.com/en-us/iaas/Content/Compute/References/high-performance-compute.htm) documentation introduces bare metal infrastructure and cluster networking for this class of problems.

A workload's bottleneck can shift with scale. A solver running on four nodes may be compute-bound, whereas at 32 nodes each rank's work shrinks and synchronization becomes the dominant cost.

## 3. Properly Understanding Latency, Bandwidth, and Scaling Efficiency

### 3.1. Model for a Single Exchange

A simple model for a message of size m bytes:

~~~text
T_message ≈ alpha + m / B_effective

alpha       : initiation overhead and path latency
B_effective : effective application bandwidth achieved
~~~

Small messages are typically sensitive to alpha; large messages are sensitive to bandwidth. Nominal NIC bandwidth is only one hardware ceiling. Actual bandwidth also depends on protocol, topology, memory, message size, stream count, and communication library.

Suppose one application step has 2,000 sequential exchanges on the critical path. If each exchange is reduced by 15 microseconds, the ideal reduction is:

~~~text
2,000 × 15 microseconds = 30 milliseconds per step
10,000 steps × 30 milliseconds = 300 seconds
~~~

This is an illustrative calculation. Messages running concurrently or overlapping with computation do not sum linearly this way.

### 3.2. Tail Latency and Slow Nodes

In a step involving a barrier or collective, many ranks must wait for the last rank to finish. Therefore, p95, p99, and latency spikes can affect total runtime more than average latency.

Distinguish the following metrics:

- **One-way latency**: unidirectional transit time under a specific measurement method.
- **Round-trip time**: bidirectional transit time.
- **MPI latency**: result defined by an MPI benchmark; some benchmarks report half of ping-pong time.
- **Iteration time**: duration of one compute loop, including both computation and communication.
- **End-to-end time**: from job submission until results are ready.

Do not compare values sharing the microsecond unit if their measurement methods differ. ICMP ping over VCN addresses does not prove RDMA data-path latency.

### 3.3. Limits of Adding Nodes

For a fixed problem size, you can model:

~~~text
T(n) ≈ T_serial + T_parallel / n + T_communication(n) + T_io(n)
~~~

The serial fraction imposes a ceiling per Amdahl's law. If 5% of work is strictly serial, ideal maximum speedup approaches only 20x as resource count grows arbitrarily large, even before accounting for communication overhead.

Two common measurement modes:

- **Strong scaling**: hold problem size fixed, increase resources; measure runtime reduction.
- **Weak scaling**: scale problem size with resources to keep work per resource roughly constant; measure how well runtime stays flat.

For homogeneous nodes with constant per-node configuration:

~~~text
Speedup(n)    = T(1) / T(n)
Efficiency(n) = Speedup(n) / n
~~~

If the problem does not fit on one node, use the smallest runnable configuration as the baseline and normalize by the resource ratio relative to that baseline. Never fabricate a single-node figure to plug into the formula.

## 4. RDMA and Network Paths in OCI

### 4.1. What Overhead Does RDMA Address?

Remote Direct Memory Access (RDMA) enables data transfers to or from memory regions registered with network hardware. With appropriate hardware and libraries, this reduces CPU involvement and protocol processing overhead compared to standard socket paths.

RDMA still requires resource allocation, memory registration, access control, and completion handling. Applications benefit only when MPI or the communication library actually selects the corresponding transport.

In Oracle's HPC reference architecture, the cluster interconnect uses RoCEv2—RDMA over Converged Ethernet version 2. RoCEv2 runs over Ethernet; it is not synonymous with an InfiniBand fabric even though both share many concepts in the RDMA ecosystem. See [Deploy HPC on OCI Architecture](https://docs.oracle.com/en/solutions/deploy-hpc-on-oci/index.html).

### 4.2. Separating Management, HPC Data, and Storage Paths

You can view the cluster through three traffic types:

| Traffic type | Examples | What to verify |
| --- | --- | --- |
| Management and orchestration | Login, Slurm, DNS, configuration distribution | VCN, NSG, routes, OS firewall |
| Inter-rank data | MPI, halo exchange, collectives | RDMA fabric, devices, authentication, and transport |
| Storage data | Inputs, outputs, checkpoints, shared file reads | Actual protocol and network path of the storage system |

Reachability via VCN IP addresses is not enough to confirm RDMA works. Creating extra VNICs or widening a subnet also does not create an RDMA network group.

Similarly, NSGs and security lists control VCN flows within their scope. They do not replace the RDMA authentication and configuration required by OCI. Access policy design must cover cloud resources, management paths, and in-guest software.

A parallel filesystem may have its own network design. Do not assume every read/write operation traverses RDMA simply because compute nodes have RDMA.

### 4.3. Conditional Low Latency

Oracle describes cluster networking latency as potentially reaching single-digit microseconds between closely colocated bare metal nodes. This describes infrastructure capability, not a guarantee for every MPI call or an application's full compute loop. See [Compute Clusters](https://docs.oracle.com/en-us/iaas/Content/Compute/Tasks/compute-clusters.htm).

Bandwidth specs, NIC counts, and support depend on the shape. During planning, verify the list of shapes, images, regions, and availability domains (ADs) supporting the chosen cluster model. Do not apply specs from one CPU or GPU generation across all of OCI.

## 5. Choosing the Right Cluster Management Resource

OCI offers two primary models for managing a group of nodes in an RDMA network group:

| Criterion | Cluster network with instance pool | Compute cluster |
| --- | --- | --- |
| Management style | Manages a homogeneous node set via an instance pool | Manages individual instances within a group |
| Starting point | Instance configuration and pool size | Create an empty RDMA group, then launch instances into it |
| Best fit | Homogeneous configs, group-level lifecycle | Need lifecycle control per individual node |
| What to keep clear | Relationship among cluster network, pool, and node config | Cluster membership and compatibility of each node |

The instance pool model is described in [Cluster Networks with Instance Pools](https://docs.oracle.com/en-us/iaas/Content/Compute/Tasks/managingclusternetworks.htm). The compute cluster workflow starts with an empty RDMA group as documented in [Creating a Compute Cluster](https://docs.oracle.com/en-us/iaas/Content/Compute/Tasks/create-compute-cluster.htm).

A compute cluster permits different supported instance types within the same group. However, an MPI job is usually easier to operate and more predictable when nodes are homogeneous. A slower node or one with a different instruction set or library version can slow down or break the entire job.

Distinguish further:

- **VCN/subnet** provides cloud network connectivity; sharing a subnet does not mean sharing an RDMA cluster.
- **Standard instance pool** manages a group of instances; by itself it does not guarantee RDMA.
- **Slurm cluster** is a resource set managed by the scheduler; it may span multiple infrastructure groups.
- **OCI compute cluster** is an infrastructure resource; it does not automatically install Slurm or distribute applications.
- **Cluster placement group** is a separate placement mechanism. Verify its specific capabilities and eligibility; do not treat the term as a synonym for compute cluster.

An RDMA group is placed in a supported AD. Selecting the same AD is only a location prerequisite; you must still create the proper group resource and join nodes to it via the appropriate workflow.

## 6. Reference Architecture for a Small HPC Cluster

Suppose an engineering team needs to run an MPI solver across 2–8 nodes, load inputs from Object Storage, and save checkpoints to resume after failures.

~~~mermaid
flowchart TB
    USER["Users and CI"]
    ACCESS["Controlled admin access channel"]
    OBJ["Object Storage: inputs, checkpoints, outputs"]
    OBS["Monitoring / Logging"]

    USER --> ACCESS

    subgraph VCN["VCN: nodes use private IPs"]
        HEAD["Login / Slurm controller"]
        FS["Shared filesystem"]
        subgraph AD["One availability domain"]
            subgraph RDMA["RDMA group on OCI"]
                N1["Compute node 1"]
                N2["Compute node 2"]
                NN["Compute node n"]
                N1 <-->|"MPI over RDMA"| N2
                N2 <-->|"MPI over RDMA"| NN
            end
        end
    end

    ACCESS --> HEAD
    HEAD -->|"Orchestration over VCN"| N1
    HEAD -->|"Orchestration over VCN"| N2
    HEAD -->|"Orchestration over VCN"| NN
    N1 -->|"I/O per storage design"| FS
    N2 -->|"I/O per storage design"| FS
    NN -->|"I/O per storage design"| FS
    FS -->|"Staging and backup"| OBJ
    N1 -.-> OBS
    N2 -.-> OBS
    NN -.-> OBS
~~~

This is a logical diagram. An administrative access channel can be implemented with OCI Bastion or an appropriate private connection. An actual cluster needs corresponding routes, endpoints, and access permissions designed.

Component roles:

- **Login node** receives source code, compiles, or submits jobs. Long compute tasks run on compute nodes under allocations.
- **Slurm controller** manages queues, node states, and resource allocation.
- **Compute nodes** run MPI ranks using standardized images and libraries.
- **Shared storage** provides paths applications need to share; choose a solution based on throughput and semantics.
- **Object Storage** holds versioned inputs, finalized checkpoints, and retained outputs.
- **Monitoring/Logging** aggregates hardware health, job states, and application errors.

Small labs may place login and controller on the same host. For critical environments, separately evaluate controller resilience, where scheduler state is stored, and management access controls.

If input data comes from Oracle Database, create a consistent snapshot or export for the job. Having thousands of ranks simultaneously query a database inside a compute loop can turn the data tier into a bottleneck and make experiments hard to reproduce.

## 7. Preparing IAM, Capacity, and Connectivity

### 7.1. Permission Scopes and Responsibilities

Compartments help organize resources and enforce permissions. A practical split might use one compartment for HPC infrastructure and one for shared data.

| Role | Proposed responsibility scope |
| --- | --- |
| Network admin team | VCN, subnets, NSGs, routes, and required gateways |
| HPC deployment team | Create cluster groups, instance configurations, nodes, and related resources within assigned scope |
| Job submitter | Log in under OS permissions, submit jobs, and access permitted datasets |
| Instance principal | Read inputs, write outputs, or emit metrics per specific policies |
| Operations team | Monitor, drain nodes, replace failed nodes, and control costs |

Permission to create a compute cluster does not automatically grant every permission needed for instances, subnets, images, or volumes. Deployers must have sufficient permissions on every dependency. Nor does OCI IAM automatically create Linux accounts or Slurm job submission privileges.

For programs on nodes calling OCI APIs, use instance principals with dynamic groups and narrowly scoped policies. The application or OCI SDK/CLI must explicitly use that auth provider; creating a dynamic group alone does not make code automatically acquire permissions.

### 7.2. Limits, Quotas, and Capacity Are Three Different Checks

- **Service limit**: resource allowance the tenancy can use by type and scope.
- **Compartment quota**: internal constraint limiting how much resource a compartment may consume.
- **Physical capacity**: actual hardware currently available in the requested AD and placement.

Raising a service limit does not immediately materialize hardware on-site. Having capacity for one node does not prove all nodes required for a job can be provisioned. Check current tenancy limits in [Limits by Service](https://docs.oracle.com/en-us/iaas/Content/General/service-limits/default.htm).

Before a major run, confirm shape, node count, AD, timing, capacity provisioning conditions, and a fallback if capacity is insufficient. If planning to use capacity reservations, verify whether the cluster model and shape support them as expected.

### 7.3. Outbound Connectivity and OCI Services

Compute nodes should have required paths to package/artifact repositories, DNS, time sources, storage, and metrics ingestion endpoints. Configure routes per actual endpoint:

- Service Gateway can provide private access to supported OCI services within its configuration scope.
- Public repositories require an appropriate egress path or an internal mirror.
- Hosts with private IPs still require proper routes and egress rules; a private subnet does not automatically grant outbound connectivity.
- Scheduler, remote launch, and storage flows must be permitted per the chosen software configuration.

Document the source, destination, protocol, and purpose matrix. Never open all traffic from the internet just to get past an MPI launch error.

## 8. Cluster Creation and Node Onboarding Workflow

### 8.1. Selecting Shape and Image as a Compatible Pair

Evaluate usable core count, memory per rank, local NVMe if any, GPU count, RDMA NICs, and topology. Cross-check [Compute Shapes](https://docs.oracle.com/en-us/iaas/Content/Compute/References/computeshapes.htm) against the supported shape list for the exact cluster model.

The image must match the kernel, network drivers, GPU drivers if used, MPI, and OCI plugins. Record the image OCID, package versions, and executable checksums. Even an image named "HPC" must be verified against the specific shape and software stack.

When choosing rank counts, inspect the machine's actual topology; do not assume every logical CPU equals a physical core or apply one OCPU/vCPU ratio across all architectures.

### 8.2. Creating Infrastructure Groups and Nodes

A repeatable deployment sequence:

1. Prepare compartments, policies, subnets, NSGs, storage, and egress paths.
2. Select an AD supporting the shape and cluster model.
3. If using a cluster network with an instance pool, prepare a compatible instance configuration and pool size.
4. If using a compute cluster, create the group first and then launch instances as members of that group.
5. Apply standardized images, agent configurations, and software versions.
6. Configure hostnames, DNS, accounts, system time, paths, and mounts.
7. Register nodes with Slurm; keep nodes out of service queues until validation completes.
8. Test two nodes first, then scale out and re-test representative pairs or groups.

Group creation, placement, and instance configuration attributes must follow [Creating a Cluster Network with Instance Pools](https://docs.oracle.com/en-us/iaas/Content/Compute/Tasks/create-cluster-network.htm). Selecting a compute cluster in a standard single-instance launch flow must not be substituted for creating a cluster network with a pool.

Terraform and OCI Resource Manager, or a maintained HPC stack, can automate provisioning. Pin versions and review plans before applying. Cloud provisioning completion is only one milestone; nodes must also bootstrap cleanly and pass runtime checks.

### 8.3. RDMA Authentication and Auto-Configuration

Two common plugins are:

- **Compute HPC RDMA Authentication**: maintains RDMA authentication and related configuration.
- **Compute HPC RDMA Auto-Configuration**: automatically configures hardware/interfaces where supported.

Per the [Oracle Cloud Agent HPC Plugin Guide](https://docs.oracle.com/en-us/iaas/Content/Compute/Tasks/transitioning-to-hpc-plugin.htm), migrating from legacy HPC packages must follow the exact sequence and can be disruptive. Never run that transition while workloads are active.

Beyond the desired `ENABLED` state, verify the plugin is actually running, the RDMA device is healthy, and nodes can exchange traffic. With custom images, take special care to avoid legacy and new configuration mechanisms fighting over interface management.

## 9. Tuning CPU Topology, Memory, GPUs, and Libraries

In tightly coupled workloads, intra-node topology matters as much as inter-node networking.

### 9.1. CPU and NUMA

A node may contain multiple NUMA domains. A rank running on one socket while accessing RAM on another incurs extra latency. Intentional rank and thread placement reduces process migration and remote memory access.

A sensible starting point is testing ranks per node, threads per rank, and CPU binding across controlled configurations. Record SMT settings and total allocated cores. Avoid unintentional oversubscription, which can cause severe communication jitter.

### 9.2. GPUs and Intra-Node Interconnects

Distributed GPU applications also depend on CPU–GPU, GPU–GPU, GPU–NIC paths, and collective libraries. A working RDMA device alone does not prove GPU-to-GPU transfers take the optimal path.

Choose rank counts per the application's execution model, typically aligned with how GPUs are assigned to processes. Watch collective wait times and data loaders; low GPU utilization can stem from networking, I/O, or load imbalance.

### 9.3. MPI and Transport Must Match

Diagnostic commands on Linux, assuming the corresponding tools are installed:

~~~bash
hostname
lscpu
numactl --hardware
ip -br address
rdma link show
ibv_devinfo
ulimit -l
mpirun --version
ompi_info --param pml all
ucx_info -d
~~~

The MPI/UCX commands above apply to environments using Open MPI and UCX. For Intel MPI or another library, use that stack's corresponding tools.

RoCE support in current Open MPI uses UCX. Verify exact installed versions and built components per [Open MPI InfiniBand/RoCE Documentation](https://docs.open-mpi.org/en/main/tuning-apps/networking/ib-and-roce.html). UCX supports multiple transports, including TCP; merely seeing UCX present does not prove a run selected RDMA.

Evidence should combine device status, transport selection logs, inter-node benchmarks, and corresponding RDMA counters. Do not hardcode NIC names, GID indices, MTUs, or library configs copied from a different shape.

## 10. Data and Checkpoint Design

### 10.1. Choosing Storage Tiers by Access Pattern

| Tier | Potential role | Questions to answer |
| --- | --- | --- |
| RAM | Hot state during computation | Does per-rank data fit without swapping? |
| Local NVMe if included with shape | Scratch, temporary files, cache | If a node is lost, what must be regenerated? |
| Shared filesystem | Executables, working directories, files read concurrently by ranks | Do throughput, metadata, and semantics fit? |
| Object Storage | Versioned inputs, packaged checkpoints, results | How does the app stage and verify data? |
| Block Volume | Node storage or data per design | Are attach type, filesystem, and concurrent access valid? |

Never mount a standard local filesystem on a shared volume for concurrent multi-node writes without a clustered filesystem and coordination mechanism. Object Storage provides an object interface; applications requiring POSIX need a staging step or separately evaluated integration layer.

Many small files can hit metadata limits even when total byte volume is small. Reading one shared large file, sharding, or aggregating outputs is an application-level decision that must be benchmarked against the storage configuration.

Local NVMe data is wiped when terminating an instance per [Terminating an Instance](https://docs.oracle.com/en-us/iaas/Content/Compute/Tasks/terminatinginstance.htm). Therefore, the sole checkpoint copy must never reside only on a node that might be replaced.

### 10.2. Checkpoints Must Be Recoverable

A usable checkpoint requires:

- Application state consistent across all ranks.
- Step metadata, rank count, or constraints for changing decomposition.
- Input, executable, and configuration versions.
- Integrity verification.
- A completion marker written only after all required parts finish saving.
- An actual restart test.

If a checkpoint spans multiple objects, publish the "complete" manifest only after verifying all parts. During recovery, ignore partially written sets.

Suppose a checkpoint totals 256 GiB and storage achieves an aggregate throughput of 4 GiB/s:

~~~text
Minimum transfer time ≈ 256 / 4 = 64 seconds
~~~

In practice, serialization, metadata, synchronization, and verification add time. If writing takes 64 seconds per 1,800-second compute interval, checkpoint overhead in a full cycle is approximately:

~~~text
64 / (1,800 + 64) ≈ 3.4%
~~~

Shorter intervals reduce lost compute work but increase I/O pressure. Longer intervals have the opposite trade-off. Choose based on state size, runtime, failure history, and storage capacity when the entire cluster checkpoints simultaneously.

## 11. Lab: Verifying MPI Across Two Nodes with Slurm

This section aims to confirm processes run across two nodes and execute a collective correctly. This is a functional check, not an RDMA measurement or performance benchmark.

### 11.1. Lab Prerequisites

- At least two compute nodes in the intended infrastructure group.
- Slurm already manages both nodes.
- Open MPI integrates with Slurm and has identical versions/libraries on compute nodes.
- User has permission to submit jobs to the appropriate partition.
- Working directory resides on a shared filesystem mounted at the same path across nodes.
- Commands below run on the cluster's Linux environment, not in local Windows PowerShell.

If the environment uses environment modules, load the administrator-specified compiler/MPI modules before compiling and load the same environment inside the batch job. Never mix `mpicc` from one MPI with `mpirun` from another.

### 11.2. Creating the Test Program

Save the following as `mpi-check.c` in the shared working directory:

~~~c
#include <mpi.h>
#include <stdio.h>

int main(int argc, char **argv) {
    int rank, size, name_len;
    char host[MPI_MAX_PROCESSOR_NAME];

    MPI_Init(&argc, &argv);
    MPI_Comm_rank(MPI_COMM_WORLD, &rank);
    MPI_Comm_size(MPI_COMM_WORLD, &size);
    MPI_Get_processor_name(host, &name_len);

    long long local = (long long)rank + 1;
    long long total = 0;

    MPI_Allreduce(&local, &total, 1, MPI_LONG_LONG_INT,
                  MPI_SUM, MPI_COMM_WORLD);

    long long expected = (long long)size * (size + 1LL) / 2;
    int ok = (total == expected);

    printf("rank=%d size=%d host=%.*s sum=%lld expected=%lld ok=%d\n",
           rank, size, name_len, host, total, expected, ok);
    fflush(stdout);

    MPI_Finalize();
    return ok ? 0 : 1;
}
~~~

Compile:

~~~bash
mpicc -O2 -Wall -Wextra mpi-check.c -o mpi-check
~~~

The program sums values from 1 to rank count using `MPI_Allreduce`. With four ranks, the expected sum is 10. Output line ordering is not guaranteed.

### 11.3. Submitting a Job with Explicit Allocation

Save the batch script as `mpi-check.sbatch`:

~~~bash
#!/usr/bin/env bash
#SBATCH --job-name=mpi-check
#SBATCH --nodes=2
#SBATCH --ntasks=4
#SBATCH --ntasks-per-node=2
#SBATCH --cpus-per-task=1
#SBATCH --time=00:05:00
#SBATCH --output=mpi-check-%j.out

set -euo pipefail

# Reload compiler/MPI modules here if required by the system.
cd "$SLURM_SUBMIT_DIR"

echo "job=$SLURM_JOB_ID nodes=$SLURM_JOB_NODELIST"
mpirun ./mpi-check
~~~

Specify the real partition when submitting:

~~~bash
sbatch --partition=<actual-partition-name> mpi-check.sbatch
squeue --user="$USER"
~~~

Replace the placeholder before running. With Slurm-integrated Open MPI, `mpirun` reads nodes and task counts from the allocation; no hostfile is needed. This mechanism is explained in [Launching with Slurm](https://docs.open-mpi.org/en/main/launching-apps/slurm.html). If using direct launch via `srun`, verify PMI/PMIx and your MPI distribution's documentation.

Passing criteria:

1. Job is allocated two nodes in the right partition.
2. Four ranks belong to one MPI world of size 4.
3. Output records the two expected hostnames.
4. Every rank reports `sum=10` and `ok=1`.
5. Job exits cleanly.

If only one hostname appears or each process reports `size=1`, inspect the launcher and scheduler integration before evaluating networking.

### 11.4. Proving RDMA with Dedicated Measurements

After functional verification passes, run inter-node benchmarks inside an appropriate allocation. You can use MPI benchmark suites such as OSU Micro-Benchmarks or Intel MPI Benchmarks if installed and compatible with your MPI stack.

RDMA evidence spans multiple layers:

- Test processes actually run on two distinct nodes.
- Selected transport matches the intended RDMA device.
- RDMA interfaces show corresponding activity during the test window.
- Latency/bandwidth results are stable and repeatable against baseline.
- Real application performance improves toward stated targets.

A "job succeeded" log line, fast ping, or VCN `iperf` throughput answers narrower questions. A very small-message benchmark may also generate too few bytes to show clearly in coarse-grained metric charts; rely additionally on node-level tools and transport logs.

## 12. Building Comparable Performance Benchmarks

### 12.1. Recording Full Context per Run

Every result should record region/AD, cluster group type, shape, image, kernel, driver, MPI/UCX versions, node count, rank count, thread count, CPU binding, input version, and executable version.

Hold factors outside the variable under study constant. For example, when measuring strong scaling, do not simultaneously change shape, solver algorithm, and filesystem and then credit all gains to RDMA.

Break down time intervals:

~~~text
T_total =
    T_queue
  + T_provision
  + T_bootstrap
  + T_stage_in
  + T_compute
  + T_stage_out
~~~

Optimizing `T_compute` may barely reduce `T_total` if the cluster takes a long time to provision or inputs must be re-downloaded every run.

### 12.2. Measuring from Components to Full Applications

| Measurement | Primary question | Interpretation limit |
| --- | --- | --- |
| Small-message ping-pong | What is benchmark inter-node latency? | Does not represent all collectives |
| Large-message bandwidth | Can the workload saturate the link? | Does not capture small-message overhead |
| Multi-rank Allreduce/Alltoall | How does synchronization cost grow with scale? | Depends on algorithm and message size |
| I/O benchmark | Are staging, checkpoints, or metadata bottlenecked? | Must match application access pattern |
| Real solver or training | Do runtime and results meet requirements? | Requires version control and correctness checks |

Run warm-up iterations, then repeat measurements and record distributions. When reporting p99, collect enough samples and document methodology; p99 from a handful of runs is unreliable.

Test multiple representative node pairs or node groups. One fast pair does not guarantee the entire cluster has no stragglers. Record compute versus communication time per rank when supported by a profiler.

### 12.3. Strong Scaling and Node-Hour Example

The following table contains **hypothetical data to illustrate calculations**, not OCI benchmarks:

| Homogeneous nodes | Compute time, minutes | Speedup vs. 1 node | Efficiency | Node-hours |
| --- | --- | --- | --- | --- |
| 1 | 120 | 1.00 | 100% | 2.00 |
| 2 | 68 | 1.76 | 88.2% | 2.27 |
| 4 | 40 | 3.00 | 75.0% | 2.67 |
| 8 | 32 | 3.75 | 46.9% | 4.27 |

From four to eight nodes, runtime drops by eight minutes while node-hours increase roughly 60%. With a 45-minute deadline ignoring overhead, four nodes meet the deadline at lower resource cost. With a 35-minute deadline, eight nodes may be necessary.

Add staging, startup, and other component costs before making operational decisions. If the single-node baseline ran out of memory and swapped, speedup numbers can be misleading; inspect measurement conditions.

## 13. Monitoring from Hardware to Jobs

HPC monitoring must combine three views: node health, communication behavior, and application progress.

| Observation layer | Signals to collect | Purpose |
| --- | --- | --- |
| CPU/memory | Utilization, RAM, swap, NUMA, iowait | Distinguish compute, memory exhaustion, and I/O wait |
| RDMA | Traffic, link state, device-related errors | Detect faulty links or anomalies between nodes |
| GPUs if present | Utilization, memory, hardware errors | Spot idle GPUs and stragglers |
| Scheduler | Pending reasons, node state, queue time, allocations | Distinguish missing capacity from unready nodes |
| Application | Iteration time, convergence rate, collective time | Verify actual progress is advancing |
| Storage | Throughput, latency, metadata, checkpoint duration | Identify I/O bottlenecks and progress-loss risk |

OCI provides HPC namespaces such as `rdma_infrastructure_health` and `gpu_infrastructure_health`. For instance, `RdmaTxBytes`/`RdmaRxBytes` reflect bytes on the RDMA interface; `RdmaLinkSpeedFault` is a fault signal, not a latency measurement. Read metric semantics, units, and dimensions before building queries per [High Performance Computing Metrics](https://docs.oracle.com/en-us/iaas/Content/Compute/References/high-performance-computing-metrics.htm).

Do not rely solely on cluster-wide averages: one failing node can be masked by the rest. Retain per-instance and per-device visibility, and correlate time windows with job IDs. Metrics sampled per second or minute also do not replace microsecond-level benchmarks.

Monitoring plugins, IAM, and paths to endpoints must be fully configured. Emitting metrics to custom namespaces may incur charges per service policies. When metrics are missing, inspect the emission pipeline before assuming nodes are down.

Actionable alerts tie directly to responses: a node with link faults stops accepting new jobs; sustained iteration time spikes trigger profiler capture; failed checkpoints preserve the previous valid copy and trigger storage investigation.

## 14. Evidence-Based Ordered Troubleshooting

| Symptom | Hypothesis to check first | Appropriate inspection step |
| --- | --- | --- |
| Not enough nodes provisioned | Limits, quotas, shape/AD mismatch, or capacity shortage | Lifecycle states, API errors, and actual node count |
| Nodes do not join queue | Bootstrap, mounts, DNS, or Slurm not ready | Init logs, node states, and scheduler config |
| MPI fails to launch | Launcher, environment, file permissions, or orchestration connectivity | Run small test, compare PATH and libraries |
| MPI runs slowly | TCP fallback, binding, NUMA, I/O, or imbalance | Transport logs, profiler, and component benchmarks |
| Only some nodes are slow | Hardware fault, config drift, local disk, or noisy tasks | Compare healthy vs. unhealthy nodes on same test |
| Collectives spike suddenly | Straggler, network congestion, CPU scheduling, or checkpointing | Per-rank timeline and concurrent events |
| Performance drops after update | Kernel, driver, MPI, image, or config changed | Compare version manifest against baseline |
| Job loses progress after node swap | Incomplete checkpoint or stored only on scratch | Check manifest and test restart from verified copy |

Narrow investigation by layer:

1. Confirm the job has the right resources, nodes, and cluster membership.
2. Confirm RDMA devices, drivers, plugins, and authentication.
3. Confirm the MPI runtime and selected transport.
4. Compare a two-node benchmark against baseline.
5. Check collectives, CPU binding, and NUMA.
6. Check I/O and application characteristics.

Change only one related variable group at a time. If you change MTU, driver, MPI, and rank count simultaneously, a faster run will not tell you why.

Before replacing nodes or updating software, collect logs and drain nodes from accepting new jobs. Never leave firewalls disabled or authentication turned off as a permanent workaround.

## 15. Availability and Recovery for Tightly Coupled Workloads

### 15.1. Colocated Placement and Failure Domain

Concentrating nodes in one AD serves latency goals, but creates dependency on that infrastructure scope. Do not design a tightly coupled MPI job spanning multiple regions and expect intra-cluster RDMA latency.

A standard MPI job typically aborts if one rank is lost. Continuing across member failures depends on specific libraries, applications, and fault-tolerant designs; multiple machines do not automatically make a single run highly available.

A practical approach is keeping data durable, checkpoints consistent, and clusters reproducible. For recovery outside an AD/region, replicate data using capabilities of the chosen storage service and estimate capacity provisioning time at the target.

### 15.2. Node Replacement and Scheduler-Driven Scaling

A controlled node replacement cycle:

~~~text
Detect failure
    -> Stop scheduling new jobs to node
    -> Wait for job completion or checkpoint/cancel per policy
    -> Save logs and verify durable checkpoint
    -> Replace node
    -> Verify hardware, networking, and MPI
    -> Return node to queue
    -> Resume or resubmit job
~~~

Never terminate instances actively running ranks without coordinating with Slurm. When scaling up, mark nodes ready only after images, mounts, agents, MPI, and scheduler state are uniform.

For pool-based cluster networks, resize operations must follow OCI's resource model and integrate with scheduler node lifecycles. See [Resizing a Cluster Network with Instance Pools](https://docs.oracle.com/en-us/iaas/Content/Compute/Tasks/resize-cluster-network.htm). Resizing a pool does not automatically allow a running MPI job to change rank counts.

### 15.3. RTO and RPO Must Be Measured

RTO includes time to detect failure, decide recovery, provision capacity, configure nodes, load checkpoints, and resume execution. Compute progress RPO depends on the latest valid checkpoint.

For example, checkpointing every 30 minutes does not guarantee losing at most 30 minutes if the latest checkpoint is still writing or has not replicated to the recovery location. Measure both checkpoint publication time and restart tests.

Slurm controller state, queue configuration, accounts, and software must also have a recovery path. Rebuilding compute nodes without scheduler state or licenses does not restore an operable environment.

## 16. Controlling Costs by Completed Outcomes

### 16.1. Accounting for the Full Resource Lifecycle

A cost estimation model:

~~~text
Cost per job =
    sum(node-hours of each node type × corresponding unit rate)
  + allocated portion of controller/login costs
  + storage and data operations
  + billable data transfer
  + software licenses
  + logging/monitoring and related services
~~~

Node allocation time can exceed solver runtime. Include staging waits, bootstrap, idle time, and reruns. Across many jobs, compare total cost divided by qualified completed outcomes.

Use current unit prices for the actual region, shape, and contract when budgeting. Do not assume stopping every bare metal shape or storage component halts all charges; verify billing rules for each resource.

### 16.2. Scaling by Queue, Reclaiming by Job State

Effective autoscaling needs queued job counts, per-job resource requests, deadlines, node caps, and startup times. Low CPU utilization alone is an insufficient signal: a job may be waiting on I/O or a collective.

When reclaiming nodes, drain them from new jobs, wait for allocations to end, verify outputs/checkpoints, and then terminate. Define clearly who may cancel jobs, when to retain nodes for investigation, and maximum acceptable idle time.

Tag resources with owner, project, environment, and expiration. Job logs should correlate with cluster configuration and allocation windows for cost allocation.

### 16.3. Budgets Are Alerts, Not Kill Switches

OCI Budgets set soft thresholds and emit alerts; they do not automatically stop resources from incurring charges. See [Budgets](https://docs.oracle.com/en-us/iaas/Content/Billing/Concepts/budgetsoverview.htm).

If automated actions are required, design a dedicated controlled mechanism: scale limits, resource TTLs, job status checks, checkpoints, and teardown workflows. Never rely on a delayed billing alert as the sole safeguard for a large cluster's budget.

After a lab session, inventory compute nodes, head nodes, boot/block volumes, filesystems, objects, backups, and billable network components. Delete data only after verifying needed results are stored safely.

## 17. Handover Package for an Operable HPC Cluster

A deployment is ready for handover when all the following evidence is complete:

| Evidence group | Required contents |
| --- | --- |
| Workload fit | Communication pattern, RAM/GPU/I/O needs, and rationale for node count |
| OCI infrastructure | Compartment, AD, shape, cluster model, image, and actual membership |
| Permissions and connectivity | IAM roles, Linux accounts, admin path, egress, and data access |
| Runtime | Driver/MPI versions, plugin checks, devices, and active transport |
| Functionality | MPI runs across intended nodes; collectives return expected results |
| Performance | Contextualized benchmarks, appropriate strong/weak scaling, and run-to-run variance |
| Data | Versioned inputs, completed checkpoints, and restart test results |
| Operations | Alerts, node drain/replacement runbooks, and capacity-shortage fallback |
| Cost | Full-lifecycle estimate, scaling thresholds, and reclamation mechanism |

Acceptance thresholds must originate from the application. For example, a solver might require finishing in 45 minutes, checkpointing under two minutes, and restarting from the latest copy. Another workload may prioritize results per unit cost. Defining thresholds before measuring grounds configuration choices in verifiable goals.

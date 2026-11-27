# Designing HPC with Compute Engine and High-Performance Networking

High Performance Computing (HPC) is a set of approaches that harness substantial compute resources to solve compute-intensive problems: computational fluid dynamics (CFD), finite element analysis (FEA), weather modeling, physics simulations, financial modeling, or scientific data processing. An HPC job may run on a single very powerful machine, or across thousands of processes spanning many machines that must exchange data with ultra-low latency.

Google Cloud provides Compute Engine with specialized machine families, VPC networking, high-performance networking options, memory/storage tiers, and operational services to build HPC clusters. However, simply creating many VMs does not yield good HPC performance. Outcomes depend on **the application's parallelization model, inter-node communication performance, VM placement, memory architecture, storage read/write throughput, scheduler, quotas, and budget**. Sound design measures *time-to-solution* rather than staring at vCPU counts or nominal network interface speeds alone.

## 1. Distinguishing HPC from Standard Cloud Workloads

Web applications can distribute largely independent requests across different instances. An MPI-based HPC application may require all processes to reach a synchronization barrier before the simulation step advances; if one node lags or network latency spikes, the entire job stalls.

| Characteristic | Typical Web / Service App | HPC Workload |
| --- | --- | --- |
| Unit of work | Independent request or task | Job, rank, domain decomposition, collective operation |
| Primary goal | Latency, availability, RPS | Time-to-solution, job throughput, parallel efficiency |
| Communication | HTTP/gRPC, database, queue | MPI, TCP, and potentially RDMA on supported hardware |
| Scaling model | Add instances to serve requests | Add CPUs/nodes, accounting for synchronization overhead |
| Common risks | CPU/DB saturation, timeouts | Slow network, load imbalance, I/O bottlenecks, single rank failure |
| Scheduler | Autoscaler or general job queue | Slurm or an appropriate batch/HPC scheduler |

HPC workloads fall into two broad categories:

- **Loosely coupled:** each task is nearly independent, such as running thousands of parameter sweeps or rendering individual frames. Typically scales easily with task count and can use Spot VMs with proper checkpointing or retries.
- **Tightly coupled:** many processes continuously exchange data, such as a multi-node domain-decomposed CFD simulation. Requires careful attention to latency, bandwidth, topology, node homogeneity, and placement.

Identify which category your application belongs to upfront; an architecture tuned for independent batch jobs may fail badly for multi-node MPI.

## 2. Gathering Requirements and Performance Profiles

Before selecting machine types, benchmark a representative problem in an active environment:

| Question | Data to Record | Related Decision |
| --- | --- | --- |
| How many CPU cores does the job use? | CPU utilization, rank/thread counts, scaling efficiency | vCPU and node counts |
| How much RAM does it need? | Peak RSS, per-rank memory footprint, NUMA locality | Machine family, RAM/node |
| How do ranks communicate? | MPI message sizes, collective frequency, latency sensitivity | Networking, placement, RDMA |
| How large are inputs and checkpoints? | Total bytes, IOPS, throughput, small-file count | Local SSD, Hyperdisk, Filestore, Parallelstore |
| How long does a job run? | Median/p95 runtime, startup and queue wait times | Scheduler, Spot/standard VMs |
| Are GPUs or accelerators used? | GPU memory, kernel utilization, data transfer | GPU machine family, GPU libraries |
| How many jobs run concurrently? | Queue depth, job priorities, peak demand | Quotas, capacity, cluster autoscaling |

For instance, consider a job running 64 MPI ranks, each using ~2 GiB RAM and exchanging small messages every solver iteration. Adding nodes without improving interconnect performance can sharply increase synchronization wait times and fail to reduce time-to-solution.

Lock down a fixed dataset and application version for testing. Never compare two VMs using different inputs or different compiler optimization flags.

## 3. Reference Architecture for an HPC Cluster on GCP

A typical HPC cluster separates login/head nodes, scheduler, compute nodes, storage, and observability. Control-plane components should stay off compute nodes so administrative tasks do not contend with solver execution.

~~~mermaid
flowchart TB
  U["Researcher / CI"] --> L["Login node / IAP / OS Login"]
  L --> Q["Slurm controller and job queue"]
  Q --> C1["Compute Engine worker group A"]
  Q --> C2["Compute Engine worker group B"]
  C1 <-->|"MPI / high-performance network"| C2
  C1 <--> F["Shared filesystem"]
  C2 <--> F
  F <--> O["Cloud Storage: input / artifact / backup"]
  Q --> M["Metrics, logs, job accounting"]
  C1 --> M
  C2 --> M
  I["IAM, quotas, images, and policies"] --> Q
  I --> C
~~~

The arrow between worker groups represents logical multi-node communication, not a separate standalone network link present in every VPC. For RDMA, an actual diagram must reflect the exact NICs, interfaces, and networks supported by the chosen machine family.

Key architectural decisions:

1. Run compute nodes in a **single zone** for tightly coupled jobs when hardware and placement support it, avoiding unnecessary cross-zone latency.
2. Use homogeneous VM configurations within a partition to prevent straggler ranks.
3. Define clear lifecycles for schedulers, images, storage, and access provisioning.
4. Omit public IPs on compute nodes unless required; enforce controlled management paths and egress.
5. Separate input data, temporary scratch, checkpoints, and final outputs according to performance and durability requirements.

## 4. Choosing Compute Engine Machine Families

Compute Engine offers machine families targeting HPC, compute-intensive, or GPU workloads—such as H3, H4D, and relevant C- or A-series families. Exact catalogs, vCPU counts, RAM, GPUs, network bandwidth, RDMA support, disk types, and supported zones vary by product generation and location. **Never assume a feature exists on every machine simply because it runs on Compute Engine.**

| Criterion | How to Evaluate |
| --- | --- |
| CPU performance | CPU architecture, clock speeds, instruction sets, compiler optimization, solver benchmark results |
| Memory capacity | GiB per node; sufficient RAM for ranks and buffers |
| Memory bandwidth / NUMA | Memory bandwidth and locality when multiple processes share a node |
| Network | gVNIC, supported bandwidth/tiers, latency, RDMA if available |
| GPU/accelerator | CUDA/driver compatibility, GPU memory, and family-specific interconnects |
| Storage | Supported Persistent Disk/Hyperdisk/Local SSD types, bandwidth, and IOPS |
| Availability | Quotas, actual zonal capacity, reservations, and maintenance policies |
| Cost | Price per node-hour and cost per completed job, not just price per vCPU |

For example, if a job consumes heavy RAM while leaving CPUs underutilized, adding CPU cores only inflates cost. If a job spends most of its time in MPI exchanges while CPUs sit idle waiting on the network, focus on communication, placement, and domain decomposition before upgrading to higher-vCPU machines.

Benchmark at least two supported configurations and measure time-to-solution on the actual representative job. Do not pick VMs solely from advertised peak network bandwidth.

## 5. Placement and Fault Domains

For tightly coupled HPC, physical distance between nodes and network topology directly impact latency. Compute Engine offers placement policy options, where **compact placement** can benefit co-located node groups, though availability depends on machine family, zone, VM count, and capacity.

Principles:

- Keep MPI communicators inside a single zone; avoid spanning communicators across regions.
- Verify the target VM type supports the planned placement policy and node-count limits.
- Validate actual capacity before setting multi-thousand-rank thresholds for a job.
- Explicitly document mappings between scheduler partitions, machine families, zones, and network traits.
- Never allow a multi-node MPI job to scatter inadvertently across mismatched machine configs or network tiers.

Co-locating nodes lowers latency while concentrating hardware failure risk within one infrastructure fault domain. This is a conscious HPC trade-off. Durability and recovery are achieved through checkpointing, job restartability, data backups, and standby region plans—not by stretching synchronous MPI jobs across regions.

## 6. gVNIC, Network Bandwidth, and RDMA

Google Virtual NIC (**gVNIC**) is Google Cloud's optimized virtual network interface supported on modern VM types. Pairing gVNIC with an appropriate network performance tier can deliver higher TCP/IP throughput, though real throughput remains bounded by VM shape, traffic patterns, flow counts, CPU load, packet sizes, and destinations.

**Remote Direct Memory Access (RDMA)** enables inter-node memory communication with lower CPU overhead under suitable conditions. On Google Cloud, Cloud RDMA and high-performance fabrics are available only on specific supported VM types and configurations, paired with specific drivers, runtimes, and network setups per product docs.

| Attribute | Standard VPC TCP/IP Networking | RDMA on Supported Configurations |
| --- | --- | --- |
| Application model | TCP/UDP sockets, HTTP/gRPC, MPI over TCP | MPI/libraries with compatible RDMA transports |
| CPU overhead | Traverses TCP/IP stack and kernel processing | Can reduce overhead via appropriate data paths |
| OS requirements | NIC driver, gVNIC if enabled | Compatible drivers, userspace stack, and RDMA configuration |
| Constraints | Bandwidth/latency tied to VM shape and path | Restricted by machine family, zone, topology, image, and libraries |
| Compatibility | Broad across most workloads | Requires benchmarking and framework/transport verification |

You cannot enable RDMA simply by selecting gVNIC or raising MTU. On VM types supporting Cloud RDMA, configure the exact NICs/interfaces, images/drivers, and libraries (e.g., MPI built with the right transport), and verify traffic actually traverses the fast path. Always pull exact settings from the machine family and software version documentation.

## 7. Latency, Bandwidth, and Message Size

MPI performance is never defined by a single Gbps figure. For small messages, per-message latency and collective frequency dominate; for large messages, bandwidth, memory copies, and network saturation matter most.

A simplified model for a single message:

\[
T_{\text{message}} \approx L + \frac{S}{B}
\]

Where \(L\) is fixed latency, \(S\) is message size, and \(B\) is effective bandwidth. This is an approximation: concurrent transfers, congestion, MPI collectives, and topology can significantly alter observed behavior.

Measurements should cover:

- **Ping-pong latency:** small messages between two nodes and across multiple node pairs.
- **Sustained bandwidth:** large messages and multiple flows to gauge effective bandwidth.
- **MPI collectives:** Allreduce, Alltoall, and Barrier across increasing rank counts.
- **Real application:** time-to-solution and MPI wait times, not microbenchmarks alone.

For a given simulation, increasing rank count can lower computation time while raising synchronization overhead. Identify the sweet spot where compute gains still outweigh communication overhead.

## 8. VPC, Subnet, Firewall, and MTU Design

An HPC cluster needs VPCs/subnets sized with enough IP space for worker nodes, controllers, storage endpoints, and management tooling. For autoscaling clusters, IPAM must size for **peak VM count**, not steady-state baseline counts.

A clean segmentation model:

| Zone / Tier | Components | Principle |
| --- | --- | --- |
| Management | Login nodes, scheduler, monitoring | Restricted strictly to authorized admin sources |
| Compute | Worker nodes, MPI traffic | Allow required worker-to-worker flows; zero public ingress |
| Storage | NFS/parallel FS endpoints, object storage paths | Authorized workloads only |
| Egress | Package registries, APIs, update endpoints | Private Google Access/NAT/proxies as required |

Firewall rules must match the actual ports and transports used by the scheduler, MPI, and storage. Never open all ports to the Internet just because MPI uses dynamic ephemeral ports. Specifically validate multicast, UDP, or custom transport behavior if used by your application.

**MTU:** VPCs support configurable MTUs within product limits, yet jumbo frames only help when the end-to-end path and NICs support them. Mismatched MTUs trigger fragmentation, packet drops, or subtle hangs. For Cloud VPN, Interconnect, or RDMA, verify the MTU limit of every link rather than assuming the VPC MTU applies uniformly.

Basic network inspection commands:

~~~bash
gcloud compute networks describe HPC_VPC \
  --project=PROJECT_ID \
  --format="yaml(name,mtu,autoCreateSubnetworks)"

ip -br link
ip -s link
~~~

The two `ip` commands run on a Linux worker node. They only inspect interface configuration and packet counters; they do not prove MPI traffic is using the high-speed NIC or RDMA path.

## 9. Why Cloud Interconnect Does Not Replace Internal HPC Networking

Cloud Interconnect and HA VPN link Google Cloud to on-premises datacenters or external networks using their respective technologies. They excel at staging input data to the cloud and returning results, but they are not drop-in substitutes for a low-latency inter-node network during an MPI job.

If every simulation step exchanges data with an on-premises node, WAN latency will negate the speed of a powerful VM cluster. A far more effective pattern is:

1. Transfer required datasets or checkpoints to storage close to the cloud compute cluster.
2. Run tightly coupled computation inside a single zone with appropriate placement.
3. Save final artifacts and results to durable storage.
4. Sync back to the datacenter in batches or via scheduled pipelines.

When sensitive data must stay on-premises due to residency rules, revisit where compute should live; never try to optimize by stretching tight solver loops across two distant networks.

## 10. HPC Storage: Input, Scratch, Checkpoint, and Output

Different HPC I/O phases have distinct characteristics. One storage class rarely fits every phase optimally.

| Data Tier | Characteristics | GCP Options to Evaluate |
| --- | --- | --- |
| Input / reference | Read repeatedly, requires durability | Cloud Storage, staged into filesystem |
| Shared working set | Concurrent multi-node reads/writes | Filestore or Parallelstore in supported regions/VMs |
| Local scratch | Ephemeral, high throughput/IOPS, durability unneeded | Local SSD or compatible disks |
| Checkpoint | Periodic state saves for failure recovery | Durable storage, snapshots/backups, or object storage per architecture |
| Final results | Long-term retention, shared downstream | Cloud Storage with lifecycle policies |

**Cloud Storage** is object storage and does not natively provide full POSIX shared-filesystem semantics. FUSE mounts help in certain workflows but require evaluating metadata overhead, consistency, and small-file performance.

**Filestore** offers managed file sharing over standard protocols; **Parallelstore** targets high-throughput HPC/AI workloads where supported by product, region, and connectivity. Never assume every machine type supports every service tier or published peak throughput; check provisioning limits and benchmark your real workload.

**Local SSD** is fast but ephemeral and tied to VM lifetime. Never store sole checkpoints or irrecoverable outputs on Local SSD. Offload critical data to durable storage before nodes are deleted, fail, or get preempted.

## 11. File Layout and Parallel I/O Optimization

HPC I/O commonly hits two bottleneck patterns:

- A few massive files demanding high sequential throughput.
- Millions of tiny files stressing metadata operations and IOPS.

In the second pattern, listing, creating, and stat'ing files can take longer than reading data. Reorganize dataset layouts, bundle tiny files where formats allow, and shard directories to reduce metadata contention.

Useful storage benchmarks:

| Test | What to Measure |
| --- | --- |
| IOR or equivalent | Multi-node concurrent read/write throughput |
| mdtest or metadata suite | Create/stat/remove rates and small-file latency |
| Application checkpoint benchmark | Checkpoint size, write duration, and resume time |
| Scale test | I/O scaling from one node to many nodes |

Never mistake host RAM or page-cache results for persistent storage throughput when benchmarking durable I/O. Document dataset sizes, cache policies, flush settings, and run conditions.

## 12. Schedulers: Slurm, Job Queues, and Cluster Autoscaling

Schedulers like **Slurm** manage job queuing, node allocation, and batch execution. On Google Cloud, Cluster Toolkit and supported blueprints help automate HPC infrastructure components; they act as architectural building blocks rather than replacing scheduler operations and version compatibility testing.

Typical lifecycle:

~~~mermaid
flowchart LR
  S["Submit job"] --> Q["Slurm queue"]
  Q --> C["Provision worker nodes"]
  C --> D["Stage data / prepare environment"]
  D --> R["MPI / solver execution"]
  R --> O["Checkpoint + output"]
  O --> U["Reclaim nodes when idle"]
  R --> M["Metrics / exit code / accounting"]
~~~

Define upfront:

- Partitions aligned to CPU/memory/GPU/network tiers and priorities.
- Minimum/maximum node counts, queue timeouts, preemption policies, and scale-out latency.
- How MPI jobs behave when all required nodes cannot be allocated simultaneously.
- Constraints blocking heterogeneous machine types, zones, or images when jobs require uniformity.
- How idle nodes scale down to save money while keeping controllers, job state, and data intact.

For independent batch tasks, Cloud Batch or another orchestrator may fit better. Never force an independent-task orchestrator to guarantee tightly coupled multi-node MPI semantics unless the service explicitly supports them.

## 13. Example Slurm Script for an MPI Solver

The sample job below requests four nodes with eight MPI ranks per node. Numbers are illustrative; rank counts must align with CPU, RAM, and partition policies.

~~~bash
#!/bin/bash
#SBATCH --job-name=cfd-benchmark
#SBATCH --partition=hpc-cpu
#SBATCH --nodes=4
#SBATCH --ntasks-per-node=8
#SBATCH --time=00:30:00
#SBATCH --output=logs/%x-%j.out

set -euo pipefail

echo "Job ID: $SLURM_JOB_ID"
echo "Nodes: $SLURM_JOB_NODELIST"

module load mpi
srun --mpi=pmix ./solver --input ./datasets/case-01.in
~~~

**Prerequisites:** the `hpc-cpu` partition exists; the matching `mpi` module is installed; the MPI build and Slurm support the same PMIx mode; the `logs` directory exists; and the solver binary plus dataset are accessible on all nodes.

Not every Slurm/MPI installation uses the exact same **`--mpi=pmix`** value. Check with **`srun --mpi=list`** and your cluster configuration. For RDMA transports, verify MPI/UCX or the equivalent stack actually selects the RDMA interface; a successful `srun` execution alone does not prove RDMA was used.

Record solver/compiler/MPI versions and thread-affinity environment variables so benchmarks remain reproducible.

## 14. MPI Tuning, CPU Affinity, and NUMA

HPC performance depends heavily on process placement across CPUs and memory. On multi-NUMA-domain nodes, cross-domain memory access increases latency and lowers effective bandwidth.

Best practices:

- Match rank counts to physical cores and hyperthreading configuration.
- Use CPU binding/affinity to prevent unnecessary process migration.
- Align NUMA locality across threads, memory allocations, and NICs.
- Avoid oversubscription unless the application is explicitly tuned for core sharing.
- Keep compiler flags, MPI libraries, and OS images uniform across workers.
- Measure CPU time, MPI wait, memory bandwidth, and cache misses when profiling tools are available.

For hybrid MPI + OpenMP applications, total threads approximate:

\[
\text{Threads/node} \approx
\text{MPI ranks/node} \times \text{OpenMP threads/rank}
\]

If a node has 64 physical cores but launches 64 MPI ranks with 4 OpenMP threads each, 256 threads will contend for CPUs. Tune **`OMP_NUM_THREADS`**, rank count, and affinity via benchmarks rather than assuming more threads always run faster.

## 15. Illustrative IaC: Compute Engine Worker Without a Public IP

Terraform can standardize worker nodes. The snippet below shows subnet, NIC, service account, and OS Login setup for a VM **with gVNIC support**:

~~~hcl
resource "google_compute_instance" "hpc_worker" {
  project      = var.project_id
  name         = "hpc-worker-example"
  zone         = var.zone
  machine_type = var.machine_type

  boot_disk {
    initialize_params {
      image = var.image
    }
  }

  network_interface {
    subnetwork = var.subnetwork_self_link
    nic_type   = "GVNIC"
    # Omit access_config: no external IPv4 assigned here.
  }

  service_account {
    email  = var.worker_service_account_email
    scopes = ["cloud-platform"]
  }

  metadata = {
    enable-oslogin = "TRUE"
  }

  labels = {
    role = "hpc-worker"
  }
}
~~~

This is a **fragment**, not a complete Terraform cluster: inputs are undeclared, and it omits scheduler, placement policy, filesystems, firewall rules, OS bootstrap, and quota checks. Add those pieces to match your VM types and orchestration tooling.

The **`cloud-platform`** OAuth scope does not grant Owner access: actual permissions remain bounded by IAM. Worker service accounts should hold only permissions needed to read inputs and write outputs/metrics; never assign project admin accounts to compute nodes.

This snippet illustrates VPC/gVNIC only—**it is not a Cloud RDMA configuration**. RDMA-capable machine families carry specific NIC, image, driver, and placement requirements; follow hardware-specific docs instead of adapting this fragment as RDMA config.

## 16. Preparing Images, Dependencies, and Input Data

A 100-node cluster wastes significant startup time if every node downloads compilers, MPI, solvers, and hundreds of GiBs of data from the Internet at job start. Bake versioned images or immutable startup artifacts for stable software, and stage datasets via appropriate storage.

Standard workflow:

1. Standardize the base image and kernel/driver/NIC versions.
2. Install compilers, MPI, solvers, and math libraries with matching ABIs.
3. Verify license servers, environment variables, and required permissions.
4. Track image digests, bootstrap configs, and package versions for rollbacks.
5. Stage data to storage/working directories near workers before MPI launches.
6. Verify checksums and avoid having all workers redundantly download massive datasets.
7. Run an MPI smoke test before opening the cluster to production jobs.

For periodic updates, rebuild images and canary-test on a staging partition instead of patching live nodes by hand. Node drift causes mysterious failures that appear only when jobs hit specific subsets of nodes.

## 17. Quotas, Capacity, and Resource Scheduling

HPC often requires provisioning many VMs simultaneously. Having quota does not mean the target zone holds enough physical capacity for that machine family. Conversely, physical capacity does not guarantee the project has quota or permissions for that machine type.

Always verify:

- vCPU/GPU/Local SSD/network quotas per region or per product quota model.
- Whether the machine type and placement/RDMA features exist in the target zone.
- Reservation eligibility per product policy and cost commitments.
- Expected lead time to acquire all nodes for a high-rank job.
- Risk of partial allocation where some nodes spin up while the rest fail.
- Queue timeouts, retries, and node release rules if a job cannot start.

Initial discovery commands:

~~~bash
gcloud compute machine-types list \
  --project=PROJECT_ID \
  --zones=ZONE

gcloud compute regions describe REGION \
  --project=PROJECT_ID \
  --format="yaml(quotas)"
~~~

These are discovery commands only—they do not confirm instant capacity for a large HPC cluster. Quotas apply across multiple scopes and product models; verify against current project quotas, submit increases ahead of time, or use reservations for predictable demand.

## 18. Spot VMs, Maintenance, and Checkpointing

Spot VMs lower costs for interruption-tolerant jobs. However, a tightly coupled MPI job may have to restart from scratch if a single node is preempted, wasting time and driving up total cost.

Spot fits when:

- Tasks are independent and safely retryable without duplicate side effects.
- Solvers support checkpoint/restart written to durable storage.
- The scheduler handles preemption events with bounded retries.
- Job durations are short enough—or checkpoint intervals frequent enough—for the preemption risk.

Use standard VMs, reservations, or more reliable capacity models for strict-deadline jobs or high restart penalties. Clusters can offer both Spot and standard partitions, routing jobs by fault tolerance.

**Checkpoint interval** is a trade-off: checkpointing too often burns I/O time; too rarely risks losing substantial work on interruption. Measure checkpoint write and restore times at real job scale.

Never rely on Local SSD as the sole checkpoint store. When VMs terminate or experience certain failures, ephemeral local data disappears.

## 19. Measuring Parallel Efficiency: Strong and Weak Scaling

**Strong scaling** holds total problem size fixed while increasing node count. **Weak scaling** scales problem size proportionally with node count to test scalability at constant per-node work.

Suppose a job takes 120 minutes on 1 node and 20 minutes on 8 nodes. Speedup:

\[
S(8) = \frac{120}{20} = 6
\]

Strong scaling efficiency per node:

\[
E(8) = \frac{S(8)}{8} = 75\%
\]

This example **only illustrates the math**, not a benchmark of any specific GCP VM. Always record the exact single-node baseline config, cores/ranks per node, and identical input dataset.

A scaling table should capture:

| Nodes | MPI ranks | Time-to-solution | Speedup | Efficiency | Notes |
| ---: | ---: | --- | --- | --- | --- |
| 1 | Per config | Measure | 1.0 | 100% | Baseline |
| 2 | Per config | Measure | Calculate | Calculate | Network, CPU wait |
| 4 | Per config | Measure | Calculate | Calculate | Collective time |
| 8 | Per config | Measure | Calculate | Calculate | I/O and contention |
| 16 | Per config | Measure | Calculate | Calculate | Quotas, scheduler, placement |

Never measure a single kernel in isolation. Measure end-to-end time from job start until results are committed, breaking down staging, compute, communication, checkpointing, and output phases to target optimizations.

## 20. Designing Repeatable Benchmark Experiments

Measurement procedure:

1. **Lock artifacts:** solver version, container/image, compiler, MPI/transport, flags, and dataset.
2. **Lock placement:** same zone, machine type, placement policy, and per-run node counts.
3. **Lock storage:** same filesystem, dataset, caching policy, and I/O sizes.
4. **Test network independently:** ping-pong, bandwidth, and MPI collectives before solver runs.
5. **Measure workload:** time-to-solution, CPU utilization, MPI wait, memory, and I/O.
6. **Repeat runs:** measure variance and rule out noisy neighbors or cold-start anomalies.
7. **Vary one variable:** node count, networking, placement, or storage—never all at once.
8. **Summarize:** p50/p95 with sufficient samples, speedup, efficiency, and cost per completed job.

Where multi-tier caches exist, state clearly whether runs are cold-cache or warm-cache. If microbenchmarks look great yet the solver lags, inspect domain decomposition, collective frequency, rank skew, shared-file metadata, and memory bandwidth.

## 21. Observability, Alerting, and Operations

HPC observability should combine infrastructure metrics with scheduler and application accounting:

| Layer | Metrics and Signals |
| --- | --- |
| Scheduler | Queue wait, running/pending jobs, node allocation failures, retries/preemptions |
| Compute | CPU utilization, NUMA/memory, disk throughput, OOMs, kernel errors |
| Network | NIC throughput, packet drops, retransmissions, MPI latency, collective wait |
| Storage | IOPS, throughput, metadata latency, filesystem fullness, checkpoint duration |
| Application | Time-to-solution, convergence, rank exit codes, checkpoint consistency |
| Financial | VM node-hours, quota utilization, storage/egress, idle costs, cost per job |

Cloud Monitoring and Cloud Logging capture VM/OS signals when agents and permissions are configured. Specialized signals like MPI wait or solver convergence require application- or scheduler-level instrumentation. Never assume a job succeeded merely because VMs are still running.

Actionable alerts: lost scheduler controller, spiking job failure rate, queue wait breaching targets, filesystem nearing full, unreachable nodes, data staging failures, or quota blocks. Separate user input errors from platform incidents to prevent alert fatigue.

## 22. Security and Access Governance for HPC Clusters

HPC clusters often process proprietary scientific, financial, or IP-sensitive models. Baseline protections:

- Enforce IAM per user, group, and service account; restrict project Editor/Owner roles.
- Use OS Login/IAP or approved bastion access instead of public SSH on every worker.
- Segment head/login nodes from compute nodes with firewalls; omit external IPs on workers.
- Restrict egress to required package repositories and APIs; plan secure patch delivery.
- Enforce encryption and least privilege on buckets, Filestore/Parallelstore, and disks.
- Never embed tokens, SSH private keys, or license secrets in images or committed job scripts.
- Retain audit logs for VM creation/deletion, IAM edits, network changes, and sensitive storage access.
- Configure quotas and budget alerts so a runaway job cannot spawn unbounded VMs or spend.

When multiple teams share a cluster, evaluate isolation across Slurm partitions/users, file permissions, networks, and data tiers. Never assume OS-level Linux user isolation on a shared VM suffices for high-sensitivity workloads; isolate nodes or clusters by trust boundary when required.

## 23. Cost: Optimizing for Time-to-Solution

Hourly VM rates are only one component. A pricier configuration that finishes sooner can lower total job cost:

\[
C_{\text{job}} \approx
\sum_i (\text{VM Hours}_i \times \text{Unit Price}_i)
+ C_{\text{storage}} + C_{\text{network}}
+ C_{\text{orchestration}}
\]

Include boot/staging time, idle node time waiting for cluster assembly, checkpointing, failures, and restarts. Cross-region transfers or datacenter-to-GCP dataset ingestion can also be significant.

For example, scaling from 4 to 8 nodes while only cutting runtime from 60 to 40 minutes increases node-hours from 4 to ~5.33 node-hours (excluding other costs). If SLAs demand faster completion, that trade-off may be worthwhile; otherwise, 4 nodes is more economical.

Cost-control strategies:

1. Shut down idle workers via scheduler-aware autoscaling.
2. Use Spot for restart-capable job classes.
3. Evaluate reservations/commitments for steady long-term demand per product terms.
4. Move long-term outputs to object storage and purge scratch after job completion.
5. Tune rank/thread topology and I/O before adding more nodes.
6. Label jobs/projects/teams for accurate showback and chargeback.

## 24. Availability and DR for HPC

Because HPC optimizes for single-zone performance, its recovery strategy differs from multi-region web apps:

- Store source code, image builds, job definitions, and IaC in recoverable repositories.
- Write checkpoints to durable storage and regularly test restarts from those checkpoints.
- Replicate critical data to another region if RPO/RTO and retention policies require it.
- Maintain plans to rebuild the scheduler/cluster in another zone or region **if compatible hardware and quotas exist**.
- Never assume an active MPI job can live-migrate across regions without stopping and restarting.
- Define RTO and RPO at the job/dataset level, not just VM state.

For example, a 12-hour simulation checkpointing every 30 minutes can resume from the latest checkpoint after an outage. Actual recovery time also includes provisioning the new cluster and staging datasets; never quote RTO as merely VM reboot time.

## 25. Lab: Designing a Multi-Node CFD Cluster

**Scenario:** A research team needs to run MPI-based CFD simulations. The baseline takes 3 hours on one node, uses several hundred GiB of input data, and writes periodic checkpoints. Goals: cut time-to-solution while controlling costs and supporting recovery from node failures.

Execute the following steps:

1. Profile CPU, peak RAM, MPI wait, input/output bytes, and checkpoint duration on the baseline setup.
2. Select two Compute Engine machine types/shapes supported in the target zone; justify both choices.
3. Design IPAM, subnets, firewalls, management access, and zero external IPs on workers.
4. Verify gVNIC, placement policies, network performance tiers, and RDMA support if required.
5. Design the head node, Slurm partitions, max node limits, quotas, and node scale-up/down policies.
6. Select shared filesystems and local scratch matching large/small file profiles, and specify checkpoint locations.
7. Run latency, bandwidth, and MPI collective microbenchmarks; document which network paths are active.
8. Run the solver across 1, 2, 4, and 8 nodes on the same dataset; compute speedup and efficiency.
9. Calculate node-hours, storage/network charges, and cost per completed job.
10. Simulate a worker failure in a test environment, verify scheduler handling, and restart from checkpoint.

**Deliverables:** architecture diagram, VM/zone/network/storage selection table, sample scheduler/job configs, benchmark table with real metrics, cost estimate, and recovery runbook.

Never run heavy load benchmarks in production projects or request major quotas/allocations without budget approval, time limits, and an assigned owner.

## 26. Common Design Pitfalls

| Mistake | Consequence | Fix |
| --- | --- | --- |
| Adding vCPUs without measuring MPI wait | Minimal speedup, higher spend | Profile compute and communication separately |
| Picking VMs from advertised Gbps alone | Fails solver latency/throughput needs | Run MPI microbenchmarks and real app tests |
| Confusing gVNIC with RDMA | Traffic misses expected fast path | Verify supported machine/NIC/driver/stack |
| Spanning tightly coupled MPI across regions | High latency and extra fault domains | Keep jobs inside a single zone where suitable |
| Mixing VM types in one MPI partition | Slowest rank bottlenecks all barriers | Enforce homogeneous nodes per partition |
| Using Local SSD as sole checkpoint store | Loses restart capability on reclamation | Write checkpoints to durable storage |
| Treating object storage as POSIX shared FS untested | Metadata stalls or semantic bugs | Evaluate Filestore/Parallelstore and run I/O tests |
| Ignoring quotas, capacity, and placement | Long queues or partial node allocations | Plan quotas, reservations, and queue policies |
| Running non-restartable jobs on Spot | Total progress lost on preemption | Use standard VMs or implement checkpoints |
| Skipping image/MPI version control | Unreproducible benchmarks, runtime breaks | Version images and run compatibility tests |
| Monitoring only VM uptime | Misses failed or diverged jobs | Track job accounting, solver metrics, and logs |
| Ignoring idle nodes and data transfer costs | Real spend exceeds budget estimates | Track cost per completed job |

## 27. Pre-Launch HPC Cluster Checklist

- Workload classified as loosely or tightly coupled with a reproducible baseline.
- Profiles captured for CPU, memory, network communication, I/O, and runtime.
- Machine type, zone, placement, NIC, and RDMA support verified against real availability.
- Cluster partitions use homogeneous nodes with tuned rank/thread placement.
- IPAM, subnets, firewalls, admin access, and egress follow least privilege.
- Shared FS, scratch, checkpoint, and output tiers have clear capacity, performance, and durability policies.
- Scheduler handles pending queues, retries, node capacity, time limits, and cleanup.
- Quotas/capacity verified, with fallback plans for stockouts or preemptions.
- Network/MPI microbenchmarks and strong/weak scaling tested on a representative dataset.
- Dashboards track scheduler, nodes, network, storage, job success, and cost.
- Secrets, data, images, licenses, and service accounts are secured.
- Checkpoint/restore and cluster recovery tested for zone or VM failures.
- Spend caps, review schedules, and cluster operational owners are established.

Designing HPC on Google Cloud is a whole-system optimization problem, not simply picking the biggest VM. Compute Engine provides raw compute; proper networking and placement let processes collaborate efficiently; storage and schedulers deliver data and capacity on time. By measuring time-to-solution, scaling efficiency, and cost per job, teams can make evidence-based choices across CPUs, GPUs, gVNIC, RDMA, storage, and cluster scale while preserving security and resilience across specialized infrastructure.

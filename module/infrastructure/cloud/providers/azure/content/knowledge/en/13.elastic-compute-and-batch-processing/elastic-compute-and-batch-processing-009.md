# Designing HPC workloads and using GPU virtual machines

One research team must run 20,000 engineering simulations before the weekend; another needs to train an AI model on a massive dataset, while a design team needs interactive 3D rendering sessions. All three want to tap into Microsoft Azure's large-scale compute capacity, yet **they should not all pick the same GPU VM type, the same cluster structure, or the same billing model**.

**High-Performance Computing (HPC)** is the practice of organizing compute, networking, and storage resources to execute workloads demanding high performance. A **GPU** is an accelerator processor suited for specific math operations; GPUs help in many HPC, AI, and graphics workloads, yet **not every HPC workload needs a GPU**. Proper design starts from the computation model, parallelism pattern, memory needs, and data access, then selects the VM family, scheduler, and cost model.

This lesson belongs to the **Elastic Compute and Batch Processing** chapter of the `CLOUD_PROVIDERS_AZURE` module. The module explores Azure from subscriptions, resource groups, and Microsoft Entra ID through virtual networks, compute, storage, and data, then teaches how to deploy, monitor, secure, and control costs for an application architecture. For HPC, **scaling resources with the queue and releasing VMs when idle** is often just as important as single-job execution speed.

## 1. Learning objectives

After this lesson, you will be able to:

1. Classify workloads into **independent batch**, **tightly coupled MPI HPC**, **GPU-accelerated computing**, **AI training/inference**, or **visualization**.
2. Select Azure VM families by **CPU, GPU, VRAM, RAM, I/O, and inter-node interconnect**, rather than looking only at vCPU counts.
3. Explain why **RDMA/InfiniBand** and **accelerated networking** are not the same feature.
4. Design storage tiers for inputs, scratch, and outputs using Azure Blob Storage, Azure Managed Lustre, Azure NetApp Files, or appropriate alternatives.
5. Compare **Azure Batch**, **Azure CycleCloud with Slurm**, and other orchestrators by job type.
6. Prepare GPU drivers, CUDA/ROCm libraries, MPI, NCCL, and images matching hardware requirements.
7. Plan quotas, capacity, autoscaling, checkpointing, and Spot eviction handling.
8. Calculate **cost per job** instead of only comparing hourly VM rates.
9. Monitor GPU utilization, VRAM, throughput, runtime, I/O, and distributed failures.
10. Draft a reference architecture for an engineering simulation or multi-node AI training problem.

## 2. HPC, batch, GPU, and AI: distinct concepts

| Concept | Nature | Examples | What to optimize |
|---|---|---|---|
| **Batch processing** | Queues and processes tasks in batches, typically non-interactively. | Converting 100,000 files, rendering independent scenes. | Throughput, scheduling, autoscale, cost/job. |
| **HPC** | Combines high-performance resources to solve large compute problems. | CFD, materials simulation, weather forecasting. | Time-to-solution, parallelism, bandwidth/latency. |
| **CPU HPC** | Uses CPUs with high compute/memory bandwidth/interconnects. | Certain MPI solvers, code not leveraging GPUs. | CPU speed, RAM, memory bandwidth, and RDMA if needed. |
| **GPU computing** | Uses GPUs to accelerate suitable algorithms. | CUDA kernels, deep learning, rendering. | GPU throughput, VRAM, GPU–CPU/GPU–GPU transfers. |
| **Distributed training** | Trains models across multiple GPUs or nodes. | Data-parallel and model-parallel AI. | VRAM, gradient sync, interconnect, checkpoints. |
| **Inference** | Serves prediction requests on trained models. | Image recognition APIs, LLM serving. | Latency, throughput, SLAs, cost/request. |

An **independent batch** job like 20,000 Monte Carlo simulations runs efficiently across hundreds of disconnected CPU VMs because tasks barely exchange data. Conversely, a **tightly coupled MPI** solver continuously exchanges boundary data across processes: network latency and node placement can dictate performance. A large AI model also hinges on **per-GPU VRAM**, interconnects, and parameter sharding.

Therefore, **"more VMs" does not automatically mean "faster job."** A sequential workload gains almost nothing from more nodes, while synchronous communication can slow things down if scaled too wide.

## 3. Analyzing workloads before choosing VMs

A minimal discovery table should cover:

| Question | Data to measure | Architectural consequence |
|---|---|---|
| Are tasks independent? | Job count, dependency graph, data exchange | Batch task pool vs. MPI cluster |
| How are CPU/GPU utilized? | CPU time, GPU utilization, kernel profile | CPU VMs, GPU VMs, or optimize code first |
| How much RAM/VRAM is needed? | Peak resident memory, GPU memory, batch size | Memory-sized SKU and sharding strategy |
| Is I/O the bottleneck? | Input/output size, read/write IOPS, throughput, metadata ops | Object storage vs. POSIX parallel file system |
| Do nodes communicate? | Message rate, size, collective communication | Standard Ethernet vs. RDMA/InfiniBand |
| Target completion window? | Deadlines, queue wait, actual runtime | Parallelism, quotas, capacity reservations if needed |
| Is work interruptible? | Checkpoint interval, retries, idempotency | Spot, autoscale, or dedicated VMs |
| Is data sensitive? | Data classification, residency, permissions, audits | Private networking, encryption, RBAC, region |
| Is usage seasonal? | Run hours/day, jobs/month | Scale-to-zero and budgeting |

### Three common parallelism patterns

**Embarrassingly parallel:** each task runs on its own data with near-zero communication. Fits batch queues and independent nodes.

**Tightly coupled / MPI:** multiple processes solve one shared problem with frequent communication. Requires careful networking and node placement; can benefit from InfiniBand/RDMA.

**GPU parallel:** one or more GPUs execute massive parallel math within a node; when scaling across nodes, tensor/gradient synchronization and inter-node bandwidth become critical.

```text
            Workload
                |
        +-------+-------+
        |               |
   Independent?    Split one job?
        |               |
        v               v
  Batch task pool    CPU MPI or GPU
  + autoscale           |
                    +---+-----------+
                    |               |
               1 node fits?    Multi-node?
                    |               |
                    v               v
              CPU/GPU VM       Scheduler + high-perf
              + local I/O           network
```

## 4. Performance mindset: speedup and efficiency

Suppose a program runs **8 hours on 1 node**. If 4 nodes finish it in **2.5 hours**, we have:

```text
Speedup    = T(1 node) / T(N nodes) = 8 / 2.5 = 3.2
Efficiency = Speedup / N = 3.2 / 4 = 80%
```

Runtime drops, though not linearly by 4×. Overhead can come from:

- Reading/writing input data and checkpoints.
- MPI exchanges across nodes.
- GPU data/gradient synchronization.
- Serial code sections, data prep, or environment initialization.
- Storage contention or queue wait time.

By **Amdahl's law**, if a fraction of work cannot be parallelized, speedup hits a ceiling no matter how many nodes you add. Conversely, problems scaling dataset size alongside node count can be evaluated via weak scaling. Always state clearly whether you are measuring **strong scaling** (fixed problem size, more nodes) or **weak scaling** (scaling data with resources).

For GPUs, measure **end-to-end** time including data loading and CPU↔GPU copies, not just one kernel's execution time. A GPU with high theoretical specs can still run slowly if VRAM overflows, I/O stalls, or the workload lacks parallelism.

## 5. Selecting Azure VM families by workload characteristics

Azure offers many VM families; SKU names, hardware generations, GPU/RDMA capabilities, and regional availability evolve over time. Use the groups below as **selection guidance**, not a feature guarantee across every SKU.

| VM group | General characteristics | Suitable scenarios |
|---|---|---|
| **HB/HC and select H-series** | HPC-optimized primarily for CPU, RAM/memory bandwidth, with select SKUs offering high-speed networking/RDMA. | MPI solvers, engineering compute, CPU scientific simulations. |
| **NC-series** | Compute/accelerated GPU configurations depending on generation. | GPU compute, select AI training/inference or GPU HPC workloads. |
| **ND-series** | High-end GPU configurations for large-scale AI workloads per generation. | Distributed training/large models requiring GPU memory and interconnects. |
| **NV-series** | GPUs for graphics, rendering, or virtual desktops depending on generation. | Visualization, remote workstations, graphics applications. |
| **D/E/F-series** | General-purpose, memory-optimized, or compute-focused CPU VMs per series. | Pre/post-processing, coordinators, non-GPU batch tasks. |

**Do not assume all NC, ND, or NV SKUs share the same GPU, VRAM, GPU count, NVLink, or RDMA.** Even within one family, VM generations differ substantially. Inspect the **exact** SKU specifications: `Standard_...`, GPU count, VRAM capacity, vCPUs, RAM, local storage type, and network capabilities.

### CPU HPC or GPU HPC?

Choose GPUs when:

- The algorithm has mature GPU-accelerated libraries/kernels.
- Parallel compute volume outweighs data transfer overhead.
- VRAM fits the data/model or a supported partitioning scheme exists.
- The team can operate GPU drivers, runtimes, and profiling tools.

Do not pick GPUs merely because computation feels "heavy." If a solver is tuned for CPU/MPI, relies heavily on large host memory, or spends most runtime in sequential I/O, expensive GPU VMs may **improve neither runtime nor cost**.

### Balancing GPU, RAM, and CPU

A GPU node still needs CPUs to decode data, assemble minibatches, drive task execution, run the network stack, and write checkpoints. Pairing powerful GPUs with starved CPU/RAM leaves GPUs waiting on data, lowering utilization.

Conversely, if a model exceeds VRAM:

- Lower batch size or precision within accuracy bounds.
- Pick a GPU with higher VRAM if an appropriate SKU exists.
- Use gradient accumulation, activation checkpointing, model/tensor parallelism, or framework-supported distribution techniques.
- Measure synchronization overhead and complexity instead of assuming "more GPUs always solves it."

## 6. GPU memory and inter-GPU communication

Distinguish the interconnect layers:

| Component | Role | Impact |
|---|---|---|
| **GPU VRAM/HBM** | Direct GPU memory. | Determines whether model/tensors and batch fit in memory. |
| **CPU RAM** | Host memory, data buffers, pre/post-processing. | Keeps pipelines feeding GPUs without starvation. |
| **PCIe** | CPU↔GPU or intra-node device transfers. | Copies and I/O can become bottlenecks. |
| **NVLink/NVSwitch** | High-speed GPU–GPU interconnect on supported configurations. | Valuable for intra-node model parallelism/collectives. |
| **Ethernet** | IP network links between VMs. | Fits many batch workloads or clusters without ultra-low-latency needs. |
| **InfiniBand/RDMA** | Remote direct memory access when supported by VM/network. | Valuable for MPI or multi-node training needing fast sync. |

**Intra-node NVLink does not replace inter-node InfiniBand.** A multi-GPU VM does not automatically have high-speed inter-node networking. When procuring capacity for distributed training, verify both **intra-node topology** and **inter-node interconnect**.

### GPU memory does not simply sum into one shared pool

A VM with 4 GPUs of 40 GiB VRAM each **does not automatically become a single 160 GiB GPU**. Each GPU typically has its own memory space; frameworks must manage tensor/model distribution or data transfers. Effective capacity depends on the parallelism strategy and overhead.

For example, a model needing 60 GiB on **a single device**:

- One 40 GiB GPU may be insufficient.
- Two 40 GiB GPUs can work if the framework supports model/tensor sharding or offloading.
- One GPU with sufficient VRAM can be simpler if supported and cost-effective.

With precisions like FP32, FP16, or BF16, shrinking data types saves memory and boosts throughput, yet depends on hardware support, numerical stability, and accuracy requirements. Never alter precision in scientific simulations or financial models without testing numerical error.

## 7. HPC networking design: Ethernet, Accelerated Networking, and RDMA

**Accelerated Networking** in Azure reduces part of network virtualization overhead and improves throughput/latency on supported SKUs. It is **not synonymous** with a VM having **RDMA** or InfiniBand.

**RDMA (Remote Direct Memory Access)** enables remote memory transfers over a bypassed data path, which can be especially valuable for chatty collective algorithms. In Azure, select HPC/GPU VMs provide dedicated networking and compatible drivers/runtimes.

### What to verify for distributed MPI/GPU clusters

1. Does the **exact SKU** support RDMA/InfiniBand?
2. Are nodes deployed in the **region, zone, and topology** required by the SKU's guidance?
3. Does the image/OS include the required network drivers, kernel, and MPI stack?
4. Does the scheduler allocate nodes in an appropriate topology for an MPI job?
5. Do subnet/NSG rules allow required cluster traffic?
6. Have you measured network latency, bandwidth, and MPI collectives on real workloads?

For high-performance clusters, physical node placement affects latency. Mechanisms such as **proximity placement groups** or service-supported placement/network topologies can help, yet **do not guarantee RDMA** nor guarantee capacity availability. Support varies by family/SKU and orchestration model.

### VNet, NSGs, and private access

A common architecture:

```text
         Administrators / CI pipeline
                   |
            Microsoft Entra ID
                   |
              Bastion / VPN
                   |
               VNet HPC
          +--------+---------+
          |                  |
     Head / scheduler     Compute subnet
        node             +------+------+
          |              |             |
      Job queue       CPU/GPU-01    CPU/GPU-N
          |              |             |
          +--------> Shared file system <----+
                          |
                 Blob outputs/checkpoints
```

Prefer private IPs for compute nodes, restrict SSH/RDP ingress to management networks, and use managed identity/Entra RBAC for least-privilege Storage access. For RDMA/InfiniBand networks, follow provider configuration guidelines and avoid accidentally blocking intra-cluster traffic.

**Do not assign public IPs to every GPU node just to install software.** Use standardized images, private endpoints, controlled egress via NAT/firewalls, or organization-approved package mirrors.

## 8. Data: separating sources, working sets, and results

An HPC job typically involves distinct data classes:

- **Durable inputs:** datasets, meshes, base checkpoints, model weights.
- **Scratch/working sets:** temporary data, intermediate tensors, partitioned files, caches.
- **Outputs:** simulation results, trained models, artifacts, and logs.
- **Metadata:** job ID, code version, parameters, operator, seeds, image, and provenance.

Do not place every layer on the same disk tier using one storage technology.

| Service / storage type | Strengths | Constraints to check |
|---|---|---|
| **Azure Blob Storage / ADLS Gen2** | Large-scale object data, inputs/outputs/checkpoints, lifecycle policies. | Object API semantics, not natively a POSIX parallel file system for every solver. |
| **Azure Managed Lustre** | High-performance parallel file system in supported regions/SKUs, fits many HPC problems. | Cluster file system setup, Blob integration, quotas, and cost. |
| **Azure NetApp Files** | High-performance managed file service by service level and protocol. | Capacity pools, throughput/latency, protocols, networking, and fees. |
| **Azure Files** | Managed SMB/NFS file shares per supported share tier. | Not automatically sized for metadata/IOPS of thousand-node HPC workloads. |
| **Managed disks** | VM-attached block storage; tiers differ in performance specs. | Per-disk IOPS/throughput and VM limits; not shared like a parallel FS. |
| **Local NVMe/temporary disk** | Very fast scratch/cache on select VMs. | **Ephemeral**: never use as the sole copy of results or critical checkpoints. |

### Data staging model

```text
Azure Blob: data/raw, models, reference
          |
          | stage input / hydrate
          v
Shared HPC file system (if app requires POSIX)
          |
          +--> Compute nodes / GPU nodes
          |       |
          |       +--> Local scratch / temporary checkpoints
          |
          v
      Validated outputs
          |
          | upload by job version
          v
Azure Blob: results/<job-id>/, checkpoints/, logs/
```

Workflow:

1. Stage datasets to an appropriately fast tier before launching jobs en masse.
2. Partition files matching application read patterns; avoid millions of tasks hammering one tiny metadata file.
3. Use local scratch for regenerable data or caches.
4. Persist critical checkpoints to **durable** storage at sensible intervals.
5. Post-job, sync outputs, verify checksums/structure, and record provenance.
6. Clean scratch only after confirming outputs are persisted and recoverable.

Fast GPUs **cannot rescue** a workflow constantly waiting on Storage reads. Measure IOPS, throughput, latency, and metadata operations alongside GPU utilization.

## 9. Choosing an orchestrator: Azure Batch, CycleCloud, or others?

An HPC cluster needs a system deciding **which job runs, how many nodes are needed, when to scale up/down, and how to collect results**.

| Solution | Model | When suitable |
|---|---|---|
| **Azure Batch** | Manages compute pools, jobs, and tasks; supports autoscale and properly configured multi-instance tasks. | Many batch tasks, rendering, independent simulations needing Azure-managed orchestration. |
| **Azure CycleCloud + Slurm** | Manages HPC cluster lifecycle; Slurm schedules jobs/partitions/nodes. | HPC centers with MPI apps, traditional job queues, complex CPU/GPU clusters. |
| **Azure Machine Learning** | Managed jobs/pipelines, distributed training, and ML lifecycle per supported configs. | AI/ML workloads needing experiment tracking, datasets, environments, model registry. |
| **Azure Kubernetes Service** | Container orchestration with GPU node pools and compatible schedulers/integrations. | Containerized workloads, inference/services, and select batch/distributed patterns. |
| **Self-managed VMs** | DIY scheduler, images, scripts, queues, and scaling. | Niche cases; full operational cost and complexity burden. |

Do not equate **VM Scale Sets** with an HPC scheduler: VMSS manages VM groups, yet does not natively provide job queues, job dependencies, MPI topologies, or application-aware retries.

### Azure Batch: many relatively independent tasks

Concept:

```text
Job: monthly-risk-simulation
      |
      +--> Task 0001 -> compute node
      +--> Task 0002 -> compute node
      +--> Task 0003 -> compute node
      ...
      +--> Task 20000 -> compute node
      |
      +--> collect results -> Blob Storage
```

In Azure Batch, a **pool** holds compute nodes; a **job** organizes tasks; **tasks** run commands or programs. Settings cover VM images, sizes, quotas, node count/autoscale, Storage permissions, startup tasks, and dependencies.

Some MPI workloads can use Batch **multi-instance tasks** in supported configurations; never assume every MPI/RDMA app works without verifying networking, images, and process placement.

### Azure CycleCloud and Slurm: traditional HPC clusters

CycleCloud deploys/manages clusters from templates and infrastructure components; Slurm handles **job queues, resource requests, partitions, node allocation, and job states**.

Example Slurm submission commands on an **already configured** cluster:

```bash
sbatch --nodes=4 --time=02:00:00 run-solver.sh
squeue --me
sacct -j <JOB_ID>
```

These commands merely illustrate scheduler interfaces. Partition names, GPU resource directives, and Slurm accounts vary; match cluster-specific scripts. Never submit unapproved or unbudgeted jobs to a Production cluster.

### When is a complex scheduler unnecessary?

If you run only one small GPU job weekly on a single VM, standing up a full Slurm cluster adds needless effort and cost. A scheduled batch job, a managed ML job, or a VM scripted to spin up and shut down on completion can be much simpler.

## 10. Designing HPC nodes and queues

A professional cluster typically separates:

- **Login/management node:** where engineers prepare commands; avoid running heavy compute jobs here regularly.
- **Scheduler/head node:** manages queues, policies, and node allocations.
- **CPU compute nodes:** run pre/post-processing or CPU solvers.
- **GPU compute nodes:** execute training/rendering/GPU kernels.
- **Shared file system:** shared data at matching throughput.
- **Control plane/monitoring:** logs, metrics, alerts, billing, automation.

### Partitions and queue policies

Illustrative logical partitions:

| Partition / queue | Resources | Illustrative policy |
|---|---|---|
| `cpu-short` | CPU VMs | Short jobs, low wall-clock cap. |
| `cpu-mpi` | HPC CPU nodes, compatible interconnect | Multi-node MPI. |
| `gpu-single` | GPU nodes | Single node, GPU and VRAM limits per need. |
| `gpu-distributed` | GPU nodes with matching interconnect | Multi-node distributed training. |
| `spot-batch` | Spot VMs where supported | Idempotent/checkpointed jobs only. |

Partitions are **scheduler planning constructs**, not pre-created Azure resource names. Configure queue permissions, per-group resource caps, and fair-share/priorities when multiple teams share a cluster.

### Autoscale and scale-to-zero

Ideal batch flow:

1. Jobs enter queue → scheduler/Batch spins up matching nodes.
2. VMs boot and run startup/driver/bootstrap scripts.
3. Scheduler waits for ready nodes and dispatches jobs.
4. Jobs run, writing logs and checkpoints.
5. Jobs finish → outputs persisted to durable storage.
6. Nodes sit idle past threshold → reclaimed to avoid unnecessary compute billing.

**Scale-to-zero of compute nodes does not make the entire cluster free when idle.** Head nodes, storage, gateways, vaults, networking, and logging platforms can still accrue fees. Some schedulers/templates require specific setup to scale compute to 0 without disrupting orchestration services.

## 11. Preparing GPU VMs: images, drivers, runtimes, and frameworks

An allocated GPU VM **does not mean** drivers and applications are ready. Verify every layer:

| Layer | Component | Verification |
|---|---|---|
| Infrastructure | Exact GPU SKU, region/zone, quota | VM landed on intended hardware. |
| OS / image | Supported Ubuntu/RHEL/Windows or HPC/AI image | Kernel, firmware, patches, and support matrix. |
| GPU driver | NVIDIA or AMD driver matching GPU model | Driver detects devices cleanly with zero errors. |
| Compute runtime | CUDA/cuDNN or ROCm per hardware and app | Versions compatible with driver and framework. |
| Distributed libs | MPI, UCX, NCCL, or equivalent runtime | Built for target network and driver; tested multi-node. |
| Application | Solver, PyTorch/TensorFlow, or ISV software | Versions, licenses, precision, data validation. |
| Container | Image + GPU container runtime/toolkit if used | GPU devices and host driver exposed properly. |

**CUDA is NVIDIA's platform**—not every GPU uses CUDA. If VMs use AMD GPUs, verify supported ROCm software stacks; an app with CUDA-only kernels cannot run unchanged on another vendor's GPU.

### Checking GPUs on Linux

After connecting over an approved management channel with NVIDIA drivers installed:

```bash
nvidia-smi
```

Query useful benchmark telemetry:

```bash
nvidia-smi \
  --query-gpu=index,name,memory.total,memory.used,utilization.gpu,temperature.gpu \
  --format=csv
```

If `nvidia-smi` is missing or finds no GPU, the VM may not use NVIDIA GPUs, drivers may be missing/incompatible, OS/image may be mismatched, or hardware may not be exposed per config. Before reinstalling drivers, check **SKU**, GPU vendor, image, and matching driver docs.

`nvcc --version` checks the CUDA compiler when the toolkit is installed; lacking `nvcc` **does not prove** the CUDA runtime/driver is broken, since many runtime containers omit the compiler.

### Checking GPU topology

With NVIDIA and supported drivers:

```bash
nvidia-smi topo -m
```

This displays interconnects among GPUs, CPUs, and related devices. Check SKU specs if your app depends on NVLink/NVSwitch; never infer from series name alone.

### Image management

For production clusters:

1. Lock a **golden image** or versioned container image.
2. Record driver, CUDA/ROCm, MPI/NCCL, package versions, checksums, and OS version.
3. Validate a reference job on 1 node, then multi-node.
4. Upgrade images in controlled waves; avoid mixing incompatible node versions inside a single job.
5. Keep configs in IaC/version control; **never** bake Storage keys or secrets into images.

If MPI/GPU jobs break after a driver update, verify alignment across kernel version, userspace libraries, driver/firmware, and container runtime before blaming app code.

## 12. Quotas, capacity, and region/zone selection

This is one of the most frequent failure points when deploying GPU/HPC on Azure.

**Quota** is the resource limit (such as family vCPUs in a region) a subscription is allowed to request. **Capacity** is the physical hardware Azure can actually allocate for a given SKU and location at deployment time.

A subscription with **plenty of quota** can still receive **insufficient capacity** errors for a specific SKU at that moment. Conversely, a region flush with GPUs does not help if your subscription's family quota is 0.

| Factor | What to check |
|---|---|
| **SKU availability** | Is the SKU supported in the target region/zone and subscription? |
| **Regional vCPU quota** | Is overall regional vCPU quota sufficient? |
| **VM-family quota** | Is the specific GPU/HPC family quota sufficient? |
| **Availability Zone** | Is a specific zone configured; does the SKU support it? |
| **Physical capacity** | Are enough nodes of that size available when needed? |
| **Placement/network constraints** | Any extra rules for RDMA/InfiniBand, zones, placement groups, or networking? |
| **Commercial options** | Do on-demand, reservations, capacity reservations, or Spot fit? |

**Reserved Instances** are typically commitment-based cost optimizations, **not automatic guarantees** of physical capacity at VM creation time. For tight-deadline workloads, evaluate **on-demand capacity reservations** within supported families/SKUs or Azure-provided capacity assurance options. Do not assume every GPU/HPC SKU supports capacity reservations via the exact same mechanism.

### Initial checks via Azure CLI

The commands below are **read-only**, illustrated with `eastus`; substitute your target region before drawing conclusions:

```bash
az account show \
  --query "{Subscription:id,Name:name,Tenant:tenantId}" \
  --output table

az vm list-skus \
  --location eastus \
  --resource-type virtualMachines \
  --size Standard_NC \
  --output table
```

Check quota/usage where supported by API:

```bash
az vm list-usage \
  --location eastus \
  --output table
```

`list-skus` shows reported SKU support and API-returned restrictions; `list-usage` shows quota limits. **Neither command guarantees instances will allocate successfully when a job starts.**

If additional quota is needed, submit quota requests via the Azure Portal or approved support channels. For scarce GPUs, requesting quota must never be left until after locking a deployment deadline.

## 13. On-demand, Spot, and interruption handling

| Option | Advantage | Risks / conditions |
|---|---|---|
| **On-demand VM** | Flexible model with no long-term commitment. | Billed by usage time; still carries capacity risk. |
| **Azure Spot VM** | Lower pricing when spare capacity exists. | Can be **evicted**; no availability or runtime guarantee. |
| **Reservations / savings mechanisms** | Reduces cost for steady utilization. | SKU/scope rules and commitments; not a capacity guarantee. |
| **Capacity reservation (if supported)** | Suits workloads requiring guaranteed capacity at set times. | Specific SKU, region, zone scope, charges, and operational rules. |

### When to use Spot?

Use Spot when a job:

- Can **retry** or **resume from checkpoints**.
- Has no hard deadline or has schedule buffer.
- Keeps inputs in durable storage and writes periodic outputs.
- Does not keep unique state on local NVMe/temporary disks.
- Uses a scheduler capable of replacing evicted nodes.

Avoid placing **sole coordinator nodes**, critical metadata, or multi-hour **uncheckpointed** MPI jobs on Spot without interruption handling. In tightly coupled MPI jobs, losing one node can fail the entire job.

### Checkpointing as part of the design

Example 12-hour training job writing a checkpoint to durable storage every 30 minutes:

```text
Start ── 30m ── checkpoint 01 ── 30m ── checkpoint 02 ── ...
                                        |
                                  Spot eviction
                                        |
                          Requeue job with checkpoint 02
                                        |
                                     Resume
```

Checkpoints must capture **model weights/optimizer state, step progress, seeds, data configuration, and required metadata**. Saving model weights alone may not resume a training loop accurately.

For scientific HPC simulations, checkpoints must align with solver state and restart semantics; never treat copying a half-written directory as a consistent checkpoint.

## 14. Securing data and access in HPC clusters

Because HPC often handles proprietary research, customer data, or high-value models, lock down both the **cluster** and the **data pipeline**.

### Access control

- Use **Microsoft Entra ID** and **Azure RBAC** to manage Azure resources with least privilege.
- Use managed identities for nodes/apps accessing Storage or Key Vault within scoped permissions.
- With Slurm, configure dedicated accounts/users/groups and queue permissions; scheduler permissions **do not automatically mirror** Azure RBAC.
- When using shared filesystems, verify POSIX/SMB/NFS permissions per protocol rather than assuming "inside a VNet" means secure.
- Separate operators authorized to provision hundreds of GPU nodes from users authorized only to submit jobs.

### Networking and secrets

- Compute nodes use **private IPs**; administrative access flows through Bastion/VPN or approved channels.
- Use private endpoints/DNS where appropriate to reach Storage/Key Vault over private networks.
- NSGs/firewalls restrict admin, management, and data traffic without accidentally blocking HPC interconnects.
- Secrets/certificates live in vaults or secure stores—never inside startup scripts, images, or job outputs.
- Control outbound egress to reduce data exfiltration risk while allowing required system/driver/package endpoints.
- Enable encryption at rest and TLS within supported scope; never pass Storage credentials on command lines or in logs.

### Provenance tracking

Record per job:

```text
job_id
input_dataset_version
code_git_commit
container_or_vm_image_version
driver_and_runtime_version
vm_sku_and_gpu_count
scheduler_parameters
start_and_end_timestamp
output_location
validation_metrics
owner_and_cost_center
```

This metadata supports reproducibility, root-causing differences after image upgrades, and departmental chargeback.

## 15. HPC/GPU costs: measure per completed job

**The lowest hourly VM rate rarely yields the lowest cost per result.** Faster VMs can cut runtime enough to lower total spend.

Simple formula:

```text
Compute cost = VM count × VM run hours × hourly rate
Total cost   = compute + storage + data transfer + networking
               + scheduler/head nodes + logging + licenses + other fees

GPU-hours    = VM count × GPUs/VM × run hours
Cost/job     = total job-attributed cost / valid completed jobs
```

### Illustrative example, not an Azure quote

A distributed training job uses:

- **4 GPU VMs**, each with **2 GPUs**.
- Runs for **6 hours**.
- Assume an illustrative rate of **5 USD/VM-hour**.

```text
Compute cost = 4 × 6 × 5 = 120 USD
GPU-hours    = 4 × 2 × 6 = 48 GPU-hours
Compute cost / GPU-hour = 120 / 48 = 2.50 USD
```

The 5 USD/VM-hour figure is **strictly hypothetical** for math practice; do not infer any Azure SKU costs that amount. Actual bills also cover storage, logs, data transfer, coordinator nodes, and VM time spent booting or waiting in queues.

### Comparing two SKUs by completion time

Suppose the same job has two options:

| Option | Assumed rate | Measured duration | Compute cost |
|---|---:|---:|---:|
| VM A | 4 USD/hour | 10 hours | 40 USD |
| VM B | 7 USD/hour | 5 hours | 35 USD |

Option B is both faster and cheaper per job despite a higher hourly price—assuming **identical accuracy**, identical data, and verified runtimes.

For batch jobs, track **jobs/hour** and **USD/1,000 jobs**; for AI inference, track **latency, requests/s, cost/1,000 requests**; for simulations, track **time-to-solution** and numerical error.

### Hidden costs to avoid

- Idle GPU nodes waiting on schedulers or storage.
- Head nodes running 24/7 while compute jobs run only a few hours a week.
- Spot evictions forcing jobs to restart from zero.
- Expensive storage tiers holding cold data, or long snapshot/checkpoint retention.
- Cross-region data transfers or Internet egress out of Azure.
- Large datasets copied repeatedly across nodes due to missing shared caches.
- Solver/visualization software licenses billed per node or core.
- Adding GPUs without boosting throughput due to network/CPU/I/O bottlenecks.

## 16. Data-driven benchmarking and sizing

Before scaling a cluster out, run **controlled benchmarks**.

### Minimal measurement suite

| Component | Metrics |
|---|---|
| CPU | CPU utilization, cycles, memory bandwidth, peak RAM |
| GPU | GPU utilization, VRAM usage, power/temperature, kernel time |
| I/O | Read/write throughput, IOPS, p95 latency, metadata ops |
| Network | Bandwidth, latency, retransmissions, MPI collectives |
| Scheduler | Queue wait, node startup time, allocated vs. used time |
| Application | Time-to-solution, samples/s, steps/s, accuracy/convergence |
| Cost | Compute spend, GPU-hours, cost/job, idle ratio |

### Three test rounds

**Round 1 – baseline:** run a small job on 1 CPU or GPU node; measure duration, RAM/VRAM, I/O, and accuracy.

**Round 2 – scale-up:** increase CPUs/GPUs inside one node if SKU/framework permits; measure performance and intra-node communication.

**Round 3 – scale-out:** increase node count with fixed or planned problem size; measure MPI/NCCL overhead, throughput, cost, and stability.

Never compare two SKUs if model versions, compiler flags, batch sizes, precision, or datasets differ; that invalidates the benchmark.

### Understanding low GPU utilization

For instance, 20% GPU utilization may stem from:

- Slow CPU data loading/decoding.
- High-latency storage filesystem reads.
- Batch size too small to saturate the GPU.
- Unoptimized kernels or heavy CPU steps in the pipeline.
- GPUs stalling on collective communication from other nodes.
- Single jobs underutilizing allocated GPUs (oversizing).

Profile accurately instead of blindly adding GPUs or swapping SKUs.

## 17. Cluster operations and monitoring

Azure Monitor collects VM and infrastructure metrics/logs. **Detailed GPU metrics usually require in-guest tools, agents, exporters, or configured integrations**; do not assume every GPU VM natively displays full VRAM, temperature, and utilization on the default metrics pane.

Organize monitoring across three layers:

1. **Infrastructure:** VM state, CPU, memory (with agent support), networking, disks, GPU status, quota, and capacity errors.
2. **Scheduler:** queue wait, failed jobs, node readiness, scale actions, idle GPU count, and eviction events.
3. **Application:** training loss/convergence, solver errors, checkpoint age, validated outputs, business SLAs.

### Recommended alerts

- GPU nodes running past a threshold with near-zero utilization and no useful job.
- Excessive job failures/retries or Spot evictions exceeding plan.
- Near-full VRAM, CUDA out-of-memory, or logged GPU hardware errors.
- Dataloader/storage throughput drops lengthening runtime.
- Latest checkpoint older than recovery policy allows.
- Queue wait breaching deadlines or quotas/capacity nearing exhaustion.
- Project compute spend/budget exceeding thresholds.
- Nodes drifting off approved image/driver versions.

### Job completion workflow

1. Check exit codes/scheduler states.
2. Verify correctness or convergence metrics, not just "process ended."
3. Confirm outputs/checkpoints exist in durable storage with checksums/versions.
4. Log cost, runtime, SKU, node count, and GPU-hours.
5. Clean local scratch/temporary files per policy.
6. Release unneeded nodes; verify autoscaling shrinks properly.
7. Document errors, benchmarks, or improvements for future runs.

## 18. Reference Azure deployment workflow

Suppose a project must run **thousands of independent simulations** and **several GPU jobs**. There is no need to stand up a huge cluster on day one.

### Phase A – Design

1. Gather input sizes, parallelism traits, CPU/GPU profiles, deadlines, and data classification.
2. Choose Batch for mostly independent tasks; consider CycleCloud/Slurm for MPI and dedicated HPC queues.
3. Pick regions/SKUs with sufficient quotas and expected infrastructure supply.
4. Plan VNets/subnets, private access, Storage, shared filesystems, and DNS.
5. Establish budgets, tags (`project`, `owner`, `environment`, `costCenter`), and cleanup policies.

### Phase B – Node preparation

1. Create a small compute pool/cluster following approved workflows.
2. Select a supported OS image and install matching GPU drivers/runtimes or use standardized images.
3. Connect Storage using least-privilege identities.
4. Verify GPUs with `nvidia-smi` for NVIDIA; test MPI/RDMA if planning multi-node runs.
5. Run an end-to-end test on small input.

### Phase C – Testing and scaling

1. Run a metric-instrumented baseline.
2. Scale node counts and compare efficiency/cost/job.
3. Configure scheduler policies, job retries, and checkpoints.
4. Verify accurate results and zero data loss when a node is replaced.
5. Scale within approved quotas/capacity.

### Phase D – Operations

1. Build dashboards for queues, GPUs, storage, and costs.
2. Configure alerts for failed jobs and idle GPUs.
3. Document checkpoint recovery runbooks.
4. Periodically review performance across SKUs/drivers.
5. Spin down resources off-hours and reconcile actual spend.

**Run GPU VM/cluster creation commands only in authorized subscriptions**, as GPU VMs and high-performance filesystems incur substantial costs. CLI examples in this lesson emphasize read-only checks.

## 19. Reference architecture diagram for hybrid HPC and GPU

```text
               Developers / researchers
                       |
                Microsoft Entra ID
                       |
                VPN / Azure Bastion
                       |
               +-------------------+
               | HPC head / queue  |
               | Slurm or Batch    |
               +---------+---------+
                         |
                   Job scheduling
                 /               \
                v                 v
       +----------------+   +------------------+
       | CPU compute     |   | GPU compute       |
       | solver / prep   |   | training / accel  |
       | scale on demand |   | scale on demand   |
       +--------+--------+   +---------+--------+
                |                      |
                +---------+------------+
                          |
                Shared HPC file system
                  (if workload needs)
                          |
                stage data / checkpoints
                          |
                  Azure Blob Storage
                 inputs / outputs / logs

     Azure Monitor + budget + alerts + job metadata
```

This is a logical diagram; in Azure Batch, the scheduler and compute pools are service-managed, without requiring a user-created "head VM." With CycleCloud/Slurm, coordinator nodes are designed and operated per the deployed cluster template.

## 20. Real-world scenario A: CFD simulation requiring MPI

**Requirement:** airflow simulation is one large problem split across 32 processes exchanging boundary data continuously. The solver supports CPU MPI; a GPU build is unverified.

**Common mistake:** immediately picking ND-series GPUs because of the "HPC" label, then submitting 32 independent Batch tasks. Here, all 32 processes **solve one shared problem**, requiring MPI communication and shared data.

**Better design:**

1. Benchmark the CPU solver on a single node.
2. Select an appropriate HPC CPU VM family; verify RDMA if communication patterns warrant it.
3. Use CycleCloud/Slurm or an appropriate cluster mechanism to co-allocate nodes within the same job.
4. Prepare the MPI stack, shared filesystem, and mesh data.
5. Test with 1, 2, 4, and 8 nodes; measure time-to-solution, MPI efficiency, RAM, and I/O.
6. Choose the scale hitting the deadline at reasonable cost; do not scale blindly once efficiency drops.
7. Save checkpoints, outputs, and metadata to durable storage.
8. Periodically regression-test numerical accuracy when updating compilers/MPI/libraries.

**Success criteria:** accurate scientific results, target runtime met, strong CPU/RDMA utilization, and clean restart capability if a node fails.

## 21. Real-world scenario B: distributed GPU training

**Requirement:** an AI model is too large to train fast on one GPU; large datasets live in Blob Storage, with weekly experiment runs.

**Reference design:**

1. Estimate model/optimizer/activation memory and required VRAM.
2. Benchmark 1 GPU, then multi-GPU inside one node to measure scaling.
3. If multi-node is needed, choose GPU VMs with matching interconnects and a distributed-training framework.
4. Use Slurm, Azure Machine Learning, or another workflow managing distributed jobs.
5. Pin compatible image/driver/CUDA/framework versions; verify NCCL communication.
6. Bring data close to nodes and tune dataloader prefetch/caching.
7. Write periodic durable checkpoints containing full resume state.
8. Measure GPU utilization, throughput (samples/s), convergence, network time, and cost/training run.
9. Use Spot only with interruption logic and acceptable deadlines.
10. Store model artifacts and metadata with access controls.

If hitting `CUDA out of memory`, do not immediately add more nodes. First check batch size, model placement, precision, fragmentation, and per-GPU VRAM. Adding nodes only helps when software shards memory properly.

## 22. Common HPC/GPU troubleshooting table

| Symptom | Causes to check | Remediation |
|---|---|---|
| Cannot create GPU VM: quota exceeded | Exhausted family quota or regional vCPU quota | Check usage/quotas, request quota increase, or change options. |
| Quota available yet deployment fails | No capacity left for SKU/zone/placement | Try alternate planned regions/SKUs/zones; consider capacity reservation if supported. |
| `nvidia-smi` fails | Wrong/missing driver, VM lacks NVIDIA GPU, image/kernel mismatch | Verify SKU and vendor, driver support matrix, kernel logs. |
| CUDA runtime mismatch | Incompatible CUDA toolkit/framework, driver, or container version | Pin compatible image and versions; test on a small node. |
| Low GPU utilization | CPU/dataloader, storage bottleneck, small batch, inefficient kernels | Profile end-to-end, increase prefetching, optimize data pipeline. |
| `CUDA out of memory` | Model/batch/activations exceed active GPU VRAM | Tune batch size, precision, activation checkpointing, or proper sharding. |
| MPI/NCCL hangs | Version mismatch, network/driver, topology or firewall, desynced ranks | Check logs, interconnect, rank allocation, and small collective tests. |
| GPU job slower than CPU | Unaccelerated code, copy overhead, poor configuration | Re-benchmark algorithm and measure end-to-end time-to-solution. |
| Jobs keep retrying | Non-idempotent script, missing dependency, Spot eviction, bad node | Inspect scheduler logs, checkpoints, and retry policies. |
| Outputs vanish after VM reclamation | Written only to temporary/local scratch | Transfer outputs/checkpoints to durable storage before cleanup. |
| Low storage throughput | Too many tiny files, undersized shared FS, poor data staging | Use caching/parallel FS appropriately; measure IOPS and metadata ops. |
| Costs exceed budget | Idle GPUs, cluster fails to scale down, cross-region data copies | Analyze tags, VM-hours, storage, and logs; tune queues/retention. |

### Rapid investigation method

1. **Identify job:** job ID, scheduler state, start time, image version, and SKU.
2. **Check resources:** VM state, quotas, visible GPUs, VRAM, CPU/RAM.
3. **Check data:** input availability, mount/file permissions, and throughput.
4. **Check distribution:** rank counts, nodes, networking, and MPI/NCCL libraries.
5. **Check application:** stack traces, exit codes, convergence, and a sample job output.
6. **Check costs:** node time, retry counts, Spot events.
7. **Recover:** pick latest valid checkpoint, fix root cause, and requeue.
8. **Close incident:** confirm valid output, verify nodes released, and document lessons learned.

## 23. Hands-on exercise: designing a controlled HPC/GPU solution

**Context:** A research team has two workload types in the same project:

- **Group A:** 10,000 independent simulations, each using 4 vCPUs and running roughly 20 minutes on a hypothetical CPU configuration.
- **Group B:** training an AI model requiring 4 GPUs running continuously for roughly 8 hours, with checkpoints at least every 60 minutes.
- Shared input is 4 TB in Blob Storage; projected output is 800 GB.
- The team runs only two major waves per month and wants to minimize idle compute.
- Data must not live on public VMs; must use private identities and private networking.
- Must compare cost/job, failure recovery, and verify quotas.

### Tasks

1. Does Group A fit a Batch task pool or a tightly coupled MPI cluster? Why?
2. Should Group B test single-node multi-GPU first or jump straight to multi-node? Why?
3. Define **SKU selection criteria** for CPU nodes and GPU nodes, not merely family names.
4. Design the Blob → staging → compute → Blob output pipeline.
5. Explain how to handle data locality and avoid 10,000 tasks redundantly downloading huge datasets.
6. Define scheduler policies to scale up with the queue and release compute after jobs finish.
7. Design checkpointing, retries, and responsible Spot usage.
8. Choose 5 performance evaluation metrics and 5 operational monitoring metrics/sources.
9. Write formulas estimating VM-hours/GPU-hours and remaining cost items.
10. Identify 3 security risks and their mitigations.

### Solution hints

**Group A:** because simulations are independent, Azure Batch or an equivalent batch scheduler fits well. With 100 parallel task slots assuming each slot finishes 1 job every 20 minutes, **ideal compute duration** is:

```text
10,000 jobs / 100 concurrent jobs = 100 waves
100 waves × 20 minutes = 2,000 minutes ≈ 33 hours 20 minutes
```

This excludes node allocation, data staging, output uploads, retries, and runtime skew. "100 task slots" is a logical unit; actual VM count depends on vCPUs per VM and tasks/node settings. For 4-vCPU jobs, 100 concurrent jobs need matching vCPU capacity without oversubscription slowdowns.

**Group B:** verify whether all 4 GPUs are needed on **one node** or across multiple nodes based on VRAM, GPU interconnects, and framework. If memory and GPUs fit on one node, testing single-node multi-GPU reduces inter-node overhead. If multi-node is mandatory, choose compatible networking and schedulers. Checkpoint at least every 60 minutes or more frequently per training RPO.

**Storage:** Blob holds source data and outputs; stage data onto a throughput-matched filesystem or cache before dispatching jobs; never use local scratch as the sole copy. With 4 TB of data, transfer/read and warm-up costs can be significant.

**Scaling:** provision nodes when queues fill, set idle timeouts, and reclaim nodes once outputs are verified. With two waves/month, keeping GPU nodes running continuously wastes huge budget.

**Security:** private subnets, RBAC/managed identities, secrets in Key Vault, network policies, and audit logs. Never distribute a shared Storage account key inside scripts across all nodes.

**Acceptance:** compare actual runtime/cost against baseline, test failures/retries, prove checkpoint restoration works, and verify all GPU VMs are deallocated post-job.

## 24. Self-check quiz

**Question 1.** Does HPC always require using GPUs?

A. Yes, every HPC job must use NC/ND VMs.  
B. No; HPC can optimize for CPUs, GPUs, or a hybrid mix.  
C. Yes, except on single-node jobs.

**Answer: B.** Hardware selection depends on algorithms, parallelism, memory, and how applications utilize accelerators.

**Question 2.** When does an RDMA/InfiniBand interconnect matter more than standard Ethernet?

**Answer:** For MPI or distributed GPU training workloads with frequent inter-node communication sensitive to latency/bandwidth. Not every independent batch workload needs RDMA.

**Question 3.** Does Azure Accelerated Networking guarantee a VM uses RDMA?

**Answer:** No. Accelerated Networking optimizes VM network paths on supported setups; RDMA/InfiniBand is a separate capability that must be verified per SKU/network.

**Question 4.** A VM has 4 GPUs, each with 40 GiB VRAM. Can one process automatically use 160 GiB of contiguous VRAM?

**Answer:** No. VRAM resides on separate GPUs; utilizing aggregate memory requires an appropriate framework/distribution strategy.

**Question 5.** When GPU utilization is only 15%, should you immediately add more GPUs?

**Answer:** No. First profile CPU/dataloaders, storage, networking, batch sizes, and kernels; adding GPUs when bottlenecked elsewhere raises costs without improving throughput.

**Question 6.** Why can creating a GPU VM fail even when you have GPU quota?

**Answer:** Quota permits requesting resources, yet **physical capacity** for that SKU/zone/region may be exhausted at allocation time.

**Question 7.** Which jobs fit Azure Spot VMs?

**Answer:** Jobs that can checkpoint/retry, keep no unique state on local disk, and tolerate eviction; unsuitable for uninterruptible tight-deadline jobs lacking fallbacks.

**Question 8.** How do Azure Batch and CycleCloud/Slurm differ?

**Answer:** Batch offers a managed pool/job/task model for batch workflows. CycleCloud manages HPC clusters and Slurm provides queue/partition/resource-allocation scheduling, typically suited to specialized HPC/MPI environments.

**Question 9.** If outputs are written only to local NVMe and the VM is reclaimed, what can happen?

**Answer:** Ephemeral data can be lost. Critical outputs/checkpoints must move to durable storage before node cleanup.

**Question 10.** A 7 USD/hour VM finishes a job in 5 hours vs. a 4 USD/hour VM taking 10 hours; which is cheaper for compute?

**Answer:** The 7 × 5 = 35 USD option beats 4 × 10 = 40 USD, given the same job/accuracy; total spend still depends on storage/network and ancillary fees.

**Question 11.** Why record driver/runtime versions per job?

**Answer:** To reproduce results, explain throughput or accuracy shifts, and troubleshoot incompatibilities after image upgrades.

**Question 12.** Can you pick an ND-series GPU solely by family name and assume you get NVLink and InfiniBand?

**Answer:** No. Check the exact model/SKU/series generation, GPU count, GPU–GPU topology, and supported interconnects.

**Question 13.** A 4-node MPI solver runs slower than 1 node. What could cause this?

**Answer:** Synchronization/network overhead, problem too small to scale, placement, MPI settings, or I/O. Run strong-scaling benchmarks and profilers.

**Question 14.** Do you still need backups beyond local scratch when using Azure Managed Lustre or Blob?

**Answer:** Each tier serves a different role: scratch/cache is non-durable, and durable storage still needs backup/versioning/recovery policies matching requirements; never rely on a single copy of data.

**Question 15.** Is a job considered complete once the scheduler reports exit code 0?

**Answer:** Not enough. Verify output data, accuracy/convergence, metadata, durable checkpoints/outputs, and confirm compute resources were released.

**In summary:** Designing HPC/GPU on Azure means coordinating **algorithms – VMs – memory – networking – storage – schedulers – security – cost**. Start with small benchmarks, find bottlenecks, pick the right VM family, scale out only with measured efficiency gains, and always prepare checkpoints/recovery. A great cluster is not the one with the most GPUs, but the one that **finishes work accurately, on time, and within controlled total cost**.

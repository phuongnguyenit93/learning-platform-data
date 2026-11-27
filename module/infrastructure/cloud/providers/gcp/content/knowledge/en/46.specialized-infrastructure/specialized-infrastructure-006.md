# Slurm and HPC Job Queue Organization on Google Cloud

A physics simulation may need hundreds of CPUs for 20 minutes, while a model optimization run requires GPUs for many hours. If research teams request virtual machines manually, resources sit idle or get monopolized by one group; users cannot tell when their turn will come, and administrators struggle to attribute costs per project. **Slurm** solves this orchestration layer by accepting jobs, queuing them, allocating resources according to policy, monitoring execution, and reclaiming resources after completion.

On Google Cloud, Slurm integrates with Compute Engine to spin up compute nodes when jobs are scheduled and tear them down when no longer needed. **Cluster Toolkit** provides blueprints and modules to deploy Slurm, networking, shared storage, and compute resources via Infrastructure as Code (IaC). Operations teams still own scheduling policies, access controls, scientific software correctness, quotas, and budgets; **autoscaling does not mean resources are always available or free when queues are empty**.

This lesson belongs to the **Specialized Infrastructure** chapter in the **CLOUD_PROVIDERS_GCP** module, where learners explore Google Cloud from project organization, IAM, and VPCs to Compute Engine, GKE, Cloud Run, storage, and databases; through deployment scenarios, learners practice selecting services, securing resources, automating releases, and tracking reliability and costs. This topic focuses on designing and operating **Slurm queues for HPC/AI workloads** on Google Cloud—do not confuse Slurm with a general message-queuing service.

> **Lab Scope:** Project names, partitions, jobs, machine types, and pricing examples in this lesson are illustrative. Do not run infrastructure creation or teardown commands against production from this guide. Features, limits, TPU/GPU support, VM shapes, regions, and pricing depend on Cluster Toolkit versions, regions, and specific configurations; always verify in a test project before applying.

## Learning Objectives

After this lesson, you will be able to:

- Distinguish the Slurm scheduler, controller, login node, compute nodes, partitions, nodesets, and accounting.
- Explain the job lifecycle from `PENDING` through `RUNNING` to completion, and how Slurm requests Compute Engine scaling.
- Use `sinfo`, `squeue`, `sbatch`, `srun`, `scancel`, `sacct`, and `scontrol` to submit and monitor jobs.
- Organize partitions by CPU, GPU, batch profile, priority, and capacity model.
- Configure resource limits, job array concurrency, fair-share/QOS, and sensible retry/checkpoint policies.
- Distinguish job waits caused by Slurm policies from Google Cloud quota or capacity shortages.
- Design shared storage, networking, IAM, logging, backups, and cluster lifecycle cost accounting.
- Complete a lab deploying a sample cluster via Cluster Toolkit and cleaning up resources afterward.

## 1. How Do HPC and Slurm Differ from Standard Cloud Applications?

**High Performance Computing (HPC)** typically covers numerical simulations, CFD, bioinformatics, rendering, quantitative finance, optimization, or AI tasks requiring heavy CPU/GPU, memory, I/O, or low-latency multi-node communication.

HTTP apps on Cloud Run/GKE serve incoming requests immediately and autoscale with traffic. An HPC workload may:

- Know upfront how many nodes, cores, RAM, or GPUs it needs.
- Run for tens of minutes to many hours and require checkpointing.
- Require synchronized MPI processes that cannot arbitrarily scale down mid-run.
- Process huge input datasets and emit thousands of output files.
- Have research deadlines or priorities across projects, users, and budgets.
- Need to queue and **wait until all required resources are available together**, rather than handling individual requests.

Slurm manages **batch job queues and resource allocation**. It does not replace Pub/Sub or Cloud Tasks (message/event queues), does not make scientific code restartable by itself, and is not a zero-ops managed service when self-deployed on Compute Engine.

| Requirement | Typical Best Fit | Why |
|---|---|---|
| Multi-node simulations needing MPI and batch queues | Slurm on Google Cloud | Supports job allocation, partitions, priorities, accounting |
| Stateless HTTP APIs | Cloud Run / GKE | Orchestrates requests/replicas rather than HPC batch |
| Independent batch tasks without Slurm policies | Google Cloud Batch | Managed batch service without operating Slurm |
| Kubernetes containers with K8s scheduling | GKE and appropriate orchestrators | Uses Kubernetes APIs, scheduling, and policies |
| Existing on-prem Slurm needing cloud bursting | Hybrid Slurm / Cluster Toolkit | Preserves `sbatch` workflows and expands capacity when designed properly |

Choose your orchestrator based on workload model, team skills, and required control. **Cluster Director** is Google Cloud's Google-managed Slurm offering introduced in **Preview** at reference time; **Cluster Toolkit** is a more flexible open-source IaC framework where cluster operations remain the deploying team's responsibility. Never assume features or SLAs from one option automatically apply to the other.

## 2. Slurm Architecture on Google Cloud

A Slurm cluster typically includes these components:

| Component | Role | Operational Notes |
|---|---|---|
| Login node | Users SSH in, prepare scripts, submit jobs | Never run heavy workloads here |
| Slurm controller (`slurmctld`) | Schedules jobs, decides job/node allocations | Critical control-plane component to monitor and protect |
| Compute nodes (`slurmd`) | Execute allocated tasks | Can be static or dynamic |
| Accounting service (`slurmdbd`), if enabled | Stores job/association history and supports accounting | Needs a database and setup; `sacct` depends on retention config |
| MUNGE or configured auth | Authenticates Slurm components | Protect secret keys, host permissions, and identity sync |
| Shared filesystem | Shares inputs, home dirs, software, and outputs | Metadata performance and throughput govern I/O speed |
| Google Cloud VPC/IAM | Networking, identities, API rights to create/delete VMs | Never confuse Linux users/Slurm accounts with IAM principals |
| Cloud Monitoring/Logging | Observes VMs, controller, and applications | Requires proper collection config; not all job metrics appear automatically |

~~~mermaid
flowchart LR
    U["Researcher"] -->|SSH/IAP| L["Login node"]
    L -->|sbatch/squeue| C["Slurm controller"]
    C --> Q["Queues / partitions"]
    Q -->|Schedule + resume| N["Dynamic compute nodes"]
    C -->|Allocate| S["Static compute nodes"]
    N -->|Read/write| F[("Shared storage")]
    S --> F
    L --> F
    C -->|Cloud API| CE["Compute Engine / quotas / capacity"]
    C --> A[("Optional accounting service")]
    N --> M["Logs/metrics"]
    C --> M
    S --> M
~~~

Logical flow:

1. A user connects to an authorized login node and submits a job via `sbatch`.
2. `slurmctld` queues the job and evaluates partition rules, resource requests, fair-share/QOS, and node states.
3. For dynamic nodesets, Slurm-GCP integration requests Compute Engine to create matching VMs.
4. VMs boot, attach networking/storage, start `slurmd`, and register with the controller.
5. Once required resources are ready, Slurm allocates the job and runs the script on compute nodes.
6. Jobs write stdout/stderr, checkpoints, and outputs while logging accounting records if configured.
7. Upon completion, nodes are retained, suspended, or deleted according to nodeset/partition type and power-saving rules.

**Note:** VM boot times, image setup, filesystem mounts, and MPI/GPU initialization add latency between submission and execution. Autoscaling does not turn a `PENDING` job into `RUNNING` instantaneously.

### 2.1. Login Is Not Compute

Login nodes are for lightweight interactive work: compiling code, preparing inputs, running `squeue`, and inspecting outputs. Heavy jobs belong in partitions on compute nodes.

If users run CPU/GPU workloads directly on login nodes:

- It contends with the Slurm controller or admin tasks if improperly co-located.
- Jobs bypass expected accounting and cgroup resource limits.
- It inflates login node sizing costs and can lock everyone out of the cluster under load.

Enforce Linux access controls, login session resource limits, and clear guidance to move jobs to `sbatch`.

## 3. Core Scheduling Concepts

| Term | Meaning |
|---|---|
| Job | A user-submitted unit of work with a script, resource spec, and lifecycle |
| Job step | An execution step inside an allocation, typically launched with `srun` |
| Partition | A logical set of compute nodes and shared rules for running jobs |
| Nodeset | A homogeneous group of nodes in Cluster Toolkit feeding into partitions |
| Account / association | User/project accounting grouping under Slurm Accounting |
| QOS | Service-level policy controlling priority, preemption, and limits |
| Fair-share | How Slurm adjusts priority based on historical usage and shares |
| Reservation | Resources reserved upfront for a specific time window or group |
| Walltime | Maximum run duration for a job, e.g., `--time=00:30:00` |
| Node resources | CPU, RAM, GPU/GRES, filesystems, topology, or features |
| Static node | Pre-provisioned node with a persistent lifecycle |
| Dynamic node | Node provisioned on demand and reclaimed when idle |

**A partition does not necessarily map to one single VM type.** A partition can reference one or more nodesets. Ensure resources fit the job: mixing overly disparate machine types inside one partition can produce suboptimal placements and unpredictable runtimes.

### 3.1. Job States

| State | Common Code | Interpretation |
|---|---|---|
| Pending | `PD` | Waiting on resources, priority, dependencies, or policies |
| Running | `R` | Job is actively executing |
| Completing | `CG` | Job is finishing and running teardown steps |
| Completed | `CD` | Finished successfully per Slurm status |
| Failed | `F` | Job failed |
| Cancelled | `CA` | Cancelled |
| Timeout | `TO` | Exceeded walltime limit |
| Node fail | `NF` | Node failure impacted the job |
| Out of memory | `OOM` or equivalent | Job hit memory limits |

Exact state strings and exit codes depend on Slurm/plugin configuration. `COMPLETED` does not prove scientific correctness; validate outputs, checksums, convergence, or business checks.

## 4. Preparing Google Cloud Before Deployment

To avoid unexpected bills, use a **dedicated lab project**, budget alerts, tight quotas, and scheduled teardown. Even a basic idle cluster incurs costs for the **controller, login node, disks, shared filesystem, and networking** with zero running compute jobs.

Preparation checklist:

1. Billing-enabled project with permissions for Compute Engine, IAM, Filestore, or chosen storage.
2. Verify **region/zone** availability for machine types, CPUs/GPUs/TPUs, and shared storage.
3. Check quotas: regional CPUs, machine-family quotas, GPUs, disks, IPs, and API limits; also verify actual zonal capacity.
4. Plan VPC, subnets, internal firewalls, SSH/IAP/OS Login, and package download egress.
5. Decide single-zone vs. multi-zone topology; chatty MPI jobs generally need compatible single-zone placement.
6. Create a controller service account scoped to manage compute nodes; never hand JSON keys to users.
7. Design Linux user/group mapping and Slurm accounts/QOS; never share root across users.
8. Select shared filesystems, mount paths, input/output layouts, and checkpoint policies.
9. Pick a maintained Cluster Toolkit blueprint, pin versions, and review the Terraform plan.
10. Tag cloud resources by cluster/project/owner/cost-center and define lab cleanup steps.

Example enabling core APIs with an authorized bootstrap account:

~~~bash
gcloud services enable \
  compute.googleapis.com \
  iam.googleapis.com \
  file.googleapis.com \
  secretmanager.googleapis.com \
  storage.googleapis.com \
  serviceusage.googleapis.com \
  --project=HPC_LAB_PROJECT_ID
~~~

Required APIs vary by blueprint. **Do not grant `Owner` by default** to the controller service account; quickstarts may use broad roles for demos, whereas production requires custom or tightly scoped roles per least privilege.

### 4.1. Project Isolation

If an HPC team shares a project with production apps, autoscaling or exhausted CPU/GPU quotas can disrupt unrelated workloads. Use a dedicated project for labs. In production, consider per-cluster/workload/environment projects, folder policies, and billing labels to contain blast radius.

## 5. Deploying Slurm with Cluster Toolkit

**Cluster Toolkit** is an open-source Google Cloud tool using YAML blueprints and modules to generate Terraform/Packer deployments. It is not a managed service operating the cluster on your behalf.

The official quickstart covers:

1. Installing a released `gcluster` binary for your OS/architecture.
2. Using the sample blueprint `examples/hpc-slurm.yaml`.
3. Inspecting variables/modules and generating a deployment directory via `gcluster create`.
4. Reviewing the Terraform plan and deploying via `gcluster deploy`.
5. SSHing to the login node and running `srun`/`sbatch` to trigger dynamic compute nodes.
6. Destroying the cluster after finishing lab exercises.

Example **only run after downloading official Cluster Toolkit** and confirming region/quota/budget:

~~~bash
# Run inside the installed Cluster Toolkit directory.
./gcluster --version

# Inspect configurable variables in the blueprint.
./gcluster explain examples/hpc-slurm.yaml

# Generate a Terraform deployment from the sample blueprint.
./gcluster create examples/hpc-slurm.yaml \
  -l ERROR --vars project_id=HPC_LAB_PROJECT_ID

# Review the plan before deciding whether to apply.
./gcluster deploy hpc-slurm
~~~

`gcluster create` generates a folder such as `hpc-slurm/`; `gcluster deploy` invokes Terraform to provision real infrastructure and can incur charges. Never use `deploy` as a syntax check; use `explain` and validate/plan steps instead. Folder names vary by blueprint and version—check actual output before running follow-up commands.

**Operational responsibilities remain yours:** Terraform state, OS image patching, Slurm controller, MUNGE, scheduler configs, backups, accounting, security, and upgrades. Current Google Cloud docs recommend Cluster Toolkit blueprints/modules over using legacy `slurm-gcp` Terraform modules directly unless specifically needed.

### 5.1. Nodesets and Partitions in a Blueprint

Organize queues around **homogeneous machine groups**. Cluster Toolkit provides nodeset and partition modules. Illustrative snippet (**incomplete for standalone deployment**):

~~~yaml
# Excerpt from the modules section of a Cluster Toolkit blueprint.
# Network, shared filesystem, and Slurm controller modules
# must be defined elsewhere in the blueprint.
- id: cpu_nodes
  source: community/modules/compute/schedmd-slurm-gcp-v6-nodeset
  use: [network]
  settings:
    node_count_dynamic_max: 8
    machine_type: n2-standard-4

- id: cpu_partition
  source: community/modules/compute/schedmd-slurm-gcp-v6-partition
  use: [cpu_nodes, homefs]
  settings:
    partition_name: cpu
    is_default: true
    exclusive: true
    suspend_time: 300
    resume_timeout: 300
    suspend_timeout: 120
~~~

Explanation:

- `node_count_dynamic_max: 8` caps dynamic nodes in this **nodeset** at the Cluster Toolkit config level; it does not guarantee Google Cloud quota or capacity for 8 VMs.
- `machine_type` sets CPU/RAM per node in the nodeset.
- Partition `cpu` binds the defined nodeset and filesystem.
- `is_default: true` routes jobs omitting `--partition` here.
- `exclusive: true`: dedicates nodes to a single job per module design; dynamic nodes may be deleted immediately upon job completion instead of waiting `suspend_time`.
- `resume_timeout` and `suspend_timeout` control power-saving node lifecycle timeouts, not maximum job queue wait time.

**Important:** In Cluster Toolkit's Slurm partition module, `exclusive=true` is default and can delete nodes immediately after jobs finish. With `exclusive=false`, compatible jobs can share nodes and idle nodes suspend after the configured idle window. Benchmark both modes to weigh boot latency against node utilization.

### 5.2. Why Not Manually Configure Slurm Across All VMs?

Installing Slurm manually on VMs offers deep control, yet forces you to build and maintain:

- Consistent bootstrapping and controller/compute image updates.
- Syncing `slurm.conf`, MUNGE keys, UIDs/GIDs, and shared mounts.
- Cloud API hooks to create/delete VMs and handle Compute Engine failures.
- Monitoring, accounting databases, backups, and controller failover.
- Resolving state drift between Slurm and actual cloud VMs.

Cluster Toolkit eliminates scaffolding boilerplate without removing the need to understand architecture and operations.

## 6. Submitting Jobs: Three Foundational Workload Patterns

The examples below run **from an authorized login node with the Slurm client** once the cluster is up. The partition name `cpu` assumes the blueprint example above; substitute `debug` or `compute` as reported by `sinfo`.

### 6.1. Discovering Resources

~~~bash
# List available partitions and nodes.
sinfo

# Formatted view for quick comparison.
sinfo -o "%P %a %l %D %t"

# View your own jobs.
squeue --me

# Inspect a specific partition.
scontrol show partition cpu

# Inspect node states in a partition.
sinfo -p cpu -N
~~~

`AVAIL` and `STATE` show partition/node availability from Slurm's perspective. **A dynamic node that does not yet exist in Compute Engine** may appear powered down or in another logical state; verify how your module represents idle nodes instead of assuming "8 listed nodes means 8 running billable VMs."

### 6.2. Simple CPU Job with sbatch

Create the log directory **before submitting**:

~~~bash
mkdir -p "$HOME/slurm-lab/logs"
cd "$HOME/slurm-lab"
~~~

Create `hello.sbatch`:

~~~bash
#!/usr/bin/env bash
#SBATCH --job-name=hello-hpc
#SBATCH --partition=cpu
#SBATCH --nodes=1
#SBATCH --ntasks=1
#SBATCH --cpus-per-task=2
#SBATCH --mem=4G
#SBATCH --time=00:05:00
#SBATCH --output=logs/%x-%j.out
#SBATCH --error=logs/%x-%j.err

set -euo pipefail

echo "Job ID: $SLURM_JOB_ID"
echo "Node list: $SLURM_JOB_NODELIST"
date -u
srun hostname
sleep 10
echo "Job complete"
~~~

Submit and track:

~~~bash
sbatch hello.sbatch
squeue --me
squeue -j JOB_ID
scontrol show job JOB_ID
~~~

Option meanings:

- `--nodes=1`: requests one node.
- `--ntasks=1`: one Slurm task (**does not mean one single CPU**).
- `--cpus-per-task=2`: requests two logical CPUs per cluster topology/config.
- `--mem=4G`: memory request enforced per scheduler policy.
- `--time=00:05:00`: walltime limit; exceeding it triggers job cancellation/kill.
- `--output` and `--error`: log paths; parent directories must already exist and be writable before execution starts.

**Never request 64 CPUs for single-threaded code.** Slurm reserves requested resources; unused cores stay locked and still cost money. For OpenMP apps, set `OMP_NUM_THREADS=$SLURM_CPUS_PER_TASK` after validating compatibility.

### 6.3. Job Arrays for Parameter Sweeps

Suppose a team needs to run 16 independent parameter sets. Use a **job array** instead of writing 16 near-identical scripts:

~~~bash
#!/usr/bin/env bash
#SBATCH --job-name=param-sweep
#SBATCH --partition=cpu
#SBATCH --array=0-15%4
#SBATCH --nodes=1
#SBATCH --ntasks=1
#SBATCH --cpus-per-task=1
#SBATCH --mem=2G
#SBATCH --time=00:10:00
#SBATCH --output=logs/%x-%A_%a.out

set -euo pipefail

echo "Array parent ID: $SLURM_ARRAY_JOB_ID"
echo "Array task ID: $SLURM_ARRAY_TASK_ID"
echo "Node: $(hostname)"

# Replace with the actual simulation binary;
# use the task index to pick the right input or seed.
sleep 5
echo "Case $SLURM_ARRAY_TASK_ID done"
~~~

`--array=0-15%4` creates 16 array tasks capped at **at most four concurrent tasks within this array**. This cap does not govern the whole cluster or other jobs. Slurm also enforces `MaxArraySize`, account, QOS, and submission limits if configured.

Verify:

~~~bash
sbatch sweep.sbatch
squeue --me
sacct -j ARRAY_JOB_ID --format=JobID,State,Elapsed,AllocCPUS,ExitCode
~~~

`sacct` requires job accounting to be configured on the cluster to query historical records. If `sacct` returns empty output, inspect Slurm accounting configuration rather than assuming the job never ran.

### 6.4. Multi-Node MPI Job

MPI apps typically require multiple concurrent tasks with low network latency:

~~~bash
#!/usr/bin/env bash
#SBATCH --job-name=mpi-solver
#SBATCH --partition=cpu
#SBATCH --nodes=2
#SBATCH --ntasks-per-node=4
#SBATCH --time=00:20:00
#SBATCH --output=logs/%x-%j.out

set -euo pipefail
echo "Allocated nodes: $SLURM_JOB_NODELIST"

# Example running a binary compiled against a compatible MPI stack.
srun ./solver
~~~

Prerequisites for a real run:

- `solver` is accessible on compute nodes and compiled against a compatible MPI stack/runtime.
- The partition has at least two compatible nodes with sufficient resources.
- Networking, firewall rules, NICs, and performance tiers support inter-node MPI traffic.
- Slurm's `srun`/MPI launch plugin matches the MPI library. If using `mpirun`, verify cluster integration rather than swapping directly without testing.

**Two nodes do not guarantee double the performance.** Communication and I/O overhead can limit scaling; benchmark strong and weak scaling.

## 7. Monitoring Jobs and Diagnosing Queue Waits

Common Slurm commands:

| Command | Purpose | Example |
|---|---|---|
| `squeue` | Inspect queued/running jobs | `squeue --me` |
| `sinfo` | Inspect partitions and nodes | `sinfo -R` to see down/drained reasons |
| `scontrol show job` | Inspect job details: resources, reason, allocation | `scontrol show job JOB_ID` |
| `scontrol show node` | Inspect node state/features | `scontrol show node NODE_NAME` |
| `sacct` | Job history and CPU/memory accounting | `sacct -j JOB_ID` |
| `sstat` | Live metrics for running jobs/steps if configured | `sstat -j JOB_ID --format=AveCPU,MaxRSS` |
| `sprio` | Priority components when multifactor priority is enabled | `sprio -j JOB_ID` |
| `sshare` | Fair-share metrics when accounting is enabled | `sshare -l` |
| `scancel` | Cancel your own job | `scancel JOB_ID` |

Inspect pending jobs and wait reasons:

~~~bash
squeue -t PD -o "%.12i %.10P %.12u %.2t %.10M %.12l %R"
scontrol show job JOB_ID
sinfo -R
~~~

Common wait reasons:

| Reason / State | Common Meaning | Checks |
|---|---|---|
| `Priority` | Higher-priority jobs are ahead | `sprio`, fair-share, job age |
| `Resources` | Eligible resources not yet free | Node states, VM types, partition, job size |
| `Dependency` | Waiting on upstream job | `Dependency` field in job details |
| `QOSGrpCpuLimit` or account limits | Exceeded QOS/association caps | `sacctmgr` (admin), quota policies |
| `ReqNodeNotAvail` | Requested node unavailable | `sinfo`, reservations, drained/powered-down nodes |
| `Nodes required for job are DOWN/DRAIN` | Nodes unhealthy or drained | `sinfo -R` and `slurmd` logs |
| `CG` stuck too long | Cleanup or node teardown stalled | Epilog scripts, filesystems, controller logs |
| Pending long despite dynamic nodes | API/quota/capacity/bootstrap failure | Slurm resume logs, Compute Engine operations, quotas |

**Distinguish three limit layers:**

1. **Scheduler limits:** blocked by partition time limits, account/QOS caps, fair-share, or node eligibility.
2. **Cloud quotas:** project lacks CPU/GPU/disk quota or hits API rate limits.
3. **Cloud capacity:** quota exists, yet the zone lacks physical VMs/GPUs right now; Spot fluctuates heavily.

Raising QOS cannot materialize GPUs in an out-of-stock zone. Raising quotas does not guarantee Compute Engine has physical hardware ready on demand.

## 8. Organizing Partitions for Multiple HPC Teams

An organization might separate:

| Illustrative Partition | Node Type | Workload | Sample Policy |
|---|---|---|---|
| `debug` | Small CPU, dynamic | 1–5 minute test scripts | Short MaxTime, elevated queue priority |
| `cpu` | Compute-optimized CPU, dynamic | Batch simulations | 8-hour MaxTime, fair-share |
| `gpu` | Appropriate GPU VMs | Training/visualization | GPU quotas, per-user GPU caps |
| `mpi` | MPI-tuned VMs/networking | Multi-node jobs needing topology | Placement/capacity constraints |
| `spot` | Spot VMs | Restartable/checkpointed jobs | Preemption-aware, bounded retries |

These names and policies are illustrative, not pre-created by Slurm or Cluster Toolkit. **One partition can span multiple nodesets** if hardware traits align; split partitions when users need distinct policies or limits.

### 8.1. Partition Policies vs. QOS Policies

- **Partition:** eligible node groups, `MaxTime`, default routing, priority tiers, and access controls per cluster.
- **QOS / account association:** concurrent job/CPU/GPU limits, priorities, preemption, and shared user/group caps.
- **Job flags:** `--time`, `--mem`, `--cpus-per-task`, `--gpus`, or `--constraint`.
- **Google Cloud:** quotas, reservations, machine-family availability, VM lifecycles, and billing.

To share resources fairly between two research teams, creating two partitions alone is rarely enough. One user can flood the queue with thousands of jobs; implement accounting/QOS, user/association limits, fair-share, and active monitoring.

### 8.2. Policy Adjustments by Workload Type

| Workload | Requirements | Governance Focus |
|---|---|---|
| Many small simulations | 1–4 CPUs, low RAM, short walltime | Job arrays with concurrency caps |
| Large-memory simulation | High RAM, few nodes | Explicit mem requests, memory-optimized machine family |
| Tightly coupled MPI | Simultaneous nodes, low latency | Placement, networking, shared FS, gang scheduling |
| GPU experiments | GPU type/count and driver/CUDA | GPU quotas, compatible images/modules, usage caps |
| Checkpointed training | Tolerates preemption | Spot partition, checkpoint/restart |
| Long continuous jobs | Stable resources for days | Static/reserved capacity, never casual Spot |

## 9. Fair-Share, QOS, and Job Priority

Slurm supports multifactor priority and accounting mechanisms such as `PriorityType=priority/multifactor`, fair-share trees, job age, job size, partition/QOS weights, reservations, and limits. Active factors depend on your cluster's `slurm.conf` and database—there is no single universal formula.

Example organizational policy:

- Each group receives a resource share proportional to its HPC budget.
- Small debug jobs get short walltime limits and quick turnaround priority, but cannot lock expensive GPUs for hours.
- Long GPU jobs must specify a valid account and draw from internal GPU-hour quotas.
- Fair-share boosts priority for under-spending groups over subsequent cycles.
- Submission and running-job caps prevent queue flooding.

Users can specify admin-defined QOS levels:

~~~bash
# Valid only when QOS 'normal' and the account are granted to the user.
sbatch --partition=cpu --qos=normal --account=research hello.sbatch

# Inspect priority components if the cluster enables multifactor priority.
sprio -j JOB_ID
sshare -l
~~~

Admins manage accounts, users, associations, and QOS via `sacctmgr`. Never embed production permission or limit changes inside user job scripts; those changes must be reviewed, audited, and executed by authorized administrators.

### 9.1. Backfill Scheduling

Slurm can slot smaller jobs into scheduling gaps while high-priority jobs wait for larger node blocks, provided backfill is configured. Users should supply **realistic walltimes**: requesting 24 hours for a 10-minute job cripples backfill efficiency and blocks resources unnecessarily.

Avoid "setting the maximum walltime just to prevent timeouts." Measure p95 runtimes, add sensible safety margins, checkpoint long runs, and tune limits using observed data.

## 10. Autoscaling: Dynamic Nodes and VM Lifecycles

On Google Cloud, Cluster Toolkit supports dynamic nodesets: Slurm spins up nodes when scheduled and reclaims idle ones per configuration. Google Cloud infrastructure and Slurm state must remain synchronized; desynchronization can leave orphan VMs or `DOWN` nodes.

~~~mermaid
sequenceDiagram
    actor U as User
    participant C as Slurm controller
    participant API as Compute Engine API
    participant VM as Compute node
    U->>C: sbatch job
    C->>C: Check resources, priority, limits
    C->>API: Resume / create VMs if needed
    API-->>C: Operation accepted or error
    API->>VM: Boot, mount storage, start slurmd
    VM-->>C: Node ready
    C->>VM: Allocate job
    VM-->>C: Job completed
    C->>API: Suspend/delete per partition policy
    API-->>C: VM stopped/deleted
~~~

### 10.1. Static vs. Dynamic

| Choice | Benefits | Risks / Costs |
|---|---|---|
| Static nodes | Minimal startup delay, ideal for steady load | Capacity can sit idle while incurring charges |
| Dynamic exclusive | Provisioned per job, reclaimed quickly | Startup latency and per-job setup overhead |
| Dynamic shared | Multiple jobs share nodes, kept warm briefly | More complex sharing, isolation, and fragmentation |
| Reservation-backed | Stronger capacity assurance under commitment | Reservation fees/commitments and management overhead |
| Spot nodes | Savings for checkpoint/restart jobs | Preemption risk, unguaranteed capacity, lost progress |

In Cluster Toolkit's Slurm partition module, default `exclusive=true` can delete dynamic nodes immediately after a job ends, bypassing `suspend_time`. With `exclusive=false`, `suspend_time` governs the idle wait before suspension. **Always verify power-saving behavior against the exact module/version in use**, rather than guessing from variable names.

### 10.2. Quotas and Availability

A dynamic nodeset with `node_count_dynamic_max: 8` is only a cluster config cap; when a job requests 8 VMs, it can still be blocked by:

- Regional CPU or machine-family quotas.
- GPU quotas or supported accelerator counts.
- IP addresses, Persistent Disks, or Filestore network limits.
- Available VM stock in the target zone.
- Missing `compute.instances.create` permissions or service account IAM.
- Placement policies incompatible with topology.
- Startup images missing drivers, network setup, or filesystem mounts.

When jobs stay `PENDING`, check both Slurm wait reasons and Compute Engine activity. Never assume "open queue slots" means "8 GCP VMs are waiting on standby."

## 11. Selecting VM Types, Networking, and Placement for HPC

HPC depends on **CPU architecture, memory bandwidth, network latency, accelerator topology, storage IOPS**, and node scale. Choosing the cheapest VM per vCPU can inflate runtime dramatically due to memory or network bottlenecks.

| Component | What to Verify |
|---|---|
| CPU VM | ISA, core count, NUMA, memory per core, application benchmarks |
| Memory | Peak RSS, memory bandwidth, unintended swapping |
| GPU | Model, GPUs/node, driver/CUDA/ROCm compatibility, quotas |
| TPU | Slurm TPU nodeset/topology and per-generation support |
| Network | Bandwidth, latency, topology, placement, TCP/gVNIC/RDMA if needed |
| Storage | IOPS, throughput, metadata rates, sharing semantics, cost |
| Location | Regions/zones supporting the machine type, reservations, data residency |

Google Cloud offers specialized HPC VMs and networks, including high-bandwidth/Cloud RDMA configurations for eligible workloads and VMs. **Never assume every Compute Engine VM supports RDMA**, nor assume flipping a network flag automatically accelerates MPI. Match machine type, image, drivers, topology, and benchmarks.

### 11.1. MPI and Multi-Node Communication

For tightly coupled simulations, measure:

- Inter-node latency and bandwidth under the target placement.
- `MPI_Allreduce` or collective times across rank counts.
- Strong scaling: fixed total problem size, increasing node count.
- Weak scaling: fixed work per node, scaling total problem size.
- Checkpoint and input I/O so storage bottlenecks aren't misdiagnosed as compute bottlenecks.

Never run `hostname` across three nodes and claim MPI throughput is verified. `hostname` checks basic Slurm allocation and launch—not HPC performance.

## 12. Shared Storage and Input/Output Data

HPC clusters typically share data across login, controller, and compute nodes. Google Cloud offers distinct storage options:

| Service / Pattern | Best For | Caveats |
|---|---|---|
| Filestore (NFS) | Home directories, software stacks, standard shared files | Throughput/IOPS, tiers, capacity, network |
| Google Cloud Managed Lustre | High-performance parallel scratch I/O for HPC | Pricing, capacity, lifecycle; not a backup tier |
| Cloud Storage | Datasets, checkpoints, artifacts, durable outputs | Object semantics; not a native POSIX filesystem |
| Cloud Storage FUSE | Mounting object buckets for compatible use cases | Differs from POSIX in semantics/latency; benchmark your app |
| Local SSD / local disk | High-speed ephemeral node scratch | Data lost upon node deletion/preemption |
| Persistent Disk | VM boot/attached storage per design | Performance/capacity/attachment limits; bills when VM stopped |

### 12.1. Staging Data Before and After Jobs

A common pattern:

~~~mermaid
flowchart LR
    G[("Cloud Storage: input dataset")] -->|Stage-in| L["Scratch/Shared FS"]
    L -->|Run job| C["Compute nodes"]
    C -->|Periodic checkpoints| L
    L -->|Stage-out| O[("Cloud Storage: outputs/artifacts")]
    C --> M["Job stdout/stderr + metrics"]
~~~

Never write final checkpoints **exclusively** to a dynamic node's local disk; if the node is deleted or Spot-preempted, the checkpoint vanishes. For large files, design stage-in/out with checksums, retries, and concurrency throttling.

### 12.2. Filesystem Performance

For example, a 100-task job array opening 10,000 tiny files concurrently can overwhelm metadata ops despite tiny total byte volume. Mitigations include:

- Packing tiny files or using chunked binary formats.
- Avoiding concurrent appends from all jobs into one shared file.
- Sharding outputs by job ID or array task ID.
- Throttling concurrent I/O-heavy tasks.
- Using local scratch for intermediate steps and staging out upon completion.
- Benchmarking throughput and metadata latency at realistic workload scale.

## 13. Checkpointing and Spot/Preemption

Spot VMs can be reclaimed per infrastructure policy; hourly rates are lower than on-demand without continuity SLAs. Running a multi-hour MPI job without checkpoints on Spot can increase total cost and completion time.

A minimal checkpointing strategy:

1. Identify state needed to resume, including iteration counters and RNG seeds.
2. Checkpoint at intervals balancing write overhead against preemption probability.
3. Write checkpoints to shared/durable storage, never solely local disk.
4. Write to temporary files and atomically rename/commit to avoid torn checkpoints.
5. On restart, locate the latest **valid** checkpoint rather than blindly trusting the newest timestamp.
6. Bound retries to prevent endless loops on configuration or OOM errors.
7. Record provenance: image/build, input dataset, code version, job ID, and output checksums.

**Slurm jobs do not magically resume safely after Spot preemption.** Slurm can requeue/restart per config, yet the application itself must handle state, idempotency, and checkpoints. A `COMPLETED` Slurm status only means the process exited 0—not that outputs were safely staged out.

## 14. Permissions, Security, and Multi-Tenancy

HPC clusters are multi-user environments often holding sensitive research data. Distinguish four identity planes:

- **Google Cloud IAM:** who can create VMs, read buckets, manage VPCs, impersonate service accounts, and call APIs.
- **Linux identity:** UID/GID, SSH/OS Login, file permissions on shared filesystems.
- **Slurm identity:** users, accounts, partitions, QOS, and fair-share/associations.
- **Application identity:** permissions used when jobs call Google Cloud APIs.

Permission to run `sbatch` does not grant permission to create Compute Engine VMs directly. The controller uses its own service identity for autoscaling, while jobs run under appropriate Linux users and/or data-scoped service accounts.

### 14.1. Baseline Controls

- Enforce least-privilege IAM across controller SA, login access, compute node SA, and admins.
- Prefer OS Login/IAP and private IPs; restrict public SSH.
- Never store service account JSON keys in home directories, job scripts, or shared filesystems.
- Protect MUNGE secrets and SlurmDBD/database credentials; keep cluster nodes trusted.
- Isolate projects/accounts for sensitive research or strict compliance workloads.
- Pin base VM images and packages; patch, scan vulnerabilities, and test driver updates.
- Enforce user/group ACLs on Filestore/Lustre rather than relying solely on "internal networking."
- Configure retention/auditing for logs and research data; keep secrets/PII out of stdout.
- Restrict who can run `scontrol update`, `sacctmgr`, and modify blueprints.

### 14.2. Data and Job Permissions

When jobs read Cloud Storage, use attached service accounts and metadata credentials via SDK Application Default Credentials where suitable, scoped to required buckets/prefixes. Never hardcode static access tokens in `sbatch` scripts. Remember that **every job sharing one node may share the same VM metadata identity** unless isolated; never co-locate teams with different data sensitivity levels on shared nodes without proper isolation controls.

## 15. Resource Accounting, Quotas, and Cost

In Cloud HPC, evaluate costs across **both jobs and the entire cluster lifecycle**, not just active code execution time.

~~~text
HPC Cost ≈
  Compute nodes (VM/GPU + boot disk + local SSD if used)
  + Controller/login/static nodes
  + Shared filesystem and minimum provisioned capacity
  + Network egress/NAT/inter-zone traffic
  + Cloud Storage, logs, Monitoring
  + Reservations/commitments/Spot per choice
  + Operational effort, backups, and upgrades
~~~

Hypothetical example: four 4-vCPU VMs running for 20 minutes consume:

~~~text
Total VM-runtime = 4 nodes × (20 / 60 hours) = 1.33 VM-hours
Total vCPU-time  = 4 nodes × 4 vCPUs × (20 / 60 hours) = 5.33 vCPU-hours
~~~

**This is not a price quote.** Actual bills depend on machine types, regions, Spot/on-demand/reservations, memory/disks, billing rules, and ancillary resources. Check Compute Engine pricing and the Pricing Calculator at deployment time.

### 15.1. VM Costs vs. Queue Wait Costs

A `PENDING` job accrues zero **compute-node running time** if VMs haven't launched, yet the cluster still pays for controller/login/storage baseline resources. Once the controller provisions VMs, billing starts even before the job script begins running. After completion, delays before suspension/deletion or idle shared nodes continue accruing charges.

A sound attribution formula:

~~~text
Job effective cost ≈ allocated resources × runtime/cost rate
                      + allocated share of cluster overhead
                      + associated storage/network/logging
~~~

Slurm `sacct` records allocated CPUs and elapsed time, but knows nothing about Google Cloud discounts, storage, or egress. For showback/chargeback, join accounting logs with Cloud Billing exports, resource labels, and cluster overhead allocation rules.

### 15.2. Guardrail Layers

| Layer | Controls | What It Cannot Replace |
|---|---|---|
| Slurm job | `MaxTime`, `MaxJobs`, `MaxSubmitJobs`, QOS, fair-share, array caps | Google Cloud CPU/GPU quotas |
| Nodeset | Max dynamic node count, machine type, zone | Budgets or physical capacity |
| GCP project | CPU/GPU quotas, IAM, org policies, budgets | Slurm user/account fairness |
| Billing | Budget alerts, billing exports, cost dashboards | Hard automatic spending caps |
| Application | Checkpoints, timeouts, memory profiling | Cluster scheduling policies |

Google Cloud budget alerts do **not** automatically halt spending. Automatically disabling APIs/projects on a spend threshold can break jobs and corrupt data; if auto-remediation is required, design, test, and approve it carefully.

## 16. Observability: Measuring Queues, VMs, and Scientific Output

A healthy Slurm cluster tracks far more than "all VMs are green":

| Metric Category | What to Monitor |
|---|---|
| Queue | Pending jobs by partition/account, p95 pending age, reason histogram |
| Scheduling | Job start latency, backfill rate, preemptions, QOS rejections |
| Runtime | Success/fail/timeout/OOM counts, actual vs. requested walltime |
| Compute | Active VMs, boot latency, idle nodes, CPU/GPU utilization |
| Filesystem | Throughput, metadata IOPS, fullness, mount errors |
| Network | MPI latency/bandwidth, errors/retransmits, link saturation |
| Spend | VM-hours/GPU-hours, idle node spend, shared storage spend |
| Controller | `slurmctld` health, queue depth, sync errors, disk/database |

Slurm metrics can be gathered via job accounting, logs, exporters, or bundled deployment agents; **not all metrics appear automatically in Cloud Monitoring out of the box**. Configure Ops Agent/monitoring agents, log filters, custom metrics, and alerts appropriate for your toolkit version.

### 16.1. Long Queue While Compute Sits Idle

Often a matching issue rather than missing hardware:

- Job specifies an invalid partition, QOS, or account.
- Job requests RAM, GPUs, or node counts exceeding every nodeset.
- Job has an unmet hard dependency.
- Nodes are `DRAIN`ed or failing filesystem/bootstrap.
- Machine-family quota or zonal capacity is exhausted.
- Job requests 8 simultaneous nodes when only 7 are available.
- Affinity/constraint/feature flags narrow eligible nodes down to zero.

Check `scontrol show job` first, then `sinfo`, controller logs, and Compute Engine operations; never edit production `slurm.conf` blindly "just to test."

## 17. Troubleshooting Playbook

| Symptom | Common Cause | Action |
|---|---|---|
| Job stays `PD (Priority)` | Fair-share or queue priority | Check `sprio`, run queue, account policies |
| Prolonged `PD (Resources)` | Insufficient resources/eligible nodes | Compare requests against nodesets and GCP quotas |
| `PD (Dependency)` | Upstream job incomplete | Inspect dependency and upstream status |
| Node `DOWN` or `DRAIN` | Bootstrap, mount, network, or Slurm daemon failure | `sinfo -R`, `slurmd` logs, VM serial console |
| VM resume fails | IAM, zonal capacity, quota, API, or image error | Compute Engine operations, controller resume logs |
| Job hits `OOM` | `--mem` set too low or memory leak | Check peak RSS, profile, pick higher-RAM nodes |
| Job runs slower than expected | CPU throttling, I/O, or MPI inefficiency | Profile app, filesystem/network metrics |
| Job fails after Spot preemption | Missing checkpoints/requeue handling | Implement restart state and bounded retries |
| `sacct` has no data | Accounting DB/SlurmDBD unconfigured | Check config, permissions, and retention |
| High bills with zero jobs | Controller/login/shared FS/static nodes | Audit Billing by SKU, idle nodes, suspend policy |
| Filesystem full | Heavy checkpoints/logs/outputs | Enforce FS quotas and approved retention cleanup |
| User accesses another team's data | Linux ACLs, SA IAM, or shared node permissions | Audit UID/GID, mount ACLs, and service identities |

**Never manually delete VMs in an active partition** just because they look idle in the Google Cloud Console: Slurm state and VM lifecycles can drift, killing jobs or leaving orphaned resources. Use approved Slurm/Cluster Toolkit pause/drain/reconfigure workflows.

## 18. Lab: Deploying and Observing a Cost-Bounded Queue

Recommended lab inside a **dedicated HPC project** with tight quotas, budget alerts, and a strict timebox.

### Step 1 — Preparation

- Verify project, zone, VM shapes, and actual quotas.
- Confirm operator permissions to deploy IaC and use only the lab cluster.
- Pick a version-pinned sample Slurm blueprint.
- Review controller/login/shared storage sizing and record a cost estimate before deploying.

### Step 2 — Generate and Review

~~~bash
./gcluster explain examples/hpc-slurm.yaml

./gcluster create examples/hpc-slurm.yaml \
  -l ERROR --vars project_id=HPC_LAB_PROJECT_ID

# Deploy only after reviewing the Terraform plan and getting approval.
./gcluster deploy hpc-slurm
~~~

Never ignore warnings about Filestore capacity, network limits, or quotas. Even dynamic-node clusters provision persistent baseline resources.

### Step 3 — Access Login Node and Submit a Test Job

In the official quickstart, connect via SSH-in-browser to the blueprint-created login VM. Once Slurm finishes bootstrapping:

~~~bash
sinfo
squeue --me

# Match partition and node count to your actual blueprint.
srun -N 1 hostname
~~~

If dynamic nodes start in down/power-down state, Slurm spins up a VM. Measure the elapsed time from `srun` until `hostname` returns to benchmark cold-start latency.

### Step 4 — Practice Batch and Array Jobs

- Create the `logs/` directory first.
- Submit `hello.sbatch` and monitor with `squeue`.
- Submit `sweep.sbatch` with `--array=0-15%4`.
- Run `sacct` if accounting is enabled; record completed, timed-out, and failed counts.
- Test a `--time` limit shorter than runtime **strictly on a lab job**, observe `TIMEOUT`, and verify handling.

### Step 5 — Check Quotas, Fairness, and Costs

- Observe simultaneous Compute Engine VMs created.
- Compare running jobs against array and nodeset max caps.
- Record boot times, running/idle durations, and auto-delete behavior.
- Do not raise quotas or instance sizes solely to prove scaling if lab budgets are tight.
- Review Cloud Billing reports once costs settle to compare actual spend against estimates.

### Step 6 — Resource Cleanup

Before tearing down the cluster, verify no jobs are still running and required outputs have been staged out:

~~~bash
squeue --me
# Stop/cancel your lab jobs if needed.
# scancel JOB_ID
~~~

Once compute nodes are reclaimed, run the quickstart teardown command:

~~~bash
# ONLY for dedicated lab clusters; destroys infrastructure.
./gcluster destroy hpc-slurm --auto-approve
~~~

`gcluster destroy` removes infrastructure managed by the deployment. Inspect the destroy plan and resource inventory before running; **never run against shared or production clusters**. Audit VMs, disks, shared filesystems, load balancers/IPs, buckets, and Billing afterward—retained artifacts, data, or backups may require separate cleanup.

## 19. Architecture Exercise: Three Research Teams

Suppose an organization supports:

- **Team A:** 50,000 independent simulation cases, each needing 1 CPU, 2 GB RAM, ~3 minutes.
- **Team B:** 32-node MPI job needing low network latency, 2-hour walltime.
- **Team C:** Long GPU training with checkpointing, tolerant of interruption.

Design at least three partitions/nodesets—such as CPU array, MPI, and Spot GPU—and specify:

1. Job submission syntax for each workload, including resources and walltime.
2. How to cap Team A's concurrency so it neither overwhelms the scheduler nor the filesystem.
3. Fairness/QOS rules across the three teams.
4. Why Team B needs topology/capacity planning, and when reservations help.
5. Checkpoint cadence and stage-out path for Team C.
6. GCP quotas and resource limits to verify before allowing max nodeset scale.
7. Always-on costs of controller/login/filesystems and how to allocate them across teams.
8. Metrics/log sources to catch long pending waits, idle nodes, and job failures.

**Hints:** Increase node counts only after measuring CPU utilization and time-to-start. For Team A, `--array=0-49999%64` limits concurrency of **one array** to 64 tasks if `MaxArraySize`/cluster limits allow; submitting 50,000 tasks in one shot isn't always wise—smaller batches and throttled input I/O may work better. For Team B, avoid Spot if losing one node forces the entire MPI job to restart without effective checkpoints.

## 20. Self-Check Questions

1. What problem does Slurm solve that Cloud Tasks or Pub/Sub cannot directly replace?
2. Distinguish the controller, login node, and compute nodes.
3. How does a nodeset differ from a partition in Cluster Toolkit?
4. Why doesn't `node_count_dynamic_max: 8` guarantee 8 VMs can run?
5. How do `sbatch` and `srun` differ in usage?
6. Does `--array=0-15%4` cap the entire cluster at 4 concurrent tasks?
7. When a job stays `PENDING` too long, which three limit layers must you distinguish?
8. Why can `exclusive=true` delete dynamic nodes immediately after a job finishes?
9. Why shouldn't heavy simulations run on login nodes?
10. What is required for `sacct` to return useful job history?
11. Can fair-share and QOS solve a zonal GPU capacity stockout?
12. Is a checkpoint stored solely on a Spot VM's local disk safe?
13. Does Cloud Storage FUSE behave identically to a POSIX filesystem for all MPI workloads?
14. Why doesn't Slurm autoscaling make the controller and shared FS free?
15. Which factors should you measure when MPI scales poorly despite adding nodes?

**Suggested Answers**

1. Slurm schedules HPC jobs needing simultaneous CPUs/GPUs/memory/nodes with gang allocation, priority, accounting, and batch lifecycles; Pub/Sub and Cloud Tasks deliver or schedule discrete messages/tasks.
2. Controller schedules work, login nodes let users prepare/submit jobs, and compute nodes execute workloads.
3. A nodeset defines a group of similarly configured compute nodes; a partition groups nodesets and enforces scheduling policies.
4. It is only a config ceiling; Google Cloud still enforces quotas, physical capacity, IAM, topology, and networking.
5. `sbatch` submits batch scripts to the queue; `srun` launches job steps inside an allocation or requests interactive allocations depending on context.
6. No. It only caps concurrency for that specific array; account/QOS/cluster limits operate separately.
7. Slurm scheduling/limits, Google Cloud quotas, and Google Cloud physical capacity/availability.
8. Per the partition module design, exclusive dynamic nodes can be deleted right after job completion instead of waiting for `suspend_time`.
9. They bypass scheduler allocation/accounting and contend for resources needed by interactive login users.
10. Slurm accounting service/database must be configured and recording data, with proper query permissions and retention.
11. No. Scheduler policies cannot conjure physical GPU hardware beyond quotas and capacity.
12. No; the node can be reclaimed, so checkpoints must be staged out to shared/durable storage.
13. No. Object semantics, consistency, metadata latency, and edge behaviors differ from POSIX; benchmark the application.
14. Because the controller, login node, static capacity, shared filesystem, disks, and networking remain provisioned and billable.
15. MPI collective latency, placement/network bandwidth, data partitioning, synchronization overhead, and filesystem I/O.

## Conclusion

Slurm on Google Cloud provides a familiar HPC queuing model while Compute Engine dynamically provisions capacity on demand. Sound design **ties job profiles to nodesets/partitions, Slurm fairness/QOS to cloud quotas, and autoscaling to data protection and cost controls**. A cluster passing `srun hostname` only proves basic plumbing; reliable operations demand application benchmarks, accounting, right-sized shared filesystems, checkpointing, security hardening, queue observability, and disciplined teardown workflows.

## References

- [Google Cloud — Cluster Toolkit overview](https://docs.cloud.google.com/cluster-toolkit/docs/overview)
- [Google Cloud — Deploy an HPC cluster with Slurm](https://docs.cloud.google.com/cluster-toolkit/docs/quickstarts/slurm-cluster)
- [Google Cloud — Set up Cluster Toolkit](https://docs.cloud.google.com/cluster-toolkit/docs/setup/configure-environment)
- [Google Cloud — Create a nodeset for a Slurm partition](https://docs.cloud.google.com/cluster-toolkit/docs/modules/slurm-nodeset)
- [Google Cloud — Create a Slurm partition](https://docs.cloud.google.com/cluster-toolkit/docs/modules/slurm-partition)
- [Google Cloud — Slurm TPU deployments overview](https://docs.cloud.google.com/cluster-toolkit/docs/deploy/slurm/slurm-tpu-overview)
- [Google Cloud — Demand scaling overview](https://docs.cloud.google.com/docs/compute-area/scale-overview)
- [Google Cloud — Overview of HPC clusters](https://docs.cloud.google.com/compute/docs/hpc/overview-hpc-clusters)
- [Google Cloud — Choose compute options](https://docs.cloud.google.com/docs/compute-area/choose-compute-options)
- [Google Cloud — Cluster Toolkit release notes](https://docs.cloud.google.com/cluster-toolkit/docs/release-notes)
- [Slurm — sbatch command](https://slurm.schedmd.com/sbatch.html)
- [Slurm — Job arrays](https://slurm.schedmd.com/job_array.html)
- [Slurm — Quality of Service (QOS)](https://slurm.schedmd.com/qos.html)
- [Slurm — Slurm commands overview](https://slurm.schedmd.com/quickstart.html)
- [Google Cloud — Compute Engine quotas](https://docs.cloud.google.com/compute/quotas)
- [Google Cloud — Cloud Billing budgets](https://docs.cloud.google.com/billing/docs/how-to/budgets)
- [Google Cloud — Pricing Calculator](https://cloud.google.com/products/calculator)

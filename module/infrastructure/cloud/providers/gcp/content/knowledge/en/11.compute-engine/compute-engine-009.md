# Spot VMs and Handling Workload Interruptions on Compute Engine

An e-commerce company processes product images, generates sales reports, and runs periodic analytics. These tasks are CPU-intensive but do not always need immediate completion. The infrastructure team wants to lower costs by using Google Compute Engine **Spot VMs** instead of standard VMs for part of the system. After a few hours, a VM processing a batch of data gets reclaimed. If the job only stored results in memory or a temporary disk, progress can be lost and the work must restart from scratch.

The essence of Spot VMs is **trading interruption tolerance for lower compute pricing**, not a permanently cheap VM carrying the same uptime commitment as a standard VM. To use them effectively, applications must handle interruption signals, checkpoint progress, retry safely, prevent duplicate processing from corrupting data, and maintain capacity fallback when Spot capacity is unavailable.

This lesson belongs to the **Compute Engine** chapter of the **CLOUD_PROVIDERS_GCP** module. It connects resource selection with project organization, IAM, VPC, GKE, Cloud Run, storage, databases, release automation, and reliable operations within budget. The focus is on **Spot VMs and interruption-tolerant architectures**, not merely VM creation syntax.

## 1. Learning Objectives

After this lesson, you will be able to:

1. Distinguish Spot VMs, standard VMs, and legacy preemptible VMs; know when to choose or avoid Spot.
2. Explain **preemption** events, brief shutdown notices, and `STOP`/`DELETE` termination actions.
3. Design **idempotent** jobs with checkpoints and durable external state outside the VM.
4. Separate the **work queue**, **preemptible workers**, and **durable result store**.
5. Use `gcloud` to create, inspect, and investigate Spot VMs; understand the role of Managed Instance Groups (MIGs).
6. Build capacity fallback strategies, monitor completion latency, and control end-to-end cost.

## 2. What Is a Spot VM and How Does It Differ from a Standard VM?

### 2.1. Compute Engine Provisioning Models

Compute Engine supports different VM provisioning models. When choosing **Spot**, the workload accepts that Google Cloud may **preempt** (reclaim) the VM whenever resources are needed elsewhere, and the VM is not guaranteed to stay running for a desired duration.

| Aspect | Standard VM | Spot VM |
| --- | --- | --- |
| Purpose | Workloads needing standard provisioning and retention guarantees. | Workloads tolerant of VM preemption or execution delays. |
| Pricing | Follows standard provisioning rates and applicable discount options. | Lower Spot pricing compared to standard VMs when eligible, subject to pricing tables and service terms. |
| Interruption for capacity reclamation | No Spot-based preemption mechanism. | Can be preempted at any time, even shortly after creation. |
| Point-in-time availability | Still subject to quotas and capacity. | Depends more heavily on zonal Spot capacity for the machine type; creation or restart may fail. |
| Suitable workloads | Critical APIs, primary databases, interruption-sensitive services. | Batch jobs, partitionable data processing, CI builds/tests, retryable workers, checkpointed ML training. |
| Failure mindset | HA/backup designs still required. | Must treat **preemption as normal operation**, not a rare edge case. |

A Spot VM is still a **Compute Engine VM**: it has a machine type, image, boot disk, network interfaces, service account, firewalls, and metrics as configured. The primary difference lies in **provisioning policy and reclaimability**. Spot does not automatically add retry, HA, or checkpointing capabilities to an application.

### 2.2. Spot vs. Legacy Preemptible VMs

Google Cloud also had an earlier **preemptible VM** model. Both can be reclaimed, yet **Spot VMs do not carry the 24-hour maximum runtime cap of legacy preemptible VMs**. That does not turn Spot into a guaranteed long-lived machine: a VM may run for days or be preempted very quickly.

When reading older docs or scripts, do not confuse `--preemptible` with `--provisioning-model=SPOT`. For new systems, choose the model aligned with current Google Cloud policy; never predict when a VM will be preempted based on how long it has been running.

### 2.3. Suitable vs. Unsuitable Workloads

**Strong candidates:**

- Processing thousands of images divisible into independent tasks.
- Partitioned data analytics with checkpoints or safe retries.
- CI builds and tests with artifacts stored outside the worker.
- Background workers pulling jobs from Pub/Sub, Cloud Tasks, or managed queues.
- Data processing/ML training steps able to persist state and resume after interruption.

**Candidates needing caution or generally unsuitable:**

- A single VM serving a high-availability production API.
- A primary write database storing its sole copy on a Spot VM's local disk.
- Interactive real-time work requiring predictable latency without fallback.
- Monolithic jobs that cannot be split and lose hours of work on every interruption.
- Systems lacking duplicate-write protection, recovery, or progress tracking.

Selecting Spot should be based on the **end-to-end business workflow's tolerance for interruption**, not just CPU utilization and headline discount rates.

## 3. Spot VM Lifecycle and Preemption Events

### 3.1. Differences Between STOP and DELETE

A Spot VM can configure an **instance termination action** defining what happens upon preemption:

| Termination Action | On Preemption | Key Consequences |
| --- | --- | --- |
| **`STOP`** | VM stops running, typically entering `TERMINATED`. | VM resource and disks remain per config; regaining capacity requires restarting/orchestrating and may still hit Spot capacity shortages. |
| **`DELETE`** | VM is deleted upon preemption per supported behavior. | VM is gone; boot/attached disks may be deleted if `autoDelete` is set. Requires orchestration to spawn replacement instances to continue work. |

Note: `TERMINATED` in Compute Engine means **the VM is stopped**, not necessarily proof of preemption. An operator or automation could have stopped it manually. When investigating, check **system events**, scheduling config, operations, and available logs rather than inferring cause from status alone.

Under both actions, **memory, running processes, and open connections are not preserved**. Unflushed data can be lost. Retaining a disk on `STOP` does not mean a running process resumes from the exact instruction where it halted.

### 3.2. Key Scheduling Constraints

Spot VMs use the `SPOT` provisioning model, and related scheduling options must be compatible. Common Google Cloud examples use:

~~~yaml
scheduling:
  provisioningModel: SPOT
  instanceTerminationAction: STOP
  automaticRestart: false
  onHostMaintenance: TERMINATE
~~~

This illustrates **related properties**, not a raw API payload file. Spot VMs do not automatically restart like standard VMs when reclaimed. An external orchestrator (MIG, scheduler, job controller, or automation) is needed to recreate or restart workers.

### 3.3. Shutdown Notice Before Preemption

When preemption occurs, Compute Engine sends a shutdown signal to the guest OS and attempts to provide **up to roughly 30 seconds** for shutdown tasks where supported. This is **best effort**, not a guarantee that the app always gets a full 30 seconds or completes shutdown scripts.

~~~mermaid
flowchart TD
    RUN["Spot VM processing job"] --> EVENT{"Compute Engine preempts VM?"}
    EVENT -- "Not yet" --> RUN
    EVENT -- "Yes" --> NOTICE["Shutdown notice when possible"]
    NOTICE --> SAVE["Worker tries to stop taking jobs, flush checkpoint"]
    SAVE --> ACTION{"Termination action"}
    ACTION -- "STOP" --> STOP["VM stops; orchestrate capacity back"]
    ACTION -- "DELETE" --> DEL["VM deleted; orchestrator may create replacement"]
    STOP --> RESUME["New/restarted worker picks up remaining work"]
    DEL --> RESUME
    RESUME --> RUN
~~~

Because the notice can be very brief or insufficient for a full flush, **periodic checkpointing during normal execution** is the primary safeguard. Shutdown hooks only trim the amount of rework.

### 3.4. Which Storage Survives Interruption?

| Where State Lives | After STOP / Preemption | Recommendation |
| --- | --- | --- |
| **RAM / process memory** | Execution state lost. | Never use as the sole source of progress. |
| **Local SSD or scratch dirs** | Data can be lost on stop/preemption per storage behavior. | Use only for cache/scratch; persist valuable data durably. |
| **Eligible Persistent Disk / Hyperdisk** | Can persist across VM STOP per disk settings. | Verify lifecycle/attachment; do not tie distributed job recovery to a single VM. |
| **Disk with auto-delete on VM deletion** | May be deleted alongside the instance. | Never store sole results on an auto-deleted boot disk. |
| **Cloud Storage, databases, queues** | Lifecycle decoupled from the VM per service config. | Ideal for inputs, outputs, checkpoints, and job state. |

**Simply using a Persistent Disk is not enough:** a VM may use `DELETE`, disks may auto-delete, or another worker may need to read state independently. Explicitly define **durable state storage, access permissions, checkpoint versioning, and recovery flows**.

## 4. Architecting a Preemptible Worker

### 4.1. Separating Three Components

A straightforward preemption-tolerant pattern:

~~~mermaid
flowchart LR
    P["Job producer app"] --> Q["Pub/Sub / work queue"]
    Q --> W1["Spot VM worker A"]
    Q --> W2["Spot VM worker B"]
    W1 --> D["Cloud Storage / Cloud SQL: checkpoints and results"]
    W2 --> D
    W1 -. "Preempted" .-> X["Worker disappears"]
    Q -. "Unacknowledged job redelivered" .-> W2
    M["Monitoring / alerting"] -. "Track backlog and errors" .-> Q
    M -.-> W1
    M -.-> W2
~~~

1. **Queue** tracks pending work, dispatches tasks, and redelivers unacknowledged work.
2. **Spot VM worker** pulls jobs, computes, and can be replaced at any moment.
3. **Durable store** holds inputs, checkpoints, and committed outputs decoupled from VM lifetimes.

For important workloads, define how the queue manages **acknowledgments, lease/visibility timeouts, retries, and dead-letter queues**. Choose **Pub/Sub** vs. **Cloud Tasks** based on pattern: Pub/Sub suits event/message streaming, while Cloud Tasks suits HTTP task dispatch with rate limiting and retries. A managed scheduler like **Cloud Batch** can also run batch jobs on VMs so you do not have to build a custom worker scheduler from scratch.

### 4.2. Decoupling Workers from State

Example job payload:

~~~json
{
  "job_id": "image-batch-2026-001",
  "object_uri": "gs://retail-inputs/images/item-8842.jpg",
  "output_uri": "gs://retail-results/images/item-8842.webp",
  "attempt": 1
}
~~~

The worker receives metadata and reads the input file from Cloud Storage. If the VM is reclaimed, the queue or scheduler dispatches the same `job_id` to another worker. Input metadata is self-contained and does not depend on temporary local paths on the previous VM.

The `attempt` field in JSON is only an application example, **not a mandatory built-in Pub/Sub field**. If attempt tracking is needed, the app or scheduler must manage it explicitly.

### 4.3. Idempotency Is Essential for Survival

A job is **idempotent** when executing it multiple times produces the same business outcome as executing it once. On Spot VMs, a job can execute twice if:

- The previous worker committed outputs but got preempted before sending the ack.
- The worker took longer than the lease duration, prompting the scheduler to redeliver.
- An operator manually retried after a network timeout without knowing whether the commit succeeded.

**Unsafe pattern:**

~~~text
Receive message → charge customer → write image → ack

If preempted after "charge customer" but before ack:
  message redelivered → customer may be charged twice.
~~~

**Safer pattern:**

~~~text
Receive message (stable job_id)
  → check if job_id is already committed
  → process input
  → write output under a stable key using conditional writes/transactions as needed
  → mark job_id COMPLETED in durable store
  → ack message

If same job_id arrives again:
  → detect COMPLETED status
  → skip duplicate side effects
  → ack safely
~~~

When spanning **multiple target systems** (e.g., writing Cloud SQL and calling a payment API), checking `COMPLETED` beforehand can still hit race conditions. Implement **unique constraints, transactions, idempotency keys**, or outbox/saga patterns matching business semantics. Never assume Pub/Sub alone gives end-to-end "exactly-once" semantics across external systems.

## 5. Checkpointing and Progress Recovery

### 5.1. What Is a Checkpoint?

A **checkpoint** is saved state sufficient to resume work from a consistent point rather than restarting from zero. For large file processing, a checkpoint might list completed partitions. For model training, it might capture model weights, optimizer state, and step counters. For ETL, it might record an offset, watermark, or last committed key.

~~~text
Input 100 partitions

0 ───── 20 ───── 40 ───── 60 ───── 80 ───── 100
                ^
           committed checkpoint: 40

VM preempted while processing partition 47:
  another worker resumes from checkpoint 40,
  verifying committed outputs before reprocessing.
~~~

Losing at most a small slice of work since the last checkpoint cuts rework cost, though checkpointing too frequently adds I/O and latency overhead.

### 5.2. Choosing a Checkpoint Interval

A trade-off:

| Checkpoints Too Infrequent | Checkpoints Too Frequent |
| --- | --- |
| Low state-saving overhead. | More time spent writing checkpoints. |
| Preemption loses large amounts of work. | Minimizes lost work per interruption. |
| Slow recovery for long-running jobs. | Increases storage, API call, or database write costs. |

For instance, if a job normally runs 60 minutes and saving a checkpoint takes 2 seconds, you might start testing checkpoints every 2–5 minutes and measure overhead vs. rework. These numbers **merely illustrate an experimental tuning approach**, not a universal optimum.

More important than frequency is **consistency**. If you mark "partition 40 done" before partition 40's data is durably flushed, a subsequent worker could skip missing data.

### 5.3. Saving Checkpoints Safely

Recommended structure:

1. Write intermediate outputs to an isolated location/version, such as a staging object or transactional record.
2. Only after the output persists cleanly, **commit the checkpoint** as completed.
3. Use object generation preconditions, unique keys, or transactions when multiple workers may race.
4. Verify checkpoint schema/version matches the running worker code version.
5. Retain input metadata, code version, output checksums, and timestamps for auditing.

Example metadata structure:

~~~json
{
  "job_id": "daily-sales-2026-11-19",
  "checkpoint_version": 3,
  "completed_partitions": ["p00", "p01", "p02"],
  "input_manifest_uri": "gs://retail-inputs/manifests/2026-11-19.json",
  "output_prefix": "gs://retail-results/daily/2026-11-19/",
  "worker_release": "sales-etl-1.8.0",
  "state": "RUNNING"
}
~~~

This is a **custom application schema**, not a Google Cloud API response. With concurrent workers, a JSON file in Cloud Storage is only safe if concurrency control (e.g., generation preconditions) is implemented; otherwise two workers can overwrite each other's checkpoints.

### 5.4. Protecting Commits with Cloud SQL Example

Suppose each job stores its final result in PostgreSQL on Cloud SQL:

~~~sql
CREATE TABLE batch_results (
    job_id TEXT PRIMARY KEY,
    output_uri TEXT NOT NULL,
    committed_at TIMESTAMPTZ NOT NULL DEFAULT now()
);

-- Idempotent commit example: skip inserting if job_id already exists.
INSERT INTO batch_results (job_id, output_uri)
VALUES ('image-batch-2026-001', 'gs://retail-results/images/item-8842.webp')
ON CONFLICT (job_id) DO NOTHING;
~~~

A primary key prevents duplicate rows for the same job, though it **does not automatically validate output object contents**. If the same `job_id` runs with different algorithms or inputs, define manifest checks, checksums, and conflict rules. If writing an object first and committing SQL second, handle cases where SQL fails and a staging object lingers via cleanup/garbage collection.

## 6. Shutdown Scripts: Helpful, Not Sufficient

### 6.1. Realistic Objectives

Upon receiving a shutdown notice, a worker should prioritize:

1. Stopping **acceptance of new jobs**.
2. Marking a draining/stopping state if time allows and the coordinator supports it.
3. Flushing a nearly finished checkpoint or small critical state.
4. Closing connections and logging concisely without launching long tasks.

Never defer a multi-gigabyte upload until VM shutdown begins. Shutdown may occur with insufficient time, terminating the script mid-transfer.

### 6.2. Illustrative Shutdown Script Example

Below is a Bash snippet usable as **`shutdown-script` metadata**, requiring customization for real paths, services, and state persistence:

~~~bash
#!/usr/bin/env bash
set -u

# Illustrative only: the application must already checkpoint periodically.
logger -t spot-worker "Shutdown requested: stop taking new jobs"

# If the worker handles signals, ask the service to stop accepting work.
# Do not assume systemctl or this unit name exists on every image.
systemctl stop retail-batch-worker.service || true

logger -t spot-worker "Shutdown hook finished (best effort)"
~~~

On Linux VMs with a compatible guest environment, Compute Engine supports startup/shutdown scripts via metadata. **The script above does not guarantee a checkpoint is saved**; it simply illustrates asking the worker to stop cleanly. Enforce tight timeouts on shutdown hooks, and ensure the worker saves progress periodically or handles stop signals in a testable way.

### 6.3. Why Never Use Shutdown Hooks as the Source of Truth?

Things that can go wrong:

- The worker is CPU- or network-saturated and fails to respond in time.
- The VM fails or is reclaimed too quickly for the hook to finish.
- Connectivity to Cloud Storage/Cloud SQL drops right during flush.
- The script logs "done" even though output commits failed.

The source of truth must be **durable checkpoints and consistent transactions**, never "the shutdown script ran" or a final VM log line.

## 7. Creating and Inspecting Spot VMs with gcloud

The commands below use illustrative values. **Commands with `create`, `start`, `stop`, or `delete` mutate live resources and may incur charges**; run them only in authorized projects/zones. Examples use Bash; adjust variable syntax and line continuations for PowerShell.

### 7.1. Checking Context Before Creation

~~~bash
# READ-ONLY: inspect project and account.
gcloud config get-value project
gcloud auth list

# READ-ONLY: list existing instances.
gcloud compute instances list \
  --project=retail-lab
~~~

If a custom VPC exists, specify the designed network/subnet and service account. Avoid relying on the default VPC or default Compute Engine service account when workloads access production data.

### 7.2. Creating a Single Spot VM

~~~bash
# WRITE: creates a test VM with illustrative parameters.
gcloud compute instances create spot-worker-01 \
  --project=retail-lab \
  --zone=asia-southeast1-a \
  --machine-type=e2-standard-2 \
  --provisioning-model=SPOT \
  --instance-termination-action=STOP \
  --maintenance-policy=TERMINATE \
  --no-restart-on-failure \
  --image-family=debian-12 \
  --image-project=debian-cloud \
  --boot-disk-size=20GB
~~~

Flags may vary by CLI version, machine type, and zonal support. If organizational policy forbids public IPs, add private networking flags and check **Private Google Access**, Cloud NAT, or egress paths needed for package updates and Google APIs. Never attach broad external IPs merely for test convenience.

Key flags:

| Flag | Meaning |
| --- | --- |
| `--provisioning-model=SPOT` | Requests Spot provisioning for the VM. |
| `--instance-termination-action=STOP` | Keeps the VM stopped upon preemption per supported behavior. |
| `--maintenance-policy=TERMINATE` | Sets guest behavior during host maintenance events, matching Spot rules. |
| `--no-restart-on-failure` | Disables standard automatic restart behavior. |
| `--machine-type` and `--zone` | Determine hardware resources and placement; affect pricing and capacity. |

Command success does not guarantee the Spot VM will stay alive long enough to finish its job.

### 7.3. Inspecting the VM After Creation

~~~bash
# READ-ONLY: inspect current status and scheduling settings.
gcloud compute instances describe spot-worker-01 \
  --project=retail-lab \
  --zone=asia-southeast1-a \
  --format="yaml(name,status,zone,machineType,scheduling,disks)"

# READ-ONLY: list VMs using the Spot provisioning model.
gcloud compute instances list \
  --project=retail-lab \
  --filter="scheduling.provisioningModel=SPOT" \
  --format="table(name,zone.basename(),status,scheduling.provisioningModel)"
~~~

These commands read current state only. To determine when an instance was preempted, also inspect **Cloud Logging system event/audit logs** and operations if retained. A `TERMINATED` status does not prove whether preemption, manual stop, or another event occurred.

### 7.4. Configuring DELETE with Active Orchestration

For pure compute workers whose outputs live outside the VM, **`DELETE`** may fit better than `STOP`:

~~~bash
# WRITE: a new Spot VM that can be deleted upon preemption.
gcloud compute instances create spot-worker-ephemeral \
  --project=retail-lab \
  --zone=asia-southeast1-a \
  --machine-type=e2-standard-2 \
  --provisioning-model=SPOT \
  --instance-termination-action=DELETE \
  --maintenance-policy=TERMINATE \
  --no-restart-on-failure \
  --image-family=debian-12 \
  --image-project=debian-cloud
~~~

**Verify `autoDelete` on boot and attached disks.** Critical data must never depend on the VM or disks surviving preemption. If replacement VMs must appear automatically after deletion, pair with an appropriate **scheduler/MIG/automation**; `DELETE` alone does not spawn replacements.

## 8. Managed Instance Groups with Spot Workers

### 8.1. Why Are MIGs Useful?

A **Managed Instance Group (MIG)** manages a fleet of VMs from an **instance template**. The group can recreate instances, maintain target counts, autoscale, and manage fleets per MIG type. With Spot VMs:

- A VM may be preempted and stop serving.
- The MIG attempts to **recreate/maintain the target VM count** per configuration.
- Recreation is **not guaranteed to succeed immediately**, as Spot capacity for that zone or machine type may be exhausted.
- A replacement worker must pull pending work from the queue/checkpoints; never assume the MIG restores old in-memory processes.

**A MIG provides best-effort capacity orchestration—it does not turn Spot into standard guaranteed-capacity VMs.**

### 8.2. Creating a Spot Instance Template

The example below configures Spot workers with termination action `DELETE` so the group can replace VMs as needed. Commands create real resources:

~~~bash
# WRITE: template for Spot workers.
gcloud compute instance-templates create retail-spot-worker-template \
  --project=retail-lab \
  --machine-type=e2-standard-2 \
  --provisioning-model=SPOT \
  --instance-termination-action=DELETE \
  --maintenance-policy=TERMINATE \
  --no-restart-on-failure \
  --image-family=debian-12 \
  --image-project=debian-cloud

# WRITE: zonal MIG targeting two workers.
gcloud compute instance-groups managed create retail-spot-workers \
  --project=retail-lab \
  --zone=asia-southeast1-a \
  --template=retail-spot-worker-template \
  --size=2
~~~

A production setup must add **startup processes, least-privilege service accounts, private networking, health policies, logs/metrics, and safe job handling**. Whether workers use `systemd`, startup scripts, or containers, keep startup versions consistent and never embed credentials inside instance templates.

### 8.3. Observing the MIG

~~~bash
# READ-ONLY: MIG status and configuration.
gcloud compute instance-groups managed describe retail-spot-workers \
  --project=retail-lab \
  --zone=asia-southeast1-a

# READ-ONLY: list instances managed by the group.
gcloud compute instance-groups managed list-instances retail-spot-workers \
  --project=retail-lab \
  --zone=asia-southeast1-a
~~~

If the MIG reports fewer active instances than its target size, inspect operations/errors, quotas, and capacity. **Never assume raising target size from 2 to 10 instantaneously yields 10 running Spot VMs.**

### 8.4. Zonal or Regional MIG?

| Choice | Advantages | Trade-offs |
| --- | --- | --- |
| **Zonal MIG** | Simpler configuration, suitable for test workloads or retryable jobs. | Tied to one zone's capacity; zonal events can hit most workers at once. |
| **Regional MIG** | Can distribute VMs across multiple zones per group policy. | More complex setup/capacity; still does not guarantee Spot availability in every zone. |
| **Spot group + on-demand baseline** | Reserves stable baseline capacity while using Spot for burst capacity. | Requires coordinating load distribution, quotas, and explicit cost/SLO targets. |

Choose regional MIG distribution policies based on features supported at deployment time. For deadline-driven systems, **baseline standard VM capacity** or a controlled fallback mechanism is far more reliable than relying 100% on Spot.

## 9. Spot VMs in GKE and Alternatives

### 9.1. GKE Spot Node Pools

GKE can use **Spot VMs as worker nodes** through appropriately configured node pools. Kubernetes workloads on those nodes can still be interrupted when nodes are preempted. Therefore:

1. Schedule only interruption-tolerant Pods onto Spot nodes.
2. Use **node labels, taints/tolerations, affinity**, or supported scheduling controls for placement.
3. Break jobs into retryable units; use **Kubernetes Jobs** or queue-driven workers.
4. Ensure apps handle `SIGTERM`, termination grace periods, and save checkpoints outside the Pod/node.
5. Monitor available nodes/Pods, Pending Pods, and rescheduling capacity.

Having a **PersistentVolume** does not automatically protect data written to `emptyDir`, container filesystems, or memory. Also check StorageClass behavior, access permissions, and volume reattachment rules across zones.

### 9.2. Do Not Confuse Spot VMs with Cloud Run

Cloud Run is a serverless platform where users **do not pick Compute Engine Spot provisioning for underlying VMs** the way they do for Compute Engine Spot VMs. For an HTTP API scaling with request volume, Cloud Run may offer far simpler operations, yet it should not be thought of simply as "unmanaged-ops Spot VMs."

For batch workloads, evaluate **Cloud Batch**, **GKE Jobs**, Compute Engine MIGs, or Pub/Sub worker architectures. The choice depends on interruption tolerance, packaging, runtime duration, GPU needs, portability, and operational maturity.

### 9.3. Tool Selection Table

| Need | Option to Evaluate | What to Verify |
| --- | --- | --- |
| Running a repeatable test script. | A single Compute Engine Spot VM. | Output persistence and restart workflow. |
| Thousands of independent, checkpointed jobs. | Cloud Batch or queue + Spot workers/MIG. | Retries, concurrency, quotas, capacity, checkpoints. |
| Containerized jobs inside a Kubernetes cluster. | GKE Jobs on a Spot node pool where fit. | Placement, Pod lifecycle, volumes, rescheduling. |
| Stateless HTTP service wanting minimal ops. | Cloud Run or standard VMs/MIG per SLO. | Never assume Cloud Run provisions Compute Engine Spot VMs on demand. |
| Primary transactional database. | Managed database like Cloud SQL or proper HA architecture. | RPO/RTO, durability, backups, restores, SLOs. |

## 10. Economics: Cheap Hourly Price Does Not Guarantee Lower Total Cost

### 10.1. Simple Analytical Model

Suppose a job needs 100 compute units if uninterrupted:

~~~text
Actual total cost
  ≈ Spot VM runtime cost
   + Cost of re-running lost work
   + Checkpoint / durable storage / queue costs
   + Network, logging, and orchestration costs
   + Standby standard capacity cost (if used)
~~~

This is an **analytical model**, not an official Billing formula. When comparing Spot against standard VMs, factor in:

- Current rates by machine type, zone, disk configuration, and timing.
- Job completion rate, preemption frequency, rework duration, and checkpoint overhead.
- Cloud Storage/Cloud SQL/Pub/Sub, logging, data transfer, and orchestration fees.
- Average worker count, capacity headroom, schedule, and business deadlines.

A task taking 30 minutes that repeatedly gets preempted at minute 29 and restarts from zero can end up with a higher **cost per completed result**, regardless of Spot's low hourly rate.

### 10.2. Conditional Comparison Example

Suppose:

| Metric | Option A: No Checkpoints | Option B: Periodic Checkpoints |
| --- | --- | --- |
| Ideal processing time | 60 minutes | 60 minutes |
| When preempted at minute 45 | Must restart from scratch. | Can resume from minute-40 checkpoint. |
| Lost work | Approx. 45 minutes. | Approx. 5 minutes, excluding overhead. |
| State storage cost | Lower. | Additional I/O and storage. |
| Completion reliability | Depends on one long unbroken run. | Higher once a replacement worker starts. |

Numbers illustrate one scenario only, not Google Cloud preemption statistics. Rework savings must be weighed against measured checkpointing overhead.

### 10.3. Deadlines and Spot/On-Demand Mix

A practical architecture can partition queues:

~~~text
Tight-deadline jobs / tasks needing steady capacity
    → standard workers or appropriate managed services

Flexible, partitionable, well-checkpointed jobs
    → Spot workers

Queue backlog or prolonged Spot capacity shortage
    → trigger controlled fallback within budget/SLO limits
~~~

This governs **time to completion**. Pushing Spot to 100% solely to minimize unit CPU cost can increase business cost if critical jobs miss deadlines.

## 11. Monitoring Preemption and Processing Quality

### 11.1. Two Metric Groups to Track

**Resource health:**

- Count of Spot VMs running, stopped, deleted, or failing to provision.
- Preemption/system events recorded in Cloud Logging.
- Failed MIG VM recreations, quota warnings, or capacity shortages.
- CPU/memory/disk/network metrics from configured monitoring tools.

**Business health:**

- Queue backlog depth and oldest waiting job age.
- Percentage of jobs finishing within deadline.
- Average attempts, retry rate, and work lost to preemption.
- Age of latest checkpoint, recovery time, and jobs needing manual intervention.
- Duplicate output rate, commit errors, idempotency failures, or incorrect results.

A MIG with two running Spot VMs while the queue backs up for hours is **not healthy**. Prioritize SLIs reflecting true outcomes, such as "95% of product images processed within 10 minutes of upload."

### 11.2. Distinguishing Capacity Errors from Application Errors

| Symptom | Initial Hypothesis | Investigation Path |
| --- | --- | --- |
| VM unexpectedly `TERMINATED`. | Preemption, manual stop, or other error. | Inspect system events, operations, scheduling, and audit logs. |
| MIG below target size. | Spot capacity shortage, quota, policy, or broken template. | Check MIG errors/operations, machine type, zone, and quotas. |
| Workers running yet jobs processed twice. | Late ack, expired lease, or worker died after commit. | Inspect idempotency keys, transactions/commits, and retry logic. |
| Checkpoint exists yet job fails to resume. | Schema change, bad checksum, or incomplete checkpoint commit. | Verify versions, input manifests, data, and logs. |
| Job stuck indefinitely after preemption. | No redelivery mechanism, premature ack, or infinite lease. | Inspect queue, scheduler, and durable job state. |
| Costs rise despite using Spot. | Heavy rework, over-provisioning, logging/network/PD, or unchecked fallback. | Review Billing, cost per completion, and resources retained after STOP. |

### 11.3. Inspecting with gcloud

~~~bash
# READ-ONLY: current state of Spot VMs.
gcloud compute instances list \
  --project=retail-lab \
  --filter="scheduling.provisioningModel=SPOT" \
  --format="table(name,zone.basename(),status)"

# READ-ONLY: inspect scheduling/termination action for one VM.
gcloud compute instances describe spot-worker-01 \
  --project=retail-lab \
  --zone=asia-southeast1-a \
  --format="yaml(status,scheduling)"

# READ-ONLY: inspect MIG managed instance status.
gcloud compute instance-groups managed list-instances retail-spot-workers \
  --project=retail-lab \
  --zone=asia-southeast1-a
~~~

For preemption history, inspect **Cloud Logging System Event logs** filtered by project, instance ID, timestamp, and log config; Google Cloud records preemption-related events where supported. Retention rules, log read permissions, and schemas can vary by event type, so never assume absence of a log proves a VM was never preempted.

### 11.4. Smarter Alerting Than Paging on Every Single VM

A Spot VM being reclaimed is an **expected event**. You should not fire urgent pages on every single preemption. More actionable alerts include:

- Queue backlog breaching SLO thresholds.
- Insufficient active workers for a duration threatening deadlines.
- Consecutive job failure spikes or retries exceeding limits.
- Stale checkpoints not updating within expected intervals.
- Estimated spend or fallback usage approaching budget thresholds.

Separating **infrastructure signals** (VM capacity drops) from **business alerts** (jobs missing deadlines) keeps ops focused on real impact and prevents alert fatigue.

## 12. Deployment Scenario: Product Image Processing

### 12.1. Requirements

A retail platform processes hundreds of thousands of images daily:

- Source images live in a **Cloud Storage bucket**.
- A **Cloud Run** service accepts job requests and enqueues metadata.
- **Compute Engine Spot VMs** run the image format conversion workers.
- **Cloud SQL** stores business state and output image URIs.
- Related services use **GKE** for downstream analytics pipelines.
- Goal: most images finish on time while tolerating worker preemption without losing images or creating duplicate records.

Spot VMs need only read source images, write outputs/checkpoints under a granted prefix, and update job status using least-privilege IAM. Never grant project Editor just so workers can access Cloud Storage.

### 12.2. Proposed Design

~~~mermaid
flowchart TD
    CLIENT["Catalog manager uploads image"] --> GCSIN["Cloud Storage: input"]
    CLIENT --> API["Cloud Run: create job_id"]
    API --> Q["Queue: job metadata"]
    API --> SQL["Cloud SQL: job state"]
    Q --> MIG["MIG / scheduler managing Spot workers"]
    MIG --> W["Worker VM: process one image"]
    W --> GCSIN
    W --> TMP["Cloud Storage: staged output"]
    TMP --> OUT["Cloud Storage: published output"]
    W --> SQL
    W -. "Preemption" .-> REDO["Queue redelivery / retry"]
    REDO --> MIG
    MON["Cloud Monitoring"] -. "Queue lag, retries, internal SLA" .-> Q
    MON -.-> SQL
~~~

The data flow needs explicit commit rules. One pattern:

1. Cloud Run generates a deterministic `job_id` and inserts a `PENDING` row in Cloud SQL.
2. Job metadata is pushed to the queue; any worker can claim it.
3. The worker computes the output and uploads it to a **staging object** keyed by job/attempt.
4. The worker verifies the checksum and commits `COMPLETED` status via a transaction/idempotency key.
5. The finalized object is published via versioning/atomic write rules; the queue message is acked once durable state is valid.
6. If preempted at any point, another worker inspects state and resumes or cleanly retries uncommitted steps.
7. Periodic cleanup sweeps orphaned staging objects and jobs exceeding retry limits.

**Important:** if publishing an object and committing Cloud SQL are two separate operations, there is no automatic distributed transaction across them. Design for crashes between the two steps using intermediate states, reconciliation, or consistent commit ordering. Never claim the entire flow is "exactly-once" solely because SQL has a primary key.

### 12.3. IAM, Networking, and Data

| Component | Permissions/Config to Consider | Rationale |
| --- | --- | --- |
| Spot worker service account | Only required input read and output/checkpoint write permissions. | Limits data exposure if a worker VM is compromised. |
| Cloud SQL | Authenticated connectivity and least-privilege DB roles. | Network reachability alone must not allow arbitrary DB updates. |
| VPC | VMs need no external IP if Google APIs/DB paths are properly routed. | Reduces attack surface; use Private Google Access/Cloud NAT/PSC as needed. |
| Queue identity | Permitted only to pull and ack jobs for this workload. | Separates enqueue permissions from worker execution permissions. |
| CI/CD deployer | Scoped permissions to update templates/MIGs. | Keep infra management rights away from runtime workers. |
| Logging | Log `job_id`, attempt, checkpoint, and errors cleanly. | Essential for investigating preemptions and retries. |

Never store service secrets or Cloud SQL passwords in public images or unprotected metadata startup scripts. Prefer managed identities, Secret Manager, and least-privilege access per architecture.

### 12.4. Failure Scenarios to Test

| Moment VM Is Preempted | Expected Outcome |
| --- | --- |
| Before pulling a job. | Zero lost work; job stays in queue. |
| After claiming a job, before writing output. | Job is redelivered after lease/ack deadline expires. |
| After uploading staged object, before SQL commit. | Next worker detects staging artifact and completes/retries safely. |
| After SQL commit, before queue ack. | Redelivery detects `COMPLETED` and skips duplicate writes/side effects. |
| Mid-checkpoint write. | Last committed checkpoint remains valid; partial write is ignored. |
| Entire zone runs out of Spot capacity. | Queue buffers jobs; if deadlines approach, approved fallback triggers. |

This test suite is what proves **the application survives interruptions**, not merely seeing `gcloud compute instances create` succeed.

## 13. Common Mistakes

### 13.1. "Spot VMs Are Cheap, So They Fit Every Production Workload"

False. Lower prices do not guarantee capacity or uptime. Production can use Spot **for flexible workload tiers**, yet critical paths usually need stable baseline capacity or fallback.

### 13.2. "The VM Has Run for 20 Hours, So It Will Probably Be Reclaimed Soon"

No such simple timer exists for Spot. Preemption depends on resource demand and service conditions, not a predictable countdown clock. Never schedule restarts based on guessed VM age.

### 13.3. "Enabling a Shutdown Script Means Zero Data Loss"

False. Notice duration is best effort and may not suffice. Periodic checkpointing and durable commits are the real protection.

### 13.4. "A MIG Always Replaces Preempted Spot VMs Immediately"

False. A MIG tries to maintain target capacity, yet if a zone lacks Spot capacity, replacements cannot start right away. Multi-zone spread, fallback capacity, and backlog monitoring are still required.

### 13.5. "Persistent Disks Make Every Job Automatically Resumable"

Not necessarily. A disk may survive `STOP`, but process memory vanishes; if the VM uses `DELETE` and disks auto-delete, data disappears too. Replacement workers must also know how to locate and safely resume from persisted state.

### 13.6. "Queue Redelivery Guarantees Zero Loss and Zero Duplicates"

Queues provide retry on failure, yet **acking before committing** risks losing work, while **committing before acking** risks duplicate execution. Idempotency and transactions/reconciliation remain mandatory.

### 13.7. "Running Cloud Run on Spot VMs Will Be Cheaper"

Cloud Run users do not select Compute Engine's Spot provisioning model for Cloud Run services the way they do for VMs. To self-manage Spot compute, choose Compute Engine, GKE, or Batch and account for the operational overhead.

## 14. Self-Check Exercises

### Exercise 1 — Choosing Workloads

Classify three systems: (a) primary database server, (b) queue-based image resize worker, (c) high-availability payment HTTP API. Which is suitable to pilot on Spot first and why?

**Hint:** (b) typically fits well if each image is retryable, inputs/outputs are durable, and deadlines are handled; (a) and (c) require stronger availability and durability models.

### Exercise 2 — Distinguishing STOP and DELETE

A Spot VM has `--instance-termination-action=STOP`. After preemption, what must you check before assuming it can restart and continue the job? If switched to `DELETE`, what happens to a boot disk with `autoDelete`?

**Hint:** check VM state, Spot capacity, checkpointed data, queue state, boot/attached disks, and worker launch triggers; with `DELETE`, account for disks deleting alongside the instance.

### Exercise 3 — Picking a Checkpoint Interval

A job runs for 90 minutes and takes 4 seconds to save a checkpoint. Compare checkpointing every 2, 5, and 15 minutes. Analyze worst-case lost work on preemption and checkpoint overhead, then propose an initial benchmark interval.

**Hint:** more frequent checkpoints cut rework while increasing writes. Factor in consistency and recovery reliability, not just raw overhead.

### Exercise 4 — Handling Double Processing

Worker A commits output to Cloud SQL and gets preempted before acking the message. Worker B receives the same `job_id`. Design how Worker B checks state and avoids duplicate writes; explain the role of unique keys/transactions.

### Exercise 5 — Investigating a Stopped VM

~~~bash
gcloud compute instances describe spot-worker-01 \
  --project=retail-lab \
  --zone=asia-southeast1-a \
  --format="yaml(status,scheduling)"
~~~

If `status: TERMINATED`, is that sufficient evidence that preemption occurred? List additional sources to inspect and how to verify whether the job was redelivered.

### Exercise 6 — Deadline Architecture

A daily job must finish by 06:00, yet Spot capacity runs short from 04:00 to 05:30. Propose how to monitor queue lag, when to trigger standard workers, and how to cap fallback spend. Why might simply raising the desired Spot count in a MIG fail to solve this?

## 15. Pre-Production Deployment Checklist

| Item | What to Verify |
| --- | --- |
| **Workload suitability** | Interruptible, retryable, and able to meet SLOs across restarts. |
| **Provisioning model** | Uses `SPOT` with supported machine type/zone and verified quotas. |
| **Termination action** | `STOP` or `DELETE` chosen deliberately for worker and disk lifecycles. |
| **Shutdown handling** | Hook/signal handling present where helpful, without relying solely on notice duration. |
| **Durable state** | Inputs, checkpoints, outputs, and idempotency keys live outside the VM or are protected by design. |
| **Retries** | Ack/lease timeouts, retry caps, and dead-letter or terminal error handling configured. |
| **Concurrency** | Race conditions and duplicate writes across concurrent workers are prevented. |
| **Orchestration** | MIG/Batch/GKE or orchestrator handles Spot capacity drops and monitors shortages. |
| **Fallback** | Standard capacity fallback or load-shedding plan exists when deadlines are threatened. |
| **IAM and networking** | Least-privilege service account; VPC egress/Google APIs/DB paths properly configured. |
| **Observability** | Tracks preemptions, backlog, checkpoint age, retries, and job completion rates. |
| **Cost control** | Measures cost per completed job, not hourly VM price alone. |
| **Recovery tests** | Tested VM loss at multiple pipeline stages verifying zero lost or duplicate data. |

## 16. Reference Links and Key Takeaways

Features, pricing, supported machine types/zones, and preemption policies can change. Verify current Google Cloud documentation during deployment:

- [Spot VMs overview — Compute Engine](https://cloud.google.com/compute/docs/instances/spot)
- [Create and use Spot VMs](https://cloud.google.com/compute/docs/instances/create-use-spot)
- [Preemptible VM instances](https://cloud.google.com/compute/docs/instances/preemptible)
- [Instance scheduling options](https://cloud.google.com/compute/docs/instances/instance-scheduling-options)
- [Managed Instance Groups overview](https://cloud.google.com/compute/docs/instance-groups)
- [Cloud Batch documentation](https://cloud.google.com/batch/docs)
- [GKE Spot VMs](https://cloud.google.com/kubernetes-engine/docs/concepts/spot-vms)
- [Cloud Storage consistency](https://cloud.google.com/storage/docs/consistency)
- [Cloud Pub/Sub subscriber overview](https://cloud.google.com/pubsub/docs/subscriber)
- [Compute Engine pricing](https://cloud.google.com/compute/all-pricing)

**Spot VMs work well when workloads are engineered to survive interruptions.** A VM can be reclaimed at any moment; true resilience comes from breaking work into small units, writing consistent checkpoints, committing idempotently, redelivering unfinished jobs, and maintaining fallback capacity for deadlines. Combining these principles with Compute Engine, IAM, VPC, data services, and monitoring lets teams capture Spot cost savings while safeguarding data integrity and service quality.

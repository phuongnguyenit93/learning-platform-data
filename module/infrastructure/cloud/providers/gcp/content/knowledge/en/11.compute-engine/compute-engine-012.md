# Live Migration, Maintenance Policies, and Maintenance Schedules

## Learning Objectives

After this lesson, learners will be able to:

1. Explain why **Compute Engine** performs physical host maintenance and how **live migration** keeps VMs running during planned maintenance.
2. Distinguish **onHostMaintenance: MIGRATE/TERMINATE**, **automaticRestart**, **hostErrorTimeoutSeconds**, **Local SSD** recovery behavior, as well as differences between maintenance and hardware failures.
3. Identify VM types that **do not support live migration**, particularly Spot/preemptible, GPU/TPU, bare metal, and certain specialized configurations.
4. Inspect and modify **host maintenance policies** with `gcloud` under valid conditions, while reading **maintenance-event**, **upcoming-maintenance**, and Cloud Audit Logs notices.
5. Understand the limits of **advance maintenance notifications** and **on-demand maintenance**; build runbooks to minimize application impact, verify behavior, and recover.
6. Design availability for Java APIs on Compute Engine, managed instance groups (MIGs), GKE, and data systems; evaluate monitoring, security, cost, and SLOs.

## 1. Context: VMs Run on Infrastructure That Must Be Maintained

A VM on **Google Compute Engine** runs inside a zone on a physical host managed by Google Cloud. Over the host's lifecycle, the platform may need to update the hypervisor, apply security patches, replace components, fix network issues, or perform hardware maintenance. These operations do not mean customer applications must go down in every case.

For example, a **Java/Spring Boot** order-processing application runs on VM **orders-api-01**, with an attached Persistent Disk inside a private VPC network. If the physical server hosting the VM requires maintenance, there are two main outcomes:

- **Live migrate:** Google Cloud transfers the running VM's state to another host within the **same zone**, with a brief pause and without requiring a normal guest OS reboot.
- **Terminate:** the VM is stopped during the maintenance event; depending on configuration and machine type, Compute Engine may **automatically restart** it afterward.

These behaviors are governed by the **host maintenance policy** and VM type support. Merely calling a machine a "standard VM" does not always permit live migration; GPUs, bare metal, Spot, and certain specialized machines have distinct rules.

In the **CLOUD_PROVIDERS_GCP** module, learners deploy projects, IAM, VPCs, Compute Engine, GKE, Cloud Run, storage, and databases while automating releases and tracking reliability and cost. Understanding host maintenance is part of operational design: **avoid confusing the platform's effort to keep a single VM alive with a guarantee that the application will never experience disruption**.

### Key Terms

| Term | Meaning | Do Not Confuse With |
|---|---|---|
| **Host maintenance event** | Maintenance activity on the underlying host/infrastructure running the VM | Deploying an app update or patching the guest OS |
| **Live migration** | Moving a running VM to another physical host in the same zone | Migrating workloads from on-premises to cloud or switching zones |
| **Host error** | A host failure leaving the VM unresponsive or needing recovery | Scheduled maintenance that always arrives with advance notice |
| **Host maintenance policy** | VM behavior during host events/errors via scheduling fields | An instance schedule that stops/starts VMs to save money |
| **Upcoming maintenance notification** | Advance notice with a time window for certain machine families | A fixed calendar available for every VM |
| **On-demand host maintenance** | Proactively triggering an **already announced maintenance event** when eligible | Ordering Google Cloud to maintain any VM at arbitrary times |
| **Application high availability (HA)** | Multi-instance/multi-zone design, health checks, retries, failover | Merely enabling live migration on one VM |

## 2. How Does Live Migration Work?

Live migration moves a VM's **execution state** between two hosts within the **same zone**. The goal is to preserve VM properties—including **IPs, metadata, network configuration, application state, and block storage** per service capabilities—rather than stopping and rebooting from scratch.

~~~mermaid
sequenceDiagram
    participant G as Google Cloud control plane
    participant S as Source host
    participant T as Target host (same zone)
    participant C as Application client
    G->>S: Detect host maintenance
    G->>T: Prepare target VM
    S->>T: Copy memory, track dirty pages
    C->>S: Active traffic
    Note over S,T: Final state transfer, brief blackout
    S->>T: Hand off execution to target host
    C->>T: Continue reaching VM at the same IP
    G->>G: Record migration event
~~~

High-level stages:

1. **Source brownout:** the VM continues running on the source host; memory pages are copied to the target host while tracking modified pages.
2. **Blackout:** a very brief execution pause to sync final state and switch control to the target host.
3. **Target brownout:** the VM resumes on the target host; post-migration tasks complete and steady-state performance stabilizes.

The pause is typically **sub-second** for normal live migrations, though it is not an absolute guarantee of zero packet loss, zero latency spikes, or zero timeouts. Workloads with heavy memory-write rates, latency-sensitive dependencies, or specialized drivers may experience brief performance jitter during migration.

### What Is Normally Preserved

- **VM name, resource identity, zone, and IP addresses**; neither project nor zone changes.
- **Guest OS and application processes** keep running; no reboot occurs during a successful live migration.
- **Persistent Disks** and network settings remain intact per storage/network support.
- **Local SSDs** can also live-migrate with their data on supported machine lines, though Local SSD data remains ephemeral and at risk during non-migratable host events.

### What Live Migration Does Not Guarantee

- Does not protect a VM from a **zonal outage** or widespread network disruption.
- Does not replace backups, database recovery, replication, load balancing, or application fault testing.
- Does not prevent every **host failure**: if hardware fails completely or state cannot be migrated, the VM may terminate and recover via restart.
- Does not fix application bugs, memory leaks, deadlocks, schema migrations, or broken backend dependencies.
- Does not move a VM from **zone A to zone B**, nor perform cross-region disaster recovery.

**Conclusion:** live migration minimizes disruption from **planned infrastructure maintenance**, whereas **HA/SLOs** depend on the overall application architecture.

## 3. Host Maintenance Policy: Three Key Behavioral Controls

These settings live under the **`scheduling`** field of a Compute Engine instance. Defaults depend on machine type, provisioning model, and platform support.

### 3.1. onHostMaintenance: MIGRATE or TERMINATE

| Value | Behavior When Host Needs Maintenance | When Appropriate |
|---|---|---|
| **MIGRATE** | Compute Engine attempts to move the running VM to a new host in the same zone | VM supports live migration, workload needs high uptime and tolerates brief brownouts |
| **TERMINATE** | Compute Engine stops the VM during maintenance; may auto-restart afterward depending on policy | Machine type does not support migration, or workload is designed to accept stops |

**MIGRATE** is the default for many standard VMs that support it. **TERMINATE** is mandatory for VM types that cannot live migrate, and is also the default/only valid option for Spot and preemptible VMs.

You cannot enable **MIGRATE** on a GPU VM or bare metal instance simply by flipping a flag. Compute Engine validates the machine configuration and rejects invalid settings.

### 3.2. automaticRestart: Compute Engine Restart After Failure

The **automaticRestart** field controls whether Compute Engine automatically restarts a standard VM after it stops due to a **host error** or a **programmed stop** such as maintenance under an eligible policy.

- **true**: Compute Engine attempts to restart the VM after being stopped by the platform.
- **false**: no automatic restart via this mechanism; operations must handle recovery.
- Not a guarantee that "the VM will always stay up": user-initiated stops, full zonal outages, capacity issues, or other conditions behave differently from a host-error restart.
- **Spot/preemptible VMs are not automatically restarted** by this `automaticRestart` mechanism.

For instance, **TERMINATE + automaticRestart=true** is not live migration: the OS must **reboot**, services reinitialize, in-memory state is lost, client connections must reconnect, and the application experiences downtime.

### 3.3. Host Error Timeout and Local SSD Recovery Timeout

Advanced options:

| API Property | Meaning | Notes |
|---|---|---|
| **hostErrorTimeoutSeconds** | Max wait time before recovering a VM when a host becomes unresponsive | Balances fast detection against premature recovery; valid values vary by machine/API |
| **localSsdRecoveryTimeout** | Max time spent trying to recover Local SSD data in supported cases before falling back | Not a backup and does not guarantee Local SSD data survival |
| **gracefulShutdown** and timeout (where supported) | Gives workloads extra time to finish tasks during shutdown | Not a promise that graceful shutdown always runs for every host maintenance or host error |

**Local SSDs** fit caches and scratch data; critical data belongs on **Persistent Disks, Cloud Storage, replicated databases, or other durable stores**. If a GPU VM terminates for host maintenance, attached Local SSD data may be unrecoverable; checkpoint to durable storage beforehand.

## 4. Distinguishing Host Maintenance, Host Errors, and Intentional Actions

| Event | Cause | Live Migration? | What to Prepare? |
|---|---|---|---|
| **Planned host maintenance** | Host, hypervisor, security patch, or infra upgrades | Possible if VM supports it and policy=MIGRATE | Monitor notices, SLOs, and performance |
| **Emergent maintenance** | Predictive host fault or degrading hardware needing intervention | Possible depending on severity and VM | Notice may be short; be ready to drain/recover |
| **Sudden host failure** | Complete host failure / cannot migrate | Likely no | `automaticRestart`/HA, alerts, and runbooks |
| **Manual VM stop** | Admin or pipeline explicitly stops the VM | No, not live migration | Coordinate app maintenance windows, checkpoint, restart |
| **Guest OS update/reboot** | OS patching or app deployment | Not handled by live migration | Rolling updates, backups, health checks |
| **Zonal outage** | Availability zone disruption | Live migration cannot solve this | Multi-zone / multi-region architecture |
| **Spot/preemptible preemption** | Capacity reclamation for that provisioning model | No | Checkpointing, job retries, idempotent design |

**Maintenance policy is not an instance schedule:** configuring a VM to stop nightly at 22:00 to save costs is resource scheduling, not scheduling Google Cloud physical host maintenance.

## 5. Which VMs Cannot Live Migrate?

The support matrix depends on machine series and attached devices and changes over time. The rule of thumb is to **check the maintenance experience documentation for your exact machine type**, rather than relying on the family letter alone.

| Group | Live Migration Capability | Operational Action |
|---|---|---|
| **Common standard VMs** (e.g., N2, E2 types) | Many support live migration and default to MIGRATE | Verify live policy with `describe` |
| **Standard E2 VMs** | Supports only migrate during host maintenance; cannot arbitrarily switch to TERMINATE | Do not force policy changes just to test |
| **Spot / preemptible** | Do not live migrate during host maintenance | TERMINATE; checkpoint and recover at workload layer |
| **GPU-attached VMs** | Do not support live migration | TERMINATE; save checkpoints beforehand; mind Local SSDs |
| **TPU-attached instances** | Do not support live migration per architecture specs | Prepare for stop/restart and model checkpointing |
| **Bare metal instances** | Cannot live-migrate an entire bare metal host like a VM | TERMINATE; schedule maintenance and expect downtime |
| **Cloud RDMA network interfaces** | Do not support live migration | TERMINATE; coordinate HPC jobs |
| **Z3 with > 18,000 GiB Titanium SSD** | Do not live migrate | TERMINATE; check machine series docs |
| **Z4D/Z4M with > 42,000 GiB Titanium SSD** | Do not live migrate | TERMINATE per configuration requirements |
| **Selected Confidential VMs or specialized shapes** | Depends on chip/config; may be unsupported | Consult technology-specific documentation |

At the time of writing, Google Cloud docs also list specialized lines like **H4D, X4/X5, and certain Z-series** with distinct maintenance or restart behaviors. This list is **not static**: check **Host maintenance overview** and the series-specific maintenance experience at deployment time.

**Important distinction:** a machine may support **advance maintenance notifications** while **not supporting live migration**. For example, GPU VMs receive advance notices so teams can checkpoint—not because GPU workloads live migrate.

## 6. Hands-On with gcloud: Viewing and Setting Host Maintenance Policy

Illustrative values used below:

| Variable | Sample Value |
|---|---|
| Project ID | **shop-dev-001** |
| Zone | **asia-southeast1-b** |
| Live-migratable VM | **orders-api-lab** |
| VM testing terminate policy | **batch-lab** |

These are **hypothetical** names. Run only in an authorized test project; creating VMs/disks and enabling logging can incur charges. Never run stop/reconfigure/maintenance commands in production without approval.

### 6.1. Inspecting VM Status and Machine Type

~~~bash
# List VMs in the target project
gcloud compute instances list --project=shop-dev-001

# Inspect current VM configuration
gcloud compute instances describe orders-api-lab \
  --project=shop-dev-001 \
  --zone=asia-southeast1-b \
  --format="yaml(name,status,machineType,scheduling,disks,resourceStatus)"
~~~

Inspect **scheduling.onHostMaintenance**, **scheduling.automaticRestart**, **scheduling.provisioningModel**, GPU/Local SSD attachments, and VM status before deciding on changes.

### 6.2. Inspecting the Maintenance Policy Specifically

~~~bash
gcloud compute instances describe orders-api-lab \
  --project=shop-dev-001 \
  --zone=asia-southeast1-b \
  --flatten=scheduling
~~~

Example output (hypothetical):

~~~yaml
scheduling:
  automaticRestart: true
  onHostMaintenance: MIGRATE
  preemptible: false
  provisioningModel: STANDARD
~~~

This shows the VM is configured to **attempt live migration during host maintenance**. It does not mean host errors, zonal outages, or Java application bugs are eliminated.

### 6.3. Creating a VM with an Explicit Maintenance Policy

Illustrative creation command (incurs charges; run only when authorized):

~~~bash
gcloud compute instances create orders-api-lab \
  --project=shop-dev-001 \
  --zone=asia-southeast1-b \
  --machine-type=n2-standard-2 \
  --image-family=debian-12 \
  --image-project=debian-cloud \
  --maintenance-policy=MIGRATE \
  --restart-on-failure
~~~

`n2-standard-2` illustrates a typical live-migratable standard VM. In real usage, verify quotas, VPC/firewall/IAM/OS Login configs, and costs; creating the VM **does not deploy the Java API on its own**.

### 6.4. Changing Policy on an Existing VM

CLI command per current docs:

~~~bash
# IMPACTING OPERATION: test VM must be stopped per CLI prerequisites
gcloud compute instances set-scheduling batch-lab \
  --project=shop-dev-001 \
  --zone=asia-southeast1-b \
  --maintenance-policy=TERMINATE \
  --restart-on-failure
~~~

**Important:** the CLI reference for **`gcloud compute instances set-scheduling`** specifies calling it when the VM is **`TERMINATED` (stopped)**. Therefore this example assumes **batch-lab is safely stopped** and tasks are checkpointed. Never stop a customer-facing VM casually just to tweak a policy.

If the VM or machine series forbids modifying **onHostMaintenance** (such as E2 or certain Spot/specialized lines), the command will be rejected. For instance templates and MIGs, set the policy in the **instance template** and roll out via MIG workflows rather than manually editing individual managed instances.

### 6.5. Automatic Restart Is Independent of MIGRATE/TERMINATE

~~~bash
# Example disabling auto-restart on a stopped lab VM
gcloud compute instances set-scheduling batch-lab \
  --project=shop-dev-001 \
  --zone=asia-southeast1-b \
  --no-restart-on-failure
~~~

Use **`--restart-on-failure`** to re-enable it when supported by the machine type. Avoid **`--no-restart-on-failure`** on systems needing self-recovery unless the workload layer handles replacement; disabling restart can leave the VM stopped after a host event.

## 7. Maintenance Schedules: Not Every VM Receives Advance Notice

Compute Engine can issue **upcoming maintenance notifications** for supported machine families. Notifications tell operations teams the **maintenance window** and sometimes permit **proactively starting maintenance within an allowed interval**.

### 7.1. Machine Families with Advanced Maintenance Notifications

At the time of writing, Google Cloud docs list advanced notifications across eligible lines such as **A/G-series GPUs**, **TPUs**, **C3/C3D/C4/C4A/C4D**, **C4N**, **H3/H4D**, **M-series**, **X-series**, and **Z-series**. The exact list and lead time **vary by machine and configuration**.

Never claim **"all E2/N2 VMs get 7 days' advance notice."** Many standard VMs rely primarily on live migration and emit only short-lead **`maintenance-event`** signals. **Emergency/unscheduled** events may arrive with shorter notice or without a standard window.

### 7.2. Key `upcomingMaintenance` Fields

Illustrative JSON showing an event **eligible for manual early start**:

~~~json
{
  "canReschedule": true,
  "latestWindowStartTime": "2026-12-10T18:00:00Z",
  "machineType": "c4-highmem-192",
  "maintenanceStatus": "PENDING",
  "type": "SCHEDULED",
  "windowStartTime": "2026-12-10T18:00:00Z",
  "windowEndTime": "2026-12-10T22:00:00Z"
}
~~~

These timestamps are **hypothetical** for learning how to read the structure, not a real account schedule.

| Field | Interpretation |
|---|---|
| **maintenanceStatus: PENDING** | Event is scheduled and awaiting start |
| **maintenanceStatus: ONGOING** | Maintenance is currently in progress |
| **canReschedule: true** | Machine type and timing allow manually starting maintenance within the notified window |
| **canReschedule: false** | Timing cannot be altered manually, or event already started / machine unsupported |
| **windowStartTime** | Expected maintenance window start |
| **windowEndTime** | Expected maintenance window end |
| **latestWindowStartTime** | Latest timestamp selectable to trigger maintenance under supported rules |
| **type: SCHEDULED** | Planned maintenance |
| **type: UNSCHEDULED** | Urgent/emergency maintenance; presentation may differ by channel |

Read **UTC timestamps** carefully and convert to your operational timezone. Never read **`latestWindowStartTime`** as "maintenance will definitely happen at that exact hour"; it marks the boundary of the reschedule/on-demand choice window.

### 7.3. Users Cannot Arbitrarily Schedule Infrastructure Maintenance

On machine types with **on-demand maintenance**, you can **start early** an already-notified event within the allowed window. If you take no action, Compute Engine executes it per platform scheduling policy.

There is no universal "Google, maintain this VM every Wednesday" button for all VMs. Setting schedules for **app restarts**, **nightly VM stops**, or **OS patch rollouts** are separate workflows; they do not control Google Cloud's physical host maintenance calendar.

## 8. Three Ways to View Maintenance Notifications

### 8.1. Via gcloud / Compute Engine API

~~~bash
# Returns details only if the VM is a supported type with an upcoming event
gcloud compute instances describe orders-api-lab \
  --project=shop-dev-001 \
  --zone=asia-southeast1-b \
  --format="yaml(resourceStatus.upcomingMaintenance)"
~~~

If it returns **null** or omits the field, either no event is currently scheduled or the VM's machine family does not support **`upcomingMaintenance`**. Never infer that the host will never undergo maintenance.

### 8.2. Via the Metadata Server Inside the VM

**`maintenance-event`** is a near-real-time metadata key used by applications needing immediate signals:

~~~bash
# Run INSIDE the guest VM
curl -sS -H "Metadata-Flavor: Google" \
  "http://metadata.google.internal/computeMetadata/v1/instance/maintenance-event"
~~~

Common values:

| Value | Meaning |
|---|---|
| **NONE** | No imminent host maintenance event reported on this key |
| **MIGRATE_ON_HOST_MAINTENANCE** | VM is about to live migrate / is migrating |
| **TERMINATE_ON_HOST_MAINTENANCE** | VM will terminate during host maintenance |

Per Compute Engine docs, live-migrating VMs can receive roughly **60 seconds of advance notice** if the application **has queried the `maintenance-event` key at least once between events**. If the key was never queried since the prior maintenance, Compute Engine may **skip the 60-second warning**. For non-migratable VMs like GPUs, termination notices typically appear around **60 minutes prior**; exact timing depends on machine type and event nature.

You can long-poll:

~~~bash
curl -sS -H "Metadata-Flavor: Google" \
  "http://metadata.google.internal/computeMetadata/v1/instance/maintenance-event?wait_for_change=true"
~~~

**This waits for a single change.** A production daemon needs a loop managing **ETags**, timeouts, retries/backoff, and idempotent handling, as the metadata server may briefly return **HTTP 503** during maintenance.

For machines supporting advanced notifications, check:

~~~bash
curl -sS -H "Metadata-Flavor: Google" \
  "http://metadata.google.internal/computeMetadata/v1/instance/upcoming-maintenance?alt=json"
~~~

If it returns **NONE** or has no data yet, keep polling periodically. **`upcoming-maintenance`** and **`maintenance-event`** are **two keys serving two purposes**: early planning vs. imminent reaction.

### 8.3. Via Cloud Logging and Cloud Audit Logs

Compute Engine emits **System Event audit logs** for infrastructure events:

- **compute.instances.upcomingMaintenance**: advance notification, PENDING/ONGOING or completion states.
- **compute.instances.migrateOnHostMaintenance**: VM live-migrated for host maintenance.
- **compute.instances.terminateOnHostMaintenance**: VM terminated for host maintenance.
- **compute.instances.automaticRestart**: Compute Engine automatically restarted the VM where supported.

In **Logs Explorer**, an illustrative filter:

~~~text
resource.type="gce_instance"
(
  "compute.instances.upcomingMaintenance"
  OR "compute.instances.migrateOnHostMaintenance"
  OR "compute.instances.terminateOnHostMaintenance"
  OR "compute.instances.automaticRestart"
)
~~~

Readers need **Cloud Logging Logs Viewer** or equivalent permissions; exact log emission varies by machine type and logging settings. Create **log-based alert policies** when maintenance events arrive, routing notifications to ops and ticketing/runbook systems.

During incidents, distinguish **system events** from **VM guest logs**, **application logs**, and **health checks**: system events report what the platform did, while application metrics show how users were affected.

## 9. Proactively Starting Maintenance When Supported

If a VM has an upcoming maintenance event with:

- **`canReschedule: true`**,
- **`maintenanceStatus: PENDING`**,
- within the permitted time bounds,

administrators can trigger maintenance proactively to avoid peak traffic windows.

~~~bash
# IMPACTING OPERATION, only for eligible approved VMs
gcloud compute instances perform-maintenance INSTANCE_NAME \
  --project=PROJECT_ID \
  --zone=ZONE
~~~

When executed successfully, maintenance **begins immediately**, triggering live migration or stop/restart depending on policy and machine type. This is **not a dry-run** command. If no eligible event exists, the service may report **`There is no reschedulable upcoming maintenance`**.

**Pre-execution runbook:**

1. Verify exact **project/zone/VM**, machine type, and policy.
2. Confirm **`canReschedule/PENDING`** status and window bounds.
3. Balance **SLOs and business demand**; schedule off-peak for sensitive apps.
4. Notify dependent teams and on-call engineers.
5. Drain requests or checkpoint data **if required by the workload**; verify backups/restores.
6. Run **`perform-maintenance`** only with approval.
7. Watch logs, VM status, health checks, and metrics during and after the event.
8. Record outcomes, actual duration, application errors, and lessons learned.

### Distinguishing from Simulating Maintenance Events

Google Cloud also offers **`simulate-maintenance-event`** to test metadata transitions and application responses in test environments:

~~~bash
# Potentially disruptive test command; lab VMs only
gcloud compute instances simulate-maintenance-event orders-api-lab \
  --project=shop-dev-001 \
  --zone=asia-southeast1-b \
  --with-extended-notifications=True
~~~

This simulation tests maintenance handling end-to-end; it is **not** a read-only command. On non-migratable VMs or VMs with terminate policy, it can stop/restart the VM. Never run it in production without an approved change and rollback plan.

## 10. Operating a Java Application Through Maintenance

Suppose **orders-api** runs Java/Spring Boot on Compute Engine, talks to **Cloud SQL PostgreSQL**, stores images in Cloud Storage, and receives traffic via an Application Load Balancer.

### 10.1. What Can Happen During Live Migration?

- **Brief latency spikes** during state handoff, causing a few slow HTTP responses or timeouts.
- **Long-lived TCP connections / WebSockets** may drop or stall if client timeouts are aggressive or sensitive to latency blips.
- **Database connection pools** may observe transient errors from network jitter; proper reconnect handling is essential.
- **Java processes** usually stay up without restarting during successful live migration, yet applications must still handle unpredictable platform hiccups.

Never use live migration as an excuse to skip bounded retries, sane timeouts, circuit breakers, and idempotency on state-changing transactions.

### 10.2. Configuring Applications for Brief Interruptions

**Sane timeouts:** clients and backends need deadlines aligned with business needs; overly tight timeouts amplify brownout errors, while huge timeouts cause queue pileups.

**Safe retries:** retry only **idempotent** operations, or use idempotency keys on order/payment endpoints. Unbounded retries can trigger retry storms right after maintenance.

**Connection pools:** enable connection validation, max wait timeouts, and automatic pool recovery on errors; never assume in-memory sessions survive VM termination/restarts.

**Readiness/health endpoints:** load balancers and managed instance groups must know whether an instance can truly serve traffic. Health checks should verify real app readiness, not just OS ping.

**Drain before stop:** for VMs facing terminating maintenance, proactively drain traffic from the instance, finish in-flight jobs, and checkpoint within the warning window.

### 10.3. Minimal Multi-Instance, Multi-Zone Design

~~~mermaid
flowchart TB
    C["Client"] --> LB["Application Load Balancer"]
    LB --> M["Regional Managed Instance Group"]
    M --> Z1["VM A<br/>zone A"]
    M --> Z2["VM B<br/>zone B"]
    Z1 --> DB["Cloud SQL HA / protected database"]
    Z2 --> DB
    OBS["Cloud Monitoring / Logging"] --> M
~~~

**Live migration** operates at the **VM/host** level. A **regional MIG** and load balancer keep serving when an instance or entire zone is affected, provided capacity, health checks, and networking are properly designed. **Cloud SQL HA** is also a separate mechanism; VM HA does not automatically make a database HA.

For VMs holding persistent local state, consider **stateful MIGs** or externalizing state. Stateless applications allow far simpler rolling replacement and failover.

## 11. Maintenance in Managed Instance Groups (MIGs)

A MIG defines VMs via an **instance template** and provides **autohealing** when health checks fail. A VM's host maintenance policy inside a MIG does not replace those capabilities.

| Layer | Role | Risks to Manage |
|---|---|---|
| **VM host maintenance MIGRATE** | Reduces per-VM downtime during maintenance | Latency spikes; non-migratable exceptions |
| **VM automaticRestart** | Attempts VM recovery after host error/maintenance terminate | Requires boot and app readiness; not zonal HA |
| **MIG autohealing** | Replaces unhealthy instances based on health checks | Overly sensitive health checks can cause instance churn |
| **Rolling update** | Proactively rolls out new templates/images | Can cause downtime if update policies are misconfigured |
| **Regional MIG** | Spreads VMs across multiple zones | Capacity, quotas, and distribution must still be managed per zone |
| **Load balancer** | Routes traffic to healthy backends | Must verify warm-up, draining, and session affinity |

To change a fleet's maintenance policy:

1. Define the updated policy in a new **instance template**.
2. Test on a canary or staging group.
3. Review update policy, `maxSurge`/`maxUnavailable`, and zonal capacity.
4. Roll out in controlled batches with health checks, watching 5xx errors and latency.
5. Never hand-edit MIG-managed VMs only for the old template to overwrite changes on recreation.

**Note:** a user-initiated rolling update is **separate** from Google Cloud's host-maintenance live migration.

## 12. GPUs, Local SSDs, and HPC Workloads: Preparing for Termination

### 12.1. GPU VMs Need Checkpointing

GPU VMs do not support live migration during host maintenance. For AI model training on GPUs:

~~~text
GPU job running → maintenance notice → checkpoint model/optimizer state
          → stop job cleanly → host maintenance / VM terminates
          → VM ready again → load checkpoint → resume training
~~~

Your plan should include:

- **Periodic checkpoints** saved to Cloud Storage or durable disks.
- Checkpoint restoration logic with integrity/version verification.
- Graceful shutdown during supported notice windows, without assuming every urgent host failure yields full warning time.
- Monitoring for preempted/terminated jobs, retries, and uncommitted outputs.

Specifically on GPU VMs, **Local SSD data may be unrecoverable when Compute Engine stops a VM for host maintenance**. Never keep your sole checkpoint on Local SSD.

### 12.2. Bare Metal and RDMA

Bare metal or HPC instances with **Cloud RDMA** may require terminate/restart during maintenance. They commonly run long jobs sensitive to topology and local storage:

- Schedule less-disruptive windows when **`upcomingMaintenance`** offers **`canReschedule`**.
- Use job schedulers/checkpointing compatible with Slurm/MPI or HPC frameworks.
- Expect full restarts or host swaps per machine series specs; never treat restarts as live migration.
- Measure downtime windows, restore speeds, and temporary data loss risk.

### 12.3. Local SSD Is Not Persistent Disk

| Property | Local SSD | Persistent Disk / Hyperdisk |
|---|---|---|
| Data location | Attached to local host infrastructure | Managed network block storage service |
| Typical use | Caches, scratch space, intermediate data | Boot, application data, database disks |
| Live migration | Can migrate with VM on supported machine lines | Data persists per storage service design |
| Non-migratable host failure | Data loss risk; recovery not guaranteed | Higher durability; still requires backups and HA |
| Recovery | May require rebuilding caches/checkpoints | Snapshots, replication/backups per product |

Not all Local SSD types/configurations share identical recovery behavior; **Z3/Z4** lines have specific Titanium SSD thresholds and maintenance rules.

## 13. Observability, SLOs, and Testing

### 13.1. Metrics to Measure

| Metric | Purpose |
|---|---|
| **VM uptime/restarts** | Distinguish rebootless live migration from terminate/restart |
| **System Event audit logs** | Confirm exact host event type and timestamp |
| **HTTP 5xx rate, p95/p99 latency** | Measure actual end-user impact |
| **Load balancer backend health** | See whether instances failed health checks |
| **CPU/memory, network throughput, disk I/O** | Spot brownouts and abnormal load |
| **Database connection errors** | Identify dependency errors triggered during migration |
| **Queue lag, job checkpoint duration** | Evaluate batch recovery efficiency |
| **Time to recover / RTO / RPO** | Measure recovery quality when migration is unavailable |

### 13.2. Tests to Run

1. **Read-only preflight:** verify machine type, policy, `automaticRestart`, and logs.
2. **Metadata listener:** verify the app reads the key and handles NONE/MIGRATE/TERMINATE.
3. **Simulated maintenance in lab:** measure error budget burn and latency.
4. **Host termination path:** test controlled stop/restart for terminate-policy workloads; measure boot-to-READY time.
5. **Multi-instance failover:** pull one backend out of the load balancer and verify clean traffic shift.
6. **Durability test:** restore backups/checkpoints after interruption; ensure no critical transactions are lost.
7. **Alert routing:** confirm log-based alerts create tickets/incidents routed to the right owners with context.

During tests, record **timestamps, request counts, error rates, latency, VM states, audit events, and rollback results**. Only mark a test successful against explicit acceptance criteria.

### 13.3. Log-Based Alerts for Maintenance

Conceptual Logs Explorer filter:

~~~text
resource.type="gce_instance"
(
  protoPayload.methodName="compute.instances.upcomingMaintenance"
  OR protoPayload.methodName="compute.instances.terminateOnHostMaintenance"
  OR protoPayload.methodName="compute.instances.migrateOnHostMaintenance"
)
~~~

Depending on event log format/version, fields may appear under **`protoPayload.methodName`**, **`operation.producer`**, or elsewhere; verify your filter against actual sample logs in the project. Enable alerts in pre-prod and test with simulated events before relying on them in production.

## 14. Maintenance Window Runbook

**Scenario:** a standalone VM serves a Java service on a machine line supporting **`upcomingMaintenance`**, with `maintenanceStatus=PENDING` and `canReschedule=true`.

### Phase A — Upon Receiving Notification

1. Record **project, zone, instance ID, machine type, `onHostMaintenance`, `automaticRestart`**.
2. Record **`windowStartTime`, `windowEndTime`, `latestWindowStartTime`** converted to the on-call team's timezone.
3. Check the machine type's maintenance experience to confirm actual **MIGRATE** vs. **TERMINATE** behavior.
4. Check backups/checkpoints, app version, SLO dashboards, and stakeholders.
5. For production, open a change record with approver and acceptable start time.

### Phase B — Before Maintenance

1. Confirm the workload has **graceful handling** and notify app owners.
2. For terminate: drain traffic, checkpoint, pause new long jobs, and confirm restore readiness.
3. For migrate: keep serving if appropriate, while heightening monitoring on latency and connection errors.
4. If supported and beneficial, start early via **`perform-maintenance`**; otherwise monitor until Compute Engine runs it.
5. Do not touch unrelated IAM, firewall, or storage configs just because a host event is pending.

### Phase C — During the Event

1. Watch System Event logs and **`MIGRATE_ON_HOST_MAINTENANCE`** or **`TERMINATE_ON_HOST_MAINTENANCE`** metadata.
2. Monitor VM state, load balancer health, and business metrics.
3. Watch for exceptions, DB pool errors, queue consumers, and restart initialization duration.
4. Escalate if error budgets burn excessively or the VM fails to recover as expected.

### Phase D — After the Event

1. Confirm the VM and service are healthy and endpoints respond cleanly.
2. Correlate audit event timestamps with any user-facing errors.
3. For GPU/HPC workloads, confirm checkpoints reloaded and jobs resumed from valid state.
4. Record actual downtime, error counts, and runbook improvements.
5. Close the ticket only once health, data integrity, and SLOs pass criteria.

## 15. End-to-End Scenario: E-Commerce and Analytics Jobs

Company **Hai An** runs its retail platform on Google Cloud:

- **orders-api** (Java) on a three-instance **regional MIG** across two zones behind an Application Load Balancer.
- **Cloud SQL** storing orders, with backups and HA configured as required.
- **image-processing** running on GPU VMs for batch image work, writing outputs to Cloud Storage.
- **Nightly-report** running retryable batch jobs on Spot VMs.

### 15.1. Policy Selection

| Workload | Characteristics | Recommended Policy / Strategy | Rationale |
|---|---|---|---|
| **orders-api** | Stateless API, latency-sensitive | Standard VMs with **MIGRATE** + `automaticRestart`; regional MIG, health checks | Minimizes host disruption with instance/zone failover |
| **Cloud SQL** | Managed database | Rely on **Cloud SQL HA/backups/failover**, not customer VM host policies | Managed database is a separate service |
| **image-processing GPU** | GPU, multi-hour batches | **TERMINATE**, periodic checkpoints + job recovery | GPUs do not live migrate; may receive advance notices |
| **Nightly-report Spot** | Low cost, interruption-tolerant | Spot with scheduler/job-level retries, not `automaticRestart` | Spot offers no continuous-runtime guarantee |

### 15.2. Two Different Alerts

**Event 1:** an `orders-api` VM live-migrates. Backend health stays mostly steady, p99 latency bumps for a few seconds, and no OS reboot occurs. Evaluate **error budget** impact rather than paging a Sev-1 incident solely because a migrate log appeared.

**Event 2:** a GPU VM receives a `PENDING` maintenance notice. The system alerts the ML team, who flush a checkpoint before the window. With **`canReschedule`**, they trigger maintenance right after finishing a batch step. Once the VM restarts, the job loads the checkpoint from Cloud Storage. Scratch data left solely on Local SSD is not assumed to survive.

### 15.3. Acceptance Matrix

| Test Condition | Expected Outcome |
|---|---|
| `orders-api` migrates in lab | Zero data loss; latency and error counts measured |
| One MIG VM stops | API keeps serving via remaining backends within SLO |
| One zone fails | Healthy instances remain in surviving zone with sufficient capacity |
| GPU VM receives maintenance notice | Checkpoint and runbook executed before stop |
| GPU VM restarts | Job resumes cleanly from durable checkpoint |
| Spot job is preempted | Retry/idempotency works without duplicating records |
| Logs record migrate/terminate events | Alerts/tickets classify severity accurately |
| Cost tracking | Metrics tracked per workload and runtime; policy is not mistaken for budget |

## 16. Common Misconceptions

**"Enabling MIGRATE means zero downtime ever."** False. Live migration minimizes disruption, yet unmigratable host failures, guest crashes, or zonal outages can still cause downtime.

**"Automatic restart is live migration."** False. Restart reboots the guest OS and application; successful live migration transfers a running VM without rebooting.

**"Every VM gets 7 days' advance notice."** False. **`upcomingMaintenance`** applies only to supported machine families and maintenance types; emergency events may arrive with short notice or no standard window.

**"A GPU VM with `upcomingMaintenance` can live migrate."** False. GPU VMs terminate during maintenance and require checkpointing.

**"Spot VMs can enable `automaticRestart` to avoid preemption."** False. Spot/preemptible VMs do not have standard VM `automaticRestart`.

**"Local SSD always survives a host failure."** False. While some live migration/recovery paths exist, Local SSD is not durable storage.

**"`set-scheduling` can change any policy on any running VM."** False. The CLI requires specific VM states (`TERMINATED`), and several VM types enforce fixed policies.

**"Live migration removes the need for a regional MIG."** False. Live migration stays within the **same zone**; regional MIGs/HA mitigate instance and zonal risks.

**"Maintenance windows can be fixed like a weekly cron job."** False. Only supported series allow rescheduling or early triggering within an **already notified maintenance window**.

**"Seeing no `upcomingMaintenance` means no maintenance will happen."** False. Either none is scheduled yet or the machine family does not support advanced notices; host events can still occur.

## 17. Practice Exercises

### Exercise A — Reading a Policy

Given output:

~~~yaml
scheduling:
  onHostMaintenance: TERMINATE
  automaticRestart: true
  provisioningModel: STANDARD
~~~

**Questions:**

1. Is this live migration?
2. What differs between **TERMINATE + `automaticRestart=true`** and **MIGRATE**?
3. What happens to in-memory Java sessions and connection pools when the VM stops/restarts?
4. Why are backend health checks and backups still required?

**Hints:** (1) No; (2) the VM stops and reboots rather than transferring live execution state; (3) in-memory state is lost and connections must reconnect; (4) host policy does not replace application HA or data protection.

### Exercise B — Choosing Policy and Architecture

Consider three workloads:

- A Java payment API on standard VMs.
- An 8-hour GPU training job.
- A repeatable ETL pipeline on Spot VMs.

Select the maintenance policy, maintenance handling, backup/checkpointing, state placement, and alerting mechanism for each workload.

**Guided answer:** API uses MIGRATE where supported + MIG/multi-zone; GPU uses TERMINATE + durable checkpoints and window tracking; Spot uses preemption-tolerant design with scheduler retries rather than automatic VM restarts.

### Exercise C — Interpreting a Maintenance Notice

~~~json
{
  "canReschedule": false,
  "maintenanceStatus": "PENDING",
  "type": "SCHEDULED",
  "windowStartTime": "2026-12-10T18:00:00Z",
  "windowEndTime": "2026-12-10T22:00:00Z"
}
~~~

**Questions:**

1. Can you run **`perform-maintenance`** to trigger it early at your discretion?
2. What should you do if the workload does not support live migration?
3. Which timezone do these timestamps use, and who should be notified?

**Hints:** (1) No, `canReschedule=false`; (2) checkpoint, prepare for terminate/restart within the window, and ensure HA; (3) UTC timestamps—convert to the on-call team's timezone and notify stakeholders.

### Exercise D — Diagnosing an Incident

A standard VM with **MIGRATE + `automaticRestart=true`** emits the log:

~~~text
compute.instances.migrateOnHostMaintenance
~~~

Immediately afterward, the API shows a p99 latency spike and a few timeouts, with no fresh OS boot. Distinguish a **live migration brownout** from **backend overload**, explaining how to correlate System Events, app logs, metrics, load balancer health, and database connection pools.

**Guidance:** correlate timestamps, compare request rates, CPU/memory/network, VM uptime, and dependency errors. Never treat one migration log as sole proof for every anomaly. Tune timeouts/retries thoughtfully and validate with simulated maintenance in a lab.

### Exercise E — Designing a Maintenance Runbook

Write a checklist for a GPU VM showing **`canReschedule=true, PENDING`**, covering:

1. Confirming exact VM/project/zone and data retention thresholds.
2. Saving a checkpoint to durable storage.
3. Measuring real stop/start/recovery timings.
4. Picking an approved `perform-maintenance` execution time.
5. Monitoring, resuming the job, verifying outputs, and updating the incident/change record.

**Criteria:** never rely on Local SSD as the sole checkpoint location; include a rollback plan and explicit owner.

## 18. Key Takeaways and Reference Links

**Six core principles:**

1. **Live migration** keeps many VMs running during host maintenance **within the same zone**, yet never replaces HA architecture.
2. **MIGRATE** and **TERMINATE** define host maintenance handling; **`automaticRestart`** governs recovery after platform-initiated stops.
3. **GPUs, Spot, bare metal, and several specialized configurations** cannot live migrate; always read machine-series docs.
4. **`maintenance-event`** lets apps react right before an event; **`upcoming-maintenance`** aids early planning on supported machine types.
5. **`perform-maintenance`** only triggers an already notified event early when **`canReschedule=true/PENDING`**; it is not an arbitrary maintenance calendar for all VMs.
6. Measure **SLOs and real metrics**, and prepare backups/checkpoints, multi-instance/multi-zone redundancy, logging, runbooks, and recovery plans.

**Official Google Cloud documentation:**

1. [About host events](https://docs.cloud.google.com/compute/docs/instances/host-maintenance-overview) — maintenance, host errors, MIGRATE/TERMINATE, restart, and unsupported machines.
2. [Live migration process during maintenance events](https://docs.cloud.google.com/compute/docs/instances/live-migration-process) — live migration phases, blackout duration, and Local SSDs.
3. [Set the host maintenance policy for a compute instance](https://docs.cloud.google.com/compute/docs/instances/setting-vm-host-options) — scheduling fields and gcloud examples.
4. [gcloud compute instances set-scheduling](https://docs.cloud.google.com/sdk/gcloud/reference/compute/instances/set-scheduling) — syntax and state prerequisites for policy updates.
5. [Monitor and plan for a host maintenance event](https://docs.cloud.google.com/compute/docs/instances/monitor-plan-host-maintenance-event) — `upcomingMaintenance`, logs, and notification lead times.
6. [Query metadata server for maintenance notices](https://docs.cloud.google.com/compute/docs/metadata/getting-live-migration-notice) — `maintenance-event`, 60-second/60-minute notices, and `wait_for_change`.
7. [Manually start a host maintenance event](https://docs.cloud.google.com/compute/docs/instances/trigger-host-maintenance-event) — `perform-maintenance` within allowed windows.
8. [Simulate a host maintenance event](https://docs.cloud.google.com/compute/docs/instances/simulating-host-maintenance) — testing and metadata transitions.
9. [Handle GPU host maintenance events](https://docs.cloud.google.com/compute/docs/gpus/gpu-host-maintenance) — GPU termination, checkpointing, and Local SSDs.
10. [About graceful shutdown](https://docs.cloud.google.com/compute/docs/instances/graceful-shutdown-overview) — capabilities and limits.

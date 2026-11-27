# Safely Suspending, Resuming, Stopping, and Deleting VMs on Compute Engine

> **Chapter:** Compute Engine  
> **Module:** **CLOUD_PROVIDERS_GCP** — Exploring Google Cloud from project organization, IAM, and VPC to Compute Engine, GKE, Cloud Run, storage services, and databases. Through deployment scenarios, learners know how to select services, protect resources, automate releases, and track reliability and cost.

A Compute Engine VM running a Java application may need to pause outside business hours, stop for maintenance, resume days later, or be decommissioned after migrating the workload to Cloud Run or GKE. The four operations—**suspend, resume, stop, and delete**—look like simple management buttons, yet their consequences differ drastically for **RAM, disks, Local SSDs, IPs, OS state, SLAs, recoverability, and billing**.

What matters is not memorizing a command, but choosing **the right action for your data and business goal**, predicting which resources are preserved or released, and verifying the outcome. This lesson teaches how to design safe runbooks before touching live VMs.

## Learning Objectives

After this lesson, learners will be able to:

1. Distinguish **RUNNING, SUSPENDING, SUSPENDED, STOPPING, TERMINATED** and start/resume/delete operations.
2. Explain accurately what is preserved on **suspend** vs. **stop**, and what risks being lost on **delete**.
3. Understand suspend constraints such as the **60-day limit**, unsupported VM types, zonal capacity, and Local SSD handling.
4. Inventory boot disks, data disks, `autoDelete`, snapshots, backups, external IPs, service accounts, networking, and dependencies before changes.
5. Practice read-only **gcloud** commands and controlled command patterns for suspend/resume/stop/start/delete.
6. Design workflows for **graceful shutdown, backups, restore testing, approvals, and post-action verification**.
7. Analyze impacts on **Managed Instance Groups (MIGs)**, GKE nodes, Cloud Load Balancing, IAM, Cloud Monitoring, and billing.

## 1. Understanding the Compute Engine VM Lifecycle

A virtual machine is a Compute Engine resource bound to a **project and zone**, with a machine type, boot disk, optional additional disks, network interfaces, service account, metadata, and other properties. A VM typically transitions through states such as:

| State | Operational Meaning |
|---|---|
| **PROVISIONING** | Compute Engine is allocating resources |
| **STAGING** | Preparing to launch the VM |
| **RUNNING** | VM is running and can serve workloads if the OS and app are ready |
| **SUSPENDING** | Saving RAM, device, and application state for suspend |
| **SUSPENDED** | Suspended with RAM state saved; not actively processing requests |
| **STOPPING** | Stopping or shutting down |
| **TERMINATED** | VM is stopped; VM resource remains so it can be started again if supported |
| **REPAIRING** | Platform is performing a repair action; lifecycle operations may be restricted |

**TERMINATED** means the VM is **stopped**, not **deleted**. Once deletion completes, the VM no longer exists to describe or start under that resource.

~~~mermaid
stateDiagram-v2
    [*] --> PROVISIONING: Create
    PROVISIONING --> STAGING
    STAGING --> RUNNING
    RUNNING --> SUSPENDING: Suspend
    SUSPENDING --> SUSPENDED
    SUSPENDED --> PROVISIONING: Resume
    RUNNING --> STOPPING: Stop
    STOPPING --> TERMINATED
    TERMINATED --> PROVISIONING: Start
    SUSPENDED --> TERMINATED: After up to 60 days
    RUNNING --> [*]: Delete
    SUSPENDED --> [*]: Delete
    TERMINATED --> [*]: Delete
~~~

This diagram simplifies the core states; start and resume flows also traverse STAGING and transitional states. A **RUNNING** status does not prove the application is ready: a JVM might still be booting, waiting on a database, or failing health checks.

### 1.1. Operations Are Not Interchangeable

- **Suspend:** preserves RAM and device/application state in persistent storage, then releases compute resources.
- **Resume:** returns a **SUSPENDED** VM to running state, restoring RAM from saved state if still valid and zonal capacity exists.
- **Stop:** shuts down the VM **without preserving RAM state** to resume mid-execution; VM config and persistent disks can remain.
- **Start:** boots a **TERMINATED** VM, starting the OS and applications afresh.
- **Delete:** removes the VM resource; whether disks and ancillary resources remain depends on configuration and deletion flags.
- **Reset:** equivalent to pressing a hard reset button rather than a clean stop; risks losing unflushed in-memory data.
- **Reboot inside guest OS:** restarts within the operating system; never equivalent to Compute Engine suspend.

To **suspend**, never run **`systemctl suspend`** inside the guest OS expecting Compute Engine to manage that state. Use the Console, `gcloud compute instances suspend`, or the platform API.

## 2. Choosing Suspend, Stop, or Delete?

| Need | Appropriate Action | Why |
|---|---|---|
| Pause a desktop/dev VM overnight while keeping IDE/RAM sessions | **Suspend**, if VM qualifies | Can resume work close to prior state |
| Shut down a test VM off-hours where normal reboot is fine | **Stop** | Avoids paying for RAM state storage |
| Change machine type or perform maintenance needing shutdown | **Stop → update → Start**, if VM type allows | Certain edits require a stopped VM |
| Retire VM from service while keeping data and config for inspection | **Stop** before considering delete | Allows verifying dependencies and recovery |
| VM no longer needed, but data must be preserved | **Backup/snapshot + Delete VM with explicit disk retention** | Removes compute without accidentally wiping data |
| End of lifecycle, data handled per retention policy | **Delete** after approval | Cleanly removes VM and unneeded resources |
| JVM hung, need to restore service | **Inspect app → graceful restart/stop → reset only as last resort** | Reset is never the first safe option |
| Workload running inside a Managed Instance Group | **Act via MIG / desired state** | MIG may recreate deleted or stopped VMs |
| GKE node in a node pool | **Manage via GKE**, never ad-hoc stop/delete the node VM | Kubernetes/GKE runs its own controllers |

**No single action optimizes every criterion.** Suspend keeps app sessions yet does not guarantee live network sockets survive, instant resume capacity, or valid DB connections. Stop avoids RAM storage fees but requires booting anew. Delete is only safe once disk policies and dependencies are clear.

## 3. Which Data Is Preserved and Which Can Be Lost?

### 3.1. RAM, Device State, and Application State

When suspend is supported, Compute Engine saves **guest OS memory, device state, and application state** to persistent storage for resumption. That is the core difference from stop.

After **stop/start**, programs boot from scratch. JVM in-memory sessions, in-RAM caches, in-process queues, and uncommitted transactions are gone. Java apps need shutdown hooks, safe job replay, connection retries, and durable state persistence.

After **suspend/resume**, RAM is restored, yet **external connections, DNS caches, expired tokens, TLS sessions, and stale connection pools** may be invalid. Never assume resume seamlessly continues all network activity without reconnecting.

### 3.2. Boot Disk and Data Disks

The boot disk is typically a Persistent Disk or Hyperdisk supported by the machine family, optionally paired with persistent data disks. During **stop or suspend**, persistent disks attached to the VM normally remain intact and continue accruing storage charges.

On **delete**, each disk has an **`autoDelete`** property or keep/delete selection at deletion time. Typically, **boot disks default to `autoDelete=true`**, meaning they are deleted alongside the VM. Every data disk must be **checked individually**—never assume from the boot disk or the word "data" in its name.

| Storage Type | Suspend | Stop | Delete VM |
|---|---|---|---|
| **Persistent boot disk** | Normally retained | Normally retained | Can be **deleted** per `autoDelete` / delete flags |
| **Persistent data disk** | Normally retained | Normally retained | Depends on `autoDelete` / keep/delete flags |
| **RAM/device/app state** | Saved for resume where supported | Not preserved | Lost |
| **Local SSD** | Discarded by default; limited/pre-GA preserve option | Discarded by default; limited/pre-GA preserve option | Not retained independently on VM delete |
| **Separately taken snapshots/backups** | Unaffected by suspend | Unaffected by stop | Persist independently per retention policy |

**Snapshots are not synonymous with complete backups:** a single-disk snapshot does not guarantee multi-disk or database transactional consistency without quiescing, freezing, or application-consistent backups. For production databases, use native database backups and practice restores.

### 3.3. Local SSDs Are High-Risk Cases

**Local SSDs** deliver high performance, yet their data is tied to host/VM lifecycle and **they are not persistent disks**. Under current documentation:

- **Stop or suspend discards Local SSD data by default**, leaving Local SSDs blank when the VM starts again.
- **Options to preserve Local SSD data during stop/suspend** exist in certain scenarios, but remain **Preview/pre-GA** with limits on disk types, counts, and tools.
- Never rely on default Google Cloud Console preservation behavior; some preserve workflows work only via `gcloud`/API with explicit flags.
- **Titanium SSDs** and unsupported shapes carry separate constraints; consult machine-family documentation.
- If data on a Local SSD matters, **copy/back it up to persistent storage first** before stopping, suspending, or deleting.

Never keep non-reproducible application data solely on Local SSD while relying on a Preview flag as your sole recovery plan.

### 3.4. IPs, Networking, and Service Accounts

During stop/suspend, a VM generally retains its network interface config, MAC address, internal IP, and attached **static external IPs** where supported; **ephemeral external IPs can be released**.

Practical consequences:

- After resume/start, public endpoints can change if the VM previously used an ephemeral external IP.
- If apps depend on fixed IPs, use reserved static IPs or load balancers/DNS with safe cutovers.
- Even while a static IP remains reserved, it may **continue incurring charges**.
- Maintain proper labels, network tags, and service accounts; post-start access remains governed by current IAM and firewalls.
- If the VM sits in a load balancer backend pool, it is marked unhealthy whenever not `RUNNING`.

### 3.5. Retention Summary

| Aspect | Suspend / Resume | Stop / Start | Delete |
|---|---|---|---|
| VM resource/name/config | Retained | Retained | Removed |
| RAM/application state | Conditionally saved within time limit | Not retained | Lost |
| Persistent disks | Normally retained and billed | Normally retained and billed | Must choose keep vs. delete |
| Local SSD contents | Not retained by default; conditional Preview | Not retained by default; conditional Preview | Not retained |
| Ephemeral external IP | Can be released | Can be released | Released per config |
| Static external IP | Remains attached/billed | Remains attached/billed | Verify if released or reassigned |
| VM vCPU/memory runtime fees | Stop after suspend completes | Stop after stop completes | Stop after deletion |
| RAM state storage fees | Can accrue | No suspend state storage needed | Gone once state is dropped |
| Workload restart | Must verify app after resume | Boots OS and app from scratch | Create new VM / restore as needed |
| Reversible? | Resume within valid window | Start if capacity and config remain | No VM delete undo; requires rebuild/restore |

## 4. Suspend Has Limits and Is Not a Backup

### 4.1. The 60-Day Maximum Rule

A VM can remain **`SUSPENDED` for up to 60 days**. Afterward, Compute Engine transitions it to **`TERMINATED`**; **saved RAM, device, and application state are discarded and cannot be resumed**. Persistent disk data follows disk lifecycle rules, yet you must **start** and boot the application as if after a stop.

Therefore:

- Suspend is unsuitable for "keeping an open desktop alive for six months."
- For long-term session persistence, store state in durable databases/storage or appropriate snapshots.
- Track VMs approaching the limit; never let an unexpected transition catch you expecting RAM to survive.

### 4.2. Unsupported VMs and Special Conditions

Depending on service version, machine type, and OS, suspend may be rejected. Per Google Cloud docs, notable exclusions include:

- **Bare metal instances**.
- **Confidential VMs**.
- VMs with **GPUs or TPUs**.
- VMs with **more than 208 GB RAM**.
- VMs using **CSEK**-encrypted disks in unsupported configurations.
- Unsupported guest OSes or OSes needing extra configuration; docs note Windows and older Debian releases among constraints.
- Insufficient **Persistent Disk Standard quota** to store RAM/state, even if the VM uses another disk tier.
- VM not in the **`RUNNING`** state when suspend is requested.

Some Spot/preemptible VMs can be suspended, yet remain subject to preemption during transitions. Never use suspend hoping to lock a Spot VM against reclamation.

### 4.3. Resume Depends on Zonal Capacity

Suspending returns compute capacity to the zone's pool. Resuming requires the zone to have **sufficient available capacity** or a matching reservation. If capacity is tight, resume can **fail while leaving the VM `SUSPENDED`**. This is not necessarily data loss; resolve availability/quota/capacity and retry per docs—never delete the VM to "fix" it.

### 4.4. Suspend Is Not Ad-Hoc Guest OS Hibernation

Compute Engine orchestrates saving RAM and device state. Sleep or hibernation triggered solely **inside the guest OS** does not register as Compute Engine infrastructure suspend. Use only the Console, `gcloud`, or supported REST APIs.

## 5. Costs: Stop/Suspend Cut Compute, Not the Entire Bill

A very common misconception is **"turning off a VM means zero cost."** When a VM is stopped or suspended, active CPU/RAM runtime charges stop after the transition, yet **persistent storage, static IPs, and related resources** continue billing.

| Cost Item | RUNNING | SUSPENDED | TERMINATED (stopped) | After DELETE |
|---|---|---|---|---|
| Running vCPU/guest RAM | Billed per machine/pricing | Running compute stops | Running compute stops | No VM compute fees |
| Persistent disks/Hyperdisk | Billed | Continues | Continues | Continues if disks kept |
| RAM/device suspend state storage | Not applicable | Billed for applicable storage | No suspend state stored | Gone |
| Static external IPv4 or billable IPs | Depends on type/usage | Can continue | Can continue | Continues if still reserved |
| Local SSD data preservation | Depends on config | Storage charges if Preview enabled | Storage charges if Preview enabled | Not retained with VM |
| Snapshots/backups | Billed by stored bytes | Continues | Continues | Continues if retained |
| Reservations/commitments | Per contract/config | Not auto-canceled | Not auto-canceled | Not canceled merely by deleting VMs |
| Sole-tenant nodes or shared hosts | Billed separately | May continue | May continue | May continue |

**Illustrative estimate** (not list pricing): a dev VM assumes 20 units/day compute, 3 units/day disks, and 1 unit/day static IP/misc. Stopping for 10 days avoids the 200 compute units, while disks/IP still generate roughly 40 units in this model. Suspend adds RAM state storage fees. Actual bills also depend on region, machine type, CUDs, IPv4 pricing, OS licenses, storage, commitments, reservations, and Billing account terms.

### 5.1. Why You Cannot Assume "VM Deleted = 100% Savings"

Deleting a VM does not automatically remove:

- Disks explicitly set to **keep**.
- Independent snapshots/backups.
- Unreleased reserved external IPs.
- Unmodified reservations.
- Active **Committed Use Discounts**.
- Sole-tenant nodes or other shared resources.
- Cloud Logging retention or external app resources.

To verify real savings, inspect **Cloud Billing Reports by Service/SKU and project**, cross-checking the **Cost table** at billing close. Billing metrics lag, so never judge cost savings a few minutes after deletion.

## 6. Preflight: Investigating a VM Before Pressing Any Button

A stop, suspend, or delete action is only safe once you have evidence answering:

1. **Right VM?** Do project ID, zone, VM name, and resource ID match the ticket?
2. **Who owns it?** Labels, team, application, dev/staging/prod environment, and approver?
3. **What workload runs inside?** Java processes, databases, batch jobs, queue consumers, cron, live traffic?
4. **What dependencies exist?** Load balancer backends, Managed Instance Groups, DNS, private IPs, Cloud SQL, GKE, Cloud Run connectors, firewalls, hybrid VPNs?
5. **Which disks are affected?** Boot/data disk names, `autoDelete`, disk types, Local SSDs, encryption keys?
6. **Are backups needed?** Snapshots and app/DB backups, retention policies, and tested restores?
7. **Is it reversible?** Start/resume path, IaC recreation, disk restore, DNS/traffic rollback?
8. **Who has permissions?** Least-privilege IAM roles/permissions, access to CMEK/CSEK keys if used?
9. **When is downtime allowed?** Maintenance window, SLO/SLA, alert recipients, communications plan?
10. **What is the expected outcome?** How will API state, health checks, data, and costs be verified afterward?

~~~mermaid
flowchart TD
    Q["Request to cut cost / stop VM"] --> ID["Verify project/zone/owner/workload"]
    ID --> DEP["Check traffic, MIG/GKE, networking, and disks"]
    DEP --> DATA{"Need to preserve RAM?"}
    DATA -- "Yes" --> SUS{"Suspend supported and under 60 days?"}
    SUS -- "Yes" --> S["Controlled Suspend"]
    SUS -- "No" --> SAVE["Flush state/backup then choose stop"]
    DATA -- "No" --> KEEP{"Need to keep VM resource?"}
    KEEP -- "Yes" --> STOP["Controlled Stop"]
    KEEP -- "No" --> RET["Retention, backups, autoDelete, approvals"]
    RET --> DEL["Controlled Delete"]
    SAVE --> STOP
    S --> VER["Verify status + app + billing"]
    STOP --> VER
    DEL --> VER
~~~

There is no rule saying "any VM with `test` in its name is safe to delete." Names go stale, labels lie, and instances silently serve critical tasks. In production, verify **dependencies and data** across multiple signals, never by name alone.

## 7. Hands-On 1 — Read-Only Inventory with gcloud

Commands in this section **make zero infrastructure changes**. Ensure you are authenticated in `gcloud` with Compute Engine read access and the right project/zone. Never inspect another team's VMs indiscriminately just because you hold broad project permissions.

### 7.1. Verifying Identity, Project, and VM

~~~bash
# Read-only: active gcloud identity and configured project.
gcloud auth list
gcloud config list project

# REPLACE with authorized project/zone and VM name.
PROJECT_ID="my-training-project"
ZONE="asia-southeast1-a"
VM="java-dev-vm"

# List VMs and states in the project without changing anything.
gcloud compute instances list \
  --project="$PROJECT_ID" \
  --format="table(name,zone,status,machineType)"

# Describe one specific VM.
gcloud compute instances describe "$VM" \
  --project="$PROJECT_ID" \
  --zone="$ZONE" \
  --format="yaml(name,id,status,zone,machineType,labels,deletionProtection)"
~~~

**Note:** **`status=TERMINATED`** usually means the VM is stopped. An absent VM in `list` could mean deleted, wrong project, insufficient permissions, or active filters—verify before concluding. Resource **`id`** distinguishes an old deleted VM from a newly created one reusing the same name.

### 7.2. Inventorying Disks and `autoDelete`

~~~bash
# Read VM disk attachments: disk source, boot/data, autoDelete.
gcloud compute instances describe "$VM" \
  --project="$PROJECT_ID" --zone="$ZONE" \
  --format="yaml(disks)"

# Persistent disks in the lab zone.
gcloud compute disks list \
  --project="$PROJECT_ID" \
  --filter="zone:$ZONE" \
  --format="table(name,zone,type,sizeGb,status,users)"

# Inspect a specific disk from the output if authorized.
gcloud compute disks describe "DISK_NAME" \
  --project="$PROJECT_ID" --zone="$ZONE" \
  --format="yaml(name,type,sizeGb,users,labels)"
~~~

From **VM disk attachments**, tabulate:

| Field | What to Record |
|---|---|
| Device/source | Disk resource name and zone |
| **`boot`** | Boot disk vs. data disk |
| **`autoDelete`** | Whether it deletes automatically on VM delete |
| Disk type/size | Persistent Disk, Hyperdisk, or equivalent |
| Encryption | Google-managed key, CMEK, CSEK, or other |
| Business data | DB, user uploads, artifacts, cache, or reproducible data |
| Backups | Snapshot/backup IDs, timestamps, and restore test status |

If the VM has Local SSDs, verify disk types and mount paths inside the guest OS. Disk metadata only describes block devices—it does not prove the application flushed all buffered writes to disk.

### 7.3. Checking Networking, IPs, Service Account, and Deletion Protection

~~~bash
gcloud compute instances describe "$VM" \
  --project="$PROJECT_ID" --zone="$ZONE" \
  --format="yaml(networkInterfaces,serviceAccounts,tags,metadata,deletionProtection,scheduling)"

# Read-only check of existing snapshots in the project.
gcloud compute snapshots list \
  --project="$PROJECT_ID" \
  --format="table(name,creationTimestamp,status,sourceDisk)"
~~~

Never print credentials, tokens, encryption keys, or secrets to logs. **Metadata** may contain sensitive config strings; share only redacted excerpts in audit tickets. For CMEK/CSEK disks, confirm key access before starting or restoring disks.

### 7.4. Checking Workload Activity Before Stopping

Beyond VM metadata, operators must inspect:

- **Cloud Monitoring**: CPU, network, disk I/O, request rates, traffic, errors.
- **Load balancers**: is the instance in a backend pool receiving live traffic?
- **Managed Instance Groups**: is the VM managed by an autoscaling/autohealing controller?
- **Cloud Logging / Audit Logs**: recent errors, lifecycle events, config edits.
- **IaC / CI/CD**: is the VM in Terraform state, startup scripts, or active pipelines?
- **Application**: is the JVM serving requests, running cron jobs, consuming queues, or writing data?

Never mistake low CPU for "idle and unused": a VM could be waiting on events, holding queue leases, acting as a warm standby, or running scheduled batches.

## 8. Hands-On 2 — Controlled Suspend and Resume

**Scenario:** a Java dev workstation used during daytime needing to preserve JVM/debugging sessions overnight. Use suspend only if the VM qualifies, no uninterruptible workload runs on it, and resumption will happen well within 60 days.

### 8.1. Suspend-Specific Preflight

Before running:

1. VM is **`RUNNING`**; critical data has snapshots/backups.
2. Guest OS/machine type qualifies—not GPU/TPU, Confidential VM, bare metal, or over RAM limit.
3. No unbacked-up Local SSD dependency; if Local SSD exists, understand discard/preserve rules.
4. Sufficient Persistent Disk Standard quota exists to store RAM/state.
5. Application tolerates dropped connections; pools reconnect cleanly on resume.
6. Zone likely has capacity upon resume, with a fallback plan if capacity runs tight.
7. Recorded suspend timestamp, owner, and <60-day reminder deadline.

### 8.2. Suspend Command

~~~bash
# MUTATES LIVE STATE.
# Run only after owner approval and eligibility checks.
gcloud compute instances suspend "$VM" \
  --project="$PROJECT_ID" \
  --zone="$ZONE"

# READ-ONLY — verify status after operation.
gcloud compute instances describe "$VM" \
  --project="$PROJECT_ID" --zone="$ZONE" \
  --format="value(status)"
~~~

Wait for **`SUSPENDED`**; never assume completion right when the CLI accepts the API call. Large-RAM VMs take longer to serialize memory. Never reset or delete a VM mid-suspend merely because the command takes time.

If the VM has Local SSDs, **explicitly specify discard or preserve** per machine/SDK support. Example discarding Local SSD data:

~~~bash
# ILLUSTRATIVE ONLY FOR VMs WITH LOCAL SSDs.
# IMPACT: all Local SSD data may be permanently lost.
gcloud compute instances suspend "$VM" \
  --project="$PROJECT_ID" --zone="$ZONE" \
  --discard-local-ssd=true
~~~

Never run this example if Local SSD holds important data. Preserving Local SSDs via **`--discard-local-ssd=false`** in `gcloud beta` is **Preview** and restricted to specific setups. Unless you fully understand its constraints and recovery behavior, copy data to Persistent Disk/Cloud Storage and use stable supported methods.

### 8.3. Resume Command

~~~bash
# MUTATES LIVE STATE.
gcloud compute instances resume "$VM" \
  --project="$PROJECT_ID" \
  --zone="$ZONE"

# READ-ONLY — verify VM is RUNNING.
gcloud compute instances describe "$VM" \
  --project="$PROJECT_ID" --zone="$ZONE" \
  --format="yaml(name,status,networkInterfaces)"
~~~

Resume works only on **`SUSPENDED`** VMs. If a VM automatically transitioned to **`TERMINATED`** after the 60-day cap, you must use **`start`** instead of resume, and **RAM state is gone**.

### 8.4. Post-Resume Verification

- VM returns to **`RUNNING`** and Java app passes health checks.
- Verify JVM processes, thread pools, and schedulers.
- Reconnect DB, Pub/Sub, Redis/Memorystore, Cloud SQL, and Secret Manager per client libraries.
- Refresh expired access/ID tokens and re-establish TLS sessions as needed.
- Verify ephemeral external IPs, DNS caches, and load balancer membership.
- Observe latency, error rates, and network traffic until steady state stabilizes.
- If the zone lacks capacity to resume, follow the runbook—never panic-delete the VM.

**Restoring RAM does not replace business-level durability.** An in-flight request during suspend may time out client-side and retry after resume. Services need idempotency for payments and state-mutating writes.

## 9. Hands-On 3 — Safe Stop and Start

Stop fits when you want to **retain the VM and persistent disks** without preserving RAM state—for example, a batch VM running business hours only, or stopping to change machine type.

### 9.1. Graceful Shutdown Is Shared Responsibility Between App and Infra

Before stopping:

- Stop accepting new traffic: drain backends from routing or enable app draining mode.
- Finish or checkpoint long-running batch jobs.
- Stop queue consumers from pulling new work; verify in-flight messages are acked or retryable.
- Flush write buffers and commit open transactions; never leave sole data in RAM.
- Where appropriate, use a **`shutdown-script`** with bounded timeout to notify or clean up resources.
- Check graceful shutdown timeout settings for the VM type; exceeding timeout forces termination.

In Java, a **shutdown hook** helps close connection pools cleanly, yet hooks are not guaranteed on every failure (host crash, power loss, `kill -9`). Data persistence must survive sudden stops.

### 9.2. Stop Command

~~~bash
# MUTATING — requests standard graceful stop.
gcloud compute instances stop "$VM" \
  --project="$PROJECT_ID" \
  --zone="$ZONE"

# READ-ONLY — verify expected stopped state.
gcloud compute instances describe "$VM" \
  --project="$PROJECT_ID" --zone="$ZONE" \
  --format="value(status)"
~~~

Expected final state is **`TERMINATED`**. Never use **`--no-graceful-shutdown`** by default: it skips or cuts short orderly shutdown, risking unflushed data loss. Use it only with approval and full awareness of app state.

If the VM has Local SSDs:

~~~bash
# MUTATING — IMPACT: discards Local SSD data on stop.
gcloud compute instances stop "$VM" \
  --project="$PROJECT_ID" --zone="$ZONE" \
  --discard-local-ssd=true
~~~

Per docs, when Local SSDs are attached you must declare whether to discard them. Preserving Local SSDs on stop via `false` may be limited to **`gcloud beta`** Preview; never treat it as a backup.

### 9.3. Start Command

~~~bash
# MUTATING — boots OS and applications from scratch.
gcloud compute instances start "$VM" \
  --project="$PROJECT_ID" \
  --zone="$ZONE"

# READ-ONLY — inspect status, IPs, and attached disks.
gcloud compute instances describe "$VM" \
  --project="$PROJECT_ID" --zone="$ZONE" \
  --format="yaml(status,networkInterfaces,disks)"
~~~

Start works from **`TERMINATED`**; it does not restore RAM from `SUSPENDED`. For disks with custom encryption keys, key permissions and key parameters may be required before starting.

### 9.4. Post-Start Verification

| Component | What to Verify |
|---|---|
| VM | `RUNNING`, expected machine type/zone/labels |
| Disks | Boot/data disks attached, mount points, filesystems, data integrity |
| Network | VPC, subnet, IPs, DNS, firewalls, routes, VPN/Interconnect |
| Application | JVM/service started, health/readiness passing, logs free of fatal errors |
| Database | Connections healthy, zero migration/transaction errors |
| Queue/batch | Retries/idempotency intact, no duplicate work |
| IAM and secrets | Runtime service account has least privilege, token refresh works |
| Monitoring | Traffic, CPU, error rate, alerts, and SLOs recovered |

If start fails due to **quota/capacity/availability**, that is not justification to delete disks or force cross-zone moves without a proper migration plan.

## 10. Deleting VMs Safely: Sequence Matters More Than the Command

**Delete is a high-risk operation** because the VM resource vanishes and boot/data disks may be deleted depending on configuration. Never treat it as a "cheaper stop" without explicit decisions on data, dependencies, and backups.

### 10.1. Pre-Delete Runbook

1. **Verify exact target:** project ID, zone, VM name, resource ID, and environment.
2. **Owner sign-off:** data, operations, and security approvals as required.
3. **Drain traffic:** remove endpoint from load balancers/DNS or reroute cleanly.
4. **Assess dependencies:** schedulers, queues, IAM, service accounts, Cloud SQL, storage, VPC firewalls, monitoring, backups.
5. **Inventory disks:** every boot/data disk, `autoDelete`, Local SSDs, snapshots/backups; decide explicitly which disks to **keep** vs. **delete**.
6. **Back up and test restore:** prefer application-consistent backups; verify snapshot/backup completion and test restoration.
7. **Retention check:** verify compliance retention, holds/locks, and sensitive data sanitization rules.
8. **Identities and IPs:** identify static external IPs, reserved addresses, DNS names, URLs, certificates, and references to update.
9. **IAM and IaC:** update source IaC so controllers/pipelines do not recreate the VM; log operator and ticket.
10. **Execute safely:** avoid bulk deletions or `--quiet` without guardrails; wait for API completion.
11. **Post-check:** confirm VM is gone, disks/IPs/snapshots match plan, and monitoring/billing are updated.

### 10.2. Deletion Protection

Compute Engine offers **`deletionProtection`** to prevent accidental VM deletion. It can be set at creation or updated with appropriate permissions. However:

- Deletion protection **does not block stop, reset, or suspend**.
- **Deletion protection is not supported on VMs inside a Managed Instance Group**.
- It is not absolute protection against project deletion or broader actions.
- Anyone authorized to update `deletionProtection` can turn it off, so least-privilege IAM, approvals, and audit logs remain essential.

~~~bash
# READ-ONLY — check deletion protection before deleting.
gcloud compute instances describe "$VM" \
  --project="$PROJECT_ID" --zone="$ZONE" \
  --format="yaml(name,id,status,deletionProtection,disks)"
~~~

If **`true`**, never blindly disable it just to force a delete command through. Verify whether it was placed intentionally as a guardrail requiring separate approval.

### 10.3. `autoDelete` on Boot and Data Disks

Suppose a VM has these disks:

| Disk | Role | Observed `autoDelete` | Decision on Delete |
|---|---|---|---|
| boot-java-dev | Operating system | true | Can delete if image/IaC and needed data are preserved |
| user-workspace | Developer source/data | false | Keep and verify backup |
| scratch-cache | Reproducible cache | true | Can delete after confirmation |
| Local SSD | Scratch/temp | Not a persistent disk | Lost with VM lifecycle; copy needed data beforehand |

**`autoDelete` is evaluated on the instance's disk attachment.** Failing to check it can wipe a boot disk holding unbacked-up config or a data disk someone left with `autoDelete=true`.

### 10.4. Delete Command with Explicit Disk Retention

For an authorized dev VM teardown where **all persistent disks must be kept** for later review:

~~~bash
# SEVERE IMPACT: DELETES VM.
# Run only after checklist/approvals/backups PASS.
# --keep-disks=all preserves attached persistent boot and data disks;
# does NOT preserve RAM or Local SSDs.
gcloud compute instances delete "$VM" \
  --project="$PROJECT_ID" \
  --zone="$ZONE" \
  --keep-disks=all
~~~

The command prompts for confirmation by default; **do not add `--quiet`** in runbooks so a basic safeguard remains intact. **`--keep-disks`** accepts **`all`**, **`boot`**, or **`data`** as needed. If disks should also be deleted, decide explicitly and inspect `autoDelete`/disk deletion policies rather than guessing.

**Keeping a disk does not replace an independent backup.** An orphaned disk can still be deleted accidentally later or hit corruption; keep separate snapshots/backups and verify restores.

### 10.5. Post-Delete Verification

~~~bash
# READ-ONLY — VM must no longer appear in the list.
gcloud compute instances list \
  --project="$PROJECT_ID" \
  --filter="name=$VM"

# READ-ONLY — confirm retained disks match plan.
gcloud compute disks list \
  --project="$PROJECT_ID" \
  --format="table(name,zone,status,users)"

# READ-ONLY — inspect reserved addresses if any.
gcloud compute addresses list \
  --project="$PROJECT_ID"

# READ-ONLY — inspect retained snapshots.
gcloud compute snapshots list \
  --project="$PROJECT_ID"
~~~

If the VM disappears from `list`, verify the API operation finished in the right project/zone and no Managed Instance Group or pipeline recreated it. For any retained disks, document **owner, retention deadline, backup location, and ongoing charges**.

## 11. Backups, Snapshots, and Real Recoverability

### 11.1. What Do Snapshots Provide?

Snapshots capture disk data via Persistent Disk/Hyperdisk mechanisms, valuable when you need to:

- Preserve data before maintenance or VM deletion.
- Create new test disks from a snapshot.
- Recover after VM deletion when paired with configuration/IaC.

Snapshots do not automatically capture network configs, IAM roles, service account permissions, external startup scripts, or application dependency topology. For multi-disk setups and databases, design **application-consistent backups**; standalone snapshots may only be crash-consistent depending on write state.

### 11.2. Example: Snapshotting a Boot or Data Disk

~~~bash
# MUTATING — creates a snapshot incurring storage fees.
# Run only after verifying exact disk, permissions, and backup policy.
DISK_NAME="user-workspace"
SNAPSHOT_NAME="workspace-before-decommission-20261119"

gcloud compute disks snapshot "$DISK_NAME" \
  --project="$PROJECT_ID" \
  --zone="$ZONE" \
  --snapshot-names="$SNAPSHOT_NAME"

# READ-ONLY — confirm snapshot completed.
gcloud compute snapshots describe "$SNAPSHOT_NAME" \
  --project="$PROJECT_ID" \
  --format="yaml(name,status,sourceDisk,creationTimestamp)"
~~~

When snapshotting a running VM, coordinate app quiescing/flushing and operational policies. For strict RPO/RTO workloads, use purpose-built database or storage backups rather than treating ad-hoc snapshots as complete backups.

### 11.3. Restore Drills Are the True Proof

Verification flow:

1. Pick a completed, non-expired snapshot/backup.
2. Create a **test disk** from the snapshot in an appropriate zone/region.
3. Attach it to an **isolated recovery VM** with proper permissions, or launch a new VM from a boot disk where supported.
4. Verify filesystems, checksums/data samples, Java apps, or databases in a safe mode.
5. Compare actual recovery time against **RTO**, and latest data timestamp against **RPO**.
6. Ensure the restored VM never hits production endpoints, publishes duplicate messages, or overwrites live databases.
7. Record test evidence and clean up test recovery resources cleanly.

**An untested backup is not proven recoverability.** When deleting disks is risky, a restore drill is worth far more than a "snapshot created" status line.

## 12. VMs Managed by MIGs, GKE, or Special Provisioning Models

Not every VM listed under **Compute Engine → VM instances** should be managed directly. Before any lifecycle action, identify **who owns the VM's control loop**.

### 12.1. Managed Instance Groups (MIGs)

A **Managed Instance Group** manages VMs via instance templates, target sizes, autoscaling, autohealing, and rolling updates. If a member VM is stopped or deleted out of band, **the MIG may recreate or reconcile it back to target state**, nullifying cost cuts or causing churn.

Scenarios:

- Need fewer VMs serving: adjust **autoscaler / min-size / target-size** through the MIG.
- Need maintenance/rolling updates: use MIG update/repair controls.
- Need a **stopped/suspended pool**: use MIG standby pools where supported by MIG type rather than stopping random instances.
- In **regional MIGs**, mind `targetDistributionShape` and redistribution rules when stopping/suspending specific instances.
- For stateful MIGs, verify **preserved state** for disks/IPs rather than assuming standalone VM behavior.

**Deletion protection cannot be applied to VMs belonging to a MIG** per Compute Engine docs. Guardrails must live in IAM, pipelines, MIG configuration, and approval workflows.

### 12.2. GKE Nodes Are Not App-Managed Standalone VMs

GKE nodes run on Compute Engine yet are controlled by **GKE node pools, autoscalers, and upgrade controllers**. If an operator manually stops or deletes a node VM:

- Pods lose their host and are rescheduled elsewhere if cluster capacity allows.
- PodDisruptionBudgets, graceful drains, and termination periods may be bypassed or stressed.
- Controllers may repair or replace the node automatically.
- Ephemeral local node data may be lost.
- App SLOs can degrade even though the goal was saving Compute Engine spend.

To resize GKE capacity, use **GKE node pool, autoscaling, and maintenance** controls. Never run `gcloud compute instances delete` on an active cluster node merely because its name shows up in the VM list.

### 12.3. Spot, Preemptible, GPU, TPU, Confidential, and Sole-Tenant

| VM Type | What to Check Before Lifecycle Actions |
|---|---|
| **Spot/preemptible** | Can be preempted; restart/preemption handling and scratch data must align |
| **GPU/TPU** | Suspend may be unsupported; stop/start requires verifying capacity and quotas |
| **Confidential VM** | Suspend is unsupported per current documentation |
| **Bare metal** | Suspend is unsupported |
| **High-memory VMs** | Over 208 GB RAM is unsupported for suspend per reviewed documentation |
| **Sole-tenant VM** | Stopping/deleting VMs may not stop sole-tenant physical node charges |
| **Reservation-bound/committed workload** | Stopping/deleting one VM does not cancel reservations or commitments |
| **VM with Local SSDs** | Data discarded by default on stop/suspend; preserve features have limits |
| **VM with custom encryption keys** | Start/restore may require active keys and key-use permissions |

Preview limits and capabilities evolve across releases. For specialized machine types, verify official docs and test on non-critical VMs before codifying into production runbooks.

## 13. IAM, Auditing, Automation, and Lifecycle Policies

### 13.1. Least-Privilege Action Permissions

Representative Compute Engine permissions:

| Action | Commonly Involved IAM Permission |
|---|---|
| View VMs | **`compute.instances.get`**, **`compute.instances.list`** |
| Suspend | **`compute.instances.suspend`** |
| Resume | **`compute.instances.resume`** |
| Stop | **`compute.instances.stop`** |
| Start | **`compute.instances.start`** |
| Delete | **`compute.instances.delete`** |
| Toggle deletion protection | **`compute.instances.update`** or matching API permission |
| Create/read snapshots | **`compute.disks.createSnapshot`**, corresponding snapshot perms |
| Standalone disk actions | Permissions on disks, snapshots, regions/zones, and dependencies |

Broad roles like **`roles/compute.instanceAdmin.v1`** bundle many VM admin actions; prefer custom roles, tighter project/VM scoping, and IAM Conditions per policy. Backup/restore operators also need snapshot/storage/key permissions. Never grant **Owner** to an automation pipeline just to suspend VMs.

### 13.2. Audit Logs and Operator Attribution

For stop, suspend, resume, delete, or deletion-protection changes, preserve evidence:

- **Who** requested it: user or service account.
- **When**: UTC timestamp, project, zone, and instance ID.
- **Why**: ticket, change request, environment, owner.
- **Result**: operation ID, status, any errors, state transition timestamps.
- **Data**: disk keep/delete choices, snapshot IDs, retention, and restore drill results.
- **Health**: post-change health checks, monitoring, and billing review.

**Cloud Audit Logs** provide the authoritative trail for API actions; correlate with PR/IaC history to see who modified templates or deployments. Avoid logging sensitive strings or credentials.

### 13.3. Cost-Saving Automation Requires Guardrails

You can use Cloud Scheduler with Cloud Run/Workflows or IaC to **auto-stop/start dev VMs outside working hours**. Minimum safety guardrails:

1. Fixed scope: **explicit project and zone allowlist**, never sweeping an entire org by default.
2. Controlled labels such as **`lifecycle=schedulable`**, **`environment=development`**, **`owner=...`**.
3. A **dry-run/report** stage before execution, showing exact VM IDs and planned actions.
4. Exclude MIG/GKE VMs and production unless explicitly architected for it.
5. Check safe workload stop readiness, backups, and Local SSDs.
6. Support **opt-outs/exceptions**, manual overrides, and expiration dates.
7. Run under a least-privilege service account.
8. Alert on stop/start failures with clear on-call ownership.
9. Retain audit trails and reconcile billing monthly.
10. Never automate **delete** solely because an `expires_on` label passed without checking data and dependencies.

Example read-only query to build a review list:

~~~bash
# READ-ONLY — filter candidate VMs. Verify output and labels carefully.
gcloud compute instances list \
  --project="$PROJECT_ID" \
  --filter="labels.environment=development" \
  --format="table(name,zone,status,labels)"
~~~

Never pipe a filtered list directly into bulk stop/delete in a one-liner. Labels can be stale or missing; require owner review per runbook.

### 13.4. Pre-Change Decision Record Template

| Field | Required Value |
|---|---|
| Change/ticket ID | … |
| Project/zone/instance name/ID | … |
| Application/environment/owner | … |
| Action | Suspend / Resume / Stop / Start / Delete |
| Reason | Cost / maintenance / decommissioning |
| Traffic handled? | Drained / disabled backend / scheduled |
| RAM state needed? | Yes/no, and for how long |
| Local SSD holds data? | Yes/no and handling plan |
| Boot/data disks and `autoDelete` | Per-disk table |
| Snapshot/backup IDs | List and restore test outcome |
| Static/ephemeral IPs | Any DNS/client dependencies |
| MIG/GKE/Spot/reservation/commitment | Verification result |
| Approval/rollback owner | … |
| Expected post-action state | … |
| Post-check and billing review | … |

Every "…" must be filled with verified facts—never mark "PASS" based on assumptions.

## 14. Troubleshooting Suspend, Resume, Stop, Start, and Delete

### 14.1. Root-Cause Flowchart

~~~mermaid
flowchart TD
    A["Lifecycle command failed"] --> B{"Right project/zone/VM state?"}
    B -- "No" --> ID["Check identity, resource ID, and status"]
    B -- "Yes" --> C{"Sufficient IAM/API/quotas?"}
    C -- "No" --> IAM["Check permissions, quotas, API enablement"]
    C -- "Yes" --> D{"Suspend/stop restricted by VM type/disk?"}
    D -- "Yes" --> LIMIT["Local SSD, GPU, RAM, Confidential, OS, quotas"]
    D -- "No" --> E{"Resume/start blocked by zonal capacity/key?"}
    E -- "Yes" --> CAP["Capacity, reservations, encryption keys"]
    E -- "No" --> F{"Delete blocked or controller-managed?"}
    F -- "Yes" --> PROTECT["Deletion protection, MIG/GKE, dependencies"]
    F -- "No" --> LOG["Audit logs, API error, operation status"]
~~~

### 14.2. Common Symptoms

| Symptom | Likely Cause | Resolution |
|---|---|---|
| Suspend reports unsupported | VM not `RUNNING`, unsupported OS/machine, GPU/Confidential | Check status, machine type, and OS against docs |
| Suspend fails on disk quota | Insufficient Persistent Disk Standard quota for RAM state | Inspect regional quota and request increase per process |
| Suspend takes a long time | Large RAM/device state or Local SSD preserve step | Watch operation progress; do not reset impulsively |
| `SUSPENDED` switches to `TERMINATED` after 60 days | Exceeded suspend window | Use `start` and reboot app; RAM state is gone |
| Resume lacks capacity | Zone out of hardware and no matching reservation | Wait/evaluate capacity; never delete VM to "fix" it |
| VM resumes yet Java app fails | Stale DB pools/tokens/DNS cache or checkpoints | Check logs, reconnect logic, readiness, and secrets |
| Stop fails with Local SSD | Missing required discard/preserve flag | Verify data; supply supported flag and feature |
| Start succeeds yet public IP changed | Previously used an ephemeral IP | Update DNS or adopt static IP/load balancer |
| Start fails on encryption key | Key revoked or missing KMS access | Check CMEK/CSEK status and key permissions |
| Delete rejected | Deletion protection, missing IAM, or controller-managed VM | Inspect guardrails, MIG/GKE, policies; obtain approval |
| Deleted VM reappears immediately | MIG/automation recreated it per desired state | Update controller/template rather than deleting instances |
| Disk vanished after delete | `autoDelete=true` or delete flags | Restore from backup/snapshot if available; audit process |
| Bill still climbs after stop/delete | Disks, IPs, snapshots, reservations, CUDs, sole-tenant, or other services | Break down Billing by project/service/SKU |
| VM `RUNNING` yet app does not serve | Boot script, service crash, IAM, firewall, or DB timeout | Inspect health/readiness, logs, and monitoring |

### 14.3. Separating Infrastructure Errors from Application Errors

- **`VM status=RUNNING`** but HTTP 503: JVM may still be initializing or backend fails health checks.
- **`VM status=SUSPENDED`** and `curl` times out: expected behavior while suspended, not a firewall bug.
- **`VM status=TERMINATED`** after stop: do not run `resume`; use `start`.
- **`403` from Google APIs** after start/resume: inspect IAM/service account/tokens; adding an external IP will not fix auth.
- **Disk charges continue after stop**: persistent storage still bills; evaluate retention rather than wiping data just to silence a line item.

For unclear errors, record the **exact operation ID and error payload** and inspect Cloud Logging/Audit Logs/Compute Engine operations instead of blindly repeating destructive commands.

## 15. Case Study — Migrating from a Java VM to Cloud Run and Decommissioning the Old Machine

**Hypothetical scenario:** the payments team has a VM **`checkout-legacy`** in project **`commerce-prod`** running a Java order processor. A new app now runs on Cloud Run, yet the old VM remains. One data disk holds reconciliation files, the boot disk holds legacy config, and an internal batch job still references the VM's IP.

### 15.1. What Goes Wrong If You Delete Immediately?

- Boot disk with `autoDelete=true` gets deleted, losing unbacked-up config.
- Data disk, if `autoDelete=true`, can also be wiped.
- The internal job breaks hitting the dead IP, or hits a wrong endpoint if an ephemeral IP gets reassigned.
- An end-of-day task still running on the VM loses in-flight work.
- Legacy monitoring fires false alerts; old IAM/service accounts retain active privileges.
- Retained disks, snapshots, or reserved IPs continue billing unnoticed.

### 15.2. Safe Decommissioning Plan

1. **Inventory:** capture VM resource ID, owner, labels, zone, disks, `deletionProtection`, networking, and service account.
2. **Traffic check:** confirm via request logs/load balancer/backend metrics that Cloud Run handles 100% of live traffic.
3. **Scheduler/queue check:** migrate batch jobs and consumers to the new system; verify zero pending events remain.
4. **Data retention:** back up reconciliation files, snapshot the data disk, and run a restore test in an isolated environment.
5. **IAM/network review:** identify unused secrets, service accounts, firewalls, and DNS records; revoke gradually per plan without breaking shared resources.
6. **Timed stop observation:** stop the VM during a maintenance window and verify zero dependent jobs fail.
7. **Measure and confirm:** monitor the new app's SLOs and error events over an observation period.
8. **Delete keeping disks:** once approved by the owner, delete the VM while keeping disks for a defined verification window; update IaC.
9. **Post-check:** verify VM is gone, data disks/snapshots retained properly, batch jobs healthy, IP/DNS clean, and remaining charges accounted for.
10. **End retention:** only after the retention window closes with proper sign-off, delete the retained disks/snapshots.

### 15.3. Why Not Choose Suspend?

The VM is being retired **long-term**; preserving JVM RAM serves no purpose. Suspend caps at 60 days, adds state storage costs, and does not resolve unmigrated dependencies. **Stop first, observe, then delete** is far safer here.

If this were a personal dev VM paused overnight mid-debug, suspend would fit. **Lifecycle choices must follow real operational goals**, not whichever button cuts immediate compute spend.

## 16. Practice Exercises and Self-Check Questions

### 16.1. Exercise A — Choosing the Action

For each scenario, pick **Suspend, Stop, Start, Resume, or Delete**, and explain required data checks:

| Scenario | Suggested Decision |
|---|---|
| Java dev VM with open IDE/JVM session, pausing overnight, suspend-eligible | **Suspend**, then **Resume** |
| Weekly batch VM needing no RAM state preserved | **Stop**, then **Start** when needed |
| VM `SUSPENDED` for 10 days, ready to resume work | **Resume**, verify app connections |
| VM `SUSPENDED` 61 days and auto-transitioned to `TERMINATED` | **Start**; no RAM state left to resume |
| Retired production VM with unverified backups/data disks | **Do not delete yet**; inventory, back up, optionally controlled **Stop** |
| Replaced VM with all data, owners, and retention approved | **Delete** with explicit disk retention flags |
| MIG member needing fewer replicas | Update **MIG desired state / autoscaler**, never ad-hoc single-VM edits |

### 16.2. Exercise B — Reading Disk Attachments

Suppose a VM lists:

~~~yaml
# Simulated data, not a full API response.
disks:
  - boot: true
    source: boot-disk
    autoDelete: true
  - boot: false
    source: orders-data
    autoDelete: false
  - boot: false
    source: scratch-backup
    autoDelete: true
~~~

**Questions:**

1. If you delete the VM without overriding disk flags, which disks risk deletion?
2. How does **`--keep-disks=all`** change the outcome?
3. Will retaining `orders-data` still incur charges?
4. If `scratch-backup` actually holds critical data, what must you do before deleting?
5. Does checking `autoDelete` prove a backup succeeded?

**Guided answers:** (1) `boot-disk` and `scratch-backup`; (2) keeps attached persistent disks upon VM deletion; (3) yes, based on disk type and size; (4) verify data, snapshot/back up, and test restore; (5) no.

### 16.3. Exercise C — Investigating a Failed Suspend

A VM has a **GPU, 256 GB RAM, and Local SSD**. An engineer runs:

~~~bash
gcloud compute instances suspend training-gpu-vm \
  --project=training-project \
  --zone=asia-southeast1-a
~~~

The command is rejected. List at least **three independent causes** and propose an alternative lifecycle strategy.

**Guidance:** GPUs and >208 GB RAM both disqualify suspend; Local SSDs also impose data-handling requirements. To cut costs, back up/persist critical data and evaluate **stop** per VM support, checking GPU/Local SSD rules, restart capacity, and app SLAs.

### 16.4. Exercise D — Verifying Costs

A VM was stopped at month-end, yet Billing Reports show daily charges continuing. Analyze potential ongoing charges: persistent boot/data disks, snapshots, static external IPs, reservations, CUDs, sole-tenant nodes, and logs/monitoring. Compare by **Service/SKU** to verify rather than assuming the VM failed to stop from a single summary line.

### 16.5. Lifecycle Operation Record Template

~~~text
REQUEST_ID:
UTC_TIMESTAMP:
PROJECT_ID:
ZONE:
VM_NAME:
VM_RESOURCE_ID:
APPLICATION:
ENVIRONMENT:
OWNER:
CURRENT_STATUS:
REQUESTED_ACTION:
REASON:
APPROVER:
MIG_OR_GKE_CONTROLLER:
DISKS_AND_AUTODELETE:
LOCAL_SSD_POLICY:
BACKUP_AND_RESTORE_RESULT:
IP_AND_DNS_DEPENDENCIES:
TRAFFIC_DRAIN_RESULT:
COMMAND_OR_OPERATION_ID:
FINAL_VM_STATUS:
POST_ACTION_HEALTH_CHECK:
BILLING_REVIEW_DATE:
ROLLBACK_OR_RECOVERY_PLAN:
OPEN_ISSUES:
~~~

Fields in the record must reflect **actually observed results**—never mark "PASS" from predictions alone.

## 17. Pitfalls to Avoid and Reference Links

### 17.1. Common Misconceptions

| Misconception | Accurate Understanding |
|---|---|
| "`TERMINATED` means the VM was deleted." | `TERMINATED` usually means the VM is stopped and can be started again. |
| "Suspend and stop are identical." | Suspend saves RAM within limits; stop does not preserve RAM for resume. |
| "Suspend preserves state indefinitely." | Maximum limit is **60 days**. |
| "Any VM can be suspended." | Restrictions apply for OS, GPU/TPU, Confidential, RAM size, disks/keys, and quotas. |
| "Resume always succeeds immediately." | Depends on zonal capacity and resource availability. |
| "Stopped VMs cost nothing." | Disks, IPs, backups, reservations, and commitments may still bill. |
| "Local SSD always retains data on stop." | Discarded by default; preservation is limited/Preview. |
| "Deleting a VM deletes all disks." | Depends on `autoDelete` and keep/delete flags. |
| "Deleting a VM never touches data." | Boot/data disks can be deleted; verify each attachment. |
| "Deletion protection blocks all disruptions." | Does not block stop, suspend, or reset; does not replace IAM or backups. |
| "A snapshot is a consistent full-database backup." | Requires application-consistent backups and restore tests. |
| "Deleting a GKE/MIG node saves cost permanently." | Controllers recreate nodes; change desired state instead. |
| "`RUNNING` means the app is healthy." | Must verify readiness/health checks, DBs, traffic, and logs. |
| "Zero CPU means safe to delete." | Could be a standby node or scheduled workload. |
| "Stopping a VM cancels CUDs/reservations." | Commitments and reservations have separate lifecycles. |

### 17.2. Official Google Cloud Documentation

- [Compute Engine instance lifecycle](https://docs.cloud.google.com/compute/docs/instances/instance-lifecycle)
- [Suspend, stop, or reset Compute Engine instances](https://docs.cloud.google.com/compute/docs/instances/suspend-stop-reset-instances-overview)
- [Suspend or resume a Compute Engine instance](https://docs.cloud.google.com/compute/docs/instances/suspend-resume-instance)
- [Stop or restart a Compute Engine instance](https://docs.cloud.google.com/compute/docs/instances/stop-start-instance)
- [Delete a Compute Engine instance](https://docs.cloud.google.com/compute/docs/instances/deleting-instance)
- [Prevent accidental VM deletion](https://docs.cloud.google.com/compute/docs/instances/preventing-accidental-vm-deletion)
- [View disk details and autoDelete](https://docs.cloud.google.com/compute/docs/disks/view-disk-details)
- [Local SSD disks and data preservation](https://docs.cloud.google.com/compute/docs/disks/local-ssd)
- [Troubleshoot suspend and resume](https://docs.cloud.google.com/compute/docs/troubleshooting/troubleshooting-suspend-resume)
- [Stopped and suspended VMs in a MIG](https://docs.cloud.google.com/compute/docs/instance-groups/suspended-and-stopped-vms-in-mig)
- [Compute Engine pricing](https://cloud.google.com/compute/all-pricing)

Product limits, Preview status, `gcloud` flags, pricing, and machine-family capabilities evolve. In live environments, verify documentation for your **exact VM type and SDK version** before executing changes.

---

**Connecting to the CLOUD_PROVIDERS_GCP track:** managing the Compute Engine lifecycle is inseparable from **projects/IAM, VPCs, persistent storage, snapshots/backups, service accounts, Cloud Monitoring, Cloud Billing, and CI/CD/IaC**. When migrating workloads to GKE, Cloud Run, or managed databases, evaluate dependencies and orchestration controllers before retiring old VMs. An operation is only truly safe when **the target resource is verified, data retention is explicit, permissions/approvals are in place, a recovery plan exists, and post-action checks confirm success**.

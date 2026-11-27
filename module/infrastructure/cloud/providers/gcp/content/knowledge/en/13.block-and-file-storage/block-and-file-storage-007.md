# Snapshots, Instant Snapshots, and Disk Snapshot Schedules in Google Cloud

A Compute Engine VM may run a Java application, store upload directories, search indexes, or temporary data on Persistent Disk or Hyperdisk. If an application update corrupts data, an administrator accidentally deletes files, or an entire zone experiences an outage, the operations team needs to **restore data to a known point in time**. Compute Engine provides multiple ways to protect disk data, notably **standard snapshots**, **instant snapshots**, and **snapshot schedules**.

These three mechanisms are not equivalent:

- **Standard snapshot** stores a copy of disk data outside the source disk location in a selected storage location; suited for longer-term backups and recovery from zone/region failures as designed.
- **Instant snapshot** creates a rapid recovery point **in the same zone or region as the source disk**; optimized for fast recovery after operational mistakes or software updates, yet does not replace off-site backups.
- **Snapshot schedule** is a **resource policy** that runs automatically hourly/daily/weekly to create **standard snapshots**; it **does not create instant snapshots**.

This lesson belongs to the **Block and File Storage** chapter of the `CLOUD_PROVIDERS_GCP` module. While learning project organization, IAM, VPC, Compute Engine, GKE, Cloud Run, storage services, databases, and release automation, selecting a backup strategy must align with **data protection, availability, verified recovery, and cost control**.

## Learning Objectives

After this lesson, you will be able to:

1. Distinguish **source disks**, **standard snapshots**, **archive snapshots**, **instant snapshots**, and **snapshot schedules**.
2. Explain **incremental** snapshots, **crash consistency**, **application consistency**, and differences in RPO/RTO.
3. Choose standard snapshot storage locations matching zone/region risks, recovery latency, cost, and data constraints.
4. Create and restore standard snapshots and instant snapshots via Google Cloud Console or `gcloud`.
5. Create, attach, and inspect snapshot schedules, configuring frequency, retention, and behavior when deleting the source disk.
6. Recognize key limitations of instant snapshots: no scheduling, deleted alongside the source disk, and accessible only at the source location.
7. Design a recovery drill without overwriting production disks while verifying restored data integrity.
8. Monitor snapshot failures, safeguard IAM/CMEK, establish lifecycle policies, and forecast costs.

## 1. Real-World Scenario: Recovering After VM Data Corruption

Suppose the Commerce team runs the Java application `orders-worker` on a Compute Engine VM. The VM has:

- Boot disk: operating system and service runtime configuration.
- Data disk `orders-data`: processing data and business files.
- Cloud SQL: primary transactional database, managed by its own backup mechanism.
- Cloud Storage: long-term object storage.

Before an upgrade that risks altering file structures, the team wants a rollback point within minutes if the upgrade fails. At the same time, they need a data copy that **is not lost if the VM's zone goes down**.

~~~mermaid
flowchart LR
    VM["Compute Engine VM<br/>orders-worker"]
    DISK["Persistent Disk<br/>orders-data"]
    INSTANT["Instant snapshot<br/>same zone as disk"]
    STANDARD["Standard snapshot<br/>location chosen by policy"]
    RECOVER["New restored disk<br/>attached to test VM"]
    DR["New disk in target zone/region<br/>per recovery capability"]
    VM --> DISK
    DISK -->|"Before upgrade"| INSTANT
    DISK -->|"Scheduled / manual"| STANDARD
    INSTANT -->|"Rapid recovery"| RECOVER
    STANDARD -->|"Restore outside source location"| DR
~~~

**A sound design uses multiple layers**: instant snapshots for rapid in-place rollback, and scheduled standard snapshots for recovery history and broader resilience. If the workload holds critical business data, you also need mechanisms for application consistency, database backups, and restore testing.

## 2. Understanding Snapshot Concepts and Differences Between Types

A snapshot captures **the data state of a disk at a point in time**; it is neither a running VM nor a complete bundle of all infrastructure resources around the VM.

| Criterion | Standard snapshot | Instant snapshot | Archive snapshot |
| --- | --- | --- | --- |
| Primary purpose | Regular backups, disaster recovery | Fast local disk recovery | Long-term, infrequently accessed retention |
| Data location | Stored outside source disk in selected region/multi-region | **Same zone or region** as source disk | Stored outside source disk |
| Survives source disk deletion | **Remains intact** | **Deleted with source disk** | **Remains intact** |
| Recovery on full zone outage | Possible if storage location and access remain available | **Not** guaranteed | Possible depending on storage location and restore conditions |
| Time to create restored disk | Suited for backup/DR, typically slower than instant | Optimized for rapid restore | Usually slowest |
| Created via snapshot schedule | **Yes** | **No** | **No** |
| Consistency | Crash-consistent by default; application-consistent methods supported | **Crash-consistent**, does not support application-consistent hooks like standard | Per supported snapshot workflow |
| Cost | Based on stored data volume and related charges | Per instant snapshot mechanism/storage | Storage price may be lower; evaluate retrieval/restore costs |

Supported features and disk types can change. Some Hyperdisk types do not support instant snapshots; review the **About instant snapshots** documentation at the end of this lesson before choosing machine/disk types.

### 2.1. Do Not Confuse with Disk Images or Application Backups

- **Custom images** are typically meant for packaging boot disks or golden images to launch new VMs, not for replacing backup schedules on frequently changing data.
- **Disk clones** create disk copies for cloning tasks; not a default off-site backup strategy.
- **Database-native backups**, such as Cloud SQL backups/PITR or application dumps/backups, protect logical and transactional integrity that block snapshots cannot guarantee on their own.
- **Cloud Storage Object Versioning** tracks object versions; it is not a Persistent Disk snapshot.
- **Filestore snapshots/backups** are native mechanisms of the NFS file service; do not run `gcloud compute snapshots` directly against Filestore.

## 3. Standard Snapshots: Incremental Copies and Flexible Recovery

Persistent Disk/Hyperdisk standard snapshots support an **incremental** model: subsequent snapshots primarily track blocks changed since the prior snapshot. From a user-experience perspective, you can still restore from any valid snapshot as an independent point-in-time copy; Compute Engine manages the underlying block chain.

~~~mermaid
flowchart LR
    D["Changing disk"]
    S1["Snapshot S1<br/>baseline"]
    S2["Snapshot S2<br/>new/changed blocks"]
    S3["Snapshot S3<br/>new/changed blocks"]
    R["Restored disk<br/>state at S3"]
    D --> S1 --> S2 --> S3
    S3 --> R
~~~

**Do not assume deleting S1 breaks restoration from S2/S3.** The service manages shared data blocks so remaining valid snapshots stay restorable. However, deleting a snapshot may not reduce billed storage by that single snapshot's displayed size, since shared blocks can still be referenced by other snapshots.

### 3.1. Taking a New Snapshot While a VM Is Running

Compute Engine lets you take a standard snapshot while the disk is attached to a running VM. However, capturing data at the block level **does not mean the application has flushed all in-memory transactions** to disk. For databases, message queues, or actively updated files, design application-level consistency separately.

### 3.2. Snapshot Storage Location and Usable Scope

Standard snapshots normally have **global scope in the default model**, while actual bytes are stored in the **region or multi-region** configured. These two concepts differ:

- **Resource scope** describes how a snapshot is identified/addressed in the Compute Engine API.
- **Storage location** describes the physical/logical location where backup bytes reside to satisfy residency, availability, and cost goals.
- **Regionally scoped snapshots** may be in Preview or have separate restrictions; do not apply that syntax across projects without verifying eligibility.

For example, a disk in `asia-southeast1-b` can be backed up to an organization-approved **multi-region** to avoid single-region dependency. If you store standard snapshots solely in **the same region** as the disk, the backup gains redundancy within that region, yet should not be treated as guaranteed protection against a **full-region outage**.

### 3.3. Choosing Location by Objective

| Objective | Decision |
| --- | --- |
| Recover when a single zone fails | Snapshot must be independent of the source zone; restore into an available zone |
| Recover when the source region is disrupted | Choose an appropriate multi-region/out-of-region snapshot storage location; verify permissions and target region |
| Data must stay in an approved jurisdiction | Choose a location compliant with policy and residency rules |
| Optimize transfer time/cost | Consider placing snapshots near the workload without compromising required protection |
| Share snapshots across projects | Configure IAM permissions and check resource/snapshot scope restrictions |

**A real DR plan** must test creating the disk, attaching to a VM, and running the application in the **destination zone/region**, not merely confirming a snapshot exists.

## 4. Instant Snapshots: Fast Recovery, Not Off-Site Backup

An **instant snapshot** is a local point-in-time snapshot optimized for **creating a new disk rapidly** when operators need to revert state prior to a change.

~~~mermaid
flowchart TD
    D["Source disk in zone b"] --> I["Instant snapshot I1<br/>also in zone b"]
    I --> N["Create new restored disk<br/>in supported location"]
    D -->|"Delete source disk"| X["Instant snapshot is also deleted"]
    I -. "Cannot move directly to another region" .-> DR["Need standard snapshot for off-site copy"]
~~~

Key limitations to remember:

1. **Location:** an instant snapshot of a zonal disk resides in the same zone; for a regional disk, in the same region. You cannot pick another location.
2. **Lifecycle:** deleting the source disk **deletes all instant snapshots** of that disk, including when a VM is deleted with auto-delete enabled on boot/data disks.
3. **Scheduling:** instant snapshots cannot be created via Compute Engine snapshot schedules.
4. **Consistency:** instant snapshots provide **crash consistency**, not application consistency.
5. **Frequency/count limits:** as of the referenced documentation, at most one instant snapshot every **30 seconds** per disk and no more than **32 instant snapshots** per disk.
6. **Hyperdisk:** not supported for every Hyperdisk type; for instance, Hyperdisk ML and Hyperdisk Throughput do not support instant snapshots.
7. **Moving regions or keeping after disk deletion:** create a **standard snapshot from the instant snapshot** before deleting the source disk.
8. **Boot recovery:** you cannot create a VM directly from an instant snapshot of a boot disk; first create a **new disk** from the instant snapshot, then boot a VM from that disk.
9. **Moving disks:** existing instant snapshots can block moving a disk; review lifecycle before moving.

### 4.1. When to Choose an Instant Snapshot

- Immediately before a software upgrade that could modify on-disk file state.
- Before a system operation that might accidentally delete data.
- When needing a fast rollback point for a workload inside a healthy zone/region.
- When capturing multiple disks together as a **consistency group** (if supported) to restore synchronized points in time.

**Never use instant snapshots as the sole copy of critical data.** If the source disk is deleted or the zone/region fails, instant snapshots cannot satisfy recovery goals.

### 4.2. Consistency Groups for Multiple Disks

If an application keeps data on one disk and transaction logs on another, snapshotting each disk separately at slightly different instants can leave an inconsistent state. Compute Engine supports creating a **consistency group of instant snapshots** across eligible disks in supported configurations.

This yields a synchronized capture point **at the disk level**, yet **does not automatically guarantee in-memory transactions were flushed and application logic completed**. If transaction-level consistency is required, use quiescing/app-native backups or an appropriate application-consistent backup solution.

## 5. Crash Consistency vs. Application Consistency

A **crash-consistent snapshot** records the disk blocks already written to storage as if the machine suddenly lost power. Filesystems can replay journals on mount; databases may need recovery from transaction logs. Unflushed in-memory data is not captured.

An **application-consistent snapshot** attempts to ensure the application flushes/quiesces state prior to capture via guest-flush, VSS, or supported application hooks.

| Level | Primary guarantee | Limitations |
| --- | --- | --- |
| Crash-consistent | Point-in-time capture of on-disk blocks | Does not guarantee all transactions/app buffers were flushed |
| File-system-consistent | Filesystem quiesced/flushed via supported hook | Database may not have flushed logical transactions |
| Application-consistent | Application/database coordinates a consistent backup point | Requires app-specific hooks and restore verification |

### 5.1. Linux and Windows

- On **Linux**, Compute Engine supports **application-consistent standard snapshots** using guest-flush and appropriate scripts/guest environment setup. The sequence can include pre-snapshot actions, flush/quiesce, snapshot, and post-snapshot actions.
- On **Windows**, you can use the **Volume Shadow Copy Service (VSS)** per Google Cloud documentation.
- If a snapshot requires application coordination yet guest setup is missing or scripts fail, do not treat the snapshot as a transaction-consistent backup.

**Do not simply drop `fsfreeze` into a cron job assuming it is safe**; freezing a filesystem improperly can hang or disrupt applications. Use supported workflows, bounded freeze durations, and test restores.

### 5.2. Consistency Goals for Business Data

For `orders-worker`:

1. Pause accepting new batches where appropriate and ensure message queues lose no data.
2. Flush critical buffers to disk or create an application checkpoint if supported.
3. Create the standard snapshot or application backup per the tested procedure.
4. Resume workload processing; verify the snapshot reaches completion.
5. Test restoring onto another disk/VM and validate data and business logic.

If real transactions reside in **Cloud SQL**, use **Cloud SQL backups/PITR** aligned with RPO/RTO targets; VM disk snapshots do not replace consistent managed database backups.

## 6. RPO and RTO Guide Snapshot Selection

- **RPO (Recovery Point Objective):** maximum tolerable data loss measured in time.
- **RTO (Recovery Time Objective):** how quickly the application must resume operation after an outage.

Examples:

| Workload | Hypothetical target RPO | Hypothetical target RTO | Suggested design |
| --- | --- | --- | --- |
| Batch VM temp files directory | 24 hours | 2 hours | Daily standard snapshot |
| Pre-rollout staging data | Per deployment | 15 minutes | Instant snapshot before upgrade + restore rehearsal |
| Critical business document files | 4 hours | 1 hour | Hourly standard snapshot, app-consistent backup when needed |
| Payment transactions | Very low | Very low | Dedicated database replication/PITR/backups, not disk snapshots alone |

These numbers are **planning hypotheses**, not Google Cloud SLAs. Real RTO depends on restore volume, disk/VM creation speed, consistency recovery, app startup time, networking/IAM, and verification time.

### 6.1. Scheduled RPO Formula

If a daily snapshot runs every 24 hours, a failure right before the next scheduled run can lose **nearly 24 hours of data**, or even more if the previous snapshot failed or was delayed.

~~~text
Expected worst-case RPO
  ≈ interval between two successful snapshots
  + delay or unhandled failed snapshot runs
~~~

Shortening the interval is insufficient if failed backups trigger no alerts, or if completed snapshots fail to restore.

## 7. Lab Preparation: Identifying Disks and Permissions Before Snapshotting

Lab example parameters:

~~~text
Project: PROJECT_ID
Region: asia-southeast1
Zone: asia-southeast1-b
Disk: lab-orders-data
Standard snapshot: lab-orders-std-001
Instant snapshot: lab-orders-inst-001
Snapshot schedule: lab-orders-daily
Restored disk: lab-orders-restore
~~~

**Disk/snapshot creation commands can incur charges.** Execute only in an approved lab project with budget, proper IAM permissions, and a cleanup plan; never run against production disks holding unauthorized data.

~~~bash
# Read-only: verify account and project before acting
gcloud auth list
gcloud config get-value project

# Inspect disks in the target zone
gcloud compute disks list --project=PROJECT_ID
gcloud compute disks describe lab-orders-data \
  --zone=asia-southeast1-b \
  --project=PROJECT_ID
~~~

For **regional** disks, disk/snapshot management commands must use `--region` instead of `--zone` per API rules. Do not confuse `asia-southeast1` (region) with `asia-southeast1-b` (zone).

### 7.1. Which IAM Permissions Are Needed?

Exact permissions depend on action and scope, but typically involve:

- Creating standard snapshots: disk snapshot and snapshot creation permissions (`compute.disks.createSnapshot`, `compute.snapshots.create` as needed).
- Creating instant snapshots: `compute.instantSnapshots.create` and corresponding disk use/read permissions.
- Restoring: `compute.disks.create` and permission to use the source snapshot (`compute.snapshots.useReadOnly` or `compute.instantSnapshots.useReadOnly`), plus attach permissions if needed.
- Creating/attaching snapshot schedules: permissions to create/update **Compute Engine resource policies** and attach policies to disks.
- Attaching disks to VMs: `compute.instances.attachDisk` and `compute.disks.use`.

Use narrow predefined roles or custom roles per organizational policy. Permissions to create/read snapshots are sensitive because **snapshots can contain personal data, secrets, or application internals**. Never grant project-wide Owner just to operate backup schedules.

## 8. Creating a Standard Snapshot Manually

### 8.1. Using Google Cloud Console

1. Select the right project and open **Compute Engine → Snapshots**.
2. Click **Create snapshot**, enter a name, and select type **Standard**.
3. Choose the **source disk** and verify its zone/region.
4. Select a **storage location** meeting residency/DR requirements.
5. If application consistency is required, execute documented guest-flush/VSS hooks before/during capture.
6. Create the snapshot, wait for completion, and inspect metadata.

### 8.2. Using `gcloud`

~~~bash
gcloud compute snapshots create lab-orders-std-001 \
  --source-disk=lab-orders-data \
  --source-disk-zone=asia-southeast1-b \
  --snapshot-type=STANDARD \
  --storage-location=asia \
  --project=PROJECT_ID
~~~

In this example, `asia` is a **multi-region storage location**, distinct from the disk's zone. Choose only locations permitted by Organization Policy and data governance; if multi-region redundancy is unnecessary, use a storage location matching company policy.

Verify:

~~~bash
gcloud compute snapshots list --project=PROJECT_ID

gcloud compute snapshots describe lab-orders-std-001 \
  --project=PROJECT_ID
~~~

When inspecting, verify snapshot status, source disk, creation timestamp, storage location, size, and encryption. **A successful creation command does not replace verifying the snapshot is ready for restoration.**

### 8.3. Incremental Snapshot Cycles and Rate Limits

When multiple standard snapshots are taken of the same disk, the service generally stores only new/changed blocks. Avoid running concurrent snapshots on the same disk and respect rate limits. Compute Engine enforces a cap on standard snapshot creations per disk within a 60-minute window; do not put manual snapshot commands in tight loops.

## 9. Creating and Restoring Instant Snapshots

### 9.1. Create an Instant Snapshot of a Zonal Disk

~~~bash
gcloud compute instant-snapshots create lab-orders-inst-001 \
  --source-disk=lab-orders-data \
  --zone=asia-southeast1-b \
  --project=PROJECT_ID
~~~

Verify:

~~~bash
gcloud compute instant-snapshots list --project=PROJECT_ID

gcloud compute instant-snapshots describe lab-orders-inst-001 \
  --zone=asia-southeast1-b \
  --project=PROJECT_ID
~~~

Instant snapshots **have no flag to choose another storage location**: location is tied to the source disk. For a **regional disk**, pass `--region=REGION` per documentation instead of `--zone`.

### 9.2. Restore to a New Disk

~~~bash
gcloud compute disks create lab-orders-from-instant \
  --zone=asia-southeast1-b \
  --source-instant-snapshot=lab-orders-inst-001 \
  --project=PROJECT_ID
~~~

After creating the disk, **attach it to an eligible test VM**, mount, and inspect the data. Never overwrite production data. If the snapshot holds a filesystem mounted by UUID, avoid mounting two disks with identical filesystem UUIDs or LVM identifiers on the same VM; use a separate VM for verification.

### 9.3. Need to Keep an Instant Snapshot After Deleting the Source Disk?

You cannot simply "move" an instant snapshot to another region. Before deleting the source disk, create a **standard snapshot from the instant snapshot**:

~~~bash
gcloud compute snapshots create lab-orders-inst-export \
  --source-instant-snapshot=lab-orders-inst-001 \
  --source-instant-snapshot-zone=asia-southeast1-b \
  --snapshot-type=STANDARD \
  --storage-location=asia \
  --project=PROJECT_ID
~~~

Verify the new standard snapshot **has completed** before deleting the source disk. This conversion counts toward the disk's standard snapshot frequency limits and can incur charges. If the source disk was deleted beforehand, the instant snapshot **no longer exists to convert**.

## 10. Restoring a Standard Snapshot to a New Disk/VM

### 10.1. Restore to a Zonal Disk

~~~bash
gcloud compute disks create lab-orders-restore \
  --zone=asia-southeast1-b \
  --source-snapshot=lab-orders-std-001 \
  --type=pd-balanced \
  --project=PROJECT_ID
~~~

You can specify `--size` if needed, though the new disk must be **no smaller than** the source disk of the snapshot. Choose a supported disk type and a zone with available capacity/quota.

### 10.2. Restore in Another Zone/Region

With a **standard snapshot whose scope/location permits restoration**, you can create a disk in another zone, for example:

~~~bash
gcloud compute disks create lab-orders-dr-restore \
  --zone=asia-southeast1-a \
  --source-snapshot=lab-orders-std-001 \
  --type=pd-balanced \
  --project=PROJECT_ID
~~~

Cross-region restoration also depends on **snapshot scope, storage location, allowed access locations, Organization Policy, encryption keys, and target networking/application setup**. Never assume every region-and-snapshot combination is permitted.

### 10.3. Attach the Disk to a VM for Inspection

~~~bash
# Only when LAB_TEST_VM already exists in the same zone
gcloud compute instances attach-disk LAB_TEST_VM \
  --disk=lab-orders-restore \
  --zone=asia-southeast1-b \
  --project=PROJECT_ID
~~~

Inside the VM, check `lsblk`, filesystems, real data, and the application; never mount a disk holding sensitive production copies on an unmanaged VM. For **boot disk snapshots**, you can create a new VM or boot disk via the dedicated workflow; for an **instant snapshot of a boot disk**, first create a disk and then boot from that disk.

### 10.4. Verify Recovery

A restore drill passes only when:

1. The new disk creates cleanly from the snapshot with appropriate size/type.
2. The filesystem mounts and data is readable.
3. Required data exists as of the capture timestamp.
4. The application runs and completes test operations (e.g., reading files, restoring records).
5. Target environment IAM permissions, encryption keys, networking, and secrets work.
6. Elapsed time from simulated incident start to application readiness is measured against **RTO**.

## 11. Snapshot Schedules: Automating Standard Snapshots

A **snapshot schedule** is a **regional resource policy** attached to one or more eligible Persistent Disks/Hyperdisks. It automatically creates **standard snapshots** at a declared cadence: hourly, daily, or weekly.

~~~mermaid
flowchart LR
    POL["Resource policy<br/>daily-schedule"]
    D1["Disk orders-data<br/>zone b"]
    D2["Disk reports-data<br/>zone a"]
    S1["Scheduled standard<br/>snapshots"]
    POL -. "Attach in same region" .-> D1
    POL -. "Can attach where eligible" .-> D2
    D1 --> S1
    D2 --> S1
~~~

A single schedule can be reused across multiple disks in the same region when eligible. Conversely, do not assume a disk can hold multiple concurrent snapshot schedules; verify disk-type limits and resource policy rules.

### 11.1. Components of a Schedule

| Field | Meaning | Example value |
| --- | --- | --- |
| Name | Policy name | `lab-orders-daily` |
| Region | Resource policy location; matches disk region | `asia-southeast1` |
| Frequency | Recurrence cadence | Daily |
| Start time | Start window **in UTC** | `12:00` |
| Storage location | Where standard snapshots are stored | `asia` |
| Max retention days | Days to retain auto-generated snapshots (subject to rules) | 7 |
| On source disk delete | How snapshots are handled if source disk is deleted | `apply-retention-policy` |
| Snapshot labels | Governance metadata on snapshots | `env=lab`, `owner=commerce` |

**Capture timing is not an exact-minute `:00` SLA.** The schedule can begin anytime within the **specified hour window**. UTC also differs from local timezones: convert carefully in operational calendars and watch for DST if teams observe daylight saving time.

### 11.2. Frequency Options Are Mutually Exclusive

A schedule defines **one** frequency pattern at a time:

- **Hourly:** every N hours per supported syntax.
- **Daily:** once per day within the specified UTC hour window.
- **Weekly:** on specific day(s) of the week.

Never combine `--hourly-schedule` and `--daily-schedule` in the same command. For sensitive workloads needing layered cadences, evaluate organizing separate disks/policies or other backup mechanisms rather than stacking schedules blindly onto one disk.

## 12. Hands-on: Creating and Attaching a Daily Snapshot Schedule

### 12.1. Create the Resource Policy

~~~bash
gcloud compute resource-policies create snapshot-schedule lab-orders-daily \
  --region=asia-southeast1 \
  --daily-schedule \
  --start-time=12:00 \
  --max-retention-days=7 \
  --on-source-disk-delete=apply-retention-policy \
  --storage-location=asia \
  --snapshot-labels=env=lab,team=commerce \
  --project=PROJECT_ID
~~~

In this example:

- The schedule policy lives in region `asia-southeast1`, matching `lab-orders-data` in `asia-southeast1-b`.
- Auto-generated snapshots are **standard snapshots**, stored in multi-region `asia` per config.
- To retain snapshots for 7 days, `--max-retention-days=7` sets the retention window (subject to retaining the newest snapshot).
- `--on-source-disk-delete=apply-retention-policy` keeps applying retention if the source disk is deleted, instead of keeping them indefinitely by default.
- Labels help trace snapshots created by the schedule.

### 12.2. Attach the Policy to a Disk

~~~bash
gcloud compute disks add-resource-policies lab-orders-data \
  --resource-policies=lab-orders-daily \
  --zone=asia-southeast1-b \
  --project=PROJECT_ID
~~~

For a **regional disk**, pass `--region` per corresponding command syntax. If the disk already has another schedule, evaluate and replace it properly instead of stacking policies blindly.

### 12.3. Inspect After Attaching

~~~bash
gcloud compute resource-policies describe lab-orders-daily \
  --region=asia-southeast1 \
  --project=PROJECT_ID

gcloud compute disks describe lab-orders-data \
  --zone=asia-southeast1-b \
  --project=PROJECT_ID

gcloud compute snapshots list \
  --project=PROJECT_ID
~~~

On the disk, inspect attached **resourcePolicies**. On the schedule, verify frequency, UTC time, retention, storage location, and disk deletion policy. Once a scheduled run completes, inspect the generated snapshot, completion timestamp, and restorability. **Successfully creating/attaching a schedule does not immediately prove a valid backup exists.**

## 13. Retention and Behavior When Deleting the Source Disk

### 13.1. Omitting Retention Keeps Snapshots Indefinitely

If `--max-retention-days` is omitted, a snapshot schedule can retain generated snapshots **indefinitely**, causing storage costs to climb continuously. Policies should clearly specify business needs and retention periods.

### 13.2. Retention Does Not Strictly Delete Every Snapshot on the Exact Day

When a snapshot passes the retention threshold, Compute Engine normally **auto-deletes it only if a newer snapshot exists** for that disk. If no newer snapshot exists, the last remaining snapshot can be retained past the declared window. This lowers the risk of losing every recovery point if a schedule stops running.

Additionally:

- Schedule retention affects only **auto-generated snapshots**, never **manually created** snapshots.
- Updating retention does not retroactively alter all older snapshots; snapshots created after the update follow the new policy per service rules.
- If you delete the schedule, prior snapshots may **be kept forever** until manually deleted; the schedule no longer manages their retention.

### 13.3. When the Source Disk Is Deleted

There are two primary behaviors:

| Option | When source disk is deleted |
| --- | --- |
| `keep-auto-snapshots` | **Default**: keeps auto-generated snapshots regardless of old retention until manually deleted |
| `apply-retention-policy` | Continues applying retention rules to schedule-created snapshots per service rules |

**Do not confuse with instant snapshots:** instant snapshots **are deleted along with the source disk**, with no retention toggle like standard snapshot schedules.

### 13.4. Is a Snapshot Schedule an Absolute Backup SLA?

No. A schedule can fail to create a snapshot due to quotas, IAM, encryption keys, disk errors, rate limits, or service status. Therefore, **monitor the latest successful snapshot timestamp** and alert if the gap exceeds RPO.

## 14. Managing, Updating, and Cleaning Up Snapshot Schedules

### 14.1. List Schedules

~~~bash
gcloud compute resource-policies list \
  --project=PROJECT_ID

gcloud compute resource-policies describe lab-orders-daily \
  --region=asia-southeast1 \
  --project=PROJECT_ID
~~~

### 14.2. Update a Schedule

You can update fields such as description, frequency, labels, and deletion/retention policy via:

~~~bash
gcloud compute resource-policies update snapshot-schedule lab-orders-daily \
  --region=asia-southeast1 \
  --daily-schedule \
  --start-time=13:00 \
  --max-retention-days=10 \
  --project=PROJECT_ID
~~~

**Updates apply only to snapshots created after the update**, not necessarily altering retention on existing older snapshots. Avoid moving capture windows into peak hours or changing schedules solely to cut costs without understanding metrics.

### 14.3. Detach a Schedule from a Disk

~~~bash
gcloud compute disks remove-resource-policies lab-orders-data \
  --resource-policies=lab-orders-daily \
  --zone=asia-southeast1-b \
  --project=PROJECT_ID
~~~

Once removed, the schedule stops auto-creating snapshots for that disk. Already-created snapshots still need inventory and lifecycle cleanup.

### 14.4. Delete a Resource Policy

~~~bash
gcloud compute resource-policies delete lab-orders-daily \
  --region=asia-southeast1 \
  --project=PROJECT_ID
~~~

Run only when **no other disks share the schedule**. Deletion can fail if the schedule remains attached. Deleting a schedule **does not automatically delete** prior snapshots; inventory their retention and cost separately.

## 15. Encryption, Permissions, and Snapshot Access Risks

A snapshot can contain:

- File contents, user data, and temporary files.
- Java application configs, secrets, or tokens accidentally left on disk.
- Database files stored on the VM disk.
- Search indexes and sensitive recoverable content.

Consequently, **permission to create a disk from a snapshot** can grant read access to data protected by the original application. Scope IAM tightly by project, snapshot, and operations team.

### 15.1. CMEK/CSEK

- With **CMEK (Cloud KMS)**, key usage permissions may be needed during both snapshot creation and restoration; ensure keys remain available and usable at the destination.
- With **CSEK**, admins/applications must safeguard customer-supplied keys; losing a key can render data unrecoverable.
- For **snapshot schedules**, Compute Engine documentation notes **CMEK** inheritance from the source disk, whereas **schedules are not supported for CSEK-encrypted disks** under current capabilities.

**Never arbitrarily delete or disable Cloud KMS keys** while snapshots remain needed for DR. Audit KMS permissions, key locations, rotation, key version status, and security logs.

### 15.2. Cross-Project Sharing and Location Restrictions

Standard snapshots can be shared/used across projects per IAM and supported product mechanics. However, copying/sharing data requires approval and checks against **Organization Policy**, VPC Service Controls (where applicable), and data residency.

If using regionally scoped snapshots in Preview, verify **allowed access locations** and corresponding `gcloud beta` syntax; never assume `--source-snapshot=NAME` grants restore access in every region.

## 16. Monitoring Snapshot Schedules and Periodic Restore Testing

A reliable backup schedule is not "policy created," but a continuous verification loop:

~~~mermaid
flowchart TD
    A["Snapshot schedule trigger time"] --> B["Create standard snapshot"]
    B --> C{"Snapshot completed?"}
    C -->|No| D["Alert, inspect logs/quota/IAM/KMS, remediate"]
    C -->|Yes| E["Record timestamp of latest successful backup"]
    E --> F["Test restore onto isolated disk/VM"]
    F --> G{"Data and application checks pass?"}
    G -->|No| H["Investigate consistency and restore runbook"]
    G -->|Yes| I["Measure RPO/RTO and confirm targets"]
    D --> A
    H --> A
    I --> A
~~~

### 16.1. Signals to Track

| Signal | Meaning | Action |
| --- | --- | --- |
| Latest completed snapshot | Did a recent backup land on schedule? | Alert if RPO threshold breached |
| Snapshot creation failures | No reliable capture occurred | Check quotas, disk state, KMS, IAM |
| Retention and snapshot count | Are expired snapshots lingering or schedules deleted? | Review policy and costs |
| Storage location | Are backups stored in approved locations? | Verify against DR/residency policy |
| Restore test | Can we create a disk/VM and read data? | Schedule periodic drills |
| Measured RTO | Actual recovery duration vs. target | Refine runbook/snapshot type |
| Snapshot costs | Data storage, restores, egress | Billing Reports and budgets |

### 16.2. Recovery Drill Checklist

- [ ] Verified exact project and snapshot type to avoid targeting the wrong environment.
- [ ] Snapshot exists and is complete, with matching source disk and timestamp.
- [ ] Required IAM permissions and encryption keys are available.
- [ ] Selected supported destination zone/region, disk type, and capacity.
- [ ] Created a **new** disk—never overwriting production disks.
- [ ] Attached disk to an authorized test VM and mounted safely.
- [ ] Verified real data and Java/application functionality after recovery.
- [ ] Recorded elapsed recovery time and maximum data loss.
- [ ] Cleaned up test disks/VMs per policy while preserving production snapshots.
- [ ] Documented results, owner, and follow-up improvements.

## 17. Costs: Snapshots Are Not Free and Involve Multiple Line Items

Costs can arise from:

1. **Stored snapshot capacity**, depending on standard/instant/archive type, location, and changed blocks.
2. **Cross-region/location data transfer**, when creating or restoring per billing rules.
3. **New disks** provisioned during restores and VMs used for verification.
4. **Cloud Logging, Monitoring**, data protection tooling, and encryption/KMS per configuration.
5. **Orphaned snapshots** no longer governed by schedules, or forgotten manual snapshots.
6. **Archive snapshot restores**, requiring evaluation of retrieval fees and restore time by tier.

There is no flat fixed price across all regions, snapshot types, or timeframes. Use [Compute Engine disks and images pricing](https://cloud.google.com/compute/disks-image-pricing) and Cloud Billing Reports to forecast before running labs.

### 17.1. Why Incremental Does Not Always Mean Cheap

If a disk churns most of its blocks daily, the snapshot chain stores many new blocks. If retention is overly long, total unique retained data grows. If builds generate large temporary files on a data disk, backups end up storing unnecessary churn.

**Ways to reduce costs without compromising goals:**

- Snapshot only disks that need protection; separate temporary scratch data.
- Match frequency to actual RPO instead of picking hourly out of habit.
- Define clear retention and source-disk deletion policies.
- Inventory manual/auto snapshots regularly, especially after deleting schedules.
- Consider archive snapshots for rarely accessed data where restore time fits.
- Track locations, egress, and restore test costs—but **never skip recovery drills** to save pennies.

### 17.2. Retention Planning Example

Suppose a 100 GiB data disk changes partially each day. The team wants 7 days of daily snapshots and monthly copies retained for 6 months. You cannot compute cost simply as **100 GiB × snapshot count**, because incremental deduplication, storage tiers, and retention policies change actual billed GBs.

Measure **actual daily churn** from history, inspect Billing Reports, and design long-term/exception backup policies separately. A single daily schedule does not automatically satisfy monthly retention or audit compliance requirements.

## 18. Common Troubleshooting

| Symptom | Possible cause | How to verify |
| --- | --- | --- |
| Standard snapshot fails to create | Wrong disk name/zone, quota/rate limit, IAM/KMS | Disk describe, API error message, permissions, and status |
| Snapshot exists yet restore fails | Insufficient permissions, KMS key unavailable, disallowed region/scope | Snapshot location, IAM, CMEK/CSEK, and org policy |
| Instant snapshot creation rejected | Unsupported Hyperdisk type, count/frequency limit exceeded | Disk type, 30s/32-snapshot limits, API status |
| Instant snapshot missing after VM delete | Boot/data disk auto-deleted, deleting instant snapshots with it | Check disk deletion history and whether standard backups remain |
| Instant snapshot won't restore in another region | Instant snapshots stay in source location | Export a standard snapshot from the instant snapshot before deleting source |
| No scheduled snapshots appearing | Resource policy not attached, UTC window not reached, job failed | Disk `resourcePolicies`, schedule describe, logs |
| Scheduled snapshots not deleted after 7 days | No newer snapshot exists or different deletion policy | Retention, latest run history, source-disk deletion option |
| Old snapshots kept indefinitely after deleting schedule | Retention policy no longer manages older snapshots | Manual inventory and cleanup workflow |
| Data restored yet database fails to start | Crash-consistent snapshot, missing log/checkpoint, or KMS error | Application-native recovery, consistency, testing |
| Disk from snapshot fails to mount | Filesystem/UUID/LVM conflict, missing driver, or size | Linux `lsblk`, filesystem tools, isolated VM |
| Bill increases even after deleting disk | Retained standard snapshots, instant/schedule/other resources | Billing Reports, snapshots list, retention |
| Actual RPO exceeds target | Snapshot job failures, schedule too sparse, lag, or unflushed app writes | Backup monitoring and application checks |

### 18.1. Ordered Debugging Workflow

~~~mermaid
flowchart TD
    A["Backup/restore failed"] --> B{"Which snapshot type?"}
    B -->|"Instant"| C["Check source disk still exists, location, limits, compatibility"]
    B -->|"Standard"| D["Check status, storage location, IAM/KMS"]
    B -->|"Schedule"| E["Check disk policy attachment, UTC window, run history, retention"]
    C --> F{"Snapshot exists and is usable?"}
    D --> F
    E --> F
    F -->|No| G["Read logs/metrics, fix root cause, take fresh backup if needed"]
    F -->|Yes| H["Create new disk for restore test"]
    H --> I{"Are app and data consistent?"}
    I -->|No| J["Check guest flush/app backup and runbook"]
    I -->|Yes| K["Measure RTO, confirm backup passes"]
~~~

## 19. Integrated Scenario: Protecting Order Data Across Upgrades and Zone Outages

The Commerce team owns a VM data disk in `asia-southeast1-b`. This week they need to upgrade the application while ensuring they can redeploy in another zone if the current zone becomes unavailable.

**Approach:**

| Risk | Mechanism | Rationale |
| --- | --- | --- |
| App upgrade corrupts data | **Instant snapshot before deploy** | Fast rollback while disk and zone remain intact |
| Accidental disk deletion or zone loss | **Standard snapshot in appropriate location** | Snapshot is independent of source disk lifecycle |
| Operator forgets manual backups | **Daily snapshot schedule** | Automatically creates standard snapshots on schedule |
| Inconsistent transactional data | **Application quiesce/DB-native backup** | Block snapshots alone do not guarantee transaction consistency |
| Snapshot exists yet fails to restore | **Periodic restore drills** | Verifies IAM, encryption, disk, and application |
| Storage bill exceeds plan | **Retention + Billing budgets** | Prevents retaining unneeded snapshots indefinitely |

### 19.1. Pre-Deployment Workflow

1. Identify the data copy to protect, owner, RPO/RTO, and maintenance window.
2. Confirm the standard snapshot schedule is active and **the latest snapshot succeeded**.
3. If application consistency is required, run checkpoint/quiesce steps prior to backup per approved procedure.
4. Create an instant snapshot and record snapshot name, source disk, zone, and timestamp.
5. Deploy the application via CI/CD; monitor health, latency, and data integrity.
6. For in-place rollback, create a **new disk from the instant snapshot** and restore onto a managed VM.
7. If the source disk/zone is gone, use the **ready standard snapshot** to create a disk in a valid destination.
8. Once the new release stabilizes, review unneeded instant snapshots; avoid deleting standard snapshots governed by retention.
9. Record metrics, costs, and drill outcomes.

### 19.2. Three Decision Principles

**Principle 1: Recovery speed and failure domain are two separate axes.** Instant snapshots offer fast RTO for local corruption yet do not protect against an entire zone outage.

**Principle 2: Automation must include verification.** A schedule can sit configured for months without producing a single valid backup due to IAM/KMS/disk errors.

**Principle 3: Having a copy does not equal having usable data.** A crash-consistent snapshot may require filesystem/database recovery; always verify application functionality after restoring.

## 20. Self-Check Exercises

**Question 1.** What is the primary difference between an instant snapshot and a standard snapshot when a VM needs recovery after a zone outage?

*Hint:* Instant snapshots stay in the source disk's zone/region and do not protect against zone/region loss; standard snapshots are stored outside the source disk in a chosen location and provide broader recoverability.

**Question 2.** Deleting the source disk deletes which type of snapshot?

*Hint:* Instant snapshots of that disk are deleted. Standard/archive snapshots exist independently of the source disk lifecycle.

**Question 3.** Does a snapshot schedule automatically create hourly instant snapshots?

*Hint:* No. Compute Engine snapshot schedules create **standard snapshots**.

**Question 4.** A daily schedule has `--max-retention-days=7`, yet no newer snapshot exists. Is the old snapshot guaranteed to be deleted on day 7?

*Hint:* No. Auto-deletion generally waits for a newer snapshot of that disk to avoid deleting the final recovery point.

**Question 5.** Why does an application database on a disk with a crash-consistent snapshot still require transaction recovery?

*Hint:* Unflushed in-memory transactions/buffers were not captured on disk; database logs and recovery routines must replay/reconcile state.

**Question 6.** Does running a snapshot schedule with `--start-time=12:00` mean it captures at exactly 12:00 Vietnam time?

*Hint:* No. The time is in **UTC** and the schedule can start anywhere within the specified hour window; convert timezones accordingly.

**Question 7.** You need to keep an instant snapshot after deleting the source disk. What must you do first?

*Hint:* Create a **standard snapshot from the instant snapshot**, verify the new snapshot completes, and only then delete the source disk.

**Question 8.** Does `gcloud compute snapshots delete` render other standard snapshots of the same disk unrestorable?

*Hint:* Not automatically. Compute Engine manages shared blocks across incremental snapshots; remaining valid snapshots stay restorable. Still, never delete carelessly without checking retention.

**Question 9.** Can someone who creates a disk from a snapshot containing user data read that data?

*Hint:* Yes. Restrict `compute.snapshots.useReadOnly` and equivalent permissions, alongside CMEK/CSEK and auditing.

**Question 10.** After deleting a snapshot schedule, do prior standard snapshots automatically expire under the old retention?

*Hint:* Not by default; deleting the policy can leave prior snapshots retained until manually deleted.

**Question 11.** Why does combining an instant snapshot before rollout with a scheduled standard snapshot make sense?

*Hint:* The former optimizes rapid local recovery, while the latter provides history and off-site backups against broader outages.

**Question 12.** Scheduled snapshots exist, yet the system still loses more data than its RPO allows. Why might that happen?

*Hint:* Failed/incomplete captures, overly sparse schedules, lag, or unflushed application writes; backup monitoring and restore tests are required.

**Question 13.** A team picks archive snapshots for a rollback point requiring recovery within minutes. Is that a good default choice?

*Hint:* No. Archive targets infrequent access with typically slower restoration; verify against RTO.

## 21. Pre-Production Checklist

- [ ] Identified source disks, zone/region, owner, and data requiring protection.
- [ ] Defined RPO, RTO, and target failure scenarios: operator mistakes, disk deletion, zone outage, region outage.
- [ ] Used **instant snapshots** for fast rollback where needed, never as the sole backup.
- [ ] Used **standard snapshots** stored in locations compliant with DR and data residency.
- [ ] Selected archive snapshots only when longer recovery times are acceptable.
- [ ] Verified application consistency and native backup mechanisms for databases.
- [ ] Confirmed snapshot schedules are **regional resource policies** with accurate frequency and UTC start time.
- [ ] Configured retention, **on-source-disk-delete**, and owner labels.
- [ ] Audited manual/existing snapshots prior to policy changes.
- [ ] Scoped least-privilege IAM permissions and Cloud KMS keys; ensured keys cannot be lost.
- [ ] Monitored latest successful snapshot timestamps, failure logs, and costs.
- [ ] Conducted periodic restore tests onto isolated disks/VMs and measured real RPO/RTO.
- [ ] Checked for lingering snapshots after deleting disks or schedules to avoid waste.
- [ ] Established runbooks and approvals before deleting snapshots/disks holding real data.

## 22. Key Takeaways

- **Standard snapshots** are incremental disk copies stored outside the source disk; usable for backup/DR with an appropriate storage location.
- **Instant snapshots** enable rapid recovery in the same zone/region, yet **are deleted with the source disk**.
- **Snapshot schedules create only standard snapshots**, not instant or archive snapshots.
- **Crash consistency differs from application consistency**; databases require dedicated quiescing/backup mechanisms when needed.
- **Retention is conditional**, not a promise that snapshots vanish at the exact minute; the newest snapshot may be preserved.
- **Deleting a schedule does not delete existing snapshots**, and the default behavior on disk deletion keeps auto standard snapshots unless overridden.
- **Having snapshots is not enough**: test restores, validate data, and measure RPO/RTO.
- **Snapshots carry costs and sensitive data**: govern IAM, KMS, locations, lifecycles, and Billing.

When deploying Compute Engine, GKE node disks, Cloud Run, or other services in the Google Cloud module, always ask: **"If the disk is deleted or the zone disappears, where is the latest recovery point, does it exist independently of the source, who can access it, and have we successfully restored from it?"** Only then do you have an operational data protection plan.

## Official References

- [About archive and standard disk snapshots](https://cloud.google.com/compute/docs/disks/snapshots)
- [Create archive and standard disk snapshots](https://cloud.google.com/compute/docs/disks/create-snapshots)
- [Best practices for disk snapshots](https://cloud.google.com/compute/docs/disks/snapshot-best-practices)
- [Restore from a standard snapshot](https://cloud.google.com/compute/docs/disks/restore-snapshot)
- [About instant snapshots](https://cloud.google.com/compute/docs/disks/instant-snapshots)
- [Create and manage instant snapshots](https://cloud.google.com/compute/docs/disks/create-instant-snapshots)
- [Restore disks from instant snapshots](https://cloud.google.com/compute/docs/disks/restore-instant-snapshot)
- [About snapshot schedules for disks](https://cloud.google.com/compute/docs/disks/about-snapshot-schedules)
- [Create snapshot schedules](https://cloud.google.com/compute/docs/disks/scheduled-snapshots)
- [Manage snapshot schedules](https://cloud.google.com/compute/docs/disks/manage-snapshot-schedules)
- [Compute Engine disks and images pricing](https://cloud.google.com/compute/disks-image-pricing)
- [gcloud compute snapshots create](https://cloud.google.com/sdk/gcloud/reference/compute/snapshots/create)
- [gcloud compute instant-snapshots create](https://cloud.google.com/sdk/gcloud/reference/compute/instant-snapshots/create)
- [gcloud compute resource-policies create snapshot-schedule](https://cloud.google.com/sdk/gcloud/reference/compute/resource-policies/create/snapshot-schedule)

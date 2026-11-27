# Zonal Disks, Regional Disks, and Replication Requirements on Google Cloud

> **Chapter:** Block and File Storage  
> **Lesson:** Zonal Disks, Regional Disks, and Replication Requirements  
> **Module:** CLOUD_PROVIDERS_GCP

In the **CLOUD_PROVIDERS_GCP** module, learners explore Google Cloud from project organization, IAM, and VPC to Compute Engine, GKE, Cloud Run, storage, and databases. Through deployment scenarios, learners select services, protect resources, automate releases, and monitor reliability and cost. For Compute Engine virtual machines, one of the most consequential decisions is **placing disk data in a single zone or maintaining replicas across two zones**.

A Java application on a VM can reboot from an image, yet stateful data such as uploaded files, transaction logs, databases, and queues on disk require a dedicated protection strategy. **Zonal disks** satisfy block storage needs within one zone; **regional disks** are designed to protect block data against a single-zone failure via **synchronous replication** across two zones in the same region. Even so, disk replicas **do not automatically start standby VMs, repair deleted data, or replace backups**.

This lesson focuses on Compute Engine **Persistent Disk** and **Hyperdisk**, comparing them against snapshots, cross-region asynchronous replication, and application-level HA/DR strategies. Examples use hypothetical projects, VMs, disks, and regions; verify machine-type catalogs and limits at actual deployment time.

## 1. Learning Objectives

After this lesson, you will be able to:

1. Distinguish **zonal disks** and **regional disks** in terms of failure domains, replica placement, and how VMs access data.
2. Explain how **Regional Persistent Disk** and **Hyperdisk Balanced High Availability** replicate synchronously across two zones.
3. Interpret **fully replicated**, **catching up**, and **degraded** states and understand their impact on recoverability.
4. Distinguish **data durability**, **availability**, **RPO**, **RTO**, **backups**, and **disaster recovery**.
5. Choose disks for Java applications, file servers, databases, GKE workloads, and multi-zone deployment needs.
6. Create, list, describe, and attach disks via Google Cloud Console or `gcloud` in an authorized sandbox.
7. Design failover incorporating **standby VMs, fencing, disk attachment, and application recovery** instead of mistaking storage replication for application failover.
8. Build workflows for snapshots, recovery, monitoring, cost optimization, and controlled zone-failure drills.

## 2. Core Concepts

### 2.1. A Disk Is Block Storage, Not a Shared File System

**Block storage** presents a block device to the guest OS. On Linux, operators typically format `ext4`/`XFS` and mount it to a directory; Windows can use NTFS/ReFS as configured. The filesystem is managed by the OS and the application running above it.

| Term | Meaning | Google Cloud example |
|---|---|---|
| **Block storage** | Block device attached to a VM; OS creates the filesystem | Persistent Disk, Hyperdisk |
| **File storage** | Sharing files/directories over a file protocol like NFS | Filestore |
| **Object storage** | Storing objects via API, not a VM-attached block device | Cloud Storage |
| **Zonal disk** | Disk stored within one zone | Zonal Persistent Disk, zonal Hyperdisk |
| **Regional disk** | Disk replicating data synchronously across **two zones in one region** | Regional Persistent Disk, Hyperdisk Balanced High Availability |
| **Snapshot** | **Point-in-time** saved copy used for recovery | Standard snapshots/instant snapshots per supported types |
| **Asynchronous replication** | Copying to another region with replication lag | Hyperdisk asynchronous replication where supported by disk type |

**Do not confuse:** A regional block disk does not automatically turn into an NFS share for dozens of VMs. To allow multiple machines to read/write files concurrently, consider **Filestore**, an appropriate file storage service, or a specialized clustered filesystem configured on a disk type supporting multiple writers.

### 2.2. Region, Zone, and Failure Domain

~~~text
Google Cloud region: asia-southeast1
├── Zone A: asia-southeast1-a
│   ├── VM orders-a
│   └── Replica A of regional disk
├── Zone B: asia-southeast1-b
│   ├── VM orders-b (standby)
│   └── Replica B of the same regional disk
└── Zone C: asia-southeast1-c
    └── Other workloads
~~~

A **region** is a geographic area composed of multiple zones. A **zone** is a deployment domain designed with independent failure risk. A **zonal disk** has a zonal scope; a **regional disk** has a regional scope yet is configured with **two specific replica zones**. Creating a regional disk in `asia-southeast1` **does not** mean Google Cloud places copies in every zone of that region.

### 2.3. Separating Compute from Storage

On Compute Engine, the **VM** is a compute resource; the **Persistent Disk/Hyperdisk** is a disk resource with an independent lifecycle that persists when the VM is stopped. Depending on deletion rules, deleting a VM may delete or keep attached disks. Therefore:

- A healthy running VM does not prove its disk has backups.
- Stopping a VM does not stop disk charges.
- A regional disk with healthy replicas does not keep the application online if the primary VM fails.
- Having snapshots does not mean data is synchronously replicated on every write.

## 3. Zonal Disks: Scope, Advantages, and Limitations

### 3.1. Zonal Persistent Disk

A Zonal Persistent Disk is a durable disk provisioned in **one zone**. Common types include:

- **`pd-standard`:** HDD-backed, suited for workloads prioritizing capacity and verified I/O patterns.
- **`pd-balanced`:** balances performance and cost; usually the starting choice for boot/data disks.
- **`pd-ssd`:** SSD-backed, suited for workloads requiring higher read/write performance.
- **`pd-extreme`:** supports provisioned IOPS in supported configurations; check current limits.

**A Zonal Persistent Disk is not stored as a single copy on one physical drive.** Google Cloud maintains durability **within the same zone** per the service's storage architecture. However, if the **entire zone becomes unavailable**, the workload may lose access to the disk until the zone recovers or data is restored by another mechanism.

### 3.2. Zonal Hyperdisk

Hyperdisk is a managed block storage family offering disk types with independent performance provisioning. Examples include:

- **Hyperdisk Balanced:** zonal, optimized for price/performance balance; does **not** automatically replicate across zones.
- **Hyperdisk Extreme:** zonal, targeting high performance/IOPS within supported limits.
- **Hyperdisk Throughput:** suited for high sequential throughput requirements.
- **Hyperdisk ML / other specialized types:** check feature scope per generation.

To get **synchronous cross-zone replication for Hyperdisk**, select **Hyperdisk Balanced High Availability**, not standard Hyperdisk Balanced. **Cross-region asynchronous replication** may be available for supported Hyperdisk types, though that is a separate DR design.

### 3.3. When Is a Zonal Disk a Reasonable Choice?

| Scenario | Is a zonal disk suitable? | Conditions |
|---|---|---|
| Development VM or CI runner | Usually yes | VM can be recreated; snapshot if data must be retained |
| Stateless Java API on a MIG | Usually yes | State lives in Cloud SQL/Cloud Storage/managed services |
| Regenerable scratch/cache disk | Can be | Cache loss and rebuild time are acceptable |
| Critical database on a single VM | Needs further evaluation | Zonal alone may fail RPO/RTO on zone outage |
| Storage for a workload using app-level replication | Can be | Database/cluster already maintains true multi-zone quorum and replicas |
| Stateful files accessed by machines across zones | Not by default | Needs appropriate filesystem/synchronization/data sharing |

If the application already uses **Cloud SQL HA**, **Spanner**, or a self-managed database with proper replication, adding replicated disks to every VM may waste money without proportionally improving availability. Identify **which layer already protects the data** first.

## 4. Regional Disks: Replicas Across Two Zones in One Region

Two main product groups are designed for synchronous cross-zone replication:

1. **Regional Persistent Disk**: `pd-balanced`, `pd-ssd`, and `pd-standard` types under supported configurations.
2. **Hyperdisk Balanced High Availability**: the Hyperdisk type that synchronously replicates between two zones in a region, alongside dedicated provisioned performance and access mode capabilities.

~~~mermaid
flowchart LR
    VM["Primary VM in zone A<br/>Writes data"]
    VM --> D["Regional disk<br/>one logical resource"]
    D --> A["Replica A<br/>zone A"]
    D --> B["Replica B<br/>zone B"]
    B -. "Ready for failover" .-> SB["Standby VM in zone B"]
    C["Application control plane<br/>health checks + fencing"] -. "Decides primary switch" .-> SB
~~~

From the application's perspective, a regional disk is **a single logical block device**. Compute Engine manages maintaining two replicas in **the specified zones**. Under normal operation, writes are replicated synchronously; **write acknowledgments in the fully replicated state** are returned only after data is durably written to both replicas per service mechanics.

### 4.1. Primary Zone and Secondary Zone

- **Primary zone:** typically the zone of the VM currently attaching the disk and issuing I/O.
- **Secondary zone:** the other zone holding the synchronously maintained replica.
- Both zones must belong to the **same region** and support the corresponding disk/machine type.
- A VM attaching a regional disk normally must reside in **one of the two replica zones**; you cannot attach a regional disk arbitrarily to a VM in another region.
- Select the standby zone based on VM creation capability, quotas, network connectivity, routing, storage types, and application dependencies.

### 4.2. VM Support and Access Modes Vary by Product

| Criterion | Regional Persistent Disk | Hyperdisk Balanced High Availability |
|---|---|---|
| Scope | Two replica zones in one region | Two replica zones in one region |
| Mechanism | Synchronous replication | Synchronous replication |
| Disk types | `pd-standard`, `pd-balanced`, `pd-ssd` | `hyperdisk-balanced-high-availability` |
| Machine types | Compatibility restrictions; Regional PD docs cite E2, N1, N2, N2D | Separate list of supported machine types |
| Performance | Depends on disk type, size, VM machine type | Provisioned IOPS/throughput configurable within limits |
| Single-VM read/write attach | Typical case | Default `READ_WRITE_SINGLE` |
| Multi-writer | Varies across disk types/modes; must verify support | Supports `READ_WRITE_MANY` when configured; requires cluster filesystem and fencing |
| Zone failure protection | Can fail over to the other replica zone | Can fail over; includes specialized cluster modes |
| Backups/snapshots | Still required | Still required |

**Do not assume:** every modern VM series can attach regional PDs. Some series support zonal Hyperdisk yet do not support Regional Persistent Disk; always verify **machine type × disk type × region** and access mode.

### 4.3. What Does *Not* Happen When Choosing a Regional Disk?

- Does not automatically create a standby VM in zone B.
- Does not automatically shift IPs, DNS, or load balancers to zone B.
- Does not guarantee the application automatically recovers from crashes, checks database WAL, or becomes ready for traffic.
- Does not automatically create point-in-time backups for accidental deletion.
- Does not replicate data to **another region**.
- Does not automatically provide a clustered filesystem so two VMs can write safely to the same ext4 volume.

Synchronous disk replication is an **HA building block**, not a complete HA service.

## 5. Replication States and Data Protection Limits

### 5.1. Replica States

| Replica state | Meaning |
|---|---|
| **Synced** | Replica is ready and caught up with all applied writes |
| **Catching up** | Replica is synchronizing missing data |
| **Out of sync** | Replica is temporarily unavailable or not up to date with disk contents |

At the disk level, Google Cloud documentation describes these conditions:

| Disk state | Condition | Impact |
|---|---|---|
| **Fully replicated** | Both replicas are synchronized | Single-zone failure protection at optimal designed state |
| **Catching up** | One replica is catching up to the other | Not yet at the protection level of fully replicated |
| **Degraded** | One replica is out of date or unavailable | I/O can continue on the healthy replica, yet redundancy is reduced |

**Important technical point:** if replication fails in one zone or lags excessively, the disk may enter `degraded` state. In that state, **writes can be acknowledged after persisting on only one replica**, not both. If the remaining healthy replica fails before resynchronization completes, **RPO/RTO are no longer defined as in the healthy state**. Never claim "a regional disk always guarantees RPO=0 under all conditions."

### 5.2. Creating or Cloning a Regional Disk

A disk created by **cloning** a zonal disk may not be fully synchronized the moment it becomes usable. Google Cloud may take time for the second copy to **catch up**. Before running failover drills or relying on it for critical data, check actual replica status and consider protection active only once it is **fully replicated**.

### 5.3. RPO and RTO

- **Recovery Point Objective (RPO):** maximum tolerable data loss measured in time (e.g., at most 5 minutes of transactions).
- **Recovery Time Objective (RTO):** target elapsed time to restore service operation after an outage (e.g., 15 minutes).
- **Durability:** probability data remains intact despite infrastructure failures.
- **Availability:** ability of the system to continue serving requests on time.

A fully replicated regional disk reduces data loss risk from a **single-zone** failure, yet **application RTO** also includes failure detection, failover decision, fencing the old VM, attaching the disk, mounting the filesystem, database crash recovery, switching endpoints, and verifying service health. Therefore, **"the disk attaches quickly" does not mean the application always achieves sub-minute RTO**.

### 5.4. Failure Matrix

| Incident | Zonal disk | Healthy regional disk | Mandatory supplement |
|---|---|---|---|
| VM OS fails while zone is healthy | Disk remains in the zone | Disk remains available | Reboot/replace VM, restart application |
| Entire zone goes down | Zonal disk in that zone is unreachable | Can fail over to healthy replica zone | Standby VM, orchestrator, and return path |
| Secondary replica fails | No cross-zone replica | May become degraded/catching up | Alerts, healing monitoring, snapshots |
| Accidental deletion from Linux | Deletion writes to disk | Deletion is **synchronously replicated** | Snapshots/backups/versioned data |
| Ransomware encrypts files | Data can be encrypted | Replica receives malicious writes too | Independent backups, IAM, and recovery protection |
| Entire region fails | Cannot serve from that region | Both replicas in the region may be unusable | Cross-region DR/backups/asynchronous replication |
| Java app or DB logical bug | Not self-healing | Not self-healing | Transactional consistency, replay/recovery, deployment rollback |

## 6. Data Replication Differs from Backups and Disaster Recovery

### 6.1. Synchronous Within a Region, Asynchronous Across Regions

~~~mermaid
flowchart TD
    APP["Application needing data protection"]
    APP --> Z{"Target failure scope to survive?"}
    Z -->|"VM failure, data can be restored later"| ZON["Zonal disk + snapshot/restore"]
    Z -->|"Single zone failure, low RPO required"| REG["Regional PD / Hyperdisk Balanced HA<br/>Synchronous across 2 zones"]
    Z -->|"Entire region failure"| CR["Cross-region backup / Hyperdisk async replication<br/>or app/database replication"]
    REG --> B["Snapshots/backups against logical errors"]
    CR --> T["DR drills, routing, and application recovery"]
    ZON --> B
~~~

- **Synchronous replication:** writes data to two zones **in the same region**, optimizing single-zone HA when fully replicated.
- **Asynchronous replication:** maintains a copy in **another region** in supported modes, with **non-zero replication lag/RPO** depending on load and design.
- **Snapshot:** saves point-in-time state for restoration; can be scheduled or on-demand, not a live per-write mirror.
- **Application backup:** can include logical database dumps, WAL/binlog archives, PITR, immutable backups, and corresponding recovery procedures.

For Hyperdisk, **Hyperdisk Balanced** and **Hyperdisk Balanced High Availability** support combining with **Asynchronous Replication** within product limits. Do not assume every Persistent Disk or every Hyperdisk series supports the same cross-region option.

### 6.2. Replication Does Not Cure Logical Data Errors

Suppose a Java API executes an SQL statement that accidentally drops the `orders` table. Synchronous storage copies the block-level changes to the second copy. Both replicas remain consistent, yet both hold the **corrupted state**. Recovering transactions requires **point-in-time backups/snapshots, transaction logs, and a restore procedure**.

A snapshot taken while a database is running may only be **crash-consistent**, not automatically **application-consistent**. For an RDBMS, review snapshot mechanics, freeze/flush procedures, WAL handling, and database vendor guidance for reliable recovery.

### 6.3. When to Use Cloud SQL or Filestore Instead of Managing Disks Directly

| Need | Option worth considering | Rationale |
|---|---|---|
| PostgreSQL/MySQL/SQL Server needing managed HA/PITR | **Cloud SQL HA** and appropriate backups/PITR | Google Cloud manages much of the DB/storage failover |
| NFS file share for multiple VMs | Appropriate **Filestore** tier | Provides a shared filesystem rather than a single block device |
| Object uploads, images/static files, JAR builds | **Cloud Storage** | Object APIs, versioning/lifecycle, and durability |
| Self-managed stateful DB on Compute Engine | Regional disks or app replication | Full OS/database control; you build failover and backups |
| Stateless containers on GKE/Cloud Run | External stateful services or suitable storage | Do not store critical data in ephemeral local filesystems |

For **GKE**, Kubernetes PersistentVolume/PersistentVolumeClaim and the Container Storage Interface (CSI) driver implement specific provisioning/attachment logic. Do not manually attach one regional disk to two Pods across two zones and mount ext4 read/write concurrently as usual; check access modes, topology, cluster filesystems, and scheduler/failover behavior.

## 7. Designing HA: Regional Disks Must Pair with Applications and Standby Compute

### 7.1. Example: Stateful Java Application on VMs

A company runs a **Java Order Processor** storing local working data in `/var/lib/orders`. The backend runs on VM `orders-a` in `asia-southeast1-a`; zone B hosts standby VM `orders-b`. A regional disk `orders-data-regional` is replicated across both zones.

~~~mermaid
flowchart TD
    LB["Load balancer / traffic router"]
    A["orders-a (primary) in zone A<br/>Java process + mounted filesystem"]
    B["orders-b (standby) in zone B<br/>No concurrent RW mount"]
    D["Regional disk: orders-data-regional"]
    RA["Replica A in zone A"]
    RB["Replica B in zone B"]
    CTRL["HA controller<br/>Health checks + fencing"]
    LB --> A
    LB -. "switches on failover" .-> B
    A <-- "normal read/write" --> D
    D --> RA
    D --> RB
    CTRL -. "designates 1 primary at a time" .-> A
    CTRL -. "attach/mount + start service" .-> B
~~~

**Principle:** in **single-writer** mode, only one VM owns write access to the disk. On stateful systems, **fencing** must prevent the old primary from continuing to write after the standby takes over, avoiding **split-brain**.

### 7.2. Cold Standby, Warm Standby, and Hot Standby

| Mode | Meaning | Impact |
|---|---|---|
| **Cold standby** | Create the VM after an outage | Low compute cost, potentially high RTO due to VM creation/setup |
| **Warm standby** | VM exists yet does not run the full app, per design | Balances cost and recovery time |
| **Hot standby** | Standby VM ready to launch/recover quickly | Better RTO, yet higher cost and requires testing |
| **Active–active** | Multiple VMs serving simultaneously | Cannot simply use one single-writer disk; requires app-level replication/appropriate shared storage |

For many stateless Java applications, a **regional MIG** plus a managed HA database is far simpler than failing over regional data disks back and forth. For stateful systems that cannot move to a managed DB, replicated disks can form part of the HA strategy.

### 7.3. What Must the Application Control Plane Do?

An **application-specific control plane** or orchestrator built by the organization needs to:

1. Monitor VM, application, and disk replica health.
2. Distinguish transient glitches, network partitions, and true zone failures.
3. Prevent the old primary from writing to the disk on failover (fencing, appropriate attach controls).
4. Select a standby VM in an active replica zone.
5. Attach the disk in a supported mode, mount the filesystem, and run application/database **crash recovery**.
6. Shift traffic via health checks/load balancers/DNS per design.
7. Verify data, transaction replay, idempotency, and error logs before finalizing.
8. Include a **failback** workflow once the primary zone recovers, avoiding two concurrent primaries.

**Never deploy a script that runs "if VM ping fails, immediately force-attach" in production.** Missing verification/fencing can trigger spurious failovers and corrupt data.

## 8. Failover, Force-Attach, and Split-Brain

### 8.1. Normal Detach/Attach

If the primary zone remains reachable and the application can shut down cleanly:

1. Stop Java/database processes, flush buffers, and halt incoming write requests.
2. Unmount the filesystem and detach the disk from the old VM.
3. Attach the regional disk to the standby VM in the other zone.
4. Mount, run filesystem/database recovery checks, and start the service.
5. Switch traffic and verify the return path.

This is a **planned failover**; it is generally safer than force-attach because the primary OS stops writing cleanly.

### 8.2. Force-Attach When a Zone Is Unresponsive

During a zone outage, Compute Engine provides **force-attach** to attach a regional disk to a VM in the surviving replica zone **even while the disk is still recorded as attached to the old VM**. Once completed, Compute Engine blocks the old VM from continuing to write to the regional disk per service mechanics.

However:

- **Use only for supported disks and access modes**; never force-attach a zonal disk.
- **Do not use `--force-attach` for Hyperdisk Balanced High Availability in multi-writer mode** (unsupported).
- Force-attach **does not automatically repair filesystems or databases**; journal replay and consistency checks may still be required.
- Do not treat force-attach as a routine maintenance action or a way to break locks while a VM is still healthy.
- After recovery, control the **failback** direction carefully to avoid booting the old VM with stale filesystem/application state.

Reference command per documentation (for reference inside an approved runbook only):

~~~bash
# DANGEROUS operation if misused in production.
# Only force attach after confirming outage, zone, and fencing.
gcloud compute instances attach-disk STANDBY_VM \
  --project=PROJECT_ID \
  --zone=REPLICA_ZONE_B \
  --disk=REGIONAL_DISK_NAME \
  --disk-scope=regional \
  --force-attach
~~~

This is **not** a default lab step. The hands-on section below uses normal attach only and does not simulate real outages.

### 8.3. What Makes Up Actual RTO?

~~~text
Actual RTO ≈ time to detect and confirm the outage
           + time to block the old primary (fencing)
           + time to attach disk to standby
           + time to mount / replay filesystem
           + time for DB/application startup and recovery
           + time to switch endpoints + pass health checks
           + time to verify service operation
~~~

Disk attachment time can be under a minute under documented conditions, yet that is **insufficient to assume end-to-end application RTO is under a minute**. Standby readiness, failure detection tooling, and automation quality govern most of actual RTO.

## 9. Choosing Disk Types by Performance, Protection, and Cost

### 9.1. Decision Matrix

| Workload / requirement | Zonal Persistent Disk | Regional Persistent Disk | Hyperdisk Balanced HA | Complementary approach |
|---|---|---|---|---|
| Dev/test, regenerable data | Suitable | Usually overkill | Usually overkill | Periodic snapshots if needed |
| Stateless Java behind MIG | Suitable for per-VM boot disk | Unnecessary if state is externalized | Unnecessary | Cloud SQL HA, Cloud Storage |
| Stateful app tolerating manual failover | Possible if RTO is generous | Fits when zone outage is a required risk | Consider if high performance needed | Standby VM + runbook |
| Database needing low RPO on zone failure | Hard with zonal alone | An HA building block | An HA building block | DB recovery, snapshots, fencing |
| High IOPS/throughput workload needing cross-zone HA | Needs app replication/snapshots | May be capped by performance/type | Evaluate by provisioned performance | Live benchmarks |
| Cluster filesystem needing multi-writer | Not by default | Not by default | Supported `READ_WRITE_MANY` mode | Cluster filesystem, quorum, fencing |
| DR when an **entire region** fails | Insufficient | Insufficient | Insufficient if sync within region only | Cross-region async replication + backups |
| Shared files across multiple VMs via NFS | Not default direction | Not NFS | Not NFS | Filestore/file service |

### 9.2. Performance Depends on More Than Disk Type

Actual IOPS, throughput, and latency are influenced by:

- Disk type, capacity, and provisioned IOPS/throughput for eligible Hyperdisks.
- VM **machine type**, vCPU count, attach limits, and I/O bandwidth.
- Random vs. sequential reads/writes, block size, and queue depth.
- Latency between application and replicas, and synchronous replication characteristics.
- Filesystem, block cache, RAID/LVM (if used), and database flush/fsync behavior.
- Concurrent load and whether the disk is **degraded/catching up**.

Do not take maximum IOPS from a pricing sheet as guaranteed performance for every VM. **Measure** with safe tools on a test filesystem and inspect application p95/p99 latency; never run destructive write benchmarks on production disks.

### 9.3. Cost of Replicated Disks

Replicating across two zones requires two copies of the data, so **capacity storage cost for Regional Persistent Disk is typically roughly double that of the equivalent zonal disk**, yet the **total bill is not simply doubled**: there are also standby VMs, Hyperdisk IOPS/throughput, snapshots, networking, backups, and logs.

- A 200 GiB zonal `pd-balanced` and a 200 GiB regional `pd-balanced` are **two different pricing configurations** by region/SKU.
- Hyperdisk Balanced HA bills by **capacity, provisioned IOPS, and throughput** per product rules; charges can apply even when unattached.
- A continuously running standby VM has different compute costs from an on-demand standby.
- Backups/snapshots incur storage and restore/traffic charges per policy.
- Capacity/reservations and zone choice can affect operations and budget.

**Never quote a fixed USD unit price** without knowing the region, SKU, date, discounts, licensing, and Hyperdisk provisioned performance rates. Use the Google Cloud Pricing Calculator and Billing Reports for real decisions.

## 10. Technical Limits to Verify Before Deployment

| Limit / condition | Meaning |
|---|---|
| **Machine type × disk type** compatibility | Regional Persistent Disk and Hyperdisk Balanced HA have different supported VM lists |
| Replica zones | Must specify two distinct zones in the **same region** |
| Regional disk types | `pd-balanced`, `pd-ssd`, `pd-standard`, and `hyperdisk-balanced-high-availability` per supported options |
| Capacity | Regional `pd-standard` has a larger minimum, e.g., 200 GiB; other types have specific limits |
| Read-write access mode | Single writer by default; multi-writer clusters require compatible disks/modes/filesystems |
| Boot disks | Regional disks can serve as boot disks within limits; creation from images or clones has specific support conditions |
| Resize | Can increase capacity, **cannot shrink directly**; guest OS partitions/filesystems must also be expanded |
| Disk catching up | Does not yet provide full healthy-state protection |
| Zonal availability | Not every region/zone/machine type supports every configuration |
| AI zones | Have specific restrictions regarding regional disks |
| Quota/capacity | Available quota does not guarantee VM standby capacity during a zone outage |
| IAM | Permissions required on both VM and disk to create/attach/force-attach/snapshot |

For example, regional disk documentation specifies minimum sizes: regional `pd-standard` from **200 GiB**, regional `pd-balanced` and `pd-ssd` from **10 GiB**, and Hyperdisk Balanced HA from **4 GiB**. Check maximums, access modes, and availability in the current documentation for your version.

## 11. Hands-on A — Inspecting Zonal and Regional Disks with `gcloud`

Commands in this section are **read-only**, suitable for starting on an authorized sandbox project.

~~~bash
# Confirm identity and project.
gcloud auth list
gcloud config get-value project

# List disks in the project: includes zonal and regional disks you can view.
gcloud compute disks list --project=PROJECT_ID

# Details for a zonal disk.
gcloud compute disks describe ZONAL_DISK_NAME \
  --project=PROJECT_ID \
  --zone=asia-southeast1-a

# Details for a regional disk.
gcloud compute disks describe REGIONAL_DISK_NAME \
  --project=PROJECT_ID \
  --region=asia-southeast1

# Inspect primary VM, attached disks, and status.
gcloud compute instances describe PRIMARY_VM \
  --project=PROJECT_ID \
  --zone=asia-southeast1-a \
  --format="yaml(name,status,disks,machineType,networkInterfaces)"
~~~

When inspecting a regional disk, check:

- `name`, `sizeGb`, `type`, `region`, and the **replicaZones** list.
- Which VM currently has the disk attached (`users` field or attachment info).
- Access mode, and multi-writer capability if it is a supported Hyperdisk type.
- Replication/replica status fields if surfaced by the API/Monitoring.
- Whether snapshot policies and recovery settings align with RPO/RTO requirements.

An illustrative JSON output (for explanation only, not a full response):

~~~json
{
  "name": "orders-data-regional",
  "sizeGb": "100",
  "type": "projects/example-lab/zones/asia-southeast1-a/diskTypes/pd-balanced",
  "region": "projects/example-lab/regions/asia-southeast1",
  "replicaZones": [
    "projects/example-lab/zones/asia-southeast1-a",
    "projects/example-lab/zones/asia-southeast1-b"
  ]
}
~~~

**Note:** the live API may represent `type` and fields using different URL/URI formats; do not build policy parsers around illustrative JSON. The key takeaway is confirming **the disk is truly regional with two replica zones**.

## 12. Hands-on B — Creating and Attaching Disks in a Sandbox

**The commands below mutate real resources and incur charges**. Use only in a sandbox project, never in production without a change ticket, backup, and approver. Referenced VMs are assumed **already created**, with the primary in zone A, standby in zone B, and machine type compatibility verified.

### 12.1. Create a Zonal Persistent Disk

~~~bash
gcloud compute disks create orders-zonal-lab \
  --project=PROJECT_ID \
  --zone=asia-southeast1-a \
  --type=pd-balanced \
  --size=100GB
~~~

This disk lives in one zone. It has durability mechanisms **within the zone**, yet no automatic replica in `asia-southeast1-b`.

### 12.2. Create a Regional Persistent Disk

~~~bash
gcloud compute disks create orders-data-regional \
  --project=PROJECT_ID \
  --region=asia-southeast1 \
  --replica-zones=asia-southeast1-a,asia-southeast1-b \
  --type=pd-balanced \
  --size=100GB
~~~

**Pre-execution checks:**

1. `PROJECT_ID` is the right sandbox project and both replica zones are supported.
2. Regional `pd-balanced` supports the target VM's machine type.
3. The disk name is unused in the corresponding scope.
4. The operator holds least-privilege IAM disk permissions and sufficient quota.
5. Replicated disk costs are accepted and a cleanup plan exists.

### 12.3. Create Hyperdisk Balanced High Availability

Baseline command example:

~~~bash
gcloud compute disks create orders-hd-ha-lab \
  --project=PROJECT_ID \
  --region=asia-southeast1 \
  --replica-zones=asia-southeast1-a,asia-southeast1-b \
  --type=hyperdisk-balanced-high-availability \
  --size=100GB
~~~

This Hyperdisk type has specific IOPS/throughput rules and supported machine types. The command above illustrates the **region/replica/type structure** using default performance settings. For real workloads, design and set `--provisioned-iops`/`--provisioned-throughput` per current capabilities/CLI and cost estimates.

### 12.4. Inspect and Attach a Regional Disk

~~~bash
gcloud compute disks describe orders-data-regional \
  --project=PROJECT_ID \
  --region=asia-southeast1

# Attach only to a VM in one of the two replica zones with verified compatibility.
gcloud compute instances attach-disk PRIMARY_VM \
  --project=PROJECT_ID \
  --zone=asia-southeast1-a \
  --disk=orders-data-regional \
  --disk-scope=regional \
  --device-name=orders-data
~~~

After attaching, the disk appears as a block device on the VM, yet **does not automatically have a filesystem or mount point**.

### 12.5. On Linux: Safe Identification and Mounting

**Warning:** `mkfs` **erases any existing filesystem structure**. Format only if you are certain the new disk is **empty**, matches the exact disk ID, and contains no data to keep. For active or restored disks, **never run `mkfs`**.

~~~bash
# Inspect inside the VM.
lsblk -o NAME,SIZE,TYPE,FSTYPE,MOUNTPOINTS
sudo blkid

# Check symlink path and actual device presented by Compute Engine.
ls -l /dev/disk/by-id/ | grep orders-data || true

# ONLY WHEN certain this is a blank sandbox disk:
# sudo mkfs.ext4 -F /dev/disk/by-id/google-orders-data

# Mount a disk that already has a filesystem (or was safely formatted).
sudo mkdir -p /srv/orders-data
# sudo mount /dev/disk/by-id/google-orders-data /srv/orders-data

# Verify mount before the application writes.
findmnt /srv/orders-data || true
~~~

The path `/dev/disk/by-id/google-orders-data` corresponds to `--device-name=orders-data`; verify the actual path before acting. To persist mounts across reboots, use **UUID** in `/etc/fstab` or a managed mount unit and check `nofail`/dependency options per design. Never hardcode `/dev/sdb` as device ordering can change.

### 12.6. Recovery After Planned Failover

For a single-writer disk:

1. Put the API/DB into maintenance mode and stop accepting write requests.
2. Flush transactions, stop the service, and unmount on the primary VM.
3. Detach the disk (cloud operation).
4. Attach the disk to the standby in the second replica zone.
5. Inspect the device, mount the filesystem **without formatting**, and run crash recovery if needed.
6. Start the application, run health checks, switch traffic, and verify data.
7. Record measured RTO and the failback plan.

Do not attempt `force-attach` while the VM is still running normally or when fencing cannot be verified.

## 13. Analyzing a Java System: Where Should State Live?

### 13.1. Case Study: Orders API on Compute Engine

Suppose a Java application has:

- **REST API:** Stateless, multiple VMs behind a load balancer.
- **Order database:** PostgreSQL requiring transactional protection.
- **Uploaded PDF invoices:** must be accessible across multiple API instances.
- **Cache:** regenerable data.
- **Job runner:** processes queues and job checkpoints.

| Component | Where should it be stored? | Why |
|---|---|---|
| JAR/container and non-sensitive config | Artifact Registry or image/instance template | Redeployable; no need for a shared regional data disk |
| Transactional order data | Cloud SQL HA or properly HA self-managed DB | Protects transactions/backups/PITR |
| PDF invoice files | Cloud Storage with IAM and data controls | Multiple VMs access via object API, not a shared block device |
| Cache | Memorystore or local cache as needed | Regenerable; no need for unconditional block replication |
| Critical job checkpoints | Database/Cloud Storage or persistent disk matching RPO | Must define replay/idempotency |
| Application logs | Cloud Logging with proper configuration | Centralized visibility when VMs fail over or get deleted |

**Architectural conclusion:** most modern Java APIs should **decouple state from VMs**, rather than putting all data onto a regional disk and moving VMs across zones.

### 13.2. When Is a Regional Disk Genuinely Needed?

It can be suitable if the application:

- Depends on a specific filesystem/block device and cannot easily move to a database/object store.
- Needs a single disk volume read/written by one primary VM with a standby in another zone.
- Has a tested failover/fencing/recovery runbook or orchestrator.
- Requires low RPO for single-zone failures and accepts replicated storage costs.
- Does not require **active–active concurrent writes** when using single-writer mode.

If the requirement becomes "GKE Pods across two zones writing to the same directory" or "multiple VMs running concurrently on the same ext4," the need has shifted to a **shared file system/cluster filesystem**; choose **Filestore** or a suitable multi-writer product/mode rather than forcing a regional block disk to solve the wrong problem.

## 14. Backups, Data Consistency, and Recovery

### 14.1. Scheduled Snapshots and Restore Drills

A minimum plan includes:

1. Define **application RPO**: how much data loss in time is tolerable?
2. Choose snapshot or database backup frequency based on RPO and rate of change.
3. Define backup **location/retention** per policy and compliance constraints.
4. Separate permissions to create/delete snapshots from application permissions whenever possible.
5. Protect backup data against unauthorized deletion and monitor backup failures.
6. **Rehearse restores onto a test disk/VM**, verifying files/checksums/database consistency.
7. Include actual restore time in RTO measurements, not just API disk creation time.

### 14.2. Example Snapshot Read-Back

Command to create a snapshot (mutating operation):

~~~bash
# Example regional disk snapshot; requires permissions and a DB consistency plan.
gcloud compute snapshots create orders-data-snap-lab \
  --project=PROJECT_ID \
  --source-disk=orders-data-regional \
  --source-disk-region=asia-southeast1
~~~

To inspect the snapshot after creation:

~~~bash
gcloud compute snapshots describe orders-data-snap-lab \
  --project=PROJECT_ID \
  --format="yaml(name,status,diskSizeGb,creationTimestamp,sourceDisk)"
~~~

If running a database, consult guides for ensuring **application consistency** and treat a snapshot as recoverable only after a successful restore test, not merely because its creation status succeeded.

### 14.3. Building a Three-Layer Data Protection Policy

| Layer | Goal | Tools |
|---|---|---|
| **Intra-region HA** | Minimize service downtime on single-zone outage | Regional disk + standby VM/failover or managed HA |
| **Independent backups** | Recover from accidental deletion/ransomware/logical bugs | Snapshots, database backups/PITR, retention |
| **Cross-region DR** | Respond to regional outages or disasters | Cross-region backups, async replication, or app replication |

The three layers complement—not replace—each other. When high data protection is required, also enforce **access controls**, policy-compliant encryption/KMS, immutable/deletion-protected backups, and a security incident response plan.

## 15. Monitoring and Diagnosing Replica State

### 15.1. Metrics to Observe

| Category | Signal | Suggested alert |
|---|---|---|
| Replication | Replica state `Synced/Catching up/Out of sync` | Prolonged deviation from `Fully replicated` |
| Disk availability | Disk unattached / unable to read or write | Primary loses write access or attach fails |
| Storage performance | IOPS, throughput, latency, and throttling | DB p99 latency rising due to disk |
| Capacity | Filesystem near full, usage growth rate | `/var/lib/orders` filling up, write errors |
| VM/zone | VM state, zone outage, health check failures | Trigger investigation or approved failover |
| Application | 5xx errors, DB connection errors, WAL replay | Service not recovered even after disk attach |
| Backups | Snapshot failures, time since last successful snapshot | Backup RPO breached |
| Cost | Regional disk fees, Hyperdisk IOPS/throughput, standby VM | Over budget or orphaned resources |

You can use **Cloud Monitoring metrics** and disk/replica state information exposed by Compute Engine; check exact metric names in current documentation for your disk type. When configuring alerts, verify permissions, export intervals, and differences across disk types.

### 15.2. Scenario A — Regional Disk Is Degraded

**Symptom:** the app can still write, yet the dashboard reports replica B `Out of sync` and the disk `Degraded`.

**Accurate interpretation:**

- Do not immediately assume data has been lost.
- Redundancy is no longer **fully replicated**; if replica A also fails during this window, data availability and RPO/RTO become indeterminate.
- Monitor automatic healing; check zone/replica incidents, write load, and updated status.
- Consider taking a **snapshot** from the healthy replica per documentation if the degraded state persists and threatens RPO targets.
- **Do not proactively force-attach** to an out-of-sync replica without proper procedures and evidence.

### 15.3. Scenario B — Cannot Create a VM in the Standby Zone

The disk remains fully replicated, yet when the primary zone fails, creating a standby VM in the secondary zone fails due to insufficient capacity.

**Root cause:** the disk had two replicas, yet compute capacity for the standby VM was not guaranteed. The HA lesson is to design **both storage and compute**, quotas, service accounts, networking, dependencies, images, and capacity reservations where appropriate.

### 15.4. Scenario C — Application Reports Bad Data After Restore

Snapshot restore succeeds at the API level, yet the database fails to start or lacks the latest transactions.

**Likely causes:**

- The snapshot is older than the required RPO.
- The database had not flushed/checkpointed and needs WAL/transaction log replay.
- The snapshot was not application-consistent.
- The app also relies on object storage, secrets, or secondary databases from a different timestamp.
- Code rollback and database schema versions are incompatible.

**Lesson:** the existence of a snapshot does not mean **system recovery meets targets**. Test recovery at the application layer.

## 16. Runbook: When to Fail Over to the Standby Zone

### 16.1. Trigger Conditions

Trigger failover only when appropriate signals align:

- VM/API health checks fail continuously beyond the defined threshold.
- The primary zone or compute is unavailable and does not self-recover within the acceptable window.
- The secondary replica is in a state that allows safe failover.
- The orchestrator can prevent split-brain.
- A compatible standby instance and traffic/database/network paths exist in zone B.

### 16.2. Reference Sequence

~~~text
[1] Confirm impact and incident severity
       |
       v
[2] Check disk state + replica state
       |
       v
[3] Check standby VM / capacity / quota / zone
       |
       v
[4] Fence or block writes from old primary
       |
       v
[5] Detach/attach, or force-attach when strictly necessary
       |
       v
[6] Mount filesystem (DO NOT FORMAT), recover DB/app
       |
       v
[7] Health checks + data verification + shift traffic
       |
       v
[8] Monitor + record evidence + prepare failback
~~~

Assign clear roles: **incident commander** authorizes failover, **storage/compute owner** operates disks/VMs, **application owner** verifies data, **network owner** verifies routes/load balancers, and **security** checks anomalies and permissions. For production, rehearse in a sandbox to catch IAM, mount device, script, and load balancer issues before an actual outage.

### 16.3. Failback After the Primary Zone Recovers

Failback is also a primary transition:

1. Never allow the old VM to auto-start the application with write access to stale data.
2. Confirm the disk is `fully replicated` and all replicas have caught up.
3. Choose a maintenance window or orchestrated failback.
4. Stop/flush the application on the current primary, fence, and detach/attach back to the target zone.
5. Restore the application and traffic; verify transactions, latency, and backups.
6. Ensure only one primary is writing (unless using a properly engineered multi-writer cluster).

**Never create two "primaries" by booting both VMs with an ext4 filesystem on the same disk** in a single-writer model.

## 17. Design Exercises and Self-Assessment

### Exercise 1 — Choosing Zonal vs. Regional

A stateless Java application runs on a **regional MIG** across three zones. Order data lives in Cloud SQL HA, and images live in Cloud Storage. Each VM stores only caches and temporary logs.

**Question:** Does each VM need a regional Persistent Disk? Why or why not? Where should backups live?

**Hint:** Not necessarily. When state is decoupled from VMs and VMs are disposable, zonal boot disks are usually appropriate. Backups/PITR belong at the database and object data layers as required.

### Exercise 2 — RPO and RTO

An accounting service self-manages a database on Compute Engine and must survive a **single-zone failure** with near-zero RPO and a maximum 15-minute RTO. The team plans to buy a regional disk without provisioning a standby VM.

**Question:** What components are missing? If zone B is catching up, can near-zero RPO still be promised unconditionally?

**Hint:** Standby compute/capacity, health checks, fencing, attach/mount automation, DB crash recovery, traffic switching, and drills are missing. While a replica is degraded/catching up, protection is reduced.

### Exercise 3 — Replication and Accidental Data Deletion

An employee accidentally deletes `/var/lib/invoices` on a regional disk. The disk is fully replicated.

**Question:** Does replica B still hold the pre-deletion data? What is the right recovery approach?

**Hint:** Deletion is replicated; you cannot by default recover from replica B. Use snapshots/backups/versioning and choose an appropriate restore point.

### Exercise 4 — Multi-Region DR Design

Critical transactional data must be recoverable even if **region A is completely lost**. The team uses a regional disk with two replica zones inside region A.

**Question:** Why does this fall short? What must be added?

**Hint:** Both replicas still reside within the same region. Add cross-region replication/backups, a standby site, DNS/routing, data consistency planning, RPO/RTO targets, and DR drills.

### Exercise 5 — Multi-Writer

Two VMs want to write **concurrently** to the same ext4 file—one in zone A and one in zone B. An engineer suggests enabling `READ_WRITE_MANY` on Hyperdisk Balanced HA and mounting regular ext4.

**Question:** Is this safe? What mechanisms are missing?

**Hint:** Do not use ext4 as a concurrent clustered filesystem. You need a cluster-aware filesystem or an application designed for shared block access, a lock manager/quorum/fencing, and verified product feature support.

### Exercise 6 — Cost Optimization

A small development environment runs a VM in one zone, with data rebuildable from Artifact Registry and Cloud Storage. The team wants a regional disk because they heard "regional is always better."

**Question:** Compare zonal + snapshots against regional + standby. What cost and reliability are actually needed?

**Hint:** Choose based on downtime impact, RPO/RTO, budget, and recovery strategy; a replicated disk may be unnecessary overhead in dev.

### Exercise 7 — Troubleshooting a Disk Attach Failure

You run:

~~~bash
gcloud compute instances attach-disk orders-b \
  --project=PROJECT_ID \
  --zone=asia-southeast1-c \
  --disk=orders-data-regional \
  --disk-scope=regional
~~~

The disk has replicas in `asia-southeast1-a` and `asia-southeast1-b`.

**Question:** What is the immediate issue? Should you try `--force-attach`?

**Hint:** Zone C is not one of the two replica zones; the VM does not satisfy attachment requirements. `--force-attach` does not fix topology mismatches.

## 18. Pre-Production Checklist for Regional Disks

- [ ] Documented workload, stateful components, data owner, and **RPO/RTO**.
- [ ] Identified target failure domains to survive: VM, zone, or **entire region**.
- [ ] Compared zonal Persistent Disk, zonal Hyperdisk, Regional Persistent Disk, Hyperdisk Balanced HA, and managed services.
- [ ] Verified machine type × disk type × region × replica zones × access mode.
- [ ] Determined single-writer vs. cluster multi-writer; fencing/quorum in place if needed.
- [ ] Verified standby VM, image, quota, capacity, VPC, IAM, and traffic paths.
- [ ] Tested application-specific failover controller/runbook.
- [ ] Understood `fully replicated`, `catching up`, `degraded`, and configured alerts on replica state.
- [ ] Verified filesystem/database recovery, integrity, WAL, and crash consistency.
- [ ] Created independent snapshots/backups and tested **restores**—not treating replication as backup.
- [ ] Established a cross-region DR plan if requirements include region outages.
- [ ] Measured application IOPS, throughput, p95 latency, and observed VM limits.
- [ ] Reviewed pricing for provisioned storage/IOPS/throughput, standby compute, backups, and logging.
- [ ] Defined planned failover, approved emergency force-attach, and failback procedures.
- [ ] Protected data with least-privilege IAM, policy-compliant encryption/KMS, and auditing.
- [ ] Tested cleanup in a sandbox, checked deletion rules, and noted disks continue billing when VMs stop.

## 19. Official Google Cloud Documentation

Limits, machine-type support, and command syntax may change across versions. Before executing in a real project, consult the documentation:

- [Persistent Disk overview](https://docs.cloud.google.com/compute/docs/disks/persistent-disks)
- [Google Cloud Hyperdisk overview](https://docs.cloud.google.com/compute/docs/disks/hyperdisks)
- [Create and manage regional disks](https://docs.cloud.google.com/compute/docs/disks/regional-persistent-disk)
- [About synchronous disk replication](https://docs.cloud.google.com/compute/docs/disks/about-regional-persistent-disk)
- [Manage failures for regional disks](https://docs.cloud.google.com/compute/docs/disks/repd-failover)
- [Build HA services using synchronously replicated disks](https://docs.cloud.google.com/compute/docs/disks/high-availability-regional-persistent-disk)
- [About Hyperdisk Balanced High Availability](https://docs.cloud.google.com/compute/docs/disks/hd-types/hyperdisk-balanced-ha)
- [Disk data protection](https://docs.cloud.google.com/compute/docs/disks/data-protection)
- [Attach disks to VM](https://docs.cloud.google.com/compute/docs/disks/attach-disks)
- [gcloud compute disks create](https://docs.cloud.google.com/sdk/gcloud/reference/compute/disks/create)
- [gcloud compute instances attach-disk](https://docs.cloud.google.com/sdk/gcloud/reference/compute/instances/attach-disk)
- [Compute Engine disk pricing](https://cloud.google.com/compute/disks-image-pricing)
- [Filestore overview](https://cloud.google.com/filestore/docs/overview)

**Key takeaway:** **Zonal disks** fit when data can be restored or the application manages replication itself; **regional disks** provide synchronous replication across **two zones in the same region**, helping build zone-fault-tolerant services when paired with **standby VMs, fencing, failover, and application recovery**. Even when **fully replicated**, a regional disk **does not replace backups** and **does not protect against full-region outages**. Sound storage decisions rest on **RPO/RTO, data type, performance, operability, and total cost**, never on the disk's name alone.

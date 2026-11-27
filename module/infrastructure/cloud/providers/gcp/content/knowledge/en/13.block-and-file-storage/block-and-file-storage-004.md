# Local SSD and Ephemeral Data Management on Google Cloud

> **Chapter:** Block and File Storage  
> **Module:** **CLOUD_PROVIDERS_GCP** — Explore Google Cloud from project organization, IAM, and VPC to Compute Engine, GKE, Cloud Run, storage services, and databases. Through deployment scenarios, learners select services, protect resources, automate releases, and monitor reliability and cost.

When processing a large dataset on Compute Engine, reading and writing intermediate files can account for a significant portion of job duration. **Local SSD** is high-performance block storage physically attached directly to the host running the VM, making it ideal for **caches, scratch space, intermediate data, and regenerable components**. Yet high performance comes with a core trade-off: **never treat Local SSD as the sole copy of your data**.

This lesson walks through identifying suitable workloads, creating and attaching Local SSDs on Compute Engine, safely preparing filesystems, handling VM reboots/stops/host failures, building recoverable cache/checkpoint mechanisms, and monitoring performance and costs. For GKE or Java systems running on GCP, the lesson also delineates the boundary between **local ephemeral storage** and **durable storage**.

## Learning Objectives

After this lesson, learners will be able to:

1. Explain the differences among **Local SSD**, **Titanium SSD**, **Persistent Disk**, **Hyperdisk**, **Filestore**, and **Cloud Storage**.
2. Choose Local SSD for cache/scratch and recognize data that must never be stored solely on Local SSD.
3. Understand how Local SSDs are provisioned by machine series, **NVMe/SCSI** interfaces, and the constraint that disks cannot be added after VM creation.
4. Inspect devices before **formatting, mounting, or creating RAID 0** to avoid overwriting boot/data disks.
5. Build a lifecycle matrix for Local SSD across **guest reboot, live migration, host error, stop, suspend, Spot preemption, and delete**.
6. Design **read-through caches, checkpoints, replicated state, retries, and recovery after data loss**.
7. Monitor Local SSD IOPS, throughput, latency, capacity, REPAIRING behavior, and cost.
8. Apply these concepts in a Java batch processing scenario on Compute Engine and GKE workloads.

## 1. What Is Local SSD?

**Local SSD** in Compute Engine is high-speed block storage **physically attached directly to the host** where the VM runs. Unlike Persistent Disk or Hyperdisk—durable storage services decoupled from the VM host—Local SSD sits closer to CPU resources, delivering **low latency and high IOPS/throughput** under appropriate conditions.

~~~mermaid
flowchart LR
    subgraph HOST["Physical host running Compute Engine VM"]
      VM["VM / Java workload"]
      LOCAL["Local SSD / Titanium SSD\nScratch and cache"]
      VM <-->|"Host-local block read/write"| LOCAL
    end
    VM <-->|"Store durable data"| PD["Persistent Disk / Hyperdisk"]
    VM <-->|"Object API over network"| GCS["Cloud Storage"]
    VM <-->|"Network file share"| FS["Filestore"]
~~~

Key characteristics:

- **Ephemeral data:** data on Local SSD can be lost when the VM/host changes state or encounters an error; there is no automatic copy guaranteeing independent persistence.
- **Not a boot disk:** Local SSD cannot be used as a VM boot disk.
- **Provisioned with the VM:** Local SSDs can only be added when **creating the VM**; you cannot attach additional Local SSDs to an existing VM like a persistent disk. Depending on the machine series, disk count or capacity comes bundled with the machine type.
- **No direct snapshot/clone/machine image backups:** you must **copy data worth keeping** to Hyperdisk, Persistent Disk, Cloud Storage, or another durable store beforehand.
- **Not automatically shared across VMs:** a filesystem on a Local SSD is mounted inside a single VM, not equivalent to Filestore or a shared block service.
- **Machine type restrictions:** not every machine series, instance shape, OS image, or disk interface is supported.

### 1.1. Local SSD Is Ephemeral Block Storage

Understand these two terms separately:

- **Block storage:** the operating system sees a block device such as NVMe or SCSI; operators can create an ext4/XFS filesystem, use a volume manager, or mount it to a directory.
- **Ephemeral:** data lifecycle is **not independent and not guaranteed durable** like a long-term storage volume.

You can create a filesystem, regular files, and directories on Local SSD, yet that **does not turn it into a durable file storage service**. When a VM disappears or a Local SSD is re-provisioned as a blank device, the entire filesystem structure can vanish.

### 1.2. Distinguishing Local SSD and Titanium SSD

Google Cloud offers multiple generations of local drives:

| Attribute | Traditional Local SSD | Titanium SSD |
|---|---|---|
| Concept | Host-attached local SSD | Local SSD generation utilizing Titanium I/O offload architecture |
| Goal | High performance for temporary data | Higher performance on supported machine series |
| Capacity | Many VM types use **375 GiB** per disk | Sizes and counts vary by machine series |
| Interface | NVMe or SCSI depending on machine/OS | Per supported machine, typically NVMe |
| Provisioning | Some machines select disk count, some include fixed drives | Usually attached per machine type |
| Durability | Not guaranteed | Not guaranteed |
| Preserve option on stop/suspend (Preview) | Available in supported configurations | **Not supported** |
| Best suited for | Cache, scratch, intermediate I/O | Cache/scratch, heavy I/O tasks per machine capability |

Do not claim every Local SSD on GCP is **375 GiB**: many Titanium SSD configurations have different per-disk sizes, potentially reaching multiple TiBs. When estimating cost and partitioning, check the **actual capacity for your machine type**.

## 2. Comparing Storage Options

| Service | Access model | Durability level | Typical use |
|---|---|---|---|
| **Local SSD / Titanium SSD** | Local block device inside VM | Ephemeral, not guaranteed across host loss/stop | Cache, sort/spill, batch scratch, regenerable data |
| **Persistent Disk** | Block volume over storage infrastructure | Durable, exists independently of VM per policy | Boot disks, data disks, apps needing persistent files |
| **Hyperdisk** | Block volume with performance tiers by type | Durable, performance/features vary by type | Databases, apps with specific IOPS/throughput targets |
| **Filestore** | Managed NFS file share over network | Centrally managed file storage by tier | Sharing a filesystem across clients |
| **Cloud Storage** | Object storage via API | Durable object storage per configuration | Source datasets, artifacts, checkpoints, backups |
| **RAM or tmpfs** | In-process memory / RAM-backed filesystem | Lost with process/VM lifecycle | Very short-lived buffers, small ultra-fast data |

**Do not choose storage based on IOPS alone.** Evaluate data durability, recovery procedures, file/block/object models, shareability, location, IAM permissions, end-to-end performance, and total cost.

### 2.1. Classify Data Before Choosing

| Data type | Can it live solely on Local SSD? | Conditions |
|---|---|---|
| HTTP/image cache with durable origin | **Yes** | Cache misses must be refetchable; warm-up acceptable |
| Temporary sort/map/shuffle files | **Yes** | Durable inputs, job retries/checkpoints, and idempotency exist |
| Build caches and temporary compiler files | **Yes** | Source/artifact registry exists to rebuild |
| Download staging before commit | **Temporarily only** | Cannot be considered complete until written durably |
| Logs for auditing or investigation | **No**, if sole copy | Ship to Cloud Logging or durable storage |
| Database primary data, sole WAL/transaction log | **No** | Needs durability/replication/proper recovery workflows |
| User-uploaded files | **No**, if sole copy | Persist to object/durable block storage before returning success |
| Final batch checkpoints | **No**, if sole copy | Sync to durable storage on schedule |
| Business sessions, orders, payments | **No** | Write durably; design idempotency/transactions |
| Model weights downloaded from Cloud Storage | **Yes** for cached copy | Reliable primary source and warm-up mechanism exist |

**Practical rule:** if wiping the Local SSD directory and rerunning the workload from remaining data sources cannot meet your RPO/RTO requirements, that data **must not live solely on Local SSD**.

## 3. Which Architectures Fit Local SSD?

### 3.1. Cache-Aside / Read-Through Cache

Example of a Java API reading images or reference data from Cloud Storage:

~~~mermaid
sequenceDiagram
    participant U as API client
    participant APP as Java service
    participant SSD as Local SSD cache
    participant GCS as Cloud Storage origin
    U->>APP: Request object X
    APP->>SSD: Check cache key for X
    alt Cache hit
        SSD-->>APP: Data X
    else Cache miss
        APP->>GCS: GET object X
        GCS-->>APP: Data X
        APP->>SSD: Store cache X (atomic write)
    end
    APP-->>U: Return response
~~~

If Local SSD loses data, cache misses spike and the system reloads from Cloud Storage. The **risk** is a cache stampede (many requests fetching the same object concurrently), raising latency, API fees, and network usage. Implement concurrency limits, request coalescing, eviction, TTLs, and quotas.

### 3.2. Batch Scratch + Checkpoint

Example of a Java batch job reading 500 GB of input from Cloud Storage, decompressing/sorting on Local SSD, and writing final output to another bucket.

~~~mermaid
flowchart LR
    IN["Cloud Storage\nImmutable input"] --> LOAD["Java batch worker"]
    LOAD --> TMP["Local SSD\nChunks, temp files, sorting"]
    TMP --> VALID["Verify checksum, format"]
    VALID --> OUT["Cloud Storage\nDurable output"]
    OUT --> META["Checkpoint/job metadata\nDurable DB or manifest"]
    FAIL["Host/VM failure"] -. "Rerun from checkpoint" .-> LOAD
~~~

Principles:

1. Inputs and job definitions are **durable**.
2. Scratch files are expendable; every processing step can be **rerun**.
3. After each chunk, write output durably and commit the checkpoint **only after verifying output**.
4. Job retries do not duplicate data or corrupt results.
5. When booting with a blank disk, the worker can **reinitialize the filesystem/cache in a controlled manner**.

### 3.3. Flash-Optimized Workloads Requiring Durable Copies

Some databases or search engines use local flash for speed, while durability comes from **replication, WAL on durable storage, backups, quorum, and recovery architecture**. Never say "a database running on Local SSD is safe" merely because a cluster has three nodes; you must understand asynchronous replication, failure domains, quorum, split-brain, replica state, and RPO.

## 4. Provisioning Limits, Machine Series, and Interfaces

### 4.1. Provisioning Local SSD at VM Creation

You cannot create a VM first and attach Local SSDs later like Persistent Disks. Depending on machine series:

- **N2, N2D, and some older generations:** you can choose the number of supported Local SSDs at VM creation, e.g., using the gcloud **--local-ssd** flag.
- **C3/C3D, C4/C4A/C4D/C4N, and similar machines:** select a machine type with the **-lssd** suffix to get the corresponding number of drives attached.
- **Certain storage-optimized/GPU/AI machine series:** Local SSD or Titanium SSD comes bundled with the machine by default.

Supported machine series, disk counts, capacities, and zones can change. **E2 shared-core** machines do not support Local SSD; do not pick the cheapest machine assuming you can attach Local SSD.

### 4.2. NVMe and SCSI

| Criterion | NVMe | SCSI |
|---|---|---|
| Potential performance | Typically higher | May be lower depending on configuration |
| Requirements | Supported OS/driver and machine series | Only on machines/OSes that still support it |
| Linux path naming | Usually stable symlink under **/dev/disk/by-id/google-local-nvme-ssd-...** | Usually under **/dev/disk/by-id/google-local-ssd...** |
| Recommendation | Prefer when machine and image support it | Use when the environment requires SCSI and documentation permits |

Some newer machine generations support **NVMe** only. With custom Linux images, compatible kernels/drivers are required; using Compute Engine public OS images is usually simpler. Do not force SCSI just because an old tutorial references **/dev/sdb**.

### 4.3. Capacity Does Not Mean Linear Performance

IOPS/throughput limits depend on:

- Number of Local SSD disks.
- NVMe/SCSI interface and drive generation.
- Machine type and enough vCPUs to drive I/O.
- Block size, queue depth, thread count, and read/write pattern.
- Filesystem, RAID, kernel/drivers, and cgroup/I/O limits.
- Whether the workload is CPU-bound or network-bound.

Published benchmark figures represent **maximums under specific test conditions**, not guaranteed throughput for a Java process running live business logic. Benchmarks must distinguish **random IOPS** from **sequential MB/s**, **p50/p95/p99 latency**, and cache hit rates.

### 4.4. Encryption and Data Security

Compute Engine **automatically encrypts Local SSD data when written to the device**. However, per current Local SSD documentation, **customer-managed encryption keys (CMEK) or customer-supplied encryption keys (CSEK) are not supported** for Local SSD.

If regulations mandate that all data at rest be encrypted with **organization-controlled keys**, do not default to Local SSD; evaluate application-layer encryption and compliance requirements, or store the data on storage supporting CMEK.

Local SSD still resides within the VM's filesystem, so guest-OS permissions (user/group, file permissions, process isolation), VM IAM, SSRF defenses, and application security remain vital. Default encryption **does not replace** access controls.

## 5. Hands-on A — Inspecting the VM and Local SSD (Read-Only)

Before creating/formatting, verify **project, zone, identity, and attached disks**. The following commands are read-only and do not modify resources.

~~~bash
PROJECT_ID="YOUR_PROJECT_ID"
ZONE="asia-southeast1-a"
VM="scratch-worker-01"

gcloud auth list
gcloud config list project

# Inspect status, machine type, and disk attachments.
gcloud compute instances describe "$VM" \
  --project="$PROJECT_ID" \
  --zone="$ZONE" \
  --format="yaml(name,id,status,machineType,disks,scheduling,labels)"

# List VMs in the same zone to cross-check names/machines.
gcloud compute instances list \
  --project="$PROJECT_ID" \
  --filter="zone:$ZONE" \
  --format="table(name,zone,status,machineType)"
~~~

In the **disks** field, Local SSD usually appears with disk type **SCRATCH**; persistent boot/data disks have type **PERSISTENT**. However, the metadata layout for a machine series with bundled Local SSDs may differ. Always cross-check the machine type and product documentation rather than identifying drives by disk count alone.

Inside the Linux guest, via an authorized SSH/IAP connection:

~~~bash
# READ-ONLY — list block devices, filesystems, and mount points.
lsblk -o NAME,TYPE,SIZE,FSTYPE,MOUNTPOINT,MODEL
ls -l /dev/disk/by-id/google-local* 2>/dev/null || true
df -hT
findmnt
~~~

Record device paths, sizes, and **current FSTYPE**. If a drive already has a filesystem/data, **do not reformat it** merely because it carries a "local" label. For VMs serving active applications, never alter mount points, LVM, or RAID without owner review.

## 6. Hands-on: Creating a VM with Local SSD

VM creation commands can incur charges. Run them only in a **lab project with proper authorization and budget**, never in production. Verify machine type, zone, image, and subnet compatibility before running.

### 6.1. N2 VM with One NVMe Local SSD

~~~bash
PROJECT_ID="YOUR_PROJECT_ID"
ZONE="asia-southeast1-a"
SUBNET="YOUR_EXISTING_SUBNET"
VM="scratch-worker-01"

# CREATES REAL RESOURCES — run only in a lab project.
gcloud compute instances create "$VM" \
  --project="$PROJECT_ID" \
  --zone="$ZONE" \
  --machine-type="n2-standard-8" \
  --image-family="debian-12" \
  --image-project="debian-cloud" \
  --subnet="$SUBNET" \
  --no-address \
  --local-ssd="interface=NVME" \
  --labels="environment=development,application=scratch-lab"
~~~

The **--local-ssd** flag is used with machine series such as N2 that let you specify drives at VM creation. To attach multiple drives within machine-type limits, repeat **--local-ssd** accordingly. **--no-address** omits an external IPv4 address; SSH or OS updates may require IAP, Cloud NAT, or another management path.

For machine series that bundle Local SSDs with the machine—such as certain **C3/C4 -lssd** types—do not pass the flag above; instead choose a **machine type with the -lssd suffix** per documentation:

~~~bash
# Illustrative example; availability depends on zone and quota.
gcloud compute instances create "scratch-c3-lab" \
  --project="$PROJECT_ID" \
  --zone="$ZONE" \
  --machine-type="c3-standard-8-lssd" \
  --image-family="debian-12" \
  --image-project="debian-cloud" \
  --subnet="$SUBNET" \
  --no-address
~~~

You cannot attach additional Local SSDs to an existing VM. To change Local SSD capacity, you normally must **create a new appropriate VM** and copy any data worth keeping to durable storage before replacing the machine.

### 6.2. Inspect Configuration

~~~bash
gcloud compute instances describe "$VM" \
  --project="$PROJECT_ID" --zone="$ZONE" \
  --format="yaml(name,id,status,machineType,disks,networkInterfaces)"
~~~

Select the exact **project, zone, and VM ID**. After creation, Local SSDs are normally unformatted and unmounted for application use.

## 7. Safe Formatting, Mounting, and Auto-Mounting on Linux

**Warning:** **mkfs** erases data and destroys any existing filesystem. Only format a **new, completely empty Local SSD after verifying the exact device**. Never blindly format all **/dev/nvme*** devices because the boot disk may also use NVMe.

### 7.1. Verify Device Symlink

~~~bash
# READ-ONLY — run on the Linux lab VM.
lsblk -o NAME,TYPE,SIZE,FSTYPE,MOUNTPOINT,MODEL
ls -l /dev/disk/by-id/google-local* 2>/dev/null || true

DEV="/dev/disk/by-id/google-local-nvme-ssd-0"
test -b "$DEV" && readlink -f "$DEV"
sudo blkid "$DEV" || true
findmnt --source "$DEV" || true
~~~

The name **google-local-nvme-ssd-0** is an NVMe example. If the VM uses SCSI or a different machine series, verify the name from actual output. Match Compute Engine metadata **type=SCRATCH**, capacity, device name, and filesystem before proceeding.

### 7.2. Create Filesystem and Mount the New Drive

~~~bash
# DESTRUCTIVE ON DEV — run only after confirming the drive is empty.
sudo mkfs.ext4 -F "$DEV"

sudo mkdir -p /mnt/localssd
sudo mount "$DEV" /mnt/localssd

# READ-ONLY: verify actual mount.
findmnt /mnt/localssd
df -hT /mnt/localssd
sudo blkid "$DEV"
~~~

Java applications should write inside a directory with restricted permissions. Do not apply **chmod 777** across the entire mount:

~~~bash
# Assumes appuser/appgroup are managed and already exist on the VM.
sudo install -d -o appuser -g appgroup -m 0750 /mnt/localssd/jobs
ls -ld /mnt/localssd /mnt/localssd/jobs
~~~

If using XFS, follow the corresponding filesystem creation procedure after verifying image support; choose based on I/O characteristics and operational needs.

### 7.3. `/etc/fstab` with `nofail`

Read the UUID:

~~~bash
sudo blkid -s UUID -o value "$DEV"
~~~

Only after verifying the UUID, add the corresponding line with an administrative editor:

~~~text
UUID=<ACTUAL_UUID> /mnt/localssd ext4 defaults,nofail 0 2
~~~

The **nofail** option lets the OS boot even if the drive is absent. However, **fstab does not protect data**: if the VM receives a blank Local SSD after an outage, the old filesystem UUID is gone and the mount will not occur. Startup logic must detect that condition rather than running **mkfs unconditionally**.

### 7.4. Safe Startup Logic

1. Enumerate the exact Local SSD via metadata/by-id and expected size.
2. If a valid filesystem exists, **mount it without formatting**.
3. If the new disk is genuinely blank, reinitialize only if policy confirms **all data is expendable cache/scratch**.
4. Create directories and user/group ownership; connect to durable data sources.
5. Warm the cache with concurrency limits and monitor miss rates.
6. Mark the application **readiness=healthy** only after it can safely serve requests.

If a normal reboot preserves data, a script that unconditionally reformats causes **operator-inflicted data loss**. This is a critical bug to avoid.

## 8. RAID 0 Across Multiple Local SSDs

When a VM has multiple Local SSDs, **mdadm RAID 0** can aggregate capacity and stripe I/O across drives. RAID 0 **has no mirroring or parity**: losing a single member can destroy the entire array's data.

~~~mermaid
flowchart TD
    APP["Java workload"] --> MNT["/mnt/localssd"]
    MNT --> FS["Filesystem ext4/XFS"]
    FS --> MD["/dev/md0 RAID 0"]
    MD --> D0["Local SSD 0"]
    MD --> D1["Local SSD 1"]
    FAIL["One device fails/vanishes"] -. "Entire array may be lost" .-> MD
~~~

### 8.1. Lab Example with Two New Drives

**Destructive to data:** run only after confirming both drives are **verified Local SSDs, empty, and unused by other VMs/processes**.

~~~bash
# READ-ONLY — confirm both drives are actually present.
ls -l /dev/disk/by-id/google-local-nvme-ssd-*
lsblk -o NAME,TYPE,SIZE,FSTYPE,MOUNTPOINT

# CREATE RAID 0 — overwrites metadata on both drives.
sudo mdadm --create /dev/md0 \
  --level=0 --raid-devices=2 \
  /dev/disk/by-id/google-local-nvme-ssd-0 \
  /dev/disk/by-id/google-local-nvme-ssd-1

# FORMAT ARRAY — destroys data on /dev/md0.
sudo mkfs.ext4 -F /dev/md0
sudo mkdir -p /mnt/localssd
sudo mount /dev/md0 /mnt/localssd

# READ-ONLY.
sudo mdadm --detail /dev/md0
findmnt /mnt/localssd
df -hT /mnt/localssd
~~~

To auto-mount after reboot, you must configure **mdadm assembly** and UUID-based fstab properly. Do not assume **/dev/md0** is always ready at OS boot. RAID 0 is suitable only for rebuildable data: it is **not a way to increase durability**.

## 9. Local SSD Data Lifecycle

Distinguishing between **guest reboot**, **stop/start**, **live migration**, **host error**, **preemption**, and **delete** determines whether data survives or vanishes.

| Event | Local SSD data retention | Application rule |
|---|---|---|
| **Normal guest OS reboot** | Usually **preserved** | Remount and verify filesystem |
| **Live migration host maintenance (when supported)** | **Preserved** in documented cases | Do not treat as a backup |
| **Host error/host failure** | **Best-effort**, can be lost | Rebuild from durable origin |
| **Default VM stop** | **Discards data** | Copy data worth keeping to durable storage beforehand |
| **Default VM suspend** | **Discards data** | RAM suspend does not protect Local SSD |
| **Stop/suspend with preserve (Preview)** | May preserve if VM/disk eligible | Has quotas/fees/limits; does not replace backups |
| **Spot/preemptible preemption** | **Data lost** | Checkpoint and retry |
| **Delete VM** | **Local SSD lost** | No option to retain Local SSD independently |
| **Host maintenance requiring termination** | Can be lost per machine/restart policy | Check host policy and verify recovery |
| **Disk unreachability/misconfiguration** | Not guaranteed | Do not reformat before diagnosing |

**Do not make blanket claims that "restart loses data"**: a guest-OS reboot is not the same as an **API stop followed by start**. Conversely, even if Local SSD survives a reboot, it still fails to meet durable storage criteria.

### 9.1. REPAIRING and Recovery Timeout

After a host error, Compute Engine may place the VM into **REPAIRING** while attempting to recover the Local SSD. The **localSsdRecoveryTimeout** field sets the wait window in hours; documentation supports **0–168 hours**, with defaults varying by machine series.

- **0:** prioritizes fast restart and discards unrecoverable Local SSD data.
- **Greater than 0:** allocates time to attempt recovery, though the application may remain unavailable while the VM is REPAIRING.
- If the timeout expires without recovery: the VM may start with **blank, unformatted Local SSDs**.
- Behavior also depends on **automaticRestart** and host maintenance policies.

Do not always pick 168 hours thinking it is "safest." If caches can be rebuilt and standby nodes exist, failing over quickly to maintain SLOs can be far better than waiting days for host repair.

### 9.2. Preserving Local SSD on Stop/Suspend (Preview)

Google Cloud offers a capability to preserve traditional Local SSD data during stop/suspend by copying it to durable storage and restoring it upon start/resume. Note the caveats:

- **Preview / pre-GA**, not a default GA feature.
- **Does not support Titanium SSD**.
- Not supported if the VM has **more than 48 Local SSD disks**.
- Cannot request preservation via **Google Cloud console** per current guidance; requires gcloud/REST.
- Consumes **Persistent disk standard GB quota** and incurs storage charges for preserved data.
- Data can still be lost/corrupted if hardware fails during copying; restoration may run in the background.
- Spot/preemptible VMs can lose data if preempted while preserving.

**This is not a backup**. If data matters, copy it to Cloud Storage, Hyperdisk, or Persistent Disk and verify readability before stopping/suspending.

### 9.3. Example: Stopping and Discarding Data

~~~bash
# STATE CHANGE, DELETES LOCAL SSD DATA.
# Run only on a lab VM after confirming cache/scratch is expendable.
gcloud compute instances stop "$VM" \
  --project="$PROJECT_ID" \
  --zone="$ZONE" \
  --discard-local-ssd=true
~~~

If preservation is needed under supported conditions, documentation uses **gcloud beta** with **--discard-local-ssd=false**; evaluate quotas/costs/Preview limits before adopting it. Do not use with Titanium SSD.

### 9.4. Reset Is Not a Backup Procedure

Resetting a VM generally preserves locally attached drives, yet can lose unflushed writes and corrupt the filesystem. Do not use reset to maintain transactional consistency. Critical applications need graceful shutdowns, checkpoints, and crash-safe design.

## 10. Designing Java Applications Using Expendable Scratch

Local SSD is business-safe only when the application **does not rely on that local copy to recover critical data**.

### 10.1. Classifying Data by RPO/RTO

| Question | If the answer is "no" | Action required |
|---|---|---|
| Can it be reloaded from a durable source? | No | Do not use Local SSD alone |
| Can it be regenerated by retrying the job? | No | Write state and outputs to durable storage |
| Is losing progress since the last checkpoint acceptable? | No | Increase checkpoint frequency or change architecture |
| Can it be rebuilt within the required RTO? | No | Use replicas/hot standby or more durable storage |
| Does the system know when output was committed? | No | Design transactions/manifests/checksums and verification |

**RPO (Recovery Point Objective)** is the acceptable data loss measured in time; **RTO (Recovery Time Objective)** is the target time to restore service. For a pure cache, source data may have near-zero RPO because the origin is durable, yet **RTO** is still impacted by cache warm-up time.

### 10.2. The "Durable-First, Scratch-Second" Workflow

A safe Java batch job should follow this workflow:

1. Store **inputs, job definitions, and checksums** in Cloud Storage or a durable database.
2. Assign a **job ID, attempt ID**, and idempotency key to prevent duplicate output writes.
3. Create a job-specific directory on Local SSD, e.g., **/mnt/localssd/jobs/JOB_ID**.
4. Process intermediate files/chunks on Local SSD.
5. Upload temporary outputs to a durable destination via retrying APIs, verifying checksums/sizes.
6. **Only after outputs are verified**, write the commit manifest or durable checkpoint.
7. Delete scratch files from completed attempts.
8. If the VM/disk fails, read the manifest to skip committed chunks and rerun uncommitted ones.

~~~mermaid
stateDiagram-v2
    [*] --> PENDING
    PENDING --> PROCESSING: Load durable input
    PROCESSING --> UPLOADING: Create scratch output
    UPLOADING --> COMMITTED: Durable upload verified + checkpoint
    PROCESSING --> RETRY: VM/Local SSD failure
    UPLOADING --> RETRY: Upload failure before commit
    RETRY --> PROCESSING: Recreate scratch
    COMMITTED --> [*]: Cleanup local cache
~~~

**Write output first, checkpoint second** to avoid a state where "the checkpoint says done yet output is not durable." When retrying uploads, design **object names, generation preconditions, or manifests** to prevent unintended overwrites; cases where an upload succeeds yet committing the checkpoint fails must be handled idempotently.

### 10.3. Java: Creating Scratch Files and Cleanup

The following plain Java example **writes no durable business data**; it illustrates scoped scratch usage only. **SCRATCH_ROOT** must point to a mounted filesystem with appropriate application permissions.

~~~java
import java.nio.charset.StandardCharsets;
import java.nio.file.Files;
import java.nio.file.Path;

public final class ScratchWork {
    private static final Path SCRATCH_ROOT =
            Path.of("/mnt/localssd/jobs");

    public static void runJob(String jobId) throws Exception {
        // Directory must exist on the Local SSD filesystem with proper ACLs.
        if (!Files.isDirectory(SCRATCH_ROOT) ||
            !Files.isWritable(SCRATCH_ROOT)) {
            throw new IllegalStateException(
                    "Scratch directory is not ready or not writable"
            );
        }

        Path temp = Files.createTempFile(
                SCRATCH_ROOT, "attempt-", ".tmp");

        try {
            // Store temporary data only; never store the sole copy of an order.
            Files.writeString(
                    temp, "chunk for " + jobId,
                    StandardCharsets.UTF_8
            );

            // TODO:
            // 1. Process temporary data in temp.
            // 2. Write output to Cloud Storage/durable DB.
            // 3. Verify output and COMMIT durable checkpoint.
            // 4. Report SUCCESS only after step 3 completes.
        } finally {
            Files.deleteIfExists(temp);
        }
    }
}
~~~

This is a minimal example of **file lifecycle**, not a complete pipeline. The **finally** block may not execute if the VM/host fails or is killed forcibly, so alongside in-process cleanup you also need **periodic cleanup by job age**.

### 10.4. Cache Eviction and Preventing Disk Exhaustion

When a cache nears full capacity, Linux/applications can hit **ENOSPC**, failing jobs or blocking other components from writing. Use:

- **TTLs** for cache entries based on data characteristics.
- **LRU/LFU** or an appropriate eviction policy.
- **Per-job quotas** and concurrent-job limits.
- Separate directories for caches, scratch, staging, and logs.
- High-watermark thresholds, e.g., begin evicting old cache entries before reaching 90%.
- Rate limiting when warming the cache after failover to avoid overwhelming Cloud Storage/databases.
- Rules **forbidding deletion of actively uploading outputs** or uncommitted jobs.

Never wipe the entire mount via cron **rm -rf /mnt/localssd/** as a "quick cleanup": that can easily delete files actively held by running processes. Use a manifest/job registry and age/ownership rules for controlled cleanup.

## 11. Copying/Persisting Data from Local SSD to Durable Storage

### 11.1. No Native Snapshots for Local SSD

Compute Engine does not support creating **snapshots, clones, disk images, or machine images** as backups of Local SSD data. If data must be retained, it must be **copied out before it is lost**.

Common destinations:

| Destination | When to use |
|---|---|
| **Cloud Storage** | Batch inputs/outputs, object-based checkpoints, artifacts, log archives |
| **Persistent Disk** | Need a filesystem/block data volume that can reattach to a VM |
| **Hyperdisk** | Need durable block storage with specific performance tiers |
| **Managed database** | Queryable, consistent state metadata/checkpoints/transactions |
| **Filestore** | Multiple clients needing a shared NFS filesystem |

### 11.2. Example Copy to Cloud Storage

Assume the VM uses a **service account granted write permission only to the appropriate bucket/checkpoint prefix**, and **gcloud storage** is available:

~~~bash
# READ-ONLY — inspect scratch directory before copying.
du -sh /mnt/localssd/jobs/job-123
find /mnt/localssd/jobs/job-123 -maxdepth 1 -type f

# WRITES TO CLOUD STORAGE — run only with a valid lab bucket.
BUCKET="YOUR_DURABLE_BUCKET"
gcloud storage cp --recursive \
  /mnt/localssd/jobs/job-123 \
  "gs://$BUCKET/checkpoints/job-123/"

# READ-ONLY — verify remote output after copying.
gcloud storage ls "gs://$BUCKET/checkpoints/job-123/"
~~~

Exit code 0 from a copy command **is insufficient for financial or sensitive data workflows**. Verify complete file lists, sizes, checksums, or generations before writing the checkpoint/manifest. For mutable datasets, lock writes or use application-consistent snapshots/checkpoints prior to copying.

**Never place files containing raw credentials/secrets** into backup buckets; IAM, bucket policies, encryption, and retention must match data sensitivity.

### 11.3. What Happens If an Upload Fails Mid-Way?

A safe design requires:

- Writing outputs under an attempt-specific **staging prefix/object name**.
- Using retries with backoff and timeouts.
- Verifying upload completion via checksums/metadata.
- Committing state metadata in a durable database or manifest.
- Recognizing already-completed states on retry to avoid double-counting.
- Cleaning up expired staged artifacts per retention/cleanup policy.

With Cloud Storage, use **generation preconditions** or appropriate versioning features to avoid blind overwrites. Never treat a local filesystem rename on Local SSD as proof that output has been persisted in Cloud Storage.

## 12. How Do GKE, Cloud Run, and Managed Services Use Local SSD?

### 12.1. GKE: Ephemeral Storage Resides on the Node

GKE runs pods on Compute Engine nodes, so **Local SSD can be used** in supported node pool configurations, such as:

- **Local SSD-backed ephemeral storage** for pod ephemeral data when configured properly.
- **Raw block Local SSD** managed according to supported service/cluster mechanisms.
- Temporary files, build scratch, and sort/shuffle space for Kubernetes workloads.

However:

- **emptyDir** does not automatically guarantee Local SSD across all node pools. Verify backing storage configuration and GKE version.
- **Kubernetes ephemeral-storage requests/limits** affect pod scheduling/eviction, yet do not make data durable.
- When a pod **is rescheduled to another node**, local scratch/cache on the old node does not follow the pod.
- **PodDisruptionBudget** mitigates planned disruptions; it does not keep Local SSD alive across host failures.
- GKE node pools/controllers can recreate node VMs; never manually stop/delete nodes via Compute Engine CLI expecting to "preserve data."

Design Pods to **reinitialize caches, reload inputs, handle retries, and use checkpoints**. If data must be shared or long-lived, use a PersistentVolume with an appropriate CSI driver/storage class, Filestore, Cloud Storage, or a database.

### 12.2. Cloud Run Is Not a User-Managed VM with Local SSD

Cloud Run is a serverless environment. The writable filesystem inside a Cloud Run instance/container **is not a Compute Engine Local SSD that you can attach/format via `gcloud compute`**. Temporary filesystem data can disappear when an instance is replaced; never use it as a business data store.

When migrating a Java application from Compute Engine to Cloud Run:

1. Replace hardcoded **/mnt/localssd** scratch paths with environment-appropriate storage configuration.
2. Do not assume a Cloud Run instance keeps caches across scale-to-zero or redeployments.
3. Move outputs and business state to Cloud Storage/Cloud SQL/Firestore as appropriate.
4. Monitor memory/ephemeral filesystem limits and concurrent requests.
5. Evaluate cost/latency when replacing local caches with Cloud Storage.

### 12.3. Managed Databases

Cloud SQL and other managed database services do not let users arbitrarily attach Local SSD block devices to service hosts like Compute Engine VMs. Review the **product-specific** temporary storage, I/O, and backup mechanisms. Even if a database engine uses internal local flash within its architecture, that **does not place customer data onto a user-managed Compute Engine Local SSD**.

### 12.4. Spot VMs and Batch Jobs

Spot VMs cut compute costs for fault-tolerant batch workloads, yet **preemption wipes Local SSD data**. Proper design:

- Use immutable inputs in Cloud Storage.
- Split jobs into small chunks with retries/idempotency.
- Write durable checkpoints/outputs after every chunk.
- When a new VM starts, rebuild Local SSD/cache before accepting work.
- Do not rely on shutdown notices to guarantee enough time to flush all data.

## 13. Observing Performance and Capacity

Local SSD delivers very high performance, yet real-world issues commonly involve **full filesystems, rising p99 I/O latency, lost RAID members, or load spikes during cache warm-up**.

### 13.1. Metrics to Track

| Group | Example metrics/observations | Action |
|---|---|---|
| **Capacity** | Filesystem used %, free inodes | TTL/eviction, limit job counts and outputs |
| **I/O** | Read/write IOPS, MiB/s, await/latency | Analyze block size, queue depth, machine bottlenecks |
| **Cache** | Hit rate, miss rate, eviction rate | Improve cache keys/TTLs and warm-up |
| **Batch** | Bytes processed, chunk retries, checkpoint age | Reduce work lost on VM failure |
| **Availability** | VM RUNNING/REPAIRING, Local SSD remount failures | Alert/failover to another worker |
| **Data safety** | Durable checkpoint lag, uncommitted output | Alert on RPO or pause accepting new jobs |
| **Cost** | Local SSD provisioned GiB-hours, network/API calls | Right-size machines, disk counts, cache policies |

### 13.2. Read-Only Linux Commands

~~~bash
# Capacity and inodes.
df -hT /mnt/localssd
df -i /mnt/localssd

# Mount point/source, non-destructive.
findmnt /mnt/localssd
lsblk -o NAME,TYPE,SIZE,FSTYPE,MOUNTPOINT

# Size of scratch subdirectories.
du -sh /mnt/localssd/* 2>/dev/null || true

# If sysstat is installed:
iostat -xz 1 5
~~~

Confirm **/mnt/localssd is actually mounted** before writing data. If the mount is missing, an application might accidentally write into a directory of the same name on the boot disk and fill up the **Persistent Disk**.

### 13.3. Non-Destructive Benchmarking

You can use **fio** to measure I/O, yet many benchmark commands targeting raw block devices (**/dev/nvme***, **blkdiscard**, raw writes) **destroy data**. In production, never run destructive benchmarks just to compare against Google's published maximums.

When measuring in a lab:

- Use VMs/disks **containing no data worth keeping**.
- Prefer file-based benchmarks inside a dedicated directory rather than raw block disks.
- Document block size, ioengine, queue depth, job count, random/sequential, and read/write mix.
- Monitor CPU, RAM, and throttling alongside IOPS.
- Do not run benchmarks while latency-sensitive applications are active.

## 14. Security and Governance Responsibilities

Local SSD encrypts data automatically when writing to disk, yet data safety requires additional layers:

- **IAM:** only authorized service accounts/users should hold VM management permissions; avoid overly broad roles.
- **Guest OS access:** user/group ownership, filesystem permissions, process isolation; avoid letting untrusted workloads write to shared directories.
- **Secrets:** never keep long-lived access tokens, service account JSON keys, or private keys in cache/scratch.
- **Network:** VPC firewalls, DNS, routes, and IAM for Cloud Storage/DB when persisting outputs.
- **Data lifecycle:** PII classification, TTL/retention configuration, encryption requirements; if CMEK is mandatory, account for Local SSD's limitation.
- **Audit:** log changes to VM machine types, disk configurations, stops/suspends, deletions, and operators.
- **Backups:** checkpointing and restore drills, not just enabling logging.

### 14.1. Sensitive Data and Secure Deletion

Because Local SSD is not an independent durable disk, users cannot detach it to move to another VM; deleting the VM deletes the disk with it. Still, that does not replace **data minimization, least privilege, and retention controls**. Do not write PII or payment credentials to scratch without business justification and governance controls.

Do not treat a guest-OS **rm** command as proof of physical erasure under compliance standards. For strict audit requirements, rely on data storage/deletion policies and Google Cloud documentation on encryption/media retirement, while minimizing sensitive data placed on Local SSD in the first place.

## 15. Cost and Sizing Choices

Local SSD is **billed by provisioned capacity** (provisioned GiB) over the lifetime of the VM holding the drive, not merely by bytes written. Pricing and discounts also depend on region, machine series, Local SSD/Titanium SSD generation, and consumption model.

| Factor | Impact on total cost |
|---|---|
| Local SSD capacity | Billed across all provisioned capacity, including unused space |
| Machine type | Must pick configurations offering compatible vCPU/RAM and Local SSD |
| VM lifetime | Local SSD ties to VM lifecycle; check SKU billing during stop/suspend |
| Stop/suspend preserve | May add storage charges for preserved data and consume PD standard quota |
| Cache misses | Increases Cloud Storage reads/network traffic and rebuild CPU |
| Over-frequent checkpoints | Increases API/write requests and storage costs |
| Over-infrequent checkpoints | Increases rerun time and progress lost on failure |
| Spot VMs | Offer Spot pricing for Local SSD, but higher preemption risk |
| Logs and Monitoring | May incur ingestion/retention fees based on usage |

### 15.1. Simple Illustrative Calculation (Hypothetical)

Suppose an N2 VM has one 375 GiB drive at an illustrative unit price of **0.10 units/GiB-month**. Running/paying for the disk for a full month gives a baseline Local SSD cost of:

\[
375 \times 0.10 = 37.5\text{ units/month}
\]

This number **is not real Google Cloud pricing**. To compare options, add compute, boot disk, Cloud Storage, network egress, other snapshots/backups, and rerun time after host failures.

If a job uses only 40 GiB of scratch, you may still pay for the entire 375 GiB drive (or all Local SSD capacity bundled with the machine type). Measure **capacity utilization** and choose an appropriate machine type rather than adding drives simply because Local SSD is fast.

### 15.2. Verifying Bills

Use **Cloud Billing Reports** filtered by project and grouped by Service/SKU to locate lines related to Compute Engine Local SSD. For invoice reconciliation, use the **Cost table** and exact invoice period. Cross-check against VM create/delete timestamps, disk types, credits/discounts, and billing reporting lag.

**Do not use used GB from `df` directly to estimate Local SSD charges**, since billing is based on provisioned capacity rather than current file usage.

## 16. Runbook: Local SSD Vanished or Filesystem Won't Mount

When a VM restarts after a host error with blank Local SSDs, the top priority is not "recover an old drive at all costs," but **preventing the application from serving bad data**, confirming disk state, and **safely recovering from durable origins**.

### 16.1. Incident Response Flow

~~~mermaid
flowchart TD
    ALERT["Alert: scratch unavailable / I/O errors"] --> STATE["Check VM status RUNNING/REPAIRING"]
    STATE --> DEV["Check devices, lsblk, mounts, logs"]
    DEV --> Q{"Filesystem/data still readable?"}
    Q -- "Yes" --> CHECK["Verify checksums, health, quota, app"]
    Q -- "No" --> STOP["Stop accepting new jobs, verify data classification"]
    STOP --> SAFE{"Contains only regenerable cache/scratch?"}
    SAFE -- "No / uncertain" --> ESC["Escalate, preserve evidence, verify owner"]
    SAFE -- "Yes" --> INIT["Initialize blank device per runbook"]
    INIT --> RESTORE["Fetch durable input/checkpoint, rebuild cache"]
    CHECK --> READY["Health/readiness/metrics"]
    RESTORE --> READY
    READY --> RESUME["Resume traffic under monitoring"]
~~~

**Never run `mkfs` while REPAIRING** or before confirming whether Local SSD is truly lost permanently. Doing so can destroy still-recoverable data, hinder root-cause analysis, and fail to resolve host availability.

### 16.2. Initial Read-Only Commands

~~~bash
# READ-ONLY from a machine with project management permissions.
gcloud compute instances describe "$VM" \
  --project="$PROJECT_ID" --zone="$ZONE" \
  --format="yaml(name,id,status,disks,scheduling)"

# When the VM is reachable via SSH and the app permits inspection:
lsblk -o NAME,TYPE,SIZE,FSTYPE,MOUNTPOINT
ls -l /dev/disk/by-id/google-local* 2>/dev/null || true
findmnt /mnt/localssd || true
df -hT
sudo dmesg --ctime | tail -n 50
~~~

Do not paste raw kernel logs into public tickets: logs may contain sensitive infrastructure details. For production applications, coordinate with SRE and owners when gathering diagnostic data.

### 16.3. Diagnostic Table

| Symptom | Hypothesis | Checks / remediation |
|---|---|---|
| Local SSD device missing | Wrong machine type/VM, host failure, device not attached as expected | Describe VM and `/dev/disk/by-id`; check API/status |
| Disk visible but no filesystem | Drive re-provisioned blank after error/stop | Confirm scratch-only and follow format/mount runbook |
| Filesystem present yet not mounted | Stale fstab UUID, mdadm array not assembled, filesystem error | Check `blkid`, `mdadm`, `dmesg`; do not rush `mkfs` |
| VM in REPAIRING | Attempting recovery per host policy | Check recovery timeout, evaluate RTO and failover plan |
| Disk full | Cache lacks eviction, job temp files not cleaned | `df`/`du`, stop new jobs, delete by manifest/owner |
| Out of inodes despite free GB | Too many small files | `df -i`, clean up by TTL/job |
| App writing to boot disk | `/mnt/localssd` not mounted | `findmnt`, check startup volume guard |
| Latency spike | I/O saturation, queue depth, CPU, app pattern | `iostat` + app tracing, check capacity |
| Data lost after stop/start | Default discard Local SSD behavior | Rebuild from origin, verify job checkpoints |
| Spot worker preempted | Scratch lost, incomplete job attempt | Reschedule job, load checkpoint, and retry |
| Data exists but unreadable | Permissions/UID/GID, filesystem corruption | Check mount/ACLs, notify owner, avoid reset |
| RAID 0 broken | Member lost or array failed to assemble | `mdadm --detail`; rebuild only if scratch is expendable |

### 16.4. Post-Incident Review

Close the incident only when:

1. **Durable data sources** and the latest checkpoint are clearly verified.
2. No job reported success while missing output in the durable origin.
3. Workers/apps are restored and live health checks PASS.
4. Retried jobs did not duplicate writes or corrupt transactions.
5. Mount guards prevented the application from writing onto the boot disk.
6. Owner, timeline, suspected/verified root cause, and recurrence prevention are documented.
7. Post-incident storage, retry, and Cloud Storage API costs are tracked.

## 17. Case Study: Java Data Processing with Local SSD

**Hypothetical scenario:** an e-commerce company runs a **Java batch service** on Compute Engine, ingesting anonymized transaction data from Cloud Storage. Each night, the job reads several hundred GB, sorts and aggregates, and writes Parquet/CSV files for BigQuery analytics. An N2 VM uses Local SSD as scratch. Source inputs and final outputs must be durable, while temp files are regenerable.

### 17.1. Chosen Architecture

~~~mermaid
flowchart LR
    SCHED["Cloud Scheduler / Workflows"] --> JOB["Compute Engine Java worker\nLocal SSD scratch"]
    ORIGIN["Cloud Storage\nimmutable input"] --> JOB
    JOB --> STAGE["Cloud Storage\nattempt-scoped staging output"]
    STAGE --> VERIFY["Verify checksum/size"]
    VERIFY --> MANIFEST["Durable commit manifest"]
    MANIFEST --> BQ["BigQuery / downstream"]
    FAIL["Spot preemption / host error"] -. "Retry from checkpoint" .-> JOB
    LOG["Cloud Monitoring & Logging"] -. "Observability" .-> JOB
~~~

Design rules:

- Inputs are immutable/versioned, never residing solely on Local SSD.
- Workers write scratch chunks and stage outputs per **attempt ID**.
- Durable checkpoints commit only after uploads finish.
- Jobs can rerun multiple times without double-counting totals.
- Caches cold-start cleanly from empty without corrupting results.
- Upon stop/Spot preemption/host failure, a new worker can resume from the checkpoint.
- Logs, IAM, and storage buckets follow least privilege.

### 17.2. A Typical Incident

At 02:30, a host fails and Compute Engine cannot recover the Local SSD. The VM reboots with a blank drive. The old startup script mounts by UUID and fails. The Java service starts anyway and writes scratch files to **/mnt/localssd**, which is actually on the boot disk, filling the boot disk and causing co-located jobs to fail.

**The root cause was not merely Local SSD data loss**. The design also lacked:

- A guard verifying **findmnt** and the exact block device before enabling readiness.
- Safe scratch initialization for a brand-new disk scenario.
- Per-chunk checkpoints instead of end-of-job only.
- Alerts for full boot disks and unavailable local scratch mounts.
- Automated job rerouting to healthy workers when a VM becomes unavailable.

### 17.3. Measurable Remediation

1. During startup, verify Local SSD is mounted before Java accepts jobs.
2. Create a filesystem only if the disk is confirmed blank scratch and authorized by owner policy.
3. Add durable manifests/checkpoints after every chunk.
4. Separate staging and committed outputs; enforce idempotent retries.
5. Add metrics for cache hit/miss, disk used %, mount state, and checkpoint age.
6. Enforce temp-file TTLs, `appuser` permissions, and concurrent-job limits.
7. Run chaos tests in a lab by **deliberately stopping/discarding Local SSD**, verifying full pipeline recovery from Cloud Storage.
8. Compare job cost and p95 duration before/after, rather than optimizing purely for peak IOPS.

**Success metric:** a worker losing Local SSD loses zero committed transactions/outputs; jobs retry cleanly, meet target RPO/RTO, and never treat local drives as the sole data store.

## 18. Practice Exercises and Self-Check

### 18.1. Exercise A — Choosing the Right Storage Type

For each scenario below, select Local SSD, Persistent Disk/Hyperdisk, Filestore, or Cloud Storage and explain why:

| Scenario | Suggestion |
|---|---|
| Temp sort files with durable inputs and rerun support | Local SSD |
| Java VM boot disk | Appropriate Persistent Disk or Hyperdisk |
| Two VMs needing a shared filesystem over NFS | Filestore |
| User-uploaded images needing long-term retention | Cloud Storage |
| Sole WAL of an unreplicated database | Never place solely on Local SSD |
| Cache of model weights reloadable from a bucket | Local SSD may be suitable |
| Raw source dataset retained for many months | Cloud Storage or durable storage |
| Uncommitted upload staging | Local SSD is temporary only; must persist durably before SUCCESS |

### 18.2. Exercise B — Determining Data State

Answer after each event:

1. A Linux VM performs a **reboot** inside the guest OS. Does it automatically wipe all Local SSDs?
2. The VM is **stopped** from Compute Engine with default behavior. When restarted, what happens to Local SSD?
3. The VM uses **Titanium SSD**. Can the Preview Local SSD preserve option be used on suspend?
4. A running Spot VM is **preempted**. Can the job rely on old scratch files to continue?
5. The VM hits a host error and enters **REPAIRING**. Should you immediately re-run `mkfs` on the device?
6. The VM is **deleted**. Can the Local SSD be retained as a standalone persistent disk?
7. You create **RAID 0 across two Local SSDs**. Does losing one device affect the entire array?
8. Does taking a boot disk snapshot copy all Local SSD data?

**Answers:** (1) No; data is normally preserved across guest reboots; (2) discarded by default; (3) no; (4) no; (5) no; (6) no; (7) yes; (8) no.

### 18.3. Exercise C — Finding Bugs in a Startup Script

Read the following script—**do not execute**:

~~~bash
# BAD EXAMPLE — DO NOT RUN.
sudo mkfs.ext4 -F /dev/nvme0n1
sudo mkdir -p /mnt/localssd
sudo mount /dev/nvme0n1 /mnt/localssd
java -jar worker.jar
~~~

**Questions:**

1. Why could hardcoding **/dev/nvme0n1** wipe the boot disk?
2. Why does running `mkfs` on every startup lose data after a reboot?
3. What checks are required before deciding to format?
4. What checks are required before marking the Java service ready?

**Guidance:** cross-check by-id symlinks, instance metadata, and `disk type=SCRATCH`; use `lsblk`/`blkid`/`findmnt`; format only confirmed blank drives; verify the real mount point and durable data sources before serving workloads.

### 18.4. Exercise D — Designing Checkpoints

A batch job has 100 chunks, each taking 2 minutes. If Local SSD fails after chunk 90 and the job only checkpoints at the end, how many minutes must be rerun in the worst case? If checkpointing every 5 chunks, what is the maximum chunks to rerun, assuming no upload/commit issues?

**Suggested answer:** without intermediate checkpoints, up to 180 minutes of processed work may need rerunning; with checkpoints every 5 chunks, at most roughly 5 chunks/10 minutes of work (watching checkpoint boundary timing and in-flight data). Achieving better RPO/RTO requires balancing checkpoint frequency, write fees, and overhead.

### 18.5. Local SSD Inventory and Recovery Record

~~~text
PROJECT_ID:
ZONE:
VM_NAME / VM_ID:
OWNER:
MACHINE_TYPE:
LOCAL_SSD_TYPE: classic / Titanium
DEVICE_INTERFACE: NVMe / SCSI
DEVICE_BY_ID:
NUMBER_OF_DISKS / CAPACITY:
FILESYSTEM / RAID:
MOUNT_PATH:
CACHE_OR_SCRATCH_PURPOSE:
DURABLE_SOURCE_OF_TRUTH:
CHECKPOINT_LOCATION / RPO:
RECOVERY_PROCEDURE / RTO:
SPOT_OR_HOST_POLICY:
LOCAL_SSD_RECOVERY_TIMEOUT:
STOP_SUSPEND_PRESERVE_POLICY:
ENCRYPTION_AND_DATA_CLASSIFICATION:
DISK_USED_PERCENT / CACHE_HIT_RATE:
COST_REVIEW:
TEST_DATE_AND_RESULT:
OPEN_ISSUES:
~~~

Never mark **PASS** by merely predicting recoverability. Record steps actually executed, metrics measured, and saved output evidence.

## 19. Misconceptions to Avoid

| Misconception | Accurate understanding |
|---|---|
| "Local SSD is fast, so it is safer than Persistent Disk." | Performance and data durability are two separate properties. |
| "Putting data on an ext4 filesystem makes it durable." | A filesystem does not fix the ephemeral nature of host-attached storage. |
| "You can add Local SSDs while a VM is running." | Configured only at VM creation; machines with bundled Local SSDs by machine type are a separate case. |
| "Every Local SSD is exactly 375 GiB." | Sizes depend on machine family, especially Titanium SSD. |
| "Rebooting the guest OS always wipes Local SSD data." | Normal guest reboots can preserve data. |
| "Stop/start preserves Local SSD if the VM name stays the same." | By default, Local SSD is discarded on stop. |
| "Preview preserve equals a guaranteed backup." | Subject to machine limits, quotas, fees, and data-loss risks. |
| "Titanium SSD supports Preview preserve." | Not supported per current documentation. |
| "You can snapshot Local SSD directly." | No; copy data worth keeping to durable storage. |
| "RAID 0 increases data availability." | RAID 0 has no redundancy; losing one member can lose the entire array. |
| "fstab with nofail preserves data." | `nofail` only affects boot/mount behavior when the disk is absent. |
| "`/dev/nvme0n1` is always the Local SSD." | Verify by-id symlinks, filesystems, metadata, and disk types. |
| "Losing a cache has zero user impact." | Cold cache starts can raise latency, network/API fees, and cause stampedes. |
| "Spot VMs only lose RAM when preempted." | Local SSD data can also be lost. |
| "GKE `emptyDir` always sits on Local SSD." | Depends on node pool/backing storage configuration and GKE version. |
| "A VM's Local SSD is shared like Filestore." | Local block devices differ from managed NFS. |
| "Using 10 GiB means paying only for 10 GiB." | Billed by provisioned capacity, not written bytes. |
| "Startup software should run `mkfs` whenever a mount is missing." | That can destroy data on delayed mounts or wrong devices. |

## 20. Official Google Cloud Documentation

References for verifying limits, machine series, `gcloud` syntax, and Local SSD behavior:

- [About Local SSD disks](https://docs.cloud.google.com/compute/docs/disks/local-ssd)
- [Add Local SSD disks to your VM](https://docs.cloud.google.com/compute/docs/disks/add-local-ssd)
- [Choose a disk type](https://docs.cloud.google.com/compute/docs/disks)
- [Format and mount a non-boot disk on Linux](https://docs.cloud.google.com/compute/docs/disks/format-mount-disk-linux)
- [Optimize Local SSD performance](https://docs.cloud.google.com/compute/docs/disks/optimizing-local-ssd-performance)
- [Benchmark Local SSD performance](https://docs.cloud.google.com/compute/docs/disks/benchmarking-local-ssd-performance)
- [Host maintenance policy and Local SSD recovery](https://docs.cloud.google.com/compute/docs/instances/host-maintenance-overview)
- [Stop or restart a Compute Engine VM](https://docs.cloud.google.com/compute/docs/instances/stop-start-instance)
- [Suspend or resume a Compute Engine VM](https://docs.cloud.google.com/compute/docs/instances/suspend-resume-instance)
- [General-purpose Compute Engine pricing](https://cloud.google.com/products/compute/pricing/general-purpose)
- [Disk and image pricing](https://cloud.google.com/compute/disks-image-pricing)

Performance specifications, machine families, Preview features, quota requirements, CLI flags, and pricing can change across Google Cloud versions. In production environments, verify documentation for your exact **machine type, OS image, zone, and deployment time**.

---

**Connection to the CLOUD_PROVIDERS_GCP track:** Local SSD adds a fast block storage option for Compute Engine and certain GKE workloads, yet the core lesson is **choosing where to keep the primary data copy and where to keep expendable copies**. Combine **Cloud Storage/Persistent Disk/Hyperdisk** for durable persistence, **IAM and VPC** to protect access, **Cloud Monitoring/Logging** to detect failures, and **Cloud Billing** to control costs. When moving workloads to Cloud Run or other managed services, maintain the same principle: **scratch is expendable — outputs/checkpoints must be durable — applications must recover from a trusted source**.

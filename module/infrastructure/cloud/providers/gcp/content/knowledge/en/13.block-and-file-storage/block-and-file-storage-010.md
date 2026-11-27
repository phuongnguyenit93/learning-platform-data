# Hands-on Disk Performance Benchmarking and Data Recovery

> **Chapter:** Block and File Storage  
> **Module:** CLOUD_PROVIDERS_GCP  
> **Module scope:** Explore Google Cloud from project organization, IAM, and VPC to Compute Engine, GKE, Cloud Run, storage services, and databases. Through deployment scenarios, learners select services, protect resources, automate releases, and monitor reliability and cost.

When an application on Compute Engine reads data files, writes logs, or runs a database, disk performance directly impacts response times. Yet "a 100 GB disk" reveals nothing about operations per second, bytes transferred per second, or actual latency. The same disk type can yield different numbers when size, VM type, vCPU count, I/O size, and concurrency change.

**Data recoverability** also does not appear automatically simply by using Persistent Disk or Hyperdisk. Durable disks preserve data across certain VM lifecycle events, yet accidental deletion, application bugs, or malware can still alter or destroy data. You need **snapshots or a dedicated backup strategy**, and more importantly, you must **test restores** to prove backups are usable.

This lesson combines two skills: **measuring IOPS/throughput/latency with `fio`** on an isolated lab disk and **creating a snapshot → restoring to a new disk → verifying checksums**. Every operation that can write or delete data is strictly scoped to test resources.

## Learning Objectives

After this lesson, you will be able to:

1. Select the proper roles of **Persistent Disk**, **Hyperdisk**, **Local SSD**, and **Filestore** when evaluating performance and recoverability.
2. Distinguish **IOPS**, **throughput**, **latency**, **block size**, **queue depth**, and caching; explain why benchmark results vary.
3. Safely identify a data disk from Compute Engine and Linux, avoiding confusing the **boot disk** with the lab disk.
4. Use `fio` to run sequential and random read/write tests on a **dedicated file** without writing directly to a raw block device.
5. Explain the impact of disk size, VM machine type, vCPUs, I/O profile, and provisioned performance limits.
6. Create a snapshot **after syncing and stopping writes**, create a new disk from the snapshot, attach it to a VM, and verify files/checksums.
7. Plan backups/restores around **RPO**, **RTO**, cost, permissions, encryption, and resource cleanup procedures.

## 1. Choose the Right Storage Type Before Measuring

Compute Engine offers multiple storage forms, so identify **what you are benchmarking** first:

| Storage type | Primary use | Performance | Recovery / caveats |
|---|---|---|---|
| **Persistent Disk (`pd-standard`, `pd-balanced`, `pd-ssd`...)** | Block disk for VMs; boot or data | Depends on type, size, vCPUs, and VM limits | Can create disk snapshots and create new disks from snapshots |
| **Hyperdisk** | Block disk with tunable performance by type (Balanced, Extreme, Throughput...) | Provisioned IOPS/throughput per feature and capped by VM | Supported snapshot/backup mechanisms; check compatibility per type |
| **Local SSD** | Very fast host-local block storage for scratch/cache | Typically low latency, high IOPS | **Never treat as a durable copy**; data can be lost on VM lifecycle events; does not use PD disk snapshot workflows |
| **Filestore** | NFS file share for multiple clients | Depends on tier, instance capacity, network, and clients | Use **Filestore's own** backup/snapshot policies, not Compute Engine disk snapshot commands |
| **Cloud Storage** | Object storage via API | Measured in object requests/throughput, not raw block IOPS | Versioning, retention, and backups follow the object model |

**This lab uses `pd-balanced`** for ease of practice on compatible VMs, not to claim it is the best-performing choice for every system. On newer machine series that only support Hyperdisk, select an eligible disk type or use a Persistent Disk-compatible lab VM.

### 1.1. Block Storage Differs from File Storage

**Block storage** appears to the OS as a block device, such as `/dev/sdb` or an NVMe device name. Users create partitions/filesystems, mount them, and applications read/write. **File storage** like Filestore provides a shared filesystem over NFS mounted over the network; customers do not manage a standalone block device snapshotted with `gcloud compute snapshots create`.

Therefore, running `fio` against a Filestore NFS directory can be useful when tuning applications, yet results reflect NFS protocol, network, and multi-client factors. Disk snapshot instructions in this lesson **do not apply to Filestore**.

### 1.2. Durable Disks Do Not Equal Backups

```text
Application on VM
   |
   +--> Persistent Disk / Hyperdisk: live data
   |       |
   |       +--> Accidental edits/deletions can still lose data
   |
   +--> Disk snapshot: recovery point at time T
           |
           +--> Create new disk from snapshot
                    |
                    +--> Mount, verify files/checksums, restore service
```

Regional disks or replication improve tolerance to certain infrastructure faults, yet **do not replace point-in-time backups**: deletions or bad writes can propagate to replicas.

## 2. Metrics to Understand Before Benchmarking

### 2.1. IOPS, Throughput, and Latency

| Metric | Unit | Question answered |
|---|---|---|
| **IOPS** | Operations/second | How many reads/writes can the disk complete per second? |
| **Throughput** | MiB/s or MB/s (must specify clearly) | How much data is read/written per second? |
| **Latency** | ms, µs; p50/p95/p99 | How long does a single I/O operation take to finish? |
| **Block size** | 4 KiB, 64 KiB, 1 MiB... | How much data does each I/O operation transfer? |
| **Queue depth** | Pending/concurrent I/Os | How many concurrent requests does the workload queue? |
| **Read/write mix** | e.g., 70% read / 30% write | The application's read/write balance |
| **Random/sequential** | Random or sequential access | Does the I/O pattern resemble a database or large file writes? |

Approximate formula in a test with uniform I/O size:

\[
\text{Throughput (MiB/s)} \approx
\frac{\text{IOPS} \times \text{block size (KiB)}}{1024}
\]

For example, a hypothetical **5,000 IOPS** at **4 KiB** equals roughly **19.5 MiB/s**. The same 5,000 IOPS at **256 KiB** equals **1,250 MiB/s**, if infrastructure and workload actually sustain it. **Do not infer that a disk can sustain both profiles** purely from multiplication: IOPS and throughput have independent ceilings.

### 2.2. Low Latency Does Not Always Mean High IOPS

`fio` can report:

- **`clat`:** completion latency of I/O, including waiting for completion per the I/O engine.
- **`slat`:** submission latency, time spent preparing/submitting the I/O.
- **`lat`:** total request time measured by `fio`.
- **Percentiles** such as p95/p99: reveal tail latency, critical for latency-sensitive apps.

As queue depth grows, throughput/IOPS may rise while p99 latency degrades. Thus, never report a single "peak IOPS" figure while ignoring latency SLOs.

### 2.3. Why Does the Same Disk Yield Different Numbers?

Actual observed performance can be capped by **one or more factors**:

```text
Achievable I/O performance
    <= Disk limit by type / size / provisioned performance
    <= VM limit by machine type / vCPU / I/O capability
    <= Filesystem, OS, queuing, application, and workload limits
```

With **Persistent Disk**, disk size, disk type, and VM/vCPU type govern performance ceilings. With **Hyperdisk**, IOPS/throughput can be configured separately by disk type, yet real performance remains bounded by machine series, compatibility, and per-VM/aggregate disk caps. Read the limit tables for your exact disk type and VM before concluding you need to "upgrade the disk."

**Example:** if a VM is too small or CPU-saturated, raising Hyperdisk provisioned performance will not necessarily speed up the workload; the bottleneck may reside in the VM or application.

## 3. What Makes a Reliable Benchmark?

A benchmark is meaningful when conditions are **reproducible**:

1. Record **project, zone, VM machine type, vCPU count, disk type, disk size, filesystem, and I/O configuration**.
2. Use a **dedicated lab data disk**; never run `fio` writes against a boot disk or production disk.
3. Benchmark only inside a **dedicated directory**; never pass `--filename=/dev/sdX` or any raw block device.
4. Run **sequential write/read** and **random read/write** tests separately, reporting block size/iodepth/numjobs/runtime alongside results.
5. Use `--direct=1` to reduce **OS page cache** effects; still recognize underlying caches and filesystem behavior can influence measurements.
6. Include **warm-up/ramp time** and an adequate test window, avoiding conclusions from tiny bursts.
7. Avoid running competing I/O tests simultaneously unless evaluating a real mixed workload.
8. Repeat runs and record **IOPS, throughput, p95/p99 latency**, CPU, and VM state; disclose measurement limitations.

**Safety note:** `fio` can destroy data if given the wrong `--filename`, `--directory`, `--rw`, or target path. In this lab, use **only new files under `/mnt/disk-lab`**. Never run on shared filesystems, real data directories, boot disks, or raw devices.

### Test Profiles Matching Applications

| Workload | `fio --rw` | Suggested block size | Notes |
|---|---|---|---|
| Large file reads | `read` | `1m` | Prioritizes throughput; target file must exist |
| Large file writes | `write` | `1m` | Measures write throughput; write only to a **test file** |
| OLTP database | `randread` or `randrw` | `4k` or `8k` | IOPS, p95/p99, and read/write mix |
| Sequential log writes | `write`/append equivalent | Match app write size | Also measure fsync/durability if needed |
| Mixed workload | `randrw`, `rwmixread=70` | `4k`/`16k` | Compare against live application profile |

Synthetic benchmark numbers **do not automatically represent** a production database. Databases involve transaction logs, indexes, caches, flushes, and concurrency.

## 4. Lab Setup: Use Authorized Resources Only

This hands-on assumes you have **a Linux sandbox VM** with approved SSH/OS Login access. We will create a **new data disk**, format and mount it separately, and leave the boot disk untouched. Creating disks, snapshots, and restored disks **can incur charges**.

### 4.1. Illustrative Values

| Variable | Example value | Meaning |
|---|---|---|
| `PROJECT_ID` | `my-gcp-disk-lab` | Sandbox project |
| `ZONE` | `asia-southeast1-a` | Zone of the VM and data disk |
| `VM_NAME` | `disk-test-vm` | Existing Linux VM authorized for testing |
| `DISK_NAME` | `bench-data-lab` | New disk solely for benchmarking |
| `RESTORE_DISK` | `bench-restored-lab` | Disk restored from snapshot |
| `SNAPSHOT_NAME` | `bench-data-lab-snap-01` | Snapshot of the data disk |
| `DATA_DEVICE` | `/dev/disk/by-id/google-bench-data-lab` | Expected guest OS path from device name |
| `RESTORED_DEVICE` | `/dev/disk/by-id/google-bench-restored-lab` | Path of the restored disk |
| `MOUNT_DIR` | `/mnt/disk-lab` | Mount directory for source disk |
| `RESTORE_MOUNT` | `/mnt/restore-lab` | Mount directory for restored disk |

**Names/addresses are examples.** If the VM already has a disk with the same name or `/dev/disk/by-id/google-bench-data-lab` attached, **stop** and inspect. Format only after confirming it is the **brand-new empty lab disk**.

### 4.2. Permissions and Environment

You need:

- Appropriate IAM to **view/create/attach/detach/delete disks** and **create/view/delete snapshots** in the project; do not grant Owner/Editor solely for the lab.
- Approved Linux VM access, with `sudo` inside the guest OS for formatting/mounting.
- Compute Engine API enabled, sufficient disk quota, and a machine type supporting `pd-balanced`.
- Enough disk space for two separate `fio` files; this lab chooses **20 GiB** and two test files of roughly **2 GiB** each, adjustable per policy constraints.
- An IAM plan, Billing budget, scheduled lab window, and awareness of **snapshot costs**. Budgets send alerts only—they do not stop resources automatically.
- Approval from the VM owner if reusing an existing VM: benchmarks can raise latency for all disks/workloads sharing the VM due to shared VM limits.

**Do not use Local SSD** for the snapshot portion. If a VM does not support `pd-balanced`, switch the exercise to **read-only** inspection or ask the environment owner for a compatible VM/disk; never modify a production VM's machine type.

## 5. Inspect Project, VM, and Disks Before Creating

Run in **Cloud Shell or a terminal with Google Cloud CLI**:

```bash
PROJECT_ID="my-gcp-disk-lab"
ZONE="asia-southeast1-a"
VM_NAME="disk-test-vm"
DISK_NAME="bench-data-lab"
RESTORE_DISK="bench-restored-lab"
SNAPSHOT_NAME="bench-data-lab-snap-01"

# Read-only: active account, VM, and existing disks
gcloud auth list --filter="status:ACTIVE"
gcloud projects describe "$PROJECT_ID" \
  --format="table(projectId,name,lifecycleState)"

gcloud compute instances describe "$VM_NAME" \
  --project="$PROJECT_ID" --zone="$ZONE" \
  --format="yaml(name,status,machineType,disks)"

gcloud compute disks list \
  --project="$PROJECT_ID"

# List existing snapshots to avoid colliding with another system's names
gcloud compute snapshots list \
  --project="$PROJECT_ID"
```

Cross-check `machineType`, the boot disk name in `disks`, attached disks, and resource owners. **Never run `gcloud compute instances delete`** in this lab: the VM already exists and is outside disk cleanup scope.

### 5.1. Create the Lab Data Disk and Attach to VM

Only after confirming `bench-data-lab` **does not exist** and the VM is in the right zone:

```bash
# Create a 20 GiB pd-balanced disk; charges apply per pricing table
gcloud compute disks create "$DISK_NAME" \
  --project="$PROJECT_ID" \
  --zone="$ZONE" \
  --type=pd-balanced \
  --size=20GB

# Attach data disk to VM with a stable device name for the guest OS
gcloud compute instances attach-disk "$VM_NAME" \
  --project="$PROJECT_ID" --zone="$ZONE" \
  --disk="$DISK_NAME" \
  --device-name="$DISK_NAME"

# Verify the data disk is attached and distinct from the boot disk
gcloud compute instances describe "$VM_NAME" \
  --project="$PROJECT_ID" --zone="$ZONE" \
  --format="yaml(disks)"
```

The new disk is only a **block device**; it has no filesystem yet. **Attaching** can normally be done while the VM is running, though guest-OS disk operations must still follow platform and VM-owner rules.

## 6. Inside the Linux VM: **Safely** Identify and Mount the Disk

Commands in this section run **inside the Linux VM**, never from Cloud Shell guessing VM device names. Names like `/dev/sdb` or `/dev/nvme0n2` can change across reboots and machine series; prefer **`/dev/disk/by-id/google-<device-name>`** when provided by the guest OS.

### 6.1. Verify Disk Identity

```bash
# Read-only commands inside the VM
lsblk -o NAME,SIZE,TYPE,FSTYPE,MOUNTPOINTS,MODEL,SERIAL
ls -l /dev/disk/by-id/
df -hT

# Must match --device-name from the attach step; if missing, stop and check
DATA_DEVICE="/dev/disk/by-id/google-bench-data-lab"
test -b "$DATA_DEVICE" && readlink -f "$DATA_DEVICE"
lsblk -f "$DATA_DEVICE"
```

**Stop immediately if**:

- The path does not exist or is not a block device.
- The disk appears to be the **boot disk**, containing `/`, `/boot`, or a pre-existing workload filesystem.
- `lsblk -f` shows an existing filesystem/partition or a mount point not created by this lab.
- Size/serial/device name does not match the 20 GiB data disk just created.

Never rely on `/dev/sdb` guessing it is the data disk. If the guest OS does not create the `google-...` symlink as shown, consult guest environment documentation and identify the disk from live metadata before continuing.

### 6.2. Create a Filesystem **Only on the New Empty Data Disk**

**`mkfs.ext4` destroys existing data on the target device.** Run it only after confirming the device is **the new lab disk**, with no existing filesystem, partition, or data to keep. Never run it on a disk restored from a snapshot.

```bash
DATA_DEVICE="/dev/disk/by-id/google-bench-data-lab"
MOUNT_DIR="/mnt/disk-lab"

# Final check; if a filesystem/mountpoint appears, DO NOT run mkfs
lsblk -f "$DATA_DEVICE"
sudo blkid "$DATA_DEVICE" || true

# WARNING: format only a brand-new empty lab data disk
sudo mkfs.ext4 "$DATA_DEVICE"

# Mount to operate on files; do not write directly to raw device
sudo mkdir -p "$MOUNT_DIR"
sudo mount "$DATA_DEVICE" "$MOUNT_DIR"
sudo chown "$(id -u):$(id -g)" "$MOUNT_DIR"

# Re-verify: mountpoint must point to the lab disk
findmnt "$MOUNT_DIR"
df -hT "$MOUNT_DIR"
```

If a disk has partitions, procedures may require mounting the specific partition rather than the raw disk. Here we create the filesystem directly on the **whole empty data disk** for simplicity, without creating a partition table.

### 6.3. Create a Marker for Post-Snapshot Recovery Verification

Create a small file with verifiable content and a checksum file on the lab disk. This file serves as the **recovery checkpoint**, independent of `fio` benchmark files:

```bash
MOUNT_DIR="/mnt/disk-lab"

printf 'backup-point=v1\nworkload=disk-lab\n' \
  > "$MOUNT_DIR/marker.txt"

# Create checksum with relative filename for verification at another mount
(cd "$MOUNT_DIR" && sha256sum marker.txt > marker.sha256)

cat "$MOUNT_DIR/marker.txt"
(cd "$MOUNT_DIR" && sha256sum --check marker.sha256)
```

**Expected:** `marker.txt: OK`. Save the checksum or output in your lab log for independent verification if needed. Never put personal data or secrets in test files.

## 7. Preparing `fio` and `sysstat`

`fio` generates synthetic read/write load; `iostat` (from `sysstat`) monitors OS-level device status and queues.

On an authorized Debian/Ubuntu lab VM allowed to install packages:

```bash
sudo apt-get update
sudo apt-get install -y fio sysstat

# Verify tool versions and disk/mount state
fio --version
iostat -V
findmnt /mnt/disk-lab
```

On RHEL/Rocky/Container-Optimized OS, installation differs and may require a suitable test image. Never alter packages or restart production services merely to install `fio`.

### 7.1. Command Safety Boundaries

The upcoming tests:

- Use only `/mnt/disk-lab/bench-seq.dat` and `/mnt/disk-lab/bench-rand.dat`.
- Never pass `/dev/...` as `--filename`.
- Set `60s` per test (with `5s` ramp) and file size roughly `2 GiB`; reduce if project limits require.
- Use `--numjobs=1`, `--iodepth=16` to keep lab load controlled—do not treat these as optimal settings for every drive.
- Skip or abort benchmarks if the VM runs latency-sensitive services or if the mount point holds non-lab data.

**`fio` overwrites existing files with matching names.** Before every run, confirm the mount point and ensure the target file is solely this lesson's test file:

```bash
MOUNT_DIR="/mnt/disk-lab"
test "$(findmnt -n -o TARGET --target "$MOUNT_DIR")" = "$MOUNT_DIR" \
  || { echo "Not the lab mountpoint; aborting."; exit 1; }

ls -lh "$MOUNT_DIR"
```

## 8. Benchmarking IOPS/Throughput/Latency with `fio`

### 8.1. Sequential Write Test

The command below writes to a **new file on the lab data disk**, not a raw block device. Do not run if the file already holds data to keep.

```bash
fio --name=seq-write-lab \
  --filename=/mnt/disk-lab/bench-seq.dat \
  --rw=write \
  --bs=1m \
  --size=2G \
  --ioengine=libaio \
  --direct=1 \
  --iodepth=16 \
  --numjobs=1 \
  --ramp_time=5 \
  --runtime=60 \
  --time_based \
  --group_reporting
```

**Reading the output:**

- `write: IOPS=...`: write operations per second with 1 MiB blocks.
- `BW=...MiB/s`: write throughput in MiB/s during the run.
- `clat (usec/msec)` and percentile tables: completion latency.
- `IO depths`: whether the queue actually reached the configured depth.

Output numbers **depend on the real VM/disk**—never treat a hypothetical number as your lab result. Given the 2 GiB file size and short duration, this is a **quick check**, insufficient to guarantee sustained production throughput.

### 8.2. Sequential Read Test

Once `bench-seq.dat` is created successfully, read that same file:

```bash
sync
fio --name=seq-read-lab \
  --filename=/mnt/disk-lab/bench-seq.dat \
  --rw=read \
  --bs=1m \
  --size=2G \
  --ioengine=libaio \
  --direct=1 \
  --iodepth=16 \
  --numjobs=1 \
  --ramp_time=5 \
  --runtime=60 \
  --time_based \
  --group_reporting
```

`--direct=1` requests direct I/O, reducing Linux page cache interference. It **does not** bypass every cache layer in the storage stack or guarantee results identical to live application access.

### 8.3. Random 4 KiB 70/30 Read/Write Test

Test a pattern resembling small random accesses of transactional databases:

```bash
fio --name=randrw-lab \
  --filename=/mnt/disk-lab/bench-rand.dat \
  --rw=randrw \
  --rwmixread=70 \
  --bs=4k \
  --size=2G \
  --ioengine=libaio \
  --direct=1 \
  --iodepth=16 \
  --numjobs=1 \
  --ramp_time=5 \
  --runtime=60 \
  --time_based \
  --group_reporting
```

Output shows separate `read` and `write` sections. **Total IOPS** sums reads and writes in the run, yet never compare a read-only IOPS figure against a 70/30 mixed run without stating conditions.

To evaluate **SLO latency**, check read and write p95/p99 separately; high p99 can hurt user requests even when aggregate IOPS looks healthy.

### 8.4. Watching OS State During Benchmarks

In another terminal **on the same VM**, run:

```bash
# Active block device metrics; Ctrl+C to stop
iostat -xz 2
```

Useful columns:

- `r/s`, `w/s`: read/write requests per second observed by the OS.
- `rkB/s`, `wkB/s`: data read/written on the device.
- `await`: average I/O latency observed by Linux.
- `aqu-sz`: average I/O queue length.
- `%util`: percentage of time the device has active requests; **never naively interpret `100%` as "the cloud disk hit its throughput cap"** on virtualized/parallel storage.

Device names in `iostat` may appear as `sdb` or `nvme...`, **not the symlink name**. Confirm they map to the lab data disk before reading numbers.

### 8.5. Recording a Comparable Results Table

| Test | Block / mix | Actual IOPS | Throughput (MiB/s) | Read p95/p99 | Write p95/p99 |
|---|---|---:|---:|---|---|
| Seq write | 1 MiB, 100% write | *Fill from fio* | *Fill from fio* | — | *Fill from fio* |
| Seq read | 1 MiB, 100% read | *Fill from fio* | *Fill from fio* | *Fill from fio* | — |
| Random read/write | 4 KiB, 70/30 | *Fill total/split* | *Fill result* | *Fill from fio* | *Fill from fio* |

Also record **disk type/size, machine type, vCPUs, zone, kernel, filesystem, fio version, iodepth, numjobs, and timestamp**. Never compare this table against someone else's results if configurations differ.

## 9. Interpreting Results: Finding the True Bottleneck

Common observations:

| Observation | Possible explanation | Next check |
|---|---|---|
| Low random IOPS yet acceptable sequential throughput | Disk/workload not tuned for small I/O or insufficient queue depth | Check block size, IOPS limit, queue depth |
| Increasing disk size did not raise throughput | Hit VM/vCPU cap or I/O pattern limit | Check machine type and VM PD caps |
| High Hyperdisk provisioned IOPS not achieved | VM does not support that level or workload lacks queue depth | Check Hyperdisk/VM caps, I/O size, fio depth |
| High p99 despite steady average IOPS | Bursts, I/O contention, CPU saturation, or overly deep queue | Measure over time; watch CPU and `iostat` |
| `fio` reads abnormally fast without direct I/O | Page cache skewed numbers | Retest with `--direct=1` and larger dataset |
| Unstable numbers across runs | Caching, startup effects, contention, platform variance, small files | Repeat runs in a controlled environment |
| App slow yet disk benchmark looks fine | Bottleneck is DB queries, locks, CPU, network, or app code | Inspect profiler, traces, business metrics |
| Growing disk capacity raises costs | PD ties performance to capacity | Consider Hyperdisk if VM supports it and economics fit |

**Mental formula:** useful performance is **the level achieved within acceptable latency and appropriate cost**, not simply the highest IOPS from a brief synthetic test.

### 9.1. Cloud Monitoring Data

Compute Engine exposes disk and VM metrics via **Cloud Monitoring**; view read/write bytes/operations charts and metrics supported per disk/VM type. To inspect Linux filesystem latency or detailed disk queues, use the **Ops Agent**/guest monitoring where authorized.

**Distinctions:**

- Cloud Monitoring VM/disk metrics reflect platform-level aggregates over sampling intervals.
- `fio` measures a specific synthetic test workload inside the guest OS.
- `iostat` measures I/O as seen by the guest OS.
- Application SLOs measure what end users actually experience.

Never assume numbers match identically across tools due to counting methods, units, aggregation windows, and caching.

## 10. Preparing for Snapshots: Data Safety First

A **snapshot** is a point-in-time recovery point for disk data. Compute Engine snapshots typically store incremental changes per service mechanics and can restore into a new disk. A completed snapshot does not mean an **actively writing application** was in a business-consistent state.

### 10.1. Crash Consistency vs. Application Consistency

| Consistency level | What to expect | Risks |
|---|---|---|
| **Crash-consistent** | Reflects block state as if power dropped suddenly at one instant | In-memory app data and unflushed transactions may be missing; needs recovery logic |
| **Filesystem-consistent** | Filesystem synced/paused enough to reduce unflushed journal risks | Does not guarantee databases finished logical transactions |
| **Application-consistent** | App/database coordinates flush/quiesce before snapshot | Requires hooks/tools and can briefly impact availability |

For PostgreSQL, MySQL, SQL Server, or multi-disk/transactional workloads, never run a lone `sync` and claim the app is **application-consistent**. Use database-native backups, quiescing, or supported backup tooling. For this lab's **test-file-only filesystem**, we **stop writes and unmount** before snapshotting to achieve a clean filesystem state.

### 10.2. Why Snapshots and Backups Must Be Tested

A complete backup process requires:

1. Selecting the **target** (which disks/data), recovery points, and storage locations.
2. Defining **RPO** (maximum acceptable data loss) and **RTO** (maximum acceptable recovery time).
3. Scheduling snapshots with proper IAM, encryption, and retention.
4. Periodically **restoring to a separate disk**, mounting, verifying data, and running app smoke tests.
5. Testing recovery when **an entire VM/zone fails**, not merely when a single file is deleted.

**Example:** daily 24-hour snapshots can yield nearly 24 hours of RPO in the worst case. RTO includes creating the disk from snapshot, attaching, mounting, verifying, and starting the app—**not just the snapshot command duration**.

## 11. Creating a Snapshot of the Lab Data Disk

### 11.1. Stop Writes, Verify Marker, and Unmount

On the **Linux lab VM**, finish all `fio` runs and any processes writing to `/mnt/disk-lab`, then:

```bash
MOUNT_DIR="/mnt/disk-lab"

# Confirm original content and checksum still pass
(cd "$MOUNT_DIR" && sha256sum --check marker.sha256)

# Flush write buffers and unmount the lab disk
sync
sudo umount "$MOUNT_DIR"

# Confirm unmounted; never snapshot while benchmarks are actively writing
findmnt "$MOUNT_DIR" || echo "Lab disk unmounted"
```

If `umount` says "target is busy," never use `umount -l` as a shortcut. Find the terminal/process holding files open or with its `cwd` inside the mount point, close it cleanly, and retry `umount`. Never force-unmount active workloads.

### 11.2. Create the Snapshot with `gcloud`

Back in **Cloud Shell or an authenticated terminal**, run the Google Cloud-recommended command:

```bash
# Snapshot the zonal disk; writes stopped and filesystem unmounted
gcloud compute snapshots create "$SNAPSHOT_NAME" \
  --project="$PROJECT_ID" \
  --source-disk="$DISK_NAME" \
  --source-disk-zone="$ZONE" \
  --snapshot-type=STANDARD

# Inspect snapshot status, source disk, and storage locations
gcloud compute snapshots describe "$SNAPSHOT_NAME" \
  --project="$PROJECT_ID" \
  --format="yaml(name,status,sourceDisk,storageLocations,creationTimestamp)"
```

**Proceed to restoration only once the snapshot API status is ready/completed.** A snapshot is an independent resource; you do not need to delete the source disk to restore.

Snapshots have a **storage location**, selectable via snapshot settings or `--storage-location` to meet data placement requirements. This lab uses admin-approved defaults; real environments must verify **data residency, IAM, CMEK/encryption, and retention** before creating snapshots.

### 11.3. Console Equivalent

1. Open **Compute Engine → Snapshots → Create snapshot**.
2. Enter name `bench-data-lab-snap-01`, standard snapshot type (**STANDARD**), and **source disk `bench-data-lab`**, not the boot disk.
3. Review **storage location** and project backup policies.
4. Confirm writes have stopped and the lab filesystem is unmounted.
5. Create the snapshot, open details, and verify completion status.

**Warning:** never select a production/database disk by mistake; snapshots of sensitive data carry the same protection and access-control requirements as the original data.

## 12. Restoring from Snapshot to a **New Disk**

The safe pattern is **never overwriting the source disk**, instead creating a new disk from the snapshot and mounting it for verification. A snapshot is not an "in-place overwrite" command.

### 12.1. Create the Restored Disk

In Cloud Shell:

```bash
# Create a new disk name that does not collide with existing disks
gcloud compute disks create "$RESTORE_DISK" \
  --project="$PROJECT_ID" \
  --zone="$ZONE" \
  --type=pd-balanced \
  --source-snapshot="$SNAPSHOT_NAME"

# Confirm the new disk shows sourceSnapshot and valid status
gcloud compute disks describe "$RESTORE_DISK" \
  --project="$PROJECT_ID" --zone="$ZONE" \
  --format="yaml(name,status,sizeGb,type,sourceSnapshot)"
```

The disk created **from the snapshot** already contains the filesystem and files from the snapshot timestamp. **Never run `mkfs.ext4` on the restored disk**: reformatting overwrites filesystem metadata and defeats the recovery test.

### 12.2. Attach the Restored Disk to the Lab VM

```bash
gcloud compute instances attach-disk "$VM_NAME" \
  --project="$PROJECT_ID" \
  --zone="$ZONE" \
  --disk="$RESTORE_DISK" \
  --device-name="$RESTORE_DISK"

# Clearly distinguish boot disk, source disk, and newly restored disk
gcloud compute instances describe "$VM_NAME" \
  --project="$PROJECT_ID" --zone="$ZONE" \
  --format="yaml(disks)"
```

**Note:** the source disk and restored disk can share the exact same **filesystem UUID** because snapshots copy the filesystem. This lab keeps the source disk **unmounted** and mounts only the restored disk to avoid UUID collisions in mounts/fstab.

### 12.3. Mount Read-Only and Verify Checksum

On the **Linux VM**, confirm the restored device differs from the source device and boot disk:

```bash
RESTORED_DEVICE="/dev/disk/by-id/google-bench-restored-lab"
RESTORE_MOUNT="/mnt/restore-lab"

# Read-only verification of the new disk and existing filesystem
lsblk -o NAME,SIZE,FSTYPE,MOUNTPOINTS,MODEL,SERIAL
ls -l /dev/disk/by-id/
test -b "$RESTORED_DEVICE" && readlink -f "$RESTORED_DEVICE"
lsblk -f "$RESTORED_DEVICE"

# Restored disk already has a filesystem; DO NOT run mkfs
sudo mkdir -p "$RESTORE_MOUNT"
sudo mount -o ro "$RESTORED_DEVICE" "$RESTORE_MOUNT"

findmnt "$RESTORE_MOUNT"
ls -lah "$RESTORE_MOUNT"

# Use the checksum created BEFORE snapshotting to verify contents
(cd "$RESTORE_MOUNT" && sha256sum --check marker.sha256)

# Read the marker file at the exact recovery point
cat "$RESTORE_MOUNT/marker.txt"
```

**Expected:** `marker.txt: OK` and marker content:

```text
backup-point=v1
workload=disk-lab
```

If mounting reports journal/filesystem errors, **do not immediately run `fsck -y` or format the restored disk**. Inspect snapshot state, disk state, source state, and error messages. If filesystem repair is needed, clone/restore another copy for diagnosis rather than altering the initial test disk. For real data, resume application traffic only after validating filesystem and application-layer data.

### 12.4. Verifying Point-in-Time Recovery via Post-Snapshot Changes (Optional)

To see clearly that a snapshot is a **point-in-time image**, test on the isolated source disk after the snapshot finishes:

1. Once the restored disk is verified and **unmounted**, keep a safe record of the v1 checksum.
2. Remount the **lab source** disk, change `marker.txt` to `backup-point=v2`, then `sync` and unmount.
3. Remount the **restored** disk read-only. Content on the restored disk still reads `v1`.
4. Do not overwrite `marker.sha256` on the source disk if using it to demonstrate the contrast; compare the v1 checksum against the restored disk.

**Execute this only on the lab disk when certain which device is mounted.** Never write test files onto live workload disks. For databases, "restoring a single file" does not replace transactional database recovery.

### 12.5. Console Equivalent

1. Open **Compute Engine → Snapshots** and select `bench-data-lab-snap-01`.
2. Choose **Create disk** from the snapshot.
3. Name it `bench-restored-lab` in the VM's zone with a supported disk type.
4. Open **Compute Engine → VM instances → lab VM → Edit** and attach the existing disk per UI options.
5. SSH into the VM, verify the device, mount **read-only**, and verify checksums before letting applications use the data.

## 13. Reading Recovery Results: RPO, RTO, and Consistency

| Goal | Verification in lab | Common failure |
|---|---|---|
| **Backup exists** | Snapshot exists and status is completed | Saw job trigger without checking completion status |
| **Disk recovery** | New disk shows matching `sourceSnapshot` | Wrong snapshot or incompatible zone |
| **Filesystem recovery** | Read-only mount succeeds | Wrong device, duplicate UUID, or filesystem error |
| **Data integrity** | `sha256sum --check` returns `OK` | Failed to record pre-snapshot checksum |
| **RPO** | Latest snapshot timestamp relative to failure time | Snapshot schedule too infrequent |
| **RTO** | Elapsed time from recovery start until app serves requests | Measuring disk creation time only, ignoring mount/app startup |
| **Operability** | IAM permissions, keys, network, and dependencies work | Disk holds data yet app cannot reach DB/secrets |

In a multi-disk application or database, successfully restoring one filesystem **does not prove** all tables, indexes, transactions, and dependent services are consistent. Add business-logic tests, logical consistency checks, and full recovery runbooks.

### 13.1. Testing a Realistic Incident Scenario

Suppose the operations team targets:

- **Target RPO:** at most 4 hours of data loss.
- **Target RTO:** application back serving within 60 minutes.
- **Measures:** snapshot schedule meeting RPO, periodic restore drills, IaC/scripts managing VM configuration, measuring disk creation and app startup durations.

You cannot claim RPO/RTO compliance merely because snapshots are scheduled. Measure under realistic simulated outages including data, images, access permissions, secrets, and key dependencies.

## 14. Snapshot Schedules, Retention, and Accidental Deletion Prevention

Manual snapshots are only the first recovery point. Production operations require:

1. **Snapshot schedules** aligned with RPO; check frequency limits and feature support per disk type.
2. **Retention policies:** keep enough recovery points while avoiding deleting backups still needed.
3. **Least privilege:** users reading data do not automatically get snapshot create/delete permissions; separate encryption key and disk admin duties.
4. **Snapshot storage locations** compliant with data residency rules and organizational DR plans.
5. **Monitoring snapshot failures**, confirming backup completion, and alerting on missed cycles.
6. **Restore drills:** periodically create a new disk, mount/test the application, and clean up test resources.

**Incremental snapshots** reduce stored capacity compared to keeping full copies at every point per service mechanics; however, snapshot and restore costs still depend on real data churn and configuration. **Never assume snapshots are free**, or restorable without permissions/quota in the target project.

Snapshot schedules and application backups are complementary layers. For systems needing database point-in-time recovery, use solutions supporting **transaction logs / WAL / binlogs** or dedicated backup services rather than relying solely on disk snapshots.

## 15. Security and Limitations of Data Copies

Snapshots and newly restored disks can contain:

- Files, database files, logs, and application configurations.
- Tokens/secrets improperly saved on disk.
- Personal data or regulated records subject to retention policies.

Therefore:

- **Snapshot and disk IAM** must restrict who can view, restore, or delete copies.
- Verify **encryption at rest**, CMEK/CSEK keys if used by the organization, key lifecycles, and key access at restore time.
- Never share snapshots containing real data with personal projects just for benchmarking.
- Snapshots are not standalone ransomware immunity: combine deletion-prevention policies, retention, change auditing, and isolated copies per organizational security models.
- When deleting a restored disk during cleanup, verify it is not the sole remaining copy of critical data.

## 16. Cleaning Up Lab Resources and Stopping Charges

**Clean up only the disks/snapshots created specifically for this lesson.** Never delete pre-existing VMs, boot disks, buckets, production data files, or snapshots governed by organizational backup policies.

### 16.1. Unmount and Verify in Guest OS

On the VM:

```bash
# Stop any programs using test data, then unmount
sudo umount /mnt/restore-lab

# Source disk must also be unmounted before detaching
findmnt /mnt/disk-lab || echo "Source disk not mounted"
findmnt /mnt/restore-lab || echo "Restored disk not mounted"
```

If it reports "target is busy," stop processes still holding the filesystem; never force commands or delete disks while a VM is actively writing.

### 16.2. Inventory Disks/Snapshots from Cloud Shell

```bash
printf 'Project=%s Zone=%s VM=%s\nSource=%s Restore=%s Snapshot=%s\n' \
  "$PROJECT_ID" "$ZONE" "$VM_NAME" \
  "$DISK_NAME" "$RESTORE_DISK" "$SNAPSHOT_NAME"

gcloud compute instances describe "$VM_NAME" \
  --project="$PROJECT_ID" --zone="$ZONE" \
  --format="yaml(disks)"

gcloud compute disks describe "$DISK_NAME" \
  --project="$PROJECT_ID" --zone="$ZONE"

gcloud compute disks describe "$RESTORE_DISK" \
  --project="$PROJECT_ID" --zone="$ZONE"

gcloud compute snapshots describe "$SNAPSHOT_NAME" \
  --project="$PROJECT_ID"
```

### 16.3. Detach and Delete **Only Lab Disks**

```bash
# Detach restored disk from VM only after unmounting and confirming owner
gcloud compute instances detach-disk "$VM_NAME" \
  --project="$PROJECT_ID" \
  --zone="$ZONE" \
  --disk="$RESTORE_DISK"

# Detach benchmark data disk from VM
gcloud compute instances detach-disk "$VM_NAME" \
  --project="$PROJECT_ID" \
  --zone="$ZONE" \
  --disk="$DISK_NAME"

# Delete only the two disks created by this lab after verifying no data needs keeping
gcloud compute disks delete "$RESTORE_DISK" \
  --project="$PROJECT_ID" --zone="$ZONE"

gcloud compute disks delete "$DISK_NAME" \
  --project="$PROJECT_ID" --zone="$ZONE"
```

**Deleting a disk destroys data.** If you intend to keep the snapshot as a recovery point, do not delete the snapshot afterward. Conversely, if the lab is finished and the snapshot is no longer needed, verify ownership before deleting.

### 16.4. Delete the Lab Snapshot When No Longer Needed

```bash
# ONLY when this snapshot was created for the lab and verified expendable
gcloud compute snapshots delete "$SNAPSHOT_NAME" \
  --project="$PROJECT_ID"

# Re-list resources to confirm what billable resources remain
gcloud compute disks list --project="$PROJECT_ID"
gcloud compute snapshots list --project="$PROJECT_ID"
```

Never delete snapshots serving backup/DR or used by another system. Cloud Billing Reports may lag after deletion; proactively confirming no lab disks/IPs/snapshots remain in listings is the definitive check.

## 17. Troubleshooting: Benchmarking and Restoring

| Symptom | Possible cause | Verification steps |
|---|---|---|
| Cannot create lab disk | Insufficient permissions, quota, billing, or unsupported machine type | Check IAM, disk type/zone, and Compute Engine API |
| `attach-disk` reports incompatibility | Disk in different zone, VM doesn't support disk type, or incompatible attach mode | Compare VM/disk location, machine series, and attach mode |
| `/dev/disk/by-id/google-...` missing | Different device name or missing guest environment symlink | Check `instances describe`, `lsblk`, `ls -l /dev/disk/by-id`; never guess `/dev/sdb` |
| `mkfs` reports device busy | Disk mounted/partitioned or held by kernel | **Stop** and verify the exact disk; never force |
| Slow `fio` writes | Disk size/type, VM vCPU, queue depth, CPU, or I/O contention | Check fio/`iostat` against disk and VM caps |
| Abnormally fast `fio` reads | Page cache, file too small, or flawed test setup | Enable direct I/O; grow dataset under control |
| `fio` fails with `No space left on device` | Combined test files exceed filesystem capacity | Check `df -hT`; shrink test files or size lab disk adequately |
| `umount` reports `busy` | Terminal/process still inside mount | Exit directory, stop fio/processes, check `fuser` if permitted |
| Snapshot fails | Permissions, quota, wrong disk/zone, or disk error state | Read error details and operation; do not delete source disk |
| Snapshot succeeds yet file is missing | File unflushed, written after snapshot, or wrong disk selected | Verify timing, marker, snapshot source, and quiesce strategy |
| Restored disk won't mount | Wrong device/FS, incomplete snapshot, or filesystem needs check | Check `lsblk -f`, `blkid`, snapshot details; never format restored disk |
| `sha256sum --check` fails | Wrong recovery point, wrong checksum, or data corruption | Verify snapshot name, source state at T, retry fresh restore |
| VM has two filesystems with same UUID | Snapshot copied filesystem UUID | Avoid duplicate UUID mounts; use stable device IDs and filesystem management procedures |
| Backup exists yet RTO missed | Disk restores yet app/DB/IAM/network not ready | Time full recovery workflow and run smoke tests |
| Charges continue after deleting disk | Extra snapshots/disks remain or billing lag | Inventory disks/snapshots; check Billing Reports/labels |

### Ordered Diagnostic Flow

1. **Resource layer:** are project, zone, VM, disk type, and snapshot correct?
2. **Block device layer:** do `lsblk` and symlinks match the lab disk?
3. **Filesystem layer:** are mountpoint, `df`, `findmnt`, and checksums valid?
4. **Performance layer:** `fio` settings, `iostat`, caching, CPU/VM limits, disk limits?
5. **Backup layer:** snapshot source, timestamp, status, storage location, and IAM permissions?
6. **Application layer:** logical data consistency, database recovery, and smoke tests?
7. **Operations layer:** are RPO/RTO met, evidence saved, and lab resources cleaned up?

## 18. Operational Scenarios

### Scenario A — Database with Heavy Random I/O

A VM running PostgreSQL suffers high p99 latency as traffic grows. The team plans to move from Persistent Disk Balanced to Hyperdisk to boost IOPS. Before acting, they measure a `4 KiB random` workload with realistic read/write ratios, checking disk/VM limits, CPU, and tail latency instead of looking solely at 1 MiB sequential file throughput.

**Lesson:** if the bottleneck is CPU, SQL queries, or locks, upgrading the disk may yield little improvement. If IOPS/throughput is genuinely lacking, compare disk types, provisioned performance, VM compatibility, and cost.

### Scenario B — Snapshotting While the Application Writes

A team snapshots a database data disk during heavy transaction writes. The snapshot completes, yet upon restore the database requires crash recovery or lacks unflushed transactions.

**Lesson:** point-in-time block-level snapshots are not automatically application-consistent. Use supported database quiescing/backup methods and test restores.

### Scenario C — Accidental File Deletion on a Data Disk

A buggy script deletes `reports/2026/summary.csv` in an application. The disk stays healthy and the VM stays up, yet the data is gone. With a pre-deletion snapshot available, the team creates a **new** disk from the snapshot, mounts it read-only, verifies checksums, and copies the exact restored file per procedure.

**Lesson:** disk replication/durability does not replace versioned backups; restore to an isolated location before copying back into a live system.

### Scenario D — Lab Run Fills Up Disk

A learner runs `fio` with `--size=100G` on a 20 GiB filesystem or targets the boot disk by mistake. The test file runs out of space and can crash the app/OS due to disk exhaustion.

**Lesson:** benchmarks must stay strictly within the **lab filesystem**, verified via `df`/`findmnt` with bounded file sizes. Avoid running on boot disks or raw devices.

### Scenario E — Recovering When a Zone Becomes Unavailable

An application and zonal disk run in a single zone. If that zone fails, the DR plan may require a **snapshot stored in an eligible location** to create a new disk in **another supported zone**, alongside launching/bringing up a VM in the standby zone.

**Lesson:** restore feasibility also depends on snapshot scope, data storage location, disk/VM types, IAM permissions, and application dependencies. Rehearse alongside networking, DNS, secrets, and databases—not just file recovery.

## 19. Completion Checklist

| Check item | Evidence |
|---|---|
| Project/VM | Right sandbox project, authorized VM |
| Data disk | New disk, not boot disk, size/type verified |
| Device mapping | `/dev/disk/by-id` symlink matches `--device-name` |
| Filesystem | `findmnt` and `df -hT` confirm dedicated `/mnt/disk-lab` mount |
| Non-destructive | Never used `fio --filename=/dev/...`; `mkfs` ran once only on new disk |
| Benchmark | Ran seq write/read, random mix; recorded IOPS/throughput/p95/p99 |
| Limits | Explained effects of VM, disk, cache, queue depth, and runtime |
| Marker | Created `marker.txt` and `marker.sha256` before snapshot |
| Consistency | Stopped `fio`, ran `sync`, and unmounted source before snapshot |
| Snapshot | Right source disk, completed status, approved storage location |
| Restore | New disk from snapshot, **no formatting**, mounted read-only |
| Checksum | `sha256sum --check marker.sha256` returned `OK` |
| RPO/RTO | Understands recovery point and steps to measure bringing the app back |
| Cleanup | Unmounted, detached/deleted lab disks, handled snapshot per retention |
| Billing | Inventoried remaining disks/snapshots; aware of billing update lag |

## 20. Self-Check Questions

**1. Why is measuring 1 MiB sequential throughput insufficient to evaluate an OLTP database?**  
**Answer:** databases often generate many small random I/Os and are sensitive to p99 latency; benchmarks must approximate real workloads, block sizes, read/write mixes, and concurrency.

**2. What does `--direct=1` in `fio` do?**  
**Answer:** it requests direct I/O to reduce OS page cache influence; it does not eliminate every cache in the system and does not turn a synthetic benchmark into an application SLO.

**3. High IOPS was provisioned for Hyperdisk, yet measured performance stays low. Why?**  
**Answer:** it may hit VM/machine-type caps, insufficient workload queue depth/CPU, unsuitable I/O sizes, or I/O contention.

**4. Can you take a Compute Engine disk snapshot to back up a Filestore NFS share?**  
**Answer:** no. Filestore is a file storage service requiring Filestore's own backup/snapshot mechanisms.

**5. Is a snapshot taken while a database is actively writing guaranteed to be application-consistent?**  
**Answer:** no. You must use appropriate quiesce/flush/backup workflows and verify restoration logic.

**6. Why shouldn't you run `mkfs.ext4` on a disk just restored from a snapshot?**  
**Answer:** the restored disk already contains the filesystem and data from the snapshot; formatting overwrites metadata and destroys the data being verified.

**7. What does seeing `marker.txt: OK` on the restored disk prove?**  
**Answer:** the marker file matches the checksum saved before the snapshot; it does not by itself prove every other file, database, or application is consistent.

**8. Does a daily snapshot give a default RPO of 0?**  
**Answer:** no. Changes after the latest snapshot can be lost; RPO depends on backup frequency and transaction recovery capability.

**9. Why does a durable disk still need backups?**  
**Answer:** durability does not eliminate accidental deletion, bad edits, malware, or application logic bugs; independent recovery points are required.

**10. After deleting the benchmark disk, what components might still incur charges?**  
**Answer:** the restored disk, snapshots, VM/boot disk, reserved IP addresses, logs, and other services; inventory across the project.

## Key Takeaways

- **IOPS, throughput, and latency** measure three distinct dimensions. To compare fairly, specify block size, queue depth, read/write mix, disk/VM configuration, and duration.
- **Persistent Disk** performance scales with disk type/size and VM limits; **Hyperdisk** can decouple provisioned performance from capacity for supported types and machine series.
- **Run `fio` only on test files on a lab disk**; never benchmark raw devices or boot disks containing data to keep.
- **Snapshots are recovery points, not application-consistency certificates**. Stop writes/quiesce properly and rehearse restores.
- **Restore to a new disk, mount read-only, and verify checksums** before exposing data to applications. Never format a restored disk.
- **RPO/RTO are operational requirements that must be tested**, not merely snapshot schedule settings; protect IAM, encryption, retention, and budgets throughout the lifecycle.
- **Clean up only lab-created resources**; pre-existing VMs, boot disks, and shared backups are out of deletion scope.

## Official References

- [Google Cloud — Choose a disk type](https://cloud.google.com/compute/docs/disks)
- [Google Cloud — Persistent Disk performance](https://cloud.google.com/compute/docs/disks/performance)
- [Google Cloud — Hyperdisk performance](https://cloud.google.com/compute/docs/disks/hyperdisk-performance)
- [Google Cloud — Optimize Persistent Disk performance](https://cloud.google.com/compute/docs/disks/optimizing-pd-performance)
- [Google Cloud — Benchmarking Persistent Disk performance](https://cloud.google.com/compute/docs/disks/benchmarking-pd-performance)
- [Google Cloud — Create archive and standard snapshots](https://cloud.google.com/compute/docs/disks/create-snapshots)
- [Google Cloud — Manage disk snapshots](https://cloud.google.com/compute/docs/disks/manage-snapshots)
- [Google Cloud — Add a non-boot disk to a VM](https://cloud.google.com/compute/docs/disks/add-persistent-disk)
- [Google Cloud — Filestore documentation](https://cloud.google.com/filestore/docs)

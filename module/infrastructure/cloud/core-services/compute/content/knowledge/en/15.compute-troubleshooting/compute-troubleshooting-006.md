# Disk Full or Slow I/O: Inodes, Queues, and Volume Limits

## Learning objectives

After this lesson, you will be able to:

- Distinguish between block capacity exhaustion, inode exhaustion, and volume IOPS or throughput throttling.
- Read capacity, inode, latency, IOPS, throughput, and queue depth metrics to locate bottlenecks.
- Isolate failures across the filesystem, guest OS, cloud volume, storage transport path, or VM I/O limits.
- Use Linux and Windows tools to inspect disks, filesystems, and read/write activity.
- Choose safe remediation options: freeing space, expanding filesystems, tuning workloads, or adjusting volume configuration.
- Set up alerts and testing procedures to prevent repeat incidents.

## 1. Why can a VM run slowly or fail to write data?

A VM's disks typically consist of one or more volumes provisioned by the cloud platform as block devices or equivalent storage services. The guest OS creates partitions, filesystems, and mount points on top of those devices; applications then create files, directories, databases, and logs.

A disk incident can occur at multiple layers:

1. **Filesystem capacity:** no free blocks remain to create or extend files.
2. **Inodes or filesystem metadata:** no free inodes remain to create new files, even though free blocks exist.
3. **Volume performance:** the volume has hit its IOPS or throughput limit or is experiencing high latency.
4. **I/O queue:** many read/write requests wait to complete, forcing applications to stall.
5. **VM or transport limits:** the VM has hit its aggregate I/O limit, storage network bandwidth cap, or virtual device limits.
6. **Application and OS:** synchronous-write workloads, inefficient queries, filesystem corruption, drivers, or kernel issues.

Multiple causes can occur together. For example, a database creating many temporary files can exhaust inodes while a random-write workload hits the volume's IOPS cap. Simply expanding volume capacity leaves the inode or I/O problem unresolved.

**Common symptoms:**

- Applications report `No space left on device`, `Disk full`, `write failed`, or file creation errors.
- Logs stop writing, databases switch to read-only, or transaction logs cannot be created.
- SSH/RDP login succeeds, yet shells or applications respond sluggishly.
- Query times climb, job queues back up, and timeouts or retries repeat continuously.
- CPU stays low while processes frequently wait on I/O.
- The VM remains `Running`, yet the volume exhibits high latency or hits performance caps.

Identify whether the incident stems from capacity, inodes, or performance before changing configuration.

## 2. How do block capacity and inodes differ?

### 2.1. Block capacity

Filesystems allocate storage space in blocks or equivalent allocation units. When a file is created or extended, the filesystem needs enough blocks to hold its contents and metadata.

For example, a 100 GiB filesystem that has used all 100 GiB cannot write additional data. `df -h` can still report 100% even if the underlying cloud volume was already expanded; the filesystem does not automatically claim new space until the partition or filesystem is properly grown.

### 2.2. Inodes

On common Unix/Linux filesystems such as ext4, an inode is a metadata structure describing a file or directory object. An inode stores attributes such as permissions, owner, size, timestamps, and pointers to data blocks. Filenames and directory hierarchy are stored in directory entries pointing to inodes.

A filesystem can have plenty of free blocks yet be unable to create new files if all inodes are consumed. This commonly occurs when applications generate huge numbers of small files, caches, sessions, mail spools, temporary files, or per-request logs.

Example:

- A 50 GiB filesystem can hold millions of small files.
- If the inode count created at format time is exhausted, applications report out-of-space errors even while `df -h` shows many GiB free.
- Deleting one large file frees substantial blocks, but if the issue is inode exhaustion, enough files must be deleted to free inodes.

Not every filesystem manages inodes the same way. XFS allocates inodes dynamically by design, whereas ext4 typically fixes the inode count when the filesystem is created. On Windows NTFS, inodes are not exposed the same way as on ext4; NTFS uses the Master File Table (MFT) and its own metadata structures.

### 2.3. Quick comparison

| Indicator | Block/capacity exhaustion | Inode exhaustion |
|---|---|---|
| Used capacity | Near or at 100% | May still have ample free space |
| Used inodes | May still have free inodes | Near or at 100% |
| Commonly failing tasks | Writing large files, extending files, creating files | Creating new files or directories |
| Common causes | Large logs, databases, backups, file uploads | Massive numbers of small files, caches, sessions, spools, temp files |
| Linux check | `df -h` | `df -i` |
| Remediation direction | Find files consuming blocks, expand or free space | Locate directories with excessive files, clean up appropriately, or redesign storage |

### 2.4. Blocks, inodes, and file descriptors are three different things

- A block is space holding data on a filesystem.
- An inode is file metadata on Unix-style filesystems.
- A file descriptor is an identifier used by a process to access an open file, socket, or other resource.

An application can run out of file descriptors even when blocks and inodes remain available. In that case, errors typically say `Too many open files`. Check process limits and open descriptor counts rather than treating it as a disk-full error.

## 3. IOPS, throughput, and latency

Cloud volumes are commonly characterized by core performance metrics:

- **IOPS (Input/Output Operations Per Second):** the number of read/write operations per second a volume or device can serve.
- **Throughput:** the amount of data read/written per unit of time, typically measured in MiB/s or MB/s.
- **Latency:** the time required to complete one I/O operation, typically measured in ms or µs.
- **Queue depth:** the number of I/O requests waiting or in flight at a given layer of the I/O path.
- **IO size:** the average size of each read/write operation.

### 3.1. IOPS and throughput depend on I/O size

A workload composed of many small operations can demand high IOPS with modest throughput. Conversely, large sequential block operations can achieve high throughput with lower IOPS.

Approximate formula relating the two metrics:

\[
\text{Throughput (MiB/s)} \approx
\frac{\text{IOPS} \times \text{IO size (KiB)}}{1024}
\]

For example, 3,000 IOPS with an average 16 KiB I/O size equates to roughly 46.9 MiB/s if all operations sustain that rate. This is a theoretical conversion excluding overhead, volume/VM caps, and read/write characteristics.

Consequently, a volume may hit its IOPS limit before its throughput limit or vice versa. Monitor both.

### 3.2. Latency and queue depth

High latency means the application waits longer for each I/O operation to complete. High queue depth indicates many operations are waiting or in flight, which does not automatically prove a volume fault. Workloads may intentionally issue parallel I/O to utilize the device.

Evaluate queue depth alongside latency, IOPS, throughput, device utilization, and application response times:

- Rising queue paired with rising latency: the device or I/O path may be saturated.
- Rising queue with rising throughput and IOPS and stable latency: the workload is normally exploiting parallelism.
- Low queue yet high latency: individual requests are slow due to the storage backend, network path, sync writes, flushes, or another dependency.
- High I/O wait while volume metrics look normal: inspect the filesystem, kernel, network, application, and VM-level limits.

Never apply a single universal queue depth threshold across all volumes. Each device, driver, workload pattern, and platform behaves differently.

### 3.3. Volume limits and VM limits

Actual performance is typically governed by the lowest limit along the I/O path:

- Volume IOPS and throughput caps.
- IOPS/throughput caps tied to volume size or volume type.
- Aggregate I/O caps on the VM or instance family.
- Controller, virtual device, or network path caps.
- Filesystem, kernel, and application bottlenecks.
- Burst credits or platform performance mechanisms.

For instance, a VM attached to multiple volumes can generate combined I/O demand that exceeds the instance's aggregate cap even before any single volume hits its individual cap. Conversely, a high-I/O VM can still be bottlenecked by a single small volume.

## 4. Burst, baseline, and volume performance caps

Some volume types provide baseline performance plus the ability to burst for a limited period. When demand spikes, the volume can temporarily exceed baseline using burst credits or burst mechanisms. Once credits deplete or the burst window expires, performance drops back to the sustained baseline.

Indicators to check:

- IOPS or throughput rises briefly and then flattens at a ceiling.
- Burst balance/credit metrics drop low.
- Latency and queue depth climb after a period of sustained high load.
- Performance recovers once workload subsides or credits replenish.

Not all volume types use burst credits. Some allow provisioning IOPS/throughput independently or scaling dynamically. Consult documentation for the specific volume type and region.

When selecting a volume, determine:

1. Sustained baseline performance required continuously.
2. Peak demand and duration of workload spikes.
3. Burst capacity and credit replenishment rate, if applicable.
4. Aggregate VM I/O limits.
5. Cost of provisioned capacity, IOPS, and throughput.
6. Ability to modify performance dynamically while attached to the VM.

Do not rely on burst capacity for workloads with continuous high load if the baseline does not meet requirements.

## 5. Collecting evidence before making changes

When a disk is full or I/O is slow, record the following details before cleaning up files, rebooting, or modifying volumes:

- VM ID, hostname, region/zone, and instance type.
- Volume ID, volume type, size, and performance configuration.
- Filesystem, mount point, partition, LVM, or storage pool layout.
- Start time, duration, and active workloads.
- Capacity, inode, IOPS, throughput, latency, queue depth, and burst balance metrics.
- Application, database, kernel, and system logs.
- Recent changes: deployments, backups, log rotation, batch jobs, snapshots, resizes, or patches.
- Failing operations and scope of impacted users.

During an active production incident, do not run heavy benchmarks or bulk-delete files before understanding which data is actively used. Capturing initial state enables before/after comparison and preserves evidence for root cause analysis.

## 6. Diagnosing capacity and inodes on Linux

### 6.1. Inspect filesystem capacity

```bash
# Used and available space by filesystem
df -hT

# Used and available inodes
df -i

# Devices, filesystems, partitions, and mount points
lsblk -f

# Active mounts and mount options
findmnt
```

Use `df` to inspect mounted filesystems. If a cloud volume was expanded yet `df` remains unchanged, the partition or filesystem may not have been grown yet.

### 6.2. Locate directories and files consuming space

```bash
# Total space by top-level directory on the root filesystem
sudo du -xhd1 / 2>/dev/null | sort -h

# Inspect the log directory
sudo du -xhd1 /var/log 2>/dev/null | sort -h

# Find files larger than 1 GiB on the current filesystem
sudo find / -xdev -type f -size +1G -printf '%s %p\n' 2>/dev/null | sort -n

# Check size of a specific directory
sudo du -sh /var/cache
```

The `-xdev` option restricts searches to the same filesystem so traversal does not cross into other mounts. This is useful when the root filesystem is full while a separate data volume still has space.

Do not delete a file solely because it is large. Identify which application owns it, whether a process still uses it, and whether it is database or backup data that must be retained. For logs, prefer log rotation, retention policies, or truncating per application guidance rather than deleting files actively written by a running process.

### 6.3. Find where inodes are consumed

```bash
# Count files inside a subtree
sudo find /var -xdev -type f | wc -l

# Count files by immediate parent directory in an area under investigation
sudo find /var/spool -xdev -type f -printf '%h\n' 2>/dev/null |
  sort | uniq -c | sort -n

# Check entry counts in candidate directories
sudo find /var/cache -xdev -type f | wc -l
sudo find /tmp -xdev -type f | wc -l
```

`find` can consume heavy CPU and I/O on filesystems holding millions of files. Scope commands narrowly, run during lower load when possible, and avoid repeating excessively on production hosts.

### 6.4. Deleted files still consuming space

On Linux, unlinking a filename does not free blocks while a process still holds an open file descriptor. This commonly happens when logs are manually deleted while a daemon keeps writing to the old file.

Check with:

```bash
# Find deleted files still held open by processes
sudo lsof +L1

# Inspect file descriptors of a process once PID is known
sudo ls -l /proc/<PID>/fd
```

If deleted-but-open files are found, identify the owning process and reload/reopen logs according to application documentation. Do not kill processes arbitrarily, as doing so can interrupt transactions or lose unflushed data.

### 6.5. Reserved space and differences between df and du

Some filesystems reserve a portion of blocks for `root` or metadata. Thus, space shown as available to regular users can differ from total capacity. Additionally:

- `du` counts only files reachable by traversing directories.
- `df` reflects blocks allocated by the filesystem, including unlinked files still held open.
- Snapshots or thin provisioning at the cloud layer use separate accounting models.
- Filesystem metadata, journals, and reserved blocks also occupy space.

If `df` reports full while `du` across directories does not add up, check deleted-open files, reserved blocks, filesystem metadata, obscured mounts, and separate mount points.

## 7. Checking I/O on Linux

### 7.1. Observe per device

```bash
# Per-device I/O stats, latency, and queue
iostat -xz 1

# Processes performing heavy reads/writes (if sysstat is installed)
pidstat -d 1

# Overall process and I/O view
iotop -oPa

# Memory, run queue, swap, and I/O wait stats
vmstat 1
```

Useful fields in `iostat`:

- `r/s`, `w/s`: read/write operations per second.
- `rMB/s`, `wMB/s` or equivalent throughput fields: data read/written per second.
- `await`: average time for an I/O request to complete, including wait and service time as measured by the tool.
- `aqu-sz`: average queue length over the sampling interval in recent `sysstat` versions.
- `%util`: percentage of time the device had active I/O as reported by the tool.

Exact meanings vary by kernel, driver, and device type. On parallel storage or virtual devices, 100% `%util` does not always mean throughput/IOPS limits are reached. Combine with latency, queues, cloud metrics, and application SLOs.

### 7.2. Identify processes driving I/O

If a process generates heavy I/O:

- Check which files or databases it accesses.
- Determine whether backups, scans, compaction, vacuum, indexing, or log rotation are running.
- Compare against batch schedules and deployment timestamps.
- Check whether the application performs excessive synchronous writes or creates many tiny files.
- Check whether a retry storm is driving repeated reads/writes.

Do not throttle priority or kill a database process based solely on high I/O. That I/O may be normal activity required to maintain durability or serve queries.

### 7.3. Distinguish I/O wait from CPU bottlenecks

I/O wait is CPU idle time while the system has pending I/O tasks waiting to complete as tracked by the kernel. High I/O wait can signal slow storage, yet it does not identify the exact cause on its own.

Check together:

- CPU utilization and run queue.
- `iowait` and per-device latency.
- Queue depth, IOPS, throughput, and burst balance.
- Whether the application issues heavy synchronous writes/`fsync`.
- Network/storage paths and cloud-side metrics.
- RAM and cache hit ratios, since low RAM can trigger extra disk reads/writes.

## 8. Checking disks and filesystems on Windows

Windows uses NTFS or ReFS in many VM environments. Rather than Linux-style inodes, monitor volume space, filesystem metadata, the MFT, and file counts.

### 8.1. Volume and partition capacity

```powershell
# Inspect volumes, filesystems, and capacity
Get-Volume

# Inspect disks and partitions
Get-Disk
Get-Partition

# Volume free space
Get-CimInstance Win32_LogicalDisk |
  Select-Object DeviceID, Size, FreeSpace

# Check volume capacity using system utility
fsutil volume diskfree C:
```

### 8.2. Check I/O and latency

```powershell
# Key disk performance counters
Get-Counter '\PhysicalDisk(_Total)\Disk Reads/sec', '\PhysicalDisk(_Total)\Disk Writes/sec', '\PhysicalDisk(_Total)\Avg. Disk sec/Read', '\PhysicalDisk(_Total)\Avg. Disk sec/Write', '\PhysicalDisk(_Total)\Current Disk Queue Length' -SampleInterval 2 -MaxSamples 5

# Inspect processes with I/O activity
Get-Process | Sort-Object IOReadBytes -Descending |
  Select-Object -First 10 Name, Id, IOReadBytes, IOWriteBytes
```

Counter names can vary by Windows display language and system configuration. Performance Monitor can be used to pick the matching LogicalDisk, PhysicalDisk, and process counters. `Current Disk Queue Length` must be interpreted alongside latency and IOPS; a high queue value can be normal when a workload issues parallel I/O and the device responds quickly.

### 8.3. Check filesystems and system errors

```powershell
# Check filesystem online in read-only mode
chkdsk C:

# Inspect disk, NTFS, and storage events in the System log
Get-WinEvent -FilterHashtable @{
  LogName = 'System'
  StartTime = (Get-Date).AddHours(-24)
} | Where-Object {
  $_.ProviderName -match 'disk|Ntfs|stor|vol'
} | Select-Object TimeCreated, ProviderName, Id, LevelDisplayName, Message
```

Do not run `chkdsk` with repair flags in production without backups and a maintenance plan. Filesystem checks can generate substantial I/O load on large volumes.

## 9. Reading cloud-layer volume metrics

Guest metrics and storage-service metrics measure different segments of the I/O path. Correlate them across the same time window.

### Metrics to inspect

| Metric | Meaning | Diagnostic question |
|---|---|---|
| Volume read/write IOPS | Read/write operations per second | Is it hitting provisioned or baseline caps? |
| Volume read/write throughput | Bytes read/written per second | Is it hitting MiB/s or MB/s ceilings? |
| Read/write latency | Time to serve I/O | Is latency rising at the volume or only inside the guest? |
| Queue length / outstanding I/O | Requests waiting or in flight | Is queue rising alongside latency or merely reflecting concurrency? |
| Burst balance / credit | Remaining burst capacity if volume type supports it | Did performance drop after credits depleted? |
| Volume status / health | Device state and platform events | Are there volume errors, detaches, or maintenance events? |
| VM disk bandwidth/IOPS cap | Aggregate instance I/O limit | Does the sum across volumes exceed the VM ceiling? |

Metric names, units, sampling intervals, and reporting delays differ by provider. Some platforms expose per-volume metrics, while others also expose per-VM or per-host metrics. Never compare two metrics directly if their aggregation periods, units, or formulas differ.

### 9.1. Correlating guest and cloud metrics

- Guest reports high latency and cloud volume latency is also high: investigate volume, backend, provisioned limits, and burst behavior.
- Guest reports high latency while cloud volume latency looks normal: check the filesystem, kernel, guest queues, sync writes, drivers, and VM aggregate caps.
- Cloud volume hits IOPS cap while throughput stays low: the workload likely uses small I/Os; check I/O size and the IOPS cap.
- Throughput hits ceiling while IOPS stays modest: the workload likely uses large I/Os; check throughput caps and VM bandwidth.
- Individual volume is below its cap yet multiple volumes slow down together: check VM aggregate I/O, network path, or host-level limits.
- Cloud metrics look normal yet application is slow: inspect database locks, connection pools, CPU, RAM, caches, and dependencies.

### 9.2. Example of identifying limits

A VM has two volumes. The data volume is provisioned at 8,000 IOPS, yet the VM type supports only 10,000 total IOPS across all volumes. If the second volume is consuming 4,000 IOPS, the VM can hit its aggregate ceiling even though the data volume has not reached 8,000 IOPS.

In this situation, raising provisioned IOPS on the data volume alone may produce no improvement. Check instance limits, balance I/O across volumes, or switch to a VM type with a higher aggregate cap if the workload requires it.

Numbers are illustrative only. Check actual limits for your exact VM type, volume type, region, and configuration.

## 10. Handling full filesystems or exhausted inodes

Before cleaning up data, identify the filesystem, data owner, and retention policy. Never delete database files, WALs, transaction logs, journals, or backups merely because they consume space.

### 10.1. Procedure for full capacity

1. Identify the full mount point using `df -hT`.
2. Locate block-consuming directories and files using `du`/`find`.
3. Check for deleted files still held open by processes using `lsof +L1`.
4. Identify data eligible for cleanup under retention policies.
5. Stop or throttle write workloads if needed to halt continued growth.
6. Safely free space or expand the volume/filesystem.
7. Verify the application can write again and filesystem usage does not keep climbing abnormally.
8. Tune log rotation, retention, quotas, or alerts to prevent recurrence.

If the cloud volume is full at its provisioned tier while the filesystem is not fully used, check storage metrics and configuration. If the filesystem is full while the volume has unpartitioned space, extend the partition/filesystem.

### 10.2. Procedure for exhausted inodes

1. Confirm inode usage is near or at 100% with `df -i`.
2. Isolate directories containing huge file counts.
3. Identify file types: caches, sessions, temp files, spools, small logs, or artifacts.
4. Check whether the application actively needs those files.
5. Clean up expired files per policy or adjust file-creation behavior.
6. Verify inodes were freed and the application can create new files.
7. Redesign caching or storage to reduce small-file counts if needed.

If an ext4 filesystem was created with too few inodes, enlarging the block device alone does not increase existing inode counts. You may need to create a new filesystem with an appropriate inode density and migrate data safely. On XFS, inodes are allocated dynamically, though capacity or metadata limits can still occur. Check filesystem documentation before deciding.

### 10.3. Expanding volumes and filesystems on Linux

Expanding a disk typically involves two layers: increasing volume size in the cloud, then having the guest recognize the new size and growing the partition/LVM/filesystem. Exact sequence and commands depend on layout.

General procedure:

1. Confirm the volume supports online resize and take a snapshot/backup as required.
2. Increase volume size in the cloud console/API.
3. Verify the guest detects the new disk size with `lsblk`.
4. If partitioned, grow the partition with the appropriate tool.
5. If using LVM, extend the physical volume and logical volume according to layout.
6. Grow the filesystem with the filesystem-specific tool.
7. Verify with `df -hT` and test application writes.

Example for the first partition on an illustrative `/dev/nvme1n1` device:

```bash
# Confirm disk and partition layout
lsblk

# Grow partition (requires cloud-guest-utils or equivalent growpart package)
sudo growpart /dev/nvme1n1 1

# For an ext4 filesystem on that partition
sudo resize2fs /dev/nvme1n1p1

# For an XFS filesystem mounted at /data, use its dedicated command
sudo xfs_growfs /data

# Verify
df -hT /data
```

Do not run both `resize2fs` and `xfs_growfs` on the same filesystem. Choose the command matching the filesystem. NVMe device names and partition naming conventions vary by platform. Inspect `lsblk` and `findmnt` before running commands.

With LVM, the workflow may require `growpart`, `pvresize`, `lvextend`, and then filesystem resizing. Do not apply sample commands without positively identifying the PV, VG, LV, and mount point.

### 10.4. Expanding volumes and partitions on Windows

After enlarging the disk in the cloud:

1. Verify Windows detects the expanded disk.
2. Identify the exact disk and partition to extend.
3. Check maximum supported extension size and contiguous unallocated space.
4. Extend the partition/volume.
5. Verify capacity and application operation.

PowerShell example for an identified volume:

```powershell
# Inspect volumes and partitions
Get-Volume
Get-Partition

# Check maximum size the partition can grow to
Get-PartitionSupportedSize -DriveLetter F

# Extend partition to maximum supported size
$size = Get-PartitionSupportedSize -DriveLetter F
Resize-Partition -DriveLetter F -Size $size.SizeMax

# Verify
Get-Volume -DriveLetter F
```

Replace `F` with the actual drive letter. Never run commands on system or production volumes without verifying layout, backups, and change procedures. Partitions require contiguous unallocated space; if free space is not contiguous, handle the layout separately.

## 11. Handling slow I/O or throttled volumes

When latency climbs, distinguish whether the workload exceeded provisioned specs or a backend/guest fault occurred.

### 11.1. Identify the workload profile

- **Random small I/O:** many small operations at random offsets; typically sensitive to IOPS and latency. Example: OLTP databases.
- **Sequential large I/O:** reading/writing contiguous regions with large blocks; typically sensitive to throughput. Example: streaming, backups, or large-file processing.
- **Mixed workload:** combination of random and sequential read/write; measure read/write ratios and I/O sizes.
- **Metadata-heavy:** creating, deleting, renaming, or stat-ing massive numbers of small files; can bottleneck on filesystem metadata and inodes.
- **Sync-write-heavy:** applications frequently issuing flushes/`fsync` for durability; per-operation latency strongly impacts response times.

Never choose a volume based on capacity alone. A small database may require high IOPS; a large data warehouse may require higher throughput.

### 11.2. Check volume limits

Compare actual IOPS/throughput against provisioned specs and volume type. If hitting caps:

- Increase provisioned IOPS or throughput if supported by the volume type.
- Switch to a volume type tailored to the workload.
- Increase volume size if performance scales with capacity under the service's pricing/tier model.
- Reduce unnecessary I/O via caching, batching, or application tuning.
- Partition data or stripe/split workloads across multiple volumes if architecture and VM limits permit.

Enlarging a volume does not always raise performance. Some volume types couple performance to size; others decouple IOPS/throughput configuration. Check pricing and limits for your specific volume type.

### 11.3. Check VM limits

If aggregate I/O across multiple volumes hits the instance ceiling, upgrading an individual volume may not help. Remediation paths:

- Check the instance family's storage bandwidth/IOPS limits.
- Sum I/O across all attached volumes over the same interval.
- Check network bandwidth if volumes rely on network-attached storage paths.
- Check whether the instance type supports an optimized storage path.
- Consider resizing to an instance with a higher aggregate I/O ceiling.
- Separate read-heavy and write-heavy workloads where feasible.

### 11.4. Reduce unnecessary I/O

Application and OS optimizations can improve performance:

- Batch small writes together when durability requirements allow.
- Use appropriate caching and monitor cache hit ratios.
- Avoid scanning entire files or large directories too frequently.
- Optimize queries and indexes to reduce unnecessary random reads.
- Tune log levels, log rotation, and retention.
- Avoid overlapping backups, compaction, indexing, and batch jobs when they contend for I/O.
- Check for retry storms and repeated operations following timeouts.
- Use queues to smooth write rates when producers outpace storage.

Do not arbitrarily disable `fsync` or durability settings on databases. Doing so can boost speed at the cost of data loss during crashes or power failures.

## 12. Safe performance testing

Benchmarks confirm whether a configuration meets workload demands, yet benchmark tools can generate heavy load and write data. Run them only in test environments or approved maintenance windows, using dedicated test files on mounted filesystems.

### 12.1. Linux with fio

`fio` can simulate diverse workload patterns and measure IOPS, throughput, and latency. The example below uses a test file inside `/mnt/bench` without writing directly to raw block devices:

```bash
# Create a test directory on a mounted filesystem
sudo mkdir -p /mnt/bench

# Example short 4 KiB random read/write workload
# Run only on test volumes with a dedicated test file.
sudo fio --name=rand-mix \
  --filename=/mnt/bench/fio-test.bin \
  --size=2G \
  --rw=randrw \
  --rwmixread=70 \
  --bs=4k \
  --iodepth=16 \
  --numjobs=2 \
  --direct=1 \
  --runtime=60 \
  --time_based \
  --group_reporting
```

Meaning of key parameters:

- `rw=randrw`: mixed random read/write.
- `rwmixread=70`: target 70% reads, remainder writes.
- `bs=4k`: 4 KiB I/O block size.
- `iodepth=16`: target outstanding I/Os per job in supported engines.
- `numjobs=2`: two concurrent jobs.
- `direct=1`: bypasses most guest page-cache effects for this test.
- `runtime=60`: 60-second run duration.

Results depend on filesystem, drivers, caches, device, volume type, and VM limits. Do not compare benchmarks across different workload profiles. Remove test files once confirmed no process uses them and per data policy.

### 12.2. Windows

You can use DiskSpd in test environments to simulate workloads and measure latency/IOPS/throughput. Create a dedicated test file on a test volume and select appropriate size, read/write ratio, block size, queue depth, and duration. Never run benchmarks on raw disks or production volumes actively serving databases without a load and backup plan.

### 12.3. Interpreting benchmark results

Look beyond average IOPS alone. Inspect:

- Separate read/write IOPS and throughput.
- Mean latency and latency percentiles if provided by the tool.
- CPU utilization and memory pressure during the run.
- Actual queue depth achieved.
- Warm-up behavior and cache effects.
- Single-job results versus realistic concurrency.
- Concurrent load from other applications.

Benchmarks must mirror the I/O size, read/write ratio, concurrency, and durability demands of the real workload.

## 13. Symptom-based troubleshooting workflows

| Symptom | First check | Potentially appropriate remediation |
|---|---|---|
| `df -h` shows 100%, `df -i` has plenty free | Find large files/directories, deleted-open files, reserved blocks | Clean per retention or expand volume/filesystem |
| `df -h` has free space yet `df -i` shows 100% | Locate directories with excessive small files | Clean expired files, reduce file churn, or redesign storage |
| Filesystem has space yet app reports `Too many open files` | Check descriptors and process limits | Fix leaks, close files properly, adjust limits carefully |
| High latency and volume hits IOPS cap | Compare provisioned vs. actual IOPS and queue | Increase IOPS, change volume type, or reduce random I/O |
| Throughput hits ceiling while IOPS stays low | Inspect I/O size and throughput cap | Increase throughput or optimize sequential I/O |
| Multiple volumes slow down together | Check instance-level I/O/network cap | Change instance family, rebalance workloads, or reduce aggregate I/O |
| `df` shows full yet `du` cannot account for it | Check `lsof +L1`, reserved blocks, and mounts | Reopen logs, fix mounts, or handle filesystem per procedure |
| Disk metrics look normal yet app is slow | Check sync writes, locks, database, CPU/RAM, and network | Optimize app/dependencies and pinpoint latency at the right layer |
| Cloud volume expanded yet filesystem unchanged | Inspect partitions, LVM, and filesystem | Expand the right partition/LVM/filesystem layer |

### General diagnostic sequence

1. Determine whether the fault is block exhaustion, inode exhaustion, file descriptors, or slow I/O.
2. Record VM, volume, filesystem, mount point, timestamp, and active workload.
3. Compare guest and cloud metrics over the exact same time window.
4. Locate the process or directory generating heavy I/O or files.
5. Identify whether the limit sits at the volume, VM, filesystem, or application layer.
6. Choose the smallest reversible fix: retention-compliant cleanup, workload tuning, or capacity/spec expansion.
7. Execute in a narrow scope or maintenance window if risk exists.
8. Verify space, inodes, latency, queues, application health, and data integrity afterward.
9. Update alerts, runbooks, and capacity plans to prevent recurrence.

## 14. Designing monitoring and prevention

### 14.1. Capacity and inode alerts

Alert on both usage percentage and remaining free space. On a 100 GiB filesystem, 10% remaining is 10 GiB; on a 2 TiB filesystem, 10% remaining is 200 GiB. Time remaining until exhaustion can differ dramatically.

Monitor:

- Filesystem usage percentage.
- Free bytes and space growth rate.
- Inode usage percentage on fixed-inode filesystems.
- Remaining inodes and file creation rate.
- Log, temp, cache, and database growth.
- Deleted-but-open files if appropriate tooling is available.

Base alerts on projected time to exhaustion when possible, rather than a single static percentage threshold.

### 14.2. I/O performance alerts

Monitor per volume and per VM:

- Read/write IOPS and throughput.
- Read/write latency.
- Queue depth or outstanding I/O.
- Burst balance/credits.
- VM storage bandwidth/IOPS caps.
- Disk errors, timeouts, detaches, and health events.
- I/O wait and application latency.

Use sustained duration windows and baselines to reduce alert noise. A brief I/O spike may be a normal backup; prolonged high I/O paired with rising p99 latency and queue depth indicates user-facing impact.

### 14.3. Application-layer prevention

- Configure log rotation and retention policies.
- Cap cache sizes and temporary file directories.
- Purge expired sessions, spools, and artifacts.
- Use object storage for large or long-lived file objects where appropriate.
- Avoid generating millions of small files when they can be consolidated into databases or object storage.
- Enforce per-user or per-project quotas when supported by the filesystem.
- Separate logs, databases, and scratch data onto dedicated volumes when needed.
- Plan capacity around data growth and peak loads.

### 14.4. Infrastructure-layer prevention

- Select volume types matching IOPS, throughput, and latency profiles.
- Check aggregate instance I/O limits.
- Provision adequate capacity and performance headroom.
- Verify online resize capabilities and volume limits.
- Take snapshots/backups before risky changes.
- Rehearse restores and filesystem expansions.
- Track provisioned IOPS/throughput and capacity costs.
- Periodically re-evaluate volumes as workloads evolve.

## 15. Practical example: database slows down at end of day

A VM running a database has a 500 GiB data volume. Queries run normally during the day, but end-of-day reporting drags and applications time out. Dashboards show:

- Filesystem still has 35% free capacity.
- Plenty of free inodes remain.
- Volume IOPS is near its configured ceiling.
- Throughput remains below its cap.
- Read latency climbs alongside queue depth.
- A batch job runs concurrently with backups.

The operations team investigates:

1. `df -h` and `df -i` confirm neither block exhaustion nor inode exhaustion.
2. `iostat` shows heavy small random I/O and rising `await`.
3. Cloud metrics confirm the volume is hitting its IOPS cap, and burst balance is depleted if the volume uses burst credits.
4. Job schedules show reporting batches and backups overlapping, generating heavy concurrent reads/writes.
5. Operations moves backups outside reporting hours, tunes concurrency, and re-measures.
6. If baseline load still regularly exceeds capacity, the team evaluates raising provisioned IOPS or moving to a more suitable volume tier.
7. Post-change, they verify p95/p99 query latency, queue depth, and cost.

Expanding volume size to 1 TiB alone may not help if the volume type does not scale IOPS with size or if the cap sits at the instance level. Verify the performance model before making changes.

### Variant: inode exhaustion despite free disk space

A Linux worker creates a dedicated temporary file for every request. After several days, `df -h` shows 40 GiB free, yet `df -i` hits 100%. The worker cannot create new files and returns `No space left on device`.

Operations locates millions of old files in the temp directory, verifies which ones are expired and no longer held by running processes, and cleans them up per retention rules. Developers add post-processing file cleanup, cap temporary file counts, and add inode alerts. If the ext4 filesystem was formatted with too few inodes for long-term workload needs, the team plans a migration to a new filesystem with an appropriate inode ratio.

## 16. Common misconceptions

- **Free disk space means you can always create files.** Filesystems can exhaust inodes or metadata even with free blocks.
- **Inode exhaustion means the cloud volume is out of capacity.** Inodes are filesystem metadata limits; expanding block device capacity does not automatically add inodes.
- **High queue depth is always an error.** Queue depth must be read alongside latency, IOPS, throughput, and workload concurrency.
- **High IOPS equals high throughput.** I/O size determines bytes per operation; small-I/O workloads can max out IOPS at low throughput.
- **Expanding volume size always increases IOPS.** Performance scaling depends on volume type; some types decouple size from IOPS/throughput.
- **If a volume is below its cap, the VM still has spare I/O.** The instance may have an aggregate cap lower than the sum of attached volumes.
- **Deleting a log file immediately frees disk space.** An unlinked file still held open by a process retains its blocks until the descriptor closes.
- **Low CPU means the application is not bottlenecked.** The application may be stalled on disk I/O, sync writes, or dependencies.
- **Running fio on a production disk is a harmless quick check.** Benchmarks generate heavy load and write data; use test environments and dedicated test files.
- **Expanding the disk in the cloud is enough.** The guest may still have old partition or filesystem boundaries; expand the right layers.
- **Disabling fsync for speed is safe.** Weakening durability increases data-loss risk during crashes or power loss.

## 17. Self-check

**Scenario 1:** A Linux filesystem has 25 GiB free, yet the application reports `No space left on device` when creating files. What do you check first?

**Hint:** Run `df -i` to inspect inodes. If inodes are exhausted, find the directory holding abnormally many small files and identify expired files safe to clean.

**Scenario 2:** `df -h` reports 100%, yet `du` does not sum to full capacity. What causes should you inspect?

**Hint:** Check deleted files still held open by processes with `lsof +L1`, reserved blocks, filesystem metadata, and obscured mount points.

**Scenario 3:** A volume hits its provisioned IOPS cap while throughput stays low. Can this happen?

**Hint:** Yes. A workload issuing many small I/Os can hit the operations-per-second limit before hitting the byte-throughput limit. Check I/O size and read/write profile.

**Scenario 4:** Individual volumes are below their IOPS caps, yet every disk attached to the VM slows down simultaneously. What should you inspect?

**Hint:** Check the instance's aggregate IOPS/throughput limit, network/storage path, and competing workloads across volumes.

**Scenario 5:** After expanding a cloud volume, `df` still displays the old size. Why?

**Hint:** The guest may see the larger disk, yet the partition, LVM, or filesystem has not been grown. Check `lsblk`, `findmnt`, and layout before running the matching grow tool.

**Scenario 6:** The database slows down when backups run concurrently; latency and queue depth spike while plenty of capacity remains. What should you adjust first?

**Hint:** Check IOPS/throughput caps and workload schedules. Separate backup windows, limit concurrency, or adjust volume specs after benchmarking.

## Conclusion

Disk-full and slow-I/O incidents must be distinguished across block capacity, inodes, file descriptors, volume performance, and VM I/O limits. Use `df`/`du`/`lsof` and OS utilities to assess filesystem health; correlate cloud IOPS, throughput, latency, queue depth, and burst metrics to pinpoint storage bottlenecks. When remediating, identify data eligible for cleanup, expand the proper partition/filesystem layers, or tune volumes and workloads to match actual profiles. Monitoring capacity, inode, and performance trends alongside tested backup/restore procedures helps catch issues early and prevent recurrence.

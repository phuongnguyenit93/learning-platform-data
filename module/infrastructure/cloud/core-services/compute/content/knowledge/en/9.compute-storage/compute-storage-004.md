# Choosing Capacity, Disk Types, and Per-Instance I/O Limits

Storage attached to cloud compute directly affects boot times, data read/write speed, application latency, and operational costs. A large-capacity volume does not guarantee fast I/O; a high-IOPS SSD will not help an application either if the instance is capped on storage bandwidth or if the workload is mainly waiting on network and CPU.

When choosing storage for a VM, you must evaluate **capacity, IOPS, throughput, latency, access pattern, and instance-level I/O limits** together. You also need to determine whether data must survive the VM lifecycle or can be regenerated, along with durability, backup, encryption, and future scaling requirements. The goal is to provide sufficient space and performance for both normal and peak loads at a reasonable cost.

## 1. Fundamental Storage Metrics

### Capacity

Capacity is the amount of data a volume can store, usually expressed in GB or GiB. When planning capacity, account for business data, indexes, logs, temporary files, write-ahead/update overhead, operational headroom, and growth rate.

Avoid provisioning a volume tightly fitted to current data size. Filesystems need free space to operate; databases may need temporary space for sorting, index rebuilds, vacuuming, compaction, or transaction logs. When a filesystem approaches full capacity, performance and write capability can degrade, or the application may even halt.

### IOPS

IOPS (Input/Output Operations Per Second) is the number of read/write I/O operations completed per second. IOPS is typically critical for workloads with many small, random operations, such as OLTP databases, metadata, queues, or filesystems with many small files.

IOPS does not tell you the size of each operation. 10,000 IOPS with 4 KiB blocks transfers vastly different data volume than 10,000 IOPS with 256 KiB blocks. Therefore, evaluate IOPS together with block size, read/write mix, and latency.

### Throughput

Throughput is the amount of data read or written per unit of time, usually measured in MB/s or MiB/s. It is critical for workloads transferring large, continuous blocks of data such as backups, ETL, video processing, data scans, or sequential reads of large files.

For workloads with relatively consistent I/O sizes, throughput can be estimated as:

\[
\text{Throughput} \approx \text{IOPS} \times \text{I/O size}
\]

For example, 6,000 IOPS with 16 KiB blocks yields a theoretical throughput of:

\[
6{,}000 \times 16\text{ KiB} = 96{,}000\text{ KiB/s}
\approx 93.75\text{ MiB/s}
\]

This is a simplified calculation. Actual throughput is also constrained by the volume, instance, filesystem, queuing, network, and how the workload issues I/O.

### Latency

Latency is the time from when an application submits an I/O request until the operation completes. It is typically measured in milliseconds (ms) or microseconds (µs). Transactional databases and interactive applications are usually more sensitive to latency than aggregate throughput.

Do not rely solely on average latency. Monitor percentiles such as p50, p95, and p99 to spot abnormally slow I/Os. A system with low average latency but high p99 can still trigger timeouts or feel sluggish to users.

### Queue Depth and Concurrency

Queue depth is the number of I/O requests waiting or executing concurrently. Increasing queue depth can help a storage device or service sustain higher throughput, especially for parallel workloads. However, overly deep queues increase wait times and degrade latency.

Applications with low concurrency may not reach advertised maximum IOPS because they do not submit enough concurrent requests. Conversely, a multi-worker workload can build large queues and hit volume or instance limits. Benchmark with queue depths and job counts close to production behavior.

## 2. Identifying Workload Access Patterns

Storage specifications should be selected based on the I/O patterns the application actually generates.

| Workload type | I/O characteristics | Typically critical metrics |
|---|---|---|
| OLTP database | Many small, random operations, mixed read/write, sensitive to fsync | IOPS, p95/p99 latency, write latency, and consistency |
| Data warehouse / analytics | Reads large blocks, table and file scans | Read throughput, capacity, and parallelism |
| Backup / restore | Sequential writes or reads of large blocks | Throughput, completion time, and data transfer cost |
| Log / queue | Sequential writes or appends, may require flushes | Write throughput, latency, and data durability |
| Web / application server | Many small files, packages, logs, and caches | Capacity, moderate latency, and steady IOPS |
| CI/CD and builds | Reading/writing small files, creating/deleting many files, extraction | IOPS, metadata performance, and temporary capacity |
| Media processing | Reading/writing large files and sequential data | Throughput, capacity, and scalability |
| Regenerable cache | Fast reads/writes, data loss is acceptable | Latency, IOPS, and cost; local disk may fit |

A single application may combine multiple access patterns. For example, a database might need high IOPS for transaction logs yet high throughput for backups and batch scans. You can separate data, logs, temp, and backups onto dedicated volumes if the platform and application benefit from I/O isolation.

## 3. Compute-Attached Storage Types

### Persistent Block Storage

A persistent block volume is a block device provided over the cloud's storage network or fabric. A volume can be attached to a VM as a disk and generally persists independently of the VM lifecycle unless deleted by policy.

Common characteristics:

- Can be detached from one VM and attached to another within service limits.
- Capacity or performance can be scaled according to platform capabilities.
- Supports snapshots, encryption, and backups per provider features.
- I/O traverses cloud storage infrastructure and internal networking; latency and throughput depend on both the volume and the instance.

Persistent block storage fits root disks, databases, stateful applications, and data that must survive stop/start or VM replacement. However, do not treat a volume as an independent backup: operator mistakes, accidental deletions, ransomware, or application bugs can still corrupt data on the volume.

### General-Purpose SSD

General-purpose SSDs typically balance price, IOPS, and throughput. Some services scale performance with provisioned capacity; others allow configuring IOPS or throughput independently within limits.

This type fits boot volumes, application servers, small-to-medium databases, development environments, and general-purpose workloads. Check baseline performance, maximums, burst mechanisms, and pricing by capacity or performance.

### Provisioned IOPS SSD

Provisioned IOPS SSD lets you choose a guaranteed IOPS level within a configurable range. It fits large databases, transactional workloads, or applications requiring steady I/O performance and strict latency targets.

Provisioned IOPS does not guarantee the workload will hit the configured number in every scenario. The volume remains bound by throughput caps, block size, queue depth, instance-level caps, filesystem overhead, and the application's ability to drive I/O. Some services enforce a maximum IOPS-to-capacity ratio; check configuration rules before setting high tiers.

### Throughput-Optimized or Capacity-Optimized HDD

Cloud HDDs generally cost less per unit of capacity than SSDs, fitting large datasets, sequential access, log archives, or latency-tolerant workloads. Some variants are throughput-optimized, while others target cold or infrequently accessed data.

HDDs are generally unsuitable for OLTP databases with many small random I/Os or workloads requiring low latency. Never select solely on capacity and price if the application requires high IOPS.

### Local NVMe / Instance Store

Local NVMe is storage physically attached to the instance's host. It can deliver low latency and high throughput due to a shorter I/O path than network-attached volumes. Some instances offer multiple local NVMe devices that can be combined for higher capacity or performance.

Local NVMe typically has a lifecycle tied to the host or instance. Data may be lost upon termination, host replacement, certain stop/start operations, or hardware failure. Behavior across reboots or stop/start depends on the instance type and provider guarantees.

Local NVMe fits caches, scratch space, intermediate data, temporary processing, and regenerable replicas. For databases, use it as primary storage only when the application has proper replication, backups, and recovery mechanisms; never rely on local disk as the sole copy.

### File Storage and Object Storage

File storage provides a network-shared filesystem interface, suited for multiple VMs accessing a shared directory tree, home directories, shared content, or applications requiring file protocols. Performance depends on throughput, IOPS, client count, and metadata operations.

Object storage stores data as objects and metadata, accessed via API/HTTP rather than a standard block device. It fits backups, logs, artifacts, media, and large durable datasets. Object storage generally cannot be mounted natively as a block disk without a gateway or filesystem adapter; such access layers have different limits and behaviors than block storage.

Do not pick file/object storage simply to replace a block volume without checking application semantics, locking, consistency, renames, random writes, and latency.

### Quick Comparison

| Storage type | Typical performance | Durability / lifecycle | Matching workloads |
|---|---|---|---|
| General-purpose SSD volume | Balanced IOPS and throughput | Persistent per volume policy | Boot, general apps, medium databases |
| Provisioned IOPS SSD | High IOPS, explicit performance tiering | Persistent per volume policy | OLTP, databases, latency-sensitive workloads |
| Throughput HDD | Sequential throughput, lower random IOPS than SSD | Persistent per volume policy | Backups, large logs, sequential scans |
| Cold HDD | Low capacity cost, slower access | Persistent per volume policy | Infrequently accessed data |
| Local NVMe | Low latency, high throughput | Host/instance-dependent; data may be lost | Caches, scratch, intermediate data |
| File storage | File sharing over the network | Per file service | Shared directories and multi-client apps |
| Object storage | API access, optimized for object data | Per object service | Backups, archives, media, artifacts |

Specific names and characteristics vary by cloud provider. Always use specifications for the exact service and region when designing for production.

## 4. Calculating Required Capacity

Capacity should account for current data, growth rate, temporary space, logs, indexes, and operational headroom.

A simple estimation formula:

\[
\text{Capacity}_{required} =
(\text{Data} + \text{Index} + \text{Logs} + \text{Temp})
\times (1 + \text{Growth})
\times (1 + \text{Headroom})
\]

Here, `Growth` is the expected increase over the planning horizon, and `Headroom` is the buffer to keep the filesystem from running near full. Adjust the formula if logs have separate retention, data is compressed, replication is used, or temp lives on another volume.

### Database Sizing Example

Suppose a database currently has:

- Data: 500 GiB.
- Indexes: 100 GiB.
- Logs and journals: 50 GiB.
- Projected 30% growth over the planning period.
- Extra 20% headroom after accounting for growth.

Capacity before buffers:

\[
500 + 100 + 50 = 650\text{ GiB}
\]

After growth:

\[
650 \times 1.30 = 845\text{ GiB}
\]

After headroom:

\[
845 \times 1.20 = 1{,}014\text{ GiB}
\]

You might choose a ~1 TiB volume if service limits and unit conversions align. Before finalizing, separately account for backups, snapshots, transaction log retention, compaction, and maintenance operations. Not all data needs to sit on a single volume.

### Tracking Growth Rate

Measure disk usage daily or weekly to identify trends. For databases, track data, indexes, transaction logs, temp, backup staging, and filesystem free space separately. Use average growth rates alongside periodic peaks to forecast when expansion is needed.

Set alerts by both percentage and absolute capacity. For example, an 80% full 20 GiB volume has only 4 GiB left, whereas an 80% full 10 TiB volume still has substantial absolute space. Appropriate thresholds depend on write velocity and the time needed to expand the volume.

## 5. Choosing IOPS and Throughput by Workload

### Identifying Read/Write Mix and Block Size

Before selecting a volume, gather:

- Read/write ratio (e.g., 70% read, 30% write).
- Common block sizes and I/O size distribution.
- Random vs. sequential; synchronous vs. asynchronous.
- Worker count, concurrency, and queue depth.
- IOPS, throughput, and latency at both normal and peak load.
- Peak duration and whether burst behavior occurs.

An OLTP database may generate many random 4 KiB or 8 KiB operations, whereas backups generate sequential 1 MiB operations. The same volume may achieve high IOPS in small-block tests yet fail to hit target throughput at larger block sizes.

### Calculating IOPS from Application Load

If you know the average I/O operations per request and requests per second, you can estimate:

\[
\text{IOPS}_{required} \approx
\text{I/O operations per request}
\times \text{requests per second}
\]

For example, a service handling 800 requests/second where each request generates an average of 12 block read/write operations:

\[
800 \times 12 = 9{,}600\text{ IOPS}
\]

To maintain 30% headroom, the target tier would be around 12,500 IOPS. This is an initial estimate; cache hits, write coalescing, batching, the filesystem, and the database engine can alter the actual I/O reaching the volume.

### Calculating Throughput from Block Size

If a workload requires 8,000 IOPS with an average 32 KiB block:

\[
8{,}000 \times 32\text{ KiB} = 256{,}000\text{ KiB/s}
\approx 250\text{ MiB/s}
\]

The volume must support both the IOPS and the corresponding throughput, and the instance must have sufficient storage bandwidth. If either limit is lower, the workload will be capped at the lower limit.

### Reads and Writes May Have Different Limits

Some services exhibit asymmetric read and write performance, especially with caches, replication, or durable write mechanisms. Synchronous write workloads may be more sensitive to write latency than aggregate write throughput. Databases using `fsync` or log flushes generally require consistent durable write completion times.

Measure read IOPS, write IOPS, read throughput, write throughput, and directional latencies separately when tools allow. Average read/write ratios can obscure periodic log writes or checkpoints.

## 6. Understanding Volume and Instance I/O Limits

This point is frequently overlooked during sizing. A volume may be provisioned for 20,000 IOPS and 500 MiB/s, while the VM supports only 10,000 aggregate IOPS or 300 MiB/s for storage. In that case, attaching a faster volume will not push the workload past the instance's limit.

### Two Layers of Limits

A **volume-level limit** is the maximum or baseline determined by volume type, capacity, and IOPS/throughput configuration. Each volume may have its own limits for IOPS, throughput, maximum size, queue depth, or burst.

An **instance-level limit** is the aggregate I/O ceiling the instance can exchange with the storage service. It may be expressed as total IOPS, total throughput, or EBS/block storage bandwidth. All volumes attached to the same VM share this limit.

Actual performance is typically constrained by the lowest ceiling in the I/O path:

\[
\text{Effective I/O} \leq
\min(\text{Volume limit},\text{Instance limit},\text{Workload demand})
\]

Additional limits come from the filesystem, drivers, network path, hypervisor, and storage service.

### Multi-Volume Aggregation Example

Suppose a VM has two volumes:

| Volume | Max IOPS | Max throughput |
|---|---:|---:|
| Data | 8,000 | 250 MiB/s |
| Log | 6,000 | 200 MiB/s |
| Volume sum | 14,000 | 450 MiB/s |

If the instance only supports 10,000 aggregate IOPS and 300 MiB/s for storage traffic, both volumes cannot hit their maximums simultaneously. The VM's total performance is capped by the instance. During design, check the limits table for the exact instance family and size, and verify whether limits depend on machine size or burst mode.

### Baseline, Burst, and Credits

Some volumes or instances provide a baseline I/O level and allow bursting for a period via credits or similar mechanisms. For short workloads, bursting can deliver high performance; under sustained load, performance can drop to baseline once credits deplete.

For continuously running databases, never size based on peak burst performance if the baseline falls below steady demand. Inspect credit balance, burst duration, refill rate, and post-exhaustion behavior. Benchmarks must run long enough to detect degradation after the burst window ends.

### Do Multiple Volumes Automatically Increase Performance?

Attaching multiple volumes can increase aggregate IOPS/throughput if the service supports performance aggregation and the instance has headroom. However, adding volumes does not scale infinitely. Instance-level caps, filesystems, RAID/LVM, queues, and application behavior can all become bottlenecks.

Striping via RAID 0 or LVM can spread I/O across multiple volumes to raise throughput or IOPS, but it adds complexity and means a single volume failure can break the entire logical volume. Use it only with clear benchmarks, backups, and recovery plans.

## 7. Separating Volumes by Role

Separating root and data volumes clarifies lifecycle management and recovery. Some workloads benefit from separating data, transaction logs, temp, and backup staging to reduce I/O contention.

| Volume | Contents | Design goal |
|---|---|---|
| Root | OS, packages, and agents | Right-sized capacity, easy image replacement or OS recovery |
| Application | Binaries, artifacts, or application files | Depends on deployment speed and access pattern |
| Data | Tables, indexes, or primary data | Prioritize durability, IOPS, and workload-matched latency |
| Transaction log | WAL, redo logs, or journals | Consistent writes, low latency, and data protection |
| Temp / scratch | Temporary files, sorts, build outputs | Can use a separate volume or local NVMe if regenerable |
| Backup staging | Temporary backup files before moving to object storage | Read/write throughput and easy cleanup |

Separating volumes can improve manageability, though it does not always boost performance. If all volumes still share a single instance cap or a single filesystem queue, gains may be negligible. Clarify whether the goal is fault isolation, backup management, lifecycle separation, or I/O scaling before splitting volumes.

## 8. Filesystems and Guest OS Configuration

The cloud provides a block device; the guest OS must detect the device, create partitions and filesystems, and mount them into the directory tree. Performance and safety also depend on configuration inside the VM.

### Linux

Basic inspection commands:

```bash
# List disks, partitions, and mount points
lsblk -o NAME,SIZE,TYPE,FSTYPE,MOUNTPOINTS

# View filesystems and used capacity
df -hT

# View UUIDs and filesystem types
blkid

# Monitor per-device IOPS, throughput, latency, and queue depth
iostat -xz 1

# Inspect kernel logs related to disks and filesystems
dmesg -T | grep -Ei 'nvme|scsi|virtio|I/O error|filesystem'
```

When mounting data volumes, use UUIDs or stable identifiers rather than assuming a disk will always be `/dev/sdb`. Device names can shift when disks are added, instance families change, or controllers differ. Configure `/etc/fstab` with appropriate options so a missing volume does not unexpectedly hang system boot.

### Windows

On Windows, use Disk Management or PowerShell to inspect disks, partitions, and filesystems:

```powershell
# List disks and status
Get-Disk

# View volumes, filesystems, and capacity
Get-Volume

# View partitions per disk
Get-Partition
```

Performance Monitor can track counters such as `Disk Reads/sec`, `Disk Writes/sec`, `Disk Read Bytes/sec`, `Disk Write Bytes/sec`, `Avg. Disk sec/Read`, `Avg. Disk sec/Write`, and `Current Disk Queue Length`. Interpret queue length alongside disk type, volume count, and workload concurrency.

### Choosing a Filesystem

Linux commonly uses ext4 or XFS; Windows commonly uses NTFS or ReFS in supported scenarios. Filesystem selection depends on OS, application, file sizes, file counts, snapshot/backup tooling, and operational needs. No single filesystem is always fastest for every workload.

Consider:

- Whether block size and allocation unit fit the workload.
- Whether metadata operations could become a bottleneck.
- Whether journaling or write barriers meet durability requirements.
- Whether the filesystem supports online expansion on the platform.
- Whether backup, snapshot, and recovery tools support the filesystem.
- Whether discard/TRIM options are recommended for the volume type.

Never disable consistency or durability guarantees just to boost benchmarks without understanding the data risks.

## 9. Expanding Capacity and Changing Performance

Many clouds support expanding volume capacity while the VM is running, but after the control-plane change, the guest OS may still need to expand the partition and filesystem. Exact steps depend on the OS, filesystem, volume type, and provider.

### Expanding a Volume

General workflow:

1. Verify backups/snapshots and confirm they can be restored.
2. Check whether the volume type supports online resizing.
3. Increase capacity or performance in the control plane per service instructions.
4. Verify the guest OS sees the new block device size.
5. Expand the partition if present, then expand the filesystem using OS tools.
6. Run `df`, `lsblk`, or equivalent tools to confirm the new capacity.
7. Monitor latency, IOPS, and throughput after the change.

Increasing capacity does not always automatically increase IOPS or throughput. On capacity-scaled volumes, increasing size raises the baseline; on provisioned IOPS volumes, performance settings must be adjusted separately. Check service limits and billing rules.

### Shrinking a Volume

Shrinking is usually complex and may not be supported directly. Some services only allow capacity increases. To downsize, you typically create a new smaller volume, copy data at the application or filesystem level, verify consistency, and cut over the workload. Never attempt unsupported block-device or filesystem shrinking, as it risks data loss.

### Changing IOPS and Throughput

If the service allows tuning IOPS or throughput independently, changes may take effect online but come with limits, propagation delays, and costs. Check:

- Minimum/maximum values and IOPS-to-capacity ratios.
- Maximum throughput per volume and per instance.
- Rate limits on how often changes can be made within a window.
- How long changes take to apply and whether temporary performance impact occurs.
- Whether higher costs persist once workload demand drops.

## 10. Measuring Storage Performance

Never select a volume type solely on marketing specs or benchmarks from an unrelated workload. Measure with block sizes, read/write mixes, queue depths, concurrency, and run durations close to real behavior.

### Metrics to Collect

- Read and write IOPS.
- Read and write throughput.
- p50, p95, and p99 latency.
- Queue depth and wait time.
- CPU iowait and application CPU utilization.
- Cache hit ratio and actual data reaching the volume.
- Burst credits or throttling status if the service uses them.
- Instance storage bandwidth/IOPS usage and remaining headroom.

### Using fio on Linux

`fio` generates I/O loads with configurable block size, read/write mix, job count, and queue depth. The example below illustrates a random read/write test against a pre-created test file on a test volume:

```bash
fio --name=rand-mixed \
  --filename=/mnt/bench/fio-test.bin \
  --size=4G \
  --rw=randrw \
  --rwmixread=70 \
  --bs=4k \
  --iodepth=32 \
  --numjobs=4 \
  --runtime=60 \
  --time_based \
  --direct=1 \
  --group_reporting
```

Run tests on a dedicated volume or disposable test file—never directly against a device containing production data. Write tests can overwrite data; even read tests generate load and impact live services. Run during test windows, use a dataset large enough to minimize caching artifacts, and repeat across multiple profiles matching the application.

For sequential workloads, test larger block sizes such as 256 KiB or 1 MiB with `--rw=read`/`--rw=write` on a separate test file. Do not draw conclusions for every access pattern from a single profile.

### Interpreting Results

If IOPS is low and latency is high, the volume or instance may have hit a ceiling, queues may be too deep, or the device may suffer contention. If throughput is low despite high IOPS, block size may be small or the application may be issuing many tiny operations. If CPU iowait is high, processes may be waiting on storage; if CPU is low yet application latency is high, investigate database locks, networking, or downstream dependencies.

`fio` results measure the capability of the I/O path under test conditions, not guaranteed database performance. Databases are also shaped by caching, transactions, fsync, concurrency, indexes, and data layout.

## 11. Cost and Data Durability

Storage costs extend beyond price per GiB/month. They may include:

- Provisioned volume capacity, including unused space.
- Provisioned IOPS or throughput beyond what is included with capacity.
- Snapshots, backups, replication, and replica storage capacity.
- Data transfer or cross-zone/cross-region access if billed by the service.
- Static performance reservations or unattached/orphaned volumes.
- Local NVMe included in instance pricing that pushes up the instance family cost.
- File/object requests, retrievals, lifecycle transitions, and egress per service model.

When comparing two configurations, calculate cost per completed unit of work—such as cost per transaction, per GB processed, or restore duration. A pricier volume may shorten batch jobs or reduce the number of instances needed; conversely, over-provisioned IOPS incurs continuous charges even when the workload uses only a fraction.

### Durability, Availability, and Backups

Durability is the ability to prevent data loss; availability is the ability to access data when needed. A persistent volume may have high durability per service guarantees, yet it still does not replace independent backups. Application bugs, malware, accidental deletions, ransomware encryption, or misconfigurations can be written to the volume and propagate to the latest snapshot if snapshots are unprotected.

Data protection design should review:

- Scheduled snapshots and backups, retention, and recoverability.
- Whether backups are stored in a separate account, region, or isolated system.
- Encryption at rest and in transit, key access permissions, and rotation procedures.
- Application-consistent backups for databases or actively writing systems.
- Workload RPO and RTO.
- Periodic restore testing, timing measurements, and post-recovery data validation.

RAID or multi-volume arrays can improve performance or fault tolerance at one layer, yet they do not replace backups. Snapshots in the same account or region can also share administrative blast radius; design copies around your threat model.

## 12. Process for Choosing Capacity and Disk Type

1. **Classify data:** distinguish root, data, logs, temp, caches, backups, and regenerable data.
2. **Define requirements:** current size, growth, retention, RPO/RTO, durability, and encryption.
3. **Measure the workload:** read/write mix, block size, random/sequential ratio, IOPS, throughput, latency, and queue depth.
4. **Select storage tiers:** general-purpose SSD, provisioned IOPS, HDD, local NVMe, file, or object based on access pattern and data lifecycle.
5. **Check both limit layers:** volume-level IOPS/throughput and aggregate storage limits for the instance family/size.
6. **Calculate headroom:** reserve space for growth, bursts, backup staging, compaction, and maintenance.
7. **Benchmark:** test on target volumes and instances using production-like profiles.
8. **Calculate total cost:** capacity, provisioned performance, snapshots, backups, network, and compute idle time.
9. **Design protection:** encryption, backups, restore tests, monitoring, and capacity/I/O alerts.
10. **Monitor post-deployment:** re-evaluate when data size, traffic, or instance families change.

### Quick Decision Table

| Need | Storage type to evaluate first | What to verify |
|---|---|---|
| Root disk and general apps | General-purpose SSD | Capacity, baseline IOPS, boot latency, and cost |
| OLTP database with many small I/Os | High-performance SSD or provisioned IOPS | p95/p99 latency, write IOPS, fsync, and instance cap |
| Backups or large file scans | Suitable throughput SSD/HDD | Sequential throughput, completion time, and retrieval cost |
| Regenerable cache | Local NVMe or SSD volume | Data loss on host/instance change and cache warming |
| Large cold datasets | Cold HDD or object storage | Access frequency, retrieval time, and retention cost |
| Multiple VMs sharing files | File storage | Concurrent clients, locking, metadata IOPS, and throughput |
| Artifacts, log archives, long-term backups | Object storage | Lifecycle, versioning, retention, and egress |

## 13. Storage Design Example for a Database VM

Suppose a VM runs a transactional database with 500 GiB of data, 100 GiB of indexes, and 50 GiB of logs. The workload generates roughly 9,600 IOPS at peak, primarily random 4–16 KiB I/O; it requires low p95 latency and daily backups.

A candidate design to test:

- A separate general-purpose SSD root volume so the OS and agents do not contend with data.
- An SSD data volume with enough IOPS for the measured read/write load plus headroom.
- A separate log volume if benchmarks prove isolating synchronous writes stabilizes latency.
- Backups offloaded to object storage or a backup service, with retention and restore testing.
- An instance sized with aggregate IOPS and throughput above the combined simultaneous demand of data and logs.

Before going to production, validate post-growth capacity, the volume's ability to sustain IOPS at the real block size, write latency during fsync, total instance-level caps, snapshot behavior, and restore duration. If a separate log volume does not improve benchmark performance, you can simplify and use fewer volumes.

## 14. Common Sizing Mistakes

| Mistake | Consequence | Fix |
|---|---|---|
| Choosing disks by capacity alone | Enough space but insufficient IOPS or throughput | Measure the workload and size for both capacity and performance |
| Confusing IOPS with throughput | Meets operation counts yet transfers data too slowly | Compute IOPS × block size and check both limits |
| Checking only volume limits | VM fails to reach expected aggregate performance | Check instance-level storage caps |
| Sizing to peak burst | Performance drops once credits deplete | Size to baseline or sustained load |
| Using local NVMe as the sole copy | Data loss when host/instance changes | Use for regenerable data or add replication/backups |
| Mixing root and data together | Harder OS replacement, backups, and growth control | Separate volumes by role when benefits are clear |
| Benchmarking on production volumes | Generates load and risks overwriting data | Use dedicated test volumes/files and test windows |
| Expanding volume without extending filesystem | OS still sees old capacity | Inspect block device, partition, and filesystem after resize |
| Skipping restore tests | Backups exist but cannot recover in time | Test restores periodically and measure RTO/RPO |

## 15. Pre-Production Checklist for Volumes

**Capacity and performance:**

- [ ] Accounted for data, indexes, logs, temp, retention, and growth rate.
- [ ] Identified read/write mix, block size, random/sequential pattern, and concurrency.
- [ ] Set targets for IOPS, throughput, and p95/p99 latency.
- [ ] Checked both volume limits and aggregate instance I/O limits.
- [ ] Understood baseline, burst, credits, and throttling conditions.
- [ ] Benchmarked with a representative workload on a test volume.

**Operations and data protection:**

- [ ] Selected persistent or ephemeral appropriately for the data lifecycle.
- [ ] Selected filesystem and configured stable mounting via UUID or equivalent.
- [ ] Enabled encryption and configured proper access controls.
- [ ] Configured snapshots/backups, retention, and tested restores.
- [ ] Set alerts for capacity, IOPS, throughput, latency, and queue depth.
- [ ] Calculated costs for volume, provisioned performance, snapshots, backups, and network.

## Conclusion

Choosing storage for a VM requires balancing capacity, IOPS, throughput, latency, and the instance's aggregate I/O limits. General-purpose SSDs fit most common workloads; provisioned IOPS targets workloads needing consistent performance; HDDs fit large datasets and sequential access; local NVMe fits regenerable caches or scratch space; file and object storage serve shared-file or object-based needs. Measure actual access patterns, plan for growth and headroom, verify both volume and instance limits, benchmark in an isolated environment, and build backup/restore into the design from day one.

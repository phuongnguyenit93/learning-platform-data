# Disk IOPS, Throughput, Latency, and Queue Depth

## 1. Why Understand Storage Performance Metrics?

A server with a powerful CPU and abundant memory can still respond sluggishly if the storage system cannot keep up with read/write requests. A database may have to wait for log writes before committing transactions; an application may stall while reading many small files; an analytics job may take too long because it fails to achieve sufficient sequential read bandwidth. In these cases, adding CPU or memory will not resolve a bottleneck located in the I/O path.

When selecting disks or cloud storage services, four metrics are commonly used to describe performance: **IOPS**, **throughput**, **latency**, and **queue depth**. They are interrelated, yet they measure different aspects:

- IOPS indicates how many read/write operations complete per second.
- Throughput indicates how much data is transferred per second.
- Latency indicates how long a single I/O request takes to complete.
- Queue depth indicates how many I/O requests are queued or executing concurrently.

No single metric is sufficient to declare a disk fast or slow. A volume with high IOPS can still fall short on a workload reading large blocks of data if throughput is capped. A volume with high throughput may be unsuitable for a transactional database that needs to complete many small operations with low latency. A queue depth that is too low may underutilize the device; a queue depth that is too high can increase wait times without increasing useful throughput.

Within the scope of **compute storage**, these metrics must be evaluated alongside CPU, memory, networking, operating system, application type, and storage model. After this lesson, you will be able to:

- Distinguish between IOPS, throughput, latency, and queue depth.
- Calculate the approximate relationship among I/O size, IOPS, throughput, and outstanding requests.
- Identify the I/O characteristics of databases, file applications, and analytics workloads.
- Read volume performance limits alongside VM or instance limits.
- Measure performance using appropriate tools and interpret benchmark results.
- Select, configure, and optimize storage according to workload, data durability, and budget.

## 2. The Path of an I/O Request

### 2.1. From Application to Storage Device

When an application requests to read or write data, the operation typically traverses multiple layers: application library, filesystem or database engine, OS page cache, block layer, driver, interconnect, and storage device. With networked storage, the request also crosses the NIC, internal network, and the provider's storage service.

```text
Application / Database
        |
        v
Filesystem / Page cache
        |
        v
Block layer / I/O scheduler
        |
        v
Driver / Virtual device
        |
        +---- Local NVMe / SSD
        |
        +---- PCIe / NIC / Network fabric
                       |
                       v
                 Cloud block storage
```

The latency observed by the application is the cumulative result of the entire path. A volume with strong specifications can still deliver poor results if the instance runs out of block storage bandwidth, CPU is overloaded, the filesystem suffers lock contention, the network is congested, or the application issues I/O inefficiently.

### 2.2. Common Storage Types

| Storage type | Access method | Performance characteristics | Use cases |
|---|---|---|---|
| Local SSD/NVMe | Device attached directly to the host | Low latency, high throughput/IOPS; tied to physical host and may be ephemeral | Caches, scratch data, intermediate data, regenerable workloads needing fast I/O |
| Network block storage | Block volume attached to a VM/instance over internal network | Configurable capacity and performance; subject to volume, instance, and network limits | Boot disks, databases, server filesystems, data needing lifecycle independent of the VM |
| File storage | Accessed via file protocols like NFS or SMB | Supports sharing across multiple machines; performance depends on metadata, client count, network, and service | Shared home directories, content repositories, shared folders, multi-node apps |
| Object storage | Accessed via API/object key | Optimized for large objects and massive scale; lacks standard block device semantics | Datasets, backups, logs, artifacts, media, and long-term archival data |

Disk IOPS and queue depth are discussed most often for block storage and local devices. File storage may publish IOPS, throughput, or limits per client and metadata operation. Object storage is typically evaluated by request rate, throughput, API latency, and object size rather than block-device queue depth.

### 2.3. Local Storage vs. Network Storage

Local NVMe can offer a short I/O path and low latency because the device connects directly over PCIe. However, data may be lost when the instance is stopped, the host is replaced, or the machine is reallocated, depending on the service type. Therefore, local storage is generally best suited for regenerable data or data replicated in durable storage.

Network block storage decouples volume lifecycle from VM lifecycle, making snapshots, backups, detaching, and reattaching convenient. In return, I/O requests traverse network infrastructure and the storage service layer. Providers may publish maximum performance by volume type, capacity, provisioned tier, or instance type. You must read the exact applicability conditions and check end-to-end limits.

## 3. The Four Core Performance Metrics

### 3.1. IOPS – I/O Operations Per Second

IOPS (Input/Output Operations Per Second) is the number of read or write operations completed in one second. Each operation may read or write a small or large block. Consequently, IOPS alone does not directly indicate how much data was transferred.

Examples:

- 8,000 IOPS with 4 KiB blocks corresponds to roughly 31.25 MiB/s if every operation transfers a full 4 KiB.
- 8,000 IOPS with 64 KiB blocks corresponds to roughly 500 MiB/s if the same operation rate and I/O size are achieved.

Two workloads with identical IOPS can move vastly different amounts of data. IOPS is typically critical for OLTP databases, directory trees with many small files, metadata operations, or applications performing many random operations.

When reading an IOPS specification, check whether it refers to read IOPS, write IOPS, or total IOPS; what read/write ratio the workload uses; the block size used in the published figure; whether the IOPS level is sustained or burstable; and whether any volume size conditions apply.

### 3.2. Throughput – Data Volume Per Second

Throughput is the amount of data read or written per second, commonly expressed in MB/s, MiB/s, GB/s, or GiB/s. Throughput matters for large data transfers, sequential reads, backups, restores, log processing, and data analytics.

Throughput depends on IOPS and the average size of each I/O operation. If a device achieves 20,000 IOPS with an average 16 KiB block, the theoretical throughput is approximately:

\[
20{,}000 \times 16\text{ KiB} = 312.5\text{ MiB/s}
\]

Actual values may be lower due to overhead, volume/instance caps, filesystem behavior, read/write mix, queuing, and how the workload issues requests.

Do not confuse volume throughput with the instance's general network speed. If a volume is capable of 1,000 MB/s but the instance is allocated lower aggregate block storage bandwidth, the workload will be capped at the lower limit. Similarly, multiple volumes attached to one instance may share a single machine-level cap.

### 3.3. Latency – I/O Completion Delay

Latency is the time from when an I/O request is issued until the application or calling layer receives completion notification. It is typically measured in microseconds (µs) or milliseconds (ms). For an interactive application, high latency can degrade response times even when aggregate throughput remains low.

Latency can include:

- Time spent by the application and OS scheduling the request.
- Time waiting in queues.
- Processing time at the storage device or service.
- Transmission time across buses or networks.
- Flush, synchronization, or durable write acknowledgment time.
- Filesystem/database metadata and locking overhead.

Do not monitor average latency alone. Look at percentiles such as p50, p95, p99, and p99.9. p50 represents the median experience; p99 shows how long the slowest 1% of operations can take. A system with low average latency but spiking p99 can suffer timeouts or sudden application queue buildup.

Distinguish read latency from write latency, random from sequential latency, cache hit from cache miss latency, and flush/fsync latency. For a database, a write acknowledged only after durable log persistence can have very different latency than a write that lands in the page cache.

### 3.4. Queue Depth – Outstanding I/O Requests

Queue depth describes the number of I/O requests that have been submitted but not yet completed, or the number of requests waiting/being processed at a given layer in the I/O path. Depending on the tool and platform, the metric may reflect the queue at the block device, driver, storage service, or a benchmark configuration parameter.

A higher queue depth gives the device more requests to process in parallel. This can raise throughput when the storage device or service requires concurrent I/Os to reach peak performance. However, high queue depth can also force requests to wait longer, especially once the device is saturated.

Distinguish between:

- **Configured queue depth:** the maximum number of outstanding requests permitted by the application or benchmark.
- **Observed queue depth:** the actual number of requests outstanding at a point in time.
- **Queue wait:** the time a request spends waiting before being serviced.

Setting queue depth to 64 does not guarantee the device always has 64 requests in flight. The application may not issue enough concurrent I/O, or another layer may bottleneck it. Conversely, steadily rising queue depth alongside rising latency and flat throughput indicates likely saturation.

## 4. Relationship Between IOPS, Throughput, Latency, and Queue Depth

### 4.1. Deriving Throughput from IOPS and I/O Size

When average I/O size is relatively stable, you can estimate:

\[
Throughput \approx IOPS \times Average\ I/O\ Size
\]

For example, a workload achieving 12,000 IOPS with 8 KiB blocks:

\[
12{,}000 \times 8\text{ KiB} = 93.75\text{ MiB/s}
\]

If the workload uses 128 KiB blocks at the same 12,000 IOPS, theoretical throughput climbs to about 1,500 MiB/s. However, hardware or the service may hit a throughput ceiling before reaching that level. This is why both IOPS and throughput limits must be evaluated.

When calculating, keep units consistent. 1 KiB equals 1,024 bytes; 1 MiB equals 1,024 KiB. Some pricing sheets or dashboards use decimal MB/GB, so never compare MB/s directly against MiB/s without conversion.

### 4.2. Queue Depth, IOPS, and Latency – Little's Law

In a steady-state system, Little's Law gives an approximate relationship among the average number of requests present in the system, completion rate, and average residence time:

\[
Average\ Queue\ Depth \approx IOPS \times Average\ Latency
\]

Latency must be converted to seconds when IOPS is measured per second. For instance, if a workload completes 10,000 IOPS with an average latency of 2 ms:

\[
Q \approx 10{,}000 \times 0.002 = 20
\]

On average, roughly 20 I/O requests are outstanding across that measurement boundary. This is a steady-state observational relationship, not a formula to blindly set maximum queue depth for every device. Ensure IOPS and latency are measured at the same layer, for the same operation type, and over the same interval.

If queue depth is capped too low, the workload may not issue enough concurrent requests to reach maximum throughput. If queue depth is increased after the device is already saturated, IOPS may barely rise while latency climbs sharply. At that point, increasing queue depth only makes more requests wait longer.

### 4.3. Comparison Example of Two Workloads

| Characteristic | Workload A | Workload B |
|---|---:|---:|
| IOPS | 15,000 | 3,000 |
| Average I/O size | 4 KiB | 128 KiB |
| Estimated throughput | 58.6 MiB/s | 375 MiB/s |
| Access pattern | Random, many small operations | Sequential, large blocks |
| Metrics to watch | p95/p99 latency and sustained IOPS | Sustained throughput and completion time |

Workload A has higher IOPS yet transfers less data. Workload B has lower IOPS yet delivers higher throughput. Choosing a volume solely by IOPS can pick the wrong fit for Workload B; looking solely at throughput can overlook latency critical to Workload A.

### 4.4. Saturation Curve

As concurrent requests increase, IOPS and throughput typically rise until a limit is reached. Beyond the saturation point, throughput tends to flatten while queue depth and latency continue to climb.

```text
Throughput / IOPS
      ^
      |                  ____________
      |              ___/
      |           __/
      |        __/
      |     __/
      |____/____________________________> Queue depth
                    saturation point

Latency
      ^
      |                         /
      |                       _/
      |                    __/
      |                ___/
      |______________/
      +---------------------------------> Queue depth
```

This is a conceptual illustration. The exact curve depends on the device, cloud service, I/O size, read/write mix, and contention levels. The goal is to find the queue depth operating zone that delivers strong throughput while keeping latency within SLO.

## 5. Workload I/O Patterns

### 5.1. Random I/O vs. Sequential I/O

**Random I/O** accesses non-contiguous data locations. OLTP databases, indexes, metadata, and many transactional workloads typically generate small, random operations. IOPS and latency are usually critical.

**Sequential I/O** reads or writes contiguous regions of data. Backups, restores, streaming, log processing, and large file analytics can often generate large block I/Os. Throughput typically matters more than peak IOPS.

An application can combine both. For example, a database may read data pages randomly while writing transaction logs sequentially. Measure each I/O stream or device separately when possible to identify which component generates the load.

### 5.2. Read-Heavy, Write-Heavy, and Read/Write Mix

The read/write ratio affects performance. Some volume types publish symmetric read and write specs; others have different limits or costs. Synchronous writes can be impacted by flushes and durability requirements. Asynchronous writes may be acknowledged sooner, but you must clearly understand when data actually becomes durable.

Measure the actual read/write ratio rather than assuming an application is read-heavy or write-heavy from its name. The same database can exhibit very different ratios during peak traffic, batch windows, and backup windows.

### 5.3. Block Size

Block size directly impacts the data transferred per I/O. Small blocks generate more operations for the same amount of data; large blocks reduce operation counts but may read/write more unnecessary data.

For example, a query performing random 4 KiB reads will not necessarily benefit from configuring 1 MiB blocks. Conversely, sequentially reading a 1 GiB file can usually take better advantage of large blocks and batching. Measure using sizes close to the real application.

### 5.4. Synchronous vs. Asynchronous I/O

Synchronous I/O causes the calling thread to wait for the operation to complete before continuing. If the application has only a few threads, outstanding I/Os may stay low, leaving the device underutilized. Asynchronous I/O allows the application to submit multiple requests and continue processing while I/O executes.

Increasing concurrency can improve throughput, but it also increases memory buffering, queued requests, and latency. For databases, never disable synchronous modes just to boost benchmark scores if doing so alters durability guarantees or transaction semantics.

### 5.5. Caches and Page Cache

Measurements can be skewed by caching in the application, operating system, hypervisor, or storage service. Repeatedly reading the same data may be served from RAM instead of the storage device. In that case, the benchmark reflects cache performance rather than storage performance.

To measure the underlying device, understand how benchmarking tools bypass or control caching. However, do not exclude caching if the real production workload relies on it; measure both cold-cache and warm-cache scenarios where appropriate.

## 6. Understanding Cloud Storage Performance Limits

### 6.1. Volume-Level Limits

Providers may publish maximum IOPS and throughput based on volume type, capacity, provisioned performance tier, or specific configurations. Some volumes scale baseline performance with capacity; others allow provisioning IOPS or throughput independently within defined bounds.

Review the following attributes in service documentation:

- Maximum IOPS and baseline IOPS.
- Maximum throughput and baseline throughput.
- Relationship between volume capacity and performance.
- Whether performance is sustained continuously or only during burst windows.
- I/O size limits and read/write mix constraints if applicable.
- Maximum number of volumes attachable to an instance.
- Propagation time for configuration changes and billing rules.

Never treat marketing maximums as guaranteed for every volume size. A published IOPS figure may only be achievable when the volume is large enough, the instance type is compatible, and queue depth is sufficiently high.

### 6.2. Burst and Credits

Some storage tiers have a baseline lower than their burst performance limit. A volume can accumulate credits while operating below baseline and spend credits to burst above baseline for a limited duration. Once credits are depleted, performance drops back to baseline.

This can cause short benchmarks to look impressive while long-running workloads slow down. For long batch jobs, databases, or steady-load systems, measure performance after burst credits deplete or verify the service's sustained performance model.

Not every service uses a credit model. Identify the exact volume type and check whether monitoring dashboards expose a burst balance metric or equivalent.

### 6.3. Instance-Level and Interconnect Limits

The volume is not the only limit. An instance/VM may enforce an aggregate IOPS or throughput ceiling across all attached storage. Multiple volumes attached to one instance share that ceiling. CPU, PCIe, NIC, network fabric, and drivers can also become bottlenecks.

For example, if three volumes can each reach 500 MB/s but the instance supports only 800 MB/s aggregate for block storage, the combined throughput of those three volumes cannot reach 1,500 MB/s on that instance. Upgrading individual volume performance will not break through the instance cap.

Also check instance burst limits, machine family, vCPU count, network bandwidth, and multi-queue support. If the CPU is saturated, interrupt handling or checksum computation can throttle I/O speeds even when the storage service still has headroom.

### 6.4. Striping Multiple Volumes

Multiple volumes can be combined using RAID or a logical volume manager to increase aggregate IOPS/throughput or capacity. If the workload and platform support it, striping can spread I/O across multiple volumes.

However, aggregate performance does not always scale linearly. Volumes may still share an instance or network ceiling. Striping also increases operational complexity and blast radius if a single volume fails. With RAID 0, a single component failure can wipe out the entire striped dataset. Clear backups and recovery procedures are required; per-volume snapshots must preserve consistency across the entire group.

Only stripe when volume limits have been confirmed as the bottleneck, the instance still has bandwidth headroom, and there is a clear performance or capacity justification. Do not use striping to mask choosing the wrong instance type or storage tier.

### 6.5. Snapshots, Backups, and Background Activity

Snapshots, backups, replication, encryption, and migrations can generate extra I/O or impact performance depending on the service. Some platforms offload snapshot processing to the backend; certain operations can still trigger bursts or contention along the storage path. Observe metrics during backup windows and inspect impacts on p95/p99 latency.

Never skip backups just to keep benchmark numbers high. Schedule backups appropriately, use application-consistent snapshots, and test restores. The goal is sustainable production performance alongside required data protection.

## 7. Choosing Storage by Workload

### 7.1. OLTP Databases

OLTP databases typically generate many small, random I/Os while requiring consistent latency for transaction logs and synchronous operations. Key selection criteria usually include sustained IOPS, p95/p99 read/write latency, peak-hour queue depth, and burst handling.

Measure data files, indexes, transaction logs, and temporary files separately if the architecture permits. Transaction logs may require low write latency; data files may require high read IOPS. Placing them on separate volumes only helps when performance limits can genuinely be isolated and observed independently.

### 7.2. Data Warehouses and Analytics

Analytics workloads typically read large data regions, perform sequential scans, and run batch processing. Throughput, parallel read capability, worker count, and bandwidth between storage and compute are usually critical. Object storage can be well suited for large datasets, while block or file storage may fit scratch space and temporary data.

Measure throughput when multiple workers read concurrently. A single job may achieve high speed, yet cluster-wide throughput may hit network, storage service, or quota limits.

### 7.3. File Servers and Shared Content

File servers handle varied operations: reading/writing file contents, creating/deleting/renaming files, directory lookups, and permission checks. Metadata operations can become the bottleneck even when bulk data throughput remains low. Measuring MB/s alone does not capture full performance.

Measure metadata operations, concurrent client counts, file open latency, and read/write throughput. Select a file service based on protocol, sharing model, access permissions, and concurrency level.

### 7.4. Caches and Temporary Data

Caches, build artifacts, intermediate data, and scratch data typically prioritize low latency and high IOPS/throughput. Local NVMe can be a great fit if the data is regenerable or backed up elsewhere. If data must survive VM replacement, use durable storage or sync data out to another service.

### 7.5. Backups and Long-Term Archival

Backups typically optimize for cost, durability, and restore time. Throughput governs backup creation and restore duration; random latency matters less than for OLTP databases. Object storage or cold storage tiers can cut costs, but you must understand retrieval times, retrieval fees, and request limits.

## 8. Measuring Performance and Benchmarking

### 8.1. Measure Real Workloads Before Synthetic Benchmarks

Start with metrics from the application, database, and operating system. Record read/write IOPS, throughput, latency percentiles, queue depth, I/O sizes, random/sequential ratio, and read/write mix. Measure during normal hours, peak hours, and backup or batch runs.

Synthetic benchmarks help isolate specific storage attributes, but they do not replace real workloads. If a database uses 8 KiB blocks and frequent fsyncs, a 1 MiB sequential benchmark proves nothing about storage suitability for that database.

### 8.2. Using fio to Measure I/O

`fio` is an I/O workload generator that lets you configure block size, access pattern, read/write mix, job count, and queue depth. The following example creates a 4 KiB random read test with queue depth 32 on a test file:

First, create the test file on a scratch volume. This command writes data and should only be run on a designated writable test area:

```bash
fio --name=prepare \
    --filename=/mnt/test-volume/fio-test.bin \
    --size=10G \
    --rw=write \
    --bs=1m \
    --ioengine=libaio \
    --direct=1 \
    --iodepth=16 \
    --end_fsync=1 \
    --group_reporting
```

Once the file is created, you can run the random read and sequential read tests below.

```bash
fio --name=randread-4k \
    --filename=/mnt/test-volume/fio-test.bin \
    --size=10G \
    --rw=randread \
    --bs=4k \
    --ioengine=libaio \
    --direct=1 \
    --iodepth=32 \
    --numjobs=1 \
    --runtime=60 \
    --time_based \
    --group_reporting
```

Sequential read example with large blocks to observe throughput:

```bash
fio --name=seqread-1m \
    --filename=/mnt/test-volume/fio-test.bin \
    --size=10G \
    --rw=read \
    --bs=1m \
    --ioengine=libaio \
    --direct=1 \
    --iodepth=16 \
    --numjobs=1 \
    --runtime=60 \
    --time_based \
    --group_reporting
```

These examples target Linux environments supporting `libaio`; verify the appropriate I/O engine for your kernel and device. The test file must reside on a scratch volume cleared for writes. Preparing the file writes data to the volume; never run write tests or create test files on production volumes holding critical data. Benchmarks generate heavy I/O load and can degrade co-located workloads.

`--iodepth` specifies the requested queue depth per job; `--numjobs` spawns multiple jobs. Total potential outstanding requests can scale with job count, though actual concurrency depends on the engine, application, and device. Avoid raising both parameters simultaneously without watching latency and saturation.

### 8.3. Testing Across Multiple Load Points

A sound benchmark procedure varies one factor at a time:

1. Measure a low-load baseline using a block size close to the real workload.
2. Step up queue depth incrementally, such as 1, 4, 8, 16, 32, and 64.
3. Record IOPS, throughput, p50/p95/p99 latency, and observed queue depth.
4. Repeat for reads, writes, and realistic read/write mixes.
5. Test random and sequential patterns across different block sizes.
6. Run long enough to uncover burst limits or performance degradation over time.
7. Measure while backups, snapshots, or co-located workloads run if that matches production.

Do not record only the highest number. Look for the inflection point where throughput gains flatten while latency spikes; that usually signals passing the effective queue depth sweet spot.

### 8.4. OS Observation Tools

On Linux, you can use:

```bash
iostat -xz 1
```

This command displays per-device I/O statistics at regular intervals. Depending on the sysstat and kernel version, fields may include read/write IOPS, throughput, wait times, queue size, and device utilization. Understand the exact field definitions for your installed version; never rely on `%util` alone to conclude a modern device has reached 100% capacity.

Other useful tools:

- `pidstat -d`: observe I/O per process.
- `vmstat`: inspect system state, including high-level I/O wait.
- `lsblk` and `findmnt`: inspect block devices and mount points.
- Database tools: monitor file latency, fsyncs, checkpoints, and buffer/cache hit rates.
- Cloud monitoring: track volume, instance, burst balance, queue, and network metrics provided by the service.

### 8.5. Reading fio Output

`fio` output typically includes:

- `IOPS`: operations completed per second.
- `BW`: measured bandwidth/throughput.
- `clat`: completion latency at the I/O engine level.
- `lat`: total latency as reported by fio, which can include submission and completion time.
- Percentile latency: completion time distribution, such as p95 and p99.
- `IO depths`: distribution of observed outstanding requests.
- `util`: device utilization reported according to the tool's accounting mechanism.

Read the units and statistical sections carefully. Comparing `clat` with application-level latency must account for layers outside `fio`. When benchmarking cloud block storage, cross-reference volume and instance metrics to separate storage caps from host/network limits.

## 9. Interpreting Scenarios and Finding Bottlenecks

| Observation | Possible cause | What to check |
|---|---|---|
| Low IOPS, low throughput, low queue depth | Application issues little I/O; cache hits; low concurrency | Check worker count, async I/O, cache behavior, and benchmark config |
| High IOPS but low throughput | Small block size | Check I/O size and whether the real workload needs larger blocks |
| Low throughput even though IOPS is not maxed out | Volume/instance throughput cap, network, or CPU | Inspect caps at volume, instance, NIC, and CPU levels |
| Queue depth and latency rise together while throughput flattens | Device or a layer in the I/O path is saturated | Lower test concurrency, locate the bottleneck, and scale the right layer |
| p99 latency spikes while average stays stable | Certain requests sit in long queues, contention, flushes, or background tasks | Analyze percentiles, read/write mix, snapshots, backups, and noisy neighbors |
| IOPS starts strong then drops | Burst credits depleted or sustained load hit baseline | Watch burst balance and run longer tests |
| Multiple volumes added yet total throughput does not rise | Instance or network cap is throttling | Compare per-volume metrics against aggregate instance metrics |
| fio looks good but the application is slow | Benchmark pattern differs from workload; caching, filesystem, locks, or CPU | Measure at the application layer and match real block size and concurrency |

Do not conclude storage is the bottleneck solely from low CPU utilization or high queue depth. Correlate multiple metrics over the same time window and pinpoint the first layer hitting a limit.

## 10. Optimizing Storage Performance

### 10.1. Choosing the Right Volume Type and Performance Tier

Select volumes based on IOPS, throughput, latency, capacity, durability, and cost combined. For transactional databases, prioritize consistent IOPS and low latency. For sequential processing, prioritize throughput. For regenerable caches, local NVMe can be ideal. For data that must outlive the VM, choose durable storage with appropriate snapshots/backups.

### 10.2. Optimizing I/O Size and Batching

Coalescing small operations when the application allows reduces overhead and raises throughput. However, larger blocks can increase unnecessary read/write amplification and single-operation latency. Tune to the real pattern rather than applying a universal preset.

### 10.3. Tuning Concurrency and Queue Depth

Increasing I/O threads or queue depth helps devices exploit parallelism. Scale up gradually while monitoring IOPS, throughput, and percentile latency. Stop increasing once throughput barely improves while latency continues climbing.

### 10.4. Reducing Unnecessary I/O

- Use appropriate caching to cut redundant reads.
- Avoid overly verbose logging or flushing more frequently than required.
- Batch metadata operations and reduce tiny-file proliferation where the app allows.
- Use compression or columnar formats for analytics datasets when beneficial.
- Separate batch workloads from latency-sensitive databases if they contend on the same volume.
- Place temporary data on suitable regenerable storage.

Never disable durability, fsync, or synchronization mechanisms solely to inflate benchmark scores if doing so weakens the application's data guarantees.

### 10.5. Scaling the Right Layer

If a volume hits its IOPS ceiling while the instance has spare headroom, upgrading or provisioning more IOPS on the volume helps. If aggregate throughput is capped at the instance, move to an instance type with higher storage bandwidth. If multiple workloads contend, split volumes or separate instances to reduce contention. If the bottleneck is network or CPU, raising volume IOPS will not fix the problem.

### 10.6. Continuous Monitoring

Set up dashboards and alerts for IOPS, throughput, p95/p99 latency, queue depth, burst balance, free capacity, and I/O errors. Alerts should be grounded in SLOs and sustained durations rather than firing on brief single-point spikes.

Monitoring capacity is equally critical: a nearly full filesystem can trigger write failures or degrade performance; a full volume can halt the application even with plenty of IOPS headroom. Forecast growth to expand capacity before hitting thresholds.

## 11. Data Durability, Security, and Cost

### 11.1. Performance Does Not Replace Durability

Local NVMe may be fast, yet it should generally not hold the sole copy of critical data. Network block volumes can survive independently of the VM, yet they still require snapshots, backups, and recovery plans. RAID boosts performance or fault tolerance in certain configurations, yet it does not replace backups against accidental deletion, logical corruption, or ransomware.

Verify durability policies, replication, snapshot consistency, backup retention, and restore times. For databases, use backup or snapshot mechanisms consistent with transaction state.

### 11.2. Securing the I/O Path

Encrypt data at rest and in transit as required. Manage keys via KMS or equivalent services, restricting volume attach/detach and snapshot permissions. Separate storage administration privileges from application data access. Log audit trails for volume creation, modification, snapshotting, sharing, and deletion.

For file storage, enforce identity and permissions at both the network and filesystem layers. For object storage, use bucket/object policies, restrict public access, and enable appropriate logging/auditing. Never put sensitive data onto benchmark volumes or test files.

### 11.3. Performance Cost

Costs can include volume capacity, provisioned IOPS/throughput, snapshots, backups, requests, network transfers, and instance runtime. Over-provisioning a volume wastes budget; under-provisioning can prolong processing jobs and inflate compute costs as instances sit idle waiting on I/O.

Evaluate cost per unit of work—for example, cost per thousand transactions, per TB processed, or per hour to complete backups. Factor in compute time wasted waiting on storage. For variable workloads, compare baseline/burst pricing against steady provisioned tiers.

## 12. Practical Examples

### Example 1: Transactional Database

A database handles many random queries, small I/O sizes, and synchronous transaction log writes. Users report rising response times during peak hours.

**Analysis approach:** measure read/write IOPS, block size, p95/p99 latency, queue depth, and fsync latency. Compare against the volume's baseline and provisioned limits. Check CPU, cache hit rates, backups, and co-located workloads sharing the instance. If queue depth and latency climb while IOPS flattens, the storage path may be saturated. If queue depth is low, the application may not be issuing enough concurrent I/O or may be bottlenecked on CPU or database locks.

**Remediation:** select a volume with appropriate sustained IOPS and latency; separate logs/data if beneficial; cut redundant I/O; check instance-level storage limits; benchmark using a production-like read/write mix.

### Example 2: Sequential Data Analytics

A job reads large files from storage for batch processing. IOPS is modest, yet the job finishes slowly.

**Analysis approach:** measure per-worker throughput, block size, reader thread count, network throughput, and storage limits. Check whether the volume or file service has hit a throughput ceiling. If each worker reads sequentially yet aggregate bandwidth stays low, check concurrency, NICs, and the path to storage.

**Remediation:** use throughput-optimized storage, increase reader threads in a controlled way, select appropriate block sizes, and partition data to reduce contention. If the data consists of large objects, consider object storage with parallel range or partition reads.

### Example 3: Volume with Burst Performance

An application gets strong results in a short benchmark, but after 30 minutes of heavy load, throughput drops and latency rises.

**Analysis approach:** check whether the volume type uses burst credits; track burst balance over time; compare performance when credits are full versus after credits deplete. Check whether the workload exceeds baseline over extended periods.

**Remediation:** choose a volume tier whose baseline meets sustained demand, provision appropriate IOPS/throughput, or smooth load via caching/batching. Design benchmarks long enough to reflect real runtime durations.

## 13. Common Mistakes

- **Looking only at IOPS:** ignoring block size and actual throughput.
- **Looking only at throughput:** missing high p99 latency on small operations.
- **Assuming higher queue depth is always better:** overly deep queues may simply increase wait time.
- **Using sequential benchmarks to evaluate a database:** the I/O pattern does not match the real workload.
- **Running benchmarks that are too short:** you may only be measuring burst credits or caches.
- **Ignoring instance limits:** aggregate throughput across multiple volumes can be capped at the VM/host.
- **Equating MB/s with MiB/s:** unit mismatches distort comparisons.
- **Ignoring read/write mix:** read and write performance can differ significantly.
- **Measuring with a hot cache without noting it:** results may fail to reflect cold reads.
- **Using local SSD as the sole store for critical data:** high speed does not equal high durability.
- **Increasing queue depth or worker counts without monitoring latency:** can overload the system.
- **Disabling fsync or durability to score higher in benchmarks:** alters the application's data protection guarantees.

## 14. Storage Selection and Validation Checklist

- [ ] Identified workload random/sequential pattern, read/write mix, and I/O sizes.
- [ ] Measured IOPS, throughput, p50/p95/p99 latency, and queue depth.
- [ ] Distinguished application-level latency from device or cloud service latency.
- [ ] Calculated approximate throughput from IOPS and average I/O size.
- [ ] Checked baseline, burst, provisioned performance, and volume limits.
- [ ] Checked aggregate IOPS/throughput limits at the instance and network levels.
- [ ] Selected the right storage type: local, block, file, or object.
- [ ] Benchmarked using production-like patterns and ran long enough.
- [ ] Observed queue depth and latency while scaling concurrency.
- [ ] Checked the impact of backups, snapshots, caches, and shared workloads.
- [ ] Defined durability, backups, restores, encryption, and access controls.
- [ ] Calculated costs for capacity, provisioned performance, snapshots, network, and compute wait time.
- [ ] Configured dashboards, alerts, and scaling thresholds aligned with SLOs.

## 15. Conclusion

IOPS, throughput, latency, and queue depth describe four complementary dimensions of storage performance. IOPS measures completed operations; throughput measures data volume; latency measures completion time; queue depth reflects outstanding request concurrency. I/O size and concurrency determine how these metrics interact.

Choose storage based on real I/O patterns, verify limits at both the volume and instance levels, measure latency percentiles, and benchmark long enough to surface burst limits or saturation. Tuning queue depth, batching, and concurrency only helps when it improves throughput while keeping latency within SLO. Ultimately, balance performance against durability, security, recoverability, and total operational cost.

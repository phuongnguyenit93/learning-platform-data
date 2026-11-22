# Impact of OS Cache, Page Faults, and Disk Speed

The performance of a Java application does not depend solely on CPU, JIT, or algorithms. Reading and writing data are also affected by the operating system page cache, page faults, physical memory, swap, filesystem, and storage device speed. With CRaC, these factors appear during checkpoint creation, storing checkpoint artifacts, restoring the process, and when the application begins accessing data again.

A checkpoint may be created very quickly on a machine with a warm cache yet restore slowly on another host with a cold cache. Conversely, a fast restore measurement may only reflect that the checkpoint file is already in the page cache, not the actual disk speed. For an accurate evaluation, separate checkpoint read time, JVM state restore time, page faults during the workload, and business I/O after restore.

## 1. What Is the Operating System Page Cache?

The page cache is a memory region used by the kernel to store pages of file data that have been read or written. When an application reads a file, the kernel can retrieve the data from RAM if the corresponding page is already in the cache; if not, the kernel must fetch the page from the filesystem or storage device before providing it to the application.

On Linux, the page cache is typically managed system-wide. Multiple processes reading the same file can share that file's cached pages. The page cache is not the Java heap and does not belong exclusively to a single object or JVM.

Example:

~~~text
Java application reads file
       |
       v
read() / FileChannel / memory mapping
       |
       v
Kernel checks page cache
       |
       +---- Page already in RAM
       |          |
       |          v
       |      Return data to application
       |
       +---- Page not yet in cache
                  |
                  v
             Filesystem / block layer
                  |
                  v
             SSD / HDD / network storage
                  |
                  v
             Load page into RAM
                  |
                  v
             Return data to application
~~~

If a file is read multiple times and its pages remain in RAM, subsequent reads can be significantly faster. If the system runs low on RAM, the kernel can reclaim page cache to allocate memory for other workloads. The next read must then fetch the data from storage again.

### Page Cache Is Not the Same as Application Cache

An application may have multiple cache layers:

- Object caches in the heap, such as Caffeine or a Map.
- Data caches in libraries, HTTP clients, or ORMs.
- Buffers of Java streams or NIO.
- The kernel page cache.
- Caches on the controller, SSD, or storage service.

A read operation can be served from one of these layers. If the application cache returns the result, no file read syscall may occur. If the application invokes a read while the page cache is warm, the kernel may not need to read the device. If the page cache is cold, data may have to be read from storage.

When measuring performance, identify which cache layer is being tested. Merely observing that the second read is faster is not enough to conclude that the page cache is the cause; application caches, JIT, DNS, connection pools, and other states may also have warmed up.

## 2. What Is a Page Fault?

A page fault occurs when the CPU or process accesses a virtual memory page whose current mapping is not ready as required. The kernel handles the fault and decides how to provide the page or report an error.

A page fault is not inherently an application error. It is a normal part of the virtual memory mechanism.

Situations that can cause a page fault:

- A memory-mapped file page has not yet been brought into RAM.
- An anonymous memory page has not yet been assigned a physical backing page.
- A page has been swapped out and needs to be read back in.
- A copy-on-write page needs to be separated when the process writes to it.
- An invalid mapping or disallowed access permission, resulting in errors such as SIGSEGV.

### Minor Page Fault

A minor page fault is handled without reading a data page from a storage device. Examples may include:

- The page is already in the page cache or RAM and only needs a mapping set up for the process.
- The kernel allocates a zero-filled page for anonymous memory.
- Copy-on-write creates a copy of a page in RAM.
- A mapping can be completed from existing memory state.

Minor faults still consume CPU and kernel time. If the count is very high, they can affect latency, though they generally do not incur storage I/O latency like major faults.

### Major Page Fault

A major page fault requires an I/O operation to resolve the fault. For example, a file-backed page not yet in RAM must be read from backing storage, or an anonymous page that was swapped out must be read back in.

Major faults are usually more expensive than minor faults because they may have to wait on storage. However, a major fault should not be equated with a direct read from a local SSD: backing storage could be a network filesystem, virtual volume, encrypted device, or another storage layer.

Some tools report the number of minor and major faults of a process. This is a diagnostic signal, not a direct measurement of bytes read from disk or total I/O latency.

### Distinguishing Page Faults from Java Exceptions

A page fault at the memory management layer is not the same as a Java exception such as IOException, OutOfMemoryError, or NullPointerException.

- Minor/major page faults are kernel events handling virtual memory.
- IOException is typically an error returned by Java I/O APIs.
- OutOfMemoryError reflects that the JVM cannot satisfy an allocation request under runtime conditions.
- SIGSEGV can occur if a process accesses an invalid mapping or violates memory permissions.

An application can generate many page faults without throwing any exception. Conversely, an IOException is not necessarily related to page faults.

## 3. Why Do Warm Cache and Cold Cache Produce Different Results?

Suppose an application reads a checkpoint file several GB in size.

**Warm cache:** the file's pages are already in the page cache. The kernel can serve most reads from RAM. Measured duration is lower, and physical device reads can be minimal.

**Cold cache:** the pages are not yet in the page cache. The kernel must fetch data from storage. Duration depends on device latency, throughput, queue depth, filesystem, file placement, and read pattern.

**Cache under pressure:** part of the file remains in cache while other parts have been reclaimed. The result is a mix of cache hits and I/O. Performance can fluctuate across runs.

| State | Primary Data Source | Common Symptoms |
|---|---|---|
| Warm cache | RAM/page cache | Few block reads, low read duration |
| Cold cache | Storage or backing filesystem | Many major faults or block reads, increased latency |
| Partial cache | Mix of RAM and storage | Performance depends on which data regions are accessed |
| Memory pressure | Cache continuously reclaimed | Repeated I/O, fluctuating faults and latency |

Sequential reads of a large file often leverage kernel readahead and can achieve high throughput. Random reads of scattered pages can be impacted more strongly by storage latency and IOPS. Two workloads that both read 1 GB but with different patterns can have very different durations.

## 4. How Does Disk Speed Affect Checkpoints?

Creating and using a checkpoint can generate several types of I/O:

1. Writing checkpoint data to the filesystem or volume.
2. Flushing or syncing data as required by the tool.
3. Packaging, compressing, encrypting, or transferring artifacts to a repository.
4. Reading the checkpoint artifact during restore.
5. Reloading configuration files, libraries, or data accessed by the application after restore.

Storage speed directly affects steps involving synchronous I/O or reading large volumes of data. However, total checkpoint/restore time also depends on CPU, memory bandwidth, compression, the engine, filesystem, network, and the number of resources to handle.

### Creating a Checkpoint

The checkpoint engine may need to write a large amount of memory state to storage. Write duration depends on:

- Size of the state to be saved.
- Sequential write speed and I/O handling capability of the device.
- Number of files and how the engine organizes data.
- Whether compression or encryption is enabled.
- Filesystem, mount options, and container storage driver.
- Whether flush/fsync must wait to guarantee data durability.
- Whether storage is shared with other workloads.

A drive with high sequential throughput can still be slow when a checkpoint creates many small files or requires continuous synchronous flushes. IOPS and latency also matter.

### Restoring a Checkpoint

Restore may need to read the checkpoint artifact from a filesystem or volume. Whether the artifact resides on local NVMe, a network block volume, NFS, or mounted object storage, latency and throughput can vary.

In particular, do not assume every CRaC runtime restores using the same read strategy. Some implementations load data eagerly; some engines or configurations support demand paging/lazy restore, where part of the memory pages are fetched only when the process accesses them. Check the documentation and behavior of the exact JDK distribution, checkpoint engine, and version in use.

If restore uses demand paging, the process can begin executing before all checkpoint pages have been loaded. In that case, the first access to an unloaded memory region can trigger a page fault and require fetching data from the checkpoint backing storage or page server. As a result, time until the process is running can be low, while latency of the first request remains high if that request touches many unloaded pages.

If restore loads most of memory before signaling completion, startup duration can reflect this I/O directly. Do not infer the restore strategy merely from the fact that the application has a CRaC Resource.

## 5. Impact of HDD, SSD, NVMe, and Network Storage

Different storage types have different characteristics:

| Storage Type | General Characteristics | Observable Impact |
|---|---|---|
| HDD | Higher random-access latency; sequential throughput depends on mechanics and disk zone | Random page-ins and many small files can be slow |
| SATA SSD | Lower latency than HDD; throughput and queue depth limited by device/controller | Sequential checkpoint reads/writes are usually better than HDD but have IOPS limits |
| NVMe SSD | Low latency, high queue handling capability and IOPS | Beneficial for large checkpoints or workloads with heavy random I/O |
| Network block volume | Performance depends on network, deployment zone, QoS, and volume load | Latency can vary over time and by host placement |
| NFS/network filesystem | Adds network round trips, metadata server, and cache coherence | Small files, metadata, and random access can suffer significant latency |
| Object storage via gateway/mount | Typically has different semantics and latency from a local filesystem | Not suitable by default as a backing path for a checkpoint engine |

This is a qualitative comparison. There is no single universal throughput figure for all SSDs or cloud volumes. Measure the actual device, filesystem, mount options, workload, and deployment configuration.

### Throughput and Latency Are Two Different Metrics

- **Throughput** indicates how much data is transferred per unit of time, for example MB/s.
- **IOPS** indicates the number of I/O operations per second.
- **Latency** indicates how long a single operation takes.
- **Queue depth** indicates how many I/O operations are queued or currently being processed.

Sequential reading of a large file typically focuses on throughput. Reading many small scattered pages can be bottlenecked by latency and IOPS. Storage with high throughput but high random-read latency can still make the first request after restore slow.

## 6. Page Cache and Memory Pressure in Containers

The page cache uses host RAM and may be charged to cgroup memory accounting depending on the data type and kernel. Inside a container, memory limits do not relate only to the Java heap. File cache, anonymous memory, page tables, native allocations, and various kernel memory types can all contribute to memory pressure.

When a cgroup approaches its memory limit:

- The kernel may reclaim file cache.
- The process may have to re-read files from storage.
- Reclaim and compaction can increase latency.
- If configuration allows, memory may be swapped; otherwise, the container may be OOM killed.
- Another workload on the same node can put pressure on shared cache.

Therefore, increasing -Xmx does not always improve performance. If the heap occupies nearly the entire cgroup limit, the kernel has little RAM left to hold page cache and native allocations. Conversely, reducing the heap too much can increase GC activity. Measure both total container memory and JVM memory.

### Observing Memory cgroup on Linux

With cgroup v2, you can read:

~~~shell
cat /sys/fs/cgroup/memory.current
cat /sys/fs/cgroup/memory.max
cat /sys/fs/cgroup/memory.stat
cat /sys/fs/cgroup/memory.events
~~~

In memory.stat, fields such as anon, file, file_dirty, and file_writeback help understand how memory accounting splits between anonymous memory and file cache. Names/fields may vary by kernel. Inside a container with its own cgroup namespace, the actual path may differ; identify the process's cgroup before reading.

Do not treat the entire file field as checkpoint cache. It may include many files used by the process or cgroup. Combine with block I/O metrics and the specific workload to determine the cause.

## 7. Operating System Cache After CRaC Restore

A checkpoint saves process state, whereas the page cache is state managed by the kernel. Do not assume that the page cache from the checkpoint-creation host will be transferred intact to the restore host.

Several scenarios:

- Restore on the same host: checkpoint file pages may still remain in the page cache, if not yet reclaimed.
- Restore on a different host: the new host's page cache generally does not contain the file's data merely because the old host read it.
- Restore after a long period: the cache may have been reclaimed due to memory pressure.
- Restore from a network volume: the new client/host cache and the storage-service-side cache can differ.
- Restore with lazy paging: unloaded pages may only be read when accessed by the application.

This explains why the same checkpoint can have different restore times across runs or across nodes. Results also depend on whether the artifact was read previously.

### JIT Warmup Does Not Warm the Checkpoint Page Cache

JIT warmup causes the JVM to execute methods to gather profiles and compile code. It does not guarantee that pages of the checkpoint artifact or business files are in the page cache.

Conversely, pre-reading a large file can warm the page cache without bringing Java methods up to JIT thresholds. The two activities have different goals and costs:

| Activity | What Does It Warm? | Tool/Approach |
|---|---|---|
| JIT warmup | Method profiles and machine code | Run synthetic workload on code paths to optimize |
| File pre-read | Page cache for the file being read | Controlled file read before the workload |
| Application cache warmup | Objects/data in the application cache | Load keys or data via the cache API |
| Dependency warmup | Connections, DNS, TLS, or client pools | Check and initialize dependencies per lifecycle |

Do not read the entire checkpoint file during startup solely to warm the cache if not required by the runtime. It can increase I/O, contend for memory, and slow down other instances.

## 8. Measuring Page Faults and I/O on Linux

Combine multiple tools because each tool measures a different aspect.

### vmstat

~~~shell
vmstat 1
~~~

Some useful columns:

- si, so: amount of memory swapped in/out in the tool's units.
- bi, bo: block input/output.
- r: number of runnable processes.
- wa: CPU time waiting for I/O according to vmstat's calculation.
- free, buff, cache: system-level memory metrics.

vmstat provides a host-wide view, not just for the Java process. Use it to determine whether there is I/O or swap pressure during checkpoint/restore.

### pidstat

~~~shell
pidstat -r -d -p 2481 1
~~~

-r displays memory and page fault statistics; -d displays task I/O. Check the help output for your sysstat version because fields and units can differ.

### iostat

~~~shell
iostat -xz 1
~~~

Commonly useful fields include:

- r/s, w/s: number of read/write operations per second.
- rkB/s, wkB/s: read/write throughput.
- r_await, w_await: average I/O wait time.
- aqu-sz: average queue size.
- %util: device busy level as reported by the tool.

Do not interpret %util alone as the percentage of remaining capacity, especially on NVMe devices or multi-queue storage. Also inspect latency, queue depth, and the limits of the device type.

### perf stat

~~~shell
perf stat -p 2481 -e page-faults,minor-faults,major-faults
~~~

This command measures process page fault events while perf is attached. perf permissions may be restricted by kernel policy or container security. Some platforms do not expose all events or require separate configuration.

### /proc and System Metrics

~~~shell
cat /proc/2481/stat
cat /proc/2481/status
cat /proc/meminfo
cat /proc/vmstat
~~~

/proc/PID/stat contains the process's minor/major fault counters; /proc/meminfo and /proc/vmstat provide system-wide metrics. Read the exact format and units of the running kernel. System counters accumulate since boot, so take before/after samples or use an interval-based monitoring tool.

## 9. Distinguishing Page Faults from Block I/O

A major fault signals that a page fault required I/O, but it is not an exact count of device block read operations. One major fault can trigger multiple I/Os; a single file read can be readahead and satisfy multiple page faults; I/O can be served from a network filesystem or another cache layer.

Conversely, block I/O can occur without directly corresponding to a process's major faults:

- Page cache writeback.
- Flush or fsync.
- Proactive kernel read-ahead.
- I/O from other processes on the same host.
- Filesystem metadata I/O.
- Storage driver or container runtime activity.

When analyzing restore:

1. Measure major/minor faults of the Java process.
2. Measure block reads/writes of the host or device.
3. Measure checkpoint artifact read duration.
4. Observe device latency and queue depth.
5. Correlate timestamps with CRaC runtime logs.

If major faults rise without a corresponding rise in device reads, the data may be served from a cache layer or a different backing store. If device reads rise while JVM major faults stay low, the I/O may come from the engine, helper processes, readahead, or writeback. Check which process and device are actually performing the I/O.

## 10. Benchmarking the Impact of Cache and Storage

Benchmarks must isolate variables to avoid misleading conclusions. A workflow can include:

### Defining the Questions to Measure

Examples:

- How does checkpoint creation time depend on write throughput?
- How much does restore differ between warm cache and cold cache?
- Does storage latency affect time-to-readiness or first-request latency?
- Does lazy restore increase major faults when traffic begins?
- Does memory pressure cause page cache to be reclaimed and slow down restore?

Do not combine every objective into a single startup figure. Measure checkpoint duration, restore duration, time-to-ready, and post-restore latency separately.

### Controlling the Environment

- Use the same JDK vendor/build, CRaC runtime, engine, and JVM flags.
- Use the same checkpoint artifact or create the artifact using the same procedure.
- Record container image digest, kernel, CPU, and storage type.
- Run on a host without competing workloads, or explicitly record competing workloads.
- Record memory limits, heap size, cgroup limits, and swap policy.
- Use the same network/storage region if using network volumes.
- Repeat multiple times and record the distribution, not just the best run.

### Comparing Warm Cache and Cold Cache

A measurement can be divided into two groups:

**Warm-cache group:** read the checkpoint artifact once before measuring, then restore and measure the subsequent run. Document the pre-read step and verify the file remains in cache if observability tools allow.

**Cold-cache group:** use a fresh test host/VM or a file/artifact that has not yet been read on that host. Do not assume that merely starting a new process means the page cache is cold; the page cache belongs to the kernel and may still hold data from a previous process.

On Linux, you may encounter instructions to use /proc/sys/vm/drop_caches to clear the cache. This operation affects the entire system, can slow down other workloads, and requires administrative privileges. Do not run it in production or on shared hosts. Prefer a dedicated benchmark host, a fresh VM, or a new uncached artifact.

### Selecting Representative I/O Patterns

- Sequential read: reading a file sequentially.
- Random read: reading scattered regions.
- Sequential write: creating a large checkpoint artifact.
- Small-file metadata: many small files and directory entries.
- Sync write: workloads requiring flush/fsync.

Do not use a single sequential benchmark to represent every type of checkpoint I/O. How the engine writes files and how restore reads files may follow different patterns.

### Recording Metrics

| Metric | Meaning |
|---|---|
| Checkpoint duration | Time from checkpoint request until the artifact is ready |
| Restore duration | Time the runtime/engine takes to restore the process |
| Time-to-ready | Time from restore start until the instance can accept traffic |
| First-request latency | Latency of the first request or first batch of requests |
| p50/p95/p99 latency | Post-restore latency distribution |
| Major/minor faults | Number of process page faults |
| Device read/write throughput | Storage read/write bandwidth |
| I/O await and queue depth | Device latency and queue depth |
| Memory pressure | Cgroup usage, reclaim, swap, and OOM events |
| CPU utilization | Cost of handling page faults, compression, and runtime |

Record both time to readiness and post-readiness latency. A system may report ready early while the first requests still have to wait for page-ins, resulting in high p99.

## 11. Using fio and Storage Benchmark Tools

fio can generate synthetic I/O workloads to measure storage. Sequential read example:

~~~shell
fio --name=seq-read --filename=/mnt/checkpoint-bench/test.bin \
    --size=4G --rw=read --bs=1M --iodepth=16 \
    --direct=1 --runtime=60 --time_based --group_reporting
~~~

Random read example:

~~~shell
fio --name=rand-read --filename=/mnt/checkpoint-bench/test.bin \
    --size=4G --rw=randread --bs=4k --iodepth=32 \
    --direct=1 --runtime=60 --time_based --group_reporting
~~~

The commands above are examples creating dedicated benchmark files. Choose size, block size, queue depth, and direct I/O according to the actual device and workload. Direct I/O bypasses the page cache for supported I/O paths, so the results do not represent a Java application using buffered I/O or memory mapping. Measure buffered I/O as well if that is the actual behavior.

Do not run fio against real data files, production volumes, or checkpoints currently in use. Benchmark workloads can consume IOPS, bandwidth, and storage space, affecting other applications. Use a separate volume/host and delete test files following safe procedures.

fio measures the storage path, not CRaC restore directly. After establishing a storage baseline, still measure actual checkpoint/restore to understand how the engine and runtime use storage.

## 12. Should Checkpoint Files Be Pre-Read to Warm the Cache?

Pre-reading an artifact can warm the page cache on the current host, but it is not always beneficial:

- Reading the entire file can occupy the page cache and evict other business data.
- It consumes storage bandwidth prior to restore.
- If the artifact is larger than available RAM, the initial pages may be reclaimed before restore uses them.
- If restore uses lazy paging, pre-reading the whole file can negate the benefit of loading only needed pages.
- If restore occurs on a different host, pre-reading on the checkpoint-creation host does not warm the target host's cache.

If the runtime has an official prefetch mechanism, use it according to the runtime's documentation. If implementing a custom pre-read, measure its impact on memory pressure and latency of other workloads. Do not blindly add a step that reads the entire checkpoint file at startup without benchmarking.

## 13. Optimizing the Storage Path for Checkpoints

Several ways to improve can be considered:

**Use storage with suitable latency and throughput.** Large checkpoints or latency-sensitive lazy-paging workloads may benefit from local NVMe or an appropriately configured volume. Measure according to the actual I/O profile.

**Avoid contended volumes.** If checkpoint artifacts share a volume with logs, databases, or heavy workloads, I/O contention can occur. Separate volumes or apply QoS when needed.

**Inspect the filesystem and container layers.** Overlay filesystems, copy-up, metadata operations, and many small files can introduce overhead. Measure the exact path actually used by the engine.

**Reduce state size sensibly.** Clearing unnecessary caches or temporary objects before checkpointing can reduce the memory state that must be saved. However, do not remove state required for correctness or increase post-restore startup cost.

**Consider compression and encryption.** Compression reduces bytes written/read but consumes CPU and can alter demand-paging behavior. Encryption protects artifacts but can add CPU/I/O overhead. Choose based strictly on measurements and security policies.

**Place checkpoint artifacts close to the restore environment.** Reducing network hops or artifact download time can improve restore. However, the storage location must meet durability, access control, encryption, and distribution policies.

**Maintain sufficient memory headroom.** If heap and native memory occupy nearly the entire cgroup limit, the page cache is easily reclaimed and restore can trigger memory pressure. Evaluate -Xmx together with total memory, not just the heap.

## 14. Example Analysis of a Slow Restore

Suppose the same checkpoint yields these results:

| Run | Restore duration | Time-to-ready | First-request p99 |
|---|---:|---:|---:|
| A: host already read artifact | 1.8 s | 2.1 s | 45 ms |
| B: cold-cache host | 7.4 s | 7.8 s | 52 ms |
| C: demand paging and early traffic | 2.0 s | 2.2 s | 480 ms |

The numbers above are illustrative examples only, not reference benchmarks.

These can be interpreted as:

- Run A is fast because the checkpoint artifact may already reside in the page cache.
- Run B takes longer to load the artifact from backing storage before readiness.
- Run C reports ready early, but the first request accesses unloaded pages, causing latency to spike.

To confirm, correlate engine logs, page fault counters, block I/O, storage latency, and request traces. A timing table alone does not prove the cause.

If C reflects lazy restore behavior, consider prefetching regions genuinely needed for critical request paths or delaying readiness until a required set of pages/dependencies is ready. Use official runtime mechanisms; do not manually read or write internal checkpoint memory regions.

## 15. Common Measurement Mistakes

**Comparing a warm-cache run with a cold-cache run without recording the cache state.**

Results are not reproducible. Record pre-read steps, host, page cache, memory pressure, and I/O metrics.

**Treating every major fault as an SSD read.**

A major fault only indicates that I/O is needed to resolve the fault; backing storage may be swap, a network filesystem, or another layer.

**Treating the page cache as Java heap.**

The page cache belongs to the kernel and has a lifecycle distinct from the heap, GC, and checkpoint object graph.

**Increasing the heap to hold file cache.**

A larger heap can reduce RAM remaining for page cache and native memory. The entire cgroup must be balanced.

**Using drop_caches in production to create a cold cache.**

This operation affects the entire host. Use a dedicated benchmark environment.

**Measuring only storage throughput.**

Random I/O, latency, IOPS, queue depth, and fsync may be the actual bottleneck.

**Using fio to conclude whether CRaC restore is fast or slow.**

fio only measures synthetic storage workloads. Measure actual restore on the exact engine/runtime.

**Assuming JIT warmup warms the page cache.**

JIT warmup executes methods; it does not automatically read checkpoint artifacts or data files.

**Assuming a fast restore means a fast first request.**

With demand paging, a process can begin running before all required pages are loaded. Measure first-request and p95/p99 latency after restore.

## 16. Measurement and Improvement Workflow

A practical workflow:

1. Identify the I/O portion to evaluate: checkpoint write, artifact transfer, restore read, or post-restore workload.
2. Record the JDK/CRaC runtime, checkpoint engine, kernel, container digest, storage type, and mount path.
3. Record heap size, cgroup memory limit, swap policy, and memory pressure level.
4. Separate warm-cache, cold-cache, and partial-cache runs; do not drop caches on production hosts.
5. Measure checkpoint duration, restore duration, time-to-ready, and first-request latency.
6. Collect minor/major faults, block reads/writes, I/O latency, queue depth, and cgroup memory statistics.
7. Run sequential/random workloads and realistic application workloads on dedicated storage to establish a baseline.
8. Repeat multiple times, compare p50/p95/p99, and document variance across hosts.
9. Change one factor at a time—such as storage class, memory headroom, compression, or prefetch policy—and re-measure.
10. Apply changes only after verifying correctness, artifact durability, and restore capability in the target environment.

## 17. Conclusion

The page cache enables the kernel to serve file reads from RAM; a page fault is the mechanism handling virtual memory accesses, where minor faults usually require no storage I/O while major faults require I/O to complete. Disk speed, IOPS, latency, filesystem, and memory pressure can all affect checkpoint creation time, artifact reading, restore, and post-restore latency.

With CRaC, the page cache is not Java heap state and should not be assumed to transfer intact between hosts. Eager versus lazy restore behavior depends on the specific implementation. Measure checkpoint duration, restore duration, time-to-ready, and first-request latency separately; combine page fault counters with block I/O, storage latency, and cgroup memory statistics. Use a dedicated benchmark environment to compare warm/cold caches, then optimize the storage path and memory headroom for the actual workload.

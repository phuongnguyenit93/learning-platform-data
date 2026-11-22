# Measuring RSS, Container Memory, CPU, and Image Storage Size

Evaluating Java CRaC performance cannot look solely at restore time. A checkpoint can shorten JVM startup time while increasing resident memory, artifact size, storage read time, or CPU usage during the restore phase. In Kubernetes, container memory and CPU limits can also cause a Pod that restores quickly on a development machine to suffer throttling or OOM when running under actual quotas.

To compare cold start against restore meaningfully, at least four groups must be measured separately: **RSS and process memory**, **container memory accounting**, **CPU usage/throttling**, and **checkpoint storage size**. Measurements must be recorded at the same lifecycle milestones, under the same workload, and with the same resource limits. These metrics have different meanings; RSS does not equal Java heap, container memory usage does not equal the RSS of a single process, CPU percentage is not CPU time, and archive size does not necessarily equal actual filesystem usage.

## 1. Defining the Metrics to Measure

Before collecting data, standardize the names and units so different metrics are not mistakenly compared.

| Metric | Meaning | Common Measurement Source |
|---|---|---|
| RSS (Resident Set Size) | Process memory pages currently resident in RAM | `/proc/<pid>/status`, `smaps_rollup` |
| PSS (Proportional Set Size) | Resident memory scaled proportionally by the number of processes mapping a page | `/proc/<pid>/smaps_rollup` |
| USS (Unique Set Size) | Private pages belonging solely to the process | Sum of private clean/dirty in `smaps_rollup` |
| Java heap used/committed | Heap currently in use and heap committed by the JVM | JMX `MemoryMXBean`, GC logs, JFR |
| Native memory | JVM native memory and part of native libraries | Native Memory Tracking (NMT), profiler, OS metrics |
| Container memory current | Memory currently accounted to the cgroup/container | cgroup v2 `memory.current`, v1 `memory.usage_in_bytes` |
| Container working set | Estimate of actively used memory, typically excluding part of inactive file cache | cAdvisor / Kubernetes metrics |
| CPU time | Actual CPU time consumed by the process or cgroup | `/proc`, cgroup `cpu.stat`, process metrics |
| CPU throttling | Time or number of periods throttled by CPU quota | cgroup `cpu.stat`, cAdvisor |
| Checkpoint apparent size | Total logical size of the checkpoint files | `du --apparent-size`, sum of file sizes |
| Checkpoint allocated size | Filesystem blocks actually allocated | `du`, filesystem metrics |
| Archive/object size | Number of bytes after packaging or compression | `stat`, object storage metadata |

Do not sum the RSS of all processes and treat it as container memory if they share pages. Conversely, a container can have multiple processes and page cache outside the JVM's RSS. When evaluating the ability to run under a memory limit, cgroup metrics are usually the authoritative source; RSS/PSS helps explain which portions the process is using.

## 2. RSS, PSS, and USS of a Java Process

### 2.1. RSS

RSS is the number of process pages currently residing in RAM. It is a useful metric for observing the JVM's resident footprint, but it includes shared pages and does not indicate which pages belong to the heap, metaspace, code cache, thread stacks, or file mappings.

On Linux, RSS can be viewed with:

```bash
grep -E '^(VmRSS|VmHWM|VmSize|VmPeak):' /proc/<pid>/status
```

Common fields:

- `VmRSS`: current RSS, usually displayed in kB.
- `VmHWM`: high-water mark of RSS since the process started.
- `VmSize`: virtual address space, not actual RAM in use.
- `VmPeak`: highest virtual memory observed.

`VmSize` can be much larger than RAM because the JVM reserves heap regions or memory mappings. Do not use `VmSize` in place of RSS or container memory.

### 2.2. PSS and USS

`/proc/<pid>/smaps_rollup` aggregates statistics across memory map regions:

```bash
cat /proc/<pid>/smaps_rollup
```

Notable fields:

- `Rss`: total resident pages.
- `Pss`: shared pages scaled proportionally by the number of mappings/processes sharing them.
- `Private_Clean` and `Private_Dirty`: clean and dirty private pages.
- `Shared_Clean` and `Shared_Dirty`: clean and dirty shared pages.
- `Anonymous`: anonymous resident memory.

USS can be estimated as `Private_Clean + Private_Dirty`. PSS is useful when multiple JVMs map the same libraries or file page cache; USS is useful when estimating the memory belonging solely to a single process. These numbers are snapshots at the time of reading and can change immediately afterward.

Example extracting the key fields:

```bash
awk '/^(Rss|Pss|Private_Clean|Private_Dirty|Shared_Clean|Shared_Dirty|Anonymous):/ { print }' \
  /proc/<pid>/smaps_rollup
```

Not every kernel or container permission setup allows full reading of `smaps_rollup`. If the file does not exist or returns permission denied, note this limitation and use cgroup metrics along with other measurement sources.

## 3. Distinguishing RSS from Java Heap and Native Memory

The JVM manages many memory regions outside the heap. A Java process can use:

- Java heap containing objects.
- Metaspace and compressed class space containing class metadata.
- JIT code cache containing compiled machine code.
- Thread stacks for Java/native threads.
- Direct buffers and memory mappings.
- Native allocations from the JVM, JNI, TLS, compression, database drivers, and other libraries.
- File-backed mappings and page cache managed by the kernel.

Therefore, `MemoryMXBean.getHeapMemoryUsage().getUsed()` does not represent RSS. Committed heap does not equal RSS either: part of the committed heap may not have been touched yet, while RSS can contain substantial native memory.

Measuring heap via JMX:

```java
import java.lang.management.ManagementFactory;
import java.lang.management.MemoryUsage;

public final class MemorySnapshot {
    public static void printHeap() {
        MemoryUsage heap = ManagementFactory.getMemoryMXBean()
                .getHeapMemoryUsage();

        System.out.printf(
                "heap.used.bytes=%d heap.committed.bytes=%d heap.max.bytes=%d%n",
                heap.getUsed(), heap.getCommitted(), heap.getMax());
    }
}
```

JMX shows the heap state from the JVM perspective. Record RSS/PSS and cgroup memory alongside it to see whether the difference lies in native/runtime memory, page cache, or auxiliary processes.

### 3.1. Native Memory Tracking

HotSpot Native Memory Tracking (NMT) can help classify part of the native memory managed by the JVM. Enable NMT at startup:

```bash
java -XX:NativeMemoryTracking=summary -jar app.jar
```

Or use `detail` when more detailed information is needed, at a higher tracking overhead:

```bash
java -XX:NativeMemoryTracking=detail -jar app.jar
```

Then query:

```bash
jcmd <pid> VM.native_memory summary
```

NMT can report categories such as Java Heap, Class, Thread, Code, GC, Compiler, and Internal. It is useful for explaining the JVM footprint, but it is not a total system memory counter. NMT does not cover every allocation made by third-party native libraries or every memory mapping outside the JVM; cross-check against `/proc` and cgroup.

NMT must be enabled when the JVM starts. Full NMT cannot be enabled retroactively for an already running process. Enabling NMT also incurs overhead, so it must be used consistently across benchmark runs or separated into diagnostic runs.

### 3.2. Recording GC and JFR

GC logs help understand heap occupancy, pauses, and allocation pressure:

```bash
java -Xlog:gc*,safepoint:file=/var/log/app-gc.log:time,uptime,level,tags \
  -jar app.jar
```

JFR can provide execution samples, allocation, thread, GC, and compilation events. When comparing restore, use the same JFR recording configuration on both branches. Observability tools also consume CPU and memory; do not compare a profiled run against an unprofiled run and conclude the difference comes from CRaC.

## 4. Measuring Container Memory Using cgroup

Inside a container, cgroup is an important source for knowing how much memory the kernel accounts to the workload. Kubernetes can display memory usage via the metrics pipeline, but reading cgroup directly helps understand the limits and state at the time of measurement.

### 4.1. Identifying the cgroup Version

On Linux, cgroup v2 is typically mounted at `/sys/fs/cgroup` and contains the `cgroup.controllers` file. It can be checked with:

```bash
test -f /sys/fs/cgroup/cgroup.controllers && echo cgroup-v2
```

If that file is absent, the system may be using cgroup v1 or a hybrid layout. Inside a container, the actual cgroup path can be found from `/proc/self/cgroup` and mount information.

### 4.2. cgroup v2

Commonly useful files:

| File | Meaning |
|---|---|
| `memory.current` | Memory currently accounted to the cgroup |
| `memory.max` | Memory limit; `max` means no limit is set at that cgroup level |
| `memory.peak` | Highest recorded memory level if supported by the kernel |
| `memory.stat` | Breakdown of anonymous, file, kernel, slab, and other memory types |
| `memory.events` | Event counters such as `high`, `max`, `oom`, `oom_kill` |
| `cpu.stat` | CPU usage and throttling information |
| `cpu.max` | CPU quota and period |

Reading a snapshot:

```bash
cat /sys/fs/cgroup/memory.current
cat /sys/fs/cgroup/memory.max
cat /sys/fs/cgroup/memory.peak
cat /sys/fs/cgroup/memory.stat
cat /sys/fs/cgroup/memory.events
cat /sys/fs/cgroup/cpu.stat
cat /sys/fs/cgroup/cpu.max
```

`memory.current` accounts for the memory of the entire cgroup, which can include anonymous memory, file cache, and some kernel memory. Therefore, it usually differs from the JVM's RSS. `memory.events` helps detect memory pressure and OOM; if `oom_kill` increases after restore, inspect peak memory and limits instead of looking only at heap used.

`memory.peak` may be unavailable on older kernels or not exposed inside the container namespace. If per-phase peaks are needed, sample `memory.current` periodically or use metrics from the node/cAdvisor. Do not reset the high-water mark during a benchmark if doing so breaks comparability across phases.

### 4.3. cgroup v1

With cgroup v1, the files typically have different names:

| File | Meaning |
|---|---|
| `memory.usage_in_bytes` | Memory currently accounted to the cgroup |
| `memory.limit_in_bytes` | Memory limit |
| `memory.max_usage_in_bytes` | High-water mark |
| `memory.stat` | Memory and cache breakdown |
| `memory.failcnt` | Number of times the limit threshold was exceeded |
| `cpuacct.usage` | Cumulative CPU time in nanoseconds |
| `cpu.stat` | Quota/throttling statistics if the controller is enabled |
| `cpu.cfs_quota_us` / `cpu.cfs_period_us` | CPU quota and period |

Mount paths for v1 can vary across container distributions. Use `/proc/self/cgroup` and `/proc/mounts` to determine the actual path instead of hard-coding every environment into a single script.

### 4.4. Container Working Set

Kubernetes metrics often include `container_memory_working_set_bytes`, which cAdvisor computes from memory usage after subtracting part of the inactive file cache. This is a useful metric for observing workload memory pressure, though the exact calculation depends on cAdvisor and the kernel. Do not treat the working set as RSS or as the exact total of every byte the container may use.

Cross-check at least three figures: process RSS/PSS, cgroup memory current/peak, and container working set. If cgroup memory is significantly higher than RSS, check file cache, native/kernel memory, or other processes in the same cgroup.

## 5. Measuring Memory in Kubernetes

Kubernetes distinguishes between requests and limits:

- `resources.requests.memory` affects scheduling and certain QoS decisions.
- `resources.limits.memory` sets the memory limit for the container; exceeding the limit can lead to an OOM kill.
- `kubectl top pod` provides a snapshot from Metrics Server, not a replacement for time series or high-water marks.

Example:

```yaml
resources:
  requests:
    cpu: "1"
    memory: "2Gi"
  limits:
    cpu: "2"
    memory: "3Gi"
```

These values are illustrative only. Choose requests/limits from the measured distribution under restore and steady-state conditions, accounting for peaks, native memory, page cache, and auxiliary processes.

Taking a snapshot:

```bash
kubectl top pod -n production
kubectl top pod orders-api-abc123 -n production --containers
kubectl describe pod orders-api-abc123 -n production
```

`kubectl top` may not reflect brief peaks during restore. For benchmarks, collect Prometheus/cAdvisor time series or read cgroup periodically inside the container. `kubectl describe pod` helps check `OOMKilled`, restart count, and events, but does not provide full memory history.

Some useful cAdvisor/Prometheus metrics:

- `container_memory_usage_bytes`: memory usage according to cAdvisor.
- `container_memory_working_set_bytes`: working set.
- `container_memory_rss`: RSS according to container metrics.
- `container_cpu_usage_seconds_total`: cumulative CPU time.
- `container_cpu_cfs_throttled_seconds_total` and `container_cpu_cfs_throttled_periods_total`: throttling with CFS quota when exposed.

Metric names and availability depend on the Kubernetes version, kubelet, cAdvisor, and Prometheus configuration. Verify metrics in the running environment before writing dashboards or alerts.

## 6. Measuring CPU Usage and CPU Throttling

CPU must be measured as cumulative CPU time and consumption rate over a time interval. A single CPU percentage snapshot is not sufficient for comparison.

### 6.1. Process CPU Time

On Linux, `/proc/<pid>/stat` contains user CPU time and system CPU time in ticks. Tools such as `pidstat` can display periodic CPU utilization:

```bash
pidstat -p <pid> 1
```

For a Java process, `top -H` or `pidstat -t` helps inspect which threads are consuming CPU. However, the PID may differ after a restore or container restart; measurements should be tagged with Pod UID/container ID and timestamp.

### 6.2. cgroup v2 CPU Time

`cpu.stat` typically contains:

- `usage_usec`: total cgroup CPU time in microseconds.
- `user_usec` and `system_usec`: user/system time if provided by the kernel.
- `nr_periods`, `nr_throttled`, `throttled_usec`: quota/throttling statistics if available.

To calculate average CPU cores over the measurement interval:

\[
\text{CPU cores} = \frac{\Delta\text{usage\_usec}}{\Delta t_{usec}}
\]

For example, a cgroup consuming 2,000,000 microseconds of CPU over 1,000,000 microseconds of wall-clock time corresponds to an average of 2 CPU cores. To express this as a percentage of one core, multiply the result by 100. To express it as a percentage of quota, divide by the allocated quota cores and multiply by 100.

`cpu.max` has the form `quota period` (microseconds) or `max period`. For example, `200000 100000` grants a quota equivalent to 2 CPU cores per period. If the quota is `max`, the cgroup has no hard quota at that level, though it may still be subject to node or parent-level CPU limits.

### 6.3. Throttling

A container may require substantial CPU during restore but be constrained by a CPU limit. In that case, restore time increases even though the code has not changed. Record `usage_usec`, `nr_throttled`, `throttled_usec`, and the CPU quota.

CPU throttling is not the same as low CPU utilization. A container may want to use more CPU but get throttled; the usage chart may appear capped at the quota while latency rises. Looking only at CPU percentage makes it easy to misjudge that restore is not saturating CPU or that the workload is already optimized.

### 6.4. Separating Restore CPU from Post-Ready CPU

Record CPU across separate phases:

1. Container start and reading checkpoint artifacts.
2. JVM restore.
3. `afterRestore` and reconnection.
4. Post-restore warm-up, if any.
5. First request.
6. Steady-state workload.

Total Pod CPU time does not show which phase consumes the most. Use timestamps or trace events to separate the segments. For cold start, record the corresponding phases such as JVM startup, application initialization, warm-up, and first request.

## 7. Measuring Checkpoint Storage Size

A checkpoint can be a directory containing many files. Three types of size must be distinguished:

1. **Logical/apparent size:** total bytes according to the file sizes seen by the application.
2. **Allocated size:** filesystem blocks actually allocated; this can differ from logical size due to sparse files, compression, or block size.
3. **Archive/object size:** number of bytes after packaging, compression, or upload.

On Linux:

```bash
# Logical size (bytes) of the directory tree
du --apparent-size -B1 -s /var/lib/app/checkpoint

# Filesystem-allocated block size
du -B1 -s /var/lib/app/checkpoint

# Size of each file
find /var/lib/app/checkpoint -type f -printf '%s %p\n' | sort -nr
```

`du --apparent-size` is appropriate for determining total logical file size. `du` by default measures allocated blocks. For sparse files, the two numbers can differ significantly. If a filesystem with compression, deduplication, or reflinks is used, the physical usage on the storage backend may differ even further.

After creating an archive:

```bash
stat -c '%n %s bytes' checkpoint.tar.zst
```

The compression ratio can be calculated as:

\[
\text{Compression ratio} = \frac{\text{archive size}}{\text{apparent payload size}}
\]

For example, an 8 GiB payload compressed into a 3 GiB archive yields a ratio of 0.375 (37.5%). Record both payload size and archive size; recording only archive size hides storage costs if the checkpoint is stored as an uncompressed directory.

### 7.1. Measuring Checkpoint Write and Read Speed

Checkpoint creation time and restore time can be dominated by storage. Measure separately:

- Time for the runtime to write checkpoint files.
- Time to generate the manifest and compute checksums.
- Time to compress the archive.
- Time to upload or copy to storage.
- Time to download/copy to the new Pod.
- Time to extract or prepare the working copy.
- Time for the JVM to read and restore the checkpoint.

Do not lump everything into a single "restore duration" figure if the goal is to find bottlenecks. If the checkpoint is mounted directly from a PVC or network filesystem, measure read throughput and latency on that exact storage class.

### 7.2. Container Storage and Ephemeral Storage

Kubernetes can account ephemeral storage for the writable layer, logs, and `emptyDir`. Checkpoints written to the container filesystem can increase ephemeral storage usage and exceed node/container quotas. If a PVC is used, capacity is accounted against the storage backend and its own quota.

Track:

- Size of the checkpoint directory.
- Size of the archive in the registry/object storage.
- Size of the working copy on `emptyDir` or the writable layer.
- Size of logs and temporary files during verification/restore.
- Number of old checkpoints still retained and the retention policy.

If every scaling-out Pod creates a large local checkpoint copy on the node, total storage can grow with the replica count. Use immutable artifacts and appropriate node-level caching if the platform allows it, while controlling write permissions and integrity.

## 8. Calculating Storage Costs with Multiple Replicas

A shared checkpoint may be stored once in object storage, yet each Pod may still need its own working copy. To estimate storage, separate:

- Size of the base artifact.
- Number of copies at the node or volume level.
- Size of each Pod's individual working directory.
- Concurrent archives and extracted copies during a rollout.
- Checkpoint versions retained under the retention policy.

For example, with a 4 GiB artifact, a rollout with 6 concurrent new Pods each requiring a 4 GiB working copy can need up to 24 GiB of working storage, excluding the base artifact, archive, and headroom. This is only a linear estimate; reflinks, shared volumes, or node-local caches can make actual usage differ.

When multiple versions are retained, estimate total storage as:

\[
S_{total} = \sum_{v=1}^{N} S_{artifact,v} + S_{working} + S_{temporary}
\]

Where `N` is the number of retained checkpoint versions. If object storage uses versioning or replication, add the extra cost from the storage provider's policy.

## 9. Comparing Cold Start and CRaC Restore

A fair benchmark requires the same application, the same JDK/CRaC build, the same node class, the same CPU/memory limits, the same data, and the same workload. If restore uses a warmed-up checkpoint while cold start is not warmed up, the measurement compares two different workflows. Two separate scenarios can be measured:

- **Cold start baseline:** JVM starts from scratch, followed by application initialization and warm-up according to the baseline configuration.
- **CRaC restore:** JVM restores from a checkpoint created through a defined process, runs `afterRestore`, and reaches readiness.

If the goal is to measure the snapshot's benefit specifically, document which initialization and warm-up the checkpoint already includes and which resources are refreshed after restore.

### 9.1. Timestamps to Record

| Milestone | Meaning |
|---|---|
| `t0` | Container/Pod starts |
| `t1` | Entrypoint begins verifying/preparing checkpoint |
| `t2` | JVM begins cold start or restore |
| `t3` | JVM restore/start completes |
| `t4` | `afterRestore` and dependency refresh complete |
| `t5` | Readiness succeeds |
| `t6` | First request completes |
| `t7` | Steady-state workload stabilizes |

From these milestones, the following can be calculated:

- Restore duration: `t3 - t2`.
- Post-restore resource duration: `t4 - t3`.
- Restore-to-ready: `t5 - t0` or `t5 - t2`, depending on the measurement question.
- First-request latency: time to process the first request after `t5`.
- End-to-first-response: `t6 - t0`.

Milestone definitions must be consistent between cold start and restore. If cold start includes application initialization while restore starts at a different point in the process, report both total time to Ready and each phase separately.

### 9.2. Multiple Runs and Percentile Reporting

A single run is not enough to draw conclusions. Execute multiple repetitions under equivalent conditions, recording the node, kernel, runtime, CPU quota, memory limit, and storage class. Report:

- Median (p50) to describe a typical run.
- p90/p95 or p99 to show tail latency.
- Min/max to identify outliers, without using them as the primary conclusion.
- Number of failures, OOMs, timeouts, or restore errors.
- RSS/memory peak and CPU time within the same phase.
- Payload/archive size and transfer duration.

If the data contains outliers caused by image pulls, node scheduling, or storage caching, retain and classify them rather than silently discarding them. Time from container start and JVM restore time can be reported separately to distinguish Kubernetes overhead from CRaC overhead.

## 10. Collecting Linux Snapshots by PID

A simple shell script can record current RSS and cgroup memory during a benchmark:

```bash
#!/usr/bin/env bash
set -euo pipefail

PID="$1"
OUT="${2:-memory-snapshot.txt}"

{
  date --iso-8601=ns
  echo "pid=$PID"
  grep -E '^(Name|VmRSS|VmHWM|VmSize):' "/proc/$PID/status"
  if [ -r "/proc/$PID/smaps_rollup" ]; then
    grep -E '^(Rss|Pss|Private_Clean|Private_Dirty|Anonymous):' \
      "/proc/$PID/smaps_rollup"
  fi
  if [ -r /sys/fs/cgroup/memory.current ]; then
    echo "cgroup_memory_current=$(cat /sys/fs/cgroup/memory.current)"
    echo "cgroup_memory_max=$(cat /sys/fs/cgroup/memory.max)"
  fi
} >> "$OUT"
```

The script assumes cgroup v2 is mounted at `/sys/fs/cgroup`; for cgroup v1 or nested cgroups, resolve the exact path from `/proc/self/cgroup`. `PID` must be the PID in the PID namespace visible from where the script runs. If restore creates a different PID, retrieve the new PID from the process supervisor or container namespace.

To observe peaks, run periodic sampling throughout the restore phase. Taking a single snapshot after the Pod is Ready can miss peaks that occur while the JVM maps the image or extracts the artifact.

## 11. Collecting Metrics with Prometheus/cAdvisor

In Kubernetes, time series help compare multiple Pods and detect brief peaks. An illustrative PromQL query for average CPU cores over 1 minute:

```promql
rate(container_cpu_usage_seconds_total{
  namespace="production",
  pod=~"orders-api-.*",
  container="app"
}[1m])
```

Working set:

```promql
container_memory_working_set_bytes{
  namespace="production",
  pod=~"orders-api-.*",
  container="app"
}
```

CPU throttling ratio by number of throttled periods (if the metric is available):

```promql
rate(container_cpu_cfs_throttled_periods_total{
  namespace="production",
  pod=~"orders-api-.*",
  container="app"
}[5m])
/
clamp_min(rate(container_cpu_cfs_periods_total{
  namespace="production",
  pod=~"orders-api-.*",
  container="app"
}[5m]), 1)
```

Queries must be adjusted according to actual labels and exposed metrics. Some environments use different metric names or do not expose CFS throttling. The throttling ratio above is the ratio of throttled periods, not the percentage of CPU time lost.

When dashboards include multiple Pods, attach a release/checkpoint version label to compare matching versions. Pod names change during rollouts; use deployment/version labels for grouping, and use Pod UID in logs/traces when investigating a specific replica.

## 12. Designing the Benchmark Results Table

Results should be stored per run and per phase. Example CSV schema:

```text
run_id,mode,phase,pod_uid,jdk_version,crac_version,cpu_limit,memory_limit,rss_bytes,pss_bytes,cgroup_memory_bytes,cgroup_memory_peak_bytes,cpu_time_usec,throttled_usec,checkpoint_apparent_bytes,checkpoint_allocated_bytes,archive_bytes,duration_ms,result
run-001,cold,startup,...
run-002,crac,restore,...
```

Do not fill estimated numbers into the table. Record `NA` if a metric is unavailable and add the reason, for example if the kernel does not expose `memory.peak`. Save environment metadata alongside the results so subsequent benchmarks are reproducible.

## 13. Factors That Skew Measurements

### Different Heap Sizes and GCs

Differences in `-Xms`, `-Xmx`, collector, or GC ergonomics can cause RSS and restore time to vary. Keep configurations identical or document the differences explicitly.

### NMT/Profiler Enabled on Only One Branch

NMT, JFR, and profilers add overhead. If needed for analysis, enable them identically on both branches or separate diagnostic runs from performance benchmarks.

### Node File Cache

The first restore may read the checkpoint from cold storage; subsequent runs find the data already in the page cache. Document the cache state and test both cold-cache and warm-cache if both are scenarios that may occur in production.

### CPU Throttling and Noisy Neighbors

Other Pods on the same node can contend for CPU or storage. Record the node, quota, and throttling. Run enough iterations to observe variance.

### RSS and cgroup Memory Do Not Have the Same Scope

RSS covers only one process; cgroup accounts for the whole process group and several other memory types. Do not immediately treat a discrepancy as a measurement error.

### Sparse Files and Compression

Logical size, allocated size, and archive size differ. Report all three if storage cost is an objective.

### Checkpoints Without the Same Warm-Up Level

A checkpoint created after a warm-up workload cannot be fairly compared against an unwarmed cold start unless the benchmark objective is explicitly stated.

### Measuring Time from Different Starting Points

Pod start, container start, JVM start, restore start, and readiness are different milestones. Choose one definition and apply it consistently.

## 14. Recommended Benchmark Workflow

An experimental workflow can be conducted as follows:

1. Select a fixed application version, JDK/CRaC runtime, kernel, container runtime, and storage class.
2. Configure identical CPU requests/limits and memory requests/limits for cold start and restore.
3. Define the workload, data, request count, and readiness criteria.
4. Run cold start multiple times; collect RSS/PSS, cgroup memory, CPU time/throttling, startup duration, and first request.
5. Create the checkpoint following the described initialization/warm-up procedure; record checkpoint duration and file inventory.
6. Measure apparent size, allocated size, archive size, checksum duration, and transfer duration.
7. Run restore multiple times on the same node type; collect metrics at the same milestones as cold start.
8. Separately record peaks during restore, after Ready, and at steady state.
9. Inspect `memory.events`, OOMs/restarts, CPU throttling, and storage pressure.
10. Compare p50/p95/p99, peak memory, CPU time, checkpoint storage, and time to Ready.
11. Repeat with cold/warm storage or different concurrency levels if relevant to production.
12. Save raw samples and metadata, not just final averages.

When benchmarking in Kubernetes, measure both the Pod-level timeline and process-level metrics. A Pod may spend time on scheduling or image pulling before the JVM starts; CRaC only affects a portion of that total time.

## 15. Interpreting Results and Identifying Bottlenecks

Some interpretation patterns:

| Observation | Potential Causes to Check |
|---|---|
| Fast restore but RSS/cgroup peak spikes sharply | Heap snapshot, native memory, thread stacks, page mappings, or warm-up footprint |
| Stable RSS but rising cgroup memory | File cache, native/kernel memory, auxiliary processes, or working copy |
| Low heap used but high RSS | Metaspace, code cache, direct/native buffers, stacks, or mapped pages |
| CPU usage hits quota and throttling rises | CPU limit too low for restore burst or multiple Pods restoring concurrently |
| Low CPU time but high restore duration | I/O wait, storage latency, lock contention, or dependency reconnection |
| Large checkpoint apparent size but small allocated size | Sparse files or filesystem behavior |
| Small archive but slow creation/extraction | Compression CPU cost or storage throughput |
| Fast Pod Ready but slow first request | Lazy initialization, JIT, cache misses, or unwarmed dependency paths |
| Single Pod restores fast, multi-Pod scale-out is slow | Storage contention, connection storm, CPU/node capacity, or image pull |

Do not draw conclusions from a single metric alone. For example, low CPU usage does not automatically mean restore is blocked on I/O; cross-check block I/O, disk latency, thread states, and the timeline. High RSS does not necessarily cause an OOM if cgroup headroom remains sufficient, yet a cgroup peak near the limit is still a risk that must be measured under high load.

## 16. Security and Access Control During Measurement

A checkpoint may contain heap data, tokens, sessions, credentials, and user data. Checkpoint files, manifests, and diagnostic logs must be protected as sensitive artifacts.

- Do not include memory dump contents or raw heap data in benchmark logs.
- Restrict read permissions on `/proc/<pid>/mem`, `smaps`, and the checkpoint directory.
- Do not store tokens or secrets in CSV/metrics labels.
- Keep checkpoints and archives in storage with appropriate ACLs/encryption.
- Delete test artifacts according to the retention policy.
- When using `strace`, detailed NMT, or JFR, control access permissions on output files.

## 17. Data Collection Checklist

- [ ] RSS and VmHWM are recorded with PID and timestamp.
- [ ] PSS/USS are collected if supported by the kernel.
- [ ] Java heap used/committed are recorded via JMX or JFR.
- [ ] NMT is enabled consistently if native JVM memory analysis is needed.
- [ ] cgroup memory current/peak/max and events are saved.
- [ ] Container working set is collected through the metrics pipeline if available.
- [ ] CPU time and quota are recorded for each phase.
- [ ] CPU throttling is measured and distinguished from utilization.
- [ ] Checkpoint logical size, allocated size, and archive size are recorded separately.
- [ ] Transfer, checksum, compression, and extraction durations are separated.
- [ ] Cold start and restore use identical resource limits and workload.
- [ ] The timeline from Pod start to Ready and first response is recorded.
- [ ] Multiple iterations are performed with median/p95/p99 reported.
- [ ] OOMs, restarts, memory events, and storage pressure are checked.
- [ ] Raw samples and environment metadata are saved for reproducibility.

## 18. References

- [Linux proc PID status](https://man7.org/linux/man-pages/man5/proc_pid_status.5.html): Process RSS, VmHWM, and virtual memory.
- [Linux proc PID smaps](https://man7.org/linux/man-pages/man5/proc_pid_smaps.5.html): RSS, PSS, private/shared memory, and mapping details.
- [Linux cgroup v2 documentation](https://docs.kernel.org/admin-guide/cgroup-v2.html): Memory, CPU quota, usage, and event counters.
- [OpenJDK Native Memory Tracking](https://docs.oracle.com/en/java/javase/21/vm/native-memory-tracking.html): How to enable and read NMT.
- [Kubernetes Resource Management](https://kubernetes.io/docs/concepts/configuration/manage-resources-containers/): CPU/memory requests, limits, and container resource behavior.
- [Kubernetes Resource Metrics Pipeline](https://kubernetes.io/docs/tasks/debug/debug-cluster/resource-metrics-pipeline/): Metrics Server and `kubectl top`.
- [Prometheus cAdvisor metrics](https://github.com/google/cadvisor): Container CPU, memory, and throttling metrics.

Evaluating CRaC requires looking simultaneously at resident footprint, container memory limits, CPU time/throttling, and checkpoint storage size. RSS/PSS explains JVM memory usage; cgroup shows the actual memory pressure the container faces; CPU counters reveal cost and throttling; filesystem/archive metrics indicate storage and transfer costs. Comparing cold start against restore is only meaningful with identical runtime, workload, quota, storage, and milestones, while reporting both peaks and percentiles rather than a single snapshot or average value.

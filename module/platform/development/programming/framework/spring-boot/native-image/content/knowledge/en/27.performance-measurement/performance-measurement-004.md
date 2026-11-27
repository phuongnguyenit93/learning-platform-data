# RSS, Heap, Off-Heap Memory, and Container Limits

## 1. Why Can't You Only Look at the Java Heap?

In the **SPRING_BOOT_NATIVE_IMAGE** module, a Spring Boot application is processed by **Spring AOT** and compiled into a **GraalVM Native Image** to evaluate startup time, memory, container packaging, and operations. When comparing memory between a JVM application and a native executable, a common mistake is using heap size as a proxy for total RAM consumption.

Heap is only part of a process's memory. An application also uses memory for thread stacks, runtime/GC structures, direct buffers, JNI or native libraries, image code and data regions, memory-mapped files, socket buffers, and kernel-managed structures. When running in a container, cgroups also account for memory charged to page cache, kernel objects, and other processes in the same cgroup.

Therefore, you need to distinguish three perspectives:

- **Heap:** memory for Java objects managed by the garbage collector.
- **Process memory:** memory pages of the process currently resident in RAM, typically measured via RSS/PSS.
- **Container memory:** memory accounted by cgroups for the container and its descendant processes, compared against the container limit.

These three numbers answer three different questions. Native Image has its own Java heap and does not run on the HotSpot VM; the maximum heap limit only caps the Java heap, not total RSS or container memory. [GraalVM clearly documents this boundary in its Memory Management documentation](https://www.graalvm.org/latest/reference-manual/native-image/optimizations-and-performance/MemoryManagement/).

After this lesson, learners will be able to:

1. Distinguish runtime Java heap, image heap, off-heap/native memory, RSS, PSS, and container memory.
2. Explain why a small heap does not guarantee low RSS or low cgroup usage.
3. Measure Linux process RSS/PSS and cgroup memory usage/limits.
4. Read Spring Boot Actuator memory metrics without confusing them with RSS.
5. Set an appropriate heap budget with container limits and headroom for native memory.
6. Compare JVM and native under identical workload, CPU, memory limits, and measurement duration.
7. Diagnose OOMs caused by Java heap, native allocations, or cgroup limits.
8. Record peak memory, GC state, latency, and benchmark conditions so results are reproducible.

> **Principle:** measure heap to understand object allocation and GC; measure RSS/PSS to understand resident process memory; measure cgroup to know which container limit is being approached. Never substitute one metric for another.

## 2. Memory Model of JVM and Native Image Applications

### 2.1. Runtime Java Heap

The Java heap holds objects created while the application runs. The garbage collector reclaims unreachable objects and may expand or shrink the heap according to runtime policy.

Common heap metrics:

- **Used:** amount of heap currently occupied by objects at sampling time.
- **Committed:** amount of heap the runtime has allocated or guaranteed for allocations.
- **Max:** maximum heap limit permitted by the runtime.
- **Young/old generation:** heap regions serving different roles in GC policy if the active collector uses a generational layout.

Used fluctuates with allocation and GC. Committed does not necessarily equal used, and max is a ceiling rather than guaranteed resident RAM.

For example, a process with heap max 256 MiB, committed 160 MiB, and used 70 MiB does not mean the process consumes only 70 MiB of RAM. RSS also includes other regions and may include committed/resident heap pages managed by the runtime.

### 2.2. Image Heap and Runtime Java Heap in Native Image

Native Image introduces two concepts to separate:

- **Image heap:** objects created during the build, such as static class state initialized at build time. These objects are embedded into the image and become the executable's initial state.
- **Runtime Java heap:** the heap created when the native executable runs, holding objects allocated while processing requests and other runtime work.

The image heap is not the dynamic heap bounded by the application's Xmx. Image data, code, and memory-mapped regions can contribute to RSS as their pages are touched. Executable file size does not equal RSS either: the file may contain pages not loaded into RAM, whereas RSS counts only pages currently resident.

Native Image does not run on the Java HotSpot VM. It uses GraalVM's runtime and memory manager; Serial GC is the default collector in current documentation, while available collectors and specific options depend on distribution, release, and platform. [GraalVM Memory Management](https://www.graalvm.org/latest/reference-manual/native-image/optimizations-and-performance/MemoryManagement/) and [Native Image Build Output](https://www.graalvm.org/latest/reference-manual/native-image/overview/BuildOutput/) show image heap and code area broken out separately in build output.

### 2.3. Off-Heap and Native Memory

In this lesson, **off-heap/native memory** refers collectively to memory regions outside the GC-managed Java object heap. Common sources include:

| Source | Examples | Signals to Watch |
| --- | --- | --- |
| Thread stacks | Stacks of individual platform threads | RSS rises with thread count; high thread count. |
| Direct buffers | ByteBuffer.allocateDirect, network buffers | Buffer pools grow even though heap stays flat. |
| JNI/native libraries | Drivers, codecs, compression, crypto, or C/C++ libraries | RSS increases while heap stays relatively steady; native allocation or library load errors. |
| Runtime and GC structures | Metadata/runtime structures, GC bookkeeping | May appear in RSS without being counted as object heap. |
| Memory-mapped files | Files, shared libraries, resource mappings | RssFile, Pss_File, or file cache changes. |
| Socket/kernel buffers | TCP send/receive buffers and kernel structures | Cgroup usage can climb while process heap does not change. |

On HotSpot, operators are often familiar with Metaspace, Code Cache, and Native Memory Tracking. Do not transfer that exact mental model to Native Image: Native Image does not share HotSpot's metaspace/JIT code cache model. Measure with real tools on the actual runtime, then categorize regions by observable source.

### 2.4. Quick Reference Table

| Concept | Scope | Is It Total Container RAM? |
| --- | --- | --- |
| Heap used | Live/allocated objects in the Java heap | No |
| Heap committed | Heap committed/reserved by the runtime for the allocator | No |
| Heap max | Java heap ceiling | No |
| Image heap | Objects baked into the executable at build time | No |
| Off-heap/native memory | Buffers, stacks, JNI, runtime, and native allocations | No, only a portion |
| RSS | Process pages currently resident in RAM | No |
| PSS | RSS with shared pages allocated proportionally | No |
| Cgroup memory usage | Memory charged to the cgroup and its descendants | Closest to the container limit view |

## 3. RSS, PSS, and Virtual Memory

### 3.1. What Is RSS?

**Resident Set Size (RSS)** is the amount of a process's pages currently resident in RAM. On Linux, RSS is commonly split into:

- RssAnon: anonymous pages, such as heap, stacks, and anonymous mappings.
- RssFile: resident file-backed pages, such as executables and shared libraries.
- RssShmem: shared memory pages, including certain tmpfs mappings.

Conceptually:

~~~text
RSS ≈ RssAnon + RssFile + RssShmem
~~~

RSS is good for observing a single process's footprint, but it counts the full size of shared pages toward each process's RSS. Summing RSS across multiple processes can therefore double-count shared pages.

### 3.2. What Is PSS?

**Proportional Set Size (PSS)** divides the cost of shared pages by the number of processes sharing them. If two processes map a shared page, each process is charged half a page in PSS.

PSS is helpful when comparing the footprint of multiple processes or replicas sharing library pages. On Linux, you can read Pss from /proc/<PID>/smaps_rollup. The kernel documents smaps_rollup as an aggregate summary of fields across all process memory mappings. [Linux proc filesystem documentation](https://www.kernel.org/doc/html/latest/filesystems/proc.html).

### 3.3. Virtual Memory Is Not RAM in Use

VmSize/virtual size reflects mapped or reserved address space. A process can reserve a large region while touching only a small fraction; in that case RSS is much smaller than virtual size.

Do not use VmSize to report memory footprint. When comparing native/JVM, record RSS/PSS and container memory; use virtual size only when investigating mappings or address-space behavior.

### 3.4. Reading Process Information on Linux

Find the application's PID, then read:

~~~bash
cat /proc/<PID>/status
~~~

Common lines to inspect:

~~~text
VmSize:      ...
VmRSS:       ...
VmHWM:       ...
RssAnon:     ...
RssFile:     ...
RssShmem:    ...
Threads:     ...
~~~

VmHWM is the peak RSS high-water mark reported by the kernel. RSS fields in status are approximate counters; for finer breakdown, read:

~~~bash
cat /proc/<PID>/smaps_rollup
~~~

Useful fields include Rss, Pss, Private_Clean, Private_Dirty, Shared_Clean, Shared_Dirty, Anonymous, and Swap. smaps_rollup is more expensive to read than simple counters, so avoid polling it too aggressively during high-load benchmarks.

You can use ps or pmap for quick inspection:

~~~bash
ps -o pid,rss,vsz,comm -p <PID>
pmap -x <PID>
~~~

ps reports RSS in KiB on Linux by default. Always record units when saving results.

## 4. Container Memory and Cgroup Limits

### 4.1. Why Does RSS Differ from Container Memory?

Containers on Linux are resource-constrained via cgroups. Cgroup memory accounting can include multiple categories:

- Anonymous memory and page cache.
- Kernel data structures such as dentries, inodes, and page tables.
- TCP socket buffers.
- Memory of other processes in the same cgroup or descendant cgroups.

Therefore, cgroup memory.current is not a measure of the Java/native process's RSS alone. If a container runs sidecars/helper processes or writes heavily to filesystem cache, cgroup usage can rise even if the application's RSS stays flat. [Linux cgroup v2 documentation](https://github.com/torvalds/linux/blob/master/Documentation/admin-guide/cgroup-v2.rst).

### 4.2. Key Counters in cgroup v2

When the system uses cgroup v2, common files include:

| File | Meaning |
| --- | --- |
| memory.current | Total memory currently used by the cgroup and its descendants. |
| memory.max | Hard memory limit; max means no hard limit is set at that cgroup. |
| memory.high | Threshold that triggers reclaim/throttling when exceeded; does not directly invoke the OOM killer. |
| memory.peak | Recorded peak memory usage of the cgroup. |
| memory.stat | Breakdown of usage across anon, file, kernel, sock, shmem, and other categories. |
| memory.events | Event counters for high, max, oom, oom_kill, and related events. |
| memory.swap.current | Swap currently used by the cgroup. |
| memory.swap.max | Swap limit of the cgroup. |

memory.max is the main hard limit. When usage hits the limit and the kernel cannot reclaim enough, the OOM killer may be invoked inside the cgroup. memory.high typically causes reclaim/throttling and performance degradation before an OOM occurs. Check memory.events to see whether oom or oom_kill counters incremented during a test. [Linux cgroup v2 memory controller](https://github.com/torvalds/linux/blob/master/Documentation/admin-guide/cgroup-v2.rst).

Inspect files inside a Linux container:

~~~bash
cat /sys/fs/cgroup/memory.current
cat /sys/fs/cgroup/memory.max
cat /sys/fs/cgroup/memory.peak
cat /sys/fs/cgroup/memory.stat
cat /sys/fs/cgroup/memory.events
~~~

The paths above are typical when the container sees cgroup v2 mounted at /sys/fs/cgroup. Cgroups may be mounted elsewhere or the process may sit in a sub-cgroup. Check /proc/self/cgroup and mount info to locate the exact directory.

~~~bash
cat /proc/self/cgroup
mount | grep cgroup
~~~

### 4.3. Cgroup v1

Some older systems use cgroup v1. Common filenames:

| File | Meaning |
| --- | --- |
| memory.usage_in_bytes | Current usage. |
| memory.limit_in_bytes | Memory limit. |
| memory.max_usage_in_bytes | Peak usage. |
| memory.stat | Usage breakdown. |
| memory.failcnt | Number of times usage hit the limit per controller accounting. |

Do not assume containers always use cgroup v2. Verify the actual version and mount point before writing collection scripts.

### 4.4. Docker and Kubernetes

Docker sets a hard limit with --memory and a soft reservation with --memory-reservation. Example:

~~~bash
docker run --rm \
  --memory=512m \
  --cpus=1.0 \
  -p 8080:8080 \
  orders-service:native
~~~

--memory=512m is the container limit; it does not mean the Java heap is allowed to use 512 MiB. Docker also documents separate swap options and the performance consequences when a container swaps. [Docker resource constraints](https://docs.docker.com/engine/containers/resource_constraints/).

In Kubernetes:

- **Memory request** influences scheduling decisions and guaranteed resource allocation per cluster mechanics.
- **Memory limit** is enforced via cgroups; exceeding it can trigger an OOM kill.
- kubectl top pod and dashboards typically show working set or metrics-pipeline values; do not assume they match RSS or memory.current identically.
- When a Pod is OOM-killed, inspect container state/reason, restart count, events, and cgroup metrics if accessible.

## 5. Heap, Off-Heap, and Native Image Heap Limits

### 5.1. Xmx Only Caps the Java Heap

You can run a native executable with a max heap:

~~~bash
./orders-service -Xmx256m
~~~

You can also set an initial heap:

~~~bash
./orders-service -Xms64m -Xmx256m
~~~

This limit excludes thread stacks, direct buffers, native library allocations, runtime/GC structures, file mappings, and kernel-accounted memory. Therefore, never set Xmx equal to the entire container limit.

Illustrative example: with a 512 MiB container limit, if you set Xmx512m, the process still needs off-heap memory and may be cgroup OOM-killed before the Java heap reaches max. The heap budget must leave room for everything else plus a safety margin.

### 5.2. Default Heap Configuration Depends on GC and GraalVM Release

Do not copy a single default percentage across all projects. Current GraalVM documentation explains that Serial GC and G1 determine max heap differently; for instance, Serial GC uses defaults based on a fraction of physical RAM, whereas G1 uses MaxRAMPercentage. G1 availability also depends on GraalVM distribution, edition, and platform.

Common options in current documentation:

- Xmx: runtime heap limit.
- Xms: runtime minimum heap.
- R:MaxHeapSize: default max heap configured at image build time.
- MaximumHeapSizePercent: max heap percentage for GC configurations supporting this option.
- MaxRAMPercentage: percentage of RAM used as max heap in configurations supporting this option.

Example setting max heap at build time:

~~~bash
native-image -R:MaxHeapSize=256m ...
~~~

Example overriding at runtime:

~~~bash
./orders-service -Xmx256m
~~~

Option names and GC compatibility should be verified against documentation for your exact GraalVM release. Read the Image configuration section in native build output to see which collector and max heap were actually selected. [GraalVM Memory Management](https://www.graalvm.org/latest/reference-manual/native-image/optimizations-and-performance/MemoryManagement/).

### 5.3. GC Can Temporarily Increase RSS

During collection, the GC may need extra memory for copying, marking, or processing objects. GraalVM notes that RSS can spike temporarily during GC, which matters especially in tightly constrained containers.

Hence, taking a single snapshot right after startup can miss peak memory. Sample during warm-up, high load, GC events, and soak tests. Do not assume post-GC RSS always drops immediately back to pre-collection levels.

### 5.4. Do Not Confuse native-image Builder Memory with Application Memory

The native-image builder itself runs on the JVM and can consume substantial heap/RSS while analyzing, optimizing, and emitting the executable. Build output summarizes build resources, memory per stage, image heap, and code area. This is **build-time memory**, not the deployed service's runtime memory.

If CI hits OOM during nativeCompile/native:compile, investigate builder memory, thread count, and CI limits. If a production container hits OOM, investigate the native executable runtime and container cgroup. [Native Image Build Output](https://www.graalvm.org/latest/reference-manual/native-image/overview/BuildOutput/).

## 6. Collecting Memory Metrics in Spring Boot

### 6.1. Spring Boot Actuator and Micrometer

Spring Boot Actuator can export JVM meters via Micrometer, including memory/buffer pool, GC, and thread utilization info. Meters commonly carry the jvm prefix. Spring Boot also provides application startup metrics:

- application.started.time: time to start the application.
- application.ready.time: time from start until the application is ready to accept requests.

See [Spring Boot Actuator Metrics](https://docs.spring.io/spring-boot/reference/actuator/metrics.html) and verify the actual meters available in your exact Spring Boot/GraalVM version.

Example exposing the metrics endpoint in a benchmark environment:

~~~yaml
management:
  endpoints:
    web:
      exposure:
        include: health,info,metrics,prometheus
~~~

Query available meters:

~~~bash
curl http://localhost:8080/actuator/metrics
curl http://localhost:8080/actuator/metrics/jvm.memory.used
curl "http://localhost:8080/actuator/metrics/jvm.memory.used?tag=area:heap"
~~~

Meter names and tags may vary by version/runtime. Query the listing endpoint first, then select the exact meters present in the application.

### 6.2. Actuator Does Not Replace RSS/Cgroup Measurement

jvm.memory.used describes memory regions exposed by the JVM/Micrometer via memory management APIs. It is not RSS, PSS, or memory.current. Especially with Native Image, do not assume all HotSpot memory pools or JMX metrics carry the same meaning or availability as on the JVM.

Measure separately:

- Actuator/Micrometer: heap, buffer pool, GC, thread, and startup metrics if exposed by the runtime.
- Process: RSS/PSS/peak RSS from the OS.
- Container: cgroup current/peak/limit/events.
- Workload: request rate, latency, error rate, and connection count.

Do not leave public Actuator endpoints exposed solely for benchmarking. Secure metrics endpoints per operational policy and disable or restrict exposure after testing.

## 7. JVM and Native Memory Benchmarking Workflow

A comparison is meaningful only when execution conditions are controlled.

### 7.1. Lock Experimental Conditions

Record:

- Same commit and application functionality.
- Same Spring Boot/Spring Framework and dependency versions.
- JDK/GraalVM distribution and version.
- Same OS, architecture, libc, and container base image when possible.
- Same memory limit, CPU quota, and swap policy.
- Same environment variables, profile, datasource, and external services.
- Same dataset, request mix, concurrency, and run duration.
- Same logging level, metrics exporters, and tracing configuration.

Do not compare an unconstrained JVM process running on a host against a native executable in a 512 MiB container and conclude native saves more memory. Limits and workloads must be equivalent.

### 7.2. Split Sampling into Phases

Measure at least these phases:

1. **Cold start:** start a new process/container; measure RSS and cgroup usage during startup.
2. **Ready/idle:** wait for the readiness endpoint to succeed with no traffic; record heap, RSS, cgroup.
3. **Warm-up:** send steady workload to initialize connection pools, caches, serializers, and code paths.
4. **Steady load:** sustain target load long enough; record time series and percentiles.
5. **Peak load:** ramp concurrency/RPS to design load; record peak RSS/cgroup and GC.
6. **Soak:** sustain load over an extended period to detect gradual upward trends.
7. **Shutdown:** stop the process/container; record duration and verify resource release.

Native Image lacks typical HotSpot JIT warm-up, yet the application still warms up via connection pools, caches, lazy initialization, DNS/TLS sessions, and first-time data loading. You must still separate cold start from steady state.

### 7.3. Select Metrics to Store

| Metric | Cold/Idle | Warm/Steady | Peak/Soak |
| --- | --- | --- | --- |
| Startup-to-ready | Yes | No | No |
| Heap used/committed/max | Yes | Yes | Yes |
| Buffer/off-heap metrics | Yes if exposed by runtime | Yes | Yes |
| RSS and PSS | Yes | Yes | Yes, save peak |
| Cgroup memory.current | Yes | Yes | Yes, save memory.peak |
| memory.events | Baseline | Monitor | Check high, max, oom, oom_kill |
| GC count/time/pause | Baseline | Yes | Yes |
| Thread count | Yes | Yes | Yes |
| RPS, p95/p99 latency, errors | Smoke | Yes | Yes |
| CPU usage/throttling | Yes | Yes | Yes |

Sample at a fixed interval, such as 1–5 seconds depending on load and measurement cost. Keep the same interval for JVM and native. In short benchmarks, sampling too sparsely can miss peaks; in very high-load benchmarks, sampling too densely can add overhead.

### 7.4. Run Docker with Identical Resource Limits

Example running an image with a hard memory limit and CPU quota:

~~~bash
docker run --rm \
  --name orders-native \
  --memory=512m \
  --cpus=1.0 \
  -p 8080:8080 \
  orders-service:native
~~~

Run the JVM image with the same --memory and --cpus, and the same profile/workload. Check docker stats for an overview; when exact reference figures for cgroups are needed, read memory.current, memory.peak, memory.stat, and memory.events from the container's cgroup.

### 7.5. Repeat Multiple Times

Run each variant multiple times from a clean state, alternating JVM/native order if the environment has varying background load. Report median and spread rather than cherry-picking the best run. For peak memory, record each run's maximum and the distribution of peaks across runs.

## 8. Calculating a Heap Budget for Containers

### 8.1. Use a Budget Model

You can draft a conceptual budget:

~~~text
Container limit = runtime heap + native/off-heap + image/code resident + stacks + cache/kernel + other processes + safety margin
~~~

This is not an exact additive formula from raw metrics, because RSS/cgroup accounting can overlap or charge shared pages differently. The model reminds the team that heap is only one component.

### 8.2. Illustrative Example

Suppose a container has a 512 MiB hard limit. Under a representative workload, the team measures:

| Observed Component | Illustrative Value |
| --- | ---: |
| Runtime Java heap resident/used | 150 MiB |
| Native/direct buffers and runtime allocations | 65 MiB |
| Thread stacks and resident code/image pages | 80 MiB |
| Page cache, kernel, and socket accounting | 35 MiB |
| Other processes/helpers in same cgroup | 20 MiB |
| Remaining headroom to limit | 162 MiB |

These numbers are only an example illustrating budget planning, not a quota for Spring Boot Native Image. In practice, some regions may be counted from different angles; use cgroup counters as the reference against the hard limit and process metrics to explain components.

If measured cgroup peak reaches 490 MiB against a 512 MiB limit, the application has almost no headroom for bursts, GC spikes, traffic growth, or dependency changes. Optimize or raise the limit before releasing.

### 8.3. Never Set Max Heap Equal to Container Limit

If the container limit is 512 MiB, Xmx512m allows native/off-heap memory to push total usage past the cgroup limit. Measure the workload and pick a max heap with headroom. Then run stress/soak tests to confirm cgroup peak stays below the hard limit with the agreed margin.

## 9. Diagnosing Memory Growth Patterns

### 9.1. Heap Grows Together with RSS

Possible causes include large object allocations, caches retaining objects, request backlogs, or memory leaks in the object graph. Check:

- Heap used before/after GC.
- Object retention and cache sizes.
- Request concurrency and queue length.
- Number of sessions/connections or per-tenant objects.
- Allocation rate and GC frequency.

If heap used after successive GC cycles climbs steadily over time under constant load, investigate object retention.

### 9.2. Heap Is Stable While RSS Grows

This signals you must inspect outside the heap:

- Growing direct buffers or native allocations.
- Rising thread counts increasing stack memory.
- JNI/native libraries holding memory.
- Increasing memory-mapped files or file-backed pages.
- Allocator retaining freed arenas even after objects are released.
- GC/runtime needing additional temporary memory.

Cross-reference RssAnon, RssFile, Pss, memory.stat, and relevant library metrics. Never declare a memory leak from a single RSS snapshot.

### 9.3. RSS Is Stable While Cgroup Usage Grows

Inspect:

- Page cache or tmpfs.
- Kernel memory, socket buffers, and page tables.
- Helper processes or sidecars in the same cgroup.
- File read/write patterns and logging.
- memory.stat to see whether anon, file, kernel, or sock changed.

If memory.current increases mainly in file, check cache/tmpfs; if kernel or sock grows, inspect connection counts, network buffers, and process activity.

### 9.4. OOM Even Though Heap Never Reached Xmx

The cgroup hard limit may have been hit before Java heap reached max. Check:

- memory.current and memory.peak.
- memory.max.
- memory.events for oom, oom_kill, max.
- Kubernetes lastState.terminated.reason and pod events.
- Process RSS/PSS and other processes in the cgroup.

A process receiving SIGKILL or exit code 137 may be OOM-related, though by itself it does not prove OOM. Cross-check kernel/cgroup/Kubernetes events to confirm.

### 9.5. Heap OOM vs. Cgroup OOM

| Error Type | Common Symptoms | Where to Check |
| --- | --- | --- |
| Java heap OOM | OutOfMemoryError: Java heap space or runtime allocation failure | Heap metrics, GC logs, Xmx, object retention |
| Native allocation failure | JNI/native library allocation fails; process may crash or return errors | Native library logs, RSS/PSS, memory.stat, system logs |
| Cgroup OOM kill | Process killed by kernel when cgroup cannot reclaim under hard limit | memory.events, Docker/Kubernetes state, kernel logs |
| Build-time OOM | native-image builder dies or reports high heap/RSS while compiling | Build logs, builder peak RSS, -J-Xmx, parallelism, and CI limits |

## 10. Common Measurement Mistakes

| Mistake | Why It Misleads | Correct Approach |
| --- | --- | --- |
| Reporting only Xmx | It is a heap cap, not total memory. | Report heap, RSS/PSS, and cgroup usage. |
| Using executable file size as RAM usage | File size does not show which pages are resident. | Measure RSS/PSS once the process runs. |
| Comparing JVM heap with native RSS | Two metrics with different scopes. | Compare identical metric types across both runtimes. |
| Taking RSS at a single point in time | Can miss peaks during GC or peak traffic. | Collect time series and peaks. |
| Running JVM unconstrained and native with cgroup cap | Benchmark conditions are not equivalent. | Apply identical CPU/memory/swap limits. |
| Looking only at docker stats | Obscures heap/off-heap and differs in accounting across platforms. | Combine process metrics with cgroup files. |
| Treating Actuator jvm.memory.used as RSS | The meter reflects memory pool/heap APIs, not process resident set. | Measure RSS/PSS from the OS. |
| Skipping soak tests | Memory leaks or gradual cache growth may not appear yet. | Run long enough under steady load. |
| Omitting GC/runtime versions | Defaults and GC capabilities vary across GraalVM releases/distributions. | Record GraalVM, GC, options, and platform in the report. |
| Mixing build RSS with runtime RSS | native-image builder is a separate process from the service executable. | Report build memory and runtime memory separately. |

## 11. Practice Lab: Measuring Heap, RSS, and Cgroup for the Same Service

**Scenario:** A development team has a Spring Boot service running on the JVM and as a native executable. Both are deployed in containers with a 512 MiB limit. The team wants to determine whether native reduces memory footprint at idle and steady load while ensuring no OOM occurs during peak traffic.

### Tasks

1. Record commit, Spring Boot, JDK/GraalVM, GC, Native Build Tools, OS/architecture, and container base image.
2. Build the JVM artifact and native executable from the same source/configuration.
3. Run both variants in containers with identical --memory, CPU quota, and swap policy.
4. Expose Actuator metrics in the benchmark environment; confirm which heap/buffer/GC meters are actually available.
5. Measure application.started.time/application.ready.time if exposed.
6. Collect RSS/PSS/peak RSS from the Linux process.
7. Collect cgroup memory.current, memory.peak, memory.max, memory.stat, and memory.events.
8. Run identical workloads across cold start, idle, warm-up, steady load, peak load, and soak.
9. Record RPS, p95/p99 latency, errors, GC count/time, and thread count.
10. Compute peak memory and safety margin relative to the container limit.
11. Analyze cases where heap is stable yet RSS/cgroup rises.
12. Rerun after adjusting max heap or GC settings; keep changes only if metrics and latency meet targets.

### Results Log

| Evidence | JVM | Native |
| --- | --- | --- |
| GraalVM/JDK/GC version | Record version | Record version |
| Container memory limit | Record value | Record value |
| Startup-to-ready | Record median and spread | Record median and spread |
| Heap used/committed/max | Record by phase | Record by phase if exposed by runtime |
| RSS/PSS/peak RSS | Record by phase | Record by phase |
| Cgroup current/peak | Record by phase | Record by phase |
| Cgroup memory.events | Record delta | Record delta |
| RPS and p95/p99 | Record by workload | Record by workload |
| GC count/time | Record by workload | Record by workload |
| OOM/restarts | Record events | Record events |
| Safety margin | Relative to limit | Relative to limit |

### Completion Criteria

- [ ] Can distinguish heap, image heap, off-heap, RSS, PSS, and cgroup usage.
- [ ] Can measure Linux process RSS/PSS.
- [ ] Can read cgroup memory current/peak/limit/events.
- [ ] Applied identical workload and resource limits to JVM/native.
- [ ] Collected measurements across idle, steady, peak, and soak.
- [ ] Can distinguish heap OOM from cgroup OOM kill.
- [ ] Can explain scenarios where heap is steady while RSS/cgroup grows.
- [ ] Selected a max heap with headroom for native/off-heap memory.
- [ ] Reported peak memory and safety margin, not just heap used.
- [ ] Saved toolchain/versions and benchmark conditions for reproducibility.

## 12. Self-Assessment Questions

1. Why does Xmx256m not mean the process uses at most 256 MiB of RAM?
2. How does the image heap differ from the runtime Java heap?
3. How does RSS differ from PSS in accounting for shared pages?
4. Why is virtual memory size not a suitable metric for reporting resident RAM?
5. What questions do memory.current, memory.max, memory.peak, and memory.events in cgroup v2 answer?
6. Why can container memory increase while the Java process's RSS remains stable?
7. When heap used is low yet a cgroup OOM occurs, which areas should be inspected?
8. Why can GC cause temporary increases in RSS?
9. How does Spring Boot Actuator jvm.memory.used differ from RSS?
10. Why must peak RSS of the native-image builder be separated from peak RSS of the service runtime?
11. Which conditions must remain identical when benchmarking JVM and native?
12. How do you determine a heap budget with an adequate safety margin under a container limit?

## 13. Official Documentation

GC/heap options and memory figures depend on GraalVM distribution/release, OS, and container runtime. Cross-check against your project's exact versions:

- [GraalVM Native Image — Memory Management](https://www.graalvm.org/latest/reference-manual/native-image/optimizations-and-performance/MemoryManagement/): Java heap, GC, RSS peak, and heap options.
- [GraalVM Native Image — Build Output](https://www.graalvm.org/latest/reference-manual/native-image/overview/BuildOutput/): build resources, peak RSS, image heap, and code area.
- [GraalVM Native Image — Optimize Memory Footprint](https://www.graalvm.org/latest/reference-manual/native-image/guides/optimize-memory-footprint/): measuring and limiting native executable heap.
- [Spring Boot — Actuator Metrics](https://docs.spring.io/spring-boot/reference/actuator/metrics.html): JVM memory/buffer/GC/thread metrics and application startup metrics.
- [Docker Engine — Resource Constraints](https://docs.docker.com/engine/containers/resource_constraints/): hard/soft memory limits, swap, and CPU quota.
- [Linux Kernel — Control Group v2](https://github.com/torvalds/linux/blob/master/Documentation/admin-guide/cgroup-v2.rst): memory.current, memory.max, memory.stat, memory.events, and memory controller.
- [Linux Kernel — The /proc Filesystem](https://www.kernel.org/doc/html/latest/filesystems/proc.html): process mappings, RSS, PSS, and smaps_rollup.
- [Linux man-pages — proc_pid_status(5)](https://www.man7.org/linux/man-pages/man5/proc_pid_status.5.html): VmRSS, VmHWM, RssAnon, RssFile, and RssShmem.

**Key takeaway:** heap describes runtime-managed object memory; RSS/PSS describes resident process pages; cgroup describes memory accounted toward container limits. Only by measuring all three under identical workloads and resource limits can a team accurately evaluate the footprint and OOM risk of Spring Boot Native Image.

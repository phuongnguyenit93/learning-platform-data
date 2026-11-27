# Measuring on Realistic Load Before Changing JVM Parameters in Java 17

## 1. Why shouldn't you tune JVM parameters by guesswork?

When a Java application slows down, uses a lot of RAM, or runs garbage collection (GC) frequently, the instinctive reaction is to increase `-Xmx`, swap garbage collectors, or add multiple `-XX` flags. However, a single JVM parameter affects only part of the system. Raising the heap can lower GC frequency while increasing allowed memory footprint and potentially lengthening pauses. Switching collectors may improve latency for one workload while altering throughput or CPU consumption.

There is no single optimal parameter set for every application. Results depend on:

- Workload type: request/response, batch, streaming, image processing, numeric compute, or background tasks.
- Load distribution: steady, periodic, bursty, peak hours, or multi-tenant.
- Object sizes and lifetimes: many short-lived objects, long-lived objects, large caches, or large arrays.
- CPU, RAM, disk, network, and container limits.
- JDK version, garbage collector, frameworks, native libraries, and deployment configuration.

**Principle:** measure a baseline with a representative workload first, identify an evidence-backed bottleneck, change one targeted factor, and re-measure under comparable conditions. Never change parameters solely because an article, another machine, or a single isolated run looked better.

After this lesson, learners should be able to:

1. Construct test workloads close to realistic traffic.
2. Collect latency, throughput, CPU, heap, GC, thread, and native memory metrics.
3. Use JFR, unified GC logging, JMX, and JDK 17 diagnostic tools.
4. Distinguish heap pressure from off-heap memory pressure or container limits.
5. Determine when to change JVM flags vs. when to fix application code.
6. Design experiments with a baseline, acceptance criteria, repeatability, and a rollback plan.

## 2. What should you measure before tuning the JVM?

A performance report should never contain just one RAM figure or one CPU snapshot. Observe multiple signals simultaneously to understand where the system is constrained.

### 2.1. Latency and throughput

Two core application metric groups:

- **Latency:** time taken to complete an operation or request.
- **Throughput:** operations completed per unit time, such as requests/second or records/second.

Do not report average latency alone. A system with a good average can still deliver a poor experience if a subset of requests is severely slow. Measure:

| Metric | Meaning |
|---|---|
| p50 | 50% of operations finish in this time or faster |
| p90 | 90% of operations finish in this time or faster |
| p95 | 95% of operations finish in this time or faster |
| p99 | 99% of operations finish in this time or faster |
| max | Longest observed duration; sensitive to outliers |
| Throughput | Operations completed over a period of time |
| Error rate | Percentage of failed requests/operations |

Set criteria before running, such as p95 under one threshold, p99 under another, throughput meeting target, and error rate not increasing. Thresholds must come from your system's SLA/SLO or business requirements, not arbitrary universal numbers.

### 2.2. CPU and saturation levels

Monitor:

- CPU utilization of the JVM process and container/host.
- Actual CPU cores allocated.
- Time threads spend running, waiting, blocked, or delayed by the scheduler.
- User/system CPU split and competing processes on the resource.

High CPU can stem from business logic, excessive allocation, GC, serialization, logging, or lock contention. Low CPU combined with high latency often points to I/O waits, locks, exhausted thread pools, or downstream dependencies. You cannot diagnose root cause from CPU percentage alone.

In containers, distinguish host CPU count from the container's CPU quota. Modern JVMs detect container limits, yet deployment configs, quotas, and actual limits still need to be measured and confirmed.

### 2.3. Heap: look beyond Xmx

Information to track:

- Committed heap and used heap.
- Heap occupancy after GC cycles.
- Heap growth over a time window.
- Allocation rate: bytes/objects allocated per second.
- Live set: objects remaining live after GC reclaims unreachable objects.
- Frequency and duration of GC events.

`-Xmx` is the upper limit of the Java heap, not total RAM the JVM process can use. The heap shares the memory budget with metaspace, code cache, thread stacks, direct buffers, JVM native structures, native libraries, and other regions.

If heap rises sharply under load and drops after GC, that can be normal allocation. If post-GC heap climbs steadily across comparable cycles, investigate long-lived objects, caches, listeners, ThreadLocals, or unintended reference retention.

### 2.4. GC: pauses, frequency, and work volume

Do not merely count GC events. Inspect:

- Counts of young/minor collections and old/mixed/full collections.
- Pause duration per type and total stop time.
- Percentage of application time spent paused for GC.
- Heap before and after each cycle.
- Allocation rate and reclamation rate.
- Whether concurrent GC contends for CPU with the application.
- Any abnormal Full GCs, evacuation failures, or allocation failures.

A long GC pause does not automatically mean you must switch collectors. The cause could be an undersized heap, an overly large live set, allocation bursts, large object graphs, insufficient CPU, or unneeded object retention.

### 2.5. Off-heap memory and process resources

If a container hits OOM or RSS climbs while heap stays low, examine:

- Metaspace: class metadata.
- Compressed class space.
- Code cache containing JIT-compiled code.
- Thread stacks: thread count and stack size per thread.
- Direct byte buffers and native memory regions.
- Native/JNI libraries.
- Memory managed by the OS and process mappings.

Different error symptoms:

| Symptom | Area to investigate first |
|---|---|
| `OutOfMemoryError: Java heap space` | Heap, live set, allocation, object retention |
| `OutOfMemoryError: Metaspace` | Loaded class count, class loader leaks, metadata |
| `OutOfMemoryError: Direct buffer memory` | Direct buffers, pools, buffer lifecycle, and direct memory limit |
| `unable to create native thread` | Thread count, PID/thread limits, stack and native memory |
| Container OOMKilled without JVM throwing OOME | Total RSS/container memory, native memory, cgroup limits |

Do not raise `-Xmx` to fix every type of OOM. When the cause is native memory or thread count, increasing the heap can worsen the issue by eating into remaining RAM budget.

## 3. Building a representative workload

Measurement quality depends first on the workload. A tiny benchmark creating a few objects or calling one method in a loop cannot represent a production system with concurrent requests, varied data, and external dependencies.

### 3.1. Derive workload from real behavior

Capture key characteristics:

- Read/write mix, endpoint mix, or job types.
- Request, response, and record sizes.
- Data distributions: hot items, rare items, small/large payloads.
- Cache hit/miss ratios.
- Concurrent connection counts.
- Mix of CPU-bound and I/O-bound work.
- Burst windows, batch windows, and peak hours.
- External dependencies like databases, caches, queues, and HTTP services.

If production telemetry exists, use anonymized or synthetic metrics to shape test workloads. Never copy sensitive data or personal information into test environments without proper justification and controls.

### 3.2. Load tests should include multiple phases

A useful test typically includes:

1. **Warm-up:** start the application, load classes, trigger JIT compilation, and warm caches.
2. **Ramp-up:** gradually increase load to target levels.
3. **Steady state:** hold stable load long enough to observe GC and memory behavior.
4. **Peak/burst:** verify peak handling if production sees bursts.
5. **Soak:** run long enough to expose gradual growth in memory, threads, or resources.
6. **Cool-down:** drop load and observe how resources are released.

Do not treat startup time or the first few seconds as representative of steady-state throughput. JIT, class loading, connection pools, and caches can make initial behavior look quite different.

### 3.3. Use an independent load generator

If the load generator runs on the same machine or container as the measured JVM, it competes for CPU, RAM, network, and I/O. Results can reflect contention between the app and the load tool rather than app capacity.

Whenever possible, run the load generator on a separate machine or container. Sync clocks, document its config, drive defined load profiles, and monitor the generator itself to verify it does not become the bottleneck.

### 3.4. Test both low load and high load

Low load reveals fixed overhead and baseline latency. High load exposes saturation, queueing, GC pressure, and contention. Measuring at only one load level can miss critical behavior.

Do not push load far past every reasonable limit solely to provoke OOM and declare the configuration bad. Separately define normal valid load, expected peak load, and stress-test levels.

## 4. Baseline: recording conditions before making changes

Before tweaking any JVM parameter, save a repeatable baseline.

### 4.1. Record runtime configuration

Collect:

- JDK version and distribution.
- Full launch command and all JVM flags.
- Active GC.
- Min/max heap, container memory limit, and CPU quota.
- OS, kernel, CPU architecture, and allocated cores.
- Application version, frameworks, dependencies, and app config.
- Environment variables affecting the runtime.

Check version with:

~~~bash
java -version
~~~

For a running process, use `jcmd` to inspect flags and VM info:

~~~bash
jcmd <pid> VM.version
jcmd <pid> VM.flags
jcmd <pid> VM.command_line
~~~

`<pid>` is the process ID of the JVM being inspected. Never include secrets from command lines or environment variables in public reports.

### 4.2. Record resource configuration

For example, for a container deployment record:

| Item | Value to record |
|---|---|
| Memory limit | Container RAM limit |
| CPU quota/limit | Actual CPU count or quota |
| JVM heap | `-Xms`, `-Xmx`, or RAM percentage |
| Thread count | Threads at steady state and peak |
| Direct memory | Limit and usage if app uses NIO/direct buffers |
| Replica count | Number of instances sharing infrastructure |
| Load profile | Requests/s, concurrency, payload distribution |

A test on a 16 GB RAM workstation cannot be compared directly to a 2 GB container without accounting for the resource difference.

### 4.3. Save comparable results

Give each test run an experiment ID and store:

- Git commit/build version.
- JVM flags.
- Workload and data seed if applicable.
- Durations of warm-up, ramp-up, steady state, and soak.
- p50/p95/p99, throughput, error rate.
- CPU, heap, GC, threads, native memory.
- Logs, JFR recordings, and notes on anomalies.

Changing multiple variables at once makes it very hard to tell which factor caused the difference.

## 5. Using Java Flight Recorder to observe the application

Java Flight Recorder (JFR) is a JVM and application event recorder built into JDK 17. JFR can capture data on GC, allocations, thread scheduling, lock contention, I/O, class loading, and many other runtime events.

### 5.1. Starting a recording from the command line

You can launch the application with recording enabled:

~~~bash
java -XX:StartFlightRecording=filename=baseline.jfr,settings=profile,dumponexit=true -jar app.jar
~~~

`settings=profile` is a profiling configuration capturing more useful events than the lighter default config. Recording can add overhead and produce larger files; measure its impact in an appropriate environment.

### 5.2. Starting a recording on a running process

For an already-running JVM, use `jcmd`:

~~~bash
jcmd <pid> JFR.start name=baseline settings=profile duration=120s filename=baseline.jfr
~~~

You can check active recordings:

~~~bash
jcmd <pid> JFR.check
~~~

Or dump an active recording:

~~~bash
jcmd <pid> JFR.dump name=baseline filename=baseline.jfr
~~~

Exact commands and options depend on JDK version; run `jcmd <pid> help JFR.start` on your target runtime to inspect supported syntax.

### 5.3. Reading JFR

Open `.jfr` files with a compatible Java Mission Control (JMC). Focus on:

- **Garbage Collections:** timestamps, GC types, pauses, and heap occupancy.
- **Allocation in new TLAB / outside TLAB:** where allocations originate.
- **Object statistics:** which classes create the most objects or occupy the most memory.
- **Thread activity:** threads running, waiting, blocked, or parked.
- **Lock instances/contention:** monitors or locks experiencing contention.
- **Socket/File I/O:** long-running I/O operations.
- **CPU samples:** which call stacks consume the most CPU.

JFR helps you ask sharper questions. For instance, if allocation rate is high, inspect call stacks creating lots of objects; if p99 spikes alongside GC pauses, check correlation between request latency and GC events; if CPU is low while threads are blocked, investigate locks or I/O dependencies.

### 5.4. Avoid enabling every event at high detail indiscriminately

JFR supports multiple profiles and event types. Overly detailed recordings for long durations increase overhead, file size, and analysis noise. Start with a suitable profile, pick a representative window, and enable extra events only to test specific hypotheses.

## 6. GC logging via Unified Logging

Java 9+ uses unified logging. In Java 17, configure GC logs using `-Xlog` rather than legacy GC logging options.

### 6.1. Enabling GC logs

Example:

~~~bash
java -Xlog:gc*,safepoint:file=logs/gc.log:time,uptime,level,tags:filecount=5,filesize=20M -jar app.jar
~~~

Explanation:

- `gc*` logs the GC event group and related tags.
- `safepoint` logs safepoint information.
- `file=logs/gc.log` writes output to a file.
- `time,uptime,level,tags` adds timestamps, uptime, level, and tags.
- `filecount=5` keeps up to five rotated log files.
- `filesize=20M` limits each log file to roughly 20 MB.

The log path must exist or have appropriate write permissions. In containers, plan where logs live and how they are collected to avoid filling the filesystem.

### 6.2. Choosing verbosity

For concise monitoring:

~~~bash
-Xlog:gc:file=logs/gc.log:time,uptime,level,tags
~~~

For deeper investigation, enable specific tags like `gc+heap` or `gc+ergo`. Do not enable higher verbosity than needed everywhere without accounting for I/O and disk costs.

### 6.3. Reading signals in GC logs

Cross-reference:

- GC timestamps against p95/p99 latency.
- Pre/post-collection heap.
- Young collection frequency.
- Presence of old/mixed/full collections.
- Pause times and concurrent phase durations.
- Signs of allocation failure or evacuation failure.

A GC log alone cannot identify which objects retain heap. If you suspect a leak, combine heap dumps, JFR allocation/object statistics, and reference path analysis.

## 7. Using jcmd and JDK diagnostic tools

`jcmd` is a versatile tool for sending diagnostic commands to a JVM. Target the exact PID and matching runtime.

### 7.1. Listing supported commands

~~~bash
jcmd <pid> help
~~~

View help for a specific command:

~~~bash
jcmd <pid> help GC.heap_info
~~~

### 7.2. Heap info

~~~bash
jcmd <pid> GC.heap_info
~~~

Provides an overview of heap and collector state from the runtime. Use it to inspect a point-in-time state; gather multiple samples over time to observe trends.

### 7.3. Thread dumps

~~~bash
jcmd <pid> Thread.print
~~~

Thread dumps reveal blocked threads, deadlocks, exhausted pools, or I/O waits. A single dump is only a snapshot; when investigating deadlocks or lock contention, capture several dumps spaced apart to compare stacks.

### 7.4. Class histogram

~~~bash
jcmd <pid> GC.class_histogram
~~~

A histogram shows instance counts and estimated total bytes per class. This diagnostic command can have noticeable runtime impact depending on heap size and options. Do not run it in a tight loop on production without evaluating impact.

### 7.5. Heap dump

~~~bash
jcmd <pid> GC.heap_dump /path/to/heap.hprof
~~~

Heap dumps help diagnose memory leaks and object retention. They can consume time, disk space, and cause pauses; dump files may contain sensitive object data. Capture only with a proper plan for storage, security, and analysis.

### 7.6. jstat

`jstat` remains a JDK tool for periodic GC statistics:

~~~bash
jstat -gcutil <pid> 1000
~~~

This example samples every 1000 milliseconds. It gives periodic snapshots, not a substitute for GC logs or JFR when investigating root causes and call stacks.

## 8. Native Memory Tracking and off-heap memory

If RSS/container memory is high while Java heap is modest, enable Native Memory Tracking (NMT) to inspect a portion of native allocations managed by HotSpot.

### 8.1. Enabling NMT at JVM startup

~~~bash
java -XX:NativeMemoryTracking=summary -jar app.jar
~~~

Or higher detail:

~~~bash
java -XX:NativeMemoryTracking=detail -jar app.jar
~~~

NMT carries memory and CPU overhead. You cannot fully enable it retroactively on an already-running process launched without this flag.

### 8.2. Viewing the summary

~~~bash
jcmd <pid> VM.native_memory summary
~~~

To capture a baseline and compare:

~~~bash
jcmd <pid> VM.native_memory baseline
jcmd <pid> VM.native_memory summary.diff
~~~

Repeat snapshots across comparable phases to see which category grows. NMT provides information on Java Heap, Class, Thread, Code, GC, Compiler, and other internal categories.

### 8.3. Limitations of NMT

NMT tracks HotSpot native memory allocations within its supported scope; it **is not a complete measurement of every byte of process RSS**. Native allocations from third-party libraries, drivers, or components outside NMT's scope may not be fully captured.

Therefore cross-check:

- NMT.
- Heap usage and GC logs.
- RSS/container memory from the OS or container platform.
- Direct buffer pools and relevant JMX metrics.
- Thread counts, stacks, and native libraries if present.

Never mechanically sum NMT categories expecting exact equality with RSS; shared pages, reserved vs. committed differences, and untracked native regions all affect RSS.

## 9. JMX and runtime metrics

Java Management Extensions (JMX) exposes MBeans to monitor the JVM. Useful MBeans include:

| MBean / group | Metrics to watch |
|---|---|
| `java.lang:type=Memory` | Heap/non-heap usage, pending finalization count |
| `java.lang:type=MemoryPool,name=*` | Per-memory-pool usage |
| `java.lang:type=GarbageCollector,name=*` | Collection count and collection time |
| `java.lang:type=Threading` | Thread count, peak thread count, daemon count |
| `java.lang:type=OperatingSystem` | CPU load and OS information exposed by the JVM |
| `java.nio:type=BufferPool,name=direct` | Direct buffer count, memory used, total capacity |

Verify exact names and attributes against your runtime's MBeans. Inspect them via JConsole, Java Mission Control, or a JMX-integrated metrics pipeline.

### 9.1. Monitoring heap and non-heap

`MemoryMXBean` provides `getHeapMemoryUsage()` and `getNonHeapMemoryUsage()`. These give high-level summaries and do not replace inspecting individual memory pools.

### 9.2. Monitoring collectors

`GarbageCollectorMXBean` provides cumulative collection counts and collection times. Differences between two snapshots estimate GC activity over that window.

Collection time from an MBean does not necessarily equal total wall-clock pause time experienced by users, especially for collectors with concurrent phases. Use GC logs and JFR for detailed pause breakdowns.

### 9.3. Securing management endpoints

Never expose unauthenticated remote JMX to public networks. When enabling remote management, configure authentication, TLS, firewalls, and proper access controls. JMX can expose sensitive information and powerful administrative operations.

## 10. Interpreting results to find bottlenecks

A single metric is rarely enough. Look for relationships across metrics.

### 10.1. Heap grows rapidly, frequent GC, pauses affect latency

Possibilities:

- High allocation rate.
- Heap too small for live set and allocation bursts.
- Many intermediate objects from serialization, mapping, or logging.
- Caches or object graphs retaining too much data.

Investigation steps:

1. Use JFR to inspect allocations by class/call stack.
2. Compare pre/post-GC heap and GC pauses.
3. Determine post-collection live set.
4. If live set is legitimate but heap is tight, try increasing heap within container limits.
5. If objects are retained unintentionally, fix retention before raising heap.

### 10.2. Post-GC heap climbs steadily across comparable cycles

This can signal a memory leak or unbounded cache, though workload shifts and warm-up must be ruled out first.

Investigation steps:

- Run a soak test with steady workload.
- Compare post-GC heap occupancy at comparable intervals.
- Capture two heap dumps to compare dominator trees and retained sizes.
- Inspect static collections, caches, listeners, ThreadLocals, executor queues, and class loaders.

Do not diagnose a leak solely from rising pre-GC heap; short-lived objects may be reclaimed on the next cycle.

### 10.3. Heap is low yet RSS is high

Investigate off-heap/native memory:

- NMT if enabled.
- Direct buffer pool.
- Thread counts and stacks.
- Metaspace/class loading.
- JNI or native libraries.
- Memory mappings and container limits.

Raising `-Xmx` can shrink headroom for these regions. Identify the memory consumer first.

### 10.4. CPU is high yet GC is minimal

The application may be constrained by:

- CPU-intensive algorithms.
- Serialization/compression/encryption.
- Regex or string processing.
- Lock contention and retry loops.
- Excessive logging or data conversions.

Use JFR CPU samples or a profiler to locate hot methods. Tweaking GC flags will not fix an expensive computation loop.

### 10.5. CPU is low yet latency is high

Investigate:

- Blocked/waiting/parked threads.
- Database, HTTP, or file I/O.
- Exhausted connection pools or thread pools.
- Lock contention.
- Queueing and backpressure.
- Inter-service timeouts/retries.

JFR, thread dumps, and dependency metrics are usually far more helpful here than resizing the heap.

### 10.6. GC pauses are short yet p99 stays high

p99 latency may be dominated by requests waiting on I/O, locks, the scheduler, or slow dependencies. Correlate request timestamps with GC events, JFR thread events, and distributed traces. Do not assume every latency spike comes from GC.

## 11. Changing JVM parameters in a controlled way

Test changes only once you have a hypothesis and baseline data. Every change must tie to a measurable goal.

### 11.1. Change one factor at a time

Example:

| Experiment | Change | Hypothesis to test |
|---|---|---|
| A | Increase `-Xmx` within RAM limits | Undersized heap causes overly frequent GC |
| B | Adjust `-Xms` | Heap resize/commit behavior affects startup or latency |
| C | Switch GC | Current collector does not meet latency/throughput target |
| D | Adjust thread stack | High thread count puts pressure on native memory |
| E | Adjust direct memory | App uses direct buffers and hits corresponding limit |

Do not change A, B, C, and D together and try to infer which caused the result. If multiple changes are unavoidable, test them sequentially or use an experiment design that separates effects.

### 11.2. Start with evidence-based heap sizing

`-Xms` sets initial/minimum heap as managed by the JVM; `-Xmx` sets maximum heap limit.

Example:

~~~bash
java -Xms512m -Xmx2g -jar app.jar
~~~

Do not pick these two values solely from host RAM. In containers, the overall budget must still accommodate non-heap, native memory, thread stacks, and any other processes in the container.

You can use `-XX:MaxRAMPercentage` so the JVM calculates the heap limit from available RAM detected by the runtime:

~~~bash
java -XX:MaxRAMPercentage=60 -jar app.jar
~~~

The number 60 is purely illustrative, not a default recommendation. Verify the JVM detects the right container memory limit and preserve enough headroom for off-heap areas. Use `jcmd <pid> VM.flags` and runtime metrics to confirm effective settings.

### 11.3. Never raise heap to mask a memory leak

If live set keeps climbing due to retained references, raising `-Xmx` only delays exhaustion. It may buy temporary breathing room while investigating, yet the real fix must address retention or properly bound caches/queues.

### 11.4. Do not switch collectors without knowing the bottleneck

G1 is a common default on server-class configurations in Java 17. ZGC is a production collector included in JDK 17 and can suit low pause-latency targets; the choice still depends on JDK distribution, setup, heap, and workload.

No collector is universally superior. When testing another collector:

1. Keep workload, resources, and other parameters identical to the baseline.
2. Measure throughput, p95/p99, CPU, GC pauses, and memory overhead.
3. Run long enough through steady state and soak.
4. Verify your distribution/version supports the collector and needed features.

Do not use removed GC flags such as `-XX:+UseConcMarkSweepGC` on Java 17. Do not fall back on PermGen-based tuning; class metadata is now managed in Metaspace.

### 11.5. Be cautious with metaspace, direct memory, and thread stacks

Options like `-XX:MaxMetaspaceSize`, `-XX:MaxDirectMemorySize`, and `-Xss` target different areas. Adjust them only after measuring the relevant area:

- Lowering `-Xss` can shrink per-thread native stack footprint, though too small a stack can trigger `StackOverflowError`.
- Setting metaspace too low can trigger `OutOfMemoryError: Metaspace` when loading many classes or when a class loader leak exists.
- Setting direct memory too low can trigger `OutOfMemoryError: Direct buffer memory`.

Never tweak these options to treat a heap symptom without supporting evidence.

## 12. Containers and memory limits

In containerized environments, understand the distinction between:

- Container memory limit.
- Max heap chosen by the JVM.
- Committed/used heap.
- Non-heap and native memory.
- Process RSS.
- Page cache or memory from other processes in the same container.

JDK 17 supports container awareness on supported platforms, yet you still must verify real cgroup/quota settings and JVM configuration. Setting heap close to the memory limit can cause the OS/container runtime to kill the process before the JVM even has a chance to throw a Java OOME.

### 12.1. Example memory budget

Suppose a container has a 2 GiB limit. Do not allocate the entire 2 GiB to the heap by default. An illustrative budget might reserve:

| Component | Example budget |
|---|---:|
| Max Java heap | 1.2 GiB |
| Metaspace, code cache, and JVM structures | 160 MiB |
| Thread stacks | 180 MiB |
| Direct/native buffers and native libraries | 220 MiB |
| Headroom for bursts and other overhead | Remainder |

This is a budgeting mindset, not a rigid formula. Actual figures must be measured from your process and workload; a Netty application has very different direct memory needs from a simple batch job.

### 12.2. Monitoring cgroups and containers

Combine container/orchestrator platform metrics with JMX/JFR/NMT. Record:

- Memory working set/RSS and limit.
- CPU usage and quota throttling.
- OOMKilled/restart count.
- Heap usage and GC.
- Thread count and native memory.

If the JVM is killed by container OOM, Java logs may contain no OOME stack trace. Inspect events from the container runtime or orchestrator.

## 13. Designing a reliable A/B experiment

A configuration experiment should follow a clear process:

### Step 1: Write a hypothesis

Example: "Current max heap causes G1 to collect too frequently at steady state; increasing heap within container limits will cut GC pressure without pushing RSS over the limit."

A good hypothesis predicts which metrics should improve and which must not regress.

### Step 2: Capture a baseline

Run the representative workload with current settings. Capture p50/p95/p99, throughput, error rate, CPU, heap, GC, and off-heap memory.

### Step 3: Change one parameter

Change only `-Xmx` or the single variable named in the hypothesis. Keep build, dataset, load profile, CPU/memory limits, and all other flags identical.

### Step 4: Repeat measurements

Run matching warm-up and steady-state periods. Execute multiple runs to avoid concluding from an anomalous run. If shared-environment noise appears, document it and rerun.

### Step 5: Compare against criteria

Example table:

| Metric | Baseline | Candidate | Target |
|---|---:|---:|---|
| Throughput | Record value | Record value | No drop beyond threshold |
| p95 latency | Record value | Record value | Within SLO |
| p99 latency | Record value | Record value | Improved or within SLO |
| GC pause time | Record value | Record value | Reduced if hypothesized |
| CPU | Record value | Record value | Within budget |
| RSS | Record value | Record value | Headroom remaining in container |
| Error rate | Record value | Record value | No increase |

Compare distributions, variance, and repeated runs rather than averages alone.

### Step 6: Decide and preserve rollback capability

Keep the change only if targets are met without significant regressions elsewhere. Save old settings, new settings, and test results so you can roll back quickly if needed.

## 14. Common mistakes when benchmarking the JVM

### 14.1. Measuring too briefly

A test lasting only a few seconds may measure only class loading and JIT warm-up. Measure through steady state long enough to observe GC behavior.

### 14.2. Failing to hold workload constant

Comparing two configs across different datasets, concurrency levels, or request mixes cannot support reliable causal conclusions.

### 14.3. Checking only pre-GC heap

High pre-GC heap does not automatically indicate a leak. Watch post-collection occupancy and multi-cycle trends.

### 14.4. Checking only CPU or RAM

Low CPU does not mean the app is healthy; threads may be blocked. Low heap does not mean low RSS; native memory may be growing.

### 14.5. Leaving heavy profiling on during final measurement

Excessive profiling or verbose logging can distort the workload. Use appropriate instrumentation, measure its overhead, and keep observation consistent between baseline and candidate.

### 14.6. Running the load generator on the same host unaccounted for

A load generator competes with the JVM for CPU and RAM. Isolate it or track its resource usage.

### 14.7. Changing multiple flags at once

When throughput shifts, you will not know which flag caused it. Test one variable at a time or use an experiment design capable of attributing effects.

### 14.8. Optimizing one metric at the expense of another

Cutting GC pauses while blowing up CPU or memory may be unacceptable. Optimize against the full SLO and total budget, not a single isolated metric.

### 14.9. Relying on outdated tuning flags

Old articles or scripts may contain deprecated or removed flags. Verify against your exact JDK 17 runtime:

~~~bash
java -XX:+PrintFlagsFinal -version
~~~

And consult JDK 17 documentation. Never copy flags for PermGen, CMS, or unsupported collectors.

## 15. Pre- and post-change checklist

**Before changing:**

- [ ] Workload is representative and repeatable.
- [ ] Baseline latency, throughput, and error rate are recorded.
- [ ] CPU, heap, GC, threads, native memory, and container limits are recorded.
- [ ] Hypothesis targets a specific bottleneck.
- [ ] JDK version, flags, and build version are recorded.
- [ ] Acceptance criteria and rollback thresholds are defined.

**After changing:**

- [ ] Only the intended parameter was changed in the test.
- [ ] Warm-up and steady-state match the baseline.
- [ ] Compared p95/p99, throughput, and error rate.
- [ ] Compared GC, heap, CPU, and RSS/native memory.
- [ ] Ran long enough to observe trends and soak behavior.
- [ ] Recorded results, configuration, and keep/rollback decision.

## 16. Example data collection script on Java 17

A test run can start the application with GC logging and JFR:

~~~bash
java \
  -Xms512m \
  -Xmx1536m \
  -Xlog:gc*,safepoint:file=logs/gc.log:time,uptime,level,tags:filecount=5,filesize=20M \
  -XX:StartFlightRecording=filename=logs/baseline.jfr,settings=profile,dumponexit=true \
  -jar app.jar
~~~

Heap values are purely illustrative. In an actual experiment, use the config under evaluation and keep everything else fixed between baseline and candidate.

During execution, collect application metrics (request rate, latency percentiles, error rate), CPU, and container memory. To inspect the live process:

~~~bash
jcmd <pid> VM.flags
jcmd <pid> GC.heap_info
jcmd <pid> Thread.print
jcmd <pid> JFR.check
~~~

If NMT was enabled at startup:

~~~bash
jcmd <pid> VM.native_memory summary
~~~

After completion:

1. Archive GC logs, JFR recordings, and metric timelines.
2. Mark warm-up, steady-state, peak, and soak windows.
3. Correlate latency spikes with GC, thread, and I/O events.
4. Identify one evidence-backed bottleneck.
5. Propose one small change, re-measure, and compare.

## 17. Practice exercises

### Exercise 1 — Establish a baseline

Pick a Java 17 application. Identify three primary endpoints or jobs, traffic mix, payload sizes, and concurrency level. Build a table recording steady-state p50/p95/p99, throughput, error rate, CPU, heap, and GC.

### Exercise 2 — Distinguish heap pressure from native pressure

A container is OOMKilled while peak heap usage was only half of `-Xmx`. List the areas to check: metaspace, direct buffers, thread stacks, JNI/native libraries, RSS, and cgroup limit. Explain why raising the heap could make the problem worse.

### Exercise 3 — Read GC logs

Enable `-Xlog:gc*` for a steady workload. Record counts of young/mixed/full GCs, pause durations, pre/post-collection heap, and pause time percentage. Compare timestamps against p99 latency.

### Exercise 4 — Use JFR to locate allocations

Capture a steady-state JFR profile. Identify the top three classes or call stacks generating allocations. Propose how to check whether those allocations are necessary, avoidable intermediates, or caches that can be bounded.

### Exercise 5 — Test a single change

Hypothesize that the current heap is too small. Run a baseline, increase `-Xmx` within container limits while holding workload and all other parameters fixed. Compare GC pauses, throughput, p99, CPU, and RSS. Write a keep or rollback decision backed by numbers.

### Exercise 6 — Investigate high p99 with low GC

Use JFR or thread dumps to find blocked/parked threads, lock contention, and slow I/O. Explain why switching garbage collectors might not improve this scenario.

### Exercise 7 — Design a soak test

Run a fixed workload for an extended duration. Compare post-GC heap occupancy, thread count, metaspace, and RSS across intervals. Identify which signals suggest a leak and which heap dump/NMT/JFR artifacts are needed next.

## 18. Completion criteria

Learners complete this lesson when they can:

1. Explain why realistic workloads must be measured before changing JVM flags.
2. Design warm-up, ramp-up, steady-state, peak, and soak tests.
3. Collect latency percentiles, throughput, error rate, CPU, heap, GC, and native memory metrics.
4. Use JFR and unified GC logging in Java 17.
5. Use `jcmd`, `jstat`, JMX, and NMT within their proper scopes.
6. Distinguish the Java heap from total process/container memory and RSS.
7. Recognize when a bottleneck stems from allocation, live set, native memory, threads, I/O, or CPU.
8. Formulate a hypothesis and change one parameter in a controlled test.
9. Compare baseline vs. candidate on identical workloads and acceptance criteria.
10. Avoid legacy tuning flags and maintain rollback capability if changes cause regressions.

## 19. Official documentation

- [Java SE 17 Troubleshooting Guide — JFR](https://docs.oracle.com/en/java/javase/17/troubleshoot/diagnostic-tools.html): diagnostic tools and runtime data capture.
- [Java SE 17 JFR Runtime Guide](https://docs.oracle.com/en/java/javase/17/jfapi/flight-recorder-configurations.html): configuring and using Flight Recorder.
- [Java SE 17 Troubleshooting — GC Logging](https://docs.oracle.com/en/java/javase/17/gctuning/garbage-collector-implementation.html): GC information and log collection mechanisms.
- [Java SE 17 man page — java](https://docs.oracle.com/en/java/javase/17/docs/specs/man/java.html): JVM options and unified logging.
- [Java SE 17 man page — jcmd](https://docs.oracle.com/en/java/javase/17/docs/specs/man/jcmd.html): diagnostic commands.
- [Java SE 17 man page — jstat](https://docs.oracle.com/en/java/javase/17/docs/specs/man/jstat.html): JVM statistics.
- [Java SE 17 Troubleshooting — Native Memory Tracking](https://docs.oracle.com/en/java/javase/17/vm/native-memory-tracking.html): scope and usage of NMT.
- [Java SE 17 Management Extensions Guide](https://docs.oracle.com/en/java/javase/17/management/): JMX and management interfaces.
- [OpenJDK JEP 328 — Flight Recorder](https://openjdk.org/jeps/328): Flight Recorder in the JDK.
**Key takeaway:** JVM tuning is an empirical discipline. Workloads must be representative, baselines must be measurable, and experiments must be controlled. Change parameters only when data points to an applicable bottleneck; evaluate latency, throughput, CPU, heap, GC, and total memory together so improving one metric does not break the rest.

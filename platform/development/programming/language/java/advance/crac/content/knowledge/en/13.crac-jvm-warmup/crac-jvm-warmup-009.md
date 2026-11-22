# Verifying Post-Restore Performance Instead of Inferring From Pre-Checkpoint State

A CRaC checkpoint saves the state of a JVM process at a point in time so the process can be restored faster. However, performance metrics measured before checkpointing only describe conditions at that point in time. After restore, the JVM may run in an environment with different CPU, memory, network, database, cache, and load. The application may also need to refresh resources or warm up certain processing paths again.

Therefore, you should not conclude that the application remains as fast as before the checkpoint merely because the image was created from a warmed-up run. Post-restore performance must be measured again across specific phases, from when the process is restored, when dependencies become ready, until the system reaches a steady serving state.

A useful measurement needs to answer:

- How long does it take the application to move from restore to readiness?
- What is the latency of the first request and the initial requests after restore?
- Do throughput, error rate, and latency percentiles return to expected levels?
- How do CPU, heap, GC, threads, code cache, and RSS change?
- Are caches, database pools, DNS, TLS, and external connections truly ready?
- Is additional warm-up or post-restore configuration tuning needed?

## 1. Why measure again after restore?

CRaC helps restore the checkpointed process state. It does not freeze the entire external environment. Between checkpoint and restore, many conditions can change:

| Factor | What can change after restore |
|---|---|
| CPU and machine architecture | CPU model, allocated core count, CPU quota, frequency, and contention |
| Memory | Memory limit, cgroup pressure, NUMA placement, RSS, and reclaim pressure |
| JIT compiler | Optimization decisions may need to adapt to the current runtime or hardware |
| Heap and GC | Heap occupancy, allocation rate, GC pauses, and fragmentation level |
| Code cache | Compiled code size, compiler state, and recompilation |
| Application cache | Cache still holds data yet may be stale, or need reloading |
| Database | Old connections become invalid, endpoint fails over, or database is overloaded |
| Network and DNS | Addresses, routes, TLS sessions, or network latency change |
| System load | Concurrent requests, traffic patterns, and instances competing for resources |
| Filesystem | Page cache, file mappings, storage latency, and volumes may differ |

A checkpoint image created after warm-up is not a guarantee that every request after restore will have the same latency. Restored heap data can help reduce startup time, yet state dependent on the operating system or external services still needs to be verified and re-established.

### Pre-checkpoint state does not represent post-restore conditions

For example, before checkpointing:

- The JVM has already compiled some hot methods.
- Application caches have already been populated.
- The database pool has several active connections.
- DNS has already been resolved.
- TLS connections have already been established.
- The CPU is idle and no other instances are competing for resources.

After restore:

- The connection pool may need to be recreated.
- DNS may point to a new endpoint.
- Caches may have expired or data may have changed.
- The CPU quota may be lower.
- JIT may continue compiling or adjusting optimizations.
- The first request may trigger class loading, lazy initialization, or code paths that were not executed beforehand.

Therefore, you must separate JVM performance from application and dependency performance. A slow endpoint after restore may be caused by database reconnection or cache misses, not necessarily by JIT or GC.

## 2. Distinguishing post-restore milestones

Do not use a single milestone called "startup time" for every purpose. Record the following timestamps:

1. **Restore started**: the platform starts restoring the image.
2. **Process restored**: the JVM resumes execution after restore.
3. **Resources restored**: required CRaC Resources have finished processing callbacks.
4. **Application ready**: the application can accept traffic according to the readiness policy.
5. **First request completed**: the first request completes.
6. **Warm-up completed**: required processing paths have met the warm-up criteria.
7. **Steady state**: throughput and latency are stable over the selected measurement window.

Different intervals carry different meanings:

| Time metric | Calculation | Meaning |
|---|---|---|
| Restore duration | Process restored - Restore started | Time for the runtime to restore the process |
| Resource recovery duration | Resources restored - Process restored | Time to re-establish resources |
| Time to ready | Application ready - Process restored | Time from when the JVM resumes until accepting traffic |
| First-request latency | First request completed - request received time | Cost of the first request after restore |
| Warm-up duration | Warm-up completed - Application ready | Time to meet warm-up criteria |
| Time to steady state | Steady state - Process restored | Time to reach steady performance |

Use a monotonic clock such as System.nanoTime() to measure durations within the same process. Use Instant or UTC timestamps to record event milestones for correlation across systems. Do not subtract timestamps from two different machines without accounting for clock skew.

## 3. Metrics to monitor

Measuring post-restore performance requires multiple perspectives. A single average latency figure or restore duration is not enough to draw conclusions.

### Latency

Monitor at least:

- P50: 50th-percentile latency, representing a typical request.
- P90/P95: latency across the majority of requests, helping identify tail latency.
- P99: latency of the slowest requests, important for latency-sensitive systems.
- Maximum: used to investigate spikes, should not be used alone as an SLO.
- First-request latency: latency of the first request after readiness opens.

Averages can hide a group of very slow requests. For example, P50 may remain good while P99 spikes sharply because the connection pool creates new connections or JIT compilation occurs during certain requests.

### Throughput and errors

Monitor:

- Requests per second or operations per second.
- Number of concurrent in-flight requests.
- HTTP 5xx rate, timeouts, and business errors.
- Retry rate and retry count.
- Number of connections newly created, closed, or failed.
- Queue depth and queue wait time.

Throughput must be compared under the same incoming load. If a run receives fewer requests, lower throughput is not necessarily a regression. Conversely, higher throughput while error rate rises is not an improvement either.

### CPU and memory

Monitor:

- Container CPU utilization and CPU throttling.
- Heap used, committed, and max.
- Allocation rate and GC count.
- GC pause duration and total GC time.
- Non-heap memory, Metaspace, and Code Cache.
- RSS, container memory, and memory pressure.
- Thread count, thread states, and context switching if available.

Low heap used does not mean the process uses little RAM. RSS can be high due to thread stacks, direct buffers, native memory, mapped files, or other off-heap regions. High CPU utilization can come from JIT compilation, GC, warm-up, request load, or dependency retries.

### Dependencies and caches

Monitor:

- Database pool creation time and connection acquisition time.
- Connection validation failures and SQLState.
- Query latency and timeouts.
- Cache hit ratio, miss ratio, and refresh duration.
- DNS lookup duration and resolution errors.
- TLS handshake duration and handshake errors.
- Message broker reconnect, consumer rejoin, and queue lag.

Measuring dependencies separately helps isolate root causes. If slow requests coincide with database connection retries, increasing heap or changing GC may not solve the problem.

## 4. Collecting JVM metrics after restore

The Java Management API provides MXBeans to read runtime metrics. The values below should be recorded at multiple milestones, such as immediately after restore, after readiness, and after warm-up.

Example:

~~~java
import java.lang.management.GarbageCollectorMXBean;
import java.lang.management.ManagementFactory;
import java.lang.management.MemoryMXBean;
import java.lang.management.MemoryUsage;
import java.lang.management.ThreadMXBean;
import java.util.List;
import java.util.Locale;

public final class JvmMetrics {

    private static final long MIB = 1024L * 1024L;

    private JvmMetrics() {
    }

    public static void print(String phase) {
        MemoryMXBean memory = ManagementFactory.getMemoryMXBean();
        MemoryUsage heap = memory.getHeapMemoryUsage();
        MemoryUsage nonHeap = memory.getNonHeapMemoryUsage();
        ThreadMXBean threads = ManagementFactory.getThreadMXBean();

        System.out.printf(
                Locale.ROOT,
                "phase=%s heap_used_mib=%.1f heap_committed_mib=%.1f heap_max_mib=%.1f%n",
                phase,
                mib(heap.getUsed()),
                mib(heap.getCommitted()),
                mib(heap.getMax())
        );

        System.out.printf(
                Locale.ROOT,
                "phase=%s nonheap_used_mib=%.1f live_threads=%d peak_threads=%d%n",
                phase,
                mib(nonHeap.getUsed()),
                threads.getThreadCount(),
                threads.getPeakThreadCount()
        );

        List<GarbageCollectorMXBean> collectors =
                ManagementFactory.getGarbageCollectorMXBeans();

        for (GarbageCollectorMXBean gc : collectors) {
            System.out.printf(
                    Locale.ROOT,
                    "phase=%s gc=%s count=%d time_ms=%d%n",
                    phase,
                    gc.getName(),
                    gc.getCollectionCount(),
                    gc.getCollectionTime()
            );
        }
    }

    private static double mib(long bytes) {
        return bytes < 0 ? -1.0 : bytes / (double) MIB;
    }
}
~~~

GC counters are cumulative since JVM startup. To compare a specific interval, record two snapshots and calculate the delta for count and time. A negative value may indicate the collector does not provide the metric.

Heap and non-heap in the example are JVM metrics, not RSS. To measure RSS and container memory, use operating system or cgroup tools. Do not substitute committed heap for RSS.

### Monitoring JIT and class loading

JIT compilation and class loading can affect post-restore latency. You can observe:

- Compilation count and compilation time via JMX or JFR.
- Compiler activity and code cache.
- Class loading count and class loading time.
- Deoptimizations or uncommon traps if supported by the JFR/JVM profile.
- CPU increases during the warm-up phase.

Do not assume pre-checkpoint code cache or profiling data guarantees every hot path will maintain the same performance. Optimization assumptions may no longer hold when load, CPU, or dependency states change. Observe actual compiler behavior and latency.

### Using JFR for analysis

Java Flight Recorder (JFR) can collect events on:

- Execution samples and hot methods.
- JIT compilation.
- Garbage collection and pauses.
- Object allocation.
- Thread scheduling and monitor contention.
- Socket/file I/O and various runtime events.

You can start a recording after restore to capture the phase under observation. For example with jcmd:

~~~bash
jcmd <pid> JFR.start name=after-restore settings=profile duration=5m filename=after-restore.jfr
~~~

Check supported options using the JFR help command on the exact JDK. Profile recordings carry overhead; choose an appropriate duration and settings. If comparing against a pre-checkpoint baseline, create recordings with the same settings and under the same load interval. Do not assume a recording running before checkpointing will continue writing to the expected file or at the expected time after restore; verify recordings with JFR.check and start a new recording when needed.

## 5. Designing post-restore measurement windows

A measurement should be divided into windows so resource recovery, warm-up, and steady state are not mixed together.

### Window A - Immediately after restore

Record:

- Time the process resumed.
- Current PID, hostname, and incarnation ID.
- Heap, non-heap, thread count.
- CRaC Resource states.
- Callback durations and recovery errors.

In this phase, the application may not be ready yet. Do not send business traffic solely to measure latency if dependencies have not yet recovered.

### Window B - After dependencies are ready

Once databases, brokers, listeners, and credentials are verified:

- Record time from restore to readiness.
- Record pool creation time and connection count.
- Record initial cache hit ratio.
- Confirm readiness/admission is open.
- Record the first request.

This is when you can measure the actual experience of the first request after restore. Do not skip the first request and report only steady state if deployment goals require good latency immediately after an instance receives traffic.

### Window C - Warm-up

Run predefined warm-up operations:

- Requests representing hot paths.
- Lightweight, controlled database queries.
- Populate required caches.
- Initialize serializers, templates, or lazy structures.
- Trigger processing paths needing JIT compilation.

Warm-up should use data and load close to production, yet keep costs bounded. Do not repeatedly invoke endpoints that cause side effects or write business data solely to warm up the JVM.

### Window D - Steady state

Once warm-up completes, measure over a sufficiently long interval under steady load:

- Throughput.
- P50/P95/P99 latency.
- Error rate.
- CPU, memory, and GC.
- Dependency latency.
- Queue depth and connection pool.

Steady state must be determined by observable criteria, not merely a fixed sleep duration. For example, require throughput and latency to remain within a stable range across several consecutive windows.

## 6. Comparing baselines properly

To evaluate whether CRaC improves startup experience and post-restore performance, proper baselines are needed.

At least three flows should be distinguished:

| Flow | How to run | Purpose |
|---|---|---|
| Fresh start | Start a new JVM from scratch | Standard startup baseline |
| CRaC restore | Restore from checkpoint image | Measure restore time and post-restore performance |
| CRaC restore + warm-up | Restore then run controlled warm-up | Measure performance after the preparation phase |

If pre-checkpoint metrics exist, store them as a historical baseline. Do not use them in place of post-restore measurements.

### Keep comparison conditions equivalent

When comparing, try to keep the following identical:

- Application and dependency versions.
- JDK distribution, version, and JVM flags.
- GC collector, heap size, and container memory limit.
- CPU quota, core count, and machine type.
- Database version, dataset, and cache state.
- Request mix, concurrency, duration, and load rate.
- TLS, DNS, network path, and load balancer.
- Connection pool and warm-up configuration.

If environments differ, record the differences. Do not attribute latency changes to CRaC when CPU quota, database, or incoming load also changed.

### Repeat measurements

Run multiple restores from equivalent images and use multiple fresh starts as a control. Report medians and spread rather than picking only the best run.

If one restore is fast yet other runs show high tail latency, investigate causes such as connection storms, JIT activity, cache misses, or contention. A single run is insufficient to draw conclusions.

## 7. Measuring the first request and tail latency

The first request after restore often behaves differently from steady state. It may trigger:

- Creating new connections.
- DNS lookups and TLS handshakes.
- Lazy initialization in frameworks or libraries.
- Class loading and JIT compilation.
- Cache misses or refreshes.
- Thread or executor initialization.

Record separately:

1. First-request latency.
2. Latency of the initial batch of requests (e.g., 10, 100, or 1,000 requests depending on traffic).
3. P50/P95/P99 during the warm-up phase.
4. P50/P95/P99 after reaching steady state.

If the system has multiple routes, measure each major route group. A lightweight health endpoint does not represent database read/write APIs or CPU-intensive endpoints.

### Do not rely solely on averages

Suppose two versions have the same average latency of 40 ms. Version A has a P99 of 80 ms; version B has a P99 of 600 ms because some requests have to recreate connections. The average fails to show the difference in experience for slow requests.

When setting SLOs, use percentiles suited to service requirements and monitor error rate. Analyze tail latency alongside queueing time, connection acquisition time, and dependency latency.

## 8. Cache and dependency warm-up

CRaC can retain cached data in the heap, yet a cache existing in memory does not mean the cache is still valid.

### Application caches

For each cache, determine:

- Whether data can be retained across checkpoint duration.
- Whether TTL may have expired while the process was paused.
- Whether versions or invalidation signals exist from external systems.
- Whether cache misses cause load spikes on the database.
- Whether a set of popular keys needs to be preloaded.

A cache can be retained if data remains valid and a clear invalidation policy exists. If data may be stale, refresh or clear the cache before opening traffic.

### Database pools

After restore, old connections may be unusable. Measure:

- Pool creation time.
- First connection acquisition time.
- Validation time.
- Connection creation rate.
- Query latency and error rate.

Do not treat a pool object still present on the heap as proof that the pool is ready.

### DNS, TLS, and HTTP clients

Measure DNS lookup, TLS handshake, and new connection establishment times. If a client holds an old connection pool, use lifecycle mechanisms supported by the library to close and recreate or refresh connections. Verify current credentials and certificates.

### Message brokers

After restore, consumers may have to rejoin groups or receive partition reassignments. Measure reconnect duration, rejoin duration, consumer lag, and time until the first message is processed. Verify offsets, acknowledgments, and idempotency to avoid duplicate processing.

## 9. Analyzing GC, heap, and native memory

After restore, heap used may be high because caches were retained. This is not automatically a bug. Examine allocation rate, GC frequency, pause time, and heap occupancy over time.

Some diagnostic patterns:

| Observation | Possibilities to check |
|---|---|
| High yet stable heap used, low GC | Intentionally retained caches or object graphs |
| Heap used growing continuously | Memory leak or unbounded cache |
| GC pauses increase after restore | Allocation burst, heap pressure, or collector behavior |
| High RSS yet low heap | Native memory, thread stacks, direct buffers, mappings |
| CPU rises alongside compilation | JIT is compiling hot paths |
| CPU rises alongside GC | Allocation pressure or heap sizing |
| P99 rises yet CPU is low | Network, database, queueing, or lock contention |

Do not call System.gc() just to make heap numbers look better in benchmarks. Full GC can introduce pauses and alter application behavior. Only experiment with explicit GC when you have a hypothesis and measure both benefits and costs.

If Native Memory Tracking is needed, the JVM must be started with appropriate configuration, for example:

~~~bash
-XX:NativeMemoryTracking=summary
~~~

Afterward, statistics can be viewed with jcmd if supported by the JVM:

~~~bash
jcmd <pid> VM.native_memory summary
~~~

Native Memory Tracking carries overhead and does not cover every allocation from native libraries outside the JVM. Combine NMT figures with RSS and cgroup memory.

## 10. CPU quota, throttling, and runtime environment

An application restored in a container may receive a different CPU quota than the checkpoint creation environment. A low CPU quota slows down JIT compilation, warm-up, GC, and request processing.

Record:

- Number of CPUs visible to the JVM.
- cgroup CPU quota and throttling.
- CPU utilization by container and host.
- Load average or CPU contention level.
- CPU model/architecture if the environment can change.

Do not look only at the core count reported by the JVM. A container may see multiple CPUs yet still be limited by quota. Check cgroup settings and platform throttling metrics.

Similarly, a lower memory limit can cause more frequent GC or result in the process being OOMKilled. Compare RSS, heap, and container memory limit within the same window.

## 11. Automating post-restore measurements

You can create a small tracker that logs lifecycle events and JVM snapshots. The example below uses System.nanoTime() to measure durations within the same process while recording UTC timestamps for log correlation.

~~~java
import java.time.Instant;
import java.util.concurrent.atomic.AtomicLong;

public final class RestoreTimeline {

    private final AtomicLong processStartNanos =
            new AtomicLong(System.nanoTime());
    private final AtomicLong restoreNanos = new AtomicLong();
    private final AtomicLong readyNanos = new AtomicLong();

    public void markRestored() {
        long now = System.nanoTime();
        // Start a new measurement window for this process incarnation.
        processStartNanos.set(now);
        restoreNanos.set(now);
        readyNanos.set(0);
        log("process_restored");
    }

    public void markReady() {
        readyNanos.compareAndSet(0, System.nanoTime());
        log("application_ready");
    }

    public long timeToReadyMillis() {
        long restored = restoreNanos.get();
        long ready = readyNanos.get();
        if (restored == 0 || ready == 0 || ready < restored) {
            return -1;
        }
        return (ready - restored) / 1_000_000;
    }

    private void log(String event) {
        System.out.printf(
                "event=%s timestamp=%s uptime_ms=%d%n",
                event,
                Instant.now(),
                (System.nanoTime() - processStartNanos.get()) / 1_000_000
        );
    }
}
~~~

In a real application, call markRestored() from a callback or appropriate coordination point after the JVM has restored; call markReady() only after listeners and required dependencies are ready. If you need to distinguish individual restore attempts, generate a new ID for the run and attach it to logs.

The example above only measures durations inside the process. Time from when the orchestrator starts restoring until the process runs must be measured at the orchestration layer because Java code is not running yet during that interval.

## 12. Defining warm-up completion criteria

Do not use a fixed sleep such as "wait 30 seconds then open traffic" without supporting data. Warm-up duration depends on:

- Load and request mix.
- Number of hot paths needing activation.
- JIT compilation and class loading.
- Caches and dependencies.
- CPU quota and memory pressure.
- Data size and number of connections to create.

Warm-up criteria can be defined using observable conditions:

- Critical routes have been invoked with representative requests.
- Cache hit ratio reaches an appropriate threshold.
- The database pool has the minimum required number of connections.
- Throughput remains stable across several consecutive measurement windows.
- P95/P99 fall within target bounds.
- Error rate and GC pauses remain within limits.

Warm-up must be idempotent or run only once per incarnation. Do not cause business side effects when issuing warm-up requests. If warm-up may take time, hold readiness or route admission according to deployment policy.

## 13. Investigating post-restore regressions

When post-restore performance is worse than the baseline, proceed from overall metrics down to components:

### Step 1 - Identify scope

- Is only the first request slow, or is the entire steady state slow?
- Are all routes slow, or only routes accessing the database?
- Is only one instance affected, or all instances?
- Does latency rise alongside error rate, CPU, GC, or dependency latency?

### Step 2 - Check dependencies

Measure database connection acquisition, query latency, DNS, TLS, broker reconnect, and cache misses. If dependencies are slow, JVM tuning may not improve requests.

### Step 3 - Check the JVM

Compare heap, allocation, GC pauses, compilation activity, class loading, thread count, and code cache. Use JFR or an appropriate profiler to identify hot paths and contention.

### Step 4 - Check the environment

Cross-check CPU quota, throttling, memory limit, RSS, filesystem, and network. Restoring an image on a machine with fewer resources can produce different results even with unchanged code and JVM flags.

### Step 5 - Make hypothesis-driven adjustments

Change only one group of factors at a time, such as warm-up routes, pool size, or CPU limit. Rerun the same workload and compare latency percentiles, throughput, error rate, and resources.

## 14. Example measurement results table

A report should clearly state the measurement windows and conditions. The table below is an illustrative example, not general recommended thresholds:

| Metric | Fresh start after warm-up | Restore immediately after ready | Restore after warm-up |
|---|---:|---:|---:|
| Time to ready | 18 s | 2.4 s | 2.4 s |
| First request | 210 ms | 340 ms | 95 ms |
| P50 latency | 42 ms | 68 ms | 40 ms |
| P95 latency | 95 ms | 190 ms | 92 ms |
| P99 latency | 180 ms | 510 ms | 175 ms |
| Throughput | 1,000 req/s | 720 req/s | 1,020 req/s |
| Error rate | 0.1% | 1.2% | 0.1% |

In the example, restore shortens time to ready, yet the first request and tail latency remain high. After warm-up, performance returns close to baseline. The results show that fast startup and steady-state performance are two distinct goals; both should be reported.

When compiling an actual report, specify:

- Application/JDK versions and JVM flags.
- CPU, memory limit, and deployment environment.
- Database/cache state.
- Request mix and concurrency.
- Number of iterations.
- Length of each measurement window.
- How percentiles and error rate are calculated.

## 15. Common measurement mistakes

| Unsuitable measurement practice | Why it misleads | Better approach |
|---|---|---|
| Using pre-checkpoint metrics as post-restore results | Environment and dependencies may have changed | Measure fresh snapshots after restore |
| Reporting only restore duration | Does not show time to ready or request latency | Measure each lifecycle milestone |
| Using only average latency | Hides tail latency | Report P50/P95/P99 and error rate |
| Measuring before dependencies are ready | Results mainly reflect recovery failures | Separate resource recovery from workload performance |
| Using different workloads | Cannot compare fairly | Keep request mix and concurrency consistent |
| Measuring only once | Easily skewed by environmental variance | Repeat and report spread |
| Using a fixed sleep to assume warm-up | Does not reflect actual state | Define warm-up criteria with metrics |
| Looking only at heap used | Ignores native memory and RSS | Measure heap, non-heap, RSS, and cgroup |
| Looking only at CPU utilization | Does not distinguish JIT, GC, requests, and retries | Combine JFR with dependency metrics |
| Opening traffic before readiness | Failed requests skew benchmarks and affect users | Keep admission closed until ready |

## 16. Post-restore performance measurement checklist

### Before establishing baselines

- [ ] Record application version, JDK, GC, and JVM flags.
- [ ] Record CPU model/quota, memory limit, and container configuration.
- [ ] Record database, cache, broker, and network states.
- [ ] Define request mix, concurrency, and measurement duration.
- [ ] Define restore, resource-ready, application-ready, and steady-state milestones.

### After restore

- [ ] Generate a new incarnation ID and log current PID/host for diagnostics.
- [ ] Record time to ready and per-CRaC-Resource duration.
- [ ] Send business workload only after readiness permits.
- [ ] Measure the first request and initial batch of requests.
- [ ] Measure P50/P95/P99, throughput, and error rate.
- [ ] Record heap, non-heap, GC, threads, compilation, and code cache if available.
- [ ] Measure RSS, cgroup memory, CPU quota, and throttling.
- [ ] Measure database pool, query latency, cache hit ratio, DNS/TLS, and broker reconnect.
- [ ] Capture JFR during windows needing investigation if required.

### Comparing and improving

- [ ] Have both fresh start and restore baselines.
- [ ] Compare under the same workload and resource conditions.
- [ ] Repeat measurements multiple times.
- [ ] Separate first request, warm-up, and steady state.
- [ ] Identify root causes before changing JVM flags or GC.
- [ ] Re-measure after every change and retain complete metrics.

CRaC can shorten application recovery time, yet post-restore performance must be verified using metrics from that exact run. Measure time to ready, first request, warm-up, and steady state; monitor the JVM, operating system, and dependencies; then compare against baselines under identical conditions. This approach helps separate fast startup benefits from real serving performance and detects regressions caused by JIT, GC, caches, or external environments early.
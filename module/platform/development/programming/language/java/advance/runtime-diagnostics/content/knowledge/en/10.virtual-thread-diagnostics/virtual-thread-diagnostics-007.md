# 10.7 Distinguishing Carrier Starvation, Saturated External Resources, and CPU-Bound Workloads

## Objectives and Nature of the Problem

A service running thousands of **virtual threads** can still suffer rising p95/p99 latency, timeouts, and flat throughput. You must distinguish three situations:

1. **No available carrier:** virtual threads are ready to run but cannot mount onto platform threads in time because the scheduler lacks capacity to make progress or many carriers are held in unmountable blocking calls.
2. **Saturated external resources:** tasks are active and waiting on a connection pool, DB, downstream HTTP service, rate limit, quota, or other resource. Waiting may release the carrier completely; adding more carriers does not lift external limits.
3. **CPU-bound tasks:** computation, serialization, compression, encryption, data processing, or tight loops executing continuously. Virtual threads still require real CPU and do not create extra processor cores.

**Diagnostic requirement:** identify *where tasks are waiting*, *which resource hits its limit*, and *what the CPU is doing*, then verify with a controlled change. Multiple bottlenecks can occur simultaneously; never assign a cause based solely on virtual thread count.

## 1. Mechanics to Understand Before Measuring

A virtual thread (`java.lang.Thread`) is scheduled by the JVM onto **carriers**, which are platform threads. When a JVM-supported blocking operation (such as `Thread.sleep` or many JDK socket I/O calls) causes a virtual thread to **unmount**, the carrier is returned to run another virtual thread. A virtual thread waiting on a connection pool or HTTP response may consume memory or other resources without holding a carrier. Once the task is ready to continue, the scheduler must mount it again.

Separate at least four states:

- **Mounted and running code:** requires a carrier and may consume CPU.
- **Waiting while unmounted:** waiting on a permit, I/O, or timer; the carrier can serve other tasks.
- **Ready-to-run but not yet mounted:** queued waiting for the scheduler; delay here points to carrier/scheduler pressure.
- **Pinned while blocking:** unable to unmount at a specific point, keeping the carrier occupied even though the task is not actively using CPU.

**JDK version changes how pinning is interpreted.** On **JDK 21–23**, blocking while holding a `synchronized` monitor can pin the carrier; native/foreign calls can also pin. Starting in **JDK 24**, JEP 491 eliminates pinning *caused by `synchronized`*; certain native/VM paths can still pin. Consequently, a stack containing `synchronized` does not prove pinning on JDK 24+. Scheduler parallelism typically defaults to the number of CPUs visible to the JVM, but **this is not a cap on total virtual threads**. Virtual threads suit many I/O-waiting tasks; they do not make individual computations run faster.

## 2. Table Distinguishing the Three Bottlenecks

| Observation Data | Carrier Shortage / Held Carriers | External Resource Saturation | CPU-Bound |
| --- | --- | --- | --- |
| Process CPU | Can be low when carriers are pinned and waiting, or high if carriers run long CPU code | Typically low/moderate while waiting on DB/HTTP; can rise if retries/serialization accompany it | Typically near the granted CPU quota, with CPU samples concentrated in hot code |
| Growing queues | Virtual threads are ready yet waiting on the scheduler/carrier | Pool pending, permit waiters, DB queues, HTTP queues, rate limits | CPU work contends for CPU; requests wait for compute steps to finish |
| JFR/dumps | Long/repeated `jdk.VirtualThreadPinned` if pinned; growing ready queue, little progress | Stacks waiting on permits/JDBC/HTTP, pool `active=max`, high downstream p95, 429/503 | Dense `jdk.ExecutionSample` in algorithms, high actual compute time |
| Verification | Remove the pinning site or check JDK behavior; re-measure ready→run latency | Throttle admission or adjust pool/downstream capacity with justification | Reduce CPU concurrency/optimize, test against corresponding core limits |
| Remediation | Avoid carrier-holding blocking, shorten critical sections, fix native paths | Backpressure, timeouts, concurrency limits, optimize DB/target services | Optimize workload, bound parallel CPU work, scale resources when needed |

These are **correlation patterns**, not a single-metric deduction formula. Low CPU + high p99 can come from a slow DB, monitor contention, or pinned carriers; follow up with metrics at the exact wait point. High CPU can also come from GC or retries rather than business algorithms.

## 3. Evidence-Based Investigation Workflow

### Step 1 — Establish a Baseline

Record the **JDK/build**, CPUs visible to the JVM, container/CPU quota, memory/GC, arrival rate, throughput, in-flight count, timeouts/errors, and p50/p95/p99. Compare comparable load windows before and after degradation. Do not look at virtual thread counts and try to calculate required carriers.

Instrument timing at step boundaries:

- `T_wait_to_start`: from task submission until execution actually starts or resumes (if instrumented by the app).
- `T_wait_pool`: from requesting a permit/connection until it is granted.
- `T_downstream`: duration holding the connection and executing JDBC/HTTP.
- `T_cpu`: application computation portion (requires a CPU profiler/CPU-time to estimate), plus other components.

For sequential requests, you can picture: `T_total ≈ T_wait_to_start + T_wait_pool + T_downstream + T_cpu + T_other`. With parallel or nested spans, avoid double counting. By Little's law in steady state, `L ≈ λ × W`: longer wait times increase in-flight requests; **many existing virtual threads do not prove a carrier shortage**.

### Step 2 — Inspect CPU and Queues Together

1. **CPU near quota** and profiler shows continuous application computation → investigate **CPU-bound** first. Distinguish CPU from business logic, GC, encode/decode, retries, and lock spinning.
2. **CPU has headroom**, pool `active=max`, `pending>0`, acquire time or downstream p95 rising → points toward **external saturation**. Virtual threads waiting on a pool generally do not hold carriers.
3. **CPU has headroom**, pools/downstreams are not full, yet ready virtual threads wait a long time, with prolonged pinning events/traces or scheduler queue backlog → points toward a **carrier/scheduler bottleneck**.
4. **Both CPU and pool pending are high** → could be both. Use per-span timings and a load sweep to find which limit hits first, changing one factor at a time.

100% CPU in a tool can mean **one core**, not 100% of the entire CPU quota. A `RUNNABLE`/`WAITING` state alone does not tell you whether a task occupies a carrier or has unmounted.

### Step 3 — Collect Dumps, JFR, and Downstream Metrics

Use `jcmd` from the exact target JVM/JDK; `<PID>` is a placeholder replaced by the actual PID:

~~~bash
jcmd <PID> Thread.dump_to_file -format=json vthreads.json
jcmd <PID> Thread.dump_to_file -format=text vthreads.txt
~~~

These commands target JDK 21+ and reveal virtual threads that legacy thread dumps can miss. Capture several snapshots spaced apart while the issue reproduces; look for repeated stacks, where tasks are waiting, and progress over time. Depending on the JDK, dumps lack complete lock/JNI metadata and do not represent an absolute atomic snapshot of the entire JVM.

Start JFR during an anomalous load window:

~~~bash
jcmd <PID> JFR.start name=vt-triage settings=profile duration=60s filename=vt-triage.jfr
jfr print --events jdk.VirtualThreadPinned,jdk.VirtualThreadSubmitFailed vt-triage.jfr
~~~

Read the file only after the recording completes (or after a manual dump). Open it in JDK Mission Control to analyze `jdk.ExecutionSample`, pinning/blocking events, hot methods, and timestamps when latency climbed. On **JDK 21**, `jdk.VirtualThreadPinned` is typically enabled by default with a **20 ms** threshold. Zero events **does not mean** the scheduler is healthy: operations may fall below the threshold, belong to an unrecorded pin type, be disabled in settings, or stem from another bottleneck. `VirtualThreadSubmitFailed` indicates submit/unpark failures, not total queue depth.

**Version-specific diagnostics:**

- **JDK 21–23:** you can start with `-Djdk.tracePinnedThreads=full` to print stacks when virtual threads block while pinned. Use only when needed in appropriate test/diagnostic scopes.
- **JDK 24+:** `jdk.management.VirtualThreadSchedulerMXBean` exposes `getParallelism()`, `getPoolSize()`, `getMountedVirtualThreadCount()`, and `getQueuedVirtualThreadCount()`. These counts are estimates; observe trends as load rises rather than treating one sample as conclusive. This interface **does not exist in Java 21**. Some newer JDKs provide `jcmd <PID> Thread.vthread_scheduler`; verify with `jcmd <PID> help` on your running version.
- On every JDK: simultaneously measure **pool idle/active/pending/acquire-timeout**, DB query duration/slow queries, HTTP duration/status/rate limits, CPU samples, and GC. An unobstructed scheduler does not prove downstream dependencies are unobstructed.

## 4. Analyzing Three Classic Incidents

### A. Pinned Carriers on JDK 21

A service has many virtual threads running `synchronized(lock) { blockingCall(); }` on a hot path, each waiting hundreds of milliseconds. Process CPU is not saturated, yet other ready tasks progress slowly; JFR shows many long `jdk.VirtualThreadPinned` events with stacks at the blocking call under the monitor. **Well-supported conclusion:** carriers are being held when virtual threads ought to yield them.

Remediation on JDK 21: move I/O/blocking outside the locked region if correctness holds, shrink the locked section, or use `ReentrantLock` properly when synchronization must span an unmount point. **Do not** replace every `synchronized`: short non-blocking critical sections are rarely bottlenecks. When moving to JDK 24+, monitor-related pinning behavior changes; re-measure rather than extrapolating from JDK 21 symptoms. Native/VM calls still need separate checking.

### B. Saturated Connection Pool or Remote Service

An application has **10 DB connections**. Each request holds a connection for **250 ms** on average. If every transaction uses one connection and no other limit applies, the approximate ceiling is **10 / 0.25 = 40 transactions/second**. 10,000 virtual threads will not raise that ceiling to 400/s. At 120 requests/s, `active=10`, pool pending and acquire time climb, and requests time out; application CPU can stay low because waiting virtual threads unmounted.

Verify with pool metrics, DB query latency, locks, quotas, transaction duration, and completed request counts. Fix by shortening connection hold time, optimizing queries/transactions, bounding concurrency, setting timeouts, and applying backpressure. **Increase pool size only** if the DB can truly absorb more load; a larger pool can slow the DB down further. For HTTP 429 responses, reduce request rate, enforce rate limits, and apply backoff instead of pumping more requests.

### C. Truly CPU-Bound Workload

You have **4 effective vCPUs**, yet 500 virtual threads simultaneously compress or encrypt data. The profiler shows CPU time concentrated in the algorithm, the process hits nearly its entire quota, and throughput barely grows from 50 to 500 concurrent tasks; p99 may worsen from CPU contention. **Conclusion:** CPU bottleneck. Virtual threads do not time-slice long CPU computations to create extra processing capacity.

Prioritize reducing work per request, profiling/optimizing hot paths, adding verified caching/batching, capping concurrent CPU tasks near real CPU capacity, or provisioning more CPU. If a flow both awaits a DB and parses large JSON, measure the **two phases** independently; the bottleneck can shift after fixing the DB.

## 5. Java 21+ Lab: Comparing the Three Modes

Run the same 12 virtual threads across three workload modes. `external` simulates a downstream with only 2 active slots via `Semaphore`; `Thread.sleep` represents an I/O wait without calling a real DB. `cpu` busy-computes for roughly 250 ms/task. `pin21` holds 12 **distinct** monitors while sleeping to illustrate JDK 21-style pinning without conflating it with contention on a shared lock. All timings are empirical; there is no fixed deterministic stdout timing.

Create the file **`VirtualThreadBottleneckLab.java`**:

~~~java
import java.util.ArrayList;
import java.util.List;
import java.util.concurrent.Executors;
import java.util.concurrent.Future;
import java.util.concurrent.Semaphore;
import java.util.concurrent.TimeUnit;
import java.util.concurrent.atomic.AtomicInteger;
import java.util.concurrent.atomic.AtomicLong;

public class VirtualThreadBottleneckLab {
    private static final int TASKS = 12;
    private static final int DURATION_MS = 250;
    private static final Semaphore EXTERNAL_SLOTS = new Semaphore(2);
    private static final AtomicInteger IN_EXTERNAL = new AtomicInteger();
    private static final AtomicInteger PEAK_EXTERNAL = new AtomicInteger();
    private static final AtomicLong PERMIT_WAIT_NS = new AtomicLong();
    private static final Object[] LOCKS = new Object[TASKS];
    private static volatile long resultSink;

    static {
        for (int i = 0; i < TASKS; i++) {
            LOCKS[i] = new Object();
        }
    }

    public static void main(String[] args) throws Exception {
        if (args.length != 1 ||
                !(args[0].equals("external") ||
                  args[0].equals("cpu") ||
                  args[0].equals("pin21"))) {
            System.out.println(
                    "Usage: java VirtualThreadBottleneckLab external|cpu|pin21");
            return;
        }

        String mode = args[0];
        long start = System.nanoTime();

        try (var executor = Executors.newVirtualThreadPerTaskExecutor()) {
            List<Future<?>> tasks = new ArrayList<>();
            for (int id = 0; id < TASKS; id++) {
                final int taskId = id;
                tasks.add(executor.submit(() -> {
                    switch (mode) {
                        case "external" -> externalWait();
                        case "cpu" -> compute();
                        case "pin21" -> pinOnJdk21(taskId);
                        default -> throw new IllegalArgumentException(mode);
                    }
                    return null;
                }));
            }
            for (Future<?> task : tasks) {
                task.get();
            }
        }

        long elapsedMs = TimeUnit.NANOSECONDS.toMillis(
                System.nanoTime() - start);
        long avgPermitWaitMs = TimeUnit.NANOSECONDS.toMillis(
                PERMIT_WAIT_NS.get() / TASKS);
        System.out.printf(
                "mode=%s tasks=%d elapsedMs=%d peakExternal=%d avgPermitWaitMs=%d%n",
                mode, TASKS, elapsedMs, PEAK_EXTERNAL.get(), avgPermitWaitMs);
    }

    private static void externalWait() throws InterruptedException {
        long startWait = System.nanoTime();
        EXTERNAL_SLOTS.acquire();
        PERMIT_WAIT_NS.addAndGet(System.nanoTime() - startWait);
        try {
            int current = IN_EXTERNAL.incrementAndGet();
            PEAK_EXTERNAL.accumulateAndGet(current, Math::max);
            try {
                Thread.sleep(DURATION_MS);
            } finally {
                IN_EXTERNAL.decrementAndGet();
            }
        } finally {
            EXTERNAL_SLOTS.release();
        }
    }

    private static void compute() {
        long deadline = System.nanoTime()
                + TimeUnit.MILLISECONDS.toNanos(DURATION_MS);
        long v = 0x9E3779B97F4A7C15L;
        while (System.nanoTime() < deadline) {
            v ^= v << 13;
            v ^= v >>> 7;
            v ^= v << 17;
        }
        resultSink = v;
    }

    private static void pinOnJdk21(int id)
            throws InterruptedException {
        // Dedicated lock per task to avoid artificial monitor contention.
        synchronized (LOCKS[id]) {
            Thread.sleep(DURATION_MS);
        }
    }
}
~~~

Compile and run with **Java 21 or later**:

~~~bash
javac VirtualThreadBottleneckLab.java
java -Djdk.virtualThreadScheduler.parallelism=2 VirtualThreadBottleneckLab external
java -Djdk.virtualThreadScheduler.parallelism=2 VirtualThreadBottleneckLab cpu
java -Djdk.virtualThreadScheduler.parallelism=2 VirtualThreadBottleneckLab pin21
~~~

Stdout follows `mode=... tasks=12 elapsedMs=... peakExternal=... avgPermitWaitMs=...`; **`elapsedMs` and `avgPermitWaitMs` vary across runs**. How to read the output:

- `external`: `peakExternal` is at most **2**, and permit wait rises as slots stay busy. With 12 tasks × 250 ms / 2 slots, elapsed time is typically near **1.5 seconds** plus overhead, even though most time is spent waiting and carriers remain free.
- `cpu`: `peakExternal=0`, `avgPermitWaitMs=0`. Actual CPU capacity of the JVM/container governs effective parallelism; setting scheduler parallelism=2 here is strictly for simulation, **not a production tuning recommendation**.
- `pin21`: on **JDK 21–23**, `Thread.sleep` inside `synchronized` can hold the carrier and lengthen total runtime when only two carriers are available; JFR pinning events may appear. On **JDK 24+**, `synchronized` no longer causes this type of pinning, so the same program can finish close to a single sleep duration. Both `peakExternal` and permit wait are 0 in this mode.

This is an illustrative lab: the semaphore **simulates** an external resource, `Thread.sleep` **simulates** latency, and the CPU busy loop is no substitute for a proper benchmark. Do not use `pin21` to generate load in production; do not conclude that raising `jdk.virtualThreadScheduler.parallelism` is the universal fix.

## 6. Deciding the Fix and Re-Measuring

| Confirmed Diagnosis | Direct Action | Post-Fix Criteria |
| --- | --- | --- |
| Carriers held in prolonged pinning | Move blocking out of monitors (especially JDK 21), pick appropriate locks, replace/limit pinning native calls, evaluate JDK upgrade | Pinned duration/count drops, ready queue drains, throughput and p99 improve under the same load |
| Saturated external pool/downstream | Reduce hold time, optimize queries, cap concurrency, add backpressure and timeouts, size downstream capacity appropriately | Pool pending/acquire time drops, 429/5xx do not climb, p99/errors drop |
| CPU-bound | Profile code, reduce per-request work, bound concurrent CPU tasks, add CPU if needed | CPU time/request falls or CPU capacity suffices; throughput rises without degrading p99/GC |

Test at **baseline → near-threshold → above-threshold load**, changing **one factor at a time**, while recording throughput, p50/p95/p99, errors, CPU/GC, scheduler queues, pool queues, and downstream durations. Removing one bottleneck often exposes the next; keep observing the full pipeline.

## 7. Common Reasoning Errors

1. **"20,000 virtual threads require 20,000 carriers."** Waiting virtual threads can unmount; live virtual thread count is not the number of carriers needed concurrently.
2. **"Low CPU proves carriers are pinned."** Slow DB queries, pool queues, HTTP timeouts, and locks also leave CPU low. Scheduler/pinning evidence is required.
3. **"No `jdk.VirtualThreadPinned` means carriers cannot be bottlenecked."** The event has a threshold and narrow scope; CPU hogs and other scheduler issues do not necessarily emit it.
4. **"Increasing virtual threads, pool size, or scheduler parallelism always increases throughput."** It changes neither downstream capacity nor core count; larger backlogs can worsen p99.
5. **"Every `synchronized` pins."** Check whether blocking happens inside and check the JDK version; JDK 24 eliminates monitor-related pinning.
6. **"A single thread dump is conclusive."** You need multiple snapshots plus JFR/metric time series; isolated WAITING/RUNNABLE states easily mislead.
7. **"Increasing the connection pool fixes a slow DB."** An overloaded DB can slow down further under extra concurrent transactions and lock contention. Expand only after verifying DB capacity.
8. **"Virtual threads suit long CPU jobs."** Virtual threads mainly scale I/O-bound workloads; CPU jobs still require concurrency bounds matched to the CPU budget.

## 8. Field Checklist

- [ ] Recorded JDK build, CPU quota/effective cores, generated load, and incident time window.
- [ ] Collected requests/s, in-flight count, p50/p95/p99, errors/timeouts, and process CPU/GC.
- [ ] Measured pool/permit wait time, connection hold time, and downstream latency/errors.
- [ ] Captured dumps containing virtual threads and JDK-compatible JFR CPU samples/pinning data.
- [ ] Separated **ready waiting for carrier**, **unmounted waiting for resource**, and **mounted burning CPU**.
- [ ] Confirmed the hypothesis by changing a single limit under identical load while watching p99 and errors.
- [ ] Checked for secondary bottlenecks after resolving the primary bottleneck.

### Official References

- Oracle Java 21 — Virtual Threads: https://docs.oracle.com/en/java/javase/21/core/virtual-threads.html
- OpenJDK JEP 444 — Virtual Threads: https://openjdk.org/jeps/444
- OpenJDK JEP 491 — Synchronize Virtual Threads without Pinning: https://openjdk.org/jeps/491
- JDK 24 `VirtualThreadSchedulerMXBean`: https://docs.oracle.com/en/java/javase/24/docs/api/jdk.management/jdk/management/VirtualThreadSchedulerMXBean.html

**Concluding principle:** pinpoint where tasks wait, identify the real resource bound, and run a confirming experiment; high virtual thread counts or high latency are symptoms, not root-cause names.
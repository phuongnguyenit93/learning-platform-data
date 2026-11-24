# 2.3. Distinguishing Elapsed Time, CPU Time, and Waiting Time

A Java call taking 2 seconds does not mean the CPU spent 2 seconds processing it. Conversely, a process consuming 3 seconds of CPU in 1 real second is completely possible when multiple threads run in parallel. To diagnose performance, you must specify **what time is being measured, for which subject, and from which point to which point**, before blaming CPU, locks, I/O, or external systems.

This lesson belongs to **2. Measurement Methodology**. Three concepts to distinguish:

- **Elapsed time / wall-clock duration:** the real-time length between two events, including both active execution and waiting.
- **CPU time:** total CPU duration executing one thread or the threads of a process, depending on the measured scope.
- **Waiting time:** duration a unit of work or thread waits for a specific condition such as a queue, lock, I/O, response from another service, or CPU scheduling. **No single Java metric covers all kinds of waiting.**

The goal is to read numbers for what they actually are, pick the right Java 17+ APIs, calculate properly on multi-core hosts, understand thread state limitations, and know when each waiting segment must be measured separately.

## 1. Metrics Answer Different Questions

| Quantity | Question | Typical Scope | Cannot Be Inferred Directly |
| --- | --- | --- | --- |
| **Elapsed** | How long did the user/task wait from start to end? | Request, operation, method, observation window | How much CPU was consumed |
| **Thread CPU** | How much CPU time did this thread actually use? | One platform thread over a defined interval | Full async request time or total process CPU |
| **Process CPU** | How much total CPU did all JVM threads consume? | One JVM/process over a window | Per-request latency or CPU of one specific thread |
| **Queue wait** | How long did work sit waiting to be processed? | From enqueue to dequeue/start | Worker processing time after dequeue |
| **Lock/I/O/dependency wait** | How long was work held at a specific operation? | Monitor, lock, DB/HTTP, socket, filesystem | The entire difference between elapsed and CPU |

**Example with one sequential thread:** an operation has 1,000 ms elapsed and 120 ms thread CPU. There are roughly 880 ms during which the thread **did not consume CPU** in that window. That interval can include I/O wait, lock wait, sleep, preemption, safepoint/GC, and scheduler delays. **Do not call 880 ms "waiting on database"** without measuring the database separately.

**Example with multiple cores:** four threads run during the same 1 second, each using 700 ms CPU. Total CPU across the four threads is **2,800 ms**, while the window elapsed time remains **1,000 ms**. Subtracting 1,000 − 2,800 to compute waiting time is completely meaningless because CPU is summed across multiple threads.

**Example with a queue:** a request sits in a queue for 450 ms, then a worker spends 50 ms of CPU. End-to-end elapsed is at least ~500 ms; measuring CPU on the worker after it picks up the request cannot see the 450 ms waited beforehand.

## 2. Elapsed: Duration Clocks vs. Wall-Clock Timestamps

Within the same JVM, **System.nanoTime()** is suitable for measuring elapsed intervals:

~~~java
long startNanos = System.nanoTime();
// Actual work is placed here when applying the measurement.
long elapsedNanos = System.nanoTime() - startNanos;
double elapsedMillis = elapsedNanos / 1_000_000.0;
~~~

The snippet above is an **illustrative pattern showing how to bracket a measurement**, not a complete program. `System.nanoTime()` returns nanoseconds from an arbitrary JVM/environment origin, useful for taking **differences**, not calendar timestamps. The nanosecond unit does not guarantee nanosecond accuracy or resolution. Measured elapsed time includes time the thread slept, waited for I/O, was paused, contended for CPU, or hit GC/safepoints if they occurred between the two readings.

Conversely, **System.currentTimeMillis()** and **Instant.now()** are suited for marking **when** an event occurred in logs/traces. The system clock can be adjusted by NTP or an administrator, so subtracting two calendar timestamps can be unreliable for short durations. When aligning timelines across JVMs, containers, and services, store timestamps with timezones; when measuring duration inside one JVM, use a monotonic source.

You must specify the measurement boundary:
- **Client elapsed** can include network, DNS/TLS, gateway, retries, queues, server, and downstream calls.
- **Controller/endpoint elapsed** only covers the segment inside that instrumented layer, and may miss time the request waited before dispatch.
- **Method elapsed** is strictly the start/end of the instrumented method.
- **Trace span elapsed** is the span's duration; spans executing in parallel overlap and must not be summed into sequential total elapsed time.

Even when measured accurately, handler duration and client-observed duration can differ substantially with no tooling bug at all.

## 3. CPU Time: Specify Thread or Process

### 3.1. CPU Time of a Single Platform Thread

Java provides **java.lang.management.ThreadMXBean**:

- `isCurrentThreadCpuTimeSupported()`: whether the JVM supports measuring CPU time of the current thread.
- `isThreadCpuTimeEnabled()` and `setThreadCpuTimeEnabled(true)`: check and request enabling tracking if supported and permitted.
- `getCurrentThreadCpuTime()`: total CPU nanoseconds for the current thread; may return `-1` if unavailable.
- `getCurrentThreadUserTime()`: the user-mode portion of CPU time, distinct from total CPU time which also includes system-mode time.

Taking the difference of two samples **on the same thread** near the start and end of work gives `threadCpuDelta`. Intervals where the thread is not executing on CPU—such as `Thread.sleep`, waiting on a monitor, or waiting on I/O—normally do not advance this counter correspondingly.

**Approximate relationship for the same thread and same measurement interval:**

~~~text
elapsed ~= on-CPU time of the thread + off-CPU time of the thread
off-CPU ~= elapsed - threadCPU
~~~

The `~=` emphasizes differences in resolution, OS/JVM accounting, and counter read cost. **Off-CPU does not mean I/O wait**: it also includes monitor waits, sleep, parking, scheduler wait, CPU quota throttling, GC/safepoints, etc.

CPU time measures CPU consumption, **not instruction count or useful progress**. A buggy loop can burn CPU continuously without completing requests; conversely, a thread waiting on a remote result has low CPU but large elapsed time.

### 3.2. CPU Time of the Entire Process

A JVM has application workers, GC threads, JIT compilers, system threads, and potentially many concurrent tasks. **Process CPU** sums CPU consumed across threads, so it **can exceed elapsed time** on multi-core machines.

One interpretation formula:

~~~text
average logical CPU cores used ≈ delta(process CPU seconds) / delta(elapsed seconds)
~~~

If a process consumes 2.4 CPU seconds in 1 real second, it used an average of roughly **2.4 logical cores**. This metric may be displayed as 240% when normalized to one core; to interpret "% of allocated capacity", you must consider the actual CPUs/quota available to the process/container.

Java 17 has `ProcessHandle.current().info().totalCpuDuration()` returning `Optional<Duration>`: if the OS supports it, take **two snapshots of the same process** and compute the difference. OS/container tools also provide process CPU, CPU quota, and throttling; cross-check these layers when CPU limits are suspected. Cumulative process CPU since startup cannot be directly compared against the elapsed time of a single request.

### 3.3. Do Not Assume "Request CPU = Worker CPU"

In synchronous processing, if one request runs end-to-end on the same thread and the thread does not interleave other work, the thread's CPU delta over the bracketed interval can represent that segment's CPU reasonably well.

However, an async/reactive request may hop across multiple executors, callbacks, or threads. CPU time read from the request-receiving thread is only a fragment, while that same thread may go on to process other requests. Attributing CPU per request requires context-aware tracing/profiling, not subtracting request elapsed from total process CPU. For virtual threads on JDKs newer than Java 17, check your measurement tooling because per-thread CPU counters may not represent individual virtual threads the way users assume by default.

## 4. "Waiting Time" Has Many Types and Many Boundaries

| Wait Type | Useful Measurement Boundary | Evidence Source |
| --- | --- | --- |
| **Queue wait** | enqueue → worker start | Queue timestamps, age, wait histograms |
| **Monitor wait** | request to enter `synchronized` → monitor ownership acquired | Thread dumps, Java monitor contention, JFR |
| **Lock/condition/park wait** | acquire/park start → acquired/unparked | Lock instrumentation, JFR park events, multiple thread dumps |
| **I/O/DB/HTTP wait** | call start → response received/finished | Trace spans, JDBC/HTTP metrics, JFR I/O, timeouts |
| **CPU scheduler wait** | thread runnable → scheduled on CPU | OS scheduler/run queue, CPU throttling, off-CPU profiling |
| **JVM pause** | pause/safepoint start → end | GC/safepoint logs, JFR GC pauses |

**Thread.State is a state snapshot, not a waiting-time statistic:**

- **RUNNABLE:** thread is running or eligible to run; some native I/O paths still appear as RUNNABLE. Does not prove CPU is currently executing that thread.
- **BLOCKED:** waiting to enter or reenter a **Java object monitor** to execute `synchronized`. Does not cover all lock types or socket I/O.
- **WAITING:** waiting indefinitely for another party's action, e.g., `Object.wait()`, `Thread.join()`, `LockSupport.park()`.
- **TIMED_WAITING:** bounded wait such as `Thread.sleep()`, timed wait/join/park.
- **NEW/TERMINATED:** not yet started / finished; not used to conclude request bottlenecks.

An idle thread pool can have most workers in WAITING while the system is completely healthy. Conversely, a thread in RUNNABLE can be spinning CPU or stuck in native I/O. Capture multiple timestamped thread dumps and examine **progress counters, stacks, lock owners, and queues** before calling it "hung" or "deadlocked".

### Does ThreadMXBean Measure Waiting Time?

When the JVM supports thread contention monitoring and `setThreadContentionMonitoringEnabled(true)` is enabled, **ThreadInfo** can provide:
- `getBlockedTime()`: approximate time spent waiting to enter/reenter a **monitor**.
- `getWaitedTime()`: approximate time spent in **WAITING/TIMED_WAITING** under the monitoring mechanism.

These counters may report `-1` if unsupported or disabled, are cumulative, and depend on JVM resolution/overhead. They are **not** total business-request wait time and do not cover all I/O, external queues, or all lock primitives. Enabling contention monitoring in production requires weighing its overhead.

If you want to assert "waited 500 ms to get a DB connection", instrument **enqueue/acquire start → acquired**, and separately measure **query start → query end**. Do not use `elapsed - threadCPU` to blame the DB for everything.

## 5. Runnable Java 17+ Program: CPU Work and Sleep

The program below measures two tasks on the same **main thread**. The first phase sums numbers to burn CPU; the second phase sleeps for 250 ms. It gets duration from `System.nanoTime()` and CPU from `ThreadMXBean` when supported.

Save the full code in **TimeTypesDemo.java**:

~~~java
import java.lang.management.ManagementFactory;
import java.lang.management.ThreadMXBean;
import java.util.Locale;

public class TimeTypesDemo {
    private static volatile long checksum;

    public static void main(String[] args) {
        ThreadMXBean bean = ManagementFactory.getThreadMXBean();
        boolean cpuAvailable = bean.isCurrentThreadCpuTimeSupported();

        if (cpuAvailable && !bean.isThreadCpuTimeEnabled()) {
            try {
                bean.setThreadCpuTimeEnabled(true);
            } catch (SecurityException | UnsupportedOperationException e) {
                cpuAvailable = false;
            }
        }
        cpuAvailable = cpuAvailable && bean.isThreadCpuTimeEnabled();

        measure("CPU work", bean, cpuAvailable, () -> {
            long sum = 0L;
            for (int i = 0; i < 10_000_000; i++) {
                sum += i % 7;
            }
            checksum = sum;
        });

        measure("Sleep", bean, cpuAvailable, () -> {
            try {
                Thread.sleep(250);
            } catch (InterruptedException e) {
                Thread.currentThread().interrupt();
                throw new IllegalStateException("sleep interrupted", e);
            }
        });

        System.out.println("checksum=" + checksum);
    }

    private static void measure(
            String label, ThreadMXBean bean,
            boolean cpuAvailable, Runnable task) {

        long cpuStart = cpuAvailable
                ? bean.getCurrentThreadCpuTime() : -1L;
        long wallStart = System.nanoTime();

        task.run();

        long elapsedNanos = System.nanoTime() - wallStart;
        long cpuEnd = cpuAvailable
                ? bean.getCurrentThreadCpuTime() : -1L;

        String cpuText = (cpuStart >= 0 && cpuEnd >= cpuStart)
                ? String.format(Locale.ROOT, "%.3f ms",
                        (cpuEnd - cpuStart) / 1_000_000.0)
                : "unavailable";

        System.out.printf(Locale.ROOT,
                "%s: elapsed=%.3f ms, threadCPU=%s%n",
                label, elapsedNanos / 1_000_000.0, cpuText);
    }
}
~~~

Compile and run commands:

~~~bash
javac TimeTypesDemo.java
java TimeTypesDemo
~~~

**Interpreting the output properly:** the first two lines start with `CPU work:` and `Sleep:`, followed by measured elapsed time and measured thread CPU. Timings depend on hardware, scheduler, JIT, and OS, so **fixed timing stdout cannot be provided**. If CPU time is unsupported, the program prints `threadCPU=unavailable`. The final line is **always**:

~~~text
checksum=29999994
~~~

For `Sleep`, elapsed is typically around 250 ms or more because the scheduler may wake the thread slightly late; thread CPU barely increases, showing that elapsed interval was **not spent computing on the main thread**. For `CPU work`, CPU usually forms a larger fraction of elapsed time, though it can be lower under core contention or throttling. Do not treat the difference between the two phases as a hardware speed benchmark: JIT warm-up, CPU clock scaling, measurement timing, and runtime overhead all affect it.

**Limitations:** this code only measures the current thread's CPU, without adding GC/JIT/other workers; it does not directly measure lock wait, I/O wait, or queues. Reading CPU before/after elapsed introduces slight timing skew; very short blocks should be sampled many times with appropriate benchmark/profiler tools. This is an example of **measuring the nature of quantities**, not a reliable microbenchmark for comparing two systems.

## 6. Investigation Strategy When Latency Increases

A sound strategy is to measure **the same time window** across layers and cross-reference:

1. **End-to-end:** get elapsed p50/p95/p99, sample count, request type, success/error, deadline, and trace IDs. High p99 may come from a small subset of requests; looking only at the mean misses it.
2. **Processing spans:** split queue wait, connection acquire, DB/HTTP calls, locks, business logic, and serialization. If spans run in parallel, they overlap—do not simply sum them.
3. **Thread/JVM:** check thread CPU delta, stacks/thread states across multiple timestamps, park/monitor/I/O events, and GC/safepoints. A single thread dump does not measure total wait time.
4. **Process/OS/container:** process CPU, CPU quota, throttling, run queue, disk/network latency, thread pool saturation. Spare host CPU does not guarantee the container has sufficient quota.
5. **Dependencies:** DB latency, connection pool wait, downstream HTTP, retries, and timeouts. A method with high elapsed time due to network calls can still use very little CPU.

With HotSpot JDK and appropriate attach permissions, you can capture a thread dump and a JFR recording using the corresponding PID:

~~~bash
jcmd 12345 Thread.print -l
jcmd 12345 JFR.start name=timing settings=profile duration=60s filename=timing.jfr
~~~

`12345` is an example PID. `Thread.print -l` gives a snapshot of stacks and locks, not an exact wait-time percentage. JFR can provide execution samples, park/monitor, I/O, and GC events depending on enabled events and recording thresholds; inspect the recording settings. Collection has overhead and files may contain sensitive data, so weigh permissions/size and capture at the right time. If the process has already exited, you cannot attach to the old PID.

### Reading Signals Without Over-Concluding

| Observation | Initial Hint | Evidence to Check Next |
| --- | --- | --- |
| High request elapsed, low thread CPU | Significant off-CPU or wait outside measured CPU segment | Queue, DB, lock, sleep, GC, scheduler, whether request hops threads |
| High elapsed, thread CPU close to elapsed | Thread segment may be CPU-heavy | CPU profile/hot methods, sample count, contention, algorithmic optimization |
| High process CPU, high single-request elapsed | JVM is burning CPU somewhere | Which threads consume CPU? GC/JIT or this request? CPU quota? |
| Low process CPU, many request timeouts | Likely waiting on non-CPU resource | Pools, downstream, I/O, locks, saturation, quota throttling |
| Many threads WAITING, healthy throughput | Likely normal idle workers | Queue/completion rate, stacks, and pool utilization |
| Process CPU 250% in 1 second | Likely using ~2.5 cores on average | Logical cores/quota and OS accounting, never infer "negative wait" |
| p99 elapsed rises while per-task CPU is flat | Tail latency likely comes from waiting | p99 traces, queue age, dependency p99, I/O and lock evidence |

## 7. Before–After Discrimination Scenarios

**A — Sleep and CPU:** code sleeping 500 ms typically increases elapsed by at least ~500 ms while CPU time stays tiny. This is **intentional waiting**, not proof of a weak CPU. Notably, `Thread.sleep()` does not release held monitors, so sleeping inside `synchronized` can also cause lock contention for other threads.

**B — Scheduler wait vs. database wait:** a request uses 80 ms CPU yet takes 300 ms elapsed because the process is CPU-quota throttled or contending for cores. The 220 ms off-CPU difference is not enough to call it DB wait. Check cgroup CPU throttling, run queue, OS scheduler, and CPU profile before tuning SQL.

**C — Connection pool wait vs. query time:** total request is 900 ms, of which 500 ms is waiting to acquire a connection and 250 ms is executing SQL. Measuring only SQL and blaming all 900 ms on the database engine is wrong. Place a separate span on acquire, a separate span on the query, and measure end-to-end request time.

**D — Process CPU exceeds elapsed:** four workers execute in parallel, consuming a total of 6 CPU seconds within a 2-second wall-clock window; average consumption is ~3 logical cores. This is valid. Never subtract 6 seconds from 2 seconds elapsed; to know what a request waited on, measure CPU/timeline of **the exact request and its involved threads**.

**E — WAITING threads do not imply a hang:** workers waiting for jobs in a pool with no backlog is normal. Only when completion counters stall despite a full queue, and multiple snapshots show workers waiting on the same lock/dependency, do you have evidence of a stall. Distinguish "normal idle wait" from "no forward progress".

**F — GC causes high elapsed with low app-thread CPU:** stop-the-world pauses prevent application progress, while an application thread's CPU barely increases; process CPU may still be high due to GC threads consuming CPU. Use GC logs/JFR to confirm pauses instead of immediately blaming the database.

## 8. Common Measurement and Reasoning Pitfalls

- **Confusing timestamps with durations:** using `currentTimeMillis()` for microbenchmarks; system time can be adjusted, use `nanoTime()` for durations.
- **Bracketing start/end at the wrong layer:** measuring a method at 100 ms and concluding client latency is 100 ms, ignoring queues, network, and retries.
- **Equating elapsed = CPU:** ignoring I/O, sleep, locks, scheduling, and GC/safepoints.
- **Equating elapsed − CPU = I/O wait:** the same-thread difference only approximates off-CPU time; measure I/O spans separately.
- **Subtracting multi-thread process CPU from one request's wall time:** incompatible scopes.
- **Assuming RUNNABLE means actively consuming CPU:** state does not prove CPU allocation.
- **Assuming WAITING/BLOCKED means deadlock:** a single thread state is just a snapshot; need lock graphs and progress checks over time.
- **Treating ThreadInfo blocked/waited time as total request wait:** limited to monitors/WAITING tracking and enabled monitoring.
- **Ignoring thread switches in async code:** one worker's CPU does not represent an entire multi-stage request.
- **Summing parallel spans:** two overlapping 400 ms branches do not necessarily yield 800 ms elapsed; identify the critical path.
- **Measuring once and concluding:** JIT compilation, class loading, GC, CPU frequency, and background load create variance; use multiple samples, clear windows, and equivalent baselines.
- **Ignoring measurement overhead:** excessive synchronous logging, heavy profilers, and instrumentation can affect the very work being measured.

## 9. Checklist for an Evidence-Backed Conclusion

A timing measurement report should answer: **(1)** what is the subject and measurement interval; **(2)** from which layer—client/server/method/span—was elapsed recorded; **(3)** was monotonic duration or calendar timestamp used; **(4)** is CPU per-thread or process-wide, and did work hop threads or run in parallel; **(5)** was the wait type instrumented directly or only inferred; **(6)** are queue, lock, I/O, dependency, scheduler, CPU quota, and GC metrics present; **(7)** are load, measurement window, and baseline equivalent?

**Good conclusion:** "From 10:00–10:05, GET /orders p95 elapsed is 920 ms; the DB connection-acquire wait span p95 is 640 ms. Worker CPU is low; the delay source is confirmed at the acquire step, and pool saturation is under inspection."

**Insufficiently grounded conclusion:** "Request took 920 ms, CPU 80 ms, so DB wait is 840 ms." That subtraction does not pinpoint the DB; it can contain many wait types, scheduler delays, and runtime pauses, and the two numbers might not even share the same scope.

**Remember:** **elapsed** answers "how much real time passed"; **thread/process CPU time** answers "how long the CPU worked"; **waiting time** is meaningful only when specifying "waiting on what, measured from where to where". Use comparisons and subtractions only when **subject, window, and accounting semantics** are compatible.
# 18.1 Distinguishing Compute-Bound vs. Resource-Wait-Bound Latency

## 1. The diagnostic problem: where did the request time go?

A Java API returning a result after **1,000 ms** does not mean the CPU was computing continuously for one second. Within a single request, multiple causes of slowness can exist at the same time:

- **CPU-bound:** the thread is genuinely using the CPU for computation, JSON encoding, compression, parsing, searching, encryption/decryption, data processing, high-complexity algorithms, or spinning.
- **I/O-bound:** the thread/execution flow must wait on disk, files, sockets, databases, HTTP/gRPC services, DNS, TLS, storage, or an external system.
- **Resource/coordination-bound:** waiting to acquire a connection from a pool, waiting on a lock, queue, semaphore, rate limiter, or a thread pool or executor with no free workers.
- **CPU scheduling-bound:** runnable work is ready to execute, but does not receive enough CPU due to host contention, container CPU quota/throttling, long run queues, or scheduler priority.
- **JVM/system pauses:** GC stop-the-world pauses, safepoints, class loading, JIT compilation, paging, kernel/scheduler activity, etc., can increase latency without resembling a simple CPU hot loop.

**The goal** is to identify **which branch lies on the request's critical path**, backed by measurable evidence. Never conclude the root cause from a single CPU chart, a `RUNNABLE` state, or a single thread dump.

This lesson focuses on **distinguishing computation from waiting for resources** using wall-clock time, CPU time, metrics, thread dumps, JFR, and tracing, with standalone Java 17+ examples to verify for yourself.

## 2. The two most important clocks: wall time and CPU time

**Wall-clock elapsed time** is the actual time elapsed from the start to the end of a processing block, including time when the thread has not been scheduled to run or is waiting on I/O/locks.

**Thread CPU time** is the total CPU time spent executing instructions for **that platform thread** in user mode and system mode. A thread may take 500 ms of wall time waiting on the network while consuming only a few milliseconds of CPU; conversely, a busy computation loop taking about 500 ms of wall time typically accumulates nearly 500 ms of CPU time if the scheduler grants CPU continuously.

| Time type | Java measurement source | Used to answer | Caveats |
| --- | --- | --- | --- |
| Wall elapsed | `System.nanoTime()` delta between two points | How long did the caller wait? | Includes CPU, I/O wait, queuing, scheduling, and many other pauses. |
| Current thread CPU | `ThreadMXBean.getCurrentThreadCpuTime()` | How much CPU did this platform thread actually use? | May be unsupported/disabled by default; does not support virtual threads via this API. |
| Process CPU | OS/JMX process CPU time or process telemetry | How much total CPU did **all threads** in the process use? | Can exceed wall time because multiple CPU cores run in parallel. |
| Machine/container CPU | OS/container monitoring | Is the host or CPU quota saturated? | Must understand the denominator by cores/quota; 25% CPU can correspond to one core at 100%. |
| Dependency time | Distributed tracing, DB/HTTP client metrics | How long did it wait on database, pool, socket, or remote service? | Needs matching trace/timestamps; cannot be inferred accurately from process CPU. |

The diagnostic formula **is only an approximation meaningful for a single platform thread measured over the same interval**:

```text
elapsed = endNanoTime - startNanoTime
threadCpu = endThreadCpuTime - startThreadCpuTime

cpu_fraction ≈ threadCpu / elapsed
remaining_elapsed ≈ elapsed - threadCpu
```

If a thread shows **200 ms wall, 190 ms CPU**, that segment has substantial on-CPU time. If **200 ms wall, 2 ms CPU**, almost the entire elapsed time is not CPU execution of that thread. However, **the remaining 198 ms cannot automatically be called "network wait"**: it could be waiting on a pool, monitor, park, GC pause, scheduling, or CPU throttling. Classification requires evidence from other layers.

CPU clock precision is determined by the JVM/OS. Very short measurements or millisecond rounding can produce a ratio slightly above 1.0; do not use a hard threshold for microbenchmarks. `System.nanoTime()` is used to **take elapsed time differences**, not as a Unix timestamp, and points taken from unrelated JVMs/clocks should not be compared.

## 3. How are CPU-bound and wait-bound different?

### When slow due to computation

A thread loops inside a codec, parser, regex, `O(n²)` algorithm, JSON serialization, encryption, validation, or business logic. Under a steady workload, common signs include:

1. The executing thread's CPU time increases almost proportionally with elapsed time.
2. Process/container CPU or a single core saturates, especially as request volume grows.
3. JFR execution samples cluster repeatedly on specific call stacks/hot methods.
4. Changing data structures, reducing operation counts, or caching results lowers both CPU time **and** latency.

**CPU-bound does not have to mean 100% CPU across the whole machine.** On a 16-core host, **one** thread saturating a single core may appear as only ~6.25% machine-wide CPU if the dashboard uses all 16 cores as the denominator. For a sequential endpoint where only one worker executes the heavy step, a single saturated core still limits throughput.

### When slow due to waiting for resources

Wait time can originate from:

- **Network/DB:** socket read waiting for a response, remote DB executing a query, another server overloaded, timeouts/retries.
- **Pool:** HTTP connection pool or JDBC pool out of slots; threads wait on acquisition even though the database has not received a query yet.
- **Locks:** Java `synchronized` monitors, `ReentrantLock`, conditions, semaphores.
- **Queue/executor:** requests waiting for a processing slot; whether workers are idle or busy, queue length and time in queue are decisive data.
- **File/storage:** file reads, fsync, page cache misses, disk queues.
- **Scheduler:** threads have runnable work but wait for CPU due to quota or host contention.

Common signs: wall time increases while thread CPU time is low; tracing shows large dependency/pool spans; JFR shows `SocketRead`, `ThreadPark`, `JavaMonitorEnter` events or thread dumps show corresponding stacks. **However, event-loop/async applications may not have one dedicated platform thread "waiting" per request**: you need to track futures, callbacks, queues, and request-level traces rather than looking only at thread states.

### Mixed situations

You do not have to pick only one label. A request can compute for 80 ms, wait 100 ms to acquire a DB connection, execute a query for 650 ms, and serialize the response for 70 ms. A single thread can be CPU-bound during the parse phase and I/O-bound during the DB phase. The diagnostic goal is to identify **the segment with the largest impact** and evaluate each segment's contribution.

## 4. Breaking down a request along the critical path

**Illustrative** example of a slow 990 ms request in a sequential execution flow:

| Stage | Wall time | CPU or wait? | Required evidence |
| --- | ---: | --- | --- |
| Wait in application queue | 120 ms | Wait for scheduler/worker slot | Queue latency/in-flight, executor metrics |
| Wait to acquire JDBC connection | 180 ms | Wait on connection pool | Pool acquire time, active/idle/pending |
| DB execution + network round-trip | 540 ms | Mostly external wait; database itself may be CPU-bound | DB server timings, SQL plan, socket events |
| Business validation/compute | 90 ms | Possibly CPU-bound | Thread CPU delta, execution samples |
| Serialize response | 60 ms | Usually CPU, sometimes waiting on output | CPU samples, write events |
| **Total** | **990 ms** | **Wait phases dominate** | Aggregated tracing/measurements |

Looking only at Java process CPU, a low value is not enough to prove the DB is slow; you must distinguish **pool wait (DB has not received the request yet)** from **query/remote wait (DB has received it)**. A 540 ms query can be caused by high DB server CPU, database locks, DB I/O, a poor query plan, or the network. Each hypothesis requires DB-side evidence.

For **parallel work**, do not mechanically sum child span durations: two remote calls each taking 400 ms but running in parallel may contribute only about 400 ms—not 800 ms—to the critical path. Total CPU time across multiple threads can exceed the request's elapsed time; that is normal when running concurrently on multiple cores.

To explain p99, analyze requests **that actually fall in the p99 cohort**, rather than taking only the average across all requests or a JVM-wide histogram.

## 5. Checklist of metrics to collect before opening a profiler

Pick a concrete time window—for example, 5 minutes when p95/p99 spikes—and record the release, load, core count/quota, GC, errors, and timeouts. Collect at minimum:

| Measurement group | Metrics | Why |
| --- | --- | --- |
| Request | RPS/throughput, concurrency/in-flight, p50/p95/p99 by route, errors, retries | Confirm scope and correlate load rate with latency |
| Process CPU | Process CPU usage/time, user/system CPU, top threads | See whether CPU execution increased and on which threads |
| Host/container CPU | Core count, CPU quota, throttling, run queue/pressure, CPU steal | Detect CPU limits even when % charts look low |
| JVM | GC pause duration, allocation rate, safepoints, thread count | Avoid mistaking GC pauses for network waits |
| Thread pool | Active threads, queue size, queue wait, rejected tasks | Find queuing bottlenecks even when CPU is not saturated |
| DB pool | Active/idle/pending, connection acquisition time, timeout count | Distinguish pool exhaustion from slow DB queries |
| Database | Query latency percentiles, active queries, lock waits, pool/connection count | See whether the issue is in the JDBC client or DB server |
| Network/remote | HTTP/gRPC client duration, response code, DNS/TLS timings, connection reuse, retries | Confirm an external service is slow |
| Filesystem | File I/O duration, disk saturation, read/write bytes, filesystem latency | Confirm storage is where time is waiting |
| Lock | Contended monitors, park events, lock owner/waiter | Detect serialization and contention |

A single metric alone is only a **hint**, not a conclusion. Attach thread/request/span names, timestamps, and release versions so evidence can be correlated. Metrics on a **multi-tenant host** must separate processes/cgroups to avoid confusing host CPU with the Java service's CPU.

## 6. Symptom matrix for choosing the first hypothesis

| Simultaneous observations | Priority hypothesis | Check immediately | Do not conclude |
| --- | --- | --- | --- |
| Latency rises, one/a few cores busy, high thread CPU | CPU-bound in a hot method or busy spin | JFR CPU samples, thread CPU deltas, repeated stack traces | "Host CPU is below 100%, so it cannot be CPU-bound" |
| Latency rises, low process CPU, long `SocketRead` | Waiting on remote response/DB/network | Dependency spans, DB/server latency, retries | "Low CPU means CPU is already optimized" |
| Latency rises, JDBC pool pending increases, active=max | Pool exhaustion/connections held too long | Pool acquire histogram, checkout duration, long transactions | "The DB query is definitely slow" |
| Latency rises, repeated `BLOCKED` on the same monitor | Lock contention | Multiple dumps, JFR `JavaMonitorEnter`, lock owner | "Many threads means not enough CPU" |
| Latency rises, task queue grows, all workers busy | Executor saturation or upstream flood | Pool active/queue/service time, backpressure | "Just increase the thread pool size" |
| Latency rises, process CPU near quota, throttling rises | Cgroup CPU limit/scheduling | `cpu.stat`, request CPU demand, host pressure | "Dashboard CPU is 30%, so 70% is spare" |
| Latency spike coincides with GC pause | JVM stop-the-world or GC pressure | JFR GC phases, GC logs | "Network timeout caused GC" |
| Only p99 increases, average stays stable | Tail latency, queuing, retries, locks, GC, or remote outliers | Trace slow requests, histograms, correlated time series | "The service in general is CPU-bound" |

When workload changes, CPU and latency increasing together may simply reflect **higher traffic**. Compare before and after at the same RPS, payload size, cache miss ratio, dataset, and concurrency; isolate **a causal change** rather than general correlation.

## 7. Reading thread dumps properly: `RUNNABLE` does not mean burning CPU

Java `Thread.State` is a state reported by the JVM, **not the OS scheduler state**:

| Java state | How to interpret | Diagnostic notes |
| --- | --- | --- |
| `RUNNABLE` | Eligible to execute in the JVM | May be running, waiting to be scheduled CPU, or inside a native I/O operation; does not prove CPU-bound. |
| `BLOCKED` | Waiting to acquire a **Java intrinsic monitor** to enter/re-enter `synchronized` | Check lock owner and repetition across dumps; not every kind of wait is `BLOCKED`. |
| `WAITING` | Waiting indefinitely, e.g., `Object.wait()`, `Thread.join()`, `LockSupport.park()` | Can be an idle worker, queue, future, or connection pool; many waiting threads are not automatically an error. |
| `TIMED_WAITING` | Timed wait, e.g., `Thread.sleep()`, timed park/wait/join | Normal for schedulers/timers; the stack determines whether the wait is on the critical path. |
| `NEW`/`TERMINATED` | Not yet started/already finished | Little diagnostic value for current request latency. |

**Two particularly dangerous reasoning errors:**

- Seeing `RUNNABLE` in `SocketDispatcher.read0` or native I/O and concluding "CPU-bound code": the thread may be **waiting for data** at the OS layer. Cross-check thread CPU delta, JFR socket events, and OS state.
- Seeing many `WAITING`/`TIMED_WAITING` threads and concluding "all threads are stuck": having many idle workers is completely normal. You must distinguish where **the actually slow requests** are waiting.

A single thread dump is an instantaneous snapshot. Capture **multiple snapshots spaced apart** during the incident window to see whether a stack/lock persists repeatedly or was merely coincidental; a single snapshot may miss short waits or always catch threads at a routine waiting point.

## 8. Capturing thread dumps and matching them to CPU threads

Below are diagnostic commands **run against the target Java process**, not placed inside Java source code. Replace `<PID>` with the real process ID:

```bash
jcmd -l
jcmd <PID> VM.version
jcmd <PID> Thread.print -l
```

`Thread.print -l` displays thread stacks along with `java.util.concurrent` lock information when supported by the runtime. Inspect thread name, stack, `nid`, and lock owner/waiters. Typically, three or more snapshots **spaced about 1–2 seconds apart** while the issue is happening are needed, rather than relying on one arbitrary snapshot.

**On Linux** (illustrative OS commands; require appropriate permissions and available tools):

```bash
top -H -p <PID>
pidstat -t -p <PID> 1 5
ps -L -p <PID> -o pid,tid,stat,pcpu,comm
```

These commands show which **OS threads** are consuming CPU at the time of measurement. When matching with a HotSpot thread dump, `nid` usually represents the native thread ID in hex; convert the decimal TID from Linux to hex via `printf '%x\n' <TID>` (substituting the real number) and search for `nid=0x...`. This mapping applies to **platform/native threads**; virtual threads do not have a fixed dedicated OS thread.

**Reading paired evidence:**

1. The OS shows a TID consuming nearly a full core across multiple samples.
2. Java dumps show the same `nid` consistently in a hot loop/call stack.
3. JFR execution samples and thread CPU deltas corroborate the CPU-consuming code path.

In that case, the CPU-bound hypothesis is substantially stronger than merely seeing a thread in `RUNNABLE`. If the OS shows the TID using almost no CPU while the Java stack is in `park`/pool acquisition or `SocketRead`, pivot to analyzing the wait cause.

**Permissions and environment:** `jcmd` must be able to attach to the target JVM with suitable permissions, on the same machine/PID namespace. A container image might not include `jcmd`. Running `jcmd 0` is not safe in production because it can target multiple processes; always specify the exact PID. Taking dumps too frequently on a system with many threads also incurs overhead; use a reasonable sampling interval.

## 9. Using JFR to correlate CPU and wait events

Java Flight Recorder captures a **time series** rather than a single thread dump snapshot. On a supported HotSpot JVM, take a short recording during an incident:

```bash
jcmd <PID> JFR.start name=latency settings=profile duration=120s filename=/tmp/latency.jfr
jcmd <PID> JFR.check name=latency
```

After the recording completes and the file is written:

```bash
jfr summary /tmp/latency.jfr
jfr print --events jdk.CPULoad,jdk.ThreadCPULoad,jdk.ExecutionSample /tmp/latency.jfr
jfr print --events jdk.SocketRead,jdk.SocketWrite,jdk.FileRead,jdk.FileWrite /tmp/latency.jfr
jfr print --events jdk.JavaMonitorEnter,jdk.JavaMonitorWait,jdk.ThreadPark,jdk.ThreadSleep /tmp/latency.jfr
jfr print --events jdk.GarbageCollection,jdk.GCPhasePause /tmp/latency.jfr
```

Or open `/tmp/latency.jfr` with **JDK Mission Control (JMC)** to inspect CPU, Hot Methods, Call Tree, I/O, thread stalls, locks, and GC on a timeline.

**Distinguishing events accurately:**

| JFR event | Question | Limitations |
| --- | --- | --- |
| `jdk.CPULoad` | How are JVM/host using CPU over time? | Does not directly pinpoint which method consumed CPU. |
| `jdk.ThreadCPULoad` | Which platform threads have high CPU activity? | Not a per-request critical path; depends on collected samples. |
| `jdk.ExecutionSample` | Which stacks appear frequently while code is running? | **Sampling**, not an exact CPU time counter; depends on frequency and sample count. |
| `jdk.SocketRead` / `SocketWrite` | Are there long socket I/O waits? | Has a threshold; async/higher-level operations may not appear as a corresponding blocking event. |
| `jdk.FileRead` / `FileWrite` | Where is file/storage I/O taking long? | Event coverage/threshold/caching behavior affect results. |
| `jdk.JavaMonitorEnter` | How long did a thread wait to enter `synchronized`? | Does not cover all lock/concurrency primitives. |
| `jdk.JavaMonitorWait` | How long did a thread wait in monitor wait? | Distinct from monitor-enter contention; read the right event. |
| `jdk.ThreadPark` / `ThreadSleep` | How long did park/sleep last? | Park can be an idle worker, queue, pool, or backpressure; stack/correlation reveals which. |
| `jdk.GarbageCollection` / `jdk.GCPhasePause` | Do GC/pauses coincide with latency spikes? | A GC event alone does not explain all request tail latency. |

Some stall/I/O events are only recorded by default **when duration exceeds a threshold**, often around **20 ms** in common profiles; check the actual JVM's `.jfc` file and `JFR.check ... verbose=true`. Not seeing `SocketRead` **does not prove there is no I/O**: many short operations below the threshold or async I/O may not appear. If you need to lower thresholds, take a **short** recording, measure overhead, and avoid keeping full stack traces enabled continuously in production.

**Execution samples are not a waiting-time profile**: a sleeping thread or one waiting on the network may be captured rarely or not at all by the CPU sampler while the request is still slow. Read execution samples alongside stall events and tracing; never treat CPU sample counts as percentages of request wall time.

## 10. Tracing to separate network, DB, pool, and queue waits

The strength of distributed tracing is placing timings into **request context**. A good trace should record:

- `request.received` and `handler.start`: how long did the request wait for a worker or middleware?
- `pool.acquire.start` / `pool.acquire.end`: time spent **waiting for a connection**, not yet the DB query.
- `db.query.start` / `db.query.end`: client-observed query duration; separate server execution/DB locks if the DB supports it.
- `http.client.request`: time spent waiting on DNS, connect, TLS, sending the request, receiving the response; includes retries if the client retries internally.
- `serialization` / `response.write`: CPU work to build the payload and whether socket write blocked.
- `message.queue.wait` and `worker.process`: queue wait time versus service time.

Each span should distinguish **client observed duration** from **server processing duration**. For example, a query takes 400 ms according to the Java client while the DB reports 40 ms execution; the remainder may come from **pool waiting, network, driver, fetching results, locks, or queuing**. Never conclude "SQL took 400 ms" before separating those segments.

On async paths, do not treat thread park time as request time. A request can hop across multiple threads/futures/virtual threads. Propagate trace ID/request ID end-to-end; compare p50 and p99 traces on the same endpoint.

**Controlled logging tip:**

```java
long started = System.nanoTime();
try {
    // Call the dependency or processing block to measure.
} finally {
    long elapsedNanos = System.nanoTime() - started;
    long elapsedMs = java.util.concurrent.TimeUnit.NANOSECONDS.toMillis(elapsedNanos);
    // Record span/metric tagged with route, dependency, status; avoid high-cardinality labels.
}
```

This is an **illustrative snippet**, not a standalone program; replace the comments with real work. Use `nanoTime()` for duration instead of subtracting two `currentTimeMillis()` calls, which are vulnerable to wall-clock adjustments. Do not log secret request payloads or emit per-user/per-request-ID metric labels that cause cardinality explosion.

## 11. Java 17+ lab: measuring CPU time versus actual socket wait time

The following example creates **two reproducible phases** in one JVM:

1. `compute`: the main thread performs arithmetic in a loop for about 400 ms.
2. `socket_read`: the main thread reads one byte from a loopback TCP socket; another thread waits 400 ms before sending that byte. The delay is **waiting for socket data**, not CPU-heavy computation on the main thread.

Both phases are measured with **two clocks**: `System.nanoTime()` and `ThreadMXBean.getCurrentThreadCpuTime()` on the **platform main thread**. Standalone Java code, no external services required.

Save as **`CpuVsWaitDemo.java`**:

```java
import java.lang.management.ManagementFactory;
import java.lang.management.ThreadMXBean;
import java.net.InetAddress;
import java.net.ServerSocket;
import java.net.Socket;
import java.util.Locale;
import java.util.concurrent.TimeUnit;

public class CpuVsWaitDemo {
    private static volatile long checksum;

    @FunctionalInterface
    interface Work {
        void run() throws Exception;
    }

    private static void measure(
            String name, Work work, ThreadMXBean bean, boolean cpuAvailable)
            throws Exception {
        long wallStart = System.nanoTime();
        long cpuStart = cpuAvailable ? bean.getCurrentThreadCpuTime() : -1L;

        work.run();

        long wallEnd = System.nanoTime();
        long cpuEnd = cpuAvailable ? bean.getCurrentThreadCpuTime() : -1L;

        long wallMs = TimeUnit.NANOSECONDS.toMillis(wallEnd - wallStart);
        long cpuMs = (cpuStart >= 0L && cpuEnd >= 0L)
                ? TimeUnit.NANOSECONDS.toMillis(cpuEnd - cpuStart)
                : -1L;

        String cpuText = cpuMs >= 0L ? Long.toString(cpuMs) : "N/A";
        String ratio = cpuMs >= 0L
                ? String.format(Locale.ROOT, "%.2f",
                        (double) cpuMs / Math.max(1L, wallMs))
                : "N/A";

        System.out.printf(Locale.ROOT,
                "%s wall_ms=%d thread_cpu_ms=%s cpu_wall_ratio=%s%n",
                name, wallMs, cpuText, ratio);
    }

    public static void main(String[] args) throws Exception {
        ThreadMXBean bean = ManagementFactory.getThreadMXBean();
        boolean cpuAvailable = bean.isCurrentThreadCpuTimeSupported();

        if (cpuAvailable && !bean.isThreadCpuTimeEnabled()) {
            try {
                bean.setThreadCpuTimeEnabled(true);
            } catch (UnsupportedOperationException | SecurityException ignored) {
                cpuAvailable = false;
            }
        }
        if (cpuAvailable) {
            cpuAvailable = bean.isThreadCpuTimeEnabled();
        }

        // Case 1: CPU-bound computation on the main thread.
        measure("compute", () -> {
            long deadline =
                    System.nanoTime() + TimeUnit.MILLISECONDS.toNanos(400);
            long value = 1L;
            while (System.nanoTime() < deadline) {
                value = value * 1664525L + 1013904223L;
            }
            checksum = value; // Keep the result so the loop is not eliminated as meaningless.
        }, bean, cpuAvailable);

        // Case 2: Wait on a TCP loopback socket, no Internet required.
        try (ServerSocket server =
                     new ServerSocket(0, 1, InetAddress.getLoopbackAddress())) {
            server.setSoTimeout(3000);

            Thread responder = new Thread(() -> {
                try (Socket peer = server.accept()) {
                    Thread.sleep(400); // Simulate a slow remote service response.
                    peer.getOutputStream().write(7);
                } catch (Exception ex) {
                    System.err.println(
                            "responder_error=" + ex.getClass().getSimpleName());
                }
            }, "demo-responder");

            responder.start();
            measure("socket_read", () -> {
                try (Socket client = new Socket(
                        InetAddress.getLoopbackAddress(),
                        server.getLocalPort())) {
                    client.setSoTimeout(3000);
                    int response = client.getInputStream().read();
                    if (response != 7) {
                        throw new IllegalStateException("Unexpected response");
                    }
                }
            }, bean, cpuAvailable);
            responder.join();
        }

        System.out.println("DONE");
    }
}
```

Compile and run with **JDK 17+**, in an environment that allows creating loopback TCP sockets:

```bash
javac --release 17 CpuVsWaitDemo.java
java CpuVsWaitDemo
```

The `wall_ms`/`thread_cpu_ms`/`cpu_wall_ratio` values **vary by OS, CPU quota, JIT, scheduler, and machine load**, so there is no single exact stdout set across all machines. The program prints two measurement lines prefixed with `compute` then `socket_read`, and finally prints **exactly**:

```text
DONE
```

One test run on JDK 24 showed the pattern **compute ~400 ms wall with CPU close to wall; socket_read ~400 ms wall with main-thread CPU close to 0 ms**. This is an illustrative result, not a guarantee. In environments with CPU throttling or scheduler contention, `compute` may consume less CPU time than wall time; that illustrates why OS resource metrics are needed when classifying.

### Explanation and experiment limitations

- `compute` does not read from the network; it keeps the thread busy in a time-bounded loop. `checksum` is `volatile` so the result is visibly used.
- `socket_read` calls `InputStream.read()`; the responder thread intentionally delays sending. This is a **real loopback socket wait**, though the server delay is created by `Thread.sleep` in the example rather than a full network congestion simulation.
- `ThreadMXBean` counts CPU only for **the thread being measured**, without adding CPU from the responder, GC, or other JVM workers. For a multi-threaded API, per-request CPU requires measurement compatible with concurrent execution.
- `cpu_wall_ratio` is a heuristic, not a strict "100% CPU-bound" label. Millisecond rounding and sampling timing can yield a value slightly greater than 1.0.
- If the JVM does not support or allow enabling thread CPU time, output prints `N/A`; do not replace it with 0 and conclude the thread used no CPU.
- Sockets have timeouts so the experiment does not hang indefinitely if no response arrives. If a sandbox policy blocks loopback/TCP, the program may fail with an I/O error; run it in an environment that allows Java to open loopback sockets.

**Next step to extend:** replace the responder delay with a measurable SQL query or HTTP request; attach start/end spans and capture JFR. Then measure **pool wait, remote duration, and thread CPU** separately; do not assume all time inside an API call is network wait.

## 12. Classifying incidents across production scenarios

### Scenario A — High CPU, slow requests, and one prominent hot method

**Observation:** p99 increases with request rate; one worker TID uses nearly an entire core, thread CPU delta is high; JFR hot methods recur in a regex parser or a large-list filtering algorithm.

**Hypothesis:** the endpoint is **CPU-bound** in that processing block. **Action:** determine complexity on real inputs, compare CPU/request before and after, choose an appropriate algorithm/data structure, reduce repeated parsing/serialization, add bounded caching, and benchmark under equivalent load. **Do not** rush to increase thread count: adding threads on already-saturated cores can worsen context switching and queuing.

### Scenario B — Low Java CPU, JDBC query call takes 700 ms

**Observation:** trace shows 700 ms inside the DB client; Java process CPU is low. **Wait branches:** check how much is pool acquisition, when the DB received the query, query plan and server execution, DB lock waits, round-trip/network, result fetching, and retries.

**Action:** if `pool.acquire` took 600 ms while DB execution was only 50 ms, fix pool sizing/connection hold time/transaction duration; unconditionally increasing pool size can overload the DB. If pool acquire was 2 ms while the DB server query took 650 ms, optimize SQL/indexes/transaction isolation and DB resources. **Do not** lump both together as "slow network."

### Scenario C — Thread dump shows many `WAITING` threads in a pool and a long queue

**Observation:** executor queue depth grows, active workers = max, process CPU is not necessarily high. Several threads are `park`ed waiting on a completion/future or a connection; this can be a downstream consequence of remote waits rather than the root cause.

**Action:** measure `queue_wait_ms` and `service_time_ms` separately; check whether workers are busy on CPU or waiting on I/O. If all workers are waiting on a remote dependency, adding workers can simply push more requests downstream and trigger a **cascading failure**. Consider bounded queues, timeouts, backpressure, bulkheads, and evidence-based concurrency limits.

### Scenario D — Low CPU, but `BLOCKED` grows on the same monitor

**Observation:** many threads are waiting to enter the same `synchronized` block; JFR `jdk.JavaMonitorEnter` shows prolonged contention, and thread dumps show the same lock owner repeatedly.

**Action:** shrink the critical section, move I/O outside the monitor, use immutable data, or adopt an appropriate concurrency design. Verify whether the lock holder is waiting on remote I/O inside a synchronized block: **a single** I/O call inside a lock can stall hundreds of other requests even while process CPU stays low.

### Scenario E — Dashboard CPU is not high, yet the process is throttled

**Observation:** the container has a small CPU quota, and cgroup `cpu.stat` shows `nr_throttled`/`throttled_usec` rising alongside latency; the app has many runnable tasks that do not get CPU frequently enough.

**Action:** inspect CPU quota/period, throttled duration, CPU requests/limits, and host contention; reduce CPU demand or adjust quota/scheduling to match need. **Low CPU utilization relative to the whole host does not prove CPU capacity is available to the container.** Read interval rates rather than looking only at cumulative counters.

### Scenario F — Latency spike coincides with GC stop-the-world pauses

**Observation:** multiple endpoints slow down at the same timestamp, and JFR `jdk.GCPhasePause`/GC logs show pauses. Java handlers may not accumulate much thread CPU time during a pause, yet request wall latency still increases.

**Action:** check allocation rate, heap pressure, collector choice, and pause distribution; improve allocation behavior or GC configuration if supported by data. Do not infer "low CPU so it must be I/O" when GC pauses or safepoints are occurring.

### Scenario G — Storage is slow during file reads

**Observation:** long JFR `jdk.FileRead` events, rising Linux disk I/O latency/queues. However, if files sit completely in the page cache or use async I/O, the relationship is not straightforward.

**Action:** correlate file size, read pattern, throughput, filesystem, disk capacity, and OS-level I/O wait. Avoid blaming every `FileRead` event on the physical storage device: some time is spent in the filesystem, cache, kernel, or shared storage.

### Scenario H — HTTP client wait caused by DNS/retry/connection pool

**Observation:** outbound HTTP end-to-end takes 900 ms while the target server processes in 80 ms; the remainder may be DNS, TCP connect, TLS handshake, queuing in the client pool, failed keep-alive, or retries.

**Action:** enable instrumentation for client stages; check connection reuse, DNS caching, timeouts, retry backoff, and server-side metrics. In tracing, mark **attempts** separately instead of attributing the entire 900 ms to a single network round-trip.

## 13. Why "100% CPU" and "10% CPU" are easy to misread

CPU percentages require knowing **the denominator**:

- On a machine with 8 logical CPUs, one thread keeping one core busy is ~100% in tools like `top` that define 100% as one core, yet only ~12.5% if a dashboard normalizes across all 8 cores.
- An application with two CPU-heavy threads on two cores can show process CPU around 200% in `top`; this does not mean the clock is wrong.
- A container with a 0.5-core CPU quota on a 16-core host: a workload needing one core can be heavily throttled while host-level charts look very low.
- `load average` includes task states Linux counts into its load metric, not "CPU utilization %". High load can suggest runnable contention or I/O-waiting tasks; investigate with specific metrics.
- Higher CPU time does not prove good process throughput: busy spinning, retry loops, excessive polling, GC, or spin-based lock contention can burn CPU without completing requests.

Use **interval CPU time**, CPU quota, available core count, and corresponding latency/throughput. When a process uses high CPU while app thread CPU time does not match, investigate GC threads, JVM background threads, JIT compilers, native threads, or profiler sampling.

## 14. Queuing and saturation: CPU need not be saturated to have bad p99

When the arrival rate approaches service capacity, **queue time** can spike sharply well before aggregate metrics make it obvious. Little's Law for a system in steady state:

```text
L = λ × W

L: average number of requests/jobs in the system
λ: average throughput (jobs/second)
W: average time in the system (seconds)
```

Illustrative example: **50 requests/second** and **W=0.4 seconds** correspond to **L≈20 requests in-flight** if steady-state conditions hold. Do not use this formula to assert p99 because it relates **averages** and does not by itself describe the tail latency distribution. In multi-layer queue/pool systems, instrument **each** stage to locate the bottleneck.

Basic indicators:

- **CPU saturated + growing queue:** inspect CPU-heavy workers, runnable backlog, and scaling/optimization options.
- **CPU not saturated + growing queue:** inspect blocking tasks, pool exhaustion, downstream bottlenecks, concurrency limits, or coordinator threads.
- **Concurrency increases while throughput plateaus:** you are hitting a critical-path limit; pushing higher concurrency can worsen p99.

**Watch throughput vs. cause:** when I/O-bound, raising concurrency can improve utilization if the remote service is not yet overloaded. But if the remote service is already saturated, raising concurrency increases latency and timeouts without fixing the cause.

## 15. A repeatable outside-in investigation workflow

**Step 1 — Lock down the incident window and scope.** Record endpoint, p95/p99, RPS, payload, instance count, release, deployment region, request IDs, and timestamps. Do not capture JFR during low-traffic hours to explain a midday incident.

**Step 2 — Analyze CPU capacity.** Inspect process CPU, per-core CPU, quota/throttling, host pressure, and GC. If CPU is high on a few threads, prioritize CPU sampling; if CPU is low, do not conclude yet and move to tracing/queuing.

**Step 3 — Narrow down the critical path.** Use distributed traces of slow requests: handler CPU work, task queue, connection pool, DB, remote HTTP, filesystem, serialization, and response write. Separate time in queue from time in service. Mark parallel spans explicitly.

**Step 4 — Verify with JVM evidence.** Take several thread dumps, a short JFR with CPU/I/O/lock/GC events, and a set of dependency metrics. Start with a short JFR `profile` configuration rather than enabling excessive specialized events before knowing what you need.

**Step 5 — Form a falsifiable hypothesis.** For example: "80% of p99 comes from JDBC pool acquire because connections are held too long" rather than "the DB has an issue." Expected evidence: pool pending count, checkout time, long-running transaction count, and traces.

**Step 6 — Change one controlled variable.** Optimize a query, adjust/reduce retries, tune pool timeouts, shrink payloads, or fix an algorithm. Compare at the same RPS/concurrency, data distribution, and CPU quota settings. Measure **CPU time/request, critical-path wait time, error rate, and p99** afterward.

**Step 7 — Confirm the bottleneck did not merely shift.** After optimizing a compute step, the DB may become the next bottleneck; increasing pool size can saturate the DB. Monitor resources across the whole path, not only the single chart that improved.

## 16. Virtual threads and asynchronous I/O: limits of traditional tools

Since Java 21, virtual threads can handle many I/O wait operations without pinning a dedicated OS thread for the entire wait. Therefore:

- **Do not** assume every `WAITING`/`TIMED_WAITING` virtual thread represents a wasted OS thread.
- `java.lang.management.ThreadMXBean` tracks **platform threads** and does not expose per-virtual-thread CPU time directly via traditional APIs. One virtual thread may run across multiple carrier/platform threads at different times.
- OS `top -H`, `pidstat -t`, and `nid` entries in thread dumps mainly reflect **kernel/platform threads**; do not use them to count or map 1-to-1 to all virtual requests.
- For virtual-thread requests, measure wall time by **request/span**, JFR events supported on the target JDK, and pool/DB/HTTP metrics; do not arbitrarily divide carrier CPU time onto one request.
- For reactive/event-loop systems, a request may not have its own thread "standing and waiting"; tracing and queue/callback durations reveal the real wait time.

Virtual threads **do not make the network/DB faster** and do not cure an already-overloaded downstream service. They reduce the cost of holding threads while many tasks wait. If the bottleneck is CPU computation, you still need CPU capacity and code optimization; if the bottleneck is a small DB pool or slow queries, raising virtual thread counts may simply lengthen the queue.

## 17. Common diagnostic mistakes

| Mistake | Why it is wrong | Right approach |
| --- | --- | --- |
| "CPU is low so it must be waiting on the network" | It could be waiting on locks/pools, GC pauses, CPU quota, idle workers, or queues | Collect trace + JFR + OS metrics |
| "`RUNNABLE` means the thread is running on CPU" | JVM state does not equal OS running state | Match OS TID CPU time with stack/JFR |
| "Many `WAITING` threads mean a deadlock" | Idle workers, `park`, and timers are normal | Find critical path, lock owner/waiter, deadlock evidence |
| "`BLOCKED` means blocked I/O" | Java `BLOCKED` means waiting on an intrinsic monitor | Check stack/locks and JFR `JavaMonitorEnter` |
| "100% process CPU means the whole host is out of CPU" | 100% can mean a single core | Know core count/quota and dashboard denominator |
| "A 700 ms JFR event means the DB server spent 700 ms" | Client duration includes network/pool/fetch/retry | Separate client spans from server timings |
| "No `SocketRead` means no I/O wait" | Thresholds/async paths/recording settings may omit events | Check `.jfc`, summary, stacks, and traces |
| "CPU samples are 80% so 80% of request wall time is CPU" | CPU sampling does not measure off-CPU request time | Compare CPU clock with request latency |
| "Low CPU delta = no CPU shortage" | OS scheduler/quota can make threads wait for CPU | Check throttling, run queue, host contention |
| "Just adding threads/pool size makes it faster" | Can push load onto an already-saturated resource | Find throughput limits and use bounded concurrency |
| "Sum of span durations equals request wall time" | Spans can overlap | Compute the critical path and check parallel fan-out |
| "Good trace average means good p99" | Tail requests can diverge far from the average | Inspect p95/p99 and trace slow outliers |
| "Subtract `System.currentTimeMillis()` calls to measure latency accurately" | Wall clock can jump and has coarse resolution | Use `System.nanoTime()` differences |
| "Measure virtual thread CPU time just like platform threads" | `ThreadMXBean` does not track per-virtual-thread CPU | Use JFR/OS CPU and request-level metrics |

## 18. Checklist before confirming root cause

- [ ] Identified route/request cohort, time window, RPS, p95/p99, release, core/quota, and workload.
- [ ] Measured **wall** and **CPU** separately on **the same interval/thread** where measurement allows.
- [ ] Checked process/per-core CPU, container CPU throttling, and OS scheduling.
- [ ] Checked whether GC pauses and JVM background activity coincided with the incident window.
- [ ] Captured multiple thread dumps or JFR with sufficient CPU/I/O/lock/park/GC events.
- [ ] Did not infer CPU-bound from `RUNNABLE` or I/O-bound solely from low CPU.
- [ ] Separated executor queue, DB pool acquisition, DB query, remote HTTP/timeout/retry, file I/O, and serialization along the critical path.
- [ ] Checked JFR thresholds/coverage and verified the recording covered the right time window.
- [ ] Used downstream metrics to distinguish **client waiting** from **server computing/waiting**.
- [ ] Accounted for concurrent requests, virtual threads, and async I/O; did not sum parallel spans incorrectly.
- [ ] Formulated a concrete, falsifiable hypothesis, then changed one variable under the same load.
- [ ] Re-measured latency distribution, throughput, CPU/request, queue time, and errors to prove real improvement.

## 19. Official references for deeper study

1. Oracle JDK 26, *Troubleshoot Performance Issues Using Flight Recorder* — distinguishing CPU bottlenecks, I/O, synchronization, GC, `jdk.ExecutionSample`, `jdk.SocketRead`, `jdk.JavaMonitorEnter` events, and thresholds: https://docs.oracle.com/en/java/javase/26/troubleshoot/troubleshoot-performance-issues-using-jfr.html
2. Java SE 21, `ThreadMXBean` — per-thread CPU time, platform thread support, and limitations: https://docs.oracle.com/en/java/javase/21/docs/api/java.management/java/lang/management/ThreadMXBean.html
3. Java SE 21, `Thread.State` — definitions of `RUNNABLE`, `BLOCKED`, `WAITING`, and `TIMED_WAITING`: https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/lang/Thread.State.html
4. Oracle JDK 21 `jcmd` manual — `Thread.print`, `JFR.start`, and diagnostic commands: https://docs.oracle.com/en/java/javase/21/docs/specs/man/jcmd.html
5. Java SE 21, `System.nanoTime()` — clock for measuring elapsed time intervals: https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/lang/System.html#nanoTime()
6. Java SE 21, `TimeUnit` — time unit conversions: https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/util/concurrent/TimeUnit.html
7. Oracle JDK Mission Control — analyzing JFR recordings and timelines: https://www.oracle.com/java/technologies/jdk-mission-control.html

**Conclusion:** "The application is slow" must be broken down into **CPU execution time, time waiting on dependencies/locks/pools/queues, time waiting to be scheduled CPU, and JVM pauses**. Wall time tells you how long the user waited; thread CPU time tells you how much CPU a platform thread consumed; JFR, thread dumps, tracing, and OS metrics tell you **where the waiting occurred**. The strongest conclusion is one backed by measurements along the critical path and re-verified after the change.

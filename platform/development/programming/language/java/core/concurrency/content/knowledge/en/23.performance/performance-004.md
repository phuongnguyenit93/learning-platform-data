# CPU saturation vs. I/O wait in Java Concurrency

## 1. Why distinguish them?

When a Java program processes slowly, increasing the number of threads is often the first reflex. However, an application can be slow because **the CPU no longer has enough execution time**, because **threads are waiting for data or I/O resources**, or because of **locks, queues, GC, the scheduler, and system limits**. These situations have similar symptoms but require different approaches.

This lesson focuses on Java Concurrency and how to correlate **JVM + operating system + workload metrics**, without using Spring-specific concurrency mechanisms.

After this lesson, you will be able to:
- Distinguish CPU utilization, CPU saturation, wall-clock time, thread CPU time, and I/O wait.
- Understand the exact meaning of `%wa` on Linux and why it does not measure every kind of thread "waiting for I/O".
- Read and combine `vmstat`, `mpstat`, `pidstat`, `iostat`, thread dumps, and Java Flight Recorder (JFR).
- Choose different executor strategies, concurrency limits, and optimization approaches for CPU-bound and I/O-bound workloads.
- Distinguish I/O waiting from contention, thread pool starvation, GC, CPU throttling, and queue wait time.

## 2. Metrics that must not be equated

### 2.1. CPU utilization: how busy is the CPU?

**CPU utilization** describes the proportion of time the CPU spends working within an observation window. It is a measure of **usage**, not by itself a statement that the CPU is overloaded. A CPU running at 95% while all requests still meet target latency may simply be doing useful work. Conversely, a system with 16 logical CPUs may have 7% total usage while a sequential processing thread pins **one core** near 100%, making a specific request unable to speed up by adding more threads.

When looking at CPU percentage, you must ask:
- Is it **one logical CPU**, **the whole machine**, **the Java process**, or **individual OS threads**?
- Does the tool report 100% for **one core** or for **the entire machine**? For example, `top` on Linux can often display a multi-threaded process exceeding 100% depending on the scaling mode.
- Does the JVM running in a container have a CPU quota/cpuset/affinity different from the host's physical CPU count?
- Is busy CPU spent on application code, GC, kernel, native code, or another process?

### 2.2. CPU saturation: CPU demand exceeds serving capacity

**CPU saturation** is the condition where runnable work requires more CPU than can be allocated in the relevant time interval. Some tasks must wait for the scheduler to grant CPU time; queue/CPU pressure increases. Common signs include:

1. Useful CPU is near the ceiling on relevant cores or hitting CPU quota.
2. The number of runnable threads/processes is large and sustained relative to available CPU capacity; run queue or CPU pressure is high.
3. Adding more tasks/threads increases throughput very little or not at all, while latency and scheduler wait time increase.
4. Many Java threads are executing computation, loops, parsing, encryption, compression, or GC consuming CPU.

**High CPU busy alone is not enough to conclude saturation**; evidence of waiting demand is needed. **Low overall CPU busy is not enough to rule out saturation** of a single core, cpuset, container quota, or a hot thread.

### 2.3. Wall-clock time and thread CPU time

- **Wall time:** elapsed real time from start to finish, including execution time, scheduler preemption, waiting for locks, sleep, waiting for I/O, GC pauses, and other wait intervals.
- **Thread CPU time:** time an OS/platform thread is actually executed by the CPU in user/kernel mode, when the environment supports that metric. In Java, there is `ThreadMXBean.getCurrentThreadCpuTime()`.
- **Wall − CPU** *cannot* all be attributed to I/O. This difference also includes queues, monitors/locks, parking, sleeping, preemption, GC pauses, and scheduling.

For a platform thread measured over an interval, a `CPU time / wall time` ratio close to 1 indicates the thread spent most of the time running on the CPU; close to 0 indicates the thread did not use much CPU during the measured interval. This is a **directional indicator**, not an exact classifier of wait causes. When multiple workers run concurrently across multiple cores, their total CPU time can exceed the wall time of the entire batch.

### 2.4. Linux I/O wait: what does `%wa` measure?

On Linux, `wa` in `vmstat` or `%iowait` in `mpstat`/`top` is how the operating system accounts for **CPU idle time while there is an outstanding I/O operation** according to the kernel/counter definition. It is often useful when investigating **block/storage I/O**.

It is **not**:
- "Percentage of time Java threads spend waiting for I/O".
- "Percentage of requests delayed by the network".
- "Percentage of time the disk is busy".
- A direct counter of the time each Java thread spends waiting on sockets, connection pools, or databases.

`%wa` can be near **0% even when thousands of threads are waiting on the network**: the CPU is not necessarily idle under the iowait accounting condition, and many socket-waiting states are not represented by this metric. It can also be low when the disk is very slow while other CPUs remain busy. On multi-core systems, a hot task on another core, sampling timing, kernel activity, and accounting rules make inferring "the application is not waiting on I/O" from `wa=0` incorrect. Conversely, high `%wa` is a signal to investigate storage, not proof by itself that disk is the final root cause.

**Rule:** To confirm **what** a Java request is waiting on, correlate the latency/counters of that operation (file/socket/DB) with JVM traces, rather than looking only at `%wa`.

## 3. Bottleneck classification model

| Scenario | Prominent symptom | Metrics to correlate | Remediation approach |
|---|---|---|---|
| CPU-bound near saturation | Cores/quota full, runnable count rises, latency rises as concurrency increases | Per-core/process/thread CPU, run queue, CPU pressure, JFR CPU samples | Reduce CPU/task, optimize algorithms, limit workers, add CPU when needed |
| Slow block/storage I/O | File read/write/fsync has high latency, disk queue grows; `wa` may be high | `iostat` latency/queue, JFR file events, filesystem metrics | Reduce I/O, batching, proper caching, improve storage |
| Slow network/remote I/O | Socket read/connect or backend response takes long; Java CPU may be low | JFR socket events, timeouts, network and backend metrics | Limit in-flight, timeouts, appropriate connection pool, optimize backend |
| Lock contention | Many threads wait on the same monitor/lock, CPU may be low | JFR monitor/park events, thread dumps, lock profiling | Reduce shared mutable state, narrow lock scope, change coordination design |
| Thread pool starvation / long queue | Tasks wait in queue, workers busy/blocked; total CPU may be low | Active workers, queue length, task submit-to-start latency | Separate CPU/I/O pools, bounded queue, backpressure, avoid blocking joins |
| GC / allocation pressure | CPU consumed by GC, pauses increase, throughput stalls | JFR allocation/GC, heap/GC logs, process CPU | Reduce allocation, tune heap and GC based on evidence |
| Container throttling | CPU hits quota, requests slow even with idle host cores | cgroup CPU throttling, quota, CPU pressure | Adjust quota, reduce load, limit concurrency |

**Saturation is the relationship between demand and capacity**, whereas "CPU-bound/I/O-bound" describes **where the work spends most of its time**. CPU saturation and an I/O bottleneck can exist simultaneously at different stages of a pipeline.

## 4. Java thread states do not equal CPU/I/O states

`Thread.State` has: `NEW`, `RUNNABLE`, `BLOCKED`, `WAITING`, `TIMED_WAITING`, `TERMINATED`.

- `RUNNABLE`: the thread is executing in the JVM **or may be executing/waiting in native code**; this state alone **does not prove CPU consumption**. A thread in a native socket read can still be reported as `RUNNABLE` in a platform thread dump, depending on the JDK/implementation.
- `BLOCKED`: the thread is waiting to acquire an **intrinsic monitor** (`synchronized`). It does not mean the Linux process is in state D or waiting on block-device I/O.
- `WAITING`/`TIMED_WAITING`: can come from `Object.wait()`, `LockSupport.park()`, conditions, `Future.get()`, `Thread.sleep()`, and other coordination mechanisms. They **do not automatically mean I/O wait**.
- With **virtual threads (Java 21+)**, supported blocking operations can typically cause the virtual thread to unmount/park while the carrier serves other work; a high number of waiting virtual threads does not correspond to an equal number of waiting OS threads.

Therefore, thread dumps need **stack traces** and **samples over time**. A single snapshot showing `RUNNABLE` or `WAITING` is not enough to conclude where most of the latency originates. Use JFR + OS + application metrics to increase confidence.

## 5. Runnable Java 17+ example: clearly seeing wall time vs. CPU time

The example below performs a CPU-only computation, then calls `sleep` to simulate a wait interval. **Sleep only illustrates time without CPU usage; it does not generate block-device I/O and is not a Linux `%iowait` test.**

Save the whole file as `CpuTimeVsWallTimeDemo.java`:

```java
import java.lang.management.ManagementFactory;
import java.lang.management.ThreadMXBean;
import java.util.Locale;

public class CpuTimeVsWallTimeDemo {
    private static volatile long observed;

    @FunctionalInterface
    interface CheckedTask {
        void run() throws Exception;
    }

    private static void measure(
            String label, CheckedTask task, ThreadMXBean bean) throws Exception {
        long cpuStart = bean.getCurrentThreadCpuTime();
        long wallStart = System.nanoTime();

        task.run();

        long wallNanos = System.nanoTime() - wallStart;
        long cpuNanos = bean.getCurrentThreadCpuTime() - cpuStart;
        double wallMillis = wallNanos / 1_000_000.0;
        double cpuMillis = cpuNanos / 1_000_000.0;
        double ratio = 100.0 * cpuNanos / wallNanos;

        System.out.printf(
            Locale.ROOT,
            "%s: wall=%.1f ms, cpu=%.1f ms, CPU/wall=%.1f%%%n",
            label, wallMillis, cpuMillis, ratio
        );
    }

    public static void main(String[] args) throws Exception {
        ThreadMXBean bean = ManagementFactory.getThreadMXBean();

        if (!bean.isCurrentThreadCpuTimeSupported()) {
            System.out.println("Thread CPU time không được hỗ trợ.");
            return;
        }
        if (!bean.isThreadCpuTimeEnabled()) {
            try {
                bean.setThreadCpuTimeEnabled(true);
            } catch (SecurityException | UnsupportedOperationException ex) {
                System.out.println("Không thể bật đo thread CPU time.");
                return;
            }
        }

        measure("Tính toán", () -> {
            long sum = 0;
            for (long i = 0; i < 40_000_000L; i++) {
                sum += (i * 31) ^ (i >>> 3);
            }
            observed = sum;
        }, bean);

        measure("Chờ giả lập", () -> Thread.sleep(400), bean);
        System.out.println("Đã hoàn thành hai pha đo.");
    }
}
```

Run with JDK 17+:

```bash
javac CpuTimeVsWallTimeDemo.java
java CpuTimeVsWallTimeDemo
```

Output format (time values and ratios **depend on the machine, JIT, and scheduling**, so there are no fixed numbers):

```text
Tính toán: wall=<số> ms, cpu=<số> ms, CPU/wall=<số>%
Chờ giả lập: wall=<số> ms, cpu=<số> ms, CPU/wall=<số>%
Đã hoàn thành hai pha đo.
```

In the compute phase, the thread typically spends most of its wall time on the CPU. In the sleep phase, wall time is approximately or greater than 400 ms while CPU time is usually very small. If the thread is preempted or the container is throttled, the CPU phase can also have a low `CPU/wall` ratio even though the code is purely computing. `ThreadMXBean` is an observation tool and does **not** produce an `iowait` metric; CPU time is only part of the evidence.

In real benchmarks, do not use this example to compare speed across JDKs/machines: JIT warmup, loop optimization, CPU frequency, and code recompilation significantly affect results. Use JMH for compute microbenchmarks when appropriate.

## 6. Reading Linux metrics accurately: from machine to Java process

The commands below are for **Linux**; many commands in the `sysstat` package (`mpstat`, `pidstat`, `iostat`) may need to be installed separately. Take multiple samples during the incident window rather than concluding from a single snapshot.

### 6.1. Per-core CPU and run queue

```bash
vmstat 1
mpstat -P ALL 1
```

How to read:
- `vmstat r`: number of tasks in runnable state (running or waiting for CPU). If `r` is consistently high relative to available CPUs and latency increases, suspect CPU pressure; however, consider cpuset/quota and per-core usage.
- `vmstat b`: number of tasks in uninterruptible sleep, often tied to certain kernel/I/O operations; do not confuse with Java `Thread.State.BLOCKED`.
- `us`, `sy`, `id`, `wa`: percentages of user, system, idle, and iowait CPU. Do not add `wa` into CPU "busy executing Java code".
- `mpstat -P ALL`: see which cores are hitting the ceiling and which are idle. A low overall average can hide a hot core.

With `vmstat`, the first sample is usually an average since boot; observe subsequent samples. Account for virtualization environments, hypervisor steal time (`st`), and CPU quota.

### 6.2. Java process and OS threads

```bash
pidstat -u -t -p <PID> 1
top -H -p <PID>
```

Replace `<PID>` with the actual PID when running. Both the process and OS threads can be observed by CPU. If only a few threads are busy, inspect their corresponding stacks with:

```bash
jcmd <PID> Thread.print -l
```

In some HotSpot/Linux environments, platform thread dumps show `nid=0x...` (native thread ID in hex). You can match this to the OS TID by converting decimal ↔ hex. Sample close together in time and remember that virtual threads do not map 1:1 to OS threads. Stacks can change during collection, so do not claim a thread "always" consumes CPU from a single dump.

Example of sound analysis: `pidstat` shows the same OS thread consistently consuming nearly one core and JFR CPU samples cluster in `parseRecord()`. In that case, the bottleneck is likely computation/parsing; measure and optimize that hot path before adding workers.

### 6.3. Storage I/O

```bash
iostat -xz 1
pidstat -d -p <PID> 1
```

Observe together:
- `r/s`, `w/s`, bytes read/written: I/O volume.
- `r_await`, `w_await`, or `await` (depending on version): average time I/O requests take to be serviced, which may include queueing.
- `aqu-sz`/queue depth and latency trend: evidence of storage resource contention.
- `%util`: block device busy metric; **do not** automatically apply a "100% = saturated" threshold to all multi-queue SSDs/NVMe devices.
- `pidstat -d`: amount of I/O generated by the process; be careful with page cache, delayed writes, and I/O from other processes.

High block-device metrics must **align in time** with file/DB latency or JFR file read/write events before attributing the cause. A `read()` call reading from page cache can complete quickly even though the application still processes many bytes.

### 6.4. Network I/O

When Java threads are waiting on HTTP/DB/sockets over the network, collect:
- **Client:** request latency, connect latency, read latency, timeout count, retries, connections leased/waiting in pool, in-flight requests.
- **Server/backend:** processing time, queues, connection limits, throttling/rate limits.
- **OS/network:** RTT, retransmissions, packet drops, socket queues, and DNS/TLS when relevant.
- **JFR:** `jdk.SocketRead`, `jdk.SocketWrite`, or corresponding events enabled in the recording configuration.

Network wait **does not necessarily increase `%wa`**. Many requests waiting on long responses while CPU usage is low is normal; you still need to distinguish "slow network" from "slow backend processing" and "exhausted connection pool".

## 7. Using Java Flight Recorder to connect CPU and I/O wait

JFR is built into modern JDKs and provides CPU samples, GC events, monitor/park events, and some I/O events without adding application libraries. On JDK 17+, for example, start a ~60-second recording:

```bash
jcmd <PID> JFR.start name=cpu-io settings=profile duration=60s filename=cpu-io.jfr
jfr summary cpu-io.jfr
```

Run the second command after the recording finishes and the file appears. The `filename` path and write permissions depend on the JVM environment. You can open the file with JDK Mission Control (JMC) to inspect the timeline and CPU sample stacks.

Correlate the following event groups (availability and event enabling depend on JDK/JFR settings, thresholds, and sampling):
- **CPU/load/sampling:** `jdk.CPULoad`, `jdk.ThreadCPULoad`, `jdk.ExecutionSample`, and native method sampling when collected. Look for hot methods and CPU-consuming phases.
- **File/network I/O:** `jdk.FileRead`, `jdk.FileWrite`, `jdk.SocketRead`, `jdk.SocketWrite`. Check duration, size, and stack if events are recorded.
- **Contended synchronization:** `jdk.JavaMonitorEnter`, `jdk.ThreadPark`. Check wait time and related code; do not misclassify them as storage I/O.
- **GC/heap:** GC pause, heap, and allocation events to separate collector activity from application CPU.

Events below the threshold or not enabled may **not appear**. "Seeing no SocketRead" does not mean there is no network activity. Combine JFR traces with client/backend and OS metrics within the **same time window**.

### How to read a timeline

Example of a 10-second latency spike:
1. Per-core CPU hits the ceiling; JFR execution samples concentrate in a data-processing method; `r` rises. Prioritize the CPU saturation hypothesis.
2. CPU is low, each request stalls in socket read for 2 seconds, and the backend also reports a 2-second p95; `wa` is low. Prioritize investigating remote latency.
3. CPU is low, many tasks wait on `CompletableFuture.join` or a condition in the worker pool; pool queue grows. Prioritize investigating the dependency model and starvation.
4. Host CPU has headroom, but the JVM process is repeatedly throttled by cgroup CPU throttling. Prioritize checking quotas before increasing thread count.

These are examples of **synthesizing evidence**, not rules for concluding from a single metric.

## 8. Same application, three different kinds of "wait"

Suppose a Java pipeline consists of `read file → parse JSON → call API → aggregate`.

**File read step:** if data must be fetched from slow storage, latency and block I/O can rise. However, if data is already in the page cache, file reads can be fast while still showing many bytes read at the application layer.

**JSON parse step:** mostly CPU work. If you increase workers beyond useful cores, throughput may flatten and latency may rise due to CPU contention, allocation, and GC.

**API call step:** most wall time may be waiting for a response from another service; low CPU and low `wa` do not contradict high latency. Adding threads can increase capacity to handle concurrent waiting requests, but it does not fix an overloaded target service and can push it into heavier overload.

Additionally, a worker waiting to acquire a connection from a pool is not the same as waiting on an actual network socket; it is waiting on a **bounded local resource**. Each type of wait needs metrics from the right source.

## 9. Choosing concurrency levels by bottleneck

### 9.1. CPU-bound: bound workers near actual CPU capacity

For compute-only code:
- Use a bounded executor, such as `Executors.newFixedThreadPool(n)`, and try `n` near the number of useful CPUs as a **starting point for measurement**, not as an absolute formula.
- Check `Runtime.getRuntime().availableProcessors()` on the running JDK; in containers, verify CPU quota/cpuset and whether the JDK recognizes that limit accurately.
- Prioritize reducing O(n²) algorithms, caching appropriately, reducing allocation/GC, improving memory locality, or partitioning independent data.
- Avoid letting CPU workers block on long I/O or locks; if there are multiple distinct phases, consider separating executors to prevent I/O from occupying all CPU workers.
- Increasing thread count beyond core capacity usually only increases contention and context switching without creating more CPU.

**Note:** CPU-bound work cannot automatically be parallelized indefinitely. Sequential parts, result dependencies, splitting/merging data, and memory bandwidth all limit speedup (Amdahl's law).

### 9.2. I/O-bound: bound "in-flight" work by resources, not just core count

Tasks that spend most wall time waiting can benefit from overlapping operations. Estimate directionally at steady state using Little's Law:

`L ≈ λ × W`

Where `L` is the number of items in the system (in-flight), `λ` is the completion throughput per second, and `W` is the average time an item spends in the system (seconds). For example, a target of **100 requests/second** with an average residence time of **0.2 seconds** suggests about **20 in-flight requests** at steady state. This is **not** advice to immediately create 20 threads: you must also account for latency distribution, queue layers, client/backend limits, connection pools, memory, and deadlines.

You can use:
- Bounded executors/queues and `Semaphore` limits for scarce resources (connections, API quotas, file descriptors).
- True asynchronous or nonblocking I/O where beneficial, but do not automatically assume callbacks mean zero CPU work.
- **Virtual threads (Java 21+)** for many blocking I/O operations, with supporting APIs. Virtual threads reduce thread management overhead while waiting; they do **not** create more cores, connections, bandwidth, or DB capacity. Still enforce concurrency limits based on downstream capacity.
- Timeouts, cancellation, bounded retries, and backpressure so queues do not grow unbounded.

**Do not use long queues as proof that the system is handling load well:** queues absorb load but increase end-to-end latency and out-of-memory risk.

### 9.3. Mixed workloads

If a workload is both CPU-bound and I/O-bound, a shared pool can end up with all workers occupied by network blocking while compute tasks cannot run. Separate phases, limit waiting tasks, or use a coordination model matched to the dependencies and cost of each phase. Avoid spawning an unbounded thread per item during traffic spikes.

With `CompletableFuture`, the choice of executor for `supplyAsync`/`thenApplyAsync` matters greatly: running a compute stage on an I/O-congested executor can increase tail latency. Calling `join()` on a worker inside a pool that is too small can cause dependency starvation/deadlock; express dependency branches with composed stages instead of blocking a worker waiting on a task in the same pool.

## 10. Distinguishing easily misdiagnosed phenomena

### 10.1. High CPU but low throughput

Does not automatically mean more threads are needed. Possible causes:
- Excessive retries or spin loops doing useless work.
- GC or allocation churn consuming CPU.
- Lock contention with spinning; repeated CAS failures.
- Too many workers and excessive context switching.
- Redundant computation, repeated serialization/parsing, single-threaded hot code.

Check JFR CPU samples, GC, per-thread CPU, and throughput before deciding.

### 10.2. Low CPU but high latency

Suspect waiting on network, storage, connection pool, semaphore, monitor/condition, queue, or a sequential stage. Measure `submit → task start`, `task start → task end`, and `remote request → remote response` separately. A task can look "slow" at 5 seconds even though its code ran for only 20 ms because it sat in a queue for 4.98 seconds.

### 10.3. High Linux load average but low CPU

Linux load average includes runnable tasks and certain tasks in uninterruptible sleep. Therefore, it is not purely "CPU utilization". Observe `vmstat r/b`, `wa`, stacks, and disk metrics. High load accompanied by many tasks in state D can indicate an I/O/kernel issue; do not automatically conclude CPU saturation.

### 10.4. Low host CPU but Java is CPU-bottlenecked

In containers, CPU quota can throttle the process even when the host has idle capacity. On Linux cgroup v2, you can inspect `cpu.max` and `cpu.stat` in the appropriate cgroup; rising `nr_throttled`/`throttled_usec` relates to CPU quota. Size workers based on **allocated CPU** and actual performance, not the host's total cores.

### 10.5. Do many waiting virtual threads mean high I/O wait?

No. A large number of virtual threads parked on I/O can be normal behavior. Check latency, carrier health, actual CPU, and downstream limits. When needed, inspect JFR pinning events on supporting JDKs and analyze blocking code that does not cooperate with virtual threads; do not attribute every `WAITING` state to disk I/O.

## 11. Repeatable practical diagnostic workflow

**Step 1 — Frame the question by symptom.** Is the slowdown in throughput, p95/p99 latency, startup time, or a batch job? Specify the time window, load (requests/second), actual concurrency, and normal baseline.

**Step 2 — Check CPU/quota and runnable tasks.** Measure per-core CPU, process/thread CPU, run queue, or CPU pressure. In containers, check quota/throttling. Determine whether the application truly lacks CPU or only has a single hot thread.

**Step 3 — Break request/task time into phases.** At a minimum, measure queue wait, CPU/compute, file/network calls, lock wait, and aggregation. Do not measure only total end-to-end time.

**Step 4 — Correlate JVM with OS.** Collect JFR and several thread dumps during the incident; simultaneously observe `vmstat`, `mpstat`, `pidstat`, `iostat`, and network/backend metrics if relevant. Use the same timeline.

**Step 5 — Form a testable hypothesis.** Examples:
- "Increasing workers from 8 to 16 did not increase throughput because 8 CPU cores are already saturated."
- "CPU is low because 80% of request wall time is spent in socket read to backend B."
- "The task queue is long because all 8 workers are blocking on another Future in the same pool."

**Step 6 — Change only one variable intentionally.** Reduce workers, limit in-flight requests, cache/batch I/O, fix an algorithm, resize the connection pool, or optimize the backend according to the hypothesis. Re-measure throughput, p95/p99, error rate, CPU, queues, and I/O latency. Watch the impact on downstream services as well.

**Step 7 — Verify under realistic load.** A dev environment with `Thread.sleep` does not replace a real system. Test both steady load and bursts; monitor backpressure, memory, timeouts, and error recovery.

## 12. Two concrete diagnostic examples

### Case A: processing 1 million records on a machine with 4 usable CPUs

The pool is increased from 4 to 32 threads; throughput goes from 20,000 to 20,500 records/second, but p95 doubles. Observed CPU is near the ceiling, there are many runnable tasks, and JFR shows most samples in parsing/hashing.

Interpretation: evidence leans toward **CPU saturation**. Next steps to test: reduce workers closer to CPU capacity, profile the hot path, reduce allocations, and batch better. Running 32 workers does not create 32 cores. The numbers are **hypothetical** to practice reasoning.

### Case B: calling a service from Java with p95 around 2 seconds

JVM CPU is low; requests wait on remote socket read; Linux `%wa` is near 0; the backend reports rising queue time. Even when increasing concurrent tasks, the target service only handles a fixed amount and the error rate begins to rise.

Interpretation: this is a **remote wait/downstream bottleneck**, with no evidence of Java CPU saturation and no need for `%wa` to be high. Next steps to test: control in-flight requests and timeouts, inspect remote queues, optimize or scale the backend. Adding virtual threads only makes waiting cheaper on the Java side; it does not increase backend capacity.

## 13. Common mistakes and how to fix them

| Mistake | Why it is wrong | Correct approach |
|---|---|---|
| "`%wa=0` ⇒ not waiting on I/O" | `wa` is not a timer for Java socket/DB waits | Measure JFR socket/file events + client/backend latency |
| "Every `RUNNABLE` is consuming CPU" | JVM thread state does not equal OS CPU time | Combine per-thread CPU, JFR CPU samples, and stacks |
| "Every `WAITING` is disk I/O" | Could be waiting on a monitor/condition/Future/sleep | Read stacks, monitor/park events, and dependency model |
| "90% CPU ⇒ definitely saturation" | No evidence of queueing/pressure or SLA degradation | Correlate runnable count, pressure, throughput, and latency |
| "Low total CPU ⇒ not CPU-bottlenecked" | Could have a hot core, quota, or affinity | Inspect per-core CPU and cgroup quota/throttling |
| "I/O-bound ⇒ increase threads indefinitely" | Connections, backend, queues, and heap all have ceilings | Bounded concurrency, backpressure, and deadlines |
| "`sleep(500)` simulates Linux I/O wait" | Sleep does not generate disk I/O | Use sleep to teach wall/CPU; use disk workloads + `iostat` to measure I/O |
| "Disk `%util` near 100 definitely means saturation" | SSD/NVMe have multiple queues and different accounting | Evaluate latency, queue depth, throughput, and device limits |
| "One thread dump is enough to pinpoint the cause" | It is a snapshot at a single point in time | Sample over time and correlate with JFR/OS |
| "Increasing the pool fixes latency" | If the bottleneck is CPU quota or backend, a larger pool can make it worse | Prove the bottleneck first, then optimize |

## 14. Self-check exercises

**Exercise 1.** A Java service runs on a machine with 8 logical CPUs. Total CPU is about 15%, but one thread uses nearly 100% of one core and requests passing through a sequential code section see rising latency. Can you conclude "CPU is still idle so add more threads"? Explain the limit of a hot path and how to find it in JFR.

**Exercise 2.** You see `vmstat` reporting `wa=1%`, low `r`, process CPU at 10%, and HTTP call p95 at 3 seconds. List at least three types of metrics to check before concluding it is caused by network/backend or connection pool.

**Exercise 3.** `iostat` shows storage `await` spiking at the same time JFR records long `FileRead` events. `%wa` also rises. What is the initial hypothesis? What else would you measure to distinguish slow storage from page cache misses or device load caused by another process?

**Exercise 4.** A 4-thread worker pool has all four tasks calling `Future.get()` to wait for other tasks just submitted **to the same pool**. CPU is low, queue grows. Is this I/O wait? Fix the design by eliminating blocking dependencies inside workers or arranging executors/dependencies properly.

**Guided answers:** (1) A sequential hot path can saturate one core even when total CPU is low; per-thread CPU and CPU samples are needed. (2) Client timeouts/connection-pool wait, JFR socket events, and backend latency/queue, plus network RTT/retransmissions when needed. (3) Suspect storage I/O; correlate file timing, per-process I/O, cache behavior, device latency/queue, and load from other processes. (4) This is starvation from task dependencies within the same pool; a blocked `Future.get()` does not prove I/O and requires restructuring the task graph.

## 15. Takeaways for decision-making

- **CPU saturation:** runnable work demand exceeds CPU capacity; read utilization **together with** run queue/pressure, per-core usage, quota, and throughput/latency impact.
- **I/O wait (`%wa` Linux):** an accounting metric for CPU idle time under certain I/O conditions, especially useful for block storage investigation; it does **not** measure all time Java threads wait on network/DB.
- **Wall time ≠ CPU time:** the difference includes many types of waits; determine the cause using stacks, JFR events, OS metrics, and specific resource metrics.
- **Optimize the right bottleneck:** CPU-bound workloads prioritize reducing CPU work and bounding workers; I/O-bound workloads prioritize latency, in-flight limits, backend resources, timeouts, and backpressure; mixed workloads require separating phases and measuring in practice.

The most important distinction in operating Java concurrency is **insufficient CPU capacity to run tasks** versus **tasks waiting on another resource or condition**. Only when metrics, stacks, and wall time all point to the same cause is the choice to add threads, reduce threads, or optimize I/O well-founded.

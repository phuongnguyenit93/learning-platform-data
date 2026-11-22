# Measuring the Impact of Thread Count and Context Switching in Java

## 1. Objectives and Key Takeaways

**Thread count** is the number of threads currently existing or used to process work; **context switching** is the process by which the operating system pauses execution of one thread and resumes execution of another thread on a CPU. When increasing the number of threads, an application can utilize more CPU capacity or overlap I/O wait time. Beyond a certain threshold, however, the benefit diminishes or turns into overhead due to CPU contention, synchronization, memory, the scheduler, and context switches.

You cannot conclude that “more threads is always faster” or “high context switches mean the application is slow” from a single number alone. To evaluate the **impact**, you must vary thread count in a controlled manner, measure throughput/latency, and also observe CPU, context switches, contention, GC, and workload characteristics.

This lesson focuses on **Java concurrency at the JDK/JVM and operating system levels**, especially platform threads and ExecutorService. No Spring-specific APIs or mechanisms are required.

After this lesson, you will be able to:

1. Explain when increasing thread count helps CPU-bound and I/O-bound workloads.
2. Design an experiment that varies the number of threads while keeping total work constant.
3. Measure time, throughput, CPU utilization, and context switches using appropriate tools.
4. Distinguish OS context switches from block/wait counts and JVM thread states.
5. Choose thread pool sizes based on data, and detect oversubscription and contention.

## 2. Mechanism: Why Does Thread Count Affect Performance?

### 2.1. Thread count, concurrency, and parallelism

- **Concurrency**: multiple tasks making progress overlapping in time; they can take turns on a single CPU.
- **Parallelism**: multiple tasks executing **truly simultaneously** on multiple logical processors.
- A **platform thread** in Java 17 maps to an operating system thread; the operating system decides when a thread runs, is paused, and is moved between CPUs.
- **Logical processors** include the CPUs that the process is permitted to use; this number may differ from the physical core count due to SMT, affinity, or CPU quotas in containers.

For example, on a machine permitted to use four logical processors:

~~~text
4 CPU-bound threads:
CPU 1: [T1--------]
CPU 2: [T2--------]
CPU 3: [T3--------]
CPU 4: [T4--------]

8 CPU-bound threads:
CPU 1: [T1---][T5---][T1---] ...
CPU 2: [T2---][T6---][T2---] ...
CPU 3: [T3---][T7---][T3---] ...
CPU 4: [T4---][T8---][T4---] ...
~~~

The diagram only illustrates CPU time-sharing. A real scheduler involves priorities, runqueues, migration, interrupts, and other fluctuations.

If all threads continuously perform computation, increasing the thread count from 1 toward the number of logical processors can reduce the **wall-clock time** of an independent batch. Exceeding that level usually does not increase computational capacity; sometimes it even slows things down because threads must share CPUs, lose locality, and experience more contention.

If many threads are **waiting** on disk, network, timers, or locks, the CPU can run another thread during the wait. Therefore, an I/O-bound workload sometimes needs more threads than the core count. However, connection counts, resource pools, wait times, memory footprint, and external service limits remain important constraints.

### 2.2. What Is a Context Switch?

A **context switch** (thread context switch) occurs when a CPU switches from one running thread to another. The operating system saves/restores the necessary state (such as registers, instruction pointer, stack/scheduling state), updates the scheduler, and resumes execution of the selected thread. The costs may include:

- Time spent performing scheduling and kernel state transitions.
- Loss of cache/TLB locality or having to warm up data and instruction caches again; the extent depends on the pair of threads, CPU, and architecture.
- CPU migration across cores, which changes locality and interacts with the cache hierarchy.
- Synchronization contention and cache coherence traffic, which can increase when more threads access shared state concurrently.

Not every context switch wipes out the entire cache, nor is there a single **fixed cost in microseconds** that applies to every machine.

There are two causes commonly tracked by the operating system:

- **Voluntary context switch**: the thread yields the CPU because it is waiting for a resource or event, such as a mutex, condition, or I/O.
- **Involuntary context switch**: the thread is runnable, but the operating system stops its execution—for example, its time slice expires or the CPU is preempted for another thread.

An increase in context switches is not automatically a bug. An efficient I/O system may voluntarily sleep/wait very frequently; a problem arises when the level of context switching or contention reduces **useful work output**.

### 2.3. Java Thread States Are Not OS Context Switch Counters

Thread.State in the JVM includes NEW, RUNNABLE, BLOCKED, WAITING, TIMED_WAITING, and TERMINATED.

- **RUNNABLE** in Java may simply mean the thread is ready to run or is executing native/JVM code; it **does not prove** the thread is actively occupying a CPU.
- **BLOCKED** reflects waiting to enter a Java monitor (synchronized), and does not describe all waiting cases.
- **WAITING/TIMED_WAITING** can be caused by Object.wait(), LockSupport.park(), Thread.join(), or Thread.sleep(); you cannot convert the total count of these states into the number of OS context switches.
- ThreadMXBean provides thread count, peak thread count, CPU time, and blocked/waited statistics when supported/enabled. It **does not** provide a standard total OS context switch counter across all JVMs/OSes.
- A thread dump shows a single point in time; seeing many WAITING threads in one dump is not enough to conclude scheduler thrashing.

Therefore, you must combine **JVM telemetry** and **OS counters** when analyzing context switching.

## 3. Which Metrics Should Be Measured?

| Metric | Meaning | How to Interpret |
|---|---|---|
| Wall-clock time | Time from start to completion of the work | For a batch keeping total work constant, **lower is better** |
| Throughput | Items or tasks completed per second | Useful for continuous workloads; must keep the amount of computation per item constant |
| Latency (p50/p95/p99) | Time for each request to complete | Must include queueing time; higher throughput can come with worse tail latency |
| CPU utilization / CPU time | CPU consumed during processing | Distinguishes CPU scarcity, over-shared CPU, or waiting |
| Live / active / peak thread counts | Resource pressure and concurrency level | Does not mean every thread is running; also measure pool size and active tasks |
| Context switches/s | Scheduler activity on the OS | Evaluate alongside throughput and CPU time; per-thread/per-process is more accurate than system-wide totals |
| Voluntary / involuntary switches | Thread voluntarily waiting vs. being preempted | May suggest heavy blocking or oversubscription, does not prove a single root cause |
| CPU migrations, runqueue / scheduling delay | Thread changing cores and time waiting for CPU | Useful when CPU is heavily loaded or latency increases |
| Lock contention, monitor blocked time | Portion of time spent waiting on synchronization | Many threads contending for locks can degrade scaling |
| GC pauses, heap, and allocation | Other JVM overhead affecting latency | Avoid blaming every spike on context switches |

Do not measure “tasks/s” alone while ignoring latency, or use **current thread count** in place of the number of active worker threads. When reporting, specify the permitted CPU cores, machine/JDK type, Java flags, thread count, workload type, duration, sample count, median, and dispersion.

## 4. Java 17+ Experiment: Fixed Work, Varying Thread Count

Goal: use the same set of tasks and the same fixed-pool ExecutorService, changing only the worker count parameter between runs. Two simple workload types:

- **CPU**: each task runs a data-dependent loop computation and returns a result so the JVM cannot easily eliminate the entire calculation. The total tasks × iterations is **kept constant** across comparisons.
- **WAIT**: each task calls Thread.sleep() for a fixed duration to simulate **overlappable wait time**. This is only a waiting model and does **not** represent real network/database performance.

File **ThreadCountBenchmark.java**:

~~~java
import java.util.ArrayList;
import java.util.Arrays;
import java.util.List;
import java.util.Locale;
import java.util.concurrent.ExecutorService;
import java.util.concurrent.Executors;
import java.util.concurrent.Future;
import java.util.concurrent.TimeUnit;

public final class ThreadCountBenchmark {
    enum Mode { CPU, WAIT }

    private static volatile long sink;

    private static long doWork(Mode mode, int work)
            throws InterruptedException {
        if (mode == Mode.WAIT) {
            Thread.sleep(work); // milliseconds; simulates waiting only
            return 1L;
        }

        long value = 0x9E3779B97F4A7C15L;
        for (int i = 0; i < work; i++) {
            value ^= value << 13;
            value ^= value >>> 7;
            value ^= value << 17;
        }
        return value;
    }

    private static long runBatch(
            ExecutorService pool, Mode mode, int tasks, int work
    ) throws Exception {
        List<Future<Long>> futures = new ArrayList<>(tasks);
        for (int i = 0; i < tasks; i++) {
            futures.add(pool.submit(() -> doWork(mode, work)));
        }

        long checksum = 0;
        for (Future<Long> future : futures) {
            checksum += future.get();
        }
        return checksum;
    }

    public static void main(String[] args) throws Exception {
        if (args.length != 4) {
            throw new IllegalArgumentException(
                    "Usage: java ThreadCountBenchmark "
                  + "cpu|wait threads tasks iterationsOrWaitMs");
        }

        Mode mode = switch (args[0].toLowerCase(Locale.ROOT)) {
            case "cpu" -> Mode.CPU;
            case "wait" -> Mode.WAIT;
            default -> throw new IllegalArgumentException("Mode: cpu|wait");
        };
        int threads = Integer.parseInt(args[1]);
        int tasks = Integer.parseInt(args[2]);
        int work = Integer.parseInt(args[3]);
        if (threads < 1 || tasks < 1 || work < 1) {
            throw new IllegalArgumentException(
                    "threads, tasks and work must be positive");
        }

        ExecutorService pool = Executors.newFixedThreadPool(threads);
        try {
            // Warm up the pool and JVM. This is not a full JMH warmup.
            int warmupTasks = Math.min(tasks, threads * 2);
            for (int i = 0; i < 3; i++) {
                sink = runBatch(pool, mode, warmupTasks, work);
            }

            long[] samples = new long[5];
            for (int i = 0; i < samples.length; i++) {
                long start = System.nanoTime();
                sink = runBatch(pool, mode, tasks, work);
                samples[i] = System.nanoTime() - start;
            }

            Arrays.sort(samples);
            double seconds = samples[2] / 1_000_000_000.0;
            System.out.printf(Locale.US,
                    "mode=%s threads=%d tasks=%d work=%d "
                  + "median_ms=%.1f tasks_per_sec=%.1f checksum=%d%n",
                    mode.name().toLowerCase(Locale.ROOT), threads,
                    tasks, work, seconds * 1_000.0, tasks / seconds, sink);
        } finally {
            pool.shutdown();
            if (!pool.awaitTermination(10, TimeUnit.SECONDS)) {
                pool.shutdownNow();
            }
        }
    }
}
~~~

Compile:

~~~bash
javac ThreadCountBenchmark.java
~~~

Example runs from a terminal:

~~~bash
java ThreadCountBenchmark cpu 1 160 2000000
java ThreadCountBenchmark cpu 2 160 2000000
java ThreadCountBenchmark cpu 4 160 2000000
java ThreadCountBenchmark cpu 8 160 2000000
java ThreadCountBenchmark cpu 16 160 2000000

java ThreadCountBenchmark wait 1 160 20
java ThreadCountBenchmark wait 2 160 20
java ThreadCountBenchmark wait 4 160 20
java ThreadCountBenchmark wait 8 160 20
java ThreadCountBenchmark wait 16 160 20
~~~

The corresponding arguments are: **mode**, **thread count**, **task count**, and **iterations per task for CPU** or **sleep milliseconds per task for WAIT**. In each run of the same mode, keep tasks and work constant; do not directly compare CPU tasks/s with WAIT tasks/s because the unit of work differs.

The program output includes mode, threads, tasks, work, **median_ms**, **tasks_per_sec**, and checksum. Timing/throughput depend on the machine, scheduler, and JVM state, so **there are no fixed stdout numbers reliable enough to copy beforehand**. The checksum helps ensure the result values are observed and detects unexpected discrepancies, though it does not replace logic testing.

**Measurement explanation:**

1. ExecutorService creates a fixed number of workers; tasks are submitted with submit(), and results are retrieved with Future.get(). Both enqueue time and waiting for batch completion are included.
2. Three small batches warm up the pool/JIT; five measured batches use System.nanoTime(), taking the median to reduce the impact of a noisy sample.
3. For CPU, the workload is independent computation; if enough logical CPUs are available, a small thread count can speed up as thread count increases. Once the CPU is saturated, adding more threads usually does not help.
4. For WAIT, sleep intervals can overlap, so increasing thread count typically reduces total wall time significantly while the pool is small. This illustrates **hiding wait time**, not that increasing threads is always good for real I/O.
5. This experiment is an **illustrative benchmark**, still affected by startup, GC, OS scheduling, task size, thread pool, and JIT. To publish reliable microbenchmark numbers, use JMH and a controlled measurement environment.

**Notes on the code:** Thread.sleep() has OS-dependent precision and granularity; WAIT results are not exact mathematical multiples. Creating the pool outside the measurement loop reduces thread creation bias, but each process invocation still has its own JVM startup and warmup. The CPU benchmark uses repeated integer operations, so it does not simulate cache contention, databases, file I/O, or a full business workload.

## 5. Reproducible Comparison Procedure

### 5.1. Experimental Conditions

Before running, record:

- Java version (**java -version**) and JDK distribution; the number of logical processors visible to the JVM via Runtime.getRuntime().availableProcessors() (this number is affected by runtime/container configuration).
- CPU model, allocated cores/logical processors, affinity/quota, and whether the machine is bare-metal or a VM/container.
- Heap/GC flags; whether the machine is running other heavy workloads; power source/power profile and temperature when possible.
- Thread pool, task count, work size, warmup/measurement iterations, and error handling policy.
- For real workloads: external service latency, permitted connection count, batch size, buffer/queue capacity, and input rate.

Keep **total work and data source** identical when varying thread count. If measuring a workload that receives continuous requests, you must keep the **offered load** constant and also observe the queue; comparing only successful responses/s can hide drops/rejections.

### 5.2. Thread Count Series and How to Run

Start with **1, 2, 4, 8, 16** or a series around the actual logical CPU count. When throughput plateaus or drops, refine around the inflection point (for example 3, 4, 5, 6). Do not assume a single number is optimal for all modes.

Run each configuration across multiple process invocations and vary the order of configurations between runs. Keep the JDK, JVM flags, and data unchanged; record the median, p95/p99 if the workload has independent requests, variance, and sample count. If the work per task is too small, Future/queue/scheduler overhead will dominate: increase the duration of each task or switch to a more representative benchmark.

In the benchmark code above, each batch sample must finish before the next; the code does not attempt to reproduce a real request arrival rate. To evaluate a live service, use an independent workload generator, measuring latency **from the moment the request enters the system** (including queueing) as well as errors/timeouts.

### 5.3. Computing Speedup and Efficiency

For a batch with the **same total amount of work**:

~~~text
Speedup(p) = T(1) / T(p)
Efficiency(p) = Speedup(p) / p

T(p): wall-clock time when using p threads
~~~

As a **mathematical illustration**, if T(1)=8 seconds and T(4)=2.5 seconds, speedup=3.2 and efficiency=0.8 (80%). This is an example of the calculation, not measured output from the program above.

According to **Amdahl's law**, if the fraction of strictly sequential work is s and the rest is perfectly parallelizable:

~~~text
Speedup_ideal(p) = 1 / (s + (1 - s) / p)
~~~

In practice, synchronization, queues, memory, caches, and scheduling push speedup even lower than the ideal model. If one configuration has higher throughput but p99 latency spikes sharply, it may fail operational goals.

## 6. Measuring Context Switching at the OS Level

**Real context switches must be measured via the OS**. Most JVM values such as Thread.State, thread dumps, or blocked counts are supplementary information, not this counter.

### 6.1. Linux: pidstat or perf

If the sysstat package is installed, run the Java process long enough to sample and observe it (in bash):

~~~bash
java ThreadCountBenchmark cpu 16 1000 2000000 &
pid=$!
pidstat -w -t -p "$pid" 1
wait "$pid"
~~~

**pidstat -w -t** displays voluntary and involuntary context switches per second by process/thread when supported by the OS and tool version. Stop pidstat after the process finishes; it may exit when the PID no longer exists or require manual interruption. If the benchmark finishes too quickly, increase tasks so the process lives for enough intervals; do not change tasks across the thread counts you are comparing.

Depending on perf_event permissions, you can collect aggregate hardware/software counters for a command:

~~~bash
perf stat -e context-switches,cpu-migrations,task-clock \
  -- java ThreadCountBenchmark cpu 16 1000 2000000
~~~

**Context-switches** and **cpu-migrations** are counts; **task-clock** measures the total CPU time of the observed tasks. Distinguish them from the elapsed time of the entire process. Repeat each configuration with the same command and conditions; tool overhead and OS permissions may vary. On some machines perf is restricted by perf_event_paranoid or system permissions; do not change machine security settings just to run an example.

On Linux, /proc/PID/task/TID/status also contains voluntary_ctxt_switches and nonvoluntary_ctxt_switches counters depending on the kernel. To measure deltas, take two samples while the thread is still alive; **do not arbitrarily sum terminated thread IDs** or compare different snapshots without accounting for thread lifecycle.

### 6.2. Windows: Performance Monitor

Use **Performance Monitor (perfmon)** and add the counters:

- **Thread → Context Switches/sec**, filtering the instances associated with the java process being measured.
- **Process → Thread Count**, **Process → % Processor Time**, and relevant CPU/memory metrics.
- Also monitor Processor Information → % Processor Utility or other counters available on the system to observe CPU load.

Counter/instance names may be localized or differ by Windows version. Multiple concurrent Java processes make identifying by the name "java" ambiguous; identify the exact **PID** and process instance. Do not take the total counters of all system threads and attribute them to a single Java program.

You can use **jps -l** or Task Manager Details to find the Java PID and correlate it with when the process ran. To count per-thread context switches on Windows, data in Performance Monitor/WPA is usually more useful than looking at standard Task Manager alone.

### 6.3. JVM: JFR, jcmd, jstack, ThreadMXBean

Java Flight Recorder provides visibility into JVM activity, contention, blocking, and execution samples; **JFR is not an OS context switch counter by default**.

Run the benchmark with JFR enabled from startup:

~~~bash
java -XX:StartFlightRecording=filename=threads.jfr,settings=profile,dumponexit=true \
  ThreadCountBenchmark cpu 16 1000 2000000
jfr summary threads.jfr
jfr print --events jdk.ThreadPark,jdk.JavaMonitorEnter threads.jfr
~~~

The command above uses bash line-continuation syntax; in Windows PowerShell, enter the **java** command on a single line. Profile configuration and thresholds determine which events are recorded; a file without JavaMonitorEnter does not absolutely prove the application never experienced monitor contention. JFR can add a small overhead, so for quantitative comparisons you must use the same JFR configuration or measure separately without profiling.

Other tools:

- **jcmd**: find the PID and collect thread dumps/JFR from a running process; for example, jcmd PID Thread.print (replace PID with the actual ID).
- **jstack PID**: snapshots of thread stacks and states; useful for identifying WAITING, BLOCKED, lock locations, or hot stacks.
- **ThreadMXBean** via java.lang.management.ManagementFactory: reports live/peak count, thread CPU time when supported/enabled, and blocked/waited counts; not OS context switches.
- **JFR CPU samples**: show code sampled across threads, helping identify hotspots; samples alone do not tell you how many times the scheduler switched from one thread to another.

To attribute root cause, compare two time series: (1) throughput/latency/CPU, (2) context-switches/s and contention. A single number, especially one collected over a very short window, easily leads to wrong conclusions.

## 7. Interpreting Three Typical Result Patterns

### Case A: CPU-Bound Speeds Up Then Plateaus

Suppose on a machine allocated four logical processors, throughput increases clearly from 1→2→4 threads, barely increases at 8→16 threads, and the CPU is already busy. A reasonable interpretation:

- Four workers may nearly saturate the allocated computational capacity.
- Eight or sixteen workers may need to share time slices; throughput does not increase because there is no extra CPU.
- If context switches/s and CPU migrations increase while throughput stays flat or drops, this is evidence **consistent with** oversubscription, but you still need to check cache, lock contention, and GC before attributing the cause entirely to context switching.

Action: consider capping the fixed pool around the best throughput region and verify tail latency. Do not mechanically set threads equal to physical cores: SMT, quotas, CPU affinity, and the actual workload can shift the optimal point.

### Case B: WAIT Workload Speeds Up with Many Threads

With many 20ms sleep tasks, adding workers allows wait intervals to overlap. Even though context switches/s increase, wall time can still drop significantly. This is a case where **increased context switches do not mean bad performance**.

However, in real I/O, DB connection counts, response times, locks, memory, timeouts, and rate limits can become saturated. Do not infer from a sleep model that 1000 platform threads are always better than 100. Measure success/error rates, latency, queue depth, CPU, and downstream resource limits.

### Case C: Many Threads Cause Throughput to Drop Sharply

If increasing 8→32 threads keeps the CPU busy, increases switches/s, worsens latency, and lowers throughput, the cause may be:

- **Oversubscription**: too many runnable workers competing for CPU.
- **Lock contention**: synchronized/Lock turns a critical section into a sequential bottleneck.
- **Memory bandwidth/cache contention**: many threads reading/writing shared data regions, increasing misses or cache-line bouncing.
- **Excessive allocation/GC**: each task allocates many objects, causing GC to interrupt progress.
- **Queueing/oversized pool**: active requests exceed DB or device capacity, increasing retries/timeouts.

A single symptom is not enough to pick a cause. Check CPU time, blocked stacks, ThreadPark/JavaMonitorEnter, hotspot profiles, GC logs, and the corresponding OS counters.

## 8. An Additional Experiment: Detecting Contention

When a CPU benchmark produces unexpected results, compare the **same total work** in two forms:

**Form A — independent data**: each task computes on local variables and returns a single result. Do not lock shared mutable state in the hot loop.

**Form B — shared state contention**: multiple tasks update the same variable under synchronized or the same Lock. When the critical section takes up a large share of time, many threads can queue up waiting and lose parallelism.

Code snippet illustrating only the critical section, used as a **separate** test:

~~~java
private static final Object lock = new Object();
private static long sharedSum;

static void addWithLock(long value) {
    synchronized (lock) {
        sharedSum += value;
    }
}
~~~

This is not a complete benchmark program. If you put synchronized inside every loop iteration, you have **changed the workload**: increasing lock operations and memory contention, so you cannot claim the slowdown is purely due to OS context switches. Compare lock acquisitions, lock hold time, and JFR monitor events alongside context switches.

Another case is **false sharing**: threads modify logically independent variables that reside on the same cache line, causing cache coherence traffic to rise. That situation can cause poor scaling **even when context switches are not particularly high**. Analyze CPU/profile/cache metrics before blaming the scheduler.

## 9. Choosing a Practical Thread Count

### CPU-bound pool

A reasonable starting point is the number of logical processors allocated to the JVM:

~~~java
int cpuCount = Runtime.getRuntime().availableProcessors();
ExecutorService pool = Executors.newFixedThreadPool(cpuCount);
~~~

Measure around this threshold rather than treating it as a fixed truth. If there are other CPU-heavy threads outside the pool (GC, other applications, shared services), fewer workers may be needed. If limited by memory bandwidth or a critical section, adding threads may stop helping before all CPU cores are utilized.

### Blocking workload and initial estimation

An **approximate rule to choose a starting test point** when tasks are independent, homogeneous, and alternate between CPU work and waiting:

~~~text
Initial test thread count ≈ Allocated CPUs × (1 + W/C)

W: time the task spends waiting (not using CPU)
C: time the task actually spends using CPU
~~~

For example, with W/C=3 and 4 allocated logical processors, the estimate is around 16 threads; you must still measure empirically. This formula does **not** replace connection limits, queue capacity, downstream saturation, memory, or the actual degree of wait overlap. When W/C is unstable, choosing a thread count range via load testing is more reliable.

### Bounded queues and overload policies

Increasing thread count cannot fix a problem where producers submit faster than service capacity. With ThreadPoolExecutor, consider:

- Sizing the pool according to workload and CPU rather than growing unbounded.
- Using a bounded queue capacity to avoid accumulating unserved tasks.
- Defining a clear rejection/backpressure policy and metrics for rejected tasks.
- Controlling wait times, timeouts, and cancellation so stuck tasks do not hold resources forever.
- Measuring **queue wait time** and **execution time** separately, because queue waiting often degrades p99 before the CPU is saturated.

**Note on Executors.newFixedThreadPool:** this factory uses an essentially unbounded work queue. The benchmark example submits a finite batch, so it suits learning purposes; for continuous input, review ThreadPoolExecutor with a bounded queue and rejection policy instead of applying the example as-is in production.

### Java 21+ Virtual Threads

Java 21 introduces **virtual threads**, which allow running many waiting/blocking tasks in a way that uses fewer platform threads in many cases. They **do not increase the number of cores** and do not make CPU-bound computation faster just by spawning very many virtual threads. You also need to consider pinning, carrier threads, and downstream limits when measuring. The benchmark in section 4 uses a **fixed platform-thread pool as in Java 17**, so do not use its results to draw direct conclusions about virtual threads.

## 10. Common Measurement Mistakes and How to Avoid Them

1. **Running only once.** JVM warmup, JIT, GC, scheduler, thermal throttling, and background tasks cause numbers to vary. Warm up and repeat multiple times; use the median along with dispersion.
2. **Increasing total tasks at the same time as increasing threads.** When the workload is not fixed, higher throughput may simply come from larger load. Compare with the same input or the same offered load.
3. **Mistaking wall time for CPU time.** A blocking task can have high elapsed time but low CPU time. Measure both; with platform threads, total CPU time can even exceed wall time when running in parallel across multiple cores.
4. **Treating the RUNNABLE state as occupying a CPU.** A thread may be in the runqueue waiting to be scheduled or executing inside native code. Use CPU counters/samples to distinguish.
5. **Assuming every park()/sleep() equals exactly one switch.** This is not guaranteed; OS scheduling, timeouts, and state transitions can be more complex.
6. **Using context-switches/s as the sole KPI.** A program with heavy I/O wait may switch frequently while still having good throughput. Evaluate switches per **completed unit of work**, combined with latency, CPU, and error rate.
7. **Failing to define the unit of task.** A task computing 100 loop iterations is completely different from a task computing 2 million iterations; splitting tasks too small makes executor overhead dominate.
8. **Not measuring queue depth and p99.** Throughput may look fine while requests wait too long in the queue and time out. Check queue wait, latency, and rejections as well.
9. **Running configuration sweeps under different conditions.** A VM sharing CPU, a laptop switching power modes, different JDK flags, or different cached data will make conclusions unreliable.
10. **Confusing context switches with transitions from Java code to native code or JVM safepoints.** Those are different mechanisms; OS switch counts do not equal native call counts, safepoint counts, or garbage collection counts.

## 11. Result Analysis Checklist

When thread count increases, ask yourself:

1. Does throughput increase, plateau, or drop? Was batch total work kept constant?
2. How do median and p95/p99 latency change, including queue wait?
3. Does CPU saturate the **permitted** logical processors?
4. How do voluntary/involuntary switches, migrations, and scheduler wait trend? How does **switches per completed task** change?
5. Do more threads lead to monitor/lock contention, IO wait, GC, or cache bottlenecks?
6. Are pool/queue sizes, active worker counts, and downstream capacity reasonable?
7. Is the best operating point reproducible across multiple runs and in a production-like environment?

Record a structured results table:

| Threads | Median wall time | Tasks/s | CPU utilization | Voluntary switches/s | Involuntary switches/s | p99 latency (if measuring requests) | Notes |
|---|---|---|---|---|---|---|---|
| 1, 2, 4, 8, ... | From benchmark | From benchmark | From OS | From OS | From OS | From load test | Evidence-based |

The table is a **recording structure template**, not simulated results; only fill in real values after running and ensure the tools collect data over comparable time windows.

## 12. Conclusion and Self-Check Questions

**Increasing thread count** helps when it unlocks parallel processing on spare CPU capacity or allows wait times to overlap. When exceeding actual CPU/IO/lock/memory capacity, adding threads can increase scheduling, context switching, and queue wait, reducing useful processing speed.

**Context switching** is a potential source of overhead, not the default root cause. To prove its impact, compare multiple configurations on the **same workload**, record throughput/latency/CPU, and use OS counters to measure actual switches, then inspect contention/JVM behavior if scaling is poor.

Self-check:

- A CPU-bound workload with 8 threads on a 2-CPU quota has no higher throughput than 2 threads; should you increase to 16? **There is no basis for doing so from thread count alone.** Check CPU saturation, switch rate, queueing, locks, and workload.
- Why can 16 sleeping tasks finish faster than 1 worker while CPU utilization remains low? **Wait intervals can overlap**; this is concurrency while waiting, not necessarily parallel CPU execution.
- Does ThreadMXBean.getThreadCount() return the OS context switch count? **No.** Use OS tools such as pidstat/perf/Performance Monitor.
- If context switches/s increase 3× while tasks/s increase 5×, is that definitely bad? **No.** You need to examine latency, CPU, error rate, and switches/task; raw switches/s alone is not enough to conclude.
- When measuring a real application, why are p99 latency and queue depth needed? **Because good throughput can hide long waits and overload before the processing point**.

**References (JDK):** [Thread](https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/lang/Thread.html), [Thread.State](https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/lang/Thread.State.html), [ThreadPoolExecutor](https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/util/concurrent/ThreadPoolExecutor.html), [ThreadMXBean](https://docs.oracle.com/en/java/javase/21/docs/api/java.management/java/lang/management/ThreadMXBean.html), [JFR](https://docs.oracle.com/en/java/javase/21/jfapi/).

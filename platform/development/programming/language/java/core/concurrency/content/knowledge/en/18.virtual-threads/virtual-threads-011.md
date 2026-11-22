# CPU-bound workloads do not automatically get faster with virtual threads

## Lesson Objectives

After this lesson, you will be able to:

- Explain why a **virtual thread** saves the cost of holding a thread while waiting, but **does not make a CPU computation run faster**.
- Distinguish **concurrency** (multiple tasks coexisting and making progress) from **parallelism** (actually computing simultaneously across multiple processors).
- Understand the relationship between virtual threads, carrier/platform threads, CPU cores, work queues, parallelism level, and throughput.
- Choose an appropriate strategy for pure CPU tasks, I/O-heavy waiting tasks, and mixed workloads.
- Write Java 21+ examples to verify results, measure performance carefully, and recognize benchmark pitfalls.

This lesson uses only Java SE and JVM concurrency concepts.

## 1. What problem do virtual threads solve?

Java 21 made **virtual threads** a standard feature. They are still instances of `java.lang.Thread`, but are managed more lightly by the JVM and do not own a fixed OS thread for their entire lifecycle. A platform thread is typically bound to an OS thread. When a virtual thread performs a waiting operation compatible with the JVM's mechanism, it can **unmount** from its carrier thread; the carrier is then used to run another virtual thread.

Essential concepts:

| Term | Meaning |
| --- | --- |
| **Virtual thread** | A lightweight thread scheduled by the JVM, suited for workloads with many independent tasks that frequently block to wait. |
| **Carrier thread** | The platform thread currently executing a virtual thread's Java code while the virtual thread is mounted. |
| **Mount / unmount** | Attaching a virtual thread onto a carrier to run / temporarily detaching it during supported waiting operations. |
| **CPU-bound** | Most of the time is spent actually consuming CPU for computation, such as batch hashing, data transformation, compression, or numerical algorithms. |
| **I/O-bound / blocking-heavy** | Most of the time is spent waiting on sockets, databases, files, or other blocking operations; the CPU is not continuously computing while waiting. |
| **Throughput** | The number of tasks completed per unit of time. |
| **Latency** | The time a task takes from when the request starts until it finishes; this may include queuing time. |

**Virtual threads are a tool for scaling the ability to serve many waiting tasks; they are not a faster-executing version of platform threads for addition, multiplication, encryption, or computation.** When a virtual thread is busy executing a computation loop, it must still run on a carrier, and the carrier still uses an actual CPU thread.

### Concurrency vs. parallelism

Suppose a machine has 4 logical processors:

~~~text
100 CPU-bound virtual threads are created
        |
        v
JVM scheduler schedules them to run on carriers
        |
        v
CPU 0 | CPU 1 | CPU 2 | CPU 3
        |
        v
Only a limited number of tasks can actually execute on the CPU at the same time.
The remaining tasks must wait their turn or share the CPU.
~~~

The diagram above illustrates the CPU capacity limit; the actual number of carriers and how the JVM schedules them depend on the JVM version, scheduler configuration, container environment, and blocking behavior. `Runtime.getRuntime().availableProcessors()` provides the number of logical processors visible to the JVM; it does not guarantee how many computations will always run efficiently in parallel.

- **Concurrency:** 100 tasks are managed at the same time.
- **Parallelism:** if only 4 logical processors are available, you cannot turn 100 pure CPU tasks into 100 computations actually happening simultaneously just by changing the thread type.
- **I/O waiting:** when 96 tasks are waiting on I/O, other virtual threads can continue running using the freed carriers. This is a very different benefit from accelerating computation.

The right question to ask is **“is the task spending time computing or spending time waiting?”**, rather than simply “how many threads are there?”.

## 2. Why do CPU-bound workloads not automatically speed up?

### 2.1. Still constrained by compute resources

A pure CPU computation must execute a certain number of operations. Virtual threads and platform threads both use the same CPU, caches, memory bandwidth, and execution units. Switching from:

~~~java
executor.submit(this::calculate);
~~~

to:

~~~java
Thread.startVirtualThread(this::calculate);
~~~

does not change the algorithmic complexity of `calculate()`, does not increase the number of CPU cores, and does not automatically vectorize the computation. Both snippets are illustrative code; `executor` and `calculate()` must be declared in an actual program.

If there is only **one** CPU-bound task running on one logical processor, creating more virtual threads does not split **that task itself** into multiple independent parts. To utilize multiple cores, you need to partition the problem by data or task, process them concurrently, and combine the results properly.

### 2.2. Virtual threads are not “free” CPU workers

When a virtual thread computes without blocking, it holds its carrier for that entire execution segment (until it completes or reaches an appropriate transition point). Other virtual threads that need CPU must still be scheduled. Creating thousands of virtual threads to compute simultaneously:

- Does not increase total physical CPU capacity.
- Can add overhead for task creation, context switching, object management, and memory.
- Can increase cache/bandwidth contention, lock contention, or GC overhead.
- Does not guarantee lower per-task time; it can even increase latency because many tasks compete for the same CPU.

**Note:** you should not conclude that every CPU-bound workload running on virtual threads is slower. Compared to a previous platform-thread implementation that was overly constrained, the new program might run faster due to **increased parallelism**. That is the benefit of using otherwise idle CPUs, not because a virtual thread executes CPU code faster. For a fair comparison, you must compare the same work and the same actual level of parallelism.

### 2.3. Limited by the sequential portion and shared resources

Even when a program can use multiple cores, maximum speedup is still bounded by the sequential portion, synchronization operations, memory, and data transfer. According to **Amdahl's law**, if the sequential fraction is `s` and the remaining fraction can run in parallel across `p` processors:

\[
S(p) \leq \frac{1}{s+\frac{1-s}{p}}
\]

For example, if 20% of the time cannot be parallelized (`s = 0.2`), even as the number of processors grows very large, the ideal speedup cannot exceed `1 / 0.2 = 5`x; real-world coordination overhead reduces the result even further. Using virtual threads does not eliminate this sequential portion.

## 3. Runnable example: the same CPU problem on two executor types

This program counts prime numbers below 1,000,000 using 100 independent tasks, each processing a range of 10,000 numbers:

- Approach A: `Executors.newFixedThreadPool(...)` with a worker count close to the CPU count observed by the JVM.
- Approach B: `Executors.newVirtualThreadPerTaskExecutor()`, using one virtual thread per task.
- Both perform **the same computation** and must return **the same result**.
- A single timed run is only for observation. Do not treat it as a benchmark conclusion because the JVM needs warm-up, JIT compilation, CPU clock/workload can vary, and the OS schedules runs differently.

Create the file `CpuWorkloadDemo.java`:

~~~java
import java.util.ArrayList;
import java.util.List;
import java.util.concurrent.ExecutorService;
import java.util.concurrent.Executors;
import java.util.concurrent.Future;
import java.util.concurrent.TimeUnit;

public class CpuWorkloadDemo {
    private static final int LIMIT = 1_000_000;
    private static final int CHUNK = 10_000;

    public static void main(String[] args) throws Exception {
        int cpuCount = Runtime.getRuntime().availableProcessors();
        int fixedWorkers = Math.max(1, Math.min(cpuCount, LIMIT / CHUNK));

        long beginFixed = System.nanoTime();
        int fixedCount;
        try (ExecutorService pool = Executors.newFixedThreadPool(fixedWorkers)) {
            fixedCount = countAll(pool);
        }
        long fixedMillis = TimeUnit.NANOSECONDS.toMillis(
                System.nanoTime() - beginFixed);

        long beginVirtual = System.nanoTime();
        int virtualCount;
        try (ExecutorService pool = Executors.newVirtualThreadPerTaskExecutor()) {
            virtualCount = countAll(pool);
        }
        long virtualMillis = TimeUnit.NANOSECONDS.toMillis(
                System.nanoTime() - beginVirtual);

        System.out.println("Platform pool: " + fixedCount + " primes");
        System.out.println("Virtual threads: " + virtualCount + " primes");
        System.out.println("Equal results: " + (fixedCount == virtualCount));
        System.out.printf("Measured times (ms): fixed=%d, virtual=%d%n",
                fixedMillis, virtualMillis);
    }

    private static int countAll(ExecutorService pool) throws Exception {
        List<Future<Integer>> results = new ArrayList<>();
        for (int from = 0; from < LIMIT; from += CHUNK) {
            final int low = from;
            final int high = Math.min(from + CHUNK, LIMIT);
            results.add(pool.submit(() -> countPrimes(low, high)));
        }
        int count = 0;
        for (Future<Integer> result : results) {
            count += result.get();
        }
        return count;
    }

    private static int countPrimes(int low, int high) {
        int count = 0;
        for (int n = low; n < high; n++) {
            if (isPrime(n)) {
                count++;
            }
        }
        return count;
    }

    private static boolean isPrime(int n) {
        if (n < 2) return false;
        for (int divisor = 2; divisor * divisor <= n; divisor++) {
            if (n % divisor == 0) return false;
        }
        return true;
    }
}
~~~

Compile and run with **JDK 21 or later** (virtual threads have been a standard feature since Java 21):

~~~bash
javac --release 21 CpuWorkloadDemo.java
java CpuWorkloadDemo
~~~

The first three output lines are fixed:

~~~text
Platform pool: 78498 primes
Virtual threads: 78498 primes
Equal results: true
~~~

The last line has the form `Measured times (ms): fixed=<measured>, virtual=<measured>`; the two numbers vary by machine and run. This is a functional check that also introduces timing measurement—it is **not** sufficient to declare the speed of either model.

**Analysis:**

1. `countPrimes(low, high)` is a CPU-bound task with no intentional waiting on network, files, or locks.
2. `countAll` submits all 100 tasks, then retrieves the `Future` results; because `get()` runs on the `main` coordinator thread, no worker has to wait for subtasks on its own pool.
3. The fixed platform pool uses a worker count no greater than the number of logical CPUs (and no greater than the number of tasks); the virtual-thread-per-task executor allocates one virtual thread per task.
4. Both must return 78,498; if they differ, check for computation/partitioning bugs first before discussing speed.
5. If virtual threads appear faster or slower in a single run, it could be due to JVM warm-up, JIT compilation, GC, worker count, executor creation overhead, thermal throttling, or the task being too small. The order “fixed runs first, virtual runs second” also introduces bias because the code has already been progressively optimized by the JVM by the second run.

### How finely should the problem be split?

Splitting one million elements into one million tiny tasks can create more management overhead than useful computation time. Conversely, splitting into just one task fails to utilize multiple CPUs. Choose **granularity** based on work size, split/merge overhead, memory, and measured throughput. For CPU-bound work, **bounded parallelism** (a reasonable worker count with sufficiently large tasks) is usually a predictable starting point.

## 4. When do virtual threads actually help? Workloads that frequently wait

Suppose there are 24 independent requests, each needing to wait 200 ms (for example, representing an I/O operation). With a pool of 4 platform threads, they typically must be processed in multiple batches because each thread is held while waiting. With virtual threads, when `Thread.sleep` parks the virtual thread, the carrier can be used for other work.

This is a **waiting-time simulation**, not a real network or database measurement. Create `WaitingWorkloadDemo.java`:

~~~java
import java.util.ArrayList;
import java.util.List;
import java.util.concurrent.Callable;
import java.util.concurrent.ExecutorService;
import java.util.concurrent.Executors;
import java.util.concurrent.Future;
import java.util.concurrent.TimeUnit;

public class WaitingWorkloadDemo {
    private static final int TASK_COUNT = 24;

    public static void main(String[] args) throws Exception {
        long fixed = run(Executors.newFixedThreadPool(4));
        long virtual = run(Executors.newVirtualThreadPerTaskExecutor());

        System.out.printf("Measured times (ms): fixed=%d, virtual=%d%n",
                fixed, virtual);
    }

    private static long run(ExecutorService pool) throws Exception {
        long start = System.nanoTime();
        try (pool) {
            List<Callable<Integer>> tasks = new ArrayList<>();
            for (int i = 0; i < TASK_COUNT; i++) {
                tasks.add(() -> {
                    Thread.sleep(200);
                    return 1;
                });
            }
            List<Future<Integer>> futures = pool.invokeAll(tasks);
            int total = 0;
            for (Future<Integer> future : futures) {
                total += future.get();
            }
            System.out.println("Completed: " + total);
        }
        return TimeUnit.NANOSECONDS.toMillis(System.nanoTime() - start);
    }
}
~~~

Run:

~~~bash
javac --release 21 WaitingWorkloadDemo.java
java WaitingWorkloadDemo
~~~

The two lines with fixed output are:

~~~text
Completed: 24
Completed: 24
~~~

The third line prints the actual elapsed time, which varies by environment. Under light load, a pool of 4 platform workers typically needs about 6 batches of 200 ms waits (roughly 1.2 seconds plus overhead), whereas virtual threads can wait concurrently and finish in roughly one batch (around 200 ms plus overhead). This is a **concurrency benefit while waiting**, not proof that virtual threads compute CPU work faster.

**Practical limits:** network connections, connection pools, API rate limits, and databases cannot accept an unlimited number of requests. If concurrency is increased too high, external systems can become congested, time out, or suffer higher latency. Using virtual threads does not bypass business or resource limits.

## 5. Why might a CPU benchmark show virtual threads as faster?

A result such as “virtual was 3x faster on the first run” needs to be explained before drawing conclusions. Check the following:

| Symptom | Question to verify |
| --- | --- |
| Code changed at the same time as thread type | Do both versions use the same algorithm, data, task partitioning, JVM settings, and output? |
| Old pool had only 1–2 workers on a multi-core machine | Did speed increase from using more CPUs or from virtual threads? |
| Fixed ran first, virtual ran second | Did JIT compilation, class loading, allocation, and warm-up give an advantage to the later run? |
| Problem is too small | Does executor, `Future`, and submission overhead dominate the computation? |
| Machine has other load | Did background processes, CPU frequency, GC, or container quotas differ? |
| Some tasks wait on disk/network/locks | Is the workload truly CPU-bound or mixed with blocking? |
| Measuring “time to create all threads” | Did the benchmark wait for **all tasks to complete**, or only measure submission time? |
| Measuring total throughput while comparing single-task latency | Which metric is being optimized, and is queue time included? |

For example, if a program originally used `newFixedThreadPool(1)` on an 8-core machine and then switched to many virtual threads, CPU throughput could increase significantly because previously only one core was used. To analyze the cause, also compare against a **platform thread pool with an appropriate level of parallelism**. Then an advantage merely from creating more logical threads will no longer be a sufficient explanation.

### What does a proper benchmark require?

- Use **JMH (Java Microbenchmark Harness)** for microbenchmarks to handle warm-up, iterations/forks, and avoid many JVM measurement pitfalls. Never treat a single `System.nanoTime()` measurement as a conclusive benchmark.
- Ensure the program actually consumes the computed result so the JIT does not eliminate dead code.
- Test across different task sizes, task counts, and CPU parallelism levels; record the JDK version, logical processor count, container CPU quota, and memory limits.
- Inspect **CPU utilization**, throughput (tasks/sec), p50/p95/p99 latency, memory/GC, scheduling overhead, and wait time.
- Run multiple iterations after warm-up for each configuration, vary execution order or run in separate forks, and report result variance.
- Measure the right goal: does a single independent CPU task need lower latency, does a CPU batch need higher throughput, or does a mixed service need to handle many concurrent connections?

`jcmd`, Java Flight Recorder, and Java Mission Control help observe thread states, CPU samples, allocations, and blocking. Read the metrics together: for example, if CPU is already near saturation while queues are growing, adding more virtual threads is unlikely to reduce the CPU computation part.

## 6. Choosing the right executor for the workload

| Workload type | Reasonable starting point | Why |
| --- | --- | --- |
| Few tasks, each doing heavy CPU work | Direct processing or a platform pool sized to the CPU count | Utilizes limited CPUs with low task-splitting overhead. |
| Many independent CPU chunks that can be evenly split | Fixed thread pool / `ForkJoinPool` / parallel algorithm when appropriate | Controls parallelism; work-stealing helps with suitable divide-and-conquer algorithms. |
| Many requests mostly waiting on I/O | Virtual thread per task executor | OS workers do not have to be occupied throughout compatible wait times. |
| Tasks mixing CPU and I/O | Profile first, separate blocking and compute phases or bound CPU work | Prevents increasing waiting tasks from pushing the CPU into overload. |
| Depends on external services with quotas/connection pools | Virtual threads + concurrency/queue limits or backpressure | Virtual threads do not increase the capacity of external services. |
| A single sequential computation | Optimize the algorithm, data, or partition the problem properly | Simply changing thread type does not create a parallel algorithm. |

### Choosing the number of CPU workers

`Runtime.getRuntime().availableProcessors()` is a **starting point** for measurement, not an immutable optimal formula. Workloads heavy on CPU cache/memory bandwidth, SMT/hyper-threading, and container CPU limits can make the effective worker count differ from the logical processor count. A fixed platform pool for CPU-bound work limits the number of active tasks; tasks exceeding the worker count can wait in a queue. For computation that can be recursively subdivided, `ForkJoinPool` may be suitable, though profiling is still needed because a poor splitting strategy still causes overhead.

### Do not use virtual threads as an automatic CPU pool

`Executors.newVirtualThreadPerTaskExecutor()` creates a new virtual thread per task; it **does not attempt to bound the number of virtual threads to the CPU count**. For CPU-bound work, submitting millions of small tasks can allocate millions of objects, `Future` instances, metadata, and pending results, even if only a fraction are running on the CPU at once.

You should not build a “pool of virtual threads” the way platform threads are reused; the strength of virtual threads is that they are cheap to create per task. However, **cheap does not mean free**. When a data source is very large, limit the number of concurrently created tasks on the producer side, batch the work, or use an appropriate bounded executor instead of submitting unboundedly. For I/O tasks, bound concurrency according to external resources using a `Semaphore`, connection pool, and rate limiting; do not use the number of virtual threads as a proxy for backend capacity.

## 7. What happens in the scheduler and the impact of pinning

Virtual threads are scheduled by the JVM onto carrier platform threads. When a virtual thread runs non-blocking CPU code, it continues to occupy its carrier during that execution window. When it encounters a blocking operation supported by the JVM for unmounting, the carrier becomes free to do other work. The virtual thread scheduler typically has a target parallelism related to the processor count, but this is not a guarantee that all existing virtual threads run in parallel, nor is there “one dedicated CPU per virtual thread.”

**Pinning** occurs when a virtual thread cannot unmount from its carrier during a certain waiting operation; the carrier remains held, which can reduce the scalability of blocking workloads:

- **JDK 21–23:** blocking operations inside a `synchronized` block/method can pin the carrier; native/foreign code can also have pinning scenarios.
- **JDK 24 and later:** JEP 491 changes the monitor mechanism so blocking inside `synchronized` is no longer a typical cause of pinning; cases involving native/foreign interactions still require observation.
- In both eras, **CPU-bound code does not need to unmount** because it is using the CPU to compute; fixing pinning does not make the computation itself execute faster.

Do not choose APIs based on a blanket rule like “replace every `synchronized` with `ReentrantLock`” across all versions. Analyze according to your actual JDK and measure with JFR when issues arise. Avoid confusing **pinning**, **lock contention**, **CPU saturation**, and **thread starvation**: they are distinct causes, even though all of them can reduce throughput.

## 8. Protecting correctness and resources under high concurrency

When splitting a problem into many tasks, the thread type does not solve standard concurrency risks:

- **Race conditions / data races:** multiple tasks updating a shared counter without synchronization can lose updates. In the example, each task returns its own `Integer` and the coordinator thread sums the results to avoid shared writes.
- **Coordination overhead:** tens of thousands of tiny tasks can spend more time on submission, `Future`, and queuing than on computation.
- **Unbounded fan-out:** creating too many concurrent tasks can consume significant heap/metadata; control work-in-flight at the producer.
- **Blocking inside a CPU pool:** a CPU worker task waiting on a `Future`/subtask from the same saturated pool can cause thread-starvation deadlock. Use composition or wait on a coordinator thread outside the pool.
- **Cancellation:** `Future.cancel(true)` sends an interrupt signal; it does not force CPU code that ignores interrupts to stop immediately. Long-running tasks should proactively check the interrupt flag at appropriate points and clean up resources in `finally`.
- **ThreadLocal:** each virtual thread can have its own `ThreadLocal` variables, so if you create very many virtual threads, using `ThreadLocal` to cache expensive per-thread objects can bloat memory—unlike a platform thread pool that reuses a small number of workers.
- **Observability:** always measure correctness, completion time, CPU usage, and queue length; a log line saying “started 100k threads” does not tell you whether work is being processed fast or slow.

`ExecutorService` supports `close()` via try-with-resources in Java 21+, which waits for tasks to finish when closing in demos. Production applications still need proper timeout, interruption, backpressure, and lifecycle policies; a hung task can cause executor shutdown to wait longer than expected.

## 9. Practice exercises and how to interpret results

**Exercise 1 — Keep the thread type, vary parallelism.** Run `CpuWorkloadDemo` with the platform pool set to 1, 2, 4, and 8 workers (within your environment's limits). Observe whether speedup stops once the CPU limit is reached; verify that the count is always 78,498.

**Exercise 2 — Vary task size.** In `CpuWorkloadDemo`, try `CHUNK` values of 1,000, 10,000, and 100,000. Track the task count, submit/merge overhead, and work distribution; explain why both very small and very large chunks can perform poorly.

**Exercise 3 — Replace waiting with computation.** In `WaitingWorkloadDemo`, replace `Thread.sleep(200)` with a sufficiently heavy CPU computation that still returns a result. Observe how the timing benefit changes. Do not compare using a single run; set up a warm-up process and measure multiple runs.

**Exercise 4 — Spot a flawed benchmark.** Examine a measurement that only times calling `submit` without `get` or `awaitTermination`. Show that it is measuring **task submission time**, not work completion time. Fix it to have a clear completion point, identical input, and a checksum.

**Exercise 5 — Evaluate a mixed system.** Suppose a task reads data for 300 ms and then computes on the CPU for 50 ms. Explain why virtual threads can improve concurrency while waiting for data, yet do not make the 50 ms CPU phase run faster; propose limits for connections and CPU work-in-flight.

During practice, you may observe counterintuitive results on a single run because the OS and JIT are non-deterministic. Explain behavior using actual resources, measured data, and correctness checks before changing executors.

## 10. Summary for practical application

1. **Focus on the bottleneck:** is the code computing on the CPU or waiting? If it is CPU-bound, changing thread type does not add cores and does not make the algorithm faster.
2. **For CPU-bound work:** prioritize proper work partitioning, suitable algorithms, bounded parallelism, and warmed-up benchmarks; thread pool size typically starts from the CPU count visible to the JVM and is tuned by measurement.
3. **For blocking-heavy work:** virtual threads are a very useful choice for serving many waiting tasks without holding many platform threads.
4. **For mixed workloads:** analyze CPU, I/O, queues, backend capacity, and latency together; scaling virtual threads must be paired with external resource limits.
5. **Do not treat a single benchmark result as a rule:** identical input, identical work, identical conditions, sufficient warm-up, and repeated measurements are required for a valid evaluation.

**Key takeaway:** virtual threads make managing **many concurrent tasks—especially waiting tasks—**cheaper. A **CPU-bound** task still consumes real CPU resources; making it faster requires improving the algorithm, parallelizing appropriately, or adding real compute capacity.

### Java references

- [JEP 444 — Virtual Threads](https://openjdk.org/jeps/444): design goals, limitations, and usage of virtual threads.
- [Oracle Java 21 — Virtual Threads](https://docs.oracle.com/en/java/javase/21/core/virtual-threads.html): mount/unmount mechanics, thread-per-task, and suitable blocking scenarios.
- [JEP 491 — Synchronize Virtual Threads without Pinning](https://openjdk.org/jeps/491): monitor changes starting in Java 24.
- [JMH](https://openjdk.org/projects/code-tools/jmh/): microbenchmarking tool for the JVM.

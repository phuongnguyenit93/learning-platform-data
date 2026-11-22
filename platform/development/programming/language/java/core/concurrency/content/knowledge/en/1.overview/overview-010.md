# When Should You Use Sequential Execution Instead of Multithreading in Java?

## 1. Understanding the Problem Correctly

**Sequential execution** processes steps one after another on a single thread of control: the next step begins only after the previous step completes. **Multithreading** allows multiple tasks to make progress within the same time period, either truly running in parallel across multiple CPU cores or taking turns when tasks are waiting.

Multithreading is **not faster by default**. The decision depends on the size and independence of the work, the ratio of computation to I/O wait time, ordering requirements, shared state, resources, and actual measured performance.

Three concepts to distinguish:

- **Sequential:** a sequence of tasks processed in order; the code is usually easier to follow.
- **Concurrency:** multiple tasks can make progress together, even if they are not necessarily running at the exact same instant.
- **Parallelism:** computational parts actually run simultaneously across multiple cores or execution units.

A single thread can also be blocked when calling I/O. Multiple threads may also fail to speed things up if they contend for the same resource.

## 2. When Should Sequential Execution Be Preferred?

### 2.1. Small Workloads with Low Per-Task Cost

Creating or coordinating multiple threads incurs overhead: enqueuing tasks, context switching, synchronization, managing results, and memory usage. For small loops or simple calculations, this overhead can exceed the task processing time.

For example, summing a few hundred numbers, checking a small number of objects, or processing a small configuration should usually start with a sequential loop. There is no universal element-count threshold for every program: the same 1,000 elements might each be a simple addition or an expensive computation. **Measure by actual workload**, do not decide based on element count alone.

### 2.2. Steps with Dependencies

If B needs the result of A and C needs B, the three steps form a dependency chain A → B → C. Putting them onto three threads does not eliminate the dependency chain; instead, it adds waiting and result-passing mechanisms.

For example: read data → validate → compute result → update a state based on the result. Keeping dependent parts sequential makes pre/post-conditions clear. If within one step there are multiple truly independent branches, you can still split out those branches for concurrent processing.

### 2.3. Strict Ordering and Predictable Behavior Are Required

Operations that require ordered updates, state-transition chains, position-dependent algorithms, or writing to a resource in a specific order are usually easier to implement sequentially.

Sequential code has fewer execution schedules to reason about, making it convenient for reading stack traces, reproducing bugs, and testing. However, sequential execution **does not automatically guarantee** algorithm correctness, safe transactions, or that external data remains unchanged.

### 2.4. Shared Mutable State Is Hard to Synchronize

Multiple threads running `count++` on an `int` variable can lose increments because the statement consists of read, add, and write; it is not an atomic operation. `volatile` helps guarantee certain visibility rules, but **does not make `count++` atomic**.

For small workloads with low throughput requirements, sequential processing can avoid locking overhead and race risks. If multithreading is needed, consider partitioning non-shared data, immutable objects, `AtomicInteger`, synchronization, or an appropriate concurrent collection.

### 2.5. The Downstream Resource Processes One Task at a Time

If all tasks wait on the same lock, a single-threaded device, or a tightly constrained resource, having more workers does not make that resource faster. The system may only add queueing, timeouts, and memory consumption.

For example, multiple operations needing a write lock on a small piece of state: even when running on multiple threads, the protected section still executes one at a time. Find the **actual bottleneck** before increasing the thread count.

### 2.6. No Evidence That Concurrency Helps Meet the Goal

For small jobs, command-line programs, application startup, or processing small amounts of data, a sequential solution is usually a good baseline: easy to understand, less error-prone, and easy to measure. Keep this approach if it already meets the required response time, throughput, and resource usage.

This is not a "always use a single thread" rule. When a long I/O-waiting task blocks other work, or when there are large independent computation blocks, concurrent approaches should be evaluated.

## 3. Java 17+: Sequential Loop Example

Create the file `SmallSum.java`:

```java
import java.util.stream.IntStream;

public class SmallSum {
    public static void main(String[] args) {
        int[] values = IntStream.rangeClosed(1, 1_000).toArray();
        long sum = 0;

        for (int value : values) {
            sum += value;
        }

        System.out.println(sum);
    }
}
```

Compile and run:

```bash
javac SmallSum.java
java SmallSum
```

Output:

```text
500500
```

The program sums 1,000 integers sequentially in a single loop. There is no business requirement forcing it to be split into multiple tasks. Summation could be done with a parallel Stream in another problem, but for this small example there is no evidence it would be faster. **This illustrates correctness, not a performance benchmark.**

## 4. When Is Multithreading Worth Trying?

| Scenario | Starting Approach | Why |
| --- | --- | --- |
| Simple calculation on few elements | Sequential | Avoids coordination overhead |
| Directly dependent steps | Sequential for the dependent part | Another thread does not remove data dependencies |
| Shared mutable state, low load | Sequential or redesign state | Reduces races and synchronization cost |
| Many heavy, independent, sufficiently large CPU blocks | Try bounded parallelism | Can utilize multiple CPU cores |
| Many independent I/O tasks, frequently waiting | Try bounded concurrency | Can hide wait time |
| Tasks contending for a single resource | Measure bottleneck; often keep sequential | Downstream resource remains the limit |
| Need to respond to other work while a task waits | Consider splitting tasks | Avoids one task blocking the processing thread |

**CPU-bound:** most of the time is actually spent using the CPU. If there are multiple sufficiently large independent blocks and multiple cores, parallelism can be helpful; if there are too many workers relative to useful cores, CPU contention and context switching can cause slowdowns.

**I/O-bound:** most of the time is spent waiting for network, disk, or external services. Concurrency can utilize the wait intervals, but you must bound the number of connections, file descriptors, requests to services, and queue lengths.

**Mixed workload:** you need to measure processing time and wait time, CPU, memory, connection pools, timeouts, throughput, and latency. Do not choose the worker count based solely on a single CPU-bound/I/O-bound label.

## 5. Java 17+: Comparing Sequential vs. Thread Pool for Waiting Tasks

This example **simulates I/O wait** using `Thread.sleep(120)`. Four independent tasks each return a distinct string. The sleep illustrates overlapping wait time, not a real network or disk measurement.

Create the file `SequentialOrConcurrent.java`:

```java
import java.util.ArrayList;
import java.util.List;
import java.util.concurrent.ExecutionException;
import java.util.concurrent.ExecutorService;
import java.util.concurrent.Executors;
import java.util.concurrent.Future;

public class SequentialOrConcurrent {
    private static String simulateWait(int id) throws InterruptedException {
        Thread.sleep(120);
        return "job-" + id;
    }

    private static List<String> sequential() throws InterruptedException {
        List<String> results = new ArrayList<>();
        for (int id = 1; id <= 4; id++) {
            results.add(simulateWait(id));
        }
        return results;
    }

    private static List<String> concurrent()
            throws InterruptedException, ExecutionException {
        ExecutorService pool = Executors.newFixedThreadPool(2);
        try {
            List<Future<String>> futures = new ArrayList<>();
            for (int id = 1; id <= 4; id++) {
                final int taskId = id;
                futures.add(pool.submit(() -> simulateWait(taskId)));
            }

            List<String> results = new ArrayList<>();
            for (Future<String> future : futures) {
                results.add(future.get());
            }
            return results;
        } finally {
            pool.shutdown();
        }
    }

    public static void main(String[] args) throws Exception {
        List<String> a = sequential();
        List<String> b = concurrent();
        System.out.println(a);
        System.out.println(b);
        System.out.println("Ket qua tuong duong: " + a.equals(b));
    }
}
```

Compile and run:

```bash
javac SequentialOrConcurrent.java
java SequentialOrConcurrent
```

Deterministic output when all tasks complete normally:

```text
[job-1, job-2, job-3, job-4]
[job-1, job-2, job-3, job-4]
Ket qua tuong duong: true
```

The sequential version performs four wait intervals back-to-back. A thread pool with two workers allows up to two tasks to make progress at the same time; the wait intervals can overlap. The `Future` list is iterated in **task submission order**, so the results are assembled in that exact order, even though the actual completion order may differ. `Future.get()` waits for the task result and establishes a synchronization relationship so the receiving thread observes the effects of the completed task.

Do not infer from this example that multithreading will be "twice as fast." Timing depends on scheduling, pool creation time, machine load, and external resources. The example shuts down the pool via `shutdown()` after retrieving all results. In long-running applications, you also need timeout strategies, cancellation, `ExecutionException`/`InterruptedException` handling, queue bounds, partial failure handling, and pool lifecycle management.

## 6. Costs and Risks of Multithreading

**Coordination:** submitting tasks, queueing, context switching, `Future`, assembling results, synchronization. Reusing threads via a pool reduces the cost of repeatedly creating threads, but does not eliminate all overhead.

**Races, visibility, deadlocks:** unprotected writes to the same data can lose updates; locks can suffer contention or cause deadlocks if acquired inconsistently. With immutable data, sharing is safer, though contention for external resources must still be considered.

**Throughput and latency:** handling more requests/second does not mean each individual request is faster. Queueing and resource contention can worsen p95/p99 latency. You need to measure average time, tail latency, and load capacity.

**Resources:** many platform threads consume stack memory and OS resources; many concurrent tasks require more heap, connections, bandwidth, or file descriptors. Concurrency must have bounds and backpressure mechanisms when input arrives faster than it can be processed.

**Errors, timeouts, and cancellation:** when tasks run concurrently, errors can occur at various points in time; other tasks may keep running even after one task has failed. You need to define behavior for timeouts, interrupts, cancellation, partial results, and the order in which results are applied.

Java 17 can use `ExecutorService`, `CompletableFuture`, and standard JDK concurrency primitives depending on the workload. Choosing any API does not replace proving independence and measuring benefits.

## 7. Measure Before Deciding

1. **Build a correct sequential baseline:** define inputs, expected outputs, and execution time on a representative workload.
2. **Analyze dependencies:** are the tasks independent, do they update the same state, require ordering, or contend for any resources?
3. **Measure bottlenecks:** CPU/I/O wait ratio, useful CPU cores, memory, connection count, queues, throughput, p50/p95/p99 latency, and timeouts.
4. **Test bounded concurrency:** vary the worker count step by step, compare results with the sequential version, verify correctness under load, and test cancellation/recovery.
5. **Weigh total cost:** if it only reduces time slightly while making the code significantly harder to debug, manage pools, and test, the sequential solution may be better.

For parallel computation, **Amdahl's law** gives an ideal upper-bound estimate: if the parallelizable fraction is `p` and there are `k` compute units, then:

```text
Speedup <= 1 / ((1 - p) + p / k)
```

For example, `p = 0.8` and `k = 4` gives an ideal bound of `1 / (0.2 + 0.8 / 4) = 2.5` times, excluding additional overhead. The larger the sequential portion, the less effect adding workers has. This formula illustrates compute parallelism limits and does not directly predict how well I/O wait time is hidden.

Do not use a single `System.nanoTime()` run of a small example to draw JVM microbenchmark conclusions: JIT compilation, warm-up, optimizations, GC, and environmental noise all affect it. Use JMH for Java microbenchmarks (warm-up, multiple measurement iterations, representative inputs) and use load tests/real metrics for I/O systems.

## 8. Common Misconceptions and Mistakes

- **"Adding threads is always faster."** False if tasks are too small, dependent, or contend for CPU, locks, or downstream resources.
- **"Sequential is always slow."** False when doing little work or when task splitting/merging overhead exceeds the benefit.
- **"Having multiple threads means running in parallel."** The scheduler may interleave them; the number of cores and bottlenecks determine actual parallelism.
- **"`volatile` makes `count++` safe."** False, because read–modify–write is not atomic.
- **"`parallelStream()` is the default way to speed things up."** False when work is small, unevenly split, has side effects, or many tasks contend for the pool/resources.
- **"A sleep demo proves production performance."** False; `Thread.sleep` only demonstrates overlapping wait time.
- **"Tasks don't share variables, so we can create as many threads as we want."** False, tasks still share CPU, memory, connections, and service quotas.

## 9. Selection Checklist

**Choose sequential first** when tasks are small, steps depend on each other, processing order is a primary constraint, shared mutable state is hard to manage, the downstream resource executes one task at a time, or no clear benefit from multithreading has been measured.

**Consider bounded multithreading** when there are many sufficiently large and independent tasks, you can utilize CPU cores or overlap I/O wait, and you have designed worker bounds, error/timeout handling, resource control, and concurrency testing.

Start with a **correct and measurable** sequential solution, identify bottlenecks, and only increase concurrency on the independent parts that need speedup. Decide based on real workload results, not on having as many threads as possible.
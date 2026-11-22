# Concurrency in Java Applications: Use Cases and Risks

## 1. Why Do Java Applications Need Concurrency?

**Concurrency** is the way of structuring multiple tasks so they can make progress over an overlapping period of time. They may take turns on a single CPU core or actually run simultaneously on multiple cores. **Parallelism** is the case where tasks genuinely execute simultaneously; **asynchrony** is the pattern of initiating a task and receiving its result at a different point in time, without necessarily creating a dedicated thread or running in parallel.

Real-world applications typically handle multiple requests, I/O operations, and background tasks. If everything had to wait for one another in a sequential chain, waiting on network, disk, or database operations could leave CPU resources idle. Concurrency allows other work to make progress while one task is waiting; for computational problems that can be split independently, parallelism also helps utilize multiple CPU cores.

However, **adding more threads does not automatically make a program faster**. How useful it is depends on the type of task, coordination overhead, resource limits, and the load capacity of downstream systems.

### Terms to Distinguish

| Concept | Meaning | Java Example |
| --- | --- | --- |
| Task | A unit of work with its own inputs/results | `Runnable`, `Callable<T>` |
| Thread | A JVM execution thread with its own stack and scheduling | `Thread` |
| Concurrency | Multiple tasks making interleaved progress | Executor running requests/tasks |
| Parallelism | Multiple tasks genuinely running simultaneously across cores | Processing multiple independent data partitions |
| Asynchrony | Results are handled after the work completes | `CompletableFuture`, callbacks |
| Thread safety | Correctness when an object is used from multiple threads | Immutable state, locks, atomics |

An I/O-bound task and a CPU-bound task are two different kinds of workloads. You should not use a single concurrency configuration for all cases.

## 2. Suitable Use Cases

### 2.1. Serving Multiple Independent Requests

Network applications can receive many connections, calls, or messages simultaneously. In the thread pool model, independent processing tasks are handed off to a pool of worker threads; a worker finishes one task and then picks up the next. The goal is to **maintain responsiveness and throughput** when multiple users access the system concurrently.

Prerequisites: shared data must be safe, the number of queued tasks must be bounded, and dependent resources (network connections, databases, external APIs) must be able to handle the corresponding load. A system receiving 1,000 tasks does not mean it can simultaneously open 1,000 connections to every dependent service.

### 2.2. Hiding I/O Latency

Reading files, making HTTP calls, querying data, or waiting for messages often takes time due to I/O. While one task is waiting, other workers can serve other work. For example, a page aggregating independent information from services A and B can issue both calls at the same time and then wait for both.

Important condition: the two calls must be **business-independent**. If B needs the result of A, launching B in parallel may violate ordering or provide no benefit. Concurrency also does not eliminate connection limits, rate limits, timeouts, or the capacity of the target service.

### 2.3. Offloading Background Tasks from the Main Path

Controlled logging, report generation, file compression, thumbnail creation, or processing a queue are examples that can be moved off the interactive request path. The goal is to reduce the time users have to wait for work that does not need to complete immediately.

You must decide clearly: is the task allowed to be lost when the application shuts down; does it need durable persistence, retries, or guarantees against duplicate processing; when an error is reported, who monitors it? Merely calling `executor.submit(...)` does not create a durable delivery mechanism. For critical tasks, reliability must be designed at the system level.

### 2.4. Pipelines and Batch Processing

A pipeline might consist of ingesting data → validating → transforming → writing results. Stages run concurrently with a bounded queue, helping balance the rate between input sources and output sinks. Tasks that analyze multiple independent files can also be split into parts and have their results aggregated.

You must avoid the situation where an upstream stage produces data much faster than a downstream stage can consume it. When that happens, the queue grows, increasing RAM usage and latency; the solution is **backpressure** or blocking/shedding excess work, not continuing to add threads indefinitely.

### 2.5. Multi-Core CPU Computation

Problems such as analyzing large datasets, encrypting/transforming independent blocks, or computing over many elements can split tasks to use multiple cores. `ForkJoinPool`, `parallelStream()`, or an appropriate executor can be useful if each task is large enough and there is no state contention.

Speedup limits: non-parallelizable portions of work, data conversion, cache/memory bandwidth, result merging, locks, and context switches. Splitting a very small computation into thousands of tasks is often slower than running it sequentially.

### 2.6. Scheduling and Event Handling

`ScheduledExecutorService` is suitable for periodic or delayed work inside a Java process. Concurrency helps handle multiple independent events. However, an in-JVM schedule does not replace durable scheduling: if the process stops, in-memory schedules/tasks are lost; long-running tasks can also skew subsequent execution times.

## 3. When Should You Run Sequentially?

Prefer sequential execution if tasks are small, tightly order-dependent, require a simple transformation on small data, or have no significant waiting points or meaningful work to split. Running sequentially keeps reasoning and error handling simple. Only increase concurrency after there is a measurable need for **latency, throughput, or responsiveness**.

Questions before parallelizing:

1. Are the tasks truly independent and do they have a clear way to merge results?
2. Is the workload primarily CPU-bound or I/O-bound? How many finite downstream resources are involved?
3. What state is shared, who owns it, and who is allowed to write to it?
4. Are there timeouts, cancellation, queue bounds, and overload behavior?
5. Has it been benchmarked against the sequential version under the same conditions?

## 4. Common Java Mechanisms

| Tool | Role | Considerations When Applying |
| --- | --- | --- |
| `Thread` | Represents a thread of execution | Do not create unbounded new threads per unit of work |
| `Runnable` / `Callable<V>` | Describes a task; `Callable` returns a result or throws an exception | Prefer decoupling tasks from thread allocation policy |
| `ExecutorService` | Runs and manages tasks via an executor | Must be shut down in a controlled manner |
| `Future<V>` | Retrieves a result, error, or cancellation request | `get()` can block; timeouts are needed |
| `CompletableFuture` | Composes asynchronous results | `Async` variants require understanding which executor is used |
| `BlockingQueue` | Exchanges data between producers/consumers | Use bounded capacity for data streams needing backpressure |
| `synchronized` / `Lock` | Protects a shared invariant | Keep lock regions small and lock acquisition order consistent |
| `volatile` | Guarantees visibility and appropriate ordering for a single variable | Does not make `count++` atomic |
| `AtomicInteger` and atomic family | Atomic operations for single-variable state | Does not automatically protect invariants spanning multiple variables |
| `ConcurrentHashMap` | Map supporting concurrent access | Compound sequences of operations still require atomicity consideration |
| `CountDownLatch` / `Semaphore` | Coordinates completion / limits concurrent access to a resource | Do not use `Thread.sleep` to simulate synchronization |
| `ForkJoinPool` | Work-stealing for split tasks, typically CPU-oriented | Avoid long blocking I/O in compute workloads |
| Virtual threads (Java 21+) | Serves many I/O-waiting tasks using the thread-per-task model | Does not make CPU faster; still subject to external resource limits |

`ExecutorService`, `Future`, and `CompletableFuture` are all available in Java 17. **Virtual threads are an official feature starting in Java 21**; the Java 17 code snippets below do not depend on this feature.

## 5. Example 1 — Multiple Independent Tasks and Safe Result Aggregation (Java 17+)

Suppose there are three independent I/O tasks; `Thread.sleep` only **simulates wait time** so the example can run on any machine, not how real I/O is performed.

Create the file `ConcurrentWorkDemo.java`:

~~~java
import java.util.List;
import java.util.concurrent.Callable;
import java.util.concurrent.ExecutorService;
import java.util.concurrent.Executors;
import java.util.concurrent.Future;
import java.util.concurrent.TimeUnit;
import java.util.concurrent.atomic.AtomicInteger;

public class ConcurrentWorkDemo {
    public static void main(String[] args) throws Exception {
        ExecutorService pool = Executors.newFixedThreadPool(3);
        AtomicInteger completed = new AtomicInteger();

        try {
            List<Callable<String>> jobs = List.of(
                () -> {
                    Thread.sleep(80);
                    completed.incrementAndGet();
                    return "A";
                },
                () -> {
                    Thread.sleep(40);
                    completed.incrementAndGet();
                    return "B";
                },
                () -> {
                    Thread.sleep(60);
                    completed.incrementAndGet();
                    return "C";
                }
            );

            List<Future<String>> results = pool.invokeAll(jobs);
            for (Future<String> result : results) {
                System.out.println(result.get());
            }
            System.out.println("Completed: " + completed.get());
        } finally {
            pool.shutdown();
            if (!pool.awaitTermination(5, TimeUnit.SECONDS)) {
                pool.shutdownNow();
            }
        }
    }
}
~~~

Compile and run:

~~~bash
javac ConcurrentWorkDemo.java
java ConcurrentWorkDemo
~~~

Output:

~~~text
A
B
C
Completed: 3
~~~

Explanation:

- `invokeAll` submits the three tasks and waits for them to complete; the returned list of `Future`s is **in the order of the input tasks**, not the order in which tasks finish. Therefore it always prints A, B, C if the tasks complete normally.
- `AtomicInteger.incrementAndGet()` increments the counter atomically; the three tasks do not lose updates.
- `result.get()` retrieves the result or throws `ExecutionException` if the task failed. This overload of `invokeAll` waits indefinitely if a task does not finish; a timeout is needed when there is a risk of hanging.
- `shutdown()` stops accepting new tasks and lets existing tasks finish; `awaitTermination` waits with a bound. `shutdownNow()` is a request to interrupt/reclaim tasks and **does not guarantee** a task will stop if it ignores interrupts.

This example illustrates concurrency and result coordination; it does not prove that a real application will be faster. To verify, measure latency, throughput, and resource usage against a sequential version under equivalent load.

## 6. Correctness Risks: Shared Mutable State

### 6.1. Race Conditions and Lost Updates

When multiple threads read/write mutable state without synchronization, the result can depend on the interleaving order. For example, `count++` consists of reading the old value, adding 1, and writing the new value; two threads can read the same value and one increment is lost.

~~~java
// ILLUSTRATION of a bug; not a standalone program.
int count = 0;
// Two threads running concurrently:
count++; // Not atomic and not guaranteed to be thread-safe
~~~

Solutions depend on context: avoid sharing data; use immutable objects; confine ownership to a single thread; or protect updates with `synchronized`, `Lock`, or atomic classes. Do not choose a tool based on speed alone; first identify the **invariant** that must always hold (for example, the total balance across two accounts remains constant).

### 6.2. Visibility and the Java Memory Model

Sometimes thread A has written a value, yet thread B does not observe it as expected due to compiler/JIT optimizations, caches, and missing synchronization relationships. The **Java Memory Model (JMM)** defines **happens-before** relationships to specify when an action by one thread is guaranteed to be visible to another thread.

Key examples: unlocking a monitor happens-before the subsequent locking of the same monitor; a write to a `volatile` variable happens-before a subsequent read of that same variable in synchronization order; executor/`Future` mechanisms also provide specific guarantees for publishing results. `Thread.start()` and `Thread.join()` have corresponding ordering guarantees.

~~~java
// ILLUSTRATION: a simple stop flag with only one state variable.
private volatile boolean running = true;

// Another thread calls:
void stop() {
    running = false;
}

// Worker checks:
void work() {
    while (running) {
        // Perform short work, checking the flag regularly.
    }
}
~~~

`volatile` is suitable for a simple status flag when there is no multi-step invariant; it **does not** guarantee compound updates like `balance = balance - amount` or `count++`. An empty busy loop can also consume CPU: real systems typically use interruptible waiting mechanisms or coordination signals.

### 6.3. Atomicity Is Not Enough for Multi-Variable Invariants

`AtomicInteger` makes a single increment atomic, but it does not automatically ensure that two related variables stay consistent. For example, a money transfer must atomically protect checking sufficient balance, debiting the source account, and crediting the destination account under a consistent protocol. Similarly, checking `containsKey` then calling `put` on a concurrent map can still be interleaved by another thread; consider `putIfAbsent`, `compute`, or an appropriate transaction/lock.

### 6.4. Unsafe Object Publication

Passing a reference to a partially initialized object to another thread, or publishing a mutable structure without synchronization, causes reading threads to see an incomplete state. Prefer completing initialization before sharing, appropriate `final` fields, immutable values, and concurrent structures; do not let `this` escape from a constructor via callbacks or self-starting threads.

## 7. Liveness Risks: Deadlock, Livelock, Starvation

**Deadlock:** threads wait for each other in a cycle (A holds lock 1 and needs lock 2; B holds lock 2 and needs lock 1), so neither thread makes progress. Prevention: establish a consistent lock acquisition order, avoid holding locks while waiting on network/I/O, keep critical sections short, and use `tryLock` with a timeout where appropriate. Timeouts help detect or recover from some situations, but they do not fix an incorrect lock order by themselves.

**Livelock:** threads are not hard-blocked, but continuously yield or change state in response to each other so no useful work completes. Adjust retry strategies with backoff/jitter, set limits, and reconsider how progress rights are distributed.

**Starvation:** a task is repeatedly denied CPU/locks/workers because other tasks monopolize resources. For example, long or blocking tasks flood a small pool while other tasks remain stuck in the queue. Categorize workloads, bound durations, balance priorities, and measure queue wait time.

**Thread-pool deadlock:** task A occupies the only worker, submits B to the **same pool**, and calls `B.get()`; B has no worker to run on, so A waits forever. Avoid waiting on a dependent task on the same exhausted executor; consider non-blocking composition or redesigning task decomposition.

## 8. Resource and Load Capacity Risks

### 8.1. Too Many Threads or Tasks

Platform threads consume stack memory and scheduling overhead. When the number of threads exceeds demand, context switching and lock contention reduce throughput. Conversely, a pool that is too small for I/O-waiting tasks can cause the queue to grow even while the CPU is idle.

**Unbounded queues** are a distinct risk: the number of workers is fixed, but the number of waiting tasks can grow with the input rate; latency and memory balloon, eventually risking `OutOfMemoryError`. In many overload scenarios, failing fast in a controlled way is better than accumulating work indefinitely.

### 8.2. Bounded Queues and Overload Policies

An illustrative configuration (not a standalone program):

~~~java
ThreadPoolExecutor pool = new ThreadPoolExecutor(
    2, 2,
    0L, TimeUnit.MILLISECONDS,
    new ArrayBlockingQueue<>(8),
    new ThreadPoolExecutor.AbortPolicy()
);
~~~

Add imports from `java.util.concurrent` when placing the snippet above into a program. In this case, at most two tasks execute and at most eight tasks wait in the queue at the same time; when saturated and unable to accept more, `execute` may throw `RejectedExecutionException`. You must design error handling, bounded retries, or caller-side backpressure. `CallerRunsPolicy` can make the submitting thread execute the task directly, slowing down the caller; use it only after understanding what the submitting thread is serving.

Worker count and queue capacity are **operational parameters**; there is no single set of numbers right for every application. Measure these metrics: active workers, pool size, queue depth, queue wait time, rejections, task duration, CPU, memory, and end-to-end latency.

### 8.3. External Dependencies as Bottlenecks

Increasing the number of tasks calling a rate-limited API, a small database connection pool, or a slow disk usually only increases queuing and timeouts. Use a `Semaphore` or similar mechanism to bound concurrent tasks according to **downstream capacity**, while applying connection timeouts, request timeouts, and retries with appropriate backoff. Do not retry indefinitely within the same thread pool when the downstream service is already overloaded.

### 8.4. Mixing Blocking Work into a CPU Pool

A pool designed for CPU computation can run out of workers if tasks inside it wait on long I/O. When that happens, even small CPU tasks get stuck in the queue. Separate work groups by workload type and measure, or choose an appropriate execution model. With `CompletableFuture.supplyAsync(...)` without passing an executor, the default usually uses `ForkJoinPool.commonPool()`; consider a dedicated executor for blocking work to avoid affecting other parts of the code.

## 9. Timeouts, Cancellation, Interruption, and Errors

### 9.1. Timeout Does Not Mean Stopping the Task

`Future.get(timeout, unit)` only limits **how long the calling thread waits for the result**. On timeout, the underlying task may still be running. `cancel(true)` requests interrupting the running task (if any); whether it stops depends on whether the task checks/propagates interrupts and whether the API being used responds to interrupts.

An illustrative pattern for timeout handling (Java 17+):

~~~java
import java.util.concurrent.*;

public class TimeoutDemo {
    public static void main(String[] args) throws Exception {
        ExecutorService pool = Executors.newSingleThreadExecutor();
        Future<String> future = pool.submit(() -> {
            Thread.sleep(1000);
            return "done";
        });

        try {
            System.out.println(future.get(50, TimeUnit.MILLISECONDS));
        } catch (TimeoutException ex) {
            future.cancel(true);
            System.out.println("Timed out; cancellation requested");
        } finally {
            pool.shutdownNow();
        }
    }
}
~~~

Compile/run:

~~~bash
javac TimeoutDemo.java
java TimeoutDemo
~~~

While the task is still waiting on `Thread.sleep(1000)`, the typical output is:

~~~text
Timed out; cancellation requested
~~~

This is a typical outcome, **not an absolute scheduling guarantee**: after an unusual scheduling delay, the task could finish before the calling thread executes `get`. Timing and cancellation behavior in real programs must be verified. `shutdownNow()` also only attempts to interrupt; it is not a forceful thread-killing operation.

### 9.2. Handling Interrupts Properly

When a blocking operation throws `InterruptedException`, the thread is being requested to stop or transition state. If the exception cannot be propagated, you should usually restore the interrupt flag via `Thread.currentThread().interrupt()` and exit work safely. Do not swallow the interrupt and continue an infinite loop.

~~~java
// ILLUSTRATION inside a Runnable, not a standalone program.
try {
    queue.take();
} catch (InterruptedException ex) {
    Thread.currentThread().interrupt();
    return;
}
~~~

### 9.3. Task Errors and Cancellation Scope

With `submit`, an exception inside a task is stored in the `Future` and typically observed via `get()` as an `ExecutionException`; if the `Future` is ignored, business errors may not be handled as intended. With `CompletableFuture`, observe the exceptional branch and decide whether to fall back or propagate the error. When one branch of a group of tasks fails, decide whether the remaining branches should be canceled or allowed to continue.

Do not configure timeouts only at the caller layer. You must align the **end-to-end processing deadline** and per-step budgets; three sequential 5-second waits can add up to 15 seconds of latency. Retries must be bounded, conditional, and aligned with the idempotency of the operation.

### 9.4. Controlled Application Shutdown

When stopping task intake, transition the executor to `shutdown`, wait for current tasks up to a limit, and only then call `shutdownNow` if needed. Know whether incomplete tasks are persisted for replay or not. Do not rely on JVM shutdown to automatically finish or save tasks that exist only in memory.

## 10. Thread Safety, Context, and Dependent Work

Not every Java object is safe to share across threads. Check the API contract: many types such as `String` are immutable; standard collections such as `ArrayList` do not guarantee thread safety when read and modified concurrently from multiple threads. Use concurrent structures or confine access appropriately.

`ThreadLocal` binds data to a **specific thread** and does not automatically propagate values to another worker thread. Thread pools reuse workers, so data from a previous request can accidentally remain if you forget `remove()`. For information such as correlation ID, user context, or locale, pass it explicitly via parameters/context objects or use a propagation mechanism with a clear contract; never assume the calling thread's context will automatically reach a new task.

Correctness also depends on business ordering: if task B needs task A to finish, express the dependency explicitly (bounded waiting, composing `CompletableFuture`, or a sequential pipeline) rather than relying on thread scheduling order. In operations with side effects (writing files, sending requests, updating data), retries/cancellations can cause duplicate processing; design idempotency and transaction boundaries appropriately.

## 11. Virtual Threads in Java 21+: When to Use Them?

Virtual threads are managed by the JVM with lower creation and blocking overhead than platform threads for many blocking I/O tasks. They are a good fit when you want to write readable, synchronous-style code while serving a large number of tasks that frequently **wait on I/O**.

A short example specifically for Java 21+ (API illustration, not for Java 17):

~~~java
try (var executor = Executors.newVirtualThreadPerTaskExecutor()) {
    Future<String> future = executor.submit(() -> "result");
    System.out.println(future.get());
}
~~~

Import `java.util.concurrent.Executors` and `java.util.concurrent.Future` when using this snippet in a complete class. Virtual threads do not increase core count, do not make a CPU-bound algorithm faster, and do not raise database/API connection limits. Do not use a small pool of virtual threads as a mechanism to throttle resource access: use a `Semaphore` or explicit resource limits. You should also measure blocking overhead, pinning, and library compatibility on the target JVM version.

**Scope note:** The Java concurrency patterns here do not depend on Spring; configuring executors/async in Spring belongs in a separate chapter.

## 12. Design, Testing, and Observability

### Design Before Coding

1. **Define measurable goals:** throughput, p95/p99 latency, concurrent requests, or batch completion time.
2. **Classify tasks:** CPU-bound, I/O-bound, blocking or non-blocking, ordered/dependent or independent.
3. **Inventory shared state:** which objects are immutable, which belong to a single thread, and which invariants must be preserved with locks/atomics/transactions.
4. **Set bounds:** worker concurrency, queue capacity, connection limits, deadlines, retry budgets, and rejection policies.
5. **Define the lifecycle:** task success, failure, timeout, interrupt, cancellation, shutdown, restart, and replayability.
6. **Measure under realistic load:** compare sequential vs. concurrent versions, monitoring JVM and dependent service resources.

### Valuable Tests

- Create many tasks updating the same state and verify **invariants** (not just that the program throws no exceptions).
- Use `CountDownLatch` or a barrier to actively start threads at the same time; repeat stress tests across many interleavings.
- Simulate slow dependencies, errors, timeouts, full queues, interrupted tasks, and mid-flight shutdowns; verify fallbacks, remaining tasks, and rejection behavior.
- Run measurements long enough with proper JVM warm-up; distinguish latency, throughput, and CPU, and avoid drawing performance conclusions from a single run.
- For hard-to-reproduce bugs, collect thread dumps, Java Flight Recorder (JFR) recordings, logs with correlation IDs, and pool/queue/lock metrics. Inspect thread states and lock owners to identify wait chains.
- Avoid writing tests that rely on `Thread.sleep(100)` assuming "long enough for the other thread to finish"; the scheduler does not guarantee this. Use synchronization primitives or bounded waits.

### Symptoms Worth Investigating

| Symptom | Hypothesis to Check | Diagnostic Direction |
| --- | --- | --- |
| Intermittent wrong results | Race condition, unsafe publication, unprotected invariant | Stress tests, review shared mutable state / JMM |
| Hanging requests despite low CPU | Deadlock, intra-pool dependency, downstream blocking | Thread dump, call stack, lock/wait graph |
| Latency rises with load | Unbounded queue, saturated downstream resources | Queue depth, wait time, connection-pool metrics |
| High CPU without throughput gain | Contention, context switching, retry loop/livelock | CPU profiling, JFR, retry counters |
| Lost or silently failing background tasks | Ignored `Future`, abrupt shutdown, in-memory-only jobs | Error logs, task lifecycle, persistence design |
| Mixed-up request data | Uncleaned `ThreadLocal`, improper shared state | Check propagation and `remove()` |

## 13. Common Mistakes and Final Checklist

- **"More threads means faster"** — false when overhead, lock contention, and downstream limits dominate.
- **"Using volatile makes it thread-safe"** — false for compound updates or multi-variable invariants.
- **"Concurrent collections make the entire business flow atomic"** — false if the business logic consists of multiple separate operations.
- **"get(timeout) kills the task"** — false; it only limits the caller's wait time.
- **"Submitting a task automatically gives retries/durability"** — false; an in-memory executor does not guarantee durable persistence.
- **"The executor manages its own lifecycle"** — false; the application must define shutdown and observe errors.
- **"Virtual threads solve every concurrency problem"** — false; races, deadlocks, and resource limits still exist.

Before taking concurrency into production, confirm that: tasks are business-independent; shared state has a clear protection mechanism; queues/workers/downstream calls are bounded; every waiting call has a deadline; errors and interrupts are handled; shutdown is planned; and performance metrics and bottleneck signals are observable.

**Learning takeaway:** Concurrency is a tool for improving responsiveness and resource utilization when multiple tasks can make independent progress. The greatest value comes from **choosing the right use case, setting the right bounds, and preserving correctness under every execution order**.
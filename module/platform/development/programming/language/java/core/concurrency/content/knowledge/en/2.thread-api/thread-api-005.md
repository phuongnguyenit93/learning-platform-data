# Platform Threads and Resource Creation Cost in Java

## 1. Objectives and Scope

After this lesson, you will be able to explain how a platform thread maps to an operating system execution thread; distinguish between a `Thread` object, a native thread, and a CPU core; identify the sources of cost when creating, maintaining, scheduling, blocking, and destroying threads; choose ways to bound concurrency for Java applications; and measure before optimizing. The content focuses on **Java SE and the JVM**, with examples compatible with **Java 17+**.

Core question: why can creating one platform thread per task work well for a few dozen tasks, yet become a burden when thousands of requests are simultaneously waiting on I/O?

## 2. What Is a Platform Thread?

In common JVMs such as HotSpot, a **platform thread** is a Java thread mapped by the JVM closely to a **one Java platform thread ↔ one native OS thread** model. The operating system allocates resources and schedules native threads onto logical CPUs. The JVM manages Java semantics: code execution, `Thread` state, interrupts, the Java Memory Model, stack traces, and interaction with the garbage collector.

Three concepts to keep separate:

| Component | Role |
|---|---|
| `java.lang.Thread` object | A Java object on the heap used to identify and control a thread (`start`, `join`, `interrupt`, `getState`...). |
| Native/platform execution thread | An execution context backed by the JVM/OS, with its own stack and scheduling state; created when the thread is actually started. |
| CPU core / logical processor | A processing resource capable of executing code at a given moment. The number of threads can be much larger than the number of cores; only a subset of threads run concurrently on the CPU. |

For a new `Thread` object, `new Thread(runnable)` **does not yet** create a running execution thread. Calling `start()` asks the JVM to start a new thread and invoke `run()` on that thread. Calling `run()` directly is just a normal method call on the current thread.

Java states such as `NEW`, `RUNNABLE`, `BLOCKED`, `WAITING`, `TIMED_WAITING`, and `TERMINATED` describe the lifecycle observed from Java. **`RUNNABLE` does not guarantee active CPU usage**: it may be running or ready and waiting for the OS scheduler. Java's `Thread.State` is not a one-to-one mirror of every native scheduler state.

## 3. What Resources Does a Platform Thread Consume?

Creating a platform thread does more than allocate a Java object. Actual costs vary by JVM, operating system, CPU architecture, runtime flags, and how the application uses threads.

| Resource Source | When It Occurs | Significance |
|---|---|---|
| `Thread` object and related data on the Java heap | Object instantiation and linking management structures | Increases the number of objects to track/collect; the object itself does not reflect the full cost. |
| Native thread and OS/JVM management structures | When `start()` successfully creates an execution thread | Incurs creation/destruction cost and counts toward OS/runtime native thread/process limits. |
| Per-thread stack | When the native thread is initialized | Holds local variables, method calls, return addresses, and Java/native frames; consumes address space and physical memory as pages are touched. |
| TLS/`ThreadLocal` data and execution context | While the thread is active or when the application attaches data | Can retain references longer than expected, especially in a thread pool. |
| CPU scheduling time | When many threads are ready to run | The OS must distribute execution time; frequent context switches can degrade cache locality. |
| Runtime interactions (GC, safepoints, stack inspection...) | When the JVM needs to traverse or coordinate with threads | Higher thread counts and live frames can increase management/inspection overhead. |

### Stack: Reserved Size vs. Actual RAM Used

Each platform thread has its own stack, not shared with other threads. The JVM/OS typically **reserves a virtual address space region** for the stack; the number of bytes touched or actually committed can be smaller than the reserved amount. Do not equate **reserved virtual memory** with **resident physical memory (RSS)**.

Depending on the JVM/platform, the `-Xss` option can adjust the stack size of a Java platform thread. For a **hypothetical** example, if each stack is reserved 1 MiB, 10,000 threads could correspond to roughly 10,000 MiB (approximately 9.77 GiB) of **address space reserved for stacks**; this is **not a claim** that the process has consumed 9.77 GiB of RAM. Default sizes, guard pages, reserve/commit behavior, and memory limits all depend on the environment.

A stack that is too small increases the risk of `StackOverflowError` on deep call stacks. A stack that is too large increases resource reservation cost, limiting how many threads can be created. Therefore, do not choose `-Xss` based solely on theoretical multiplication.

### Even Waiting Threads Consume Resources

A platform thread waiting on a socket, file, lock, `Condition`, or `sleep` typically **does not continuously burn CPU while waiting**; however, it still owns a thread context, stack, and associated structures. A high ratio of wait time causes the "one platform thread per request" model to require a large number of threads without a corresponding increase in CPU throughput.

A thread in `BLOCKED` waiting to enter `synchronized` differs from a thread in `TIMED_WAITING` due to `Thread.sleep(...)` or `Object.wait(timeout)`. All three cases still hold onto thread resources while doing no useful CPU work. Specific states help diagnose the cause of waiting; do not use thread count alone to conclude an application is bottlenecked.

## 4. What Do Thread Creation and Context Switching Cost?

A lifecycle may include:

1. Creating the `Thread` object and binding a `Runnable` or `run()` logic.
2. `start()` requesting the JVM/OS to initialize the native thread, stack, and control data.
3. The OS placing the thread into the scheduling queue; the thread executes `run()` when given CPU time.
4. The thread may run, wait on I/O/locks, be woken up, and be swapped on and off the CPU many times.
5. When `run()` finishes, the thread reaches `TERMINATED`; native resources are released according to runtime/OS mechanisms, while the Java object is only garbage-collected when no references to it remain.

There is **no single fixed millisecond number** for `start()` or a context switch across all machines. Thread creation incurs latency, memory, and kernel work; context switching also requires saving/restoring context, which can lose cache locality and cause scheduler contention. The severity of the impact grows when there are far more `RUNNABLE` threads than actually available CPUs.

Distinguish two problems:

- **Creating too many threads**: consumes native resources, stacks, and creation/destruction time, easily hitting environment limits.
- **Having too many threads competing for CPU**: increases scheduling and context switching, which can reduce throughput even when the work per thread is unchanged.

Threads waiting on I/O do not necessarily cause continuous context switches; conversely, thousands of threads running CPU loops simultaneously can overload the scheduler. Rely on profiling and real workloads to tell them apart.

## 5. Java 17+ Example: 12 Tasks, 3 Platform Workers

This example creates **12 tasks** that simulate waiting time while using at most **3 platform threads** in a pool. A `ThreadFactory` names and counts the exact number of workers created. A bounded queue (`ArrayBlockingQueue`) makes the task acceptance capacity explicit.

Save the file **PlatformThreadCostDemo.java**:

~~~java
import java.util.concurrent.ArrayBlockingQueue;
import java.util.concurrent.CountDownLatch;
import java.util.concurrent.ThreadFactory;
import java.util.concurrent.ThreadPoolExecutor;
import java.util.concurrent.TimeUnit;
import java.util.concurrent.atomic.AtomicInteger;

public class PlatformThreadCostDemo {
    public static void main(String[] args) throws InterruptedException {
        int taskCount = 12;
        int workerCount = 3;
        AtomicInteger createdWorkers = new AtomicInteger();

        ThreadFactory platformFactory = job ->
                new Thread(job, "platform-worker-" +
                        createdWorkers.incrementAndGet());

        ThreadPoolExecutor pool = new ThreadPoolExecutor(
                workerCount,
                workerCount,
                0L,
                TimeUnit.MILLISECONDS,
                new ArrayBlockingQueue<>(taskCount),
                platformFactory,
                new ThreadPoolExecutor.AbortPolicy()
        );

        CountDownLatch finished = new CountDownLatch(taskCount);

        for (int i = 0; i < taskCount; i++) {
            pool.execute(() -> {
                try {
                    // Simulate waiting work, not measuring throughput.
                    Thread.sleep(40);
                } catch (InterruptedException interrupted) {
                    Thread.currentThread().interrupt();
                } finally {
                    finished.countDown();
                }
            });
        }

        finished.await();
        pool.shutdown();
        boolean terminated = pool.awaitTermination(1, TimeUnit.MINUTES);

        System.out.println("tasksCompleted=" +
                (taskCount - finished.getCount()));
        System.out.println("platformWorkersCreated=" +
                createdWorkers.get());
        System.out.println("executorTerminated=" + terminated);
    }
}
~~~

Compile and run with JDK 17 or later:

~~~bash
javac PlatformThreadCostDemo.java
java PlatformThreadCostDemo
~~~

Output under normal execution conditions (no native thread allocation errors or external interruptions):

~~~text
tasksCompleted=12
platformWorkersCreated=3
executorTerminated=true
~~~

**How it works:**

- The first three `execute(...)` calls cause `ThreadPoolExecutor` to initialize all three core workers; subsequent tasks enter the queue with capacity 12, which is enough for this example. It does not create one thread per task.
- Each worker picks up and processes multiple tasks sequentially. `sleep(40)` yields the CPU so the scheduler can run other work during the wait, but **the worker remains an existing native thread**.
- `CountDownLatch` makes the completed task count independent of execution order; the code does not infer runtime or performance from `sleep`.
- `finally` ensures the latch counts down even if the task is interrupted. In real tests, tasks need a cancellation/interrupt handling policy aligned with business requirements.
- `shutdown()` stops accepting new tasks and lets already-accepted tasks complete; `awaitTermination(...)` waits for the pool to finish. In real applications, timeout scenarios and controlled shutdown mechanisms must be handled.

The example **demonstrates worker reuse and bounding worker count**; it does not precisely measure OS thread creation cost, stack memory, or task processing performance. Serious benchmarks require sufficient load, warmup, multiple iterations, bounded concurrency, and observation of CPU, RSS, GC, latency, and throughput.

## 6. Platform Thread Management Strategies

### Create per Task or Use a Thread Pool?

**One thread per task** is simple conceptually, but the thread count can grow with the number of concurrent tasks. For a small number of independent, long-lived tasks, this design can be suitable; for high request volumes, resources are hard to control.

A **thread pool** reuses a group of platform threads to execute many tasks. It helps bound the number of native threads created and reduces continuous creation/destruction overhead. However, a pool **does not solve overload by itself** if the queue grows unboundedly or tasks hold locks/wait indefinitely.

The parameters must be understood together:

| Component | Decision |
|---|---|
| `corePoolSize` / `maximumPoolSize` | Limits the number of platform workers depending on configuration and pool state. |
| Bounded queue | Limits the number of waiting tasks; when full, a rejection policy or input throttling must take effect. |
| `RejectedExecutionHandler` | Handles tasks that cannot be accepted: `AbortPolicy` throws `RejectedExecutionException`; `CallerRunsPolicy` can run the task on the submitting thread, creating backpressure. |
| Task timeout, cancellation, interrupt | Prevents holding workers indefinitely and enables controlled stopping. |
| `shutdown` / `awaitTermination` / `shutdownNow` | Manages pool lifecycle and handles running/pending work. |

**Warning about rejection policies:** `CallerRunsPolicy` runs tasks on the caller when the pool is still active and saturated; this can slow down or block the request-accepting thread itself, so context must be weighed. `AbortPolicy` requires the caller to handle `RejectedExecutionException`. With an unbounded queue such as the default `LinkedBlockingQueue` in `Executors.newFixedThreadPool(...)`, the worker count is fixed, but the number of queued tasks can still grow very large. Even with a bounded queue, you must define how to respond and recover when the system is overloaded.

**Examples of choosing worker counts by workload type:**

- **CPU-bound:** When tasks are mostly computation with little waiting, a reasonable starting point is near the number of logical CPUs actually allocated to the process; then benchmark. Adding more threads does not create more CPU cores.
- **I/O-bound:** Tasks with long waits can achieve better throughput with more workers than CPUs, but native threads still have a cost. Measure wait ratio, external service latency, connection counts, and resource limits; do not increase workers indefinitely.
- **Mixed workloads:** Separate pools for CPU work and blocking work when latency isolation is needed; monitor queues, rejections, and saturation instead of applying the same pool size to everything.

A rough estimation formula can be used for steady workloads: **N ≈ P × (1 + W/C)**, where P is the number of usable CPUs, W is the average wait time, and C is the average CPU time per task. This is only a **starting heuristic**, not a guarantee of optimality: external service limits, memory, lock contention, burst traffic, and SLOs are often as important as or more important than the formula. If C is near 0, the formula loses practical meaning; measure and set a clear ceiling.

### Backpressure Is Different from Just Adding Threads

Suppose 200 requests/second arrive, but the backend can only process 100 requests/second stably. Increasing the pool can overload the backend faster; an unbounded queue will accumulate waiting work, increase latency, and eventually risk running out of memory. A responsible solution needs to bound admission, wait time, timeouts, and overload responses (bounded waiting, slowing down the sender, or controlled rejection). The pool is only one component of throttling.

## 7. Diagnosing and Measuring Costs Accurately

Signals worth observing together:

1. **Thread counts:** live threads, peak thread count, daemon threads, workers per pool, and native threads of the process.
2. **Wait states:** ratio of `RUNNABLE`/`BLOCKED`/`WAITING`/`TIMED_WAITING`, repeated thread dumps to spot persistent states.
3. **CPU and scheduler:** CPU usage, load, context switches, runnable thread count, lock contention level.
4. **Memory:** heap, native memory, RSS, virtual address space, stack reservation/commit, and OS/container limits.
5. **Business load:** throughput, p50/p95/p99 latency, queue depth, task wait time, rejected tasks, connection counts, and timeouts.

**In Java**, basic metrics can be obtained via `java.lang.management.ThreadMXBean`:

~~~java
import java.lang.management.ManagementFactory;
import java.lang.management.ThreadMXBean;

public class ThreadMetricsDemo {
    public static void main(String[] args) {
        ThreadMXBean threads = ManagementFactory.getThreadMXBean();
        System.out.println("live=" + threads.getThreadCount());
        System.out.println("peak=" + threads.getPeakThreadCount());
        System.out.println("daemon=" + threads.getDaemonThreadCount());
    }
}
~~~

Save as **ThreadMetricsDemo.java**, run `javac ThreadMetricsDemo.java` then `java ThreadMetricsDemo`. The numbers vary by JVM and timing, so **there is no fixed stdout**. `ThreadMXBean` counts live Java threads as defined by the API; it does not replace OS native thread counters or memory measurements.

**Practical tools:** With a JDK that includes `jcmd`, `jcmd <pid> Thread.print` captures a thread dump; Java Flight Recorder (JFR) supports profiling, allocation, and wait/lock analysis when appropriate events are configured. HotSpot Native Memory Tracking (NMT), if enabled at startup with `-XX:NativeMemoryTracking=summary`, can inspect JVM memory breakdown via `jcmd <pid> VM.native_memory summary`; this feature has overhead and does not equal total RSS. On Linux, OS tools like `top -H -p <pid>` or `ps -L -p <pid>` help view native threads. Syntax and availability depend on the JDK/OS.

To avoid misreading metrics:

- **Many `WAITING` threads:** may simply be an idle pool and not a bug; examine queue, demand, and latency.
- **Many `BLOCKED` threads:** inspect lock/monitor contention points and critical section length.
- **Many `RUNNABLE` threads with saturated CPU:** check for oversubscription and CPU contention.
- **RSS growing as more threads are created:** do not automatically attribute all of it to stacks; cross-check heap, native memory, and thread count.
- **`OutOfMemoryError: unable to create native thread`** (or equivalent message): check thread count, OS/container limits, stack size, native memory, and allocation policies; simply increasing the heap usually does not fix the root cause.

If benchmarking thread creation cost, separate at least three scenarios: (a) creating and joining a finite number of threads in batches; (b) many tasks through a fixed pool; (c) blocking load with controlled concurrency and timeouts. Warm up the JVM, measure multiple runs, report JDK/OS/CPU configuration, task counts, throughput, and tail latency; do not compare based on a single run or synthetic `sleep` numbers.

## 8. Common Design Mistakes

**1. Equating a `Thread` object with a running native thread.** `new Thread(...)` only creates the object; `start()` is what requests concurrent execution. Calling `start()` a second time on the same `Thread` throws `IllegalThreadStateException`. A completed thread cannot be restarted; to reuse **workers**, use an executor.

**2. "One request = one platform thread" in every situation.** When many requests wait on I/O simultaneously, native resources grow sharply. Designs should bound concurrency, queues, and timeouts according to system capacity, or consider another concurrency model when appropriate.

**3. Treating a thread pool as a free resource.** A fixed pool caps the worker count, but an unbounded queue and stuck tasks still cause memory/latency problems. Both queue wait time and rejections must be measured.

**4. Ignoring interrupts and shutdown.** `Thread.interrupt()` is a cooperative signal, not an instant thread "kill". `sleep`/`wait`/`join` can throw `InterruptedException`; when not handled fully, you usually need to restore the interrupt flag with `Thread.currentThread().interrupt()` and then exit or return the decision to the caller.

**5. Storing large data in `ThreadLocal` within a pool.** Long-lived workers can retain data across tasks; you must call `remove()` in a `finally` block when the scope of use ends. Avoid leaking request data or classloader references across thread reuse.

**6. Relying on `Thread.setPriority(...)` to fix performance bugs.** Priority semantics depend on the OS/JVM and are not a mechanism that guarantees fairness, deadlines, or throughput. Measure the scheduler and design load handling first.

**7. Misusing daemon threads for critical work.** The JVM can exit when only daemon threads remain; do not rely on daemon threads to finish data writes, transactions, or orderly shutdown.

**8. Tuning `-Xss` arbitrarily.** Shrinking the stack can break deep-call workloads; increasing the stack can reduce the number of available native threads. You must check stack depth, memory limits, and actual errors in the deployment environment.

## 9. Platform Threads and Virtual Threads: Important Connection

Since **Java 21**, virtual threads are an official feature, allowing many lightweight Java threads to be scheduled by the JVM onto a smaller number of platform carrier threads. For many workloads that are primarily **I/O-bound**, virtual threads can significantly reduce the cost of dedicating a native thread per task; however, they **do not turn CPU cores into an infinite resource** and do not automatically solve limited backends or connection pools.

Platform threads remain important for running CPU-bound code, serving as carriers for virtual threads, and executing controlled executors. Do not claim "virtual is always faster than platform": measure throughput/latency in real workloads, and distinguish high concurrency due to waiting from true CPU parallelism. When working with JDK 17, virtual threads are not available as a standard feature; the examples in this lesson use platform threads.

## 10. Practical Checklist

Before deciding to create many platform threads, ask yourself:

- Is the work CPU-bound or waiting on I/O/locks? How much time is spent waiting?
- At most how many tasks should run concurrently, how many can be queued, and how should the system respond when full?
- Are timeouts, interrupts, cancellation, and shutdown clearly defined?
- How are queues, thread count, stack/native memory, CPU, context switches, and p95/p99 latency being measured?
- Has the worker count been tested under target load, traffic spikes, and real container/OS limits?

**Key takeaway:** A platform thread is an execution unit tied to a native OS thread and therefore carries its own resource cost. Waiting threads may use little CPU, but they are not free; increasing thread count beyond need does not mean faster execution. Reusing workers, bounding concurrency and backpressure, and measuring with real metrics are the foundation for operating Java concurrency reliably.

# Choosing Pool Size for CPU-bound and I/O-bound Workloads in Java

## 1. Why is pool size a system capacity decision?

In the Executor Framework, a thread pool reuses worker threads to process multiple tasks. The number of workers directly affects **throughput** (tasks completed per second), **latency** (response time), CPU utilization, memory, context switching, and wait queues.

- **Too few threads:** the CPU may sit idle while workers are waiting on I/O; tasks have to wait in the queue even when the system still has processing capacity.
- **Too many threads:** CPU tasks compete for the same processing cores, increasing context switching, stack memory, GC, and lock contention. For I/O, too many concurrent requests can also bottleneck the connection pool, database, or downstream services.
- **Right-sized:** keeps useful resources busy at the target level while keeping queues bounded and respecting dependency capacity limits.

**There is no single pool size that works best for every application.** Formulas are only a starting point. The final value must be validated against representative load, allocated CPU, blocking behavior, latency, and downstream limits.

## 2. Identifying task characteristics

| Characteristic | CPU-bound | I/O-bound |
|---|---|---|
| Most of the time spent | Executing computation on the CPU | Waiting on file read/write, network, JDBC, remote service, etc. |
| Typical bottleneck | Number of CPU cores and scheduling overhead | I/O latency and external resource limits |
| Increasing threads past threshold | Little throughput gain, may become slower | Can hide wait time until hitting another limit |
| Examples | Data compression, hash calculation, image transformation, numerical computation | Blocking file read, blocking HTTP call, JDBC query, waiting on socket |

A task can have a **mixed workload**: parsing JSON on the CPU, calling a service over the network, and then processing the data further. Measure the **CPU execution** portion and the **waiting** portion within the same task lifecycle, rather than labeling it by method name. A database query both consumes CPU on the server and causes the client-side Java thread to wait on I/O; those two resources must be evaluated separately.

Distinguish further:

- **Blocking:** the worker thread is occupied while waiting, for example Thread.sleep, blocking socket read, or Future.get. That thread cannot run other tasks.
- **Non-blocking/asynchronous I/O:** the thread can serve other work while I/O has not yet completed. Do not apply blocking thread pool formulas directly to an event loop.
- **Lock contention:** threads waiting on a monitor/lock do not do useful CPU work, yet increasing the number of workers may not help; investigate the cause of contention first.

## 3. CPU-bound: start near the actual available CPUs

Let **N** be the number of effective logical processors that the Java process is allowed to use, **U** be the target CPU utilization (0–1), and **P** be the number of workers running independent computational tasks. A commonly used starting point is:

**P ≈ N × U**, then measure and tune, typically testing around **N** workers.

For example, if the process can actually use 8 logical CPUs and the target CPU utilization is around 80–90%, try around 6–8 compute workers. This is an **experimental range**, not a strict rounding rule; the CPU also serves GC, the runtime, other threads, and co-located services.

If all tasks are always runnable and CPU-consuming, increasing from 8 to 80 workers on a machine with only 8 logical CPUs of capacity creates no additional CPU resources. It typically increases the run queue, context switching, and cache contention while throughput saturates.

**Be careful when determining N:**

1. Runtime.getRuntime().availableProcessors() is a convenient signal, but verify it against container CPU quota/cpuset, JVM configuration, and the number of CPUs actually allocated. The effective CPU limit may differ from the host's physical CPUs; JVM version and container awareness settings also affect the returned value.
2. Logical CPUs from SMT/Hyper-Threading do not mean each CPU has the capacity of an independent physical core. Benchmark with real tasks.
3. If multiple CPU-bound pools share the same JVM, do not allocate **N CPU-saturating workers to each pool** as if each pool had N dedicated cores.
4. Work involving synchronized, JNI, heavy allocation/GC, or memory access often does not scale linearly with thread count; profile to find the real limit.

## 4. Blocking I/O-bound: account for wait time

Let:

- **N:** effective CPU capacity.
- **U:** target CPU utilization, for example 0.8.
- **C:** average CPU time consumed by one task.
- **W:** total time a task **does not consume useful CPU** during processing, mainly due to blocking/waiting, in the same unit as C.
- **P:** number of pool workers.

Common estimation formula:

**P ≈ N × U × (1 + W / C)**

Interpretation: if a task only uses the CPU for 1 part out of (C + W) parts of time, more workers than CPUs are needed so that while one worker waits, another worker can run. The formula assumes steady load, relatively independent tasks, overlapping waits, and that CPU is the constraint being modeled. **It does not guarantee that a pool of that size is safe for the database, APIs, or memory.**

**Example:** N = 8, U = 0.8, each task takes C = 5 ms of CPU and W = 45 ms of I/O wait.

~~~text
W / C = 45 / 5 = 9
P ≈ 8 × 0.8 × (1 + 9) = 64 workers
~~~

You can test 32, 48, and 64 workers under realistic load and compare throughput, p95/p99 latency, CPU, queue wait, and downstream errors. If the database only allows 20 usable connections, increasing to 64 workers will not produce 64 parallel database queries: the excess workers will wait for connections, worsening queue wait and tail latency. **Downstream limits may dictate a lower concurrency than the formula.**

An equivalent form, when defining the wait time ratio as b = W/(C+W), is **P ≈ N × U / (1-b)** with 0 ≤ b < 1. When C is very small, the W/C ratio becomes extremely large and the formula can yield unrealistic results; in that case, set concurrency/queue/memory limits first rather than creating thousands of platform threads based on calculator output.

### Do not confuse throughput with concurrency

Suppose the system receives an average of λ tasks/second and each task stays in the system for an average of T seconds. By **Little's Law**, the average concurrency is **L = λ × T** in steady state. For example, 200 tasks/second with an average processing time of 0.2 seconds corresponds to about 40 tasks being processed/waiting in the system.

Here L may include tasks **in the queue**, so do not automatically treat L as the number of workers to create. For sizing, observe queue wait, active processing time, and the resources each stage uses separately. If the arrival rate exceeds sustainable processing capacity, the queue will keep growing even if you slightly increase the pool size.

## 5. How to measure C, W, and load capacity?

**Step 1 — classify each type of work.** Trace the request path: computation, blocking I/O, locks, connection waiting, retries, and external limits. A pool handling multi-stage requests must be measured on that exact request type; do not take the ratio from a small sub-task and apply it to all tasks.

**Step 2 — measure under representative load.** Collect the time from submission to execution start (**queue wait**), execution time from start to finish (**task wall time**), CPU time executed in the worker, I/O call latency, timeouts/rejections, active connections, CPU utilization, and throughput. JFR, thread dumps, profilers, executor metrics, ThreadMXBean, and downstream metrics can help.

With ThreadMXBean, getCurrentThreadCpuTime() measures the CPU time of the current thread when supported and enabled by the JVM; simply subtracting CPU time from total wall time does not accurately yield **I/O wait time** alone. The difference also includes scheduling, lock waits, and other unmeasured intervals. Time each I/O segment with timers and verify at the system level. For very short tasks, measurement overhead can be significant.

**Step 3 — sweep a range of values.** Keep workload, input, warm-up time, CPU quota, and dependencies equivalent, then vary **one parameter**: for example, CPU pool = 4/6/8/12 or blocking I/O pool = 16/32/48/64. Evaluate throughput, p50/p95/p99, errors/timeouts, CPU, memory, thread count, queue depth, and GC. Do not pick a configuration solely for highest throughput if p99 or error counts spike.

**Step 4 — burst load and overload.** Test steady load, bursts, slow dependencies, connection pool exhaustion, and shutdown. Successful sizing must exhibit clear backpressure/rejection behavior when capacity is exceeded.

## 6. Runnable Java 17 example: separating CPU pool and blocking I/O pool

The following program intentionally simulates two classes of work: a CPU-consuming computation loop and Thread.sleep simulating **the time a platform thread must wait**. It illustrates creating separate pools, submitting Callable tasks, waiting on Future, and shutting down; **this is not a benchmark** for deriving optimal pool sizes. In real applications, Thread.sleep is no substitute for measuring I/O latency.

Create **PoolSizingDemo.java**:

~~~java
import java.util.ArrayList;
import java.util.List;
import java.util.concurrent.Callable;
import java.util.concurrent.ExecutionException;
import java.util.concurrent.ExecutorService;
import java.util.concurrent.Executors;
import java.util.concurrent.Future;

public class PoolSizingDemo {
    public static void main(String[] args)
            throws InterruptedException, ExecutionException {
        int cpus = Math.max(1, Runtime.getRuntime().availableProcessors());

        // Starting values for illustration; measure for real configuration.
        int cpuPoolSize = cpus;
        int blockingIoPoolSize = Math.min(32, Math.max(4, cpus * 4));

        List<Callable<Long>> cpuTasks = new ArrayList<>();
        for (int task = 0; task < 20; task++) {
            cpuTasks.add(() -> {
                long sum = 0;
                for (int number = 1; number <= 100_000; number++) {
                    sum += number;
                }
                return sum;
            });
        }

        List<Callable<Integer>> ioTasks = new ArrayList<>();
        for (int task = 0; task < 20; task++) {
            ioTasks.add(() -> {
                Thread.sleep(30); // Simulate blocking I/O wait.
                return 1;
            });
        }

        long checksum = 0;
        for (long value : execute(cpuPoolSize, cpuTasks)) {
            checksum += value;
        }

        int completed = 0;
        for (int value : execute(blockingIoPoolSize, ioTasks)) {
            completed += value;
        }

        System.out.println("CPU checksum = " + checksum);
        System.out.println("I/O completed = " + completed);
    }

    private static <T> List<T> execute(
            int poolSize, List<Callable<T>> tasks)
            throws InterruptedException, ExecutionException {
        ExecutorService executor = Executors.newFixedThreadPool(poolSize);
        try {
            List<Future<T>> futures = executor.invokeAll(tasks);
            List<T> results = new ArrayList<>();
            for (Future<T> future : futures) {
                results.add(future.get());
            }
            return results;
        } finally {
            executor.shutdown();
        }
    }
}
~~~

Run with JDK 17+:

~~~bash
javac PoolSizingDemo.java
java PoolSizingDemo
~~~

Expected output (independent of thread ordering):

~~~text
CPU checksum = 100001000000
I/O completed = 20
~~~

Each CPU task computes 1 + 2 + ... + 100000 = 5,000,050,000; 20 tasks sum to 100,001,000,000. The two pool sizes are **illustrative** configurations only. Do not draw benchmark conclusions from an ad-hoc run time of this program because JIT, warm-up, and scheduling can vary.

In this example invokeAll waits for all work to finish before returning; shutdown is in finally so no new tasks are accepted. For production lifecycles, manage bounded shutdown, handle InterruptedException properly, and consider shutdownNow when waiting longer is not possible.

## 7. Pool size is only half the story: queues, limits, and rejection

**Executors.newFixedThreadPool(n)** uses n workers and an explicitly unbounded LinkedBlockingQueue. When the submission rate exceeds the completion rate, the queue can grow large, consuming heap and causing very high latency even though the thread count is fixed.

For services that need load limiting, use ThreadPoolExecutor with a **bounded queue** and an intentional rejection policy:

~~~java
import java.util.concurrent.ArrayBlockingQueue;
import java.util.concurrent.RejectedExecutionException;
import java.util.concurrent.ThreadPoolExecutor;
import java.util.concurrent.TimeUnit;

public class BoundedPoolDemo {
    public static void main(String[] args) {
        ThreadPoolExecutor executor = new ThreadPoolExecutor(
                4, 4,
                0L, TimeUnit.MILLISECONDS,
                new ArrayBlockingQueue<>(100),
                new ThreadPoolExecutor.AbortPolicy()
        );

        try {
            executor.execute(() -> System.out.println("Task accepted"));
        } catch (RejectedExecutionException rejected) {
            System.err.println("Pool overloaded or shutting down");
        } finally {
            executor.shutdown();
        }
    }
}
~~~

Save as **BoundedPoolDemo.java**, run:

~~~bash
javac BoundedPoolDemo.java
java BoundedPoolDemo
~~~

For the single-task program above, stdout is:

~~~text
Task accepted
~~~

Under real load, AbortPolicy throws RejectedExecutionException when a task cannot be accepted, allowing the caller to react explicitly (return an overload error, record metrics, retry **with bounds and backoff**, or throttle the producer). CallerRunsPolicy makes the submitting thread run the task itself to slow down submission, but it can increase the caller's latency; examine its behavior carefully during pool shutdown. Do not use DiscardPolicy unless silent task loss is acceptable.

**Meaning of corePoolSize / maximumPoolSize:** ThreadPoolExecutor normally creates threads up to corePoolSize first, then **enqueues into the queue**, and only creates additional threads up to maximumPoolSize if the queue cannot accept more. With an unbounded queue, maximumPoolSize almost never grows threads beyond corePoolSize. When sizing, design **pool + queue + rejection + timeout** together.

Separate two more limits:

- **Number of workers:** the number of Java threads running/waiting.
- **Number of requests to a dependency:** the number of concurrent connections, RPCs, or transactions an external resource can handle.

For example, if a pool has 64 workers but the database pool allows at most 16 connections, you can use a Semaphore or connection-limiting mechanism to keep at most 16 concurrent queries; you must still design queue/wait timeouts for the rest. Do not raise both limits just to make the queue disappear when the database is already saturated.

## 8. When to separate pools, when to use virtual threads?

**Separate pools when work characteristics differ.** If 8 long computational tasks occupy all 8 workers and blocking I/O tasks share that same 8-thread pool, the I/O work can starve. A small CPU pool and a larger, separately bounded blocking I/O pool make resource policies easier to observe. However, do not create dozens of pools per method; total workers across the JVM still share overall limits.

**ForkJoinPool / work-stealing** fits small divide-and-conquer CPU tasks and tasks with fork/join relationships. It is not the default choice for arbitrary blocking I/O; undeclared blocking can occupy workers and reduce parallelism. For specific cases, look into ManagedBlocker and the characteristics of APIs using the common pool.

**Virtual threads (Java 21+):** for many blocking I/O tasks following the thread-per-request model, virtual threads enable high task concurrency without a corresponding pool of platform threads. In that case, you typically **do not size a virtual thread pool using N × (1 + W/C)**; create a virtual thread per task and limit concurrency at scarce resources such as connections, APIs, or rate limits. Virtual threads **do not make the CPU faster**; CPU-bound code still contends for the actual CPUs. Some blocking/native/monitor scenarios may affect carrier threads depending on the JDK version; observe in practice. The Java 17 code above still uses platform threads and does not assume Java 21.

Java 21+ syntax example (independent of the Java 17 program above):

~~~java
import java.util.concurrent.Executors;
import java.util.concurrent.Semaphore;

public class VirtualThreadIoDemo {
    public static void main(String[] args) throws Exception {
        Semaphore downstreamLimit = new Semaphore(10);
        try (var executor = Executors.newVirtualThreadPerTaskExecutor()) {
            for (int i = 0; i < 100; i++) {
                executor.submit(() -> {
                    downstreamLimit.acquire();
                    try {
                        // Replace with actual blocking I/O to a bounded dependency.
                        Thread.sleep(20);
                    } finally {
                        downstreamLimit.release();
                    }
                    return null;
                });
            }
        }
        System.out.println("100 tasks submitted and completed");
    }
}
~~~

Run with JDK 21+ after saving **VirtualThreadIoDemo.java**; the try-with-resources block waits for the executor to finish tasks on close. Semaphore limits the number of tasks **entering the I/O section** concurrently to 10; creating 100 virtual threads does not mean 100 connections to downstream. For production scenarios, add appropriate timeouts, cancellation, and interruption handling.

## 9. Process for choosing a configuration for a specific system

1. **Define load and targets:** tasks/second, concurrency, p95/p99 targets, SLA, CPU/RAM limits, connection pool, and rate limits.
2. **Classify each task type:** CPU-bound, blocking I/O, non-blocking I/O, or mixed; list which dependencies are called.
3. **Choose a baseline:** test CPU pool around N; test blocking I/O pool starting from N × U × (1 + W/C) after measuring, then **cap by downstream limits, memory, and available platform threads**.
4. **Choose a bounded queue:** capacity appropriate for bursts and acceptable wait time; define rejection, timeout, and fallback.
5. **Load test:** gradually increase workers and concurrency; measure throughput, CPU, latency, queue wait, saturation, contention, timeouts, GC, and dependency errors.
6. **Select a stable configuration:** prefer the region where throughput is near saturation while tail latency, errors, and resources remain safe; re-test with bursts and slow downstream dependencies.

### Practical symptoms

| Observation | Suggested check | Action to try |
|---|---|---|
| CPU near 100%, queue growing, adding workers does not increase throughput | CPU saturation | Optimize algorithm, reduce CPU/task, or scale CPU; avoid increasing threads indefinitely |
| Low CPU, many workers TIMED_WAITING/WAITING on I/O, long queue | Blocking wait, connection starvation | Measure wait time; try increasing workers with control and check I/O limits |
| Low CPU but many threads BLOCKED on the same lock | Contention | Reduce contention/critical section before increasing pool size |
| p99 latency spikes and queue balloons during bursts | Missing backpressure, queue too large | Bound queue, add admission control, timeouts, and rejection handling |
| Downstream timeouts increase when pool grows | Dependency overloaded | Lower downstream concurrency, reduce retry storms, add bulkhead/rate limit |
| Throughput stable but RAM/thread count grows sharply | Too many platform threads/queues | Reduce limits, consider virtual threads for Java 21+ blocking I/O |

### Common mistakes to avoid

- Using a fixed number like “pool = 2 × cores” for all task types.
- Applying the I/O formula to CPU-bound tasks or assuming more threads always means faster.
- Treating Runtime.availableProcessors() as complete proof of CPU quota, ignoring shared resources.
- Measuring wall time and calling all of it CPU time; forgetting queue wait, lock contention, and dependency latency.
- Setting a very high maximumPoolSize while using an unbounded queue, assuming ThreadPoolExecutor will automatically grow threads to the max.
- Measuring only average throughput without tracking p99, rejections, timeouts, RAM, GC, or overload.
- Increasing pool size to mask slow queries, lock contention, small connection pools, or unbounded retries.
- Running CPU-heavy tasks in a pool meant for blocking I/O, causing I/O tasks to starve.

## 10. Completion checklist

A pool size choice is well-founded when you can answer: **What is N in the real deployment environment? How were C and W measured? What is the dependency concurrency limit? What is the maximum queue size? How does rejection/backpressure behave under overload? Do p95/p99 and throughput still meet targets after load testing?**

**Remember:** CPU-bound work usually starts near actual CPU capacity; blocking I/O may need more workers to hide wait time, but concurrency is only reasonable within what the system can sustain. Accurate configuration comes from measurement, load testing, and queue/downstream control, not from a single formula.

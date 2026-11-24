# Waiting for Resources vs. Using CPU in Java and Spring Framework

## 1. Properly Understanding the Two Types of Thread Time

A thread can **exist and hold a slot in a thread pool while consuming almost no CPU**. Distinguishing this is foundational for diagnosing slow Java/Spring applications, configuring executors, and choosing the right concurrency model.

- **Using CPU (CPU work):** the thread is executed by a CPU to compute, traverse data, encrypt, parse JSON, run algorithms, or execute business logic. During that time, the thread needs actual processing time on a CPU core.
- **Waiting for resources (waiting):** the thread cannot proceed because it depends on an external condition: a network/database response, a connection from a pool, a lock held by another thread, a result from another task, data from a queue, or a timer. The thread may use no CPU while waiting, yet still occupies management resources and, for a blocking platform thread, still occupies a worker slot in the pool.

Example of an HTTP request taking 420 ms:

| Stage | Illustrative Duration | Primary Activity |
| --- | ---: | --- |
| Validate input data | 15 ms | CPU |
| Wait to acquire a connection from the connection pool | 80 ms | Waiting |
| Wait for SQL execution and returned data | 270 ms | Waiting |
| Map results, serialize JSON | 25 ms | CPU |
| Wait on other tasks / CPU scheduling | 30 ms | Waiting or not yet scheduled |
| **Total response time** | **420 ms** | **Actual CPU used may be only around 40 ms** |

The numbers in the table are illustrative only; actual CPU time also depends on drivers, the kernel, GC, and how it is measured. A slow request **does not mean** the CPU is busy. Conversely, high CPU does not necessarily mean threads are stuck on the network.

### Wall-Clock Time vs. CPU Time

- **Wall-clock time:** actual elapsed time from start to finish, measured with a monotonic clock such as `System.nanoTime()` when measuring durations.
- **Thread CPU time:** the amount of CPU time spent executing the thread's code (usually user plus system CPU time), measurable via `ThreadMXBean` if supported by the JVM.
- **Wait / unscheduled time:** the remainder cannot be deduced accurately by simple subtraction alone, because scheduler wait time, GC/safepoints, and measurement overhead are also involved; detailed breakdown requires tracing, JFR, or metrics.

For **a single thread** on one core at a time, the `CPU time / wall-clock time` ratio is a rough indicator: near 100% suggests CPU-bound; very low while the request still takes long suggests waiting or being starved of CPU turns. For **an entire process**, threads running concurrently on multiple cores can yield total CPU time greater than wall-clock time.

## 2. How Do CPU-Bound and Wait-Bound Work Differ?

| Scenario | Is CPU Continuously Busy? | Is a Synchronous Java Thread Held? | What to Inspect |
| --- | --- | --- | --- |
| Image compression, hashing, heavy data-processing loops | Usually yes | Yes, during computation | CPU profile, algorithms, CPU cores |
| `Thread.sleep(500)` | Almost not at all | Yes: the sleeping thread processes nothing else | Avoid using sleep for synchronization |
| Reading JDBC/HTTP via blocking calls | Usually not during I/O wait | Yes | Latency, timeouts, connection pool, downstream |
| Waiting on `synchronized` held by another thread | Not while waiting for the lock | Yes | Lock contention, critical sections |
| Waiting on `BlockingQueue.take()` when empty | No | Yes | Producer/consumer, data supply rate |
| Unfinished `CompletableFuture.join()` or `Future.get()` | Not while waiting | Yes | Dependencies, potential deadlock/starvation |
| True asynchronous I/O via an event loop | CPU used when handling callbacks, no thread held while waiting | Typically does not hold a dedicated thread during I/O | Nonblocking drivers, callbacks, backpressure |

**CPU-bound** work is bottlenecked by computation speed: adding more runnable threads than CPU cores usually only increases contention and context switching. **Wait-bound/I/O-bound** work is delayed primarily by other resources: low CPU can still coincide with low throughput, growing queues, and timeouts. A real request often contains *both phases*; measure each phase instead of labeling an entire endpoint solely by an API name.

### Waiting Is Not Free

With **platform threads**, every blocking call still holds a thread until it resumes or times out. If 200 requests wait on the DB concurrently and the processing model assigns one thread per request, roughly 200 workers can be tied up even while CPU sits idle. They still put pressure on stack memory, thread pools, connection pools, request memory, and capacity to accept new work.

Long wait conditions can originate inside the system itself: an undersized connection pool, exhausted DB resources, contended mutexes, or a thread holding a lock too long. Increasing thread count usually **does not fix** this bottleneck and increases load on downstream dependencies.

## 3. What Does Java `Thread.State` Tell You, and What Does It Not?

`Thread.State` is a Java-level state snapshot, **not a CPU meter** or an exact classification of every I/O type:

| State | Primary Meaning | Example |
| --- | --- | --- |
| `NEW` | Created but not yet started | `new Thread(...)` |
| `RUNNABLE` | Running or eligible to run under the JVM model | CPU loop; sometimes also blocking native I/O |
| `BLOCKED` | Waiting to enter a `synchronized` monitor | Another thread holds the same monitor |
| `WAITING` | Waiting indefinitely until notified / condition met | `Object.wait()`, `Thread.join()`, certain `park()` calls |
| `TIMED_WAITING` | Waiting with a time bound | `Thread.sleep(...)`, `wait(timeout)`, `join(timeout)` |
| `TERMINATED` | Execution has finished | `run()` has returned |

Three common misconceptions:

1. `RUNNABLE` **does not prove** the thread is using CPU. The thread may merely be eligible to run, waiting for the scheduler, or inside a native I/O call that the JVM still reports as RUNNABLE.
2. `BLOCKED` in `Thread.State` refers specifically to waiting on an **intrinsic monitor** (`synchronized`). Waiting for a `ReentrantLock`, `Condition`, or `LockSupport.park()` can appear as `WAITING/TIMED_WAITING`.
3. `WAITING` does not tell you whether the wait is healthy or abnormal. A consumer waiting for data may be normal; a never-ending `join()` or deadlock is a bug. You must inspect stack traces, lock owners, and business context.

`Thread.sleep()` does not release monitors held inside a `synchronized` block; `Object.wait()` releases the corresponding monitor while waiting and must be called while owning that monitor. Therefore, sleeping inside a critical section can leave many other threads `BLOCKED` even though the lock-holding thread uses no CPU.

When reading a thread dump, ask **"what is it waiting for, who is it waiting on, for how long, and is it making progress?"** rather than jumping to conclusions from a single state.

## 4. Java 21 Experiment: Same Elapsed Time, Different CPU Usage

Measure two tasks that both take roughly 300 ms: a continuous computation loop and a sleep call. The following standalone program runs on JDK 21; `ThreadMXBean` retrieves the CPU time of the platform thread running `main`.

**File `ThreadCostDemo.java`:**

```java
import java.lang.management.ManagementFactory;
import java.lang.management.ThreadMXBean;
import java.util.concurrent.TimeUnit;

public class ThreadCostDemo {
    private static final ThreadMXBean MX =
            ManagementFactory.getThreadMXBean();
    private static volatile long sink;

    @FunctionalInterface
    interface Work {
        void run() throws InterruptedException;
    }

    private static void cpuWork() {
        long until = System.nanoTime()
                + TimeUnit.MILLISECONDS.toNanos(300);
        long sum = 0;
        while (System.nanoTime() < until) {
            sum += System.nanoTime() & 1L;
        }
        sink = sum; // Keep the result so the JIT does not eliminate the entire computation.
    }

    private static void measure(String name, Work task)
            throws InterruptedException {
        long beforeCpu = MX.getCurrentThreadCpuTime();
        long beforeWall = System.nanoTime();

        task.run();

        long wallNs = System.nanoTime() - beforeWall;
        long cpuNs = MX.getCurrentThreadCpuTime() - beforeCpu;
        System.out.printf(
                "%s: wall=%d ms, cpu=%d ms%n",
                name,
                TimeUnit.NANOSECONDS.toMillis(wallNs),
                TimeUnit.NANOSECONDS.toMillis(cpuNs));
    }

    public static void main(String[] args)
            throws InterruptedException {
        if (!MX.isCurrentThreadCpuTimeSupported()) {
            System.out.println("JVM does not support thread CPU time.");
            return;
        }
        if (!MX.isThreadCpuTimeEnabled()) {
            MX.setThreadCpuTimeEnabled(true);
        }

        measure("CPU work", ThreadCostDemo::cpuWork);
        measure("Sleep", () -> Thread.sleep(300));
    }
}
```

Run:

```bash
javac ThreadCostDemo.java
java ThreadCostDemo
```

Results are **not fixed**: both lines usually show `wall` of at least roughly 300 ms; `CPU work` has substantially higher `cpu` than `Sleep`, while `Sleep` consumes only a tiny amount of CPU. Noise from the scheduler, JIT, GC, and machine load causes exact numbers to vary. On some JVMs, CPU time measurement is unsupported/disabled or restricted by the environment. Under heavy CPU contention, `CPU work` can show much lower CPU time than wall time; that is another reason never to label behavior from a single sample.

**Key takeaway:** two requests that are both slow by 300 ms can demand vastly different CPU resources. Before optimizing, determine whether the system is *computing* or *waiting*.

## 5. Where Do Spring MVC Request Threads Typically Wait?

With the common synchronous handling model in Spring MVC:

```text
HTTP request
  -> servlet container worker
  -> controller -> service
  -> wait to acquire DB connection -> blocking JDBC/HTTP call
  -> process result on CPU -> write response
  -> worker can accept the next request
```

During the blocking JDBC or HTTP wait phase, **the request-handling thread is occupied even though CPU does not need to stay busy continuously**. When concurrent requests exceed worker pool capacity, queues grow or requests are rejected/timed out, even if overall CPU utilization remains low.

Distinguish the wait points:

- **Waiting on the connection pool:** the request does not yet have a connection to send SQL; inspect active/idle/pending connections and pool limits.
- **Waiting on the database:** the query was sent, yet the DB server is slow, tables are locked, queries lack indexes, or network latency is high.
- **Waiting on downstream HTTP:** another service is slow to respond or timeouts are too long.
- **Waiting on synchronization:** a lock or `Future.get()` holds the thread; sometimes caused by deadlocks or thread-pool starvation.
- **CPU-busy inside the application:** mapping large objects, JSON serialization, complex regexes, compression/encryption, or inefficient algorithms.

### `@Async` Does Not Automatically Turn Blocking I/O into Nonblocking I/O

When a call is handled by a Spring proxy via `@Async` and a configured executor, work runs on another worker. The calling thread may be freed early, yet **the worker executing blocking JDBC/HTTP remains occupied for the entire wait**.

If the calling thread immediately calls `future.get()`/`join()`, it blocks itself again. Calling an `@Async` method via `this.method()` inside the same bean normally bypasses the Spring proxy and has no default async effect. Verify proxy boundaries, the actual executor, queues, exception handling, and how results are returned.

With Spring MVC async requests such as `Callable`/`DeferredResult`, the servlet request thread can be returned to the container during asynchronous processing; however, a blocking I/O call offloaded to another executor **still occupies a thread of that executor**. Releasing the request thread and not using a thread to wait on I/O are two distinct properties.

## 6. Blocking, Nonblocking, and Virtual Threads Solve Different Problems

### Blocking Platform Threads

Sequential, easy-to-read style: call an API, wait for the result, then continue. Fits moderate concurrency, mostly blocking libraries, and clear executor/connection pool limits. Its weakness is that a large number of slow I/O calls tie up many platform threads.

### Nonblocking I/O and Spring WebFlux

An event loop initiates I/O operations and processes other tasks while waiting for data; results arrive via callbacks/reactive signals. This model can sustain many concurrent connections without dedicating a waiting platform thread per connection, **provided the entire critical I/O path is nonblocking**.

In Spring WebFlux, never call `Thread.sleep()`, blocking JDBC, or `block()` on an event-loop thread. If you must integrate a blocking library, you can *offload* the call to an appropriate scheduler:

```java
// Illustrative snippet inside a bean using Project Reactor.
Mono<String> loadLegacy() {
    return Mono.fromCallable(() -> {
        Thread.sleep(200); // Simulate a legacy blocking API.
        return "data";
    }).subscribeOn(Schedulers.boundedElastic());
}
```

The snippet above requires importing `reactor.core.publisher.Mono` and `reactor.core.scheduler.Schedulers` inside a Spring/Reactor class; it is an illustration, **not a standalone runnable Java program**. `boundedElastic()` shifts blocking work onto a bounded worker group; it **does not make `Thread.sleep` itself nonblocking**. If too many tasks arrive, the scheduler's queue and concurrency limit still become a bottleneck. Never place long CPU-heavy work on the event loop.

### Virtual Threads (Java 21+)

Virtual threads allow sequential blocking-style code, yet upon encountering many supported wait operations, a virtual thread can **unmount** from its carrier platform thread so the carrier can run other work. This reduces the cost of tying up one platform thread per wait operation and benefits high-concurrency I/O workloads.

However, virtual threads **do not make CPU processing faster**, do not bypass DB/HTTP connection pool limits, and do not automatically fix timeouts or slow queries. On Java 21, certain situations such as blocking while holding a `synchronized` monitor can *pin* a virtual thread to its carrier; use JFR/diagnostics to detect and evaluate real cases. Availability/behavior of CPU-time monitoring can also differ from platform threads.

All three options still require downstream limits, timeouts, cancellation, and real measurements; the choice depends on I/O libraries, concurrent traffic, deployment profile, and programming model.

## 7. Thread Pools: Why Increasing Thread Count Is Not the Default Answer

For CPU-bound work, the number of tasks truly running in parallel is typically bounded by **effective CPU cores**; an oversized pool increases scheduling overhead and memory/cache contention.

For wait-heavy work, higher concurrency *can* hide I/O latency: while task A waits, task B can run. A classic rule-of-thumb estimate for worker count is `N ≈ cores × (1 + W/C)`, where `W` is wait time and `C` is CPU time per task. This is only a reference model under steady load, not a direct configuration formula: container CPU quotas, DB connection limits, timeouts, queues, and memory must all be accounted for.

For example, suppose a system steadily receives 200 requests/s, each averaging 250 ms of I/O wait. By Little's Law, on average this phase alone has roughly `200 × 0.25 = 50` concurrent requests waiting. In a synchronous model holding one worker per request throughout this phase, I/O waiting alone can occupy around 50 workers. In a nonblocking model, around 50 requests are still waiting, yet 50 platform threads do not necessarily have to wait alongside them.

When configuring `ThreadPoolTaskExecutor`, servlet pools, Reactor schedulers, or virtual-thread executors, examine all of these together:

- **Active threads, queue depth, rejections, and saturation:** is the pool genuinely short on workers or are tasks stuck on a dependency?
- **DB/HTTP connection counts and downstream latency:** will adding workers push more requests into an already overloaded dependency?
- **Timeouts and cancellation:** do tasks have an exit mechanism when a source stops responding, or do they occupy slots forever?
- **Backpressure and concurrency limits:** does the system throttle work before queues/memory allocations balloon?
- **CPU throttling in containers:** host-level CPU metrics can mislead when a container is capped by CPU quotas.

Separate pools for long/wait-heavy work and latency-sensitive work when needed; avoid a single unbounded shared executor where one workload stalls the entire application.

## 8. How to Diagnose When an Application Is Slow with Low CPU

1. **Define the symptoms:** measure throughput, p50/p95/p99 latency, in-flight requests, timeouts, and errors/rejections. Low CPU is only a clue, not a diagnosis.
2. **Measure per-dependency durations:** DB connection acquisition, SQL execution, HTTP calls, lock wait, CPU processing, and executor queueing. Use traces/spans and metrics with a shared correlation ID where possible.
3. **Inspect thread dumps over time:** run `jcmd <PID> Thread.print -l` from the JDK and capture multiple samples spaced appropriately apart. Focus on repeated stack traces, lock holders, `WAITING/BLOCKED`, and executor names; remember `RUNNABLE` does not guarantee CPU consumption.
4. **Profile / capture JFR:** CPU samples explain computation time; events such as `jdk.JavaMonitorEnter`, `jdk.ThreadPark`, `jdk.SocketRead`, and `jdk.FileRead` (depending on recording settings) reveal wait sources. Cross-check with connection pool, DB, and downstream metrics.
5. **Check the environment:** CPU quotas/throttling, GC pauses, thread creation, socket timeouts, scheduler/connection limits. Retest under representative load before and after changes.

A useful pattern is **rising latency without a corresponding rise in CPU**: prioritize investigating connection waits, locks, DB, network, and queues. If **CPU is saturated, many threads are RUNNABLE, and CPU profiles concentrate in the same functions**, prioritize analyzing algorithms, work per request, CPU cores, and parallelism.

A single thread dump can be skewed by sampling timing. Multiple samples, stack traces, and metrics over time are needed before concluding deadlock or a bottleneck.

## 9. Common Mistakes to Avoid

- **Confusing blocking with busy CPU:** `Thread.sleep`/`Future.get` can make requests slow while using almost no CPU; busy spinning, by contrast, continuously consumes CPU while "waiting for a flag."
- **Busy-waiting instead of conditional waiting:** `while (!done) { }` both burns CPU and has visibility issues if `done` is not properly synchronized. Use `CountDownLatch`, `BlockingQueue`, `Condition`, `CompletableFuture`, or an appropriate async mechanism; if using flags across threads, understand `volatile`/happens-before.
- **Using `Thread.sleep` for synchronization:** sleeping for a duration does not guarantee another task finished; wait on the actual event/result with a timeout.
- **Assuming `@Async` or `CompletableFuture` is inherently nonblocking:** being asynchronous for the caller does not make blocking JDBC/HTTP calls disappear; `join/get` still blocks the calling thread.
- **Putting blocking tasks onto an event loop:** a prolonged wait operation can stall progress for many other connections on the same loop.
- **Enlarging pools to cure a slow DB:** easily creates more queueing, lock contention, and downstream timeouts.
- **Missing timeouts/cancellation and interrupt handling:** tasks stuck indefinitely can exhaust threads. When catching `InterruptedException` without propagating it, consider restoring the interrupt flag with `Thread.currentThread().interrupt()` according to the method's contract.
- **Looking only at total CPU or only at `Thread.State`:** low CPU does not prove a healthy system, and RUNNABLE does not prove CPU consumption; complementary measurements are required.

## 10. Applying This When Designing Spring Features

Before building a new task, answer in order:

1. **Is the task primarily computing or waiting on dependencies?** Determine via profiler, tracing, load data, and CPU/wall-time ratio, not from method names.
2. **During waits, which thread is being held?** Servlet worker, `@Async` executor thread, Reactor scheduler, or virtual thread? Can it stall other tasks in the same pool?
3. **Which resource actually limits throughput?** CPU, DB connections, partner rate limits, locks, memory, or queues?
4. **Can blocking waits be eliminated at the I/O layer itself?** Only use nonblocking if drivers/clients support it; if staying blocking, choose a bounded executor or virtual threads with appropriate limits.
5. **How will you verify the change worked?** Compare throughput, percentile latencies, CPU time, busy workers, queue depth, lock/I/O wait time, and timeout rates under the same load scenario.

**Core message:** a waiting thread is not equivalent to a computing thread. The fix for a CPU bottleneck is reducing or distributing computation; the fix for resource waiting is finding the right dependency, bounding concurrency, setting timeouts, choosing the proper I/O model, and making wait time observable.
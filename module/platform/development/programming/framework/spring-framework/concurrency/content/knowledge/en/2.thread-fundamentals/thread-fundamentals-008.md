# Deadlocks, Thread Starvation, and the Limits of Adding More Threads

In a Spring Framework application, multiple HTTP requests, `@Async` tasks, `@Scheduled` jobs, and I/O operations may all need threads to make progress. When a system slows down or stalls, increasing the number of threads is often the first reflex, yet doing so may fail to solve the problem and can even worsen latency and resource consumption.

This lesson focuses on **three distinct issues**: deadlocks (threads waiting on one another in a cycle), thread-pool starvation (no free workers remain to execute required work), and the limits of scaling thread counts. Java examples use Java 17 or higher; Spring configuration sections are integration examples requiring Spring dependencies in the project.

## 1. Threads, Tasks, and Queues: The Model to Understand

A **thread** is an execution unit; a **task** is the work assigned to a thread; an **executor/thread pool** accepts tasks and manages workers instead of creating a new thread for every task.

In a typical system:

~~~text
Caller (HTTP / scheduler / event)
        |
        v
   TaskExecutor
        |
        +--> idle worker ----------> run task -----------> complete
        |
        +--> queue (if busy) ------> wait for turn
        |
        +--> reject (when configured limits are reached)
~~~

Three quantities must be observed together:

- **Active workers**: the number of threads currently busy executing tasks. A thread waiting on I/O or `Future.get()` may still count as busy.
- **Queue depth and queue wait time**: accepted work without a worker yet. A steadily growing queue can mask trouble until latency spikes severely.
- **Throughput, latency, and rejections**: tasks completed per second, processing duration (especially p95/p99), and rejected task count.

**Do not equate a large thread count with high throughput.** A thread holding a lock or waiting on a database produces no results yet, even though it occupies a pool slot.

## 2. Correctly Distinguishing Symptoms

| Phenomenon | Core Mechanism | Common Signs | Does Adding Threads Fix the Root Cause? |
| --- | --- | --- | --- |
| **Java lock deadlock** | Threads hold locks and wait for each other's locks in a closed cycle | Thread dump shows a cycle of monitor or ownable-synchronizer ownership/waiting; zero progress | **No**; the lock dependency cycle must be broken |
| **Thread-pool starvation** | All workers are busy/waiting, while the work needed to unblock them sits in the same pool's queue, or critical tasks are continually denied execution time | Active count hits cap; queue stalls; stacks show many `Future.get()`/`join()` calls | Enlarging the pool may hide symptoms at a specific load, yet the dangerous dependency remains |
| **Pool saturation / overload** | Arrival rate exceeds completion rate, or slow I/O ties up all workers | Queue grows, rejections rise, latency climbs; may have no deadlock cycle | Sometimes helps I/O-bound work, but only up to downstream resource limits |
| **Resource starvation** | Threads wait on a connection pool, DB lock, socket, or other bounded resource | Many stacks waiting on datasource/HTTP client; resource pool exhausted | Adding workers usually leaves more threads waiting |
| **CPU contention / too many runnable threads** | Many threads compete for CPU, caches, locks, and scheduling | High CPU, heavy context switching, flat throughput | Usually **no** |
| **Livelock / continuous retries** | Tasks keep running yet continually react/retry without making progress | High CPU or heavy logging, work never finishes | No; progress conditions and retry strategies must be fixed |

A thread in `BLOCKED` or `WAITING` **is not enough** to conclude a deadlock. Threads waiting for work, sleeping on schedule, or awaiting valid results can also be in those states. You must inspect **who/what** it is waiting on and whether a dependency cycle exists.

## 3. What Is a Deadlock and Why Does It Happen?

Suppose thread T1 holds lock A and tries to acquire B, while T2 holds lock B and tries to acquire A:

~~~text
T1: holds A -----> waits for B (held by T2)
                     ^              |
                     |              v
T2: waits for A <--- holds B
~~~

Neither side can reach the point where it releases its held lock. A classic deadlock occurs when all four Coffman conditions hold simultaneously:

1. **Mutual exclusion:** a resource/lock has at most one owner at a time.
2. **Hold and wait:** a thread holds at least one resource while waiting for additional resources.
3. **No preemption:** a lock cannot be forcibly taken away from the thread holding it.
4. **Circular wait:** a cycle of threads/resources waiting on one another exists.

Breaking **at least one condition** eliminates that form of deadlock. In Java, the most practical approach is usually **enforcing a consistent lock acquisition order** and avoiding holding locks across potentially long-blocking operations.

### 3.1. Java 17 Example: Creating and Detecting a Deadlock Deterministically

Create the file `DeadlockDemo.java`:

~~~java
import java.lang.management.ManagementFactory;
import java.lang.management.ThreadMXBean;
import java.util.concurrent.CountDownLatch;

public class DeadlockDemo {
    private static final Object LOCK_A = new Object();
    private static final Object LOCK_B = new Object();
    private static final CountDownLatch READY = new CountDownLatch(2);

    private static void takeLocks(Object first, Object second) {
        synchronized (first) {
            READY.countDown();
            try {
                READY.await();
            } catch (InterruptedException e) {
                Thread.currentThread().interrupt();
                return;
            }
            synchronized (second) {
                System.out.println("Both locks acquired");
            }
        }
    }

    public static void main(String[] args) throws InterruptedException {
        Thread t1 = new Thread(() -> takeLocks(LOCK_A, LOCK_B), "worker-A");
        Thread t2 = new Thread(() -> takeLocks(LOCK_B, LOCK_A), "worker-B");
        t1.setDaemon(true);
        t2.setDaemon(true);
        t1.start();
        t2.start();

        ThreadMXBean bean = ManagementFactory.getThreadMXBean();
        for (int i = 0; i < 100; i++) {
            long[] deadlocked = bean.findMonitorDeadlockedThreads();
            if (deadlocked != null) {
                System.out.println("Deadlock detected: " + deadlocked.length + " threads");
                return;
            }
            Thread.sleep(50);
        }
        System.out.println("No deadlock detected within the check window");
    }
}
~~~

Compile/run with JDK 17+:

~~~bash
javac --release 17 DeadlockDemo.java
java DeadlockDemo
~~~

Output on a JVM supporting monitor deadlock detection (e.g., OpenJDK/HotSpot):

~~~text
Deadlock detected: 2 threads
~~~

`CountDownLatch` forces both threads to **already hold their first lock** before attempting to acquire the second; because their order is reversed, they form a wait cycle. The example uses daemon threads **only so the demo process can exit** after reporting the error; daemon threads are not a deadlock-handling measure. The line `Both locks acquired` never appears in the deadlock scenario. `findMonitorDeadlockedThreads()` detects wait cycles on monitors managed by `synchronized`; `findDeadlockedThreads()` extends detection to ownable synchronizers such as `ReentrantLock` if supported by the JVM.

### 3.2. The Fix: Always Acquire Locks in the Same Order

If two code paths both need A and B, both must acquire **A then B**, regardless of which path runs first:

~~~java
private static void updateBothLocks() {
    synchronized (LOCK_A) {
        synchronized (LOCK_B) {
            // Critical shared-state update must be short and contain no blocking I/O.
        }
    }
}
~~~

This is an **illustrative method snippet** reusing `LOCK_A` and `LOCK_B` from the previous class, not a standalone program. Two threads may have to wait for each other, yet no A→B and B→A cycle is formed. In real designs, also minimize lock count, shorten critical sections, and avoid calling callbacks/HTTP/DB or awaiting a `Future` while holding locks. With `ReentrantLock`, `tryLock(timeout, unit)` avoids waiting forever **provided every exit path releases acquired locks in `finally`**.

**Distinguishing Java deadlocks from database deadlocks:** two transactions can lock SQL rows in opposite order; the database normally detects this and aborts one transaction. Such cases require inspecting SQL/logs/transaction order and proper retry policies rather than concluding solely from `ThreadMXBean`.

## 4. Thread Starvation: When Workers Wait on Work Needing Workers

A particularly easy mistake is **task A running in a small pool submitting task B to the same pool and synchronously awaiting B's result**. If all workers are doing what A does, no worker remains free to run B. This is commonly called *thread-starvation deadlock*; it may not show up in monitor-deadlock cycle detectors.

### 4.1. Java 17 Example: A Single-Threaded Pool Blocking Itself

Create the file `PoolStarvationDemo.java`:

~~~java
import java.util.concurrent.ExecutorService;
import java.util.concurrent.Executors;
import java.util.concurrent.Future;
import java.util.concurrent.TimeUnit;
import java.util.concurrent.TimeoutException;

public class PoolStarvationDemo {
    public static void main(String[] args) throws Exception {
        ExecutorService pool = Executors.newFixedThreadPool(1);
        try {
            Future<String> outer = pool.submit(() -> {
                Future<String> inner = pool.submit(() -> "OK");
                return inner.get();
            });
            try {
                System.out.println(outer.get(500, TimeUnit.MILLISECONDS));
            } catch (TimeoutException expected) {
                System.out.println("TIMEOUT: worker waits for a task queued in its own pool");
            }
        } finally {
            pool.shutdownNow();
        }
    }
}
~~~

Run:

~~~bash
javac --release 17 PoolStarvationDemo.java
java PoolStarvationDemo
~~~

Output:

~~~text
TIMEOUT: worker waits for a task queued in its own pool
~~~

Exact sequence of events: the single worker runs `outer` → `outer` puts `inner` into the queue → `outer` calls `inner.get()`, occupying the worker while waiting → `inner` has no worker to run on → the main thread times out after 500 ms. `shutdownNow()` interrupts the worker so the demo program terminates; that interruption does not make the underlying dependency structure valid.

**Fix at the root cause:** if `inner` is just the next step of the same job, invoke that logic directly inside `outer`; or structure an asynchronous chain that does not block a worker on the result of a task in the same pool. Splitting pools only makes sense after identifying two workloads with independent resource needs and limits. Never use a larger pool to mask a dependency cycle.

### 4.2. Other Sources of Thread Starvation in Spring Applications

- `@Async` tasks calling `get()`/`join()` to wait on other tasks running on an already saturated executor.
- Multiple `@Scheduled` tasks running long or blocking on I/O on a scheduler with few workers, delaying subsequent scheduled executions.
- Spring MVC request threads tied up by HTTP, JDBC, or external calls without bounded timeouts. If the datasource has only 10 available connections, adding 100 request threads does not create 100 connections.
- Callbacks sharing the same pool with tasks waiting on those callbacks, causing an "all workers busy waiting" dependency.
- Unbounded queues accepting more work despite low downstream capacity: the system does not reject immediately, yet wait times and memory grow steadily.

In Spring WebFlux, **blocking the event loop with blocking operations** is another pitfall: a small number of event-loop threads can be held for long durations, stalling many requests. You must use nonblocking APIs or offload blocking work to an appropriate bounded scheduler; increasing an `@Async` pool does not automatically resolve event-loop blocking.

## 5. Why Does Adding Threads Have Limits?

### 5.1. CPU-Bound vs. I/O-Bound Work

- **CPU-bound:** computation occupies the CPU continuously. If the system has roughly P effective CPU cores allocated, running more than P CPU-bound tasks concurrently usually increases scheduling contention/context switching without proportional throughput gains. Start testing around useful CPU parallelism and measure, rather than picking a fixed number for all machines.
- **I/O-bound:** threads spend substantial time waiting on network/disk/database. Higher concurrency than CPU core count may be needed to hide wait latency, yet the optimum depends on socket/connection pool limits, backend speed, timeouts, and memory.
- **Shared locks:** if all tasks must enter one critical section, adding workers may only lengthen the lock wait line.
- **Sequential dependencies:** a stage that must run serially creates a speed limit; adding workers to other stages does not eliminate that bottleneck.

Back-of-the-envelope example: an endpoint needs a database connection for 200 ms, while the database pool has only 10 connections. In an ideal model (ignoring other overhead), maximum throughput at this step is roughly `10 / 0.2 = 50` queries/second. Raising the executor from 20 to 200 workers does not push the DB pool past its limit of 10; the extra workers may simply wait for connections, worsening p95/p99 latency. This illustrates a resource limit, **not a real-world throughput forecast**.

### 5.2. Estimating Concurrency with Little's Law

In steady state, `L = λ × W`, where L is the average number of items in the system, λ is the average arrival/completion rate, and W is the average time each item spends in the system. If steady throughput is 60 tasks/second and each task spends an average of 0.5 seconds in the measured segment, average concurrency is roughly 30.

You must specify clearly whether W measures **worker-occupancy time** or **total time including queueing**. Little's Law helps sanity-check metrics; it does not directly prescribe optimal pool sizes under fluctuating load, heavy tail latencies, bounded I/O, or unstable systems.

### 5.3. The Cost of Too Many Threads

Every platform thread needs a stack and native metadata, incurring scheduling and context-switching costs; high task concurrency also increases contention on locks, connections, caches, and heap regions holding requests/queues. Stack memory can be **reserved** rather than always fully committed up front, so do not apply a rule like "every thread always consumes exactly 1 MB of RAM."

If raising thread count from 32 to 256 yields almost flat throughput while CPU, queue wait, database wait, or GC pressure rises, that signal indicates you should hunt down the bottleneck instead of raising threads further.

**Java 21+ virtual threads** can reduce the cost of keeping large numbers of I/O-waiting threads compared to platform threads in certain workloads, yet they **do not** eliminate deadlocks, expand connection pools/databases, or turn CPU-bound operations into unlimited parallel capacity. The runnable examples in this lesson still target Java 17.

## 6. `ThreadPoolTaskExecutor` in Spring Framework

`ThreadPoolTaskExecutor` wraps `ThreadPoolExecutor` and is commonly used as the executor for `@Async`. Understand the **task-acceptance order** for core, queue, and max settings:

1. While current workers are below `corePoolSize`, the executor creates a new worker for an incoming task.
2. Once core is reached, the executor **prefers placing the task into the queue if space remains**.
3. Only when the queue cannot accept more tasks can the executor scale workers up toward `maxPoolSize`.
4. If both workers and queue reach their limits, the task is rejected per the rejection policy.

Therefore, setting `maxPoolSize = 100` while keeping an **unbounded queue** does not mean the pool will actively grow to 100. With `ThreadPoolTaskExecutor`'s defaults (core 1, very large max and queue), most work can rotate through a single worker while the queue grows ever longer. Configure explicit bounds suited to your workload.

### 6.1. Example Configuring a Bounded Executor for Blocking I/O Work

The following is **Spring integration code**, requiring Spring Framework and an application scanning these beans; it is not a standalone `javac` program:

~~~java
import java.util.concurrent.CompletableFuture;
import java.util.concurrent.ThreadPoolExecutor;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.scheduling.annotation.Async;
import org.springframework.scheduling.annotation.EnableAsync;
import org.springframework.scheduling.concurrent.ThreadPoolTaskExecutor;
import org.springframework.stereotype.Service;

@Configuration
@EnableAsync
class ExecutorConfig {
    @Bean("ioExecutor")
    ThreadPoolTaskExecutor ioExecutor() {
        ThreadPoolTaskExecutor executor = new ThreadPoolTaskExecutor();
        executor.setCorePoolSize(4);
        executor.setMaxPoolSize(8);
        executor.setQueueCapacity(32);
        executor.setKeepAliveSeconds(30);
        executor.setThreadNamePrefix("io-worker-");
        executor.setRejectedExecutionHandler(new ThreadPoolExecutor.AbortPolicy());
        executor.initialize();
        return executor;
    }
}

@Service
class AuditService {
    @Async("ioExecutor")
    public CompletableFuture<String> record(String eventId) {
        // Replace with real business logic, with explicit I/O timeouts when calling external services.
        return CompletableFuture.completedFuture("saved:" + eventId);
    }
}
~~~

In this example, once all 4 core workers are busy, the executor queues up to 32 waiting tasks; once the queue is full, it can scale up to 8 workers. Once all workers are busy and the queue is full, `AbortPolicy` causes rejection failures (which Spring can surface as `TaskRejectedException`). The numbers **4/8/32 are illustrative**, not optimal defaults; measure execution duration, queue latency, downstream capacity, and peak load before choosing values.

Points to remember:

- `@EnableAsync` enables `@Async` processing; `@Async("ioExecutor")` selects the executor bean with that name.
- Under default proxy mode, **calling an `@Async` method from another method on the same instance** (*self-invocation*) bypasses the proxy and does not run asynchronously as expected. Calls must pass through a Spring-managed proxy.
- `@Async` moves execution to a worker; blocking operations inside the method still block **that worker**. `CompletableFuture.completedFuture(...)` here is merely the return type from the method already running on the worker.
- Never call `join()`/`get()` unboundedly on child tasks inside the same pool running the parent task. Use nonblocking composition or redesign dependency boundaries.
- Task rejection needs intentional handling: return an appropriate error, retry with backoff at an allowed layer, rate-limit submissions, or persist to a durable queue if business rules require it. Rejections should not be silently swallowed.
- `CallerRunsPolicy` can provide backpressure by having the **submitting thread** execute the task, yet on HTTP/event-loop/scheduler threads it can cause unintended blocking; do not pick it by habit.
- Attach timeouts/cancellation to JDBC/HTTP clients and interruptible waiting tasks. `Future.get(timeout)` only limits **how long the caller waits**; it does not automatically stop I/O inside the running task.
- If a thread calling `@Async` is inside a transaction, do not assume the caller's thread-bound transaction context transfers automatically to the worker. Design transaction boundaries inside the async work itself when needed.

A long-running `@Scheduled` task should have an appropriate scheduler/concurrency configuration and a policy preventing unintended overlapping runs. Do not lump every job type into one pool simply because they are all "background tasks."

## 7. Detecting Incidents from Evidence

### 7.1. Thread Dumps and Checking for Java Deadlocks

When signs of stalling appear, capture **multiple thread dumps at different times** from the same process to see whether progress occurs. The JDK provides `jcmd` or `jstack`, for example with process ID 12345:

~~~bash
jcmd 12345 Thread.print -l
jstack -l 12345
~~~

Replace 12345 with the real PID; requires process permissions and matching JDK tooling. When reading dumps:

- For monitor deadlocks, look for "waiting to lock" and "locked" chains forming a cycle; the tool may report "Found one Java-level deadlock."
- For `ReentrantLock`, inspect ownable synchronizers and `ThreadMXBean.findDeadlockedThreads()` if supported by the JVM.
- For pool starvation, workers may be sitting in `FutureTask.get`/`CompletableFuture.join` while waiting tasks sit in the executor queue. This dependency pattern **may not** be reported as a Java monitor deadlock.
- For slow I/O, many stacks may be waiting on sockets, datasources, or remote APIs; combine with client metrics/logs to pinpoint the wait.
- For `WAITING` or `TIMED_WAITING`, interpret based on stack frames and work state rather than treating all waiting as bugs.

Additional thread details can be pulled via JMX/`ThreadMXBean`; lock-inspection tools are meant for diagnostics, not high-frequency calls on production hot paths.

### 7.2. Measuring Executors and Downstream Resources

When using `ThreadPoolTaskExecutor`, monitor `getActiveCount()`, `getPoolSize()`, `getCorePoolSize()`, `getMaxPoolSize()`, `getQueueSize()` (on supported Spring versions), completed task count, and rejection count. In parallel, monitor:

- Queue length **and age of the oldest queued task**; looking only at worker counts can miss growing queues.
- End-to-end p50/p95/p99 latency, completion throughput, and timeout/error rates.
- Effective CPU against container quotas, context switches, GC, heap/native memory, and thread count.
- Active/waiting connections in datasources, HTTP connection pools, downstream service queues, or rate limits.
- Lock wait time, repeated stack traces, slow DB queries, and open transactions.

**Misleading signal:** `activeCount == maxPoolSize` is not by itself a deadlock; it may simply reflect high load. Conversely, `activeCount < maxPoolSize` also does not prove the pool has spare capacity: remaining queue space keeps the executor from scaling up to max.

### 7.3. Evidence-Based Triage Process

1. **Confirm the symptom:** distinguish "no tasks finishing," "finishing slowly," and "many tasks rejected"; record timestamps and load levels.
2. **Capture thread dumps alongside metrics:** examine worker states, stacks, lock owners, active/queue/rejection counts, and dependency connections.
3. **Search for wait cycles:** if an A→B→A lock cycle appears, fix lock ordering/critical sections; if workers wait on child tasks in the same pool, fix the blocking dependency.
4. **Identify the limiting resource:** if many workers wait on DB/network, measure capacity and latency there before adding workers.
5. **Make one controlled change:** such as tightening I/O timeouts, bounding queues, fixing wait code, or tuning the pool; re-verify throughput, p95/p99, errors, and resources.
6. **Run ramp-up and soak tests:** confirm the system reaches a steady operating point, handles overload gracefully, and recovers when downstream slows down.

## 8. Design Principles to Prevent Recurrence

**For locks:** enforce a global lock acquisition order; narrow `synchronized` scopes; never invoke unknown functions, callbacks, I/O, or await futures while holding multiple locks; consider immutable data and built-in concurrent structures instead of manual locking. Locks must be released cleanly on every exit path.

**For task graphs:** prevent parent tasks from holding a worker while waiting on child tasks forced onto the same pool; express relationships via sequential flow or nonblocking composition. When blocking steps are unavoidable, reserve separate concurrency budgets grounded in concrete connection counts and timeouts.

**For backpressure:** use bounded queues and control in-flight tasks plus downstream connections. When capacity is exceeded, fail fast or throttle incoming load transparently. "Accept everything into a queue" usually only shifts errors from rejections into timeouts while inflating memory usage.

**For timeouts and retries:** end-to-end timeouts must cover queue time + execution time + I/O calls; retries must be bounded, use backoff/jitter, and respect idempotency. Aggressive retries during downstream slowdowns can exhaust workers even faster.

**For pool isolation:** separate CPU-bound work from blocking I/O when resource profiles differ clearly; avoid splitting pools merely by feature names. Pool sizes, queues, connection pools, and admission thresholds must be designed **together**.

## 9. Integrated Scenario in a Spring Application

Suppose a Spring MVC service uses `@Async("ioExecutor")` to export reports. Each task needs a DB connection and calls an external API. Under high load, you observe:

| Hypothetical Metric | Observation |
| --- | --- |
| Executor | 8/8 workers busy; queue nearly full at 32/32 |
| Database pool | 10/10 connections in use; threads waiting to acquire connections |
| External API | High p99 and occasional timeouts |
| Outcome | Throughput plateaus, requests time out, or tasks are rejected |

This is **not enough evidence** to conclude a deadlock. Thread dumps show no lock cycle, yet show many workers waiting on I/O. Merely raising `maxPoolSize` from 8 to 64 lets even more tasks contend for the same 10 DB connections and slow API; the wait queue simply shifts from the executor to the connection pool while latency may worsen.

Cause-driven remediation is: identify which I/O step is slow; set finite timeouts and cancellation where appropriate; shorten connection hold times; bound concurrent calls into downstream; keep bounded queues with explicit overload responses; and consider enlarging database/HTTP pools **only if backend systems can sustain it**. Then load-test and compare throughput, p95/p99, rejections, and connection wait time. If a thread dump genuinely reveals a lock cycle, fix that deadlock before tuning pools.

## 10. Knowledge Self-Check

**Question 1. Are two `BLOCKED` threads guaranteed to be deadlocked?** No. You must prove they wait on each other in a cycle (or a longer cycle). Waiting on the same lock and taking turns acquiring it is not a deadlock.

**Question 2. Why set `maxPoolSize=100` yet observe only a few workers?** With `ThreadPoolExecutor`, once core workers are busy, tasks normally go into the queue first. If the queue is very large, it has no reason to grow toward max; inspect `queueCapacity` and metrics.

**Question 3. What category does the single-worker pool waiting on `inner.get()` fall into?** Thread-pool starvation caused by task dependencies: the worker holds its slot while the task needed to unblock it sits in the same queue. Monitor-deadlock detectors may not see it.

**Question 4. When can adding workers help?** When workers primarily wait on I/O, downstream still has spare capacity, and concurrency has not hit CPU, memory, connection, rate-limit, or queue boundaries. Decisions must be verified under realistic load.

**Question 5. Do virtual threads solve deadlocks or exhausted connection pools?** No. They change the cost model of waiting threads for certain workloads, but neither break lock cycles nor increase database capacity.

**Question 6. Is a task automatically cancelled when `Future.get(500, MILLISECONDS)` times out?** No. The timeout only ends the caller's wait. To request cancellation, call `cancel(...)` or use I/O-level timeout/cancellation mechanisms, and the task must cooperate with interruption/cancellation.

## 11. References

- Spring Framework — Task Execution and Scheduling: https://docs.spring.io/spring-framework/reference/6.2/integration/scheduling.html
- Spring Framework — `ThreadPoolTaskExecutor` implementation/API: https://github.com/spring-projects/spring-framework/blob/main/spring-context/src/main/java/org/springframework/scheduling/concurrent/ThreadPoolTaskExecutor.java
- Java SE 17 — Monitoring and Management / deadlock diagnosis: https://docs.oracle.com/en/java/javase/17/management/using-jconsole.html
- Java SE — `ThreadMXBean`: https://docs.oracle.com/en/java/javase/17/docs/api/java.management/java/lang/management/ThreadMXBean.html

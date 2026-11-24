# Task Acceptance Order in a Thread Pool: Core Thread Creation, Queuing, Expansion, Then Rejection

When submitting a task to a thread pool, whether there is "still room" does not depend solely on the thread count. Under Java's `ThreadPoolExecutor` mechanism—also the foundation of `ThreadPoolTaskExecutor` in Spring Framework—the acceptance decision generally follows this sequence:

**Create workers up to `corePoolSize` → attempt to enqueue the task → if queuing fails, add workers up to `maxPoolSize` → if still unable to accept, apply the rejection policy.**

This is a **priority order at task acceptance**, not four mandatory stages every task must pass through. A task executed immediately by a worker may never have entered the queue. Another task may sit in the queue while the executor has not yet used up `maxPoolSize`.

Understanding this sequence helps prevent a very common configuration mistake: **increasing `maxPoolSize` without seeing the pool spawn additional threads because the queue still has space**.

## 1. Components Governing Task Acceptance

In Java, `ThreadPoolExecutor` manages two places where work is placed:

- **Worker threads:** threads that actually pull tasks and run `Runnable`/`Callable`. A worker blocked on I/O or waiting on a lock still occupies an execution slot.
- **Work queue:** storage for tasks accepted by the executor that no worker has picked up yet. With a bounded queue, once full, the executor must take a different path.
- **Rejection handler:** policy invoked when a task cannot be accepted, such as when the pool has stopped or both workers and queue lack capacity.

Key parameters:

| Parameter | Role | What to understand accurately |
| --- | --- | --- |
| `corePoolSize` | Baseline workers the pool prefers creating when new tasks arrive | **Does not mean** all core threads already exist at initialization |
| `maxPoolSize` | Maximum number of workers the pool may create | Primarily comes into play when the queue stops accepting tasks |
| `queueCapacity` | Maximum tasks queued per Spring configuration | Positive → bounded `LinkedBlockingQueue` (with given capacity); 0 → `SynchronousQueue` for direct handoff |
| `keepAliveSeconds` | Idle duration before workers above core may be reclaimed | By default does not expire core workers; a setting exists to allow core timeout |
| `RejectedExecutionHandler` | Behavior when a task cannot be accepted | Rejection does not necessarily mean throwing an error; depends on the policy |
| Executor state | `RUNNING`, shutdown process, and terminated state | A shut-down pool can reject tasks **even when not full** |

In plain Java's `ThreadPoolExecutor`, the concrete queue is passed via constructor. In Spring's `ThreadPoolTaskExecutor`, `setQueueCapacity(...)` selects the queue type: capacity **greater than 0** creates a `LinkedBlockingQueue`; capacity **0 or negative** creates a `SynchronousQueue` (in practice, use 0 to clearly express direct handoff intent).

### Are Core Threads Pre-Created?

Normally `ThreadPoolExecutor` creates core workers **on demand as tasks arrive**, not necessarily all at startup. You can use `prestartCoreThread()`/`prestartAllCoreThreads()` in Java, or `setPrestartAllCoreThreads(true)` in Spring, if pre-creation is needed.

Thus, "create core threads first" means **prioritizing worker creation within the core limit when a new task arrives and current worker count is still below core**, not that the JVM must create every core worker when the bean initializes.

## 2. ThreadPoolExecutor Task Acceptance Algorithm

Assume the executor is still running and `corePoolSize ≤ maxPoolSize`.

~~~text
             execute(task)
                    |
                    v
         pool below corePoolSize?
                /            \
              YES             NO
              |                |
     try creating core worker  v
        to run task        try queue.offer(task)
              |             /           \
      created ok?        SUCCEEDED     NOT ACCEPTED
         /     \             |              |
       YES     NO            v              v
        |       |      recheck          try creating worker
    accepted    +----> executor          up to maxPoolSize
        |               state            /       \
        v                   |       succeeded   failed
      run task        if shutdown       |        |
                      remove from       v        v
                      queue & reject  run task reject
~~~

This diagram is an educational model of `execute(...)`, omitting some concurrent race-check branches. The exact procedure rechecks state after enqueuing, ensures at least one worker exists when the queue holds work and worker count is 0, and handles races with shutdown. Do not treat the diagram as an atomic, fixed sequence for every concurrent call.

### Step 1 — Prioritize Creating Workers Within Core Limits

If the current worker count is **less than `corePoolSize`**, the executor attempts to create a new worker to run the newly received task. This rule takes precedence over queuing, **even if another worker is idle** in certain situations. If worker creation succeeds, the task is accepted without trying the queue.

For example, with core = 2 and zero workers so far: two tasks arrive while the first is still running—the first brings the pool to 1 worker, and the second brings it to 2 workers.

### Step 2 — Once at Core, Prioritize Queuing

If worker count has reached or exceeded core, the executor invokes an operation equivalent to `workQueue.offer(task)` to **try queuing without waiting for space**.

- If the queue accepts the task, it is accepted and waits for a worker to take it.
- This happens **before** adding workers up to max. Hence a pool can stay at 2 workers even with `maxPoolSize=20` while hundreds of tasks accumulate in the queue.
- After enqueuing, the executor must recheck its state. If a concurrent shutdown occurred and the task can be removed from the queue, the executor rejects that task. If the pool has no remaining workers, it must try starting one to drain the queue.

**"Queued" does not guarantee the task will run immediately**, or finish before the caller's timeout. Queue wait time must be treated as part of end-to-end latency.

### Step 3 — Only When the Queue Rejects, Try Expanding Up to Max

When the queue cannot accept more (for example, a bounded queue is full or `SynchronousQueue` finds no worker waiting for handoff), the executor tries creating a **non-core worker**, provided total worker count is still below `maxPoolSize`.

The new worker immediately runs the newly submitted task. Older tasks sitting in the queue are **not necessarily processed before this new task**, because the expanded worker can start running the new task right away in parallel with active workers. Do not rely on total completion order matching submission order.

Once a task is already in the queue, raising max does not automatically force a running pool to spawn extra workers just to drain the queue; expansion still depends on the task acceptance path, settings, and live activity.

### Step 4 — Reject When Neither Worker Creation Nor Queue Can Accept

If neither the queue nor worker expansion can accept the task, the executor invokes `RejectedExecutionHandler`. In addition, **tasks submitted after the executor has shut down are also rejected** even if worker or queue counts are below their thresholds.

With `AbortPolicy`, calling `execute(task)` throws `RejectedExecutionException` in Java. In `ThreadPoolTaskExecutor`, Spring typically translates rejections into `TaskRejectedException` per the `TaskExecutor` contract. Other policies behave differently—running on the caller or dropping the task—so never conclude "rejected = definitely throws an exception" across every configuration.

## 3. A Task-by-Task Counting Example

Given a pool with:

~~~text
corePoolSize = 2
maxPoolSize  = 4
queueCapacity = 2
~~~

Suppose tasks are long enough that **no task finishes while 7 tasks are submitted sequentially**. No workers are prestarted.

| Incoming task | Decision | Pool size after acceptance | Waiting in queue |
| --- | --- | ---: | ---: |
| 1 | Create core worker #1 | 1 | 0 |
| 2 | Create core worker #2 | 2 | 0 |
| 3 | Put into queue | 2 | 1 |
| 4 | Put into queue | 2 | 2 |
| 5 | Queue full → create worker #3 | 3 | 2 |
| 6 | Queue full → create worker #4 | 4 | 2 |
| 7 | Queue full + max reached → reject (if AbortPolicy) | 4 | 2 |

At that point, the executor holds 4 running tasks and 2 waiting tasks: **6 tasks accepted, the 7th task rejected**.

This is a **fixed-load hypothetical scenario**, not an invariant counting sequence across every multithreaded program. If a worker finishes and pulls a task from the queue before the next task is submitted, the executor can continue enqueuing or handing off work without growing the pool or rejecting. Under concurrent submissions, pool size and queue size are mere snapshots.

### Understanding "Maximum Acceptance Capacity" Accurately

For a fully busy pool with positive bounded queue `Q` and pool max `M`, the number of tasks concurrently residing in the pool is roughly **M running + Q waiting**, *assuming tasks stay held long enough with no other transitions*. This is an instantaneous capacity limit, **not throughput per second**.

Completion capacity also depends on execution time, CPU, I/O, connection resources, and locks. You cannot deduce "max pool 20 means it handles 20,000 requests/second."

## 4. Standalone Java 17 Example Verifying All Four Steps

This example uses JDK's `ThreadPoolExecutor`, which follows the exact task acceptance rules wrapped by Spring's `ThreadPoolTaskExecutor`. `CountDownLatch` holds the first and third workers busy so counts do not depend on machine speed.

Create file **`PoolAdmissionDemo.java`**:

~~~java
import java.util.concurrent.ArrayBlockingQueue;
import java.util.concurrent.CountDownLatch;
import java.util.concurrent.RejectedExecutionException;
import java.util.concurrent.ThreadPoolExecutor;
import java.util.concurrent.TimeUnit;

public class PoolAdmissionDemo {
    private static Runnable hold(CountDownLatch started, CountDownLatch release) {
        return () -> {
            started.countDown();
            try {
                release.await();
            } catch (InterruptedException e) {
                Thread.currentThread().interrupt();
            }
        };
    }

    public static void main(String[] args) throws InterruptedException {
        ThreadPoolExecutor pool = new ThreadPoolExecutor(
                1, 2, 30, TimeUnit.SECONDS,
                new ArrayBlockingQueue<>(1),
                new ThreadPoolExecutor.AbortPolicy());
        CountDownLatch firstStarted = new CountDownLatch(1);
        CountDownLatch thirdStarted = new CountDownLatch(1);
        CountDownLatch release = new CountDownLatch(1);
        try {
            pool.execute(hold(firstStarted, release));
            if (!firstStarted.await(5, TimeUnit.SECONDS)) {
                throw new IllegalStateException("Task 1 did not start");
            }
            System.out.printf("task 1: workers=%d, queue=%d%n",
                    pool.getPoolSize(), pool.getQueue().size());

            pool.execute(() -> { });
            System.out.printf("task 2: workers=%d, queue=%d%n",
                    pool.getPoolSize(), pool.getQueue().size());

            pool.execute(hold(thirdStarted, release));
            if (!thirdStarted.await(5, TimeUnit.SECONDS)) {
                throw new IllegalStateException("Task 3 did not start");
            }
            System.out.printf("task 3: workers=%d, queue=%d%n",
                    pool.getPoolSize(), pool.getQueue().size());

            try {
                pool.execute(() -> { });
                System.out.println("task 4: accepted");
            } catch (RejectedExecutionException expected) {
                System.out.println("task 4: rejected");
            }
        } finally {
            release.countDown();
            pool.shutdown();
            if (!pool.awaitTermination(5, TimeUnit.SECONDS)) {
                pool.shutdownNow();
            }
        }
    }
}
~~~

Compile and run with JDK 17 or newer:

~~~bash
javac --release 17 PoolAdmissionDemo.java
java PoolAdmissionDemo
~~~

**Exact stdout** of the example (verified with JDK 21 compiled at `--release 17`):

~~~text
task 1: workers=1, queue=0
task 2: workers=1, queue=1
task 3: workers=2, queue=1
task 4: rejected
~~~

Explanation:

1. **Task 1:** the pool has 0 workers, below core=1, so it creates the first worker. `firstStarted` confirms the task started, then it waits on `release`.
2. **Task 2:** the pool is at core and the worker is waiting on the latch, so the second task enters the queue (capacity=1); it is not running yet.
3. **Task 3:** the queue is full and the pool is below max=2, so it creates a second worker for the new task. `thirdStarted` confirms the second worker also started and is waiting.
4. **Task 4:** the queue is still full and both workers exist, so `AbortPolicy` throws an exception; the program prints `rejected`.
5. The `finally` block releases the latch so accepted tasks can exit, then closes the pool. Never leave workers blocked indefinitely in real applications.

The key point is that **task 2 was queued before task 3, yet task 3 ran immediately on worker #2**. Therefore, *acceptance* order does not imply *start*, *completion*, or *database commit* order.

## 5. Behavior Changes by Queue Type

### 5.1. Bounded Positive Queue

Example:

~~~java
new ThreadPoolExecutor(
    2, 4, 60, TimeUnit.SECONDS,
    new java.util.concurrent.ArrayBlockingQueue<>(10)
);
~~~

This is an **illustrative Java instantiation expression**, not a standalone program; import `ThreadPoolExecutor` and `TimeUnit` if placed in another file.

With sufficiently long-running tasks, the first two workers are created up to core=2, the next ten tasks can be queued, and only then does the pool expand up to max=4; upon saturation it rejects via the handler. A finite queue bounds wait depth and surfaces overload signals earlier, though it does not automatically choose the right bound: an oversized queue can still accumulate timeouts.

### 5.2. Very Large or "Practically Unbounded" Queue

Spring example:

~~~java
executor.setCorePoolSize(2);
executor.setMaxPoolSize(100);
executor.setQueueCapacity(Integer.MAX_VALUE);
~~~

These are **configuration calls inside an already created `ThreadPoolTaskExecutor` bean**, not a standalone program.

Once 2 workers exist, the massive queue keeps accepting tasks and typically **never fills under realistic load**, so the pool almost never has a reason to grow from 2 to 100. "Max equal to 100" does not mean 100 workers exist; it is merely the ceiling *if worker expansion is triggered*. Do not treat `Integer.MAX_VALUE` as infinite memory: every task still occupies heap and can exhaust memory or cause severe latency long before hitting that arithmetic bound.

The direct default configuration of `ThreadPoolTaskExecutor` in Spring Framework 6.x is core=1, max=`Integer.MAX_VALUE`, queueCapacity=`Integer.MAX_VALUE`. This typically behaves nearly like a single worker processing tasks while additional tasks enter the queue. **Do not confuse this class's defaults with version-specific defaults or auto-configuration in Spring Boot.**

### 5.3. `queueCapacity=0`: Direct Handoff, No Waiting Task Storage

In Spring:

~~~java
executor.setCorePoolSize(2);
executor.setMaxPoolSize(8);
executor.setQueueCapacity(0);
~~~

`ThreadPoolTaskExecutor` selects `SynchronousQueue`. This is not a queue that buffers 0 or more tasks like `LinkedBlockingQueue`; it is a **direct handoff point**: `offer` succeeds only when a worker is ready to receive it immediately.

If existing workers are busy and none is available for handoff, the executor tries growing the pool from core toward max. If max is already reached and handoff still fails, the task is rejected. This setup avoids building backlogs in the executor queue, yet can cause rapid thread growth during sudden traffic spikes; **you must cap max and account for downstream limits**.

### 5.4. Fixed-Size Pool and core=0

- If `corePoolSize == maxPoolSize`, the pool has no expansion band beyond core; when all workers are busy, tasks must wait in the queue or be rejected.
- If `corePoolSize=0` and `maxPoolSize>0`, the pool has no core workers. The queuing mechanism and the rule ensuring a worker exists when the queue holds tasks can lead to a different path than positive-core examples; do not infer "no worker will ever run."
- `allowCoreThreadTimeOut(true)` allows core workers to expire after idle periods too. `prestartAllCoreThreads(true)` pre-creates core workers; these two settings affect worker lifetimes over time without reversing the core/queue/max acceptance priority.

| Strategy | Pros | Risks to weigh |
| --- | --- | --- |
| Bounded queue | Caps backlog, allows pool expansion after queue fills, makes overload visible | Too large causes long waits; too small triggers early rejections |
| Nearly unbounded queue | Absorbs bursts without early rejections | Easy task accumulation, rising latency/memory; max rarely used |
| SynchronousQueue | Immediate handoff, no backlog held in executor queue | Rapid worker growth; rejects when unable to accept; heavy downstream pressure |
| Fixed-size pool | Easy-to-reason concurrency cap | When tasks block long, queue and wait times can grow |

## 6. Spring Framework: Configuring ThreadPoolTaskExecutor Intentionally

`ThreadPoolTaskExecutor` is a Spring bean managing a `ThreadPoolExecutor`. When an application uses `@Async`, you can route tasks to an explicitly configured bean instead of relying on defaults.

Example **integration code for Spring Framework 6.x / Spring Boot 3.x with Java 17+**, requiring Spring dependencies and component scanning; not a file runnable directly via standalone `javac`.

File `ConcurrencyConfig.java`:

~~~java
package example.concurrency;

import java.util.concurrent.ThreadPoolExecutor;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.scheduling.annotation.EnableAsync;
import org.springframework.scheduling.concurrent.ThreadPoolTaskExecutor;

@Configuration
@EnableAsync
public class ConcurrencyConfig {
    @Bean("boundedExecutor")
    public ThreadPoolTaskExecutor boundedExecutor() {
        ThreadPoolTaskExecutor executor = new ThreadPoolTaskExecutor();
        executor.setCorePoolSize(2);
        executor.setMaxPoolSize(4);
        executor.setQueueCapacity(10);
        executor.setKeepAliveSeconds(30);
        executor.setThreadNamePrefix("bounded-");
        executor.setRejectedExecutionHandler(new ThreadPoolExecutor.AbortPolicy());
        return executor;
    }
}
~~~

File `ReportService.java`:

~~~java
package example.concurrency;

import java.util.concurrent.CompletableFuture;
import org.springframework.scheduling.annotation.Async;
import org.springframework.stereotype.Service;

@Service
public class ReportService {
    @Async("boundedExecutor")
    public CompletableFuture<String> export(String reportId) {
        // Illustrative; real I/O needs timeouts and proper error handling.
        return CompletableFuture.completedFuture("exported:" + reportId);
    }
}
~~~

When another bean invokes `reportService.export("R1")` **through the Spring proxy**, Spring dispatches the work to `boundedExecutor`. If workers and queue have room, the task is accepted in order: core → queue → scale to max. Once saturated, submission can trigger `TaskRejectedException` per the Spring API, even when the method returns `CompletableFuture`. You must handle both **immediate submission errors at the caller** and **errors occurring while the task runs**.

Notes:

- `@EnableAsync` is required to activate annotation processing; calling `this.export(...)` on the same instance under default proxy mode will not trigger `@Async` as expected.
- `@Async` does not remove limits on pools, queues, connection pools, or CPU. It simply dispatches work to the chosen execution mechanism.
- The numbers 2/4/10 only illustrate the ordering; choose values from workload measurements rather than shipping them to production without verifying system capacity.
- Within Spring's lifecycle, an executor bean is managed by Spring for initialization and shutdown. If you instantiate a Java executor manually in business code, you must manage shutdown and pending tasks yourself.
- When a task inside an executor submits subtasks to **the same executor** and blocks on `Future.get()`/`join()`, **thread-pool starvation** can occur: workers all sit waiting while subtasks are stuck in the queue. Raising max might mask symptoms in one case, never fix circular dependencies.

### 6.1. "I Raised Max to 50, Yet Active Count Is Only 2"

First inspect `queueCapacity`, queue depth, `corePoolSize`, `getPoolSize()`, and `getActiveCount()`. If the queue is still accepting tasks, the pool **prioritizes queuing** per the algorithm, so max may not have been triggered yet. Examine arrival rate, execution duration, queue wait, and downstream capacity together.

Also distinguish:

- `getPoolSize()`: number of currently existing workers.
- `getActiveCount()`: approximate number of workers actively executing tasks.
- `getQueueSize()`: number of tasks waiting in the queue (on Spring versions that support it).
- `getCorePoolSize()` and `getMaxPoolSize()`: configured bounds, **not current worker counts**.

Do not declare the pool "broken" from a single snapshot; observe trends over time alongside throughput, p95/p99, and rejections.

## 7. Rejection Policies: The Final Step Has Multiple Options

Java's `ThreadPoolExecutor` provides four standard policies. Spring allows configuring the corresponding `RejectedExecutionHandler`:

| Policy | Under overload | Operational meaning |
| --- | --- | --- |
| `AbortPolicy` | Throws `RejectedExecutionException` (surfaced in Spring as `TaskRejectedException`) | Easy to detect overload and return feedback to callers |
| `CallerRunsPolicy` | If pool is not shut down, **the thread calling `execute` runs the task itself** | Creates natural backpressure, but blocks the caller and increases caller latency |
| `DiscardPolicy` | Drops the task without raising an error via the policy | Very risky when business requires guaranteed processing; tasks can vanish silently |
| `DiscardOldestPolicy` | Drops the head of the queue and retries submitting the new task if pool is not shut down | Can lose the longest-waiting task, break FIFO expectations, and leave waiting Futures incomplete |

**Never assume `CallerRunsPolicy` is "safe async."** If the caller is an HTTP request thread, it can be forced to run background work itself. If the caller is a Reactor event-loop thread, it can block the event loop and stall many requests. For tasks with side effects or delivery guarantees, explicitly define when tasks may be dropped, retried, rejected, or persisted to a durable queue.

Where correctness matters, `AbortPolicy` plus submission error handling is easier to monitor than silent-drop policies. Changing policies **does not increase real capacity** of CPU, database, or external services.

### Responding When the Executor Cannot Accept More Tasks

Depending on application architecture, you can:

1. Return an appropriate overload error/response at the request boundary rather than hanging indefinitely.
2. Cap concurrent in-flight tasks (*bulkhead* / semaphore) before submitting.
3. Apply timeouts and controlled cancellation; `Future.get(timeout)` only stops the caller from waiting, without automatically stopping the background task.
4. If business guarantees later execution, write work to a **durable queue** with ACK/retries/idempotency instead of merely inflating the executor's in-memory queue.
5. Consider retries with backoff and jitter where allowed, avoiding thundering herds when downstream is already degraded.

## 8. Why This Order Matters for Latency and Resources

### 8.1. A Large Queue Is Not Automatically Good

A queue lowers rejection risk during brief bursts, but when submission outpaces completion over sustained periods, backlogs grow and **queue latency** climbs. An "accepted" task may no longer be valuable when it finally starts: the request timed out long ago, the user canceled, or business data changed.

Do not tune the queue solely to drive rejections to zero. A system that says "accepted" while holding tasks for minutes can be worse than one that rejects early and clearly.

### 8.2. Max Threads Is Not Throughput

Suppose each task uses a database connection for 200 ms and the DB pool has only 10 connections. Under ideal conditions, the DB step's ceiling is roughly 10 / 0.2 = **50 ops/sec** if nothing else bottlenecks. Raising `maxPoolSize` from 16 to 160 creates zero extra connections; extra workers may just wait on the DB. This calculation **illustrates an ideal bound**, not a measurement of real application throughput.

CPU-bound workloads are typically bounded by usable CPU cores; I/O-bound workloads can benefit from higher concurrency, provided you verify timeouts, connection limits, memory, and downstream capacity. Excessive threads also increase scheduling overhead, stack/native memory, lock contention, and context switching.

### 8.3. Acceptance Order Does Not Guarantee FIFO Completion

Even when the queue is FIFO, a new task can be picked up immediately by a non-core worker once the queue is full while older tasks remain queued. Multiple workers execute concurrently with varying durations. Therefore:

- Do not rely on submission order to guarantee state update order.
- If business logic needs per-key ordering (for example, same `customerId`), design per-key serialization, partitioning, or controlled state transitions.
- If exact once-only business processing is required, an in-memory executor alone provides neither durability nor exactly-once semantics.

## 9. Diagnostic Checklist When the Pool Saturates

When encountering timeouts, growing queues, or rejections, collect **simultaneously**:

| Question | Evidence |
| --- | --- |
| How many workers exist/are busy? | `poolSize`, `activeCount`, thread dump |
| Where are the tasks? | Queued count, age of tasks in queue, processing time |
| Why isn't the pool growing? | Core/max/queueCapacity, whether queue is full, policy limits |
| Why are workers busy so long? | Stacks: CPU, lock waits, HTTP, DB, `Future.get()` |
| Why are tasks rejected? | Executor saturation, shutdown, rejection count, logs/traces |
| Would more threads help? | Measure throughput, p95/p99, CPU, DB connections, and backend latency before/after |

Analyze by root cause:

1. Verify the exact executor bean used by requests/`@Async`; avoid inspecting the wrong pool.
2. Check the **effective** `corePoolSize`, `maxPoolSize`, `queueCapacity`, and rejection policy values.
3. Inspect worker stack traces and queue wait times. If workers are all blocked on I/O/DB, locate downstream limits first.
4. Distinguish a shut-down pool from a saturated pool; both reject tasks, yet fixes differ.
5. Set concurrency budgets, queue bounds, timeouts, and overload responses; validate with ramp-up and sustained load tests.
6. After each change, compare completion rate, p95/p99, timeouts, rejections, connection usage, and resources.

Common pitfalls:

- **Misconception:** "Setting max=100 means up to 100 tasks run immediately at any time." **Reality:** after core, the queue is normally prioritized; max is only the ceiling when expansion triggers.
- **Misconception:** "Queue capacity=0 means the executor always rejects." **Reality:** `SynchronousQueue` can hand off to a waiting worker or trigger expansion up to max.
- **Misconception:** "A rejected task definitely ran partially." **Reality:** `AbortPolicy` rejects the task before it executes for that submission.
- **Misconception:** "Zero rejections means the system is healthy." **Reality:** a large queue can hide backlogs and turn overload into timeouts/memory pressure.
- **Misconception:** "Shutdown just frees workers." **Reality:** shutdown alters new-task acceptance; new submissions may be rejected even when capacity remains.

## 10. Reasoning Exercises and Answers

**Question 1.** Configured with core=3, max=8, queueCapacity=100. Three workers are busy; where is the fourth task usually accepted?

**Answer:** into the queue, because core is reached and the queue still has space. It does not immediately scale to 4 workers.

**Question 2.** Configured with core=2, max=4, queueCapacity=2. Four tasks are running or queued as in Section 3's table; how is the fifth task accepted?

**Answer:** after tasks 1–2 create core workers and tasks 3–4 enter the queue, task 5's queue `offer` fails, so the pool tries creating worker #3 (still below max).

**Question 3.** If the seventh task is rejected under Question 2's configuration, can you immediately conclude the pool has shut down?

**Answer:** no. With 4 busy workers and 2 queued tasks, a saturated pool also triggers rejection. Check pool state and metrics.

**Question 4.** Why does `queueCapacity=Integer.MAX_VALUE` usually prevent `maxPoolSize` from taking effect?

**Answer:** once core is reached, the queue almost always accepts the task, so the "queue cannot accept → create non-core worker" branch rarely runs.

**Question 5.** How does `CallerRunsPolicy` reduce dropped tasks, and at what cost?

**Answer:** the caller runs the task itself if the pool is still running, slowing down submission rates. In exchange, the caller blocks, which can increase latency or stall request/event-loop threads.

**Question 6.** If increasing `maxPoolSize` leaves throughput unchanged, what should you inspect?

**Answer:** the queue may not be full so max is unused; or the bottleneck is DB/HTTP connections, CPU, locks, or backend latency. Compare queue wait, active/pool size, and downstream latency.

**Question 7.** Does a third task running immediately on a new worker ahead of a queued second task violate FIFO?

**Answer:** no. The internal queue can be FIFO for tasks **already in the queue**, while the third task is handed directly to a non-core worker and does not wait behind the second task.

## 11. References

- Oracle Java SE 17 — `ThreadPoolExecutor` (core size, queueing, rejection): https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/concurrent/ThreadPoolExecutor.html
- Oracle Java SE 17 — `BlockingQueue`: https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/concurrent/BlockingQueue.html
- Oracle Java SE 17 — `SynchronousQueue`: https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/concurrent/SynchronousQueue.html
- Spring Framework 6.x — `ThreadPoolTaskExecutor` API: https://docs.spring.io/spring-framework/docs/6.1.14/javadoc-api/org/springframework/scheduling/concurrent/ThreadPoolTaskExecutor.html
- Spring Framework — Task Execution and Scheduling: https://docs.spring.io/spring-framework/reference/integration/scheduling.html

# Experimenting With Both Thread Pool and Queue Reaching Their Limits

## 1. Goal: Intentionally Creating an Overload State

In Spring Framework, `ThreadPoolTaskExecutor` typically executes work submitted via `@Async` or `TaskExecutor.execute(...)` calls. Under heavy request volume, a pool can end up with **all workers busy** and **its pending queue also full**. If yet another task arrives, the executor cannot accept it normally: it applies its **rejection policy**.

This lab does not merely state "executors have limits"—it builds a reproducible scenario to verify:

- Which tasks run on workers and which sit in the queue?
- Once `corePoolSize` is reached, are new tasks queued or are extra threads spawned?
- Once the queue is full, does the pool keep expanding up to `maxPoolSize`?
- When **both the pool and queue are full**, how is the next task handled?
- How do we prove this behavior without relying on the randomness of `Thread.sleep(...)`?
- In Spring, how do `TaskRejectedException` and `RejectedExecutionHandler` relate?

The focus is **overload and rejection**. Never confuse a task that **was not accepted** with a task that **ran and failed in business logic**.

## 2. Admission Rules of ThreadPoolExecutor

Spring's `ThreadPoolTaskExecutor` wraps a `java.util.concurrent.ThreadPoolExecutor`. When using a bounded queue, three parameters must be considered together:

| Property | Meaning |
| --- | --- |
| `corePoolSize` | Number of core threads the executor prioritizes creating when receiving initial tasks |
| `maxPoolSize` | Ceiling on worker threads in the pool |
| `queueCapacity` | Number of unstarted tasks that can wait in the queue |
| `RejectedExecutionHandler` | How to handle when no more tasks can be accepted, or the pool has shut down |

Rules of `execute(Runnable)` in `ThreadPoolExecutor`, simplified for standard configurations:

1. **Current worker count below core:** create a worker to run the new task.
2. **Core reached:** try placing the new task into the queue.
3. **Queue cannot accept the task:** try creating another worker if below max.
4. **Queue full and workers at max:** invoke the rejection handler.
5. **Pool has shut down:** can also reject, **even when not saturated**. Therefore, distinguish the two causes of rejection.

Common misconception: **max threads are not necessarily used before the queue**. If core=1, max=10, and the queue still has space, tasks submitted after the first worker keep going into the queue; the executor only spawns workers beyond core once the queue cannot accept work.

A virtually unbounded queue keeps the pool from ever needing to expand past core. Conversely, `queueCapacity=0` in `ThreadPoolTaskExecutor` corresponds to a direct handoff strategy (`SynchronousQueue`), not an infinitely capacious queue.

## 3. Predicting With core=1, max=2, queue=1

Use a small configuration to trace every step:

```text
corePoolSize  = 1
maxPoolSize   = 2
queueCapacity = 1
handler       = AbortPolicy
```

Assume tasks #1 and #3 are **held unfinished**, so the two workers they occupy remain busy. Task #2 is short yet must queue.

| Submission | Behavior | Busy workers | Waiting tasks |
| --- | --- | ---: | ---: |
| #1 | Creates core worker, runs task #1 | 1 | 0 |
| #2 | Core worker busy, queue accepts task #2 | 1 | 1/1 |
| #3 | Queue full, creates second worker to run task #3 | 2/2 | 1/1 |
| #4 | Both workers and queue full, `AbortPolicy` rejects | 2/2 | 1/1 |

Only after releasing both workers is task #2 pulled from the queue and executed. **A total of 3 tasks are accepted**, while task #4 never runs.

```text
After submitting task #3, before submitting task #4:

+-----------------------+  +-----------------------+
| worker 1: task #1     |  | worker 2: task #3     |
| waiting on latch      |  | waiting on latch      |
+-----------------------+  +-----------------------+
         active workers = 2/2

queue (capacity 1): [ task #2 ]
         queue size = 1/1

submit task #4
  -> no worker slots left
  -> no queue space left
  -> AbortPolicy: RejectedExecutionException
```

This is a **point-in-time snapshot**, not a permanent state: if task #1 finishes before #4 is submitted, the worker can pick up task #2, freeing a queue slot so task #4 need not be rejected. That is why we must construct a controlled experiment.

## 4. Standalone Java 17: Reproducing Rejection With CountDownLatch

This example uses only the JDK 17 standard library. It requires no Spring, Maven, or server. Latches confirm two tasks are genuinely running and then **hold them at a barrier** until after the test submission.

Create file **`PoolQueueLimitDemo.java`**:

```java
import java.util.concurrent.ArrayBlockingQueue;
import java.util.concurrent.CountDownLatch;
import java.util.concurrent.RejectedExecutionException;
import java.util.concurrent.ThreadPoolExecutor;
import java.util.concurrent.TimeUnit;
import java.util.concurrent.atomic.AtomicInteger;

public final class PoolQueueLimitDemo {
    private static void awaitOrFail(CountDownLatch latch, String stage)
            throws InterruptedException {
        if (!latch.await(10, TimeUnit.SECONDS)) {
            throw new IllegalStateException("Timeout at " + stage);
        }
    }

    public static void main(String[] args) throws Exception {
        CountDownLatch firstStarted = new CountDownLatch(1);
        CountDownLatch bothStarted = new CountDownLatch(2);
        CountDownLatch release = new CountDownLatch(1);
        AtomicInteger completed = new AtomicInteger();

        Runnable heldTask = () -> {
            firstStarted.countDown();
            bothStarted.countDown();
            try {
                release.await();
                completed.incrementAndGet();
            } catch (InterruptedException ex) {
                Thread.currentThread().interrupt();
            }
        };
        Runnable shortTask = () -> {
            completed.incrementAndGet();
        };

        ThreadPoolExecutor pool = new ThreadPoolExecutor(
                1,                             // corePoolSize
                2,                             // maxPoolSize
                30, TimeUnit.SECONDS,          // keepAlive beyond core
                new ArrayBlockingQueue<>(1),   // queueCapacity = 1
                new ThreadPoolExecutor.AbortPolicy()
        );

        try {
            // Task #1: creates the core worker and holds it unfinished.
            pool.execute(heldTask);
            awaitOrFail(firstStarted, "first started");

            // Task #2: core worker is busy so the queue takes 1 task.
            pool.execute(shortTask);

            // Task #3: queue is full, so the pool must create a second worker.
            pool.execute(heldTask);
            awaitOrFail(bothStarted, "both started");

            // Both workers are still awaiting release, so task #2 stays queued.
            int active = pool.getActiveCount();
            int queued = pool.getQueue().size();
            if (active != 2 || queued != 1) {
                throw new IllegalStateException(
                        "Unexpected state: " + active + "/" + queued);
            }
            System.out.println("active=" + active + ", queued=" + queued);

            boolean fourthRejected = false;
            try {
                // Task #4: both max=2 and queue=1 are out of capacity.
                pool.execute(shortTask);
            } catch (RejectedExecutionException ex) {
                fourthRejected = true;
            }
            System.out.println("fourthRejected=" + fourthRejected);
        } finally {
            // Always release workers, even if the test fails.
            release.countDown();
            pool.shutdown();
            if (!pool.awaitTermination(10, TimeUnit.SECONDS)) {
                pool.shutdownNow();
                throw new IllegalStateException("Pool did not terminate");
            }
        }

        System.out.println("completed=" + completed.get());
    }
}
```

Run in the directory containing the source file:

```bash
javac PoolQueueLimitDemo.java
java PoolQueueLimitDemo
```

**Standard output when the program finishes normally:**

```text
active=2, queued=1
fourthRejected=true
completed=3
```

### Why Is the Result Stable?

- Main does not submit task #2 until `firstStarted` confirms task #1 is running. Task #1 still awaits `release`, so the first worker cannot pick up task #2 yet.
- Submitting task #2 fills the 1-slot queue. Submitting task #3 forces the pool to spawn a second worker, since max still allows it.
- Main awaits `bothStarted` to know **both workers have started**. Both are waiting on the same `release`, so before opening the latch, active stays at 2 and queue stays at 1.
- Submitting task #4 at that point deterministically hits `AbortPolicy`'s rejection branch. The exception is thrown on the **submitting thread** (main) and caught there, not inside task #4.
- `finally` opens the latch, the two held tasks finish, and queued task #2 is processed by a worker. `awaitTermination(...)` guarantees all three tasks finish before printing `completed=3`.
- Task #4 was never accepted, so it is not counted in `completed`.

The 10-second timeout detects an overly slow or hung execution environment, not a business executor timeout. If the test times out, it throws an error instead of pretending to pass. In the normal run above, the stdout lines are deterministic regardless of worker scheduling order.

### Why Is Using Only sleep Insufficient?

An example is unreliable if the author simply makes each task sleep a few milliseconds and fires four tasks in a row: the first task might finish before submission #4. Then the pool has free room and does not reject, yielding flaky pass/fail runs. A latch or barrier must be used to **hold the full state**, rather than creating estimated delays.

## 5. Configuring the Same Scenario in Spring ThreadPoolTaskExecutor

`ThreadPoolTaskExecutor` is Spring's convenient adapter/configuration class for JDK thread pools. The snippets below are **classes integrated into a Spring Framework/Spring Boot application**, not a JDK-only `javac` program. They require a Spring context, scheduling support, and proper application configuration.

**`AsyncConfiguration.java`**:

```java
import java.util.concurrent.ThreadPoolExecutor;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.scheduling.annotation.EnableAsync;
import org.springframework.scheduling.concurrent.ThreadPoolTaskExecutor;

@Configuration(proxyBeanMethods = false)
@EnableAsync
public class AsyncConfiguration {

    @Bean("boundedExecutor")
    public ThreadPoolTaskExecutor boundedExecutor() {
        ThreadPoolTaskExecutor executor = new ThreadPoolTaskExecutor();
        executor.setCorePoolSize(1);
        executor.setMaxPoolSize(2);
        executor.setQueueCapacity(1);
        executor.setThreadNamePrefix("bounded-");
        executor.setRejectedExecutionHandler(
                new ThreadPoolExecutor.AbortPolicy());
        return executor;
    }
}
```

Spring initializes and closes the executor bean according to its lifecycle. Example of a service using that exact bean:

**`JobService.java`**:

```java
import java.util.concurrent.CompletableFuture;
import org.springframework.scheduling.annotation.Async;
import org.springframework.stereotype.Service;

@Service
public class JobService {

    @Async("boundedExecutor")
    public CompletableFuture<String> process(String id) {
        // Sample work; replace with real processing when integrating.
        String result = "processed:" + id;
        return CompletableFuture.completedFuture(result);
    }
}
```

**Notes when running in practice:**

1. `@EnableAsync` enables asynchronous method invocation. `@Async("boundedExecutor")` selects the exact executor, avoiding confusion with another Spring Boot auto-configured executor.
2. `process(...)` must be invoked **through the Spring-managed proxy**, such as from another bean that has `JobService` injected. Calling `this.process(...)` inside the same bean in proxy mode usually bypasses `@Async`.
3. This sample method runs very fast, so firing four sequential calls **does not guarantee** pool saturation. To test at the Spring layer, hold tasks using a latch or fake dependency as in section 4.
4. With `ThreadPoolTaskExecutor`, Spring usually signals refusal to accept a task via `org.springframework.core.task.TaskRejectedException`, extending `RejectedExecutionException`. This is a **submission** error that can exit directly from the `@Async` call before the caller receives a `CompletableFuture`.
5. If a task is accepted and then fails, the caller observes it through the accepted job's Future/callback; that is **not** a rejection.
6. With `@Async void`, internal execution failures have no Future for the caller to track and require configuring the corresponding exception-handling mechanism.

Example **snippet at the caller boundary**, with an injected `jobService` field:

```java
try {
    CompletableFuture<String> future = jobService.process("A-100");
    future.whenComplete((value, error) -> {
        if (error != null) {
            // Task was accepted, yet hit an error during execution.
        }
    });
} catch (org.springframework.core.task.TaskRejectedException ex) {
    // Executor refused the task: return an overload error or persist/retry work.
}
```

Do not catch rejection and silently discard important business work. For work that must run even after a restart, you need a durable queue/job store and idempotency, not just an in-RAM executor queue.

## 6. Rejection in Java and Spring: Four Important Policies

| Handler | When pool/queue is full | What to watch out for |
| --- | --- | --- |
| `AbortPolicy` | Throws `RejectedExecutionException`; Spring wrapper usually throws `TaskRejectedException` | Caller knows the task was not accepted and must handle it |
| `CallerRunsPolicy` | Caller runs the task itself (if executor has not shut down) | Does not reject via exception, yet **blocks the caller**; task runs outside worker pool |
| `DiscardPolicy` | Silently drops the task | Easy to lose work; Future may never complete as waiters expect |
| `DiscardOldestPolicy` | Drops the old task at the head of the queue and retries submitting | Can lose older work, break ordering; inspect retry semantics carefully |

**Warning on CallerRunsPolicy:** if an HTTP request thread calls `execute(...)`, when the pool saturates the request thread may run slow work itself. This acts as backpressure, yet can sharply increase request latency. If the caller is an event-loop or a nested job awaiting a latch opened by the caller itself, blocking or deadlock can occur.

If you replace `AbortPolicy` in the Java example with `CallerRunsPolicy`, task #4 will run on main (since `shortTask` is non-blocking), so **stdout must change**. You cannot keep expecting `fourthRejected=true`. With DiscardPolicy, task #4 can be dropped without throwing an exception; you must count executed tasks to detect lost work.

Never interpret "no exception" as "accepted and processed successfully."

## 7. Varying Parameters to Reason About Outcomes

To run a worthwhile experiment, **predict the state before running**, then change exactly one parameter and verify. Keep workers held on latches so the queue does not drain prematurely.

| Configuration | Submission sequence while workers are held | First task rejected by AbortPolicy |
| --- | --- | --- |
| core=1, max=2, queue=1 | #1 runs, #2 queued, #3 runs, #4 rejected | #4 |
| core=2, max=2, queue=1 | #1/#2 run, #3 queued, #4 rejected | #4 |
| core=1, max=3, queue=1 | #1 runs, #2 queued, #3/#4 run, #5 rejected | #5 |
| core=2, max=4, queue=2 | #1/#2 run, #3/#4 queued, #5/#6 run, #7 rejected | #7 |
| core=1, max=2, queue=0 | #1/#2 run, no queue, #3 rejected | #3 |

The prediction table assumes running tasks **have not finished**, no worker is idle, the executor has not shut down, and AbortPolicy is used. If workers free up or finish between submissions, which submission gets rejected can differ.

### When the Queue Is Too Large

Suppose core=1, max=8, and `queueCapacity` is huge. Task #1 runs on core, and many subsequent tasks get accepted into the queue. The pool may stay at just one worker because the queue has not filled; max=8 **does not force** the pool to spawn seven extra workers immediately.

Consequence: long backlogs, growing memory, and deteriorating p95/p99 latency, while rejections happen very late or not until another limit breaks. Therefore, never set an unbounded queue just to "avoid overload errors."

### When `queueCapacity = 0`

In `ThreadPoolTaskExecutor`, value 0 uses a `SynchronousQueue`. It holds no waiting tasks. Tasks must be handed to an available worker or trigger a new worker if below max. Once all workers are busy and max is reached, submissions reject according to the handler.

Such a pool reacts quickly to load spikes, yet can spawn many threads rapidly; apply an appropriate max bound and control downstream capacity.

## 8. Which Metrics Should You Observe?

During a latch-held test, observe:

```text
poolSize              current number of workers existing in the pool
activeCount           number of workers currently running tasks
queueSize             number of unstarted tasks waiting
queueRemaining        remaining queue capacity
rejectedSubmissions   number of tasks rejected at the submit boundary
completedTasks        number of tasks that have finished running
```

On Spring's `ThreadPoolTaskExecutor`, you can inspect `getPoolSize()`, `getActiveCount()`, and `getQueueSize()`. After the bean is initialized, the underlying JDK executor via `getThreadPoolExecutor()` provides `getQueue()` and `getCompletedTaskCount()`. These metrics reflect **mutable state**; calling multiple getters sequentially does not guarantee an atomic snapshot in a freely running system.

In particular:

- `getPoolSize() == maxPoolSize` does **not** prove the queue is full.
- `getQueueSize() == queueCapacity` does **not** prove all workers are busy.
- Even when both are true, you still need to check whether the pool is shutting down, whether workers are about to finish, and which rejection policy is active.
- `getCompletedTaskCount()` is an approximate pool counter; it does not necessarily count tasks executed outside the pool by `CallerRunsPolicy`.
- To get an exact rejection count, count right inside the rejection handler or where `TaskRejectedException`/`RejectedExecutionException` is caught, with proper metrics and logs.

In Spring Boot applications with Micrometer/Actuator, depending on configuration and how binders discover the executor, you can track active threads, queue depth, completed tasks, utilization, rejections, and wait times. Do not assume every metric appears automatically; verify actual instrumentation.

## 9. A Reliable Testing Procedure

1. **Pin configuration and handler:** declare core, max, queueCapacity, and AbortPolicy. Note JDK/Spring versions.
2. **Hold workers with latches:** tasks signal "started" and then await release. Tests must not rely primarily on `Thread.sleep(100)`.
3. **Fill the queue:** once the core worker starts, submit short tasks into the queue while core stays held; continue submitting to expand up to max.
4. **Confirm saturation:** wait for all required workers to start; measure active workers and queue size before submitting the task expected to reject.
5. **Check exceptions at the right place:** catch errors from `execute/submit` or the Spring proxy caller. Do not place catch inside a task that was never accepted.
6. **Release and clean up properly:** open latches in `finally`, shut down, and wait for all valid tasks to finish. A test can hang forever if cleanup is missing.
7. **Count completed work:** assert total executed tasks, not just a single "rejected" log line. With three accepted tasks and one rejected task, you must never count four successes.
8. **Test recovery:** after workers release and the queue empties, try submitting a new task **before shutdown** to prove saturation was temporary. Submitting after shutdown tests shutdown rejection, not pool fullness.
9. **Swap handlers and re-predict:** CallerRuns, Discard, and DiscardOldest behave differently from Abort; do not reuse AbortPolicy expectations.
10. **Run integration load tests:** test with real datasources, HTTP clients, and pod counts. Executor saturation is only one piece of system behavior.

With JUnit, you can write matching assertions like `assertEquals(2, active)`, `assertEquals(1, queueSize)`, and `assertThrows(RejectedExecutionException.class, ...)` when testing a JDK executor. For a Spring executor, catch/assert `TaskRejectedException`. The test runner should also enforce timeouts and teardown to avoid thread leaks if an assertion fails.

## 10. Impact When Moving Configuration to Production

Small settings like core=1, max=2, queue=1 are for illustration, not default values to use across every application. Choose parameters based on task characteristics:

- **CPU-bound:** too many workers contend for CPU, increasing context switching; account for machine cores and load levels.
- **I/O-bound:** workers may wait a long time on JDBC/HTTP; adding workers does not automatically add DB connections or downstream quotas.
- **Deadline-sensitive tasks:** if a task sits in the queue past its deadline, even succeeding later can be useless; enforce a queue-wait budget/admission policy.
- **Critical tasks:** if rejected and not persisted durably, work can be lost. Use bounded retries, backoff, idempotency, or a job queue.
- **Multiple work sources:** background batches, HTTP requests, and event consumers may need separate pools or bulkheads so they do not starve one another.
- **Multiple instances:** worker and queue limits apply **per executor per JVM**; four pods each with max=2 can mean eight workers across the service, not counting other executors.
- **Bursty load:** queues help absorb short bursts, yet cannot solve arrival rates that stay persistently higher than processing rates.

At a moment when the pool is completely full and no worker is idle, a pool can hold at most **`maxPoolSize` running tasks + `queueCapacity` waiting tasks**. This is the number of tasks coexisting inside **one executor**, not total tasks processed over its lifetime. With CallerRunsPolicy, callers can also run tasks outside the pool, so that formula cannot serve as an upper bound on all application activity.

**Early rejection can be the right behavior:** returning a clear overload response is better than accepting unbounded work and timing out across the board. APIs can return HTTP 429 or 503 depending on cause/contract; message consumers need appropriate ack/nack and redelivery handling.

## 11. Common Mistakes

**Mistake: "I raised max, yet active still equals core."** While the queue still accepts work, the pool prioritizes queuing before expanding beyond core. Check `queueCapacity` and queue depth.

**Mistake: "Queue is full yet tasks are still accepted—Java must be broken."** If workers can still expand up to max, the executor creates extra workers. A full queue **alone** is not a rejection condition.

**Mistake: "Pool reached max yet tasks are still accepted."** If the queue still has space, tasks enter the queue. You must check that **both** are out of capacity.

**Mistake: "Task #4 was rejected, yet I see no logs inside `run()`."** The task never ran, so code inside `run()` cannot log. Catch the exception on the submitting thread.

**Mistake: "I only used `Thread.sleep` so the test passes sometimes and fails sometimes."** Sleep intervals do not verify workers reached a specific state. Use `CountDownLatch`/barriers and wait on concrete milestones.

**Mistake: "No requests are rejected, so the system is healthy."** With a huge queue, backlogs and latency can climb dangerously without triggering rejections. Measure queue wait, heap, p95/p99 latency, and throughput.

**Mistake: "`@Async` always returns immediately."** Submission can throw `TaskRejectedException`; `CallerRunsPolicy` can execute the task on the caller. `@Async` is not an absolute latency guarantee.

**Mistake: "`DiscardPolicy` threw no exception, so the work finished."** No exception may simply mean the task was dropped. Never use a silent-drop policy when business logic requires completion.

**Mistake: "A running task throwing an error is saturation."** Worker execution errors differ from rejection at the submission gate. With `submit(...)`, worker errors are normally stored in the `Future` and need `get()`/callbacks to observe.

**Mistake: "The test hangs after an assertion fails."** Without opening latches and shutting down in `finally`, workers can wait forever. Cleanup and timeouts are integral parts of the test.

**Mistake: "Bounding the executor is enough to protect the DB."** Tasks might open multiple connections, or other threads might also hit the DB. Coordinate datasource limits, downstream limits, transaction durations, and service quotas.

## 12. Key Takeaways and Official References

**Core rules:**

1. Below core → create worker.
2. At core, queue has space → enqueue task.
3. Queue full, below max → create new worker.
4. Queue full **and** max workers busy → apply rejection handler.
5. `AbortPolicy` lets you observe rejections via exceptions on the submission side.
6. Use `CountDownLatch` in experiments to hold workers unfinished and create verifiable saturation conditions.
7. Spring's `ThreadPoolTaskExecutor` must be configured with finite bounds; `@Async` must pass through the right proxy and the right executor.
8. After every test, release workers, shut down the pool, wait for valid tasks to complete, and verify the executed task count.

**Reference documentation:**

- [Java SE 17 – ThreadPoolExecutor](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/concurrent/ThreadPoolExecutor.html): core → queue → max → rejection mechanics and policies.
- [Java SE 17 – CountDownLatch](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/concurrent/CountDownLatch.html): synchronizing start/end milestones for stable tests.
- [Java SE 17 – ArrayBlockingQueue](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/concurrent/ArrayBlockingQueue.html): bounded queue.
- [Spring Framework 6.2 – Task Execution and Scheduling](https://docs.spring.io/spring-framework/reference/6.2/integration/scheduling.html): thread pools, queues, and rejection in Spring.
- [Spring Framework 6.2 – ThreadPoolTaskExecutor Javadoc](https://docs.spring.io/spring-framework/docs/6.2.14/javadoc-api/org/springframework/scheduling/concurrent/ThreadPoolTaskExecutor.html): configuration and monitoring APIs.
- [Spring Framework 6.2 – TaskRejectedException Javadoc](https://docs.spring.io/spring-framework/docs/6.2.14/javadoc-api/org/springframework/core/task/TaskRejectedException.html): Spring TaskExecutor exception.

**Conclusion:** to prove a pool rejects due to overload, you must create **both** conditions simultaneously: workers have reached `maxPoolSize` and the queue has no remaining space. Holding that state with latches and submitting another task clearly reveals the rejection policy and lets you design proper overload behavior for Spring applications.

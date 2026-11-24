# queueCapacity Equal to 0 and Direct Handoff in ThreadPoolTaskExecutor

In Spring Framework, **ThreadPoolTaskExecutor** is an executor backed by a thread pool to run tasks off the calling thread. When configured with **`queueCapacity = 0`**, the executor **does not create a queue capable of buffering waiting tasks**. Instead, it uses a **direct handoff** mechanism via Java's `SynchronousQueue`: a task is handed straight to a waiting worker, or the executor attempts to create another worker within `maxPoolSize`. If neither is possible, the task is **rejected** according to the rejection policy.

This is a pivotal option in the **Thread Pool** topic of **Spring Framework - concurrency**, because a small change to `queueCapacity` can completely alter task routing, how the pool scales, and overload behavior.

Key points to grasp:

- **`queueCapacity = 0` does not mean the executor cannot accept tasks.** It means there is no storage slot to *buffer* tasks in a queue.
- **Direct handoff does not mean one new thread per task.** `ThreadPoolTaskExecutor` still **reuses workers** once a worker becomes idle and ready to receive a task.
- **`corePoolSize`, `maxPoolSize`, and the rejection policy determine when worker count grows and when tasks are rejected.**
- A zero-capacity queue can surface overload early, yet leaving `maxPoolSize` too large can still spawn vast numbers of platform threads.

## 1. What Does ThreadPoolTaskExecutor Use a Queue For?

Spring's `ThreadPoolTaskExecutor` wraps a `java.util.concurrent.ThreadPoolExecutor`. A pool typically has three components:

1. **Worker threads:** threads that process one task after another.
2. **Task queue:** storage holding accepted tasks not yet picked up by a worker.
3. **Saturation/rejection policy:** decides what to do when no more work can be accepted.

Related properties:

| Property | Meaning |
| --- | --- |
| `corePoolSize` | Baseline worker threshold the pool prioritizes creating to handle tasks when needed. |
| `maxPoolSize` | Upper limit on workers the pool may create. |
| `queueCapacity` | Capacity to buffer waiting tasks; **0** selects the non-buffering queue mechanism. |
| `keepAliveSeconds` | Duration workers above core may remain idle before being reclaimed (under standard configuration). |
| `RejectedExecutionHandler` | How to handle tasks when the pool cannot accept them. |
| `threadNamePrefix` | Worker thread name prefix, aiding observation in logs/debugging. |

With `queueCapacity > 0`, Spring creates a **`LinkedBlockingQueue`** of the corresponding capacity. With `queueCapacity <= 0`, Spring creates a **`SynchronousQueue`**. In this lesson we examine the requested case: **`queueCapacity = 0`**.

Understand one point accurately: **the `maxPoolSize` limit is not the number of workers always pre-existing**. The pool may not have created the maximum number of workers yet. Expansion depends on core, queue, current worker count, and task arrival timing.

## 2. SynchronousQueue: A Queue That Stores Zero Elements

The name `SynchronousQueue` easily misleads learners into thinking it is an ordinary queue of size zero. In reality, it is a **direct exchange point** between a producer putting an item in and a consumer taking it out.

~~~text
Buffered queue (e.g., LinkedBlockingQueue)
Producer -> [ task A | task B | task C ] -> Worker
                   tasks can wait

Direct handoff (SynchronousQueue)
Producer -- task A ----------------------> Waiting Worker
              no storage slot in between
~~~

Characteristics of `SynchronousQueue`:

- **Zero internal storage capacity**; a task cannot sit in the queue waiting for a worker to appear later.
- A non-blocking `offer(task)` succeeds only when a matching receiver is already waiting to take the task.
- Its `size()` method is always **0**; that does not imply the executor has no running tasks.
- `SynchronousQueue.put(task)` itself can block waiting for a receiver, yet **do not infer that `ThreadPoolTaskExecutor.execute()` calls `put()` to block the caller until a worker is free**. Inside `ThreadPoolExecutor`, task submission uses `offer()` and then considers creating a worker or rejecting.

Thus, `queueCapacity=0` removes **task buffering capacity**, not **task processing capacity**. A worker that just finished a job can loop back to wait for the next job; at that moment a new task is handed off directly and **the existing worker is reused**.

## 3. Acceptance Algorithm: core → handoff → max → reject

The execution path of `ThreadPoolExecutor.execute(task)` can be visualized as follows (omitting internal locking details and shutdown state checks):

~~~text
                          execute(task)
                                |
               Current workers < corePoolSize?
                       /                  \
                     Yes                   No
                      |                     |
            Create new worker          Try offer(task)
            run task now               into queue
                                            |
                           +----------------+-------------+
                           |                              |
                        Success                        Failure
                           |                              |
                 Worker will run task       Workers < maxPoolSize?
                                             /                \
                                           Yes                 No
                                            |                   |
                                  Create new worker           REJECT
                                  run task now
~~~

With **`queueCapacity=0`**, the `offer()` step is a **direct handoff** attempt to a waiting worker, not writing into a buffer. If no worker can accept immediately, the pool tries **creating another worker**. Once `maxPoolSize` is reached and handoff fails, the task is rejected.

The path also depends on pool state: an already shut-down executor must not accept new tasks; after `offer()` succeeds, `ThreadPoolExecutor` also rechecks pool state to avoid retaining tasks after stopping acceptance. That is why the diagram only depicts the primary rule.

**Configuration example:** `corePoolSize=2`, `maxPoolSize=4`, `queueCapacity=0`. Suppose every task keeps its worker busy until the test explicitly releases it:

| Submission | State before submission | Outcome |
| --- | --- | --- |
| Task 1 | No workers yet | Create worker #1 (core). |
| Task 2 | 1 worker busy | Create worker #2 (core). |
| Task 3 | Both core workers busy; handoff fails | Create worker #3. |
| Task 4 | Three workers busy; handoff fails | Create worker #4. |
| Task 5 | All 4 workers busy; no buffer | **Reject** under default policy. |

If worker #2 finished its task and was **waiting for work** when Task 5 arrived, that task can be handed straight to worker #2; **creating a fifth thread is unnecessary** and rejection does not occur. The outcome always depends on **the state at submission time**.

## 4. Standalone Java 17 Example: 2–4 Worker Pool with Zero Queue

We can verify Spring's exact underlying mechanism using standard Java APIs. Because `ThreadPoolTaskExecutor` wraps `ThreadPoolExecutor`, this example reflects the core task-acceptance path when Spring selects `SynchronousQueue`.

Save as file **`DirectHandoffDemo.java`**:

~~~java
import java.util.concurrent.CountDownLatch;
import java.util.concurrent.RejectedExecutionException;
import java.util.concurrent.SynchronousQueue;
import java.util.concurrent.ThreadPoolExecutor;
import java.util.concurrent.TimeUnit;
import java.util.concurrent.atomic.AtomicInteger;

public class DirectHandoffDemo {
    public static void main(String[] args) throws InterruptedException {
        ThreadPoolExecutor pool = new ThreadPoolExecutor(
                2,
                4,
                30,
                TimeUnit.SECONDS,
                new SynchronousQueue<Runnable>(),
                new ThreadPoolExecutor.AbortPolicy()
        );

        CountDownLatch started = new CountDownLatch(4);
        CountDownLatch release = new CountDownLatch(1);
        AtomicInteger active = new AtomicInteger();

        Runnable heldTask = () -> {
            active.incrementAndGet();
            started.countDown();

            try {
                release.await();
            } catch (InterruptedException e) {
                Thread.currentThread().interrupt();
            } finally {
                active.decrementAndGet();
            }
        };

        try {
            for (int i = 0; i < 4; i++) {
                pool.execute(heldTask);
            }

            if (!started.await(5, TimeUnit.SECONDS)) {
                throw new IllegalStateException(
                        "Not enough workers started within the test timeout");
            }

            System.out.println("Running tasks: " + active.get());

            boolean rejected = false;
            try {
                pool.execute(() -> {
                    // Fifth task will not be accepted while all four are busy.
                });
            } catch (RejectedExecutionException e) {
                rejected = true;
            }

            System.out.println("Fifth task rejected: " + rejected);
            System.out.println("Waiting items in queue: "
                    + pool.getQueue().size());
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

Compile and run with **JDK 17+**:

~~~bash
javac -encoding UTF-8 DirectHandoffDemo.java
java DirectHandoffDemo
~~~

**Stdout** when workers start successfully within the test timeout:

~~~text
Running tasks: 4
Fifth task rejected: true
Waiting items in queue: 0
~~~

Point-by-point explanation:

1. **`CountDownLatch started`** forces `main` to inspect only after all four workers have actually started.
2. **`release`** keeps all four workers busy. Thus, no worker is waiting on `SynchronousQueue` to take the fifth task.
3. The pool has reached `maxPoolSize=4`, so it cannot create a fifth worker; `AbortPolicy` throws `RejectedExecutionException`.
4. **`getQueue().size() == 0`** reflects the nature of `SynchronousQueue`: zero buffered items waiting. It **does not contradict** the fact that four tasks are running.
5. `finally` always releases the latch to unblock workers and shuts down the pool. Use latches instead of `Thread.sleep()` to avoid scheduler timing dependencies.

**Scope limitation of this example:** this uses **plain Java** `java.util.concurrent.ThreadPoolExecutor` so it runs with just `javac`/`java`. In a Spring application, `ThreadPoolTaskExecutor` uses the same underlying engine while wrapping the API and exceptions in Spring classes. The next section shows the matching Spring configuration.

## 5. Configuring ThreadPoolTaskExecutor in Spring

This is a sample configuration for an application with the **Spring Context** dependency. It is **not a standalone Java program** runnable directly with `javac` without Spring on the classpath.

**`DirectHandoffConfig.java`**:

~~~java
package example.concurrency;

import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.scheduling.concurrent.ThreadPoolTaskExecutor;

@Configuration
public class DirectHandoffConfig {
    @Bean("directHandoffExecutor")
    public ThreadPoolTaskExecutor directHandoffExecutor() {
        ThreadPoolTaskExecutor executor = new ThreadPoolTaskExecutor();

        executor.setCorePoolSize(2);
        executor.setMaxPoolSize(4);
        executor.setQueueCapacity(0);
        executor.setKeepAliveSeconds(30);
        executor.setThreadNamePrefix("direct-handoff-");

        return executor;
    }
}
~~~

Once the bean initializes, this setup allows the pool to start with **up to two core workers**, scale up to **four workers**, and hold no pending tasks in a positive-capacity queue. The numbers **2, 4, 30** are for learning only; production must measure resources and pick limits intentionally.

You can verify the queue structure with the following **Spring snippet** (assuming `executor` points to the bean above):

~~~java
import java.util.concurrent.SynchronousQueue;

boolean directHandoff =
        executor.getThreadPoolExecutor().getQueue()
                instanceof SynchronousQueue;

System.out.println(directHandoff); // true
~~~

Only call `getThreadPoolExecutor()` after `ThreadPoolTaskExecutor` has been initialized. This snippet checks the configured **queue type**; it does not separately verify executed task counts or throughput.

### Why Must You Also Set maxPoolSize?

`ThreadPoolTaskExecutor` defaults to **a small core pool, a very large default queue, and a vast max pool**. If you change only `queueCapacity=0` while leaving the massive default `maxPoolSize`, the executor can create **many platform threads** during a traffic spike. Without a buffer to absorb bursts, the pool keeps spawning workers until hitting limits.

A production configuration needs a **finite `maxPoolSize`**, alongside explicit choices on:

- What maximum concurrency should be permitted?
- When full, return an error immediately or run the task on the caller?
- Should tasks be buffered in a queue, and how long may that queue grow?
- How long will a slow task hold a worker and external resources?

**Do not set `maxPoolSize` to a huge number just to "avoid rejections."** Doing so merely shifts failures to thread exhaustion, memory exhaustion, or downstream connection saturation.

## 6. Comparing queueCapacity = 0 vs. queueCapacity > 0

To see the difference, hold **`corePoolSize=2`** and **`maxPoolSize=4`**, assuming each running task is held until explicitly released:

| Submission | `queueCapacity=0` | `queueCapacity=3` |
| --- | --- | --- |
| #1–#2 | Create two core workers | Create two core workers |
| #3 | Create worker #3 | Put into queue |
| #4 | Create worker #4 | Put into queue |
| #5 | **Reject** because 4 workers are busy | Put into queue |
| #6 | — | Queue full, create worker #3 |
| #7 | — | Create worker #4 |
| #8 | — | **Reject** if workers remain busy |

This is a **simulated scenario with permanently busy tasks**, not a guaranteed execution sequence when tasks complete quickly. As workers free up or schedules interleave differently, outcomes vary.

With a buffered queue, `ThreadPoolExecutor` typically **prefers queuing once core is reached**, only expanding workers past core when the queue refuses more. With zero-capacity handoff, tasks cannot buffer, so when core workers are busy and none are waiting, the pool scales **earlier** toward max.

Therefore:

- `queueCapacity=0` tends to **scale workers early** and **reject early** when all workers are busy.
- `queueCapacity>0` can **smooth out bursts** by buffering waiting tasks, at the cost of **queue latency** and memory retention.
- A huge `queueCapacity` can leave `maxPoolSize` **virtually unused**, because tasks keep entering the queue instead of triggering non-core worker creation.
- **No single `queueCapacity` value works best for all workloads.** Base it on throughput, processing duration, SLAs, and downstream constraints.

## 7. When Are Workers Reused Even with Queue Equal to 0?

A common misconception is that "a queue with zero storage" implies "every task must spawn a new worker." With **ThreadPoolTaskExecutor**, a worker finishing a task returns to a loop to poll for the next task. When a worker is **waiting to receive** from `SynchronousQueue`, a producer can hand the new task directly to that worker.

~~~text
Task A ---> worker-1 ----> finishes A
                             |
                             +--- waits on SynchronousQueue
                                          ^
                                          |
Task B -----------------------------------+
                  direct handoff
                                          |
                                same worker-1 runs B
~~~

Hence, **`queueCapacity=0` still supports thread reuse**. This is a fundamental difference from **`SimpleAsyncTaskExecutor`**, which creates a new thread per task instead of maintaining a worker pool.

If many tasks arrive right when no worker is waiting, the pool may need to spawn additional threads (if below max) or reject. Submission timing affects acceptance, yet **there is no queue holding waiting tasks** if immediate handoff fails.

**Distinguish three concepts:**

| Concept | Meaning |
| --- | --- |
| **Direct handoff** | Stores no tasks in a queue; hands directly to a worker ready to accept immediately. |
| **Thread reuse** | A worker that ran a previous task can run the next task. |
| **Thread per task** | Each task gets a brand-new thread with no reuse. |

`ThreadPoolTaskExecutor(queueCapacity=0)` combines **direct handoff + thread reuse**; `SimpleAsyncTaskExecutor` follows a **thread-per-task** model. Never conflate the two concepts.

## 8. Overload: TaskRejectedException and Handling Policies

When the queue cannot accept a task and the pool has reached its worker limit, **rejection** occurs. `ThreadPoolExecutor` defaults to **AbortPolicy**, throwing `RejectedExecutionException`. In Spring's `ThreadPoolTaskExecutor` API, rejection errors surface as **`TaskRejectedException`** (a Spring exception for rejected task submissions).

This error happens at **task submission time**, distinct from errors thrown *inside* a worker after the task has started running.

~~~text
Caller
  |
  +-- execute(task)
         |
         +-- accepted -> worker executes -> may fail in business logic
         |
         +-- rejected -> caller receives error immediately on submit
~~~

The application must define rules for overload. Several options:

| Rejection policy | Behavior | Considerations |
| --- | --- | --- |
| **AbortPolicy** | Throws an exception when unable to accept the task | Explicit, easy to log/meter and signal overload |
| **CallerRunsPolicy** | Caller executes the task itself if the executor has not shut down | Creates indirect backpressure, yet can **block request threads** and defeat async behavior |
| **DiscardPolicy** | Drops the task per executor policy | Risk of silent work loss; usually unsuitable for critical business tasks |
| **DiscardOldestPolicy** | Attempts to evict the head of the queue and resubmit | Should not be reasoned about like a buffered queue when using `SynchronousQueue`; avoid without a verified rationale |

You can set the policy on the bean:

~~~java
import java.util.concurrent.ThreadPoolExecutor;

executor.setRejectedExecutionHandler(
        new ThreadPoolExecutor.CallerRunsPolicy());
~~~

This is an **illustrative configuration snippet**, which must be called before `initialize()`. **`CallerRunsPolicy` is not free**: if an HTTP request submits a task while the pool is full, that request thread itself may have to execute the entire task, spiking response latency and causing `@Async` not to run off-thread in that invocation. If the executor has already shut down, this policy does not guarantee task execution.

When fast failure under high load is preferred, you normally need to **acknowledge overload and reject intentionally**: catch the exception at an appropriate boundary, bound retries, and inform the caller properly. When all work must eventually run, use bounded buffers/queues, separate retries, or an external **durable queue** for durability-critical tasks; never treat `ThreadPoolTaskExecutor` as a durable queue.

## 9. Integration with @Async

In Spring, a method annotated with **`@Async`** can be routed by an interceptor to an executor. To target the zero-queue bean specifically, declare the **executor name** explicitly.

**Configuration** (requires Spring Context, and typically present in Spring Boot apps):

~~~java
package example.concurrency;

import org.springframework.context.annotation.Configuration;
import org.springframework.scheduling.annotation.EnableAsync;

@Configuration
@EnableAsync
public class AsyncSupport {
}
~~~

**Service**:

~~~java
package example.concurrency;

import java.util.concurrent.CompletableFuture;
import org.springframework.scheduling.annotation.Async;
import org.springframework.stereotype.Service;

@Service
public class BillingService {
    @Async("directHandoffExecutor")
    public CompletableFuture<Integer> computeTotal(int price, int fee) {
        int total = price + fee;
        return CompletableFuture.completedFuture(total);
    }
}
~~~

If **another bean** calls `billingService.computeTotal(100, 20)` through the Spring proxy and the task is accepted, the caller receives a future. Upon success, the future holds **120**. If the caller calls `join()` before completion, the caller still blocks.

**Distinguish failures at two points in time:**

- **At submission:** pool full, no handoff, cannot add worker → executor call may throw `TaskRejectedException` at the submit boundary; caller must handle it separately.
- **After acceptance:** logic inside `computeTotal` fails → the future completes exceptionally; caller handles it via `exceptionally`, `handle`, or `join`/`get`.

Standard `@Async` requirements still apply:

- Enable `@EnableAsync` or equivalent configuration.
- Under default proxy mode, **self-invocation** like `this.computeTotal(...)` within the same bean **bypasses the proxy**, so the annotation does not offload execution as expected.
- `@Async` does not mean **never blocks**: under `CallerRunsPolicy`, the caller may run the task; calling `join()` blocks for the result.
- Thread-bound values (MDC, SecurityContext, transaction/request attributes) are **not guaranteed to propagate across every executor automatically**. Pass business data explicitly as parameters/snapshots, or use managed propagation mechanisms when needed.

**Note:** the service example returns `CompletableFuture.completedFuture(total)` because the method itself already runs inside `@Async`. There is no need to call `supplyAsync` inside just to add another async layer.

## 10. Suitable Workloads and Choosing Bounds

`queueCapacity=0` works well when prioritizing **no in-memory backlog accumulation** and wanting crisp concurrency limits:

### CPU-Bound Tasks

Examples: compression, encryption, pure CPU computation. With a finite number of CPU cores, raising worker counts indefinitely will not increase throughput infinitely. A pool with **`maxPoolSize` aligned to usable CPU capacity** and measured queue/rejection bounds keeps load steady. Zero handoff rejects fast when full, though it may reject brief spikes that a small queue would otherwise absorb.

### I/O-Bound Tasks

Examples: downstream REST calls, DB reads, or storage operations. Workers frequently wait on I/O; useful concurrency can exceed core count, yet **DB connection pools, HTTP connection limits, and downstream rate limits** remain the hard constraints. With `maxPoolSize=100` against a 10-connection DB, adding workers does not increase DB capacity; instead it piles up tasks waiting for connections.

### Mandatory Business Work

If a task represents critical business work (transactions, guaranteed notifications, order processing), **even a RAM-backed executor queue is not durable storage**. `queueCapacity=0` has even less buffering. When you need accept/ack and guaranteed processing across restarts, use a durable job/queue mechanism with proper idempotency and retries.

### Selection Guidelines

| Priority | Direction to consider |
| --- | --- |
| Reject early when workers are busy, hold no internal backlog | `queueCapacity=0`, finite max, and explicit rejection |
| Absorb short bursts within acceptable latency bounds | Positive finite `queueCapacity`; monitor queue wait |
| Many small CPU-bound tasks | Reused worker pool sized to CPU capacity |
| Many I/O-blocking tasks | Bound by target resource capacity; consider virtual threads on supported JDKs |
| Jobs must never be lost | Durable job queue system; do not rely solely on an internal executor |

Never treat any specific configuration value as a universal default for every project; validate with representative load.

## 11. Observing and Monitoring When queueCapacity=0

Because `SynchronousQueue.size()` always returns **0**, looking only at `queueSize=0` misleads you into thinking the system is idle.

Monitor these signals together:

| Signal | Meaning |
| --- | --- |
| `getPoolSize()` | Current number of workers in the pool. |
| `getActiveCount()` | Number of workers actively executing tasks (point-in-time snapshot). |
| `getCorePoolSize()` / `getMaxPoolSize()` | Configured limits, compared against active and pool sizes. |
| Rejected task count | Overload severity and dropped submissions; requires proper instrumentation to count. |
| Task execution duration | Are workers busy on CPU or blocked on I/O? |
| Caller submit time and response latency | Is `CallerRunsPolicy` slowing down callers? |
| Downstream saturation | Are connection pools, timeouts, and dependent services hitting their limits? |

**`queueSize=0` is a structural fact, not a clean bill of health.** With direct handoff, rejection counts and active/max ratios are far more informative than queue length.

Example scenario requiring investigation: pool size reaches 4/4, active 4/4, queueSize 0, and rejections climb. This **matches saturation under direct handoff**, even though queue length never rises.

## 12. Testing Zero-Queue Behavior

A reliable test must **hold workers busy with synchronization primitives**, like `DirectHandoffDemo`, rather than firing tasks quickly and hoping the scheduler hits a race.

Test flow for a Spring bean:

1. Configure pool **core=2, max=4, queue=0** with a known rejection policy.
2. Submit four tasks blocking on a `CountDownLatch`; use another latch to verify all four have started.
3. Submit a fifth task while all four workers are guaranteed still busy.
4. With `AbortPolicy`, assert the fifth submission fails with `TaskRejectedException` at the Spring layer, or `RejectedExecutionException` when testing the Java executor directly.
5. Release the latch inside `finally`, wait for tasks to finish, and shut down the pool; never leave tests hanging.

Also verify **thread reuse** after workers complete. Do not assert a specific worker thread name or deterministic selection order; simply confirm an existing live worker can pick up the next task when ready and understand why.

To verify Spring selected the right queue type, query:

~~~java
boolean isDirect =
        executor.getThreadPoolExecutor().getQueue()
                instanceof java.util.concurrent.SynchronousQueue;
~~~

This is an **illustrative snippet in a scope with an initialized `executor` variable**. It checks actual wiring, without replacing behavioral tests.

**Never write a test asserting only `getQueueSize()==0`.** Even when the pool is saturated and rejecting every incoming task, that number stays 0 with `SynchronousQueue`.

## 13. Common Mental Traps

**"With `queueCapacity=0`, there's no queue so every task gets rejected."** False. If a worker can receive immediately or a new worker can be created below max, the task is accepted.

**"Direct handoff always spawns a new thread."** False. The worker pool reuses idle workers; it only creates a new worker when handoff fails and max is not reached.

**"Setting `maxPoolSize=4` means there are always four workers."** False. Workers are created on demand per pool policy; core/max are bounds.

**"`queueCapacity=0` is identical to `SimpleAsyncTaskExecutor`."** False. One is a thread pool with worker reuse and `SynchronousQueue`; the other follows a thread-per-task model.

**"`queueSize` equal to 0 proves there is no backlog or issue."** False. There is no internal buffer, yet all four workers may be stalled and callers may be getting rejected.

**"Setting `queueCapacity=0` automatically turns on backpressure by blocking callers."** False. Under default `AbortPolicy`, the pool rejects when full; only specific policies like `CallerRunsPolicy` make the caller execute the task directly.

**"Just raise `maxPoolSize` to eliminate rejections."** Risky. Unbounded platform thread growth shifts failures to the OS or downstream services; size bounds to system capacity.

**"`ThreadPoolTaskExecutor` with `queueCapacity=0` cannot handle bursts."** Not entirely. The pool can scale rapidly from core to max and reuse idle workers. Once all max workers are busy, however, there is no buffer for extra tasks.

**"`@Async` means the caller always returns instantaneously."** Not unconditionally: the caller can still pay submission cost, rejection errors, `CallerRunsPolicy`, or future waits.

**"No queue means no shutdown needed."** False. The pool still owns worker threads and requires proper lifecycle management, task duration bounds, and acceptance shutdown.

## 14. Reasoning Exercises

**Exercise 1.** With `corePoolSize=2`, `maxPoolSize=4`, `queueCapacity=0`, all four tasks are running and no worker is idle. A fifth task is submitted using the default `AbortPolicy`. What happens?

**Answer:** Handoff fails and a fifth worker cannot be created, so it is **rejected**.

**Exercise 2.** Under the same configuration, worker #3 just finished and is waiting for work. A caller submits a task. Must a new worker be created?

**Answer:** No. Direct handoff can deliver the task to worker #3; that worker is reused.

**Exercise 3.** `getQueueSize()` stays at 0 continuously, yet rejections are rising. Is there a contradiction?

**Answer:** No. `SynchronousQueue` stores zero items while all pool workers can still be busy.

**Exercise 4.** Change `queueCapacity` from 0 to 50 while keeping core=2 and max=4. Will the pool still always scale to 4 workers as soon as the third task arrives?

**Answer:** No. Once the two core workers are busy, the pool prioritizes putting tasks into the 50-slot queue; only when the queue stops accepting will it consider scaling past core.

**Exercise 5.** Why is `queueCapacity=0` not equivalent to `SimpleAsyncTaskExecutor`?

**Answer:** `ThreadPoolTaskExecutor` still maintains a pool where workers can be reused. `SimpleAsyncTaskExecutor` creates a separate thread for each task.

**Exercise 6.** If **CallerRunsPolicy** is configured and the pool is full, is an `@Async` method guaranteed to run off the request thread?

**Answer:** No. The request thread itself may execute the task upon pool rejection, directly impacting response latency.

**Exercise 7.** Should you set a massive `maxPoolSize` to avoid rejections when a database has only 10 connections?

**Answer:** You should not make that choice. Determine allowable database concurrency, timeouts, and waiting/rejection behavior at the appropriate boundary instead.

## 15. Practical Implementation Checklist

- [ ] Verify the Spring bean actually has `queueCapacity=0` and uses `SynchronousQueue`.
- [ ] Configure `corePoolSize` and a **finite `maxPoolSize`** suited to the workload.
- [ ] Define the **rejection policy** and caller behavior when the pool is full.
- [ ] Clearly distinguish **having no buffer** from **having no capacity to accept tasks**.
- [ ] Bound downstream resources: DB/HTTP connections, timeouts, rate limits.
- [ ] Monitor `activeCount`, `poolSize`, rejections, and task duration; do not rely solely on queue size.
- [ ] Test pool saturation using latches and clean up/shut down the executor properly.
- [ ] With `@Async`, invoke through the Spring proxy and handle submission errors separately from future errors.
- [ ] Review shutdown behavior, long-running tasks, and application lifecycle.
- [ ] Evaluate a **finite positive queue** if the workload has bursts that need brief buffering.

## Summary

**`queueCapacity=0` in `ThreadPoolTaskExecutor` selects `SynchronousQueue`: tasks are handed off directly to a waiting worker, otherwise the pool grows workers up to `maxPoolSize`, and finally rejects according to the configured policy.** There is no buffer for waiting tasks, yet **thread reuse** remains active in the pool. The effectiveness of this configuration lies in deliberately controlling concurrency, latency, and overload—not in the fact that the queue length reads zero.

**Reference documentation:** Spring Framework Javadoc for `ThreadPoolTaskExecutor` (`setQueueCapacity`, `createQueue`); Java SE Javadoc for `ThreadPoolExecutor`, `SynchronousQueue`, `RejectedExecutionHandler`; Spring documentation on Task Execution and `@Async`.

# Why an Unbounded Queue Prevents maxPoolSize from Taking Effect

> **Module:** Spring Framework – concurrency · **Parent Topic:** Thread Pool  
> **Core Question:** Why does a `ThreadPoolTaskExecutor` configured with `corePoolSize = 2`, `maxPoolSize = 16`, and a very large queue typically run only about two workers while thousands of tasks wait in the queue?

## 1. Core Answer

For Spring's standard `ThreadPoolTaskExecutor`, the underlying scheduling engine is `java.util.concurrent.ThreadPoolExecutor`. Once worker count reaches `corePoolSize`, the executor **prioritizes inserting new tasks into the queue before creating workers beyond core**. Only when queue insertion **fails** and total workers have not reached `maximumPoolSize` does it attempt to create an additional worker.

Consequently, with a **practically unbounded** queue, adding a task to the queue almost always succeeds. The condition that triggers scaling from `corePoolSize` to `maxPoolSize` virtually never occurs. The typical outcome is few active workers, many queued tasks, high latency, and growing memory usage. Setting a very large `maxPoolSize` **does not automatically make the pool grow to that size**.

This rule belongs to **`ThreadPoolExecutor` and adapters built on it**, not every `TaskExecutor` implementation. For example, `SimpleAsyncTaskExecutor` does not operate with the same thread-pool/queue mechanism.

## 2. The Three Parameters That Govern Behavior

| Parameter | Role | What it does not mean |
| --- | --- | --- |
| `corePoolSize` | Baseline worker count the executor prioritizes creating when accepting work; core workers are normally retained even when idle | Not an absolute cap on total workers |
| `maxPoolSize` | Ceiling on workers the executor may create when needed | Not a target worker count the executor tries to reach on its own |
| `queueCapacity` | Tasks that can wait in the queue, determining when `offer` fails and the executor tries expanding workers | Not concurrent running tasks; running tasks are generally not in the queue |

`poolSize` is the current number of existing workers, `activeCount` is the instantaneous estimate of workers executing tasks, and `queueSize` is the number of waiting tasks. Reading `poolSize` without looking at `queueSize` easily leads to wrong conclusions about load.

A queue capacity of 100 does not mean the system runs 100 tasks in parallel: if core is 2 and the queue is not full, typically only 2 tasks execute while the rest wait.

## 3. Why Is the Expansion Branch Rarely Triggered?

`ThreadPoolExecutor.execute` prioritizes creating workers up to `corePoolSize`; next it tries `workQueue.offer(task)`; only if `offer` fails does it try creating workers up to `maxPoolSize`, and finally rejects when no more can be accepted. The actual implementation also includes shutdown checks and concurrency race handling.

**The bottleneck in this lesson is the condition under which `offer` fails.** With `LinkedBlockingQueue(Integer.MAX_VALUE)`, `offer` can succeed an enormous number of times, so the worker-expansion branch is practically never entered. The lesson "Task Acceptance Order: Core Thread Creation, Queuing, Expansion, Then Rejection" presents the detailed algorithm; here we evaluate the consequences of a **near-unbounded queue** across backlog, latency, and scaling to max.

## 4. Why Does a Very Large Queue Keep the Pool Near corePoolSize?

Suppose:

- `corePoolSize = 2`;
- `maxPoolSize = 16`;
- a `LinkedBlockingQueue` with huge capacity;
- tasks are slow, so both initial workers remain busy.

When the third task arrives, the pool already has 2 workers and tries putting it in the queue. That operation succeeds. The fourth, fifth, and hundreds of subsequent tasks are likewise enqueued because space remains. The pool has no reason to take the branch that creates worker #3, #4... #16.

~~~text
core = 2, max = 16, practically unbounded queue

Worker #1: [TASK A running]
Worker #2: [TASK B running]
Queue:     [C][D][E][F][G][H][... many more tasks ...]
Workers #3 ... #16: not yet created

new task -> queue.offer(...) succeeds -> still only two workers
~~~

If tasks arrive faster on average than two workers complete them, queued items pile up. Increasing `maxPoolSize` from 16 to 64 **does not directly alter the decision branch**: as long as `offer` succeeds, the pool keeps preferring the queue.

For a **truly unbounded queue** in the JDK model, the Javadoc explicitly notes that workers normally never exceed `corePoolSize`; `maximumPoolSize` therefore has no effect. With Spring's default queue having a technical limit of `Integer.MAX_VALUE`, it is theoretically fillable; in practice, out-of-memory risk and severe latency arrive long before hitting that integer bound. That is why documentation and operators commonly call it an "unbounded queue."

## 5. Default Configuration of ThreadPoolTaskExecutor in Spring

For the `org.springframework.scheduling.concurrent.ThreadPoolTaskExecutor` class itself, the typical default values are:

| Property | Class default value | Impact |
| --- | --- | --- |
| `corePoolSize` | `1` | One baseline worker |
| `maxPoolSize` | `Integer.MAX_VALUE` | Very high theoretical ceiling |
| `queueCapacity` | `Integer.MAX_VALUE` | Positive queue capable of holding vast numbers of tasks |
| `keepAliveSeconds` | `60` | Idle retention time for workers above core (if any) |
| `allowCoreThreadTimeOut` | `false` | Core workers normally do not time out |

`ThreadPoolTaskExecutor` creates a `LinkedBlockingQueue` when `queueCapacity > 0`, while `queueCapacity <= 0` uses `SynchronousQueue` (direct handoff, no backlog storage). These are defaults and queue-creation branches of the **Spring class**, not a claim that every **Spring Boot** application always uses these exact numbers: Boot auto-configuration, versions, properties, and custom executor beans can change them.

A surprising consequence: despite the huge default `maxPoolSize`, a `ThreadPoolTaskExecutor` instance using all defaults generally behaves close to a single worker processing tasks one by one with a very long queue.

## 6. Comparing the Same Load Across Three Queue Types

Suppose `core = 2`, `max = 6`, and **six tasks** are submitted consecutively; all block on a latch so none complete at measurement time.

| Queue | First two tasks | Tasks 3 and 4 | Tasks 5 and 6 | Measured result |
| --- | --- | --- | --- | --- |
| `LinkedBlockingQueue(Integer.MAX_VALUE)` | Create 2 workers | Wait in queue | Continue waiting | 2 workers; 4 queued |
| `LinkedBlockingQueue(2)` | Create 2 workers | Fill 2 queue slots | Queue full → create 2 more workers | 4 workers; 2 queued |
| `SynchronousQueue` | Create 2 workers | Cannot buffer in queue → create 2 more workers | Create 2 more workers | 6 workers; 0 queued |

Key observation: configuring a **bounded queue** gives `maxPoolSize` a chance to take effect, though it can also lead to rejections once both queue and pool are full. **Queue 0** makes the executor scale earlier, while also hitting the worker cap sooner. No single configuration automatically fits all workloads.

A less-noticed side effect: with a finite queue, a task arriving after the queue is full can be handed straight to a newly created worker while older tasks stay waiting in the queue. **Never assume submission order equals start or completion order**, unless a separate ordering mechanism exists.

## 7. Standalone Java 17+ Example: Proof by Measurement

The following example uses JDK's `ThreadPoolExecutor` directly, the foundation of the mechanism explained here. It **requires no Spring dependency**, so it runs standalone to verify the exact worker–queue policy before placing it in a Spring app.

Save to file **QueueGrowthDemo.java**:

~~~java
import java.util.concurrent.BlockingQueue;
import java.util.concurrent.CountDownLatch;
import java.util.concurrent.LinkedBlockingQueue;
import java.util.concurrent.SynchronousQueue;
import java.util.concurrent.ThreadPoolExecutor;
import java.util.concurrent.TimeUnit;

public class QueueGrowthDemo {
    static void demonstrate(String label, BlockingQueue<Runnable> queue,
                            int expectedRunning) throws InterruptedException {
        ThreadPoolExecutor pool = new ThreadPoolExecutor(
            2, 6, 30, TimeUnit.SECONDS, queue);
        CountDownLatch started = new CountDownLatch(expectedRunning);
        CountDownLatch release = new CountDownLatch(1);

        try {
            for (int i = 0; i < 6; i++) {
                pool.execute(() -> {
                    started.countDown();
                    try {
                        release.await();
                    } catch (InterruptedException ex) {
                        Thread.currentThread().interrupt();
                    }
                });
            }

            if (!started.await(10, TimeUnit.SECONDS)) {
                throw new IllegalStateException("Workers did not start");
            }

            System.out.printf("%s: pool=%d, queue=%d%n",
                label, pool.getPoolSize(), pool.getQueue().size());
        } finally {
            release.countDown();
            pool.shutdown();
            if (!pool.awaitTermination(10, TimeUnit.SECONDS)) {
                pool.shutdownNow();
            }
        }
    }

    public static void main(String[] args) throws InterruptedException {
        demonstrate("Almost unbounded",
            new LinkedBlockingQueue<>(Integer.MAX_VALUE), 2);
        demonstrate("Bounded 2",
            new LinkedBlockingQueue<>(2), 4);
        demonstrate("Direct handoff",
            new SynchronousQueue<>(), 6);
    }
}
~~~

Run with JDK 17 or newer:

~~~bash
javac QueueGrowthDemo.java
java QueueGrowthDemo
~~~

**Stdout when workers start within the 10-second timeout**:

~~~text
Almost unbounded: pool=2, queue=4
Bounded 2: pool=4, queue=2
Direct handoff: pool=6, queue=0
~~~

Explanation:

- All three runs use `core=2`, `max=6`, six tasks, and identical task logic.
- `CountDownLatch release` prevents running tasks from finishing prematurely, avoiding noisy results from fast workers.
- `started` confirms the expected number of workers have started before measuring. Because no task passes `release.await()`, worker and queued counts at print time are deterministic per configuration.
- On completion, `release.countDown()` unblocks tasks, and `shutdown()` plus `awaitTermination()` clean up resources; only if workers fail to exit within the timeout is `shutdownNow()` called.
- This example simulates **acceptance and queuing mechanics**, not throughput of a system with DB, network, or downstream limits. Never infer that "more workers" is always better.

## 8. Corresponding Configuration in Spring Framework

Below is a **Spring integration snippet**, which must be placed in a project with `spring-context` and loaded by an `ApplicationContext`; it is not a standalone Java file compiled with plain `javac`.

~~~java
import java.util.concurrent.ThreadPoolExecutor;

import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.scheduling.concurrent.ThreadPoolTaskExecutor;

@Configuration(proxyBeanMethods = false)
public class PoolConfiguration {
    @Bean("reportExecutor")
    public ThreadPoolTaskExecutor reportExecutor() {
        ThreadPoolTaskExecutor executor = new ThreadPoolTaskExecutor();
        executor.setCorePoolSize(2);
        executor.setMaxPoolSize(6);
        executor.setQueueCapacity(2);
        executor.setKeepAliveSeconds(30);
        executor.setThreadNamePrefix("report-");
        executor.setRejectedExecutionHandler(
            new ThreadPoolExecutor.AbortPolicy());
        return executor;
    }
}
~~~

With `queueCapacity=2`, once two core workers are busy and two other tasks occupy the queue, subsequent tasks can grow the pool to three, four... up to six workers. When both the queue and all six workers are full, `AbortPolicy` rejects the task.

If you change only `setQueueCapacity(Integer.MAX_VALUE)`, tasks normally keep entering the queue; growing from two to six workers rarely occurs. If you set `setQueueCapacity(0)`, Spring uses `SynchronousQueue`: there is no internal waiting queue, new workers can spawn earlier up to max, and tasks are rejected once capacity is exhausted.

**Note:** verify the executor **actually** selected by `@Async` or your service. If multiple `TaskExecutor` beans exist, specify the right qualifier/executor name. Also, under standard proxy mode, calling `this.methodAnnotatedAsync()` within the same bean bypasses the `@Async` interceptor. Queue sizing only matters when calls are genuinely submitted to the pool under inspection.

### Do Not Change Only maxPoolSize

This configuration is insufficient to expect pool expansion:

~~~java
executor.setCorePoolSize(2);
executor.setMaxPoolSize(64);
executor.setQueueCapacity(Integer.MAX_VALUE);
~~~

Changing `maxPoolSize` from 6 to 64 solves no bottleneck if the queue still accepts every task. You must tune the **relationship** among core, max, and queue against latency targets, real capacity, and downstream capabilities.

## 9. Do Not Conclude Smaller Queues Are Always Better

Three common strategies carry different trade-offs:

| Strategy | Pros | Risks |
| --- | --- | --- |
| Very long queue | Absorbs short bursts with fewer extra workers; reduces thread-creation churn | Higher wait latency, retains references/tasks in RAM, masks overload, max goes unused |
| Finite queue | Caps backlog; pool can expand when queue fills; overload is visible | Must pick rejection/backpressure; high worker counts can exhaust connection pools and raise contention |
| `queueCapacity = 0` | Direct handoff; pool adds workers quickly when existing workers are busy | Thread count can spike, hit max, and reject early; no burst buffer |

Raising `corePoolSize` appropriately can make workers available earlier even with a long queue. Yet you must also factor in **CPU**, memory, blocking I/O, DB connection counts, external API limits, timeouts, and contention. A pool with 64 workers backed by a 10-connection DB pool may just create dozens of workers waiting on connections instead of running faster.

`allowCoreThreadTimeOut(true)` lets core workers expire when idle; `keepAliveSeconds` governs extra worker lifetimes. Neither changes the **queue-before-expansion-beyond-core priority**, so neither directly fixes an unused max limit. `prestartAllCoreThreads` only pre-creates core workers, without scaling to max.

## 10. When the Queue Fills: Rejection Is Part of the Design

Any bounded pool eventually reaches maximum capacity. When every worker is busy and the queue is full, new submissions go to `RejectedExecutionHandler`. With `ThreadPoolTaskExecutor`, calls through Spring surface rejections as `TaskRejectedException` (a subtype of `RejectedExecutionException`).

Decide at the caller layer:

- **Explicit abort/reject:** return an overload notice or appropriate error; never silently pretend the task was accepted.
- **CallerRunsPolicy:** while the executor is running, the task can execute directly on the caller thread, slowing the caller down and creating backpressure; you must accept the impact on request latency. During shutdown, this policy has specific semantics and does not guarantee acceptance.
- **Bounded retries:** only for idempotent tasks with backoff/jitter; hammering a full pool with immediate retries worsens saturation.
- **Durable queue/job store:** if losing tasks on JVM crash is unacceptable, store work outside memory and handle recovery. An executor queue is not a durable store.

Do not use `DiscardPolicy` or silent-drop variants for work requiring completion confirmation unless drop semantics are explicitly defined.

## 11. How to Diagnose in a Live Application

Measure the following metrics together, ideally under ramping load:

1. **Pool:** `corePoolSize`, `maxPoolSize`, `poolSize`, `activeCount`, and peak pool size.
2. **Queue:** capacity, queued item count, wait time from `submit/execute` to task start; with a near-unbounded queue, pending counts can climb for a long time.
3. **Errors/overload:** rejected count, timeouts, retries, cancellations, and tasks interrupted/unfinished at shutdown.
4. **Task duration:** total runtime, I/O wait ratio, transaction duration, and connection pool utilization.
5. **Resource pressure:** heap, thread count, CPU, GC, downstream rate limits, and dependent service latency.

Typical signature of the problem in question:

~~~text
corePoolSize = 2
maxPoolSize = 32
poolSize = 2
activeCount ≈ 2
queueSize steadily increasing
rejectedCount ≈ 0
p95/p99 completion time rising
~~~

When observing this pattern, inspect `queueCapacity` and queue policy **before simply raising `maxPoolSize` further**. If tasks have long wait times, check downstream too; adding workers may just increase connection wait queues.

A sound load test should cover ramp-up, steady state, brief bursts, sustained saturation, and recovery. Pick settings based on SLOs (latency/throughput), memory, connection counts, and acceptable rejection rates.

## 12. Common Misconceptions

| Wrong statement | Accurate understanding |
| --- | --- |
| "`maxPoolSize=32` means the pool will have 32 workers as load rises." | The pool grows past core only when the queue stops accepting and workers are below max. |
| "No rejections means the system is very healthy." | A large queue can keep accepting work while wait times grow uncontrollably. |
| "A larger queue runs more tasks in parallel." | The queue holds **waiting** tasks; workers are what execute in parallel. |
| "Just raise maxPoolSize to fix slowness." | If the queue is not full, changing max rarely reaches the worker-expansion branch. |
| "Setting queue=0 is always faster and safer." | Easily expands to max, creates contention and rejections; requires knowing real load. |
| "Setting core=max means there is no queue." | A fixed-size pool still has a queue if configured with one. |
| "The default queue capacity is mathematically infinite." | In `ThreadPoolTaskExecutor` the default is `Integer.MAX_VALUE`—enormous, yet finite. |
| "The executor guarantees FIFO completion." | The queue can be FIFO for waiting tasks, but multiple workers and expansion paths do not guarantee overall completion order. |
| "Enqueued work survives restarts." | An in-memory executor queue is not durable across process crashes. |

## 13. Controlled Configuration Tuning Process

1. **Confirm the right executor:** bean type, `@Async` qualifier, actual implementation, applied properties, and bean lifecycle.
2. **Measure the bottleneck:** busy workers, queue wait, execution duration, CPU, DB connections, remote latency; determine whether workers are scarce or the backend is saturated.
3. **Set targets:** maximum allowed parallelism, desired queue wait budget, max in-memory jobs, and policy when capacity is full.
4. **Pick the trio:** core for normal load, max matching resources, finite queue to absorb allowed bursts. Use queue=0 when direct handoff is needed and overload handling is designed.
5. **Define rejection and recovery policies:** confirm acceptance, return errors, retry/backoff, idempotency, and durable jobs for critical work.
6. **Test ramp-up and failures:** use latches in unit tests to control saturation; run integration tests against real DB/APIs to surface contention, timeouts, deadlocks, and bottlenecks.
7. **Monitor after changes:** evaluate throughput, queue wait, p95/p99, rejections, memory, and downstream health before declaring victory.

## 14. Self-Check Questions

**Question 1.** With `core=2`, `max=20`, and plenty of queue space left, 100 long tasks are submitted consecutively. Why may the pool remain around two workers?

Because once core is reached, new tasks are successfully enqueued. The executor does not yet need to run the branch that creates extra workers up to max. Remaining tasks wait in the queue.

**Question 2.** With `core=2`, `max=6`, `queueCapacity=2`, and six tasks blocking concurrently, what is the expected state?

Two tasks run on core workers, two sit in the queue, and the last two trigger worker expansion. When held on a latch, four workers are active and two tasks wait in the queue, as shown in the Java example.

**Question 3.** Why can't you simply set queue=0 and consider the problem solved?

Because that shifts pressure from the queue to workers and rejections, while still remaining bounded by CPU, connection counts, downstream limits, errors, and latency. Whether it is right must be verified against real load and SLOs.

**Conclusion:** For `ThreadPoolExecutor`, the **queue-after-core priority** branch directly explains why a near-unbounded queue keeps `maxPoolSize` from taking effect. To give the pool a chance to scale past core, you need a queue policy with a saturation point; to keep the system healthy, you must also design load bounds, latency targets, rejections, and downstream resources.

## Official References

- [Java SE 17: ThreadPoolExecutor](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/concurrent/ThreadPoolExecutor.html) — *Core and maximum pool sizes* and *Queuing* sections.
- [Spring Framework: ThreadPoolTaskExecutor Javadoc](https://docs.spring.io/spring-framework/docs/current/javadoc-api/org/springframework/scheduling/concurrent/ThreadPoolTaskExecutor.html) — core/max/queue defaults, `LinkedBlockingQueue` and `SynchronousQueue` creation details.
- [Spring Framework Reference: Task Execution and Scheduling](https://docs.spring.io/spring-framework/reference/integration/scheduling.html) — executor/scheduler configuration and `@Async` integration.
- [Java SE 17: LinkedBlockingQueue](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/concurrent/LinkedBlockingQueue.html) and [SynchronousQueue](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/concurrent/SynchronousQueue.html) — nature of both queue types.

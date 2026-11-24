# Task Submission Time Differs from Execution Start Time

In a Spring Framework application, when a controller calls an `@Async` method or a service submits a `Runnable` via `TaskExecutor.execute(...)`, the submission call can complete **before the task starts executing**. This happens when the executor accepts the task into a queue while no worker is free. Conversely, an idle worker may start running even before the submission method finishes returning; a synchronous executor can even run the entire task on the calling thread.

Therefore, we must distinguish **submission (submit)**, **acceptance (accept)**, **execution start (start)**, **completion (finish)**, and **when the caller regains control (return)**. This lesson explains the mechanism, implications for `Future` and `@Async`, how to measure queue wait latency in Spring, and a standalone Java 17 example.

## 1. The Milestones Are Not Synonymous

~~~text
Caller                         Executor / queue                     Worker
  |                                   |                               |
  |---- execute(task) --------------->|                               |
  |       t_submit                    |                               |
  |                                   |-- accept / enqueue ---------->|
  |                                   |      t_accept                 |
  |<--- execute returns --------------|                               |
  |       t_return                    |                               |
  |                                   |  waiting for free worker      |
  |                                   |---- dispatch task ----------->|
  |                                   |                          t_start
  |                                   |                        runs task
  |                                   |                          t_finish
~~~

The milestones have distinct meanings:

1. **`t_submit`**: the caller begins requesting the executor to execute the task (calling `execute`/`submit` or entering an `@Async` proxy).
2. **`t_accept`**: the executor accepts the task, either scheduling it immediately or placing it into a queue. Not every executor exposes this timestamp via an API.
3. **`t_return`**: the submission method returns control to the caller. `execute(Runnable)` returns `void`, while `ExecutorService.submit(...)` returns a `Future` once accepted.
4. **`t_start`**: the worker starts running the executor-managed body, such as the `Runnable.run()` callback.
5. **`t_finish`**: the callback finishes, normally or via an exception; a `Future` may also complete via cancellation.

Intervals that should be measured separately:

| Interval | Approximate measurement | Question answered |
| --- | --- | --- |
| Submission duration | `t_return − t_submit` | How long did the caller spend submitting the request? |
| Wait/queue latency before start | `t_start − t_submit` | How long after submission did a worker start running the task? |
| Execution duration | `t_finish − t_start` | How long did the worker take to execute the callback? |
| Task end-to-end | `t_finish − t_submit` | How long from the submission request until the task actually finished? |

In a pool with a queue and busy workers, the typical order is `t_submit < t_return < t_start < t_finish`. However, **there is no general guarantee that `t_return` always precedes `t_start`**: a very short task can be started by a worker while the caller is still inside `execute`. With `SyncTaskExecutor` or `CallerRunsPolicy`, the callback can even execute **directly on the caller before `execute` returns**.

**The distinction between submit and start is conceptual, not a promise that every task must wait in a queue.**

## 2. Why Does a Task Succeed at Submission Yet Not Run Immediately?

### 2.1. Worker Is Busy, Task Waits in Queue

Suppose an executor has one worker. Task A holds the worker for 5 seconds; task B is submitted after A has already started:

~~~text
Time           0s          1s                  5s         5.1s
               |-----------|-------------------|-----------|
Worker:        [================ Task A =======][ Task B ]
Caller:        submit A    submit B -> returns
Queue:                     [ B waiting .........]
                           ^                   ^
                           submitted           B finally starts
~~~

From the caller's perspective, `submit(B)` can return very quickly. From B's perspective, it had to wait several seconds before running. If you only log execution duration *inside* method B, the system might report "B ran in 100 ms", even though the user experienced over 4 seconds of latency.

### 2.2. Admission Order in ThreadPoolExecutor

Spring's `ThreadPoolTaskExecutor` typically wraps Java's `ThreadPoolExecutor`, with this basic sequence:

1. If the current worker count is less than `corePoolSize`, try creating a new worker for the task.
2. Once core is reached, try placing the task into the queue.
3. If the queue cannot accept it, try spawning a new worker up to `maxPoolSize`.
4. If it still cannot be accepted, or the executor is shut down, the task is rejected according to policy.

Because **the queue is preferred after core**, setting `maxPoolSize=16` does not mean the third task will immediately run on worker #3 when `corePoolSize=2` and the queue still has space. With a very large queue, the pool may stay near core workers even as queued tasks pile up. A practically unbounded queue can also accumulate work to the point of severe wait times and memory consumption.

Conversely, with `queueCapacity=0` on `ThreadPoolTaskExecutor`, Spring uses a `SynchronousQueue` for direct handoff; when no worker takes the task and the pool is below max, it can spawn a new worker. Therefore, **start latency depends on queue, core, max, completion rate, and actual load together**, not a single parameter.

### 2.3. A Blocked Worker Does Not Mean CPU Is Busy

A worker still occupies a pool slot while waiting on a JDBC connection, HTTP response, lock, or `Future.get()`. If many workers block on I/O, queue wait can spike even when CPU usage is low. Diagnosing properly requires distinguishing CPU saturation, worker exhaustion due to blocking, and downstream resource depletion.

## 3. Java 17: Program Confirming B Is Submitted Before B Starts

Create **`SubmissionVsStartDemo.java`**. The program uses a single worker and `CountDownLatch` instances to enforce deterministic ordering without guessing delays via `Thread.sleep(...)`:

~~~java
import java.util.concurrent.CountDownLatch;
import java.util.concurrent.ExecutorService;
import java.util.concurrent.Executors;
import java.util.concurrent.Future;
import java.util.concurrent.TimeUnit;

public class SubmissionVsStartDemo {
    public static void main(String[] args) throws Exception {
        ExecutorService pool = Executors.newSingleThreadExecutor();
        CountDownLatch firstStarted = new CountDownLatch(1);
        CountDownLatch releaseFirst = new CountDownLatch(1);
        CountDownLatch secondStarted = new CountDownLatch(1);
        try {
            Future<?> first = pool.submit(() -> {
                firstStarted.countDown();
                try {
                    releaseFirst.await();
                } catch (InterruptedException ex) {
                    Thread.currentThread().interrupt();
                }
            });
            if (!firstStarted.await(5, TimeUnit.SECONDS)) {
                throw new IllegalStateException("First task did not start");
            }
            System.out.println("1. Task A started");
            Future<?> second = pool.submit(() -> {
                secondStarted.countDown();
                System.out.println("4. Task B started");
            });
            System.out.println("2. Task B submitted");
            System.out.println("3. Task B started yet? "
                    + (secondStarted.getCount() == 0));
            releaseFirst.countDown();
            first.get(5, TimeUnit.SECONDS);
            second.get(5, TimeUnit.SECONDS);
            System.out.println("5. Task B completed");
        } finally {
            releaseFirst.countDown();
            pool.shutdownNow();
        }
    }
}
~~~

Run with JDK 17 or later:

~~~bash
javac --release 17 SubmissionVsStartDemo.java
java SubmissionVsStartDemo
~~~

Stdout verified by compiling with `--release 17` and running the program:

~~~text
1. Task A started
2. Task B submitted
3. Task B started yet? false
4. Task B started
5. Task B completed
~~~

Step-by-step explanation:

- `firstStarted.await(...)` confirms task A has started on the sole worker.
- A waits on `releaseFirst`, so the worker cannot move on to B yet.
- `submit(B)` returns a `Future<?>` once B is accepted. Even so, B is **sitting in the queue**.
- When checking `secondStarted.getCount()`, main has not released A yet so B is guaranteed not to have started; the third line prints `false`.
- After `releaseFirst.countDown()`, A can exit; the worker runs B and prints the fourth line.
- `second.get(...)` waits for B to complete before main prints the fifth line.

`CountDownLatch` makes the observation deterministic. Do not infer submit/start relationships by just adding `Thread.sleep(10)` in tests: CPU load variations and OS scheduling easily make such tests flaky.

### 3.1. Future Is Not a Start Timestamp

| Future state | What can be concluded | What cannot be concluded |
| --- | --- | --- |
| `isDone() == false` | Task has not reached a completed state | Whether task is queued or running |
| `isDone() == true` | Task completed per the Future contract (may be success, error, or cancel) | When the task started, or how long it waited |
| `isCancelled() == true` | Future was cancelled | Whether prior side effects were rolled back |
| `get()` returns a value | Task completed successfully with that value | Queue wait duration |
| `get(timeout)` throws `TimeoutException` | Caller waited past the allowed timeout | That the task automatically stopped |

When `t_start` is needed, measure at the start of the callback or use executor instrumentation. `Future.get(timeout)` only bounds **the caller's wait**, without setting a deadline on queued or running work.

## 4. In Spring, @Async Is Also Just a Request to Hand Off Work to an Executor

Example **Spring Framework 6.x, Java 17+ integration snippet** (requires Spring dependencies, component scanning, and `@EnableAsync`):

~~~java
package example.concurrency;

import java.util.concurrent.CompletableFuture;
import org.springframework.scheduling.annotation.Async;
import org.springframework.stereotype.Service;

@Service
public class ReportWorker {
    @Async("reportExecutor")
    public CompletableFuture<String> generate(String reportId) {
        // Actual logic starts when an executor worker executes this invocation.
        return CompletableFuture.completedFuture("ready:" + reportId);
    }
}
~~~

Caller in another bean:

~~~java
CompletableFuture<String> result = reportWorker.generate("R-101");
// At this point the task may be queued, running, or already completed.
~~~

The caller snippet assumes `reportWorker` was injected from the Spring context and the call goes through the proxy. At the moment `result` is received, **there is no proof that the method body has started**. If the caller immediately calls `result.join()` or `get()`, the caller will block waiting for the result, losing the ability to perform other work in the meantime.

Conditions for `@Async` to work properly:

- `@EnableAsync` or an equivalent activation mechanism is present.
- The executor bean specified in `@Async("reportExecutor")` exists and is managed by Spring.
- The call goes **through the Spring proxy**. In default proxy mode, calling `this.generate(...)` from the same bean bypasses the async interceptor and may run synchronously.
- The caller tracks both **submission-time failures** (such as pool rejection) and **runtime failures after the task starts**. A Future can represent execution failures; exceptions from `@Async void` methods require separate handling.

One more point: an idle worker may start executing before the proxy call returns, especially for short tasks. Therefore, do not assume "the method body cannot start before the caller receives the Future".

## 5. Configuring a Spring Pool with a Queue to Observe Wait Time

Example of an explicit bean configuration:

~~~java
package example.concurrency;

import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.scheduling.annotation.EnableAsync;
import org.springframework.scheduling.concurrent.ThreadPoolTaskExecutor;

@Configuration
@EnableAsync
public class AsyncExecutorConfiguration {
    @Bean("reportExecutor")
    public ThreadPoolTaskExecutor reportExecutor() {
        ThreadPoolTaskExecutor executor = new ThreadPoolTaskExecutor();
        executor.setCorePoolSize(2);
        executor.setMaxPoolSize(4);
        executor.setQueueCapacity(10);
        executor.setThreadNamePrefix("report-");
        return executor;
    }
}
~~~

This is a **Spring integration file**, not compilable standalone with a `javac` command lacking the Spring classpath. Spring manages the lifecycle and initializes the executor bean when registered normally in the ApplicationContext.

Suppose both core workers are busy with long tasks and the queue has space. A newly submitted task can be **enqueued** and the caller regains control while the task waits for a worker. Once the queue is full, the pool can scale up to max=4; when both workers and queue are full, it can reject.

The numbers 2/4/10 are purely illustrative. Real pools must be sized for CPU, I/O duration, connection pools, throughput, p95/p99, and peak load. An overly large queue can turn explicit errors into prolonged wait times.

### 5.1. Accepted, Rejected, or Executed on the Caller?

Three outcomes to distinguish:

1. **Accepted, runs asynchronously:** the task may run immediately or wait in the queue.
2. **Rejected:** with the default policy based on `AbortPolicy`, Spring may throw `TaskRejectedException` when the executor is saturated or shut down. There is no `t_start` for an unaccepted task.
3. **Caller executes instead of a worker:** if `CallerRunsPolicy` is configured and the pool is not shut down, an overflow task can run directly on the submitting thread. Then `execute(...)` blocks until execution finishes.

Hence, "submit is always non-blocking" cannot be stated universally across all `TaskExecutor` implementations and policies. `SyncTaskExecutor` also intentionally runs synchronously on the calling thread and is useful in certain test setups.

## 6. Measuring Latency from Submit to Start with TaskDecorator

`ThreadPoolTaskExecutor.setTaskDecorator(...)` lets you wrap the callback executed by the executor. You can record one timestamp when creating the wrapper and another when the wrapper starts running.

Below is an **alternative version** of the `reportExecutor` bean from section 5; do not declare two beans with the same name in one ApplicationContext:

~~~java
package example.concurrency;

import java.util.concurrent.TimeUnit;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.scheduling.annotation.EnableAsync;
import org.springframework.scheduling.concurrent.ThreadPoolTaskExecutor;

@Configuration
@EnableAsync
public class AsyncExecutorConfiguration {
    @Bean("reportExecutor")
    public ThreadPoolTaskExecutor reportExecutor() {
        ThreadPoolTaskExecutor executor = new ThreadPoolTaskExecutor();
        executor.setCorePoolSize(2);
        executor.setMaxPoolSize(4);
        executor.setQueueCapacity(10);
        executor.setThreadNamePrefix("report-");

        executor.setTaskDecorator(callback -> {
            long submittedNanos = System.nanoTime();
            return () -> {
                long startedNanos = System.nanoTime();
                long waitMillis = TimeUnit.NANOSECONDS.toMillis(
                        startedNanos - submittedNanos);
                System.out.println("executor wait (ms): " + waitMillis);
                try {
                    callback.run();
                } finally {
                    long finishedNanos = System.nanoTime();
                    long runMillis = TimeUnit.NANOSECONDS.toMillis(
                            finishedNanos - startedNanos);
                    System.out.println("executor run (ms): " + runMillis);
                }
            };
        });
        return executor;
    }
}
~~~

This integration example has **no fixed stdout**: measured values vary with scheduling and workload. In production, send both measurements to a metrics system's histogram/timer with appropriate tags rather than logging on every task.

Notes when interpreting the metric:

- `System.nanoTime()` measures **elapsed time within the same JVM**, not UTC wall time, and absolute values cannot be compared across machines.
- The callback seen by `TaskDecorator` may be a **Spring wrapper**, not necessarily the original `Runnable`/`Callable`. The measured times are wait and run duration for the executor-wrapped callback.
- A rejected task never runs the wrapper, so rejections must be counted separately.
- With `submit(...)`, the callback may be a `FutureTask` holding exceptions inside the Future. Catching exceptions around `callback.run()` is not guaranteed to observe business exceptions.
- If the callback merely submits another task and returns, the callback's execution time does not equal the completion time of the downstream task.
- If a caller-runs policy triggers, measured "wait" may be tiny and "run" happens directly inside the submission call. Do not mistake that for a background worker.

### 6.1. When to Use Wall-Clock Timestamps?

To correlate logs from request to worker, record job ID / correlation ID with a timezone-aware timestamp (e.g., UTC) at both submit and start milestones. To compute accurate durations inside the same process, use a monotonic timer such as `System.nanoTime()`. Both purposes complement each other and are not directly interchangeable.

## 7. Queue Wait Affects Timeouts, SLAs, and Business Outcomes

Hypothetical example:

| Phase | Duration |
| --- | ---: |
| Caller submits task | 2 ms |
| Task waits in queue | 2,500 ms |
| Worker executes | 300 ms |
| Total from submit to completion | About 2,802 ms |

If a dashboard only measures time inside `@Async`, it shows around **300 ms**, while users experience nearly **2.8 seconds**. Queue wait must be included in end-to-end measurements and accounted for when designing deadlines.

Distinguish:

- **Request timeout:** how long the HTTP caller waits for a response; can expire before the task even starts.
- **Future timeout:** `Future.get(timeout)` expiring only stops the caller from waiting; the task may continue in the queue/worker.
- **I/O timeout:** bounds actual HTTP/JDBC/network operations, and does not solve queue wait time.
- **Business deadline:** the point at which the work loses business value. The worker may need to check the deadline before performing side effects.
- **Cancellation:** can request cancelling a task without undoing side effects that already occurred; interruption still depends on execution code and blocking libraries.

If an API returns `202 Accepted` with a job ID, clearly define which system "accepted" has persisted to. An executor with an **in-memory-only** queue does not guarantee work survives process crash or restart. If business rules require durable acceptance, use a durable job store/queue and matching tracking state.

## 8. Submission Order Is Not Start or Finish Order

With multiple workers, B can finish before A even though A was submitted first. Even with a FIFO queue, a newly arriving task can be handed directly to a non-core worker when the queue is full, while older tasks wait for workers to pull from the queue.

~~~text
Caller:   submit A ---- submit B ---- submit C
Worker 1: [----------------- A ----------------]
Worker 2:                            [-- C --]
Queue:               [----- B waiting -----]
~~~

The diagram illustrates a scenario that can happen depending on pool configuration and load. A queue's FIFO rule **does not equate to** global completion order.

If business logic requires tasks for the same customer ID to execute in order, design ordering by key/partition/transaction or an appropriate sequential queue. Merely calling `submit(A)` before `submit(B)` is insufficient to ensure A's side effects always precede B's.

## 9. How to Diagnose When Tasks Arrive Late

Collect the following data on both caller and worker:

| Data | Purpose |
| --- | --- |
| Job/correlation ID | Correlate logs across submit, queue, start, and finish |
| Submit timestamp and admission outcome | Distinguish accepted tasks from rejected tasks |
| Start, finish, failure timestamps | Measure queue wait, execution duration, and end-to-end latency |
| Active workers / pool size | Check whether workers are fully occupied |
| Queue depth and queued task age | Detect backlogs before requests time out |
| Rejection count, executor shutdown | Separate overload from shutdown state |
| CPU, lock wait, DB/HTTP pools | Identify resources preventing workers from progressing |
| p50/p95/p99 wait and run duration | See impact on the slowest requests |

Diagnostic steps:

1. Verify **which executor bean** the application uses, whether `@Async` goes through a proxy, and whether a synchronous executor is accidentally used.
2. Separate **not accepted** errors from **accepted but not yet run**; never record queue wait for rejected tasks.
3. Measure from submit to start on the same job ID, then measure worker execution separately.
4. Inspect core/max/queueCapacity/rejection policy. While the queue has space, the pool may not scale up to max.
5. Check thread dumps and downstream dependencies: are workers waiting on JDBC, HTTP, locks, or subtasks in the same pool?
6. Run step-load tests comparing throughput, queue wait, run duration, timeouts, rejections, CPU, and connection waits before/after config changes.

If queue wait rises sharply while run duration stays flat, arrival rate likely exceeds service capacity or the pool is worker-constrained. If run duration rises as well, find I/O, DB, lock, and CPU bottlenecks before adding more threads.

## 10. Common Misconceptions

**"`@Async` returning a Future means the method body is already running."** False: the Future may be returned while the task is still sitting in the queue.

**"`Future.isDone() == false` means the task has not started."** False: an incomplete Future could be running or waiting.

**"When an idle worker exists, submit must return before start."** No such guarantee exists; the worker may start very quickly, before the caller finishes the submission call.

**"Setting a large maxPoolSize eliminates queue wait."** False: after core, executors usually prefer queuing before spawning additional workers.

**"Executor means always running on a background thread."** False: Spring has `SyncTaskExecutor`; `CallerRunsPolicy` can also run tasks directly on the caller under overload.

**"Catching exceptions in a TaskDecorator wrapper captures all errors."** False: with a `FutureTask` wrapper, exceptions may be retained inside the Future.

**"Measuring time inside `run()` is enough to know latency."** False: that measurement omits the wait from submit to start.

**"No rejections means no overload."** False: a deep queue can accumulate tasks, inflating wait time and memory without rejecting.

**"Successful submit means processing is guaranteed across restarts."** False: an in-memory queue does not provide the durability of a message broker or job store.

## 11. Self-Check Questions

**Question 1.** B is submitted successfully when a single worker is busy for 3 seconds, and B runs for 100 ms. Roughly what can B's total time from submission be?

**Answer:** around 3.1 seconds in a single-worker model with no other delays: 3 seconds waiting and 0.1 seconds running.

**Question 2.** Receiving a `CompletableFuture` means the `@Async` method body has started?

**Answer:** not necessarily. It may be queued, running, or already done; start timestamps/metrics are required to know.

**Question 3.** What can `Future.isDone()==true` mean other than success?

**Answer:** the task may have ended with an exception or the Future may have been cancelled.

**Question 4.** In the Java 17 example, why was B always not yet started when main checked?

**Answer:** A occupied the sole worker and waited on a latch; main had not opened the latch at the time of the check.

**Question 5.** With `CallerRunsPolicy`, can `execute(task)` wait until the task finishes running before returning?

**Answer:** yes. When the policy triggers and the pool is not shut down, the caller runs the task itself.

**Question 6.** Why do dashboards measuring only inside an async method often show lower latency than users see?

**Answer:** they exclude the time the task waited for a worker in the queue.

**Question 7.** If a pool has core=2, max=8, and queueCapacity=100, why might the third task not run immediately?

**Answer:** because after core, the executor prefers putting tasks into the queue while space remains rather than spawning extra workers.

**Question 8.** When a task is rejected, what event should be recorded?

**Answer:** record a submission failure/rejection with pool and caller details; do not assign a non-existent start timestamp to the task.

## 12. References

- Spring Framework — Task Execution and Scheduling: https://docs.spring.io/spring-framework/reference/6.2/integration/scheduling.html
- Spring Framework — `ThreadPoolTaskExecutor`, `setTaskDecorator(...)`: https://docs.spring.io/spring-framework/docs/6.2.9/javadoc-api/org/springframework/scheduling/concurrent/ThreadPoolTaskExecutor.html
- Java SE 17 — `ThreadPoolExecutor`: https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/concurrent/ThreadPoolExecutor.html
- Java SE 17 — `Future`: https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/concurrent/Future.html
- Java SE 17 — `System.nanoTime()`: https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/lang/System.html#nanoTime()

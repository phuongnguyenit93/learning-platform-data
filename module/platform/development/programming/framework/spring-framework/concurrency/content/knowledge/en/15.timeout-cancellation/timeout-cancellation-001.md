# Distinguishing Queue Wait Time, Execution Time, and Caller Wait Time

## 1. The Problem: One Task, Three Types of Latency

When a Spring application submits a `Runnable` or `Callable<T>` to a `ThreadPoolTaskExecutor`, the work may not start immediately: workers may be busy, forcing the task to sit in the queue before it gets to run. Meanwhile, the calling thread might process other work, wait for the result via `Future.get()`, or already return an HTTP response.

Therefore, we must distinguish **three time intervals**:

1. **Queue wait time (submit-to-start)**: from the moment the task is submitted/accepted until a worker begins running it. The measured submit-to-start interval usually includes a small amount of submission/dispatch overhead, so it is not necessarily all time physically spent inside the `BlockingQueue`.
2. **Execution time (runtime)**: from when the worker starts the measured work until the work finishes. This is elapsed wall-clock time; it can include CPU time, JDBC/HTTP I/O, lock waiting, sleep, or OS/scheduler pauses.
3. **Caller wait time**: the interval during which a calling thread is blocked in a result-retrieval call, such as `Future.get()`, `get(timeout, unit)`, or `CompletableFuture.join()`. A caller might wait immediately, wait later, wait multiple times, or never wait at all.

**Key point:** the first two measure the lifecycle of the **task**, while the third measures the behavior of the **caller**. You should not add all three together to find the total time to complete a task, because caller wait usually overlaps with queue wait and/or runtime.

A task might wait in the queue for 300 ms and execute for 200 ms, yet the caller retrieves the result after 600 ms so `get()` returns almost immediately. Conversely, a caller might time out after 100 ms even though the task has not even started running yet and will still complete normally afterward.

## 2. Timeline and Exact Measurement Formulas

Place the timestamps on the same monotonic clock of the JVM:

- `t0`: the point closest in consistency to submitting the task.
- `t1`: the worker starts executing the task.
- `t2`: the task body finishes successfully or fails.
- `t3`: the caller begins a `get()` call to wait for the result.
- `t4`: that `get()` call finishes, by returning a result, throwing an error, timing out, or being interrupted.

```text
Task lifecycle:
t0 submit                 t1 worker begins              t2 task finishes
|--------------------------|-----------------------------|
          queue wait               execution time

Caller thread (independent interval):
                     t3 get() begins          t4 get() returns/throws
                     |------------------------|
                            caller wait
```

If timestamps are placed at consistent boundaries:

```text
queueWaitNanos      ≈ t1 - t0
executionNanos       = t2 - t1
submitToFinishNanos ≈ t2 - t0
oneCallerWaitNanos   = t4 - t3

submitToFinish ≈ queueWait + execution
callerWait is NOT an additive term to the sum above.
```

The approximation sign reminds us that `t0` may be recorded right before the `submit()` call and therefore includes dispatch cost; `t2` may be recorded slightly before the Future completes/publishes the result. For accurate SLO analysis, explicitly document which boundary each timestamp measures.

Within a single JVM, use `System.nanoTime()` to compute **duration**, not `System.currentTimeMillis()`, which lacks stability against system clock adjustments. `System.nanoTime()` values are relative and **cannot be compared directly across two different processes or machines**.

## 3. Numerical Example: Caller Wait Depends on When get() Is Called

Suppose:

- Submit at 0 ms.
- Worker starts at 300 ms.
- Task finishes at 500 ms.

Then queue wait is about **300 ms**, execution time is **200 ms**, and submit-to-finish is **500 ms**.

| Caller action | Approximate caller wait | Interpretation |
| --- | ---: | --- |
| Call `get()` right after submit | 500 ms | Waits for both queue and execution |
| Call `get()` only at 350 ms | 150 ms | Waits only for the unfinished portion of the task |
| Call `get()` only at 600 ms | Nearly 0 ms | Future already has the result |
| Call `get(100 ms)` starting at 0 ms | 100 ms then `TimeoutException` | Task is still in the queue and may still continue |
| Never call `get()` | 0 ms | Task can still run independently |

This is an idealized illustrative timeline, not actual stdout. Scheduler, GC, and wrapper overhead can cause small deviations in timestamps.

If the application returns HTTP 202 right after submit, **request latency can be low** while business-job latency is very high. If a controller immediately calls `get()`, the HTTP thread can still be blocked even though the task runs on a separate pool.

## 4. How Does Queue Wait Form in ThreadPoolTaskExecutor?

`ThreadPoolTaskExecutor` configures an underlying `ThreadPoolExecutor`. The typical task admission rules are:

1. Prefer creating a core worker when fewer than `corePoolSize` workers exist.
2. Once core workers are at capacity, try placing the task into the queue.
3. If the queue cannot accept more tasks, try creating workers up to `maxPoolSize`.
4. If both workers and queue are out of capacity, apply the rejection policy.

Configuring `queueCapacity` changes this behavior:

- With `queueCapacity > 0`, Spring uses a `LinkedBlockingQueue` of the configured capacity. Tasks can wait before a worker becomes free.
- With `queueCapacity = 0`, Spring uses a `SynchronousQueue`, storing no backlog; tasks are handed off directly or the pool tries to open another worker.
- With a very large queue capacity, many waiting tasks can accumulate, driving up p95/p99 queue wait and memory retention even if `maxPoolSize` is set high.

**`queueCapacity` is an element count, not a duration.** There is no such meaning as “queueCapacity=100 means wait at most 100 ms”. Wait time depends on task submission rate, completion rate, pool size, and scheduling.

### 4.1. Queue Size Does Not Equal Queue Wait

`executor.getQueueSize()` is a snapshot of how many tasks are waiting, not the age of the tasks. A queue with just one task can still hold a task that has been waiting a very long time if the worker is stuck. Conversely, a queue size of 0 can still coincide with high runtime or many callers waiting on Futures.

With `SynchronousQueue`, queue size is structurally 0, which is not enough to conclude the executor is not overloaded. You must monitor `activeCount`, throughput, rejections, and the submit-to-start latency distribution.

### 4.2. Tasks Rejected or Cancelled Before Running

If submission throws `TaskRejectedException`, the task was never accepted. If cancelled before starting, `t1/t2` do not exist in terms of task body execution. Therefore, do not put these jobs into the “execution time of executed tasks” histogram with a fake 0 value. Record **rejected, cancelled-before-start, and expired-before-start** separately to avoid distorting statistics.

## 5. Runtime: Elapsed Time, Not CPU Time

A worker can run a task for 1 second while using only a few milliseconds of CPU if most of the time is spent waiting on JDBC, HTTP responses, locks, filesystem I/O, or semaphores. That is still **1 second of execution time** when measuring elapsed time at the task boundary.

Distinguish two optimization directions:

- High queue wait with low runtime: usually calls for examining backlog, core/max/queue sizing, admission control, and fairness.
- High runtime with low queue wait: usually calls for examining business logic, I/O, queries, locks, downstream timeouts, or connection pool limits.

Only increase thread count when the real bottleneck actually allows more concurrency. When a downstream DB is already out of connections, increasing the thread pool can make both queue wait and runtime worse.

A runtime measurement fragment:

```java
long startedNanos = System.nanoTime();
try {
    return work.call();
} finally {
    long executionNanos = System.nanoTime() - startedNanos;
    recordExecutionTime(executionNanos);
}
```

This snippet is a fragment requiring `Callable<T> work` and `recordExecutionTime(...)` to be declared. If the metrics callback throws an error, it can alter the task's outcome; observers should never throw exceptions.

## 6. Caller Wait: The Limit of get(timeout) Is a Wait Limit, Not an Execution Limit

`Future.get(timeout, unit)` waits for at most the supplied duration for **that specific call**. If the result is not ready yet, it throws `TimeoutException`. Crucially:

- The timeout on `get` **does not automatically call `future.cancel(...)`**.
- It **does not stop** the worker and does not remove the task from the queue.
- The task can still start after the caller has timed out and continue executing side effects.
- If a caller calls `get(100ms)` multiple times, each call gets a new wait budget; total caller blocked time can exceed 100 ms.
- If a caller starts `get(100ms)` 900 ms after submit, total workflow time can be around 1,000 ms or more, not a 100 ms limit from submit time.

Example fragment:

```java
try {
    String value = future.get(100, TimeUnit.MILLISECONDS);
    use(value);
} catch (TimeoutException ex) {
    // The Future may still be in the queue or running.
    // Decide explicitly: continue tracking, cancel, return pending status...
}
```

This is a fragment; `Future<String> future`, the `use` method, and imports/handling for `InterruptedException`/`ExecutionException` must exist in a real application.

### 6.1. Request Latency Is Not Identical to Caller Wait

Request latency also includes validation, serialization, database work, HTTP logic, and many other steps. Caller wait is only the duration the request thread is blocked by the Future. A request that does not call `get()` has a caller wait of 0 even if the background job takes many minutes.

On the user-facing side, define separate SLOs for **request acknowledgement latency** and **business job completion latency**.

## 7. Deadline, Timeout, and Cancellation: Three Different Meanings

Because this topic belongs to **Timeouts and Cancellation**, let's clarify the differences:

| Mechanism | What does it limit? | Does it automatically stop the task? |
| --- | --- | --- |
| `Future.get(timeout)` | Time **a caller waits in one call** | No |
| Business deadline | Final deadline by which the result is still valid | No, unless checked/enforced by policy |
| HTTP/JDBC client timeout inside task | Time I/O/downstream calls are allowed to wait | Depends on API and configuration |
| `Future.cancel(true)` | Attempts to cancel Future and may request task interruption | Best-effort, no guarantee task stops immediately |
| `CompletableFuture.orTimeout(...)` | Completes Future with a timeout error if not yet done | Does not guarantee interrupting background work |
| `CompletableFuture.completeOnTimeout(...)` | Completes Future with a fallback value | Does not guarantee cancelling real work |

### 7.1. Expiring While Still in the Queue

A task has a 10:00 deadline, but a worker only picks it up at 10:01. Without a guard, the task might still execute work that is already useless. You can pass the deadline in the payload and check it **right when execution starts**:

```java
long deadlineNanos = System.nanoTime() + TimeUnit.SECONDS.toNanos(2);

Callable<String> work = () -> {
    if (System.nanoTime() - deadlineNanos >= 0) {
        throw new TimeoutException("Expired before work started");
    }
    return performWork();
};
```

This is a fragment requiring `Callable`, `TimeUnit`, `TimeoutException`, and `performWork()`. It does not remove the task from the queue before start; it only skips the work once a worker has picked it up if the deadline has passed.

To genuinely control backlog, add a bounded queue, admission control, an eviction policy for stale work, and status tracking.

### 7.2. Running Out of Execution Time

A task that already has a worker can get stuck on network/DB calls. Here, the caller's `get(timeout)` is not enough; you must configure client/downstream timeouts and/or cooperative cancellation inside the task.

`FutureTask`'s `Future.cancel(true)` can send an interrupt to a running worker, but it cannot guarantee every HTTP/socket/JDBC call stops immediately. `CompletableFuture.cancel(true)` has its own semantics and does not use the `mayInterruptIfRunning` parameter to guarantee interruption.

### 7.3. Do Not Retry Side Effects Just Because the Caller Lost Patience

If a user submits a payment or email, the caller might time out before the task finishes writing. Immediately resubmitting the same work can produce duplicate side effects. Use idempotency keys, job status, transaction/outbox patterns, or appropriate reconciliation.

A caller timeout reflects **not receiving a result on time**, not proof that the work has not happened.

## 8. Runnable Experiment: Java 21 + Spring Framework 6.2.1

This program intentionally triggers two timeouts on the same `Future<Integer>`:

1. The pool has **1 worker** and `queueCapacity=2`.
2. Task A occupies the worker, waiting on a latch.
3. Task B is submitted, but cannot run because A holds the worker.
4. Caller calls `B.get(30ms)` and times out **while B is still in the queue**.
5. Release A; task B starts and is held by another latch.
6. Caller calls `B.get(30ms)` again and times out **while B is running**.
7. Release B, read result 42. Two timeouts did not cancel the Future.

Do not use `Thread.sleep()` to guess execution scheduling. All key milestones are guarded by `CountDownLatch`.

### 8.1. Maven Structure

```text
task-timing-demo/
├── pom.xml
└── src/main/java/demo/TaskTimingDemo.java
```

**File `pom.xml`:**

```xml
<project xmlns="http://maven.apache.org/POM/4.0.0"
         xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
         xsi:schemaLocation="http://maven.apache.org/POM/4.0.0 https://maven.apache.org/xsd/maven-4.0.0.xsd">
  <modelVersion>4.0.0</modelVersion>
  <groupId>demo</groupId>
  <artifactId>task-timing-demo</artifactId>
  <version>1.0.0</version>
  <properties>
    <maven.compiler.release>21</maven.compiler.release>
    <project.build.sourceEncoding>UTF-8</project.build.sourceEncoding>
  </properties>
  <dependencies>
    <dependency>
      <groupId>org.springframework</groupId>
      <artifactId>spring-context</artifactId>
      <version>6.2.1</version>
    </dependency>
  </dependencies>
  <build>
    <plugins>
      <plugin>
        <groupId>org.apache.maven.plugins</groupId>
        <artifactId>maven-compiler-plugin</artifactId>
        <version>3.13.0</version>
      </plugin>
      <plugin>
        <groupId>org.codehaus.mojo</groupId>
        <artifactId>exec-maven-plugin</artifactId>
        <version>3.5.0</version>
        <configuration>
          <mainClass>demo.TaskTimingDemo</mainClass>
        </configuration>
      </plugin>
    </plugins>
  </build>
</project>
```

**File `src/main/java/demo/TaskTimingDemo.java`:**

```java
package demo;

import java.util.concurrent.Callable;
import java.util.concurrent.CountDownLatch;
import java.util.concurrent.ExecutionException;
import java.util.concurrent.Future;
import java.util.concurrent.TimeUnit;
import java.util.concurrent.TimeoutException;
import java.util.concurrent.atomic.AtomicLong;

import org.springframework.context.annotation.AnnotationConfigApplicationContext;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.scheduling.concurrent.ThreadPoolTaskExecutor;

public class TaskTimingDemo {
    @Configuration(proxyBeanMethods = false)
    public static class AppConfig {
        @Bean("workExecutor")
        public ThreadPoolTaskExecutor workExecutor() {
            ThreadPoolTaskExecutor executor = new ThreadPoolTaskExecutor();
            executor.setCorePoolSize(1);
            executor.setMaxPoolSize(1);
            executor.setQueueCapacity(2);
            executor.setThreadNamePrefix("timed-");
            executor.setWaitForTasksToCompleteOnShutdown(true);
            executor.setAwaitTerminationSeconds(5);
            return executor;
        }
    }

    private static void await(CountDownLatch latch, String step)
            throws InterruptedException {
        if (!latch.await(5, TimeUnit.SECONDS)) {
            throw new IllegalStateException(step + " not reached");
        }
    }

    private static boolean timedOut(
            Future<?> future, AtomicLong callerWaitNanos)
            throws InterruptedException, ExecutionException {
        long beforeWait = System.nanoTime();
        try {
            future.get(30, TimeUnit.MILLISECONDS);
            return false;
        } catch (TimeoutException expected) {
            return true;
        } finally {
            callerWaitNanos.addAndGet(System.nanoTime() - beforeWait);
        }
    }

    public static void main(String[] args) throws Exception {
        try (var context = new AnnotationConfigApplicationContext(AppConfig.class)) {
            ThreadPoolTaskExecutor executor =
                    context.getBean("workExecutor", ThreadPoolTaskExecutor.class);

            CountDownLatch blockerStarted = new CountDownLatch(1);
            CountDownLatch releaseBlocker = new CountDownLatch(1);
            CountDownLatch taskStarted = new CountDownLatch(1);
            CountDownLatch releaseTask = new CountDownLatch(1);
            AtomicLong startedNanos = new AtomicLong();
            AtomicLong finishedNanos = new AtomicLong();
            AtomicLong callerWaitNanos = new AtomicLong();

            try {
                Future<Void> blocker = executor.submit((Callable<Void>) () -> {
                    blockerStarted.countDown();
                    releaseBlocker.await();
                    return null;
                });
                await(blockerStarted, "blockerStarted");

                long submittedNanos = System.nanoTime();
                Future<Integer> task = executor.submit((Callable<Integer>) () -> {
                    startedNanos.set(System.nanoTime());
                    taskStarted.countDown();
                    try {
                        releaseTask.await();
                        return 42;
                    } finally {
                        finishedNanos.set(System.nanoTime());
                    }
                });

                boolean timeoutInQueue = timedOut(task, callerWaitNanos);
                releaseBlocker.countDown();
                await(taskStarted, "taskStarted");
                boolean timeoutWhileRunning = timedOut(task, callerWaitNanos);
                releaseTask.countDown();

                int result = task.get(5, TimeUnit.SECONDS);
                blocker.get(5, TimeUnit.SECONDS);

                long queueWaitNanos = startedNanos.get() - submittedNanos;
                long executionNanos = finishedNanos.get() - startedNanos.get();

                System.out.println("timeoutInQueue=" + timeoutInQueue);
                System.out.println("timeoutWhileRunning=" + timeoutWhileRunning);
                System.out.println("result=" + result);
                System.out.println("cancelled=" + task.isCancelled());
                System.out.println("queueWaitPositive=" + (queueWaitNanos > 0));
                System.out.println("executionPositive=" + (executionNanos > 0));
                System.out.println("callerWaitPositive=" +
                        (callerWaitNanos.get() > 0));
            } finally {
                releaseBlocker.countDown();
                releaseTask.countDown();
            }
        }
    }
}
```

### 8.2. Compile and Run

Requires Maven and JDK 21 or later. From the directory containing `pom.xml`:

```bash
mvn -q -DskipTests compile exec:java
```

**Compiled and tested actual stdout:**

```text
timeoutInQueue=true
timeoutWhileRunning=true
result=42
cancelled=false
queueWaitPositive=true
executionPositive=true
callerWaitPositive=true
```

The program prints booleans to avoid asserting millisecond values that vary across environments. The result `42` and the two timeouts were confirmed via `Future`; `cancelled=false` shows that caller timeouts do not cancel the Future.

### 8.3. Explaining the Three Measurements in Code

- `submittedNanos` is captured before submitting B.
- `startedNanos` is recorded when the worker has started B, after A is released.
- `finishedNanos` is recorded in B's `finally` block when B's body finishes.
- `callerWaitNanos` accumulates the elapsed time of **the two `get(30ms)` calls** inside `timedOut`.

Therefore:

```java
long queueWaitNanos = startedNanos.get() - submittedNanos;
long executionNanos = finishedNanos.get() - startedNanos.get();
long callerBlockedNanos = callerWaitNanos.get();
```

This is an explanatory fragment taken from the variables declared in the example. It measures the submit-to-start interval, B's execution time, and **the total wait time of exactly the two instrumented `get(timeout)` calls**. It does not include the final `get(5, SECONDS)` call to receive `42`; to measure total caller wait of a flow, you must wrap every wait call you want counted.

You can add the following snippet to view the measurements on your machine:

```java
System.out.printf(
        "queue=%.3fms, execution=%.3fms, callerWait=%.3fms%n",
        queueWaitNanos / 1_000_000.0,
        executionNanos / 1_000_000.0,
        callerBlockedNanos / 1_000_000.0);
```

These values **will vary with scheduling**, so there is no fixed numeric stdout. The two caller waits overlap with portions of queue and execution time, so do not add them to submit-to-finish.

### 8.4. Why Is the Test Stable?

`blockerStarted` ensures the worker is already occupied by A. `releaseBlocker` ensures B stays in the queue during the first timeout. `taskStarted` confirms B transitioned from queued to running. `releaseTask` holds B in the running state during the second timeout. `finally` releases both latches if an assertion fails, preventing a worker from staying blocked forever.

This is a better concurrency testing technique than relying on `Thread.sleep(100)`, because execution order is not decided by guessing whether a thread has probably run.

## 9. Practical Measurement Using a Wrapper Without Latches

In production, you can wrap `Callable<T>` at the submission point:

```java
// Utility fragment: imports Callable, Future, LongConsumer, AsyncTaskExecutor.
public static <T> Future<T> submitMeasured(
        AsyncTaskExecutor executor,
        Callable<T> work,
        LongConsumer queueObserver,
        LongConsumer runtimeObserver) {

    long submittedAt = System.nanoTime();

    return executor.submit(() -> {
        long startedAt = System.nanoTime();
        queueObserver.accept(startedAt - submittedAt);
        try {
            return work.call();
        } finally {
            runtimeObserver.accept(System.nanoTime() - startedAt);
        }
    });
}
```

This is a fragment that belongs inside a class and requires thread-safe, fast, non-throwing observers; if an observer throws an error, it can break the task or mask a business exception. The measured submit-to-start region includes dispatch overhead, not just time spent in the queue data structure alone.

**If submission is rejected**, the wrapper never runs; you must record `TaskRejectedException` at the caller or via executor instrumentation. If a task is cancelled before starting, there is likewise no runtime sample as for an executed task.

### 9.1. Is Spring's TaskDecorator Enough?

`ThreadPoolTaskExecutor.setTaskDecorator(...)` can wrap callbacks to set up MDC, context, or measure timing. However, with `submit(...)`, the callback seen by the decorator may be a `FutureTask` wrapping the original task; task failures may be stored inside the Future rather than escaping `run()`.

Therefore, `TaskDecorator` does not automatically give you complete original exceptions and timestamps. Explicitly decide where to capture submit time, how to identify tasks, and who observes the Future outcome. Do not assume `catch(Throwable)` around `Runnable.run()` will catch every error from a submitted task.

### 9.2. Metrics to Examine Together

- Histograms for queue wait (p50/p95/p99) and runtime (p50/p95/p99).
- Caller wait broken down by endpoint/call site.
- Submit-to-completion latency of the actual work.
- Accepted, rejected, expired, cancelled, failed, and succeeded counts.
- `getPoolSize()`, `getActiveCount()`, and `getQueueSize()` over time.
- CPU, GC, thread count, DB/HTTP pool wait, downstream timeouts, and retry rate.

A single point-in-time queue size snapshot cannot replace a wait-time distribution.

## 10. Shared Deadline for the Whole Workflow Instead of Resetting get(timeout)

Suppose a request has an **800 ms** budget from start, but spends 500 ms on validation. If it then calls `future.get(800ms)`, total time can reach 1,300 ms.

One way to compute remaining budget using a monotonic clock:

```java
long deadline = System.nanoTime() + TimeUnit.MILLISECONDS.toNanos(800);

// ... several other steps have elapsed ...

long remaining = deadline - System.nanoTime();
if (remaining <= 0) {
    throw new TimeoutException("Overall deadline reached");
}

String value = future.get(remaining, TimeUnit.NANOSECONDS);
```

This is a fragment; it requires `Future<String> future` and handling of checked exceptions. Each subsequent step must recompute `remaining` from **the same deadline**. This bounds total caller wait time better than creating a fresh timeout at each step, but **does not automatically force the task to stop at the deadline**.

When propagating across multiple JVMs, do not send raw `System.nanoTime()` values as global timestamps: monotonic clock origins differ across machines. You can propagate the remaining time budget or a wall-clock deadline handled with clock skew in mind.

## 11. Spring @Async and CompletableFuture: Easy-to-Confuse Measurement Scopes

### 11.1. @Async Only Runs Through a Proxy When Eligible

In the default `AdviceMode.PROXY`, `@Async` requires a Spring-managed bean, `@EnableAsync` configuration (or XML annotation-driven), and a caller invoking through the proxy. A self-invocation like `this.asyncMethod()` inside the same target bypasses the proxy; in that case the method may run synchronously, and no new async submission occurs for that call.

If you want to measure `@Async` queue wait, instrument at the executor/submission boundary rather than just taking a timestamp at the top of the method. Do not try to fix “queue wait=0” by raising `maxPoolSize` when proxy interception is not happening at all.

### 11.2. The Proxy's Future Differs from the Target's Temporary Future

An `@Async` method declaring `CompletableFuture<T>` may return `CompletableFuture.completedFuture(value)` in its body. This is a temporary Future transferring the value from the target; the caller receives the proxy's Future. The proxy's Future can remain pending until a worker runs and finishes bridging the result.

When measuring caller wait, measure on the Future the caller actually holds; when measuring runtime, define the duration of the target/bridge invocation; when measuring queue wait, start from the point Spring submits the invocation task.

### 11.3. get(timeout), orTimeout, and completeOnTimeout Differ

- `future.get(timeout, unit)` times out the **waiting** call without automatically changing the Future's completion state.
- `CompletableFuture.orTimeout(timeout, unit)` completes the Future with a timeout error if still unfinished, but does not guarantee cancelling/interrupting the worker.
- `CompletableFuture.completeOnTimeout(defaultValue, timeout, unit)` lets the Future complete with a fallback value without proving background work has stopped.

Do not use these three APIs as replacements for JDBC/HTTP client timeouts or a business cancellation contract.

## 12. When the Caller Times Out: Continue, Cancel, or Track?

The choice should be based on the nature of the work:

**Discardable tasks**, such as quick recommendation calculations: the caller can attempt `cancel(...)` or mark the result no longer needed. The task must support cooperative cancellation if you want to genuinely save worker capacity.

**Tasks that must complete**, such as issuing an invoice: a caller timeout does not invalidate the business request. You need to store a job ID, durable status, idempotency, controlled retries, or an appropriate outbox/broker; the request should have a way to look up the result.

**Tasks past their business deadline**, such as refreshing a stale cache snapshot: check the deadline before starting side effects or at safe points inside the task and record an expired status. Do not pretend a queue automatically understands deadlines just by configuring `queueCapacity`.

Separate **stopping the caller's wait**, **stopping the worker's processing**, and **expiring business validity**.

## 13. Common Mistakes

| Mistake | Why it is wrong | How to fix |
| --- | --- | --- |
| Treating queue wait, runtime, and caller wait as one | Mismeasures latency and root cause | Capture timestamps at three separate boundaries |
| Adding caller wait to queue + runtime | Double-counts overlapping time | Lay out timelines in parallel |
| Assuming `get(timeout)` limits execution time | Only limits a single caller wait | Add deadline/timeout inside the task |
| Using `queueCapacity=100` as a 100 ms queue timeout | Capacity is a task count | Measure task age and check deadlines |
| Waiting on Future after task finished and inferring runtime from get() | Caller wait is near 0 even if runtime was large | Measure start/end inside the task |
| Calling `get(100ms)` repeatedly and thinking the total is 100ms | Each call gets a fresh budget | Use a shared deadline |
| Believing `cancel(true)` always kills the worker | Interrupt is best-effort and API-dependent | Cooperative cancellation and cleanup |
| Looking only at `getQueueSize() == 0` | Does not reflect running tasks or waiting callers | Monitor activeCount, runtime, and wait latency |
| Increasing queue size to “solve” high runtime | Only holds more backlog | Find the task/downstream bottleneck |
| Putting a timestamp at the start of `@Async` and treating it as submit time | Misses queue wait | Measure at the proxy/executor boundary |
| Checking only `Future.isDone()` and assuming success | Done includes cancel/exception | Classify outcomes separately |
| Ignoring rejections/cancellations-before-start | Metrics miss tasks that never ran | Record rejected/cancelled/expired separately |
| Retrying side-effecting work right after timeout | Can execute twice | Idempotency keys and job status |
| Subtracting `nanoTime()` from two machines | Monotonic clock origins differ | Propagate remaining budget or appropriate deadline |

## 14. Self-Check Exercises

**Question 1.** Submitted at 0 ms, started at 250 ms, finished at 400 ms, caller starts `get` at 300 ms. Compute the three metrics.

Queue wait 250 ms, runtime 150 ms, caller wait approximately 100 ms. Submit-to-finish is 400 ms; **do not add** the 100 ms caller wait.

**Question 2.** Caller receives `TimeoutException` before the task has started. Is the task cancelled?

No. `Future.get(timeout)` does not auto-cancel. The task can still be run by a worker once queue space frees up.

**Question 3.** Queue wait 900 ms, runtime 10 ms versus queue wait 10 ms, runtime 900 ms — total latency is nearly equal; is the remediation the same?

No. The first case requires inspecting backlog and executor scheduling; the second requires inspecting task logic/I/O/locks/downstream calls. Simply increasing queue capacity can make the first case worse.

**Question 4.** A caller does not call `get()` and returns HTTP 202 immediately. What is caller wait? Does it prove the task is done?

Caller wait on the Future is 0; it does not prove the task has completed. You need a job completion metric and a status API.

**Question 5.** On the same Future, a caller calls `get(100ms)` three times in a row and all time out. How long can actual total wait time be?

Around 300 ms plus overhead, even though each `get` used a 100 ms timeout. To bound the whole workflow, use one shared deadline.

**Question 6.** Why does `ThreadPoolTaskExecutor.getQueueSize() == 0` not mean nobody is waiting?

Because a task may be running for a long time, callers may be waiting on Futures, or the executor may use `SynchronousQueue`, which stores no elements. Queue size is neither caller wait nor runtime.

## 15. Production Checklist

Before putting the system into production, verify:

- Are submit, worker-start, worker-finish, and caller-get-start/end milestones clearly defined?
- Do timestamps measuring duration within the same process use a monotonic clock?
- Are there p50/p95/p99 histograms for queue wait, runtime, caller wait, and submit-to-completion?
- Are accepted/rejected/cancelled/expired tasks separated from executed tasks?
- Are `corePoolSize`, `maxPoolSize`, `queueCapacity`, rejection policy, and the actual injected pool properly understood?
- If using `@Async`, do calls go through the proxy rather than self-invocation?
- Is there a shared deadline with remaining budget calculated before each `get(timeout)`?
- Are there dedicated timeouts for DB/HTTP/locks inside the task?
- If the caller times out, should the task continue or attempt cancellation? Who owns the final state?
- For side effects, are idempotency, retries, and durable job semantics in place?
- Are callers unnecessarily blocking event loops or request workers?
- Do tests use `CountDownLatch` or coordination primitives to distinguish queued vs. running instead of relying on `Thread.sleep()`?

## 16. Summary

**Queue wait** is the interval from submission until a worker starts. **Execution time** is the interval the worker executes the measured code. **Caller wait** is the interval the calling thread waits on the Future; it may span both queue+runtime, only part of it, nearly 0, or end in a timeout while the task has not yet run.

In Spring, measure the three intervals at three distinct boundaries and observe them alongside executor metrics. In particular, **a caller wait timeout does not mean the task has expired or been cancelled**. Design deadlines, downstream timeouts, cancellation, and idempotency around business requirements, not around `Future.get(timeout)` alone.

### References

- [Spring Framework 6.2 — Task Execution and Scheduling](https://docs.spring.io/spring-framework/reference/6.2/integration/scheduling.html)
- [Spring Framework 6.2.1 — ThreadPoolTaskExecutor API](https://docs.spring.io/spring-framework/docs/6.2.1/javadoc-api/org/springframework/scheduling/concurrent/ThreadPoolTaskExecutor.html)
- [Spring Framework 6.2.1 — AsyncTaskExecutor API](https://docs.spring.io/spring-framework/docs/6.2.1/javadoc-api/org/springframework/core/task/AsyncTaskExecutor.html)
- [Java 21 — Future API](https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/util/concurrent/Future.html)
- [Java 21 — CompletableFuture API](https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/util/concurrent/CompletableFuture.html)
- [Java 21 — System.nanoTime](https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/lang/System.html#nanoTime())
# Concurrency Limit of SimpleAsyncTaskExecutor

## 1. Goal and Problem to Solve

`SimpleAsyncTaskExecutor` is an `AsyncTaskExecutor` implementation in Spring Framework. Each time it receives a task, it creates **a new thread** to run that task; it **does not maintain a pool to reuse threads**. Therefore, if an application receives many slow tasks at the same time, the number of threads and concurrently executing tasks can grow rapidly. The *concurrency limit* lets you place a cap on **the number of active task executions at one time** for this executor itself.

For example, suppose a service can tolerate at most 8 concurrent external requests. If the application receives 50 tasks almost simultaneously, you should not by default spin up 50 running tasks to call that service. You can configure:

```java
SimpleAsyncTaskExecutor executor = new SimpleAsyncTaskExecutor("remote-");
executor.setConcurrencyLimit(8);
```

This is a configuration snippet and requires Spring Framework on the classpath. With a limit of 8, the executor coordinates so that no more than 8 tasks that **it** executes run concurrently. The 9th task is not automatically placed into a separate queue. **Under the default policy, the thread calling `execute(...)` blocks until an execution slot frees up.** Since Spring Framework 6.2.6, you can choose to reject immediately instead of blocking the caller.

This lesson clarifies the limiting mechanism, the two policies when hitting the cap, integration with `@Async`, the impact of platform/virtual threads, when to use it, and when to switch to an executor with a pool and queue.

## 2. Understand the Execution Model Before Setting a Limit

### 2.1. Each Task Creates Its Own Thread

When calling:

```java
executor.execute(() -> handleRequest());
```

`SimpleAsyncTaskExecutor` creates a new thread for an accepted task. After the task finishes, that thread terminates, **without returning to a pool to serve the next task**. A positive concurrency limit only caps how many tasks can run concurrently; it **does not turn the executor into a thread pool**.

Distinguish these metrics:

| Term | Meaning for `SimpleAsyncTaskExecutor` |
| --- | --- |
| Accepted tasks | Tasks that have passed the limit check and been launched by the executor |
| Concurrent tasks | Tasks currently executing, capped by `concurrencyLimit` if configured to a positive value |
| Threads created over time | Can be very large because every new task creates a thread, even when the limit is small |
| Internal queue | **No `ThreadPoolExecutor`-style task queue** to accumulate waiting work |
| Thread calling `execute` | Can **block** when the limit is full under the default configuration |
| Multiple application instances | Each executor in each JVM enforces its own limit; it does not create a cluster-wide quota |

Setting `setConcurrencyLimit(1)` means at any moment at most **one** task executes through that executor. It does not mean **the same thread** handles all tasks; each execution still uses newly created threads.

### 2.2. Timeline When concurrencyLimit = 2

Suppose A, B, and C each take 5 seconds, and A and B are already running:

```text
Time         Task A      Task B      Task C             Thread submitting C
t0           running     running     not yet accepted   calls execute(C)
t0..t5       running     running     not yet accepted   blocked because all 2 slots are full
t5           finishes    running     accepted           execute(C) finally returns
t5..         done        running     runs on a new      continues caller's work
                                     thread
```

This is an illustrative timeline, not a guaranteed execution schedule: A and B may finish at different times, another caller may claim the slot first, and the OS decides when the new thread is scheduled.

Key point: **what waits is the task-submission call**, not a task already sitting inside an executor queue. Blocking at the submission gate can provide simple *backpressure*, yet it also holds up request threads, scheduled threads, or consumer threads.

If using `@Async`, a call from another bean is dispatched by Spring to the executor. When the executor has reached its limit under the blocking policy, **the call to the `@Async`-annotated method itself can still block at the submit step**. Thus, the annotation does not guarantee that the caller always returns immediately under overload.

## 3. Settings and Boundary Values to Understand

The APIs below are verified for Spring Framework **6.2.10**. Notes explicitly marked “since 6.2.6” do not apply to all older 6.0, 6.1, or earlier 6.2 releases.

| API / value | Behavior |
| --- | --- |
| `setConcurrencyLimit(n)` with `n > 0` | Limits at most `n` tasks executing concurrently on this executor |
| `setConcurrencyLimit(1)` | Allows at most one task running at a time; still creates a new thread for each task |
| Default `-1` / `UNBOUNDED_CONCURRENCY` | **Unbounded concurrency**; this is the default state |
| `0` / `NO_CONCURRENCY` | Disables accepting concurrent executions; **do not use 0 to mean sequential execution**, use 1 |
| `getConcurrencyLimit()` | Reads the configured limit value |
| `isThrottleActive()` | Indicates whether throttling is enabled, **not** the number of running tasks or whether it is full |
| `setRejectTasksWhenLimitReached(false)` | **Default:** blocks the submitting thread until a slot is available |
| `setRejectTasksWhenLimitReached(true)` | **Since 6.2.6:** rejects immediately with `TaskRejectedException` when full |
| `setVirtualThreads(true)` | **Since Spring 6.1, JDK 21+:** creates virtual threads instead of platform threads; does not automatically remove limits |
| `setTaskTerminationTimeout(ms)` | **Since Spring 6.1:** sets how long `close()` waits for tasks to finish; incurs task-tracking overhead |

**Note on runtime configuration changes:** treat the concurrency limit as a creation-time setting. The underlying `ConcurrencyThrottleSupport` API warns against switching back and forth between `-1` and a specific limit while running, as the concurrency count state can become inconsistent. If you need dynamic rate/quota adjustments, design and test a dedicated management mechanism rather than mutating it arbitrarily while many tasks are active.

### 3.1. Leaving the Default `-1`

With platform threads, many long or I/O-waiting tasks can create many threads, consuming stack memory, scheduler resources, and putting pressure on CPU. With virtual threads, per-thread overhead is typically lower, yet **the number of DB queries, HTTP requests, file descriptors, downstream quotas, application memory, and pending work still have real limits**.

There is no “safe default limit” that fits every workload. If using `SimpleAsyncTaskExecutor` on a high-traffic processing path, you must know the expected load and how the system protects against overload.

### 3.2. A Limit Does Not Mean a Timeout

`setConcurrencyLimit(8)` **does not** require a task to finish within a certain time, nor does it set timeouts on HTTP clients, JDBC, or I/O. If eight running tasks hang indefinitely, the ninth caller can wait indefinitely under blocking mode.

Distinguish three different timeouts:

1. **Submission wait:** how long a caller waits to be admitted to the executor when all slots are taken; `SimpleAsyncTaskExecutor` does not provide a configurable queue-wait timeout directly via `setConcurrencyLimit`.
2. **Execution timeout:** the maximum time a task or dependency is allowed to run; this must be configured on the appropriate API such as the HTTP client, JDBC, or a controlled deadline/cancellation mechanism.
3. **Termination timeout:** `setTaskTerminationTimeout` is for **closing the executor**, not a per-task timeout during normal execution.

## 4. Two Policies When Hitting the Limit: Block Caller vs. Reject Immediately

### 4.1. Default: Block the Submitter

```java
SimpleAsyncTaskExecutor executor = new SimpleAsyncTaskExecutor("blocking-");
executor.setConcurrencyLimit(2);
// Do not enable setRejectTasksWhenLimitReached(true): keep default false.
```

If two tasks occupy both slots, calling `executor.execute(thirdTask)` waits until a slot frees up. This prevents running tasks from exceeding the limit, **without creating a separately managed queue**.

Pros: simple for a submitting thread willing to wait, creating backpressure to slow down submission.

Risks: an HTTP request needing to respond, an event loop, a job scheduler, or a message consumer can block unexpectedly. If a task inside the executor waits on work submitted back into **the same executor** while the limit is full, deadlock or prolonged wait chains can occur. Never do nested `execute` calls and wait for results without accounting for remaining capacity.

### 4.2. Since Spring 6.2.6: Reject Immediately When Full

```java
SimpleAsyncTaskExecutor executor = new SimpleAsyncTaskExecutor("reject-");
executor.setConcurrencyLimit(2);
executor.setRejectTasksWhenLimitReached(true);
```

When both slots are busy, a new submission throws `org.springframework.core.task.TaskRejectedException`. This exception extends `java.util.concurrent.RejectedExecutionException`. Callers need an explicit policy: return an overload error, ask to retry later, throttle input, or route work to a reliable queue/job store depending on business needs. **Do not treat rejection as the task being saved and retried automatically.**

This rejection mechanism is available from **Spring Framework 6.2.6**. If a project runs Spring Framework 6.2.5 or earlier, do not copy `setRejectTasksWhenLimitReached(true)` without upgrading or checking the API.

### 4.3. Policy Selection Table

| Requirement | Recommendation |
| --- | --- |
| A rate-controlled batch producer that can tolerate waiting | A positive concurrency limit with the **block** policy may suffice |
| An HTTP API needing fast overload detection | Consider **reject**, handling errors at the HTTP boundary; avoid holding servlet/event-loop threads long |
| Wanting to wait in a sized queue with stable worker count | Use `ThreadPoolTaskExecutor` with explicitly designed pool/queue/rejection policies |
| Tasks that must survive restarts with idempotent retries | Use a job store, message broker, outbox, or durable background processing system |
| Wanting to cap total downstream calls across multiple pods | Shared rate/concurrency control or downstream limits; a local limit is insufficient |

## 5. Runnable Example: One Execution Slot and Rejecting the Second Task

Standalone example using **Java 17 + Maven + Spring Framework 6.2.10**. It demonstrates the scenario where one task holds the slot and the second task is rejected immediately in **reject mode**. `CountDownLatch` keeps the first task active so the outcome does not depend on thread-scheduling luck.

Create the file tree:

```text
simple-executor-limit/
├── pom.xml
└── src/main/java/demo/LimitDemo.java
```

**File `pom.xml`:**

```xml
<project xmlns="http://maven.apache.org/POM/4.0.0"
         xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
         xsi:schemaLocation="http://maven.apache.org/POM/4.0.0 https://maven.apache.org/xsd/maven-4.0.0.xsd">
    <modelVersion>4.0.0</modelVersion>

    <groupId>demo</groupId>
    <artifactId>simple-executor-limit</artifactId>
    <version>1.0.0</version>
    <properties>
        <maven.compiler.release>17</maven.compiler.release>
    </properties>

    <dependencies>
        <dependency>
            <groupId>org.springframework</groupId>
            <artifactId>spring-core</artifactId>
            <version>6.2.10</version>
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
                <version>3.5.1</version>
                <configuration>
                    <mainClass>demo.LimitDemo</mainClass>
                </configuration>
            </plugin>
        </plugins>
    </build>
</project>
```

**File `src/main/java/demo/LimitDemo.java`:**

```java
package demo;

import java.util.concurrent.CountDownLatch;
import java.util.concurrent.TimeUnit;
import org.springframework.core.task.SimpleAsyncTaskExecutor;
import org.springframework.core.task.TaskRejectedException;

public final class LimitDemo {
    public static void main(String[] args) throws Exception {
        CountDownLatch firstStarted = new CountDownLatch(1);
        CountDownLatch releaseFirst = new CountDownLatch(1);
        CountDownLatch firstFinished = new CountDownLatch(1);

        try (SimpleAsyncTaskExecutor executor =
                     new SimpleAsyncTaskExecutor("limited-")) {
            executor.setConcurrencyLimit(1);
            executor.setRejectTasksWhenLimitReached(true);

            executor.execute(() -> {
                firstStarted.countDown();
                try {
                    releaseFirst.await();
                } catch (InterruptedException ex) {
                    Thread.currentThread().interrupt();
                } finally {
                    firstFinished.countDown();
                }
            });

            try {
                if (!firstStarted.await(5, TimeUnit.SECONDS)) {
                    throw new IllegalStateException("First task did not start");
                }

                System.out.println("limit=" + executor.getConcurrencyLimit());
                System.out.println("throttle=" + executor.isThrottleActive());

                boolean rejected = false;
                try {
                    executor.execute(() ->
                            System.out.println("UNEXPECTED SECOND TASK"));
                } catch (TaskRejectedException ex) {
                    rejected = true;
                }
                System.out.println("secondRejected=" + rejected);
            } finally {
                // Always release the worker, even if the check fails.
                releaseFirst.countDown();
                if (!firstFinished.await(5, TimeUnit.SECONDS)) {
                    throw new IllegalStateException("First task did not finish");
                }
            }

            System.out.println("firstFinished=true");
        }
    }
}
```

In the directory containing `pom.xml`, using JDK 17+ and Maven:

```bash
mvn -q compile exec:java
```

**Standard output from the program:**

```text
limit=1
throttle=true
secondRejected=true
firstFinished=true
```

Why is the result deterministic?

1. Before attempting to submit the second task, the main thread waits on `firstStarted`: the first task has started and is waiting on `releaseFirst`.
2. `concurrencyLimit=1` leaves no free slots. The `setRejectTasksWhenLimitReached(true)` policy causes the second `execute` call to throw `TaskRejectedException` right at the submission site.
3. The catch clause sets `rejected=true`, so `UNEXPECTED SECOND TASK` is not printed.
4. The `finally` block releases the first task and waits for `firstFinished`, preventing the example from hanging a worker.

This is a **standalone** example that does not require running a Spring Boot application context; `SimpleAsyncTaskExecutor` can be instantiated directly once Spring libraries are on the classpath. The output illustrates **reject mode**; if you remove the line enabling rejection, the second `execute` call on main will **block** while the first task is still waiting for main to open the latch. Because main never reaches `finally` to open the latch, the example will deadlock. Therefore, **do not delete the reject line and run the example as-is when trying to test blocking**.

### If You Need to Test Blocking Behavior Safely

Use **a separate thread as the submitter**, and let the coordinating thread (which is not blocked) be responsible for releasing the latch of the task holding the slot:

```text
main:       submit task A -> wait for A to start -> start submitter -> then release A's latch
task A:     start -> wait on latch -> complete, release slot
submitter:  execute(task B) -> blocked while A holds slot -> unblocked -> returns
task B:     accepted, runs on a new thread
```

This avoids the circular wait “main is blocked submitting B; A waits on main to release the latch”. Never use a `sleep(100)` as proof of a race condition; synchronize with latches/barriers and verify actual execution states.

## 6. Explicitly Configuring the Executor for `@Async` in a Spring Application

To ensure an `@Async` method actually uses the limited executor, configure a named bean and specify that name in the annotation. The snippet below is **integration code inside a Spring application with async configuration**, not a standalone `javac` program like section 5.

**Configuration for Spring Framework 6.2.10+:**

```java
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.scheduling.annotation.EnableAsync;
import org.springframework.core.task.SimpleAsyncTaskExecutor;

@Configuration(proxyBeanMethods = false)
@EnableAsync
public class AsyncConfig {
    @Bean("limitedIoExecutor")
    public SimpleAsyncTaskExecutor limitedIoExecutor() {
        SimpleAsyncTaskExecutor executor =
                new SimpleAsyncTaskExecutor("limited-io-");

        executor.setConcurrencyLimit(8);
        executor.setRejectTasksWhenLimitReached(true);
        return executor;
    }
}
```

**Service using this executor:**

```java
import java.util.concurrent.CompletableFuture;
import org.springframework.scheduling.annotation.Async;
import org.springframework.stereotype.Service;

@Service
public class ReportService {
    @Async("limitedIoExecutor")
    public CompletableFuture<String> generate(String reportId) {
        // Real work here must have timeouts, logging, and error handling.
        String result = "Generated: " + reportId;
        return CompletableFuture.completedFuture(result);
    }
}
```

**How it works:**

- Another bean injects `ReportService` and calls `generate(...)`. The Spring proxy intercepts the call and dispatches the method body to the executor named `limitedIoExecutor`.
- If fewer than 8 tasks are running, Spring can submit the new task. Once 8 are active, the submission is rejected according to configuration and the caller must handle this failure. **A failure at the submit step** is different from **an error occurring inside the task** after it has been accepted.
- `@Async` returning `CompletableFuture<String>` lets the caller handle the result or error asynchronously. If using `@Async void`, exceptions in the body have no future to return to the caller and require an `AsyncUncaughtExceptionHandler` and proper observability design.
- You must invoke the service through the **Spring-managed proxy**. Self-invoking `this.generate(...)` within the same bean normally bypasses `@Async` interception in default proxy mode.
- If the method calls a real service, you must set timeouts on the HTTP/DB client itself. An executor limit of 8 does not impose a timeout on tasks.

Do not assume every Spring Boot application uses `SimpleAsyncTaskExecutor`. For instance, Spring Boot 3.5 may auto-configure `ThreadPoolTaskExecutor` when using platform threads, or `SimpleAsyncTaskExecutor` when virtual threads are enabled on JDK 21+ and the corresponding auto-configuration conditions are met. Explicit configuration with `@Async("limitedIoExecutor")` avoids guessing the default executor and ensures this task's limit is enforced on the intended bean.

## 7. Choose the Limit Based on Capacity, Not Maximum Requests

A number like 4, 8, or 16 cannot be right for every application. Set the limit based on the **scarcest resource** that tasks consume and validate empirically.

For example: a report-export service calls an external API, and each application instance is only allowed to send at most 6 active requests. A concurrency limit of 6 can cap the number of tasks running on this executor; however, if each task concurrently opens 3 connections or makes multiple calls, the actual request count no longer equals the task count. In that case, you need limits at the appropriate call/resource level.

Questions before picking a limit:

1. **Do tasks mostly wait on I/O or process CPU?** Too many threads for CPU-bound tasks contend for CPU; I/O-waiting tasks can allow higher concurrency but are still constrained by connection limits.
2. **How many resources does one task consume?** DB connections, HTTP sockets, heap, downstream requests, file descriptors, paid-service quotas.
3. **How many instances are running?** If there are 4 pods, each set to 8, there can be **up to 32 tasks running across four independent executors**; that limit does not create a system-wide cap.
4. **Where will the caller be when slots are full?** If the caller is an HTTP request thread, blocking can raise latency; rejection needs a clear HTTP/retry response.
5. **How long does it take for a slot to free up?** Hung tasks, overly generous timeouts, or unbounded retries can keep all slots occupied.
6. **Is a queue or durable processing needed?** If work must be queued, survive restarts, and be retried, consider an out-of-JVM queue/job system.

You can monitor active task count, submit wait time, rejection rate, p95/p99 latency, CPU, heap, HTTP connection pools, and downstream error rates. `getConcurrencyLimit()` and `isThrottleActive()` only report **configuration**, and do not replace metrics on actual saturation. You can use a `TaskDecorator` or external instrumentation to measure active tasks, provided the counter is always decremented in `finally`.

## 8. Virtual Threads and Concurrency Limits

Since Spring Framework 6.1 on **Java 21+**, `SimpleAsyncTaskExecutor` offers:

```java
SimpleAsyncTaskExecutor executor = new SimpleAsyncTaskExecutor("virtual-");
executor.setVirtualThreads(true);
executor.setConcurrencyLimit(100);
```

This is a snippet for JDK 21+ and will not run on JDK 17 with virtual threads enabled. When using virtual threads, each task still gets a new virtual thread; Spring does not turn this executor into a pool. Virtual threads reduce the cost of keeping many jobs waiting on I/O, yet **they do not infinitely expand the capacity of the database, downstream services, CPU, or memory**.

The limit of 100 in the example remains a cap on tasks executing through **this executor**, regardless of whether virtual or platform threads are used. Avoid two false conclusions:

- “Virtual threads are cheap so setting limit = -1 is always safe.” False if tasks call a quota-limited downstream or place significant memory/CPU load.
- “Having a concurrency limit eliminates the need for timeouts.” False; a hung task can hold a slot indefinitely.

In Spring Boot, `spring.threads.virtual.enabled=true` depends on the Spring Boot version and requires JDK 21+; verify the actual executor via configuration/beans before applying limits. Traditional pool configuration properties may have no effect on `SimpleAsyncTaskExecutor` when the application uses virtual threads.

## 9. Comparing with `ThreadPoolTaskExecutor` to Pick the Right Tool

| Criterion | `SimpleAsyncTaskExecutor` | `ThreadPoolTaskExecutor` |
| --- | --- | --- |
| Thread usage | New thread per task; no reuse | Worker threads in a pool, reusable |
| Concurrency | `setConcurrencyLimit(n)` | `corePoolSize`, `maxPoolSize`, and execution policy |
| When full | Blocks submitter by default; since 6.2.6 can reject immediately | Typically queues up to `queueCapacity`; rejects when pool/queue reach limits |
| Task queue | No separately managed queue | Has a configurable queue |
| Suitability | Low or controlled task volume; simple; fits virtual threads when properly limited | Substantial task volume needing worker reuse and queue tuning |
| Lifecycle | Has `close()` and task-termination timeout; lacks pool pause/resume | Richer lifecycle management and pool monitoring |

When choosing `ThreadPoolTaskExecutor`, do not assume `maxPoolSize` is always the number of running threads as soon as load rises. With a positive queue capacity, a thread pool can prioritize queuing tasks before scaling from core up to max. Always evaluate **core, max, queue, and rejection policy** as a single set.

Do not swap `SimpleAsyncTaskExecutor` for `ThreadPoolTaskExecutor` merely because a limit looks low; choose based on management needs, task frequency, caller behavior under overload, and thread-creation cost. Still, for production systems requiring an explicit queue, stable worker count, metrics, and coordinated shutdown, a thread pool is usually more appropriate.

## 10. Common Mistakes and How to Fix Them

### Mistake 1: Setting a limit while assuming there is a queue

**Symptom:** requests slow down when the limit is reached despite “just calling `@Async`”. **Cause:** `SimpleAsyncTaskExecutor` blocks the caller during submission by default rather than accepting the task and placing it into a queue.

**Fix:** accept backpressure and measure wait time if appropriate; or on Spring 6.2.6+ enable rejection and handle overload; or switch to a pool with a queue if asynchronous waiting in a queue is required.

### Mistake 2: Using `setConcurrencyLimit(0)` to run one task at a time

**Wrong:** 0 corresponds to `NO_CONCURRENCY`, not “one task”. **Fix:** use 1. Under the blocking policy, 0 can make submitters wait with no slots; under reject mode, submissions will be rejected.

### Mistake 3: Enabling `setRejectTasksWhenLimitReached(true)` without handling rejection

**Symptom:** task-submission errors surface directly on the request/job path, or data is dropped assuming the task “went into a queue”. **Fix:** catch errors at the appropriate boundary and decide whether to return HTTP 429/503, perform bounded idempotent retries, or persist work to a durable system. Pick the HTTP status based on root cause and API contract rather than applying one default code everywhere.

### Mistake 4: Blocking the caller on an event loop or scarce worker

**Symptom:** even though the task is offloaded asynchronously, other endpoints slow down because submitting threads are held. **Fix:** avoid blocking submissions on an event loop; consider rejection, a dedicated asynchronous queue/worker, or a compatible non-blocking architecture.

### Mistake 5: Limiting at the executor and assuming the whole cluster is protected

**Symptom:** scaling up pods causes calls to the DB/downstream to exceed quota. **Fix:** calculate concurrency across instance count and actual calls per task; if a cluster-wide cap is needed, apply admission control or a shared policy at the appropriate layer.

### Mistake 6: Confusing `setTaskTerminationTimeout` with a task timeout

**Symptom:** hung I/O tasks do not release slots even though shutdown timeout is configured. **Fix:** configure timeouts per dependency and cancellation strategy; shutdown timeout only applies to `close()`. Enabling a positive executor close timeout also requires Spring to track tasks, adding per-task overhead.

### Mistake 7: Using `isThrottleActive()` as a check for whether it is full

**Wrong:** the return value indicates whether throttling is enabled, not how many tasks are running. **Fix:** measure active submissions/running tasks and rejection/wait times using separate instrumentation.

### Mistake 8: Switching between `-1` and a positive limit while the system is live

**Risk:** concurrency counting in the unbounded state can become inconsistent during a runtime transition, as warned by the underlying API. **Fix:** configure the limit from the start, change via tested rollout procedures, and avoid toggling it back and forth arbitrarily.

### Mistake 9: Nesting tasks on a single-slot executor

A task holding the 1/1 slot calls `execute(childTask)` on the same executor under the blocking policy and then waits for the child. Submitting the child cannot pass the throttle while the parent has not finished; the parent cannot finish while waiting on the child. This is a dependency-induced deadlock. **Fix:** avoid blocking nested submissions on the same scarce executor; design acyclic dependencies or use an appropriate execution model.

### Mistake 10: Treating concurrency limits as a reliability guarantee

An executor only coordinates tasks in-process; it does not persist durably, retry automatically, turn business logic into a transaction, or prevent duplicate requests. For tasks that must complete after a restart, use a stateful job/queue and an idempotency strategy.

## 11. How to Test the Configuration in a Real System

To verify the application rather than just reading config, prepare a workload that can actively hold and release tasks:

1. Configure a small limit, such as 2, on **the exact executor bean being called**. Use `@Async("beanName")` to avoid picking the wrong default executor.
2. Run 2 tasks concurrently holding a `CountDownLatch` to guarantee both slots are occupied. Do not rely purely on `Thread.sleep(...)` to reproduce the condition.
3. From a separate submitting thread, submit a third task. With the **block** policy, verify the submitting thread only returns after a slot frees up. With **reject**, verify `TaskRejectedException` is thrown and the third task does not run.
4. Release one task and verify remaining tasks proceed according to the expected policy. Set test timeouts so the test does not hang if misconfigured.
5. Measure peak concurrent tasks and created threads across multiple rounds; with `SimpleAsyncTaskExecutor`, threads may be recreated between rounds, unlike a pool.
6. Test when tasks throw exceptions, time out, shut down, and when the app runs across multiple instances. Verify rejected requests/retries are handled according to the business contract.
7. In real deployment, monitor caller p95/p99 latency, rejection counts, submission wait time, DB/HTTP connection usage, and recovery when downstream is slow.

The test in section 5 verifies one deterministic rejection case. It **does not prove** that the limit will achieve target throughput or avoid bottlenecks in a multi-instance system. Choosing a limit requires measurements under realistic load and topology.

## 12. Takeaways and References

- **Unconfigured:** `SimpleAsyncTaskExecutor` defaults to **unbounded** (`-1`), with each task getting its own thread.
- **Positive limit:** `setConcurrencyLimit(n)` caps concurrently running tasks on that executor.
- **When full:** defaults to **blocking the caller**; from Spring **6.2.6**, you can enable **immediate rejection** with `setRejectTasksWhenLimitReached(true)`.
- **No pool/queue:** the limit does not create a `ThreadPoolTaskExecutor`.
- **Virtual threads:** reduce thread cost in some workloads, but do not remove resource constraints or timeout requirements.
- **In Spring:** identify the exact executor bean, error policy, instance count, caller latency, and overload handling.

Official documentation:

1. [Spring Framework 6.2.10 Javadoc – SimpleAsyncTaskExecutor](https://docs.spring.io/spring-framework/docs/6.2.10/javadoc-api/org/springframework/core/task/SimpleAsyncTaskExecutor.html) — thread creation, limits, block/reject, virtual threads, shutdown behavior.
2. [Spring Framework 6.2.14 Javadoc – ConcurrencyThrottleSupport](https://docs.spring.io/spring-framework/docs/6.2.14/javadoc-api/org/springframework/util/ConcurrencyThrottleSupport.html) — defaults and warnings about runtime limit changes.
3. [Spring Framework Reference – Task Execution and Scheduling](https://docs.spring.io/spring-framework/reference/integration/scheduling.html) — `TaskExecutor` model, `@Async`, comparison of implementations.
4. [Spring Boot 3.5 Reference – Task Execution and Scheduling](https://docs.spring.io/spring-boot/3.5/reference/features/task-execution-and-scheduling.html) — executor auto-configuration and virtual threads.

A concurrency limit is **a mechanism to control the number of actively executing tasks**, not a queue and not a speed guarantee. When choosing `SimpleAsyncTaskExecutor`, the most important design question is: **once all slots are in use, should the submitting thread wait or should the system reject immediately?**

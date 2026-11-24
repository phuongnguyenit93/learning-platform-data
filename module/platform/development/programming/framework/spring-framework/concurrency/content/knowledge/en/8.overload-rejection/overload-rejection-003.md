# AbortPolicy Throws Errors at the Task Submission Site

## Objectives and Scope

When a Spring application offloads work to a thread pool, there are two separate questions: **has the pool accepted the work?** and **did the work complete successfully?** The `ThreadPoolExecutor.AbortPolicy` policy addresses the first question: if the pool cannot accept a new task, it **throws an exception immediately at the submission site**. This signals overload or that the executor has closed, and must be handled right at the caller.

After this lesson, you will be able to:

- Explain the conditions under which `ThreadPoolExecutor` rejects a task: **pool/queue saturation** or **shutdown**.
- Distinguish JDK's `RejectedExecutionException` from `TaskRejectedException` when going through Spring's `ThreadPoolTaskExecutor`.
- Predict the interaction between `corePoolSize`, `maxPoolSize`, `queueCapacity`, and the rejection handler.
- Write Java 17+ and Spring examples with **deterministic rejection via latches**, without relying on lucky `sleep()` timing.
- Distinguish exceptions **right at `execute/submit`** from exceptions occurring **inside the task**; choose appropriate handling for HTTP, queues, and jobs.
- Diagnose rejections, monitor backlogs, and avoid handling patterns that cause data loss or retry storms.

**Scope:** `java.util.concurrent.ThreadPoolExecutor` and `org.springframework.scheduling.concurrent.ThreadPoolTaskExecutor`. JDK examples run on Java 17+, and the Spring example uses **Spring Framework 6.1.3** and Maven. The content describes the standard platform thread pool model and does not apply by default to executors that create a virtual thread per task.

## 1. Understanding the Two Stages: Task Admission and Task Execution

When a caller submits a `Runnable`, the executor must first perform **admission** before scheduling **execution**. A normal return from `execute(...)` only says the task was accepted; **it does not say the task has completed**.

| Stage and outcome | What happens | What does the caller see? |
| --- | --- | --- |
| `execute(task)` accepted | Task runs on a worker or enters the queue | Submission method returns normally |
| `execute(task)` rejected by AbortPolicy | Task **is not accepted** | Throws an unchecked exception directly from the submission call |
| `submit(callable)` accepted | Caller gets a `Future`; task will run later | Can wait via `Future.get()` |
| `submit(callable)` rejected | No valid `Future` | Exception thrown **before `submit` returns** |
| Task accepted, then `run()/call()` throws | Error happens while running the task | Observed via `Future.get()`, callback, or log depending on API |
| Executor has shut down | Refuses new tasks even if queue is empty | AbortPolicy also throws an exception at the submission site |

`AbortPolicy` only rejects the **new task**. It does not automatically remove tasks already in the queue, does not stop running tasks, and does not roll back side effects from previously accepted tasks.

### Why Must Errors Be Caught at the Caller?

The rejection mechanism runs on **the thread calling `execute/submit`**, such as a Spring MVC request thread or a scheduler thread. If the task is not accepted, **the Runnable body has not executed**, so a `try/catch` placed *inside* that Runnable cannot catch a rejection of the submission call itself.

~~~java
// Fragment in a service with an executor field of type TaskExecutor.
try {
    executor.execute(() -> performWork());
    // Submitted successfully; does not yet mean performWork() finished.
} catch (org.springframework.core.task.TaskRejectedException ex) {
    // Pool did not accept the task: handle immediately in the caller.
    recordAdmissionFailure(ex);
}
~~~

This is an **illustrative snippet**, not a standalone Java class; it assumes the application already has `executor`, `performWork()`, and `recordAdmissionFailure(...)`. If uncaught at an appropriate boundary, the exception propagates up to the caller/framework.

## 2. When Does ThreadPoolExecutor Invoke RejectedExecutionHandler?

### 2.1. The Admission Flow

With a standard `ThreadPoolExecutor`, `execute(Runnable)` follows these general steps:

1. While the worker count is below `corePoolSize`, try to create a new worker to run the task.
2. Once enough core workers exist, try to insert the task into the **work queue**.
3. If the queue **cannot accept** the task, try to create workers beyond core, up to `maximumPoolSize`.
4. If worker creation also fails because the limit has been reached, hand the task to `RejectedExecutionHandler`.
5. If the executor has `shutdown()`, new tasks are also rejected; the JDK code includes state rechecks to handle races with shutdown.

~~~text
                  new task
                     |
           executor accepting work?
              /             \
             no             yes
              |               |
          REJECTION       workers < core?
                           /       \
                         yes        no
                          |          |
                    create worker  queue accepts?
                                     /     \
                                   yes      no
                                    |        |
                                 enqueue   workers < max?
                                             /     \
                                           yes      no
                                            |        |
                                      create worker REJECTION
~~~

This diagram is a learning model; real code has multiple rechecks due to concurrency. Do not use a `getQueue().size()` snapshot to promise that the next task will be accepted.

### 2.2. Example of a Bounded Pool

Suppose `corePoolSize=1`, `maxPoolSize=2`, and `queueCapacity=1`, while earlier tasks remain busy/waiting throughout submission:

| Task | Outcome while no prior task finishes |
| --- | --- |
| A | Creates the first core worker |
| B | Enters the single queue slot |
| C | Queue is full, creates the second worker |
| D | Queue full and workers at max=2; rejected |

If A or C completes before D arrives, D **can be accepted**. That is why the hands-on exercise holds A with a `CountDownLatch` instead of hoping tasks run slowly enough.

### 2.3. How Do Queue and maximumPoolSize Affect Rejection?

By default, `ThreadPoolTaskExecutor` has `corePoolSize=1`, `maxPoolSize=Integer.MAX_VALUE`, and `queueCapacity=Integer.MAX_VALUE`. When the queue is huge, tasks exceeding core capacity usually get **queued**; the pool has no reason to create workers above core until the queue stops accepting more. As a result, the application can become severely slow or consume heavy resources before ever seeing a rejection due to a **full queue**.

To set deliberate bounds, configure **finite core/max/queue** after understanding task arrival rate, execution time, CPU limits, database connections, and acceptable latency. With `queueCapacity=0`, Spring uses a `SynchronousQueue`: a task must be handed directly to a worker with no queuing slot. With `queueCapacity>0`, Spring uses a queue of that capacity.

## 3. AbortPolicy: The Default Fail-Fast Policy

`java.util.concurrent.RejectedExecutionHandler` is the contract for handling unaccepted tasks. `ThreadPoolExecutor.AbortPolicy` is the default handler of `ThreadPoolExecutor`; it **always throws `RejectedExecutionException`** when `rejectedExecution(...)` is called.

~~~java
new ThreadPoolExecutor.AbortPolicy()
~~~

This is merely a **handler instantiation expression**, not a standalone program. `RejectedExecutionException` extends `RuntimeException`, so the compiler does not force callers to declare `throws`, yet an explicit handling policy is still required.

For example, when task C is rejected:

~~~text
Caller thread                   Thread pool
     |                              |
     | execute(task C)              | worker is running A
     | ---------------------------> | queue holds B
     |                              |
     | <--- RejectedExecutionException
     |
     +-- catch in caller
          C was not accepted
          A and B are not automatically cancelled
~~~

**"Abort" here does not mean destroying the entire pool**: it throws an error to the call submitting **the rejected task**. Previously accepted tasks continue running under their own lifecycle unless another shutdown/cancellation action occurs.

There are two main groups of causes:

- **Saturation:** the queue accepts no more and workers have reached their limit; new tasks are rejected.
- **Executor stopped accepting work:** `shutdown()`, Spring context closure, or executor lifecycle prevents new tasks from being accepted, even if the queue still has room.

You cannot conclude that every `RejectedExecutionException` means `maxPoolSize` must be raised: first verify whether the executor is shutting down or saturated, whether the queue is growing, and whether downstream is the real bottleneck.

## 4. Standalone Java 17+ Example: Rejection Happens Right at execute()

The following example uses one worker and one queue slot. One `CountDownLatch` confirms task A has started, and the other latch holds A waiting. Then task B occupies the queue. Consequently, task C is guaranteed to be rejected at submission time.

Save as `AbortPolicyDemo.java`:

~~~java
import java.util.concurrent.ArrayBlockingQueue;
import java.util.concurrent.CountDownLatch;
import java.util.concurrent.RejectedExecutionException;
import java.util.concurrent.ThreadPoolExecutor;
import java.util.concurrent.TimeUnit;

public final class AbortPolicyDemo {
    public static void main(String[] args) throws InterruptedException {
        CountDownLatch started = new CountDownLatch(1);
        CountDownLatch release = new CountDownLatch(1);

        ThreadPoolExecutor pool = new ThreadPoolExecutor(
                1, 1,
                0L, TimeUnit.SECONDS,
                new ArrayBlockingQueue<>(1),
                new ThreadPoolExecutor.AbortPolicy()
        );

        try {
            pool.execute(() -> {
                started.countDown();
                try {
                    release.await();
                } catch (InterruptedException ex) {
                    Thread.currentThread().interrupt();
                }
            });

            started.await(); // A is holding the sole worker

            pool.execute(() -> { }); // B enters the queue

            try {
                pool.execute(() -> { }); // C is rejected
                System.out.println("unexpected-accepted");
            } catch (RejectedExecutionException ex) {
                System.out.println("jdk-rejected="
                        + ex.getClass().getSimpleName());
            }

            System.out.println("queue=" + pool.getQueue().size());
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

Run with JDK 17+:

~~~bash
javac AbortPolicyDemo.java
java AbortPolicyDemo
~~~

Deterministic output:

~~~text
jdk-rejected=RejectedExecutionException
queue=1
~~~

**Why is the output deterministic?**

1. `started.await()` guarantees A has started and signaled readiness.
2. A is waiting on `release`, so the single worker cannot process a new task yet.
3. B takes the single queue slot.
4. C cannot enter the queue and cannot spawn an extra worker (core=max=1), causing `AbortPolicy` to throw an exception directly on the **main thread**.
5. C does not drop B; when main prints `queue=1`, B is still waiting.
6. `finally` opens the latch, shuts down the pool, and awaits termination so no stuck worker is left behind.

If you remove the latches and just make A call `Thread.sleep(100)`, the outcome depends on CPU scheduling and machine speed, making it unsuitable as a reliable test.

## 5. In Spring, TaskRejectedException Is the Error to Catch

`ThreadPoolTaskExecutor` manages an internal `ThreadPoolExecutor` and implements Spring's `TaskExecutor`. The default handler is still **AbortPolicy**. Spring translates task-admission refusal under its contract into `org.springframework.core.task.TaskRejectedException`. `TaskRejectedException` is a subclass of `RejectedExecutionException`.

| Call | When rejected with AbortPolicy |
| --- | --- |
| `ThreadPoolExecutor.execute(...)` from JDK | `RejectedExecutionException` |
| `ThreadPoolTaskExecutor.execute(...)` from Spring | `TaskRejectedException` |
| `ThreadPoolTaskExecutor.submit(...)` | `TaskRejectedException` before returning a `Future` |
| `AsyncTaskExecutor.submitCompletable(...)` (Spring 6.0+) | `TaskRejectedException` before returning a `CompletableFuture` |

With Spring APIs, catch `TaskRejectedException` because it expresses the Spring contract and helps code distinguish Spring rejections from errors thrown at another layer. Catching the parent `RejectedExecutionException` still works, though it can obscure the error source.

### 5.1. Standalone Spring Maven Project

To verify Spring's own exception directly, create a small project with **Java 17+** and **Spring Framework 6.1.3**. The program runs via `main`, without starting a Spring Boot server and without `@EnableAsync` since it calls `executor.execute(...)` directly.

Structure:

~~~text
spring-abort-demo/
├── pom.xml
└── src/
    └── main/
        └── java/
            └── demo/
                └── SpringAbortDemo.java
~~~

File `pom.xml`:

~~~xml
<project xmlns="http://maven.apache.org/POM/4.0.0"
         xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
         xsi:schemaLocation="http://maven.apache.org/POM/4.0.0 https://maven.apache.org/xsd/maven-4.0.0.xsd">
    <modelVersion>4.0.0</modelVersion>
    <groupId>demo</groupId>
    <artifactId>spring-abort-demo</artifactId>
    <version>1.0.0</version>

    <properties>
        <maven.compiler.release>17</maven.compiler.release>
        <project.build.sourceEncoding>UTF-8</project.build.sourceEncoding>
    </properties>

    <dependencies>
        <dependency>
            <groupId>org.springframework</groupId>
            <artifactId>spring-context</artifactId>
            <version>6.1.3</version>
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
                <version>3.3.0</version>
                <configuration>
                    <mainClass>demo.SpringAbortDemo</mainClass>
                </configuration>
            </plugin>
        </plugins>
    </build>
</project>
~~~

File `src/main/java/demo/SpringAbortDemo.java`:

~~~java
package demo;

import java.util.concurrent.CountDownLatch;
import java.util.concurrent.ThreadPoolExecutor;
import java.util.concurrent.TimeUnit;

import org.springframework.core.task.TaskRejectedException;
import org.springframework.scheduling.concurrent.ThreadPoolTaskExecutor;

public final class SpringAbortDemo {
    public static void main(String[] args) throws InterruptedException {
        ThreadPoolTaskExecutor pool = new ThreadPoolTaskExecutor();
        pool.setCorePoolSize(1);
        pool.setMaxPoolSize(1);
        pool.setQueueCapacity(1);
        pool.setThreadNamePrefix("abort-demo-");
        pool.setRejectedExecutionHandler(
                new ThreadPoolExecutor.AbortPolicy());
        pool.initialize();

        CountDownLatch started = new CountDownLatch(1);
        CountDownLatch release = new CountDownLatch(1);

        try {
            pool.execute(() -> {
                started.countDown();
                try {
                    release.await();
                } catch (InterruptedException ex) {
                    Thread.currentThread().interrupt();
                }
            });

            started.await(); // A is holding the worker
            pool.execute(() -> { }); // B is in the queue

            try {
                pool.execute(() -> { }); // C is rejected
                System.out.println("unexpected-accepted");
            } catch (TaskRejectedException ex) {
                System.out.println("spring-rejected="
                        + ex.getClass().getSimpleName());
            }

            System.out.println("queue=" + pool.getQueueSize());
        } finally {
            release.countDown();
            ThreadPoolExecutor nativePool =
                    pool.getThreadPoolExecutor();
            pool.shutdown();
            if (!nativePool.awaitTermination(5, TimeUnit.SECONDS)) {
                nativePool.shutdownNow();
            }
        }
    }
}
~~~

Run inside the `spring-abort-demo` directory:

~~~bash
mvn -q compile exec:java
~~~

Output printed by the Java program, excluding any Maven logs:

~~~text
spring-rejected=TaskRejectedException
queue=1
~~~

Spring hits the exact same busy-worker and full-queue condition, yet reports `TaskRejectedException` on the `ThreadPoolTaskExecutor.execute(...)` call. We print the **exception class name** instead of the full `getMessage()`, because message wording can vary across versions. Printing `queue=1` confirms task B remains in the queue when C is rejected.

`setRejectedExecutionHandler(new AbortPolicy())` here only makes the policy explicit; it is already the default if you do not change the handler. `initialize()` is needed because the pool was created manually. In a Spring application, use a **singleton bean** and let the container manage its lifecycle.

### 5.2. Configuring as a Spring Bean

In a Spring application with component scanning enabled, a shared executor can be configured as follows (this is an **integration fragment**, not a standalone project):

~~~java
import java.util.concurrent.ThreadPoolExecutor;

import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.scheduling.concurrent.ThreadPoolTaskExecutor;

@Configuration
public class BoundedPoolConfig {
    @Bean("boundedExecutor")
    public ThreadPoolTaskExecutor boundedExecutor() {
        ThreadPoolTaskExecutor pool = new ThreadPoolTaskExecutor();
        pool.setCorePoolSize(4);
        pool.setMaxPoolSize(8);
        pool.setQueueCapacity(100);
        pool.setThreadNamePrefix("bounded-");
        pool.setRejectedExecutionHandler(
                new ThreadPoolExecutor.AbortPolicy());
        return pool;
    }
}
~~~

The numbers `4/8/100` are examples of finite bounds, **not an optimal default configuration**. When using `@Async("boundedExecutor")`, Spring requires async method processing (e.g., `@EnableAsync`) and calls must go through the proxy; calling a method on the same object can bypass the proxy. When the executor cannot accept a task at the time the proxy submits it, rejection can surface directly from **the caller's method invocation**, so the calling layer needs a handling strategy.

## 6. Submission Rejection and Task Execution Failure Are Two Different Paths

`ThreadPoolTaskExecutor.submit(...)` returns a `Future` only **after the task has been accepted**. If AbortPolicy rejects, `submit` throws `TaskRejectedException` **immediately at invocation time**. After the task is accepted, errors thrown by `Callable.call()` are observed via `Future.get()`.

~~~java
// Fragment in a service with asyncExecutor of type AsyncTaskExecutor
// and methods reportSubmissionFailure, reportTaskFailure.
Future<Integer> future;
try {
    future = asyncExecutor.submit(() -> calculate());
} catch (TaskRejectedException ex) {
    reportSubmissionFailure(ex);
    return;
}

try {
    Integer result = future.get();
    System.out.println(result);
} catch (ExecutionException ex) {
    reportTaskFailure(ex.getCause());
} catch (InterruptedException ex) {
    Thread.currentThread().interrupt();
}
~~~

This is an **illustrative snippet inside a `void` method**; it requires importing `Future`, `ExecutionException`, `InterruptedException`, `TaskRejectedException` and having the service's fields/methods. `future.get()` can block the caller thread; do not call it indiscriminately from a worker depending on the same small pool, as that can cause starvation/deadlock. Errors thrown inside the task **do not jump back to the `catch` at the `submit` site**.

Since Spring 6.0+, `AsyncTaskExecutor.submitCompletable(...)` returns a `CompletableFuture`. Stages such as `exceptionally(...)` or `handle(...)` process **the returned future**; if submission is rejected before returning a future, those callbacks **do not exist yet**. Therefore, you must still wrap the `submitCompletable` call with `try/catch(TaskRejectedException)`, and then attach callbacks for execution errors.

### When Rejected, Does the Task "Disappear"?

With AbortPolicy, a rejected task **is not in the queue** and is not executed. If the application swallows the exception, that causes **business-level work loss** because the code ignored the error. If the work must be processed reliably, you need a submission protocol with durable persistence (such as a durable queue or transactional outbox), explicit acknowledgment, and a valid retry mechanism. An in-memory executor does not replace a guaranteed-delivery system.

Do not report HTTP "accepted for processing" when executor submission failed, unless another durable component has genuinely recorded the work.

## 7. Handling Overload in the Right Place

Depending on the API's responsibility, an application can:

- **Fail fast** with a clear response to the caller. HTTP 503 usually fits temporary service capacity exhaustion; HTTP 429 usually fits per-client rate limits. Do not blindly map every `TaskRejectedException` to a single fixed status code without considering the API contract.
- **Bounded retries** with exponential backoff/jitter when the task is safe to retry and inputs remain valid. Avoid immediate continuous retries inside the catch block, which can trigger a retry storm.
- **Throttle ingress** with semaphores, rate limiters, admission control, or upstream backpressure before queues balloon.
- **Offload work to a durable queue** if task loss is unacceptable and the caller can wait for later processing; design idempotency and enqueue confirmation carefully.
- **Fix lifecycle ordering** if the pool has shut down, such as a task scheduler still submitting work while the Spring context is closing.

Simply raising `maxPoolSize` does not always fix overload: tasks may be waiting on DB connections or an external API, so adding workers just makes more tasks contend for the same bottlenecked resource.

### Comparing Rejection Policies

| Policy | Behavior on rejection | Trade-offs |
| --- | --- | --- |
| **AbortPolicy** | Throws `RejectedExecutionException` immediately at the caller | Explicit, easy fail-fast; caller must have a handling plan |
| `CallerRunsPolicy` | Runs the task on the **caller thread** if executor is not shut down | Creates indirect backpressure, but can block HTTP/event-loop threads; can drop tasks on shutdown |
| `DiscardPolicy` | Drops the task without throwing an error | Risks silent task loss |
| `DiscardOldestPolicy` | Evicts the oldest task in the queue and retries admitting the new task | Risks losing tasks and breaking ordering expectations; especially dangerous with Futures |

Do not replace `AbortPolicy` with `DiscardPolicy` just to "eliminate exceptions": that turns an observable incident into hard-to-detect work loss. With `CallerRunsPolicy`, evaluate the cost of running the task on the caller and how shutdown is handled.

If you use a custom `RejectedExecutionHandler` to increment a counter, **still throw a rejection exception** when you want to preserve fail-fast semantics; a handler that only logs and returns normally can mislead callers into thinking the task was accepted.

## 8. Monitoring and Testing

### 8.1. Metrics to Track

- **Rejected task rate:** record in the `TaskRejectedException` catch block or an instrumented handler; distinguish overload rejections from shutdown rejections when context is available.
- **Active workers / pool size:** `getActiveCount()` and `getPoolSize()` are only snapshots.
- **Queue depth / wait duration:** `getQueueSize()` and queue wait times; a steadily growing queue signals a backlog.
- **Task duration / throughput / p95-p99 latency:** reveals bottlenecks from slow tasks or traffic exceeding processing capacity.
- **Downstream health:** DB connection pool, sockets, API quotas, CPU, memory, and GC.

Do not write logic like "saw queue is 0 so submit is guaranteed to succeed," because other threads can change state right after the read. The `execute/submit` call itself and the handler are the mechanism that decides admission.

### 8.2. Test Cases to Include

1. **Saturation:** core=max=1, queue=1; use a latch to hold the first task, enqueue the second task, and verify the third task is rejected immediately at submission.
2. **Normal acceptance:** queue not full, `execute` succeeds; track task completion separately.
3. **Shutdown:** call `shutdown()` and submit a new task; verify immediate rejection even with an empty queue.
4. **Task failure:** submit an accepted `Callable` that throws an exception; verify `Future.get()` throws `ExecutionException`, not confused with rejection.
5. **Spring path:** verify catching `TaskRejectedException` at the `ThreadPoolTaskExecutor.execute` call site rather than only watching worker logs.
6. **Recovery:** once overload subsides, newly submitted tasks can be accepted again provided the pool has not shut down; do not retry unboundedly while conditions remain unchanged.

Use latches/barriers and explicit bounds in tests instead of `Thread.sleep(100)`; depending on CPU speed can make tests flake occasionally on CI.

## 9. Common Errors and How to Fix Them

1. **Catching exceptions inside the rejected task.** Ineffective because the task never runs; catch around `execute/submit` at the caller.
2. **Assuming submit always returns a Future even under overload.** False: rejection can throw before any Future is returned.
3. **Handling only `CompletableFuture.exceptionally`.** Fails to catch a `submitCompletable` call that throws synchronously.
4. **Thinking AbortPolicy stops the entire executor.** It rejects the current task; already-accepted tasks continue under their lifecycle.
5. **Configuring a nearly unbounded queue and expecting `maxPoolSize` to scale workers quickly.** Pools prefer queuing once core is reached, so max may never engage as expected.
6. **Scaling the pool infinitely to avoid rejection.** Can push limits onto the DB, memory, or network; throttle load and measure real capacity instead.
7. **Swallowing TaskRejectedException and returning "accepted."** Callers lose visibility that the task was never processed.
8. **Switching to DiscardPolicy to get rid of errors.** Tasks are silently lost; use only when the business genuinely permits dropping tasks.
9. **Retrying immediately in an unbounded loop.** Can cause overload to self-amplify.
10. **Conflating shutdown rejections with saturation.** Check lifecycle state and context at the moment of the incident.

## 10. Self-Check Questions

**Question 1.** A pool with `core=1,max=1,queue=1` is running A and queuing B. What happens to a newly submitted task C?  
**Answer:** C cannot enter the queue and cannot create another worker, so AbortPolicy throws an exception right at the submission call while A is still occupying the worker.

**Question 2.** Why can a `try/catch` inside C's body not handle rejection?  
**Answer:** C was not accepted, so C's body never ran.

**Question 3.** Spring `ThreadPoolTaskExecutor` uses AbortPolicy. Which exception should the caller catch?  
**Answer:** `TaskRejectedException` per the Spring contract; this class extends Java's `RejectedExecutionException`.

**Question 4.** `submit` returned a `Future`, then the task threw `IllegalStateException` while running. Is this a rejection?  
**Answer:** No. The executor accepted the task; the execution error is observed via `Future.get()` as an `ExecutionException` wrapping the original cause.

**Question 5.** The executor has shut down, yet the queue is not full. Can AbortPolicy reject a new task?  
**Answer:** Yes. Shutdown is a rejection cause independent of saturation.

**Question 6.** Why can replacing AbortPolicy with DiscardPolicy create business risk?  
**Answer:** New tasks can be dropped without alerting the caller; the system can mistakenly record the work as accepted.

## Official References

- [Java SE 17 — ThreadPoolExecutor](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/concurrent/ThreadPoolExecutor.html): core/queue/max rules, shutdown, rejected tasks, and handlers.
- [Java SE 17 — ThreadPoolExecutor.AbortPolicy](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/concurrent/ThreadPoolExecutor.AbortPolicy.html): default handler that always throws `RejectedExecutionException`.
- [Spring Framework 6.1.3 — ThreadPoolTaskExecutor](https://docs.spring.io/spring-framework/docs/6.1.3/javadoc-api/org/springframework/scheduling/concurrent/ThreadPoolTaskExecutor.html): executor configuration, core/max/queue defaults, Spring-contract exceptions.
- [Spring Framework 6.1.3 — TaskExecutor](https://docs.spring.io/spring-framework/docs/6.1.3/javadoc-api/org/springframework/core/task/TaskExecutor.html): `execute(Runnable)` method and `TaskRejectedException`.
- [Spring Framework 6.1.3 — AsyncTaskExecutor](https://docs.spring.io/spring-framework/docs/6.1.3/javadoc-api/org/springframework/core/task/AsyncTaskExecutor.html): how `submit` and `submitCompletable` return results and report rejection errors.
- [Spring Framework 6.1.3 — TaskRejectedException](https://docs.spring.io/spring-framework/docs/6.1.3/javadoc-api/org/springframework/core/task/TaskRejectedException.html): Spring exception when a task is not accepted.

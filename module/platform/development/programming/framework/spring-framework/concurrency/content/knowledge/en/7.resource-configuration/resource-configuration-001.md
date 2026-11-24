# Separating Executors for Workload Groups with Different Characteristics in Spring Framework

## Objectives

Spring applications often handle multiple workload groups concurrently: short business checks requiring fast responses, CPU calculations, external API calls that may wait a long time, data synchronization, and background report generation. If every group shares one executor/queue, slow tasks can occupy all workers, forcing fast tasks to queue and miss deadlines.

This lesson explains how to **group tasks by resource characteristics and operational goals**, assign a dedicated `ThreadPoolTaskExecutor` to each group, and configure thread counts, queues, rejection policies, timeouts, lifecycle, and metric observability. Through a runnable example with Java 17+ and Spring Framework, you will verify that fast tasks can complete while the slow group remains blocked.

After this lesson, you will be able to:

1. Distinguish between CPU-bound, blocking I/O, latency-sensitive, background/batch, and bottleneck-prone external dependency workloads.
2. Explain why a shared pool creates head-of-line blocking, and why multiple pools help isolate part of the load following the **bulkhead** pattern.
3. Create multiple executor beans, select the right pool with `@Async("beanName")` or `@Qualifier`, and avoid proxy-related mistakes.
4. Choose core/max/queue/rejection parameters aligned with resource limits and measured data.
5. Design error handling, timeouts, downstream limits, logging context, shutdown, and metrics for each group.
6. Understand the limits: separating thread pools does not automatically isolate CPU, database connections, heap, locks, or external service quotas.

**Key takeaway:** An executor is a place that accepts and dispatches tasks; separating executors prevents *Group A's workers and queue* from being occupied by Group B. It does not automatically make blocking work non-blocking or guarantee maximum latency in every scenario.

## 1. How Does a Shared Executor Bottleneck the Fast Group?

Suppose a shared pool has only two workers. Two tasks calling an external API via a blocking HTTP client both hang while waiting for a response. A lightweight computation task is submitted next:

```text
                      SHARED EXECUTOR
                       queue [FAST]
                               |
                 +-------------+--------------+
                 |                            |
            worker 1                       worker 2
            SLOW A                         SLOW B
         waiting on network             waiting on network

          FAST must wait for a free worker even though it only needs 2 ms of CPU.
```

FAST's wait time comes from **queueing delay**, not computation complexity. If the pool and queue are bounded, FAST can even be rejected when both are full. If the queue is very large, the caller may receive a `Future` early while the actual result arrives much later.

Grouping by needs:

```text
FAST tasks -> [fastExecutor queue] -> [fast workers] -> response
SLOW tasks -> [slowExecutor queue] -> [slow workers] -> integration result
BATCH      -> [batchExecutor queue] -> [batch workers] -> background result
```

A slow worker waiting on I/O does not take away a fast worker. High-priority groups can have different queues, time budgets, and overload policies. This is **isolation at the thread execution layer**; the pools still run in the same process/JVM and can contend for CPU, memory, or connections.

Separating pools is worthwhile when groups differ clearly in execution time, waiting behavior, SLA, downstream limits, or overload consequences. Do not mechanically create a separate pool for every method: too many pools increase total threads, heap usage, management overhead, and make resource balancing harder.

## 2. Identifying Workload Groups

| Characteristic | Examples | Approach |
| --- | --- | --- |
| **CPU-bound** | Hashing, heavy computation, in-memory data processing | Limit workers close to the actual CPU budget; measure CPU, p95/p99, and context switching. |
| **Blocking I/O** | JDBC, blocking HTTP clients, slow file reads | May need more workers than CPUs, but must be bounded by connection pool, timeouts, quotas, and memory. |
| **Latency-sensitive** | Mandatory steps to return an API response | Provide dedicated capacity and queue, monitor tail latency, and apply fail-fast/overload policies. |
| **Background/batch** | Report generation, index rebuild, batch sync | Limit throughput separately so it does not crowd the fast pool; durability requires a job store/broker. |
| **Unreliable downstream** | Third-party services with frequent timeouts/429s | Dedicated pool/bulkhead, timeouts, rate limits, circuit breakers, and bounded retries when appropriate. |
| **Scheduled work** | Jobs running every minute/night | `TaskScheduler` decides the schedule; heavy work can be handed off to another executor. |

Labels can overlap. For example, "calling payment" is both potentially slow I/O, latency-sensitive, and quota-limited. Grouping decisions should be based on **actual runtime behavior**, not just package names.

Before grouping, collect: requests/tasks per second, CPU time, I/O wait time, queue wait, p95/p99, timeouts, concurrent task counts, allowed DB/HTTP connections, and container CPU limits. Reasonable thread counts are determined by all of these resources combined.

## 3. What Components Does Spring Provide?

`TaskExecutor` is Spring's abstraction for running `Runnable`, built on top of the JDK's `Executor` concept. `AsyncTaskExecutor` extends it with task submission and `Future` retrieval. `ThreadPoolTaskExecutor` is a convenient bean wrapping `java.util.concurrent.ThreadPoolExecutor`, allowing pool configuration via the Spring API.

`@EnableAsync` enables processing of `@Async` methods; `@Async("fastExecutor")` selects the executor bean named `fastExecutor`, while `@Async("slowExecutor")` selects another bean. When no name is specified, Spring uses its default executor selection mechanism (`AsyncConfigurer` configuration, matching bean, or environment-dependent fallback). **Do not let critical pool selection rely on guessing defaults.**

Call flow:

```text
Caller thread
  -> Spring proxy of WorkService
       -> interceptor reads @Async("slowExecutor")
       -> retrieves slowExecutor bean
       -> submits method invocation
              -> slow worker executes method body
              -> completes Future or reports error

Caller gets Future/CompletableFuture, which may not have a value yet.
```

The default proxy mechanism only intercepts calls **going through the proxy**. If the same bean calls `this.slowMethod()`, the annotation usually has no effect. Additionally, `@Async` does not automatically change bean scope, thread safety, or transaction context.

Two `ThreadPoolTaskExecutor` beans are truly independent only when they own **different** underlying thread pools. If two adapters wrap the same single JDK `Executor`, giving them two bean names does not create real isolation. Check both the delegate instance and metrics.

## 4. Understanding Core, Max, Queue, and Rejection

| Property | Meaning | Notes |
| --- | --- | --- |
| `corePoolSize` | Core worker level that `ThreadPoolExecutor` can maintain. | Not the maximum concurrency limit when max is larger. |
| `maxPoolSize` | Maximum number of workers in the pool. | Does not immediately scale up to max just because a new task arrives if the queue can still accept it. |
| `queueCapacity` | Limit on queued waiting tasks. | A positive queue is typically backed by `LinkedBlockingQueue`; zero uses `SynchronousQueue`. |
| `threadNamePrefix` | Identifies workers in logs/thread dumps. | Does not replace measuring worker counts, queue wait, and rejections. |
| `RejectedExecutionHandler` | Decides what happens when the pool can no longer accept tasks. | Policy can throw an exception, run on the caller, or discard the task. |
| Lifecycle | Shuts down the pool and handles running/queued tasks on context shutdown. | Requires timeout policies and handling of unfinished work. |

With a `ThreadPoolExecutor` using a positive bounded queue, the usual sequence is: create workers up to core; then enqueue tasks while space remains; only when the queue is full, increase workers up to max; finally reject if no capacity remains. Therefore:

```text
core=2, max=20, queue=10000
```

does not mean the pool will quickly create 20 workers when 100 tasks arrive. It may keep two workers and queue most of the tasks. Configuring an overly large queue sometimes masks overload, worsening p99 and memory usage.

With `queueCapacity=0`, there is no standard holding queue for waiting tasks; the pool can create workers up to max and reject early once saturated. There is no default "right" number: choices must be based on SLA, burst load, processing time, total memory, and downstream policies.

## 5. Runnable Example: FAST Completes While SLOW Waits

This example uses Java 17+, Maven, and Spring Framework `6.2.12`; **no Spring Boot or HTTP server is required**. Configure two `ThreadPoolTaskExecutor` beans:

- `fastExecutor`: one worker, queue of four tasks; a lightweight task that must complete early.
- `slowExecutor`: one worker, queue of two tasks; simulates long-waiting I/O work.

Instead of using `Thread.sleep()` and measuring elapsed time (which is easily flaky), use `CountDownLatch` to **actively hold the slow worker**, confirm the worker has started, and then submit FAST. If FAST completes while the latch is still locked, the two pools provide separate execution regions in the example.

Directory structure:

```text
separate-executors-demo/
├── pom.xml
└── src/main/java/example/SeparateExecutorsDemo.java
```

Create `pom.xml`:

```xml
<project xmlns="http://maven.apache.org/POM/4.0.0"
         xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
         xsi:schemaLocation="http://maven.apache.org/POM/4.0.0 https://maven.apache.org/xsd/maven-4.0.0.xsd">
    <modelVersion>4.0.0</modelVersion>
    <groupId>example</groupId>
    <artifactId>separate-executors-demo</artifactId>
    <version>1.0.0</version>

    <properties>
        <maven.compiler.release>17</maven.compiler.release>
        <project.build.sourceEncoding>UTF-8</project.build.sourceEncoding>
    </properties>

    <dependencies>
        <dependency>
            <groupId>org.springframework</groupId>
            <artifactId>spring-context</artifactId>
            <version>6.2.12</version>
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
                    <mainClass>example.SeparateExecutorsDemo</mainClass>
                </configuration>
            </plugin>
        </plugins>
    </build>
</project>
```

Create `src/main/java/example/SeparateExecutorsDemo.java`:

```java
package example;

import java.util.concurrent.CompletableFuture;
import java.util.concurrent.CountDownLatch;
import java.util.concurrent.TimeUnit;

import org.springframework.context.annotation.AnnotationConfigApplicationContext;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.scheduling.annotation.Async;
import org.springframework.scheduling.annotation.EnableAsync;
import org.springframework.scheduling.concurrent.ThreadPoolTaskExecutor;

public class SeparateExecutorsDemo {

    public record Result(String value, String threadName) {
    }

    public static class Gates {
        final CountDownLatch slowStarted = new CountDownLatch(1);
        final CountDownLatch allowSlowFinish = new CountDownLatch(1);
    }

    public static class WorkService {
        private final Gates gates;

        public WorkService(Gates gates) {
            this.gates = gates;
        }

        @Async("slowExecutor")
        public CompletableFuture<Result> slowIntegration(String id) {
            gates.slowStarted.countDown();
            try {
                if (!gates.allowSlowFinish.await(10, TimeUnit.SECONDS)) {
                    return CompletableFuture.failedFuture(
                        new IllegalStateException("Slow task timed out")
                    );
                }
            } catch (InterruptedException ex) {
                Thread.currentThread().interrupt();
                return CompletableFuture.failedFuture(ex);
            }

            return CompletableFuture.completedFuture(
                new Result("slow:" + id, Thread.currentThread().getName())
            );
        }

        @Async("fastExecutor")
        public CompletableFuture<Result> fastCalculation(String id) {
            return CompletableFuture.completedFuture(
                new Result("fast:" + id, Thread.currentThread().getName())
            );
        }
    }

    @Configuration(proxyBeanMethods = false)
    @EnableAsync
    public static class Config {
        @Bean
        public Gates gates() {
            return new Gates();
        }

        @Bean
        public WorkService workService(Gates gates) {
            return new WorkService(gates);
        }

        @Bean("fastExecutor")
        public ThreadPoolTaskExecutor fastExecutor() {
            ThreadPoolTaskExecutor executor = new ThreadPoolTaskExecutor();
            executor.setCorePoolSize(1);
            executor.setMaxPoolSize(1);
            executor.setQueueCapacity(4);
            executor.setThreadNamePrefix("fast-");
            return executor;
        }

        @Bean("slowExecutor")
        public ThreadPoolTaskExecutor slowExecutor() {
            ThreadPoolTaskExecutor executor = new ThreadPoolTaskExecutor();
            executor.setCorePoolSize(1);
            executor.setMaxPoolSize(1);
            executor.setQueueCapacity(2);
            executor.setThreadNamePrefix("slow-");
            return executor;
        }
    }

    public static void main(String[] args) throws Exception {
        try (AnnotationConfigApplicationContext context =
                 new AnnotationConfigApplicationContext(Config.class)) {

            Gates gates = context.getBean(Gates.class);
            WorkService service = context.getBean(WorkService.class);
            ThreadPoolTaskExecutor fastPool =
                context.getBean("fastExecutor", ThreadPoolTaskExecutor.class);
            ThreadPoolTaskExecutor slowPool =
                context.getBean("slowExecutor", ThreadPoolTaskExecutor.class);

            CompletableFuture<Result> slow = service.slowIntegration("A");

            try {
                if (!gates.slowStarted.await(10, TimeUnit.SECONDS)) {
                    throw new IllegalStateException("Slow worker did not start");
                }

                CompletableFuture<Result> fast = service.fastCalculation("B");
                Result fastResult = fast.get(10, TimeUnit.SECONDS);

                boolean fastFinishedWhileSlowBlocked = !slow.isDone();

                gates.allowSlowFinish.countDown();
                Result slowResult = slow.get(10, TimeUnit.SECONDS);

                System.out.println("separateExecutors=" + (fastPool != slowPool));
                System.out.println("fastFinishedWhileSlowBlocked="
                    + fastFinishedWhileSlowBlocked);
                System.out.println("fastUsesFastPool="
                    + fastResult.threadName().startsWith("fast-"));
                System.out.println("slowUsesSlowPool="
                    + slowResult.threadName().startsWith("slow-"));
                System.out.println("fastValue=" + fastResult.value());
                System.out.println("slowValue=" + slowResult.value());
            } finally {
                gates.allowSlowFinish.countDown();
            }
        }
    }
}
```

Run inside the `separate-executors-demo` directory:

```bash
mvn -q compile exec:java
```

Six lines printed by the **program** on a successful run (any Maven logs are separate from these lines):

```text
separateExecutors=true
fastFinishedWhileSlowBlocked=true
fastUsesFastPool=true
slowUsesSlowPool=true
fastValue=fast:B
slowValue=slow:A
```

### Explaining Execution Flow and Output

1. The context creates two distinct executor beans, each with its own worker pool. Comparing `fastPool != slowPool` yields `true`.
2. The caller receives a `CompletableFuture<Result>` when submitting `slowIntegration("A")` through the Spring proxy. The slow worker calls `slowStarted.countDown()` and then waits on `allowSlowFinish`.
3. Main waits on `slowStarted.await(...)`, thus knowing the slow task has actually started.
4. Main calls `fastCalculation("B")` through the proxy, this time using `fastExecutor` rather than waiting for the slow worker. `fast.get(...)` finishes before main releases the slow latch.
5. The expression `!slow.isDone()` evaluates to `true` before the latch is released. This is controlled proof that the fast group runs independently of the waiting worker in the slow group.
6. Main releases the latch, retrieves the slow result, and prints in deterministic order; the `fast-`/`slow-` prefixes prove the corresponding worker names.

The latch pair is only for the **experiment**. Real applications must use HTTP/database timeouts and appropriate concurrency controls, not hold workers with latches as business logic. One worker per pool is for observability, not a production configuration formula.

With `@Async`, the actual method returns `CompletableFuture.completedFuture(result)` **inside the worker**; the Spring interceptor returns a completion handle to the caller. That does not turn the method body into a synchronous call on the caller. If the caller calls `.get()` or `.join()` immediately, the caller can still block.

## 6. Ways to Select an Executor by Group

### Using @Async by Name

`@Async("fastExecutor")` and `@Async("slowExecutor")` are intuitive choices when work is organized as methods on Spring beans. Name beans after their **purpose and SLA**, such as `paymentExecutor`, `externalIoExecutor`, `reportExecutor`, instead of `pool1`, `pool2`.

If a method is called via `this.method()` within the same bean, the call does not go through the default proxy and the annotation does not route work to the intended executor. The usual solution is to extract the async task into another injected bean and call it through the Spring reference.

### Injecting an Executor Explicitly

When you need to construct multiple tasks inside one method, or when a service dispatches tasks dynamically, inject the executor by qualifier:

```java
@Service
public class ReportDispatcher {
    private final AsyncTaskExecutor reportExecutor;

    public ReportDispatcher(
            @Qualifier("reportExecutor") AsyncTaskExecutor reportExecutor) {
        this.reportExecutor = reportExecutor;
    }

    public Future<String> dispatch(String id) {
        return reportExecutor.submit(() -> "report:" + id);
    }
}
```

This is a snippet for a Spring application, not a standalone Java file; it requires importing the Spring annotations, `AsyncTaskExecutor`, `Future`, and declaring the `reportExecutor` bean. Meaning: each `dispatch` call submits a `Callable` to the **selected pool** and returns a handle; business code must still design error handling, timeouts, and durability.

### Default Executor

`AsyncConfigurer` can provide a default executor for `@Async` methods that do not specify a value. Only use a default when resource boundaries do not matter or a policy has been agreed upon. For groups needing isolation, `@Async("namedExecutor")` helps reviewers and operations see clearly which pool takes the load.

Spring does not automatically analyze that an "API-calling" method belongs in the I/O pool or a "computation" method belongs in the CPU pool. Classification and routing are design decisions.

## 7. How to Estimate Thread Counts for Each Group

### CPU-bound

For continuously CPU-intensive tasks, the effective number of workers is usually close to the available CPUs of the process/container, depending also on other workloads and latency targets. For example, a container with two CPUs should not blindly allocate five CPU-bound executors with eight workers each and expect 40 threads to run truly in parallel. Total CPU is still only about two CPUs; contention and context switching can increase.

Start with an overall CPU budget, measure throughput, CPU utilization, p95/p99, and queue time. Tune based on profiles and actual CPU quota limits.

### Blocking I/O

If tasks spend significant time waiting on network/DB, a pool may need more workers than CPUs. A rough starting formula in a specific model is:

\[
N_{\text{threads}} \approx N_{\text{CPU}} \times U_{\text{target}} \times (1 + W/C)
\]

Here `W` is I/O wait time, `C` is CPU time, and `U_target` is target CPU utilization. **This is a starting assumption**, not a rule to apply mechanically. A 100-worker pool is useless if the DB only grants 10 connections or the API limits concurrent calls to 20. The real constraint is usually the minimum of CPU, connection pool, quota, memory, timeout, and downstream budget.

By Little's Law at steady load, average concurrent work relates to arrival rate and residence/processing time in the system. For example, at 20 requests/s with each request needing about 0.25 s of I/O, there are on average about 5 requests in that phase. You must reserve headroom for bursts and measure actual latency; do not treat average math as a p99 guarantee.

### Low-Latency Group

A small, controlled queue can protect deadlines better than a very large queue. If incoming load exceeds serving capacity, you need fail-fast, degraded responses, delayed retries, or admission control. A `Future` returned immediately on submission does not mean the result will be ready before the deadline.

### Background and Batch

They can tolerate longer wait times, yet queue/memory must still be bounded. Work that must survive restarts **cannot rely solely on an in-memory queue inside `ThreadPoolTaskExecutor`**, because RAM is not durable. Use a persistent job store/broker and design idempotency when needed.

## 8. Backpressure and Rejection Policies

| Policy | On Saturation | Things to Watch |
| --- | --- | --- |
| `AbortPolicy` | Throws a rejection error on submit. Spring typically surfaces this as `TaskRejectedException`. | The caller learns of overload; the business layer must decide response/retry/fallback. |
| `CallerRunsPolicy` | The caller runs the task itself if the pool is not shut down. | Creates backpressure, but can run very slow work on HTTP request threads, weakening isolation. |
| `DiscardPolicy` | Drops the task. | Do not use for work requiring guaranteed processing; easily causes silent data loss. |
| `DiscardOldestPolicy` | Drops the oldest item in the queue and retries accepting the new task. | Can lose already-accepted tasks, causing priority/order inversion. |

Example setter usage when configuring a bean:

```java
ThreadPoolTaskExecutor executor = new ThreadPoolTaskExecutor();
executor.setCorePoolSize(2);
executor.setMaxPoolSize(4);
executor.setQueueCapacity(8);
executor.setThreadNamePrefix("integration-");
executor.setRejectedExecutionHandler(
    new java.util.concurrent.ThreadPoolExecutor.AbortPolicy()
);
```

This is an **illustrative configuration snippet**; you must return `executor` from a `@Bean` method so Spring initializes and manages its lifecycle.

When already overloaded, immediate unbounded retries onto the same pool can trigger a **retry storm**. Depending on business needs, limit retry attempts, add backoff, jitter, timeouts, circuit breakers, or rate limits. Choosing a task-dropping policy must be driven by data requirements; never lose payments, audit records, or critical work just to "increase throughput."

## 9. Limits of Separating Pools

**Shared CPU.** Multiple pools still contend for the same machine/container CPU. If batch occupies all CPU, FAST can still slow down even with dedicated workers.

**Shared database.** `fastExecutor` and `slowExecutor` may share the same `DataSource`. When the slow group holds all connections, the fast group still stalls while acquiring a connection. Limit concurrent DB calls, transaction duration, and query timeouts; if strict isolation is required, enforce policies at the connection or storage layer.

**HTTP clients and external services.** They can bottleneck on a shared connection pool, DNS, sockets, or rate-limit quotas. Two separate groups in one JVM do not guarantee total calls across multiple replicas stay under quota.

**Heap/GC.** Every queued task holds objects and closures. Large queues increase heap usage, GC pauses, and memory pressure. Separate pools do not prevent JVM OOM.

**Locks and state.** Two groups can contend on the same monitor, cache lock, or database row. Separating workers does not replace proper synchronization and transactions.

**Shutdown/crash.** In-memory queues are lost when the process dies. Tasks requiring durability must have external state persistence and a recovery mechanism.

Therefore, an executor bulkhead is only **one layer** in an anti-bottleneck strategy. For downstreams needing protection, consider semaphore bulkheads, separate connection pools, rate limiters, timeouts, and appropriate circuit breakers.

## 10. Errors, Timeouts, Cancellation, and Context

Distinguish between:

1. **Task submission rejected:** executor/queue is saturated or shutting down; the call at the submit site may throw `TaskRejectedException`. There is no guarantee the task was accepted.
2. **Task ran and failed:** `Future.get()` may throw `ExecutionException`; `CompletableFuture.join()` typically reports `CompletionException`. Observe the future/callback so errors are not lost.
3. **Caller waited too long:** `Future.get(timeout, unit)` throws `TimeoutException` but **does not automatically stop the task**; `CompletableFuture.orTimeout` also does not guarantee the worker is interrupted.
4. **Cancellation:** cancellation/interruption depends on cooperation from the task and I/O libraries; it does not guarantee rolling back side effects in external services.

With `@Async` returning `void`, the caller has no handle to receive errors. Configure `AsyncUncaughtExceptionHandler` if truly necessary, though important work should have a result/status channel.

Example of observing `CompletableFuture` (assuming `WorkService service` from the main example):

```java
service.fastCalculation("C").whenComplete((value, error) -> {
    if (error != null) {
        System.err.println("Failed: " + error.getMessage());
    } else {
        System.out.println(value.value());
    }
});
```

`whenComplete` observes both errors and success; `exceptionally` or `handle` can be used to decide a fallback. Callbacks like `thenApply` do not automatically guarantee running on another thread; use `...Async(..., executor)` variants when choosing an executor for the next step, avoiding accidentally shifting work to the JDK common pool.

`@Async` creates a thread boundary: MDC logging, `SecurityContext`, request-scoped context, `ThreadLocal`, and the caller thread's transaction do **not automatically** propagate to the worker. You can use a `TaskDecorator` or controlled context propagation, which must restore/clear context in `finally` because workers are reused. The caller's transaction does not become the worker's transaction; if a background task needs a transaction, design a separate boundary via an appropriate Spring bean/proxy.

In Spring MVC, a controller calling `.get()`/`.join()` immediately will block the controller thread even if the service uses another executor. Releasing the Servlet request thread requires an appropriate async HTTP processing contract, independent of `@Async` pool partitioning.

## 11. Lifecycle, Shutdown, and Durability

Each `ThreadPoolTaskExecutor` bean has a lifecycle managed by the Spring container. When closing `ApplicationContext`, Spring runs the shutdown sequence according to the lifecycle contract. For real applications, define:

- Should new work stop being accepted during shutdown?
- How long are already-accepted tasks (running or queued) allowed to finish?
- If the shutdown deadline expires, can tasks be interrupted/cancelled or must their state be recorded?
- If one executor is used by multiple components, who owns shutdown authority?
- For business-critical work, are idempotency, retries, and persistent job records in place?

`ThreadPoolTaskExecutor` provides shutdown options such as `setWaitForTasksToCompleteOnShutdown` and `setAwaitTerminationSeconds` (check the API for your version). Do not equate "a separate pool" with "a submitted task is guaranteed to succeed." In the main example, main waits for both `Future` instances to finish before closing the context, so it does not have to handle restart recovery.

## 12. Monitoring and Evaluating Real Effectiveness

Tag metrics by executor, e.g., `pool=fast`, `pool=slow`, and observe:

| Metric | Meaning |
| --- | --- |
| `active threads`, `pool size`, `queue depth` | Are workers/queues saturated, and in which group? |
| Queue waiting time and execution duration | Is latency coming from waiting or actual processing time? |
| p50/p95/p99 end-to-end latency | Does pool separation protect FAST's SLA? |
| Submitted/succeeded/failed/rejected/cancelled | Are errors occurring or tasks being lost? |
| CPU, heap, GC, total thread count | Does pool partitioning add overhead or memory pressure? |
| DB/HTTP connection usage, 429s, and downstream timeouts | Which shared resource still has a bottleneck? |

`ThreadPoolTaskExecutor` exposes snapshots such as `getPoolSize()`, `getActiveCount()`, and `getQueueSize()` (depending on version API). Snapshots are insufficient for logic like "queue has space, so submit will surely succeed": state can change before submission.

A controlled improvement loop:

1. Measure baseline with a shared pool; identify which group causes queue wait/tail latency.
2. Identify groups needing isolation and total CPU/thread/connection/memory budgets.
3. Declare separate executors, bounding queues and rejection policies by business impact.
4. Load the slow group past threshold and observe whether FAST still finishes within target.
5. Test concurrent CPU/DB/downstream saturation to uncover shared bottlenecks.
6. Monitor post-deployment metrics and refine based on real load.

If using Spring Boot Actuator/Micrometer, you can instrument executors via the appropriate integration, but verify metrics setup within the application itself; core Spring Framework does not ship a complete dashboard out of the box.

## 13. Common Mistakes

| Mistake | Consequence | Fix |
| --- | --- | --- |
| All `@Async` methods share one default pool | Slow tasks occupy workers/queue of fast tasks. | Route explicitly by resource group. |
| Creating two differently named beans with the same delegate | Still shares the same thread pool and queue. | Inspect actual instances/metrics. |
| Setting large `maxPoolSize` and huge queue expecting threads to scale | Queue usually fills before scaling past core. | Understand worker–queue–max order and load test. |
| Making the queue unbounded to avoid rejection | Increases tail latency/memory, hides overload. | Bounded queues, admission control, and intentional errors. |
| Using `CallerRunsPolicy` for low-latency groups | Slow tasks may run on the HTTP caller thread. | Pick overload policies according to SLA. |
| Splitting CPU pools with total workers far exceeding CPU quota | CPU contention, context switching. | Calculate process-wide CPU budget. |
| Separating pools while sharing a saturated connection pool | FAST still stalls at DB/HTTP layer. | Limit downstream concurrency, add quotas/timeouts. |
| Forgetting `@EnableAsync` or using self-invocation | Annotation bypasses the interceptor. | Call through a Spring bean/proxy. |
| Calling `@Async` then immediately calling `join()` in controller | Caller still blocks. | Choose appropriate async HTTP/composition patterns. |
| Ignoring rejection, task failure, and timeout | Lost results or retry storms. | Observe `Future`, bound retries, define fallbacks. |
| Assuming RAM queues preserve work across restarts | Tasks can be lost on crash. | Use a job store/broker if durability is needed. |
| Passing `ThreadLocal` to worker without cleanup | Context can leak across requests. | Propagate and clean up in `finally`. |

## 14. Self-Check

**Q1.** Two blocking HTTP tasks are holding both workers of a shared pool. A 2 ms computation task is submitted. Is it guaranteed to return its result after 2 ms?

**Answer:** No. Queue waiting time can be much longer than execution time. Separating groups and adding I/O timeouts help protect workers for fast tasks.

**Q2.** Two separate executors share a single JDBC connection pool with a maximum of four connections. Four slow tasks hold all connections. Is FAST guaranteed to be isolated?

**Answer:** No. Only the thread pools are separated; JDBC connections are a shared resource. Concurrency/timeouts must also be managed at the data layer.

**Q3.** `corePoolSize=2`, `maxPoolSize=20`, `queueCapacity=10000`. When 100 tasks arrive in a short burst, will the pool definitely create 20 workers?

**Answer:** No. With a positive queue, tasks are typically queued once core workers are busy before scaling workers past core.

**Q4.** Does `CallerRunsPolicy` preserve the assumption that an `@Async` method always runs on a separate worker when the pool is overloaded?

**Answer:** No. The caller may have to execute the rejected task itself, increasing latency. This is a form of backpressure with trade-offs to weigh.

**Q5.** Why does the example use `CountDownLatch` instead of `Thread.sleep()`?

**Answer:** To confirm the slow worker has actually entered the method and is being held before submitting FAST, avoiding conclusions based on lucky scheduling.

**Q6.** Five CPU-bound executors each have eight workers, but the container only gets two CPUs. Does pool partitioning create 40 CPUs of true parallel processing?

**Answer:** No. The threads still contend for two CPUs; total concurrency must be tuned to the quota and real measurements.

**Q7.** A background report must continue after an application restart. Is separating a dedicated `reportExecutor` enough?

**Answer:** Not yet. In-memory thread pools/queues are not durable; you need job persistence and a retry/recovery/idempotency plan.

**Q8.** Does receiving a `CompletableFuture` from `@Async` prove the work is complete or that the caller will never wait?

**Answer:** No. A `Future` is a handle to the result; `get()`/`join()` can still block, and the task may still be running or failed.

### Key Points to Remember

To separate executors properly, identify **task characteristics, latency requirements, downstream limits, total resource budgets, and overload handling**. Give each group that truly needs isolation a bounded executor/queue, monitor separate metrics, and test under load. Worker isolation reduces cross-impact, yet system safety still depends on CPU, DB, heap, locks, timeouts, and job durability.

### References

- [Spring Framework 6.2 — Task Execution and Scheduling](https://docs.spring.io/spring-framework/reference/6.2/integration/scheduling.html): `TaskExecutor`, `ThreadPoolTaskExecutor`, `@Async`, qualifiers, and rejection.
- [Spring Framework 6.2 — ThreadPoolTaskExecutor API](https://docs.spring.io/spring-framework/docs/6.2.12/javadoc-api/org/springframework/scheduling/concurrent/ThreadPoolTaskExecutor.html): core/max/queue, monitoring, lifecycle.
- [Java 17 — ThreadPoolExecutor API](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/concurrent/ThreadPoolExecutor.html): worker/queue behavior, saturation, and rejection policies.
- [Java 17 — CountDownLatch API](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/concurrent/CountDownLatch.html): coordinating execution timing and happens-before.

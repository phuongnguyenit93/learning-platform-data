# supplyAsync() Without an Executor and the Risk of Sharing the Common Pool

## Scope and Goals

In Java and Spring applications, `CompletableFuture.supplyAsync(...)` runs a `Supplier<T>` elsewhere and returns a `CompletableFuture<T>` so the caller can continue work. However, **omitting an `Executor`** does not mean Spring automatically chooses your application's thread pool. In Java 17, the single-argument overload **defaults to submitting tasks to `ForkJoinPool.commonPool()`**, a **JVM-wide shared resource**.

This matters when composing multiple `CompletableFuture` instances: work that accidentally shares the common pool can contend for workers with libraries or other components, especially when tasks perform **blocking I/O**, run long, or hit traffic spikes.

After this lesson, you will be able to:

- Accurately distinguish `supplyAsync(supplier)` from `supplyAsync(supplier, executor)`, including the JDK fallback when the common pool lacks minimum parallelism.
- Explain why `ForkJoinPool.commonPool()` is a JVM-wide shared pool, not a dedicated pool per request, Spring bean, or `supplyAsync` call.
- Analyze the impact of CPU-bound work, blocking I/O, long tasks, excessive futures, and chained stages on shared resources.
- Configure a Spring `ThreadPoolTaskExecutor` and **explicitly pass it** into `supplyAsync` and any `...Async` stages needing coordination.
- Verify execution threads via thread names/metrics without writing tests that depend on fixed common-pool worker names.
- Distinguish errors inside `Supplier`, **submission-time rejection**, timeouts, cancellation, and context propagation.
- Choose `CompletableFuture` composition patterns that are safe, observable, resource-bounded, and lifecycle-appropriate for production.

**Example versions:** Java 17+; Spring examples use **Spring Framework 6.1.3**, Maven, and Java 17+. Technical details align with Java SE 17 Javadoc and Spring documentation. Focus is on execution mechanics and resource control, not internal APIs or global JVM tuning hacks.

## 1. Two Similar-Looking Overloads That Run in Different Places

`CompletableFuture` has two static methods:

~~~java
// Abbreviated API signatures — not a standalone Java class.
static <U> CompletableFuture<U> supplyAsync(Supplier<U> supplier);

static <U> CompletableFuture<U> supplyAsync(
        Supplier<U> supplier, Executor executor);
~~~

With the first overload, `Supplier.get()` runs on **the JDK's default asynchronous execution facility**. Per Java 17 Javadoc, async methods that accept no `Executor` are executed by `ForkJoinPool.commonPool()`, **unless** the common pool does not support a parallelism level of at least 2: in that case `CompletableFuture` creates **a new thread for each task**. Therefore, saying "there is always a worker named `ForkJoinPool.commonPool-worker-*`" is inaccurate across all JVMs.

The second overload uses the exact `Executor` passed in. In Spring, `ThreadPoolTaskExecutor` implements `Executor`, so it can be passed directly as the second argument. It is **not selected automatically** simply because the application declared a `TaskExecutor` bean.

Illustrative example:

~~~java
// Fragment, assuming ioExecutor is a configured Executor.
CompletableFuture<String> a =
        CompletableFuture.supplyAsync(() -> "A"); // default executor

CompletableFuture<String> b =
        CompletableFuture.supplyAsync(() -> "B", ioExecutor); // explicit choice
~~~

Both calls return `CompletableFuture<String>`, yet **their execution resources differ**. Control over queues, thread names, worker counts, thread contexts, and metrics depends on the executor that actually receives the task, not the returned `Future` type.

| Criterion | `supplyAsync(supplier)` | `supplyAsync(supplier, executor)` |
| --- | --- | --- |
| Default execution location | JVM's `ForkJoinPool.commonPool()`, with low-parallelism exception | The `Executor` you supply |
| Uses a declared Spring `TaskExecutor` bean? | **Not automatically** | Yes, if you **pass that bean** |
| Concurrency limits | Governed by common pool policy and JVM resources | Governed by your executor's configuration |
| Business workload isolation | None; shared with all other common-pool users | Can isolate by workload type |
| Thread names / metrics / shutdown | Tied to common pool | Explicitly configurable, observable, and manageable |
| Risk of blocking tasks occupying shared workers | Yes | Can be bounded with a dedicated pool and downstream limits |
| Exception inside `Supplier` | Future completes exceptionally | Future completes exceptionally |
| Executor rejects submission | Not typically governed by Spring app queues | May throw `RejectedExecutionException` / Spring `TaskRejectedException` immediately |

**Distinction:** `CompletableFuture.completedFuture(value)` does not submit an async task; it creates an **already completed** future. `CompletableFuture.supplyAsync(...)` schedules `Supplier` to run on an executor. Having a `CompletableFuture` does not by itself prove work ran on another thread.

## 2. What Is ForkJoinPool.commonPool?

`ForkJoinPool` is a JDK executor designed to split and process parallel work using work-stealing. `ForkJoinPool.commonPool()` is a **shared singleton instance** within the running JVM process. Many components calling async APIs without specifying an executor can feed tasks into it simultaneously.

~~~text
Reporting module              Notification module          Other library
       |                            |                           |
       | supplyAsync(supplier)      | runAsync(runnable)        | thenApplyAsync(fn)
       v                            v                           v
       +----------------------------+---------------------------+
                                    |
                             commonPool (JVM)
                                    |
                   workers executing various shared tasks
                                    |
                   one slow task can affect other tasks
~~~

This does not mean tasks in the common pool **always run sequentially**: the pool has multiple workers and work-stealing. The issue is **sharing finite resources** and struggling to isolate or predict latency when modules have differing load profiles.

### Why Is Sharing Sometimes Reasonable?

For a small amount of short, independent, **CPU-bound** computation that needs no dedicated pool and performs no long-blocking I/O, the common pool can be a simple choice. The JDK designed `CompletableFuture` so users do not have to create an executor for every trivial task.

In a production service, however, evaluate **workload volume, blocking behavior, coexistence with other modules, SLAs, and orchestration needs**. There is no rule that every `supplyAsync` is dangerous; risk arises when using a shared resource by default **without weighing load and ownership**.

### Inspecting the Common Pool Instead of Guessing from Core Count

~~~java
int parallelism = ForkJoinPool.getCommonPoolParallelism();
System.out.println("commonParallelism=" + parallelism);
~~~

This is a fragment requiring `import java.util.concurrent.ForkJoinPool`. The result depends on JVM settings and environment, so there is no fixed numeric stdout. `getCommonPoolParallelism()` returns the **target parallelism level**, not the number of threads currently running at that instant or the maximum number of tasks your app can complete concurrently.

Some system properties affect the common pool, such as `java.util.concurrent.ForkJoinPool.common.parallelism`. However, that is a **JVM-wide tuning knob** and can impact third-party libraries; do not reach for bumping a global property as the first fix for a workload that needs isolation.

## 3. Risks When Omitting an Executor

### 3.1. Blocking I/O Can Occupy Shared Workers

Suppose `Supplier` calls HTTP, JDBC, or a synchronous SDK:

~~~java
// Architectural anti-example: client.fetch(id) is a blocking call.
// Illustrative code only, not a standalone program.
CompletableFuture<String> result =
        CompletableFuture.supplyAsync(() -> client.fetch(id));
~~~

If `fetch` blocks for a long time, the worker executing it is held for that duration. When many similar tasks are submitted to the common pool, other short CPU-bound tasks can be **delayed**. `ForkJoinPool` has mechanisms supporting certain blocking scenarios (such as managed blocking), so you should not claim it **never compensates workers**. Still, ordinary HTTP/JDBC libraries do not automatically provide resource-compensation guarantees tailored to business SLAs.

**Common fix:** pass an I/O executor with bounded concurrency and measure downstream resources:

~~~java
// ioExecutor is a configured Executor / ThreadPoolTaskExecutor.
CompletableFuture<String> result =
        CompletableFuture.supplyAsync(
                () -> client.fetch(id),
                ioExecutor
        );
~~~

A dedicated pool can still overload, so pay attention to `maxPoolSize`, `queueCapacity`, HTTP timeouts, database connection pools, and task rejection handling. Separating executors **does not turn a synchronous API into non-blocking I/O**; it simply chooses where blocking workers reside.

### 3.2. Two Modules Can Affect Each Other Unknowingly

A slow email-sending task and a short calculation task can share the common pool if both use default `supplyAsync(...)`. The calculation module cannot see the email module's settings, yet both share execution capacity. When latency rises, developers can easily misdiagnose the calculation module's algorithm.

Separating executors provides per-workload limits and metrics: thread names, active workers, queue depth, rejection rate, task wait time, and p95/p99 latency. Still, two separate executors **still share host CPU, memory, and downstreams**; it is scheduling-level isolation, not absolute resource partitioning.

### 3.3. "Running Async" Does Not Mean "Cannot Be Slow"

`supplyAsync` returns a `CompletableFuture` early, yet if the caller immediately calls `join()`, the caller still waits for the result:

~~~java
// Fragment illustrating how async accidentally becomes blocking.
String value = CompletableFuture
        .supplyAsync(() -> expensiveOperation())
        .join();
~~~

Omitting an executor sends the work to the default facility, and `join()` blocks the caller. If this runs on a request thread, request latency still climbs. Consider keeping the `Future` and doing independent work, or returning `CompletableFuture` to a layer supporting async responses where appropriate.

### 3.4. More Futures Do Not Create More CPU Capacity

Submitting 100,000 `supplyAsync` tasks does not turn 8 CPU cores into 100,000 cores. Tasks may queue for a long time, consume memory, and put pressure on CPU and GC. If the work is blocking I/O, worker counts and throughput depend on the executor and downstream capacity. Size concurrency to **system capacity**, not by counting futures.

Do not create a fresh `newFixedThreadPool` **per request** to dodge the common pool: that causes thread explosion, defeats pool reuse, and complicates shutdown. Instead, use **shared executor beans grouped by workload type**, created once in Spring.

## 4. Do Downstream CompletableFuture Stages Inherit the Executor?

**No.** Submitting the initial step with `supplyAsync(supplier, ioExecutor)` does not establish a rule that **all subsequent stages automatically run on `ioExecutor`**.

| Stage | Executor passed? | Execution thread per contract |
| --- | --- | --- |
| `thenApply(fn)` | No Executor overload (non-async) | May run on thread completing previous stage or a completion caller |
| `thenCompose(fn)` | Non-async | May run on completion thread or completion caller |
| `thenApplyAsync(fn)` | No | Uses default asynchronous execution facility, typically common pool |
| `thenApplyAsync(fn, ioExecutor)` | Yes | Dispatched to `ioExecutor` |
| `thenComposeAsync(fn, ioExecutor)` | Yes | Composition callback dispatched to `ioExecutor`; returned future has its own lifecycle |
| `handleAsync(fn)` | No | Uses default async execution facility |
| `handleAsync(fn, ioExecutor)` | Yes | Dispatched to `ioExecutor` |

Example:

~~~java
// Fragment with variable ioExecutor of type Executor.
CompletableFuture<String> first =
        CompletableFuture.supplyAsync(() -> "spring", ioExecutor);

// No guarantee of continuing on ioExecutor:
CompletableFuture<String> second =
        first.thenApplyAsync(String::toUpperCase);

// Requests the next stage to be scheduled on ioExecutor:
CompletableFuture<String> third =
        first.thenApplyAsync(String::toUpperCase, ioExecutor);
~~~

**Subtlety:** `thenApply` **without `Async`** may run directly on the callback-registering thread if the future is already complete, or on the future-completing thread depending on timing. Therefore do not build business logic assuming "`thenApply` definitely runs on a Spring worker." For `...Async` stages where context, metrics, or pool isolation matter, pass the executor explicitly.

On the other hand, not every tiny computation needs a thread switch. A fast string-transform `thenApply` usually has low overhead; use `thenApplyAsync(..., executor)` when you genuinely want a **scheduling boundary** and execution control.

## 5. Standalone Java 17+ Example: Default vs. Explicit Executor

The following program illustrates two paths:

- A default task producing `default-ok`; **execution location** follows `supplyAsync`'s Javadoc without hardcoding thread names.
- A dedicated executor naming threads `business-*`. Both the initial task and `thenApplyAsync(..., businessPool)` use this executor.
- `Supplier` throws an exception; the future completes exceptionally and `handle` inspects the cause.

Save as `SupplyAsyncExecutorDemo.java`:

~~~java
import java.util.concurrent.CompletableFuture;
import java.util.concurrent.CompletionException;
import java.util.concurrent.ExecutorService;
import java.util.concurrent.Executors;
import java.util.concurrent.TimeUnit;
import java.util.concurrent.atomic.AtomicInteger;

public final class SupplyAsyncExecutorDemo {

    public static void main(String[] args) throws Exception {
        AtomicInteger ids = new AtomicInteger();

        ExecutorService businessPool = Executors.newFixedThreadPool(
                2,
                task -> {
                    Thread worker = new Thread(task);
                    worker.setName("business-" + ids.incrementAndGet());
                    return worker;
                }
        );

        try {
            // No executor passed: uses default async facility.
            CompletableFuture<String> implicit =
                    CompletableFuture.supplyAsync(() -> "default-ok");

            // Explicitly pass executor for both initial task and async stage.
            CompletableFuture<String> explicit =
                    CompletableFuture.supplyAsync(
                            () -> Thread.currentThread().getName(),
                            businessPool
                    ).thenApplyAsync(
                            threadName -> "dedicated="
                                    + threadName.startsWith("business-"),
                            businessPool
                    );

            // Error thrown in Supplier flows into CompletableFuture.
            CompletableFuture<Integer> failed =
                    CompletableFuture.supplyAsync(() -> {
                        throw new IllegalArgumentException("bad-input");
                    }, businessPool);

            System.out.println("default=" + implicit.join());
            System.out.println(explicit.join());

            String error = failed.handle((value, throwable) -> {
                if (throwable == null) {
                    return "none";
                }
                Throwable root = throwable instanceof CompletionException
                        ? throwable.getCause() : throwable;
                return root.getClass().getSimpleName()
                        + ":" + root.getMessage();
            }).join();

            System.out.println("error=" + error);
        } finally {
            businessPool.shutdown();
            if (!businessPool.awaitTermination(
                    5, TimeUnit.SECONDS)) {
                businessPool.shutdownNow();
            }
        }
    }
}
~~~

Run:

~~~bash
javac SupplyAsyncExecutorDemo.java
java SupplyAsyncExecutorDemo
~~~

Lines printed by the program (excluding external tool logs):

~~~text
default=default-ok
dedicated=true
error=IllegalArgumentException:bad-input
~~~

**Why not print the thread name from the default task?** Because thread names, worker counts, and the low-parallelism fallback path **depend on the JVM/environment**. When debugging, a supplier can return `Thread.currentThread().getName()` and log it **as observational data**, without asserting a fixed string.

**Why is `dedicated=true` guaranteed?** `businessPool` uses a thread factory naming threads `business-1`, `business-2`, and the first stage returns that thread's name. `thenApplyAsync(..., businessPool)` is still submitted to the same pool. The boolean is computed from the captured thread name regardless of which worker runs each stage.

**Why does `error` contain `IllegalArgumentException`?** An exception inside the supplier is not thrown synchronously at the future creation line; the future completes **exceptionally**. `handle` inspects the throwable, unwraps `CompletionException` when present, and builds the result string.

`shutdown()` applies only to the **self-created `businessPool`**. The program **does not shut down the JVM-wide common pool**; shutting down the common pool is not an appropriate cleanup action for an application module.

## 6. Demonstrating Contention on a Shared Executor (Without Touching the Common Pool)

To understand "a long task makes a short task wait," we use a self-created executor with **only 1 worker**. This is a **model simulating resource sharing**, not a claim that the real common pool always has a single worker or schedules identically to `ForkJoinPool`.

Save as `SharedExecutorContentionDemo.java`:

~~~java
import java.util.concurrent.CompletableFuture;
import java.util.concurrent.CountDownLatch;
import java.util.concurrent.ExecutorService;
import java.util.concurrent.Executors;
import java.util.concurrent.TimeUnit;

public final class SharedExecutorContentionDemo {

    public static void main(String[] args) throws Exception {
        ExecutorService shared = Executors.newSingleThreadExecutor();
        CountDownLatch started = new CountDownLatch(1);
        CountDownLatch release = new CountDownLatch(1);

        try {
            CompletableFuture<String> slow =
                    CompletableFuture.supplyAsync(() -> {
                        started.countDown();
                        try {
                            release.await();
                        } catch (InterruptedException ex) {
                            Thread.currentThread().interrupt();
                            return "interrupted";
                        }
                        return "slow-finished";
                    }, shared);

            started.await(); // the sole worker is occupied by the slow task

            CompletableFuture<String> quick =
                    CompletableFuture.supplyAsync(
                            () -> "quick-finished", shared);

            System.out.println("quickBeforeRelease=" + quick.isDone());
            release.countDown();
            System.out.println("slow=" + slow.join());
            System.out.println("quick=" + quick.join());
        } finally {
            release.countDown();
            shared.shutdown();
            if (!shared.awaitTermination(5, TimeUnit.SECONDS)) {
                shared.shutdownNow();
            }
        }
    }
}
~~~

Run:

~~~bash
javac SharedExecutorContentionDemo.java
java SharedExecutorContentionDemo
~~~

Output:

~~~text
quickBeforeRelease=false
slow=slow-finished
quick=quick-finished
~~~

The `slow` task holds the worker via the latch; `quick` is submitted to **the same executor**, yet no free worker exists, so it cannot complete before `main` opens the latch. Afterward both tasks finish. `quick.isDone()` before `release.countDown()` is `false` because the pool has exactly one worker and `slow` is still holding it.

This experiment **neither uses nor modifies the common pool**, avoiding slowing down other libraries in the same JVM during a demo. It illustrates the principle of resource sharing; `ForkJoinPool.commonPool()` has multiple workers and work-stealing, so evaluate it using real metrics and workloads rather than extrapolating exact speeds from a single-worker experiment.

## 7. Spring Integration: Explicitly Passing ThreadPoolTaskExecutor

Spring's `ThreadPoolTaskExecutor` acts as a `TaskExecutor` and can also be passed as a `java.util.concurrent.Executor` to `CompletableFuture.supplyAsync(supplier, executor)`. The recommendation is to configure **shared beans** per workload type, such as `ioExecutor` for bounded synchronous I/O work.

### 7.1. Spring Framework 6.1.3 Maven Project

The example below uses **plain Spring Framework**, requiring no Spring Boot, `@EnableAsync`, or Spring AOP proxies: it calls `CompletableFuture.supplyAsync` directly with an injected executor. Structure:

~~~text
spring-supply-demo/
├── pom.xml
└── src/
    └── main/
        └── java/
            └── demo/
                ├── IoExecutorConfig.java
                ├── DocumentService.java
                └── SpringSupplyAsyncDemo.java
~~~

`pom.xml`:

~~~xml
<project xmlns="http://maven.apache.org/POM/4.0.0"
         xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
         xsi:schemaLocation="http://maven.apache.org/POM/4.0.0 https://maven.apache.org/xsd/maven-4.0.0.xsd">
    <modelVersion>4.0.0</modelVersion>
    <groupId>demo</groupId>
    <artifactId>spring-supply-demo</artifactId>
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
                    <mainClass>demo.SpringSupplyAsyncDemo</mainClass>
                </configuration>
            </plugin>
        </plugins>
    </build>
</project>
~~~

`src/main/java/demo/IoExecutorConfig.java`:

~~~java
package demo;

import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.beans.factory.annotation.Qualifier;
import org.springframework.scheduling.concurrent.ThreadPoolTaskExecutor;

@Configuration
public class IoExecutorConfig {

    @Bean("ioExecutor")
    public ThreadPoolTaskExecutor ioExecutor() {
        ThreadPoolTaskExecutor pool = new ThreadPoolTaskExecutor();
        pool.setCorePoolSize(2);
        pool.setMaxPoolSize(4);
        pool.setQueueCapacity(20);
        pool.setThreadNamePrefix("io-");
        return pool; // Spring container manages init/shutdown
    }

    @Bean
    public DocumentService documentService(
            @Qualifier("ioExecutor") ThreadPoolTaskExecutor executor) {
        return new DocumentService(executor);
    }
}
~~~

`src/main/java/demo/DocumentService.java`:

~~~java
package demo;

import java.util.concurrent.CompletableFuture;
import java.util.concurrent.Executor;

public final class DocumentService {

    private final Executor executor;

    public DocumentService(Executor executor) {
        this.executor = executor;
    }

    public CompletableFuture<String> load(String documentId) {
        return CompletableFuture.supplyAsync(() -> {
            boolean isolated = Thread.currentThread()
                    .getName().startsWith("io-");
            return "document:" + documentId + "|isolated=" + isolated;
        }, executor);
    }
}
~~~

`src/main/java/demo/SpringSupplyAsyncDemo.java`:

~~~java
package demo;

import org.springframework.context.annotation.AnnotationConfigApplicationContext;

public final class SpringSupplyAsyncDemo {

    public static void main(String[] args) {
        try (AnnotationConfigApplicationContext context =
                     new AnnotationConfigApplicationContext(
                             IoExecutorConfig.class)) {

            DocumentService service =
                    context.getBean(DocumentService.class);

            System.out.println(service.load("A42").join());
        }
    }
}
~~~

Run inside `spring-supply-demo`:

~~~bash
mvn -q compile exec:java
~~~

Output printed by Java:

~~~text
document:A42|isolated=true
~~~

**Why does this example run through the Spring executor?** `DocumentService.load` **passes the `executor` field** into the two-argument overload of `supplyAsync`; that field comes from the Spring-managed `ioExecutor` bean. `ThreadPoolTaskExecutor` creates workers with the `io-` prefix. When the supplier runs, it checks the active thread and returns `isolated=true`.

There is no `@Async` on `DocumentService.load`, because this lesson intentionally uses the **Java `CompletableFuture` API** instead of Spring's proxy-based asynchronous method invocation. `@EnableAsync` is not required to call `supplyAsync(..., executor)` directly. `try-with-resources` closes the Spring context, causing the container to clean up the executor bean.

**Do not copy pool sizes into production mechanically.** `core=2`, `max=4`, `queueCapacity=20` simply demonstrate bounding workers and queues. Tune them to load, task duration, downstream connection counts, timeouts, and SLAs.

### 7.2. Using the TaskExecutor Interface in a Service

`org.springframework.core.task.TaskExecutor` **extends `java.util.concurrent.Executor`**, so it can be passed directly as the second argument of `CompletableFuture.supplyAsync`, even though the Spring interface only defines `execute(Runnable)`:

~~~java
// Fragment when taskExecutor of type TaskExecutor is injected:
CompletableFuture<String> future =
        CompletableFuture.supplyAsync(() -> "ok", taskExecutor);
~~~

If the variable is typed only as `TaskExecutor`, you cannot call `taskExecutor.submitCompletable(...)` because that method belongs to `AsyncTaskExecutor`, yet **`supplyAsync(..., taskExecutor)` is still valid** since it only needs `Executor`. This is useful when integrating with Spring 5.x, where `submitCompletable` does not exist.

**Be careful:** `SyncTaskExecutor` runs tasks **synchronously on the caller thread**; if you pass a synchronous executor, the future may complete immediately, meaning `supplyAsync` ran synchronously. Do not infer "non-blocking to caller" solely from the `CompletableFuture` type. Check the bean's actual implementation.

## 8. @Async and supplyAsync Do Not Share the Same Executor Selection Mechanism

Spring's `@Async` uses an interceptor/proxy mechanism when `@EnableAsync` is active in the application context. An `@Async` method's executor can be chosen by `@Async("name")`, `AsyncConfigurer`, or Spring bean resolution. By contrast, `CompletableFuture.supplyAsync(supplier)` is a **static JDK call** that does not read `@Async` or Spring configuration.

An anti-example:

~~~java
// Fragment in a Spring service, assuming @EnableAsync is enabled:
@Async("springExecutor")
public CompletableFuture<String> calculate() {
    return CompletableFuture.supplyAsync(
            () -> blockingLookup());
}
~~~

This snippet is **not a standalone program**; it requires `blockingLookup()` and bean `springExecutor`. The method is dispatched by Spring `@Async` onto `springExecutor`, **yet** inside the method it calls `supplyAsync` **without passing an executor**. Consequently, the **inner `Supplier`** is submitted onward to the common pool (or the JDK's fallback path). Having `@Async("springExecutor")` **does not make an inner `supplyAsync` inherit the Spring pool**.

Normally pick one of two clear strategies:

1. **Use `@Async("springExecutor")`:** the target method computes on the Spring worker and returns `CompletableFuture.completedFuture(result)`, letting the proxy represent asynchronous execution.
2. **Use `CompletableFuture.supplyAsync(supplier, springExecutor)`:** a regular method (no `@Async` needed) returns a future submitted directly to the chosen executor.

If you genuinely need both scheduling layers, justify it architecturally and bound resources; do not accidentally introduce **double scheduling** into the common pool and guess wrong about which thread runs I/O.

## 9. Thread Context: Transactions, MDC, SecurityContext, ThreadLocal

Spring commonly stores data bound to **the current thread** such as logging MDC, `SecurityContext`, request attributes, and transaction context. Offloading work to the common pool does not automatically carry all of that data over. Some frameworks provide propagation mechanisms; depending on version/config, do not assume they are present automatically.

Risks:

- **Logs lose correlation IDs:** MDC set on the request thread is missing on the worker, fragmenting traces.
- **Empty or wrong `SecurityContext`:** if the framework relies on per-thread security context and you do not propagate it, authorization checks inside workers lack context.
- **Transactions do not span async tasks:** a transaction bound to the caller thread does not automatically extend to a worker. The task needs its own proper transaction boundary when accessing the database.
- **`ThreadLocal` data leaks:** if you manually set context on pool workers without cleaning up in `finally`, reused workers can carry stale context into subsequent tasks.

Recommended practice: **pass immutable business data explicitly** whenever possible; if context propagation is needed, use framework-supported propagation, `TaskDecorator`, or appropriate executor wrappers. With `ThreadPoolTaskExecutor.setTaskDecorator(...)`, note that the decorator may receive a wrapper task created by `CompletableFuture` rather than the raw `Supplier`; test end-to-end that context is set **and cleared** at the right time.

Do not mutate **common pool worker** contexts by storing global `ThreadLocal` values as a quick fix; those workers can serve unrelated parts of the application.

## 10. Exceptions, Rejection, Timeouts, and Cancellation

### 10.1. Errors in Supplier: Future Completes Exceptionally

If `Supplier.get()` throws `IllegalArgumentException` or another runtime exception **after the executor accepts the task**, the `CompletableFuture` completes exceptionally.

~~~java
CompletableFuture<Integer> failed =
        CompletableFuture.supplyAsync(() -> {
            throw new IllegalArgumentException("invalid");
        }, executor);

// Fragment with an existing executor of type Executor.
CompletableFuture<Integer> recovered =
        failed.exceptionally(error -> -1);
~~~

Calling `failed.join()` without recovery typically throws `CompletionException` wrapping the original cause; `failed.get()` throws `ExecutionException` (checked). Use `handle` or `exceptionally` to substitute a fallback when **business rules allow**, rather than swallowing all errors blindly.

`Supplier<T>` differs from `Callable<T>` in that `Supplier.get()` **declares no checked exceptions**. If a `Supplier` performs I/O that throws a checked exception, catch and wrap/convert it or design a compatible API; you cannot throw undeclared checked exceptions directly from the lambda.

### 10.2. Rejection at Submission Time: No Future Yet

With `CompletableFuture.supplyAsync(supplier, executor)`, the passed executor can **reject** the task right inside the underlying `execute` call. For instance, when `ThreadPoolTaskExecutor` is full or shut down, the call can throw **`TaskRejectedException`** (subclass of `RejectedExecutionException`) **before returning a `Future`**. Thus `future.exceptionally(...)` cannot handle a call that never produced a `Future`.

~~~java
// Fragment inside a service with field ioExecutor of type ThreadPoolTaskExecutor.
// Surrounding method has return type CompletableFuture<String>.
try {
    return CompletableFuture.supplyAsync(
            () -> loadFromRemote(), ioExecutor);
} catch (org.springframework.core.task.TaskRejectedException ex) {
    // Decide overload response / fallback per business contract.
    return CompletableFuture.failedFuture(ex);
}
~~~

`CompletableFuture.failedFuture(ex)` was added in Java 9+, so it is valid on Java 17. Here synchronous rejection is intentionally converted into a failed future so callers keep the same return type. Not every case should do this: a synchronous HTTP API may want to fail fast, while a `Future`-returning API may expect a failed future. What matters is **never ignoring rejections**.

### 10.3. Future Timeouts Do Not Stop I/O Automatically

~~~java
// Fragment with an existing future and TimeUnit imported:
future.orTimeout(2, TimeUnit.SECONDS);
~~~

`orTimeout` makes the `Future` complete exceptionally if no result arrives on time, **yet does not guarantee stopping a running `Supplier` or network request**. `completeOnTimeout` likewise only provides a fallback result upon expiration; real I/O may continue and produce side effects.

`CompletableFuture.cancel(true)` is primarily an **exceptional completion** per contract; `mayInterruptIfRunning` does not directly interrupt workers the way many `FutureTask` implementations do. To bound I/O lifetimes, configure HTTP client, database, and queue timeouts plus cooperative cancellation at the resource layer.

### 10.4. Do Not Wait for Dependent Work Inside the Same Small Pool

Task A runs on a single-worker executor, submits task B to **the same executor**, and calls `B.join()`. A holds the sole worker waiting for B, while B sits in the queue with no worker to run it -> **thread-starvation deadlock**. Do not treat `supplyAsync` or the common pool as magic that eliminates deadlocks. Compose steps with `thenCompose`/`thenCombine` or design appropriate executors and wait boundaries.

## 11. Choosing Executors by Workload and Measurement

| Workload / requirement | Recommended handling |
| --- | --- |
| CPU-bound, few tasks, independent, short | Common pool can be acceptable if no isolation is needed; measure before deciding |
| Critical CPU-bound computation with its own SLA | Dedicated executor with bounded concurrency to avoid unintended contention |
| Blocking I/O: synchronous HTTP/JDBC/SDK | Dedicated bounded I/O executor with realistic downstream timeouts |
| Multiple requests/tenants with varying priorities | Consider per-workload/tenant pools, rate limits, semaphores, or queues |
| Very short work, stage only transforms a value | `thenApply` may suffice without rescheduling |
| Async stage requiring specific context or pool | `thenApplyAsync(fn, executor)`, `handleAsync(fn, executor)`, etc. |
| Spring `@Async` using a configured executor | Invoke via proxy; never assume inner `supplyAsync` inherits the pool |
| Tasks that must never be lost | Durable queue/outbox and acknowledgments; Futures/ThreadPools are not durable queues |

### Monitoring

- For Spring `ThreadPoolTaskExecutor`, track `getPoolSize()`, `getActiveCount()`, and `getQueueSize()` over time, not just a single snapshot.
- Measure **queue wait time**, task execution duration, throughput, rejection rate, timeouts, and p95/p99 latency.
- For the common pool, you can inspect `ForkJoinPool.commonPool().getPoolSize()`, `getActiveThreadCount()`, `getQueuedSubmissionCount()`, and `getStealCount()`. These are **observational/approximate metrics**, not proof that you own the pool or can attribute every task to one module.
- Attach executor names and correlation IDs when tracing dedicated pools; avoid asserting fixed thread names in tests when the runtime may switch threads.
- Test under realistic load—including **long tasks, slow I/O, shutdown, and rejections**—before changing global common-pool parallelism.

### Code Review Checklist

1. Find `CompletableFuture.supplyAsync(...)` and `runAsync(...)` calls missing an `Executor` argument.
2. For each call, classify CPU-bound / I/O-bound / blocking behavior / task duration / SLA.
3. Identify the executor's **owner**, initialization, worker/queue limits, and shutdown behavior.
4. Move tasks needing isolation onto overloads taking an `Executor`; in Spring, use shared configured beans.
5. Audit **every `...Async` stage**: `thenApplyAsync(fn)` does not inherit the previous step's pool. Pass an executor when needed.
6. Ensure proper context/transaction/security propagation and cleanup; never rely on caller `ThreadLocal` state.
7. Handle exceptions **inside `Supplier`** separately from rejections **at submission time**.
8. Configure timeouts for real I/O; never use `orTimeout`/`cancel` as proof that underlying work stopped.
9. Never call `join` on a subtask inside a worker of a small pool running the parent task.
10. Use monitoring and load tests to validate executor limits; do not merely increase worker counts when downstream is the bottleneck.

## 12. Common Mistakes

**"Having `@Async` or a `ThreadPoolTaskExecutor` bean means `supplyAsync(supplier)` automatically picks the Spring pool."** False: the static JDK call does not query the Spring container.

**"Creating a CompletableFuture spawns a new thread."** False: normally a task is run by an executor whose workers are reused. The JDK has a fallback that creates a thread per task when common pool parallelism is below 2, which is not general behavior to rely on.

**"Because the first task used `ioExecutor`, `thenApplyAsync(fn)` uses `ioExecutor` too."** False: an Async stage without an executor uses the default async facility, usually the common pool.

**"The common pool can never run blocking tasks."** False: it can run them, yet it is shared and risks hurting throughput/latency; evaluate blocking behavior and resource limits.

**"Calling `join()` does not block because `CompletableFuture` is async."** False: `join()` blocks the caller until the future completes.

**"Increasing common pool parallelism fixes every bottleneck."** False: it is a JVM-wide setting and does not resolve DB, HTTP, memory, or task-design limits.

**"Enabling a timeout on `CompletableFuture` aborts the HTTP request."** False: a future timeout does not guarantee aborting underlying I/O operations.

**"`exceptionally(...)` catches every error, including executor rejection before returning a future."** False: rejection can be thrown synchronously before any future exists.

**"Passing any `TaskExecutor` always runs work in the background."** False: `SyncTaskExecutor` can run directly on the caller thread.

**"Creating a dedicated thread pool per request isolates better."** False in most web apps: excessive threads/pools and missing lifecycle cleanup create severe resource risks.

## 13. Self-Check Questions

**Question 1.** Where will `CompletableFuture.supplyAsync(() -> load())` run in an application that defines a Spring bean `ioExecutor`?  
**Answer:** On the JDK's default async facility (the common pool when parallelism is at least 2, otherwise a new thread per task); it does not automatically select `ioExecutor`.

**Question 2.** How do you make `load()` run on Spring's `ThreadPoolTaskExecutor`?  
**Answer:** Pass the executor bean as the second argument: `CompletableFuture.supplyAsync(() -> load(), ioExecutor)`.

**Question 3.** Why can `thenApplyAsync(fn)` placed after `supplyAsync(supplier, ioExecutor)` go back to the common pool?  
**Answer:** A `thenApplyAsync` stage without an executor uses the default async facility; the executor passed to the previous stage is not inherited.

**Question 4.** Does `thenApply(fn)` guarantee running on `ioExecutor`?  
**Answer:** No. Non-async completions may run on the thread completing the future or a thread invoking completion, depending on timing.

**Question 5.** Why can putting thousands of synchronous HTTP calls into the common pool cause trouble?  
**Answer:** Shared workers stay occupied during blocking I/O, forcing other unrelated tasks sharing that pool to wait; workload isolation, quotas, and monitoring become difficult.

**Question 6.** If `CompletableFuture.supplyAsync(supplier, ioExecutor)` is rejected by the pool, can `future.exceptionally(...)` catch it?  
**Answer:** Not if the submission call throws synchronously before returning a future; catch at the call site and decide whether to fail fast or return a failed future.

**Question 7.** Does `orTimeout(2, SECONDS)` guarantee interrupting a DB query after 2 seconds?  
**Answer:** No. It changes the future's state on timeout, while the DB query needs timeouts/cancellation at the JDBC/database layer.

**Question 8.** When can using the common pool be acceptable?  
**Answer:** For small, short, non-blocking, CPU-bound tasks requiring no isolation, after measuring interaction with other workloads.

## Official References

- [Java SE 17 — CompletableFuture Javadoc](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/concurrent/CompletableFuture.html): `supplyAsync` overloads, default async facility policy, `thenApplyAsync`, errors, timeouts, and cancellation.
- [Java SE 17 — ForkJoinPool Javadoc](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/concurrent/ForkJoinPool.html): common pool, parallelism, work-stealing, managed blocking, and metrics.
- [Java SE 17 — Executor Javadoc](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/concurrent/Executor.html): `execute(Runnable)` contract and differences across implementations.
- [Spring Framework 6.1.3 — ThreadPoolTaskExecutor Javadoc](https://docs.spring.io/spring-framework/docs/6.1.3/javadoc-api/org/springframework/scheduling/concurrent/ThreadPoolTaskExecutor.html): executor bean, core/max/queue, `TaskDecorator`, lifecycle management, and rejections.
- [Spring Framework 6.1.3 — AsyncTaskExecutor Javadoc](https://docs.spring.io/spring-framework/docs/6.1.3/javadoc-api/org/springframework/core/task/AsyncTaskExecutor.html): Spring's `submit`/`submitCompletable` and the interface extending `TaskExecutor`.
- [Spring Framework Reference — Task Execution and Scheduling](https://docs.spring.io/spring-framework/reference/integration/scheduling.html): `TaskExecutor` implementations, `@Async`, executor selection, and application constraints.

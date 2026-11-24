# Avoiding Double Task Submission When Using Both `@Async` and `supplyAsync()`

**Module:** Spring Framework - concurrency  
**Knowledge Group:** CompletableFuture Composition  
**Goal:** Distinguish the two scheduling mechanisms `@Async` and `CompletableFuture.supplyAsync()`, avoid creating an outer task merely to wait on an inner task, pick the right executor, and still compose processing steps with `CompletableFuture` in a controlled manner.

## 1. Why Using Both Async APIs Together Can Backfire

Consider a Spring service with `@EnableAsync` enabled:

```java
@Async("businessExecutor")
public CompletableFuture<String> create(String id) {
    return CompletableFuture.supplyAsync(
            () -> createReportBlocking(id));
}
```

This is an **illustrative snippet**, not a standalone program: `createReportBlocking` and the `"businessExecutor"` bean must exist. One call through the Spring proxy here performs **two task submissions**:

1. Spring AOP intercepts `@Async("businessExecutor")` and submits the **method invocation** to `businessExecutor`.
2. When a worker from that pool runs the method, `CompletableFuture.supplyAsync(...)` submits the **supplier** onward to `CompletableFuture`'s default executor, usually `ForkJoinPool.commonPool()`.

```text
Caller / HTTP thread
      |
      | calls Spring proxy
      v
@Async("businessExecutor")
      |
      | SUBMIT #1
      v
Worker of businessExecutor (OUTER)
      |
      | body calls supplyAsync
      | SUBMIT #2
      v
Worker of commonPool (INNER)
      |
      | runs createReportBlocking(id)
      v
Inner Future completes
      |
      v
Future provided by Spring proxy completes
```

**Two task submissions do not mean the business logic runs twice.** In the example, the `createReportBlocking(id)` supplier typically still runs **once per accepted invocation**. The waste lies in **two scheduling hops**, extra queues/threads, and the possibility of an outer worker waiting on an inner worker.

In Spring Framework **6.x**, `AsyncExecutionInterceptor` executes the target method inside a task on the outer executor. If the target method returns a `Future`, the interceptor may call `Future.get()` to retrieve its value while executing the outer task. Consequently, if the inner future is not yet complete, **the outer worker may be held waiting**. It is not equivalent to non-blocking `thenCompose`.

Consequences:

- The outer worker stays busy without doing useful work, so throughput can drop.
- Blocking I/O accidentally runs on `ForkJoinPool.commonPool()` instead of a bounded I/O pool.
- Tracing/MDC and `ThreadLocal` values can be lost across the second boundary.
- Errors, rejections, and timeouts must be understood at **two** layers.
- If both submit to the same small pool, **starvation or deadlock** can occur.

Before adding `supplyAsync` inside an already `@Async` method, ask: **"What real work is the outer layer doing, or is it just creating another Future and waiting?"**

## 2. Three Commonly Confused Mechanisms

| Pattern | Submits a new task? | Who chooses the executor? | Effect |
| --- | --- | --- | --- |
| `@Async("pool")` | Yes, if the call goes through the async proxy | Spring `@Async`/qualifier | Offloads method invocation to a pool |
| `CompletableFuture.completedFuture(x)` | **No** | No executor needed | Creates a Future already holding result `x` |
| `CompletableFuture.supplyAsync(fn)` | Yes | Usually JDK's `ForkJoinPool.commonPool()` | Hands supplier to the JDK default executor |
| `CompletableFuture.supplyAsync(fn, executor)` | Yes | The passed executor | Hands supplier to the specified pool |
| `thenApply(fn)` | Does not submit a separate task by default | Completion thread or callback-registering thread | Transforms an existing value |
| `thenApplyAsync(fn, executor)` | Yes, for the callback | Specified executor | Moves heavy transformation to a pool |
| `thenCompose(fn)` | Does not add a worker just to wait | Governed by the Future `fn` returns | Chains work that already has an async contract |

`@Async` is not another name for `CompletableFuture.supplyAsync`. `@Async` is **Spring proxy advice**; `supplyAsync` is a **JDK API**. Having a Spring bean named `taskExecutor` or `applicationTaskExecutor`, or implementing `AsyncConfigurer`, **does not** automatically change the executor of a static `CompletableFuture.supplyAsync` call with no executor argument.

`completedFuture` does not make work "run in the background" either. It only fits inside a method **already dispatched onto a worker by the `@Async` proxy**, or when the result is genuinely ready.

## 3. Pattern A — Single Scheduling Managed by Spring

When a service method performs synchronous/blocking work yet the caller wants a `Future`, let **Spring own the thread handoff**:

```java
@Service
public class ReportService {

    @Async("reportExecutor")
    public CompletableFuture<String> create(String reportId) {
        String result = createReportBlocking(reportId);
        return CompletableFuture.completedFuture(result);
    }
}
```

This is an **illustrative class**; it requires Spring imports, `CompletableFuture`, `createReportBlocking`, and bean `"reportExecutor"`. Flow:

```text
caller -> @Async proxy -> reportExecutor worker
                                   |
                                   | createReportBlocking(reportId)
                                   v
                       completedFuture(result)
                                   |
                                   v
                         caller's Future
```

**Only one submission.** `createReportBlocking()` runs directly on the worker chosen by Spring, and `completedFuture` creates no second task.

According to Spring's `@Async` Javadoc, when the target method declares a `CompletableFuture<T>` return type, the target can return a **temporary future** already holding the computed result (commonly `CompletableFuture.completedFuture(result)`). The caller receives an **actual asynchronous Future** supplied by the Spring proxy. The two `Future` objects do not have to be the same instance.

If the method throws an exception, the caller's `Future` completes exceptionally. If the executor rejects the invocation right when submitting, the caller may receive `TaskRejectedException` at the submission boundary. Business errors after task acceptance and rejection before acceptance are **two distinct situations**.

**Good fit:** services with existing computations, synchronous JDBC/HTTP clients, or CPU work routed to an appropriate executor. Blocking operations still require timeouts, connection limits, and overload protection; `@Async` does not turn them into non-blocking I/O.

## 4. Pattern B — No `@Async`, Dispatching a Supplier via JDK API

If the codebase structures steps with `CompletableFuture` instead of annotations, let a **normal method** return a `Future`:

```java
@Service
public class ReportWorkflow {

    private final Executor reportExecutor;

    public ReportWorkflow(
            @Qualifier("reportExecutor") Executor reportExecutor) {
        this.reportExecutor = reportExecutor;
    }

    public CompletableFuture<String> create(String reportId) {
        return CompletableFuture.supplyAsync(
                () -> createReportBlocking(reportId),
                reportExecutor);
    }
}
```

This is an illustrative class: `createReportBlocking` is undefined; requires `@Service`, `@Qualifier`, `Executor`, and `CompletableFuture` imports. Flow:

```text
caller -> create(...)  [no @Async]
               |
               | supplyAsync(..., reportExecutor)
               v
        reportExecutor worker
               |
               v
        createReportBlocking(...)
```

**Also only one submission.** `create` is invoked directly on the caller thread, yet it merely creates a future and submits the supplier, so it typically returns quickly. The business work runs on the worker.

You can pick Pattern A or B depending on architecture. What matters is **not accidentally combining both when the outer layer does no useful work**.

If a method calls `CompletableFuture.supplyAsync` **without passing an executor**, it normally sends work to `ForkJoinPool.commonPool()` with certain fallbacks depending on parallelism; it **does not** automatically use `@Async("reportExecutor")` or a Spring-managed executor bean. For blocking JDBC, synchronous HTTP, or work needing isolation, choose an explicit executor, bounded queues, and downstream limits.

## 5. Pattern C — Already-Async Data: Compose Futures Without an Outer Worker

Suppose two clients already return `CompletableFuture<Integer>`:

```java
@Service
public class QuoteService {

    private final PriceClient priceClient;
    private final ShippingClient shippingClient;

    public QuoteService(
            PriceClient priceClient,
            ShippingClient shippingClient) {
        this.priceClient = priceClient;
        this.shippingClient = shippingClient;
    }

    public CompletableFuture<Integer> quote(
            String sku, String address) {
        CompletableFuture<Integer> price =
                priceClient.fetchAsync(sku);
        CompletableFuture<Integer> shipping =
                shippingClient.fetchAsync(address);

        return price.thenCombine(shipping, Integer::sum);
    }
}
```

The snippet above is an **illustrative class**: `PriceClient`/`ShippingClient` are application dependencies. Both client calls may use true non-blocking I/O or have their own pools. `QuoteService.quote` does not need an `@Async` annotation simply because its return type is `CompletableFuture`: it already gets an async contract from the two sources.

When B needs A's result:

```java
public CompletableFuture<Receipt> submitOrder(String id) {
    return priceClient.fetchAsync(id)
            .thenCompose(price -> receiptClient.createAsync(id, price));
}
```

This illustrative snippet needs `Receipt`, `receiptClient`, and `priceClient`. `thenCompose` chains a `CompletionStage` returned by the callback without writing `.get()`/`.join()` to block a thread in the continuation.

**Do not misunderstand:** `thenCompose` does not make B run asynchronously if `receiptClient.createAsync` does not actually initiate async work. It simply expresses the dependency and flattens the `Future` instead of creating `CompletableFuture<CompletableFuture<T>>`.

## 6. Why `@Async` and `supplyAsync` on the Same Pool Can Deadlock

Intentionally flawed example, do not use in production:

```java
@Bean("tinyPool")
public ThreadPoolTaskExecutor tinyPool() {
    ThreadPoolTaskExecutor e = new ThreadPoolTaskExecutor();
    e.setCorePoolSize(1);
    e.setMaxPoolSize(1);
    e.setQueueCapacity(10);
    return e;
}

@Async("tinyPool")
public CompletableFuture<String> dangerous() {
    return CompletableFuture.supplyAsync(
            () -> slowBusinessWork(),
            tinyPool);
}
```

These are **two illustrative snippets** belonging in appropriate Spring classes, not a standalone compilable file; they require bean/field `tinyPool` and method `slowBusinessWork`. If the call goes through the Spring async proxy in **Spring Framework 6.x**, the flow can be:

1. The proxy submits the **OUTER** task to `tinyPool`.
2. The sole worker runs the target method and calls `supplyAsync(..., tinyPool)`.
3. The **INNER** task enters the queue because the worker is busy.
4. The target method returns the inner `CompletableFuture<String>`.
5. The async interceptor waits on `Future.get()` inside the OUTER worker to obtain the value.
6. INNER needs the worker to run, yet the sole worker is still waiting on INNER.

```text
tinyPool:
  worker-1: OUTER -> Future.get(INNER) -> waiting...
  queue:    INNER -> waiting for worker-1
```

The result can be **starvation/deadlock** with no progress. With 2, 4, or 8 workers, the bug may only appear when enough concurrent outer tasks occupy every worker while all inner tasks sit in the queue. Thus a single successful test request does not prove the design safe.

Bumping `maxPoolSize` to hide the bug is not a sound fix: when a burst exceeds the new limit, the symptom returns. `Future.get(timeout)` in the caller also does not guarantee releasing the worker the Spring interceptor is using to wait.

**Fix:** remove one layer. If `slowBusinessWork()` is truly synchronous, use `@Async + completedFuture`. If you want to schedule explicitly with `supplyAsync`, remove `@Async` from the method.

## 7. Standalone Java 17 Demo: Counting Submissions vs. Actual Business Runs

This JDK-only program distinguishes "two submissions" from "business logic running twice." It uses **two distinct executors** to avoid deadlocking in the demo. On the double path, the outer worker **explicitly calls `join()`** to model an outer task waiting on an inner task; this is an **illustrative model**, not a full simulator of Spring AOP.

Save as **`DoubleSchedulingJdkDemo.java`**:

```java
import java.util.concurrent.CompletableFuture;
import java.util.concurrent.Executor;
import java.util.concurrent.ExecutorService;
import java.util.concurrent.Executors;
import java.util.concurrent.TimeUnit;
import java.util.concurrent.atomic.AtomicInteger;

public class DoubleSchedulingJdkDemo {

    static final class CountingExecutor implements Executor, AutoCloseable {
        private final ExecutorService delegate =
                Executors.newSingleThreadExecutor();
        private final AtomicInteger submissions = new AtomicInteger();

        @Override
        public void execute(Runnable task) {
            submissions.incrementAndGet();
            delegate.execute(task);
        }

        int count() {
            return submissions.get();
        }

        @Override
        public void close() throws InterruptedException {
            delegate.shutdown();
            if (!delegate.awaitTermination(5, TimeUnit.SECONDS)) {
                delegate.shutdownNow();
            }
        }
    }

    public static void main(String[] args) throws Exception {
        try (CountingExecutor outer = new CountingExecutor();
             CountingExecutor inner = new CountingExecutor()) {

            AtomicInteger singleRuns = new AtomicInteger();
            AtomicInteger doubleRuns = new AtomicInteger();

            CompletableFuture<String> single =
                    CompletableFuture.supplyAsync(() -> {
                        singleRuns.incrementAndGet();
                        return "done";
                    }, outer);

            CompletableFuture<String> doubleScheduled =
                    CompletableFuture.supplyAsync(() ->
                            CompletableFuture.supplyAsync(() -> {
                                doubleRuns.incrementAndGet();
                                return "done";
                            }, inner).join(), outer);

            System.out.println("single=" + single.join());
            System.out.println("double=" + doubleScheduled.join());
            System.out.println("singleRuns=" + singleRuns.get());
            System.out.println("doubleRuns=" + doubleRuns.get());
            System.out.println("outerSubmissions=" + outer.count());
            System.out.println("innerSubmissions=" + inner.count());
        }
    }
}
```

Run with JDK 17 or newer:

```bash
javac DoubleSchedulingJdkDemo.java
java DoubleSchedulingJdkDemo
```

**Exact stdout when the program completes normally:**

```text
single=done
double=done
singleRuns=1
doubleRuns=1
outerSubmissions=2
innerSubmissions=1
```

Explanation:

- There are **two logical requests** in the program: `single` and `doubleScheduled`.
- Each request executes the business work exactly once (`singleRuns=1`, `doubleRuns=1`).
- The outer executor receives **two** tasks—one per logical request.
- The inner executor receives **one** task belonging solely to the `doubleScheduled` path.
- Total tasks submitted is **three**, even though business work executed only twice. Double scheduling on the second request does not mean duplicate side effects.

`CompletableFuture.join()` in `main` only awaits the final outputs for test printing. The `join()` **inside the outer task** on the double path is what simulates occupying a worker while waiting for work on another pool.

Note that `Executors.newSingleThreadExecutor()` has an unbounded memory queue relative to processing capacity; this is only a short example, not a template for high-load production executors.

## 8. Complete Spring Boot Example: Single-Layer, Two-Layer, and Pure Future Pipeline

The example uses **Java 17+**, **Spring Boot 3.5.7** with Spring Framework 6.2.x, and Maven, with two independent `ThreadPoolTaskExecutor` beans to observe boundaries:

- `outerExecutor` with thread prefix `outer-`.
- `innerExecutor` with thread prefix `inner-`.
- Method `singleDispatch` uses `@Async` + `completedFuture`.
- Method `doubleDispatch` intentionally uses `@Async` + `supplyAsync` to demonstrate two layers; **not recommended for production**.
- Method `composeWithoutOuterAsync` has no `@Async`; it submits two independent suppliers and combines them with `thenCombine`.

### 8.1. Project Structure

```text
double-dispatch-spring/
├── pom.xml
└── src/main/java/com/example/doubledispatch/
    ├── DoubleDispatchApplication.java
    ├── ExecutorConfiguration.java
    └── JobService.java
```

### 8.2. `pom.xml`

```xml
<project xmlns="http://maven.apache.org/POM/4.0.0"
         xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
         xsi:schemaLocation="http://maven.apache.org/POM/4.0.0 https://maven.apache.org/xsd/maven-4.0.0.xsd">
    <modelVersion>4.0.0</modelVersion>

    <parent>
        <groupId>org.springframework.boot</groupId>
        <artifactId>spring-boot-starter-parent</artifactId>
        <version>3.5.7</version>
        <relativePath/>
    </parent>

    <groupId>com.example</groupId>
    <artifactId>double-dispatch-spring</artifactId>
    <version>1.0.0</version>

    <properties>
        <java.version>17</java.version>
    </properties>

    <dependencies>
        <dependency>
            <groupId>org.springframework.boot</groupId>
            <artifactId>spring-boot-starter-aop</artifactId>
        </dependency>
    </dependencies>

    <build>
        <plugins>
            <plugin>
                <groupId>org.springframework.boot</groupId>
                <artifactId>spring-boot-maven-plugin</artifactId>
            </plugin>
        </plugins>
    </build>
</project>
```

`spring-boot-starter-aop` brings in the proxy/AOP support needed for the example. This is a CLI program, requiring no web server.

### 8.3. `src/main/java/com/example/doubledispatch/ExecutorConfiguration.java`

```java
package com.example.doubledispatch;

import java.util.concurrent.ThreadPoolExecutor;

import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.scheduling.annotation.EnableAsync;
import org.springframework.scheduling.concurrent.ThreadPoolTaskExecutor;

@Configuration
@EnableAsync
public class ExecutorConfiguration {

    @Bean("outerExecutor")
    public ThreadPoolTaskExecutor outerExecutor() {
        ThreadPoolTaskExecutor e = new ThreadPoolTaskExecutor();
        e.setCorePoolSize(2);
        e.setMaxPoolSize(2);
        e.setQueueCapacity(8);
        e.setThreadNamePrefix("outer-");
        e.setRejectedExecutionHandler(new ThreadPoolExecutor.AbortPolicy());
        return e;
    }

    @Bean("innerExecutor")
    public ThreadPoolTaskExecutor innerExecutor() {
        ThreadPoolTaskExecutor e = new ThreadPoolTaskExecutor();
        e.setCorePoolSize(2);
        e.setMaxPoolSize(2);
        e.setQueueCapacity(8);
        e.setThreadNamePrefix("inner-");
        e.setRejectedExecutionHandler(new ThreadPoolExecutor.AbortPolicy());
        return e;
    }
}
```

Here two pools are separated for safe experimentation; in production, create a second pool only when a distinct workload genuinely requires separation. Spring manages `ThreadPoolTaskExecutor` lifecycles through beans; bounded queues and `AbortPolicy` surface overload.

### 8.4. `src/main/java/com/example/doubledispatch/JobService.java`

```java
package com.example.doubledispatch;

import java.util.concurrent.CompletableFuture;
import java.util.concurrent.Executor;

import org.springframework.beans.factory.annotation.Qualifier;
import org.springframework.scheduling.annotation.Async;
import org.springframework.stereotype.Service;

@Service
public class JobService {

    private final Executor innerExecutor;

    public JobService(@Qualifier("innerExecutor") Executor innerExecutor) {
        this.innerExecutor = innerExecutor;
    }

    // Single submission: business logic runs inside Spring's worker.
    @Async("outerExecutor")
    public CompletableFuture<String> singleDispatch(String id) {
        boolean onOuter =
                Thread.currentThread().getName().startsWith("outer-");
        String value = onOuter ? "outer-" + id : "unexpected";
        return CompletableFuture.completedFuture(value);
    }

    // Intentionally illustrates the double-submission anti-pattern.
    @Async("outerExecutor")
    public CompletableFuture<String> doubleDispatch(String id) {
        boolean onOuter =
                Thread.currentThread().getName().startsWith("outer-");

        return CompletableFuture.supplyAsync(() -> {
            boolean onInner =
                    Thread.currentThread().getName().startsWith("inner-");
            return onOuter && onInner
                    ? "outer+inner-" + id
                    : "unexpected";
        }, innerExecutor);
    }

    // No @Async: builds JDK pipeline directly, no outer task.
    public CompletableFuture<Integer> composeWithoutOuterAsync() {
        CompletableFuture<Integer> price =
                CompletableFuture.supplyAsync(
                        () -> 100, innerExecutor);

        CompletableFuture<Integer> shipping =
                CompletableFuture.supplyAsync(
                        () -> 25, innerExecutor);

        return price.thenCombine(shipping, Integer::sum);
    }
}
```

- With `singleDispatch`, the caller receives a `Future` from the proxy after Spring dispatches the invocation onto the `outer-` pool. There is no extra `supplyAsync` inside the body.
- With `doubleDispatch`, Spring dispatches the invocation to `outer-`; the body dispatches a supplier to `inner-`. Per Spring Framework 6.x, the interceptor may wait on the inner `Future` before completing the `Future` returned to the caller. This example is **to show the two-layer design**, not a recommendation.
- With `composeWithoutOuterAsync`, a normal method starts two JDK tasks on `inner-`, then applies `thenCombine`. The orchestrator does not call `join()` and needs no outer worker just to wait.

### 8.5. `src/main/java/com/example/doubledispatch/DoubleDispatchApplication.java`

```java
package com.example.doubledispatch;

import java.util.Map;
import java.util.concurrent.TimeUnit;

import org.springframework.boot.Banner;
import org.springframework.boot.SpringApplication;
import org.springframework.boot.WebApplicationType;
import org.springframework.boot.autoconfigure.SpringBootApplication;
import org.springframework.context.ConfigurableApplicationContext;

@SpringBootApplication
public class DoubleDispatchApplication {

    public static void main(String[] args) throws Exception {
        SpringApplication app =
                new SpringApplication(DoubleDispatchApplication.class);

        app.setWebApplicationType(WebApplicationType.NONE);
        app.setBannerMode(Banner.Mode.OFF);
        app.setLogStartupInfo(false);
        app.setDefaultProperties(Map.of("logging.level.root", "OFF"));

        try (ConfigurableApplicationContext context = app.run(args)) {
            JobService jobs = context.getBean(JobService.class);

            System.out.println("single=" +
                    jobs.singleDispatch("A").get(5, TimeUnit.SECONDS));

            System.out.println("double=" +
                    jobs.doubleDispatch("B").get(5, TimeUnit.SECONDS));

            System.out.println("composed=" +
                    jobs.composeWithoutOuterAsync().get(
                            5, TimeUnit.SECONDS));
        }
    }
}
```

Run from the directory containing `pom.xml`:

```bash
mvn -q spring-boot:run
```

**Three lines explicitly printed by `System.out` when the demo runs normally:**

```text
single=outer-A
double=outer+inner-B
composed=125
```

`single=outer-A` shows the `@Async` body ran on the outer pool. `double=outer+inner-B` shows the body started on the outer pool while the supplier ran on the inner pool. `composed=125` shows two independent Futures combined with no outer `@Async` wrapper. `main` deliberately waits with `get(timeout)` for deterministic output; this CLI test harness is not a template for non-blocking HTTP controllers.

Identifying pools by **thread name** should be used only in examples and debugging, not as reliable business logic. Core/max/queue sizes here were chosen for demo clarity; load-test and bound CPU and JDBC/HTTP connections in real usage.

## 9. `@Async`, Spring Proxies, and Self-Invocation

In default proxy mode, `@Async` only takes effect when the call passes through a Spring-managed proxy. Keep two situations distinct:

**Double dispatch:** call goes through the proxy, Spring submits once, and `supplyAsync` inside the body submits a second time.

**No dispatch from Spring:** calling `this.doAsync()` within the same bean, calling a manually constructed `new` instance, or forgetting `@EnableAsync`; the annotation may not be intercepted at all.

Example:

```java
@Service
public class ServiceA {

    public CompletableFuture<String> caller() {
        return this.worker(); // self-invocation, bypasses @Async proxy
    }

    @Async("businessExecutor")
    public CompletableFuture<String> worker() {
        return CompletableFuture.completedFuture(blockingWork());
    }
}
```

This illustrative class requires imports and a `blockingWork` method. When `caller()` is invoked, `this.worker()` may run **directly on the caller thread**, even though its return type is `CompletableFuture`. `completedFuture` does not spawn a worker.

**Diagnosis:** verify `@EnableAsync` is in the right application context, the public method is called from another bean through the proxy, the executor bean name matches, and check thread dumps/metrics for one vs. two submissions rather than relying solely on the `Future` return type.

## 10. When Is Adding Another Async Stage Valid?

Having multiple Futures or stages is not inherently wrong. What must be eliminated is an **outer wrapper task that adds no value**.

Example:

```java
CompletableFuture<byte[]> compressed =
        downloadedBytes.thenApplyAsync(
                bytes -> compressCpuHeavy(bytes),
                cpuExecutor);
```

This illustrative snippet requires `downloadedBytes`, `compressCpuHeavy`, and `cpuExecutor`. Here is a **genuinely CPU-heavy step** that should be moved off the I/O-completing thread; using `thenApplyAsync` and a CPU pool makes sense.

When A returns data and B returns a Future:

```java
CompletableFuture<Receipt> receipt =
        quoteFuture.thenCompose(
                quote -> paymentClient.chargeAsync(quote));
```

This illustrative snippet needs `Receipt`, `quoteFuture`, and `paymentClient`. `thenCompose` links the two stages without blocking a worker in the middle via `join()`.

By contrast, the following code creates an extra worker just to wait:

```java
CompletableFuture<Receipt> receipt =
        CompletableFuture.supplyAsync(
                () -> paymentClient.chargeAsync(quote).join(),
                executor);
```

This illustrative snippet uses `paymentClient`, `quote`, and `executor`; inside the worker there is a blocking `.join()`. When a dependency already returns a `Future`, it is usually better to **return the future directly** or use `thenCompose`, instead of wrapping it in a supplier and blocking.

Architectural exceptions can exist (bridging from a legacy blocking boundary to a dedicated pool, special isolation policies, or an outer task doing heavy preprocessing). Even then, identify **the real work of each stage**, its resource usage, and how waiting occurs. In Spring 6.x, an `@Async` method returning an inner `Future` still risks holding the outer worker waiting on the inner one; moving to a non-`@Async` orchestrator is usually the cleaner answer.

## 11. Errors, Task Rejections, and Cancellation Across Two Layers

A pipeline with two submission points must handle **two points of failure**:

- **Outer rejection:** Spring `@Async` fails to submit the invocation because the executor is shut down or overloaded; with `ThreadPoolTaskExecutor` and `AbortPolicy`, it can throw `TaskRejectedException` right when the caller calls the method.
- **Inner rejection:** `CompletableFuture.supplyAsync(..., executor)` fails to submit the supplier. With a Spring executor, rejection also follows `TaskRejectedException`; with JDK `ThreadPoolExecutor`, it is typically `RejectedExecutionException`.
- **Inner execution failure:** the supplier is accepted yet throws an exception; the inner `Future` completes exceptionally, and the error propagates through the async proxy / caller's `Future`.
- **Timeout:** caller `get(timeout)` only bounds the caller's wait time. `orTimeout` completes the `Future` exceptionally on expiration yet **does not guarantee aborting** an HTTP request/JDBC query or freeing an outer worker waiting on an inner task.
- **Cancellation:** `CompletableFuture.cancel(true)` completes the `Future` with `CancellationException` per contract; `mayInterruptIfRunning` does not guarantee interrupting the supplier. Real cancellation is needed on the HTTP/JDBC client or via cooperative mechanisms.
- **Retries:** multi-layer retries without idempotency can repeat side effects even when the initial problem was merely scheduling. For emails, money transfers, or DB updates, enforce business keys and proper idempotency.

Caller-side error observation example:

```java
CompletableFuture<Report> future = service.createReport(id);

future.whenComplete((value, error) -> {
    if (error != null) {
        metrics.failed(id, error);
    } else {
        metrics.completed(id);
    }
});
```

This is an illustrative snippet needing `Report`, `service`, `id`, and `metrics`. `whenComplete` is for observation. To recover into another value, use `exceptionally`/`handle` per contract; never treat a report-generation failure as an empty successful report by default.

With `@Async void`, the caller has no `Future` to observe outcomes, so use `AsyncUncaughtExceptionHandler` or appropriate status persistence. With `@Async CompletableFuture<T>`, business failures should be observed via the `Future`/completion stage.

**Do not blindly use `CallerRunsPolicy`** to "solve" overload: when the pool is full, this policy can run the task on the submitting thread itself, tying up a Servlet request thread for a long time. Use bounded queues, admission control, and explicit overload responses.

## 12. Context, Transactions, and Double Thread Switching

Every thread hop can affect thread-bound values:

- MDC/trace IDs (`ThreadLocal`), locale, and certain security/request contexts do not automatically cross every executor.
- Spring `@Transactional` binds to the transaction manager/resources per thread; transactions are not automatically copied from caller to inner tasks.
- A `TaskDecorator` can help capture/restore context for tasks on **a specific executor**, yet does not automatically carry context into `commonPool` if an inner `supplyAsync` omits an executor.
- If a DB transaction is open on an outer worker and an inner task runs DB updates, they do not automatically share the same transaction. Design dedicated transactions on the real worker and ensure commit ordering when needed.
- If a task must run after the HTTP request ends, avoid relying directly on short-lived request-scoped objects; pass validated IDs/data instead.

Eliminating an unnecessary scheduling layer also reduces context-propagation hops and simplifies tracing. For stages that genuinely must switch pools, propagate context via stack-supported mechanisms and clean up in `finally`.

## 13. Real-Code Review Checklist

Before finalizing the implementation:

1. **Mark every task submission site:** locate all `@Async`, `supplyAsync`, `runAsync`, `thenApplyAsync`, `thenComposeAsync`, `Executor.execute`, or `submit` calls in the call graph.
2. **Identify who does real work:** does the outer method perform real CPU/I/O work, or just construct another `Future`?
3. **Identify each executor:** named Spring bean, JDK common pool, task scheduler, virtual-thread executor, or client I/O? Never guess from method names.
4. **Verify proxy invocation:** `@EnableAsync`, Spring-managed bean, no self-invocation.
5. **Inspect the returned Future:** is `completedFuture` wrapping an already-computed value, or is `supplyAsync` leaving a task behind? Is an outer worker waiting on a `Future`?
6. **Inspect pools/queues:** bounded core/max/queue, rejection policy, no waiting on tasks queued in the same small pool.
7. **Inspect errors:** acceptance errors, runtime errors, exceptional completion, timeouts, and cancellations must all be observed separately.
8. **Inspect side effects:** count actual business method executions separately from submitted callbacks/tasks.
9. **Inspect context:** trace/MDC, security, transactions, and request lifecycles at every thread boundary.
10. **Inspect caller contract:** HTTP waiting on Future, returning Future via MVC async, or returning `202` with a durable job? In-memory `CompletableFuture` is **not** durable across restarts.

### A Deterministic Test Instead of Guessing Timing

In plain Java, use a self-counting `Executor` like `DoubleSchedulingJdkDemo` above. In Spring integration tests, use two instrumented executor beans or a `TaskDecorator` to confirm where business code runs, combined with `CountDownLatch` to control when workers are busy. Never use `Thread.sleep` hoping to trigger a race.

Also test:

- One request through the `@Async` proxy executes the business logic once.
- Anti-pattern code using two pools actually produces two submissions.
- When outer and inner share a 1-worker pool + bounded queue, a **strictly timed test** demonstrates the hang risk in the Spring version in use; never trigger deadlocks intentionally in production.
- An inner stage throws an exception and the caller's `Future` fails rather than swallowing it.
- Outer or inner is rejected when the queue is full, and the system returns the contract error rather than claiming the job was accepted.
- `@Async` self-invocation behaves differently from a call through the Spring proxy.

## 14. Production Symptoms of Double Scheduling

| Symptom | Possible explanation | How to verify |
| --- | --- | --- |
| High outer `activeCount` yet low CPU | Outer workers waiting on inner tasks | Take thread dumps looking for `Future.get`/`join` |
| Inner queue grows while outer queue also grows | Same logical request passing through two pools | Trace both submissions with a correlation ID |
| Adding outer workers does not improve throughput | Bottleneck is in inner/downstream | Measure queue wait and execution time per pool |
| Common pool holds many blocking JDBC tasks | `supplyAsync` called without an executor | Find source callsites and thread names |
| Trace ID present on outer yet missing on inner | Context did not cross the second executor | Inspect `TaskDecorator` and context propagation |
| Elevated CPU/GC from many callbacks/`FutureTask` | Extra allocations/scheduling | Profile allocations and watch queue metrics |
| Occasional hangs under high load | Outer waits on inner on the same pool | Thread dumps and saturation tests |
| Client times out while worker stays busy | Caller timeout does not stop inner work | Track task lifetimes, connection timeouts/cancellations |

Never conclude from a single metric alone. A worker with low CPU might intentionally be waiting on network I/O or a lock. Correlate thread dumps, call graphs, and timing before attributing it to double scheduling.

**The thorough fix** is moving scheduling to the exact stage that executes real work and removing useless outer wrappers. After refactoring, re-measure throughput, p95/p99 latency, rejections, queue depth, and trace completeness.

## 15. Common Mistakes and Fixes

| Mistake | Why it is wrong / dangerous | Fix |
| --- | --- | --- |
| `@Async` method merely returns `supplyAsync` | Double submission; outer worker may wait | `@Async + completedFuture` or remove `@Async` |
| `@Async` and `supplyAsync` submit to the same fixed pool | Risk of workers waiting on tasks queued in the same pool | Pick one layer; never `get/join` inside a worker |
| Omitting executor in `supplyAsync` | Work runs outside the intended Spring pool | Pass the executor or use `@Async` alone |
| Believing two submissions = side effect ran twice | Misdiagnoses root cause | Count submissions and business executions separately |
| Wrapping an SDK Future in `supplyAsync(() -> future.join())` | Spawns a worker just to block | Return the Future or use `thenCompose` |
| Calling `this.doAsync()` inside the same bean | Bypasses Spring proxy | Call through another bean or restructure |
| Controller calls `.join()` immediately | HTTP thread still blocks | Return async result or a dedicated job API |
| Calling `get(timeout)` and assuming the inner task was cancelled | Worker and I/O may keep running | Real client/driver timeouts and cancellation |
| Retrying both layers by default | Side effects may repeat unexpectedly | Idempotency, retry budgets, deduplication |
| Unbounded queues and deeply nested Futures | Growing backlogs, memory, and latency | Bounded queues, backpressure/admission control |
| Simply adding threads to fix a deadlock | Masks the bug temporarily without breaking the wait cycle | Remove unnecessary waits and double scheduling |
| Copying transactions to workers via `ThreadLocal` | Wrong boundaries and resource leaks | Independent transactions and proper context propagation |
| Leaving failed `CompletableFuture` unobserved | Errors go unrecorded | Observe with `whenComplete`, `handle`, or job status |
| Returning HTTP `202` backed only by an in-memory Future | Crash loses the job | Durable job store/outbox/broker when needed |

## 16. Self-Check Questions

**1.** An `@Async("ioPool")` method returns `CompletableFuture.supplyAsync(() -> jdbcCall())`. How many task submissions happen and where does the supplier typically run?  
**Answer:** Two submission layers when the Spring proxy is active: outer to `ioPool`, and inner typically to `ForkJoinPool.commonPool()` when no executor is passed.

**2.** Changing it to `return CompletableFuture.completedFuture(jdbcCall())`—does JDBC still run on a worker?  
**Answer:** Yes, provided the call goes through the Spring `@Async` proxy. `completedFuture` does not create a task itself.

**3.** Why do two task submissions not mean `jdbcCall()` runs twice?  
**Answer:** The outer task may simply dispatch and wait on the inner one; business work lives inside the inner supplier and runs once. Retries/side effects are a separate concern.

**4.** A fixed pool has 1 worker and queue capacity 10. Outer `@Async` calls `supplyAsync` on the same pool and returns the Future. What is the risk?  
**Answer:** Outer holds the worker waiting for inner; inner waits for the busy worker: deadlock/starvation.

**5.** Do you have to use `@Async` to combine two clients that already return Futures?  
**Answer:** No. The orchestrator can be non-`@Async`, start the Futures, and combine them with `thenCombine`.

**6.** When B returns a Future and depends on A, should you write `thenApply(a -> bAsync(a).join())`?  
**Answer:** Avoid it, as the callback can block a worker. Use `thenCompose(a -> bAsync(a))`.

**7.** Does `@Async` automatically set the executor for a zero-executor `CompletableFuture.supplyAsync(fn)` call?  
**Answer:** No. The static JDK API uses JDK executor rules; pass the executor explicitly to use a Spring bean.

**8.** Is `thenApplyAsync(fn, cpuExecutor)` always bad double scheduling?  
**Answer:** No. If it is a distinct CPU-heavy step needing another pool, that async boundary performs real work and can be appropriate.

**9.** Does caller `future.get(2, SECONDS)` timing out stop an HTTP call running inside the inner worker?  
**Answer:** No. That is only the caller's wait timeout; real client I/O timeouts/cancellation are needed.

**10.** Is an `@Async` method called via `this.method()` guaranteed to switch threads in Spring?  
**Answer:** No. Self-invocation bypasses the proxy under default `AdviceMode.PROXY`.

## 17. Key Takeaways and Official References

**Principle:** a business operation should have **one task-submission owner** at each boundary that genuinely needs one. Using multiple stages to combine results is normal; creating an **outer worker solely to wait on an inner worker** is a pattern to avoid.

- **With `@Async` for blocking methods:** compute on the Spring worker and return `CompletableFuture.completedFuture(result)`.
- **When preferring JDK Futures directly:** omit `@Async` and call `supplyAsync(supplier, executor)` directly.
- **When sources already return Futures:** return/compose with `thenCombine`, `thenCompose`, `allOf`; avoid adding an outer worker.
- **When intentionally switching pools:** use the `Async` variant with an explicit executor and identify real business work, resources, and timeouts.
- **Diagnosis:** count submissions and business executions separately; inspect Spring proxies, thread dumps, queues, and exceptional completions.
- **Operations:** real timeouts/cancellation, bounded queues, context propagation, and idempotency. In-memory Futures do not replace durable job queues.

References:

- [Spring Framework 6.2 — `@Async` Javadoc](https://docs.spring.io/spring-framework/docs/6.2.7/javadoc-api/org/springframework/scheduling/annotation/Async.html) — temporary Future from target and actual Future provided by the proxy.
- [Spring Framework 6.2 — `AsyncExecutionInterceptor`](https://docs.spring.io/spring-framework/docs/6.2.12/javadoc-api/org/springframework/aop/interceptor/AsyncExecutionInterceptor.html) — invocation dispatched to Spring's executor.
- [Spring Framework — Task Execution and Scheduling](https://docs.spring.io/spring-framework/reference/integration/scheduling.html) — annotations, qualifiers, exception handling, and executors.
- [Spring Framework 6.2 — `ThreadPoolTaskExecutor` Javadoc](https://docs.spring.io/spring-framework/docs/6.2.12/javadoc-api/org/springframework/scheduling/concurrent/ThreadPoolTaskExecutor.html) — core/max/queue/lifecycle/rejection.
- [Java SE 17 — `CompletableFuture` Javadoc](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/concurrent/CompletableFuture.html) — `completedFuture`, `supplyAsync`, policies, composition, exceptions, and cancellation.
- [Java SE 17 — `Executor` Javadoc](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/concurrent/Executor.html) — JDK task submission contract.
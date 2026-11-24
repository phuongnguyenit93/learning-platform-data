# Concurrency in Spring: Purpose and Use Cases

## 1. Context and Objectives

In a Spring application, multiple HTTP requests, events, background tasks, and external service calls can occur within the same time window. **Concurrency** helps organize work that is progressing at the same time and control the resources it uses. This is a decision about how to coordinate work, not a guarantee that every operation will run faster.

After this lesson, you should be able to distinguish between concurrency, parallelism, asynchrony, and non-blocking; recognize situations where concurrency mechanisms should be used in Spring; choose the right tool at a high level; and evaluate the risks of threads, queues, errors, transactions, and shared data.

### Four Frequently Confused Concepts

| Concept | Meaning | Example |
| --- | --- | --- |
| **Concurrency** | Multiple tasks coexist and are coordinated within a time window; they may interleave on a single CPU core. | A server handling multiple requests waiting on I/O. |
| **Parallelism** | Two or more pieces of work actually execute at the exact same time, typically on multiple CPU cores. | Independent computations running across multiple workers. |
| **Asynchrony** | The caller can continue its work instead of waiting for the task to finish immediately at the call site; results typically arrive via a `Future`, callback, or signal. | Calling an `@Async` method and receiving a `CompletableFuture`. |
| **Blocking** | The current thread must wait for the operation to complete. | `Thread.sleep(...)`, synchronous JDBC, `future.get()`. |
| **Non-blocking** | The operation does not hold a thread waiting on I/O; a mechanism notifies when data is ready. | I/O following the Reactor/WebFlux model with compatible libraries. |

An `@Async` call usually **offloads blocking work to another thread**; the I/O inside that work does not become non-blocking itself. Conversely, a non-blocking WebFlux pipeline does not inherently execute multiple CPU computations in parallel.

## 2. Why Does Spring Need Concurrency?

### Keeping the System Responsive During Waiting Operations

Suppose a product aggregation API has to query a pricing service (around 400 ms) and an inventory service (around 600 ms). If the two requests are **independent** and called sequentially, the I/O wait time is approximately 1,000 ms. If started concurrently and the results are only combined after both finish, the ideal wait time can be close to 600 ms plus coordination overhead. This is an illustration, not a latency guarantee: connection limits, thread pools, downstream services, queues, and failures can all change the outcome.

To benefit, there must be enough independent work to overlap the waiting time. Calling `@Async` and then immediately calling `join()` at the same point usually only adds thread-switching overhead without creating useful overlap.

### Separating Work Off the Main Response Path

For example, after handling a request, the application can kick off thumbnail generation, send a non-critical notification, or prepare a summary. The user does not necessarily need to wait for these tasks before receiving a response.

The condition is that the business logic **allows later completion** and there is a way to observe/recover from errors. Offloading work to a background thread within the same process does not guarantee that the task will survive an application restart. For work that must be delivered reliably, use a durable outbox/queue/job instead of treating `@Async void` as a reliable delivery mechanism.

### Increasing Capacity to Serve Many I/O-Waiting Requests

When requests frequently wait on the database or network, a thread can have idle CPU yet still be held due to blocking. A thread pool helps bound and distribute work; Spring MVC async APIs or non-blocking I/O can help use threads more efficiently in suitable models. **Throughput**, **latency**, and **resource utilization** are distinct goals: increasing the number of threads too much can slow the system down, consume excessive memory, and overload downstream services.

### Coordinating Time-Based Work

Needs such as periodic data scanning, token renewal, cache cleanup, or nightly report aggregation require a scheduling mechanism. In Spring, this is the `@Scheduled`/`TaskScheduler` group. Scheduling decides *when* work is triggered; concurrency control decides *how many* jobs run and *where* they run.

## 3. Typical Use Cases

| Scenario | Suitable Approach | What Needs to Be Controlled |
| --- | --- | --- |
| Combining results from two independent APIs within one request | `CompletableFuture`/bounded executor; return the future to Spring MVC if needed | Per-API timeouts, per-branch errors, number of outbound connections |
| Sending non-critical notification emails after responding | `@Async` with a dedicated executor if best-effort is acceptable | Retries, failure tracking; switch to a queue if guaranteed delivery is required |
| Generating reports/exports that may take several minutes | Background job with status and idempotency; queue/job store if it needs to survive restarts | Progress, cancellation, retries, memory usage |
| Processing files, generating thumbnails, or calling slow APIs | Dedicated I/O executor with bounded concurrency | I/O, bandwidth, limits from dependent services |
| Data synchronization, scheduled cleanup | `@Scheduled` with an appropriate anti-overlap mechanism | Multiple instances may run simultaneously; avoid overlapping runs |
| CPU-intensive tasks that can be split independently | Worker pool bounded by CPU capacity, or a batch processing system | CPU contention, memory pressure, do not multiply threads indefinitely |
| High traffic with a compatible non-blocking I/O chain | Spring WebFlux/Reactor (or an appropriate async model) | Do not block the event loop; backpressure, observability |

Do not create background tasks for very short operations, operations with strict ordering requirements, or operations that need an atomic transaction with the current request just for the sake of "using multithreading." Nor should you manually spawn `new Thread(...)` per request to bypass system capacity configuration.

## 4. Related Tools in Spring

- **`TaskExecutor` / `AsyncTaskExecutor`:** Spring's abstraction for submitting `Runnable`/`Callable` to an execution mechanism; an implementation may use a pool, dedicated threads, or even run synchronously. Not every executor has a pool.
- **`ThreadPoolTaskExecutor`:** an executor with `corePoolSize`, `maxPoolSize`, and `queueCapacity`; suitable for bounding the number of running/waiting tasks in the application. A large queue can mask bottlenecks and increase latency.
- **`@EnableAsync` + `@Async`:** enables Spring interception and routes method calls through an executor when the method is called **via a Spring proxy**. Commonly used on services injected into other beans; a specific executor can be designated via `@Async("ioExecutor")`.
- **`CompletableFuture<T>`:** represents a result that will be available later, allowing composition, error handling, and waiting for results. `thenApply`, `thenCombine`, and `allOf` help describe relationships between tasks; always consider the executing thread and exceptions.
- **`@Scheduled` + `TaskScheduler`:** used for periodic/due-time tasks. `@Scheduled` does not mean persistence or distributed locking is automatically provided.
- **Spring MVC async:** a controller can return `Callable`, `DeferredResult`, `CompletableFuture`, or supported async types to release the servlet request thread while waiting for the result, depending on the adapter and configuration. The HTTP response still completes only when data is available.
- **Spring WebFlux/Reactor:** a reactive/non-blocking model, suitable when the entire chain of operations supports non-blocking. Do not put blocking JDBC calls directly onto an event-loop thread.
- **Message broker/job system:** suitable for durable queues, retries, and long-running processing that spans process lifecycles. This is a different architectural model from submitting work to an in-JVM pool.

**Distinguishing the three paths:**

```text
Sync:       request thread -> call task -> wait -> receive result -> respond
@Async:     caller -> Spring proxy -> executor -> worker runs task
                                      -> Future completes or fails
MVC async:  request thread -> return Future/async handle -> release request thread
                                                    -> result -> complete HTTP
```

None of these three mechanisms automatically turns a blocking SQL query into a non-blocking query. The difference lies in which thread waits and which thread is released.

## 5. Runnable Example: A Spring MVC API Performing Simulated I/O Work via `@Async`

This example uses Java 17 and Spring Boot 3.5.7 (Spring Framework 6.x). It is a standalone Maven project with two files, enough to run an endpoint. It simulates a slow I/O call using `Thread.sleep(300)` to observe the asynchronous boundary; production code should replace this with a real client that has timeouts.

**File `pom.xml`:**

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
    <groupId>example</groupId>
    <artifactId>spring-concurrency-demo</artifactId>
    <version>0.0.1-SNAPSHOT</version>
    <properties>
        <java.version>17</java.version>
    </properties>
    <dependencies>
        <dependency>
            <groupId>org.springframework.boot</groupId>
            <artifactId>spring-boot-starter-web</artifactId>
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

**File `src/main/java/example/demo/ConcurrencyDemoApplication.java`:**

```java
package example.demo;

import java.util.concurrent.CompletableFuture;
import java.util.concurrent.ThreadPoolExecutor;

import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;
import org.springframework.context.annotation.Bean;
import org.springframework.http.ResponseEntity;
import org.springframework.scheduling.annotation.Async;
import org.springframework.scheduling.annotation.EnableAsync;
import org.springframework.scheduling.concurrent.ThreadPoolTaskExecutor;
import org.springframework.stereotype.Service;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.PathVariable;
import org.springframework.web.bind.annotation.RestController;

@SpringBootApplication
@EnableAsync
public class ConcurrencyDemoApplication {
    public static void main(String[] args) {
        SpringApplication.run(ConcurrencyDemoApplication.class, args);
    }

    @Bean("ioExecutor")
    public ThreadPoolTaskExecutor ioExecutor() {
        ThreadPoolTaskExecutor executor = new ThreadPoolTaskExecutor();
        executor.setCorePoolSize(2);
        executor.setMaxPoolSize(4);
        executor.setQueueCapacity(20);
        executor.setThreadNamePrefix("io-worker-");
        executor.setRejectedExecutionHandler(new ThreadPoolExecutor.AbortPolicy());
        executor.initialize();
        return executor;
    }
}

@Service
class QuoteService {
    @Async("ioExecutor")
    public CompletableFuture<String> getQuote(String productId) {
        try {
            Thread.sleep(300); // Simulates blocking I/O only.
            return CompletableFuture.completedFuture("Quote for " + productId);
        } catch (InterruptedException ex) {
            Thread.currentThread().interrupt();
            return CompletableFuture.failedFuture(ex);
        }
    }
}

@RestController
class QuoteController {
    private final QuoteService quoteService;

    QuoteController(QuoteService quoteService) {
        this.quoteService = quoteService;
    }

    @GetMapping(value = "/quotes/{id}", produces = "text/plain")
    public CompletableFuture<ResponseEntity<String>> quote(@PathVariable String id) {
        return quoteService.getQuote(id).thenApply(ResponseEntity::ok);
    }
}
```

Set up the file structure exactly as shown above. In the directory containing `pom.xml`, using JDK 17+ and Maven:

```bash
mvn spring-boot:run
```

In another terminal:

```bash
curl -s http://localhost:8080/quotes/A12
```

**HTTP response body content:**

```text
Quote for A12
```

Log ordering and thread names differ between runs, so the example does not assert a fixed stdout sequence. `Thread.sleep(300)` simulates a waiting period rather than proving performance under load.

**Execution mechanism:**

1. `QuoteController` receives the request; `quoteService` is a separate bean so the call to `getQuote` goes through the proxy set up by `@EnableAsync`.
2. Spring dispatches the `@Async("ioExecutor")` method to `ThreadPoolTaskExecutor`; the worker can run the 300 ms waiting operation without holding the request thread for that call.
3. The controller returns `CompletableFuture<ResponseEntity<String>>`; Spring MVC supports async responses and completes the HTTP response when the future has a result. The client still waits for the response; the primary benefit is server-side thread coordination.
4. Because the executor has a finite number of workers and a finite queue, task rejections can occur under overload. `AbortPolicy` only surfaces the error; it is not a complete production 503/retry response mechanism.

The example illustrates only **one** call. You cannot conclude that this endpoint reduces the total duration of a single I/O operation; to reduce latency caused by sequential waiting, you need at least two *independent* work branches and must launch them before combining the results.

## 6. Practical Decision: When Should and Shouldn't You Run Concurrently?

### When to Consider

1. There are multiple independent I/O tasks and the waiting portion is measurable; concurrency can overlap that waiting time.
2. There is secondary work that the HTTP result does not have to wait for; business requirements allow deferred processing and there is a clear error-handling plan.
3. There is a sufficiently large batch of independent tasks with bounded resources and a result-aggregation strategy.
4. You need to handle many events/requests while preventing a slow task from consuming the entire serving capacity.

### When Not to Apply Mechanically

- Very small tasks, results that depend sequentially on one another, or callers that immediately wait on `join()`; overhead can outweigh the benefits.
- Work that must commit in the same transaction as the main operation: switching to another thread can break assumptions about ordering, context, and atomicity.
- Work whose state must survive a JVM shutdown: in-memory `@Async` alone is not enough.
- CPU-bound tasks already saturating the CPU: adding threads does not add cores and can increase context switching.
- Blocking code running on the WebFlux event loop: other requests can be affected. Use non-blocking libraries or offload blocking work to a dedicated bounded scheduler, depending on the architecture.
- "Fire-and-forget" tasks without logs, metrics, timeouts, retries, or anyone responsible for handling failures.

## 7. Common Limits and Pitfalls to Know Up Front

### Pool, Queue, and Downstream Resource Limits

An executor does not have infinite capacity. Pool size, queue size, and the number of HTTP/DB connections determine how much work the system can absorb. With `ThreadPoolTaskExecutor`, a queue with remaining capacity is typically used before the pool grows up to `maxPoolSize`; configuring an overly large queue can make requests wait a long time without the worker count increasing as expected.

Choose limits based on measurements: task arrival rate, processing time, CPU, memory, capacity of dependent services, timeouts, and SLOs. Have metrics for active thread count, queued task count, rejection count, latency, and error rate. When overloaded, have a clear policy: fail fast, return an appropriate status, shed load, throttle, or route to a durable queue.

### Shared Data and Correctness

Spring `@Service`/`@Component` beans are usually singletons; multiple requests/workers can call the same bean concurrently. Do not store per-request mutable state in shared fields without proper synchronization design. Prefer local variables, immutable data, and thread-safe classes; when using locks, concurrent collections, or transactions, identify the true protection boundaries.

A `HashMap` is generally not safe when multiple threads write concurrently. Even `ConcurrentHashMap` does not automatically make multi-step "read-then-write" sequences safe if those steps require atomicity.

### Proxies, Self-Invocation, and Return Types

- `@Async` works via a Spring AOP proxy by default. Calling `this.doAsync()` from within the same bean does not go through the proxy, so it usually runs synchronously. Extract the method into another service or use an appropriate interception mechanism.
- An `@Async` method should be called through a Spring-managed bean and have a valid signature; commonly used return types are `void`, `Future<T>`, or `CompletableFuture<T>`. The example uses `CompletableFuture<T>` to handle results/errors.
- If using `@Async void`, the caller has no future to receive exceptions. You must observe errors and can configure `AsyncUncaughtExceptionHandler`; with a future, handle exceptions on the result-consuming side.
- When calling `get()` or `join()`, the calling thread blocks until the result is ready. Do not block immediately if the goal is overlapping tasks.

### Transactions, SecurityContext, and Tracing

Traditional `@Transactional` relies on thread-bound context. An `@Async` task running on another thread **does not automatically inherit** the calling thread's transaction; you need to design separate transaction boundaries where the work is processed, and do not pass unloaded lazy entities outside the persistence context boundary. `ThreadLocal`, MDC/log traces, and `SecurityContext` should also not be assumed to propagate automatically; if needed, use a properly designed and tested propagation mechanism, avoiding context leaks between tasks.

### Timeouts, Cancellation, Shutdown, and Consistency

An incomplete future can hang waiting threads if there are no realistic timeouts at the HTTP/DB/client layer. Canceling a future does not guarantee that downstream libraries will stop working; interruption capability must be controlled. When the application shuts down, in-memory tasks may be lost; test drain/shutdown policies, retries, and idempotency. If publishing events after writing data, consider publishing after commit or using an outbox so consumers do not see uncommitted data.

### Multiple Instances and Scheduled Jobs

An application with three instances can run `@Scheduled` tasks on all three. If business logic requires "only once across the cluster," you need a lock/job coordinator or a distributed scheduling system. Uniqueness cannot be inferred from the annotation.

### Virtual Threads Do Not Bypass Capacity Limits

On Java 21+, virtual threads can reduce thread overhead for many suitable blocking workloads; Spring supports integration depending on version/configuration. However, they do not make downstream APIs faster, do not infinitely increase DB connections, and do not replace timeouts, rate limits, or backpressure. For CPU-bound work, virtual threads do not create extra CPU either.

## 8. Choosing an Approach via Key Questions

Before introducing concurrency into a design, answer:

1. **Where is the independence?** Can branches run before needing each other's results? Are there ordering/transaction constraints?
2. **What is being waited on?** CPU, network, database, file, or a lock? What are the latency/throughput numbers before the change?
3. **Who waits for the result?** Must the client receive it immediately, later via a job ID, or is no result needed? Is the work allowed to be lost if the process dies?
4. **Where are the limits?** Pools, queues, DB connections, downstream quotas, memory, instance count?
5. **How are errors handled?** Timeouts, error responses, idempotent retries, monitored skips, or queuing?
6. **What is measured after the change?** P95/P99 latency, throughput, error rate, queue delay, saturation, and CPU/heap usage.

**Three self-check scenarios:**

- *An API calls two independent services, each taking a few hundred ms:* you can try calling them concurrently and combining results afterward; bound outbound requests and define timeouts/partial failure handling.
- *An order has been written to the DB, and an event must reliably be published to the inventory system even if the application restarts:* `@Async` alone is not enough; consider a transactional outbox and a broker/job worker, with retries/idempotency.
- *A CPU-intensive encryption calculation on a 4-core machine—will adding 100 workers make it 25 times faster?* No. Measure and bound concurrency by CPU, task-splitting overhead, and memory.

## 9. Reference Documentation

- [Spring Framework – Task Execution and Scheduling](https://docs.spring.io/spring-framework/reference/integration/scheduling.html): `TaskExecutor`, `@Async`, `@Scheduled`, proxies, and exceptions.
- [Spring Boot – Task Execution and Scheduling](https://docs.spring.io/spring-boot/reference/features/task-execution-and-scheduling.html): default executors and integration configuration by Boot version.
- [Spring Framework – WebFlux Overview](https://docs.spring.io/spring-framework/reference/web/webflux.html): the reactive/non-blocking approach.
- [Spring Framework – WebFlux Concurrency Model](https://docs.spring.io/spring-framework/reference/web/webflux/new-framework.html): blocking/thread model differences between MVC and WebFlux.

Concurrency in Spring makes sense when it solves a real waiting point or coordination need. Choose a model based on **task independence, reliability requirements, and resource limits**, then verify with metrics and error handling rather than defaulting every method to `@Async`.

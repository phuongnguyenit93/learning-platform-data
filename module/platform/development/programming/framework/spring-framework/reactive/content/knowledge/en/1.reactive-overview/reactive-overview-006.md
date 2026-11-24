# Comparing Processing Models of Spring MVC and Spring WebFlux

## 1. Purpose and High-Level Overview

Spring MVC and Spring WebFlux both build HTTP applications in the Spring ecosystem. Both support `@RestController`, `@GetMapping`, authentication, data validation, exception handling, JSON responses, and testing mechanisms. The core difference lies in **assumptions about I/O waiting and how threads are used when handling a request**:

- **Spring MVC** is based on the Servlet API. Its typical synchronous processing flow allows controllers to invoke *blocking* APIs: while waiting on a database or another service, the processing thread can be held. MVC also has its own *asynchronous* mechanisms, so you cannot conclude “MVC only processes synchronously.”
- **Spring WebFlux** is designed around a *reactive, non-blocking* model across its HTTP handling contracts. When a genuinely non-blocking I/O operation is waiting, the event-loop thread can serve other work. WebFlux commonly uses Reactor with `Mono<T>` (0 or 1 value) and `Flux<T>` (0 to many values).
- **Asynchronous** refers to receiving a result later; **non-blocking** refers to not forcing a thread to wait idly; **reactive** adds a data-stream model, completion/error signals, and demand regulation (*backpressure*). A method returning `Mono` is not necessarily non-blocking if it still calls JDBC or `Thread.sleep()` on the event loop.

The scope of this article is **comparing request-processing models and design consequences**. Do not choose WebFlux merely because of the “reactive” label or assume its performance is always higher than MVC.

## 2. Quick Comparison Table

| Aspect | Spring MVC | Spring WebFlux |
|---|---|---|
| HTTP foundation | Servlet API, typically on Tomcat or Jetty | Reactive HTTP API; can run on Reactor Netty or adapters to Servlet containers supporting non-blocking I/O |
| Dispatcher | `DispatcherServlet` | `DispatcherHandler` |
| Default model | Imperative, one synchronous request-processing thread that may wait on I/O | Reactive, event-driven, and non-blocking by default |
| Execution threads | Servlet container has a pool of worker threads for potentially blocking operations | Event loop typically has a small thread count; work must not block the event loop |
| Common return types | `T`, `ResponseEntity<T>`; can also use `Callable`, `DeferredResult`, `Mono`/`Flux` | `Mono<T>`, `Flux<T>`, `Mono<ResponseEntity<T>>`; can also return direct values in appropriate controllers |
| Reading request body | Typically `@RequestBody Dto` | Can use `@RequestBody Dto` or `@RequestBody Mono<Dto>` for reactive streams |
| HTTP read/write | Traditional MVC relies on Servlet I/O; response writing in async MVC flows can still block | Non-blocking read/write contracts via runtime adapters |
| Backpressure | Can support reactive streams when returning a Publisher, though HTTP writes remain blocking on an executor | Reactive Streams backpressure is a foundational part of reactive processing; end-to-end effectiveness still depends on components and transport |
| Common data access | JDBC, JPA/Hibernate, and imperative transactions | R2DBC or reactive drivers/clients when genuine non-blocking behavior is needed |
| HTTP client | `RestClient`, `RestTemplate` (legacy), or `WebClient` | `WebClient` for reactive calls |
| Handling blocking work | Fits synchronous calls well; requires managing thread and connection pool sizes | Must avoid blocking on the event loop; can temporarily isolate via `boundedElastic` |
| Complexity | Linear control flow, familiar stack traces | Requires understanding `onNext`/`onError`/`onComplete` signals, schedulers, context, and publisher composition |
| Where it usually makes sense | CRUD, JDBC/JPA applications, stable imperative systems | Many concurrent I/O-waiting connections, streaming, end-to-end reactive HTTP and data call chains |

**Note:** Saying “MVC uses one thread per connection” is imprecise. With synchronous handling, a worker thread is typically bound to one request during execution; HTTP keep-alive can serve multiple requests over one connection, and MVC async releases the thread while waiting.

## 3. Spring MVC HTTP Processing Flow

A typical synchronous path:

```text
Client
  -> Servlet container (Tomcat/Jetty)
  -> Filter chain -> DispatcherServlet
  -> HandlerMapping / HandlerAdapter -> @RestController
  -> Service -> JDBC/JPA or synchronous HTTP client
       [worker thread waits during blocking I/O]
  -> return data -> serialize JSON -> HTTP response
```

1. The Servlet container accepts the request and hands application processing to a worker thread.
2. `DispatcherServlet` routes to the controller; the controller executes sequential Java statements.
3. If the service invokes JDBC/JPA or a synchronous API taking 300 ms, the thread can be held for that waiting duration; the CPU is not necessarily busy, yet the thread resource remains occupied.
4. Once the result arrives, Spring converts it into an HTTP response and returns the worker thread to the pool.

This model is **simple to read, debug, and manage transactions in**; on the flip side, when very many requests wait on I/O simultaneously, the thread pool or connection pool can become a bottleneck.

### MVC Also Has Asynchrony

MVC supports `Callable<T>`, `WebAsyncTask<T>`, `DeferredResult<T>`, `CompletionStage<T>`, and even some Reactor types. With `DeferredResult`, the controller returns a placeholder for a result not yet available; the Servlet request enters async mode and the initial worker thread is released. When the result appears, the servlet container *dispatches* again to complete the response. With `Callable`, the task is handed off to an executor.

Thus, **MVC async can free threads while waiting**. However, it goes through Servlet async dispatch, and per Spring documentation, MVC response writes when streaming data are still blocking operations executed on an executor. This differs from how WebFlux builds all HTTP contracts around non-blocking I/O.

## 4. Spring WebFlux HTTP Processing Flow

A typical path on Reactor Netty:

```text
Client
  -> Netty event loop -> HTTP adapter / WebHandler
  -> DispatcherHandler -> @RestController
  -> create Mono/Flux (pipeline description)
  -> Spring subscribes, signaling data demand
  -> WebClient/R2DBC registers non-blocking I/O operation
       [does not hold event-loop thread waiting for I/O]
  -> callback/data signal arrives -> transform -> write response non-blocking
```

1. The event loop receives and dispatches network events. One event-loop thread can advance the processing of many connections as long as operations do not block.
2. Controllers typically return `Mono`/`Flux`, which is a **description of an asynchronous computation**, not an already-computed final value. Spring manages subscribing for the HTTP response; controllers normally **do not call** `.subscribe()` themselves.
3. While a reactive HTTP/database client is waiting, the thread can process other events. When data arrives, operators (`map`, `flatMap`, `zip`, etc.) continue running in a signal-driven manner.
4. A Publisher has three signal types to understand: data `onNext`, completion `onComplete`, and error `onError`; the receiver can call `request(n)` to express demand and can `cancel()`.
5. Never assume an entire pipeline always runs on one thread. `publishOn`/`subscribeOn`, the runtime, and integrated libraries can switch schedulers.

**Do not confuse an event loop with “only one thread for the entire server.”** The runtime still has multiple threads, and there can be separate schedulers/connection pools for other tasks. The optimization is minimizing *threads stuck merely waiting for I/O*.

WebFlux **does not require Netty**: it can run on Tomcat/Jetty supporting non-blocking I/O through adapters. Conversely, running WebFlux on Tomcat does not turn it into Spring MVC.

## 5. Two Runnable Java 17+ Examples to Observe the Difference

The two programs below belong in **two separate standalone Spring Boot applications**, each selecting only the matching web starter via Spring Initializr (MVC/Web for example 1, Reactive Web/WebFlux for example 2). Ensure they do not run simultaneously on port 8080. Dependency names may vary across Spring Boot versions; keep the matching web stack for each project.

### 5.1. Spring MVC: Simulating a Blocking Call

Create `src/main/java/example/MvcDemo.java`:

```java
package example;

import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.RestController;

@SpringBootApplication
public class MvcDemo {
    public static void main(String[] args) {
        SpringApplication.run(MvcDemo.class, args);
    }
}

@RestController
class MvcController {
    @GetMapping("/compare")
    String compare() throws InterruptedException {
        Thread.sleep(250); // Simulates blocking I/O wait, not for real production handling
        return "OK";
    }
}
```

In this synchronous controller, `Thread.sleep(250)` holds the worker thread without doing useful work during the wait. In a real application, the wait point might be a JDBC query or a blocking HTTP client.

### 5.2. Spring WebFlux: Simulating Waiting Without Holding an Event-Loop Thread

Create `src/main/java/example/WebFluxDemo.java`:

```java
package example;

import java.time.Duration;
import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.RestController;
import reactor.core.publisher.Mono;

@SpringBootApplication
public class WebFluxDemo {
    public static void main(String[] args) {
        SpringApplication.run(WebFluxDemo.class, args);
    }
}

@RestController
class WebFluxController {
    @GetMapping("/compare")
    Mono<String> compare() {
        return Mono.delay(Duration.ofMillis(250))
                   .map(ignored -> "OK");
    }
}
```

`Mono.delay` uses Reactor's timer rather than calling `sleep()` on the event loop. Spring subscribes to the result when serving the request; after the scheduled duration, the pipeline emits `"OK"`.

For a Spring Boot project using the Gradle wrapper, run each project with:

```bash
./gradlew bootRun
```

From another terminal:

```bash
curl -i http://localhost:8080/compare
```

Both examples return HTTP 200 and body `OK` when running successfully. Exact headers, thread names, and timings depend on the environment. **These two snippets only illustrate waiting mechanisms**: `Thread.sleep` and `Mono.delay` are not two ways of accessing the same database, so they must not be treated as a benchmark of MVC versus WebFlux.

## 6. When Many Requests Wait on I/O Concurrently

Suppose a service receives about 400 requests/second, each waiting on an upstream for 0.5 seconds on average. By Little's Law, the number of requests *in the system* due to this wait alone is roughly `400 x 0.5 = 200` in steady state (an estimate, excluding other queues).

- **Synchronous MVC**: if each waiting request holds a worker thread, that load level may require roughly 200 worker threads waiting concurrently, along with pool limits and upstream resources. When workers are exhausted, new requests wait or are rejected depending on configuration.
- **End-to-end non-blocking WebFlux**: ~200 pending I/O operations do not necessarily require 200 event-loop threads. Operations are registered and resume on events, though connection pools, upstream limits, memory, timeouts, and CPU still determine capacity.
- **If WebFlux calls blocking JDBC directly on the event loop**: the advantage above can vanish; one slow call can delay many other requests on the same event-loop thread.
- **If MVC uses Servlet async or virtual threads**: the number of platform workers held while waiting can drop significantly. Therefore, compare actual configurations rather than assuming “MVC always needs N threads, WebFlux always needs 1 thread.”

From the processing model alone, you **cannot conclude** that WebFlux has lower latency in every case. For CPU-bound business logic or blocking storage, the difference may be small, zero, or WebFlux may even incur higher operational cost due to pipeline complexity.

## 7. Reactor, Backpressure, and Practical Meaning

`Mono<T>` is a publisher emitting at most one value; `Flux<T>` emits many values. Reactive Streams allows a subscriber to request an element count (`request(n)`) and the publisher to coordinate emission rates so it does not emit unboundedly beyond demand at protocol-supported boundaries. This is an important advantage when handling large data sequences or streams.

```java
Flux<Integer> batch = Flux.range(1, 10)
                          .map(number -> number * 2)
                          .limitRate(2);
```

This is an **illustrative code snippet**, not a standalone Spring Boot program. `limitRate(2)` adjusts how downstream requests elements from upstream; it **is not** a limit of 2 HTTP requests/second and does not automatically turn every API or external system into non-blocking.

When streaming over HTTP, end-to-end effectiveness still depends on codecs, buffers, response types, HTTP transport, how downstream consumes, and whether upstream supports backpressure. Do not equate backpressure with rate limiting, load balancing, or timeouts.

### WebFlux Server-Sent Events (SSE) Example

Place this method inside a WebFlux `@RestController`:

```java
@GetMapping(value = "/ticks", produces = MediaType.TEXT_EVENT_STREAM_VALUE)
public Flux<String> ticks() {
    return Flux.interval(Duration.ofSeconds(1))
               .take(3)
               .map(index -> "tick-" + index);
}
```

You need to import `java.time.Duration`, `reactor.core.publisher.Flux`, and `org.springframework.http.MediaType`. A client using `curl -N http://localhost:8080/ticks` will see payloads representing `tick-0`, `tick-1`, `tick-2` in sequence, after which the stream completes; exact SSE framing details depend on the encoder. MVC **also supports SSE** via `SseEmitter` or reactive return types, so SSE alone does not force switching to WebFlux.

## 8. Service Integration: The Data Source Determines Effectiveness

Suppose an API aggregates information from two HTTP services. When both upstreams support non-blocking I/O, `WebClient` can compose the tasks without holding a thread waiting on each call:

```java
// Illustrative snippet inside a service with an injected WebClient client.
public Mono<Map<String, String>> loadSummary(String id) {
    Mono<String> profile = client.get()
            .uri("/profiles/{id}", id)
            .retrieve()
            .bodyToMono(String.class);

    Mono<String> account = client.get()
            .uri("/accounts/{id}", id)
            .retrieve()
            .bodyToMono(String.class);

    return Mono.zip(profile, account)
            .map(pair -> Map.of(
                    "profile", pair.getT1(),
                    "account", pair.getT2()
            ));
}
```

Import `java.util.Map` and `reactor.core.publisher.Mono`; the two URIs are upstream paths the application must configure. This is an integration snippet and **will not run on its own** without `WebClient client` and real services. `Mono.zip` coordinates the two sources; typically both calls can be subscribed to without waiting for the first to finish before starting the second. Timeouts, error statuses, and `Mono.empty()` must be handled according to business requirements.

**Important:** `WebClient` is not exclusive to a WebFlux server. A **Spring MVC application can completely use WebClient**, and an MVC controller can return a reactive type for Spring to adapt to Servlet async. This lets you improve I/O call paths without necessarily replacing the entire HTTP stack.

### What Happens with JDBC/JPA in WebFlux?

JDBC/JPA are blocking APIs. If a WebFlux controller calls a JDBC repository directly on the event loop, the thread is still held while the DB waits. For legacy libraries that cannot be replaced immediately, Reactor supports isolating them on a scheduler meant for blocking:

```java
Mono<String> legacyCall = Mono.fromCallable(() -> {
    Thread.sleep(100); // Only simulates a blocking API
    return "legacy-result";
}).subscribeOn(Schedulers.boundedElastic());
```

Import `reactor.core.publisher.Mono` and `reactor.core.scheduler.Schedulers`. `fromCallable` defers invocation until subscription; `subscribeOn(boundedElastic())` moves the blocking portion onto an appropriate scheduler. **It does not turn blocking I/O into non-blocking**: a scheduler thread still waits, the scheduler has finite resources, and timeouts, connection pools, and queued tasks must be controlled.

If most business logic relies on JPA/JDBC, MVC is usually the simpler, more natural choice. If you want a WebFlux pipeline that is genuinely non-blocking all the way to the database, evaluate reactive drivers and transactions (such as R2DBC), business compatibility, and transaction management semantics.

## 9. Error Handling, Request Cancellation, Context, and Transactions

### Errors and Timeouts

- **MVC:** synchronous exceptions go through `@ExceptionHandler`/`@ControllerAdvice`; async MVC has completion/error mechanisms and timeouts on `DeferredResult`, `WebAsyncTask`, and executors.
- **WebFlux:** errors are emitted as `onError` signals; use `onErrorResume`, `onErrorMap`, `timeout`, and appropriate HTTP error handling. `Mono.empty()` denotes completion with no value; if business logic requires HTTP 404, map it explicitly rather than assuming empty automatically means 404.
- **Both:** set sensible timeouts for upstreams/databases, classify errors, bound retries, and retry only safe operations. When a client disconnects, a reactive subscription can receive a cancel signal, though whether upstream actually stops depends on the library and task.

Example of handling timeouts with Reactor:

```java
Mono<String> guarded = remoteCall
        .timeout(Duration.ofSeconds(2))
        .onErrorResume(TimeoutException.class,
                       error -> Mono.just("fallback"));
```

This is a snippet: `remoteCall` must already be available as a `Mono<String>`; import `java.time.Duration` and `java.util.concurrent.TimeoutException`. A fallback is only appropriate if business rules allow it; do not mask errors in financial operations or critical data updates.

### Context, Security, Transactions

- Synchronous MVC code is generally easy to trace via stack traces and `ThreadLocal` on the same thread; with MVC async or virtual threads, you still need to watch out for propagation across context switches.
- WebFlux does not guarantee a request always runs on the same thread; avoid storing request context arbitrarily in `ThreadLocal`. Use Reactor `Context` and propagation mechanisms provided by Spring/Micrometer when appropriate.
- MVC typically uses servlet `Filter`/`HandlerInterceptor` and servlet security configuration; WebFlux typically uses `WebFilter` and reactive Spring Security APIs. Do not copy servlet filter configurations directly into WebFlux.
- Transactions using `PlatformTransactionManager` with JDBC/JPA and `ReactiveTransactionManager` with reactive data access have different context semantics. A reactive pipeline does not automatically turn blocking-style `@Transactional` into a reactive transaction.

## 10. Scalability, Virtual Threads, and Measurement

**Throughput** is the number of requests handled per unit time; **latency** is the duration per request; **concurrency** is the number of active/waiting tasks; **backpressure** is demand regulation in a data stream. They are related, not synonymous.

Since Java 21, virtual threads allow writing blocking imperative-style code with typically lower thread overhead than platform threads in many I/O-waiting scenarios. Spring Boot supports enabling virtual threads for suitable executors via configuration such as `spring.threads.virtual.enabled=true` (when the app/JDK meets requirements). This is an option worth comparing within an MVC architecture. Virtual threads are still a blocking model from the source code's perspective, do not inherently provide Reactive Streams/backpressure, and do not eliminate database connection pool or upstream limits.

When evaluating both models, test **the same business logic, same data, same upstreams, and resource limits**, monitoring:

1. Requests/second, p50/p95/p99 latency, timeouts, and error rates.
2. CPU, heap, GC, active platform/virtual threads, queue depth.
3. HTTP and database connection pools, waiting connections, actual load on upstreams.
4. Blocking operations occurring on the event loop, serialization/deserialization time, response sizes.
5. Stability under burst load, handling of client disconnects, debuggability, and maintenance cost.

Using `curl` only shows single-request behavior; to draw performance conclusions, run methodical load tests with warm-up, explicit concurrency limits, and reproducible measurements.

## 11. How to Choose in a Project

**Usually choose MVC when:**

- Building CRUD/REST applications with JDBC/JPA, many imperative APIs, or maintaining an existing MVC system running reliably.
- The team prioritizes straightforward control flow, traditional libraries, and maintainability.
- Isolated async needs exist: you can use Servlet async, `WebClient`, or consider virtual threads before making a major architectural shift.

**Consider WebFlux when:**

- The system performs very high concurrent non-blocking I/O, holds many open waiting connections, or returns continuous streaming.
- End-to-end components (HTTP clients, databases/queues) have suitable reactive drivers and the team has Reactor experience.
- You need to leverage composing multiple publishers, backpressure, and stream processing via operators.

**Hybrid situations:** a system can consist of MVC services with JDBC/JPA alongside WebFlux services handling aggregation/streaming. An MVC controller can also use `WebClient`. Every service does not have to use the same model.

### Practical Decision Questions

1. Is most request time spent in **CPU**, **blocking JDBC/JPA**, or **non-blocking I/O**?
2. Do key dependencies genuinely support reactive execution, or are they merely wrapped in `Mono`?
3. Is the number of concurrently waiting requests/connections a bottleneck backed by metrics?
4. Could the issue be solved via thread/connection pool tuning, MVC async, `WebClient`, or virtual threads with fewer changes?
5. Does the team have adequate testing, tracing, debugging, and monitoring tools for reactive flows during incidents?

Decisions should be based on actual load and system limits, not on a “faster” label.

## 12. Common Misconceptions and Mistakes

| Misconception/Mistake | Accurate Understanding |
|---|---|
| “WebFlux is always faster than Spring MVC” | No guarantee. Benefits depend on load patterns, I/O wait ratio, drivers, and team proficiency. |
| “Spring MVC cannot do async or streaming” | MVC has Servlet async, `DeferredResult`, `Callable`, `SseEmitter`, and can adapt reactive return types. |
| “Just changing the return type from `T` to `Mono<T>` makes it non-blocking” | If a blocking API is called on the event loop inside, the pipeline still has a blocking point. |
| “`Mono` always runs on its own thread” | A Publisher does not automatically create a thread. Schedulers, upstream, and the runtime determine the execution thread. |
| “Calling `.block()` in a WebFlux controller to grab data easily” | Can block the event loop and exhaust serving capacity; return `Mono`/`Flux` for Spring to handle. |
| “Calling `.subscribe()` in a controller to run the pipeline” | Risks spawning work detached from the HTTP lifecycle, losing error/cancel handling; normally return the publisher directly. |
| “WebFlux must run on Netty” | Can use non-blocking adapters on compatible Servlet containers. |
| “WebFlux completely replaces MVC” | Both models can coexist across applications and share certain tools. |
| “Backpressure is just a requests/second limit” | Backpressure controls data demand within a stream; rate limiting serves a different goal. |
| “Virtual threads make WebFlux pointless” | Virtual threads reduce thread overhead when blocking in many cases; reactive remains useful for non-blocking data paths and streaming. |

**Key takeaway:** Spring MVC is optimized for an imperative processing model that can block; Spring WebFlux builds a non-blocking reactive pipeline from the ground up. Look at **how the code and drivers underneath the controller actually wait on I/O**, because that is what determines thread-usage characteristics.

## Official References

- Spring Framework, **Spring WebFlux**: https://docs.spring.io/spring-framework/reference/web/webflux.html
- Spring Framework, **WebFlux Overview – Applicability & Concurrency Model**: https://docs.spring.io/spring-framework/reference/web/webflux/new-framework.html
- Spring Framework, **MVC Asynchronous Requests**: https://docs.spring.io/spring-framework/reference/web/webmvc/mvc-ann-async.html
- Spring Framework, **WebClient Synchronous Use**: https://docs.spring.io/spring-framework/reference/web/webflux-webclient/client-synchronous.html
- Spring Boot, **Reactive Web Applications**: https://docs.spring.io/spring-boot/reference/web/reactive.html
- Spring Boot, **Task Execution and Scheduling / Virtual Threads**: https://docs.spring.io/spring-boot/reference/features/task-execution-and-scheduling.html
- Reactor Core, **How Do I Wrap a Synchronous, Blocking Call?**: https://projectreactor.io/docs/core/release/reference/faq.html
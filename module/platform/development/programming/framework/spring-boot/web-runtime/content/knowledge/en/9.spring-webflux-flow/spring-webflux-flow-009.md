# Event Loop in Spring WebFlux and Differences From Servlet Thread Handling

## 1. Two HTTP Request Execution Models

When building APIs with Spring Boot, **Spring MVC on the Servlet stack** and **Spring WebFlux on the Reactive stack** can expose identical REST endpoints while differing substantially in how they serve concurrent requests.

- **Synchronous Spring MVC on a Servlet container** (Tomcat, Jetty, Undertow): an HTTP request executing synchronously usually occupies one container **worker thread**. If the controller waits on JDBC, synchronous I/O, or a blocking HTTP client, that thread also remains occupied while waiting.
- **Spring WebFlux with Reactor Netty**: a group of **event-loop threads** dispatches I/O events and callbacks across many connections. When using non-blocking I/O, an event-loop thread does not sit idle waiting for one request's data; it can handle events from other connections.

This is not a simplistic contrast between "Servlet has one thread" and "WebFlux uses one thread." Servlets have thread pools, Servlet async support, and can use virtual threads in suitable environments; WebFlux uses multiple event-loop threads and can use additional schedulers and workers. The cleanest comparison is **synchronous thread-per-active-request Servlet handling** versus **Reactor Netty's event-driven non-blocking model**.

## 2. What Is an Event Loop?

An **event loop** is a continuous loop monitoring ready events: new connections, readable sockets, writable sockets, scheduled callbacks, and other I/O signals. One event-loop thread typically handles events across **many channels/connections**, rather than being dedicated exclusively to the lifetime of a single HTTP request.

~~~text
Connection A ---\
Connection B ----+----> I/O Events ----> Event loop E1 ---> callbacks A, B, ...
Connection C ---/                             |
                                              +----> keep polling events

Connection D ---\
Connection E ----+----> I/O Events ----> Event loop E2 ---> callbacks D, E, ...
~~~

This high-level diagram does not depict every Netty transport detail. A Netty channel is normally pinned to a single event loop in the group for its lifetime, while many channels share that event loop. A server runs multiple event loops, not a single global loop.

For this mechanism to perform well, **callbacks must execute quickly without blocking the thread**. For example:

1. Request A arrives and initiates a non-blocking I/O query.
2. The thread registers the wait for data and returns control rather than holding a worker thread just to wait for the result.
3. The same event loop runs callbacks for B or C while A's I/O is still pending.
4. When A's I/O produces a result, A's callback continues building the response.

Thus **the event loop is an execution mechanism**; it is not request data storage, not a new thread spawned per request, and not a caching layer.

## 3. Request Path in Synchronous Servlet

With Spring MVC, a request typically flows through:

~~~text
HTTP client
  -> Embedded Servlet container
  -> FilterChain
  -> DispatcherServlet
  -> HandlerMapping / HandlerAdapter
  -> Controller
  -> Service / JDBC / HTTP client
  -> HTTP response
~~~

For a synchronous controller in flight, the container typically assigns a worker thread to handle the request. Suppose three concurrent requests invoke blocking JDBC:

~~~text
Request A -> Tomcat worker T1 -> JDBC call -> waiting -> controller returns response
Request B -> Tomcat worker T2 -> JDBC call -> waiting -> controller returns response
Request C -> Tomcat worker T3 -> JDBC call -> waiting -> controller returns response
~~~

While each request waits on synchronous I/O, its worker thread stays occupied. With high concurrency and a bounded worker pool, subsequent requests queue up, time out, or get rejected per container configuration.

**Important point:** this is not **thread-per-TCP-connection**. An HTTP keep-alive connection can remain open while no request is actively executing. The container reuses worker threads for other requests once handling completes.

Nor should you claim Spring MVC "has no async": Servlet 3.x provides `AsyncContext` and non-blocking I/O APIs; Spring MVC supports `Callable`, `DeferredResult`, and async integrations that release the request thread while waiting on work.

## 4. Request Path in WebFlux / Reactor Netty

If an application uses `spring-boot-starter-webflux` without pulling in Servlet MVC to make Spring Boot choose another stack, the embedded server is typically **Reactor Netty**. High-level path:

~~~text
HTTP client
  -> Reactor Netty TCP/HTTP server
  -> Event-loop callback
  -> WebFilter chain / DispatcherHandler
  -> WebFlux HandlerMapping / HandlerAdapter
  -> Reactive controller returning Mono/Flux
  -> Reactive operators + non-blocking client I/O
  -> Response written when data is ready
~~~

While one request waits on a remote HTTP call via `WebClient`, the event loop can serve other requests. No dedicated event-loop thread sits waiting per network call.

Example timeline:

~~~text
T0: E1 receives request A -> calls reactive client -> does not wait synchronously
T1: E1 receives request B -> prepares response B
T2: E2 receives request C -> calls reactive client -> does not wait synchronously
T3: A's data is ready -> callback A processes response
T4: C's data is ready -> callback C processes response
~~~

Do not assume a single request's callbacks **always** run on the same thread. When a pipeline uses `publishOn`, `subscribeOn`, timers, clients, or other asynchronous boundaries, stages can run on different schedulers.

### 4.1. Comparison Table

| Aspect | Typical synchronous Servlet MVC | Typical WebFlux on Reactor Netty |
|---|---|---|
| Request serving | Worker thread handles synchronous request execution | A group of event-loop threads serves many channels |
| Waiting on I/O | With blocking APIs, the thread usually blocks | With non-blocking APIs, the thread is not held while waiting |
| Calling traditional JDBC | Fits the synchronous model | Calling on the event loop causes stalls |
| Common HTTP client | `RestClient` or synchronous clients; `WebClient` is also usable | `WebClient` with a non-blocking HTTP client |
| Controller | Usually returns DTO, `ResponseEntity`, view | Can return `Mono<T>` / `Flux<T>` |
| Thread allocation | Servlet worker pool, plus async executor if configured | Event loops + schedulers + dependency workers |
| Overload risk | Worker pool exhaustion, growing request queue | Blocked event loop, scheduler queues, downstream saturation |
| Per-request state | Naturally follows synchronous call stack | May cross multiple callbacks/threads; requires context propagation |

**Non-blocking does not automatically mean faster.** If a database can only handle a fixed query rate, raising HTTP concurrency can still overwhelm the database even though event-loop threads are never held idle.

## 5. How Reactor, Mono/Flux, and Threads Relate

Spring WebFlux uses Project Reactor. Two core concepts:

- `Mono<T>` represents a publisher emitting at most one element (or completing empty/with an error).
- `Flux<T>` represents a publisher capable of emitting multiple elements, completing, or erroring.

A publisher describes a pipeline; it is **not a thread**. Some sources are **cold publishers**: work starts only upon subscription. For HTTP controllers returning publishers, WebFlux manages subscription to complete the response; you normally should not manually call `subscribe()` inside controllers for business work.

Reactor fragment example (requires Reactor dependency and importing `reactor.core.publisher.Mono`):

~~~java
Mono<String> value = Mono.fromSupplier(() -> {
    System.out.println("SUPPLIER");
    return "ready";
});

System.out.println("BEFORE");
value.subscribe(System.out::println);
~~~

Because this is a synchronous source with no scheduler switching threads, the fragment prints:

~~~text
BEFORE
SUPPLIER
ready
~~~

`Mono.just(blockingCall())` **does not** make `blockingCall()` asynchronous: Java evaluates that argument expression before creating the publisher. Likewise, an ordinary `map` callback runs on whichever thread emitted the signal rather than switching threads automatically.

## 6. Runnable Spring Boot Example: Observing Threads and a Non-Blocking Timer

This example uses **Java 17+, Spring Boot 3.x**, and a Gradle project with the Spring Boot plugin/dependency management configured. Use only the WebFlux starter on the server; do not add `spring-boot-starter-web` in this example:

~~~groovy
dependencies {
    implementation 'org.springframework.boot:spring-boot-starter-webflux'
}
~~~

File **src/main/java/demo/webflux/EventLoopDemoApplication.java**:

~~~java
package demo.webflux;

import java.time.Duration;
import java.util.Map;

import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.RestController;

import reactor.core.publisher.Mono;
import reactor.core.scheduler.Schedulers;

@SpringBootApplication
public class EventLoopDemoApplication {

    public static void main(String[] args) {
        SpringApplication.run(EventLoopDemoApplication.class, args);
    }
}

@RestController
class EventLoopDemoController {

    @GetMapping("/demo/thread")
    Mono<Map<String, String>> showThread() {
        return Mono.defer(() -> Mono.just(
                Map.of("thread", Thread.currentThread().getName())
        ));
    }

    @GetMapping("/demo/timer")
    Mono<String> nonBlockingTimer() {
        return Mono.delay(Duration.ofMillis(150))
                .map(ignored -> "done");
    }

    @GetMapping("/demo/offloaded")
    Mono<Map<String, String>> offloadedBlockingCall() {
        return Mono.fromCallable(() -> {
                    // Simulate a synchronous library to observe offloading.
                    Thread.sleep(100);
                    return Map.of(
                            "result", "finished",
                            "thread", Thread.currentThread().getName()
                    );
                })
                .subscribeOn(Schedulers.boundedElastic());
    }
}
~~~

Explanation:

1. `/demo/thread` uses `Mono.defer` to read the thread name **when the publisher is subscribed**, not when the method builds the publisher. With default Reactor Netty, you will typically see an event-loop thread name.
2. `/demo/timer` uses Reactor's timer without holding an event-loop thread during the 150 ms wait. Callbacks after `Mono.delay` can execute on a different scheduler, so never assume every operator stays on the event loop.
3. `/demo/offloaded` simulates blocking work with `Thread.sleep`, wrapping it in `Mono.fromCallable` and scheduling the source via `subscribeOn(Schedulers.boundedElastic())`. This is for observation; **using `Thread.sleep` in real APIs is discouraged**.

Run the application in a properly configured project:

~~~bash
./gradlew bootRun
~~~

On Windows you can use `gradlew.bat bootRun`. In another terminal:

~~~bash
curl -s http://localhost:8080/demo/thread
curl -s http://localhost:8080/demo/timer
curl -s http://localhost:8080/demo/offloaded
~~~

Exact body from the timer endpoint:

~~~text
done
~~~

The other two endpoints return JSON structured like these illustrative outputs:

~~~json
{"thread":"reactor-http-nio-2"}
~~~

~~~json
{"result":"finished","thread":"boundedElastic-1"}
~~~

**Thread names and numbers are dynamic**—do not treat these as fixed stdout strings. Server transport, scheduler state, and runtime version can change the names, and JSON key order is not guaranteed.

The Java classes above live in a single file with `EventLoopDemoApplication` as the sole `public` class; the controller is in the same package and gets scanned. You cannot compile/run it with plain `javac` without Spring Boot/Reactor dependencies; use the project's Gradle/Maven build.

## 7. Why Is Blocking on the Event Loop Dangerous?

An event loop must keep cycling to handle events across many connections. If a callback runs:

- `Thread.sleep(...)`;
- synchronous JDBC/JPA/Hibernate;
- a blocking HTTP client;
- `Future.get()` or long lock contention;
- long synchronous file I/O;
- `Mono.block()` / `Flux.blockFirst()`;
- heavy CPU work or huge payload serialization;

then the event-loop thread cannot return in time to serve other connections.

There are two kinds of starvation:

1. **Blocking wait:** the thread waits on a database, network call, or lock without doing useful work.
2. **CPU monopolization:** the thread runs heavy computation without waiting on I/O, delaying other callbacks.

A Reactor operator does not make code inside it non-blocking:

~~~java
@GetMapping("/bad")
Mono<String> bad() {
    return Mono.just("ok")
            .map(value -> {
                try {
                    Thread.sleep(1000);
                } catch (InterruptedException ex) {
                    Thread.currentThread().interrupt();
                    throw new IllegalStateException(ex);
                }
                return value;
            });
}
~~~

This is a WebFlux controller fragment; if the pipeline runs on a Netty event loop, `Thread.sleep` stalls that event-loop thread for roughly one second. Other connections pinned to the same loop suffer increased latency.

Reactor can throw `IllegalStateException` when `block()` is invoked on threads marked non-blocking. **Do not rely on that exception to catch all blocking operations**: JDBC and `Thread.sleep` can block without throwing a similar error.

## 8. Moving Blocking Code Off the Event Loop

In systems that depend on legacy synchronous APIs while using WebFlux, wrap the work in a deferred/callable source and pick an appropriate scheduler:

~~~java
Mono<String> safe = Mono.fromCallable(() ->
        legacyClient.fetch()
).subscribeOn(Schedulers.boundedElastic());
~~~

`legacyClient` is a hypothetical business dependency; this fragment does not compile standalone. `Mono.fromCallable` defers calling `fetch()` until subscription; `subscribeOn` schedules subscription/source execution on `boundedElastic`, keeping blocking work off the event loop.

**Common mistake:**

~~~java
Mono<String> wrong = Mono.just(legacyClient.fetch())
        .subscribeOn(Schedulers.boundedElastic());
~~~

In the wrong example, Java executes `fetch()` **before** `Mono.just(...)` is even created, so the blocking call may already run on the request/event-loop thread. Adding `subscribeOn` after `just` cannot relocate code that has already executed.

Another note: `boundedElastic` does not have infinite threads or queues. If thousands of requests wait on slow JDBC at once, the pool or queue can saturate. Offloading protects the event loop, **but does not convert blocking I/O into non-blocking I/O**. You still need driver timeouts, connection pools, concurrency limits, and downstream load management.

### 8.1. subscribeOn vs. publishOn

- `subscribeOn(scheduler)` governs the subscription/upstream source context in the reactive pipeline.
- `publishOn(scheduler)` sets a scheduler boundary for downstream signals and operators that follow it.
- Calling `map` or `flatMap` does not spawn a new thread each time.
- A pipeline can switch threads multiple times; never rely on an entire request staying on one thread.

Example solely illustrating scheduler placement (requires application-defined `source` and `cpuBoundTransform`):

~~~java
Mono<String> transformed = source
        .publishOn(Schedulers.parallel())
        .map(value -> cpuBoundTransform(value));
~~~

`Schedulers.parallel()` suits bounded CPU-bound work, **not waiting on blocking JDBC**. Avoid switching schedulers unnecessarily on every operator because thread hopping carries scheduling and context-switching overhead.

## 9. Choose Non-Blocking Clients for End-to-End Reactive Flows

If a controller returns a `Mono` yet calls synchronous `RestClient` or blocking JDBC directly on the event loop, the execution path still blocks.

**Anti-pattern** with `WebClient`:

~~~java
@GetMapping("/bad-orders/{id}")
OrderDto badOrder(@PathVariable long id) {
    return webClient.get()
            .uri("/orders/{id}", id)
            .retrieve()
            .bodyToMono(OrderDto.class)
            .block();
}
~~~

This fragment does not compile standalone without a `webClient` bean, DTO, and imports. `block()` waits synchronously, risking event-loop stalls or Reactor rejections on non-blocking threads.

Natural reactive approach:

~~~java
@GetMapping("/orders/{id}")
Mono<OrderDto> getOrder(@PathVariable long id) {
    return webClient.get()
            .uri("/orders/{id}", id)
            .retrieve()
            .bodyToMono(OrderDto.class);
}
~~~

Using `WebClient` with a reactive connector allows the HTTP client to avoid holding an event-loop thread while waiting on the remote server. You still must configure timeouts, connection counts, pending-acquire queues, and retries; non-blocking does not mean surviving unbounded traffic.

For databases, traditional JDBC/JPA is blocking, whereas R2DBC is a reactive data-access option to consider **when dependencies, transactions, and driver features fit**. Do not migrate every project to R2DBC solely because of WebFlux; if the workload is predominantly blocking JDBC, Spring MVC may be simpler.

## 10. Backpressure and Concurrency Are Different Concepts

Project Reactor follows Reactive Streams: subscribers can emit **demand** to signal how many items they are ready to receive. Backpressure throttles data between components that support it.

However, **backpressure does not automatically make all HTTP requests immune to memory exhaustion**:

- A large JSON request still hits codec/decoder buffer limits.
- A source without demand support may require buffering, dropping, or erroring policies.
- Downstream HTTP/DB services have connection limits, throughput ceilings, and rate limits.
- An application can launch too many concurrent inner publishers in `flatMap` if concurrency is unbounded.

Fragment illustrating bounding concurrent remote calls:

~~~java
Flux<Result> results = ids.flatMap(
        id -> remoteClient.fetch(id),
        8
);
~~~

This is a fragment: `ids`, `Result`, and `remoteClient` must be defined in the application. The number `8` caps concurrent inner publishers in `flatMap` at that operator; it is not a Reactor Netty global setting. Measure throughput, error rate, and downstream latency to pick a sensible limit.

**The event loop** drives I/O and callback execution; **backpressure** regulates data flow rate; **concurrency limits** cap in-flight work. They complement one another and cannot substitute for each other.

## 11. ThreadLocal, MDC, and Request Context

In synchronous Servlets, code often relies on `ThreadLocal` to hold request IDs, security context, or logging MDC data. In a reactive pipeline, operators can run across multiple threads:

~~~text
Event-loop thread A: ThreadLocal(requestId=123)
      |
      +-- publishOn(boundedElastic)
                    |
                    v
         boundedElastic thread B:
         ThreadLocal does not carry requestId=123 automatically
~~~

Never assume `ThreadLocal` crosses scheduler boundaries automatically. Project Reactor provides **`Context`** tied to the subscriber chain; reactive Spring Security uses reactive security context, and tracing frameworks provide context-propagation integrations.

Reactor `Context` fragment (import `reactor.core.publisher.Mono`):

~~~java
Mono<String> request = Mono.deferContextual(ctx ->
        Mono.just("requestId=" + ctx.get("requestId"))
).contextWrite(ctx -> ctx.put("requestId", "abc"));

request.subscribe(System.out::println);
~~~

Output of this synchronous fragment:

~~~text
requestId=abc
~~~

`Context` is not a global variable shared across requests. Avoid storing secrets/tokens where they could end up logged, and do not assume third-party libraries read Reactor `Context` without explicit integration.

## 12. Timeouts, Cancellation, and Asynchronous Flows

WebFlux can cancel a subscription when the client disconnects or an operator no longer needs further signals. In a pipeline:

~~~java
Mono<Item> item = itemClient.fetch(id)
        .timeout(Duration.ofSeconds(2));
~~~

This is a fragment; `Item`, `itemClient`, and `id` belong to application code not shown here. The `timeout` operator bounds how long the reactive pipeline waits for signals. Yet **Reactor-level cancellation or timeout does not guarantee an immediate abort of a blocking JDBC call** running inside an OS thread. The I/O library often needs its own timeout.

Combine multiple safeguards:

1. Appropriate HTTP client connection/connect/read/response timeouts.
2. DB connection/query timeouts and connection pool limits.
3. Concurrency limits and retries with backoff and max attempts.
4. Cancellation/error handling that closes unused resources.
5. Avoiding uncontrolled fire-and-forget `subscribe()` calls inside controllers.

Even in WebFlux, a CPU-heavy callback still hogs the event loop; timeouts alone do not fix CPU starvation.

## 13. Compare Performance by Measurement, Not Slogans

Suppose 100 concurrent requests arrive, each waiting ~200 ms on an external API and using only 2 ms of CPU:

- With synchronous Servlets calling a blocking client, many worker threads remain occupied while waiting.
- With WebFlux using a non-blocking HTTP client, event-loop threads do not sit idle while the external API responds.

However, this **does not prove WebFlux is always faster**. If the external API rate-limits you, the database pool has 10 connections, or CPU saturates, throughput remains capped. Async Servlets or virtual threads can also reduce waiting thread overhead for certain workloads.

Little's Law at steady state:

~~~text
Average concurrency ≈ throughput (requests/sec) × average latency (seconds)
~~~

For example, 200 requests/sec at 0.25 seconds average latency corresponds to roughly **50 concurrent in-flight requests**. Do not treat that number 50 as how many event-loop threads to allocate: request concurrency differs from I/O thread count.

Metrics worth measuring:

- Request throughput, p50/p95/p99 latency, error rate, and timeouts.
- CPU, heap, GC, stack/native memory.
- Event-loop delay or pending task queues where instrumentation supports them.
- `boundedElastic` queue depth and active workers when instrumented.
- DB pool, HTTP client connection pool, and downstream latency.
- Open connection counts and data transfer rates.
- Breakdown between receiving a request, calling downstream, and sending the response.

Exact metrics and names depend on Reactor Netty version, Micrometer/Actuator, and observability setup; do not assume all metrics appear automatically.

## 14. Investigating a Stalled Event Loop

Common symptoms include p95/p99 latency spiking across clusters of requests, thread dumps showing `reactor-http-*` threads waiting on blocking I/O or heavy CPU work, rising HTTP client timeouts, and growing task queues.

Diagnostic steps:

1. **Verify the active stack.** Inspect runtime classpath, startup logs, and `ApplicationContext` to confirm WebFlux + Reactor Netty is running, not Spring MVC selected by having both starters.
2. **Inspect thread dumps.** Look for `Thread.sleep`, JDBC, file I/O, lock contention, `block()`, or heavy JSON serialization/computation on event-loop threads.
3. **Measure each stage.** Don't just time the controller; inspect decode, service, downstream calls, encode, and response I/O.
4. **Check schedulers.** After offloading, is `boundedElastic`'s queue backing up or hitting capacity?
5. **Check downstream dependencies.** Are DB/external API connection pools exhausted, returning 429/503, or timing out?
6. **Test under controlled load.** Compare before and after changing schedulers, drivers, or concurrency limits.
7. **Examine tracing.** With Micrometer/Actuator and tracing, propagate request/trace IDs properly across the reactive chain.

BlockHound can help in development and testing on compatible versions by detecting many blocking APIs called on non-blocking threads. It does not catch every CPU hotspot and does not replace profilers or thread dumps; verify JDK/framework compatibility before enabling it.

Example logging the thread name inside a pipeline (fragment requiring declared `itemService` and `log`):

~~~java
return itemService.findById(id)
        .doOnNext(item -> log.debug(
                "operator thread={}", Thread.currentThread().getName()
        ));
~~~

The thread name only indicates where **that operator** ran at that moment; it does not prove the entire request stays on that thread. Never log tokens, sensitive request bodies, or personal data.

## 15. When to Choose Spring MVC vs. When to Choose WebFlux

### Spring MVC / Servlet Often Makes Sense When

- The project depends heavily on JDBC, JPA/Hibernate, or mature synchronous libraries.
- The team is comfortable debugging and managing transactions in synchronous flows.
- Current throughput/latency meets SLAs with no network-wait bottleneck requiring reactive architecture.
- The system needs compatibility with Servlet filters, interceptors, and existing integrations.
- Servlet async or virtual threads meet concurrency needs without changing the entire architecture.

### Spring WebFlux / Reactor Netty Often Makes Sense When

- There are many concurrent connections, streaming, gateway workloads, or high-fan-out I/O.
- Most critical dependencies offer non-blocking APIs.
- The team understands Reactor, backpressure, cancellation, schedulers, and context propagation.
- Monitoring is in place to detect event-loop blocking, queue saturation, and downstream limits.

### When Mixing Is Unavoidable

An isolated blocking call can be wrapped with `Mono.fromCallable(...).subscribeOn(Schedulers.boundedElastic())` and bounded concurrency. Yet if **most of the pipeline** blocks, WebFlux adds complexity without performance wins. Benchmark with workloads and production-like conditions before committing.

## 16. Common Mistakes

**Mistake 1 — Assuming WebFlux uses one thread for all requests.** Reactor Netty actually runs multiple event-loop threads alongside other schedulers. Inspect thread dumps instead of guessing from framework names.

**Mistake 2 — Assuming Servlets hold one thread per keep-alive connection.** Threads serve active synchronous requests while connections stay open across requests; Servlets also support async processing.

**Mistake 3 — Putting JDBC inside `Mono.just(jdbcCall())`.** JDBC runs **before** the publisher is constructed. Use a deferred source and offload if unavoidable, or use a synchronous stack.

**Mistake 4 — Calling `block()` in a WebFlux controller.** It can stall the event loop or be rejected by Reactor. Return publishers and compose pipelines instead of blocking.

**Mistake 5 — Calling `Thread.sleep` inside `map`.** `map` does not switch threads automatically. Use non-blocking timers or an appropriate scheduler when blocking APIs are unavoidable.

**Mistake 6 — Running JDBC on `Schedulers.parallel()`.** The parallel scheduler fits short CPU-bound tasks, not waiting on blocking I/O.

**Mistake 7 — Offloading everything to `boundedElastic` and calling it non-blocking.** Blocking still consumes worker threads, queue slots, and downstream resources.

**Mistake 8 — Relying on `ThreadLocal`/MDC as in synchronous code.** Context can vanish across scheduler switches. Use Reactor `Context` and context-propagation integrations.

**Mistake 9 — Leaving concurrency and timeouts unbounded.** Non-blocking does not mean downstream services can absorb infinite traffic.

**Mistake 10 — Judging performance solely by thread count.** Compare throughput, latency, error rate, CPU, memory, DB/HTTP pools, and reliability.

**Mistake 11 — Including both `starter-web` and `starter-webflux` and assuming the server is reactive.** Spring Boot defaults to Servlet MVC when both are present; verify the active stack at startup.

**Mistake 12 — Returning `Flux` while calling a blocking API for every element.** A publisher does not turn I/O sources non-blocking; check every stage of the pipeline.

## 17. Implementation Checklist

- Confirm whether the application actually runs Spring MVC/Servlet or WebFlux/Reactor Netty.
- Never block event-loop threads with JDBC, blocking HTTP clients, `block()`, `Thread.sleep`, or long CPU work.
- Wrap unavoidable blocking libraries in deferred sources with `subscribeOn(Schedulers.boundedElastic())`.
- Prefer `WebClient` and non-blocking data access when targeting end-to-end reactivity.
- Use `parallel` for suitable CPU work; understand `subscribeOn` vs. `publishOn` before switching schedulers.
- Bound concurrency, buffers, HTTP/DB connection pools, and retries; never treat backpressure as infinite resources.
- Use Reactor `Context` or proper context propagation to carry request state across threads.
- Manage cancellation, HTTP/DB timeouts, resource lifecycles, and downstream failures.
- Monitor p95/p99 latency, throughput, thread dumps, event-loop delay, scheduler queues, DB pools, and GC.
- Load-test slow downstream responses, high connection counts, and mid-request client disconnects.
- Evaluate Servlet async or virtual threads when workloads rely heavily on blocking libraries.

**Key takeaway:** In synchronous Servlet MVC, a worker thread is typically bound to active request execution; in WebFlux on Reactor Netty, event-loop threads serve many connections without sitting idle during non-blocking I/O. WebFlux's benefits come from **end-to-end non-blocking design**, not merely from returning `Mono` or `Flux`. If you block the event loop, the very mechanism meant to scale concurrency becomes a performance bottleneck.

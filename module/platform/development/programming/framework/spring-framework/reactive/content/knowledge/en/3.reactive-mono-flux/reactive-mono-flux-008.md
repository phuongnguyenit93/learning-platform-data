# Why WebFlux Is Usually the One That Subscribes

**Module:** Spring Framework – reactive  
**Parent topic:** Mono and Flux

## What Will You Understand After This Lesson?

- Why WebFlux controllers typically **return** `Mono`/`Flux` instead of calling `subscribe()` themselves.
- Where the subscriber actually appears in the HTTP lifecycle, and who coordinates sending the response, demand, errors, and cancellation.
- Why manual `subscribe()` can detach work from the HTTP request, return responses too early, miss errors, or duplicate side effects.
- When an application **needs to subscribe itself** (at an application-owned boundary) and when to use `StepVerifier`, `WebTestClient`, or `block()` in tests.
- Important exceptions: `Mono`/`Flux` do not automatically guarantee that everything is lazy, cold, or immediately cancellable; nor is WebFlux always the Java class directly invoking the `subscribe` method.

## 1. What Are `Mono` and `Flux`, and What Makes Them Run?

`Mono<T>` represents a publisher that emits **at most one element**, then completes or signals an error. `Flux<T>` can emit 0 to many elements. Both implement Reactive Streams `Publisher<T>`. A publisher is **subscribed to** when a subscriber calls `Publisher.subscribe(subscriber)`, producing an `onSubscribe(Subscription)` signal; the subscriber then requests data with `request(n)` and receives `onNext`, `onComplete`, or `onError` per the protocol.

For most **cold** publishers in Reactor, building a pipeline with `map`, `flatMap`, `filter`, `delayElement`, etc. only describes the processing steps. They execute deferred work only when subscribed to.

```java
Mono<String> greeting = Mono.defer(() -> {
    System.out.println("Running deferred work");
    return Mono.just("Hello");
});
// No one subscribes to greeting here,
// so "Running deferred work" is not printed yet.
```

This is an **illustrative snippet** using `reactor.core.publisher.Mono`, not a standalone Java program. Upon subscription, `Mono.defer`'s supplier runs. However, **not every operation is deferred**: Java still evaluates expressions when assembling the pipeline. For instance, `Mono.just(expensiveCall())` calls `expensiveCall()` immediately when creating the `Mono`; `Mono.defer(() -> Mono.just(expensiveCall()))` defers the call per subscription. A hot publisher may already be emitting data even before a late subscriber subscribes.

### The Role of WebFlux

In an HTTP application using Spring WebFlux, controller code usually just **declares the work** and **returns the publisher**:

```java
@GetMapping("/users")
public Flux<UserDto> users() {
    return userService.findAll();
}
```

The snippet above is an **illustration inside a controller**, assuming `UserDto`, `userService`, and the corresponding imports exist. The controller does not need to call `subscribe()` itself: WebFlux composes the publisher returned by the controller into the HTTP response processing pipeline, and **the WebFlux infrastructure together with the reactive HTTP server** owns subscribing, reading elements, and writing data out to the client.

The phrase "WebFlux subscribes" must be understood accurately: it describes **HTTP boundary ownership**. Depending on version, server adapter, handler, codec, and return type handling, the direct `subscribe(...)` call may live inside the HTTP/transport infrastructure classes (such as Reactor Netty), rather than right inside a `@RestController` method or a call immediately after `return`. The pipeline handling **the entire request** already has a subscriber at the server boundary; the publisher returned from the controller is composed into that pipeline and consumed when the response is processed.

## 2. From Request to Response: The Subscription Lifecycle

A typical flow with an annotated controller returning `Mono<T>` or `Flux<T>`:

```text
Client sends HTTP request
          |
          v
Reactive HTTP server / WebFlux adapter
          |
          v
DispatcherHandler -> selects handler/controller
          |
          v
Controller creates and returns Mono<T> or Flux<T>
          |
          v
HandlerResultHandler + HttpMessageWriter/encoder
          |
          v
ServerHttpResponse.writeWith(...) / writeAndFlushWith(...)
          |
          v
Server runtime subscribes to/consumes response publisher
          |
          +-- onSubscribe -> request(n) when ready to process more
          +-- onNext(value) -> encode / write response
          +-- onComplete -> complete response
          +-- onError(error) -> handle error per response state
          +-- cancel -> signal downstream stop on cancellation
```

This is a **conceptual diagram**, not a fixed stack trace: WebFlux may create and subscribe to intermediate chains in various ways. What to remember is that the controller's publisher feeds into the HTTP response mechanism; this boundary coordinates most of the lifecycle.

- **Before subscription**, lazy operators have not run yet. The controller may already have been invoked to build the publisher, but actions inside `defer`/`flatMap` have typically not executed.
- **When infrastructure consumes the publisher**, it receives signals and encodes data according to the `HttpMessageWriter`, result type, codec, and `Content-Type`. With a short `Mono<String>` body, it usually receives one string and completes; with streaming `Flux`, the response can be sent incrementally.
- **When the source signals an error**, WebFlux has the opportunity to route the error through the HTTP chain's error handling. If the response has not been committed yet, the framework can choose an error status/body; if headers or part of the body have already been sent, the HTTP status already sent cannot arbitrarily be changed.
- **When the client disconnects**, closing the connection can propagate cancellation into the pipeline. Exact timing and effectiveness depend on the server/transport and whether the source supports cancellation. `cancel` does not guarantee immediately halting a blocking operation or already-started side effect.

### Backpressure and Data Demand

Reactive Streams is not just "calling functions asynchronously". A `Subscription` lets the receiver issue `request(n)` so upstream knows the level of demand. HTTP write infrastructure can regulate demand according to write readiness, codecs, buffers, and transport. Do not infer that each TCP packet, each JSON line, or each flush corresponds one-to-one with a `request(1)` call: operators may `prefetch`/buffer and codecs have their own framing.

**Important:** Calling `subscribe()` **does not automatically create a new thread**. A synchronous cold publisher like `Flux.range` can run directly on the subscribing thread until completion or until paused by demand; asynchrony arises when sources/operators actively use schedulers or non-blocking I/O.

## 3. Runnable Example: Controller Returns Publisher, WebFlux Consumes

This example uses **Java 17+**, **Spring Boot 3.3.5** (Spring WebFlux and Reactor Netty), and **Maven**. This is a pinned version for a reproducible example; in real projects use the version managed and still supported by your project.

File structure:

```text
webflux-subscribe-demo/
├── pom.xml
└── src/main/java/demo/
    ├── WebfluxSubscribeApplication.java
    └── DemoController.java
```

### `pom.xml`

```xml
<project xmlns="http://maven.apache.org/POM/4.0.0"
         xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
         xsi:schemaLocation="http://maven.apache.org/POM/4.0.0 https://maven.apache.org/xsd/maven-4.0.0.xsd">
    <modelVersion>4.0.0</modelVersion>

    <parent>
        <groupId>org.springframework.boot</groupId>
        <artifactId>spring-boot-starter-parent</artifactId>
        <version>3.3.5</version>
        <relativePath/>
    </parent>

    <groupId>demo</groupId>
    <artifactId>webflux-subscribe-demo</artifactId>
    <version>1.0.0</version>

    <properties>
        <java.version>17</java.version>
    </properties>

    <dependencies>
        <dependency>
            <groupId>org.springframework.boot</groupId>
            <artifactId>spring-boot-starter-webflux</artifactId>
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

### `src/main/java/demo/WebfluxSubscribeApplication.java`

```java
package demo;

import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;

@SpringBootApplication
public class WebfluxSubscribeApplication {
    public static void main(String[] args) {
        SpringApplication.run(WebfluxSubscribeApplication.class, args);
    }
}
```

### `src/main/java/demo/DemoController.java`

```java
package demo;

import java.time.Duration;
import java.util.Locale;
import java.util.concurrent.atomic.AtomicInteger;
import org.springframework.http.MediaType;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.PostMapping;
import org.springframework.web.bind.annotation.RequestBody;
import org.springframework.web.bind.annotation.RestController;
import reactor.core.publisher.Mono;

@RestController
public class DemoController {
    private final AtomicInteger helloSubscriptions = new AtomicInteger();

    @GetMapping(value = "/hello", produces = MediaType.TEXT_PLAIN_VALUE)
    public Mono<String> hello() {
        System.out.println("handler: create publisher");

        return Mono.defer(() ->
                Mono.just("hello #" + helloSubscriptions.incrementAndGet()))
                .doOnSubscribe(subscription ->
                        System.out.println("hello: subscribed"));
    }

    @GetMapping(value = "/managed", produces = MediaType.TEXT_PLAIN_VALUE)
    public Mono<String> managed() {
        return delayedWork().thenReturn("work complete");
    }

    // Anti-pattern illustration only: do not follow in real handlers.
    @GetMapping(value = "/detached", produces = MediaType.TEXT_PLAIN_VALUE)
    public Mono<String> detached() {
        delayedWork().subscribe(
                value -> System.out.println("detached result: " + value),
                error -> System.err.println("detached error: " + error));
        return Mono.just("accepted");
    }

    @PostMapping(
            value = "/upper",
            consumes = MediaType.TEXT_PLAIN_VALUE,
            produces = MediaType.TEXT_PLAIN_VALUE)
    public Mono<String> upper(@RequestBody Mono<String> body) {
        return body.map(value -> value.toUpperCase(Locale.ROOT));
    }

    private Mono<String> delayedWork() {
        return Mono.delay(Duration.ofMillis(250))
                .map(tick -> "finished");
    }
}
```

Run in the directory containing `pom.xml`:

```bash
mvn spring-boot:run
```

Open another terminal and run **each command one by one**. On Windows PowerShell, use `curl.exe` to avoid PowerShell's `curl` alias; on Linux/macOS you can use `curl`:

```powershell
curl.exe -s http://localhost:8080/hello
curl.exe -s http://localhost:8080/hello
curl.exe -s http://localhost:8080/managed
curl.exe -s http://localhost:8080/detached
curl.exe -s -X POST -H "Content-Type: text/plain" --data "webflux" http://localhost:8080/upper
```

**Expected response bodies**, in the order of the commands above and assuming no other requests called `/hello`:

```text
hello #1
hello #2
work complete
accepted
WEBFLUX
```

`curl.exe -s` does not append a newline to responses lacking one, so text may run together if typed in a single script; the block above presents **each body separately** for readability. The application console contains other Spring Boot logs; the lines we explicitly printed on the first call to `/hello` are:

```text
handler: create publisher
hello: subscribed
```

The controller does not need to call `subscribe` itself for the second line to appear. `Mono.defer` inside `hello()` increments the counter when the publisher is subscribed to; the next request gets a new subscription and produces `hello #2`.

`/managed` composes the delayed work with the response using `thenReturn`. WebFlux finishes the response once the work chain completes. `/detached` intentionally illustrates the wrong pattern: the method opens **a separate subscription** and returns `accepted` independently of that result. The line `detached result: finished` may appear after the response and log order depends on the scheduler; there is no guarantee that the HTTP request is waiting for or tracking it. `/upper` illustrates `@RequestBody Mono<String>` input: WebFlux decodes the request body and composes it into response handling without calling subscribe on `body`.

## 4. Why Is Calling `subscribe()` Inside a Controller Usually Wrong?

Compare two ways of handling the same reactive task, assuming `orderService.save(request)` returns `Mono<Order>`:

**Wrong way – subscribing manually and returning another result:**

```java
@PostMapping("/orders")
public Mono<String> createOrder(@RequestBody Mono<OrderRequest> input) {
    input.flatMap(orderService::save)
         .subscribe(saved -> audit(saved));
    return Mono.just("accepted");
}
```

**Right way – returning the composed chain:**

```java
@PostMapping("/orders")
public Mono<String> createOrder(@RequestBody Mono<OrderRequest> input) {
    return input.flatMap(orderService::save)
                .doOnNext(saved -> audit(saved))
                .thenReturn("created");
}
```

Both snippets **are illustrative controller code**, assuming the application defines `OrderRequest`, `Order`, `orderService`, and `audit(...)`. `doOnNext` is suited for lightweight, synchronous observation; if `audit` performs I/O or returns a reactive publisher, you must **compose** it with `flatMap`/`then` or an appropriate transactional pattern, rather than using `doOnNext` to call subscribe manually.

In the wrong approach:

1. `subscribe` immediately creates a first subscriber for the order-saving logic. The HTTP response `Mono.just("accepted")` is **a different publisher**.
2. The client may receive `accepted` before saving succeeds or fails. Save errors do not automatically turn into the returned HTTP error; a `subscribe` call without a complete error handler can also leave errors unmanaged on the detached branch.
3. If the client disconnects, cancellation of the response branch **does not automatically** cancel the manually subscribed branch.
4. Request context, tracing, security, transactions, and resources tied to the original subscription may not flow into the new branch the way you expect; branching must be designed and managed explicitly.
5. If you also return or subscribe to a cold publisher again elsewhere, side effects such as database writes, HTTP calls, or event emissions **can run twice**.

In the right approach, the save outcome is part of the returned pipeline. `thenReturn("created")` emits the string only after the preceding operation completes successfully. `onError` propagates along the chain for WebFlux error handling; cancellation also has a propagation path upstream when supported by the source.

### If Audit Is Reactive Work

Use composition to link results and errors explicitly:

```java
return input.flatMap(orderService::save)
            .flatMap(saved -> auditService.record(saved)
                    .thenReturn(saved))
            .thenReturn("created");
```

This is an **illustrative** snippet, assuming `auditService.record(saved)` returns `Mono<Void>`. The response succeeds only when both steps succeed; atomicity guarantees between saving the order and auditing still depend on transactions/outbox and data sources, and cannot be inferred from `flatMap` alone.

### Both `subscribe()` and `block()` Create Another Subscription

- `publisher.subscribe(...)` creates a subscription and returns a `Disposable` in Reactor; callbacks are not wired to the HTTP response by default.
- `publisher.block()` also creates a subscription and then **waits synchronously** for the result. Using it in a WebFlux handler on a non-blocking event loop can throw `IllegalStateException` or hurt throughput; do not call `block()` to "pull a value out of a Mono" inside a controller.
- `publisher.toFuture()` or another terminal operation can also consume a publisher; what matters is **who owns the terminal boundary**, not merely the method name.

In handlers, prefer `map`, `flatMap`, `zip`, `then`, `onErrorResume`, and **return the composed publisher**. If you only need to return `Mono<Void>`, return the completion chain:

```java
@PostMapping("/notifications")
public Mono<Void> notify(@RequestBody Mono<Message> input) {
    return input.flatMap(notificationService::send).then();
}
```

This is an **illustrative snippet**, assuming `Message` and the service are defined by the application. When `Mono<Void>` completes, WebFlux knows processing has finished; if an error occurs, the error remains inside the HTTP chain.

## 5. Practical Consequences of Letting WebFlux Manage Subscriptions

### 5.1. Completing the Response at the Right Time

With a `Mono<T>` response, the publisher's terminal state helps determine when the server can finish the body. With `Flux<T>`, the server can process multiple elements per codec. `Content-Type: text/event-stream` commonly uses SSE to emit per event; `application/json` may need to structure data in valid JSON format without necessarily flushing each element. Do not confuse a single element in a `Flux` with an individual HTTP response.

### 5.2. Errors Follow the Right Path

A `Mono.error(...)` in the returned pipeline can be routed by WebFlux through a `WebExceptionHandler` or the application's error-handling mechanism while the response is still modifiable. `doOnError` only observes errors; it does **not** replace them. If you need to turn an error into a value, use `onErrorResume`; if you want to keep it as an error for the server to handle, let the error propagate or use `onErrorMap` when appropriate.

```java
return userService.findById(id)
        .switchIfEmpty(Mono.error(new ResponseStatusException(
                HttpStatus.NOT_FOUND, "User not found")));
```

This is an **illustrative snippet**, requiring Spring imports plus `id` and `userService` provided by the application. If the user is not found, the error stays inside the returned publisher and can produce HTTP 404 before the response is committed.

### 5.3. Backpressure and Cancellation Can Propagate Upstream

Infrastructure-managed subscription allows the HTTP consumer to regulate demand, and downstream cancellation can propagate upstream to the source. For example, closing the connection mid-stream while the server is streaming many elements can cause the subscription to receive `cancel` and stop producing further items. Still, do not expect every task or socket to stop instantaneously.

For sources that allocate per-subscription resources, clean up with `using`/`usingWhen` or track all termination kinds with `doFinally`:

```java
return someFlux
        .doFinally(signal -> metrics.recordTermination(signal));
```

This is an **illustrative snippet**: `metrics` and `someFlux` are application components. `signal` can indicate completion, error, or cancellation; `cancel` does not emit `onComplete`. Do not rely solely on `doOnComplete` to clean up resources when a client disconnects.

### 5.4. Subscription Context Is Preserved Across the Pipeline

Reactor `Context` attaches data per **subscription**, which is useful for tracing, correlation info, and reactive security/transaction components. When the controller returns the same pipeline, WebFlux components and operators have a consistent path for propagating context. When calling `subscribe` manually to spawn a detached branch, you must explicitly determine which context is carried over; do not assume every `ThreadLocal` or Reactor `Context` is automatically copied to the new subscription.

### 5.5. Managing I/O Without Occupying the Event Loop

Returning `Mono`/`Flux` enables WebFlux to work with reactive I/O without blocking threads. This **does not turn a blocking call into a non-blocking one**. For example, calling synchronous JDBC inside `map` can still block the event loop; manual `subscribe()` will not fix it either. For new systems, use appropriate reactive APIs (WebClient, R2DBC, etc.) whenever possible. If forced to wrap a synchronous source, consider `Mono.fromCallable(...).subscribeOn(Schedulers.boundedElastic())` paired with resource limits and timeout policies; that is a bridge, not a replacement for non-blocking I/O.

## 6. Cases Where the "WebFlux Subscribes" Rule Needs Nuance

| Case | Who Usually Owns Subscribe? | Appropriate Implementation |
| --- | --- | --- |
| `@RestController` returning `Mono<T>`/`Flux<T>` | WebFlux/server HTTP processing pipeline | Return the publisher; framework writes the response. |
| WebFlux.fn with `ServerResponse` | WebFlux/server pipeline | Return `Mono<ServerResponse>` from handler, pass body to builder. |
| `WebFilter` | HTTP pipeline already managed by infrastructure | Return `chain.filter(exchange)` and compose operators; do not subscribe to chain manually. |
| `@RequestBody Mono<T>` or `Flux<T>` | Body source is consumed when composed into the HTTP pipeline | Compose `input.flatMap(...)`; do not subscribe manually in controller. |
| Hot event `Flux`, SSE | HTTP pipeline subscribes per client; event source may run independently | Define multicast, replay, backpressure, and source lifecycle. |
| Background consumer, worker, event listener, or CLI with no HTTP framework consumer | Startup/consumer component **managed by the application** | Can subscribe proactively; manage `Disposable`, errors, cancellation, and shutdown. |
| Pure Reactor unit test | Test harness | Use `StepVerifier`; can `block()` at an appropriate test boundary. |
| WebFlux endpoint test | `WebTestClient`/server test infrastructure | Call `exchange()` then assert status/body; test client drives the HTTP flow. |

This does not mean **every** subscription must be performed by WebFlux. The rule applies only when the publisher is the result of a request/response that the framework will consume. If you intentionally build a pipeline outside any boundary (such as a background task started at application boot), no HTTP consumer will automatically "come subscribe for you".

### Example of a Terminal Boundary Outside a Request

```java
Disposable subscription = Flux.interval(Duration.ofSeconds(1))
        .subscribe(
                value -> handleTick(value),
                error -> handleFailure(error));

// When the application stops:
subscription.dispose();
```

**Illustrative** snippet, not a standalone runnable application: requires imports for `reactor.core.Disposable`, `reactor.core.publisher.Flux`, `java.time.Duration`, and definitions of `handleTick`/`handleFailure`. For long-lived subscriptions, retain the handle to clean up on shutdown; when data reliability is needed, provide retries, error monitoring, and state persistence. `subscribe()` is completely appropriate here **if** this component owns and manages the consumer lifecycle.

## 7. Common Misconceptions

| Misconception | Reality |
| --- | --- |
| "Without calling `subscribe()`, the API won't run." | For publishers returned from a WebFlux handler, the HTTP runtime has its own consumer and will consume the chain. |
| "`subscribe()` is always asynchronous." | No. Synchronous sources can run immediately on the current thread; schedulers/async I/O are needed to change the execution context. |
| "`return Mono.just(service.call())` is lazy." | `service.call()` executes before `Mono.just` is created; use reactive APIs or `defer` when deferral is desired. |
| "Calling `subscribe()` in the controller makes the API fast and reliable." | The response may return before work finishes and no longer reflects errors; tasks requiring background execution need a dedicated durable/background design. |
| "WebFlux always subscribes exactly once." | Do not treat that as a contract: resubscribe, retry, repeat, cache/share, multiple consumers, or other integrations can change subscription counts. |
| "Cancelling the HTTP response immediately stops every database call." | Cancellation is a stop request, dependent on the source and transport; already-committed side effects are not automatically undone. |
| "An error in a manually subscribed branch always makes WebFlux return HTTP 500." | A separate subscription has its own error channel; the HTTP response is not automatically affected. |
| "Two requests sharing the same `Flux` always share one `Subscription`." | Each subscriber has its own subscription relationship; cold/hot source semantics decide whether progress and data are shared. |
| "`doOnNext` works for all side effects, including async I/O." | `doOnNext` is a synchronous observation callback; reactive I/O must be composed with `flatMap`/`then`. |
| "Using `block()` is how you get values in a controller." | `block()` creates another subscription and blocks the thread; avoid it in non-blocking request handlers. |

## 8. Self-Check Exercises

**Exercise 1.** Why does the endpoint below still respond even though the controller does not call `subscribe()`?

```java
@GetMapping("/answer")
public Mono<Integer> answer() {
    return Mono.just(42);
}
```

**Answer:** The publisher is returned to WebFlux. The HTTP server's pipeline consumes the publisher to produce the response. This is an illustrative snippet in a `@RestController`, requiring the corresponding imports.

**Exercise 2.** Does the snippet below guarantee saving completes before returning `ok`?

```java
service.save(item).subscribe();
return Mono.just("ok");
```

**Answer:** No. The two pipelines are detached, so the response does not wait for completion/errors of `save`. If `save` returns `Mono<?>`, one way to compose it is `return service.save(item).thenReturn("ok");`. This is an illustrative snippet where `service` and `item` are defined by the application.

**Exercise 3.** Is "Calling `subscribe()` twice makes WebFlux send two responses" true?  
**Answer:** No. Two subscriptions create two consumptions of the publisher; they do not automatically turn into two HTTP responses. A WebFlux-managed response has its own lifecycle. If a cold source has side effects, two subscriptions can unintentionally repeat those side effects.

**Exercise 4.** A controller returns `Flux<Long>` emitting numbers on a timer. If the client disconnects mid-way, what is guaranteed?  
**Answer:** Nothing guarantees every operation stops at the exact instant of disconnection. Infrastructure can send cancellation to the subscription; sources and operators must honor cancellation, and already-executed side effects cannot be automatically reversed.

**Exercise 5.** When is calling `subscribe` manually right?  
**Answer:** At an application-owned boundary (background consumer, event stream, CLI), when no framework will consume the publisher for you, and the application fully manages completion, errors, cancellation, and resource lifetimes.

## Key Takeaway

**In a WebFlux handler, return the `Mono`/`Flux` representing all work tied to the HTTP request.** WebFlux and the reactive HTTP server consume the publisher to coordinate the body, errors, backpressure, and cancellation. Calling `subscribe()` manually inside a controller creates an independent branch of work, usually breaking the link between business outcomes and the HTTP response. Only subscribe manually when you truly own the terminal boundary and subscriber lifecycle.

### References

- [Spring Framework – Reactive Web Applications / WebFlux](https://docs.spring.io/spring-framework/reference/web/webflux.html): WebFlux architecture and asynchronous HTTP processing.
- [Spring Framework – @ResponseBody](https://docs.spring.io/spring-framework/reference/web/webflux/controller/ann-methods/responsebody.html): how annotated controllers write response bodies.
- [Project Reactor – Simple Ways to Create a Flux or Mono and Subscribe to It](https://projectreactor.io/docs/core/release/reference/coreFeatures/simple-ways-to-create-a-flux-or-mono-and-subscribe-to-it.html): subscriptions and terminal operations.
- [Project Reactor – Backpressure](https://projectreactor.io/docs/core/release/reference/subscribe-backpressure.html): demand and `BaseSubscriber`.
- [Reactive Streams for the JVM – Specification](https://github.com/reactive-streams/reactive-streams-jvm): `Publisher`, `Subscriber`, and `Subscription` contracts.

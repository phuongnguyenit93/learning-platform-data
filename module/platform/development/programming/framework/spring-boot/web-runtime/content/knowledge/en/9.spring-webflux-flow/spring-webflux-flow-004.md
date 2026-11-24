# Mono, Flux, and Execution Timing Upon Subscription

In Spring WebFlux, the two most common types are Project Reactor's `Mono<T>` and `Flux<T>`. A widespread misconception is thinking that when execution reaches `Mono.just(...)`, `map(...)`, or returns a `Flux`, all work inside the pipeline has already executed. In practice, you must distinguish **assembly time (creating the flow description)**, **subscription time (a subscriber registering for signals)**, **demand time (downstream requesting items via `request(n)`)**, and **emission time (`onNext`/`onError`/`onComplete` signals)**.

Understanding this boundary is essential for reading WebFlux code, avoiding double execution, avoiding manual `subscribe()` calls inside controllers, handling errors, and applying backpressure properly. This lesson uses Java 17+ and Reactor on Spring Boot 3.3.x; illustrative examples work in projects with the corresponding dependencies.

## 1. What Are Mono and Flux?

Project Reactor implements Reactive Streams and provides two primary publishers:

| Type | Max elements | Valid terminations | Use cases |
|---|---:|---|---|
| `Mono<T>` | 0 or 1 | Complete empty, emit one value then complete, or error | Fetch one record, respond to an HTTP request, write one update |
| `Flux<T>` | 0 to N | Emit multiple values then complete, or error; may be infinite | Data lists, event streams, changes over time |

Publisher creation examples:

~~~java
Mono<String> one = Mono.just("hello");
Mono<String> none = Mono.empty();
Mono<String> failed = Mono.error(new IllegalStateException("unavailable"));

Flux<Integer> many = Flux.just(10, 20, 30);
Flux<Integer> range = Flux.range(1, 5);
Flux<Integer> noItems = Flux.empty();
~~~

`Mono.just("hello")` holds an already-available value; `Flux.range(1, 5)` describes integers 1 through 5 (the second parameter is the **count**, not the upper bound). `Mono.empty()` emits no value and completes successfully. `Mono.error(...)` emits an error signal when subscribed rather than turning an exception into a data item.

Core point: **`Mono` and `Flux` are Publishers, not computed values or populated collections.** A `Mono<User>` differs from a `User`; a `Flux<User>` differs from a `List<User>`. A `Publisher` describes how signals are delivered to a subscriber.

`Mono` does not allow `null` as an `onNext` element. If a source may have no data, use `Mono.empty()`, `Mono.justOrEmpty(value)`, or design an appropriate result type.

## 2. Reactive Streams: Publisher, Subscriber, and Subscription

Four primary roles in Reactive Streams:

- **Publisher<T>**: a source capable of providing up to as many elements as its protocol permits.
- **Subscriber<T>**: the receiver of data and completion/error signals.
- **Subscription**: the link between `Publisher` and `Subscriber`; supports `request(n)` and `cancel()`.
- **Processor<T,R>**: both receives and emits data—a combined processing stage.

Conceptual signal order for a subscription:

~~~text
Publisher                    Subscriber
   |                              |
   | --- onSubscribe(sub) ------> |
   | <----- request(n) ---------- |  (n > 0)
   | --- onNext(value) ---------> |  (0..n values per demand)
   | --- onNext(value) ---------> |
   | --- onComplete() ----------> |  (success)
            or
   | --- onError(cause) --------> |  (failure)

Subscriber can call cancel() to stop receiving more data.
~~~

The two terminal signals `onComplete` and `onError` are mutually exclusive within **a single subscription**. After a terminal signal, the publisher must not send further `onNext` signals to that subscriber.

Not every `Mono` emits `onNext`: `Mono.empty()` only completes. Not every `Flux` finishes finitely: a real-time stream may emit continuously until cancelled. A `cancel` signal flows upstream from the subscriber to request stopping the stream—it is **not a successful `onComplete`**.

## 3. Assembly and Subscription Are Two Different Moments

Consider:

~~~java
Mono<Integer> pipeline = Mono.fromSupplier(() -> {
    System.out.println("loading");
    return 7;
}).map(value -> value * 2);

System.out.println("assembled");
~~~

At this point, Java has constructed a `Publisher` object and attached the `map` operator. The `fromSupplier` callback **has not run** without a subscription. Therefore, the only line printed so far is:

~~~text
assembled
~~~

Next:

~~~java
pipeline.subscribe(value -> System.out.println("result=" + value));
~~~

With `Mono.fromSupplier` and synchronous operators as in this example, the additional output will be:

~~~text
loading
result=14
~~~

The overall order is `assembled`, then `loading`, then `result=14`.

In general, **subscribing does not guarantee all callbacks finish before `subscribe()` returns**. If the flow involves timers, network I/O, schedulers, or asynchronous sources, `subscribe()` can return immediately while data arrives later.

Nor should you state absolutely that "everything only runs after subscribe": Java calls used to **build** the publisher still execute at assembly time, and hot sources can emit values independently of subscribers. The exact boundary depends on how the publisher is created.

## 4. Runnable Example: Subscribing Twice Re-runs a Cold Source

To observe this directly, create a Spring Boot project using `spring-boot-starter-webflux`. The WebFlux dependency already brings Reactor Core onto the classpath:

~~~groovy
dependencies {
    implementation 'org.springframework.boot:spring-boot-starter-webflux'
}
~~~

In `src/main/java/com/example/demo/SubscriptionDemo.java`, put:

~~~java
package com.example.demo;

import reactor.core.publisher.Flux;
import reactor.core.publisher.Mono;

public class SubscriptionDemo {

    public static void main(String[] args) {
        Mono<Integer> pipeline = Mono.fromSupplier(() -> {
            System.out.println("source invoked");
            return 2;
        }).map(number -> number * 10);

        System.out.println("assembled");

        pipeline.subscribe(value ->
            System.out.println("first: " + value));

        pipeline.subscribe(value ->
            System.out.println("second: " + value));

        Flux<Integer> items = Flux.range(1, 3)
            .doOnSubscribe(subscription ->
                System.out.println("flux subscribed"));

        items.subscribe(
            value -> System.out.println("item: " + value),
            error -> System.out.println("error: " + error.getMessage()),
            () -> System.out.println("flux complete")
        );
    }
}
~~~

This class has a standalone `main` method logically, **but requires the Reactor dependency**. Run it in your IDE with the project's runtime classpath, or via a project-configured `JavaExec` task; running `javac SubscriptionDemo.java` alone will lack the Reactor library.

With the synchronous source and operators above, stdout is deterministically:

~~~text
assembled
source invoked
first: 20
source invoked
second: 20
flux subscribed
item: 1
item: 2
item: 3
flux complete
~~~

Why is `source invoked` printed twice? `Mono.fromSupplier` is a cold source: each subscription triggers the supplier once. Two subscribers do not implicitly share results. `Flux.range` likewise supplies a fresh sequence of items for its subscription.

This example deliberately avoids schedulers or delays, so stdout ordering is deterministic. With multithreaded code or real I/O, relying on log line order alone to infer subscription timing is insufficient; observe signals and threads.

## 5. Mono.just, fromSupplier, fromCallable, and defer

The word "lazy" must be understood per **specific expression**. Compare:

~~~java
String value = loadValue();                  // runs IMMEDIATELY
Mono<String> a = Mono.just(value);           // holds already-computed value
Mono<String> b = Mono.just(loadValue());     // loadValue runs IMMEDIATELY
Mono<String> c = Mono.fromSupplier(
    () -> loadValue());                       // loadValue runs on subscribe
Mono<String> d = Mono.fromCallable(
    () -> readFile());                        // reads file on subscribe
Mono<String> e = Mono.defer(
    () -> Mono.just(loadValue()));            // creates new Mono on subscribe
~~~

These lines illustrate Java expression evaluation timing, not a standalone program; `loadValue` and `readFile` are application-defined functions.

| Factory | Key behavior |
|---|---|
| `Mono.just(value)` | Captures a value already computed at assembly; each subscription receives that value |
| `Mono.justOrEmpty(value)` | Creates a `Mono` from a nullable value or `Optional`; `null` yields empty |
| `Mono.fromSupplier(supplier)` | Invokes `Supplier` at subscription time, allowing a fresh value per subscription |
| `Mono.fromCallable(callable)` | Similar to `Supplier` but suited for tasks throwing checked exceptions; exceptions become error signals |
| `Mono.defer(factory)` | Invokes the factory at subscription time; each subscription can produce a different publisher |
| `Mono.error(exception)` | Emits an error as a reactive signal to the subscriber |
| `Mono.empty()` | Completes without emitting a value |

**Important nuance:** `Mono.just` itself emits its value upon subscription, but because the value was captured earlier, the computation producing it already happened at assembly. Reactor documentation describes this as hot-like with respect to value capture; do not assume work passed to `Mono.just` repeats per subscriber.

If `loadValue()` calls a database or HTTP service, putting it inside `Mono.just(loadValue())` executes that call before the pipeline is subscribed. Use `Mono.defer`, `Mono.fromCallable`, or genuine reactive APIs to control when work occurs.

`fromCallable` does not turn blocking I/O into non-blocking I/O. For unavoidable blocking work, consider `Schedulers.boundedElastic()` (see the threading section).

## 6. Operators map, filter, and flatMap Do Not Trigger Subscription

When chaining operators:

~~~java
Mono<String> result = Mono.just("  spring  ")
    .map(String::trim)
    .filter(text -> !text.isBlank())
    .map(String::toUpperCase);
~~~

We are describing a processing chain. Callbacks in `map` and `filter` are invoked when signals arrive from upstream during a subscription, rather than running merely by chaining operators.

In the example above, after subscribing:

~~~java
result.subscribe(System.out::println);
~~~

Stdout:

~~~text
SPRING
~~~

`flatMap` differs from `map` in that its callback returns a `Publisher`, and Reactor subscribes to and merges the inner publisher according to operator semantics:

~~~java
Mono<User> user = userRepository.findById(id); // assuming reactive repository
Mono<Order> order = user.flatMap(foundUser ->
    orderRepository.findLatestByUserId(foundUser.id())
);
~~~

This is illustrative code; the repositories are application interfaces. `flatMap` is useful when the next step is also asynchronous. Writing `map(foundUser -> orderRepository.find...)` would produce `Mono<Mono<Order>>`, leaving the caller without the desired `Mono<Order>`.

For multiple values:
- `flatMap` can run inner publishers concurrently; completion order need not match source order.
- `concatMap` preserves order by processing sequentially per operator semantics.
- `flatMapSequential` combines concurrent inner execution with ordered emission.
- `then` ignores prior data items and awaits completion; `thenReturn` supplies a value after completion.

Do not place important side-effecting logic inside a callback and assume it "has already happened" when a method returns a `Publisher`. Without a subscription, the callback may never run.

## 7. When Is a Publisher Actually Subscribed?

Actions that typically create a subscription:

1. Calling `mono.subscribe(...)` or `flux.subscribe(...)` at the end of a pipeline in a console app or system boundary service.
2. Calling terminal blocking operations like `block()`, `blockFirst()`, `blockLast()` (which also subscribe, while blocking the calling thread).
3. A framework like Spring WebFlux receiving a `Publisher` to handle an HTTP request/response and managing the subscription.
4. Testing tools such as `StepVerifier` subscribing when `verify()` is invoked.
5. Adapters/bridges converting a `Publisher` into another concurrency primitive also create a subscription.

Conversely, `map`, `filter`, `doOnNext`, `flatMap`, or assigning a `Mono<T>` variable are not subscription actions on their own.

Distinguish **"is subscribed"** from **"already has a value"**. A subscriber may be subscribed without sufficient demand yet, the source may be waiting on a timer or network I/O, the publisher may emit zero items, or it may have been cancelled. Subscription is a prerequisite for cold flows, not a guarantee of immediate completion.

## 8. Signals: doOnSubscribe, doOnNext, doOnSuccess, doOnComplete

Reactor provides operators to observe lifecycle events without terminating the pipeline:

~~~java
Mono<String> observed = Mono.fromSupplier(() -> "ok")
    .doOnSubscribe(subscription ->
        System.out.println("subscribed"))
    .doOnNext(value ->
        System.out.println("next: " + value))
    .doOnSuccess(value ->
        System.out.println("success: " + value))
    .doOnError(error ->
        System.out.println("error: " + error.getMessage()))
    .doFinally(signalType ->
        System.out.println("finally: " + signalType));

observed.subscribe();
~~~

Notes:
- `doOnSubscribe` observes when a `Subscription` has been established.
- `doOnNext` only runs when an `onNext` value is emitted.
- `Mono.doOnSuccess` runs when the `Mono` completes successfully, **including an empty Mono** (the callback receives `null` for empty).
- `Flux.doOnComplete` observes successful `Flux` completion; it does not run when the stream terminates with an error.
- `doOnError` observes an error, **without recovering from it**.
- `doFinally` receives the final termination signal type: complete, error, or cancel—useful for recording metrics and releasing scoped resources.
- `doFirst` is a hook running very early upon subscription; it can observe before `doOnSubscribe`.

`doOn...` operators are meant for logging, metrics, and controlled side effects. Do not turn them into places for business steps that must be awaited; put that work in `flatMap`, `then`, or an appropriate operator so it becomes part of the pipeline.

## 9. One Publisher and Multiple Subscribers: cold, hot, cache, share

**Cold publishers** create a fresh data emission process per subscription. `Mono.fromSupplier`, `Flux.range`, and many reactive HTTP/DB calls are common examples. With a cold publisher, subscribing twice can trigger **two real I/O calls**.

~~~java
Mono<String> cold = Mono.fromSupplier(() -> {
    System.out.println("loading");
    return "value";
});

cold.subscribe();
cold.subscribe();
~~~

Stdout:

~~~text
loading
loading
~~~

**Hot publishers** can emit data independently of any specific subscriber. Latecomers may miss earlier items if the source does not replay. Examples include sources built with `Sinks.Many` or shared via `share()`; replay behavior depends on configuration.

Sharing operators have distinct semantics:

| Approach | Behavior to note |
|---|---|
| Holding a `Mono.just(value)` | Shares the value captured at assembly; does not re-run the creation computation |
| `Mono.cache()` | Caches the signal from a single upstream subscription once it occurs; later subscribers receive cached signals per operator semantics |
| `Flux.share()` | Shares a running source across concurrent subscribers via publish/refCount; late subscribers can miss items |
| `Flux.replay(...)` / `cache(...)` | Buffers and replays data according to configuration; watch memory and cache lifetime |
| `Sinks.Many` | Lets application code emit signals programmatically; multicast/unicast/replay choice dictates fan-out |

`Mono.cache()` example:

~~~java
Mono<String> once = Mono.fromSupplier(() -> {
    System.out.println("fetch");
    return "data";
}).cache();

once.subscribe(System.out::println);
once.subscribe(System.out::println);
~~~

With this synchronous source and two sequential subscriptions, stdout is:

~~~text
fetch
data
data
~~~

Simply subscribing twice does not guarantee the same result if the source publisher has side effects; when sharing data is required, choose explicit `cache`/`share` semantics.

**Warning:** Do not use unbounded caching for data that must stay fresh or for unbounded `Flux`es without understanding memory and lifecycle implications. For APIs that need fresh data per request, a per-request cold publisher is usually clearer.

## 10. Backpressure: `request(n)` Controls Data Volume

Reactive Streams lets downstream request how many elements it is ready to receive via `Subscription.request(n)`. That is **demand**.

Example using `BaseSubscriber` to request one element at a time:

~~~java
import org.reactivestreams.Subscription;
import reactor.core.publisher.BaseSubscriber;
import reactor.core.publisher.Flux;

Flux.range(1, 3).subscribe(new BaseSubscriber<Integer>() {
    @Override
    protected void hookOnSubscribe(Subscription subscription) {
        System.out.println("subscribed");
        request(1);
    }

    @Override
    protected void hookOnNext(Integer value) {
        System.out.println("next: " + value);
        request(1);
    }

    @Override
    protected void hookOnComplete() {
        System.out.println("complete");
    }
});
~~~

With the synchronous `Flux.range` source, stdout is:

~~~text
subscribed
next: 1
next: 2
next: 3
complete
~~~

If you never call `request(n)` with `n > 0` in this subscriber, the source may wait indefinitely because downstream has not requested data. Remember:
- `request(1)` asks for one item; multiple calls accumulate demand.
- `Long.MAX_VALUE` represents unbounded demand per Reactor convention.
- Common `subscribe(value -> ...)` overloads automatically request unbounded demand; they **do not prove** the pipeline is throttling item by item.
- Some operators alter upstream demand via prefetching, buffering, or concurrency. Do not assume each `request(1)` on a subscriber always translates to one `request(1)` at the original source.

Backpressure coordinates production and consumption at the Reactive Streams layer. It does not replace memory limits, request size limits, or protection policies for hot sources that emit faster than consumers.

## 11. subscribeOn and publishOn: Subscription Does Not Imply a New Thread

In Reactor, `subscribe()` by itself does not mean "run on another thread." With `Mono.just`, `Flux.range`, and synchronous operators, callbacks can run directly on the thread calling `subscribe()`.

To change execution contexts, Reactor offers two primary operators:

| Operator | Primary effect |
|---|---|
| `subscribeOn(scheduler)` | Specifies the scheduler for upstream subscribe/request and source signals within the applicable scope |
| `publishOn(scheduler)` | Switches where signals are processed for **downstream operators** following it |

Example when forced to call a legacy blocking API:

~~~java
Mono<String> legacyCall = Mono.fromCallable(() ->
        legacyClient.loadValue())
    .subscribeOn(Schedulers.boundedElastic());
~~~

This is an illustrative snippet; `legacyClient` is an application dependency. `fromCallable` defers the call until subscription; `boundedElastic` provides an appropriate scheduler to isolate unavoidable blocking tasks. **Neither turns a blocking operation into true non-blocking I/O.**

When using reactive repositories/clients, prefer keeping the chain non-blocking:

~~~java
Mono<Order> order = reactiveRepository.findById(id)
    .flatMap(found -> reactiveService.enrich(found));
~~~

Do not add `subscribeOn(boundedElastic())` to every endpoint out of habit; scheduler switching carries overhead and can mask blocking I/O that ought to be fixed.

With WebFlux + Reactor Netty, the event loop serves I/O. Calling `Thread.sleep`, `Future.get`, or `Mono.block()` on the event loop can stall requests for many clients. On certain non-blocking threads managed by Reactor, `block()` may even be rejected with an exception.

## 12. Where Does Spring WebFlux Subscribe?

In WebFlux, controllers typically **return a Publisher** to the framework:

~~~java
@GetMapping("/api/orders/{id}")
public Mono<OrderDto> find(@PathVariable long id) {
    return orderService.findById(id);
}
~~~

Assume `orderService.findById` returns `Mono<OrderDto>` from reactive data access. The controller does not need to call `subscribe()`; Spring WebFlux handles the return value, wires it into the HTTP pipeline, and subscribes to the `Publisher` when writing the response.

Conceptual flow:

~~~text
HTTP request arrives
   |
WebFlux dispatcher finds handler
   |
Controller method is invoked
   |
Returns Mono<OrderDto> or Flux<OrderDto>
   |
WebFlux processes return value and prepares response writer
   |
Framework subscribes / demands / consumes signals
   |
Source performs work upon subscription (if cold)
   |
HttpMessageWriter encodes body and writes to transport
   |
Complete / error / client disconnect
~~~

**An easy-to-miss timing detail:** Java code **outside** the `Publisher` inside the controller method body runs immediately when the framework invokes that method. Only work placed inside a cold source or operator waits for subscription.

Example:

~~~java
@GetMapping("/api/demo")
public Mono<String> demo() {
    System.out.println("handler method invoked"); // runs when handler is called
    return Mono.fromSupplier(() -> {
        System.out.println("publisher evaluated"); // runs on subscribe
        return "OK";
    });
}
~~~

`handler method invoked` and `publisher evaluated` log at two distinct logical moments. Do not rely on log ordering across concurrent requests to deduce exact threads or subscription counts.

### 12.1. Why Not Call `subscribe()` in a Controller?

**Avoid:**

~~~java
@PostMapping("/api/orders")
public Mono<Void> create(@RequestBody Mono<CreateOrder> request) {
    request.flatMap(orderService::save).subscribe();
    return Mono.empty();
}
~~~

In this illustration, `subscribe()` launches detached background work decoupled from the HTTP response. WebFlux can return success while the save operation is still unfinished or has already failed. Exceptions, cancellation, and request lifecycle are no longer coordinated by the framework in the same pipeline. It is also easy to trigger duplicate subscriptions when both returning and subscribing to a publisher.

**Prefer:**

~~~java
@PostMapping("/api/orders")
public Mono<Void> create(@RequestBody Mono<CreateOrder> request) {
    return request.flatMap(orderService::save).then();
}
~~~

Now the response depends on completion or error of the save operation. `then()` discards values and retains only completion/error signals; `Mono<Void>` means success emits no body. This illustrates a method where `orderService.save` returns a `Publisher`; it is not a standalone runnable class.

**Never call `subscribe()` inside a controller just to "kick off" a `Mono`/`Flux`.** The framework itself is the proper subscriber at the HTTP boundary. Self-managed background jobs may need their own subscribers, but must have explicit lifecycle, error handling, cancellation, and ownership.

## 13. Complete Spring Boot WebFlux Example

In a Java 17+ project with `spring-boot-starter-webflux`, create `src/main/java/com/example/demo/ReactiveWebApplication.java`:

~~~java
package com.example.demo;

import java.time.Duration;

import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;
import org.springframework.http.MediaType;
import org.springframework.http.codec.ServerSentEvent;
import org.springframework.web.bind.annotation.*;
import reactor.core.publisher.Flux;
import reactor.core.publisher.Mono;

@SpringBootApplication
public class ReactiveWebApplication {

    public static void main(String[] args) {
        SpringApplication.run(ReactiveWebApplication.class, args);
    }
}

record Greeting(String message) {}

@RestController
class ReactiveController {

    @GetMapping("/api/hello/{name}")
    public Mono<Greeting> hello(@PathVariable String name) {
        System.out.println("handler invoked: " + name);
        return Mono.fromSupplier(() -> {
            System.out.println("source subscribed: " + name);
            return new Greeting("Hello, " + name);
        });
    }

    @GetMapping(value = "/api/numbers",
                produces = MediaType.APPLICATION_JSON_VALUE)
    public Flux<Integer> numbers() {
        return Flux.range(1, 3);
    }

    @GetMapping(value = "/api/events",
                produces = MediaType.TEXT_EVENT_STREAM_VALUE)
    public Flux<ServerSentEvent<Long>> events() {
        return Flux.interval(Duration.ofSeconds(1))
            .take(3)
            .map(index -> ServerSentEvent.<Long>builder()
                .data(index)
                .build());
    }
}
~~~

Start using the Gradle wrapper in a configured Spring Boot project:

~~~bash
./gradlew bootRun
~~~

On Windows:

~~~powershell
.\gradlew.bat bootRun
~~~

Test `Mono`:

~~~bash
curl -i http://localhost:8080/api/hello/Ada
~~~

Typical JSON body:

~~~json
{"message":"Hello, Ada"}
~~~

In server logs, the handler is called to create the `Mono`; the supplier runs when the pipeline is subscribed. Because this is a live request, WebFlux handles subscription and builds the HTTP response.

Test finite `Flux`:

~~~bash
curl -i http://localhost:8080/api/numbers
~~~

Typical JSON body:

~~~json
[1,2,3]
~~~

**Important:** `Flux<Integer>` does not automatically mean "each element is sent over the network immediately upon creation." With `application/json`, encoding as a JSON array may involve buffering. For incremental streaming, use a suitable media type and writer such as Server-Sent Events or NDJSON.

Test SSE:

~~~bash
curl -N http://localhost:8080/api/events
~~~

Example event output (line breaks/details depend on encoder):

~~~text
data:0

data:1

data:2
~~~

`Flux.interval` begins timing upon subscription; here there are three elements 0, 1, and 2 spaced roughly one second apart. Actual response timing can vary due to scheduling, network, and client behavior.

If a client disconnects midway, WebFlux can propagate cancellation into the pipeline. Whether upstream tasks actually halt and release resources depends on the publishers and operators in use.

## 14. Flux and HTTP Streaming Are Not Identical Concepts

A `Flux<T>` merely describes the ability to emit multiple items; HTTP wire representation is decided by content negotiation and codecs.

| Return shape | Typical behavior | Things to note |
|---|---|---|
| `Mono<T>` with `application/json` | One JSON value or empty body | Empty does not automatically mean 404 |
| Finite `Flux<T>` with `application/json` | One JSON array | May be written/buffered according to codec strategy |
| `Flux<T>` with `application/x-ndjson` | Multiple lines of JSON | Suited for streaming multiple objects |
| `Flux<ServerSentEvent<T>>` with `text/event-stream` | Time-based SSE events | Client must handle streaming and long-lived connections |
| `Mono<Void>` | Completion/error only | HTTP status must be set per API contract |

Do not force every API to return `Flux` when business semantics only produce a single result. Choose `Mono` vs. `Flux` by cardinality and source nature; choose media type by transport contract.

## 15. WebClient and Reactive Repositories Also Return Publishers

Example using `WebClient`:

~~~java
Mono<Product> product = webClient.get()
    .uri("/products/{id}", id)
    .retrieve()
    .bodyToMono(Product.class);
~~~

This snippet assumes application `webClient` and `Product` types. **Building** the pipeline does not send an HTTP network request immediately. In normal reactive `WebClient` usage, network I/O is tied to subscribing to the returned publisher.

Subscribing twice to a cold pipeline can trigger **two outbound HTTP requests**. This matters when controller logic invokes a service multiple times or on retries. To share a result within a single request, choose proper composition/caching and consider data freshness.

Composition example:

~~~java
Mono<ProductView> result = productRepository.findById(id)
    .flatMap(product ->
        stockClient.getStock(product.id())
            .map(stock -> new ProductView(product, stock))
    );
~~~

This chains multiple `Publisher`s without subscribing at intermediate steps. The final subscriber (such as WebFlux) drives the entire workflow.

**Do not confuse:** A method returning a `Publisher` may still run synchronous Java code before returning the publisher. What is deferred is I/O or side effects placed **inside** subscription of a properly designed reactive source; Reactor does not delay every statement in a method body.

## 16. Error, Empty, Completion, and Cancellation

Four distinct cases to handle explicitly:

| Case | Mono/Flux signal | Handling approach |
|---|---|---|
| Data present | `onNext`, then `onComplete` if finite | `map`, `flatMap`, or response writer |
| Success but empty | `onComplete` without `onNext` | `switchIfEmpty`, `defaultIfEmpty`, or API contract |
| Error | `onError` | `onErrorResume`, `onErrorMap`, or framework error handler |
| Client cancel / subscriber cancel | `cancel()` sent upstream | `doOnCancel`, `doFinally`, resource cleanup |

Example handling a missing record:

~~~java
@GetMapping("/api/products/{id}")
public Mono<Product> find(@PathVariable long id) {
    return productRepository.findById(id)
        .switchIfEmpty(Mono.error(
            new ResponseStatusException(
                HttpStatus.NOT_FOUND, "Product not found")));
}
~~~

`Product`, `productRepository`, `ResponseStatusException`, and `HttpStatus` must be imported/defined accordingly. This example converts empty into a 404 error; **`Mono.empty()` by itself does not force WebFlux to return 404**.

To handle exceptions by type:

~~~java
Mono<Product> recovered = productRepository.findById(id)
    .onErrorResume(TemporaryBackendException.class,
        error -> fallbackRepository.findById(id));
~~~

`onErrorResume` switches to a fallback flow upon receiving an error. `doOnError` only observes the error without replacing it with a value.

With `retry(1)`, Reactor typically **resubscribes** to upstream on error, so side-effecting tasks may run again. Only retry safe/idempotent operations or use deduplication. Cancellation can also happen after external side effects have partially executed; do not assume cancel rolls back database transactions or already-sent HTTP requests.

## 17. Mistakes With block() and subscribe() in WebFlux

### 17.1. `block()` Subscribes Too, While Holding the Thread

~~~java
String value = Mono.just("ok").block();
~~~

`block()` both creates a subscription and blocks the calling thread until a signal arrives. It is useful at **synchronous application boundaries** like CLI tools or small tests, but usually unsuitable inside WebFlux handlers because it can block the event loop and hurt concurrency.

Crucially, each separate `block()` call creates a new subscription; calling `block()` twice on a cold source can repeat I/O. Do not call `block()` just to "unwrap data" and re-wrap it in `Mono.just` inside a controller.

### 17.2. `subscribe()` Ignores Lifecycle Unless Managed

~~~java
Disposable subscription = flux.subscribe(
    value -> consume(value),
    error -> report(error)
);

// When no longer needed:
subscription.dispose();
~~~

This illustrates code that **owns** its subscriber. `subscribe` can return a `Disposable` to cancel the subscription. However, `dispose()` is a reactive stop request; for sources already completed or external side effects, it does not guarantee undoing work already performed.

In WebFlux controllers, prefer **returning the Publisher**. Manually subscribing and returning an empty `Mono` decouples the HTTP response from the inner work's outcome.

### 17.3. Avoid Arbitrary "Fire-and-Forget"

For sending emails, writing to a database, publishing events, or mutating state, define the contract: must the HTTP response wait for completion or merely acknowledge job acceptance? For background jobs, use a proper queue/scheduler/lifecycle mechanism with error handling and shutdown management. Simply tacking `.subscribe()` onto a controller does not create a durable job queue.

## 18. Observing and Verifying Exact Subscription Timing

### 18.1. Logging Hooks in a Pipeline

~~~java
Flux<Integer> pipeline = Flux.range(1, 3)
    .doOnSubscribe(s -> log.info("subscribed"))
    .doOnRequest(n -> log.info("requested {}", n))
    .doOnNext(value -> log.info("next {}", value))
    .doOnComplete(() -> log.info("completed"))
    .doOnCancel(() -> log.info("cancelled"))
    .doFinally(signal -> log.info("finally {}", signal));
~~~

This illustrative snippet requires a logger variable `log`. It reveals subscription, demand, emission, and cancellation along the traced flow.

Reactor's `checkpoint("product pipeline")` or `log()` also helps when debugging stack traces and signals. Avoid logging full payloads/bodies in production if sensitive data may be present. In async flows, thread names and request correlation IDs correlate events far more accurately than plain stdout.

### 18.2. StepVerifier: No Sleeping to Guess Timing

Add the test dependency to your project:

~~~groovy
dependencies {
    testImplementation 'io.projectreactor:reactor-test'
}
~~~

Example verifying that the supplier runs only after `verifyComplete()` subscribes:

~~~java
package com.example.demo;

import java.util.concurrent.atomic.AtomicInteger;
import org.junit.jupiter.api.Test;
import reactor.core.publisher.Mono;
import reactor.test.StepVerifier;

import static org.junit.jupiter.api.Assertions.assertEquals;

class SubscriptionBehaviorTest {

    @Test
    void supplierRunsWhenSubscribed() {
        AtomicInteger calls = new AtomicInteger();

        Mono<Integer> source = Mono.fromSupplier(calls::incrementAndGet);

        assertEquals(0, calls.get()); // assembled only, not yet subscribed

        StepVerifier.create(source)
            .expectNext(1)
            .verifyComplete();

        assertEquals(1, calls.get());
    }
}
~~~

`StepVerifier.create(source)` prepares the verification scenario; calling `verifyComplete()` begins test execution and subscribes to the source. This test confirms zero supplier invocations at assembly and one invocation upon verification.

To test time-based operators, `StepVerifier.withVirtualTime(...)` simulates elapsed time without waiting on a real clock; construct the publisher inside the virtual-time verifier's `Supplier` so the virtual scheduler attaches properly.

### 18.3. Testing WebFlux With WebTestClient

With Spring Boot test and WebFlux, `WebTestClient` can send requests, assert JSON/status, and verify the framework handles the returned `Publisher`. Skeleton example:

~~~java
webTestClient.get()
    .uri("/api/hello/Ada")
    .exchange()
    .expectStatus().isOk()
    .expectBody()
    .jsonPath("$.message").isEqualTo("Hello, Ada");
~~~

`webTestClient` is a bean/instance provided by test setup; this example only shows assertions, not a complete standalone test class. In tests, check error and empty cases as well as HTTP 200.

## 19. Commonly Confused Questions

**If I created a Mono with `Mono.just("A")`, has it already run?** The expression creating the value was evaluated at assembly; `Mono` holds that value and emits it once subscribed with demand. With `Mono.just(callService())`, `callService()` already ran before subscription due to Java argument evaluation rules.

**Can I pass a Mono across multiple layers without executing it yet?** Yes, with cold publishers and normal operators, you can compose and return across services and controllers. However, plain Java statements outside the `Publisher` still run when the method is called.

**Does subscribing once guarantee a result appears immediately?** No. A subscription can wait for demand, I/O duration, timers, or be cancelled before any value arrives. Do not rely on log line order across different threads.

**Is Mono asynchronous and Flux synchronous?** No. Either can be synchronous or asynchronous; the primary difference is cardinality: 0..1 vs. 0..N.

**Does Flux always send an HTTP response item by item?** No. A publisher can emit item by item, but codecs and media types determine how the HTTP body is written. JSON arrays may buffer, whereas SSE/NDJSON fit streaming.

**Is calling `subscribe()` in a controller faster?** Not by default. It detaches work from the response and risks losing error/cancellation management; real throughput gains rely on non-blocking I/O and proper backpressure.

**Why did a WebClient call fire twice?** Likely because a cold publisher was subscribed twice, retried/resubscribed, or constructed in two places. Use `doOnSubscribe`, tests, and tracing to tell them apart.

**Is it true that "without a subscriber, no Publisher does anything"?** No. Hot sources can emit data before anyone subscribes; expressions passed to `Mono.just` or code outside the pipeline can run immediately.

## 20. Checklist When Writing Spring WebFlux Code

1. Choose `Mono` for 0..1 results, `Flux` for 0..N; define empty, error, and completion explicitly.
2. Know whether sources are cold or hot, and whether side effects happen at assembly or subscription.
3. Use `defer`/`fromCallable` when deferring value creation or wrapping legacy calls.
4. Use `flatMap`/`then` to compose async work so the pipeline awaits results.
5. Return `Publisher`s to WebFlux at the HTTP boundary; avoid manual `subscribe()` in controllers.
6. Never call `block()` on event loops or threads requiring non-blocking execution.
7. For unavoidable blocking I/O, isolate with an appropriate scheduler and plan migration to reactive clients.
8. When using `Flux`, account for demand/backpressure and buffering.
9. Be cautious with `retry`, since resubscription can repeat side effects.
10. For HTTP streaming, pick suitable codecs/media types and handle cancellation.
11. Observe `doOnSubscribe`, `doOnRequest`, `doOnNext`, `doOnError`, and `doFinally` while debugging.
12. Write `StepVerifier` tests to prove execution timing instead of guessing with `Thread.sleep`.

## 21. References

- [Project Reactor Reference Guide](https://projectreactor.io/docs/core/release/reference/): publishers, signals, backpressure, threading, and testing.
- [Project Reactor — Hot Versus Cold](https://projectreactor.io/docs/core/3.7.0/reference/advancedFeatures/reactor-hotCold.html): differences between cold/hot publishers, `just`, `defer`, sharing.
- [Project Reactor — Mono API](https://projectreactor.io/docs/core/release/api/reactor/core/publisher/Mono.html): factory methods, subscribe, block, and lifecycle signals.
- [Spring Framework — WebFlux](https://docs.spring.io/spring-framework/reference/web/webflux.html): request/response processing, Reactive Streams, and annotated controllers.
- [Spring Boot — WebFlux](https://docs.spring.io/spring-boot/3.3/reference/web/reactive.html): WebFlux applications with Boot and embedded web servers.

**Key takeaway:** `Mono` and `Flux` describe signals that can be emitted; **assembly** builds the pipeline, **subscription** activates cold sources, **`request(n)`** propagates demand, and **`onNext`/`onComplete`/`onError`** convey outcomes. In Spring WebFlux, let the framework manage subscription at the HTTP boundary and compose all work into one observable, testable, cancellable pipeline.

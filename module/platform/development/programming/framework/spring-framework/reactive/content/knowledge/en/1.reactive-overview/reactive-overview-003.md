# Data Streams, Signals, and Event-Driven Processing in Spring Reactive

In Spring WebFlux, data does not necessarily have to be returned all at once after all work finishes. An application can express work as a **reactive stream**: a source produces elements when there is demand, operators transform them, and the consumer reacts to data, errors, or completion. Project Reactor is the library commonly used to build this stream via `Flux` and `Mono`.

## 1. Learning Outcomes

After this lesson, you will be able to:

- Trace the **Publisher → operators → Subscriber** path and explain when a stream starts running.
- Distinguish **data elements** (`onNext`) from **lifecycle signals** (`onSubscribe`, `onError`, `onComplete`, `cancel`).
- Explain the `Subscription.request(n)` mechanism, backpressure, cold/hot streams, and the effect of cancelling a subscription.
- Choose `map`, `filter`, `flatMap`, `concatMap`, and error-handling operators for a simple pipeline.
- Read a runnable Reactor example and relate it to event-driven HTTP handling in Spring WebFlux.

## 2. Thinking in Data Streams

In ordinary imperative programming, it is easy to picture `result = service.load()` waiting for a result before executing the next line. In the reactive model, a method can return a **description of work that will take place** as a `Publisher`. Building a pipeline (assembly) and executing a pipeline (subscription) are two distinct phases.

```text
Data source (Publisher)
    │ emits data or signals upon subscription and demand
    ▼
filter → map → flatMap → doOnNext    (operator chain)
    │
    ▼
Subscriber / HTTP response writer   (consumer)
    ▲
    └──── Subscription.request(n), cancel()  (upstream control)
```

The **data flow** typically travels from the source down to the subscriber. **Element demand** and **stream cancellation** travel from the subscriber upstream toward the source. Errors and completion are also propagated toward the subscriber. Each operator can act simultaneously as a subscriber to the preceding stage and a publisher to the following stage.

Two fundamental Reactor types:

| Type | Number of `onNext` items | When to use |
| --- | --- | --- |
| `Mono<T>` | 0 or 1 | A single result, no result, or only a completion signal (`Mono<Void>`) |
| `Flux<T>` | 0 to many | Lists, multiple records, events spanning over time |

`Mono`/`Flux` does not guarantee data always arrives asynchronously: `Flux.just(1, 2)` can run synchronously on the current thread; `Flux.interval(...)` emits on a schedule and uses a scheduler. **Reactive does not mean “one thread per element.”** Likewise, `Flux` is not equivalent to `java.util.stream.Stream`: Reactor has a protocol of signals, element demand, and cancellation, and can integrate non-blocking I/O.

## 3. Signals in Reactive Streams

The underlying protocol defines four interfaces: `Publisher<T>` (source), `Subscriber<T>` (receiver), `Subscription` (request/cancel control), and `Processor<T,R>` (a component that both receives and emits). Most Spring application code works at the `Mono`/`Flux` level rather than implementing these interfaces directly.

A subscription has a general lifecycle:

1. `subscriber` registers with `publisher` via `subscribe(...)`.
2. The Publisher sends **`onSubscribe(subscription)`** to provide control.
3. The Subscriber calls **`request(n)`** with `n > 0`; the source is permitted to emit at most the unfulfilled requested count (for sources honoring backpressure).
4. Each data element is sent via **`onNext(value)`**. A `null` value is invalid for Reactive Streams `onNext` signals.
5. The stream terminates with exactly one of two terminal signals: **`onComplete()`** (success) or **`onError(cause)`** (failure). After a terminal signal, no further `onNext` is valid.
6. The Subscriber can call **`cancel()`** to stop being interested in the stream; cancelling does not mean the subscriber receives `onComplete`.

```text
With data:   onSubscribe → request(3) → onNext(A) → onNext(B) → onComplete
Empty:       onSubscribe → onComplete
Errored:     onSubscribe → request(2) → onNext(A) → onError(E)
Cancelled:   onSubscribe → request(10) → onNext(A) → cancel
```

The arrows describe logical ordering, not that everything must happen on the same thread or at the same instant. `request(n)` can occur multiple times, and elements arrive in batches. `onSubscribe`, `onNext`, `onComplete`, and `onError` are **protocol signals**; a business record named “OrderCreated” is **application data** carried inside `onNext`. Distinguishing these helps avoid confusing a “business event” with a “stream lifecycle signal.”

### Three Cases to Remember

- `Mono.empty()` emits no `onNext`, yet completes normally. `Mono.error(e)` terminates with an error.
- In `Flux.just(1, 2, 3).map(...)`, declaring `map` does not yet consume elements. With typical cold sources, a subscription is required for work to run.
- If the source emits `onError` on the second element, subsequent elements in that same source branch will not be processed; `onErrorResume` can **switch to a fallback publisher**, not resurrect the remainder of the old source.

## 4. Runnable Example: Data Flowing Through Operators

Create a Java 17+ Maven project with the structure:

```text
reactive-flow/
├── pom.xml
└── src/main/java/ReactiveFlowDemo.java
```

Contents of `pom.xml` (using standalone Reactor to observe the mechanics; in Spring Boot, prefer versions managed by the Boot BOM):

```xml
<project xmlns="http://maven.apache.org/POM/4.0.0"
         xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
         xsi:schemaLocation="http://maven.apache.org/POM/4.0.0 https://maven.apache.org/xsd/maven-4.0.0.xsd">
  <modelVersion>4.0.0</modelVersion>
  <groupId>example</groupId>
  <artifactId>reactive-flow</artifactId>
  <version>1.0-SNAPSHOT</version>
  <properties>
    <maven.compiler.release>17</maven.compiler.release>
    <project.build.sourceEncoding>UTF-8</project.build.sourceEncoding>
  </properties>
  <dependencies>
    <dependency>
      <groupId>io.projectreactor</groupId>
      <artifactId>reactor-core</artifactId>
      <version>3.6.9</version>
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
      </plugin>
    </plugins>
  </build>
</project>
```

Contents of `src/main/java/ReactiveFlowDemo.java`:

```java
import reactor.core.publisher.Flux;

public class ReactiveFlowDemo {
    public static void main(String[] args) {
        Flux.range(1, 4)
            .doOnSubscribe(s -> System.out.println("subscribed"))
            .doOnNext(n -> System.out.println("source: " + n))
            .filter(n -> n % 2 == 0)
            .map(n -> "event-" + n)
            .doOnNext(s -> System.out.println("handled: " + s))
            .doOnComplete(() -> System.out.println("completed"))
            .blockLast();
    }
}
```

Run in the directory containing `pom.xml`:

```bash
mvn -q compile exec:java -Dexec.mainClass=ReactiveFlowDemo
```

Program stdout:

```text
subscribed
source: 1
source: 2
handled: event-2
source: 3
source: 4
handled: event-4
completed
```

Explanation in actual execution order:

- `Flux.range(1, 4)` is a source emitting 1, 2, 3, 4. Without a subscription, nothing is printed.
- `blockLast()` creates a subscription and waits for the stream to finish, which is suitable for this **console demo**. Inside a WebFlux handler/event loop, do not use `block()`/`blockLast()` to wait on I/O.
- `doOnSubscribe` observes the subscription step; the first `doOnNext` observes every value arriving from the source.
- `filter` drops 1 and 3; `map` transforms 2 and 4 into `event-2`, `event-4`.
- `doOnComplete` observes the completion signal after all four source elements have passed through the pipeline. `doOnNext` is only suitable for logging, metrics, and observation; data transformation logic should be written with `map`/`flatMap`.

This is a synchronous source, so the stdout order is deterministic. When a source or operator offloads work across schedulers, do not infer ordering across **multiple independent threads** solely from this example.

## 5. Backpressure: The Consumer Actively Requests Data

Suppose a source produces 100,000 events/second while the consumer can only process 1,000 events/second. If the source keeps pushing unboundedly, queues grow, memory increases, and latency becomes hard to control. **Backpressure** allows downstream to signal demand via `Subscription.request(n)` and upstream to throttle emission when possible.

The following example uses `BaseSubscriber` to make two explicit requests visible, rather than the `subscribe(value -> ...)` style that usually requests an unbounded amount:

```java
import org.reactivestreams.Subscription;
import reactor.core.publisher.BaseSubscriber;
import reactor.core.publisher.Flux;

public class DemandDemo {
    public static void main(String[] args) {
        Flux.range(1, 4).subscribe(new BaseSubscriber<Integer>() {
            @Override
            protected void hookOnSubscribe(Subscription subscription) {
                System.out.println("request 2");
                request(2);
            }

            @Override
            protected void hookOnNext(Integer value) {
                System.out.println("next " + value);
                if (value == 2) {
                    System.out.println("request 2");
                    request(2);
                }
            }

            @Override
            protected void hookOnComplete() {
                System.out.println("complete");
            }
        });
    }
}
```

Save as `src/main/java/DemandDemo.java` in the same project and run:

```bash
mvn -q compile exec:java -Dexec.mainClass=DemandDemo
```

Stdout:

```text
request 2
next 1
next 2
request 2
next 3
next 4
complete
```

The initial `request(2)` permits two elements. After receiving 2, the subscriber asks for two more elements, so 3 and 4 are emitted. Without requesting more, the stream still has data but can wait indefinitely for demand. Calling `request(Long.MAX_VALUE)` means unbounded demand; many lambda-based subscriptions and `block*` methods use this form. Operators such as `buffer`, `flatMap`, or `limitRate` can **transform the requested amount** when propagating upstream, so you should not assume every stage requests the exact same item count.

Reactive Streams defines the demand-propagation mechanism; it does not promise that every real-world source can slow itself down. Hot sources, external callbacks, or unstoppable event-pushing systems may need a **buffer, drop, or error** policy. Unbounded buffering risks running out of memory; measure source/sink rates and configure explicit capacity policies.

## 6. Cold Streams, Hot Streams, and Subscription

A **cold publisher** typically re-creates the event sequence for *each* subscriber. For example, `Flux.defer(() -> Flux.just(loadValue()))` calls `loadValue()` per subscription; with `WebClient`, each subscription to a typical cold HTTP publisher can trigger a new request. Pay close attention to side effects: two subscribers can cause two data-loading operations.

A **hot publisher** can emit independently of when a subscriber starts listening; late subscribers may miss previously emitted events. For instance, a stream shared with `share()` or a source backed by `Sinks.Many` has hot characteristics depending on configuration. Redistribution, replay, and caching are separate choices; do not assume a hot source always retains full history for new subscribers.

Visualization:

```text
Cold: Sub A → [1, 2, 3]    Sub B subscribes later → [1, 2, 3]
Hot:        ...1...2...3...4...
             Sub A ↑         Sub B ↑ (may receive only subsequent items)
```

**Cancellation** matters for both kinds of sources. When a client closes an SSE connection or a subscriber calls `Disposable.dispose()`, the stream can be cancelled, helping stop scheduled emissions, processing, or release resources along the cancellation path. If an external operation has already occurred, cancelling does not automatically roll it back. `doFinally(signalType -> ...)` can observe `ON_COMPLETE`, `ON_ERROR`, or `CANCEL` for cleanup/metrics.

## 7. Choosing Operators by Event-Processing Intent

| Operator | Role | Notes |
| --- | --- | --- |
| `map` | Synchronously transforms one element into one element | The transformation function must not return `null` |
| `filter` | Lets only elements matching a condition pass through | Filtered-out elements are not errors |
| `flatMap` | Turns each element into another publisher, then merges results | Can interleave and change completion order |
| `concatMap` | Processes inner publishers sequentially | Useful when input order must be preserved |
| `zip` | Pairs elements from multiple sources | May complete early if one branch runs out of data |
| `buffer(n)` | Collects elements into lists of up to `n` elements | Increases the amount of data held in memory |
| `doOnNext`, `doOnError` | Observes signals for logging/metrics | Not operators for replacing data or recovering from errors |
| `onErrorResume` | Switches to a fallback publisher on error | The original source branch has already terminated |
| `timeout` | Signals an error when no signal arrives within a time condition | Choose timeout values based on actual SLAs |

Transaction example: `Flux<OrderEvent>` receives order events → `filter` selects valid events → `map` normalizes them → `flatMap` calls a non-blocking I/O service → returns results to the consumer. If events for the same order must be processed in strict sequence, consider `concatMap` or key-based partitioning; do not use `flatMap` and assume stable ordering. A pipeline does not become non-blocking if the function inside `map` or `flatMap` directly calls a blocking I/O API.

## 8. Errors Are Terminal Signals, Not Normal Elements

The third example uses the same Maven project:

```java
import reactor.core.publisher.Flux;

public class ErrorSignalDemo {
    public static void main(String[] args) {
        Flux.just(2, 0, 5)
            .map(n -> 10 / n)
            .subscribe(
                n -> System.out.println("next " + n),
                e -> System.out.println("error " + e.getClass().getSimpleName()),
                () -> System.out.println("complete")
            );
    }
}
```

Run `mvn -q compile exec:java -Dexec.mainClass=ErrorSignalDemo`. Stdout:

```text
next 5
error ArithmeticException
```

The 0 triggers division by zero, so `onError` terminates the stream. The value 5 at the **end of the source** is not processed, and `onComplete` is not called. If you add `onErrorResume(e -> Flux.just(-1))` right after `map`, the subscriber receives 5 and then -1, and then completes; that comes from the fallback publisher, not from resuming processing of the old element 5.

Error-handling practices:

- Use `doOnError` to record errors; use `onErrorResume` or `onErrorReturn` when you genuinely want a replacement value.
- Configure `retry`/`retryWhen` conditionally, bound the number of attempts, and apply it only when repeating the operation is safe. Retry can **re-subscribe to the source** and re-execute side effects.
- Avoid swallowing every error into a default value because it hides business and infrastructure failures.
- Use proper HTTP error handling at the WebFlux boundary; do not treat `onError` as a business JSON item sent onward within the same stream.

## 9. Event-Driven Processing in Spring WebFlux

An HTTP request arriving at a non-blocking server typically progresses through stages: socket ready to read → server receives request → framework selects handler → handler **returns** `Mono`/`Flux` → framework subscribes and writes data when possible → success, error, or client disconnect. The I/O thread does not need to be held just waiting for a network query or the next event, provided the entire involved I/O path follows non-blocking design.

Example **inside a Spring WebFlux application** (this is a controller, not a standalone Java program with `main`):

```java
import java.time.Duration;
import org.springframework.http.MediaType;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.RequestMapping;
import org.springframework.web.bind.annotation.RestController;
import reactor.core.publisher.Flux;

@RestController
@RequestMapping("/events")
public class EventController {
    @GetMapping(value = "/ticks", produces = MediaType.TEXT_EVENT_STREAM_VALUE)
    public Flux<String> ticks() {
        return Flux.interval(Duration.ofSeconds(1))
                   .map(i -> "tick-" + i)
                   .take(3);
    }
}
```

With the WebFlux starter and the application running, `curl -N http://localhost:8080/events/ticks` receives SSE messages containing `tick-0`, `tick-1`, `tick-2` over time, and then the connection closes. `Flux.interval` creates a scheduled emitter; `take(3)` limits to three elements; `text/event-stream` enables HTTP to deliver events one by one. If the client disconnects, the corresponding subscription can be cancelled. **Do not call `subscribe()` manually in a controller just to “trigger” the Flux**: return the publisher so WebFlux manages subscription, backpressure, errors, and connection lifecycle.

Returning a `Flux` over HTTP does not automatically produce element-by-element streaming for every media type. For example, a standard JSON response may be aggregated/encoded differently from SSE. To send individual events to the client, choose the appropriate protocol and media type such as SSE or WebSocket according to the communication need.

### WebClient Integration Example

In a component that already has `WebClient` and suitable data types, the chain below only describes the pipeline and does not yet trigger an HTTP request:

```java
Flux<EventDto> events =
    webClient.get()
             .uri("/events")
             .retrieve()
             .bodyToFlux(EventDto.class)
             .filter(EventDto::isValid);
```

This code snippet illustrates the API and requires `webClient` and `EventDto` to be declared in a real application. When a downstream component subscribes, WebClient performs the HTTP exchange; `filter` processes the received elements. Actual data and termination behavior also depend on the server and response type. You must manage timeouts, status codes, decoding errors, and subscription lifecycle.

## 10. Event Loops, Schedulers, and the Limits of Non-Blocking

Spring WebFlux (especially when running on Reactor Netty) uses a limited number of I/O threads following the event-loop model. One thread handles many connections by reacting when I/O events occur, rather than blocking per request. Therefore, a `Thread.sleep(...)`, synchronous JDBC/JPA, `Future.get()`, or `block()` on an event loop can slow down other requests sharing that thread.

- `subscribeOn(scheduler)` affects the **subscription context and upstream emission process**.
- `publishOn(scheduler)` switches the execution context for **downstream operators** from the point of invocation onward.
- A scheduler does not turn a blocking I/O library into non-blocking. When forced to integrate a synchronous call, isolate it in a controlled manner with `Mono.fromCallable(...).subscribeOn(Schedulers.boundedElastic())`, configure timeouts/limits, and monitor load; in the long term, prefer APIs with non-blocking support.

The following example is an **illustrative snippet** depending on a legacy API provided by the application:

```java
Mono<Result> result =
    Mono.fromCallable(() -> legacyRepository.load(id))
        .subscribeOn(Schedulers.boundedElastic());
```

`Result`, `legacyRepository`, and `id` must be defined in the application. Do not place `legacyRepository.load(id)` directly inside a `map` running on the event loop. Do not add schedulers arbitrarily to every operator: thread switching has overhead and can make reasoning about ordering and concurrency harder.

## 11. Common Conceptual and Implementation Mistakes

1. **Creating a pipeline and discarding the return value.** `source.map(fn);` creates a new publisher; if you still use `source`, the `fn` transformation is not in the pipeline that downstream receives. Connect/return the new publisher.
2. **Calling `subscribe()` inside a service and returning `Mono.empty()`.** The work becomes “fire and forget,” detached from the caller's error/cancellation flow. Prefer `return repository.save(...).then(...)` or compose with `flatMap`.
3. **Assuming `doOnNext` always runs exactly once.** It runs per subscription and can repeat on retry/resubscribe. Non-idempotent side effects require dedicated design.
4. **Confusing `onComplete` with `cancel`.** A client leaving mid-stream is cancellation; do not record “processing completed” merely because callbacks stopped.
5. **Assuming `flatMap` always preserves order.** Inner publishers have different completion times. Use `concatMap` when sequentiality is required; weigh the throughput trade-off.
6. **Using unbounded buffers to cure every backpressure issue.** Buffers merely defer overload into memory; you need rate control, limits, overflow policies, and metrics.
7. **Putting blocking I/O onto the event loop.** Inspect the entire call chain, not just method signatures returning `Mono`/`Flux`.
8. **Omitting error branches.** `onError` is a real outcome; logging, HTTP error mapping, retries, and recovery strategies must be explicit.
9. **Confusing a reactive stream with a message broker.** Reactive Streams is an in-process protocol between publisher and subscriber; Kafka/RabbitMQ have their own storage, acknowledgement, delivery, and retry semantics. The two models can be integrated, but do not equate backpressure with broker acknowledgement.
10. **Using `block()` for checking in reactive production code.** Acceptable in a `main` method or an isolated test; in a WebFlux handler, return the publisher to the framework.

## 12. Testing and Observing Streams

In Reactor tests, `StepVerifier` (dependency `reactor-test`, using the same version as `reactor-core`) lets you verify **element order and terminal signals**:

```java
StepVerifier.create(Flux.just(1, 2).map(n -> n * 2))
            .expectNext(2, 4)
            .verifyComplete();
```

This is a test snippet; you need to import `reactor.test.StepVerifier`, `reactor.core.publisher.Flux`, and add the appropriate test dependency. For error streams, use `expectError(...)`/`expectErrorMatches(...)`; for time-based streams, look into virtual time for deterministic testing. Avoid testing asynchronous streams with `Thread.sleep` and assuming tasks have finished.

When observing production, use `doOnSubscribe`, `doOnRequest`, `doOnNext`, `doOnError`, and `doFinally` at appropriate points along with suitable metrics. Log selectively, avoiding sensitive data or entire large payloads; keep in mind a pipeline can be subscribed to multiple times. To propagate context across asynchronous operations, look into Reactor `Context` and Spring's observability mechanisms instead of always relying on `ThreadLocal`.

## 13. Self-Check Exercises

**Scenario A.** `Flux.just("A", "B").map(String::toLowerCase)` is created and nobody subscribes. Is there any `onNext`?  
**Answer:** No consumption takes place. This is a pipeline from a cold source; a subscription is required for elements to be emitted.

**Scenario B.** A source emits 1 → 2 → error → 3. Can the subscriber receive 3 after `onError`?  
**Answer:** No; an error is a terminal signal. To emit replacement data, you must switch to a fallback branch using an appropriate operator.

**Scenario C.** The subscriber only calls `request(1)`, and a backpressure-compliant source has 10 elements. What happens?  
**Answer:** At most one `onNext` is permitted to be emitted under the current demand; if no further request arrives, the stream may wait. There is an exception for terminal signals when the source can already determine termination; do not assume it must emit all 10 elements.

**Scenario D.** A WebFlux endpoint returns `Flux<String>` from SSE. Should you call `subscribe()` in the handler before `return`?  
**Answer:** No. Return the publisher so the framework subscribes according to the HTTP lifecycle and handles demand, errors, and cancellation consistently.

**Scenario E.** Each element triggers a non-blocking HTTP call and the result order is required to match the input order. Choose `flatMap` or `concatMap`?  
**Answer:** `concatMap` if strict sequential order is required; `flatMap` can complete interleaved, benefiting concurrency without guaranteeing that order.

## 14. Key Takeaways

**Data** flows through `onNext`; the **lifecycle** is defined by `onSubscribe`, `request`, `onError`, `onComplete`, and `cancel`. In Reactor, you compose operators to describe reactions to events, then let the subscriber or Spring WebFlux drive the pipeline. For a system to truly scale under the non-blocking model, non-blocking behavior must be preserved across I/O layers, demand and side effects must be managed, and both errors and unsubscriptions must be handled properly.

### References

- Spring Framework, [Spring WebFlux Overview](https://docs.spring.io/spring-framework/reference/web/webflux/new-framework.html).
- Spring Framework, [Reactive Core](https://docs.spring.io/spring-framework/reference/web/webflux/reactive-spring.html).
- Project Reactor, [Reactor Reference Guide](https://projectreactor.io/docs/core/release/reference/).
- [Reactive Streams specification](https://www.reactive-streams.org/).

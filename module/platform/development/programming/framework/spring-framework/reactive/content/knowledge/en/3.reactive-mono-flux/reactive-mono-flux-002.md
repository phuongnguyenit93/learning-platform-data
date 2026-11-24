# Flux Represents a Sequence of Zero to Many Elements (0..N) in Spring Reactive

## 1. Understanding the True Nature of `Flux<T>`

In **Project Reactor**, the reactive library commonly used by **Spring WebFlux**, `Flux<T>` is a `Publisher<T>` type representing **a stream of signals that can emit from 0 to many elements of type `T`** over time. Each element is sent to the receiver (`Subscriber`) via an `onNext(T)` signal. A normal finite stream ends with `onComplete()`; when it fails, it ends with `onError(Throwable)`.

The notation **0..N** describes **the number of elements emitted in a single subscription**, not the number of elements already existing in memory. `N` has no fixed upper bound: a `Flux` can emit 2, 100, a million elements, or emit continuously for a very long time. Not every `Flux` terminates; a live event stream can continue until the receiver cancels.

Basic cases:

| Case | Example | Signal Sequence |
| --- | --- | --- |
| **0 elements, completes successfully** | `Flux.empty()` | `onSubscribe → onComplete` |
| **1 element, completes successfully** | `Flux.just("A")` | `onSubscribe → onNext("A") → onComplete` |
| **N elements, completes successfully** | `Flux.just("A", "B", "C")` | `onSubscribe → onNext("A") → onNext("B") → onNext("C") → onComplete` |
| **Failure** | `Flux.error(ex)` or an error mid-stream | `onSubscribe → onNext(...)* → onError(ex)` |
| **Continuous stream** | Unbounded `Flux.interval(...)` | `onSubscribe → onNext(...)* → …`, may not have a terminal signal yet |

The `*` in the table means 0 or more times. A subscription follows this rule: there is only **one of the two terminal signals**, `onComplete` or `onError`, and no `onNext` after a terminal signal. A subscription can be cancelled with `cancel`. `Flux.never()` is a special case: after subscribing, it emits no elements, does not complete, and reports no error.

**Key point:** `Flux` describes how a sequence of data is delivered and processed; it is **not** a `List<T>`, an array, or a fully loaded collection. Being able to represent many elements does not mean all elements are always held in RAM.

## 2. Distinguishing Flux and Mono

Both `Flux<T>` and `Mono<T>` are `Publisher` implementations in Reactor, but they have different element-cardinality contracts.

| Property | `Mono<T>` | `Flux<T>` |
| --- | --- | --- |
| `onNext` elements per subscription | **0 or 1** | **0 to N** |
| Source examples | `Mono.just(user)`, `Mono.empty()` | `Flux.just(a, b)`, `Flux.range(1, 10)` |
| Common use cases | Finding one record, one HTTP result, an operation that only needs completion notification | List of records, multiple events, data streams, or continuous updates |
| Termination | Completes or errors; may also emit no terminal signal | Completes or errors; may also emit no terminal signal |
| Some conversion operators | `Mono<T>.flux()` creates `Flux<T>` | `Flux<T>.next()` returns `Mono<T>`; `collectList()` returns `Mono<List<T>>` |

For example, finding **one** user by ID typically fits `Mono<User>`; fetching **many** users by criteria typically fits `Flux<User>`. A `Flux` that emits exactly one element is still valid, but if the API guarantees at most one result, `Mono` expresses the contract more clearly.

A `Flux` can be empty even when the return type is `Flux<User>`: **having no results** is not necessarily an error. Conversely, an `onError` is a failure signal, not a normal data element. If a transformation produces multiple elements in the response, use `Flux`; if you aggregate all of them into one list, the result becomes **one** `Mono<List<T>>`, even though that list may contain many elements.

## 3. Signal- and Demand-Driven Emission Mechanism

A Reactor pipeline typically has three roles:

1. **Source (`Publisher`)**: produces or supplies elements, such as `Flux.range`, a reactive database driver, or an event stream.
2. **Operators (`Operator`)**: declare transformations such as `map`, `filter`, `take`, `flatMap`. A transformation can drop elements, produce additional elements, or change the result type.
3. **Receiver (`Subscriber`)**: subscribes to listen for signals and receives elements, errors, and completion.

The Reactive Streams model consists of `onSubscribe(Subscription)`, `onNext(T)`, `onError(Throwable)`, and `onComplete()`. Upon receiving `Subscription`, the receiver can call `request(n)` to demand `n` more elements and call `cancel()` to stop receiving. The **backpressure** mechanism lets the receiver regulate delivery demand, depending on whether the source and operators honor the contract and how they buffer data. It does not automatically make a database faster or rate-limit all incoming HTTP requests to the server.

A pipeline is usually **lazily executed** in the sense that processing signals begin upon subscription; however, creating objects or evaluating arguments at declaration time can still run immediately. For example, `Flux.just(expensiveCall())` calls `expensiveCall()` right when building the source; `Flux.defer(() -> Flux.just(expensiveCall()))` defers the call until subscription time.

Additional notes:

- **Reactive does not always mean asynchronous.** `Flux.just` and `Flux.range` typically emit elements synchronously right upon subscription; `Flux.interval` uses a scheduler and emits over time.
- **Reactive does not mean parallel execution.** Coordinating threads or performing parallel work requires examining schedulers, data sources, and appropriate operators; it cannot be inferred from the `Flux` type alone.
- **An `onNext` element must not be `null`.** Do not use `Flux.just(null)`; you can use `Flux.empty()` to represent no data, or convert from `Optional` with explicit handling.
- **Not every `Flux` is a cold stream.** With many cold sources (such as `Flux.range`), each subscription receives a fresh sequence; hot sources can share ongoing events across multiple subscribers, and late subscribers may miss events depending on configuration.

## 4. Common Ways to Create a Flux

| Factory | Effect | Example |
| --- | --- | --- |
| `Flux.empty()` | Empty sequence that completes immediately | No records found in a result set |
| `Flux.just(a, b, c)` | Sequence of pre-existing values, 1 or more elements | Emit three known names |
| `Flux.fromIterable(list)` | Emits elements from an `Iterable` when the source is subscribed to | Read elements of a `List` |
| `Flux.range(start, count)` | Emits `count` consecutive integers starting from `start` | `Flux.range(3, 4)` emits 3, 4, 5, 6 |
| `Flux.error(exception)` | Terminates with an error | Represent a failure injected into a pipeline |
| `Flux.defer(supplier)` | Creates a new publisher upon subscription | Defer computing the data source |
| `Flux.interval(duration)` | Emits `Long` numbers periodically, continuing indefinitely by default | Ticks 0, 1, 2,… over time |

With `Flux.range(3, 4)`, the second parameter is the **count** of elements rather than the end value; the result is `3, 4, 5, 6`, not `3, 4`. With `Flux.interval`, if you want a finite stream, you can use `take(n)` to receive the first `n` elements and then stop.

## 5. Runnable Java 17+ Example: 0 Elements, 1 Element, Many Elements, and Error

The example below uses **Reactor Core** directly via Maven, without starting Spring Boot, to observe `onNext`, `onComplete`, and `onError` accurately. Create two files with the following structure:

```text
flux-demo/
├── pom.xml
└── src/main/java/FluxDemo.java
```

Contents of `pom.xml`:

```xml
<project xmlns="http://maven.apache.org/POM/4.0.0"
         xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
         xsi:schemaLocation="http://maven.apache.org/POM/4.0.0 https://maven.apache.org/xsd/maven-4.0.0.xsd">
    <modelVersion>4.0.0</modelVersion>
    <groupId>example</groupId>
    <artifactId>flux-demo</artifactId>
    <version>1.0.0</version>
    <properties>
        <maven.compiler.release>17</maven.compiler.release>
    </properties>
    <dependencies>
        <dependency>
            <groupId>io.projectreactor</groupId>
            <artifactId>reactor-core</artifactId>
            <version>3.8.8</version>
        </dependency>
    </dependencies>
    <build>
        <plugins>
            <plugin>
                <groupId>org.apache.maven.plugins</groupId>
                <artifactId>maven-compiler-plugin</artifactId>
                <version>3.14.1</version>
            </plugin>
            <plugin>
                <groupId>org.codehaus.mojo</groupId>
                <artifactId>exec-maven-plugin</artifactId>
                <version>3.6.2</version>
            </plugin>
        </plugins>
    </build>
</project>
```

Contents of `src/main/java/FluxDemo.java`:

```java
import reactor.core.publisher.Flux;

public class FluxDemo {
    private static void show(String title, Flux<Integer> source) {
        System.out.println(title);
        source.subscribe(
            item -> System.out.println("onNext " + item),
            error -> System.out.println("onError " + error.getMessage()),
            () -> System.out.println("onComplete")
        );
    }

    public static void main(String[] args) {
        show("0 items", Flux.empty());
        show("1 item", Flux.just(7));

        Flux<Integer> transformed = Flux.range(1, 6)
            .filter(number -> number % 2 == 0)
            .map(number -> number * 10);
        show("many items", transformed);

        Flux<Integer> failed = Flux.concat(
            Flux.just(5),
            Flux.<Integer>error(new IllegalStateException("boom"))
        );
        show("error", failed);
    }
}
```

From the `flux-demo` directory, with JDK 17+ and Maven:

```bash
mvn -q compile exec:java -Dexec.mainClass=FluxDemo
```

**Program output** (ignoring Maven messages if the environment prints additional lines):

```text
0 items
onComplete
1 item
onNext 7
onComplete
many items
onNext 20
onNext 40
onNext 60
onComplete
error
onNext 5
onError boom
```

Case-by-case explanation:

- `Flux.empty()` is valid for emitting **0 elements**: only `onComplete`.
- `Flux.just(7)` is valid for emitting **1 element**: one `onNext`, then `onComplete`.
- `Flux.range(1, 6)` initially emits numbers 1 through 6. `filter` keeps even numbers 2, 4, 6, and `map` multiplies by 10, so the subscriber receives 20, 40, 60. This illustrates **N elements**, where N depends on the pipeline and does not have to equal the source element count.
- `Flux.concat` emits 5 and then switches to the error source. The subscriber receives `onError boom` and does **not** receive `onComplete` afterward.

All sources in the example (`empty`, `just`, `range`, `error`, and `concat` over them) emit synchronously, so the output order is deterministic. With `Flux.interval` or a source running on another scheduler, results can arrive later; a `main` program using `subscribe()` that exits too early may not wait for asynchronous signals. Waiting in a CLI program can be handled separately with appropriate tools; **do not use `block()` on the WebFlux event loop**.

## 6. Transforming a Sequence: Element Count Can Change

Suppose the source is `Flux.just(1, 2, 3, 4, 5)`. The operators have different meanings:

```java
Flux<Integer> source = Flux.just(1, 2, 3, 4, 5);

Flux<Integer> doubled = source.map(n -> n * 2);
Flux<Integer> evens = source.filter(n -> n % 2 == 0);
Flux<Integer> firstThree = source.take(3);
Mono<Integer> first = source.next();
Mono<Long> total = source.count();
Mono<java.util.List<Integer>> all = source.collectList();
```

This snippet illustrates expressions when the Reactor dependency is present, not a complete `main` program. Corresponding results:

- `map`: still 5 elements (2, 4, 6, 8, 10), changing **values**.
- `filter`: down to 2 elements (2, 4), changing **count**.
- `take(3)`: at most 3 elements (1, 2, 3), then stops the source early if needed.
- `next()`: converts to a `Mono<Integer>` containing the first element (1) or completes empty if the source has no data; may cancel the remainder after the first element.
- `count()`: `Mono<Long>` emits **one** number, 5, only when the source completes; infinite streams generally have no final count.
- `collectList()`: `Mono<List<Integer>>` emits **one** list `[1, 2, 3, 4, 5]` after the source completes; it must hold the elements in memory and is unsuitable for collecting an infinite source.

A `Flux` pipeline can transform into a `Mono` if an operator only returns a single aggregated value; that is a change in **type and result contract**, not a rule forcing every Flux to have a fixed N elements.

## 7. Application Example with Spring WebFlux

In Spring WebFlux, a controller can return `Flux<T>` directly. The framework subscribes to/consumes the publisher and encodes the data to send over HTTP. There is no need to call `subscribe()` manually inside the controller. The example below is **a controller placed in a Spring Boot project with `spring-boot-starter-webflux`**, not standalone plain Java:

```java
import java.time.Duration;
import org.springframework.http.MediaType;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.RestController;
import reactor.core.publisher.Flux;

@RestController
public class TickController {
    @GetMapping(value = "/ticks", produces = MediaType.TEXT_EVENT_STREAM_VALUE)
    public Flux<String> ticks() {
        return Flux.interval(Duration.ofSeconds(1))
            .take(3)
            .map(index -> "tick-" + index);
    }
}
```

When a client opens `GET /ticks` with SSE, the publisher is expected to emit three values `tick-0`, `tick-1`, `tick-2` roughly one second apart and then complete. The actual HTTP format is **Server-Sent Events**, which includes SSE fields/framing, so do not treat those three strings as the entire raw response body. Actual timing also depends on the scheduler and network. Because `interval` is a cold source per subscription, independently subscribed clients receive their own tick schedules.

With reactive repository data, a method like `findAll()` can return `Flux<Entity>` to represent a multi-record result set; it can still complete empty when nothing is found. Being able to emit element by element in the pipeline does not mean the HTTP client always sees each element immediately: a **JSON array** may be encoded and buffered depending on configuration/media type, whereas SSE or NDJSON is better suited when the goal is streaming data.

## 8. Common Pitfalls

1. **"Flux must have more than one element."** False. `Flux.empty()` and `Flux.just(7)` are both valid Fluxes. "0..N" includes 0, 1, and many.
2. **"Flux always emits infinitely."** False. `Flux.range`, `Flux.fromIterable`, and `Flux.just` are usually finite; `Flux.interval` can be infinite. `take(n)` is one way to bound a source.
3. **"Declaring a Flux means the data has already been loaded."** False. Most pipelines only define how data is produced/loaded/transformed; data is normally emitted on subscribe and can arrive over time.
4. **"Having a Flux automatically makes it non-blocking or parallel."** False. Synchronous or blocking code inside `map` can still block the executing thread. You need non-blocking drivers/clients and must not call `block()` on the event loop path.
5. **"You can emit null to represent no result found."** False. `onNext(null)` is not allowed; use `Flux.empty()`, `Mono.empty()`, or a clearer data model.
6. **"Calling subscribe multiple times always retrieves the same cached data."** False for cold sources; each subscription may re-trigger the query/API, while hot sources share differently. Check the nature of the source before expecting sharing.
7. **"collectList() makes streams memory-efficient."** False if it collects a large stream: it must retain all elements until completion. If the goal is streaming processing, use appropriate operators and control demand/buffering.
8. **"onError is just a normal value, followed by onComplete."** False. `onError` terminates the stream. To get recovery behavior, declare error-handling operators such as `onErrorResume` according to the business contract.
9. **"Backpressure automatically solves all overload problems."** False. `request(n)` demand regulates signals under Reactive Streams, but database resources, connections, queues, hot sources, and client speeds still need to be designed and monitored separately.

## 9. Self-Check

- How many `onNext` signals does `Flux.empty()` emit? **0**, yet it can complete successfully with `onComplete`.
- What does `Flux.range(10, 3)` emit? **10, 11, 12**; the second argument is the element count.
- Is a `Flux` that emits `A`, `B`, and then `onError` valid? **Yes**. After `onError`, there will be no `onComplete`.
- Is `Flux.just("A")` a Mono? **No**; it is still a `Flux<String>` emitting exactly one element.
- When do you need `Mono<List<T>>` instead of `Flux<T>`? When **a single result containing the entire list is required**, accepting completion latency and memory cost.
- Why is an unbounded `Flux.interval` source usually unsuitable for `collectList()`? Because there is no natural completion signal to emit the final list, and elements can continue to accumulate in memory.

**Key Takeaway:** `Flux<T>` describes **a sequence of signals consisting of 0, 1, or many elements** per subscription, which may terminate with completion/error or continue until cancelled. `Mono<T>` promises **at most one element**. When using Spring WebFlux, choose the type based on the business result cardinality, and pay attention to signals, subscriptions, cancellation, buffering, and errors — not just the element count at declaration time.

*References:* [Project Reactor — Flux, an Asynchronous Sequence of 0-N Items](https://projectreactor.io/docs/core/release/reference/coreFeatures/flux.html), [Project Reactor — Mono, an Asynchronous 0-1 Result](https://projectreactor.io/docs/core/release/reference/coreFeatures/mono.html).
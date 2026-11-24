# `map` for Synchronous Single-Element Transformation in Project Reactor

## 1. What Problem Does `map` Solve?

In Spring WebFlux/Project Reactor, data usually flows through a **pipeline** rather than being fetched and transformed in a traditional loop. The **`map`** operator receives each element emitted by a `Flux` or `Mono`, runs **a synchronous transformation function** on that element, and passes the result down to the next stage of the pipeline.

Practical examples: converting an amount from dong to thousands of dong, normalizing display names, converting an entity to a DTO, building a descriptive string from an object, or extracting a precomputed property. Each input element has **one output element** if the mapper succeeds. The transformation can keep the same type (`Integer -> Integer`) or change types (`User -> UserDto`, `Integer -> String`).

```java
Flux<Integer> tens = Flux.just(1, 2, 3)
        .map(number -> number * 10);
// When subscribed: 10, 20, 30
```

This is an **illustrative snippet** used in a context where `reactor.core.publisher.Flux` is already imported; a standalone runnable Java 17 program is provided in section 5.

Two things need to be distinguished:

- **Synchronous** describes the behavior of the *mapper function*: it takes `T` and returns `R` directly, without returning an asynchronous task such as `Mono<R>`.
- **Reactive** describes how elements flow through the pipeline when there is a subscription and demand. `map` does not create threads on its own, trigger queries on its own, or run before a subscriber connects.

Therefore, `map` still works well in reactive programs, but you must not place long-blocking work inside a mapper and assume it has become asynchronous.

## 2. API Signatures and One-to-One Contract

Two common forms in Reactor:

```java
<R> Flux<R> Flux<T>.map(
        java.util.function.Function<? super T, ? extends R> mapper);

<R> Mono<R> Mono<T>.map(
        java.util.function.Function<? super T, ? extends R> mapper);
```

These are **abbreviated signatures for explaining generics**, not valid Java method declaration syntax inside a class. They highlight the following points:

- `T`: the data type from upstream.
- `R`: the transformed data type emitted downstream.
- `Function<T,R>`: an operation that takes one `T`, computes, and directly returns one `R`.
- The result of `Flux.map(...)` is `Flux<R>`; the result of `Mono.map(...)` is `Mono<R>`. The pipeline remains in the reactive model.
- A mapper **must not return `null`** in Reactor. If it returns `null`, the pipeline emits an `onError` signal instead of sending `onNext(null)`.

In terms of cardinality, `map` is a **1 → 1 transformation on each `onNext` signal**. However, that does not mean `Mono` always produces an element: `Mono.empty().map(...)` remains empty; `Flux.empty().map(...)` still emits no values. `map` does not create elements out of an empty source.

Example preserving element count while changing type:

```java
Flux<String> labels = Flux.just(10, 20, 30)
        .map(n -> "Value: " + n);
// "Value: 10", "Value: 20", "Value: 30"
```

## 3. When Does `map` Run and Which Signal Flow Does It Follow?

Reactor typically builds pipelines in two logical phases:

1. **Assembly (declarative):** calling `Flux.just(...).map(...)` creates a description of the work. With a typical cold source, the mapper has not received any data yet.
2. **Subscription/execution:** downstream subscribes; when upstream emits `onNext(T)` according to demand, the operator invokes the mapper, receives `R`, and emits `onNext(R)` downstream.

```text
Upstream Flux<T>
    |
    | onNext(T) on demand
    v
map(Function<T, R>)
    |
    | apply(T) -> R  [synchronous]
    v
Downstream Subscriber<R>
    |
    +-- handle onNext(R)
```

The `onSubscribe`, `onError`, and `onComplete` flows must also be obeyed. `map` does not turn completion into data; errors emitted from upstream are forwarded downstream, while an exception thrown **inside the mapper** causes the stream to emit `onError` and terminate according to the contract.

A key point to remember about threading: `map` **does not switch threads on its own**. The mapper is invoked in the upstream signal-emission context and is affected by scheduling operators such as `subscribeOn`/`publishOn` if present. A simple synchronous pipeline like `Flux.just(...).map(...)` can run on the very thread that calls `subscribe()`. Having `map` does not guarantee parallel execution or execution on a separate event loop.

## 4. How to Read a Transformation in Practice

### 4.1. Data Normalization

```java
Flux<String> cleaned = Flux.just("  an  ", " binh ", "chi")
        .map(String::trim)
        .map(String::toUpperCase);
```

With an appropriate default locale for the ASCII examples above, the pipeline produces `AN`, `BINH`, `CHI`. In production where results must not depend on the server locale, use `s -> s.toUpperCase(Locale.ROOT)` and import `java.util.Locale`.

Two `map` calls are **two sequential transformation steps on the same element**: each name is trimmed with `trim()`, then converted to uppercase. They do not turn three elements into six elements.

### 4.2. Converting an Entity to a DTO

With Java 17, `record` is well suited for representing immutable data types:

```java
record Product(int id, String name, long price) {}
record ProductView(int id, String label) {}

Flux<ProductView> views = Flux.just(
        new Product(1, "Pen", 12_000),
        new Product(2, "Book", 50_000))
    .map(p -> new ProductView(
        p.id(),
        p.name() + ": " + p.price() + " VND"
    ));
```

This is a **code snippet that must be placed inside a Java class/context with `Flux` imported**, not a standalone file. If the mapper builds a plain DTO without performing I/O, `map` accurately expresses the intent of **converting `Product` into `ProductView` for each element**. Transformations of this kind are usually placed in the service/presentation layer so entities are not exposed directly through the API.

### 4.3. `Mono.map` with At Most One Element

```java
Mono<String> upper = Mono.just("spring")
        .map(value -> value.toUpperCase(java.util.Locale.ROOT));
// Emits "SPRING" when subscribed.
```

`Mono.map` is also synchronous and one-to-one, but since an upstream `Mono` has at most one value, the result also has at most one value.

## 5. Complete Runnable Example on Java 17+

The example below demonstrates four behaviors in **one program**: the mapper only runs upon subscription; `Flux.map` transforms values; converting a record to a record; `Mono.map` transforms a string; and an error in the mapper terminates the original source and can be handled with `onErrorResume`.

Create the directory:

```text
reactor-map-demo/
├── pom.xml
└── src/main/java/demo/Main.java
```

File `pom.xml`:

```xml
<project xmlns="http://maven.apache.org/POM/4.0.0"
         xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
         xsi:schemaLocation="http://maven.apache.org/POM/4.0.0 https://maven.apache.org/xsd/maven-4.0.0.xsd">
    <modelVersion>4.0.0</modelVersion>

    <groupId>demo</groupId>
    <artifactId>reactor-map-demo</artifactId>
    <version>1.0-SNAPSHOT</version>

    <properties>
        <maven.compiler.release>17</maven.compiler.release>
        <project.build.sourceEncoding>UTF-8</project.build.sourceEncoding>
    </properties>

    <dependencies>
        <dependency>
            <groupId>io.projectreactor</groupId>
            <artifactId>reactor-core</artifactId>
            <version>3.6.12</version>
        </dependency>
    </dependencies>

    <build>
        <plugins>
            <plugin>
                <groupId>org.codehaus.mojo</groupId>
                <artifactId>exec-maven-plugin</artifactId>
                <version>3.5.0</version>
                <configuration>
                    <mainClass>demo.Main</mainClass>
                </configuration>
            </plugin>
        </plugins>
    </build>
</project>
```

File `src/main/java/demo/Main.java`:

```java
package demo;

import java.util.Locale;
import reactor.core.publisher.Flux;
import reactor.core.publisher.Mono;

public class Main {
    record Item(int id, String name) {}
    record ItemView(int id, String name) {}

    public static void main(String[] args) {
        // 1) Only creates the pipeline, does not emit onNext yet.
        Flux<Integer> tens = Flux.just(1, 2, 3)
                .map(n -> {
                    System.out.println("map: " + n);
                    return n * 10;
                });

        System.out.println("assembled");

        // 2) Subscribing triggers this synchronous Flux.just source.
        tens.subscribe(
                n -> System.out.println("next: " + n),
                e -> System.out.println("error: " + e.getMessage()),
                () -> System.out.println("complete")
        );

        // 3) Transform source objects into new DTOs.
        Flux<ItemView> views = Flux.just(
                new Item(1, " An "),
                new Item(2, " Binh ")
        ).map(item -> new ItemView(
                item.id(),
                item.name().trim()
        ));

        views.subscribe(view ->
                System.out.println(
                        "item: " + view.id() + "/" + view.name()
                )
        );

        // 4) Mono.map handles at most one value.
        Mono<String> mono = Mono.just("reactor")
                .map(s -> s.toUpperCase(Locale.ROOT));

        mono.subscribe(s -> System.out.println("mono: " + s));

        // 5) An error inside the mapper becomes onError.
        // onErrorResume replaces the errored stream with a fallback.
        Flux.just("12", "bad", "36")
                .map(Integer::parseInt)
                .onErrorResume(error -> Flux.just(-1))
                .subscribe(n -> System.out.println("safe: " + n));
    }
}
```

Open a terminal in `reactor-map-demo/`, with JDK 17+ and Maven:

```bash
mvn -q compile exec:java
```

Stdout printed by the program (excluding environment messages if Maven has custom configuration):

```text
assembled
map: 1
next: 10
map: 2
next: 20
map: 3
next: 30
complete
item: 1/An
item: 2/Binh
mono: REACTOR
safe: 12
safe: -1
```

**Result explanation:**

- `assembled` appears before `map: 1` because `Flux.just` is a synchronous cold source and the mapper has not run during pipeline assembly.
- After `subscribe`, each number goes through the mapper and then to the consumer, so the `map: n` line appears before `next: n * 10`.
- `Flux.map` creates a new `ItemView` from each `Item`; the result consists of exactly two DTOs.
- `Mono.map` converts one string to uppercase and emits one string.
- `"12"` is parsed into `12`. At `"bad"`, `Integer.parseInt` throws `NumberFormatException`; Reactor emits `onError` at the `map` step. `onErrorResume` switches to `Flux.just(-1)`, so it prints `safe: -1`; `"36"` **does not continue to be processed** after the error from the preceding source.

In real applications, choose a fallback only when it makes business sense. A data conversion error should not always be turned into a dummy value like `-1`; in some cases you need to return an error to the client or record the invalid input data.

## 6. How Does `map` Interact with Backpressure and Completion?

Reactive Streams specifies that each `onNext` signal may only be sent downstream when there is demand to receive it. `map` receives one element and produces one result, so it **does not alter the number of elements passing through it**, provided the mapper succeeds.

For example, with `Flux.range(1, 100).map(n -> n * 2)`, if downstream requests two values (`request(2)`), it is only entitled to receive at most two `onNext` signals at that stage, namely `2` and `4`; subsequent elements require further demand. This does not mean two elements necessarily appear immediately for every kind of source, or that the underlying data retrieval corresponds to exactly two I/O operations: other operators may apply prefetching, buffering, or their own upstream request strategies.

For a simple pipeline:

```text
Publisher<T>
  -- onNext(t) -->
      map(t -> r)
  -- onNext(r) -->
Subscriber<R>

Upstream onComplete  -> downstream onComplete
Upstream onError     -> downstream onError
Mapper throw         -> downstream onError, stream terminates
```

`map` does not emit an extra completion signal for each value. A subscription completes when **the entire source** completes normally. Calling `cancel()` from downstream can stop processing that has not yet occurred; the operator cannot guarantee reclaiming every signal already in flight in an asynchronous context.

### Empty Sources and `null` Inputs

- `Flux.empty().map(f)` does not invoke `f`; it only completes.
- `Mono.empty().map(f)` does not create a default value; use `defaultIfEmpty` or `switchIfEmpty` when business logic requires an alternative branch.
- Reactive Streams does not allow `null` as an `onNext` element. A mapper in Reactor that returns `null` will cause an error; do not use `null` to represent “skip this element”.

If the goal is to **exclude** values based on a condition, use `filter`. If you need a transformation that can produce zero elements when returning `null` and your Reactor version supports it, consider `mapNotNull`; you must understand its value-filtering semantics, which differ from one-to-one `map`.

## 7. Comparing `map`, `filter`, `flatMap`, `concatMap`, and `doOnNext`

| Operator | Input function / meaning | Typical output cardinality | When to use |
|---|---|---|---|
| `map` | Synchronous `T -> R` | One result per input `onNext` if successful | Field normalization, value calculation, entity → DTO |
| `filter` | `T -> boolean` | 0 or 1 per input | Keeping elements that satisfy a condition |
| `flatMap` | `T -> Publisher<R>` then merges inner publishers | 0, 1, or many per input | Calling services/repositories returning `Mono` or `Flux`, composing async operations |
| `concatMap` | `T -> Publisher<R>`, concatenates inner publishers **in order** | 0, 1, or many | When processing/emission order matching the source must be preserved |
| `doOnNext` | Observation function `Consumer<T>` | Not meant to transform values | Logging, metrics, signal observation; avoid for business logic with hard-to-control side effects |

Example of an API returning `Mono<UserDto>` for each ID:

```java
Flux<Mono<UserDto>> nested = userIds
        .map(id -> userService.findDtoById(id));
```

This is an **illustrative snippet containing application-dependent variables/services**, not a standalone runnable program. If `findDtoById` returns `Mono<UserDto>`, using `map` creates a **Flux containing Monos** (`Flux<Mono<UserDto>>`), which is usually not the data the client expects. When you need to flatten the results into an actual `Flux<UserDto>`, use:

```java
Flux<UserDto> users = userIds
        .flatMap(id -> userService.findDtoById(id));
```

`flatMap` can process multiple inner publishers in an interleaved manner and does not preserve input emission order in all cases. When **strict order** is required, consider `concatMap`. Returning a `Publisher` from the mapper is a key sign to choose `flatMap`/`concatMap` instead of `map`.

Conversely, `user -> new UserDto(user.id(), user.name())` returns a DTO directly, so using `map` is right. There is no need to use `flatMap(id -> Mono.just(id * 2))` just to perform a synchronous calculation.

## 8. Common Implementation Mistakes

### 8.1. Not Assigning or Not Using the New Publisher

```java
Flux<Integer> source = Flux.just(1, 2, 3);
source.map(n -> n * 10); // Creates a new pipeline and discards it.
source.subscribe(System.out::println); // Still prints 1, 2, 3.
```

`map` does not mutate `source` in place; it returns a new Publisher with the transformation logic attached. You must use the returned pipeline:

```java
Flux<Integer> mapped = source.map(n -> n * 10);
mapped.subscribe(System.out::println); // Prints 10, 20, 30.
```

### 8.2. Blocking the Thread Inside the Mapper

```java
// Anti-pattern: do not call blocking I/O arbitrarily inside map.
Flux<User> result = ids.map(id -> blockingClient.loadUser(id));
```

If `blockingClient.loadUser` waits on the network/database, it can stall the signal-processing thread, especially when running on the WebFlux event loop. If the library provides a non-blocking API returning `Mono<User>`, typically choose `flatMap`. If you must integrate a blocking library, consider wrapping the work in a Publisher and scheduling it appropriately, such as `Mono.fromCallable(...).subscribeOn(Schedulers.boundedElastic())`, then composing via `flatMap` while managing concurrency and system load. **Do not use `map` for asynchronous work by returning a `Mono` and forgetting to flatten it.**

### 8.3. Mapper Containing Uncontrolled Side Effects

```java
Flux<Integer> results = Flux.just(1, 2)
        .map(n -> {
            auditList.add(n); // Subscription-dependent side effect.
            return n * 2;
        });
```

With a cold Publisher, each subscription can cause the mapper to run again, repeating the side effect. At the same time, when a pipeline switches schedulers or has multiple subscriptions, shared state can introduce concurrency risks. Prefer **pure** mappers (same input, same output, no external state mutation). Use `doOnNext` for observation/logging and handle business side effects with an explicit design for errors, retries, and idempotency.

### 8.4. Returning `null` or Swallowing Errors

```java
Flux<String> invalid = Flux.just("A", "B")
        .map(s -> s.equals("B") ? null : s);
```

This is an **anti-pattern**: when `"B"` arrives, the mapper returns `null` and Reactor terminates the sequence with an error. If you want to omit `"B"`, use `filter(s -> !s.equals("B"))` or choose an appropriate filtering/transformation operator—do not push `null` downstream.

### 8.5. Confusing `map` with Java's `Stream.map`

Both `java.util.stream.Stream.map` and `reactor.core.publisher.Flux.map` take a `Function`, but their execution mechanisms differ. Java Stream is an API for processing collections/streams of data driven by a Stream terminal operation; a Reactor Publisher implements the protocol of subscription, demand, completion/error, and can coordinate asynchronous sources. Do not infer all threading, error, or backpressure behaviors of Reactor from `Stream.map`.

## 9. Applying in Spring WebFlux

A WebFlux controller can return a `Flux` containing transformed values:

```java
// Illustrative snippet inside a Spring WebFlux application with dependencies/imports.
@RestController
class PriceController {
    @GetMapping("/prices")
    public Flux<String> prices() {
        return Flux.just(100, 200, 300)
                .map(price -> "VND " + price);
    }
}
```

In this example, the mapper simply converts `Integer` to `String` synchronously and quickly. Spring WebFlux takes responsibility for subscribing and handling the response/error/cancellation in the HTTP context. There is no need to call `subscribe()` yourself in the controller to collect results and return a manually mutated list.

In applications with a reactive repository, a common pattern is:

```java
// Illustration depending on the project's UserEntity, UserDto, and userRepository types.
Mono<UserDto> response = userRepository.findById(id)
        .map(entity -> new UserDto(entity.getId(), entity.getName()));
```

When `findById(id)` returns `Mono<UserEntity>`, `map` returns `Mono<UserDto>` with the same state: no result remains empty, an upstream error remains an error, and if an entity is present it becomes a DTO. The mapper converts the object in memory without querying the data a second time.

## 10. Self-Check

**Question 1.** What does `Flux.just(2, 4).map(n -> n + 1).map(n -> n * 3)` emit?

Result: `9`, `15`. For each element, the first mapper runs before the second mapper; the number of elements does not change.

**Question 2.** Does `Mono.empty().map(value -> expensiveCalculation(value))` execute `expensiveCalculation`?

No. The source emits no `onNext`, so there is no element to pass to the mapper.

**Question 3.** How does `map(id -> service.fetch(id))` differ from `flatMap(id -> service.fetch(id))` when `fetch` returns `Mono<Result>`?

`map` produces elements of type `Mono<Result>` (e.g., `Flux<Mono<Result>>` if the source is a Flux); `flatMap` subscribes/composes the inner Publishers so downstream directly receives `Result` and coordinates their signals, errors, and demand.

**Question 4.** Does `map` automatically move computation to another thread or allow emitting elements regardless of demand?

No. `map` is a synchronous transformation at the moment a signal is received; it remains within the reactive protocol, and scheduler switching must be configured separately when needed.

**Remember:** choose **`map` when converting each `T` into one `R` using a fast, synchronous, non-null operation**; use the Publisher result that `map` returns; let the source and Reactor manage subscription/demand; and use other operators when you need filtering, emitting multiple elements, or composing asynchronous tasks.

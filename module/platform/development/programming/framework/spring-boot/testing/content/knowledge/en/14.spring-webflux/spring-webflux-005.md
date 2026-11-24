# Testing Mono, Flux, and Multi-Element Data in Spring WebFlux

In **Spring WebFlux**, a service typically returns `Mono<T>` or `Flux<T>` instead of directly returning an object or a `List<T>`. Therefore, a proper test does not just ask "what is the value?" — it must also ask **upon subscription, how many items does the publisher emit, in what order, does it complete or emit an error, and does it honor consumer demand (backpressure)?**

The dedicated tool for verifying those contracts is **`StepVerifier`** from the `reactor-test` library. `StepVerifier` creates a test subscriber, explicitly sets expectations on reactive signals, and only executes the verification when `verify()` or a terminal helper such as `verifyComplete()` is called.

This article focuses on **testing `Mono`, `Flux`, and multi-element data** with runnable Java 17+ examples for Spring Boot/WebFlux projects. Topics include single values/empty streams/errors, ordering and counts, `Mono<List<T>>` vs `Flux<T>`, batching, virtual time, backpressure, and the boundary between Reactor-level tests and HTTP tests via `WebTestClient`.

## 1. Mechanism: Test Signals, Do Not Compare Publisher Objects

Reactor is built on the Reactive Streams model: a publisher emits signals to a subscriber after subscription.

```text
Subscriber                     Publisher
    |                              |
    |---------- subscribe -------->|
    |<--------- onSubscribe -------|
    |---------- request(n) ------->|
    |<--------- onNext(A) ---------|
    |<--------- onNext(B) ---------|
    |<--------- onComplete --------|
    |
    +-- or receives onError(exception) instead of onComplete
    +-- or cancels subscription before the source finishes on its own
```

A spec-compliant sequence terminates with **`onComplete` or `onError`**, never both. After a terminal signal, no further `onNext` occurs. Before subscribing, many publishers are created **lazily**, meaning the logic you intend to test has not run yet.

| Publisher | Number of `onNext` | Terminal signal | Meaning |
| --- | ---: | --- | --- |
| `Mono.just("A")` | 1 | complete | Has one result |
| `Mono.empty()` | 0 | complete | No result, not an error |
| `Mono.error(ex)` | 0 | error | Terminates with failure |
| `Flux.just("A","B","C")` | 3 | complete | Has multiple items |
| `Flux.empty()` | 0 | complete | Stream has zero items |
| `Flux.concat(Flux.just(1,2), Flux.error(ex))` | 2 | error | Emits data then errors |
| `Flux.never()` | 0 | never terminates on its own | Needs a limit/cancel so tests do not hang |
| `Mono<List<String>>` emitting `List.of("A","B")` | **1** | complete | One item that is the whole list |

**`Flux<T>` can emit 0, 1, many, or infinite elements**; the name `Flux` does not force it to always have two or more elements. **`Mono<T>` emits at most one element**, including the empty completion case. Reactor forbids `null` as an `onNext` value: `Mono.just(null)` is not how absence is represented.

Comparing two publishers directly:

```java
assertEquals(Mono.just("A"), someService.find("A"));
```

does not prove the sequence emits `"A"`. That compares **two publisher descriptor objects** rather than verifying signals after subscription. The proper test:

```java
StepVerifier.create(someService.find("A"))
        .expectNext("A")
        .verifyComplete();
```

Both snippets only illustrate usage: `someService.find("A")` is assumed to return `Mono<String>`. The runnable examples below include concrete production code and full imports.

## 2. StepVerifier APIs You Need to Know

Basic pattern:

```java
StepVerifier.create(publisher)
        .expectNext(expectedFirst, expectedSecond)
        .verifyComplete();
```

`StepVerifier.create(...)` sets up the verification script. Calling `verifyComplete()` subscribes, demands two `onNext` signals matching the exact content/order, and expects `onComplete`. Missing/extra items, wrong values, an error signal, or failure to complete as scripted causes verification to fail.

| API | Purpose | Limit to Remember |
| --- | --- | --- |
| `expectNext(a,b)` | Checks values in exact order | Unsuitable if the contract does not guarantee ordering |
| `expectNextSequence(iterable)` | Checks a sequence of values from an `Iterable` | Also requires exact order |
| `expectNextCount(n)` | Verifies `n` subsequent elements arrive | **Does not inspect the content** of those `n` elements |
| `assertNext(item -> ...)` | Runs detailed assertions on one element | Each `assertNext` consumes one `onNext` |
| `expectNextMatches(predicate)` | Next element satisfies predicate | Only verifies the written predicate |
| `recordWith(...).consumeRecordedWith(...)` | Records `onNext` values and asserts the collection | Has memory overhead |
| `verifyComplete()` | Verifies completion after expected values | Do not use for non-terminating infinite streams |
| `expectErrorMatches(...).verify()` | Verifies termination with matching error | No `onComplete` follows an error |
| `thenRequest(n)` | Increases demand granted to upstream | Works with sources that honor backpressure |
| `thenCancel()` | Cancels subscription | Does not imply the source completed on its own |
| `withVirtualTime(() -> publisher)` | Tests timers/delays using a virtual clock | Publisher must be created inside the supplier |

Do not forget terminal verification: writing only `StepVerifier.create(publisher).expectNext(...)` and exiting the method **has not executed the assertions**. For error tests, e.g.:

```java
StepVerifier.create(
                Mono.error(new IllegalStateException("down")))
        .expectErrorMatches(error ->
                error instanceof IllegalStateException
                && "down".equals(error.getMessage()))
        .verify();
```

This test expects `onError`, not `onComplete`. Do not wrap a call returning `Mono.error` in `assertThrows` if the exception is delivered **asynchronously upon subscription** rather than thrown synchronously from the Java method.

## 3. Setting Up JUnit Jupiter and reactor-test

In a Spring Boot project with Gradle, dependency management, and appropriate plugins, the needed section in `build.gradle` (Groovy DSL) is:

```groovy
dependencies {
    implementation 'org.springframework.boot:spring-boot-starter-webflux'

    testImplementation 'org.springframework.boot:spring-boot-starter-test'
    testImplementation 'io.projectreactor:reactor-test'
}

tasks.named('test') {
    useJUnitPlatform()
}
```

This is an **additive configuration snippet**, not a complete standalone `build.gradle` file. The WebFlux starter provides Reactor Core, while `reactor-test` provides `StepVerifier`. Projects not using the WebFlux starter can still test Reactor if compatible `reactor-core` and `reactor-test` versions are on the classpath.

Common imports:

```java
import reactor.core.publisher.Flux;
import reactor.core.publisher.Mono;
import reactor.test.StepVerifier;

import org.junit.jupiter.api.Test;
import static org.junit.jupiter.api.Assertions.assertEquals;
```

If you only need to test pure Java pipelines, **you do not need `@SpringBootTest`, `@WebFluxTest`, an HTTP server, or a database**. Spring Boot only becomes part of the test when you need to verify bean wiring, WebFlux HTTP infrastructure, security, persistence, or another integration.

## 4. Production Java 17+ Example: SKU Catalog

To clearly see different publisher shapes, let us build a class backed by fixed data:

| Position | SKU | Units |
| ---: | --- | ---: |
| 1 | `JAVA-1` | 2 |
| 2 | `JAVA-2` | 5 |
| 3 | `SPRING-1` | 7 |
| 4 | `JAVA-3` | 0 |

Choosing prefix `JAVA` returns three SKUs in source order: `JAVA-1, JAVA-2, JAVA-3`. Choosing prefix `NO` returns an empty `Flux`. In the example, a valid prefix consists solely of one or more ASCII uppercase letters `A–Z`.

Methods:

- `find(code)`: `Mono<Sku>` containing one SKU, empty if not found, or `onError` if `code` is blank.
- `list(prefix)`: `Flux<Sku>` with 0 or more SKUs; invalid prefix returns `Flux.error(...)`.
- `count(prefix)`: `Mono<Long>` counting matching SKUs.
- `collect(prefix)`: `Mono<List<Sku>>` emitting a single list.
- `batches(prefix,size)`: `Flux<List<Sku>>` emitting one or more lists in batches.

File structure:

```text
src/
├── main/java/example/testing/webflux/
│   ├── SkuRule.java
│   ├── SkuRuleDemo.java
│   └── SkuCatalog.java
└── test/java/example/testing/webflux/
    ├── SkuCatalogTest.java
    └── StepVerifierAdvancedTest.java
```

### 4.1. Pure Java Rule: SkuRule.java

Create `src/main/java/example/testing/webflux/SkuRule.java`:

```java
package example.testing.webflux;

public final class SkuRule {
    private SkuRule() {
    }

    public static boolean validPrefix(String prefix) {
        return prefix != null
                && prefix.matches("[A-Z]+");
    }
}
```

Separating the rule from the reactive pipeline makes testing easier. The regex `[A-Z]+` accepts only strings of at least one uppercase letter, rejecting lowercase, digits, whitespace, or null. This is an **example-specific rule**, not representative of every SKU naming standard.

### 4.2. Reactor Data: SkuCatalog.java

Create `src/main/java/example/testing/webflux/SkuCatalog.java`:

```java
package example.testing.webflux;

import java.util.List;
import java.util.Objects;

import reactor.core.publisher.Flux;
import reactor.core.publisher.Mono;

public final class SkuCatalog {
    private final List<Sku> source;

    public SkuCatalog(List<Sku> source) {
        this.source = List.copyOf(
                Objects.requireNonNull(source, "source"));
    }

    public Mono<Sku> find(String code) {
        if (code == null || code.isBlank()) {
            return Mono.error(new IllegalArgumentException(
                    "code must not be blank"));
        }

        return Flux.fromIterable(source)
                .filter(sku -> sku.code().equals(code))
                .next();
    }

    public Flux<Sku> list(String prefix) {
        if (!SkuRule.validPrefix(prefix)) {
            return Flux.error(new IllegalArgumentException(
                    "prefix must use A-Z"));
        }

        return Flux.fromIterable(source)
                .filter(sku -> sku.code().startsWith(prefix));
    }

    public Mono<Long> count(String prefix) {
        return list(prefix).count();
    }

    public Mono<List<Sku>> collect(String prefix) {
        return list(prefix).collectList();
    }

    public Flux<List<Sku>> batches(
            String prefix, int batchSize) {
        if (batchSize <= 0) {
            return Flux.error(new IllegalArgumentException(
                    "batchSize must be positive"));
        }

        return list(prefix).buffer(batchSize);
    }
}

record Sku(String code, int units) {
}
```

The code above has **one top-level public class** matching the filename and one package-private record, valid in Java 17. Tests reside in the same package to use `Sku`. `Sku` is a record, so it has value-based `equals/hashCode`, convenient for `expectNext(new Sku(...))`.

Notable characteristics:

- `List.copyOf(...)` holds an unmodifiable list via the service reference. Tests use `List.of(...)` and immutable `Sku` records so data is deterministic on every subscription.
- `Flux.fromIterable(source)` emits each SKU in List iteration order. `filter(...)` preserves the order of remaining items.
- `next()` takes the first element as `Mono<Sku>`; if no elements exist, the `Mono` completes empty.
- `Mono.error(...)` and `Flux.error(...)` emit errors upon subscription, unlike throwing immediately from the Java method.
- `count()` emits a single `Long`, including `0L` when the source `Flux` is empty.
- `collectList()` emits a single `List`, even when the `List` is empty.
- `buffer(2)` on a 3-element stream emits two `List`s: a 2-element list and a final 1-element list.

### 4.3. Verifying the Pure Rule with javac/java

Create `src/main/java/example/testing/webflux/SkuRuleDemo.java`:

```java
package example.testing.webflux;

public class SkuRuleDemo {
    public static void main(String[] args) {
        System.out.println(SkuRule.validPrefix("JAVA"));
        System.out.println(SkuRule.validPrefix("java"));
        System.out.println(SkuRule.validPrefix(null));
        System.out.println(SkuRule.validPrefix("JAVA2"));
    }
}
```

Compile/run from the project root with JDK 17+:

```bash
javac -d out src/main/java/example/testing/webflux/SkuRule.java src/main/java/example/testing/webflux/SkuRuleDemo.java
java -cp out example.testing.webflux.SkuRuleDemo
```

**Exact** stdout:

```text
true
false
false
false
```

This `javac` command **only verifies the pure Java rule**; it does not run `SkuCatalog` or `StepVerifier` since those two require Reactor dependencies from the build. The full Reactor tests can be run with Gradle in the next section.

## 5. Complete JUnit Test Suite for Mono, Flux, and Collections

Create `src/test/java/example/testing/webflux/SkuCatalogTest.java`:

```java
package example.testing.webflux;

import java.util.List;

import org.junit.jupiter.api.BeforeEach;
import org.junit.jupiter.api.Test;
import reactor.core.publisher.Flux;
import reactor.test.StepVerifier;

import static org.junit.jupiter.api.Assertions.assertEquals;

class SkuCatalogTest {
    private static final Sku FIRST =
            new Sku("JAVA-1", 2);
    private static final Sku SECOND =
            new Sku("JAVA-2", 5);
    private static final Sku OTHER =
            new Sku("SPRING-1", 7);
    private static final Sku THIRD =
            new Sku("JAVA-3", 0);

    private SkuCatalog catalog;

    @BeforeEach
    void setUp() {
        catalog = new SkuCatalog(
                List.of(FIRST, SECOND, OTHER, THIRD));
    }

    @Test
    void monoEmitsOneSkuThenCompletes() {
        StepVerifier.create(catalog.find("JAVA-2"))
                .expectNext(SECOND)
                .verifyComplete();
    }

    @Test
    void missingSkuYieldsEmptyMono() {
        StepVerifier.create(catalog.find("MISSING"))
                .verifyComplete();
    }

    @Test
    void invalidSkuEmitsErrorInsteadOfValue() {
        StepVerifier.create(catalog.find(" "))
                .expectErrorMatches(error ->
                        error instanceof IllegalArgumentException
                        && "code must not be blank"
                            .equals(error.getMessage()))
                .verify();
    }

    @Test
    void fluxEmitsThreeSkusInSourceOrder() {
        StepVerifier.create(catalog.list("JAVA"))
                .expectNext(FIRST, SECOND, THIRD)
                .verifyComplete();
    }

    @Test
    void fluxWithoutMatchesCompletesEmpty() {
        StepVerifier.create(catalog.list("NO"))
                .verifyComplete();
    }

    @Test
    void invalidPrefixIsReactiveError() {
        StepVerifier.create(catalog.list("java"))
                .expectErrorMatches(error ->
                        error instanceof IllegalArgumentException
                        && "prefix must use A-Z"
                            .equals(error.getMessage()))
                .verify();
    }

    @Test
    void assertsFirstElementAndCountsTheRest() {
        StepVerifier.create(catalog.list("JAVA"))
                .assertNext(sku -> {
                    assertEquals("JAVA-1", sku.code());
                    assertEquals(2, sku.units());
                })
                .expectNextCount(2)
                .verifyComplete();
    }

    @Test
    void collectListEmitsOneListOfThreeItems() {
        StepVerifier.create(catalog.collect("JAVA"))
                .expectNext(List.of(FIRST, SECOND, THIRD))
                .verifyComplete();
    }

    @Test
    void collectEmptyFluxStillEmitsAnEmptyList() {
        StepVerifier.create(catalog.collect("NO"))
                .expectNext(List.of())
                .verifyComplete();
    }

    @Test
    void countEmitsOneLongValue() {
        StepVerifier.create(catalog.count("JAVA"))
                .expectNext(3L)
                .verifyComplete();
    }

    @Test
    void batchesEmitTwoLists() {
        StepVerifier.create(catalog.batches("JAVA", 2))
                .expectNext(
                        List.of(FIRST, SECOND),
                        List.of(THIRD))
                .verifyComplete();
    }

    @Test
    void onErrorResumeReplacesErrorWithFallbackValue() {
        Flux<Sku> recovered = catalog.list("bad")
                .onErrorResume(IllegalArgumentException.class,
                        error -> Flux.just(new Sku("FALLBACK", 0)));

        StepVerifier.create(recovered)
                .expectNext(new Sku("FALLBACK", 0))
                .verifyComplete();
    }

    @Test
    void coldFluxCanBeSubscribedTwice() {
        Flux<Sku> flux = catalog.list("JAVA");

        StepVerifier.create(flux)
                .expectNext(FIRST, SECOND, THIRD)
                .verifyComplete();

        StepVerifier.create(flux)
                .expectNext(FIRST, SECOND, THIRD)
                .verifyComplete();
    }
}
```

**The class above has 13 test methods** (counting each `@Test`). Each method declares expectations and then triggers verification. There is no Spring context, DB, or WebFlux HTTP server. Key scenarios covered:

- **Mono with one value:** `expectNext(SECOND).verifyComplete()`.
- **Mono not found:** `verifyComplete()` with no `expectNext`, meaning empty and successful.
- **Mono error:** `expectErrorMatches(...).verify()`, not catching synchronous exceptions from calling `find(...)`.
- **Three-item Flux:** `expectNext(FIRST, SECOND, THIRD)` checks exact content and order; `verifyComplete()` also catches unexpected extra items.
- **Empty Flux:** zero `onNext`, followed by `onComplete`.
- **Detailed assertions:** `assertNext` inspects fields of the first item; `expectNextCount(2)` only verifies the **count of the next two items**, not their values.
- **`Mono<List<Sku>>`:** one `onNext` carrying a single `List` of three `Sku`s. Do not expect three separate `Sku` signals.
- **Empty list:** `collectList()` on an empty `Flux` still emits one `List.of()` before completing.
- **Count:** `count("JAVA")` emits a single `Long` `3L`, not three `onNext` signals.
- **Batches:** `Flux<List<Sku>>` emits two `List`s, one of size 2 and one of size 1.
- **Recovery:** `onErrorResume` turns an error into a fallback value + normal completion; downstream no longer sees the original error.
- **Cold stream:** a List-backed source can be subscribed to multiple times and replays from the start. Do not assume every hot/shared publisher behaves this way.

**What must not be inferred:** a test calling `SkuCatalog.list(...)` directly does not prove an HTTP endpoint returns a JSON array or the right status; verify separately with `WebTestClient` when the contract includes HTTP.

## 6. Interpreting Mono<List<T>>, Flux<T>, and Flux<List<T>> Correctly

This is the key distinction when working with **multi-element data**:

```text
Flux<Sku>:
  onNext(Sku1)
  onNext(Sku2)
  onNext(Sku3)
  onComplete()

Mono<List<Sku>>:
  onNext([Sku1, Sku2, Sku3])
  onComplete()

Flux<List<Sku>> with buffer(2):
  onNext([Sku1, Sku2])
  onNext([Sku3])
  onComplete()
```

| Publisher | How many `onNext` for 3 SKUs? | How to verify |
| --- | ---: | --- |
| `Flux<Sku>` | 3 | `expectNext(sku1,sku2,sku3)` |
| `Mono<List<Sku>>` | 1 | `expectNext(List.of(sku1,sku2,sku3))` |
| `Flux<List<Sku>>` after `buffer(2)` | 2 | `expectNext(List.of(sku1,sku2), List.of(sku3))` |
| `Mono<Long>` after `count()` | 1 | `expectNext(3L)` |

**Different empty cases:**

- `Flux.empty()`: 0 `onNext`, complete.
- `Mono.empty()`: 0 `onNext`, complete.
- `Flux.empty().collectList()`: **1 `onNext` containing an empty List**, complete.
- `Flux.empty().count()`: **1 `onNext` containing `0L`**, complete.
- `Flux.empty().buffer(2)`: produces zero batch `onNext` signals, complete.

When a DTO returns `Mono<PageDto>` with an `items: List<ItemDto>` field, `StepVerifier` sees only **one `PageDto`**. To verify the number of items inside, use `assertNext(page -> assertEquals(n, page.items().size()))`, not `expectNextCount(n)`, which counts **onNext signals** rather than nested collection elements.

## 7. Testing Multiple Elements: Ordered vs Unordered

### 7.1. When Order Is Part of the Contract

An ordered List source, a query with a stable `ORDER BY`, or an API promising sorted results requires order-preserving assertions:

```java
StepVerifier.create(Flux.just("A", "B", "C"))
        .expectNext("A", "B", "C")
        .verifyComplete();
```

Or with many expected values:

```java
StepVerifier.create(Flux.just("A", "B", "C"))
        .expectNextSequence(List.of("A", "B", "C"))
        .verifyComplete();
```

Both are snippets inside a test method importing `Flux`/`StepVerifier`/`List`. If the source emits `B,A,C`, the test must fail when ordering is genuinely a requirement.

With `flatMap` over asynchronous inner publishers, emission order **can vary** due to concurrency/schedulers. If ordering must be preserved, consider `concatMap` or `flatMapSequential` per concurrency goals; then assert the exact sequence. Do not rely on "accidental" ordering observed in a single run.

### 7.2. When Order Is Not Part of the Contract

When data arrives from parallel tasks and business rules only require all elements to be present, compare **multisets/frequencies** or sort a copy of the collection. Do not rush to convert to a `Set`, as a `Set` drops duplicate counts.

Example:

```java
StepVerifier.create(
                Flux.just("B", "A", "A").collectList())
        .assertNext(values -> {
            List<String> sorted = values.stream()
                    .sorted()
                    .toList();
            assertEquals(List.of("A", "A", "B"), sorted);
        })
        .verifyComplete();
```

This test does not depend on initial order, yet still catches a missing or extra `"A"`. Conversely, comparing only `Set.of("A","B")` would hide duplicate bugs.

You can use `recordWith(...).consumeRecordedWith(...)` instead of `collectList()`; it records `onNext` values inside `StepVerifier` and lets you assert on the recorded collection. Do not collect a non-terminating `Flux` into a `List` indefinitely.

### 7.3. When Only the Count Matters

For large finite streams, `expectNextCount` checks the number of events:

```java
StepVerifier.create(Flux.range(1, 1_000))
        .expectNextCount(1_000)
        .verifyComplete();
```

The test verifies there are exactly 1,000 `onNext` signals and completion, **without verifying the numeric values**. If the pipeline could corrupt values while preserving count, add assertions on values/boundaries worth protecting.

## 8. Termination by Completion, Error, or Cancellation

### 8.1. Completion Is Part of the Contract

Writing `expectNextCount(3).verifyComplete()` verifies the source emits three items **and then completes**. If a fourth item arrives or an error is emitted, verification fails. Thus terminal assertions are just as important as values.

### 8.2. Reactive Errors Occur Upon Subscription

Example:

```java
Flux<Integer> stream = Flux.concat(
        Flux.just(1, 2),
        Flux.error(new IllegalStateException("offline")));

StepVerifier.create(stream)
        .expectNext(1, 2)
        .expectErrorMatches(error ->
                error instanceof IllegalStateException
                && "offline".equals(error.getMessage()))
        .verify();
```

This snippet can be placed in a test method importing `Flux` and `StepVerifier`. Replacing `expectErrorMatches(...).verify()` with `verifyComplete()` must fail because the stream terminates with an error.

**Do not use `assertThrows(IllegalStateException.class, () -> methodReturningFlux())` to test `Flux.error`:** `methodReturningFlux()` may return an object normally, while the error only occurs inside the sequence at subscription time. This is the crucial difference between a **synchronous throw** and an **error signal**.

### 8.3. Recovery Changes the Downstream Outcome

`onErrorResume` can turn an error into a fallback value:

```java
Flux<String> recovered = Flux.<String>error(
        new IllegalStateException("offline"))
        .onErrorResume(ex -> Flux.just("cached"));

StepVerifier.create(recovered)
        .expectNext("cached")
        .verifyComplete();
```

Downstream, the new source completes normally; expecting the old error here would fail. If business logic requires 2 retries, test the attempt or subscription count using an external fake/counter rather than inferring retry count from the final value alone.

### 8.4. Infinite or Long-Running Sources Must Have a Stopping Point

`Flux.never()` never completes; `Flux.interval(...)` can run forever. Tests must know when to cancel or set a timeout rather than waiting indefinitely for completion. `thenCancel()` does not prove the source completed on its own; it verifies **the subscriber actively cancelled** at the desired moment.

## 9. Backpressure: Testing Demand Instead of Only Element Counts

Reactive Streams subscribers use `Subscription.request(n)` to allow a source to emit data. With `StepVerifier.create(publisher, 0)`, initially zero elements are requested; then `thenRequest(n)` is used:

```java
StepVerifier.create(Flux.range(1, 5), 0)
        .expectSubscription()
        .thenRequest(2)
        .expectNext(1, 2)
        .thenRequest(3)
        .expectNext(3, 4, 5)
        .verifyComplete();
```

Expectation: after the first request, 1 and 2 arrive; after the second request, 3, 4, 5 arrive and then complete. `Flux.range` is a synchronous source honoring demand, so the example needs no scheduler or network.

**Do not confuse demand with pagination:** backpressure controls event count within a single subscription; HTTP/DB pagination is a different contract about page/cursor/limit. A `thenRequest(2)` test does not prove an API supports `?page=2`.

Testing complex demand on external sources requires preserving the operators and source being proven: if you swap `Flux.just(...)` in place of an HTTP streaming adapter, the result only speaks to the test `Flux`, not whether the production adapter honors backpressure.

## 10. Virtual Time: Testing Delays and Intervals Without Real Sleeping

Some pipelines depend on `delayElements`, `Flux.interval`, `Mono.delay`, retry backoff, or timeouts. If tests use `Thread.sleep`, results depend on schedulers and CI load, becoming both slow and flaky. Reactor Test provides `StepVerifier.withVirtualTime(...)` to drive virtual time when schedulers are compatible.

Example of **two ticks separated by one virtual hour**:

```java
@Test
void intervalWithVirtualTime() {
    StepVerifier.withVirtualTime(
                    () -> Flux.interval(Duration.ofHours(1))
                            .take(2))
            .expectSubscription()
            .expectNoEvent(Duration.ofHours(1))
            .expectNext(0L)
            .thenAwait(Duration.ofHours(1))
            .expectNext(1L)
            .verifyComplete();
}
```

**Meaning:** `Flux.interval(Duration.ofHours(1))` emits `0L` after the first tick and `1L` after the second tick. `take(2)` causes the sequence to complete after two items. This test does not actually wait two real hours; it drives a **virtual clock**.

Points to get right:

1. **Create the Publisher inside the supplier** `() -> Flux.interval(...).take(2)`; do not create `Flux.interval` beforehand and capture an object already bound to a real scheduler in the lambda.
2. `expectNoEvent(duration)` treats subscription as an event, so place `expectSubscription()` before expecting an event-free duration.
3. Virtual time only controls operators/schedulers compatible with `VirtualTimeScheduler`. Real I/O, custom-created schedulers, or blocking code do not automatically become virtual time. Complex pipelines can starve if time is not advanced in the right order.
4. When timers are not a business rule, do not add artificial delays just to test schedulers. Prefer simple, deterministic tests.

## 11. Runnable Advanced Test Suite: Recording, Virtual Time, Demand

Create `src/test/java/example/testing/webflux/StepVerifierAdvancedTest.java`:

```java
package example.testing.webflux;

import java.time.Duration;
import java.util.ArrayList;
import java.util.List;

import org.junit.jupiter.api.Test;
import reactor.core.publisher.Flux;
import reactor.test.StepVerifier;

import static org.junit.jupiter.api.Assertions.assertEquals;

class StepVerifierAdvancedTest {

    @Test
    void countsLargeFiniteSequence() {
        StepVerifier.create(Flux.range(1, 1_000))
                .expectNextCount(1_000)
                .verifyComplete();
    }

    @Test
    void recordsRepeatedValuesWithoutLosingDuplicates() {
        StepVerifier.create(Flux.just("B", "A", "A"))
                .recordWith(ArrayList::new)
                .expectNextCount(3)
                .consumeRecordedWith(values -> {
                    List<String> sorted = values.stream()
                            .sorted()
                            .toList();
                    assertEquals(
                            List.of("A", "A", "B"), sorted);
                })
                .verifyComplete();
    }

    @Test
    void intervalWithVirtualTime() {
        StepVerifier.withVirtualTime(
                        () -> Flux.interval(
                                Duration.ofHours(1))
                                .take(2))
                .expectSubscription()
                .expectNoEvent(Duration.ofHours(1))
                .expectNext(0L)
                .thenAwait(Duration.ofHours(1))
                .expectNext(1L)
                .verifyComplete();
    }

    @Test
    void honorsDemandInTwoSteps() {
        StepVerifier.create(Flux.range(1, 5), 0)
                .expectSubscription()
                .thenRequest(2)
                .expectNext(1, 2)
                .thenRequest(3)
                .expectNext(3, 4, 5)
                .verifyComplete();
    }

    @Test
    void cancelsWithoutDrainingLargeSource() {
        StepVerifier.create(
                        Flux.range(1, 1_000_000), 0)
                .expectSubscription()
                .thenRequest(2)
                .expectNext(1, 2)
                .thenCancel()
                .verify();
    }
}
```

The class above has **5 test methods**. In total, both JUnit classes in the example contain **18 test methods** (13 in `SkuCatalogTest` and 5 in `StepVerifierAdvancedTest`). Each test is independent and requires no Spring context or HTTP request.

Read carefully:

- `countsLargeFiniteSequence` checks a count of 1,000 and completion, not individual numeric values.
- `recordsRepeatedValuesWithoutLosingDuplicates` uses `recordWith(ArrayList::new)` and checks a sorted copy, catching missing or extra duplicate values.
- `intervalWithVirtualTime` avoids `Thread.sleep` and ensures the builder creates the publisher inside the supplier.
- The demand test uses `initialRequest=0`, then grants demand in two turns.
- The cancellation test consumes two items and cancels, **without requiring one million events to be emitted**. It does not automatically prove external resource cleanup; if a real source holds a DB cursor/socket, write dedicated resource-lifecycle tests.

### Running Both Classes with Gradle

From the project root containing the Gradle wrapper:

```bash
./gradlew test --tests example.testing.webflux.SkuCatalogTest
./gradlew test --tests example.testing.webflux.StepVerifierAdvancedTest
```

On Windows PowerShell:

```powershell
.\gradlew.bat test --tests "example.testing.webflux.SkuCatalogTest"
.\gradlew.bat test --tests "example.testing.webflux.StepVerifierAdvancedTest"
```

**Expected:** all 18 methods pass when the source files match the code above, with Java 17+ and compatible Reactor/JUnit dependencies. Gradle/JUnit logging varies by build, so do not attach a fixed stdout string to the test command. For tests inside a subproject, target that subproject's test task.

## 12. Cold and Hot Publishers: Do Not Assume One Behavior for All Sources

In `SkuCatalog`, `Flux.fromIterable(source)` over an immutable `List` is a **cold publisher**: every subscription receives the data sequence from the beginning. That is why `coldFluxCanBeSubscribedTwice` runs two `StepVerifier`s on the same `Flux` instance and both receive all three SKUs.

However, a **hot** publisher (such as a multicast sink or real-time event stream) may emit events **before a new consumer subscribes**; late subscribers may miss those events. Hot publisher tests must:

- Create a fresh source per test, avoiding shared sinks across test methods.
- Ensure subscription happens **before** events are emitted if the contract requires the subscriber to receive them.
- Use `StepVerifier.then(...)` to emit events after subscription, rather than pushing events before creating the subscriber.
- Clearly establish whether the hot publisher replays/caches or only multicasts new events.
- Avoid `expectNext("A","B","C")` if data can arrive before the verifier subscribes without a replay mechanism.

For some cold publishers, re-subscribing can **re-trigger side effects** (API calls, logging, query execution). Tests should therefore not subscribe multiple times just to "peek" at data when the real source has external side effects. If subscription count is a business requirement, use an appropriate fake/counter to assert it accurately.

## 13. When to Use StepVerifier vs When to Use WebTestClient?

**`StepVerifier` verifies a `Publisher` contract**, whereas **`WebTestClient` verifies a Spring WebFlux HTTP exchange**.

| Question | Usually Appropriate Tool |
| --- | --- |
| Does `Mono<Sku>` emit one item or complete empty? | `StepVerifier` |
| Does `Flux<Sku>` emit in exact order with all elements? | `StepVerifier` |
| How many events do `collectList()/buffer()/count()` emit? | `StepVerifier` |
| Does the pipeline emit an error or recover via `onErrorResume`? | `StepVerifier` |
| Testing delays, virtual time, request demand? | `StepVerifier` |
| Does `GET /skus` return the right HTTP status and JSON array? | `WebTestClient` |
| Are WebFlux controller binding, validation, exception handler correct? | `@WebFluxTest` + `WebTestClient` |
| Do controller-service-repository collaborate for real? | Integration test with appropriate real context/infrastructure |

Example **illustrating HTTP only**, assuming the application already has a `GET /skus?prefix=JAVA` controller returning a JSON array and an injected `webTestClient`:

```java
webTestClient.get()
        .uri("/skus?prefix=JAVA")
        .exchange()
        .expectStatus().isOk()
        .expectBody()
        .jsonPath("$[0].code").isEqualTo("JAVA-1");
```

This snippet **is not a standalone runnable class**: it requires a controller/router function, `WebTestClient`, the right endpoint, and WebFlux serialization. It verifies the HTTP body and **does not replace** `StepVerifier` when you need to control service-level demand or terminal events.

`@WebFluxTest` can load a **slice** containing only WebFlux infrastructure and controllers; services outside the slice can be supplied via a mock bean appropriate for your Spring Test version. Web slice tests do not prove the database was written if repositories/services are mocked. For real HTTP streaming, media types (JSON array, NDJSON, SSE), encoders, backpressure, and network connections are separate boundaries; if network behavior needs verification, use an integration test with an appropriate server/client.

Do not use `@SpringBootTest` for every `map/filter/collectList` operation. A pure Reactor unit test runs faster and pinpoints failure causes more clearly; a context is only needed when genuinely verifying Spring bean wiring/proxies/web infrastructure or adapters.

## 14. Timeouts, Cancellation, and Preventing Hanging Tests

For publishers lacking a terminal signal or genuinely asynchronous streams, use the verifier timeout:

```java
StepVerifier.create(Flux.just(1, 2, 3))
        .expectNext(1, 2, 3)
        .expectComplete()
        .verify(Duration.ofSeconds(3));
```

This example sets a **real-time limit on the test**, not a business rule that "the `Flux` must finish in 3 seconds". Do not set timeouts tightly near average CI execution time when pipelines use thread schedulers or real I/O; tests become flaky. To test a defined delay/backoff, use virtual time as in Section 10.

For infinite streams, choose deliberately: `take(n)` when business logic genuinely wants the first `n` items, or `thenCancel()` when verifying subscription cancellation. If a publisher manages resources (files, DB cursors, network streams), add assertions proving cleanup/resource release callbacks run after cancellation; `thenCancel()` alone does not prove that.

Avoid `block()` on reactive processing threads: it can violate the non-blocking model and cause errors or slowdowns. In Reactor tests, `StepVerifier` generally gives more complete evidence than `block()` because it preserves `onNext`/`onComplete`/`onError` events.

## 15. Common Mistakes

**1. Comparing `Mono`/`Flux` as result objects.** Use `StepVerifier` to subscribe and verify signals instead of `assertEquals(publisherA,publisherB)`.

**2. Forgetting `verify()` or `verifyComplete()`.** Without the verify step, the script is never executed.

**3. Using `expectNext(a,b,c)` for `Mono<List<T>>`.** The publisher emits a single `List`; assert one `List` rather than three `T`s.

**4. Confusing `Flux.empty().collectList()` with `Mono.empty()`.** `collectList` emits one empty list and then completes.

**5. Using `expectNextCount(n)` to conclude content is correct.** Count does not inspect values; add `expectNext`/`assertNext`/recording.

**6. Assuming `Flux` always emits multiple items.** A `Flux` can emit 0, 1, many, or infinite items; base tests on the concrete contract.

**7. Forgetting to assert order or asserting wrong order.** Async `flatMap` can reorder. If order matters, use the right operator/expectation; if it does not, compare multisets preserving duplicates.

**8. Using a `Set` to compare results that may contain duplicates.** A `Set` loses occurrence counts; pick a sorted list or frequency map.

**9. Wrapping `Mono.error` in `assertThrows`.** Errors emit upon subscription. `expectErrorMatches(...).verify()` checks the signal properly.

**10. Expecting `verifyComplete` when a publisher terminates with an error.** `onError` and `onComplete` are distinct terminal outcomes.

**11. Expecting the old error after `onErrorResume`.** Downstream receives the fallback + completion; test at the right point in the pipeline.

**12. Using `Thread.sleep` to test `interval/delay`.** Tests become slow and scheduler-sensitive; use virtual time when compatible.

**13. Creating a scheduler-bound publisher outside the `withVirtualTime` lambda.** The scheduler may already be chosen before switching to the virtual clock; construct it inside the supplier.

**14. Testing `Flux.never` and waiting for completion.** There is no terminal event; use explicit cancel/timeout.

**15. Failing to control subscription timing on hot publishers.** Events may fire before the subscriber attaches and be missed; tests must coordinate subscription/emission order.

**16. Using a service `StepVerifier` test to claim HTTP responses are right.** Status, JSON, SSE, and security filters require `WebTestClient`/integration tests at the right boundary.

**17. Overusing `@SpringBootTest` for pure logic.** No context is needed to test `Flux.map/filter` with `StepVerifier`; starting external infrastructure only adds complexity.

**18. Calling `block()` to "resolve" all data and then asserting a `List`.** This can hide terminal-signal behavior, block threads, or hang on non-completing sources; prefer `StepVerifier` or bounded collection.

## 16. Checklist When Reviewing Mono/Flux Tests

Before writing:

- Does the method return `Mono<T>`, `Flux<T>`, `Mono<List<T>>`, or `Flux<List<T>>`?
- Can it emit **0, 1, many elements**, or an infinite stream? What is the terminal event per contract?
- Is missing data `empty` or `onError`? Does the error class/message need checking?
- Is ordering part of the contract? If not, does the comparison preserve duplicates?

While writing:

- `expectNext` verifies exact values/order; `expectNextCount` only counts.
- `assertNext` performs meaningful assertions on the record/DTO rather than accepting and ignoring it.
- For `collectList()/count()/buffer()`, have **onNext counts** and **nested element counts** been distinguished?
- Are completion or error checked **and `verify` called**?
- Are empty cases, boundary data, errors, and recovery tested when needed?

For asynchronous behavior:

- If time operators exist, is virtual time used with the publisher created inside the supplier?
- If testing demand, are initial request / `thenRequest` used properly?
- Can the source fail to terminate? Are cancel/timeout in place?
- Are hot streams created fresh and subscription/emission coordinated per test?
- Is there resource cleanup and no unexpected blocking on reactive threads?

With Spring Boot:

- Does this test prove a **publisher signal contract** or an **HTTP response**?
- If WebFlux routing/JSON/validation are needed, is `WebTestClient`/an appropriate test slice used?
- If real transactions/DB/HTTP clients are needed, is there an integration test with matching infrastructure?
- Is the service/pipeline under test kept real, mocking only collaborators outside the boundary?

**Remember:** `StepVerifier` lets you verify the **exact count, order, content, completion/error, and demand** of a `Mono`/`Flux`. For `Flux<T>`, `Mono<List<T>>`, and `Flux<List<T>>`, always distinguish **the number of `onNext` events from the number of elements inside the data**. Use virtual time for time operators; use `WebTestClient` when the target is HTTP. Picking the right tool and observation boundary keeps WebFlux tests reliable, fast, and easy to maintain as code evolves.

## 17. References

- [Project Reactor — Testing](https://projectreactor.io/docs/core/release/reference/testing.html): overview of `StepVerifier`, virtual time, backpressure, and test publishers.
- [Reactor Test — StepVerifier API](https://projectreactor.io/docs/test/release/api/reactor/test/StepVerifier.html): `create`, `withVirtualTime`, and `verify`.
- [Reactor Test — StepVerifier.Step API](https://projectreactor.io/docs/test/release/api/reactor/test/StepVerifier.Step.html): `expectNextSequence`, `expectNextCount`, `recordWith`, and `consumeRecordedWith`.
- [Spring Boot — Testing WebFlux Applications](https://docs.spring.io/spring-boot/reference/testing/spring-boot-applications.html): WebFlux test slice and `WebTestClient`.

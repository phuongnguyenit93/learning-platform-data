# transform and transformDeferred for Reusing Processing Chains in Project Reactor

## 1. Context and Goals

In Spring WebFlux, many `Flux` or `Mono` pipelines share a common processing chain: normalizing data, filtering, mapping, validating, enriching, and logging. Repeating the same `map`/`filter`/`flatMap` calls everywhere makes maintenance and testing harder.

Project Reactor has two operators that **take a function transforming an entire pipeline**:

- `transform(transformer)`: applies the function once at **pipeline assembly time**.
- `transformDeferred(transformer)`: applies the function **each time there is a subscription** to the resulting publisher.

This lesson explains both lifecycles accurately, how to extract shared chains, managing per-Subscriber state, common misconceptions, a runnable Java 17+ example, and how to apply them in Spring WebFlux code.

## 2. Distinguishing Assembly, Subscription, and Data

A sample pipeline:

~~~java
Flux<Integer> pipeline = Flux.range(1, 4)
        .filter(n -> n % 2 == 0)
        .map(n -> n * 10);

pipeline.subscribe(System.out::println);
~~~

Stdout from synchronous `Flux.range`:

~~~text
20
40
~~~

**Assembly** is when the program executes the chain of `Flux.range`, `filter`, and `map` calls and builds the resulting Publisher object. Most cold sources emit no data in this phase. **Subscription** begins when a Subscriber connects, establishes `onSubscribe`, and triggers data or asynchronous sources. **Element processing** is when elements actually pass through the `filter` and `map` lambdas, typically after subscribing.

Do not equate **the pipeline-assembling function** passed to `transform` with the **per-value lambda** passed to `map`. The first takes a Flux and returns a Publisher; the latter takes each `T` and returns `R`. Cold/hot semantics, request/backpressure, and signal ordering still follow the source Publisher and the composed operators.

## 3. transform: Packaging Transformations at Assembly

Conceptual signature for Flux:

~~~java
<V> Flux<V> transform(
        Function<? super Flux<T>, ? extends Publisher<V>> transformer)
~~~

`transformer` is a `Function` receiving the entire current Flux and returning a Publisher (usually adding a chain of operators). Reactor **invokes this function immediately where `transform` is being assembled**, creating the resulting Flux. If that same resulting Flux is later subscribed to multiple times, the transformer **is not invoked again** simply because another Subscriber attached.

Example transforming text tags:

~~~java
import java.util.function.Function;
import reactor.core.publisher.Flux;

Function<Flux<String>, Flux<String>> cleanTags = input ->
        input.map(String::trim)
             .filter(s -> !s.isBlank())
             .map(String::toUpperCase);

Flux<String> tags = Flux.just(" java ", " ", "reactor ")
        .transform(cleanTags);

tags.subscribe(System.out::println);
~~~

Output:

~~~text
JAVA
REACTOR
~~~

To reuse it:

~~~java
// requestTags and cachedTags are two existing Flux<String> in the application.
Flux<String> a = requestTags.transform(cleanTags);
Flux<String> b = cachedTags.transform(cleanTags);
~~~

This is an **illustrative snippet depending on application data**, not a standalone program. `cleanTags` is applied once when building `a` and once when building `b`. Each time `a` or `b` is subscribed to, the `map`/`filter` operators inside still process the actual elements of each subscription.

You can write a reusable method to avoid creating a `Function` object everywhere:

~~~java
static Flux<String> normalize(Flux<String> input) {
    return input.map(String::trim)
                .filter(s -> !s.isBlank())
                .map(String::toLowerCase);
}

// Used inside the class containing the normalize method:
Flux<String> normalized = inputFlux.transform(MyTransforms::normalize);
~~~

The name `MyTransforms` here stands for a utility class holding the method; this is only an API-level example. In production code, name utilities accurately by business domain, and prefer pure functions without mutable state when unnecessary.

### transform Does Not Run map Before Subscribing

~~~java
AtomicInteger assemblies = new AtomicInteger();
Flux<Integer> processed = Flux.just(1, 2)
        .transform(source -> {
            assemblies.incrementAndGet();
            return source.map(n -> n * 2);
        });

System.out.println(assemblies.get()); // 1
~~~

The transformer increments the counter when `processed` is created. However, the `n * 2` multiplication inside `map` has not run yet. Only when a Subscriber attaches do elements flow through `map`. These are two distinct execution layers.

## 4. transformDeferred: Applying Transformations Per Subscription

Conceptual signature:

~~~java
<V> Flux<V> transformDeferred(
        Function<? super Flux<T>, ? extends Publisher<V>> transformer)
~~~

`transformDeferred` still accepts a function transforming the whole Flux, yet **defers applying the transformer until subscription**. If a resulting Flux has two Subscribers, the transformer is invoked twice, allowing each Subscriber to receive a transformation chain rebuilt for that subscription's context.

~~~text
transform:
assembly           source ── transformer() ──► assembled pipeline
subscribe #1                               └─► data for S1
subscribe #2                               └─► data for S2

transformDeferred:
assembly           source ── defer transformer
subscribe #1               ── transformer() ──► pipeline #1 ──► S1
subscribe #2               ── transformer() ──► pipeline #2 ──► S2
~~~

Important point: “each subscription” means each connection to **that exact output Publisher** at that position. Operators such as `retry`, `repeat`, or upstream reconnections can affect how many times each segment is subscribed; do not mechanically equate one HTTP request = one subscription in every topology.

### When You Need Isolated State Per Subscriber

Suppose elements must be numbered within **each subscription**:

~~~java
Function<Flux<String>, Flux<String>> withIndex = input -> {
    AtomicInteger sequence = new AtomicInteger();
    return input.map(value ->
            sequence.incrementAndGet() + ": " + value);
};

Flux<String> numbered = Flux.just("A", "B")
        .transformDeferred(withIndex);
~~~

When `numbered` is subscribed to twice, each subscription creates a new `AtomicInteger`, so both receive `1: A`, `2: B`. If `transform(withIndex)` were used, the `sequence` object would be created once at assembly and captured by `map`'s closure; the second subscription could continue with `3: A`, `4: B`.

**Do not confuse this with built-in operator state.** For example, Reactor's `distinct()` manages its seen-elements set per subscription; placing `distinct()` inside `transform` does not cause Subscribers to share the seen set. Issues usually come from mutable state captured in lambdas by the application author.

### transformDeferred Does Not Automatically Isolate External Variables

~~~java
AtomicInteger shared = new AtomicInteger();

Function<Flux<String>, Flux<String>> lambda =
        flux -> flux.map(value ->
                shared.incrementAndGet() + ": " + value);

Flux<String> stream = Flux.just("A", "B")
        .transformDeferred(lambda);
~~~

`shared` lives **outside** the transformer, so it remains one shared object across all invocations. `transformDeferred` does not clone closures, service fields, static variables, or external resources. If per-subscription state is needed, allocate the state inside the transformer body; if sharing is intentional, design for concurrent access safety.

## 5. Complete Java 17+ Example: Observable Difference

This example uses synchronous `Flux.just` so output is deterministic and independent of timing or threads. Each transformer call creates a `generation` and a `position`. With `transform`, state created at assembly is shared across multiple subscriptions. With `transformDeferred`, state is recreated.

Directory layout:

~~~text
reactor-transform-demo/
├── build.gradle
└── src/main/java/TransformDemo.java
~~~

Contents of `build.gradle` for Gradle with Java toolchain (Reactor Core 3.8.8):

~~~groovy
plugins {
    id 'application'
}

repositories {
    mavenCentral()
}

dependencies {
    implementation 'io.projectreactor:reactor-core:3.8.8'
}

java {
    toolchain {
        languageVersion = JavaLanguageVersion.of(17)
    }
}

application {
    mainClass = 'TransformDemo'
}
~~~

Contents of `src/main/java/TransformDemo.java`:

~~~java
import java.util.concurrent.atomic.AtomicInteger;
import java.util.function.Function;

import reactor.core.publisher.Flux;

public class TransformDemo {
    public static void main(String[] args) {
        AtomicInteger applied = new AtomicInteger();

        Function<Flux<Integer>, Flux<String>> annotate = flux -> {
            int generation = applied.incrementAndGet();
            AtomicInteger position = new AtomicInteger();

            return flux.map(value -> generation + "/"
                    + position.incrementAndGet() + "=" + value);
        };

        Flux<String> immediate = Flux.just(3, 4).transform(annotate);
        Flux<String> deferred = Flux.just(3, 4).transformDeferred(annotate);

        System.out.println("after assembly: " + applied.get());

        immediate.collectList().subscribe(values ->
                System.out.println("transform S1: " + values));
        immediate.collectList().subscribe(values ->
                System.out.println("transform S2: " + values));

        deferred.collectList().subscribe(values ->
                System.out.println("deferred S1: " + values));
        deferred.collectList().subscribe(values ->
                System.out.println("deferred S2: " + values));

        System.out.println("after subscriptions: " + applied.get());
    }
}
~~~

From the `reactor-transform-demo` directory, run:

~~~bash
gradle -q run
~~~

If a Gradle wrapper is present, use `./gradlew -q run` on Linux/macOS or `gradlew.bat -q run` on Windows. Stdout emitted **by the program**:

~~~text
after assembly: 1
transform S1: [1/1=3, 1/2=4]
transform S2: [1/3=3, 1/4=4]
deferred S1: [2/1=3, 2/2=4]
deferred S2: [3/1=3, 3/2=4]
after subscriptions: 3
~~~

Analysis:

1. When declaring `immediate`, Reactor invokes `annotate` once, incrementing `applied` to 1 and creating a `position` used by that Flux. Declaring `deferred` has not invoked the transformer yet.
2. `transform S1` receives `generation = 1` and indices 1, 2. `transform S2` reuses the assembled pipeline's closure, so indices continue to 3, 4.
3. `deferred S1` now applies the transformer: `generation = 2`, with another `position` counting 1, 2.
4. `deferred S2` applies the transformer again: `generation = 3` and counts 1, 2 separately.
5. Total calls to `annotate` is 3: once at assembly, twice at subscription.

`collectList()` prints one list per subscription in the example. If `Flux.just` is replaced with an asynchronous source, log ordering across independent subscriptions is not guaranteed; what must be verified is the transformer invocation count and state semantics.

## 6. Comparison Table for Selection

| Criterion | `transform` | `transformDeferred` |
| --- | --- | --- |
| When transformer is applied | Assembly | Each subscription |
| Pipeline subscribed N times | Transformer at that spot ran once | Transformer runs N times |
| Can transformer choose a new structure per Subscriber? | Does not rerun automatically | Can choose freshly per invocation |
| Mutable state created **inside** transformer | Risk of sharing across multiple subscriptions | Can be allocated separately per subscription |
| External state captured by closure | Can be shared | Still shared |
| Pure chains like `filter` + `map` | Usually the simpler choice | Also works, usually unnecessary |
| Automatically switches scheduler/thread? | No | No |
| Automatically turns a hot publisher into cold? | No | No |

Choose `transform` when you want to **reuse a fixed rule** and do not need to rebuild the pipeline per Subscriber. Choose `transformDeferred` when the transformer genuinely needs to **allocate fresh state or make different decisions per subscription**. Do not pick deferred just because “Reactor is lazy”: the per-element lambdas of standard operators already run only when data flows through.

## 7. Applying in Spring WebFlux

### Reusing Service Rules

The following is a class in a WebFlux application, not a standalone program:

~~~java
import java.util.function.Function;
import reactor.core.publisher.Flux;

public final class TagService {
    private static final Function<Flux<String>, Flux<String>> CLEAN_TAGS =
            input -> input.map(String::trim)
                          .filter(s -> !s.isBlank())
                          .map(String::toLowerCase)
                          .distinct();

    public Flux<String> clean(Flux<String> values) {
        return values.transform(CLEAN_TAGS);
    }
}
~~~

You can pass a `Flux<String>` from an HTTP body, messaging, or a repository through this service. The processing logic is kept in one place. `distinct` in the example manages deduplication **per subscription**, so tags from one Subscriber never filter out tags for another Subscriber.

### Numbering Per Subscription

~~~java
import java.util.concurrent.atomic.AtomicInteger;
import reactor.core.publisher.Flux;

// Placed inside a WebFlux service.
public Flux<String> numbered(Flux<String> input) {
    return input.transformDeferred(source -> {
        AtomicInteger index = new AtomicInteger();
        return source.map(value -> index.incrementAndGet() + ": " + value);
    });
}
~~~

Do not place `AtomicInteger` as a field on a Spring singleton service if you expect each execution to have its own index. `transformDeferred` enables per-**subscription** state, which is the guaranteed scope.

In a WebFlux controller, return `Flux`/`Mono` instead of calling `subscribe()` or `block()` yourself so Spring coordinates subscription, cancellation, backpressure, and errors. If a transformer contains blocking queries, switch to an appropriate non-blocking API or wrap the blocking source on a suitable scheduler; `transformDeferred` does not avoid blocking on its own.

## 8. Using with Mono and Context

### Mono Also Supports Both Operators

~~~java
import reactor.core.publisher.Mono;

Mono<String> a = Mono.just("  Spring ")
        .transform(m -> m.map(String::trim).map(String::toUpperCase));

Mono<String> b = Mono.just("  Spring ")
        .transformDeferred(m -> m.map(String::trim).map(String::toUpperCase));
~~~

Upon subscription, both emit `"SPRING"` and complete. With pure lambdas like above, `transform` already satisfies reuse needs; `transformDeferred` is meaningful when the function needs to allocate state or choose a processing branch per subscriber. `Mono.empty()` still completes without triggering `map` if the transformer adds no fallback.

### Context Per Subscriber: transformDeferredContextual

If you want to build processing based on the Subscriber's Reactor `ContextView`, use the dedicated variant `transformDeferredContextual`:

~~~java
import reactor.core.publisher.Flux;
import reactor.util.context.Context;

Flux<String> tagged = Flux.just("a", "b")
        .transformDeferredContextual((source, ctx) -> {
            String tenant = ctx.getOrDefault("tenant", "public");
            return source.map(v -> tenant + ":" + v);
        });

tagged.contextWrite(Context.of("tenant", "teamA"))
      .subscribe(System.out::println);
~~~

With a synchronous source, stdout:

~~~text
teamA:a
teamA:b
~~~

`Context` is metadata attached to a subscription in Reactor's model, helping propagate request/correlation IDs without relying on thread-locals. Do not assume regular `transformDeferred` provides `ContextView` on its own; use `transformDeferredContextual` or an operator designed to read Context.

## 9. Distinguishing from Related APIs

- `map(fn)`: receives **one element** to turn into another element; invoked on `onNext`.
- `flatMap(fn)`: receives **one element** and creates a related async source; with `Flux.flatMap`, inner publishers can interleave.
- `transform(fn)`: receives **the entire Flux/Mono** and attaches an operator segment once at assembly.
- `transformDeferred(fn)`: receives **the entire Flux/Mono** and attaches that segment whenever each Subscriber subscribes.
- `Flux.defer(supplier)` / `Mono.defer(supplier)`: defers **creating a source Publisher** until each subscription; has no existing Flux parameter onto which to append a transformer segment.
- `as(fn)`: allows converting the entire Flux/Mono into **another return type** (not necessarily a Publisher), so it does not directly replace the two operators above.
- `transformDeferredContextual`: variant enabling the transformer to read `ContextView`.

A reusable function of the form `f -> f.filter(...).map(...)` is not `flatMap` because it operates on the Publisher, not per element. `transformDeferred` also does not turn a cold source into hot, nor does it automatically execute on a separate thread.

## 10. Testing with StepVerifier

In a project with `reactor-test` and JUnit 5 in test scope, you can verify when the transformer is applied. For example, with simple Gradle, add:

~~~groovy
dependencies {
    testImplementation 'io.projectreactor:reactor-test:3.8.8'
    testImplementation 'org.junit.jupiter:junit-jupiter:5.11.4'
}

tasks.named('test') {
    useJUnitPlatform()
}
~~~

File `src/test/java/TransformTest.java`:

~~~java
import static org.junit.jupiter.api.Assertions.assertEquals;

import java.util.concurrent.atomic.AtomicInteger;
import java.util.function.Function;

import org.junit.jupiter.api.Test;
import reactor.core.publisher.Flux;
import reactor.test.StepVerifier;

class TransformTest {
    @Test
    void immediateAppliedAtAssembly() {
        AtomicInteger calls = new AtomicInteger();
        Function<Flux<Integer>, Flux<Integer>> f = source -> {
            int increment = calls.incrementAndGet();
            return source.map(n -> n + increment);
        };

        Flux<Integer> data = Flux.just(10).transform(f);
        assertEquals(1, calls.get());

        StepVerifier.create(data).expectNext(11).verifyComplete();
        StepVerifier.create(data).expectNext(11).verifyComplete();
        assertEquals(1, calls.get());
    }

    @Test
    void deferredAppliedForEachSubscription() {
        AtomicInteger calls = new AtomicInteger();
        Function<Flux<Integer>, Flux<Integer>> f = source -> {
            int increment = calls.incrementAndGet();
            return source.map(n -> n + increment);
        };

        Flux<Integer> data = Flux.just(10).transformDeferred(f);
        assertEquals(0, calls.get());

        StepVerifier.create(data).expectNext(11).verifyComplete();
        StepVerifier.create(data).expectNext(12).verifyComplete();
        assertEquals(2, calls.get());
    }
}
~~~

Two independent tests demonstrate: `transform` invokes the transformer once before subscription and the closure value is fixed; `transformDeferred` does not invoke the transformer at assembly, incrementing the counter as each of the two Subscribers attaches. That tests the contract accurately. Multi-threaded projects should also add concurrency and cancellation scenarios, avoiding reliance on interleaved logs across subscribers.

## 11. Common Mistakes and Fixes

| Mistake | Consequence | How to avoid |
| --- | --- | --- |
| Assuming `transform` runs once per `onNext` | Wrong function lifecycle. | Transformer runs at assembly; `map` inside runs per element. |
| Creating a counter inside a `transform` transformer and expecting per-Subscriber reset | Closure captures state created once. | Use `transformDeferred` if a fresh counter is needed. |
| Using `transformDeferred` yet storing state in an outer variable / singleton field | State is still shared. | Allocate inside the transformer, or deliberately manage shared state. |
| Assuming every stateful operator inside `transform` shares state | Misunderstands Reactor operator state. | Distinguish per-subscription Reactor-managed state from application mutable closures. |
| Using `transformDeferred` for pure chains needing no extra condition | No clear benefit; repeats transformer invocation unnecessarily. | Prefer `transform` for fixed chains. |
| Calling blocking I/O directly inside the transformer | Can block threads at assembly or subscription time. | Design non-blocking sources or wrap blocking work on an appropriate scheduler. |
| Mistaking `transformDeferred` for creating a scheduler | Still runs on threads chosen by source/operators. | Use `subscribeOn` / `publishOn` per actual needs. |
| Using `transformDeferred` thinking a hot source turns cold | Upstream nature does not change on its own. | Inspect the source, cache/share/publish, and subscription lifecycle carefully. |
| Using `flatMap` to attach a shared transformation segment | `flatMap` applies per element. | Use `transform` / `transformDeferred` to compose whole pipelines. |
| Calling `block()` in a WebFlux handler to observe the pipeline | Blocks the event loop and loses reactive benefits. | Return the Publisher, use StepVerifier in tests and observation hooks when needed. |

When diagnosing, use `.log("before")`/`.log("after")` or `doOnSubscribe` to observe runtime signals. To know how many times the transformer was applied, place a counter/log directly **inside the transformer function**, because `onNext` logs only show elements passing through, not when assembly occurred.

## 12. Self-Check Questions

1. A Flux uses `transform(f)` and is subscribed to three times; how many times is `f` applied at that position? **Once at assembly.**
2. With `transformDeferred(f)` and three subscriptions, how many times is `f` called? **Three times.**
3. Does `transformDeferred` automatically run on another thread or create a hot publisher? **No.**
4. Does placing `AtomicInteger` **outside** the transformer automatically make it per-subscription state with `transformDeferred`? **No; the closure still shares the reference.**
5. Why does `distinct()` inside `transform` usually not mix seen data between two Subscribers? **Because that standard operator's state belongs to each subscription.**
6. What should be used to read request metadata from Reactor Context when building a per-subscription chain? **`transformDeferredContextual`.**
7. What should be chosen for pure name-normalization logic that needs no per-Subscriber state? **Usually `transform`.**

**Key takeaway:** `transform` applies the **pipeline-composing function** at assembly to reuse fixed logic. `transformDeferred` applies that function **per subscription** so distinct chains and state can be created. Always distinguish Reactor-managed state from mutable closure state and understand the scope of subscriptions.

## References

- [Project Reactor — Mutualizing Operator Usage: transform and transformDeferred](https://projectreactor.io/docs/core/release/reference/advancedFeatures/advanced-mutualizing-operator-usage.html).
- [Project Reactor — Flux Javadoc (transform, transformDeferred, transformDeferredContextual)](https://projectreactor.io/docs/core/release/api/reactor/core/publisher/Flux.html).
- [Project Reactor — Mono Javadoc](https://projectreactor.io/docs/core/release/api/reactor/core/publisher/Mono.html).
- [Project Reactor — Testing with StepVerifier](https://projectreactor.io/docs/core/release/reference/testing.html).
- [Spring Framework — WebFlux](https://docs.spring.io/spring-framework/reference/web/webflux.html).

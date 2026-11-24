# PublisherProbe to Verify That Fallback Branches Are Subscribed

## 1. The Testing Problem: Correct Output Alone Does Not Prove Which Branch Ran

In a Reactor flow, a program often has multiple execution paths:

- Look up in cache; when empty, query the database.
- Call the primary service; on an eligible error, switch to a fallback source.
- If a command exists, execute the task; otherwise, run default logic.
- Fetch a list from the priority source; when it completes empty, fetch from another source.

Example:

~~~java
Mono<String> result = cacheLookup("A-01")
    .switchIfEmpty(databaseLookup("A-01"));
~~~

If a test only uses:

~~~java
StepVerifier.create(result)
    .expectNext("value")
    .verifyComplete();
~~~

it verifies the final value and completion signal, yet **does not directly prove whether the database fallback was subscribed**. When both branches can return the same value, output-based assertions can miss selecting the wrong branch.

A trickier case is when both primary and fallback return `Mono<Void>`. Neither emits `onNext`, so:

~~~java
StepVerifier.create(resultVoid).verifyComplete();
~~~

cannot distinguish which branch actually ran.

`PublisherProbe` from `reactor-test` is designed to solve this problem. It creates an instrumented Publisher and lets you assert **subscription, request, and cancellation** after `StepVerifier` executes the scenario.

**Focus of "subscribed" in this lesson:** a Publisher was *subscribed to*. This is not synonymous with the Publisher being created, appearing in the code chain, receiving demand, emitting data, or completing business side effects.

## 2. What Is PublisherProbe?

### 2.1. Package and Dependency

`PublisherProbe<T>` belongs to:

~~~java
import reactor.test.publisher.PublisherProbe;
~~~

`StepVerifier` belongs to:

~~~java
import reactor.test.StepVerifier;
~~~

Both live in the **`reactor-test`** dependency, typically declared in test scope:

~~~xml
<dependency>
    <groupId>io.projectreactor</groupId>
    <artifactId>reactor-test</artifactId>
    <scope>test</scope>
</dependency>
~~~

Production code still depends on `reactor-core` for `Mono`, `Flux`, and operators. Never import `PublisherProbe` into production services just for branching.

### 2.2. Factory Methods

| API | Meaning | When to use |
| --- | --- | --- |
| `PublisherProbe.empty()` | Creates a probe whose Publisher completes empty while still recording subscription/request/cancel | Testing `Mono<Void>` branches or empty results |
| `PublisherProbe.of(Publisher<? extends T>)` | Wraps a real Publisher, preserving its signals while observing usage | Testing fallback branches that must emit values, errors, streams, or stay open |
| `probe.mono()` | Gets the probed `Mono<T>` view | Attaching to `Mono.switchIfEmpty`, `Mono.onErrorResume` |
| `probe.flux()` | Gets the probed `Flux<T>` view | Attaching to `Flux.switchIfEmpty` or multi-item branches |

Example:

~~~java
PublisherProbe<String> fallback =
    PublisherProbe.of(Mono.just("from-db"));

Mono<String> result = Mono.<String>empty()
    .switchIfEmpty(fallback.mono());
~~~

With `empty()`:

~~~java
PublisherProbe<Void> cleanup = PublisherProbe.empty();
Mono<Void> flow = Mono.<Void>empty()
    .switchIfEmpty(cleanup.mono());
~~~

In this case, both primary and fallback are empty. Yet the probe still lets us verify which branch was subscribed.

### 2.3. Assertions

| Assertion | Condition verified |
| --- | --- |
| `assertWasSubscribed()` | The probe received at least one subscription |
| `assertWasNotSubscribed()` | The probe was never subscribed to |
| `assertWasRequested()` | At least one data request arrived from downstream |
| `assertWasNotRequested()` | No data requests arrived |
| `assertWasCancelled()` | A subscription through the probe received cancellation |
| `assertWasNotCancelled()` | No cancellation was observed |

The API also provides boolean queries like `wasSubscribed()`, `wasRequested()`, `wasCancelled()`, and in matching versions `subscribeCount()`. However, most unit tests should use the `assertWas...` methods: when wrong, they throw `AssertionError`.

**Very important limitation:** `assertWasRequested()` only confirms that a request occurred; **it does not check the exact count n**. If you need to verify specific demand or Reactive Streams violations, use `StepVerifier` with `TestPublisher` or a dedicated measurement tool.

### 2.4. Probes Do Not Produce Business Results

`PublisherProbe.empty()` emits no data. If business logic must return a fallback value, use `PublisherProbe.of(Mono.just(value))` instead of empty.

`PublisherProbe` also does not guarantee "database committed", "HTTP request reached the server", or "message saved". It verifies **control flow at the reactive Publisher boundary**. Separate integration tests are needed to prove real side effects.

## 3. Combining StepVerifier and PublisherProbe in Order

The standard pattern has three steps:

1. **Arrange:** create the primary source and the probe for the fallback branch.
2. **Act:** use `StepVerifier` to subscribe to the final Publisher and verify values/error/completion/cancellation.
3. **Assert branch:** inspect the probe after `StepVerifier` finishes.

~~~java
PublisherProbe<String> database =
    PublisherProbe.of(Mono.just("db-value"));

Mono<String> output = Mono.<String>empty()
    .switchIfEmpty(database.mono());

StepVerifier.create(output)
    .expectNext("db-value")
    .verifyComplete();

database.assertWasSubscribed();
database.assertWasRequested();
database.assertWasNotCancelled();
~~~

Why must `verifyComplete()` be called before probe assertions? Because Reactor is lazy: merely constructing the `Mono` without subscribing gives the fallback no chance to be selected.

~~~java
PublisherProbe<String> probe =
    PublisherProbe.of(Mono.just("db"));

Mono<String> output = Mono.<String>empty()
    .switchIfEmpty(probe.mono());

// WRONG: no subscriber yet for output.
probe.assertWasSubscribed(); // AssertionError
~~~

One final rule: use a **fresh probe for each test case**. Reusing a probe across tests or multiple subscriptions accumulates observed state, which can make `assertWasSubscribed` pass from an earlier run and hide a bug in the current scenario.

### 3.1. Subscription, Request, and Cancel Are Three Separate States

~~~text
Assembly       Subscribe         Request(n)           Cancel/Complete
    |              |                 |                      |
    v              v                 v                      v
create probe -> probe.mono() -> source subscribed -> demand -> terminal
    |              |                 |                      |
    |              |                 |                      +-- cancellation?
    |              |                 +-- assertWasRequested
    |              +-- assertWasSubscribed
    +-- does not prove the branch was used
~~~

A Publisher can be subscribed to without receiving demand yet (e.g., `StepVerifier` starting with request 0), or subscribed and then cancelled before emitting data. Thus:

- `assertWasSubscribed` answers: **was the branch subscribed to?**
- `assertWasRequested` answers: **did the branch receive `request(n)`?**
- `assertWasCancelled` answers: **was the branch cancelled?**
- `expectNext` and `verifyComplete` answer: **what signals did the subscriber observe?**

Do not use one assertion as a substitute for all of these questions.

## 4. switchIfEmpty: When Is the Fallback Branch Subscribed?

### 4.1. Primary Source Empty: Fallback Must Be Used

~~~java
PublisherProbe<String> fallback =
    PublisherProbe.of(Mono.just("database"));

Mono<String> result = Mono.<String>empty()
    .switchIfEmpty(fallback.mono());

StepVerifier.create(result)
    .expectNext("database")
    .verifyComplete();

fallback.assertWasSubscribed();
fallback.assertWasRequested();
fallback.assertWasNotCancelled();
~~~

`switchIfEmpty` subscribes to the fallback only when upstream **completes without emitting any item**. The Publisher in `switchIfEmpty` must have a compatible type with upstream.

### 4.2. Primary Source Has a Value: Fallback Must Not Be Subscribed

~~~java
PublisherProbe<String> fallback =
    PublisherProbe.of(Mono.just("database"));

Mono<String> result = Mono.just("cache")
    .switchIfEmpty(fallback.mono());

StepVerifier.create(result)
    .expectNext("cache")
    .verifyComplete();

fallback.assertWasNotSubscribed();
fallback.assertWasNotRequested();
fallback.assertWasNotCancelled();
~~~

This negative branch test is critical. Testing only cache misses without testing cache hits can overlook code that accidentally subscribes to the fallback even when cached data is present.

### 4.3. Upstream Filtered to Empty

~~~java
PublisherProbe<String> fallback =
    PublisherProbe.of(Mono.just("database"));

Mono<String> result = Mono.just("stale")
    .filter(value -> value.startsWith("valid-"))
    .switchIfEmpty(fallback.mono());

StepVerifier.create(result)
    .expectNext("database")
    .verifyComplete();

fallback.assertWasSubscribed();
~~~

`filter` discards the item, causing upstream to complete empty. That still triggers the `switchIfEmpty` branch even though the initial source emitted a value before filtering.

### 4.4. Upstream Emits Error: switchIfEmpty Does Not Run

~~~java
PublisherProbe<String> fallback =
    PublisherProbe.of(Mono.just("database"));

Mono<String> result =
    Mono.<String>error(new IllegalStateException("cache unavailable"))
        .switchIfEmpty(fallback.mono());

StepVerifier.create(result)
    .expectErrorMessage("cache unavailable")
    .verify();

fallback.assertWasNotSubscribed();
~~~

`switchIfEmpty` handles **empty completion**, not `onError`. To fall back on errors, use `onErrorResume` with an appropriate predicate/exception type.

### 4.5. defaultIfEmpty Has No Fallback Publisher

~~~java
Mono<String> result = Mono.<String>empty()
    .defaultIfEmpty("default");
~~~

`defaultIfEmpty` emits a substitute value without subscribing to a secondary Publisher. There is no secondary Publisher to wrap with `PublisherProbe`. To test this operator, use `StepVerifier.expectNext("default")`.

### 4.6. Creating a Source Does Not Mean Subscribing to It

A Java expression can call a factory to **create** a fallback Publisher right when assembling the chain:

~~~java
Mono<String> alternate = databaseClient.findById("A-01");
Mono<String> result = cacheLookup("A-01")
    .switchIfEmpty(alternate);
~~~

In well-behaved reactive APIs, `findById` usually returns a cold Publisher and SQL has not executed yet. Still, the factory method creating the Publisher might perform eager work like incrementing a counter, reading a file, or making a synchronous call before returning the `Mono`.

Use `Mono.defer` when you want to **defer even the factory call** until the branch is subscribed:

~~~java
Mono<String> result = cacheLookup("A-01")
    .switchIfEmpty(
        Mono.defer(() -> databaseClient.findById("A-01"))
    );
~~~

`PublisherProbe` observes subscription. It **does not directly verify when the factory was invoked**. To test that the factory is truly lazy, add an `AtomicInteger` or spy/mock on the factory alongside the probe confirming subscription.

## 5. Special Case: Mono<Void> and Empty Fallback Branches

### 5.1. Why Return Values Are Not Enough

Suppose a method processes a command, and if no command exists, runs a fallback action. Both actions return `Mono<Void>` because they only need to complete without returning a value:

~~~java
Mono<Void> doDefaultAction() { ... }
Mono<Void> process(String command) { ... }
~~~

When the test runs:

~~~java
StepVerifier.create(operation)
    .verifyComplete();
~~~

whether `process` or `doDefaultAction` ran, the outcome is simply completion. `PublisherProbe<Void>` solves this by observing the action branch.

### 5.2. Pitfall: flatMap Returning Mono<Void> Followed by switchIfEmpty

Common mistake:

~~~java
public Mono<Void> processOrFallback(
    Mono<String> source,
    Function<String, Mono<Void>> process,
    Mono<Void> fallback
) {
    return source
        .flatMap(process)
        .switchIfEmpty(fallback);
}
~~~

Even when `source` emits a `String` and `process` runs, `flatMap(process)` still becomes `Mono<Void>`, emitting no `onNext`. `switchIfEmpty` sees an empty completion and **always runs the fallback**, even when the command existed.

The fix is to keep a value marker on the handled branch and strip the marker at the end:

~~~java
public Mono<Void> processOrFallback(
    Mono<String> source,
    Function<String, Mono<Void>> process,
    Mono<Void> fallback
) {
    return source
        .flatMap(value -> process.apply(value).thenReturn(Boolean.TRUE))
        .switchIfEmpty(fallback.thenReturn(Boolean.FALSE))
        .then();
}
~~~

`thenReturn(Boolean.TRUE)` emits a marker once `process` finishes, ensuring upstream is no longer empty. The fallback is subscribed only when `source` had no command. The final `then()` converts the internal `Boolean` back to `Mono<Void>` per the business contract.

### 5.3. Testing the Fallback Branch with PublisherProbe.empty()

~~~java
PublisherProbe<Void> fallback = PublisherProbe.empty();

Mono<Void> operation = processOrFallback(
    Mono.empty(),
    command -> Mono.empty(),
    fallback.mono()
);

StepVerifier.create(operation)
    .verifyComplete();

fallback.assertWasSubscribed();
fallback.assertWasRequested();
fallback.assertWasNotCancelled();
~~~

`PublisherProbe.empty()` emits no items yet still records the branch. This is why probes are especially valuable when both branches return `Mono<Void>`.

### 5.4. Testing the Primary Branch and Ensuring Fallback Does Not Run

~~~java
PublisherProbe<Void> fallback = PublisherProbe.empty();

Mono<Void> operation = processOrFallback(
    Mono.just("approve"),
    command -> Mono.empty(),
    fallback.mono()
);

StepVerifier.create(operation)
    .verifyComplete();

fallback.assertWasNotSubscribed();
fallback.assertWasNotRequested();
~~~

If you swap the fixed implementation for the broken one in section 5.2, `assertWasNotSubscribed` will fail—even though `verifyComplete` still passes. Such a test catches **control-flow bugs**, not merely output mismatches.

### 5.5. If the Fallback Must Emit an Error

`PublisherProbe.of(Mono.error(new SomeException()))` can wrap a failing fallback. While `StepVerifier` asserts the error, the probe still confirms that branch was subscribed.

Use `empty()` only when an empty/void fallback matches the contract. Never replace a data-returning fallback with empty and accidentally change the behavior of the method under test.

## 6. onErrorResume and Other Operators

### 6.1. Recovering from Errors

`onErrorResume` selects a fallback when the source emits a matching error:

~~~java
PublisherProbe<String> backup =
    PublisherProbe.of(Mono.just("backup-ok"));

Mono<String> result =
    Mono.<String>error(new IllegalStateException("service down"))
        .onErrorResume(IllegalStateException.class, error -> backup.mono());

StepVerifier.create(result)
    .expectNext("backup-ok")
    .verifyComplete();

backup.assertWasSubscribed();
backup.assertWasRequested();
~~~

If the source completes empty rather than erroring, `onErrorResume` is not invoked:

~~~java
PublisherProbe<String> backup =
    PublisherProbe.of(Mono.just("backup-ok"));

Mono<String> result = Mono.<String>empty()
    .onErrorResume(IllegalStateException.class, error -> backup.mono());

StepVerifier.create(result).verifyComplete();
backup.assertWasNotSubscribed();
~~~

When using `onErrorResume` with a predicate or exception type, test both recoverable errors and non-recoverable errors so bugs are not accidentally swallowed.

### 6.2. doOnError Is Not a Recovery Branch

`doOnError` only observes errors. It does not replace an error with a fallback. Only when `onErrorResume` is chained afterward is there a backup source to probe.

### 6.3. timeout with Fallback

`timeout(Duration, fallback)` can switch to an alternate Publisher upon timeout. `PublisherProbe` verifies the alternate was subscribed, while `StepVerifier.withVirtualTime` avoids real waiting time.

Create the source **lazily** inside the supplier passed to `withVirtualTime` so the virtual scheduler is installed before the timer operator is assembled.

### 6.4. firstWithSignal and Other Race/Selection Operators

Not every multi-Publisher operator waits for the first source to fail before subscribing to the second. For instance, `firstWithSignal` may subscribe to multiple candidates, pick whichever emits a signal first, and cancel the remaining candidates.

In such cases, `probe.assertWasSubscribed()` only proves **the candidate was subscribed to**, not that it "won" or produced the final output. Combine assertions on data, signals, and cancellation.

### 6.5. Real Side Effects and Mocks

A probe answers "was the branch Publisher used?". When you need to verify "how many times was `repository.findById` called" or "was the message published successfully", use mocks/spies or integration tests at the proper boundary.

Specifically, many service methods only **create a cold `Mono`** when called. A mock verifying "method was called" and a `PublisherProbe` verifying "`Mono` was subscribed to" are **two different pieces of evidence**.

## 7. Flux Fallbacks, Demand, and Cancellation

### 7.1. Flux.switchIfEmpty

`Flux.switchIfEmpty` picks a fallback Publisher if the upstream `Flux` completes without emitting items:

~~~java
PublisherProbe<String> backup =
    PublisherProbe.of(Flux.just("db-1", "db-2"));

Flux<String> output = Flux.<String>empty()
    .switchIfEmpty(backup.flux());

StepVerifier.create(output)
    .expectNext("db-1", "db-2")
    .verifyComplete();

backup.assertWasSubscribed();
backup.assertWasRequested();
backup.assertWasNotCancelled();
~~~

If upstream emits any `onNext`, the fallback is **not** used, even if upstream emits fewer items than expected. `switchIfEmpty` differs from `concatWith`: `concatWith` subscribes to the next publisher once the first completes, whether the first was empty or not.

### 7.2. Basic Backpressure Test

~~~java
PublisherProbe<String> backup =
    PublisherProbe.of(Flux.just("db-1", "db-2"));

Flux<String> result = Flux.<String>empty()
    .switchIfEmpty(backup.flux());

StepVerifier.create(result, 0)
    .expectSubscription()
    .thenRequest(1)
    .expectNext("db-1")
    .thenRequest(1)
    .expectNext("db-2")
    .verifyComplete();

backup.assertWasSubscribed();
backup.assertWasRequested();
~~~

Passing `0` to `StepVerifier.create(result, 0)` sets the initial request to 0. `thenRequest(1)` grants demand step by step. This illustrates combining `StepVerifier` to verify outputs with a probe to verify the branch.

`assertWasRequested()` does not prove "exactly 2 were requested". It only records that a request happened; demand counts and ordering are governed by the `StepVerifier` script.

### 7.3. Testing Cancellation

A fallback that emits no data and never completes:

~~~java
PublisherProbe<String> backup =
    PublisherProbe.of(Flux.never());

Flux<String> result = Flux.<String>empty()
    .switchIfEmpty(backup.flux());

StepVerifier.create(result, 0)
    .expectSubscription()
    .thenRequest(1)
    .thenCancel()
    .verify();

backup.assertWasSubscribed();
backup.assertWasRequested();
backup.assertWasCancelled();
~~~

`Flux.never()` keeps the stream active until downstream cancels. Using `Flux.just("value")` might complete right away, preventing the test from proving the cancellation path.

### 7.4. Do Not Over-Interpret

- `assertWasSubscribed`: the branch had a subscriber.
- `assertWasRequested`: demand occurred, without specifying the amount.
- `assertWasCancelled`: a cancellation signal arrived, not that the source "errored".
- `assertWasNotCancelled`: the test observed no cancellation, which does not prove connections/databases closed.
- `verifyComplete`: the Publisher emitted complete; it does not prove side-effect transactions committed.

When you need to verify exact `request(n)` counts, use `TestPublisher` or a specialized test subscriber; when you need resource cleanup, verify `doFinally` and real integration tests.

## 8. Complete Maven Example: Java 17 and reactor-test

The project below demonstrates the most important cases without starting a Spring `ApplicationContext`. The Spring Boot parent only provides dependency management for Reactor/JUnit; the business class uses pure `reactor-core`.

### 8.1. Structure

~~~text
publisher-probe-demo/
├── pom.xml
├── src/main/java/example/probe/
│   └── LookupPipeline.java
└── src/test/java/example/probe/
    └── LookupPipelineTest.java
~~~

### 8.2. pom.xml

~~~xml
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
    <artifactId>publisher-probe-demo</artifactId>
    <version>1.0.0</version>

    <properties>
        <java.version>17</java.version>
    </properties>

    <dependencies>
        <dependency>
            <groupId>io.projectreactor</groupId>
            <artifactId>reactor-core</artifactId>
        </dependency>

        <dependency>
            <groupId>io.projectreactor</groupId>
            <artifactId>reactor-test</artifactId>
            <scope>test</scope>
        </dependency>

        <dependency>
            <groupId>org.springframework.boot</groupId>
            <artifactId>spring-boot-starter-test</artifactId>
            <scope>test</scope>
        </dependency>
    </dependencies>
</project>
~~~

`reactor-test` appears only in test scope. `spring-boot-starter-test` provides JUnit Jupiter and testing utilities. The project does not use `@SpringBootTest` because no Spring container or HTTP server is needed to test Reactor operators.

### 8.3. LookupPipeline.java

~~~java
package example.probe;

import java.util.Objects;
import java.util.function.Function;

import reactor.core.publisher.Flux;
import reactor.core.publisher.Mono;

public final class LookupPipeline {

    public Mono<String> resolve(
        Mono<String> cache,
        Mono<String> database
    ) {
        Objects.requireNonNull(cache, "cache");
        Objects.requireNonNull(database, "database");
        return cache.switchIfEmpty(database);
    }

    public Flux<String> resolveMany(
        Flux<String> cache,
        Flux<String> database
    ) {
        Objects.requireNonNull(cache, "cache");
        Objects.requireNonNull(database, "database");
        return cache.switchIfEmpty(database);
    }

    public Mono<String> recover(
        Mono<String> remote,
        Mono<String> backup
    ) {
        Objects.requireNonNull(remote, "remote");
        Objects.requireNonNull(backup, "backup");

        return remote.onErrorResume(
            IllegalStateException.class,
            error -> backup
        );
    }

    public Mono<Void> processOrFallback(
        Mono<String> command,
        Function<String, Mono<Void>> process,
        Mono<Void> fallback
    ) {
        Objects.requireNonNull(command, "command");
        Objects.requireNonNull(process, "process");
        Objects.requireNonNull(fallback, "fallback");

        return command
            .flatMap(value ->
                process.apply(value).thenReturn(Boolean.TRUE))
            .switchIfEmpty(fallback.thenReturn(Boolean.FALSE))
            .then();
    }
}
~~~

**Behavior explained:**

- `resolve` subscribes to the database Publisher only when cache completes with no item.
- `resolveMany` does the same for `Flux`.
- `recover` handles only errors of type `IllegalStateException`; empty sources do not trigger recovery.
- `processOrFallback` takes a command and an action returning `Mono<Void>`. The internal `Boolean` marker ensures the fallback is subscribed only when no command is emitted, unaffected by `process.apply` returning Void.

There is no need to instantiate `PublisherProbe` in this class. Probes are passed in by tests like any regular Publisher.

### 8.4. LookupPipelineTest.java

~~~java
package example.probe;

import static org.junit.jupiter.api.Assertions.assertEquals;

import java.util.concurrent.atomic.AtomicInteger;

import org.junit.jupiter.api.BeforeEach;
import org.junit.jupiter.api.Test;

import reactor.core.publisher.Flux;
import reactor.core.publisher.Mono;
import reactor.test.StepVerifier;
import reactor.test.publisher.PublisherProbe;

class LookupPipelineTest {

    private LookupPipeline pipeline;

    @BeforeEach
    void setUp() {
        pipeline = new LookupPipeline();
    }

    @Test
    void cacheMissSubscribesFallbackMono() {
        PublisherProbe<String> database =
            PublisherProbe.of(Mono.just("db-A01"));

        StepVerifier.create(
                pipeline.resolve(Mono.empty(), database.mono()))
            .expectNext("db-A01")
            .verifyComplete();

        database.assertWasSubscribed();
        database.assertWasRequested();
        database.assertWasNotCancelled();
    }

    @Test
    void cacheHitDoesNotSubscribeFallbackMono() {
        PublisherProbe<String> database =
            PublisherProbe.of(Mono.just("db-unused"));

        StepVerifier.create(
                pipeline.resolve(Mono.just("cache-A01"), database.mono()))
            .expectNext("cache-A01")
            .verifyComplete();

        database.assertWasNotSubscribed();
        database.assertWasNotRequested();
        database.assertWasNotCancelled();
    }

    @Test
    void cacheErrorDoesNotTriggerSwitchIfEmpty() {
        PublisherProbe<String> database =
            PublisherProbe.of(Mono.just("db-unused"));

        StepVerifier.create(
                pipeline.resolve(
                    Mono.error(new IllegalStateException("cache down")),
                    database.mono()))
            .expectErrorMessage("cache down")
            .verify();

        database.assertWasNotSubscribed();
    }

    @Test
    void filteringOutItemTriggersFallback() {
        PublisherProbe<String> database =
            PublisherProbe.of(Mono.just("db-valid"));

        Mono<String> source = Mono.just("stale")
            .filter(value -> value.startsWith("valid-"));

        StepVerifier.create(pipeline.resolve(source, database.mono()))
            .expectNext("db-valid")
            .verifyComplete();

        database.assertWasSubscribed();
    }

    @Test
    void monoVoidFallbackIsObservedWhenCommandMissing() {
        PublisherProbe<Void> fallback = PublisherProbe.empty();

        StepVerifier.create(
                pipeline.processOrFallback(
                    Mono.empty(),
                    command -> Mono.empty(),
                    fallback.mono()))
            .verifyComplete();

        fallback.assertWasSubscribed();
        fallback.assertWasRequested();
        fallback.assertWasNotCancelled();
    }

    @Test
    void monoVoidFallbackIsNotUsedWhenCommandPresent() {
        PublisherProbe<Void> fallback = PublisherProbe.empty();

        StepVerifier.create(
                pipeline.processOrFallback(
                    Mono.just("approve"),
                    command -> Mono.empty(),
                    fallback.mono()))
            .verifyComplete();

        fallback.assertWasNotSubscribed();
        fallback.assertWasNotRequested();
    }

    @Test
    void onErrorResumeUsesBackupForMatchingError() {
        PublisherProbe<String> backup =
            PublisherProbe.of(Mono.just("backup-ok"));

        StepVerifier.create(
                pipeline.recover(
                    Mono.error(new IllegalStateException("remote down")),
                    backup.mono()))
            .expectNext("backup-ok")
            .verifyComplete();

        backup.assertWasSubscribed();
        backup.assertWasRequested();
    }

    @Test
    void onErrorResumeDoesNotUseBackupForEmptySource() {
        PublisherProbe<String> backup =
            PublisherProbe.of(Mono.just("backup-unused"));

        StepVerifier.create(
                pipeline.recover(Mono.empty(), backup.mono()))
            .verifyComplete();

        backup.assertWasNotSubscribed();
    }

    @Test
    void fluxFallbackHandlesDemand() {
        PublisherProbe<String> backup =
            PublisherProbe.of(Flux.just("db-1", "db-2"));

        StepVerifier.create(
                pipeline.resolveMany(Flux.empty(), backup.flux()), 0)
            .expectSubscription()
            .thenRequest(1)
            .expectNext("db-1")
            .thenRequest(1)
            .expectNext("db-2")
            .verifyComplete();

        backup.assertWasSubscribed();
        backup.assertWasRequested();
        backup.assertWasNotCancelled();
    }

    @Test
    void cancellingFluxFallbackIsRecorded() {
        PublisherProbe<String> backup =
            PublisherProbe.of(Flux.never());

        StepVerifier.create(
                pipeline.resolveMany(Flux.empty(), backup.flux()), 0)
            .expectSubscription()
            .thenRequest(1)
            .thenCancel()
            .verify();

        backup.assertWasSubscribed();
        backup.assertWasRequested();
        backup.assertWasCancelled();
    }

    @Test
    void deferredFallbackFactoryIsNotCalledOnCacheHit() {
        AtomicInteger factoryCalls = new AtomicInteger();

        PublisherProbe<String> backup = PublisherProbe.of(
            Mono.defer(() -> {
                factoryCalls.incrementAndGet();
                return Mono.just("db-value");
            })
        );

        StepVerifier.create(
                pipeline.resolve(Mono.just("cache-value"), backup.mono()))
            .expectNext("cache-value")
            .verifyComplete();

        backup.assertWasNotSubscribed();
        assertEquals(0, factoryCalls.get());
    }

    @Test
    void deferredFallbackFactoryRunsOnCacheMiss() {
        AtomicInteger factoryCalls = new AtomicInteger();

        PublisherProbe<String> backup = PublisherProbe.of(
            Mono.defer(() -> {
                factoryCalls.incrementAndGet();
                return Mono.just("db-value");
            })
        );

        StepVerifier.create(
                pipeline.resolve(Mono.empty(), backup.mono()))
            .expectNext("db-value")
            .verifyComplete();

        backup.assertWasSubscribed();
        assertEquals(1, factoryCalls.get());
    }
}
~~~

**Key points of this test suite:**

- The two cache hit/miss tests verify **both directions** of `switchIfEmpty`.
- The cache error test proves errors are not confused with empty completion.
- The two `Mono<Void>` tests distinguish branches via probes, even though both outer outcomes are mere completion.
- The two `onErrorResume` tests prove recovery happens on error, not on an empty source.
- The `Flux` test uses initial request 0 and `thenRequest` to verify demand.
- The cancellation test uses `Flux.never()` so the fallback does not complete before downstream cancels.
- The two `Mono.defer` tests verify **factory invocation** via `AtomicInteger`, which a `PublisherProbe` alone does not assert directly.

### 8.5. Running the Tests

Requires JDK 17+ and Maven:

~~~bash
mvn test
~~~

Example expected result if all tests pass:

~~~text
Tests run: 12, Failures: 0, Errors: 0, Skipped: 0
BUILD SUCCESS
~~~

This is an **expected outcome**, not an executed run log. The project has no HTTP controller or `main` method to start. All examples are direct Reactor unit tests.

### 8.6. Practice Causing an Intentional Test Failure

Change `LookupPipeline.processOrFallback` to the buggy version:

~~~java
return command
    .flatMap(process)
    .switchIfEmpty(fallback);
~~~

Run `mvn test` again. `monoVoidFallbackIsNotUsedWhenCommandPresent` will fail because `fallback.assertWasNotSubscribed()` detects that the fallback was subscribed even though a command was present.

Restore the implementation using `thenReturn(Boolean.TRUE)` and `thenReturn(Boolean.FALSE)`. The test must pass again.

This exercise clearly shows the value of `PublisherProbe`: a test calling only `verifyComplete()` would miss this regression.

## 9. PublisherProbe vs. StepVerifier, TestPublisher, and Mocks

| Tool | Question answered | Best suited for |
| --- | --- | --- |
| `StepVerifier` | What `onNext`, `onError`, `onComplete` signals does the Publisher emit and how does it react to demand/cancel? | All reactive logic tests |
| `PublisherProbe` | Was a branch Publisher subscribed/requested/cancelled? | `switchIfEmpty`, `onErrorResume`, and branch selection |
| `TestPublisher` | Can we manually emit signals and test spec violations or exact `request(n)`? | Custom operators, races, and backpressure |
| Mockito/mock | Which method/adapter was called with what arguments? | Service/repository invocations |
| Integration test | Did the real side effect happen? | DB commits, HTTP requests, message publishing |

### 9.1. When Is a Probe the Best Choice?

`PublisherProbe` excels when:

1. A fallback is represented by a separate Publisher.
2. You want to verify the fallback **was or was not** subscribed.
3. Branches both complete empty (especially `Mono<Void>`).
4. You want less boilerplate than wiring multiple `AtomicBoolean` flags with `doOnSubscribe`/`doOnRequest`/`doOnCancel`.
5. The fallback Publisher can be replaced by a probe without altering the intended business semantics.

### 9.2. When Is a Probe Not Enough?

- Measuring exact `request(n)`: combine `TestPublisher` or a test subscriber.
- Knowing if a factory was called at assembly time: use a spy/`AtomicInteger`.
- Asserting the fallback produced `onNext`: combine `StepVerifier` with distinguishable test data.
- Verifying HTTP requests actually reached downstream: use MockWebServer, WireMock, or network tests.
- Verifying a DB record was committed: integration test against a DB.
- Testing multiple subscriptions: create separate probes per scenario, and consider subscription-count APIs when supported by your version and required by the test.

### 9.3. Do Not Use TestPublisher Just as a Probe

`TestPublisher` relates to the `PublisherProbe` API, yet requires managing emitted signals. When you only need to know whether a branch was subscribed, `PublisherProbe.empty()` or `PublisherProbe.of(source)` is shorter and less error-prone.

If using `TestPublisher` for post-terminal assertions, understand its violation/cleanup modes. Do not pick `TestPublisher` merely to call `assertWasSubscribed`.

## 10. Common Mistakes and Fixes

**Mistake 1 — Only creating a Mono without subscribing.** The probe observes nothing. Always run `StepVerifier...verify()` before asserting the probe.

**Mistake 2 — Confusing "was created" with "was subscribed".** `switchIfEmpty(fallback)` can be assembled without subscribing to the fallback. Probes check subscription, not factory invocation.

**Mistake 3 — Only checking fallback subscription while forgetting the opposite branch.** Test both cache miss and cache hit with `assertWasSubscribed` and `assertWasNotSubscribed`.

**Mistake 4 — Using switchIfEmpty for errors.** `switchIfEmpty` handles only empty completion. Use `onErrorResume` for recovering from `onError`.

**Mistake 5 — Using onErrorResume to handle Mono.empty.** Empty is not an error. Use `switchIfEmpty` or `defaultIfEmpty`.

**Mistake 6 — Using PublisherProbe.empty() for a fallback that must return data.** An empty probe changes semantics. Use `PublisherProbe.of(Mono.just(value))`.

**Mistake 7 — Misunderstanding Mono<Void>.flatMap.** When a processor returns `Mono<Void>`, upstream after `flatMap` is empty, causing fallback to run erroneously. Use a `thenReturn(...)` marker before `switchIfEmpty`.

**Mistake 8 — Asserting the probe before StepVerifier.verifyComplete.** The lazy chain has not run yet. Wait for verification to finish before checking the branch.

**Mistake 9 — Reusing one probe across multiple tests.** Accumulated subscription state can cause false positives. Create a fresh probe per test case.

**Mistake 10 — Thinking assertWasRequested checks item count.** It only records that a request occurred. Use `StepVerifier` demand scripting or `TestPublisher` when counts matter.

**Mistake 11 — Thinking assertWasSubscribed proves the fallback produced output.** A Publisher can be subscribed and immediately cancelled. Verify outputs/signals with `StepVerifier`.

**Mistake 12 — Using Flux.just for cancellation tests where Flux completes before cancel.** Pick `Flux.never()` to keep the subscription alive until `StepVerifier` cancels.

**Mistake 13 — Calling StepVerifier.thenCancel followed by expectComplete.** Cancellation is the verification scenario's terminal expectation; do not expect complete after cancel.

**Mistake 14 — Forgetting requests when initial request = 0.** With demand-driven sources, `StepVerifier` can wait forever. Use `thenRequest(n)` appropriately.

**Mistake 15 — Probing branches behind an operator that subscribes to multiple candidates.** With `firstWithSignal`, subscription does not prove which candidate won. Also check emitted signals and cancellation.

**Mistake 16 — Using probes to claim DB commits.** Probes only see subscription/demand/cancel. Query the DB or run integration tests.

**Mistake 17 — Ignoring the difference between assembly and subscription.** Factories with eager side effects can run even when the fallback is not subscribed. Use `Mono.defer` and test with `AtomicInteger`/spy.

**Mistake 18 — Calling subscribe() in unit tests and asserting immediately.** Async Publishers may not have emitted or reached the fallback yet. `StepVerifier` gives an ordered script and clear completion point.

**Mistake 19 — Confusing StepVerifier vs. PublisherProbe assertion failures.** `StepVerifier` checks signals; `PublisherProbe` checks branches; when tests fail, read both to see if the bug is data or control flow.

**Mistake 20 — Trying to ship probes in production.** `reactor-test` belongs in test scope; production logic should accept cold Publisher/Publisher abstractions rather than depending on test tools.

## 11. Checklist for Writing PublisherProbe Tests

1. Which branch needs proof of being subscribed or not subscribed?
2. Is the branch chosen due to empty, error, timeout, or another condition?
3. Should the probe use `empty()` or `of(source)` to preserve fallback signals?
4. Is `probe.mono()` or `probe.flux()` attached at the exact spot?
5. Did `StepVerifier.verifyComplete/verify/thenCancel` run before probe assertions?
6. Does the test assert outputs/errors/completion per the method contract?
7. Are both positive and negative fallback tests included?
8. Are `assertWasRequested` or cancellation checked where relevant?
9. Did you avoid reusing a single probe across scenarios?
10. For `Mono<Void>`, did you avoid the `flatMap(...).switchIfEmpty(...)` pitfall?
11. For empty vs. error sources, did you distinguish `switchIfEmpty` and `onErrorResume`?
12. Do you need to test factory invocation separately from subscription?
13. Does the test need exact demand counts or merely that a request happened?
14. Does any operator subscribe to multiple candidates and cancel losing branches?
15. If real side effects exist, is there a separate integration test?

## 12. Self-Check Exercises

1. Which module does `PublisherProbe` belong to? **`reactor-test`**.
2. What is the import? **`reactor.test.publisher.PublisherProbe`**.
3. What is a probe's primary purpose? **Observing subscription/request/cancellation on a branch Publisher.**
4. What does `PublisherProbe.empty()` emit? **No `onNext`; only completes while recording interactions.**
5. How does `PublisherProbe.of(Mono.just("x"))` differ from `empty()`? **Preserves signals and values from the wrapped Publisher.**
6. API to get a `Mono` from a probe? **`probe.mono()`.**
7. API to get a `Flux` from a probe? **`probe.flux()`.**
8. Assertion that a branch was subscribed? **`assertWasSubscribed()`.**
9. Assertion that a branch was not subscribed? **`assertWasNotSubscribed()`.**
10. Assertion that a branch received demand? **`assertWasRequested()`.**
11. Assertion that a branch was cancelled? **`assertWasCancelled()`.**
12. Why must `StepVerifier.verify` run before probe assertions? **Publishers are lazy and have no subscription before verify.**
13. When does `switchIfEmpty` switch to the fallback? **When the source completes without emitting `onNext`.**
14. Does `switchIfEmpty` handle `onError`? **No; use `onErrorResume`.**
15. Does `onErrorResume` run when the source completes empty? **No.**
16. Why can `Mono<Void>.flatMap(...).switchIfEmpty(...)` erroneously call the fallback? **Because `Mono<Void>` emits no items, so downstream sees an empty source.**
17. How do you preserve a marker when `process` returns `Mono<Void>`? **`process(value).thenReturn(Boolean.TRUE)` before `switchIfEmpty`, then a final `then()`.**
18. Does a probe verify an exact `request(7)`? **No; it only checks whether a request occurred—use another tool when exact counts matter.**
19. Why is `Flux.never` useful in tests? **Keeps the Publisher open so cancellation can be observed.**
20. Does subscribing to a candidate prove it won `firstWithSignal`? **No, multiple candidates can be subscribed and then cancelled.**
21. Does a probe prove a database commit? **No; use integration tests.**
22. Why combine `Mono.defer` with a probe? **Defers creating the fallback source until subscription and separates testing factory invocation from subscription.**

## 13. Summary and References

- `PublisherProbe` is a `reactor-test` utility for verifying whether a branch Publisher **was or was not subscribed**, received requests, and was cancelled.
- Attach `probe.mono()`/`probe.flux()` to the branch under observation; run `StepVerifier` through its terminal expectation before asserting the probe.
- `PublisherProbe.empty()` fits `Mono<Void>` well when outputs of two branches are otherwise indistinguishable.
- `PublisherProbe.of(source)` wraps a real Publisher to keep `onNext`/`onError`/`onComplete` in the test.
- `switchIfEmpty` runs on empty completion; `onErrorResume` runs on errors; the two conditions differ.
- `Mono<Void>.flatMap(...).switchIfEmpty(...)` can trigger the fallback by mistake; use a `thenReturn` marker to distinguish a handled primary branch.
- `assertWasRequested` does not measure demand quantity; `assertWasSubscribed` does not prove business commits.
- For `Flux`, `StepVerifier` can issue `thenRequest(n)` and `thenCancel()` to drive and observe the lifecycle.
- Test both positive and negative branches; create a fresh probe per test and use integration tests for real side effects.

**Official references:**

1. [Project Reactor Reference — Testing, Checking the Execution Path with PublisherProbe](https://projectreactor.io/docs/core/3.7.16/reference/testing.html): `switchIfEmpty`, `Mono<Void>`, and the three core assertions.
2. [Project Reactor Javadoc — PublisherProbe](https://projectreactor.io/docs/test/release/api/reactor/test/publisher/PublisherProbe.html): `empty`, `of`, `mono`, `flux`, `assertWasSubscribed`/`Requested`/`Cancelled`.
3. [Project Reactor Javadoc — StepVerifier](https://projectreactor.io/docs/test/release/api/reactor/test/StepVerifier.html): `create`, `verify`, `expectNext`, `thenRequest`, `thenCancel`.
4. [Project Reactor Javadoc — Mono.switchIfEmpty](https://projectreactor.io/docs/core/release/api/reactor/core/publisher/Mono.html): fallback on completion without items.
5. [Project Reactor Javadoc — Flux.switchIfEmpty](https://projectreactor.io/docs/core/release/api/reactor/core/publisher/Flux.html): fallback Publisher for an empty `Flux`.
6. [Project Reactor Reference — Testing and TestPublisher](https://projectreactor.io/docs/core/release/reference/testing.html): distinguishing `StepVerifier`, `PublisherProbe`, and `TestPublisher`.
7. [Spring Boot 3.5 — Reference](https://docs.spring.io/spring-boot/3.5/reference/): JUnit/Reactor dependency management and Maven plugins in the sample project.

# Verifying Element Ordering and Discarded Data in Reactive Streams

When testing a `Flux` in Spring Boot WebFlux, knowing that **the right number of elements arrived** is not enough. A pipeline might emit the same three values in the **wrong order**, mistakenly filter out a valid event, keep a forbidden event, or fail to clean up objects dropped by an operator. These bugs often stay hidden if tests only use `expectNextCount`, convert results into a `Set`, or call `block()` and check only size.

**Project Reactor** provides `reactor-test` and **`StepVerifier`** to check sequences of `onNext`, `onComplete`, `onError`, cancellation, and post-execution states. For elements that do not appear downstream, it is important to distinguish:

- **Discarded**: elements processed and **intentionally rejected** by an operator in a valid stream, such as failing `filter`, being skipped by `skip`, or being drained from an operator's queue after cancellation. Reactor provides local discard hooks and `StepVerifier.Assertions.hasDiscarded(...)`.
- **Dropped**: `onNext` signals that are no longer valid to process, such as a noncompliant publisher attempting to emit after a terminal signal; operators may route these through `Hooks.onNextDropped`. Do not use `hasDropped` to check values normally rejected by `filter`.
- **Never emitted / never requested**: elements that never entered the operator due to backpressure or cancellation. There is **no basis** to claim they were discarded or dropped.

This lesson explains how to write assertions for exact ordering, discarded data, and terminal conditions; guides choosing between `expectNext`, `expectNextSequence`, `verifyThenAssertThat`, `doOnDiscard`, and `TestPublisher`; includes a runnable **Java 17 + Spring Boot 3.5** project with JUnit Jupiter, along with notes on concurrency and the WebFlux HTTP boundary.

## 1. Flux Signals and the Meaning of Order

A Reactive Streams–compliant Publisher can send the following signals:

```text
Subscriber                    Publisher
    |                             |
    |<---- onSubscribe(S) --------|
    |---- request(n) ------------>|
    |<---- onNext(A) -------------|
    |<---- onNext(B) -------------|
    |<---- onNext(C) -------------|
    |<---- onComplete() ----------|
    |       or onError(e)         |
```

`onComplete` and `onError` are mutually exclusive **terminal signals**; a compliant Publisher does not continue sending `onNext` after termination. A Subscriber can also cancel the `Subscription` via `cancel`. All of these signals must be verified, not just the `onNext` list.

Suppose the contract requires output **A → B → C**. There are several distinct outcomes:

| Output | Enough Elements? | Right Order? | Right Terminal? |
|---|---|---|---|
| A, B, C, complete | Yes | Yes | Yes |
| A, C, B, complete | Yes | **No** | Yes |
| A, B, C, error | Yes | Yes | **No** |
| A, B, C, D, complete | Wrong count | Prefix matches | Yes |

A test using only `expectNextCount(3)` misses the A, C, B swap. A test checking only `expectNext(A, B, C)` while omitting the terminal expectation can miss element D or an error emitted after the prefix.

## 2. StepVerifier APIs for Ordering and Terminal Signals

### `expectNext` and `expectNextSequence`

Two ways to prove **both values and positions**:

```java
StepVerifier.create(Flux.just(10, 20, 30))
        .expectNext(10, 20, 30)
        .verifyComplete();

StepVerifier.create(Flux.just(10, 20, 30))
        .expectNextSequence(List.of(10, 20, 30))
        .verifyComplete();
```

This is a snippet placed in a test with `Flux`, `StepVerifier`, and `List` imports. If the source emits `10, 30, 20`, both tests must FAIL on the expected ordering.

### `expectNextCount` Does Not Check Values

```java
StepVerifier.create(Flux.just(10, 30, 20))
        .expectNextCount(3)
        .verifyComplete();
```

This test PASSES because it only asserts **three** `onNext` signals arrived and the stream completed. It makes sense when ordering/values are outside the contract; if ordering is part of the contract, it provides **insufficient proof**.

### `assertNext` and `expectNextMatches`

To inspect multiple fields of individual events:

```java
StepVerifier.create(events)
        .assertNext(event -> {
            assertEquals("E-1", event.id());
            assertEquals(200, event.amount());
        })
        .expectNextMatches(event -> event.id().equals("E-2"))
        .verifyComplete();
```

This is a **non-standalone** snippet; the `events` variable and `event` type belong to a specific test. `assertNext` receives the element at the **current position** and allows JUnit/AssertJ assertions. `expectNextMatches` evaluates a predicate on the **next single element**; an overly loose predicate can let wrong fields slip past.

### Do Not Forget `verify`

`StepVerifier.create(...).expectNext(...)` only **declares the scenario**. You need `verifyComplete()`, `verifyError()`, `expectComplete().verify()`, `thenCancel().verify()`, or `verifyThenAssertThat()` to actually run it. For publishers that might not terminate, use `verify(Duration)` or an appropriate timeout; untimed shortcuts can wait forever.

## 3. Distinguishing `filter`, `skip`, `take`, `discard`, and `drop`

| Scenario | What Does the Subscriber See? | How Are Unseen Values Classified? |
|---|---|---|
| `Flux.range(1, 6).filter(i -> i % 2 == 0)` | 2, 4, 6 | 1, 3, 5 are **discarded** by an operator with discard support |
| `Flux.just(10, 20, 30).skip(1)` | 20, 30 | 10 is **discarded** when `skip` processes it |
| `Flux.range(1, 100).take(2)` | 1, 2 | 3..100 **may never have been emitted**; do not assert discard |
| Source prefetches into queue then downstream cancels | Emitted prefix | Items sitting in queue **may** be discarded during operator cleanup |
| Faulty source emits `onNext` after `onComplete` | New value rejected | May be reported **dropped** via `Hooks.onNextDropped` |
| `Flux.never()` emits nothing | No `onNext`, no complete | Not automatically discarded or dropped |

**Discard** belongs to normal data paths on operators that support it, whereas **drop** via hooks usually indicates an invalid signal condition. Never assume that any element unseen by the subscriber went through a discard hook. Reactor Javadoc explicitly documents **Discard Support** on supporting operators; check that section if your test relies on cleanup details.

### Why Should `take(2)` Not Assert That 3..100 Were Discarded?

`take` may request only two elements and cancel upstream, so `Flux.range` never even emits 3..100. They **were never produced as `onNext` signals to be rejected**. By contrast, an operator with prefetching/queuing cancelled mid-stream may already hold undelivered items that need cleanup via discard hooks. That behavior depends on operator, prefetch size, timing, and version—not a rule that `take` always discards everything remaining.

## 4. Post-Execution Assertions: `verifyThenAssertThat()`

A complete pattern for `filter`:

```java
Flux<Integer> evenNumbers = Flux.range(1, 6)
        .filter(n -> n % 2 == 0);

StepVerifier.create(evenNumbers)
        .expectNext(2, 4, 6)
        .expectComplete()
        .verifyThenAssertThat()
        .hasDiscardedExactly(1, 3, 5)
        .hasNotDroppedElements();
```

This is a snippet for a test method with Reactor imports. It checks:

1. **Output:** strictly 2, then 4, then 6, without reordering.
2. **Terminal:** `onComplete`, with no extra values or errors.
3. **Discarded:** the hook recorded **exactly** values 1, 3, 5.
4. **Dropped:** no `onNext` was reported via the dropped hook.

**Important note:** `hasDiscardedExactly(1, 3, 5)` checks the **set/multiset of values** with no extra discards, and **does not enforce discard order**. If the order of cleanup callbacks is itself a requirement, observe it in a controlled way on a synchronous pipeline with an explicitly ordered source.

Related APIs:

| Method | Check Performed |
|---|---|
| `hasDiscarded(a, b)` | At least these values were discarded |
| `hasDiscardedExactly(a, b)` | Exactly the expected values were discarded, with no others; **does not check order** |
| `hasDiscardedElements()` | At least one discarded value was recorded |
| `hasNotDiscardedElements()` | No discarded value was recorded via the hook |
| `hasDropped(a)` | At least these values were reported to `onNextDropped` |
| `hasDroppedExactly(a)` | Exactly these dropped values, with no others |
| `hasNotDroppedElements()` | No `onNextDropped` was recorded |
| `hasDroppedErrors()` | An error was reported to `onErrorDropped`, **distinct from** a stream's terminal error |

`verifyThenAssertThat()` **both runs verification and returns `StepVerifier.Assertions`**. Do not call `verifyComplete()` and then try to reach post-assertions from a finished builder; replace it with `expectComplete().verifyThenAssertThat()`.

## 5. Local Discard Hook: `doOnDiscard`

Reactor lets you clean up or observe objects rejected by supporting operators:

```java
List<Integer> discarded = new ArrayList<>();

Flux<Integer> even = Flux.range(1, 6)
        .filter(n -> n % 2 == 0)
        .doOnDiscard(Integer.class, discarded::add);

StepVerifier.create(even).expectNext(2, 4, 6).verifyComplete();
assertEquals(List.of(1, 3, 5), discarded);
```

This snippet belongs in a test with `List`, `ArrayList`, `assertEquals`, `Flux`, and `StepVerifier` imports. **Place `doOnDiscard` downstream of `filter`** so the hook applies to the **upstream** operator. With a synchronous source and filter like above, callback order is deterministic; with `flatMap`/parallel/async pipelines, do not assume callbacks execute in input order.

If objects hold real resources like Netty `ByteBuf`, local hooks can run cleanup, but the callback **must be idempotent** and safe if invoked multiple times. Avoid writing direct cleanup hooks inside a stream where multiple operators or hooks might release the same object without safeguards. Not all operators support discard; verify in the Javadoc for your exact version.

**Do not confuse `doOnDiscard` with `Hooks.onNextDropped`:** the former is a local hook for supported discards, while the latter is a global hook for abnormally dropped signals. Do not install global hooks in a test and forget to reset them, or you can interfere with other tests running in parallel.

## 6. Runnable Java 17 Example in a Spring Boot Module

Suppose a system receives events with `id`, `priority`, and `state`:

- `approved(source)` keeps only `APPROVED` events, **preserving the relative order** of remaining events.
- `approvedSortedByPriority(source)` intentionally `sort`s by ascending priority after filtering.
- `REJECTED` events must be filtered out; the test wants to verify **the exact discarded events**, not merely "output has 2 items".
- The subscription can be `cancel`led; the test needs to verify **cancellation is not `onComplete`**.

The example runs on **Java 17**, Spring Boot **3.5.0**, JUnit Jupiter 5, and Reactor. Here we **do not** use `@SpringBootTest` because we are only testing operator logic without requiring DI, databases, or HTTP; that is a solid choice in a Spring WebFlux project.

### 6.1. Directory Tree

```text
reactive-sequence/
├── pom.xml
└── src/
    ├── main/java/com/example/reactive/
    │   └── EventPipeline.java
    └── test/java/com/example/reactive/
        └── EventPipelineTest.java
```

### 6.2. Complete Maven Configuration

File **`pom.xml`**:

```xml
<?xml version="1.0" encoding="UTF-8"?>
<project xmlns="http://maven.apache.org/POM/4.0.0"
         xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
         xsi:schemaLocation="http://maven.apache.org/POM/4.0.0 https://maven.apache.org/xsd/maven-4.0.0.xsd">
    <modelVersion>4.0.0</modelVersion>
    <parent>
        <groupId>org.springframework.boot</groupId>
        <artifactId>spring-boot-starter-parent</artifactId>
        <version>3.5.0</version>
        <relativePath/>
    </parent>
    <groupId>com.example</groupId>
    <artifactId>reactive-sequence</artifactId>
    <version>0.0.1-SNAPSHOT</version>
    <properties>
        <java.version>17</java.version>
    </properties>
    <dependencies>
        <dependency>
            <groupId>org.springframework.boot</groupId>
            <artifactId>spring-boot-starter-webflux</artifactId>
        </dependency>
        <dependency>
            <groupId>org.springframework.boot</groupId>
            <artifactId>spring-boot-starter-test</artifactId>
            <scope>test</scope>
        </dependency>
        <dependency>
            <groupId>io.projectreactor</groupId>
            <artifactId>reactor-test</artifactId>
            <scope>test</scope>
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

The `reactor-test` line is declared explicitly for `StepVerifier`/`TestPublisher`. Versions of `reactor-core` and `reactor-test` are managed by the Spring Boot BOM for compatibility; do not pin an arbitrary Reactor version just to patch compile errors. `spring-boot-starter-webflux` provides the reactive application context, while pure operator tests **do not boot a web server**.

### 6.3. Production File: `EventPipeline`

Create **`src/main/java/com/example/reactive/EventPipeline.java`**:

```java
package com.example.reactive;

import java.util.Comparator;
import java.util.Objects;

import reactor.core.publisher.Flux;

public final class EventPipeline {

    public enum State {
        APPROVED, REJECTED
    }

    public record Event(String id, int priority, State state) {
        public Event {
            Objects.requireNonNull(id, "id");
            Objects.requireNonNull(state, "state");
        }
    }

    public Flux<Event> approved(Flux<Event> source) {
        return Objects.requireNonNull(source, "source")
                .filter(e -> e.state() == State.APPROVED);
    }

    public Flux<Event> approvedSortedByPriority(Flux<Event> source) {
        return approved(source)
                .sort(Comparator.comparingInt(Event::priority));
    }
}
```

A `record` implements component-wise `equals`, so `StepVerifier.expectNext` accurately compares event contents. `approved(...)` only calls `filter` and **preserves the source order** of selected events; `approvedSortedByPriority` deliberately reorders data once available. `sort` requires the publisher to complete so it has all elements to sort; **do not apply it blindly to an infinite `Flux`** expecting incremental emissions.

### 6.4. Complete Test File: 9 JUnit Methods

Create **`src/test/java/com/example/reactive/EventPipelineTest.java`**:

```java
package com.example.reactive;

import java.time.Duration;
import java.util.ArrayList;
import java.util.List;

import org.junit.jupiter.api.Test;

import reactor.core.publisher.Flux;
import reactor.test.StepVerifier;
import reactor.test.StepVerifierOptions;
import reactor.test.publisher.TestPublisher;

import com.example.reactive.EventPipeline.Event;

import static com.example.reactive.EventPipeline.State.APPROVED;
import static com.example.reactive.EventPipeline.State.REJECTED;
import static org.junit.jupiter.api.Assertions.assertEquals;
import static org.junit.jupiter.api.Assertions.assertTrue;

class EventPipelineTest {
    private final EventPipeline pipeline = new EventPipeline();

    private final Event a = new Event("A", 3, APPROVED);
    private final Event b = new Event("B", 1, REJECTED);
    private final Event c = new Event("C", 2, APPROVED);
    private final Event d = new Event("D", 4, REJECTED);

    @Test
    void approvedEventsKeepRelativeSourceOrder() {
        StepVerifier.create(pipeline.approved(Flux.just(a, b, c, d)))
                .expectNext(a, c)
                .verifyComplete();
    }

    @Test
    void capturesExactlyWhichEventsWereDiscarded() {
        StepVerifier.create(pipeline.approved(Flux.just(a, b, c, d)))
                .expectNextSequence(List.of(a, c))
                .expectComplete()
                .verifyThenAssertThat()
                .hasDiscardedExactly(b, d)
                .hasNotDroppedElements();
    }

    @Test
    void localHookSeesDiscardOrderForThisSynchronousSource() {
        List<Event> discarded = new ArrayList<>();

        Flux<Event> output = pipeline.approved(Flux.just(a, b, c, d))
                .doOnDiscard(Event.class, discarded::add);

        StepVerifier.create(output)
                .expectNext(a, c)
                .verifyComplete();

        assertEquals(List.of(b, d), discarded);
    }

    @Test
    void explicitSortChangesOrderByPriority() {
        StepVerifier.create(
                        pipeline.approvedSortedByPriority(Flux.just(a, b, c, d)))
                .expectNext(c, a)
                .verifyComplete();
    }

    @Test
    void allRejectedEventsAreDiscardedAndStreamCompletes() {
        StepVerifier.create(pipeline.approved(Flux.just(b, d)))
                .expectComplete()
                .verifyThenAssertThat()
                .hasDiscardedExactly(b, d);
    }

    @Test
    void aNormalSourceWithoutFilteringHasNoDiscardedItems() {
        StepVerifier.create(Flux.just(a, c))
                .expectNext(a, c)
                .expectComplete()
                .verifyThenAssertThat()
                .hasNotDiscardedElements()
                .hasNotDroppedElements();
    }

    @Test
    void requestsOneByOneStillPreserveOrdering() {
        StepVerifier.create(
                        Flux.just(a, c),
                        StepVerifierOptions.create().initialRequest(0))
                .thenRequest(1)
                .expectNext(a)
                .thenRequest(1)
                .expectNext(c)
                .verifyComplete();
    }

    @Test
    void cancellingSourceIsDifferentFromReceivingComplete() {
        TestPublisher<Event> source = TestPublisher.create();

        StepVerifier.create(source.flux())
                .then(() -> source.next(a))
                .expectNext(a)
                .thenCancel()
                .verify(Duration.ofSeconds(2));

        source.assertWasCancelled();
    }

    @Test
    void customAssertionsCheckFieldsInEachPosition() {
        StepVerifier.create(pipeline.approved(Flux.just(a, b, c)))
                .assertNext(event -> {
                    assertEquals("A", event.id());
                    assertEquals(3, event.priority());
                })
                .assertNext(event -> {
                    assertEquals("C", event.id());
                    assertTrue(event.priority() > 0);
                })
                .verifyComplete();
    }
}
```

These are two complete Java source files together with `pom.xml`; they require no Spring context, networking, or database. With fixed fixture data, **9 tests are expected to PASS, 0 FAIL**. The cancellation test has a 2-second timeout so it does not hang on a non-terminating publisher; the other tests using `Flux.just` and `Flux.range` are finite and synchronous.

### 6.5. What Each Test Proves

| Test | Result and Boundary |
|---|---|
| `approvedEventsKeepRelativeSourceOrder` | B, D are filtered out; output is **A then C**, not reversed |
| `capturesExactlyWhichEventsWereDiscarded` | Verifier hook captures **B, D**, with no unexpected dropped `onNext` |
| `localHookSeesDiscardOrderForThisSynchronousSource` | On this synchronous stream, the hook observes **B before D** |
| `explicitSortChangesOrderByPriority` | After priority sorting, **C before A**, differing from input order |
| `allRejectedEventsAreDiscardedAndStreamCompletes` | Output is empty yet **completes**, with all discarded events recorded |
| `aNormalSourceWithoutFilteringHasNoDiscardedItems` | Normal source produces no discards or drops |
| `requestsOneByOneStillPreserveOrdering` | Demand of 1 at a time delivers A, C in order |
| `cancellingSourceIsDifferentFromReceivingComplete` | Subscriber cancels and `TestPublisher` records cancellation |
| `customAssertionsCheckFieldsInEachPosition` | Asserts `id`/`priority` at each position after filtering |

`hasDiscardedExactly(b, d)` does **not** verify the order B, D, whereas `doOnDiscard(...)` with a `List` observes callback order on this specific sequential source. With parallel sources, never extrapolate `doOnDiscard` ordering logic from a synchronous test.

### 6.6. How to Run

In the Maven project directory containing `pom.xml`:

```bash
mvn test
```

Or run just the specific class:

```bash
mvn -Dtest=EventPipelineTest test
```

If the project has a Maven Wrapper, replace with `./mvnw test` or `./mvnw -Dtest=EventPipelineTest test`; on Windows, use `mvnw.cmd` when a wrapper is present. Do not execute a JUnit class like `java EventPipelineTest` because it has no `main` method and requires the JUnit runner and Reactor dependencies. For this example class alone, the expected result is **Tests run: 9, Failures: 0, Errors: 0**; Surefire stdout formatting varies by version, and there is no fixed business stdout.

## 7. Operators That Do or Do Not Guarantee Output Ordering

| Operator | How to Read Ordering |
|---|---|
| `Flux.just`, `Flux.range` | Emit in source order along a standard sequential path |
| Synchronous `map`, `filter` | Do not reorder elements; `filter` only drops non-matching items |
| `sort(comparator)` | Intentionally reorders after the source completes |
| `flatMap` with async inners | May interleave inner emissions; **does not guarantee source order** |
| `concatMap` | Executes/concatenates inner streams in input order |
| `flatMapSequential` | May subscribe eagerly to inners, yet emits results in source inner order |
| `merge` of multiple sources | Interleaves by emission timing, no total order by default |
| `zip` | Pairs by index across sources, does not sort by timestamp |
| `skip`, `distinct` | May drop items, generally preserving relative order of kept items |
| `take(n)` | Emits a prefix then completes/cancels; does not prove remaining items were discarded |
| `parallel().runOn(...).sequential()` | May interleave across rails; do not assume original total order is kept |

**Avoid creating timing-flaky tests.** Illustrative snippet:

```java
Flux<Integer> async = Flux.just(1, 2, 3)
        .flatMap(i -> Mono.just(i)
                .delayElement(Duration.ofMillis((4 - i) * 20L)));
```

This snippet is **not standalone**; it needs `Mono`/`Flux` imports and a test method. Because inner publishers complete at different times, the output may often be `3, 2, 1`, yet you should not hardcode expected order relying on real scheduler/CPU timing and call it a contract. If business rules require `1, 2, 3`, pick `concatMap` or `flatMapSequential` according to concurrency goals and test with deterministic sources or virtual time.

## 8. Backpressure and Cancellation Are Not the Same as Discard

`request(n)` represents subscriber demand. `StepVerifier` can initialize demand to 0:

```java
StepVerifier.create(
                Flux.just("A", "B", "C"),
                StepVerifierOptions.create().initialRequest(0))
        .thenRequest(1)
        .expectNext("A")
        .thenRequest(2)
        .expectNext("B", "C")
        .verifyComplete();
```

This test proves demand and ordering; you **cannot** infer "values were discarded" simply because the source initially emitted nothing while unrequested.

When cancelling:

1. Elements **not yet generated or requested from the source**: not discarded.
2. Elements **processed and rejected by `filter`/`skip`**: may be reported as discarded via the hook.
3. Elements **prefetched into a queue and cleared on cancel**: may be discarded if the operator supports discard.
4. A faulty publisher **continuing to emit after terminal**: may be dropped via the hook, not normal discard.

When a test needs to verify cancellation, `TestPublisher.assertWasCancelled()` as shown in the runnable file is stronger evidence than guessing with `hasDiscarded(3..100)`. In applications handling resource-bearing objects, verify cleanup through proper API/ownership and idempotence, not just the count of missing items.

## 9. Testing Dropped Data for the Right Purpose

`StepVerifier.Assertions.hasDropped(...)` checks `onNext` signals routed to **`Hooks.onNextDropped`**. It is meant for scenarios intentionally exercising misbehaving publishers/operators, such as emitting after termination. `hasDroppedErrors(...)` relates to errors routed to `onErrorDropped`, which is **different** from a stream emitting a normal terminal `onError`.

Conceptual sketch (not a standalone test, as you must construct a protocol-violating `malformedPublisher`):

```java
StepVerifier.create(malformedPublisher)
        .expectNext("ok")
        .expectComplete()
        .verifyThenAssertThat()
        .hasDropped("late");
```

Do not copy the snippet above assuming it automatically PASSES: if the source blocks `"late"` inside the publisher or that value never reaches the dropped hook, `hasDropped` must FAIL. You can use `TestPublisher.createNoncompliant` with the appropriate violation to test noncompliant behavior; the test must confirm the hook actually receives the signal. **For `filter` tests**, use `hasDiscardedExactly` instead of trying to manufacture a fake dropped event.

Do not enable global `Hooks.onNextDropped` casually in parallel suites. If you must configure a global hook to test a custom source, isolate the test and reset the hook inside `finally`; do not let global Reactor state leak into other test classes.

## 10. Applying to Spring WebFlux: `StepVerifier` vs `WebTestClient`

A Spring WebFlux controller may return `Flux<EventDto>`, yet an HTTP test and an operator test prove different things:

| What Needs to Be Proven | Tool |
|---|---|
| Service pipeline emits exact events, order, and complete/error | `StepVerifier` directly on the `Flux` |
| Operator rejects right items and cleanup hook receives them | `StepVerifier.verifyThenAssertThat`/`doOnDiscard` |
| URL/route, status, headers, JSON serialization | `WebTestClient` with matching controller/router context |
| Real HTTP socket, codec, and embedded server | `@SpringBootTest(RANDOM_PORT)` + `WebTestClient` |
| Reactor publisher timing/backoff | `StepVerifier.withVirtualTime` when using virtual-time-compatible schedulers |
| SSE/Flux streaming, verifying only a prefix and cancelling | `WebTestClient.returnResult(...).getResponseBody()` + `StepVerifier` `thenCancel` |

Suppose `GET /api/events` returns filtered events. `WebTestClient` can check HTTP 200/JSON and the order of elements **that were sent out**, but it **cannot directly see which events were filtered out inside the service**. If your goal is verifying "which `REJECTED` events were discarded", test the pipeline directly with `StepVerifier`/hooks rather than inferring from JSON containing only `APPROVED` events.

For Server-Sent Events or infinite `Flux` streams, do not call `expectBodyList` and wait for a completion that never happens. Consume the streaming response and use `StepVerifier` to check a finite count followed by `thenCancel` with a timeout. Tests should never `block()` on a Reactor Netty event-loop thread or use `Thread.sleep` in place of deliberate signal or timing checks.

## 11. Common Mistakes and Fixes

| Mistake | What Gets Missed | Fix |
|---|---|---|
| Using `expectNextCount(3)` when order is required | Swapped A, C, B still passes | `expectNext(A, B, C)` |
| Collecting stream into `Set` or `containsExactlyInAnyOrder` | Hides ordering bugs | Check `expectNextSequence` or order-preserving list |
| Omitting `expectComplete`/`expectError` | Fails to check terminal signal | Verify exact terminal signal |
| Forgetting `verify` | No subscription or actual check runs | `verifyComplete`, `verify(Duration)`, `verifyThenAssertThat` |
| Treating `filter` output as dropped | Confuses normal discard with `onNextDropped` | `hasDiscardedExactly` |
| Expecting `take(2)` to discard all remaining items | Remainder may never have been emitted | Check cancellation and demand |
| Putting `doOnDiscard` before `filter` | Hook misses downstream operator | Place hook after the operator needing cleanup |
| Using non-idempotent cleanup hooks | May double-release or corrupt resources | Ensure idempotence and clear ownership |
| Relying on discard order with parallel `flatMap` | Callbacks may run out of order | Assert item set, assert order only if contract guarantees it |
| Using `Thread.sleep` to "stabilize" async tests | Flaky in CI | Virtual time or controlled schedulers |
| Using `verifyComplete` on an infinite `Flux` | Test can hang | `thenCancel` and timeout |
| Assuming `StepVerifier` tested HTTP status | Only tests Publisher, not WebFlux routing | Add `WebTestClient` |
| Leaving global `Hooks` active across tests | Cross-test interference | Isolate and reset hooks |
| Missing `reactor-test` on test classpath | Compile error for `reactor.test.StepVerifier` | Add BOM-managed test dependency |

## 12. Checklist Before Finishing a Test

- [ ] I determined whether the contract **requires exact order** or only item count/set equality.
- [ ] When order is required, I used `expectNext`/`expectNextSequence`, not just `expectNextCount`.
- [ ] Every test verifies the right terminal signal: complete, error, or cancel.
- [ ] The verifier invokes `verify` or a triggering shortcut to run.
- [ ] I distinguished **discard**, **drop**, and **never emitted**.
- [ ] For `filter`/`skip` supporting discard, I checked the exact discarded values.
- [ ] I understood `hasDiscardedExactly` checks **the exact values**, not their order.
- [ ] When cleanup callback order must be tested, the source and operators are synchronous and deterministic.
- [ ] I did not assume items past `take` were discarded.
- [ ] For `flatMap`/`merge`/`parallel`, I know exactly what ordering is guaranteed.
- [ ] For backpressure/cancel, I checked subscription state instead of guessing discarded values.
- [ ] Cleanup hooks are safe, idempotent, and do not pollute global hooks.
- [ ] Tests include timeouts if the publisher might not terminate.
- [ ] I used `StepVerifier` for **pipelines** and `WebTestClient` for **HTTP contracts**.
- [ ] Reactor Core and `reactor-test` versions align with the module's Spring Boot version.

**Conclusion:** Reactive stream tests must verify **the right elements, the right order, the right terminal signal, and the right classification of rejected data**. `expectNext`/`expectNextSequence` verify ordering; `hasDiscardedExactly` and `doOnDiscard` verify elements rejected by `filter`/`skip`; `hasDropped` is reserved for abnormal `onNextDropped` signals. Never equate "did not appear downstream" with "was discarded".

### Official Documentation

- [Project Reactor — Testing with StepVerifier](https://projectreactor.io/docs/core/release/reference/testing.html)
- [Project Reactor — Dealing with Objects that Need Cleanup](https://projectreactor.io/docs/core/release/reference/advancedFeatures/cleanup.html)
- [Reactor Test Javadoc — StepVerifier](https://projectreactor.io/docs/test/release/api/reactor/test/StepVerifier.html)
- [Reactor Test Javadoc — Assertions](https://projectreactor.io/docs/test/release/api/reactor/test/StepVerifier.Assertions.html)
- [Reactor Core Javadoc — Flux](https://projectreactor.io/docs/core/release/api/reactor/core/publisher/Flux.html)

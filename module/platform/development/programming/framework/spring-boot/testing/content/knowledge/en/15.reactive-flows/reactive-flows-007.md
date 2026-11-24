# PublisherProbe for Verifying Fallback Branch Subscription

## 1. Why Is Checking the Return Value Alone Not Enough?

In a **Reactive** flow using Project Reactor, logic frequently chooses between a **primary source** and a **fallback branch**. For example: read from cache; if not found, call a backup source; or execute a task, and if there is no command, send a "no work" signal.

~~~text
                       primary Publisher
                               |
                     subscribe / request
                               |
                    onNext? / onComplete?
                        /             \
                  has value       empty completion
                      |                  |
                      v                  v
                 keep result      subscribe fallback
                      |                  |
                      +--------+---------+
                               |
                         downstream
~~~

A test using `StepVerifier` to compare the final result is very useful:

~~~java
StepVerifier.create(primary.switchIfEmpty(fallback))
        .expectNext("cached")
        .verifyComplete();
~~~

Yet getting `"cached"` **does not always prove the fallback branch ran**: the primary source could also emit `"cached"`. An even trickier case is **`Mono<Void>`**: both primary and fallback merely complete, so either path yields the exact same `onComplete` signal with no `onNext` to distinguish them.

`PublisherProbe` from the `reactor-test` artifact solves this problem. It wraps a `Publisher` and records whether that branch **was subscribed to, requested from, or cancelled**. After the test actually subscribes to the stream via `StepVerifier`, you inspect the probe to confirm which path ran.

**Important note on the lesson title:** "fallback is subscribed" here means the **fallback branch is actually chosen and receives a subscription**, not that a Spring bean is registered in the `ApplicationContext`. Placing `fallback` inside `switchIfEmpty(...)` is merely *declaring/assembling* the flow; it is **not proof that the fallback was used**.

## 2. Three Phases to Distinguish: Assembly, Subscription, and Signals

Reactive Streams follows a key principle: most Reactor publishers are **lazy/cold**. When writing an operator chain, you are usually **building a task description** rather than executing most of the behavior.

~~~java
PublisherProbe<String> backup = PublisherProbe.of(
        Mono.just("from-backup")
);

Mono<String> result = Mono.<String>empty()
        .switchIfEmpty(backup.mono());

// Up to here is assembly only: no downstream subscriber yet.
~~~

In this snippet, `backup.mono()` creates the probed publisher, yet **no downstream subscription exists**. Only when the test runs:

~~~java
StepVerifier.create(result)
        .expectNext("from-backup")
        .verifyComplete();

backup.assertWasSubscribed();
~~~

are subscription, data, and completion verified.

Four kinds of signals must typically be kept distinct:

| Event | Meaning | Example |
| --- | --- | --- |
| `subscribe` | Subscriber attaches to Publisher; branch was entered | `fallback.assertWasSubscribed()` |
| `request(n)` | Subscriber issues **demand** for data per Reactive Streams | `fallback.assertWasRequested()` |
| `onNext(value)` | A data element was emitted | `StepVerifier.expectNext(...)` |
| `onComplete` / `onError` / cancellation | Normal completion, error completion, or subscription cancellation | `verifyComplete()`, `expectError...`, `assertWasCancelled()` |

**Being subscribed does not mean a value was emitted.** A subscribed `Mono.empty()` completes immediately with no `onNext`. Likewise, `assertWasRequested()` only asserts at least one data request occurred, **not that the publisher emitted any data**.

### When Does `switchIfEmpty` Choose the Fallback?

`Mono<T>.switchIfEmpty(alternative)` and `Flux<T>.switchIfEmpty(alternative)` switch to `alternative` when **upstream completes without emitting any elements**.

- `Mono.just("A")`: emits one element → does **not** subscribe to fallback.
- `Mono.empty()`: completes with zero elements → **subscribes** to fallback.
- `Mono.error(exception)`: terminates with error → **not** an empty case; `switchIfEmpty` does not handle errors.
- `Mono.never()`: emits nothing, never completes, never errors → **no** condition to switch to fallback; if the test cancels, fallback is still never subscribed.

Never equate "no data seen within some duration" with "the source completed empty". To fall back on timeout or error, use operators with matching semantics such as `timeout(...)` or `onErrorResume(...)`.

## 3. Core API of `reactor.test.publisher.PublisherProbe`

Exact imports:

~~~java
import reactor.test.publisher.PublisherProbe;
import reactor.test.StepVerifier;
~~~

Commonly used tools:

| API | Role | What to Remember |
| --- | --- | --- |
| `PublisherProbe.empty()` | Creates a probe that emits no data, only completes | Especially useful with `Mono<Void>` |
| `PublisherProbe.of(Publisher)` | Wraps a real Publisher and preserves its signals | Suitable when fallback must return data |
| `probe.mono()` | Gets a probed `Mono<T>` | For `Mono.switchIfEmpty` |
| `probe.flux()` | Gets a probed `Flux<T>` | For `Flux.switchIfEmpty` |
| `probe.assertWasSubscribed()` | Asserts subscribed at least once | Call after `StepVerifier.verify...` |
| `probe.assertWasNotSubscribed()` | Asserts branch was never subscribed | Crucial for the primary-with-data path |
| `probe.assertWasRequested()` / `assertWasNotRequested()` | Checks demand events | Does not replace assertions on `onNext` |
| `probe.assertWasCancelled()` / `assertWasNotCancelled()` | Checks cancellation | Distinguishes normal completion from cancellation |

One probe can expose both `mono()` and `flux()`, yet **both share the same probe's recorded state**. Do not reuse the same probe across multiple independent cases and treat `assertWasSubscribed()` as evidence solely for the final case; an earlier subscription may have flipped the flag to true.

### How Does `empty()` Differ from `of(...)`?

~~~java
PublisherProbe<Void> completionOnly = PublisherProbe.empty();
Mono<Void> cleanup = completionOnly.mono();
~~~

This publisher only emits a completion signal, letting tests observe a **value-less** branch. For a fallback that emits a value:

~~~java
PublisherProbe<String> withValue = PublisherProbe.of(
        Mono.just("backup-result")
);
Mono<String> backup = withValue.mono();
~~~

The second probe **replays `"backup-result"` from the wrapped Publisher** while recording subscription/request/cancel. It does not invent other values or turn an error source into success.

**`PublisherProbe` does not assert values, item order, or exceptions.** It records signals about branch usage. Use `StepVerifier` for data/completion/errors, combined with `PublisherProbe` for control flow; pair with Mockito `verify` to check Java-level collaborator calls when appropriate.

## 4. Quickest Example: Proving the Fallback Was Subscribed To

Example needing only Reactor and `reactor-test`:

~~~java
PublisherProbe<String> fallback = PublisherProbe.of(
        Mono.just("from-cache")
);

Mono<String> flow = Mono.<String>empty()
        .switchIfEmpty(fallback.mono());

StepVerifier.create(flow)
        .expectNext("from-cache")
        .verifyComplete();

fallback.assertWasSubscribed();
fallback.assertWasRequested();
fallback.assertWasNotCancelled();
~~~

Because upstream is `Mono.empty()`, when the test subscribes, Reactor switches to `fallback`. The test proves **two contracts**: `"from-cache"` is emitted properly, and `fallback` was actually subscribed to.

Swapping the primary source:

~~~java
PublisherProbe<String> fallback = PublisherProbe.of(
        Mono.just("from-cache")
);

Mono<String> flow = Mono.just("from-primary")
        .switchIfEmpty(fallback.mono());

StepVerifier.create(flow)
        .expectNext("from-primary")
        .verifyComplete();

fallback.assertWasNotSubscribed();
fallback.assertWasNotRequested();
~~~

Here, the primary result is preserved and the fallback does not run. **Symmetric tests** catch bugs that a single happy-path test misses.

**Important note on test scope:** the snippets above are **illustrative method bodies**, not standalone compilable Java files with `class`/`import`. Sections 7 and 8 present complete compilable JUnit Jupiter test files.

## 5. Special Pitfall: `Mono<Void>` Has No Value to Observe

A `Mono<Void>` can represent "task completed" while **emitting zero elements**. Consequently, both branches can yield the same terminal signal:

~~~text
Source has command "refresh"
    → gateway.execute("refresh") returns Mono<Void>
    → onComplete

Source has no command
    → runs fallback Mono<Void>
    → onComplete
~~~

Running `StepVerifier.create(result).verifyComplete()` PASSES in both cases; **you cannot tell which path ran** without a probe.

A common mistake:

~~~java
// Wrong if the goal is falling back ONLY when the COMMAND SOURCE is empty.
return commandSource
        .flatMap(gateway::execute)  // execute returns Mono<Void>.
        .switchIfEmpty(emptyFallback);
~~~

Even when `commandSource` emits a command, `gateway.execute(...)` completes **with no `onNext`**, making the `flatMap` output empty. Placing `switchIfEmpty` **afterward** sees an empty stream and subscribes to `emptyFallback` **even though the command already ran**.

This is a semantic bug caused by **putting the operator in the wrong position**, not a timing or Mockito issue.

### Correct Design in the Example

Place `switchIfEmpty` at the **point still carrying the `String` command signal**, before converting the command into `Mono<Void>`:

~~~java
Mono<String> selected = commandSource
        .switchIfEmpty(emptyFallback.then(Mono.<String>empty()));

return selected.flatMap(gateway::execute).then();
~~~

When primary has a command, `selected` emits the `String`, skips fallback, and flows into `gateway.execute`. When primary is empty, the alternative publisher **subscribes to `emptyFallback`**, waits for it to finish, and completes empty **without calling `gateway`**.

`emptyFallback.then(Mono.<String>empty())` matches the `Mono<String>` type expected by `switchIfEmpty` while preserving the `Mono<Void>` behavior of the fallback. This avoids inventing a fake domain "sentinel value".

**Rule for reading Reactor chains:** `switchIfEmpty` does not know your business definition of "has a command"; it only checks whether **upstream at that exact operator position emitted an `onNext` or not**. Operators like `then()`, `ignoreElement()`, or `flatMap` into a completion-only Publisher change whether `onNext` exists.

## 6. Runnable Project Structure and Dependencies

The main example is a **unit test** for a reactive component usable in a Spring Boot 3.5.x, Java 17/JUnit Jupiter, Project Reactor, and Mockito application. We **do not start a Spring context** because the goal is proving Publisher routing, not bean wiring or HTTP.

Main files:

~~~text
src/main/java/com/example/reactivetest/
  CommandGateway.java
  CommandFlow.java
src/test/java/com/example/reactivetest/
  CommandFlowTest.java
  PublisherProbeBranchTest.java
~~~

In a Spring Boot 3.5.x project using Gradle Groovy DSL with the Spring Boot plugin, repositories, Java 17 toolchain, and dependency management already configured, the relevant configuration is:

~~~groovy
dependencies {
    implementation 'org.springframework.boot:spring-boot-starter-webflux'

    testImplementation 'org.springframework.boot:spring-boot-starter-test'
    testImplementation 'io.projectreactor:reactor-test'
}

tasks.named('test', Test) {
    useJUnitPlatform()
}
~~~

`reactor-test` provides `StepVerifier` and `PublisherProbe`. Declare `testImplementation 'io.projectreactor:reactor-test'` explicitly so the example does not rely on assuming another starter pulls it transitively. The Spring Boot BOM manages compatible Reactor versions, so avoid mixing mismatched `reactor-core` and `reactor-test` versions.

`spring-boot-starter-webflux` provides `Mono`/`Flux` and the Reactive stack; in a pure Java module using Reactor, you can declare `reactor-core` and `reactor-test` directly alongside JUnit/Mockito instead of the WebFlux starter. **`@SpringBootTest` is not needed** for these unit test examples.

## 7. Complete Java 17 Example: `Mono<Void>` Fallback Branch

### 7.1. Interface Representing the Real Task

**File `src/main/java/com/example/reactivetest/CommandGateway.java`:**

~~~java
package com.example.reactivetest;

import reactor.core.publisher.Mono;

public interface CommandGateway {
    Mono<Void> execute(String command);
}
~~~

In production, an implementation might write an audit log, publish a message, or invoke an async API. Unit tests mock the gateway to avoid external side effects.

### 7.2. Branching Flow with `switchIfEmpty` in the Right Position

**File `src/main/java/com/example/reactivetest/CommandFlow.java`:**

~~~java
package com.example.reactivetest;

import java.util.Objects;

import reactor.core.publisher.Mono;

public final class CommandFlow {
    private final CommandGateway gateway;

    public CommandFlow(CommandGateway gateway) {
        this.gateway = Objects.requireNonNull(gateway, "gateway");
    }

    public Mono<Void> processOrFallback(
            Mono<String> commandSource,
            Mono<Void> emptyFallback
    ) {
        Objects.requireNonNull(commandSource, "commandSource");
        Objects.requireNonNull(emptyFallback, "emptyFallback");

        Mono<String> selected = commandSource.switchIfEmpty(
                emptyFallback.then(Mono.<String>empty())
        );

        return selected.flatMap(gateway::execute).then();
    }
}
~~~

Method contract:

- Primary emits a command: calls `gateway.execute(command)` and waits for the returned Publisher to finish; **does not run fallback**.
- Primary completes empty: subscribes to and completes `emptyFallback`; **does not call gateway**.
- Primary emits an error: propagates the error downstream; **does not automatically run fallback**.
- Gateway emits an error: propagates the error downstream; **does not automatically run fallback**.
- Returns `Mono<Void>`, because callers only care whether processing completed or failed, not a `String` result.

`Objects.requireNonNull` validates object parameters when the method is called without subscribing or blocking the stream. Interactions with source/gateway/fallback are orchestrated by Reactor when downstream subscribes.

### 7.3. JUnit Jupiter and MockitoExtension Test Suite

**File `src/test/java/com/example/reactivetest/CommandFlowTest.java`:**

~~~java
package com.example.reactivetest;

import org.junit.jupiter.api.BeforeEach;
import org.junit.jupiter.api.Test;
import org.junit.jupiter.api.extension.ExtendWith;

import org.mockito.Mock;
import org.mockito.junit.jupiter.MockitoExtension;

import reactor.core.publisher.Mono;
import reactor.test.StepVerifier;
import reactor.test.publisher.PublisherProbe;

import static org.mockito.Mockito.verify;
import static org.mockito.Mockito.verifyNoInteractions;
import static org.mockito.Mockito.when;

@ExtendWith(MockitoExtension.class)
class CommandFlowTest {

    @Mock
    CommandGateway gateway;

    CommandFlow flow;

    @BeforeEach
    void setUp() {
        flow = new CommandFlow(gateway);
    }

    @Test
    void emptyPrimary_subscribesFallbackAndDoesNotRunGateway() {
        PublisherProbe<Void> fallback = PublisherProbe.empty();

        Mono<Void> result = flow.processOrFallback(
                Mono.empty(),
                fallback.mono()
        );

        StepVerifier.create(result)
                .verifyComplete();

        fallback.assertWasSubscribed();
        fallback.assertWasRequested();
        fallback.assertWasNotCancelled();
        verifyNoInteractions(gateway);
    }

    @Test
    void nonEmptyPrimary_executesGatewayWithoutFallback() {
        PublisherProbe<Void> fallback = PublisherProbe.empty();
        PublisherProbe<Void> executePublisher = PublisherProbe.of(
                Mono.empty()
        );

        when(gateway.execute("refresh"))
                .thenReturn(executePublisher.mono());

        Mono<Void> result = flow.processOrFallback(
                Mono.just("refresh"),
                fallback.mono()
        );

        StepVerifier.create(result)
                .verifyComplete();

        verify(gateway).execute("refresh");

        executePublisher.assertWasSubscribed();
        executePublisher.assertWasRequested();
        executePublisher.assertWasNotCancelled();

        fallback.assertWasNotSubscribed();
        fallback.assertWasNotRequested();
    }

    @Test
    void sourceError_doesNotTriggerEmptyFallback() {
        PublisherProbe<Void> fallback = PublisherProbe.empty();

        Mono<Void> result = flow.processOrFallback(
                Mono.error(new IllegalStateException("source unavailable")),
                fallback.mono()
        );

        StepVerifier.create(result)
                .expectErrorMatches(error ->
                        error instanceof IllegalStateException
                                && "source unavailable".equals(
                                        error.getMessage()
                                ))
                .verify();

        fallback.assertWasNotSubscribed();
        verifyNoInteractions(gateway);
    }

    @Test
    void gatewayError_propagatesWithoutUsingFallback() {
        PublisherProbe<Void> fallback = PublisherProbe.empty();

        when(gateway.execute("refresh"))
                .thenReturn(Mono.error(
                        new IllegalArgumentException("bad command")
                ));

        Mono<Void> result = flow.processOrFallback(
                Mono.just("refresh"),
                fallback.mono()
        );

        StepVerifier.create(result)
                .expectErrorMatches(error ->
                        error instanceof IllegalArgumentException
                                && "bad command".equals(error.getMessage()))
                .verify();

        verify(gateway).execute("refresh");
        fallback.assertWasNotSubscribed();
    }

    @Test
    void neverCompletingPrimary_doesNotSelectFallbackBeforeCancel() {
        PublisherProbe<Void> fallback = PublisherProbe.empty();

        Mono<Void> result = flow.processOrFallback(
                Mono.never(),
                fallback.mono()
        );

        StepVerifier.create(result)
                .thenCancel()
                .verify();

        fallback.assertWasNotSubscribed();
        verifyNoInteractions(gateway);
    }
}
~~~

**Explanation of assertions:**

| Case | `StepVerifier` Result | Probe Result | Collaborator |
| --- | --- | --- | --- |
| Empty primary | `verifyComplete()` | Fallback subscribed + requested, not cancelled | Gateway never called |
| Primary with `"refresh"` | `verifyComplete()` | Fallback not subscribed; gateway's publisher subscribed | Gateway called with exact command |
| Primary errors | `expectErrorMatches(...)` | Fallback not subscribed | Gateway never called |
| Gateway errors | `expectErrorMatches(...)` | Fallback not subscribed | Gateway was called |
| Primary never completes | Test explicitly calls `thenCancel()` | Fallback not subscribed | Gateway never called |

In the command case, the test uses **two separate probes**. `verify(gateway).execute("refresh")` confirms the mock method was called, while `executePublisher.assertWasSubscribed()` confirms **the `Mono` returned by the gateway was actually subscribed to downstream**. These are two distinct events, especially crucial in reactive APIs: calling a method returning a `Mono` does not mean side effects inside the Publisher ran.

`verifyComplete()` prints nothing and returns no data (the flow is `Mono<Void>`); the probe provides the routing proof between branches. Each test creates fresh probes so subscription state never leaks from prior cases.

## 8. Complete Example for Value-Bearing Fallbacks and `Flux`

`PublisherProbe.empty()` fits completion-only branches; when a fallback must **emit data**, use `PublisherProbe.of(...)` to preserve the wrapped Publisher's signals.

**File `src/test/java/com/example/reactivetest/PublisherProbeBranchTest.java`:**

~~~java
package com.example.reactivetest;

import org.junit.jupiter.api.Test;

import reactor.core.publisher.Flux;
import reactor.core.publisher.Mono;
import reactor.test.StepVerifier;
import reactor.test.publisher.PublisherProbe;

class PublisherProbeBranchTest {

    @Test
    void emptyMono_subscribesValueFallback() {
        PublisherProbe<String> fallback = PublisherProbe.of(
                Mono.just("cached")
        );

        Mono<String> result = Mono.<String>empty()
                .switchIfEmpty(fallback.mono());

        StepVerifier.create(result)
                .expectNext("cached")
                .verifyComplete();

        fallback.assertWasSubscribed();
        fallback.assertWasRequested();
        fallback.assertWasNotCancelled();
    }

    @Test
    void nonEmptyMono_doesNotSubscribeValueFallback() {
        PublisherProbe<String> fallback = PublisherProbe.of(
                Mono.just("cached")
        );

        Mono<String> result = Mono.just("live")
                .switchIfEmpty(fallback.mono());

        StepVerifier.create(result)
                .expectNext("live")
                .verifyComplete();

        fallback.assertWasNotSubscribed();
        fallback.assertWasNotRequested();
    }

    @Test
    void emptyFlux_subscribesMultiValueFallback() {
        PublisherProbe<String> fallback = PublisherProbe.of(
                Flux.just("backup-A", "backup-B")
        );

        Flux<String> result = Flux.<String>empty()
                .switchIfEmpty(fallback.flux());

        StepVerifier.create(result)
                .expectNext("backup-A", "backup-B")
                .verifyComplete();

        fallback.assertWasSubscribed();
        fallback.assertWasRequested();
        fallback.assertWasNotCancelled();
    }

    @Test
    void cancellingFallbackIsObservable() {
        PublisherProbe<String> fallback = PublisherProbe.of(
                Flux.<String>never()
        );

        Flux<String> result = Flux.<String>empty()
                .switchIfEmpty(fallback.flux());

        StepVerifier.create(result)
                .thenCancel()
                .verify();

        fallback.assertWasSubscribed();
        fallback.assertWasCancelled();
    }

    @Test
    void errorFallbackUsesOnErrorResumeInsteadOfSwitchIfEmpty() {
        PublisherProbe<String> recovery = PublisherProbe.of(
                Mono.just("offline-cache")
        );

        Mono<String> result = Mono.<String>error(
                new IllegalStateException("remote unavailable")
        ).onErrorResume(error -> recovery.mono());

        StepVerifier.create(result)
                .expectNext("offline-cache")
                .verifyComplete();

        recovery.assertWasSubscribed();
        recovery.assertWasRequested();
    }
}
~~~

Across all five cases, **`StepVerifier`** asserts data, completion, or cancellation actions, while **`PublisherProbe`** asserts which branch was subscribed to and which lifecycle signals hit that branch. For `Flux`, use `probe.flux()` instead of `probe.mono()` when multiple elements must flow through.

### A Note on Cancellation

In the `Flux.never()` case, `fallback` **is subscribed to** without emitting data or completion. `StepVerifier.thenCancel()` cancels the subscription, so `assertWasCancelled()` is the expected assertion.

**Do not put `assertWasNotCancelled()` into every test out of habit.** A branch can validly be subscribed, requested, and subsequently cancelled by `take(1)`, timeouts, or subscriber cancellation. Assert cancellation according to the designed lifecycle.

### A Note That Probes Do Not Identify Value Origins

If the output is `"cached"`, `StepVerifier.expectNext("cached")` only verifies the value. `fallback.assertWasSubscribed()` confirms the fallback participated. Conversely, `assertWasSubscribed()` does not prove the value was `"cached"`. The two sets of assertions complement rather than replace each other.

## 9. Sound Proof: Testing Both the Fallback Path and the Primary Path

A test suite covering only empty primaries is incomplete. If someone breaks the code to "always call fallback", the fallback test still PASSES. You need at least two opposing paths:

~~~text
Given primary = empty
When  StepVerifier subscribes to the pipeline
Then  fallback is subscribed/requested; output matches

Given primary = just(value)
When  StepVerifier subscribes to the pipeline
Then  fallback is not subscribed; output comes from primary
~~~

For operations with side effects, also verify:

~~~text
Given primary = empty
Then  gateway is not called

Given primary = just(command)
Then  gateway is called with command
  And publisher returned by gateway is subscribed
  And fallback is not subscribed
~~~

**Flow-control testing discipline:**

- Assert **downstream signals** (value/completion/error) to verify the caller-visible contract.
- Assert **fallback subscription** to prove branch selection.
- Assert **execution publisher subscription** when proving reactive work actually ran, not just that a Java method was invoked.
- Use Mockito `verify` for collaborator interactions outside the Publisher when appropriate.
- Never write tests relying on log counts, unguaranteed ordering, or `static` mutable state shared across tests.

A mock returning `Mono.empty()` emits no `onNext`; calling only `verify(mock).method(...)` does not prove the pipeline subscribed to that `Mono`. Wrap the returned `Mono` in `PublisherProbe.of(...)` when that proof matters.

## 10. `onErrorResume` Is Not `switchIfEmpty`

In Reactor:

| Condition | `switchIfEmpty(fallback)` | `onErrorResume(error -> fallback)` |
| --- | --- | --- |
| Upstream emits data and completes | Does not use fallback | Does not use fallback |
| Upstream completes **without emitting anything** | **Subscribes to fallback** | Does not use fallback |
| Upstream emits `onError` | Error propagates (unless handled elsewhere) | **May subscribe to recovery** |
| Upstream `never()` | Does not trigger | Does not trigger |

If requirements say "on cache miss, call backup source", `switchIfEmpty` fits when a cache miss is represented by `Mono.empty()`. If requirements say "when remote errors, serve cached value", `onErrorResume` fits while constraining which error types allow fallback.

Example restricting fallback to a single error type:

~~~java
Mono<String> recovered = primary.onErrorResume(
        java.io.IOException.class,
        error -> fallbackProbe.mono()
);
~~~

This is an **illustrative snippet** requiring `primary` of type `Mono<String>`, `fallbackProbe` of type `PublisherProbe<String>`, and proper imports. This operator runs fallback on `IOException`; other errors keep propagating per `onErrorResume` semantics.

**Never use `switchIfEmpty` to catch exceptions.** Likewise, never use `onErrorResume` to handle `Mono.empty()`, since emptiness is not an error. Test both empty and error paths separately whenever an API exposes both.

### Watch Out with `defaultIfEmpty`

`defaultIfEmpty(value)` replaces an empty stream with **a static value**; there is no alternative `Publisher` to wrap with `PublisherProbe`. To test an actual fallback flow, use `switchIfEmpty(fallbackPublisher)`.

With `Mono<Void>`, there is no valid `Void` value to emit as a default in standard usage, so `PublisherProbe.empty()` + `switchIfEmpty` or repositioning the operator is usually more suitable.

## 11. Lazy Fallback: Wiring a Publisher Is Not the Same as Executing Its Factory

A subtle difference:

~~~java
Mono<String> result = primary.switchIfEmpty(
        expensiveFallbackFactory()
);
~~~

Here the **Java call** `expensiveFallbackFactory()` runs during chain assembly, because Java evaluates method arguments before calling `switchIfEmpty`. If the factory merely returns a cold `Mono` with no side effects, that is usually harmless. However, if the factory **reads files, writes logs, makes synchronous API calls, or mutates state directly in its body**, that work executes **even when `primary` emits a value and fallback is never subscribed to**.

To defer **calling the factory itself** until fallback is chosen:

~~~java
Mono<String> result = primary.switchIfEmpty(
        Mono.defer(() -> expensiveFallbackFactory())
);
~~~

`Mono.defer` takes a `Supplier` that builds the publisher **only upon subscription** to that branch, not when assembling the operator. Without a fallback subscription, the factory is never invoked.

You can wrap it to test the path:

~~~java
PublisherProbe<String> fallback = PublisherProbe.of(
        Mono.defer(() -> expensiveFallbackFactory())
);

Mono<String> result = primary.switchIfEmpty(fallback.mono());
~~~

`fallback.assertWasNotSubscribed()` proves the wrapped Publisher was not subscribed to. **It does not automatically prove an arbitrary factory was never called elsewhere**, such as outside `Mono.defer`. When proving the exact invocation count of the factory matters, pair Mockito `verify(..., never())` or an isolated counter alongside the probe.

### Does `Mono.defer` Solve Every Timing Problem?

No. It provides **lazy assembly** for the factory-produced source; logic inside the publisher must still be non-blocking, handle exceptions cleanly, and be subscribed by tests to observe outcomes. Avoid calling `block()` on Reactor event loops, and do not construct hot publishers with side effects at creation time expecting an outer `Mono.defer` to undo work already done.

## 12. Backpressure, Request, and Cancel: Three Distinct Questions

`PublisherProbe` clarifies three events:

- **Subscribed:** the branch was entered. `assertWasSubscribed()`.
- **Requested:** the subscriber sent positive demand to the probe. `assertWasRequested()`. Does not prove an item was emitted.
- **Cancelled:** the subscriber or downstream chain cancelled the subscription prior to normal completion/error. `assertWasCancelled()`.

`StepVerifier.create(publisher)` in typical usage creates the subscription and issues demand matching expectations. For tests controlling demand explicitly, pass `initialRequest`:

~~~java
PublisherProbe<String> backup = PublisherProbe.of(
        Mono.just("ready")
);

StepVerifier.create(
        Mono.<String>empty().switchIfEmpty(backup.mono()),
        0
)
        .thenRequest(1)
        .expectNext("ready")
        .verifyComplete();

backup.assertWasSubscribed();
backup.assertWasRequested();
~~~

This is an illustrative method-body snippet; `StepVerifier.create(..., 0)` starts with zero demand, then `thenRequest(1)` lets one element flow through. In complex chains with operator prefetching/request transformations, **do not infer exact request counts from `assertWasRequested()`**, as that method only asserts "at least one request occurred". When exact request counts or backpressure matter, use dedicated tools and contracts.

**Do not reuse a probe across multiple subscriptions** if asserting per-attempt behavior; probe flags accumulate state. In tests involving `retry` or `repeat`, decide whether you need "at least once" or an **exact subscription count**. Simple `WasSubscribed` assertions alone do not enforce "exactly once".

## 13. How `PublisherProbe`, `TestPublisher`, `StepVerifier`, and Mockito Differ

| Tool | Question It Answers | What It Cannot Do Alone |
| --- | --- | --- |
| `StepVerifier` | Did the stream emit expected values, complete/error, honor timing/cancel? | Cannot tell if a fallback emitting the same signal as primary was used without a probe |
| `PublisherProbe` | Was this Publisher/branch subscribed, requested, or cancelled? | Does not verify detailed values, order, or error messages |
| `TestPublisher` | Programmatically emit `next`/`complete`/`error` from upstream in tests | Does not replace downstream outcome assertions |
| Mockito `@Mock`/`verify` | Which collaborator Java method was called and with what arguments? | Does not guarantee the returned `Publisher` was subscribed to |
| `@WebFluxTest` + `WebTestClient` | How do WebFlux HTTP routes, filters, and serialization behave? | Cannot directly verify internal fallback branches if responses look identical |

### Why Not Always Use `TestPublisher`?

`TestPublisher` shines when tests must **actively push signals** on a controlled schedule. `PublisherProbe` is simpler when you only need to know **whether a fallback publisher was used** and the real source can be `Mono.empty()`, `Mono.just(...)`, or `Flux.just(...)`.

Although `TestPublisher` shares the probe interface in Reactor's API, most control-flow tests should use `PublisherProbe.empty()` / `PublisherProbe.of(...)` as Reactor guides recommend, rather than manually driving signals unnecessarily.

### Why Not Just Use an `AtomicBoolean`?

An `AtomicBoolean` inside `doOnSubscribe` or `doOnNext` can record certain events, yet checking subscribe/request/cancel across many tests creates boilerplate and easily misses edge cases. `PublisherProbe` was built specifically for that job. Conversely, when proving a **business side effect committed**, a subscription assertion is insufficient; use business-level assertions or proper integration tests.

## 14. Applying This in Spring Boot / Spring WebFlux

The primary example uses **JUnit Jupiter + `MockitoExtension`**, not `@SpringBootTest`. That is the right choice when testing Java methods returning `Mono`/`Flux` and operator branches. WebFlux does not need to boot an HTTP server just to test a `switchIfEmpty`.

When the method lives inside a Spring service:

~~~java
@Service
public class QuoteLookupService {
    private final QuoteRepository repository;
    private final QuoteFallbackClient fallbackClient;

    public Mono<Quote> find(String id) {
        return repository.findById(id)
                .switchIfEmpty(Mono.defer(
                        () -> fallbackClient.load(id)
                ));
    }
}
~~~

This is an **illustrative skeleton**, not a standalone file; it needs fields, constructor, interfaces, models, and imports. In unit tests, mock `QuoteRepository` and `QuoteFallbackClient` with Mockito, then return `PublisherProbe.of(Mono.just(...))` from the client mock. To also verify **whether the factory method was called**, add Mockito `verify(fallbackClient).load(id)` / `verify(..., never())`.

A `@WebFluxTest` HTTP slice typically tests controllers/requests/responses via `WebTestClient` while mocking services outside the slice. It is not the right place to verify internal branches of a service **that was mocked away**. If tests must verify the real service alongside Spring wiring, consider `@SpringBootTest`/`@Import` appropriately; you can still wrap Publishers returned by mocked repositories/clients with `PublisherProbe`.

**Do not use `block()` just to assert** in a reactive test. `StepVerifier` handles subscribing and managing expectations; when using `WebTestClient`, the test client drives HTTP stream subscriptions through the framework.

## 15. Debugging a Misbehaving Fallback Case

| Symptom | Common Cause | How to Fix |
| --- | --- | --- |
| `assertWasNotSubscribed` FAILS even though primary has data | `switchIfEmpty` placed after `then()` or after converting to `Mono<Void>` | Move `switchIfEmpty` upstream where the value to check still exists |
| `assertWasSubscribed` FAILS when primary is empty | Missing downstream subscription, or pipeline did not use the passed probe | Call `StepVerifier.verify...` on the exact returned flow and check wiring |
| Test PASSES with `verifyComplete` yet fallback wasn't used | Both branches complete empty | Add `PublisherProbe` |
| `assertWasRequested` FAILS | Subscriber issued zero demand or cancelled early | Check `initialRequest`/`thenRequest`, operators, and cancellation |
| `assertWasNotCancelled` FAILS | `take`, timeout, `thenCancel`, or downstream cancel occurred | Assert cancellation per contract instead of assuming completion |
| Fallback runs even when unnecessary | Factory has eager side effects at assembly time | Wrap factory inside `Mono.defer` |
| Fallback never runs on `Mono.error` | `switchIfEmpty` does not handle errors | Use `onErrorResume` when contract specifies error recovery |
| Gateway method was called yet side effect never ran | Returned Publisher was never subscribed | Wrap returned publisher in a probe and assert subscription |
| Test hangs on `Mono.never()` | Test waits for completion on a non-completing stream | Use `thenCancel` or deliberate test timeouts |
| Second test sees probe "already subscribed" | Probe reused across subscriptions or tests | Create a fresh probe per test or manage state deliberately |
| `PublisherProbe.empty()` does not emit expected value | Empty factory only completes | Use `PublisherProbe.of(Mono.just(value))` |
| Test passes in IDE alone, fails in suite | Shared state, test ordering dependency, or unreset mocks | Isolate probes, stubbing, and test data per test |

### Three-Layer Debugging Approach

1. **Upstream data:** did the source actually emit `onNext`, complete empty, or signal `onError`?
2. **Operator placement:** is there a `then`/`ignoreElement`/`flatMap(... Mono<Void>)` before `switchIfEmpty` dropping the element?
3. **Path observation:** did `StepVerifier` subscribe to the right publisher? Is the probe wired into the real fallback? Do subscribe/request/cancel assertions match the contract?

As a final step when needed, combine `StepVerifier` with selective `doOnSubscribe`/`doOnEach`/`log()` for diagnosis; avoid letting logs replace deterministic assertions.

## 16. Practical Checklist

A reliable fallback test using `PublisherProbe` should:

- [ ] Identify the exact **fallback trigger**: empty, error, or timeout, and pick the matching operator.
- [ ] Verify **`switchIfEmpty` placement** comes before meaningful data signals are discarded.
- [ ] Choose `PublisherProbe.empty()` to observe completion-only branches, and `PublisherProbe.of(...)` when fallback emits data.
- [ ] Wire `probe.mono()`/`probe.flux()` into the actual fallback branch, not an unused Publisher.
- [ ] Use `StepVerifier` to subscribe and verify output/completion/error.
- [ ] After verifying, call `assertWasSubscribed()` or `assertWasNotSubscribed()` per scenario.
- [ ] Check `assertWasRequested()`/cancellation when part of the contract.
- [ ] Cover both **empty primary → fallback used** and **primary with value → fallback not used**.
- [ ] Include error cases when the system must distinguish empty from error.
- [ ] For `Mono<Void>` return types, check that no operator strips `onNext` before `switchIfEmpty`.
- [ ] Avoid relying solely on `verify(mock).method()` when proving the returned Publisher was actually subscribed.
- [ ] Never share probes across independent tests or rely on test execution order.
- [ ] Use `Mono.defer` when lazy factory evaluation is needed to avoid assembly-time side effects.
- [ ] Avoid booting a Spring context when testing pure Java/Reactor control flow.

### Running the Tests

From the directory containing the Gradle Wrapper (Linux/macOS):

~~~bash
./gradlew test --tests "com.example.reactivetest.CommandFlowTest"
./gradlew test --tests "com.example.reactivetest.PublisherProbeBranchTest"
~~~

On Windows:

~~~powershell
.\gradlew.bat test --tests "com.example.reactivetest.CommandFlowTest"
.\gradlew.bat test --tests "com.example.reactivetest.PublisherProbeBranchTest"
~~~

These tests contain no `System.out.println`, so **there is no fixed code-printed stdout**. Gradle/JUnit reports PASS/FAIL counts and task status per configuration; with valid dependencies, all assertions described here are expected to pass. Because this code depends on Reactor, `reactor-test`, JUnit Jupiter, and Mockito, it cannot be compiled/run with bare `javac Test.java` without those libraries on the classpath.

**Key takeaway:** `PublisherProbe` proves whether a fallback branch was **actually subscribed to** at runtime, even when both branches return `Mono<Void>` and both end with `onComplete`. Use it **alongside `StepVerifier`**; test both the selected and unselected paths, and always place `switchIfEmpty` where "upstream is empty" accurately reflects business semantics.

### References

- [Project Reactor — Testing, Checking the Execution Path with PublisherProbe](https://projectreactor.io/docs/core/release/reference/testing.html)
- [Reactor Test — PublisherProbe API](https://projectreactor.io/docs/test/release/api/reactor/test/publisher/PublisherProbe.html)
- [Reactor Core — Reactive Programming and switchIfEmpty](https://projectreactor.io/docs/core/release/reference/reactiveProgramming.html)
- [Spring Boot 3.5 — Testing Spring Boot Applications](https://docs.spring.io/spring-boot/3.5/reference/testing/spring-boot-applications.html)
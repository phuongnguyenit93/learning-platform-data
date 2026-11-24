# Reactive test fails to complete, loses context, or uses the wrong scheduler — Spring Boot WebFlux diagnostics

## 1. Scenario: a hung reactive test does not mean the application is “slow”

A JUnit test verifying `Mono` or `Flux` can hang, time out, receive no values, drop request/trace/security context, or fail only on CI. The surface symptoms often look identical—“waiting forever”—yet the root cause can lie in **subscription**, **demand/backpressure**, **terminal signals**, **schedulers**, **Reactor Context**, **blocking calls**, or how **`StepVerifier`** was written.

This lesson belongs to **Test Troubleshooting** in Spring Boot. The goal is to classify signals before making edits, build a minimal test proving the cause, and pick the right fix. Never treat “keep increasing `Thread.sleep`/timeouts until CI turns green” as a default strategy.

After this lesson, you should be able to:
1. Distinguish **assembly time** from **subscription time**, `onSubscribe`, `request(n)`, `onNext`, `onError`, and `onComplete`.
2. Diagnose tests missing `verify`, unsubscribed publishers, subscribers that never request, `Flux.never()`, infinite sources, and branches lacking a terminal signal.
3. Use `StepVerifier` with real deadlines, expected signals, cancellation, and explicit backpressure demand.
4. Use `StepVerifier.withVirtualTime` properly to test `delay`, `interval`, and `timeout` without waiting in real wall-clock time.
5. Distinguish `publishOn` from `subscribeOn`; pick `Schedulers.parallel()`, `Schedulers.single()`, and `Schedulers.boundedElastic()` appropriately for non-blocking work vs legacy blocking calls.
6. Diagnose per-subscriber `Context`, `contextWrite`, `deferContextual`, context propagation across schedulers, and differences from `ThreadLocal`/MDC.
7. Test WebFlux with `WebTestClient`, understanding the boundary between mock HTTP exchanges and a live server socket.
8. Recognize reactive transaction/security/tracing context and why misplaced `block()` or `subscribe()` breaks tests even when business logic looks reasonable.
9. Protect tests from thread/resource leaks, shared global scheduler state, cancellation issues, CI flakiness, and failures appearing only in parallel runs.

**Example versions:** Java 17+, Spring Boot 3.5.8, Project Reactor managed by the Spring Boot BOM, `reactor-test`, JUnit Jupiter/AssertJ, and Gradle. The code forms a consistent project needing no database, Docker, or external services. Tests are authored as practical source code; **they have not been executed** in the environment where this material was written.

## 2. First mental model: Reactive Streams is a signal protocol

```text
Publisher Mono/Flux
       |
       | subscribe()
       v
Subscriber                         Subscription
       ^                                 |
       | onSubscribe(subscription)       |
       |                                 | request(n)
       |                                 v
       |                 publisher has demand to emit
       |
       +-------- onNext(value) [0..N]
       |
       +-------- onComplete()    OR onError(error)
                  [terminal signal, at most once]
```

A publisher **may do nothing until subscribed**. A subscriber **may have subscribed without requesting yet**. A `Flux` **may emit items and never complete**. These are three distinct mechanisms, even though each prevents the test from reaching its next expectation.

### 2.1. Cold publishers and assembly do not mean execution

```java
AtomicInteger calls = new AtomicInteger();

Mono<String> publisher = Mono.fromSupplier(() -> {
    calls.incrementAndGet();
    return "READY";
});

// Here the pipeline is only assembled; the supplier has not been called yet.
assertThat(calls.get()).isZero();

StepVerifier.create(publisher)
        .expectNext("READY")
        .expectComplete()
        .verify(Duration.ofSeconds(3));

assertThat(calls.get()).isEqualTo(1);
```

This is a fragment placed inside a JUnit method importing `AtomicInteger`, `Mono`, `StepVerifier`, `Duration`, and AssertJ. `StepVerifier.create(...)` builds the verification script; calling `verify(...)` triggers subscription and checks expected events.

Omitting `verify()`/`verifyComplete()`/`verifyError()` lets a test **finish “green” without ever subscribing** to the publisher. Valid tests must actively trigger and verify terminal or cancellation semantics rather than merely constructing a `StepVerifier`.

### 2.2. Mono, Flux, and termination do not imply “at least one value”

| Publisher | Expected outcome | Appropriate test assertion |
|---|---|---|
| `Mono.just("ok")` | One `onNext`, then `onComplete` | `expectNext("ok")`, `expectComplete` |
| `Mono.empty()` | `onComplete`, **no** `onNext` | `verifyComplete` |
| `Mono.error(ex)` | `onError`, **no** `onComplete` | `expectError...` |
| `Mono.never()` | Emits no value/error/complete | cancel or explicit timeout |
| `Flux.range(1,3)` | 1,2,3 then complete | `expectNext(1,2,3)`, complete |
| `Flux.interval(...)` | Infinite stream by default | `take(n)`, cancel, or boundary test |
| `Flux.just(1,2).concatWith(Flux.never())` | Receives 1,2 then hangs | `expectNext(1,2).thenCancel` |
| `Flux.empty()` | Completes immediately | `expectComplete`, do not expect values |

In practice, a pipeline may **terminate early** via `take`, **get cancelled** on client disconnect, or **stop emitting** under backpressure. Assert the matching signals instead of blindly calling `verifyComplete()`.

## 3. Quick triage by where the test stalls

| Symptom | Priority hypothesis | How to confirm |
|---|---|---|
| Test passes yet business code never ran | Missing `verify`, unsubscribed, `Mono` unreturned | `AtomicInteger` side effect/`PublisherProbe`, check `verify` call |
| `expectNext` waits forever, no requests | `initialRequest=0` or custom Subscriber forgot `request(n)` | Inspect `doOnRequest`, add `thenRequest` |
| Received expected values, `verifyComplete` still hangs | Non-completing source: `never`, `interval`, hot stream | Switch expectation to cancellation or fix business termination |
| `expectNoEvent` fails immediately | Subscription itself counts as an event | Place `expectSubscription()` first |
| `withVirtualTime` still waits wall-clock time | Publisher/timer/scheduler created before virtual scheduler, or explicit real scheduler | Build publisher **inside** supplier, inspect scheduler |
| Virtual test hangs without advancing ticks | Forgot `thenAwait`, clock not advanced, task hogs virtual thread | Use `thenAwait`/`expectNoEvent`, avoid endless synchronous loops |
| `IllegalStateException: block()... not supported` | `block()` called on Reactor non-blocking thread | Use non-blocking composition; offload legacy I/O to `boundedElastic` |
| Context key missing | Misplaced `contextWrite`, detached subscription, manual `subscribe` | `deferContextual`, test Context per subscription |
| MDC/`ThreadLocal` lost after `publishOn` | Thread switch does not auto-propagate arbitrary ThreadLocals | Use Reactor Context or properly configured Micrometer Context Propagation |
| Test fails only under parallel CI | Shared scheduler, global `Hooks`, shared context/test data, thread leaks | Run sequentially, then step up concurrency layer by layer |
| `onErrorResume` creates a false green | Error converted into fallback/empty | Test upstream error separately from fallback contract |
| `WebTestClient` times out | Server chain never completes, infinite response stream, blocked backend | Check `onError`/`onComplete`, headers, `WebFilter`, timeouts, Reactor Netty |
| `Thread.sleep` masks the issue | Race condition or unready dependency | `Future`/`StepVerifier`/Awaitility or virtual time |

The most effective debugging strategy is to **minimize the publisher** before raising timeouts:
1. Did subscription happen?
2. Is there demand?
3. Did `onNext`/terminal signals arrive?
4. Did a scheduler switch threads or get blocked?
5. Did Context reach the target subscriber?
6. Is shared state or a long-lived publisher/stream outliving the test?

## 4. `StepVerifier`: verifying the right signals with a deadline

`reactor-test` provides `StepVerifier` to describe expected reactive signals. Pattern:

```java
StepVerifier.create(Mono.just("A"))
        .expectSubscription()
        .expectNext("A")
        .expectComplete()
        .verify(Duration.ofSeconds(3));
```

Every `StepVerifier` test must contain:
- `create(publisher)` or `withVirtualTime(supplier)`.
- Explicit expectations: `expectNext`, `assertNext`, `expectErrorMatches`, `expectComplete`, `thenCancel`, etc.
- **Triggering verification**, usually `verify(Duration)` or a shortcut like `verifyComplete()`/`verifyError()`.
- A reasonable deadline. Default shortcuts carry **no timeout** unless a global default was set; a non-terminating publisher can hang the JUnit worker indefinitely.

### 4.1. Why prefer `verify(Duration)`?

```java
StepVerifier.create(source)
        .expectNext(expected)
        .expectComplete()
        .verify(Duration.ofSeconds(3));
```

This fragment assumes `source` and `expected` are declared. This timeout is the **real verification deadline**, not a tool to turn an infinite stream into a finite one. If the application contract stays open until client cancellation, `expectComplete()` is already wrong; use an explicit `thenCancel()`.

Never replace terminal events with `Thread.sleep(5000)` and `assertTrue(flag)`. Never call `StepVerifier.setDefaultTimeout(...)` inside parallel tests because it mutates static/global state affecting other tests; per-verifier configuration is clearer and safer.

### 4.2. Terminating by error, completion, or cancellation?

```java
// Expect complete:
StepVerifier.create(Flux.just(1, 2))
        .expectNext(1, 2)
        .expectComplete()
        .verify(Duration.ofSeconds(2));

// Expect onError, not onComplete:
StepVerifier.create(Mono.error(
            new IllegalArgumentException("bad input")))
        .expectErrorMatches(ex ->
            ex instanceof IllegalArgumentException
                && "bad input".equals(ex.getMessage()))
        .verify(Duration.ofSeconds(2));

// Expect long-lived stream stays active,
// test explicitly cancels:
StepVerifier.create(
            Flux.just(1, 2).concatWith(Flux.never()))
        .expectNext(1, 2)
        .thenCancel()
        .verify(Duration.ofSeconds(2));
```

These examples fit in a JUnit method with proper imports. The last case **is not a test failing to complete**: cancellation is the contract under test. Note that cancellation alone does not prove upstream released every connection or transaction unless you also add assertions/resource probes.

### 4.3. `expectNoEvent` does not mean “no values seen”

Reactor counts the **subscription signal** as an event when `expectNoEvent` checks a time window.

**Wrong expectation:**

```java
StepVerifier.create(Mono.delay(Duration.ofSeconds(1)))
        .expectNoEvent(Duration.ofMillis(100))
        .expectNext(0L)
        .verifyComplete();
```

This anti-pattern can fail immediately because `onSubscribe` itself fires. In addition, `verifyComplete()` lacks a real timeout if the publisher stalls. Right approach:

```java
StepVerifier.create(Mono.delay(Duration.ofMillis(100)))
        .expectSubscription()
        .expectNoEvent(Duration.ofMillis(20))
        .expectNext(0L)
        .expectComplete()
        .verify(Duration.ofSeconds(3));
```

In real-time tests, scheduler/CI load introduces timing jitter; when testing timing semantics, prefer virtual time over tight millisecond bounds.

## 5. Zero demand/backpressure: subscribed yet emitting nothing

Reactive Streams lets the subscriber control how many elements to receive via `Subscription.request(n)`. On `Flux.range`, when demand is 0, the source emits no `onNext`.

```java
StepVerifier.create(
        Flux.range(1, 5),
        StepVerifierOptions.create().initialRequest(0))
    .expectSubscription()
    .thenRequest(2)
    .expectNext(1, 2)
    .thenRequest(3)
    .expectNext(3, 4, 5)
    .expectComplete()
    .verify(Duration.ofSeconds(3));
```

**Lesson:** If a test sets `initialRequest(0)` and immediately expects `expectNext(1)` without `thenRequest(1)`, the bug is not necessarily a business-code deadlock—the test never sent demand. `StepVerifier` also exposes under-requesting checks to catch mismatches where `expectNextCount` exceeds requested demand.

In production, backpressure affects queues and workloads too: `flatMap` concurrency/prefetch, `onBackpressureBuffer`, downstream cancellation, and Netty response writing. Avoid slapping `request(Long.MAX_VALUE)` everywhere to hide a design flaw when bounded demand is needed.

### 5.1. Empty publisher vs missing demand

`Mono.empty()` emits `onComplete` with no `onNext`. If a test asserts `expectNext("value")`, it fails due to a **contract mismatch**. Use:

```java
StepVerifier.create(Mono.<String>empty())
        .expectComplete()
        .verify(Duration.ofSeconds(2));
```

Distinguish empty from `Mono.never()`: empty finishes cleanly; never emits no terminal event at all.

### 5.2. Hot publishers and subscription races

`Flux.just` and `Mono.fromSupplier` are normally cold: every subscription starts its own lifecycle. `Sinks.Many` or hot streams can emit items before a subscriber attaches, causing the test to miss signals and hang forever.

When testing hot publishers:
- Subscribe before emitting; use `StepVerifier.then(() -> sink.tryEmitNext(...))` or `TestPublisher`.
- With `Sinks.many().multicast().onBackpressureBuffer()`, understand zero-subscriber and buffering behavior.
- Inspect `Sinks.EmitResult` on `tryEmitNext` instead of ignoring `FAIL_ZERO_SUBSCRIBER`/`FAIL_OVERFLOW`.
- Never use `Thread.sleep` to “wait for the subscriber to connect”.
- Ensure explicit termination or cancellation so tests do not leave sinks/subscriptions alive afterward.

Do not swap a hot publisher for a cold one in tests if production contracts demand hot semantics; build an accurate test harness instead.

## 6. Virtual time: fast-forwarding the clock instead of sleeping

`StepVerifier.withVirtualTime` replaces the default timed-operator scheduler with `VirtualTimeScheduler`. Critical requirement: **the publisher/timer must be created after the virtual scheduler becomes active**, which is why the API accepts `Supplier<? extends Publisher>` rather than an already-constructed publisher.

**Right:**

```java
StepVerifier.withVirtualTime(
        () -> Mono.delay(Duration.ofDays(1)))
    .expectSubscription()
    .expectNoEvent(Duration.ofDays(1))
    .expectNext(0L)
    .expectComplete()
    .verify(Duration.ofSeconds(3));
```

This test never sleeps for a real day. `expectNoEvent` right after `expectSubscription` confirms that throughout the virtual day no `onNext` fires before the delay expires.

**Common mistake:**

```java
Mono<Long> alreadyBuilt = Mono.delay(Duration.ofDays(1));

StepVerifier.withVirtualTime(() -> alreadyBuilt)
    .expectSubscription()
    .thenAwait(Duration.ofDays(1))
    .expectNext(0L)
    .verifyComplete();
```

This flawed snippet shows that pre-building the publisher can capture the real scheduler or bind timers before virtual time is installed, preventing the test from using the virtual clock as intended. Always construct the publisher inside the supplier and call `verify(Duration)`.

### 6.1. `thenAwait` vs `expectNoEvent`

- `thenAwait(Duration)`: advances the virtual clock (or waits in real time if not using virtual time); does not assert “no signal”.
- `expectNoEvent(Duration)`: advances the clock while **failing if any signal arrives** during that span; remember subscription counts as an event.
- `then(() -> {...})`: runs an action after previous expectation steps, useful when driving hot publishers.
- `verify(Duration)`: real deadline guarding JUnit if logic fails to terminate.

Calling `thenAwait(Duration.ofDays(1))` while forgetting `expectNext`/completion fails to confirm the timer produced the right signals; always assert the subsequent expected signals.

### 6.2. Why can virtual-time tests still hang?

`VirtualTimeScheduler` is not a universal “time machine” covering every blocking call or thread:
1. The publisher uses an **explicit Scheduler constructed outside** the supplier, bypassing the virtual scheduler.
2. A `Flux` was assembled before `withVirtualTime`, letting an operator capture the real scheduler.
3. Forgetting `thenAwait` or expecting a value before advancing the virtual clock.
4. An infinite synchronous loop or non-yielding `Flux.generate` starves the virtual-time thread.
5. Mixing hot publishers or real external I/O with virtual time makes the test wall-clock dependent.
6. Parallel tests mutate global `Schedulers` factories, `Hooks`, or virtual scheduler state concurrently.
7. Code calls `Thread.sleep` or blocking sockets—virtual time does not accelerate Java wall clocks or networks.

**Policy:** Isolate virtual-time tests, avoid storing default schedulers in static fields, build pipelines inside the supplier, supply a real `verify(Duration)` timeout, and avoid mutating global hooks/schedulers during concurrent tests.

## 7. `publishOn` vs `subscribeOn`: two different execution-switching boundaries

Reactor does not automatically offload every `Mono`/`Flux` onto a new thread. Without an explicit scheduler, most operators run on whichever thread triggered subscription or emitted the signal.

| Operator | Primary effect | Common mistake |
|---|---|---|
| `subscribeOn(scheduler)` | Shifts upstream subscribe/request execution toward source, usually placed near source | Thinking it only affects downstream operators |
| `publishOn(scheduler)` | Switches signal execution for operators **after** it | Thinking it switches operators placed before it |
| `Schedulers.parallel()` | CPU-bound, non-blocking work | Calling `block()` or JDBC on parallel workers |
| `Schedulers.single()` | Shared single non-blocking worker | Blocking the thread with synchronous I/O |
| `Schedulers.boundedElastic()` | Isolates legacy blocking I/O with bounded threads/queues | Abusing it instead of using reactive drivers |
| `Schedulers.immediate()` | Does not switch threads | Mistaking it for an async executor |
| `Schedulers.newSingle("name")` | Scheduler owned by test/app | Forgetting `dispose()`, leaking threads |

### 7.1. `publishOn` affects downstream

```java
Flux.range(1, 2)
    .map(i -> "before-" + Thread.currentThread().getName())
    .publishOn(Schedulers.parallel())
    .map(s -> "after-scheduler-change")
    .subscribe();
```

This fragment illustrates operator ordering, not a thread-ID unit test. `publishOn` applies the scheduler to callbacks following it; it does not “go backward in time” to move earlier `map` operators onto the new worker.

In real tests, avoid asserting exact thread names (`parallel-1`/`parallel-2`), as implementations and runtime load vary. When verifying a thread boundary switch, capture the caller thread ID/name before subscribing and assert the contract after `publishOn` executes on a different thread.

### 7.2. `subscribeOn` fits wrapping a blocking source

```java
Mono.fromCallable(() -> legacyJdbcCall())
    .subscribeOn(Schedulers.boundedElastic());
```

This fragment assumes `legacyJdbcCall()` exists in a real application. `fromCallable` defers blocking execution until subscription; `boundedElastic` keeps event-loop/parallel threads unblocked. **This adapts blocking APIs safely without turning JDBC into R2DBC.** If upstream HTTP/DB drivers are already non-blocking, adding `boundedElastic` unnecessarily adds context-switching overhead.

**Do not write:**
```java
Mono.just(legacyJdbcCall())
    .subscribeOn(Schedulers.boundedElastic());
```

In this fragment, `legacyJdbcCall()` executes **eagerly at assembly time**, before `subscribeOn` can switch threads. Wrap blocking work in `Mono.fromCallable(...)` or `Mono.defer(...)` to keep it lazy.

### 7.3. Calling `block()` on a Reactor non-blocking thread

Reactor marks `parallel`/`single` workers as non-blocking; calling `Mono.block()` on those threads throws `IllegalStateException` stating blocking calls are unsupported.

**Wrong inside a reactive operator:**

```java
Mono.just("ABC")
    .publishOn(Schedulers.parallel())
    .map(code -> remoteReactiveCall(code).block());
```

Here `remoteReactiveCall` is an undeclared reactive method. Calling `block()` forces a synchronous subscription inside an operator, risking non-blocking scheduler exceptions, lost Reactor Context, or deadlocks if waiting on the same worker. Fix with composition:

```java
Mono.just("ABC")
    .flatMap(code -> remoteReactiveCall(code));
```

If `remoteReactiveCall` returns `Mono<...>`, `flatMap` keeps the reactive chain intact so downstream preserves cancellation, error propagation, and Context. Never call `block()` in a WebFlux controller or service to force synchronous return types.

### 7.4. Test-created schedulers must be disposed

When a test creates its own scheduler:

```java
Scheduler scheduler = Schedulers.newSingle("probe");
try {
    StepVerifier.create(
            Mono.just("x").publishOn(scheduler))
        .expectNext("x")
        .expectComplete()
        .verify(Duration.ofSeconds(3));
} finally {
    scheduler.dispose();
}
```

A forgotten `Schedulers.newSingle` leaves a background thread running, keeping the JVM alive or interfering with other tests. Never call global `Schedulers.shutdownNow()` or reset global factories in parallel tests because that disrupts schedulers in use by other tests.

## 8. Reactor Context: attached to the subscriber, not pinned to a thread

`reactor.util.context.Context` is semantically immutable (`put` returns a new context). It is bound to the **Subscription/Subscriber** and flows upstream from subscriber to operators via `contextWrite`. This differs from `ThreadLocal`, which clings to a specific Java thread.

```text
         Assembly time
  service.requestId() creates Mono
               |
               v
    Subscriber calls subscribe()
               |
               v
       contextWrite(Context.put)
         propagates value to
           upstream chain
               |
               v
        deferContextual(...)
         reads ContextView
               |
               v
        onNext(requestId)
```

**Right:**

```java
Mono<String> requestId =
    Mono.deferContextual(context ->
        Mono.just(context.getOrDefault(
            "requestId", "missing")));

StepVerifier.create(
        requestId.contextWrite(
            context -> context.put("requestId", "RID-42")))
    .expectNext("RID-42")
    .expectComplete()
    .verify(Duration.ofSeconds(3));
```

`contextWrite` must sit **downstream of the operator reading Context** so upstream operators observe its keys. Context is not a global mutable map; two subscribers can share the same publisher while holding distinct `requestId` values.

### 8.1. Placement of `contextWrite` matters

Consider:

```java
Mono<String> current = Mono.deferContextual(ctx ->
        Mono.just(ctx.getOrDefault("key", "missing")));

Mono<String> correct =
        current.contextWrite(ctx -> ctx.put("key", "value"));
```

`correct` sees `"value"`. If `contextWrite` sits outside the upstream subscriber path of `deferContextual`, or reading happens in a detached inner `subscribe()`, the result becomes `"missing"`.

Never treat `Context` as `@RequestScope` attributes or MDC automatically copied into every thread. Standard `publishOn` stays within the same Reactor chain so `deferContextual` still sees Reactor Context, **yet custom ThreadLocals are not preserved automatically merely because Context survives**.

### 8.2. Context across `publishOn`

```java
Mono<String> afterSwitch = Mono.just("go")
    .publishOn(Schedulers.parallel())
    .flatMap(ignored ->
        Mono.deferContextual(ctx ->
            Mono.just(ctx.getOrDefault(
                "requestId", "missing"))));

StepVerifier.create(
        afterSwitch.contextWrite(ctx ->
            ctx.put("requestId", "RID-99")))
    .expectNext("RID-99")
    .expectComplete()
    .verify(Duration.ofSeconds(3));
```

Here `deferContextual` runs **after** `publishOn`, proving Context stays readable downstream after a scheduler switch. It **does not prove application MDC/`ThreadLocal` values propagate automatically too**.

### 8.3. `ThreadLocal`, MDC, SecurityContext, and trace context

| Data | Typical mechanism | Risk |
|---|---|---|
| Java `ThreadLocal` | Per thread | Lost on scheduler switch, leaks on pooled threads |
| SLF4J MDC | Usually `ThreadLocal`-backed | Missing or stale `traceId` in logs |
| Reactor `Context` | Per subscriber | Lost if chains split/subscribed manually or `contextWrite` misplaced |
| Spring Security reactive | `ReactiveSecurityContextHolder` uses Reactor Context | Cannot read with Servlet `SecurityContextHolder` `ThreadLocal` |
| Spring reactive transaction | Transaction context attached to Reactor subscriber | Not equivalent to JDBC `ThreadLocal` transactions |
| Micrometer tracing | Bridge + context propagation policy | Arbitrary custom `ThreadLocal`s do not propagate automatically |

For Spring Security WebFlux, build tests with `spring-security-test`, `WebTestClient`, and WebFlux security test configurers. **Never** read `SecurityContextHolder.getContext()` on an arbitrary parallel thread and conclude the reactive request principal was lost—you may be inspecting the wrong mechanism.

For reactive transactions, `@Transactional` on `Mono`/`Flux` (with `ReactiveTransactionManager`) binds the transaction to Reactor Context. Manually calling `subscribe()` on another publisher outside the managed chain detaches transaction, cancellation, and error context. A thread-bound JDBC `PlatformTransactionManager` will not cover R2DBC operators running across schedulers.

### 8.4. Micrometer Context Propagation and automatic mode

Spring Boot/Reactor integrates Micrometer Context Propagation to capture and restore registered `ThreadLocalAccessor`s between Reactor Context and ThreadLocals. Requirements:
- Compatible dependency/config/versions and registered accessors.
- Proper context snapshot or automatic propagation configuration.
- Never assume an unregistered custom `ThreadLocal` key propagates automatically.
- Clean up after task completion so MDC/security/tenant context never leaks.

**Never abuse** `Hooks.enableAutomaticContextPropagation()` inside individual parallel JUnit tests: it is JVM-global state affecting other tests. Test against application configuration or test-scoped context fixtures, restoring global changes on teardown only when truly needed.

## 9. `subscribe()`, `block()`, and `cache()` can produce false positives

### 9.1. Manual `subscribe()` lets the test finish before the pipeline

```java
service.saveReactive(item).subscribe();
assertThat(repository.count()).isEqualTo(1);
```

This is an illustrative anti-pattern (service/repository/item from another project). `subscribe()` **starts work asynchronously** without waiting for completion. The subsequent assertion can race ahead of the save, and async errors may only log/drop instead of failing the JUnit test properly.

**Fix:** `return` the publisher to callers in production; in tests use `StepVerifier.create(service.saveReactive(item))` with terminal assertions. To query DB state afterward, compose `then(repository.count())` in the same chain or use a separate verifier after the first completes.

### 9.2. `block()` sometimes masks subscription bugs

```java
Mono<String> source = service.loadReactive("A");
String first = source.block();
String second = source.block();
```

Fragment, not a full test. On a cold publisher, every `block()` **triggers a new subscription**. If the source executes an HTTP call, DB query, or increments a subscription counter, side effects run twice.

In plain JUnit outside Reactor event loops, `block(Duration)` can fetch a single result, yet it cannot replace `StepVerifier` for testing `onError`, cancellation, `request(n)`, or virtual time. Using `block()` inside a WebFlux application/controller signals a design issue.

### 9.3. `cache()` alters semantics

`Mono.cache()` caches results/terminal signals for subsequent subscribers. Useful in specific services, yet dangerous in tests if added to mimic “single I/O” when production needs freshness. Never add `cache()` merely to make a slow/hanging test pass. When testing cached publishers, assert subscription counts, expiration/invalidation policies, and error behavior—not just the final value.

## 10. When a publisher never finishes: identifying the terminal contract

Three cases are easy to confuse:
1. **Finite operation:** a reactive DB query or REST call expected to complete or error within a bounded deadline.
2. **Infinite/long-lived stream:** SSE, event subscriptions, `Flux.interval`, or reactive Kafka consumers normally **do not self-complete** without a stop signal.
3. **Broken flow:** intended to be finite yet chained with `concatWith(Flux.never())`, an uncompleted sink, a missing callback `success`, or a deadlock.

For finite operations, assert `expectComplete` or `expectError` with `verify(Duration)`. For infinite streams, use `take(n)`, `thenCancel()`, or client cancellation after observing expected events.

### 10.1. `take(n)` is an intentional contract boundary

```java
Flux<Long> ticks = Flux.interval(Duration.ofMillis(100));

StepVerifier.create(ticks.take(3))
    .expectNext(0L, 1L, 2L)
    .expectComplete()
    .verify(Duration.ofSeconds(3));
```

Here `take(3)` forms a **finite downstream stream** and cancels the upstream subscription after three elements. If the production API emits an infinite SSE stream, this test verifies the first three ticks and downstream cancellation—not that the server completes on its own later.

### 10.2. Pipeline `timeout` differs from verifier timeout

```java
Mono<String> result = Mono.<String>never()
    .timeout(Duration.ofSeconds(1))
    .onErrorResume(TimeoutException.class,
        ex -> Mono.just("timed-out"));
```

This fragment requires importing `java.util.concurrent.TimeoutException`. The `timeout` operator inside the **pipeline** emits `TimeoutException` when the source produces no signal in time; `onErrorResume` translates that failure into a fallback item. Conversely, `verify(Duration.ofSeconds(3))` is the **test's safety deadline** without changing pipeline behavior.

Know whether a test verifies:
- Business-level pipeline timeout behavior.
- Or merely protecting JUnit from hanging forever.

Keep those two deadlines intentionally distinct; for long pipeline timeouts, use virtual time rather than wall-clock sleep.

### 10.3. Misplaced `onErrorResume` swallows errors under test

```java
Mono<String> source = Mono.error(
    new IllegalStateException("database unavailable"));

Mono<String> recovered = source.onErrorResume(
    error -> Mono.just("fallback"));
```

Testing `recovered` with `expectError` asserts the wrong contract—the error was replaced with `"fallback"`. To test repository error propagation, verify **the source before fallback**; to verify service fallback behavior, assert `"fallback"`.

Avoid `onErrorResume(ex -> Mono.empty())` across layers to “cut down red tests”: it turns infrastructure failures into silent empty completions indistinguishable from missing records, creating false positives.

## 11. `WebTestClient`: reactive HTTP mocks differ from raw `StepVerifier`

`StepVerifier` exercises publisher APIs directly. `WebTestClient` checks **HTTP request/response semantics**; it can bind via mock exchanges to controllers/application contexts without opening sockets, or bind to a live server URL.

| Test kind | Tooling | What it proves |
|---|---|---|
| Pure operator/service test | `StepVerifier` | Signals, errors, demand, cancellation, Context |
| Controller mock exchange | `WebTestClient.bindToController(...)` or `@WebFluxTest` | HTTP status, headers, body, web binding/filters per setup |
| Full mock Boot context | `@SpringBootTest` + `@AutoConfigureWebTestClient` | Controller/filter/service wiring, response encoding |
| Live server | `@SpringBootTest(webEnvironment=RANDOM_PORT)` | Netty server/client transport close to production |
| External API dependency | Local mock HTTP server or fake `WebClient` exchange | Client serialization, timeouts, retries, URI/correlation |

**Never assume** a `WebTestClient` timeout means a Reactor publisher never completed without checking the handler chain, `WebFilter`s, codec/content negotiation, and body streaming. A controller may return an infinite `Flux` on an endpoint where the test asks `expectBodyList(...)` for completion, or a handler may call `subscribe()` on a side chain and return `Mono.empty()`.

### 11.1. `@WebFluxTest` slice vs `@SpringBootTest`

In Spring Boot 3.5, `@WebFluxTest(Controller.class)` loads only the web slice without scanning every `@Service`. Supply controller collaborators via `@MockitoBean`, `@Import`, or switch to a full context test. `@WebFluxTest` auto-configures `WebTestClient` to test web endpoints without binding a server socket.

`@SpringBootTest` defaults to a mock web environment and does not always expose `WebTestClient` automatically; for WebFlux full mock tests, add `@AutoConfigureWebTestClient`. If both MVC and WebFlux are on the classpath, Boot generally picks MVC unless `spring.main.web-application-type=reactive` is set.

## 12. Hands-on project: Spring Boot 3.5.8, Java 17+, and Reactor Test

The sections below build a minimal Spring WebFlux application. State stays purely in memory with no database, broker, or remote HTTP dependencies. The code uses a service with clear signal contracts, a `WebFilter` storing request IDs in Reactor Context, a controller reading the request ID after a scheduler switch, and JUnit test suites.

### 12.1. File layout

```text
settings.gradle
build.gradle
src/main/java/com/example/reactivediag/
    ReactiveDiagnosticApplication.java
    ReactiveProbeService.java
    RequestIdWebFilter.java
    ReactiveProbeController.java
src/test/java/com/example/reactivediag/
    ReactiveProbeServiceTest.java
    ReactiveProbeVirtualTimeTest.java
    ReactiveProbeWebTest.java
    PublisherProbeTest.java
```

Four test classes split by purpose: signals/backpressure, virtual time, HTTP/Reactor Context, and publisher subscription/cancellation. None of them hang intentionally; flawed explanatory examples are **excluded** from the runnable source set.

### 12.2. `settings.gradle`

```groovy
rootProject.name = 'reactive-diagnostics-lab'
```

### 12.3. `build.gradle`

```groovy
plugins {
    id 'java'
    id 'org.springframework.boot' version '3.5.8'
    id 'io.spring.dependency-management' version '1.1.7'
}

group = 'com.example'
version = '0.0.1-SNAPSHOT'

java {
    toolchain {
        languageVersion = JavaLanguageVersion.of(17)
    }
}

repositories {
    mavenCentral()
}

dependencies {
    implementation 'org.springframework.boot:spring-boot-starter-webflux'

    testImplementation 'org.springframework.boot:spring-boot-starter-test'
    testImplementation 'io.projectreactor:reactor-test'
    testRuntimeOnly 'org.junit.platform:junit-platform-launcher'
}

tasks.named('test', Test) {
    useJUnitPlatform()

    // Use a single fork in this lesson to avoid cross-JVM global
    // virtual-time interactions while debugging.
    maxParallelForks = 1

    testLogging {
        events 'failed', 'skipped'
        exceptionFormat 'full'
    }
}
```

**Dependency breakdown:**
- `spring-boot-starter-webflux`: Reactor, Spring WebFlux, Reactor Netty, and HTTP runtime.
- `spring-boot-starter-test`: Spring Boot Test, JUnit/AssertJ, and test utilities.
- `reactor-test`: `StepVerifier`, `StepVerifierOptions`, `PublisherProbe`, virtual-time support.
- The Spring Boot BOM aligns Reactor versions so `reactor-core` and `reactor-test` match. Do not pin an incompatible `reactor-test` version manually.
- Spring Security, R2DBC, tracing bridges, and Testcontainers are omitted from this demo because they are unnecessary to demonstrate the core mechanics.

**Important:** `maxParallelForks=1` limits only the number of **forked test JVMs**; it would not disable JUnit Jupiter parallel threads if a `junit-platform.properties` file enabled concurrent mode later. The sample omits any parallel-enabling config so Jupiter runs sequentially, keeping virtual schedulers and global hooks predictable.

### 12.4. `ReactiveDiagnosticApplication.java`

File `src/main/java/com/example/reactivediag/ReactiveDiagnosticApplication.java`:

```java
package com.example.reactivediag;

import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;

@SpringBootApplication
public class ReactiveDiagnosticApplication {

    public static void main(String[] args) {
        SpringApplication.run(
                ReactiveDiagnosticApplication.class, args);
    }
}
```

Spring Boot selects WebFlux because only the WebFlux starter is on the classpath, without Spring MVC. Running `bootRun` starts Reactor Netty; however, the JUnit web tests below use **mock exchanges** and open no port.

### 12.5. `ReactiveProbeService.java`

File `src/main/java/com/example/reactivediag/ReactiveProbeService.java`:

```java
package com.example.reactivediag;

import java.time.Duration;
import java.util.Locale;
import java.util.Objects;
import java.util.concurrent.TimeoutException;
import java.util.concurrent.atomic.AtomicInteger;

import reactor.core.publisher.Flux;
import reactor.core.publisher.Mono;
import reactor.core.scheduler.Scheduler;
import reactor.core.scheduler.Schedulers;

import org.springframework.stereotype.Service;

@Service
public class ReactiveProbeService {

    public Mono<String> normalize(String input) {
        return Mono.defer(() -> {
            if (input == null || input.isBlank()) {
                return Mono.error(new IllegalArgumentException(
                        "code must not be blank"));
            }

            return Mono.just(
                    input.trim().toUpperCase(Locale.ROOT));
        });
    }

    public Mono<String> deferredLabel(
            String id, AtomicInteger subscriptions) {

        Objects.requireNonNull(subscriptions);

        return Mono.fromSupplier(() -> {
            subscriptions.incrementAndGet();
            return "READY-" + id;
        });
    }

    public Mono<String> requestIdAfterSwitch(
            Scheduler scheduler) {

        Objects.requireNonNull(scheduler);

        return Mono.just("trigger")
                .publishOn(scheduler)
                .flatMap(ignored ->
                    Mono.deferContextual(context ->
                        Mono.just(context.getOrDefault(
                            "requestId", "missing"))));
    }

    public Flux<Integer> numbers() {
        return Flux.range(1, 5);
    }

    public Flux<Integer> numbersThenNever() {
        return Flux.range(1, 3)
                .concatWith(Flux.<Integer>never());
    }

    public Mono<Long> delayedSignal(Duration delay) {
        return Mono.delay(delay);
    }

    public Flux<Long> hourlyTicks(int count) {
        return Flux.interval(Duration.ofHours(1)).take(count);
    }

    public Mono<String> timeoutFallback(Duration timeout) {
        return Mono.<String>never()
                .timeout(timeout)
                .onErrorResume(TimeoutException.class,
                    ex -> Mono.just("timed-out"));
    }

    public Mono<String> blockingWorkThread() {
        return Mono.fromCallable(() ->
                Thread.currentThread().getName())
            .subscribeOn(Schedulers.boundedElastic());
    }
}
```

**Accurate reading:**
- `normalize` uses `Mono.defer` so validation/execution runs on subscribe; invalid input emits `onError`.
- `deferredLabel` counts **supplier executions per subscription**, not assembly.
- `requestIdAfterSwitch` places `deferContextual` **after `publishOn`**, testing subscriber context across a scheduler switch.
- `numbers` is a finite `Flux` respecting backpressure.
- `numbersThenNever` emits three items and never completes, suited for cancellation tests.
- `delayedSignal`/`hourlyTicks` build timers when called; invoke them **inside** the `withVirtualTime` supplier when testing.
- `timeoutFallback` separates pipeline timeout from verifier timeout.
- `blockingWorkThread` illustrates wrapping work with `fromCallable`/`boundedElastic`; it performs **no real blocking I/O** in this demo. Never assume a single hardcoded worker thread name.

### 12.6. `RequestIdWebFilter.java`

File `src/main/java/com/example/reactivediag/RequestIdWebFilter.java`:

```java
package com.example.reactivediag;

import reactor.core.publisher.Mono;

import org.springframework.http.server.reactive.ServerHttpRequest;
import org.springframework.stereotype.Component;
import org.springframework.web.server.ServerWebExchange;
import org.springframework.web.server.WebFilter;
import org.springframework.web.server.WebFilterChain;

@Component
public class RequestIdWebFilter implements WebFilter {

    @Override
    public Mono<Void> filter(
            ServerWebExchange exchange,
            WebFilterChain chain) {

        ServerHttpRequest request = exchange.getRequest();

        String raw = request.getHeaders()
                .getFirst("X-Request-Id");

        String requestId = raw == null || raw.isBlank()
                ? "anonymous"
                : raw;

        return chain.filter(exchange)
                .contextWrite(context ->
                    context.put("requestId", requestId));
    }
}
```

The filter reads the HTTP header and writes `requestId` into Reactor Context for **this request's reactive chain**. It avoids `ThreadLocal.set` and static maps. In real production apps, `X-Request-Id` is untrusted client input: validate length/format, sanitize logs, and enforce tracing/security policies. The demo relies solely on test-supplied IDs.

**Why `chain.filter(exchange).contextWrite(...)`?** `contextWrite` supplies context keys to upstream operators in the same subscription, including the controller/service invoked by the chain. Calling `Mono.deferContextual` outside this flow or breaking the chain with manual `subscribe()` drops the request ID.

### 12.7. `ReactiveProbeController.java`

File `src/main/java/com/example/reactivediag/ReactiveProbeController.java`:

```java
package com.example.reactivediag;

import reactor.core.publisher.Mono;
import reactor.core.scheduler.Schedulers;

import org.springframework.http.MediaType;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.PathVariable;
import org.springframework.web.bind.annotation.RequestMapping;
import org.springframework.web.bind.annotation.RestController;

@RestController
@RequestMapping("/probe")
public class ReactiveProbeController {

    private final ReactiveProbeService service;

    public ReactiveProbeController(ReactiveProbeService service) {
        this.service = service;
    }

    @GetMapping(
        path = "/context",
        produces = MediaType.TEXT_PLAIN_VALUE)
    public Mono<String> context() {
        return service.requestIdAfterSwitch(
                Schedulers.parallel());
    }

    @GetMapping(
        path = "/normalize/{code}",
        produces = MediaType.TEXT_PLAIN_VALUE)
    public Mono<String> normalize(
            @PathVariable String code) {
        return service.normalize(code);
    }
}
```

The controller **returns publishers** without calling `subscribe()` or `block()`. Server/WebFlux infrastructure handles subscribing and writing the HTTP response upon emission/completion. `/probe/context` deliberately switches onto `Schedulers.parallel()` to verify Reactor Context survives the thread hop.

No endpoint returns `Flux.never()`, because the demo does not need an intentionally hanging HTTP endpoint to teach cancellation; unit tests cover that stream safely.

## 13. JUnit 5: testing subscription, errors, backpressure, cancellation, and schedulers

### 13.1. `ReactiveProbeServiceTest.java`

File `src/test/java/com/example/reactivediag/ReactiveProbeServiceTest.java`:

```java
package com.example.reactivediag;

import java.time.Duration;
import java.util.concurrent.atomic.AtomicInteger;

import org.junit.jupiter.api.Test;

import reactor.core.publisher.Mono;
import reactor.core.scheduler.Scheduler;
import reactor.core.scheduler.Schedulers;
import reactor.test.StepVerifier;
import reactor.test.StepVerifierOptions;
import reactor.util.context.Context;

import static org.assertj.core.api.Assertions.assertThat;

class ReactiveProbeServiceTest {

    private final ReactiveProbeService service =
            new ReactiveProbeService();

    @Test
    void coldSourceRunsOnlyOnSubscription() {
        AtomicInteger runs = new AtomicInteger();
        Mono<String> publisher =
                service.deferredLabel("A", runs);

        assertThat(runs).hasValue(0);

        StepVerifier.create(publisher)
                .expectNext("READY-A")
                .expectComplete()
                .verify(Duration.ofSeconds(3));

        assertThat(runs).hasValue(1);

        // Cold source: another subscriber triggers it again.
        StepVerifier.create(publisher)
                .expectNext("READY-A")
                .expectComplete()
                .verify(Duration.ofSeconds(3));

        assertThat(runs).hasValue(2);
    }

    @Test
    void validInputCompletesWithValue() {
        StepVerifier.create(service.normalize(" ab-12 "))
                .expectNext("AB-12")
                .expectComplete()
                .verify(Duration.ofSeconds(3));
    }

    @Test
    void invalidInputEmitsError() {
        StepVerifier.create(service.normalize("  "))
                .expectErrorMatches(ex ->
                    ex instanceof IllegalArgumentException
                    && "code must not be blank"
                        .equals(ex.getMessage()))
                .verify(Duration.ofSeconds(3));
    }

    @Test
    void noContextUsesExplicitFallback() {
        StepVerifier.create(
                    service.requestIdAfterSwitch(
                        Schedulers.parallel()))
                .expectNext("missing")
                .expectComplete()
                .verify(Duration.ofSeconds(3));
    }

    @Test
    void contextSurvivesPublishOn() {
        Scheduler worker = Schedulers.newSingle("context-test");
        try {
            StepVerifier.create(
                    service.requestIdAfterSwitch(worker)
                        .contextWrite(
                            Context.of(
                                "requestId", "REQ-42")))
                .expectNext("REQ-42")
                .expectComplete()
                .verify(Duration.ofSeconds(3));
        } finally {
            worker.dispose();
        }
    }

    @Test
    void eachSubscriberHasItsOwnContext() {
        Mono<String> source = service.requestIdAfterSwitch(
                Schedulers.parallel());

        StepVerifier.create(source.contextWrite(
                    Context.of("requestId", "REQ-A")))
                .expectNext("REQ-A")
                .expectComplete()
                .verify(Duration.ofSeconds(3));

        StepVerifier.create(source.contextWrite(
                    Context.of("requestId", "REQ-B")))
                .expectNext("REQ-B")
                .expectComplete()
                .verify(Duration.ofSeconds(3));
    }

    @Test
    void rangeWaitsForExplicitDemand() {
        StepVerifier.create(
                service.numbers(),
                StepVerifierOptions.create().initialRequest(0))
            .expectSubscription()
            .thenRequest(2)
            .expectNext(1, 2)
            .thenRequest(3)
            .expectNext(3, 4, 5)
            .expectComplete()
            .verify(Duration.ofSeconds(3));
    }

    @Test
    void neverEndingTailIsCancelledRatherThanCompleted() {
        StepVerifier.create(service.numbersThenNever())
                .expectNext(1, 2, 3)
                .thenCancel()
                .verify(Duration.ofSeconds(3));
    }

    @Test
    void boundedElasticMovesBlockingWrapperOffCallerThread() {
        String callerThread =
                Thread.currentThread().getName();

        StepVerifier.create(service.blockingWorkThread())
                .expectNextMatches(
                    workerThread ->
                        !workerThread.equals(callerThread))
                .expectComplete()
                .verify(Duration.ofSeconds(3));
    }
}
```

These **9 `@Test` cases** verify:
- A cold publisher performs no work before subscription.
- Two subscriptions execute the supplier twice.
- `onError` differs from `onComplete`.
- `deferContextual` reads context values after a scheduler switch.
- Two subscribers hold **isolated Contexts**, unlike a shared `ThreadLocal`.
- Demand `request(n)` is granted explicitly via `thenRequest`.
- A stream with a `never` tail is cancelled rather than awaited indefinitely.
- `boundedElastic` offloads the callable off the JUnit caller thread.

**Assertion note:** `boundedElasticMovesBlockingWrapperOffCallerThread` captures `callerThread` **before subscription**, because the `expectNextMatches` predicate itself can execute on the worker thread. Reading `Thread.currentThread().getName()` inside the predicate would compare the worker thread against itself. Avoid asserting `"boundedElastic-1"` because exact thread names are not a business contract.

### 13.2. Why does `AtomicInteger` reveal subscription counts?

Merely calling `assertNext("READY-A")` does not prove how many times the publisher ran. `AtomicInteger` inside the source lets us assert **0 runs at assembly**, **1 run when the first verifier subscribes**, and **2 runs when another verifier subscribes**. This is a cold-publisher diagnostic technique, not a recommendation to put atomic counters into production services purely for testing.

## 14. JUnit 5: virtual time, intervals, and controlled timeouts

### 14.1. `ReactiveProbeVirtualTimeTest.java`

File `src/test/java/com/example/reactivediag/ReactiveProbeVirtualTimeTest.java`:

```java
package com.example.reactivediag;

import java.time.Duration;

import org.junit.jupiter.api.Test;

import reactor.test.StepVerifier;

class ReactiveProbeVirtualTimeTest {

    private final ReactiveProbeService service =
            new ReactiveProbeService();

    @Test
    void oneDayDelayFinishesWithoutOneDayOfWallClock() {
        StepVerifier.withVirtualTime(() ->
                    service.delayedSignal(
                        Duration.ofDays(1)))
                .expectSubscription()
                .expectNoEvent(Duration.ofDays(1))
                .expectNext(0L)
                .expectComplete()
                .verify(Duration.ofSeconds(3));
    }

    @Test
    void infiniteIntervalBecomesFiniteWithTake() {
        StepVerifier.withVirtualTime(() ->
                    service.hourlyTicks(2))
                .expectSubscription()
                .thenAwait(Duration.ofHours(2))
                .expectNext(0L, 1L)
                .expectComplete()
                .verify(Duration.ofSeconds(3));
    }

    @Test
    void businessTimeoutReturnsFallback() {
        StepVerifier.withVirtualTime(() ->
                    service.timeoutFallback(
                        Duration.ofHours(1)))
                .expectSubscription()
                .thenAwait(Duration.ofHours(1))
                .expectNext("timed-out")
                .expectComplete()
                .verify(Duration.ofSeconds(3));
    }
}
```

These three tests check timed operator behavior using **virtual time**. `withVirtualTime` accepts a lambda **invoking the service to build a fresh publisher**, avoiding premature scheduler capture.

**Distinguish the two clocks:**
- `Duration.ofDays(1)` and `Duration.ofHours(1)` represent **virtual pipeline durations**.
- `verify(Duration.ofSeconds(3))` is the **real JUnit safety timeout** if the test stalls or fails to advance as expected.

Do not claim these tests finished in a specific number of milliseconds across all machines; that is expected behavior pending real Gradle report observation.

### 14.2. Timing tests still require terminal expectations

Calling `thenAwait(Duration.ofHours(2))` alone does not verify the two ticks or completion. Two key details in the source:
- `hourlyTicks(2)` uses `take(2)`: emits `0L`, `1L`, then completes.
- `timeoutFallback`: `never` hits `timeout`, then `onErrorResume` emits `"timed-out"` and completes.

For an infinite SSE stream without `take(n)`, use `thenCancel()` instead of `expectComplete()`.

## 15. `WebTestClient`: request Context through `WebFilter` and controller

### 15.1. `ReactiveProbeWebTest.java`

File `src/test/java/com/example/reactivediag/ReactiveProbeWebTest.java`:

```java
package com.example.reactivediag;

import org.junit.jupiter.api.Test;

import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.autoconfigure.web.reactive.AutoConfigureWebTestClient;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.http.MediaType;
import org.springframework.test.web.reactive.server.WebTestClient;

@SpringBootTest(
    webEnvironment = SpringBootTest.WebEnvironment.MOCK)
@AutoConfigureWebTestClient
class ReactiveProbeWebTest {

    @Autowired
    WebTestClient client;

    @Test
    void requestIdFromHeaderSurvivesSchedulerSwitch() {
        client.get()
                .uri("/probe/context")
                .header("X-Request-Id", "HTTP-REQ-42")
                .accept(MediaType.TEXT_PLAIN)
                .exchange()
                .expectStatus().isOk()
                .expectBody(String.class)
                .isEqualTo("HTTP-REQ-42");
    }

    @Test
    void missingHeaderUsesAnonymousRequestId() {
        client.get()
                .uri("/probe/context")
                .accept(MediaType.TEXT_PLAIN)
                .exchange()
                .expectStatus().isOk()
                .expectBody(String.class)
                .isEqualTo("anonymous");
    }

    @Test
    void controllerReturnsNormalizedValue() {
        client.get()
                .uri("/probe/normalize/abc-12")
                .accept(MediaType.TEXT_PLAIN)
                .exchange()
                .expectStatus().isOk()
                .expectBody(String.class)
                .isEqualTo("ABC-12");
    }
}
```

Three Spring integration tests verify:
- Full WebFlux mock application context wiring `RequestIdWebFilter`, controller, and service.
- `X-Request-Id` written into Reactor Context by the filter is read inside the service **after `publishOn`**.
- Missing headers fall back deterministically to `"anonymous"`.
- Controller returns publishers so WebFlux streams responses and completes cleanly.

**Do not conflate:** Tests using `WebEnvironment.MOCK` and `@AutoConfigureWebTestClient` do not prove Reactor Netty bound a TCP socket. To verify live HTTP server/network transport, use `@SpringBootTest(webEnvironment=RANDOM_PORT)` over a real port. When debugging, mock exchanges are a useful isolation step before blaming Reactor Netty.

### 15.2. `WebTestClient` timeouts must match the contract

If an endpoint returns a long-lived `Flux` stream, calling `expectBodyList(...)` demands full completion and times out even when streaming works properly. For SSE, use streaming response assertions, `returnResult(...).getResponseBody()` fed into `StepVerifier` to assert expected items and cancel, or streaming-specific `WebTestClient` APIs.

If a supposedly finite endpoint never completes, test the controller's publisher first with `StepVerifier`; if that publisher completes while HTTP still times out, investigate `WebFilter`s, codecs, content negotiation, body writers, and HTTP server transport.

## 16. `PublisherProbe` and `TestPublisher`: observing which branch was subscribed

`reactor-test` includes `PublisherProbe` to track subscription, demand, and cancellation without modifying business code.

### 16.1. `PublisherProbeTest.java`

File `src/test/java/com/example/reactivediag/PublisherProbeTest.java`:

```java
package com.example.reactivediag;

import java.time.Duration;

import org.junit.jupiter.api.Test;

import reactor.core.publisher.Mono;
import reactor.test.StepVerifier;
import reactor.test.publisher.PublisherProbe;

class PublisherProbeTest {

    @Test
    void emptySourceUsesSubscribedFallback() {
        PublisherProbe<String> fallback =
                PublisherProbe.of(Mono.just("fallback"));

        Mono<String> result =
                Mono.<String>empty()
                    .switchIfEmpty(fallback.mono());

        StepVerifier.create(result)
                .expectNext("fallback")
                .expectComplete()
                .verify(Duration.ofSeconds(3));

        fallback.assertWasSubscribed();
        fallback.assertWasRequested();
        fallback.assertWasNotCancelled();
    }

    @Test
    void nonEmptySourceDoesNotSubscribeFallback() {
        PublisherProbe<String> fallback =
                PublisherProbe.of(Mono.just("fallback"));

        Mono<String> result =
                Mono.just("primary")
                    .switchIfEmpty(fallback.mono());

        StepVerifier.create(result)
                .expectNext("primary")
                .expectComplete()
                .verify(Duration.ofSeconds(3));

        fallback.assertWasNotSubscribed();
    }
}
```

These two tests prove whether the fallback branch **was** or **was not** subscribed, rather than inferring execution paths solely from the final value. `PublisherProbe` is ideal for `switchIfEmpty`, `then`, cancellation semantics, and multi-branch pipelines.

### 16.2. `TestPublisher` for test-controlled sources

Creating a publisher that emits signals on demand from the test:

```java
TestPublisher<String> publisher = TestPublisher.create();

StepVerifier.create(publisher.flux())
        .then(() -> publisher.next("A"))
        .expectNext("A")
        .then(publisher::complete)
        .expectComplete()
        .verify(Duration.ofSeconds(3));
```

This **fragment** requires importing `reactor.test.publisher.TestPublisher`. The key point is that `then(...)` runs **after the verifier subscribes**, preventing “emit before subscribe” races. For buffered streams or genuine hot sources, configure semantics matching production; `TestPublisher` is primarily a test double for signal control.

`TestPublisher` also provides non-compliant variants to test Reactive Streams violation handling, strictly for targeted tests. Never distort a production publisher solely to speed up a test.

## 17. Reactive transactions, security, and WebFlux context: testing at the right layer

### 17.1. `ReactiveTransactionManager` and Reactor Context

A Spring Data R2DBC service can use `@Transactional` on `Mono`/`Flux` or `TransactionalOperator` to manage reactive transaction context. The transaction binds to the subscriber/reactive chain, **not just the JUnit method's `ThreadLocal`**.

A brittle test:

```java
@Transactional
@Test
void shouldRollback() {
    service.createReactive(entity).subscribe();
    // Method returns before the pipeline finishes;
    // test-managed transaction does not cover reactive work
    // the way the test assumes.
}
```

Illustrative anti-pattern, **excluded from the runnable project** because no R2DBC dependency is present. You need a reactive transaction manager and composed publisher:
```java
StepVerifier.create(
        transactionalOperator.transactional(
            service.createReactive(entity)))
    .expectNextCount(1)
    .expectComplete()
    .verify(Duration.ofSeconds(5));
```

This fragment assumes `transactionalOperator`, `service`, and `entity` exist in a real R2DBC project. Verify DB commits/rollbacks via independent queries and cleanup rather than inferring transaction success solely from `onComplete` on a mocked publisher.

### 17.2. Reactive Spring Security

In WebFlux, principals and security context live in Reactor Context via `ReactiveSecurityContextHolder`. A `@WebFluxTest` using Spring Security should apply WebFlux security test support (such as `spring-security-test` and `SecurityMockServerConfigurers.mockUser`), not servlet thread-local `SecurityContextHolder`.

When a `WebFilter` or service breaks the chain with a manual `subscribe()`, security context fails to follow the detached subscriber. Never “fix” that by writing arbitrary `ThreadLocal.set` calls; preserve the reactive chain and use framework test configurers.

### 17.3. Logging/MDC/tracing propagation

`contextWrite(Context.of("requestId", ...))` writes into Reactor Context; it **does not automatically populate SLF4J MDC**. If tests expect `traceId` in logs after `publishOn`, you need Micrometer Tracing/Context Propagation integration, `ThreadLocalAccessor` registrations, and proper scope cleanup. Never assert `MDC.get("traceId")` without configuring tracing, and do not infer HTTP `traceparent` propagation simply because the service reads `requestId`.

**Important:** Reactive transactions, security, and tracing each carry distinct semantics. Testing `requestId` proves single-key Context propagation along the same chain—not security authorization, transactional consistency, or distributed trace export.

## 18. When tests fail only on CI or in parallel execution

A reactive test can pass alone yet fail across parallel forks/threads because:
- `VirtualTimeScheduler` or global `Scheduler` factories were altered/reset between tests.
- `Hooks.onOperatorDebug()` was enabled and never reset.
- Custom `Schedulers.newSingle` instances leaked threads without disposal.
- Static sinks or shared subscribers outlived a test.
- Other tests collided on shared Redis/DB topics, queues, or file paths.
- `@DirtiesContext` closed a cached Spring `ApplicationContext` while another reactive pipeline was still using it.
- `@MockitoBean` in a shared context was concurrently reset or stubbed by another test.
- `@Transactional` test-thread semantics were confused with reactive transaction context.
- Container CPU quotas sharply increased scheduling latency.
- Reactive Netty event loops got blocked by synchronous JDBC/blocking calls.
- A JUnit method spawned a background subscription without cancelling in teardown.

### 18.1. Reasonable debugging sequence

1. Run the exact test class/method via Gradle `--tests`.
2. Check whether `StepVerifier` calls `verify` with a bounded deadline.
3. Confirm whether the source is finite or infinite and whether the terminal contract matches.
4. Capture `doOnSubscribe`, `doOnRequest`, `doOnNext`, `doOnError`, and `doFinally` at suspicious boundaries.
5. Use `StepVerifierOptions.initialRequest(0)` to isolate demand problems if suspected.
6. Switch to explicit per-test schedulers and dispose properly; avoid global shutdowns.
7. Test Reactor Context directly using `deferContextual` after `publishOn`.
8. For WebFlux, verify the service publisher first, then mock `WebTestClient`, and finally a live server socket.
9. Disable Gradle forks and JUnit parallelism one layer at a time to locate races.
10. Measure actual thread counts, active Netty event loops, `boundedElastic` queues, and DB pools.
11. Keep original stack traces and operator checkpoints before retrying on failure.
12. After fixing, run the full suite and realistic CI profile rather than a single single-threaded test.

### 18.2. Reactor debugging tools

Reactor supports `.checkpoint("meaningful-stage")`, `Hooks.onOperatorDebug()`, `ReactorDebugAgent`, and signal logging to attach assembly context to errors.

```java
return repository.findById(id)
        .switchIfEmpty(Mono.error(
            new IllegalStateException("not found")))
        .checkpoint("load-order-by-id");
```

This fragment assumes `repository` and `id` exist elsewhere. `.checkpoint` attaches a clear label to stack traces without enabling JVM-wide `Hooks.onOperatorDebug()`. Global debug hooks add overhead and side effects, so restrict them to controlled diagnostic profiles/tests and reset them via the API afterward.

### 18.3. Logging signals without introducing order dependency

```java
Flux<Integer> debug = Flux.range(1, 3)
    .doOnSubscribe(s -> log.debug("subscribed"))
    .doOnRequest(n -> log.debug("requested {}", n))
    .doOnNext(n -> log.debug("next {}", n))
    .doOnError(e -> log.debug("error", e))
    .doFinally(type -> log.debug("finally {}", type));
```

This fragment assumes an SLF4J `log` logger is declared. Callbacks reveal subscription, demand, and completion/cancellation. Never write JUnit assertions on exact cross-thread log ordering because interleaving varies with scheduling. `doFinally` receives `SignalType` (such as `ON_COMPLETE`, `ON_ERROR`, `CANCEL`), which is useful for tracking cleanup lifecycles.

## 19. Why raising timeouts is rarely the right fix for reactive test timeouts

Raising `verify(Duration.ofSeconds(2))` to 30 seconds makes sense when genuine external I/O needs that SLA, yet it never fixes:
- `Flux.never()` where completion was expected.
- A subscriber failing to `request(n)`.
- `withVirtualTime` never advancing its clock.
- `Mono.just(blockingCall())` executing eagerly before the scheduler switch.
- Event loops blocked by `block()` or JDBC.
- `contextWrite` placed outside the subscriber chain.
- Tests calling `subscribe()` without awaiting completion.
- `@Transactional` tests confusing thread-bound transactions with reactive context.
- Hot sinks emitting before subscription.
- Leaked schedulers/executors or shared-context races.

If raising a timeout makes a flaky test pass, prove the **real latency** aligns with the contract and document CI load budgets. For timer-driven behavior, virtual time saves orders of magnitude more wall time than inflating sleeps.

## 20. Running the sample project and reading reports

With a Gradle wrapper present in the project:

Linux/macOS:

```bash
./gradlew test --tests "com.example.reactivediag.ReactiveProbeServiceTest"
./gradlew test --tests "com.example.reactivediag.ReactiveProbeVirtualTimeTest"
./gradlew test --tests "com.example.reactivediag.ReactiveProbeWebTest"
./gradlew test --tests "com.example.reactivediag.PublisherProbeTest"
./gradlew test
```

Windows PowerShell:

```powershell
.\gradlew.bat test --tests "com.example.reactivediag.ReactiveProbeServiceTest"
.\gradlew.bat test --tests "com.example.reactivediag.ReactiveProbeVirtualTimeTest"
.\gradlew.bat test --tests "com.example.reactivediag.ReactiveProbeWebTest"
.\gradlew.bat test --tests "com.example.reactivediag.PublisherProbeTest"
.\gradlew.bat test
```

**Source test count:** `ReactiveProbeServiceTest` has **9** tests, `ReactiveProbeVirtualTimeTest` has **3**, `ReactiveProbeWebTest` has **3**, and `PublisherProbeTest` has **2**: **17 JUnit `@Test` methods** written in total. That is the authored source count/expected discovery, **not proof that 17 tests executed and passed**.

After executing, inspect:
- `build/reports/tests/test/index.html` (HTML report).
- `build/test-results/test/` (JUnit XML results).
- Full stack traces and Gradle task outcomes.
- Whether tests executed vs `UP-TO-DATE`/`FROM-CACHE`/`NO-SOURCE`.
- Whether leftover JVM threads remain alive or timeouts/errors were swallowed.

If switching to Maven instead of Gradle, you need a complete `pom.xml` with Spring Boot BOM, `reactor-test`, JUnit launcher, and Surefire; `./mvnw test` cannot run directly on a `build.gradle`-only project. Compiling with bare `javac` is insufficient without Spring/Reactor/JUnit dependencies on the classpath.

### 20.1. Slow or hung on a single method?

```bash
./gradlew test --tests "com.example.reactivediag.ReactiveProbeServiceTest.neverEndingTailIsCancelledRatherThanCompleted" --info
```

If this method stalls, verify whether `Flux.range(...).concatWith(Flux.never())` is truly cancelled by `thenCancel`, or whether leftover global hooks/schedulers from another test interfere. `--info` provides task/worker diagnostics without replacing Reactor signal logging.

### 20.2. Never draw conclusions from `BUILD SUCCESSFUL` alone

A test missing `verify` passes without subscribing to the publisher. A Gradle task can show `UP-TO-DATE` from an earlier build. Tests with `@Disabled` or tag filters are skipped. Always cross-check assertions, signal paths, and executed counts in reports.

## 21. Anti-patterns and concise fixes

| Anti-pattern | Why it fails | Right approach |
|---|---|---|
| Building `StepVerifier` without `verify` | Never subscribes | Always call `verify(Duration)` |
| Cold `Mono` side-effect check before subscription | Work hasn't run yet | Assert laziness or subscribe explicitly via verifier |
| `expectNext` with `initialRequest=0` and no `thenRequest` | Zero demand | Issue `request(n)` explicitly |
| `expectComplete` on `Flux.never()` | Stream never finishes | Cancel or fix business termination |
| `expectNoEvent` at the very start | Subscription counts as an event | Call `expectSubscription` first |
| `Mono.delay` built before virtual time | May capture real scheduler | Create publisher inside the supplier |
| `withVirtualTime` without `thenAwait` | Clock hasn't advanced | Advance full duration |
| `withVirtualTime` with an explicit real scheduler | Timer ignores virtual scheduler | Inject/use appropriate scheduler or test real-time |
| `Thread.sleep` awaiting async work | Races with CI scheduling | `StepVerifier`/Future/latch |
| `Mono.just(blockingCall())` | Blocking call runs eagerly at assembly | `fromCallable(...).subscribeOn(boundedElastic())` |
| `.block()` inside WebFlux operators | Blocking/non-blocking mismatch, deadlock | Compose with `flatMap` |
| Manual `subscribe()` in services | Breaks cancellation/error/context chain | Return the `Publisher` |
| `contextWrite` outside subscriber path | Readers see missing context | Place downstream of reader in same chain |
| Expecting `ThreadLocal`/MDC to follow `publishOn` | Scheduler changes threads | Reactor Context / Micrometer propagation |
| Reading Servlet `SecurityContextHolder` in reactive tests | Wrong context model | `ReactiveSecurityContextHolder`/WebFlux test support |
| Applying JUnit JDBC `@Transactional` to R2DBC | Wrong transaction model | `ReactiveTransactionManager`/`TransactionalOperator` |
| Confusing pipeline `timeout` with verifier timeout | One alters pipeline, one guards test | Test the two semantics separately |
| Hot publisher emitting before subscriber attaches | Lost signals | `TestPublisher`/`then` action, check emit result |
| `@WebFluxTest` missing services | Slice skips unrelated beans | `@MockitoBean`/`@Import` |
| `WebTestClient` requesting full body on infinite SSE | Stream never completes | Streaming assertions + cancel |
| Forgetting to dispose `newSingle` | Thread/resource leak | `finally` dispose |
| Resetting global `Hooks` in concurrent tests | Disrupts whole JVM | Isolate diagnostic tests |
| Swallowing errors via `onErrorResume(Mono.empty())` | False-green tests | Assert failure/fallback contracts separately |
| R2DBC test calling standalone `subscribe()` in transaction | Detached subscriber context | Compose/return publisher |
| Unready Testcontainers/DB | Setup race | Startup waits + dynamic properties |
| Failing only in parallel CI | Shared Context/Mock/DB/global scheduler | Isolate resources / serialize lane |

## 22. Pre-PR diagnostic checklist

- [ ] Test invokes `verify(Duration)` or an equivalent deadline shortcut.
- [ ] Publisher cold vs hot semantics and subscription timing are clear.
- [ ] `expectSubscription` precedes subscription assertions or `expectNoEvent`.
- [ ] Adequate demand is issued whenever `initialRequest(0)` is used.
- [ ] `Mono.empty`, `Mono.never`, and `Mono.error` are clearly distinguished.
- [ ] Completion/error/cancellation expectations match the business contract.
- [ ] Infinite streams use `take(n)` or `thenCancel()` in tests.
- [ ] `Thread.sleep` is never used in place of subscription/terminal signals.
- [ ] `withVirtualTime` builds publishers inside the supplier without capturing timers early.
- [ ] `thenAwait`/`expectNoEvent` advance the virtual clock sufficiently.
- [ ] `block()` is never called on non-blocking schedulers or in WebFlux controllers.
- [ ] Unavoidable legacy blocking calls are deferred and offloaded to `boundedElastic`.
- [ ] `publishOn` vs `subscribeOn` boundaries are placed intentionally.
- [ ] Custom schedulers are disposed in `finally`.
- [ ] Reactor Context is read with `deferContextual` and populated via `contextWrite`.
- [ ] Context survival across scheduler switches is tested where needed.
- [ ] `ThreadLocal`/MDC values are not assumed to propagate automatically across threads.
- [ ] Reactive security, tracing, and transactions use the right context mechanism.
- [ ] Manual `subscribe()` never detaches flows or transaction context.
- [ ] HTTP tests select the right `WebTestClient` mock/slice/live-server setup.
- [ ] Errors are never masked into false positives by `onErrorResume`.
- [ ] Spring context and mock state are never mutated concurrently by parallel tests.
- [ ] Global `Hooks`/`Schedulers` resets are avoided in concurrent suites.
- [ ] Signals/logs at suspect stages guide debugging instead of blind timeout bumps.
- [ ] Real JUnit/Gradle reports are inspected before declaring PASS.

## 23. Official references

- [Project Reactor — Testing](https://projectreactor.io/docs/core/release/reference/testing.html): `StepVerifier`, `withVirtualTime`, `thenAwait`, `expectNoEvent`, `PublisherProbe`.
- [Reactor Test API — StepVerifier](https://projectreactor.io/docs/test/release/api/reactor/test/StepVerifier.html): verify, verify(Duration), cancellation, expectations.
- [Reactor Test API — StepVerifierOptions](https://projectreactor.io/docs/test/release/api/reactor/test/StepVerifierOptions.html): `initialRequest`, `withInitialContext`.
- [Project Reactor — Threading and Schedulers](https://projectreactor.io/docs/core/release/reference/coreFeatures/schedulers.html): `publishOn`, `subscribeOn`, boundedElastic and nonblocking threads.
- [Project Reactor — Context](https://projectreactor.io/docs/core/release/reference/advancedFeatures/context.html): subscriber context, `contextWrite`, `deferContextual`.
- [Project Reactor — Debugging](https://projectreactor.io/docs/core/release/reference/debugging.html): `checkpoint`, operator stack traces and hooks.
- [Spring Boot 3.5 — Testing Spring Boot Applications](https://docs.spring.io/spring-boot/3.5/reference/testing/spring-boot-applications.html): `@WebFluxTest`, `@AutoConfigureWebTestClient`, `@SpringBootTest`.
- [Spring Framework — WebTestClient](https://docs.spring.io/spring-framework/reference/testing/webtestclient.html): bind-to-controller/context/server and reactive HTTP assertions.
- [Spring Framework — WebFlux](https://docs.spring.io/spring-framework/reference/web/webflux.html): reactive server, response semantics, event-loop model.
- [Spring Framework — Reactive Transactions](https://docs.spring.io/spring-framework/reference/data-access/transaction/programmatic.html): reactive transaction operator/context.
- [Micrometer — Context Propagation](https://docs.micrometer.io/context-propagation/reference/purpose.html): ThreadLocal/Reactor Context bridge.
- [JUnit Jupiter — User Guide](https://docs.junit.org/current/user-guide/): test lifecycle, assertions and reports.

**Conclusion:** When a reactive test fails to complete, do not assume Spring Boot is slow. Check **subscription**, **request demand**, **terminal signals**, **schedulers**, and **Reactor Context** in order. `StepVerifier` with `verify(Duration)` surfaces failures instead of hanging forever; `withVirtualTime` tests timers rapidly when the publisher is built inside the supplier; `thenCancel` fits infinite streams; and `contextWrite/deferContextual` carry subscriber data across `publishOn` without copying arbitrary ThreadLocals. With WebFlux, test service publishers first, verify HTTP through `WebTestClient`, and only then investigate server/network transport. Fix broken reactive boundaries, contracts, and resource leaks—rather than bumping timeouts and hoping the next run gets lucky.

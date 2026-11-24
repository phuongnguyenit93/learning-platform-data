# withVirtualTime and Creating Publishers After Virtual Time Setup in Reactor

Reactive tests sometimes need to verify an event occurring after 10 seconds, a retry after several minutes, or a timeout after one day. Using real time makes the test suite slow and prone to flakiness from machine speed, schedulers, and CI load. Project Reactor provides **StepVerifier.withVirtualTime** to replace the clock of Reactor-managed Schedulers with a virtual clock. Tests can advance time in a few real milliseconds while accurately checking the relationship between subscription time, events, timeouts, and completion.

The single most important point in this lesson is: **a publisher using time-based operators must be created after the virtual scheduler is installed**. That is why `StepVerifier.withVirtualTime` does not take an already-constructed `Flux` or `Mono`; it takes a **Supplier of a Publisher**. If you create the publisher beforehand and write a lambda that merely returns the old publisher, operators like `delay`, `interval`, or `timeout` may already hold a reference to the real scheduler, causing virtual time to have no effect.

This lesson belongs to the **Reactor Testing** group of the Spring Framework - reactive module. It covers how the virtual scheduler works, where to create publishers, StepVerifier APIs, hands-on Java 17+ test cases, dangerous mistakes, and the limits of time simulation.

## 1. Learning Objectives

After this lesson, you will be able to:

- Explain why tests using `Thread.sleep` are poorly suited for most reactive time operators.
- Distinguish real time (wall-clock time) from `VirtualTimeScheduler` virtual time.
- Understand why `withVirtualTime` accepts a `Supplier` instead of an existing `Flux`/`Mono`.
- Create publishers inside the supplier so the scheduler is selected at the right moment.
- Use `expectSubscription`, `thenAwait`, and `expectNoEvent` in the proper order.
- Understand the outputs of `Mono.delay`, `Flux.interval`, `delayElements`, and `delayElement`.
- Test `timeout`, `retryBackoff`, `take(Duration)`, and cancellation.
- Combine `withVirtualTime` with `StepVerifierOptions` and real verification timeouts.
- Use `VirtualTimeScheduler` manually when a scheduler is passed explicitly.
- Distinguish operators using default schedulers from eagerly created custom schedulers.
- Diagnose deadlocks or hanging tests caused by failing to advance the virtual clock.
- Understand that virtual time does not accelerate `Thread.sleep`, network APIs, or blocking I/O.
- Avoid cross-test interference when a virtual scheduler alters global factories.
- Write and read a runnable JUnit 5 test suite on Java 17 and Reactor Test.

## 2. Why Do We Need Virtual Time?

Suppose a business rule sends a notification after one day:

~~~java
Mono<String> delayed = Mono.just("ready")
    .delayElement(Duration.ofDays(1));
~~~

If tested in real time, a single test would have to wait until the next day. Changing it to 100 ms for speed no longer tests the configured one-day parameter and still risks failing on a slow machine.

Testing with virtual time:

~~~java
StepVerifier.withVirtualTime(
        () -> Mono.just("ready")
            .delayElement(Duration.ofDays(1)))
    .expectSubscription()
    .expectNoEvent(Duration.ofDays(1))
    .expectNext("ready")
    .verifyComplete();
~~~

The test advances the virtual clock by one day without waiting a real day. This is a technique for **controlling schedulers and event timing**, not changing the operating system clock.

Useful applications:

- Delayed notifications via `delayElement`.
- Periodic ticks via `Flux.interval`.
- Spaced-out multi-element emissions via `delayElements`.
- Timeouts when no event arrives.
- Retries with backoff.
- Time windows and cache TTLs when operators use a controllable scheduler.
- Expiration policies, `debounce`, `bufferTimeout`, `windowTimeout`, or `take(Duration)`.
- Verifying no events are emitted before a threshold time.

Not all time-related logic can use virtual time: libraries calling `System.currentTimeMillis()`, `java.time.Clock.systemUTC()`, `Thread.sleep`, OS socket timeouts, or non-Reactor timers will not automatically follow `VirtualTimeScheduler`.

## 3. What Does StepVerifier Check?

`StepVerifier` is a utility from the `reactor-test` dependency that lets you declare sequentially the signals a Publisher must emit.

Standard example:

~~~java
StepVerifier.create(Flux.just("A", "B"))
    .expectNext("A")
    .expectNext("B")
    .verifyComplete();
~~~

Core Reactive Streams signals:

- **onSubscribe**: downstream receives the Subscription.
- **onNext**: emits an element.
- **onError**: terminates with an error.
- **onComplete**: terminates successfully.
- **cancel**: downstream cancels the Subscription.

`StepVerifier` declares expectations in order of occurrence. Only when `verify()`, `verifyComplete()`, `verifyError()`, or a corresponding variant is called do subscription and verification actually happen.

### Two Ways to Create a Verifier

~~~java
StepVerifier.create(publisher)
    .expectNext("A")
    .verifyComplete();
~~~

This is normal testing, using the publisher's scheduler.

~~~java
StepVerifier.withVirtualTime(() -> publisherCreatedHere())
    .expectSubscription()
    .thenAwait(Duration.ofSeconds(30))
    .expectNext("A")
    .verifyComplete();
~~~

This is virtual-clock testing, installed before calling the supplier that creates the Publisher.

Use `withVirtualTime` when you need to control **timing**; you do not need it for a pure `Flux.just` unrelated to time.

## 4. How Does VirtualTimeScheduler Work?

`VirtualTimeScheduler` implements `Scheduler` for tasks scheduled on a simulated timeline. Instead of waiting for the real-world clock to reach deadlines, tests call `advanceTimeBy`, `advanceTimeTo`, or use `StepVerifier.thenAwait` to move the clock forward and trigger scheduled tasks.

Diagram:

~~~text
Virtual time: 0s ----- 5s ----- 10s ----- 15s
              |        |         |         |
              |     task A     task B    task C
              |
      StepVerifier subscribe

thenAwait(5s)  --> run task A
thenAwait(5s)  --> run task B
thenAwait(5s)  --> run task C
~~~

Normally Reactor time operators obtain a scheduler via `Schedulers.parallel()` or an equivalent factory. `withVirtualTime` installs `VirtualTimeScheduler` into the `Schedulers` factories so operators **created afterward** acquire the virtual scheduler instead of the real one.

`VirtualTimeScheduler` is not a virtual sleeping thread. It stores scheduled tasks and executes them when the test advances time. As the clock advances, multiple due tasks can run immediately during verification. If a task blocks, the test can still hang.

### Key Concepts

| Concept | Explanation |
| --- | --- |
| `VirtualTimeScheduler` | Scheduler with a manually controlled clock |
| Scheduler factory | Mechanism supplying Reactor's default Schedulers |
| `Supplier<Publisher<T>>` | Function creating the publisher after the virtual scheduler is in place |
| `thenAwait(Duration)` | Advances the clock without asserting silence |
| `expectNoEvent(Duration)` | Advances the clock and asserts no signals occurred during that window |
| `verify(Duration)` | Real-time limit for waiting on verification to finish |
| `expectSubscription()` | Confirms `onSubscribe`, usually placed before `expectNoEvent` |

## 5. Why Must withVirtualTime Take a Supplier?

Common API:

~~~java
StepVerifier.withVirtualTime(
    () -> Mono.delay(Duration.ofHours(12)))
~~~

A `Supplier` is a lambda returning a Publisher, not an already-created Publisher. The reason lies in **when operators are initialized**.

When constructing a timed operator, Reactor can pick and retain a reference to a scheduler. If the operator is built before `StepVerifier` installs the virtual clock, it may capture the real scheduler.

### Right Way

~~~java
StepVerifier.withVirtualTime(
        () -> Flux.interval(Duration.ofHours(1))
            .take(3))
    .expectSubscription()
    .thenAwait(Duration.ofHours(3))
    .expectNext(0L, 1L, 2L)
    .verifyComplete();
~~~

`Flux.interval` and `take(3)` are created **inside** the supplier. The virtual scheduler is installed first, so the three-hour span is simulated.

### Wrong Way

~~~java
Flux<Long> intervalAlreadyCreated =
    Flux.interval(Duration.ofHours(1)).take(3);

StepVerifier.withVirtualTime(() -> intervalAlreadyCreated)
    .expectSubscription()
    .thenAwait(Duration.ofHours(3))
    .expectNext(0L, 1L, 2L)
    .verifyComplete();
~~~

The lambda merely returns an already-created publisher. If `intervalAlreadyCreated` already captured the real scheduler at assembly time, advancing three virtual hours will not make the real scheduler emit ticks. The result can hang or exceed the verification timeout.

Point to remember: **the supplier must re-create at least the time-dependent operators**, not merely defer reading a variable holding a publisher.

### Fix Using a Method Reference

~~~java
Flux<Long> buildIntervals() {
    return Flux.interval(Duration.ofHours(1)).take(3);
}

void testIntervals() {
    StepVerifier.withVirtualTime(this::buildIntervals)
        .expectSubscription()
        .thenAwait(Duration.ofHours(3))
        .expectNext(0L, 1L, 2L)
        .verifyComplete();
}
~~~

The method reference `this::buildIntervals` is only invoked once `StepVerifier` has set up virtual time. This is a clean way to keep pipeline construction inside a service or factory.

## 6. Publisher Creation in Services Must Be Truly Lazy

Take a service example:

~~~java
public final class ClockService {

    public Flux<String> heartbeat() {
        return Flux.interval(Duration.ofSeconds(10))
            .map(index -> "heartbeat-" + index);
    }
}
~~~

If the test calls `service.heartbeat()` **inside the lambda**, this works properly:

~~~java
StepVerifier.withVirtualTime(() -> service.heartbeat().take(2))
    .expectSubscription()
    .thenAwait(Duration.ofSeconds(20))
    .expectNext("heartbeat-0", "heartbeat-1")
    .verifyComplete();
~~~

Conversely, if the service constructs `Flux.interval` in its constructor and stores it in a field, then even calling `service.heartbeat()` inside the supplier may return a publisher holding the old scheduler.

~~~java
public final class EagerClockService {

    private final Flux<Long> sharedTicks =
        Flux.interval(Duration.ofSeconds(10));

    public Flux<Long> heartbeat() {
        return sharedTicks;
    }
}
~~~

If `EagerClockService` is instantiated before the virtual clock, a test using `withVirtualTime(() -> service.heartbeat())` is not guaranteed to work.

You can fix this by storing a **factory** instead of an assembled publisher:

~~~java
public final class LazyClockService {

    public Flux<Long> heartbeat() {
        return Flux.interval(Duration.ofSeconds(10));
    }
}
~~~

Or use `Flux.defer` to construct the time operator at subscription time if that fits the business design:

~~~java
public Flux<Long> heartbeat() {
    return Flux.defer(
        () -> Flux.interval(Duration.ofSeconds(10)));
}
~~~

`Flux.defer` is useful, yet it is no "magic fix" for an already-created publisher. `Flux.defer(() -> oldPublisher)` still returns `oldPublisher`. Put **the creation of the time operator** inside the supplier/defer.

## 7. expectSubscription() and expectNoEvent()

Reactor treats `onSubscribe` as a signal. `expectNoEvent(Duration)` asserts that no signal at all occurs during the evaluated window, **including `onSubscribe`**.

Therefore, this is usually wrong:

~~~java
StepVerifier.withVirtualTime(
        () -> Mono.delay(Duration.ofSeconds(5)))
    .expectNoEvent(Duration.ofSeconds(5))
    .expectNext(0L)
    .verifyComplete();
~~~

`onSubscribe` arrives right after the verifier subscribes, so `expectNoEvent` at the start can fail on that very signal.

Right way:

~~~java
StepVerifier.withVirtualTime(
        () -> Mono.delay(Duration.ofSeconds(5)))
    .expectSubscription()
    .expectNoEvent(Duration.ofSeconds(5))
    .expectNext(0L)
    .verifyComplete();
~~~

### Why Is expectNoEvent Stronger Than thenAwait?

Both can advance virtual time:

~~~java
.thenAwait(Duration.ofSeconds(5))
~~~

and:

~~~java
.expectNoEvent(Duration.ofSeconds(5))
~~~

Key difference:

- `thenAwait` only advances time without asserting that no `onNext` occurs in the meantime.
- `expectNoEvent` advances time **and fails if any unexpected signal arrives** during the window.

If the requirement is "only emit after 5 seconds", `expectNoEvent` is better because it catches values arriving too early. If you just want the scheduler to execute due tasks and then check multiple values, `thenAwait` is more convenient.

### Signals at the Exact Time Boundary

In Reactor documentation examples, `expectNoEvent(Duration.ofDays(1))` followed by `expectNext(0L)` works with `Mono.delay(Duration.ofDays(1))`. However, for complex operators with multiple tasks due at the same timestamp, avoid relying on task ordering if the contract does not require it; split boundaries into smaller windows or verify with `thenAwait` and `expectNext` by content.

## 8. thenAwait() Is Not Thread.sleep()

For a regular `StepVerifier`, `thenAwait(Duration)` waits in real time. For `StepVerifier.withVirtualTime`, `thenAwait` advances the virtual clock.

Example:

~~~java
StepVerifier.withVirtualTime(
        () -> Mono.just("done")
            .delayElement(Duration.ofMinutes(30)))
    .expectSubscription()
    .thenAwait(Duration.ofMinutes(30))
    .expectNext("done")
    .verifyComplete();
~~~

The test simulates a 30-minute delay without waiting 30 real minutes.

Never replace `thenAwait` with:

~~~java
Thread.sleep(30_000);
~~~

`Thread.sleep` does not advance `VirtualTimeScheduler`; instead it merely blocks the real thread for 30 seconds, slowing down tests and risking test deadline expiration.

In virtual tests, proactively advance the clock to timestamps where tasks are scheduled. If an event depends on virtual time but the test waits on `expectNext()` before calling `thenAwait()`, the verifier can hang forever.

## 9. Mono.delay: One Signal After a Scheduled Delay

`Mono.delay(Duration)` emits `Long` `0L` after the requested duration, then completes. This is the classic introductory virtual time example.

~~~java
StepVerifier.withVirtualTime(
        () -> Mono.delay(Duration.ofDays(1)))
    .expectSubscription()
    .expectNoEvent(Duration.ofDays(1))
    .expectNext(0L)
    .verifyComplete();
~~~

Expected signal trace:

~~~text
t = 0: subscribe
t = 0 .. 1 day: no onNext
t = 1 day: onNext(0)
t = 1 day: onComplete
~~~

Even though the test schedules a one-day delay, verification runs fast provided all time-dependent operators use the virtual scheduler and nothing performs real blocking work.

### delayElement vs. Mono.delay

~~~java
Mono.just("hello").delayElement(Duration.ofSeconds(5))
~~~

re-emits the `String` `"hello"` after 5 seconds. Meanwhile:

~~~java
Mono.delay(Duration.ofSeconds(5))
~~~

emits `Long` `0L`. Match the exact data type when writing `expectNext`.

## 10. Flux.interval: Multiple Ticks in Virtual Time

`Flux.interval(Duration)` emits incrementing `Long` values starting from 0, once per fixed interval. Example with a 2-second interval:

~~~java
StepVerifier.withVirtualTime(
        () -> Flux.interval(Duration.ofSeconds(2))
            .take(3))
    .expectSubscription()
    .expectNoEvent(Duration.ofSeconds(2))
    .expectNext(0L)
    .thenAwait(Duration.ofSeconds(2))
    .expectNext(1L)
    .thenAwait(Duration.ofSeconds(2))
    .expectNext(2L)
    .verifyComplete();
~~~

Trace:

~~~text
t=0s: subscribe
t=2s: onNext(0)
t=4s: onNext(1)
t=6s: onNext(2), onComplete because of take(3)
~~~

### Avoid Unbounded Intervals in Tests

Do not do this:

~~~java
StepVerifier.withVirtualTime(
        () -> Flux.interval(Duration.ofMillis(1)))
    .thenAwait(Duration.ofDays(100))
    .expectNextCount(1_000_000)
    .verifyComplete();
~~~

The Publisher is infinite, so `verifyComplete` has no completion. Moreover, a huge time jump can fire millions of tasks/ticks at once, consuming CPU and memory.

Use `take(n)`, `thenCancel`, or an explicit terminating predicate:

~~~java
StepVerifier.withVirtualTime(
        () -> Flux.interval(Duration.ofSeconds(1)))
    .expectSubscription()
    .thenAwait(Duration.ofSeconds(3))
    .expectNext(0L, 1L, 2L)
    .thenCancel()
    .verify();
~~~

`thenCancel` ends verification by cancelling the subscription; do not expect `onComplete` from an unbounded stream.

## 11. delayElements and Signal Emission Order

`delayElements(Duration)` delays each element by a duration from the time the previous element was emitted in a regulated stream. With a three-element `Flux.just`:

~~~java
StepVerifier.withVirtualTime(
        () -> Flux.just("A", "B", "C")
            .delayElements(Duration.ofSeconds(5)))
    .expectSubscription()
    .expectNoEvent(Duration.ofSeconds(5))
    .expectNext("A")
    .thenAwait(Duration.ofSeconds(5))
    .expectNext("B")
    .thenAwait(Duration.ofSeconds(5))
    .expectNext("C")
    .verifyComplete();
~~~

For this pipeline, the expected timestamps are:

~~~text
t=0s: subscribe
t=5s: A
t=10s: B
t=15s: C, complete
~~~

Do not confuse `delayElements` with `delaySequence`. `delaySequence` delays the start of the entire sequence by a duration; `delayElements` spaces out individual elements. With complex or hot sources, verify semantics per operator.

### One Single thenAwait or Multiple?

Combining into one step:

~~~java
.thenAwait(Duration.ofSeconds(15))
.expectNext("A", "B", "C")
.verifyComplete();
~~~

is usually enough when you only care about the set of values and order after 15 seconds. Splitting into three steps as above is useful when you want to verify no early emissions occur. Choose test granularity based on business requirements rather than splitting every single tick into a separate assertion.

## 12. timeout with a Virtual Clock

`Mono.timeout(Duration)` produces a `TimeoutException` if the publisher fails to respond within the deadline. Testing with `Mono.never`:

~~~java
StepVerifier.withVirtualTime(
        () -> Mono.<String>never()
            .timeout(Duration.ofSeconds(5)))
    .expectSubscription()
    .expectNoEvent(Duration.ofSeconds(4))
    .thenAwait(Duration.ofSeconds(1))
    .expectError(TimeoutException.class)
    .verify();
~~~

Trace:

~~~text
t=0s: subscribe, upstream emits nothing
t=4s: no events yet
t=5s: TimeoutException
~~~

Use `Mono.<String>never()` so the compiler knows the `String` type. `Mono.never()` neither completes nor errors on its own. The `timeout` operator generates the error when the clock hits the deadline.

### Timeout with Fallback

~~~java
StepVerifier.withVirtualTime(
        () -> Mono.<String>never()
            .timeout(Duration.ofSeconds(5))
            .onErrorReturn(TimeoutException.class, "fallback"))
    .expectSubscription()
    .thenAwait(Duration.ofSeconds(5))
    .expectNext("fallback")
    .verifyComplete();
~~~

In this case, the timeout does not surface as a terminal error because `onErrorReturn` turns it into `onNext` followed by `onComplete`. This tests **the contract of operator composition**, not merely an isolated timer.

### Do Not Confuse Internal Timeout with Verification Timeout

Two distinct kinds of timeout:

- `Mono.timeout(Duration)`: business logic of the Publisher, which can use the virtual clock.
- `StepVerifier.verify(Duration)`: real-time deadline so the verifier does not hang forever.

Example:

~~~java
StepVerifier.withVirtualTime(
        () -> Mono.delay(Duration.ofDays(10)))
    .expectSubscription()
    .thenAwait(Duration.ofDays(10))
    .expectNext(0L)
    .expectComplete()
    .verify(Duration.ofSeconds(5));
~~~

The test simulates 10 days, while capping real wall-clock verification at 5 seconds. The 5-second limit is a CI safety guard, not part of the 10-day logic.

## 13. How Is Retry with Backoff Tested?

Retry with backoff is a classic scenario requiring virtual time. A request might retry first after 1 second, next after 2 seconds, and finally succeed.

Example where the supplier constructs a fresh workflow inside the virtual scheduler:

~~~java
AtomicInteger attempts = new AtomicInteger();

StepVerifier.withVirtualTime(() ->
        Mono.defer(() -> {
                int attempt = attempts.incrementAndGet();
                return attempt < 3
                    ? Mono.<String>error(
                        new IllegalStateException("temporary"))
                    : Mono.just("ok");
            })
            .retryWhen(
                Retry.backoff(2, Duration.ofSeconds(1))
                    .jitter(0d)))
    .expectSubscription()
    .thenAwait(Duration.ofSeconds(3))
    .expectNext("ok")
    .verifyComplete();

assertEquals(3, attempts.get());
~~~

Explanation:

1. The first subscription increments `attempts` to 1 and emits an error.
2. `Retry.backoff(2, ...)` allows at most two retries.
3. The first retry arrives after 1 second.
4. The next retry arrives after 2 more seconds.
5. By 3 virtual seconds, `attempts = 3` and the result is `"ok"`.
6. `jitter(0d)` disables randomness for a deterministic test schedule.

If you keep default jitter, individual retry timings vary within the jitter range, making an exact 3-second assertion flaky. In production, jitter helps prevent thundering herds; disable it only in tests needing exact schedules.

### Do Not Create the Retry Publisher Beforehand

Do not assemble the entire `retryWhen` pipeline before `withVirtualTime` installs the scheduler and then just return that publisher. `Retry` can capture a scheduler at assembly time. Place `retryWhen` inside the lambda or inside a service method called from the lambda.

## 14. Testing Time-Bounded Operators

Operators like `take(Duration)`, `skip(Duration)`, `bufferTimeout`, `windowTimeout`, and `debounce` can depend on a scheduler. Example bounding a stream with `take(Duration)`:

~~~java
StepVerifier.withVirtualTime(() ->
        Flux.interval(Duration.ofSeconds(1))
            .take(Duration.ofMillis(3500))
            .map(n -> "tick-" + n))
    .expectSubscription()
    .thenAwait(Duration.ofMillis(3500))
    .expectNext("tick-0", "tick-1", "tick-2")
    .verifyComplete();
~~~

Expected trace:

~~~text
t=1s: tick-0
t=2s: tick-1
t=3s: tick-2
t=3.5s: onComplete due to take(Duration)
~~~

Tasks sharing the exact same timestamp may depend on operator semantics. A production test should assert the exact business boundary of interest, e.g., "no ticks after 3.5 seconds", instead of relying on incidental ordering of unrelated tasks.

### Debounce and Time Windows

When testing `debounce`, make sure the source emits events at **controlled timestamps**. If you use `Flux.just` followed by `debounce(Duration)` without spacing out emissions, all values can arrive instantaneously and only the last value is retained.

When testing `windowTimeout` or `bufferTimeout`, consider both buffer size and time boundaries; advancing the clock alone does not ensure a window receives data if inner publisher subscriptions or demand are not set up.

## 15. Using VirtualTimeScheduler Manually

`withVirtualTime` suits most tests. Sometimes code accepts an explicit `Scheduler` and you want to control that exact clock without altering global factories.

Example:

~~~java
VirtualTimeScheduler clock = VirtualTimeScheduler.create();

try {
    Flux<Long> events =
        Flux.interval(Duration.ofSeconds(2), clock)
            .take(2);

    StepVerifier.create(events)
        .expectSubscription()
        .then(() ->
            clock.advanceTimeBy(Duration.ofSeconds(2)))
        .expectNext(0L)
        .then(() ->
            clock.advanceTimeBy(Duration.ofSeconds(2)))
        .expectNext(1L)
        .verifyComplete();
} finally {
    clock.dispose();
}
~~~

Explanation:

- `VirtualTimeScheduler.create()` creates a scheduler without modifying global `Schedulers` factories.
- `Flux.interval(Duration, Scheduler)` receives `clock` directly.
- `StepVerifier.create` subscribes to the pipeline normally.
- `then(Runnable)` calls `advanceTimeBy` after subscription is established.
- The clock executes due tasks and the verifier reads the signals.
- `finally` disposes the clock to avoid leaking resources across tests.

If a source is written to accept a `Scheduler` via constructor, this design is very unit-test friendly:

~~~java
public final class ScheduledAlerts {

    private final Scheduler scheduler;

    public ScheduledAlerts(Scheduler scheduler) {
        this.scheduler = scheduler;
    }

    public Flux<Long> ticks() {
        return Flux.interval(Duration.ofSeconds(2), scheduler);
    }
}
~~~

In production, inject a real scheduler. In tests, inject `VirtualTimeScheduler` and advance the clock manually.

## 16. withVirtualTime and Custom Schedulers

`withVirtualTime` replaces schedulers obtained from Reactor's default factories. It does not automatically replace every custom `Scheduler`.

Problem example:

~~~java
Scheduler explicitScheduler = Schedulers.newSingle("external");

Flux<Long> stream = Flux.interval(
    Duration.ofSeconds(1),
    explicitScheduler);
~~~

If `explicitScheduler` is created ahead of time and passed into `Flux.interval`, `withVirtualTime` cannot control it. The test advances virtual time while the operator still schedules on the real thread/scheduler.

Better approaches:

- Pass `Scheduler` as a dependency so tests can inject `VirtualTimeScheduler`.
- Or avoid passing a custom scheduler when unneeded and build the operator **inside the supplier** so it uses the virtualized default scheduler.
- Or use the `withVirtualTime` overload accepting a `VirtualTimeScheduler` supplier when you need to control the scheduler instance.

Never assume that wrapping a publisher in a lambda replaces every timer across every library.

### Does withVirtualTime Create a "Private Time" Per Thread?

No. `VirtualTimeScheduler` alters how Reactor's default Schedulers are provided during the test. Multiple operators can share one virtual clock. This differs from adjusting a `java.time.Clock` per thread and can affect other tests running in parallel.

## 17. Testing Backpressure with Virtual Time

`StepVerifier` provides `withVirtualTime(Supplier, long initialRequest)` to control initial demand.

Example:

~~~java
StepVerifier.withVirtualTime(
        () -> Flux.interval(Duration.ofSeconds(1)).take(2),
        0)
    .expectSubscription()
    .thenRequest(1)
    .thenAwait(Duration.ofSeconds(1))
    .expectNext(0L)
    .thenRequest(1)
    .thenAwait(Duration.ofSeconds(1))
    .expectNext(1L)
    .verifyComplete();
~~~

Explanation:

- `initialRequest = 0`: no elements requested yet.
- `thenRequest(1)`: requests one element before the first tick.
- `thenAwait(1 second)`: advances to tick 0.
- `thenRequest(1)`: opens one more unit of demand.
- `thenAwait(1 second)`: advances to tick 1.
- `take(2)` completes after two values.

`Flux.interval` can emit an overflow error if a tick fires when downstream has not requested enough. That is a meaningful property when testing pressure, not a bug in virtual time.

### Backpressure and Virtual Clock Are Two Orthogonal Axes

Virtual time controls **when tasks run**. Request demand controls **how many elements the publisher is allowed to emit**. A correct test satisfies both. If the clock advances with no demand, `interval` may fail to emit or error; if demand exists but the clock has not advanced, `interval` has not ticked yet.

Do not use `withVirtualTime` as a way to ignore Reactive Streams backpressure.

## 18. When Are expectNextCount, thenCancel, or verifyThenAssertThat Useful?

When verifying many uniformly formatted elements:

~~~java
StepVerifier.withVirtualTime(
        () -> Flux.interval(Duration.ofSeconds(1)).take(100))
    .expectSubscription()
    .thenAwait(Duration.ofSeconds(100))
    .expectNextCount(100)
    .verifyComplete();
~~~

`expectNextCount` checks the exact element count without checking values. If values or ordering matter, use `expectNext` or `assertNext`.

For unbounded publishers:

~~~java
StepVerifier.withVirtualTime(
        () -> Flux.interval(Duration.ofSeconds(1)))
    .expectSubscription()
    .thenAwait(Duration.ofSeconds(2))
    .expectNext(0L, 1L)
    .thenCancel()
    .verify();
~~~

`verifyThenAssertThat` is helpful when you need to inspect dropped elements or post-scenario state after the verifier replays the script. Use it only when the test genuinely needs post-execution assertions; there is no need to attach it to every time-based test.

### expectNext When the Clock Has Not Advanced

If a source has a timer, the following easily hangs:

~~~java
StepVerifier.withVirtualTime(
        () -> Mono.delay(Duration.ofDays(1)))
    .expectSubscription()
    .expectNext(0L)
    .verifyComplete();
~~~

Here the verifier waits for `onNext` before advancing the clock. Because no `onNext` arrives, completion is never reached. Add `thenAwait` or `expectNoEvent` before `expectNext`.

## 19. Setting a Real Verification Timeout

Virtual tests can hang if a real source blocks, a custom scheduler is not replaced, or `thenAwait` is missing. To prevent CI from hanging forever, add a real-time timeout:

~~~java
StepVerifier.withVirtualTime(
        () -> Mono.delay(Duration.ofDays(30)))
    .expectSubscription()
    .thenAwait(Duration.ofDays(30))
    .expectNext(0L)
    .expectComplete()
    .verify(Duration.ofSeconds(5));
~~~

This is a safe pattern: the test simulates 30 days yet must finish within 5 wall-clock seconds.

`StepVerifier` also has a default timeout configurable for an entire test suite. However, changing the global static default timeout can affect other tests; prefer `verify(Duration)` on individual tests when specific rules are needed.

If the real-time timeout triggers, check:

1. Was the publisher created inside the supplier?
2. Was a custom scheduler created beforehand?
3. Is there `Thread.sleep`, real I/O, or a blocking source?
4. Is `thenAwait`/`expectNoEvent` missing to advance the clock?
5. Is an infinite publisher paired with `verifyComplete`?
6. Is there sufficient demand for `Flux.interval`?
7. Did an operator inside `flatMap` fail to register its timer before the clock advanced?

Do not fix it simply by raising the verification timeout to minutes. Find out why the event did not appear first.

## 20. Virtual Time and Inner Publishers in flatMap

A tricky case: an outer `Flux` emits elements and `flatMap` creates an inner publisher with a timer.

~~~java
Flux<String> source = Flux.just("A", "B")
    .flatMap(value ->
        Mono.delay(Duration.ofSeconds(5))
            .map(tick -> value));
~~~

If `source` is created inside the supplier, the scheduler can be virtualized. However, when using a very large `StepVerifier.thenAwait`, inner publisher creation, timer registration order, and clock advancement may not behave like a simple linear program.

Per the `StepVerifier` Javadoc, virtual time can be incompatible in certain cases where an inner delay is scheduled after the clock has already advanced, causing expected events not to appear.

A clearer way to write the test is to let the source emit elements and advance the clock in stages:

~~~java
StepVerifier.withVirtualTime(() ->
        Flux.just("A", "B")
            .flatMap(value ->
                Mono.delay(Duration.ofSeconds(5))
                    .map(tick -> value)))
    .expectSubscription()
    .thenAwait(Duration.ofSeconds(5))
    .expectNextCount(2)
    .verifyComplete();
~~~

Because `Flux.just` emits A and B synchronously upon subscribing, both inner timers are registered before advancing 5 seconds. With slow sources or hot producers, construct scenarios around when each inner publisher is actually subscribed to.

If A/B ordering is mandatory, replace `flatMap` with `concatMap` and advance enough time for both sequential inner publishers:

~~~java
StepVerifier.withVirtualTime(() ->
        Flux.just("A", "B")
            .concatMap(value ->
                Mono.delay(Duration.ofSeconds(5))
                    .map(tick -> value)))
    .expectSubscription()
    .thenAwait(Duration.ofSeconds(5))
    .expectNext("A")
    .thenAwait(Duration.ofSeconds(5))
    .expectNext("B")
    .verifyComplete();
~~~

Here B is processed after A; total virtual time is 10 seconds. The difference stems from `flatMap` vs. `concatMap` semantics, not test randomness.

## 21. Boundaries That Virtual Time Does Not Control

`VirtualTimeScheduler` does not alter the OS clock or replace every time source in the JVM.

| Operation | Uses virtual time automatically? | Appropriate testing approach |
| --- | --- | --- |
| `Mono.delay` with default scheduler created in supplier | Yes | `withVirtualTime` |
| `Flux.interval` with default scheduler created in supplier | Yes | `withVirtualTime` |
| `delayElements` with appropriate default scheduler | Usually yes | `withVirtualTime` |
| `retryWhen` using default Reactor scheduler at the right time | Possibly | `withVirtualTime`, disable jitter for determinism |
| Publisher using pre-created custom `Scheduler` | Not automatically | Inject `VirtualTimeScheduler` explicitly |
| `Thread.sleep` | No | Refactor away sleep, inject scheduler |
| `java.time.Clock.systemUTC()` | No | Inject a fake/fixed `java.time.Clock` |
| `System.currentTimeMillis()` | No | Inject `Clock` or time provider |
| Real HTTP/`WebClient` network delay | No | MockWebServer, fake transport, separate tests |
| Real database TTL / Redis expiration | No | Integration tests with suitable environment |
| Cron scheduler from another system | Not automatically | Test scheduling component separately |
| `CompletableFuture.delayedExecutor` outside Reactor | Not automatically | Inject appropriate executor/clock |

For example, if business logic compares `Instant.now()` with a deadline, calling `StepVerifier.withVirtualTime` alone does not change `Instant.now()`. Pass `java.time.Clock` into the service:

~~~java
public final class ExpiryPolicy {

    private final Clock clock;

    public ExpiryPolicy(Clock clock) {
        this.clock = clock;
    }

    public boolean expired(Instant deadline) {
        return !Instant.now(clock).isBefore(deadline);
    }
}
~~~

In unit tests you can use `Clock.fixed` or `Clock.offset`. That is a separate concern from Reactor's timer `Scheduler`. Both mechanisms can be combined when an application uses both a business clock and time-based operators.

## 22. Hands-On Java 17+ Project with Maven and JUnit 5

The project below is a Reactor unit test suite runnable with Maven. It does not need to start a WebFlux HTTP server because the goal is testing Reactor operators in isolation. The Spring Boot 3.3.5 parent manages Reactor versions compatible with the Spring Framework ecosystem.

### Directory Structure

~~~text
reactor-virtual-time-demo/
├── pom.xml
└── src
    ├── main/java/com/example/virtualtime
    │   └── TimeBasedService.java
    └── test/java/com/example/virtualtime
        └── VirtualTimeExamplesTest.java
~~~

### pom.xml

~~~xml
<project xmlns="http://maven.apache.org/POM/4.0.0"
         xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
         xsi:schemaLocation="http://maven.apache.org/POM/4.0.0 https://maven.apache.org/xsd/maven-4.0.0.xsd">
  <modelVersion>4.0.0</modelVersion>

  <parent>
    <groupId>org.springframework.boot</groupId>
    <artifactId>spring-boot-starter-parent</artifactId>
    <version>3.3.5</version>
    <relativePath/>
  </parent>

  <groupId>com.example</groupId>
  <artifactId>reactor-virtual-time-demo</artifactId>
  <version>1.0.0</version>

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
        <groupId>org.apache.maven.plugins</groupId>
        <artifactId>maven-surefire-plugin</artifactId>
      </plugin>
    </plugins>
  </build>
</project>
~~~

### TimeBasedService.java

~~~java
package com.example.virtualtime;

import java.time.Duration;
import java.util.concurrent.TimeoutException;
import java.util.concurrent.atomic.AtomicInteger;

import reactor.core.publisher.Flux;
import reactor.core.publisher.Mono;
import reactor.util.retry.Retry;

public class TimeBasedService {

    public Flux<String> heartbeat(int count) {
        return Flux.interval(Duration.ofSeconds(10))
            .take(count)
            .map(index -> "heartbeat-" + index);
    }

    public Mono<String> delayedNotice() {
        return Mono.just("ready")
            .delayElement(Duration.ofMinutes(5));
    }

    public Mono<String> expireAndFallback() {
        return Mono.<String>never()
            .timeout(Duration.ofSeconds(5))
            .onErrorReturn(
                TimeoutException.class, "fallback");
    }

    public Mono<String> retryThenSucceed(
            AtomicInteger attempts) {

        return Mono.defer(() -> {
                int attempt = attempts.incrementAndGet();
                if (attempt < 3) {
                    return Mono.<String>error(
                        new IllegalStateException(
                            "attempt-" + attempt));
                }
                return Mono.just("ok");
            })
            .retryWhen(
                Retry.backoff(2, Duration.ofSeconds(1))
                    .jitter(0d));
    }

    public Flux<String> ticksInWindow() {
        return Flux.interval(Duration.ofSeconds(1))
            .take(Duration.ofMillis(3500))
            .map(index -> "tick-" + index);
    }
}
~~~

Notice `heartbeat()` creates `Flux.interval` **when the method is called**, not in a constructor or static field. Each test calls `service.heartbeat(...)` from the Supplier passed to `withVirtualTime`.

### VirtualTimeExamplesTest.java — Test Cases

~~~java
package com.example.virtualtime;

import static org.junit.jupiter.api.Assertions.assertEquals;

import java.time.Duration;
import java.util.concurrent.TimeUnit;
import java.util.concurrent.TimeoutException;
import java.util.concurrent.atomic.AtomicInteger;

import org.junit.jupiter.api.Test;

import reactor.core.publisher.Flux;
import reactor.core.publisher.Mono;
import reactor.test.StepVerifier;
import reactor.test.StepVerifierOptions;
import reactor.test.scheduler.VirtualTimeScheduler;

class VirtualTimeExamplesTest {

    private final TimeBasedService service =
        new TimeBasedService();

    @Test
    void oneDayDelayEmitsWithoutWaitingOneRealDay() {
        StepVerifier.withVirtualTime(
                () -> Mono.delay(Duration.ofDays(1)))
            .expectSubscription()
            .expectNoEvent(Duration.ofDays(1))
            .expectNext(0L)
            .verifyComplete();
    }

    @Test
    void serviceCreatesTimeOperatorAfterVirtualSetup() {
        StepVerifier.withVirtualTime(
                () -> service.heartbeat(3))
            .expectSubscription()
            .expectNoEvent(Duration.ofSeconds(10))
            .expectNext("heartbeat-0")
            .thenAwait(Duration.ofSeconds(10))
            .expectNext("heartbeat-1")
            .thenAwait(Duration.ofSeconds(10))
            .expectNext("heartbeat-2")
            .verifyComplete();
    }

    @Test
    void delayedElementUsesVirtualClock() {
        StepVerifier.withVirtualTime(
                service::delayedNotice)
            .expectSubscription()
            .thenAwait(Duration.ofMinutes(5))
            .expectNext("ready")
            .verifyComplete();
    }

    @Test
    void timeoutFiresAtVirtualDeadline() {
        StepVerifier.withVirtualTime(() ->
                Mono.<String>never()
                    .timeout(Duration.ofSeconds(5)))
            .expectSubscription()
            .expectNoEvent(Duration.ofSeconds(4))
            .thenAwait(Duration.ofSeconds(1))
            .expectError(TimeoutException.class)
            .verify();
    }

    @Test
    void timeoutFallbackIsDecodedAsValue() {
        StepVerifier.withVirtualTime(
                service::expireAndFallback)
            .expectSubscription()
            .thenAwait(Duration.ofSeconds(5))
            .expectNext("fallback")
            .verifyComplete();
    }

    @Test
    void retryBackoffUsesDeterministicVirtualTime() {
        AtomicInteger attempts = new AtomicInteger();

        StepVerifier.withVirtualTime(
                () -> service.retryThenSucceed(attempts))
            .expectSubscription()
            .thenAwait(Duration.ofSeconds(3))
            .expectNext("ok")
            .verifyComplete();

        assertEquals(3, attempts.get());
    }

    @Test
    void takeDurationEndsStreamAtConfiguredWindow() {
        StepVerifier.withVirtualTime(
                service::ticksInWindow)
            .expectSubscription()
            .thenAwait(Duration.ofMillis(3500))
            .expectNext(
                "tick-0", "tick-1", "tick-2")
            .verifyComplete();
    }

    @Test
    void infiniteIntervalIsCancelledAfterThreeTicks() {
        StepVerifier.withVirtualTime(() ->
                Flux.interval(Duration.ofMinutes(1)))
            .expectSubscription()
            .thenAwait(Duration.ofMinutes(3))
            .expectNext(0L, 1L, 2L)
            .thenCancel()
            .verify();
    }

    @Test
    void controlledDemandWorksWithVirtualTime() {
        StepVerifier.withVirtualTime(
                () -> Flux.interval(Duration.ofSeconds(1))
                    .take(2),
                0)
            .expectSubscription()
            .thenRequest(1)
            .thenAwait(Duration.ofSeconds(1))
            .expectNext(0L)
            .thenRequest(1)
            .thenAwait(Duration.ofSeconds(1))
            .expectNext(1L)
            .verifyComplete();
    }

    @Test
    void explicitSchedulerCanAdvanceManually() {
        VirtualTimeScheduler clock =
            VirtualTimeScheduler.create();

        try {
            Flux<Long> events =
                Flux.interval(Duration.ofSeconds(2), clock)
                    .take(2);

            StepVerifier.create(events)
                .expectSubscription()
                .then(() ->
                    clock.advanceTimeBy(
                        Duration.ofSeconds(2)))
                .expectNext(0L)
                .then(() ->
                    clock.advanceTimeBy(
                        Duration.ofSeconds(2)))
                .expectNext(1L)
                .verifyComplete();
        } finally {
            clock.dispose();
        }
    }

    @Test
    void namedScenarioHasWallClockVerificationGuard() {
        StepVerifier.withVirtualTime(
                () -> Mono.delay(Duration.ofDays(2)),
                StepVerifierOptions.create()
                    .scenarioName("two-day-delay"))
            .expectSubscription()
            .thenAwait(Duration.ofDays(2))
            .expectNext(0L)
            .expectComplete()
            .verify(Duration.ofSeconds(5));
    }

    @Test
    void supplierIsInvokedDuringVirtualScenarioSetup() {
        AtomicInteger assemblies = new AtomicInteger();

        StepVerifier.withVirtualTime(() -> {
                assemblies.incrementAndGet();
                return Mono.delay(
                    Duration.ofSeconds(20));
            })
            .expectSubscription()
            .thenAwait(Duration.ofSeconds(20))
            .expectNext(0L)
            .verifyComplete();

        assertEquals(1, assemblies.get());
    }
}
~~~

These tests never call `Thread.sleep`. They use one of two techniques:

- `withVirtualTime` creates the publisher after Reactor installs the virtual scheduler.
- `VirtualTimeScheduler.create` creates an explicit clock and passes it to `Flux.interval(..., clock)`.

### Running the Project

Requires Java 17+ and Maven 3.8+ in an environment able to download dependencies:

~~~bash
java -version
mvn -version
mvn -q clean test
~~~

When all 12 tests pass, Maven exits with code 0. Depending on logging settings, run Maven without `-q` to inspect the test summary:

~~~bash
mvn test
~~~

An expected summary snippet when all tests pass:

~~~text
Tests run: 12, Failures: 0, Errors: 0, Skipped: 0
BUILD SUCCESS
~~~

This output is **illustrative**; exact log line counts, ordering, and timings depend on the Maven environment. Do not interpret it as test output executed in the current environment.

## 23. Reading Each Test: Scenario and Outcome

### Test 1 — One Virtual Day

`oneDayDelayEmitsWithoutWaitingOneRealDay` tests a one-day `Mono.delay`. It confirms no signal arrives before one virtual day and then receives `Long` 0.

Logical outcome:

~~~text
subscribe -> no event for 1 virtual day -> onNext(0) -> onComplete
~~~

### Test 2 — Creating Publisher Inside Supplier

`serviceCreatesTimeOperatorAfterVirtualSetup` checks three heartbeats. The first arrives at second 10, the next at seconds 20 and 30. This directly demonstrates the lesson's theme: calling `service.heartbeat(3)` inside the supplier builds `Flux.interval` after the virtual scheduler is ready.

### Test 3 — delayElement

`delayedElementUsesVirtualClock` passes the method reference `service::delayedNotice`. The method executes only when `StepVerifier` sets up the scenario, so `delayElement` uses the right scheduler.

### Tests 4 and 5 — timeout

`timeoutFiresAtVirtualDeadline` asserts a `TimeoutException` at 5 seconds. `timeoutFallbackIsDecodedAsValue` verifies the error handler converts it into a fallback `String`. Both tests share a silent source yet have different output contracts.

### Test 6 — Retry Backoff

`retryBackoffUsesDeterministicVirtualTime` disables jitter and asserts `attempts = 3`. Without `jitter(0d)`, the 3-second mark might no longer be deterministic.

### Test 7 — take(Duration)

`takeDurationEndsStreamAtConfiguredWindow` emits ticks at 1, 2, 3 seconds and completes at 3.5 seconds without waiting for second 4.

### Test 8 — Cancellation

`infiniteIntervalIsCancelledAfterThreeTicks` does not expect `onComplete` from an infinite `Flux`. `thenCancel` expresses finite consumption of a stream without natural completion.

### Test 9 — Demand

`controlledDemandWorksWithVirtualTime` shows that the clock and `request(n)` are two independent conditions. Failing to request more elements in time can cause `interval` to emit an overflow error.

### Test 10 — Manual Clock

`explicitSchedulerCanAdvanceManually` does not alter global factories; the clock is passed directly into the operator and `StepVerifier.create` invokes `advanceTimeBy` via `then(Runnable)`.

### Test 11 — Real Timeout

`namedScenarioHasWallClockVerificationGuard` uses two virtual days, while verification must finish within 5 real seconds. The scenario name makes failure messages easier to read.

### Test 12 — Supplier Executed After Setup

`supplierIsInvokedDuringVirtualScenarioSetup` counts lambda invocations, proving the scenario is created within the verifier's setup context. No pre-cached publisher is used to bypass lazy creation.

## 24. When StepVerifierOptions Is Needed

`StepVerifierOptions` supports extra scenario configuration, such as test names and virtual scheduler suppliers in the matching overloads.

Example naming a scenario:

~~~java
StepVerifier.withVirtualTime(
        () -> Flux.interval(Duration.ofSeconds(1))
            .take(2),
        StepVerifierOptions.create()
            .scenarioName("heartbeat-second-by-second"))
    .expectSubscription()
    .thenAwait(Duration.ofSeconds(2))
    .expectNext(0L, 1L)
    .verifyComplete();
~~~

Scenario names are especially useful when multiple `StepVerifier` instances have nearly identical assertions. The name aids failure diagnosis and does not alter publisher semantics.

If you need to control initial demand, `withVirtualTime(supplier, long initialRequest)` is the direct option. For specialized scenarios needing a custom scheduler, overloads accept a `VirtualTimeScheduler` supplier and initial request, or `StepVerifierOptions` with `virtualTimeSchedulerSupplier`.

When using custom overloads, make sure the supplied scheduler is genuinely the clock used by the timed operators in the scenario. Never create two separate instances and advance one clock while operators schedule on the other.

## 25. Race Conditions and Interference Between Tests

`withVirtualTime` alters Reactor's process-wide scheduler factories for the duration of the test. This introduces risks:

- Test A installs a virtual clock while Test B uses default time operators.
- A singleton creates an `interval` while Test A has installed the virtual scheduler, and is later used after the scheduler resets.
- A parallel test advances virtual time unexpectedly for another test.
- A custom `Scheduler` outlives the test.
- A test fails to clean up the clock after manually setting the global factory.

Recommendations:

1. Do not run virtual-time tests that touch global scheduler factories in parallel without an isolation strategy.
2. Create time-dependent publishers inside each scenario's supplier.
3. Avoid static `Flux.interval`/`Mono.delay` assembled during class initialization.
4. Prefer isolated tests for time-based logic instead of mixing virtual clocks into integration tests with real HTTP/network.
5. If you manually create a `VirtualTimeScheduler`, dispose it in `finally` or `@AfterEach`.
6. If you override global schedulers via `VirtualTimeScheduler.getOrSet` or manual setters, restore/reset properly in lifecycle hooks; with `StepVerifier.withVirtualTime`, let the framework manage setup/cleanup via its API.
7. Separate time unit tests from load/performance tests.

Do not indiscriminately call `Schedulers.resetFactory()` while other tests are still using schedulers. Parallel test settings and lifecycles should be designed at the project level.

## 26. Common Pitfalls and Fixes

1. **Creating `Flux.interval` before `withVirtualTime`.** The publisher may capture the real scheduler; create it inside the `Supplier`.
2. **Supplier merely returns a pre-cached publisher.** Fails to ensure laziness; move time operators into a factory/method called inside the lambda.
3. **Putting `expectNoEvent` as the first step.** `onSubscribe` is also an event; add `expectSubscription` first.
4. **Forgetting `thenAwait`.** Without advancing the clock, timers never fire and the verifier can hang.
5. **Confusing `thenAwait` with `expectNoEvent`.** `thenAwait` does not assert silence; `expectNoEvent` checks that no signals occur.
6. **Using `Thread.sleep` in virtual tests.** It only waits in real time; use `thenAwait` or `advanceTimeBy`.
7. **Using a pre-created custom `Scheduler`.** `withVirtualTime` cannot control it automatically; inject `VirtualTimeScheduler` directly.
8. **Using an infinite publisher with `verifyComplete`.** There is no completion; use `take(n)`, `thenCancel`, or an explicit contract timeout.
9. **Advancing the clock too far on dense intervals.** Can fire huge numbers of tasks; bound event counts and durations.
10. **Reading time via `Instant.now()` expecting virtual clock behavior.** Inject `java.time.Clock` for wall-clock logic.
11. **Testing real socket timeouts with virtual time.** OS/network stacks have their own timers; use integration tests or fake transports.
12. **Forgetting initial demand.** `Flux.interval` can overflow; issue `thenRequest` at the right moments.
13. **Using `Retry.backoff` with jitter while asserting exact timestamps.** Disable jitter in tests needing fixed schedules.
14. **Building the retry publisher outside the supplier.** Retry may capture the previously chosen scheduler; build inside the lambda.
15. **Using `flatMap` with inner delays and one premature `thenAwait`.** Inner timers may not be scheduled yet; split steps or inspect operator semantics.
16. **Using `concatMap` and expecting two inner publishers at the same timestamp.** `concatMap` runs sequentially; advance enough time for each inner one.
17. **Calling unbounded `verify()` on hang-prone tests.** Use `expectComplete().verify(Duration)` as a wall-clock guard.
18. **Raising the verification timeout too high instead of fixing the scheduler.** Find the root cause: eager assembly, custom scheduler, or blocking I/O.
19. **Running virtual-time tests in parallel without isolation.** Scheduler factories are shared process state; serialize or isolate tests.
20. **Failing to clean up a manual `VirtualTimeScheduler`.** Can leak resources and interfere with subsequent tests.
21. **Assuming virtual time accurately models performance.** It tests timing semantics, not real scheduler, CPU, network, or DB speed.
22. **Asserting thread names.** Virtual time does not guarantee thread identity preservation; assert signals and logical timestamps.
23. **Relying on tie-breaking order of simultaneous tasks not required by contract.** Makes tests brittle; define exact business boundaries to verify.
24. **Ignoring cancellation/backpressure.** Even with a virtual clock, demand and subscription termination still need to be specified.

## 27. Checklist Before Writing a Virtual-Time Test

- Which timed operators does the publisher need tested?
- Do those operators use default Reactor-managed `Scheduler`s?
- Are the publisher and timed operators created inside the `Supplier`?
- Does the service have a static/constructor field assembling `Flux.interval` eagerly?
- Does the test call the service method inside the supplier rather than outside?
- Is there a pre-created custom `Scheduler`?
- If so, is the scheduler injected as a `VirtualTimeScheduler`?
- Does `expectSubscription` precede `expectNoEvent`?
- Does `thenAwait` advance far enough for the tested timer to fire?
- Does the test require silence beforehand or only advancing the clock?
- Are signal data types exact, e.g., `Mono.delay` emitting `Long` 0?
- Does the publisher have natural completion?
- If infinite, is there `take(n)` or `thenCancel`?
- Are `initialRequest`/backpressure controlled if needed?
- Are `Thread.sleep` and blocking I/O removed from the virtual scenario?
- Is a separate `java.time.Clock` used when testing business wall-clock logic?
- Is jitter disabled if checking an exact retry schedule?
- Is there a wall-clock verification guard if the scenario might hang?
- Do parallel virtual-time tests interfere with global schedulers?
- Are manually created schedulers cleaned up?
- Do expected outputs specify the exact order of `onNext`/`onError`/`onComplete`?

## 28. Self-Check Exercises

**Question 1.** Does `withVirtualTime` accept a `Publisher` or a `Supplier<Publisher>`?  
**Answer:** It accepts a `Supplier<Publisher>`, allowing the publisher to be created after the virtual scheduler is set up.

**Question 2.** Why should `Flux.interval` not be created outside the lambda?  
**Answer:** The operator may capture the real scheduler at assembly time; advancing the virtual clock will not trigger it.

**Question 3.** Is Reactor `Context` directly tied to `VirtualTimeScheduler`?  
**Answer:** No. Reactor `Context` propagates subscriber data; `VirtualTimeScheduler` controls task timing.

**Question 4.** How does `thenAwait` differ from `expectNoEvent`?  
**Answer:** Both can advance time, but `expectNoEvent` also asserts that no signals occur during that interval.

**Question 5.** Why is `expectSubscription` needed before `expectNoEvent`?  
**Answer:** Because `onSubscribe` is treated as an event and would cause `expectNoEvent` as the first step to fail.

**Question 6.** What value does `Mono.delay(Duration.ofSeconds(2))` emit?  
**Answer:** `Long` `0L` after 2 seconds, then completes.

**Question 7.** When does `Flux.interval(Duration.ofSeconds(1)).take(3)` emit?  
**Answer:** `Long` `0L`, `1L`, `2L` at seconds 1, 2, 3, then completes.

**Question 8.** How can virtual time be advanced?  
**Answer:** `thenAwait`, `expectNoEvent`, or `VirtualTimeScheduler.advanceTimeBy`/`advanceTimeTo`.

**Question 9.** Does `Thread.sleep` advance the virtual clock?  
**Answer:** No, it only blocks the real thread.

**Question 10.** Is `verify(Duration.ofSeconds(5))` a logic timeout or a verifier timeout?  
**Answer:** A real-time `StepVerifier` timeout to prevent waiting too long.

**Question 11.** How should `Retry.backoff` with jitter be handled when testing exact timestamps?  
**Answer:** Disable jitter via `jitter(0d)` in tests, without necessarily removing jitter in production.

**Question 12.** Why is `thenCancel` needed with an infinite interval?  
**Answer:** Because the source never completes on its own; cancellation is a valid termination of the scenario.

**Question 13.** Can virtual time be used to test `java.time.Clock.systemUTC`?  
**Answer:** Not automatically; inject `Clock.fixed` or a fake clock.

**Question 14.** If a source uses a pre-created `Schedulers.newSingle`, does `withVirtualTime` replace it?  
**Answer:** Not guaranteed; inject `VirtualTimeScheduler` or refactor the time operator.

**Question 15.** What is the single most important condition for reliable `withVirtualTime` tests?  
**Answer:** Time-dependent publishers must be created after the virtual scheduler is activated, typically by constructing the entire chain inside the `Supplier`.

## 29. Key Takeaways

`StepVerifier.withVirtualTime` replaces Reactor's default scheduler factory with `VirtualTimeScheduler` and lets you test time-dependent operators without wall-clock waiting. The API takes a `Supplier` to **create the publisher after the virtual scheduler is installed**. A lambda returning an already-created `Flux` is not guaranteed to work; operators such as `delay`, `interval`, `timeout`, or `retry` must be constructed inside the supplier or a factory method invoked from it.

`expectSubscription` should precede `expectNoEvent` because `onSubscribe` is also a signal. `thenAwait` advances time without asserting no events; `expectNoEvent` both advances time and asserts silence. If a publisher is infinite, use `take` or `thenCancel`; to guard against hanging tests, use `verify(Duration)` as a wall-clock guard.

`VirtualTimeScheduler` only manages work scheduled on compatible schedulers. It does not control `Thread.sleep`, system time, networks, databases, or pre-created custom schedulers. You can inject `VirtualTimeScheduler` and advance its clock manually to test code accepting an explicit `Scheduler`. For stable tests, control demand, retry jitter, inner publishers, scheduler lifecycles, and parallel test interference.

### References

- Project Reactor, [Testing — Manipulating Time](https://projectreactor.io/docs/core/release/reference/testing.html#_manipulating_time).
- Project Reactor, [StepVerifier Javadoc](https://projectreactor.io/docs/test/release/api/reactor/test/StepVerifier.html).
- Project Reactor, [VirtualTimeScheduler Javadoc](https://projectreactor.io/docs/test/release/api/reactor/test/scheduler/VirtualTimeScheduler.html).
- Project Reactor, [Reactor Core Reference](https://projectreactor.io/docs/core/release/reference/).
- Project Reactor, [Retry Javadoc](https://projectreactor.io/docs/core/release/api/reactor/util/retry/Retry.html).
- Spring Boot, [Testing Spring Boot Applications](https://docs.spring.io/spring-boot/reference/testing/).

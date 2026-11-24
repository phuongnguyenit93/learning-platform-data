# Controlling Initial Requests and thenRequest When Testing Reactor with StepVerifier

## 1. Lesson Objectives

When testing `Mono` or `Flux` in Reactor, we often write:

~~~java
StepVerifier.create(Flux.just(1, 2, 3))
    .expectNext(1, 2, 3)
    .verifyComplete();
~~~

This example confirms the emitted value sequence and completion. However, it does not test how the Publisher behaves when a Subscriber **only requests a bounded number of elements**.

In Reactive Streams, a Subscriber does not passively receive all values. After `onSubscribe`, the Subscriber controls consumption rate via `Subscription.request(n)`. The number of items still permitted to be emitted is called **outstanding demand**. Testing this is especially important for large data sources, pagination, streams, queues, backpressure, prefetching operators, or a custom Publisher implemented by your team.

`StepVerifier` in the `reactor-test` module lets you:

- Set the initial demand via `StepVerifier.create(publisher, initialRequest)`.
- Configure the same thing via `StepVerifierOptions.initialRequest(long)`.
- Explicitly request more items at specific points using `thenRequest(n)`.
- Assert that items arrive right after those requests with `expectNext` / `expectNextCount`.
- Distinguish `onNext` signals from terminal `onComplete`, `onError`, and `cancel`.
- Detect test scenarios that request fewer items than they expect via under-requesting checks.
- Observe that downstream demand and upstream requests differ when operators reshape requests.

**Main takeaway:** Controlling demand lets you test the Publisher–Subscriber coordination mechanism, not merely the contents of a list.

## 2. Reactive Streams Foundations: Who Requests Data?

The basic dialogue:

~~~text
Subscriber                    Publisher
    |                             |
    |------ subscribe() --------->|
    |<----- onSubscribe(sub) ------|
    |                             |
    |------ sub.request(2) ------>|
    |<----- onNext(item1) ---------|
    |<----- onNext(item2) ---------|
    |                             |
    |------ sub.request(3) ------>|
    |<----- onNext(item3) ---------|
    |<----- onNext(item4) ---------|
    |<----- onNext(item5) ---------|
    |<----- onComplete() ----------|
~~~

The rules:

1. `onSubscribe` delivers the `Subscription` to the Subscriber.
2. `request(n)` with `n > 0` grants permission to emit up to n additional `onNext` signals, on top of remaining demand.
3. If the Subscriber requests more, demand is **cumulative**, not replacing old demand.
4. `onNext` consumes one unit of demand; `onComplete` and `onError` are terminal signals, not data items, and do not consume demand.
5. `cancel()` asks to stop the subscription; after cancellation, no `onNext` may be emitted to that subscriber per the contract.
6. `Long.MAX_VALUE` represents unbounded demand.
7. `request(0)` or negative numbers are not valid data requests per Reactive Streams; do not use them as a way to "pause".

### Formula for Tracking Outstanding Demand

When there is no unbounded demand or over-requesting:

~~~text
new outstanding demand
  = previous outstanding demand
  + added request amount
  - emitted onNext count
~~~

Example:

| Action | Outstanding demand |
| --- | ---: |
| Subscribe with initialRequest = 0 | 0 |
| request(2) | 2 |
| Publisher emits item A | 1 |
| request(3) | 4 |
| Publisher emits item B | 3 |
| Publisher emits item C | 2 |

When cumulative additions exceed the limit, Reactor uses saturating addition capped at `Long.MAX_VALUE` rather than letting overflow turn demand negative.

**Important caveat:** This formula describes demand observed at a single Subscription. When `buffer`, `flatMap`, `publishOn`, or `limitRate` sits in between, upstream may see different requests than downstream because operators transform demand and prefetch.

## 3. StepVerifier Acts as a Test Subscriber

`StepVerifier` is an API for building a "signal script" and then subscribing to a Publisher to verify it. Example:

~~~java
Flux<Integer> source = Flux.just(10, 20, 30);

StepVerifier.create(source)
    .expectSubscription()
    .expectNext(10)
    .expectNext(20, 30)
    .verifyComplete();
~~~

Distinguish two phases:

- **Assembly:** calling `create`, `expectNext`, `thenRequest` to declare the script.
- **Verification:** calling `verify()`, `verifyComplete()`, or a similar verify API to actually subscribe and execute the test.

If you only build the script without calling verify, the test can finish without verifying a single signal.

### What Is the Default Demand?

Per the `StepVerifierOptions` Javadoc, the overload:

~~~java
StepVerifier.create(source)
~~~

creates an **unbounded** initial request by default, equivalent to `Long.MAX_VALUE`.

This is why simple tests receive every element right away. If you only want to assert values, this default is completely reasonable. However, if you want to test batched requests, you must **explicitly configure initial demand**.

### Why `thenRequest` After Default Unbounded Is Not Useful

~~~java
StepVerifier.create(source)
    .expectNext(10)
    .thenRequest(1)
    .expectNext(20, 30)
    .verifyComplete();
~~~

The scenario above does not test "emit items only after thenRequest(1)": the Subscriber already granted unbounded demand from the start. `thenRequest(1)` does not reduce remaining demand or "enable bounded mode".

To assert that requests are issued in batches, use:

~~~java
StepVerifier.create(source, 0)
    .expectSubscription()
    .thenRequest(1)
    .expectNext(10)
    .thenRequest(2)
    .expectNext(20, 30)
    .verifyComplete();
~~~

## 4. Controlling initialRequest with create(Publisher, long)

Syntax:

~~~java
StepVerifier.create(publisher, initialRequest)
~~~

The second argument chooses the number of items initially requested when the subscription starts.

### Starting with Zero Request

~~~java
Flux<Integer> source = Flux.range(1, 5);

StepVerifier.create(source, 0)
    .expectSubscription()
    .thenRequest(2)
    .expectNext(1, 2)
    .thenRequest(3)
    .expectNext(3, 4, 5)
    .verifyComplete();
~~~

Walkthrough:

1. `create(source, 0)`: upon subscribing, request zero items.
2. `expectSubscription()`: confirms the Subscriber received `onSubscribe`.
3. `thenRequest(2)`: calls `request(2)`, allowing the source to emit at most 2 items.
4. `expectNext(1, 2)`: verifies the exact first two items.
5. `thenRequest(3)`: requests 3 more items.
6. `expectNext(3, 4, 5)`: verifies the remaining three items.
7. `verifyComplete()`: expects the source to complete successfully.

This is the foundational scenario for learning `thenRequest`. `Flux.range` is a cold, backpressure-aware Publisher, so results are deterministic and require no sleep or network.

### Starting with Positive Demand

~~~java
StepVerifier.create(Flux.range(1, 4), 2)
    .expectSubscription()
    .expectNext(1, 2)
    .thenRequest(2)
    .expectNext(3, 4)
    .verifyComplete();
~~~

Here the Subscriber requests 2 right at the start, so the first two elements are emitted without calling `thenRequest`. Then 2 more are requested to receive the remaining two elements.

### Starting with Unbounded Demand

~~~java
StepVerifier.create(Flux.range(1, 4), Long.MAX_VALUE)
    .expectNext(1, 2, 3, 4)
    .verifyComplete();
~~~

Use this when the goal is purely data and completion; do not use it to prove batched backpressure.

### Comparison

| Call | Initial demand | Use case |
| --- | ---: | --- |
| `StepVerifier.create(source)` | Long.MAX_VALUE | Standard value/error/complete tests |
| `StepVerifier.create(source, 0)` | 0 | Explicitly requesting in batches via thenRequest |
| `StepVerifier.create(source, 2)` | 2 | Starting with a small quota |
| `StepVerifier.create(source, Long.MAX_VALUE)` | Unbounded | Explicitly stating unbounded intent |

Do not pass negative values or 0 to `thenRequest`. `initialRequest(0)` is a valid verifier configuration and is **not equivalent** to issuing an invalid `Subscription.request(0)` call.

## 5. StepVerifierOptions.initialRequest and Useful Options

Besides the numeric overload, you can use `StepVerifierOptions`:

~~~java
import reactor.test.StepVerifier;
import reactor.test.StepVerifierOptions;

StepVerifierOptions options = StepVerifierOptions.create()
    .initialRequest(0)
    .scenarioName("Flux numbers - phased demand")
    .checkUnderRequesting(true);

StepVerifier.create(Flux.range(1, 3), options)
    .expectSubscription()
    .thenRequest(1)
    .expectNext(1)
    .thenRequest(2)
    .expectNext(2, 3)
    .verifyComplete();
~~~

Related options:

| Option | Meaning |
| --- | --- |
| `initialRequest(long)` | Specifies demand at subscription time |
| `scenarioName(String)` | Names the entire scenario for more readable failures |
| `checkUnderRequesting(boolean)` | Enables/disables warnings when expecting more onNext than granted demand |
| `withInitialContext(Context)` | Provides an initial Reactor Context at subscribe time |
| `virtualTimeSchedulerSupplier(...)` | Configures a scheduler for advanced virtual time testing |

`checkUnderRequesting` **is true by default**. It helps detect scenarios that deadlock themselves by failing to request enough items for the waiting `expectNext` steps.

**Do not disable this default** just to make a test "pass". If a scenario expects three values but only requests two, add an appropriate `thenRequest` or fix the expectation.

### Common Under-Requesting Mistake

~~~java
// INVALID EXAMPLE: this scenario requests 2 but expects 3 items.
StepVerifier.create(Flux.range(1, 3), 0)
    .thenRequest(2)
    .expectNext(1, 2, 3)
    .verifyComplete();
~~~

StepVerifier can flag insufficient requests during setup or execution depending on the steps. Do not misinterpret this error as a publisher lacking backpressure: **the test itself failed to grant enough demand**.

Fix:

~~~java
StepVerifier.create(Flux.range(1, 3), 0)
    .thenRequest(2)
    .expectNext(1, 2)
    .thenRequest(1)
    .expectNext(3)
    .verifyComplete();
~~~

## 6. What Exactly Does thenRequest(n) Do?

`thenRequest(n)` is a StepVerifier action step: it requests n more elements from the Subscription during the test.

~~~java
.thenRequest(5)
~~~

is semantically equivalent to a Subscriber actively calling `subscription.request(5)`.

### thenRequest Accumulates, It Does Not Reset the Quota

Suppose initial request is 2, 1 item has arrived, and then `thenRequest(3)`:

~~~text
Initially        : request(2)   -> outstanding = 2
Emit 1 item      : onNext       -> outstanding = 1
Request more     : request(3)   -> outstanding = 4
Emit next 4 items: onNext x4    -> outstanding = 0
~~~

`thenRequest(3)` **does not mean** "now allow at most 3 items"; it adds 3 to the remaining demand.

### Do Not Use thenRequest as a Time Control Operation

`thenRequest` is not `Thread.sleep` or "execute after n milliseconds". The StepVerifier script runs steps sequentially and sends the request at that exact step.

If you need time control:

- `thenAwait(Duration)`: wait or advance time.
- `expectNoEvent(Duration)`: assert no events are observed during the given duration.
- `withVirtualTime(...)`: test time-based operators with a virtual scheduler.

For tests checking only demand on a synchronous source like `Flux.range`, **virtual time is unnecessary**.

### Ordering Request Before expectNext Matters

~~~java
StepVerifier.create(Flux.range(1, 2), 0)
    .expectSubscription()
    .thenRequest(1)
    .expectNext(1)
    .thenRequest(1)
    .expectNext(2)
    .verifyComplete();
~~~

If you put `expectNext(1)` before issuing the first request, the verifier has no data to advance to the subsequent `thenRequest` step; the test will fail due to under-requesting or hang if safety checks are disabled.

## 7. expectSubscription and expectNoEvent When initialRequest = 0

A subscription is also an event observed by StepVerifier, even though it is not `onNext`. Therefore:

~~~java
// Usually wrong: expectNoEvent as the first step may observe onSubscribe.
StepVerifier.create(Flux.range(1, 3), 0)
    .expectNoEvent(Duration.ofMillis(30))
    .thenRequest(3)
    .expectNext(1, 2, 3)
    .verifyComplete();
~~~

Better scenario:

~~~java
StepVerifier.create(Flux.range(1, 3), 0)
    .expectSubscription()
    .expectNoEvent(Duration.ofMillis(30))
    .thenRequest(3)
    .expectNext(1, 2, 3)
    .verifyComplete();
~~~

Here:

- `expectSubscription` asserts `onSubscribe` occurred.
- Since there is no demand yet, a Reactive Streams-compliant Publisher must not emit `onNext`.
- `expectNoEvent` can be used to observe that no other events occur within 30 ms.
- After `thenRequest(3)`, the source emits three values.

**Do not generalize that every Publisher must stay silent when initial demand is 0.** A `Mono.empty()` source can emit `onComplete`, and `Mono.error(error)` can emit `onError` before any request. Terminal signals are not gated by `onNext` demand.

Because `expectNoEvent(Duration)` uses real time in regular tests, it slows tests down and can be affected by schedulers. Use it only when you genuinely need to prove "no signals arrived". With deterministic synchronous sources, `thenRequest` combined with expectations is the core pattern.

## 8. onNext and Terminal Signals Follow Different Demand Rules

Compare these cases:

~~~java
Flux<Integer> values = Flux.just(1, 2);
Mono<Integer> empty = Mono.empty();
Mono<Integer> failed = Mono.error(
    new IllegalStateException("boom")
);
~~~

| Source | Initial demand 0 | Conclusion |
| --- | --- | --- |
| `Flux.just(1, 2)` | Must not emit `onNext` before request | `onNext` is regulated by backpressure |
| `Mono.just(1)` | Value needs a request to emit | `onNext` requires demand |
| `Mono.empty()` | May complete immediately | Completion consumes no demand |
| `Mono.error(e)` | May error immediately | Error consumes no demand |

Empty Mono test example:

~~~java
StepVerifier.create(Mono.<Integer>empty(), 0)
    .expectSubscription()
    .verifyComplete();
~~~

Error test example:

~~~java
StepVerifier.create(
        Mono.<Integer>error(new IllegalStateException("boom")), 0
    )
    .expectSubscription()
    .expectErrorMessage("boom")
    .verify();
~~~

`thenRequest` asks for additional `onNext` values; it is not a prerequisite for a Publisher to complete or error.

### Mono Typically Needs Only One Request

~~~java
StepVerifier.create(Mono.just("OK"), 0)
    .expectSubscription()
    .thenRequest(1)
    .expectNext("OK")
    .verifyComplete();
~~~

If the Mono completes empty, requesting 1 will not make it "fabricate" an element.

## 9. expectNextCount, assertNext, and Testing Partially Known Data

For a Publisher emitting many items, you do not always have to list every value with `expectNext`:

~~~java
StepVerifier.create(Flux.range(1, 10), 0)
    .expectSubscription()
    .thenRequest(4)
    .expectNextCount(4)
    .thenRequest(6)
    .expectNextCount(6)
    .verifyComplete();
~~~

The scenario above verifies counts per batch, without checking individual values. When ordering and contents matter, combine approaches:

~~~java
StepVerifier.create(Flux.range(10, 5), 0)
    .thenRequest(2)
    .expectNext(10, 11)
    .thenRequest(1)
    .assertNext(value -> assertEquals(12, value))
    .thenRequest(2)
    .expectNext(13, 14)
    .verifyComplete();
~~~

`assertEquals` in the snippet comes from `org.junit.jupiter.api.Assertions`. It only compiles with the corresponding JUnit import.

Other options:

- `expectNextMatches(predicate)`: checks one element against a predicate.
- `assertNext(consumer)`: runs rich assertions on the element.
- `expectNextSequence(iterable)`: compares a sequence of elements.
- `thenConsumeWhile(predicate)`: consumes additional elements matching a condition.

With any option, you must still allocate enough demand before `onNext` expectations. `expectNextCount(10)` does not automatically request 10 items.

## 10. Testing How a Publisher Responds to Requests Using doOnRequest

Reactor provides `doOnRequest` to observe upstream requests in a pipeline:

~~~java
AtomicLong requests = new AtomicLong();

Flux<Integer> source = Flux.range(1, 5)
    .doOnRequest(requests::addAndGet);

StepVerifier.create(source, 0)
    .expectSubscription()
    .then(() -> assertEquals(0L, requests.get()))
    .thenRequest(2)
    .expectNext(1, 2)
    .then(() -> assertEquals(2L, requests.get()))
    .thenRequest(3)
    .expectNext(3, 4, 5)
    .then(() -> assertEquals(5L, requests.get()))
    .verifyComplete();
~~~

This is a straightforward test with no demand-altering operator between StepVerifier and `doOnRequest`, so the observed requests match totals of 2 and then 5.

### What Is then(Runnable) Used For?

`then(() -> ...)` lets you run an action or assertion at that exact point in the scenario, after prior steps have been processed.

Example:

~~~java
.then(() -> assertEquals(2L, requests.get()))
~~~

Contrast with `thenRequest(2)`:

- `thenRequest` sends demand.
- `then(Runnable)` runs verification or test-control code.
- `thenCancel` cancels the subscription.

These methods all start with "then" but have completely different meanings; do not confuse them.

### Do Not Use Naïve long Addition with Unbounded Demand

Using `requests.addAndGet(n)` works well when measuring small, finite requests. With `Long.MAX_VALUE` or additions exceeding the maximum, a hand-rolled counter can overflow. To observe real demand in production, use proper metrics/probes instead of blindly summing all `long` values.

## 11. Operators Can Change the Request Count Sent Upstream

A common misconception: `StepVerifier.thenRequest(n)` sends demand at the **bottom** of the pipeline, yet the source at the top does not necessarily receive the same `n`.

Example:

~~~java
Flux<List<Integer>> batches = Flux.range(1, 9)
    .buffer(3);

StepVerifier.create(batches, 0)
    .expectSubscription()
    .thenRequest(1)
    .expectNext(List.of(1, 2, 3))
    .thenRequest(1)
    .expectNext(List.of(4, 5, 6))
    .thenCancel()
    .verify();
~~~

One downstream item here is a `List<Integer>` of three elements. When downstream requests one list, `buffer(3)` needs to request three source items to assemble that list.

We can observe this:

~~~java
AtomicLong upstreamRequests = new AtomicLong();

Flux<List<Integer>> batches = Flux.range(1, 9)
    .doOnRequest(upstreamRequests::addAndGet)
    .buffer(3);

StepVerifier.create(batches, 0)
    .expectSubscription()
    .thenRequest(1)
    .expectNext(List.of(1, 2, 3))
    .then(() -> assertEquals(3L, upstreamRequests.get()))
    .thenRequest(1)
    .expectNext(List.of(4, 5, 6))
    .then(() -> assertEquals(6L, upstreamRequests.get()))
    .thenCancel()
    .verify();
~~~

**Placement of `doOnRequest` matters greatly:**

~~~text
StepVerifier request(1 List)
             |
             v
           buffer(3)
             |
             | request(3 Integer)
             v
          doOnRequest
             |
             v
      Flux.range(1, 9)
~~~

If you put `doOnRequest` after `buffer(3)`, you will observe requests on the **downstream side** of buffer—meaning `request(1 List)` rather than `request(3 Integer)`.

### Operators That Can Reshape Requests

| Operator | Change to keep in mind |
| --- | --- |
| `buffer(size)` | One downstream item may require multiple upstream items |
| `limitRate(highTide)` | Splits large requests into smaller request batches |
| `publishOn(scheduler, prefetch)` | Uses prefetching and a queue across schedulers |
| `flatMap(mapper, concurrency, prefetch)` | Requests and buffers across multiple inner Publishers |
| `concatMap(mapper)` | Uses prefetch/queue mechanics depending on overload |
| `take(n)` | Caps total items and may cancel once satisfied |
| `onBackpressureBuffer` | Uses an intermediate buffer and overflow strategy |

Do not assert that `thenRequest(2)` must cause every source or DB client to receive `request(2)` verbatim. Choose the layer where demand is measured and understand the operators in between.

## 12. thenRequest and limitRate

`limitRate` splits large downstream demand into smaller upstream request batches.

Example:

~~~java
Flux<Integer> source = Flux.range(1, 20)
    .limitRate(4);

StepVerifier.create(source, 0)
    .expectSubscription()
    .thenRequest(2)
    .expectNext(1, 2)
    .thenRequest(3)
    .expectNext(3, 4, 5)
    .thenCancel()
    .verify();
~~~

This test verifies that downstream receives exactly 5 items after a total demand of 5. It does **not** prove upstream received batches of 2 and 3. `limitRate(4)` applies its own request policy to the source.

To observe it:

~~~java
Flux<Integer> observed = Flux.range(1, 20)
    .doOnRequest(n -> System.out.println("upstream request=" + n))
    .limitRate(4);
~~~

Keep in mind:

- This is illustrative logging only, not fixed stdout across every configuration.
- Prefetch/replenishment details can vary by operator and Reactor version.
- To keep tests less brittle, focus on verifying the user-visible contract (`onNext`, ordering, completion, cancellation), adding internal assertions only when that metric is an explicit technical requirement.

## 13. Testing Subscription Cancellation After Partial Data

Not every source completes in tests. With long or infinite streams, we often want to:

1. Receive a controlled number of items.
2. Cancel.
3. Verify upstream received the cancellation.

Example:

~~~java
AtomicBoolean cancelled = new AtomicBoolean(false);

Flux<Integer> source = Flux.range(1, 100)
    .doOnCancel(() -> cancelled.set(true));

StepVerifier.create(source, 0)
    .expectSubscription()
    .thenRequest(2)
    .expectNext(1, 2)
    .thenCancel()
    .verify();

assertTrue(cancelled.get());
~~~

`thenCancel()` is a terminal scenario step: no `expectComplete()` is needed afterward. This is the right choice when intentionally stopping after a subset of items.

### Why Will expectComplete Hang If Not Enough Is Requested?

~~~java
// Invalid example: only requests 2/100 items yet expects the source to complete.
StepVerifier.create(Flux.range(1, 100), 0)
    .thenRequest(2)
    .expectNext(1, 2)
    .verifyComplete();
~~~

`Flux.range(1,100)` cannot emit the remaining 98 values yet, so it cannot complete normally. The test may wait indefinitely if no timeout is set.

How to fix it depends on your goal:

- To consume everything: add `thenRequest(98)` and verify the remaining 98 items.
- To test only the first two items: terminate with `thenCancel()`.
- To test a timeout: build an explicit timeout expectation.

## 14. Error Signals Can Arrive When Demand Is Exhausted

Suppose a pipeline emits two items and then fails:

~~~java
Flux<Integer> source = Flux.concat(
    Flux.just(10, 20),
    Flux.error(new IllegalStateException("boom"))
);

StepVerifier.create(source, 0)
    .expectSubscription()
    .thenRequest(2)
    .expectNext(10, 20)
    .expectErrorMatches(error ->
        error instanceof IllegalStateException
            && "boom".equals(error.getMessage())
    )
    .verify();
~~~

After two `onNext` signals, outstanding demand drops to 0, yet the source is still permitted to emit `onError`. An error signal is not a data item and does not require a separate `thenRequest(1)`.

Distinguish:

- `expectError(...)`: asserts the Publisher terminates with an error.
- `expectComplete()`: asserts successful completion.
- `thenCancel()`: tester proactively cancels without waiting for a source terminal signal.

**Never replace `expectError` with `onErrorComplete()` in production just to make a test pass.** Swallowing errors breaks the business contract.

## 15. Testing Hot Sources with TestPublisher

`reactor-test` also includes `TestPublisher` to actively trigger data signals in tests.

~~~java
TestPublisher<Integer> publisher = TestPublisher.create();

StepVerifier.create(publisher.flux(), 0)
    .expectSubscription()
    .then(() -> publisher
        .assertSubscribers()
        .assertMaxRequested(0))
    .thenRequest(1)
    .then(() -> publisher
        .assertMinRequested(1)
        .next(99)
        .complete())
    .expectNext(99)
    .verifyComplete();
~~~

Meaning:

- `TestPublisher.create()` creates a test-controlled source.
- `assertSubscribers()` confirms a subscriber is attached.
- `assertMaxRequested(0)` confirms the subscriber initially requested zero items.
- After `thenRequest(1)`, `assertMinRequested(1)` confirms demand is present.
- `next(99)` and `complete()` emit signals to the subscriber.
- `expectNext(99)` and `verifyComplete()` verify the result.

Methods like `assertMinRequested`, `assertMaxRequested`, and `assertNoRequestOverflow` inspect the TestPublisher's state.

### Do Not Confuse TestPublisher with Production Sources

TestPublisher is typically hot and driven by the test. It does not automatically reproduce cold/replay semantics of a repository or HTTP client. To test an operator against a protocol-violating source, `TestPublisher.createNoncompliant(Violation...)` can intentionally create a Reactive Streams-violating Publisher, but use it strictly for deliberate resilience testing. Never use violating Publishers in production applications.

Emitting `onNext` with zero demand is a protocol violation; `TestPublisher` has APIs to track request overflow, and you must not disable checks merely to treat broken behavior as valid.

## 16. Under-Requesting Is Not Upstream Backpressure Violation

Two easily confused problems:

### Test Requests Too Little

~~~java
StepVerifier.create(Flux.range(1, 3), 0)
    .thenRequest(1)
    .expectNext(1, 2)
    .verifyComplete();
~~~

Here the verifier itself expects two items while granting demand for only one. `checkUnderRequesting` helps flag this scripting mistake.

### Publisher Emits Beyond Demand

If a Subscriber calls `request(1)` and the source emits two `onNext` signals before the next request, the Publisher may be violating Reactive Streams. That is a bug in the source or adapter, not the test requesting too little.

To tell them apart, check:

- Did the script request enough demand for all `expectNext` steps?
- Where is `doOnRequest` placed?
- Which operators perform prefetching/reshaping?
- Is there a custom source or non-compliant adapter?
- Does the source have a buffer and configured overflow policy?

`StepVerifier` is helpful, yet value/`thenRequest` tests **do not replace** full Reactive Streams specification compliance testing for a custom Publisher. For custom Publisher libraries, complement with TCK and standalone backpressure/cancellation tests.

## 17. Virtual Time and Demand: Two Orthogonal Axes

There are two common reasons a Publisher has not emitted an item yet:

1. **No demand yet:** the subscriber has not called `request(n)` enough.
2. **Not time to emit yet:** the source has a delay, interval, or scheduler dependency.

`thenRequest(n)` addresses the first cause. `thenAwait(duration)` and `withVirtualTime` address the second cause.

Example testing time only (no manual demand needed):

~~~java
StepVerifier.withVirtualTime(
        () -> Flux.interval(Duration.ofSeconds(1)).take(3))
    .expectSubscription()
    .thenAwait(Duration.ofSeconds(3))
    .expectNext(0L, 1L, 2L)
    .verifyComplete();
~~~

`withVirtualTime` accepts a Supplier so the Publisher is created **after** the virtual scheduler is installed; do not create `Flux.interval` beforehand and merely return the existing variable.

When combining virtual time with manual demand:

~~~java
StepVerifier.withVirtualTime(
        () -> Flux.interval(Duration.ofSeconds(1)).take(2), 0)
    .expectSubscription()
    .thenRequest(2)
    .thenAwait(Duration.ofSeconds(2))
    .expectNext(0L, 1L)
    .verifyComplete();
~~~

Place `thenRequest(2)` before advancing the virtual clock so `Flux.interval` does not hit missing demand on the first tick. Advancing time with zero demand can cause `Flux.interval` to emit an overflow/backpressure error depending on source and timing.

Note: virtual time only controls appropriately hooked schedulers. It does not turn real network or database calls into virtual I/O.

## 18. Testing Reactor Does Not Measure Every HTTP Layer

In Spring WebFlux, a controller might return:

~~~java
@GetMapping(
    path = "/events",
    produces = MediaType.APPLICATION_NDJSON_VALUE
)
public Flux<Event> stream() {
    return eventService.events();
}
~~~

A StepVerifier unit test can verify `eventService.events()` with `initialRequest=0` and batched `thenRequest`.

However, a StepVerifier test does not by itself prove that:

- The HTTP client sends exact demand per batch as expected.
- The Reactor Netty socket does not buffer extra bytes.
- The JSON codec flushes each item immediately.
- Reverse proxies and browsers receive data the instant the source emits.
- The database driver applies the exact same request count across all operators.

To test HTTP, use `WebTestClient` or integration tests with a real client and matching media type. To verify behavior under load, measure throughput, pending queues, memory, and buffers.

Backpressure is an internal coordination mechanism via Reactive Streams; it is not a guarantee that "each `request(n)` equals one TCP packet".

## 19. Runnable Java 17 Project with Maven

This complete project demonstrates the core concepts:

- `initialRequest = 0` and requesting in multiple batches.
- Non-zero initial demand.
- `StepVerifierOptions`.
- Observing requests with `doOnRequest` and `then(Runnable)`.
- Using `buffer(3)` to illustrate request reshaping.
- Verifying `thenCancel` and `doOnCancel`.
- Verifying terminal errors when demand is exhausted.
- Using `TestPublisher`.
- Setting verifier timeouts to avoid long hangs.

The project does not start an HTTP server: it focuses on **unit testing Reactor's request/backpressure mechanics**, which applies directly to `Flux`/`Mono` returned by Spring WebFlux services.

### 19.1. Project Structure

~~~text
reactor-demand-tests/
├── pom.xml
└── src/
    ├── main/java/com/example/demand/
    │   └── DemandService.java
    └── test/java/com/example/demand/
        └── DemandServiceTest.java
~~~

### 19.2. pom.xml

~~~xml
<project xmlns="http://maven.apache.org/POM/4.0.0"
         xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
         xsi:schemaLocation="http://maven.apache.org/POM/4.0.0 https://maven.apache.org/xsd/maven-4.0.0.xsd">
    <modelVersion>4.0.0</modelVersion>

    <groupId>com.example</groupId>
    <artifactId>reactor-demand-tests</artifactId>
    <version>1.0.0</version>

    <parent>
        <groupId>org.springframework.boot</groupId>
        <artifactId>spring-boot-starter-parent</artifactId>
        <version>3.5.0</version>
        <relativePath/>
    </parent>

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

The Spring Boot parent provides Java 17-compatible dependency management and test plugins. Because this project only demonstrates Reactor, `@SpringBootApplication`, controllers, and databases are unnecessary. You can integrate these tests into a real `spring-boot-starter-webflux` application without changing the testing approach.

### 19.3. DemandService.java

~~~java
package com.example.demand;

import java.util.List;

import reactor.core.publisher.Flux;

public class DemandService {

    public Flux<Integer> numbers() {
        return Flux.range(1, 5);
    }

    public Flux<Integer> doubled() {
        return numbers().map(n -> n * 2);
    }

    public Flux<List<Integer>> batches() {
        return Flux.range(1, 9).buffer(3);
    }

    public Flux<Integer> failsAfterTwo() {
        return Flux.concat(
            Flux.just(10, 20),
            Flux.error(new IllegalStateException("boom"))
        );
    }
}
~~~

`numbers` uses a cold, synchronous, backpressure-aware source. `batches` produces groups of three items, while `failsAfterTwo` illustrates a terminal error.

### 19.4. DemandServiceTest.java

~~~java
package com.example.demand;

import static org.junit.jupiter.api.Assertions.assertEquals;
import static org.junit.jupiter.api.Assertions.assertTrue;

import java.time.Duration;
import java.util.List;
import java.util.concurrent.atomic.AtomicBoolean;
import java.util.concurrent.atomic.AtomicLong;

import org.junit.jupiter.api.Test;

import reactor.core.publisher.Flux;
import reactor.test.StepVerifier;
import reactor.test.StepVerifierOptions;
import reactor.test.publisher.TestPublisher;

class DemandServiceTest {

    private final DemandService service = new DemandService();

    @Test
    void initialZeroAndPhasedRequests() {
        StepVerifier.create(service.numbers(), 0)
            .expectSubscription()
            .thenRequest(2)
            .expectNext(1, 2)
            .thenRequest(3)
            .expectNext(3, 4, 5)
            .expectComplete()
            .verify(Duration.ofSeconds(2));
    }

    @Test
    void initialTwoAndOneAdditionalRequest() {
        StepVerifier.create(Flux.range(1, 3), 2)
            .expectSubscription()
            .expectNext(1, 2)
            .thenRequest(1)
            .expectNext(3)
            .expectComplete()
            .verify(Duration.ofSeconds(2));
    }

    @Test
    void optionsCanConfigureInitialRequest() {
        StepVerifierOptions options = StepVerifierOptions.create()
            .initialRequest(0)
            .scenarioName("doubled with staged demand")
            .checkUnderRequesting(true);

        StepVerifier.create(service.doubled(), options)
            .expectSubscription()
            .thenRequest(2)
            .expectNext(2, 4)
            .thenRequest(3)
            .expectNext(6, 8, 10)
            .expectComplete()
            .verify(Duration.ofSeconds(2));
    }

    @Test
    void noItemBeforeInitialRequest() {
        StepVerifier.create(service.numbers(), 0)
            .expectSubscription()
            .expectNoEvent(Duration.ofMillis(20))
            .thenRequest(5)
            .expectNext(1, 2, 3, 4, 5)
            .expectComplete()
            .verify(Duration.ofSeconds(2));
    }

    @Test
    void observesDemandBeforeAndAfterEachRequest() {
        AtomicLong requested = new AtomicLong();
        Flux<Integer> source = service.numbers()
            .doOnRequest(requested::addAndGet);

        StepVerifier.create(source, 0)
            .expectSubscription()
            .then(() -> assertEquals(0L, requested.get()))
            .thenRequest(2)
            .expectNext(1, 2)
            .then(() -> assertEquals(2L, requested.get()))
            .thenRequest(3)
            .expectNext(3, 4, 5)
            .then(() -> assertEquals(5L, requested.get()))
            .expectComplete()
            .verify(Duration.ofSeconds(2));
    }

    @Test
    void bufferChangesUpstreamRequestUnits() {
        AtomicLong upstreamRequested = new AtomicLong();

        Flux<List<Integer>> batches = Flux.range(1, 9)
            .doOnRequest(upstreamRequested::addAndGet)
            .buffer(3);

        StepVerifier.create(batches, 0)
            .expectSubscription()
            .thenRequest(1)
            .expectNext(List.of(1, 2, 3))
            .then(() -> assertEquals(3L, upstreamRequested.get()))
            .thenRequest(1)
            .expectNext(List.of(4, 5, 6))
            .then(() -> assertEquals(6L, upstreamRequested.get()))
            .thenCancel()
            .verify(Duration.ofSeconds(2));
    }

    @Test
    void cancellationReachesSource() {
        AtomicBoolean cancelled = new AtomicBoolean();

        Flux<Integer> source = Flux.range(1, 100)
            .doOnCancel(() -> cancelled.set(true));

        StepVerifier.create(source, 0)
            .expectSubscription()
            .thenRequest(2)
            .expectNext(1, 2)
            .thenCancel()
            .verify(Duration.ofSeconds(2));

        assertTrue(cancelled.get());
    }

    @Test
    void terminalErrorDoesNotNeedAnotherRequest() {
        StepVerifier.create(service.failsAfterTwo(), 0)
            .expectSubscription()
            .thenRequest(2)
            .expectNext(10, 20)
            .expectErrorMatches(error ->
                error instanceof IllegalStateException
                    && "boom".equals(error.getMessage())
            )
            .verify(Duration.ofSeconds(2));
    }

    @Test
    void testPublisherObservesRequests() {
        TestPublisher<Integer> publisher = TestPublisher.create();

        StepVerifier.create(publisher.flux(), 0)
            .expectSubscription()
            .then(() -> publisher
                .assertSubscribers()
                .assertMaxRequested(0))
            .thenRequest(1)
            .then(() -> publisher
                .assertMinRequested(1)
                .next(99)
                .complete())
            .expectNext(99)
            .expectComplete()
            .verify(Duration.ofSeconds(2));
    }
}
~~~

### 19.5. Running the Tests

Requires JDK 17+ and Maven. From the `reactor-demand-tests` directory:

~~~bash
mvn test
~~~

Maven compiles the source, runs the JUnit 5 tests, and exits with code 0 if all assertions pass. Maven output contains environment-dependent version numbers and timings; the key thing to observe is zero failures/errors, for example:

~~~text
Tests run: 9, Failures: 0, Errors: 0, Skipped: 0
BUILD SUCCESS
~~~

This is the expected result shape, not a verbatim guarantee of full Maven stdout on every machine. With this standalone example, no Spring context, database setup, or network access for HTTP requests is needed (aside from Maven's initial dependency download).

### 19.6. Why Does This Project Teach thenRequest Effectively?

- Test 1 shows demand growing from 0 → 2 → 3 additional items.
- Test 2 shows a positive initialRequest taking effect before thenRequest.
- Test 3 shows `StepVerifierOptions` is equivalent to the numeric overload.
- Test 4 proves no `onNext` occurs before requesting with `Flux.range`.
- Test 5 observes demand at a point with no reshaping.
- Test 6 shows downstream requesting one `List` while upstream must supply three numbers.
- Test 7 cancels the subscription after partial consumption.
- Test 8 confirms a terminal error arrives after item demand drops to 0.
- Test 9 confirms `TestPublisher` receives requests matching the script.

## 20. Negative Tests to Understand Rather Than Put in a Passing Suite

Sometimes we learn from examples **expected to fail**, though they should not remain in a suite expected to pass completely.

### Mistake 1: Default Unbounded Prevents Batched Testing

~~~java
StepVerifier.create(Flux.range(1, 5))
    .thenRequest(1)
    .expectNext(1)
    .thenRequest(4)
    .expectNext(2, 3, 4, 5)
    .verifyComplete();
~~~

This test may pass, yet it does not prove upstream waited for `thenRequest` because initial demand was already `Long.MAX_VALUE`. The flaw is in **what the test actually verifies**, not merely pass/fail.

### Mistake 2: Expecting More Than Requested

~~~java
StepVerifier.create(Flux.range(1, 3), 0)
    .thenRequest(1)
    .expectNext(1, 2)
    .verifyComplete();
~~~

The test lacks demand for the second item. You need another `thenRequest(1)` before expecting the second item; to complete, you must also handle the third item or cancel depending on your goal.

### Mistake 3: Expecting Complete After Requesting Only Part of the Stream

~~~java
StepVerifier.create(Flux.range(1, 100), 0)
    .thenRequest(1)
    .expectNext(1)
    .verifyComplete();
~~~

The Publisher is not yet permitted to emit the remaining 99 items, so it cannot complete normally after emitting all 100. Use `thenCancel()` if only testing the first item, or request all data.

### Mistake 4: expectNoEvent Before expectSubscription

~~~java
StepVerifier.create(Flux.range(1, 3), 0)
    .expectNoEvent(Duration.ofMillis(20))
    .thenRequest(3)
    .expectNext(1, 2, 3)
    .verifyComplete();
~~~

Subscription is also an event; use `expectSubscription()` before measuring a silent window.

### Mistake 5: Measuring Upstream Requests While Forgetting Operator Prefetch

~~~java
Flux<Integer> source = repository.findAll()
    .publishOn(Schedulers.parallel());
~~~

A `thenRequest(1)` downstream of `publishOn` does not necessarily translate into `request(1)` at the repository; `publishOn` prefetches. When testing source behavior, identify where `doOnRequest` sits and the operator's prefetch policy.

## 21. Timeouts and Test Determinism

Per StepVerifier Javadoc, `verify()` has **no overall timeout by default** unless a default has been configured. This easily hangs CI when a test lacks requests.

Use:

~~~java
StepVerifier.create(Flux.range(1, 3), 0)
    .thenRequest(3)
    .expectNext(1, 2, 3)
    .expectComplete()
    .verify(Duration.ofSeconds(2));
~~~

The duration in `verify(Duration)` limits how long the test waits; it does not magically grant the Publisher new demand.

You can set a global default timeout:

~~~java
StepVerifier.setDefaultTimeout(Duration.ofSeconds(3));
~~~

However, this state affects StepVerifiers created afterward in the same test process; if tests run in parallel, be careful and reset with `StepVerifier.resetDefaultTimeout()` when appropriate. For learning tests, passing an explicit timeout to `verify(Duration)` is clearer.

### Avoid Real Time When Unnecessary

- `Flux.range` works well for batched demand testing without a scheduler.
- `expectNoEvent(Duration)` adds real waiting time unless virtual time is used.
- `Flux.interval` and `delayElements` should be tested with virtual time when timing is the focus.
- Do not write tests that depend on scheduler interleaving by asserting an order not guaranteed by the contract.

### Naming Tests

Test names should describe the demand–signal relationship, for example:

- `noItemBeforeInitialRequest`.
- `thenRequestAddsDemand`.
- `bufferChangesUpstreamRequestUnits`.
- `cancelAfterTwoItemsStopsSubscription`.
- `terminalErrorDoesNotNeedDemand`.

When a test fails, these names pinpoint the violated contract much faster than a generic name like `testFlux`.

## 22. Checklist for Writing Demand-Controlled Tests

- [ ] Is the goal pure value testing or request/backpressure testing?
- [ ] If testing demand, did you use a finite or 0 `initialRequest`?
- [ ] Are you aware `StepVerifier.create(source)` requests `Long.MAX_VALUE` by default?
- [ ] Do `thenRequest(n)` steps accumulate properly with remaining demand?
- [ ] Is total demand sufficient for all `expectNext` or `expectNextCount` steps?
- [ ] Did you use `expectSubscription` when checking `expectNoEvent` right after subscribing?
- [ ] Did you distinguish `onNext` from `onComplete`/`onError`?
- [ ] Does the test end with `verifyComplete`, `expectError`, or `thenCancel` matching the goal?
- [ ] Did you set a verify deadline to avoid hanging tests on missing requests?
- [ ] Are there request-reshaping operators like `buffer`, `publishOn`, `flatMap`, or `limitRate`?
- [ ] Which side of the operator is `doOnRequest` placed on?
- [ ] If using `TestPublisher`, do you emit items only when demand exists and check for overflow?
- [ ] Did you avoid manually subscribing to the Publisher before StepVerifier subscribes?
- [ ] Did you avoid disabling `checkUnderRequesting` just to hide under-requested scripts?
- [ ] Did you use virtual time appropriately if the pipeline depends on timers?
- [ ] Did you distinguish Reactor unit tests from HTTP integration tests?

## 23. Self-Check Questions and Answers

**1.** What does `StepVerifier.create(source)` request by default? `Long.MAX_VALUE`, i.e., unbounded.

**2.** Does `StepVerifier.create(source, 0)` send an invalid `request(0)`? No; it configures the verifier not to send an initial item request.

**3.** What is `thenRequest(2)`? It sends additional demand for 2 items, analogous to `Subscription.request(2)`.

**4.** If outstanding demand is 1 and then `thenRequest(3)` runs, how much remains? 4 before any further `onNext`.

**5.** Why can `expectNext(1,2)` before sufficient requests fail? The test expects more items than the granted demand, causing under-requesting.

**6.** What is `checkUnderRequesting` by default? Enabled (`true`).

**7.** Should `checkUnderRequesting` be turned off to fix a hanging test? No; fix the demand and expectations instead.

**8.** Does `expectNoEvent` count `onSubscribe` as an event? Yes; use `expectSubscription` before checking a silent interval.

**9.** Does `Mono.empty()` need `request(1)` to complete? Not necessarily; terminal signals are not gated like `onNext`.

**10.** Does `thenRequest` force `Flux.range` to run on a new thread? No; it is not a scheduler operator.

**11.** How many source requests can `thenRequest(1)` after `buffer(3)` generate? 3 source items for one downstream `List` item.

**12.** Can `doOnRequest` before and after `buffer(3)` observe different counts? Yes; the operator reshapes requests.

**13.** When you only want to check the first two items of a long Flux, how should the test end? `thenCancel().verify(...)`.

**14.** To test completion of `Flux.range(1,100)`, is requesting 2 items enough? No; you must request all 100 items or change the goal to cancellation.

**15.** Does `onError` consume outstanding demand? No; error is a terminal signal.

**16.** With `TestPublisher`, how can you check whether a subscriber has requested yet? `assertMinRequested`, `assertMaxRequested`; there is also `assertNoRequestOverflow`.

**17.** Does `then(Runnable)` request more items? No; it runs a task or assertion within the script.

**18.** To test time-based operators, is adding `thenRequest` alone enough? No; `thenAwait` or `withVirtualTime` is needed where appropriate.

**19.** Does `verify()` have a default timeout? There is no overall default timeout; use `verify(Duration)` to bound it.

**20.** Does a passing StepVerifier test prove an HTTP proxy flushes each item immediately? No; that is the responsibility of integration/transport tests.

## 24. Summary

Controlling initial requests and `thenRequest` turns Reactor testing into a demand-controlled scenario:

~~~java
StepVerifier.create(source, 0)
    .expectSubscription()
    .thenRequest(2)
    .expectNext(item1, item2)
    .thenRequest(1)
    .expectNext(item3)
    .verifyComplete();
~~~

Read the scenario in order: **subscribe → request → receive items → request more → receive items → terminal**.

When testing backpressure, do not leave initial demand at the unbounded default. Remember that requests accumulate, terminal signals do not consume demand, and operators can transform upstream requests. Tests need enough demand to reach termination or must proactively end with cancellation. Combine `doOnRequest`, `TestPublisher`, `StepVerifierOptions`, and `verify(Duration)` so scenarios are clear, reproducible, and never hang CI.

**Official references:**

- [Project Reactor — Testing (StepVerifier, PublisherProbe, TestPublisher)](https://projectreactor.io/docs/core/release/reference/testing.html)
- [StepVerifier Javadoc — create, verify, withVirtualTime](https://projectreactor.io/docs/test/release/api/reactor/test/StepVerifier.html)
- [StepVerifier.Step Javadoc — thenRequest, thenCancel, expectNoEvent](https://projectreactor.io/docs/test/release/api/reactor/test/StepVerifier.Step.html)
- [StepVerifierOptions Javadoc — initialRequest, checkUnderRequesting](https://projectreactor.io/docs/test/release/api/reactor/test/StepVerifierOptions.html)
- [TestPublisher Javadoc — request assertions](https://projectreactor.io/docs/test/release/api/reactor/test/publisher/TestPublisher.html)
- [Reactor Reference Guide — Backpressure and reshaping requests](https://projectreactor.io/docs/core/release/reference/subscribe-backpressure.html)
- [Reactive Streams Specification](https://github.com/reactive-streams/reactive-streams-jvm#specification).
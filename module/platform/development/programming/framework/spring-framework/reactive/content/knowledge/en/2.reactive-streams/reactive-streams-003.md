# `request(n)` and Pending Demand in Reactive Streams

## 1. Problem: The Consumer Decides How Much It Can Receive

Reactive Streams is an asynchronous stream-processing protocol with **backpressure**: the receiver can inform the producer how much data it is ready to consume. In the Spring WebFlux ecosystem, Project Reactor implements this idea through `Flux`, `Mono`, and `Publisher`/`Subscriber` types.

The core of the mechanism is `Subscription.request(long n)`. When a subscriber calls `request(n)` with `n > 0`, it **grants additional permission to emit up to n `onNext` signals**, without requiring the immediate emission of exactly n items. The source may not have data yet, may emit fewer items, or may terminate validly.

After this lesson, you will be able to calculate pending demand, handle cumulative requests, distinguish exhausted quota from cancellation, observe demand passing through operators, and write a batch-requesting subscriber in Java 17+.

## 2. Publisher, Subscriber, Subscription

| Component | Responsibility |
| --- | --- |
| `Publisher<T>` | Provides a sequence of `T` items, allowing registration via `subscribe`. |
| `Subscriber<T>` | Receives `onSubscribe`, `onNext`, `onError`, `onComplete`. |
| `Subscription` | Registration relationship between one subscriber and publisher; provides `request(long n)`, `cancel()`. |
| `Processor<T,R>` | Both receives from upstream and emits to downstream; many Reactor operators play a similar intermediary role. |

Typical sequence:

~~~text
Subscriber                         Publisher
    | -------- subscribe() ----------> |
    | <------- onSubscribe(s) --------- |
    | -------- s.request(3) ----------> |  emission quota: 3
    | <---------- onNext(A) ----------- |  2 remaining
    | <---------- onNext(B) ----------- |  1 remaining
    | -------- s.request(2) ----------> |  3 remaining, not 2
    | <---------- onNext(C) ----------- |  2 remaining
    | <---------- onNext(D) ----------- |  1 remaining
    | <---------- onNext(E) ----------- |  0 remaining
    | <---------- onComplete() -------- |  if the source completes
~~~

`request` and `cancel` travel from downstream to upstream. Data and terminal signals travel from upstream to downstream. A request may result in synchronous `onNext` calls right when invoked, or items may be delivered asynchronously afterward. `request(n)` is an **upper bound on the number of `onNext` signals permitted to be emitted**, not a promise to emit all n items.

## 3. Pending/Outstanding Demand: Remaining Quota

**Pending demand** (or outstanding demand) is the number of granted but unused `onNext` emission permissions on a `Subscription`. With finite quota:

~~~text
D_new = D_old + n                 after request(n), n > 0
D_new = D_old - 1                 after a valid onNext
D = total requested - total onNext emitted
~~~

Example table:

| Event | Total Requested | Total Emitted | Remaining Demand |
| --- | ---: | ---: | ---: |
| `onSubscribe`, no request yet | 0 | 0 | 0 |
| `request(3)` | 3 | 0 | 3 |
| `onNext(A)` | 3 | 1 | 2 |
| `onNext(B)` | 3 | 2 | 1 |
| `request(2)` | 5 | 2 | 3 |
| `onNext(C)` | 5 | 3 | 2 |
| `onNext(D)` | 5 | 4 | 1 |
| `onNext(E)` | 5 | 5 | 0 |

At the `request(2)` row, the quota was 1 so it increases to **3**. `request` is **cumulative**, not a quota reset. For instance, two consecutive `request(2)` calls grant a total of 4 permissions, before subtracting any interleaved `onNext` signals.

Distinguish three concepts:

- **Total requested**: total permissions granted by the subscriber from the start.
- **Total emitted**: number of `onNext` signals that have arrived at the subscriber.
- **Remaining demand**: the difference between the two totals while quota is finite; not the number of items in a queue, in-flight async tasks, or bytes in memory.

Each `Subscription` has its own quota. Two subscribers sharing a `Flux` do not automatically share a request counter. Individual segments between operators may also record different demand values.

## 4. Core Specification Rules

1. **Never emit beyond demand:** at any time, total `onNext` signals sent to a subscriber must be less than or equal to total items requested by that subscriber (Reactive Streams Publisher 1.1). When demand is 0, the publisher must not send a new `onNext`.
2. **Request must be positive:** `request(0)` or `request(-1)` is invalid while the subscription is active. The Subscription must signal `onError` with `IllegalArgumentException` per Subscription 3.9. Do not use `request(0)` as a pause command and do not expect an exception to be thrown directly from `request`.
3. **Cumulative:** `request(n > 0)` registers n additional items (Subscription 3.8). A subscriber may call it multiple times, including from `onNext`.
4. **May emit fewer:** if the source has four items left even when the subscriber requests ten, it may send four `onNext` signals and then `onComplete` (Publisher 1.2). Requesting 10 does not guarantee receiving all 10.
5. **May emit synchronously:** `request` may trigger `onNext` before `request` returns (Subscription 3.10). Compliant implementations must manage reentrancy to avoid `request → onNext → request` recursion overflowing the stack.
6. **Integer bound:** Reactive Streams supports quota up to `Long.MAX_VALUE` (Subscription 3.17). Reactor caps demand addition at this threshold and treats `Long.MAX_VALUE` as **unbounded**. Do not manually add two `long` values to manage demand while ignoring overflow and concurrent access.
7. **Exhausted quota differs from cancellation:** a quota of 0 means waiting for the subscriber to grant more permission; `cancel()` means the subscriber wants no more items and allows resource reclamation. Asynchronous races may exist with signals already processed or scheduled when cancellation happens.
8. **Terminals do not consume data quota:** `onComplete` and `onError` terminate the stream and do not consume an `onNext` permission; a source may terminate when pending demand is 0. No valid `onNext` may follow a terminal signal.

With `request(Long.MAX_VALUE)`, Reactor treats demand at the subscriber as unbounded. That **does not create infinite memory** and does not force the publisher to emit infinitely many items.

## 5. Runnable Java 17+ Program with Reactor

Create a Gradle project with `build.gradle`:

~~~groovy
plugins {
    id 'application'
}

repositories {
    mavenCentral()
}

dependencies {
    implementation 'io.projectreactor:reactor-core:3.8.7'
}

application {
    mainClass = 'DemandDemo'
}
~~~

Create `src/main/java/DemandDemo.java`:

~~~java
import org.reactivestreams.Subscription;
import reactor.core.publisher.BaseSubscriber;
import reactor.core.publisher.Flux;

public final class DemandDemo {
    public static void main(String[] args) {
        Flux.range(1, 5)
            .subscribe(new BaseSubscriber<Integer>() {
                private int received;

                @Override
                protected void hookOnSubscribe(Subscription subscription) {
                    System.out.println("onSubscribe: request(2)");
                    request(2);
                }

                @Override
                protected void hookOnNext(Integer value) {
                    received++;
                    System.out.println("onNext: " + value);
                    if (received % 2 == 0) {
                        System.out.println("request(2) more");
                        request(2);
                    }
                }

                @Override
                protected void hookOnComplete() {
                    System.out.println("onComplete");
                }

                @Override
                protected void hookOnError(Throwable error) {
                    System.err.println("onError: " + error);
                }
            });
    }
}
~~~

Run `gradle run --quiet` or `./gradlew run --quiet` if the project has a wrapper. With synchronous `Flux.range`, the exact stdout is:

~~~text
onSubscribe: request(2)
onNext: 1
onNext: 2
request(2) more
onNext: 3
onNext: 4
request(2) more
onNext: 5
onComplete
~~~

Analysis:

- Initially `hookOnSubscribe` grants 2 permissions. Receiving 1 and 2 brings the quota to 0.
- Inside `hookOnNext` for the second item, 2 more are requested. Receiving 3 and 4 returns the quota to 0.
- The fourth item triggers requesting 2 more. The source only has 5 left, so it emits 5 and completes. **Total requested is 6 while actually received is 5**, which is valid.
- `BaseSubscriber` defaults to requesting unbounded if `hookOnSubscribe` is not overridden. When overriding it, you must explicitly grant a positive request so the stream can make progress.
- Calling request inside `onNext` is permitted by the contract; Reactor handles synchronous emission safely. The code is requesting in **batches of two items**, not creating two-item lists like `buffer(2)`.

## 6. Testing Demand with StepVerifier

Verify that without a request, a synchronous source with data cannot emit `onNext` yet. Replace the `dependencies` block in `build.gradle` above with the following and add `test` (keep only one `dependencies` block):

~~~groovy
dependencies {
    implementation 'io.projectreactor:reactor-core:3.8.7'
    testImplementation 'io.projectreactor:reactor-test:3.8.7'
    testImplementation 'org.junit.jupiter:junit-jupiter:5.12.2'
}

test {
    useJUnitPlatform()
}
~~~

File `src/test/java/DemandTest.java`:

~~~java
import java.time.Duration;
import org.junit.jupiter.api.Test;
import reactor.core.publisher.Flux;
import reactor.test.StepVerifier;

class DemandTest {
    @Test
    void onlyEmitsWhenRequested() {
        StepVerifier.create(Flux.range(1, 5), 0)
            .expectSubscription()
            .expectNoEvent(Duration.ofMillis(20))
            .thenRequest(2)
            .expectNext(1, 2)
            .thenRequest(3)
            .expectNext(3, 4, 5)
            .verifyComplete();
    }
}
~~~

Run `gradle test`. The `0` argument means **initial request = 0**. `expectSubscription()` must come before `expectNoEvent` because subscription is also considered an event. `thenRequest(2)` allows the first two items; `thenRequest(3)` allows the remaining three items. The test proves that requests grant quota incrementally in batches.

## 7. Request Strategies and Considerations

| Consumption Mode | Example Request | When Appropriate | Risk |
| --- | --- | --- | --- |
| Item by item | `request(1)`, then after processing `request(1)` again | Want small quota, easy to trace | Overhead of many request calls |
| Batched | `request(32)`, then replenish as items are consumed | Better throughput while still bounded | Choosing too high a threshold causes backlog |
| Unbounded | `request(Long.MAX_VALUE)` | Small/finite source, sufficiently fast downstream | No output bound via demand at the subscriber |

If `onNext` merely launches an asynchronous I/O task and returns, replenishing demand immediately afterward **does not guarantee** the number of concurrent tasks is bounded. You must account for when tasks actually finish, concurrency, and queues across relevant layers.

`request(10)` does **not** mean 10 items/second. It is an item count quota, not a time-based rate limit. Rate limiting and backpressure address two different concerns and may need to be combined.

## 8. Operators Can Reshape Demand Going Upstream

A Reactor pipeline can change the request size at each stage:

- `map` typically preserves one input corresponding to one output.
- `filter` may drop items; to return two matching items, upstream may have to emit and be requested for more than two items.
- `buffer(10)` turns **10 source items into one `List`**. A downstream `request(2)` may need **20 source items** to produce two full lists.
- `flatMap` handles inner publishers; concurrency and prefetch affect requests. `publishOn` also uses its own queue/prefetch mechanism.
- `limitRate(highTide, lowTide)` splits/redistributes upstream requests into batches. `limitRate(10, 0)` is a stricter batched-request form with a threshold of 10. `limitRequest(N)` instead caps the **total** number of items allowed to reach downstream and then completes the stream once N is reached.

The following snippet must be placed inside a Java class/method with imports for `Flux`, `BaseSubscriber`, and `Subscription`; it is not a standalone runnable program:

~~~java
Flux.range(1, 100)
    .buffer(10)
    .subscribe(new BaseSubscriber<java.util.List<Integer>>() {
        @Override
        protected void hookOnSubscribe(Subscription subscription) {
            request(2); // two Lists, not two Integers
        }

        @Override
        protected void hookOnNext(java.util.List<Integer> batch) {
            System.out.println(batch);
        }
    });
~~~

The subscriber receives the first two `List<Integer>` batches containing 1–10 and 11–20. This is **two downstream `onNext` signals but 20 upstream items**; without further requests, the remaining lists are not emitted to the subscriber.

Use `doOnRequest(n -> System.out.println(n))` at different positions to inspect **each request arriving at that stage**. Do not read a single request log as the pipeline-wide pending demand, because operators may already have emitted data, refilled, or buffered items in queues.

## 9. Connection with Spring WebFlux

When a Spring WebFlux controller returns a `Flux<T>`, the framework is responsible for subscribing and requesting data through the conversion/HTTP pipeline. Normally a controller **does not hold a `Subscription` and call `request` manually**.

Server-Sent Events endpoint snippet in a Spring WebFlux application:

~~~java
import org.springframework.http.MediaType;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.RestController;
import reactor.core.publisher.Flux;

@RestController
public class EventController {
    @GetMapping(value = "/events",
                produces = MediaType.TEXT_EVENT_STREAM_VALUE)
    public Flux<String> events() {
        return Flux.range(1, 100)
            .map(i -> "event-" + i)
            .limitRate(16, 0);
    }
}
~~~

`limitRate(16, 0)` shapes **upstream** request propagation into batches of size 16. It **does not guarantee** that HTTP sends exactly 16 events/second or that network buffers hold only 16 items. The serialization layer, HTTP transport, data source, and client read speed all have their own mechanisms.

With Reactive Streams-compliant sources, preserve a proper operator chain to propagate backpressure and choose concurrency/prefetch intentionally. With "push" callback sources that emit regardless of demand, wrapping them in `Flux` alone does not automatically make the system safe: you need a bounded buffer policy, drop/latest, or business-appropriate rejection responses. Backpressure also **does not turn blocking I/O into non-blocking I/O**; avoid blocking the WebFlux event loop with blocking I/O operations inside `map` or `onNext`.

## 10. Common Mistakes

| Misconception or Bug | Reality | Fix |
| --- | --- | --- |
| `request(n)` forces the source to emit n items immediately | Only grants up to n `onNext` permissions | Track terminal signals as well |
| Calling `request(2)` again to reset quota to 2 | Requests are cumulative | Sum requests minus `onNext` |
| `request(0)` is a pause button | It is an invalid request | Stop requesting more; call `cancel()` if you want to cancel |
| Emitting `onNext` when quota is 0 | Violates subscriber demand bound | Fix the non-compliant publisher/source |
| Using `subscribe(value -> ...)` to keep demand small | Common Reactor lambda overloads request unbounded | Use `BaseSubscriber` or shaping operators |
| `request(10)` keeps every queue ≤10 | Prefetch and async operators have their own queues | Measure/bound each layer |
| Overriding `hookOnSubscribe` and forgetting to request | Source may never emit data | Call `request(n > 0)` when ready |
| `Long.MAX_VALUE` is memory-safe | It is unbounded demand per the protocol | Use only when downstream can keep up |
| Manually adding `long` demand without overflow protection | Can turn negative | Use saturating addition and proper synchronization |
| Confusing `cancel` with exhausted demand | Cancellation differs from waiting for requests | Distinguish termination from pausing |

When a `Flux` appears stalled, check: did `onSubscribe` arrive; was a positive request sent; which operator transforms or holds demand; did `onComplete`, `onError`, or `cancel` occur; does the source still have data or is it blocking? Use `doOnSubscribe`, `doOnRequest`, `doOnNext`, `doOnCancel`, and `doFinally` at the right positions to observe.

## 11. Exercises with Answers

**Question 1:** `request(4)`, three `onNext` received, then `request(2)`. What is the remaining pending demand?

**Answer:** `4 - 3 + 2 = 3`.

**Question 2:** `request(5)` but the source only has two items and then emits `onComplete`. Is this a violation?

**Answer:** No. A Publisher may emit fewer items than requested and terminate.

**Question 3:** Subscriber calls `request(3)` after `buffer(4)`. How many upstream items might be needed to produce three full buffers?

**Answer:** 12 items if the source does not terminate early; each downstream list consumes four upstream items.

**Question 4:** Should you call `request(0)` to pause?

**Answer:** No. While the subscription is active, that is an error that must lead to `onError(IllegalArgumentException)`. Either send no further requests to wait, or call `cancel` to cancel.

**Question 5:** Why might a `doOnRequest` placed before `buffer(10)` log 20 when the final subscriber calls `request(2)`?

**Answer:** Two downstream lists require up to 20 upstream items.

## 12. Takeaways and References

- `request(n)`, `n > 0`, grants **n additional `onNext` emission permissions** on a subscription.
- Finite pending demand increases on request and decreases when the publisher emits `onNext`; multiple requests are **cumulative**.
- A Publisher must not emit beyond quota, but may emit **fewer** items and terminate.
- `request(0)` and negative values are invalid; `Long.MAX_VALUE` represents unbounded demand in Reactor.
- Operators can reshape demand between stages; the request at the final subscriber does not always equal the request at the source.

Authoritative sources:

1. [Reactive Streams JVM Specification](https://github.com/reactive-streams/reactive-streams-jvm#specification) — Publisher 1.1/1.2, Subscription 3.8/3.9/3.17.
2. [Reactor: Backpressure and Ways to Reshape Requests](https://projectreactor.io/docs/core/release/reference/subscribe-backpressure.html) — `BaseSubscriber`, `limitRate`, `limitRequest`, and prefetch.
3. [Project Reactor Reference Guide](https://projectreactor.io/docs/core/release/reference/) — `Flux`, `Mono`, operators.
4. [Spring WebFlux Reference](https://docs.spring.io/spring-framework/reference/web/webflux.html) — Reactive Streams in the Spring HTTP stack.

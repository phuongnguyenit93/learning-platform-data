# Demand Regulation (Backpressure) Between Publisher and Subscriber

In **Spring WebFlux** and **Project Reactor**, *backpressure* is the mechanism by which a receiver informs a sender how many **subsequent elements** it is ready to receive. It is part of the Reactive Streams protocol, allowing a data stream to adapt to actual consumption speed without pushing every element into memory by default.

## Learning Objectives

After this lesson, you will be able to:
- Explain the roles of `Publisher`, `Subscriber`, `Subscription`, and the `request(n)` signal.
- Track the count of elements requested but not yet received (*outstanding demand*), and understand when a stream pauses, completes, or is cancelled.
- Distinguish demand regulation from queues, rate limiting, load control, and asynchrony.
- Use Reactor to request data in batches, inspect demand, and choose an appropriate policy when a source cannot slow down.
- Identify the scope across which backpressure can propagate through a Spring WebFlux application and the limitations at external sources/sinks.

## 1. Why Is Backpressure Needed?

Suppose a service receives 10,000 events/second but can process 200 events/second. If the source emits freely and every event must be retained, the number of waiting events can grow by roughly **9,800/second** (in steady state). Memory usage, latency, or both will grow over time. Running asynchronously only shifts where the work happens; by itself, it does not resolve the speed mismatch.

Three distinct approaches should be differentiated:

1. **Throttling at the source:** the receiver requests bounded batches of elements; a source capable of honoring demand emits only within that limit.
2. **Buffering or dropping:** if an external source continues pushing data, the system can use a bounded buffer, drop old/new elements, keep only the latest value, or signal an error.
3. **Rate control at another layer:** limiting requests/second, bounding concurrency, pausing broker reads, or returning overload signals to clients.

Backpressure belongs to the first approach. The other two may still be necessary to build a truly resilient pipeline under load.

## 2. The Reactive Streams Contract

In the Reactive Streams model, the main roles are:

| Component | Responsibility |
| --- | --- |
| `Publisher<T>` | Provides a sequence of elements or a completion/error signal after subscription. |
| `Subscriber<T>` | Subscribes to receive data and handles `onNext`, `onError`, `onComplete`. |
| `Subscription` | Link between one subscription and the source; allows `request(n)` or `cancel()`. |
| `Processor<T,R>` | Concept combining receiver and sender, usually replaced in Reactor code by operator chains. |

Basic sequence:

1. `Subscriber` calls `publisher.subscribe(subscriber)`.
2. `Publisher` supplies a `Subscription` via `onSubscribe(subscription)`.
3. `Subscriber` calls `subscription.request(n)` with **n > 0** to grant additional demand.
4. `Publisher` emits at most the number of elements matching remaining demand via `onNext(item)`. Each `onNext` consumes one unit of demand.
5. Demand can be topped up multiple times; `request(2)` followed by `request(3)` is equivalent to requesting a total of five additional elements, provided none have been delivered yet.
6. After emitting everything or encountering an error, the source sends **one** terminal signal: `onComplete()` or `onError(error)`. `cancel()` requests stopping the subscription and releasing associated work/resources.

Example progression of a five-element source:

| Action | Remaining Demand | Elements Seen by Receiver |
| --- | ---: | --- |
| Start, before requesting | 0 | — |
| `request(2)` | 2 | — |
| `onNext(1)`, `onNext(2)` | 0 | 1, 2 |
| `request(3)` | 3 | 1, 2 |
| `onNext(3)`, `onNext(4)`, `onNext(5)` | 0 | 1, 2, 3, 4, 5 |
| `onComplete()` | — | Completed |

**Key invariants:**

- No more `onNext` calls may be emitted than the total unconsumed demand granted so far. A compliant source can wait when demand is 0.
- `request(0)` or a negative number is invalid; per specification, the subscription must terminate with `onError` signaling an `IllegalArgumentException`.
- `request(Long.MAX_VALUE)` conventionally represents *unbounded demand*.
- `onComplete` and `onError` are terminal signals and do not consume a unit of demand; once terminated, no further `onNext` is valid.
- `cancel()` is not `onComplete()`: cancellation expresses that the receiver no longer wishes to continue; do not rely on always receiving a completion callback afterward.
- Each `subscribe` has its own `Subscription`. With a *cold* source, each subscription usually gets its own execution stream; a *hot* source can share an emission stream while subscribers have different demands.

Java has the `java.util.concurrent.Flow` API with similar interfaces, whereas Reactor uses the types from `org.reactivestreams`. Do not mix up the two interface sets when declaring methods.

## 3. Runnable Example: Request Two Elements, Then Three More

`Flux` represents 0..N elements; `Mono` represents 0..1 elements. In Reactor, `BaseSubscriber` enables explicit demand control. The snippet below uses `Flux.range`, a *cold* source that emits synchronously and honors demand.

Create the file `build.gradle`:

~~~groovy
plugins {
    id 'application'
}

repositories {
    mavenCentral()
}

dependencies {
    implementation 'io.projectreactor:reactor-core:3.6.8'
}

application {
    mainClass = 'BackpressureDemo'
}
~~~

Create the file `src/main/java/BackpressureDemo.java`:

~~~java
import org.reactivestreams.Subscription;
import reactor.core.publisher.BaseSubscriber;
import reactor.core.publisher.Flux;

public class BackpressureDemo {
    public static void main(String[] args) {
        Flux.range(1, 5)
            .subscribe(new BaseSubscriber<Integer>() {
                private int received;

                @Override
                protected void hookOnSubscribe(Subscription subscription) {
                    System.out.println("request(2)");
                    request(2);
                }

                @Override
                protected void hookOnNext(Integer value) {
                    System.out.println("onNext(" + value + ")");
                    received++;

                    if (received == 2) {
                        System.out.println("request(3)");
                        request(3);
                    }
                }

                @Override
                protected void hookOnComplete() {
                    System.out.println("onComplete()");
                }

                @Override
                protected void hookOnError(Throwable error) {
                    error.printStackTrace();
                }
            });
    }
}
~~~

In the project directory, run `gradle run` (or `./gradlew run` when a Gradle Wrapper is present; on Windows use `gradlew.bat run`). The stdout printed by the program, ignoring Gradle's own messages:

~~~text
request(2)
onNext(1)
onNext(2)
request(3)
onNext(3)
onNext(4)
onNext(5)
onComplete()
~~~

**Explanation:** `hookOnSubscribe` requests only two elements. Upon receiving the second element, `hookOnNext` requests three more. `Flux.range` fulfills all five elements and then completes. No unbounded queue is needed to handle a synchronous source capable of honoring demand. In `BaseSubscriber`, if `hookOnSubscribe` is not overridden, the default behavior is unbounded demand, which is why the example explicitly calls `request(2)`.

The illustration above pins a specific Reactor version so it can run standalone. In a Spring Boot application with `spring-boot-starter-webflux`, use the Reactor versions managed by Spring Boot's BOM to avoid dependency conflicts.

## 4. How Is Demand Propagated Through Operators?

In a chain such as:

~~~java
Flux<Integer> numbers = Flux.range(1, 100)
    .map(n -> n * 2)
    .filter(n -> n % 3 == 0)
    .doOnRequest(n -> System.out.println("requested upstream: " + n));
~~~

The subscription is wired from the end of the chain back toward the source. The final subscriber grants demand; intermediate operators can pass the requested count straight through, **transform the request**, accumulate it, or request extra to compensate for filtered elements. For instance, `filter` may have to receive more elements from the source than actually reach the subscriber. Therefore, you should not infer that a single `request(5)` at the end of the chain always produces an exact `request(5)` at every stage.

Commonly confused points:

- Ordinary `subscribe(item -> ...)` requests an unbounded amount. To observe batched throttling, use `BaseSubscriber` or `StepVerifier` tests with an initial demand of 0.
- `limitRate(10)` splits large downstream demand into smaller request batches sent upstream; it **does not** rate-limit to 10 elements/second. `limitRate(10, 0)` uses full batches instead of early replenishment.
- `publishOn(scheduler, prefetch)` opens an asynchronous boundary and has a buffer/prefetch demand. `flatMap`, `buffer`, and `window` can also alter the number of requested elements or the amount of data held. The `request` count observed upstream can be higher than what the subscriber just requested.
- `subscribeOn` determines the scheduling context for subscription/appropriate emission; switching to another scheduler does not automatically cap demand or solve a source that emits too fast.
- `take(n)` takes at most n elements and then typically cancels upstream; that is a total element limit, distinct from batched demand throttling.
- Operators with queues or prefetch still consume memory. Factor in concurrency and per-element size when choosing values.

When debugging, place `doOnRequest` **at specific positions** in the chain to know which segment's demand you are observing:

~~~java
Flux.range(1, 100)
    .doOnRequest(n -> System.out.println("source demand = " + n))
    .limitRate(10)
    .doOnRequest(n -> System.out.println("downstream demand = " + n))
    .subscribe(System.out::println);
~~~

Here the subscriber requests unboundedly, while `limitRate` splits requests to the source into batches. The logs show request signals passing each point; they do not imply a fixed execution rate.

## 5. What If the Source Cannot Slow Down?

Backpressure works best when the source can pause/suspend according to demand, such as `Flux.range` or a data-reading pipeline able to fetch more only when requested. Conversely, device callbacks, market data, sockets, a *hot* source, or timer-driven emitters may produce data even when the subscriber has not requested any. In those cases, an overload policy must be declared explicitly.

| Reactor Policy | Behavior When Downstream Falls Behind | Typical Fit |
| --- | --- | --- |
| `onBackpressureBuffer` | Holds waiting elements; must choose bounds and overflow behavior. | Data that cannot be lost during brief slowdowns, with a clear memory budget. |
| `onBackpressureDrop` | Drops elements arriving while there is no demand. | Sampling/display streams where losing updates is acceptable. |
| `onBackpressureLatest` | Retains the latest update to deliver when demand arrives. | Current state matters more than intermediate changes. |
| `onBackpressureError` | Signals an error when an element arrives without demand. | Need to fail fast and let upper layers apply retry/load control. |

Example of choosing an operator, assuming `fastSource` is a `Flux<Event>` already declared in the application:

~~~java
Flux<Event> bounded = fastSource.onBackpressureBuffer(128);
Flux<Event> sampled = fastSource.onBackpressureDrop();
Flux<Event> currentState = fastSource.onBackpressureLatest();
Flux<Event> failFast = fastSource.onBackpressureError();
~~~

This is an **integration snippet**, not a standalone Java program: `Event` and `fastSource` must be defined for the real source. With `onBackpressureBuffer(128)`, if elements arrive faster than consumption and the buffer fills up, the stream can fail on overflow; error handling behavior must be decided explicitly. Avoid calling unbounded `onBackpressureBuffer()` on streams that can grow indefinitely.

Do not use lossy strategies for payments, transactions, or audit logs where every event must be processed. When data cannot be lost, you need durable storage, delivery acknowledgements, partitioning/pausing the source, controlled retries, or load shedding, rather than expecting an in-RAM buffer to solve it alone.

With `Flux.create` or `Flux.push`, authors bridging callbacks to Reactor must consider `FluxSink.OverflowStrategy`. Continuously calling `sink.next(...)` does not make an external source automatically understand `request(n)`. Check `sink.requestedFromDownstream()` or use the `onRequest` callback and implement appropriate throttling where the data is produced.

## 6. What Is the Scope of Backpressure in Spring WebFlux?

Spring WebFlux uses the Publisher model to connect handlers, Reactor operators, and response writing. The endpoint example below lives inside **a Spring Boot application with `spring-boot-starter-webflux` added**:

~~~java
import org.springframework.http.MediaType;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.RestController;
import reactor.core.publisher.Flux;

@RestController
public class NumberController {
    @GetMapping(value = "/numbers", produces = MediaType.TEXT_EVENT_STREAM_VALUE)
    public Flux<Integer> numbers() {
        return Flux.range(1, 1_000)
            .doOnRequest(n -> System.out.println("requested = " + n))
            .doOnCancel(() -> System.out.println("client cancelled"));
    }
}
~~~

Once the application is running, you can test with `curl -N http://localhost:8080/numbers`. `text/event-stream` allows sending multiple elements in one HTTP response; `-N` disables curl's output buffering. The request numbers observed in logs depend on the actual path through WebFlux, buffers, encoders, and transport; do not assume each line read by the client triggers one `request(1)`.

**Important limitation:** demand in a Reactor pipeline **does not mean** all external components support backpressure end-to-end. HTTP clients/servers, database drivers, message brokers, WebSockets, callback SDKs, and OS buffers have different flow-control mechanisms. If the source side has already loaded all data into a `List` or buffer before creating a `Flux`, downstream demand cannot reclaim the memory already allocated beforehand. When integrating systems, check how the source actually fetches data, prefetch strategies, queues, payload sizes, cancellation, and connection closing.

## 7. Testing Demand Instead of Only Testing Output

Add to `build.gradle` from the Reactor example in section 3:

~~~groovy
dependencies {
    testImplementation 'io.projectreactor:reactor-test:3.6.8'
    testImplementation 'org.junit.jupiter:junit-jupiter:5.10.3'
}

tasks.named('test') {
    useJUnitPlatform()
}
~~~

Create `src/test/java/DemandTest.java`:

~~~java
import org.junit.jupiter.api.Test;
import reactor.core.publisher.Flux;
import reactor.test.StepVerifier;

class DemandTest {
    @Test
    void receivesOnlyAfterRequesting() {
        StepVerifier.create(Flux.range(1, 5), 0)
            .thenRequest(2)
            .expectNext(1, 2)
            .thenRequest(3)
            .expectNext(3, 4, 5)
            .verifyComplete();
    }
}
~~~

Run `gradle test` or the corresponding Gradle Wrapper command. Passing `0` to `StepVerifier.create(..., 0)` sets **initial request = 0**; the test explicitly grants two units and then three units. If a source emits illegitimately without demand, the test can catch the unexpected signal. For asynchronous sources, you also need to test timing, subscription cancellation, high load, and buffer overflow policies; this test mainly verifies the demand contract of a synchronous source.

## 8. Common Mistakes

1. **Treating `Flux` as a guarantee against out-of-memory errors.** Preloaded data, operator queues, and *hot* sources can still create memory pressure.
2. **Confusing `request(n)` with a rate limit.** `request(100)` permits up to the next 100 elements, not 100 elements/second.
3. **Using `subscribe(item -> ...)` and expecting to see batched demand.** This subscription style usually requests an unbounded amount.
4. **Using an unbounded buffer to handle a source that is permanently faster than the receiver.** Sustained speed mismatch will make the queue grow forever; you need bounds, overload signals, or source throttling.
5. **Using drop/latest when every record is mandatory.** Element loss can happen by the operator's design.
6. **Thinking `publishOn`, `subscribeOn`, or adding threads is enough.** They change execution placement, not demand control, queues, or source load.
7. **Blocking the event loop with `block()` or long synchronous I/O.** Blocking can stall the event loop; if forced to use a blocking API, isolate it with an appropriate scheduler/integration layer and limit concurrency.
8. **Ignoring `cancel` and terminal signals.** Connection cancellation does not mean upstream automatically releases every resource; bridges/drivers must cooperate on cancellation and cleanup.

## 9. Practical Solution-Selection Workflow

Before adding operators, determine in order:

1. **Can the source pause?** If yes, prefer propagating `request(n)` upstream to the source and reading/emitting only when requested.
2. **Is dropping events acceptable?** If yes, consider drop/latest according to data semantics; if not, you need durable storage or lossless source throttling.
3. **Are memory and latency bounded?** Account for element size, queues, prefetch, concurrency, and total subscribers; choose a finite buffer along with an overflow policy.
4. **How will you observe it?** Track request volume, queue depth, wait time, drop/overflow rate, errors, cancellations, and production/consumption rates.
5. **Have you tested with a slow consumer?** Test demand with `StepVerifier`, then load-test with a slow downstream, *hot* sources, disconnects, timeouts, and retries.

**Key takeaway:** `request(n)` is the language of demand in Reactive Streams. It allows a cooperating source to emit only when the receiver is ready; for uncooperative sources, the application must still choose explicit throttling, buffering, dropping, or error policies.

## References

- Reactive Streams — protocol specification: https://www.reactive-streams.org/
- Project Reactor — official documentation: https://projectreactor.io/docs/core/release/reference/
- Spring Framework — WebFlux: https://docs.spring.io/spring-framework/reference/web/webflux.html

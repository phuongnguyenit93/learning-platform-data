# Ways to Subscribe with Unbounded Demand in Project Reactor

## 1. Objectives and the Backpressure Problem

In **Spring Framework Reactive**, Project Reactor uses `Flux<T>` and `Mono<T>` to represent Publishers under the Reactive Streams specification. When a Subscriber registers (`subscribe`), it must tell the source **how many elements it is allowed to receive** using `Subscription.request(n)`. This is the foundation of **backpressure**: the receiver can limit the sender's emission pace.

However, there are several ways to subscribe in Reactor that **automatically request an unbounded number** from the start. Understanding these paths helps avoid the misconception that using `Flux` automatically means per-element controlled backpressure.

After this lesson, you should be able to:

- Understand `request(Long.MAX_VALUE)` and the meaning of "unbounded demand".
- Identify `subscribe` overloads that default to requesting unbounded demand, even when you do not call `request` in application code.
- Know that `BaseSubscriber` also defaults to unbounded demand if `hookOnSubscribe` is not overridden, and use `requestUnbounded()` when expressing that intent explicitly.
- Distinguish subscription paths that can **actively grant demand** from paths that automatically request unboundedly.
- Know that demand at the final subscriber can be **altered by intermediate operators** before reaching the source, and that unbounded requests do not eliminate the need to manage memory, rate, and cancellation.
- Choose the appropriate subscription style when writing Spring WebFlux applications.

## 2. From `Subscription` to `Long.MAX_VALUE`

### 2.1. Demand Is Permission to Emit, Not the Guaranteed Total Elements Received

Conceptually, the interaction between Publisher and Subscriber looks like this:

~~~text
Publisher.subscribe(subscriber)
             |
             v
Subscriber.onSubscribe(subscription)
             |
             +-- subscription.request(2) -------------> source
             |<-------------------------- onNext(item1)
             |<-------------------------- onNext(item2)
             |
             +-- subscription.request(1) -------------> source
             |<-------------------------- onNext(item3)
             |<-------------------------- onComplete()
~~~

A single `request(2)` grants permission to receive **at most two more `onNext` signals** on top of existing demand. The source may emit fewer if it runs out of data; `onComplete` or `onError` does not count as an `onNext` element and does not require a separate unit of demand to be emitted. Demand is cumulative across requests.

`request(n)` must use a positive integer (`n > 0`); `request(0)` or `request(-1)` does not mean "not ready to receive" or "unbounded". These are invalid requests and the protocol requires the source to signal `IllegalArgumentException` while the subscription is active. **To subscribe without emitting data yet, simply refrain from calling `request` for now.**

### 2.2. Why Does `Long.MAX_VALUE` Represent an Unbounded Request?

The Java value `Long.MAX_VALUE` equals `9_223_372_036_854_775_807L`. The Reactive Streams specification requires subscriptions to support demand up to this limit and **allows** publishers to treat demand at that threshold as *effectively unbounded*. Project Reactor uses this value as the convention for an unbounded request.

~~~java
subscription.request(Long.MAX_VALUE); // Unbounded demand in Reactor
~~~

Practical meaning: "From now on, the source is permitted to emit data as fast as the pipeline allows, without waiting for the receiver to grant demand in batches." It does **not** force the source to create exactly `Long.MAX_VALUE` elements, does not turn a finite source into an infinite one, does not guarantee sufficient CPU/I/O speed, and does not mean all data is preloaded into RAM at once.

If a source has three elements, `request(Long.MAX_VALUE)` still receives only three `onNext` signals followed by `onComplete`. If a source emits infinitely, unbounded demand can lead to continuous activity until the subscriber cancels, the pipeline errors, or the application shuts down. Actual emission behavior also depends on whether the source is synchronous or asynchronous, schedulers, and operators.

### 2.3. Two Concepts Often Confused

| Concept | Meaning | Does Not Imply |
| --- | --- | --- |
| **Unbounded demand** | Subscriber does not impose a limit on `onNext` count within that subscription | Source has already generated every item, cancellation no longer applies, or resources are unlimited |
| **Unbounded source** | A source capable of generating infinite elements (if not stopped) | Subscriber will necessarily request unboundedly |

A finite source `Flux.range(1, 3)` can receive an unbounded request. Conversely, a potentially infinite source can be driven by a subscriber using individual `request(1)` or `request(10)` calls.

## 3. `subscribe` Overloads That Default to Requesting Unboundedly

This is the most common case encountered in Reactor code. When using convenient `Flux`/`Mono` overloads **without managing the `Subscription` yourself**, Reactor typically sends `request(Long.MAX_VALUE)` automatically upon subscribing.

| Call | What the Application Provides | Default Demand |
| --- | --- | --- |
| `source.subscribe()` | No consumer passed | Unbounded |
| `source.subscribe(onNext)` | Callback for data | Unbounded |
| `source.subscribe(onNext, onError)` | Callbacks for data and error | Unbounded |
| `source.subscribe(onNext, onError, onComplete)` | Adds completion callback | Unbounded |
| `source.subscribe(onNext, onError, onComplete, subscriptionConsumer)` | Callback receiving `Subscription` to request | **Exception**: callback decides demand itself; this overload is marked deprecated—prefer `BaseSubscriber` |
| `source.subscribe(customSubscriber)` | A custom `Subscriber` | **Depends** on the `Subscriber` implementation and how it calls `request` |

In short: the number of `onNext`/`onError`/`onComplete` callbacks does not determine demand. When using common lambda overloads, the callbacks only handle signals; **Reactor actively grants unbounded demand** for that subscriber.

### 3.1. `subscribe()` Without Arguments

~~~java
Flux.range(1, 3)
    .doOnRequest(n -> System.out.println("request=" + n))
    .doOnNext(n -> System.out.println("upstream=" + n))
    .subscribe();
~~~

With the synchronous `range` source, expected stdout:

~~~text
request=9223372036854775807
upstream=1
upstream=2
upstream=3
~~~

Passing no consumer **does not mean the source does not run**. The `doOnNext` callback is a pipeline hook and still observes upstream data; you simply did not attach a data-receiving callback in the `subscribe()` overload.

### 3.2. `subscribe(Consumer)`

~~~java
Flux.just("A", "B")
    .subscribe(value -> System.out.println("next=" + value));
~~~

Upon subscribing, Reactor automatically requests unboundedly and the consumer receives `A`, `B`. For an asynchronous Publisher, `subscribe` usually returns before all elements arrive. For small synchronous sources like `just`/`range` without scheduler switches, callbacks usually run immediately on the calling thread.

Pitfall to avoid: the overload with only `onNext` provides no `onError` handler callback; when the source errors, Reactor may report an unhandled error via its default error hook. Both learning and production code need explicit error handling paths.

### 3.3. `subscribe(onNext, onError[, onComplete])`

~~~java
Flux.just(10, 20)
    .subscribe(
        value -> System.out.println("next=" + value),
        error -> System.err.println("error=" + error.getMessage()),
        () -> System.out.println("complete")
    );
~~~

These three callbacks explicitly express data, error, and completion signals. **They do not bound demand**: the subscribing side still typically requests `Long.MAX_VALUE` right at subscribe time. If the stream errors, only the `onError` handler runs, with no subsequent `onComplete` on the same subscription.

### 3.4. The `Consumer<Subscription>` Exception and Why to Avoid It as a Default

An overload `subscribe(onNext, onError, onComplete, subscriptionConsumer)` lets the final callback receive the `Subscription` to call `request(n)`. With this callback, Reactor **does not automatically request unboundedly**; if the callback only logs and does not request, the source may sit idle.

In current API documentation, this overload is marked **deprecated** because users easily forget to request. Prefer `BaseSubscriber` for demand control (Section 5). Below is an illustration of the idea from the legacy API, **not a recommended pattern for new code**:

~~~java
// Deprecated API: illustrates the exception, should not be used in new code.
flux.subscribe(
    value -> consume(value),
    error -> handle(error),
    () -> completed(),
    subscription -> subscription.request(2)
);
~~~

`consume`, `handle`, `completed`, and `flux` above are illustrative names and **not** a runnable standalone program. To run a complete demand-control example with Java 17+, see Section 7.

## 4. Other "Terminal" Consumption Paths Related to Unbounded Requests

The Reactor Reference section "On Backpressure and Ways to Reshape Requests" also notes terminal operations such as `Mono.block()`, `Flux.blockFirst()`, and `Flux.blockLast()` as consumption paths that create a subscription and actively request data, typically without letting the developer grant per-element demand manually.

~~~java
String value = Mono.just("OK").block();     // Wait for one result, no manual request
Integer first = Flux.range(1, 3).blockFirst(); // Wait for the first element
Integer last = Flux.range(1, 3).blockLast();   // Wait for the final result
~~~

Note the distinctions:

- `block()` and its variants are operations that **block the calling thread**; they do not make a Publisher non-blocking.
- `blockFirst()` can cancel once the first element is received; therefore, requesting many elements from the source **does not** mean every element will reach the consumer.
- Each call to a blocking terminal like `block()` on a cold Publisher usually creates a new subscription; for sources with side effects, side effects may repeat.

The Reactor Reference also lists iteration methods `toIterable()` and `toStream()` among operations requiring care regarding large demand. In current APIs, they provide `batchSize` overloads to limit prefetch element counts and use internal buffering for blocking iteration. Therefore, **do not rigidly assume that every call to `toIterable()/toStream()` emits an exact `Long.MAX_VALUE` upstream request** across all versions and configurations; observe `doOnRequest` or configure `batchSize` if real control is needed.

Specifically in Spring WebFlux, **never call `block()` or iterate `toIterable()` on an event-loop/non-blocking thread**. Doing so can cause runtime errors and block request-serving capacity. Instead of blocking, compose Publishers with `map`, `flatMap`, `zip`, etc., and return the Publisher to the framework.

## 5. `BaseSubscriber`: Default Unbounded and Purposeful Demand Granting

Reactor's `BaseSubscriber<T>` is a helper implementing `Subscriber<T>`, providing hooks such as `hookOnSubscribe`, `hookOnNext`, `hookOnComplete`, `hookOnError`, `hookOnCancel`, along with operations `request(n)`, `requestUnbounded()`, and `cancel()`.

### 5.1. Not Overriding `hookOnSubscribe`: Still Requests Unboundedly

~~~java
Flux.range(1, 3)
    .subscribe(new BaseSubscriber<Integer>() {
        @Override
        protected void hookOnNext(Integer value) {
            System.out.println("next=" + value);
        }
    });
~~~

By default, `BaseSubscriber.hookOnSubscribe` calls the equivalent of `request(Long.MAX_VALUE)`. Therefore, overriding only `hookOnNext` **does not** make the subscription bounded.

### 5.2. Expressing Unbounded Intent Explicitly

~~~java
Flux.range(1, 3)
    .subscribe(new BaseSubscriber<Integer>() {
        @Override
        protected void hookOnSubscribe(Subscription subscription) {
            requestUnbounded(); // Equivalent to request(Long.MAX_VALUE)
        }

        @Override
        protected void hookOnNext(Integer value) {
            System.out.println(value);
        }

        @Override
        protected void hookOnError(Throwable error) {
            System.err.println("error=" + error.getMessage());
        }
    });
~~~

`requestUnbounded()` makes clear that the receiver permits all data as soon as available. This call does not mean `cancel()` ceases to work; you can still cancel the subscription when no longer needed.

### 5.3. Overriding and Requesting a Finite Amount

~~~java
Flux.range(1, 5)
    .subscribe(new BaseSubscriber<Integer>() {
        @Override
        protected void hookOnSubscribe(Subscription subscription) {
            request(2); // Grant demand only for the first two elements
        }

        @Override
        protected void hookOnNext(Integer value) {
            System.out.println("next=" + value);
            if (value == 2) {
                request(3); // Grant more after processing two items
            }
        }
    });
~~~

The source emits all five elements and completes. If `request(3)` is omitted, the subscriber only receives two items, and the subscription **remains waiting for demand** for the rest (unless cancelled or terminated by a valid terminal signal). This is the key difference from `subscribe(Consumer)`.

**Note:** If you override `hookOnSubscribe` only to log and do not request, you have also disabled the default unbounded behavior. `BaseSubscriber` is designed for **one-time use per subscription**; do not reuse an active instance to subscribe to multiple different sources. To retain a subscriber handle for cancellation when needed, you can use `subscribeWith(new BaseSubscriber<...>() { ... })`.

### 5.4. Implementing `Subscriber` Directly Has No Universal Default

When calling `publisher.subscribe(customSubscriber)`, the implementation of `customSubscriber.onSubscribe(Subscription)` decides whether to call `request`, how much, and when. Reactive Streams does not assume every custom `Subscriber` requests `Long.MAX_VALUE`. A subscriber that does not request may receive no `onNext`, even after subscribing successfully.

## 6. Unbounded Downstream Is Not Necessarily Unbounded at the Source

Demand travels **upstream** from the subscriber through the chain of operators. Several operators can **alter, batch, multiply, or limit** the number of items requested.

~~~text
Source Flux        Operator                  Final Subscriber
     |                |                              |
     |<-- request(5) -|<--- request(Long.MAX_VALUE) --|
     |--- onNext ---> |------------------ onNext --->|
     |<-- request(5) -|                              |
     |--- onNext ---> |------------------ onNext --->|
~~~

This is a conceptual diagram when an operator splits demand into 5-element batches; actual request counts also depend on the operator's replenishment strategy.

### 6.1. `limitRate` Splits Requests into Batches

~~~java
Flux.range(1, 10)
    .doOnRequest(n -> System.out.println("upstream request=" + n))
    .limitRate(5, 0)
    .subscribe(value -> System.out.println("next=" + value));
~~~

The final lambda subscriber sends an unbounded request to `limitRate`. However, this operator requests upstream **in batches of at most 5**; the parameter `lowTide = 0` uses strict batches (`5` then `5`), without the default percentage-based replenishment mechanism. Two upstream requests suffice for the ten-element source in this example.

With single-argument `limitRate(5)`, the strategy of replenishing once a threshold of elements is consumed can cause upstream requests to have sizes other than 5. Therefore, to learn exact demand behavior, observe where `doOnRequest` is placed.

### 6.2. `buffer` Changes the Demand Unit

~~~java
Flux.range(1, 100)
    .doOnRequest(n -> System.out.println("source asked=" + n))
    .buffer(10);
~~~

If downstream requests `2` **lists**, the `buffer(10)` operator can request up to `20` single elements from upstream to form two lists. Thus `request(2)` at one location does not mean `request(2)` everywhere.

Similarly, `flatMap`, `publishOn`, and certain other operators have prefetch, concurrency, or queue policies; they may emit multiple finite requests to the source even when the final subscriber requested unboundedly. Conclusions about requests must be tied to the **observation point**.

### 6.3. `doOnRequest` Is the Verification Tool

Place `doOnRequest` right next to the boundary you want to observe:

~~~java
Flux<Integer> pipeline = Flux.range(1, 10)
    .doOnRequest(n -> System.out.println("before limitRate=" + n))
    .limitRate(5, 0)
    .doOnRequest(n -> System.out.println("after limitRate=" + n));

pipeline.subscribe(value -> {});
~~~

The `after limitRate` log observes demand **from the subscriber into the operator** (it will show `Long.MAX_VALUE`), while the `before limitRate` log observes requests **from the operator to the source** (finite batches). Do not look at only one side's log and conclude the entire pipeline is bounded or unbounded.

## 7. Runnable Java 17+ Example: Observing Unbounded and Bounded

This example uses Reactor Core 3.8.8, Maven, and synchronous `Flux.range`/`Mono.just` sources with no scheduler switches. The output is designed so stdout has deterministic ordering and clearly demonstrates `request`.

Create the structure:

~~~text
reactor-unbounded-demo/
├── pom.xml
└── src/main/java/example/UnboundedDemandDemo.java
~~~

**File `pom.xml`:**

~~~xml
<project xmlns="http://maven.apache.org/POM/4.0.0"
         xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
         xsi:schemaLocation="http://maven.apache.org/POM/4.0.0 https://maven.apache.org/xsd/maven-4.0.0.xsd">
    <modelVersion>4.0.0</modelVersion>
    <groupId>example</groupId>
    <artifactId>reactor-unbounded-demo</artifactId>
    <version>1.0.0</version>
    <properties>
        <maven.compiler.release>17</maven.compiler.release>
        <project.build.sourceEncoding>UTF-8</project.build.sourceEncoding>
    </properties>
    <dependencies>
        <dependency>
            <groupId>io.projectreactor</groupId>
            <artifactId>reactor-core</artifactId>
            <version>3.8.8</version>
        </dependency>
    </dependencies>
    <build>
        <plugins>
            <plugin>
                <groupId>org.apache.maven.plugins</groupId>
                <artifactId>maven-compiler-plugin</artifactId>
                <version>3.13.0</version>
            </plugin>
            <plugin>
                <groupId>org.codehaus.mojo</groupId>
                <artifactId>exec-maven-plugin</artifactId>
                <version>3.5.1</version>
                <configuration>
                    <mainClass>example.UnboundedDemandDemo</mainClass>
                </configuration>
            </plugin>
        </plugins>
    </build>
</project>
~~~

**File `src/main/java/example/UnboundedDemandDemo.java`:**

~~~java
package example;

import org.reactivestreams.Subscription;
import reactor.core.publisher.BaseSubscriber;
import reactor.core.publisher.Flux;
import reactor.core.publisher.Mono;

public final class UnboundedDemandDemo {

    public static void main(String[] args) {
        System.out.println("== lambda subscribe ==");
        Flux.range(1, 3)
            .doOnRequest(n -> System.out.println("A request=" + n))
            .subscribe(
                n -> System.out.println("A next=" + n),
                error -> System.out.println("A error=" + error.getMessage()),
                () -> System.out.println("A complete")
            );

        System.out.println("== BaseSubscriber default ==");
        Flux.range(10, 2)
            .doOnRequest(n -> System.out.println("B request=" + n))
            .subscribe(new BaseSubscriber<Integer>() {
                @Override
                protected void hookOnNext(Integer n) {
                    System.out.println("B next=" + n);
                }

                @Override
                protected void hookOnComplete() {
                    System.out.println("B complete");
                }
            });

        System.out.println("== BaseSubscriber bounded ==");
        Flux.range(20, 3)
            .doOnRequest(n -> System.out.println("C request=" + n))
            .subscribe(new BaseSubscriber<Integer>() {
                @Override
                protected void hookOnSubscribe(Subscription subscription) {
                    System.out.println("C subscribed");
                    request(2);
                }

                @Override
                protected void hookOnNext(Integer n) {
                    System.out.println("C next=" + n);
                    if (n == 21) {
                        request(1);
                    }
                }

                @Override
                protected void hookOnComplete() {
                    System.out.println("C complete");
                }
            });

        System.out.println("== blocking Mono ==");
        String value = Mono.just("ready")
            .doOnRequest(n -> System.out.println("D request=" + n))
            .block();
        System.out.println("D value=" + value);
    }
}
~~~

**Run from the `reactor-unbounded-demo` directory:**

~~~bash
mvn -q compile exec:java
~~~

**Expected stdout:**

~~~text
== lambda subscribe ==
A request=9223372036854775807
A next=1
A next=2
A next=3
A complete
== BaseSubscriber default ==
B request=9223372036854775807
B next=10
B next=11
B complete
== BaseSubscriber bounded ==
C subscribed
C request=2
C next=20
C next=21
C request=1
C next=22
C complete
== blocking Mono ==
D request=9223372036854775807
D value=ready
~~~

Result analysis:

1. The `subscribe(onNext, onError, onComplete)` overload in part A sends `Long.MAX_VALUE` immediately; we did not write `request`, yet `doOnRequest` still records this value.
2. `BaseSubscriber` in part B **does not override `hookOnSubscribe`**, so the default behavior is also unbounded.
3. `BaseSubscriber` in part C **overrides `hookOnSubscribe`**, initially requesting 2, and after receiving element 21 requests 1 more; the source emits exactly three elements and then completes.
4. `Mono.block()` in part D also subscribes and actively requests data; however, it **blocks the thread** until a result is available.
5. Small synchronous sources without schedulers make the observed ordering reproducible. With async sources, callbacks may run at different times, so do not conclude that all `subscribe` calls are synchronous.

## 8. Performance Impact and Lifecycle Management

### 8.1. When Is an Unbounded Request Appropriate?

- **Small, finite, in-memory sources** (`Flux.just("a", "b")`, `Flux.range(1, 3)`) with a fast consumer: unbounded is simple and reasonable.
- **`Mono<T>` holding at most one element**: unbounded requests pose little risk regarding **the element count of the `Mono` itself**; you still need caution if upstream work generates large payloads or blocking I/O.
- **A terminal aggregation with clearly bounded input**: unbounded can be used, though you must still account for resources needed to create/hold the data and the result size.

### 8.2. When Should Bounded Demand Be Considered?

- Sources that can emit very large or infinite numbers of elements.
- A consumer that processes slower than the source (DB writes, API calls, data encoding).
- Pipelines with queues, prefetching, `buffer`, `collectList`, or accumulating operations.
- Subscribers that need to decide when to receive the next batch based on resource state.
- Each element carrying a resource that must be closed/released according to its lifecycle.

Unbounded demand **does not automatically cause out-of-memory errors**. Impact depends on the source, emission strategy, scheduler, buffers, and consumption rate. However, it removes the **limiting mechanism driven by final subscriber demand**, allowing the source to emit at full speed; therefore, do not use it unconditionally as a default in long-lived streams or streams with accumulation risk.

### 8.3. `Disposable.dispose()` Is Cancellation, Not Completion

The `subscribe(...)` overloads typically return a `Disposable`:

~~~java
Disposable disposable = Flux.interval(Duration.ofSeconds(1))
    .subscribe(
        tick -> System.out.println("tick=" + tick),
        error -> System.err.println("error=" + error.getMessage())
    );

// At an appropriate point decided by the application:
disposable.dispose(); // requests cancellation of the subscription
~~~

This snippet is an **illustration inside an application that already imports `reactor.core.Disposable` and `java.time.Duration`**, not a complete runnable program. `dispose()` requests cancellation; it does not emit an artificial `onComplete` to the subscriber, nor does it guarantee all asynchronous work already started stops immediately.

With a finite synchronous source like `Flux.range(1, 1000).subscribe(...)`, most or all of the source may already have completed **before the `subscribe` call returns**, so a subsequent `dispose()` cannot turn back time to stop already-emitted elements. If bounds are needed, apply `take(n)`, `limitRequest(n)`, `timeout`, or control demand from the start depending on your goal.

### 8.4. `take` Limits Received Data; `limitRate` Limits Request Pace

Do not conflate three different questions:

| Goal | Tool | Effect |
| --- | --- | --- |
| Grant demand in batches from the subscriber | `BaseSubscriber.request(n)` | Actively controls when permission is granted for new data |
| Split large downstream requests into upstream batches | `limitRate(highTide, lowTide)` | Keeps data flowing, but reshapes request sizes to the source |
| Want at most N elements then terminate/cancel | `take(n)`, `limitRequest(n)` | Caps total elements passed downstream, not merely batching |

A technical detail: `take(n)` has overloads/policies that adjust upstream request levels; if you need strict request capping to the source, check the `take(n, true)` variant or `limitRequest(n)` in the Javadoc. Do not conclude "`take(n)` always requests exactly N from every upstream" when the pipeline contains other operators.

## 9. Application in Spring WebFlux

### 9.1. Handlers Should Typically Return a Publisher

~~~java
// Illustrative snippet inside a Spring WebFlux @RestController.
@GetMapping("/numbers")
public Flux<Integer> numbers() {
    return Flux.range(1, 100);
}
~~~

When Spring WebFlux handles HTTP, the framework subscribes to the Publisher when writing the response; how much data it requests depends on the HTTP mechanism, codecs, operators, and internal subscribers. **Do not assume** that all actual upstream requests are `Long.MAX_VALUE` just because `Flux` appears in the return type.

Avoid manually calling `subscribe()` inside a controller and returning `Mono.just("OK")`: the detached operation may still be running after HTTP returns OK, and errors/cancellations are no longer tied to the response lifecycle. Prefer **returning the Publisher** and composing operations using `map`/`flatMap`/`then`.

### 9.2. Do Not Treat `subscribe()` as a Safe Way to "Trigger" I/O

~~~java
// Problematic example if inside a WebFlux handler:
service.save(event).subscribe(); // Loses ability to tie errors and cancellation to the response
return Mono.just("accepted");
~~~

Instead, if you must wait for the save to succeed before returning confirmation:

~~~java
return service.save(event).thenReturn("accepted");
~~~

If the business requirement truly calls for background processing independent of the request, design an explicit work channel and lifecycle rather than calling `subscribe()` and discarding the handle. The focus here is **demand and Subscription ownership**: whoever subscribes must take responsibility for errors and cancellation.

### 9.3. Do Not Use Blocking Terminals on the Event Loop

`block()`, `blockFirst()`, `blockLast()`, and iterating `toIterable()/toStream()` can block threads; in a WebFlux non-blocking pipeline, this harms responsiveness and can throw `IllegalStateException` on threads marked non-blocking. Compose the pipeline with reactive operators and let the framework perform the subscription.

## 10. Common Errors and How to Diagnose Them

**Error 1 — Assuming calling `subscribe(onNext)` means `request(1)` one by one.** Common lambda overloads request `Long.MAX_VALUE`; the `onNext` callback only receives data and does not throttle on its own.

**Error 2 — Thinking a `BaseSubscriber` automatically has per-element backpressure.** If `hookOnSubscribe` is not overridden, the base implementation still requests unboundedly. To be bounded, explicitly call a positive `request(n)`.

**Error 3 — Overriding `hookOnSubscribe` without requesting.** With sources requiring demand to emit `onNext`, the subscription can sit idle. Fix: call `request(n)` and grant more once enough items have been processed.

**Error 4 — Using `request(0)` to pause.** This is an invalid request under Reactive Streams, not a pause command. To temporarily stop receiving new data, refrain from sending more demand.

**Error 5 — Thinking `request(Long.MAX_VALUE)` forces the source to produce a huge number of elements.** It is unbounded **permission to emit**; the source can terminate after 0, 1, or N elements.

**Error 6 — Inferring upstream demand from a downstream `doOnRequest`.** Operators like `limitRate`/`buffer`/`flatMap`/`publishOn` can reshape requests. Place the hook at the exact boundary you want to observe.

**Error 7 — Using `subscribe()` without error handling.** For streams that can signal errors, provide an `onError` handling path or return the Publisher for the framework to manage the lifecycle.

**Error 8 — Thinking `Disposable.dispose()` sends `onComplete`.** `dispose()` cancels the subscription; cancellation is not completion.

**Error 9 — Using `block()` on the event loop to simplify processing.** The result is thread blocking and potential runtime errors; use asynchronous Publisher composition instead.

**Error 10 — Assuming `limitRate` automatically caps all memory usage.** It mainly adjusts upstream requests. Queues/buffers/aggregations and the actual source still govern resource consumption.

**Error 11 — Re-subscribing the same active `BaseSubscriber` instance.** An instance is designed to bind to a single subscription; create a new subscriber for each subscription.

**Error 12 — Confusing unbounded requests with non-blocking.** Demand is signal coordination; it does not turn a blocking I/O operation into a non-blocking one.

## 11. Practice Questions and Answers

1. Does `Flux.range(1, 3).subscribe(System.out::println)` send `request(3)` by default? **No**. Common lambda subscribers send `Long.MAX_VALUE`, even though the source only has three numbers.
2. Does `Flux.range(1, 3).subscribe()` run the source? **Yes**, the subscription has an unbounded request; lacking a final consumer does not stop upstream from running.
3. Does `new BaseSubscriber<>() { hookOnNext(...) }` automatically request one item at a time? **No**; the default `hookOnSubscribe` requests unboundedly.
4. What happens if you override `hookOnSubscribe` only to log and never call `request`? **The source has no demand for `onNext`, so it typically waits idle**. Explicitly send positive requests.
5. `source.limitRate(4, 0).subscribe(onNext)`: does the final subscriber request unboundedly? **Yes**. However, `limitRate` splits requests sent upstream into batches of at most 4.
6. When a subscriber calls `request(2)` then `request(3)`, at most how many `onNext` elements are permitted if no prior demand remained? **5**, minus any elements already emitted that reduced demand; the source may emit fewer if it completes or errors.
7. Should you call `block()` directly inside a WebFlux handler? **No** on non-blocking/event-loop threads; return a Publisher and chain operators instead.
8. If `Flux.just("A", "B")` has already completed, can `dispose()` after `subscribe` returns "retract" already-emitted items? **No**.
9. Does `request(-1)` mean an unbounded request? **No**, it is an invalid request.
10. If you want at most 5 items emitted, is `limitRate(5)` sufficient? **No**: `limitRate` adjusts request batch sizes, not the total item count. Use `take(5)`/`limitRequest(5)` for that purpose.

## 12. Key Takeaways and References

Practical rules:

- **`subscribe()` and most lambda overloads → request `Long.MAX_VALUE`.**
- **`BaseSubscriber` without overriding `hookOnSubscribe` → also requests unboundedly.**
- **To actively control demand → custom `Subscriber`/`BaseSubscriber` and positive `request(n)`.**
- **Demand observed at the end of a pipeline may differ from demand reaching the source** due to intermediate operators.
- **Unbounded requests are no substitute for data bounds, cleanup, error handling, and cancellation.**

Direct reference documentation:

1. [Project Reactor – On Backpressure and Ways to Reshape Requests](https://projectreactor.io/docs/core/release/reference/subscribe-backpressure.html): lists subscription patterns that typically emit unbounded requests, `BaseSubscriber`, and `limitRate`.
2. [Project Reactor – Simple Ways to Create a Flux or Mono and Subscribe to It](https://projectreactor.io/docs/core/release/reference/coreFeatures/simple-ways-to-create-a-flux-or-mono-and-subscribe-to-it.html): `subscribe` overloads, controlling demand, and `requestUnbounded()`.
3. [Project Reactor Javadoc – Flux](https://projectreactor.io/docs/core/release/api/reactor/core/publisher/Flux.html): `subscribe` overloads, `limitRate`, `toIterable`/`toStream`, and deprecation details.
4. [Project Reactor Javadoc – BaseSubscriber](https://projectreactor.io/docs/core/release/api/reactor/core/publisher/BaseSubscriber.html): default hooks and request/cancel methods.
5. [Reactive Streams JVM Specification](https://github.com/reactive-streams/reactive-streams-jvm#specification): rules for `request(n)`, `Long.MAX_VALUE`, terminal signals, and cancellation.
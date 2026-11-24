# Controlling Requests with BaseSubscriber

**Module:** Spring Framework – reactive  
**Parent topic:** Backpressure

## Learning Objectives

After this lesson, you will be able to:

- Clearly understand the `Publisher` → `Subscriber` → `Subscription` relationship and the backpressure mechanism via `request(n)`.
- Use `BaseSubscriber<T>` to request elements in batches or one by one, instead of the unbounded default.
- Distinguish `request`, `cancel`, `onComplete`, and `onError`; predict signals as well as the execution order of illustrative programs.
- Apply lifecycle hooks such as `hookOnSubscribe`, `hookOnNext`, `hookOnError`, `hookOnComplete`, `hookOnCancel`, and `hookFinally`.
- Explain why demand at the final subscriber can differ from requests observed upstream when `filter`, `buffer`, `flatMap`, or `publishOn` are present.
- Know when managing a subscriber manually is appropriate and why Spring WebFlux usually owns the HTTP response subscription.

## 1. The Backpressure Problem That BaseSubscriber Solves

When a source emits faster than the receiver can process, without coordination, data can pile up in memory or queues. Reactive Streams uses **backpressure** so the receiver sends a demand signal upstream: via `Subscription.request(long n)`, the subscriber announces it is ready to receive up to `n` more elements.

```text
Subscriber                  Publisher
    |                           |
    |--- subscribe() ---------->|
    |<-- onSubscribe(s) --------|
    |                           |
    |--- s.request(2) --------->|
    |<-- onNext(value1) --------|
    |<-- onNext(value2) --------|
    |                           | (0 demand left)
    |--- s.request(1) --------->|
    |<-- onNext(value3) --------|
    |<-- onComplete() ----------| (finite source exhausted)
```

The diagram is an illustrative case of a three-element source. In the actual protocol, the subscriber receives `onSubscribe` before receiving `onNext`; the source must not send more `onNext` signals than the total granted demand. `onComplete` and `onError` are terminal signals and do not require another `request(1)` just to permit signaling completion.

**Demand is permission to emit, not a promise that that exact number of values will exist.** `request(10)` might receive only three values and then `onComplete` because the source is exhausted, or receive zero values because the source is empty. If the source errors, an `onError` signal can terminate the stream before all requested items arrive.

Reactor's convenient `subscribe()` overloads such as `flux.subscribe(value -> ...)` typically request `Long.MAX_VALUE`, meaning **unbounded demand**. This approach does not automatically cause errors and may fit many scenarios, but it does not give us a "process first, then ask for more" rhythm. `BaseSubscriber` is the tool to quantify demand yourself.

## 2. What Is BaseSubscriber?

`reactor.core.publisher.BaseSubscriber<T>` is Reactor's base class for a custom subscriber. It holds a reference to the `Subscription` and provides direct control methods:

| API | Purpose |
| --- | --- |
| `request(long n)` | Request `n` more elements; `n` must be positive. |
| `requestUnbounded()` | Request `Long.MAX_VALUE`, switching to unbounded demand. |
| `cancel()` | Request cancellation of the managed subscription. |
| `dispose()` | Use the `Disposable` interface to cancel the subscription. |
| `isDisposed()` | Check disposed state; does not replace full application lifecycle management. |

One easily overlooked detail: **if `hookOnSubscribe` is not overridden, `BaseSubscriber` defaults to requesting unboundedly**. To genuinely control demand, you must override this hook and grant an appropriate positive initial number, such as `request(1)`.

`BaseSubscriber` is designed to bind to **a single subscription**. Do not reuse the same instance across different subscriptions; create a new subscriber object for each `subscribe` call.

### 2.1. Lifecycle Hooks

| Hook | When Triggered | Example Work |
| --- | --- | --- |
| `hookOnSubscribe(Subscription subscription)` | Source accepts the subscription | Initialize state and issue the first `request(1)` or `request(n)`. |
| `hookOnNext(T value)` | An element is sent downstream by the source | Process the element; request the next element when ready. |
| `hookOnComplete()` | Publisher finishes successfully | Record completion, close related resources. |
| `hookOnError(Throwable error)` | Publisher terminates with an error | Log and handle the error; no `onComplete` follows. |
| `hookOnCancel()` | `BaseSubscriber.cancel()` is called | Handle cancellation initiated by the subscriber. |
| `hookFinally(SignalType signal)` | After completion, error, or cancel | Clean up resources in one shared place; know whether termination was `ON_COMPLETE`, `ON_ERROR`, or `CANCEL`. |

`hookFinally` is invoked additionally, after the corresponding terminal hook. In real applications, override `hookOnError` because the default unhandled-error behavior does not implement your business error policy.

**Subscription lifecycle is distinct from the lifecycle of the Java object holding the source configuration.** A `Flux.range(1, 5)` can serve as a source for A and B, yet A and B each have their own subscription and demand. Cancelling A does not inherently cancel B if B uses an independent cold subscription.

### 2.2. `request(n)` Rules to Remember

- `request(1)` grants permission to emit at most **one new `onNext`** corresponding to that unit of demand; once received, that demand is consumed.
- `request(3)` followed by `request(2)` accumulates to a total demand of 5 if no elements have been received yet. Demand saturates at `Long.MAX_VALUE` instead of overflowing negative.
- `requestUnbounded()` is equivalent to an unbounded request. It does not allocate an array of `Long.MAX_VALUE` elements, but removes the cap on signals the subscriber accepts.
- `request(0)` and `request(-1)` are **not a pause button**: non-positive requests violate Reactive Streams and must signal an error per contract. To pause, refrain from sending new requests after remaining demand is exhausted.
- `cancel()` cancels the subscription relationship and **does not emit `onComplete` merely because it was cancelled**. Asynchronous cancellation may incur delay and does not roll back already-completed side effects.
- Once a subscription has terminated via complete/error/cancel, it cannot be "restarted" by calling `request(n)`; to re-consume a cold publisher, create a new subscriber.

## 3. Concrete Timeline: A and B Request Differently

With the cold publisher `Flux.range(1, 5)`, we can actively drive two subscribers:

```text
Flux.range(1, 5)
  │
  ├── subscribe(A)
  │       ├── hookOnSubscribe -> request(1)
  │       ├── onNext(1)     [0 demand left]
  │       ├── main calls A.request(2)
  │       ├── onNext(2), onNext(3) [0 demand left]
  │       └── main calls A.cancel() -> hookOnCancel
  │
  └── subscribe(B)  (new BaseSubscriber)
          ├── hookOnSubscribe -> request(1)
          ├── onNext(1)
          ├── main calls B.request(4)
          └── onNext(2), onNext(3), onNext(4), onNext(5)
              -> hookOnComplete
```

Here, A and B have **independent progress**: A stops at 3, while B starts from 1 and reads all the way through 5. There is no shared emission cursor causing B to start at 4. This holds for the cold `Flux.range` source and should not be mechanically extrapolated to a hot source emitting continuous events.

If A only asks for `request(1)`, not seeing `onComplete` yet does not mean the system is hung. The source still has elements, but has not been granted further demand. When A calls `cancel()`, not seeing `hookOnComplete` is the expected behavior.

## 4. Runnable Java 17+ Program: Controlling `request` and `cancel`

The example uses **Java 17+**, **Maven**, and **Project Reactor Core 3.8.8**. Create the following two files; Maven needs to download dependencies on the first run.

```text
base-subscriber-demo/
├── pom.xml
└── src/main/java/demo/
    └── BaseSubscriberDemo.java
```

### pom.xml

```xml
<project xmlns="http://maven.apache.org/POM/4.0.0"
         xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
         xsi:schemaLocation="http://maven.apache.org/POM/4.0.0 https://maven.apache.org/xsd/maven-4.0.0.xsd">
    <modelVersion>4.0.0</modelVersion>

    <groupId>demo</groupId>
    <artifactId>base-subscriber-demo</artifactId>
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
                <version>3.14.1</version>
            </plugin>
            <plugin>
                <groupId>org.codehaus.mojo</groupId>
                <artifactId>exec-maven-plugin</artifactId>
                <version>3.5.1</version>
            </plugin>
        </plugins>
    </build>
</project>
```

### src/main/java/demo/BaseSubscriberDemo.java

```java
package demo;

import org.reactivestreams.Subscription;
import reactor.core.publisher.BaseSubscriber;
import reactor.core.publisher.Flux;

public final class BaseSubscriberDemo {
    static final class ManualSubscriber extends BaseSubscriber<Integer> {
        private final String label;

        ManualSubscriber(String label) {
            this.label = label;
        }

        @Override
        protected void hookOnSubscribe(Subscription subscription) {
            System.out.println(label + ": subscribed");
            // Override default unbounded: request only 1 value initially.
            request(1);
        }

        @Override
        protected void hookOnNext(Integer value) {
            System.out.println(label + ": next " + value);
            // Do not request more yet: caller decides when to receive more.
        }

        @Override
        protected void hookOnComplete() {
            System.out.println(label + ": complete");
        }

        @Override
        protected void hookOnError(Throwable error) {
            System.out.println(label + ": error " +
                    error.getClass().getSimpleName());
        }

        @Override
        protected void hookOnCancel() {
            System.out.println(label + ": cancelled");
        }
    }

    public static void main(String[] args) {
        Flux<Integer> source = Flux.range(1, 5);

        ManualSubscriber a = new ManualSubscriber("A");
        source.subscribe(a);
        System.out.println("main: request A +2");
        a.request(2);
        System.out.println("main: cancel A");
        a.cancel();

        ManualSubscriber b = new ManualSubscriber("B");
        source.subscribe(b);
        System.out.println("main: request B +4");
        b.request(4);
    }
}
```

Run in the directory containing `pom.xml`:

```bash
mvn -q compile exec:java -Dexec.mainClass=demo.BaseSubscriberDemo
```

**Program stdout** (excluding Maven's own messages):

```text
A: subscribed
A: next 1
main: request A +2
A: next 2
A: next 3
main: cancel A
A: cancelled
B: subscribed
B: next 1
main: request B +4
B: next 2
B: next 3
B: next 4
B: next 5
B: complete
```

**Step-by-step explanation:**

1. `source.subscribe(a)` invokes A's `hookOnSubscribe`. A prints `subscribed` and calls `request(1)`. Because `Flux.range` is synchronous, A receives `next 1` **before** `subscribe(a)` returns.
2. `a.request(2)` grants exactly two more elements; the source emits 2 and 3. A still does not receive 4 and 5 because no demand remains.
3. `a.cancel()` requests cancellation and invokes `hookOnCancel`. Afterward there is no `A: complete` line; cancel does not mean complete.
4. B is a **new** `ManualSubscriber` that requests one element on its own, so it receives 1. After `b.request(4)`, B receives 2, 3, 4, 5, and `hookOnComplete`.

The example has deterministic output because `range` is a synchronous source without schedulers, timers, or network I/O. With asynchronous publishers, ordering between logs from the controlling thread and logs from the publisher can vary; do not blindly apply this stdout pattern to every source.

## 5. Requesting One Element After Processing: The One-by-One Pattern

We can issue an initial `request(1)` inside `hookOnSubscribe`, then request the next element from `hookOnNext` only after the just-received element has finished processing.

Add file `src/main/java/demo/OneByOneDemo.java` to the same project:

```java
package demo;

import org.reactivestreams.Subscription;
import reactor.core.publisher.BaseSubscriber;
import reactor.core.publisher.Flux;

public final class OneByOneDemo {
    public static void main(String[] args) {
        Flux.range(10, 6).subscribe(new BaseSubscriber<Integer>() {
            private int received;

            @Override
            protected void hookOnSubscribe(Subscription subscription) {
                request(1);
            }

            @Override
            protected void hookOnNext(Integer value) {
                System.out.println("handled " + value);
                received++;
                if (received == 3) {
                    cancel();
                } else {
                    request(1);
                }
            }

            @Override
            protected void hookOnCancel() {
                System.out.println("stopped after " + received);
            }

            @Override
            protected void hookOnError(Throwable error) {
                System.out.println("error: " + error.getMessage());
            }
        });
    }
}
```

Run:

```bash
mvn -q compile exec:java -Dexec.mainClass=demo.OneByOneDemo
```

Stdout:

```text
handled 10
handled 11
handled 12
stopped after 3
```

`Flux.range(10, 6)` has elements `10, 11, 12, 13, 14, 15`. The subscriber only permits receiving the first three elements and then cancels. It does **not** automatically complete because the source still has data at the time of cancellation.

Here, "finished processing" means a short synchronous operation completed before `request(1)` was called. If `hookOnNext` only launches an async task and immediately asks for more, many tasks could still be running in flight even though you think you processed elements one by one. In that case, you must manage task completion and errors or use a pipeline with bounded concurrency, such as `concatMap` or bounded `flatMap`; avoid spawning unmanaged nested `subscribe()` branches.

## 6. Choosing How to Grant Demand Based on Your Goal

| Request Approach | Purpose | Notes |
| --- | --- | --- |
| `request(1)`, then `request(1)` after processing | Per-value control | Suitable when synchronous processing can decide immediately. |
| `request(10)` per batch | Reduce demand-signaling overhead | Need to know when enough of the batch is consumed to grant more. |
| `request(1)` then wait for user signal | Pause/resume a consumer | Do not grant additional demand when pausing; do not call `request(0)`. |
| `requestUnbounded()` | Accept all elements the source can emit | Removes the subscriber-side demand cap. |
| `cancel()` | Stop the subscription relationship | Does not undo already-completed I/O or transactions. |

There is no single optimal `n` for every system. One element at a time can be easy to reason about yet add overhead in complex pipelines; larger batches can help throughput but require sufficient memory and processing capacity to absorb the data.

### 6.1. Be Careful with State and Threads

`BaseSubscriber` is a Java object, and its hooks may run on whichever thread emits the signal; with `Flux.range`, that is usually the thread calling `subscribe` or `request`. With asynchronous sources, hooks may run on a different scheduler/thread. Reactor requires signals to a subscriber to be serialized, but application state variables shared with a UI or multiple controlling threads **are not automatically thread-safe**. When updating counters, stop flags, or queues from multiple threads, use proper synchronization or a single-owner model.

## 7. Demand at the Subscriber Does Not Necessarily Equal Requests at the Source

Operators can change request units or sizes. Therefore, `request(1)` at the final subscriber **does not prove** upstream emits or holds only one object at every layer.

### 7.1. Filtering Elements

With `Flux.range(1, 10).filter(n -> n % 2 == 0)`, the subscriber requests two even numbers. To obtain two retained elements, upstream may have to supply 1, 2, 3, 4. The operator handles discarded elements while maintaining downstream demand. Reading upstream logs may show a request count larger than the number of output elements.

### 7.2. Changing Units with `buffer`

`buffer(5)` turns five source values into **one list** downstream. A single `request(1)` on `Flux<List<T>>` may require five input values. Similarly, `flatMap` can create multiple inner publishers with their own demand and prefetching.

### 7.3. Prefetch and Schedulers

`publishOn` typically uses a queue and a prefetch mechanism to reduce request coordination frequency. You may see upstream logs for a batch before the final subscriber issues corresponding additional requests. This does not automatically prove a publisher violates backpressure; you must know **where in the chain** you are observing demand.

### 7.4. Placing `doOnRequest` in the Right Spot

```java
Flux<Integer> source = Flux.range(1, 5)
        .doOnRequest(n ->
                System.out.println("observed upstream request: " + n));
```

This is an **illustrative snippet**. When this source is subscribed to by a `BaseSubscriber` with no demand-altering operators in between, `request(1)`/`request(2)` calls can be observed directly. Moving `doOnRequest` to the other side of `publishOn`, `buffer`, or `limitRate` makes you observe a different segment of demand. `doOnRequest` only observes requests; it is not an operator that adds demand on its own.

### 7.5. `limitRate` Differs from Manual Requests

```java
Flux<Integer> shaped = Flux.range(1, 100)
        .limitRate(16);
```

This is an **illustrative snippet**. `limitRate(16)` splits large downstream demand into managed request batches; it does not mean "receive only 16 elements in total". To limit the **number of output elements**, use `take(16)`. To limit the **number of concurrent inner tasks**, look at `flatMap`'s concurrency parameter and service characteristics. Operators like `onBackpressureBuffer`/`onBackpressureDrop`/`onBackpressureLatest` are policies for handling fast sources; they are not equivalent to `BaseSubscriber.request(1)`.

## 8. For Hot Sources, Does `request(1)` Stop the Outside World?

Not necessarily. With a cold `Flux.range`, sequence progress is tracked per subscription. With a hot publisher, a sensor, message broker, or event stream can keep producing data even while one subscriber sits at demand 0. Depending on the source and operator, data may be buffered, dropped, signal an overflow error, or follow another policy.

`Flux.interval` is a time-based tick source. If a tick fires when no demand remains, Reactor can signal an overflow error rather than storing every tick waiting for a later `request`. Do not treat `request(1)` as a guarantee that an infinite hot source can accurately replay every event later.

With a multi-subscriber hot source, a slow A and fast B also depend on multicasting, buffering, and replay mechanisms. Each subscriber has its own `Subscription`, yet the shared upstream may enforce a policy affecting the whole system. Clearly decide on source behavior, buffer capacity, overflow handling, and data-loss requirements before implementing.

## 9. Cancellation and Resource Management

`cancel()` expresses that the subscriber needs no more elements. It does not mean `onComplete`; on `BaseSubscriber`, `hookOnCancel` lets you observe the active cancellation branch. `hookFinally(SignalType type)` can perform shared cleanup for complete/error/cancel.

```java
@Override
protected void hookFinally(SignalType type) {
    System.out.println("subscriber terminated with: " + type);
    // Close resources actually owned by the subscriber if needed.
}
```

This is an **illustrative snippet placed inside a `BaseSubscriber` subclass**, requiring `import reactor.core.publisher.SignalType`. When this callback runs, `type` is `ON_COMPLETE`, `ON_ERROR`, or `CANCEL`. Keep in mind that cancelling from downstream does not guarantee stopping in-flight I/O immediately or reversing committed side effects; cancellation can arrive with delay in an asynchronous pipeline.

Use `using`/`usingWhen` or `doFinally` when the **publisher** owns the resource. Do not rely solely on subscriber hooks to clean up resources opened internally by the pipeline, because resource scope and subscriber lifecycle do not necessarily map one-to-one.

## 10. Where to Use `BaseSubscriber` in Applications?

### 10.1. Application-Owned Consumers

`BaseSubscriber` is useful when building your own consumer for a publisher (CLI, observation tool, desktop component, data processor with a "Next" protocol, or a managed background consumer). The component owning the consumer needs to:

- Create a new subscriber for each `subscribe` call.
- Grant initial demand purposefully; ask for more once capacity is available.
- Handle `onError`, `onComplete`, `cancel`, and close resources on shutdown.
- Monitor throughput, latency, buffers, and downstream processing, not just request counts.
- If the consumer must recover after a crash, implement its own checkpoint/acknowledgment mechanism: `BaseSubscriber` itself does not provide durable processing.

Illustrative example using the classes from Section 4:

```java
ManualSubscriber console = new ManualSubscriber("console");
source.subscribe(console);
// When the user presses Next:
console.request(1);
// When the tool closes:
console.dispose();
```

This is an **illustrative snippet**, not a complete console application with UI. Data only continues if the source is still alive and additional demand is granted; after `dispose`, create a new subscriber for a new run.

### 10.2. Spring WebFlux HTTP Already Has an Infrastructure Subscriber

In a WebFlux controller, you typically **return the publisher** for the HTTP infrastructure to consume:

```java
@GetMapping("/items")
public Flux<ItemDto> items() {
    return itemService.findAll()
            .filter(ItemDto::isVisible)
            .limitRate(32);
}
```

This is an **illustrative snippet inside a controller**, requiring `ItemDto`, `itemService`, and `GetMapping` imports. WebFlux and the reactive HTTP server own the response pipeline, including subscribing/consuming, backpressure, writing the body, errors, and cancellation. When you want to shape upstream requests, consider `limitRate`, pagination, prefetch/concurrency limits, and real source capabilities; there is no need to force a `BaseSubscriber` into a controller just to "drive" the response.

Anti-pattern:

```java
@GetMapping("/wrong")
public Flux<ItemDto> wrong() {
    itemService.findAll().subscribe(value -> saveSomewhere(value));
    return Flux.empty();
}
```

This is an **illustrative example of the wrong approach**. The manually `subscribe`d branch is detached from the returned body: the response can finish before saving completes, save errors do not automatically become HTTP errors, and client cancellation does not necessarily stop the detached branch. To keep both operations within the same HTTP lifecycle, compose the publishers using `flatMap`/`then` and return the final chain. To run intentional background work, use a fully application-managed consumer with its own lifecycle and error policy.

### 10.3. `BaseSubscriber` Is Not a Rate Limiter or a Queue

`request(n)` manages demand for **a single subscription**. It does not limit concurrent HTTP requests across the whole server, does not authorize cross-request API calls, does not automatically retry failed messages, does not guarantee durable processing, and does not enforce strict fairness across different subscribers. Those concerns belong to throttling, rate limiting, queues, schedulers, services, or source protocols.

## 11. Testing Backpressure with `StepVerifier`

`reactor-test` provides `StepVerifier` to verify scripted demand and terminal signals. You do not necessarily have to write a new `BaseSubscriber` in every test.

Add the following dependency to `pom.xml` if you need `StepVerifier` in tests:

```xml
<dependency>
    <groupId>io.projectreactor</groupId>
    <artifactId>reactor-test</artifactId>
    <version>3.8.8</version>
    <scope>test</scope>
</dependency>
```

Example **code snippet inside a test method** (requiring `reactor.test.StepVerifier` and `reactor.core.publisher.Flux` imports):

```java
StepVerifier.create(Flux.range(1, 5), 0)
        .thenRequest(1)
        .expectNext(1)
        .thenRequest(2)
        .expectNext(2, 3)
        .thenCancel()
        .verify();
```

`StepVerifier.create(..., 0)` starts with 0 demand. `thenRequest(1)` opens the way for value 1, and `thenRequest(2)` for 2 and 3. The test then explicitly calls `thenCancel`, so `onComplete` is not expected. To test completion, request enough data and use `expectNext(...)`/`verifyComplete()`. To test errors, use `expectError...` and `verify()`.

## 12. Common Mistakes and How to Fix Them

| Mistake | Consequence | How to Fix |
| --- | --- | --- |
| Not overriding `hookOnSubscribe` | `BaseSubscriber` requests unboundedly | Override, initialize needed state, and call `request(n > 0)`. |
| Calling `request(1)` only once | Stream may stop after the first element due to 0 demand | Request more when ready, or explicitly cancel. |
| Using `request(0)` to pause | Protocol violation, may cause errors | Send no new demand when pausing; `cancel` when stopping permanently. |
| Reusing a `BaseSubscriber` instance | Broken subscription lifecycle, unexpected cancellations | Create a new subscriber for each subscribe call. |
| Assuming `request(5)` guarantees five elements | Source may be empty, complete, or error early | Understand request is a maximum receivable bound, not a mandatory element count. |
| Calling `requestUnbounded()` after per-element control | Removes the intended demand cap | Use unbounded only when the consumer intentionally accepts it. |
| Thinking subscriber `request(1)` means every operator holds only one object | Prefetch/buffer/flatMap can alter upstream demand | Observe at the right spot and configure buffers/concurrency separately. |
| Calling `cancel()` and expecting `onComplete` | Cancel is not complete | Use cancel/finally hooks for observation and cleanup. |
| Starting an async task in `hookOnNext` and immediately requesting another element | Unintended multiple tasks still in flight | Coordinate completion or compose with bounded `concatMap`/`flatMap`. |
| `block()` or blocking I/O inside a hook on the event loop | Blocks threads and hurts throughput | Use reactive APIs, offload blocking work with proper configuration. |
| Creating `BaseSubscriber` inside a WebFlux controller | Work detached from HTTP lifecycle; hard to control errors and cancellation | Return the publisher and let WebFlux subscribe; use operators if needed. |
| Assuming a hot source infinitely retains data when demand = 0 | May drop, buffer, or signal overflow | Explicitly define backpressure strategy and replay policy. |

## 13. Self-Check Questions

**Question 1.** `Flux.range(1, 5)` is subscribed to by a `BaseSubscriber` that only calls `request(2)` in `hookOnSubscribe`. No further requests are made. What is the result?  
**Answer:** Receives 1 and 2, then waits. The source still has 3, 4, 5, but no demand has been granted.

**Question 2.** If `request(1)` and then `request(2)` are called afterward, what will this cold source do?  
**Answer:** Emits 3, then 4 and 5, and then completes, assuming it is not cancelled and does not error.

**Question 3.** Why is creating a `BaseSubscriber` without overriding `hookOnSubscribe` not custom backpressure yet?  
**Answer:** Because the default hook requests `Long.MAX_VALUE`. To grant finite demand, you must override it to call an appropriate `request(n)`.

**Question 4.** Does `cancel()` trigger `onComplete`?  
**Answer:** No. It triggers the cancellation path; `hookOnCancel` and `hookFinally(SignalType.CANCEL)` are appropriate for observing cancellation termination.

**Question 5.** Two subscribers A and B independently subscribe to `Flux.range(1, 5)`. A has received 1, 2, 3; which value will B start from?  
**Answer:** B starts from 1 because `range` is a cold publisher with independent progress per subscription.

**Question 6.** Why might an upstream log show requests of 32 or 256 when the subscriber asked for `request(1)`?  
**Answer:** An intermediate operator between the two points may pre-request in batches or change the demand unit (e.g., buffer/prefetch). Check the placement of `doOnRequest` before concluding the pipeline is wrong.

**Question 7.** Should you call `subscribe(new BaseSubscriber...)` inside every WebFlux controller to control the HTTP response?  
**Answer:** Usually no. Controllers should return `Mono`/`Flux`; WebFlux infrastructure manages the subscription, errors, body writing, and cancellation. Shape the pipeline with operators and source policies when needed.

## Key Takeaways

**`BaseSubscriber` helps a consumer actively grant additional demand via `request(n)`.** To genuinely control the pace, you must override `hookOnSubscribe` because the subscriber defaults to requesting unboundedly. When demand runs out, a backpressure-compliant source stops emitting further `onNext` signals to that subscriber; when ready to continue, issue a positive request. `cancel()` stops the subscription rather than generating `onComplete`. Demand can also be reshaped by operators and hot-source policies. For WebFlux HTTP, generally let the framework own the subscriber and return the composed publisher from the controller.

### References

1. [Project Reactor – BaseSubscriber API](https://projectreactor.io/docs/core/release/api/reactor/core/publisher/BaseSubscriber.html) – lifecycle hooks, `request`, `cancel`, `requestUnbounded`.
2. [Project Reactor – Creating and Subscribing to a Flux or Mono](https://projectreactor.io/docs/core/release/reference/coreFeatures/simple-ways-to-create-a-flux-or-mono-and-subscribe-to-it.html) – `BaseSubscriber` and custom requests.
3. [Project Reactor – Backpressure and Ways to Reshape Requests](https://projectreactor.io/docs/core/release/reference/subscribe-backpressure.html) – demand, `limitRate`, prefetch.
4. [Reactive Streams Specification for the JVM](https://github.com/reactive-streams/reactive-streams-jvm) – `Publisher`, `Subscriber`, and `Subscription` contract.
5. [Spring Framework – WebFlux](https://docs.spring.io/spring-framework/reference/web/webflux.html) – HTTP pipeline and reactive responses.

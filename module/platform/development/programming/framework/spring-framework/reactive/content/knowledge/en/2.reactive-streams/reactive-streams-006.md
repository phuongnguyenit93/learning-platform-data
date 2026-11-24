# Multiple Subscriptions and Per-Subscriber State

**Module:** Spring Framework – reactive  
**Parent Topic:** Reactive Streams

## Learning Objectives

After this lesson, you will be able to:

- Explain what happens when calling `subscribe()` multiple times on the same `Publisher`/`Flux`.
- Distinguish shared pipeline objects from per-subscriber `Subscription`, data demand, progress, and state.
- Create per-subscription state using `Flux.defer` or `Flux.generate`; spot bugs caused by mutable variables outside the pipeline.
- Distinguish **cold** and **hot** sources, as well as the effects of `share()`, `cache()`, cancellation, and side effects.
- Predict the output of Reactor examples and choose safe implementations in Spring WebFlux.

## 1. One Publisher, Multiple `subscribe` Calls: What Is Created Fresh?

In Reactive Streams, `Publisher<T>` describes a source, `Subscriber<T>` receives signals, and `Subscription` is the concrete registration relationship between a source and one receiver. Typical protocol for one subscription:

```text
publisher.subscribe(subscriber)
       │
       └── onSubscribe(subscription)
                ├── subscriber calls request(n)  → may receive onNext(value)
                ├── subscriber calls request(m)  → may receive more onNext(value)
                ├── onComplete() OR onError(error) → terminates
                └── cancel() → requests stop, does not emit onComplete just because of cancel
```

`onSubscribe` precedes `onNext`; the number of `onNext` calls must not exceed total requested demand. A stream may send fewer items than requested and terminate. `request(n)` must have `n > 0`; `request(0)` or negative values violate the protocol and must be signaled as an error per Reactive Streams. `cancel()` requests stopping emission and may have propagation delay in asynchronous systems.

You can call `subscribe` multiple times on one `Flux` object. **This does not mean reusing the same `Subscription` or the same `Subscriber` object.** Each accepted subscription has its own control relationship; for Reactor's `BaseSubscriber`, create a new instance for each subscription. The specification allows a `Publisher` to choose whether to support one or multiple subscribers, unicast or multicast; not every source accepts unlimited subscriptions.

Distinguish three layers of state:

| Scope | Example | Isolated by Default? |
| --- | --- | --- |
| **Assembly object** – pipeline created when writing `Flux<Integer> f = ...` | Variables captured from outside, mutable objects held by the application | **No.** Subscriptions can share this exact object. |
| **Per subscription** – when connecting the pipeline to a subscriber | Demand, progress of `range`, `take` operator, completion/cancellation signals, `generate` state supplier | **Usually yes** for cold pipelines; each receiver has its own `Subscription` and operator state. |
| **Underlying data source** | Socket connection, queue, sink, an upstream shared via `share()` | **Depends on source.** May be a shared resource, multicast, or accept only one subscriber. |

Picture a cold `Flux.range(1, 3)` subscribed to by two receivers:

```text
               Flux.range(1, 3)  (same object describing the pipeline)
                    /       \
       subscribe(A)           subscribe(B)
          │                         │
     Subscription A             Subscription B
     demand A, position A       demand B, position B
     [1, 2, 3]                 [1, 2, 3]
```

If A has only requested one item, A receives `1` and pauses waiting for further demand; B can still request all three items and reach `onComplete`. A is not "pushed" to `2` just because B received `2`. This `range` example is a synchronous, finite, cold source; this outcome does not automatically apply to all hot publishers.

## 2. Runnable Example: Independent Demand and Fresh Subscribers

This example uses **Java 17+**, **Maven**, and **Project Reactor Core 3.8.8**. Create the two files below; Java and Maven are required to download dependencies on first run.

`pom.xml`:

```xml
<project xmlns="http://maven.apache.org/POM/4.0.0"
         xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
         xsi:schemaLocation="http://maven.apache.org/POM/4.0.0 https://maven.apache.org/xsd/maven-4.0.0.xsd">
    <modelVersion>4.0.0</modelVersion>
    <groupId>example</groupId>
    <artifactId>subscription-isolation</artifactId>
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

`src/main/java/MultipleSubscriptionsDemo.java`:

```java
import java.util.concurrent.atomic.AtomicInteger;
import org.reactivestreams.Subscription;
import reactor.core.publisher.BaseSubscriber;
import reactor.core.publisher.Flux;

public class MultipleSubscriptionsDemo {
    static final class NamedSubscriber extends BaseSubscriber<Integer> {
        private final String name;

        NamedSubscriber(String name) {
            this.name = name;
        }

        @Override
        protected void hookOnSubscribe(Subscription subscription) {
            System.out.println(name + ": subscribe");
            request(1);
        }

        @Override
        protected void hookOnNext(Integer value) {
            System.out.println(name + ": " + value);
        }

        @Override
        protected void hookOnComplete() {
            System.out.println(name + ": complete");
        }
    }

    public static void main(String[] args) {
        Flux<Integer> numbers = Flux.range(1, 3);
        NamedSubscriber a = new NamedSubscriber("A");
        NamedSubscriber b = new NamedSubscriber("B");

        numbers.subscribe(a);  // A receives 1; no more requested yet
        numbers.subscribe(b);  // B also starts from 1
        a.request(2);          // A receives 2, 3 and completes
        b.request(1);          // B receives 2
        b.request(1);          // B receives 3 and completes

        AtomicInteger shared = new AtomicInteger();
        Flux<Integer> wrong = Flux.range(1, 3)
                .map(ignored -> shared.incrementAndGet());
        System.out.println("Shared A: " + wrong.collectList().block());
        System.out.println("Shared B: " + wrong.collectList().block());

        Flux<Integer> isolated = Flux.defer(() -> {
            AtomicInteger local = new AtomicInteger();
            return Flux.range(1, 3)
                    .map(ignored -> local.incrementAndGet());
        });
        System.out.println("Local A: " + isolated.collectList().block());
        System.out.println("Local B: " + isolated.collectList().block());
    }
}
```

Run from the directory containing `pom.xml`:

```bash
mvn -q compile exec:java -Dexec.mainClass=MultipleSubscriptionsDemo
```

**Program stdout** (no scheduler is used, so the order in this example is deterministic):

```text
A: subscribe
A: 1
B: subscribe
B: 1
A: 2
A: 3
A: complete
B: 2
B: 3
B: complete
Shared A: [1, 2, 3]
Shared B: [4, 5, 6]
Local A: [1, 2, 3]
Local B: [1, 2, 3]
```

**Reading the output:**

1. Both `numbers.subscribe(...)` calls use the same `numbers` variable, yet A and B receive separate `Subscription`s and have separate demand. A completing does not cause B to complete automatically.
2. `collectList().block()` creates a new subscription to collect the result of the cold `Flux`. The `shared` variable was created **outside** the pipeline and shared by both runs, so the counter continues from `4` on the second run.
3. `Flux.defer` invokes the supplier as each subscription happens. Each run creates a fresh `AtomicInteger local`, so both start at `0` and yield `[1, 2, 3]`. `AtomicInteger` in the buggy example is still safe with respect to concurrent increments, yet **wrong on state boundaries**: thread-safe does not mean subscription-isolated.
4. `BaseSubscriber` provides `request(n)`/`cancel()` and lifecycle hooks. This object is designed for one subscription; reusing instance `a` for another subscription is a modeling bug.

## 3. How to Isolate State in the Right Place

### 3.1. `defer`: Creating Objects or Side Effects at Subscription Time

When state, a request ID, a connection, a computation, or a data source must be fresh per subscription, place its creation **inside** the supplier:

```java
Flux<Integer> perSubscription = Flux.defer(() -> {
    AtomicInteger count = new AtomicInteger();
    return Flux.range(10, 12)
               .map(value -> count.incrementAndGet());
});
```

This is an **illustrative snippet**, using the imports from the program above. On every subscribe, a new `count` is created. `Flux.range(10, 12)` emits 12 items starting from 10, while `map` here turns them into a `1..12` counter. `defer` does not automatically make an external source unshared; if the supplier returns the same hot publisher or the same mutable resource, state can still be shared.

Distinguish execution timing:

```java
Flux<String> captured = Flux.just(fetchValue()); // fetchValue() runs immediately at assembly time
Flux<String> deferred = Flux.defer(
        () -> Flux.just(fetchValue()));          // fetchValue() runs on each subscribe
```

This is an illustrative snippet, assuming `fetchValue()` is defined by the application and returns `String`. `just` captures the already-computed value; every subscriber receives that captured value. What matters is **when the value is created**, not merely the number of subscribers. For asynchronous I/O, prefer reactive APIs returning `Mono`/`Flux` rather than wrapping uncontrolled blocking calls.

### 3.2. `generate`: A Dedicated State Machine per Receiver

`Flux.generate(stateSupplier, generator)` has a state supplier called for **each subscription**. Self-contained logic example:

```java
Flux<Integer> sequence = Flux.<Integer, Integer>generate(
    () -> 1,
    (state, sink) -> {
        sink.next(state);
        if (state == 3) {
            sink.complete();
        }
        return state + 1;
    }
);
// Each sequence.collectList().block() returns [1, 2, 3].
```

The `state` of run A and run B do not mix. With `generate`, each generator invocation emits **at most one `onNext`** via `SynchronousSink`; the source obeys demand and cannot push past the receiver's capacity. Use `generate` when items are computed sequentially from state, and `defer` when you need to construct a pipeline or objects per subscription.

### 3.3. `Context`: Data Attached to a Subscription Flowing Through Operators

In an asynchronous Reactor chain, do not use `ThreadLocal` to store a request ID or user info across the pipeline: operators can switch threads. Reactor `Context` is bound to a subscription, is immutable, and propagates with the chain's context.

```java
import reactor.core.publisher.Mono;
import reactor.util.context.Context;

Mono<String> label = Mono.deferContextual(context ->
        Mono.just(context.getOrDefault("requestId", "unknown")));

System.out.println(label.contextWrite(Context.of("requestId", "REQ-A")).block());
System.out.println(label.contextWrite(Context.of("requestId", "REQ-B")).block());
```

This is a Java snippet placed **inside a method** (with the imports at the top of the file); output is `REQ-A`, then `REQ-B`. `contextWrite` supplies context to upstream operators and each `block()` here creates a new subscription. `Context` is suitable for metadata, tracing, and correlation; it should not be used to hold arbitrary mutable business state.

## 4. What Do Cold and Hot Change When Subscribing Multiple Times?

| Criterion | Cold Publisher | Hot/Shared Publisher |
| --- | --- | --- |
| Data generation | Usually created/read anew per subscription | Can share a single running upstream |
| Late subscriber | Usually starts from the initial logic | May receive only new items, unless replay/cache is used |
| Resources and side effects | Can repeat on every subscribe | Can be shared; depends on operators and connection lifecycle |
| Demand/cancel | Subscription relationships remain separate | Separate subscription relationships, while shared upstream has coordination policy |
| Reactor examples | `Flux.range`, `Flux.defer` | `share()`, a multicast `Sinks.Many`, `replay`/`cache` with replay rules |

**There is no rule that "same Flux = same running data."** A `Flux` is only an object describing a processing chain, and the source type determines semantics:

- `Flux.range(1, 3)` is cold: each subscriber receives `1, 2, 3` if it requests enough.
- `Flux.just(x)` captures `x` at assembly time and replays this value for subscriptions; if computing `x` has side effects, those side effects happen before subscribe.
- `source.share()` multicasts signals from a shared upstream while connected. Late subscribers may miss earlier items; when the last receiver leaves, the upstream connection may be cancelled via reference counting.
- `source.cache()` retains signals to replay according to cache configuration; convenient for avoiding recomputation, at the cost of memory, lifecycle, and data freshness. Do not blindly apply `cache()` to user-specific or authorization-sensitive data without explicitly choosing cache scope.
- `Sinks.many().multicast()` suits event streams pushed to multiple subscribers; `Sinks.many().unicast()` allows only one receiver. `Sinks.many().replay()` can replay history according to the chosen policy. Always check the buffering, backpressure, and late-subscriber behavior of each sink variant.

**Reasoning example:** Create `Flux<Integer> f = Flux.range(1, 3)`, call `f.subscribe(A)` and then `f.subscribe(B)`: both A and B can receive all three numbers. However, with `Flux.interval(...).share()`, if B subscribes after upstream has already emitted the first number, you cannot assume B will receive that first number again. Hot outcomes depend on subscription timing, connection state, demand, and replay.

## 5. Cancellation, Errors, Resources, and Backpressure

- **Independent cancellation:** if A calls `cancel()`, A asks to stop receiving; B can continue if the source supports multiple subscribers and the shared upstream is still needed. `cancel` itself does not emit `onComplete` to A, nor does it guarantee immediately halting every scheduled task.
- **Independent termination:** finite cold sources typically emit `onComplete` per subscription. An error in one pipeline does not automatically error another pipeline, unless they share a failing source or common terminal policy.
- **Resource cleanup:** per-subscription resources should be opened and closed according to that subscription's lifecycle (consider `Flux.using`/`usingWhen`, `doFinally`). With a shared upstream, connection lifecycle may depend on the count of active subscribers.
- **Independent backpressure:** each subscriber sends `request(n)` via its own `Subscription`. In a multi-operator pipeline, `prefetch`, `buffer`, `flatMap`, `publishOn`, and other operators can alter upstream requests, so the request count logged at one stage does not necessarily match downstream item-by-item demand.
- **No absolute fairness guarantee:** a shared hot source must define a policy for slow subscribers. It may buffer, drop, error, block, or apply another strategy depending on configuration; do not infer "if A is slow, B is always unaffected."

In the `Flux.range` example, when A only calls `request(1)`, do not expect `onComplete` immediately: the source still has items, yet A has not requested more. Without increasing demand or cancelling, the subscription can stay waiting. Conversely, common Reactor `subscribe(value -> ...)` forms usually request `Long.MAX_VALUE`, which is why the controlled-demand example used `BaseSubscriber`.

## 6. Connection to Spring WebFlux

A WebFlux handler normally **returns** `Mono`/`Flux` and lets the framework manage subscription, demand, and cancellation when the client disconnects:

```java
@GetMapping("/items")
public Flux<ItemDto> items() {
    return itemService.findItems();
}
```

This is an **illustrative snippet in a Spring controller**: `ItemDto`, `itemService`, and the `@GetMapping` import must be defined by the application. Do not place a manual `subscribe()` inside the handler just to "trigger" the chain and return something else: it easily leaves tasks running outside the HTTP lifecycle and makes error propagation and cancellation hard. Return the publisher to the framework; use `map`, `flatMap`, `then`, etc., to compose processing.

If code reuses the same cold publisher for two requests or two consumers, each subscription **may repeat** database queries, HTTP calls, or side effects. To avoid recomputation, choose a sharing/caching mechanism with a valid scope and appropriate expiration policy; never assume all data is safe to share/cache globally. For request IDs and HTTP request-specific metadata, use Reactor `Context` when propagating across asynchronous pipelines.

## 7. Common Mistakes and Fixes

| Symptom | Cause | Resolution |
| --- | --- | --- |
| B receives counter continuing after A (`4, 5, 6` instead of `1, 2, 3`) | Mutable variable captured outside the chain | Create state inside `defer` or `generate` state supplier. |
| Assuming B receives data automatically because A requested | Confusing per-`Subscription` demand with shared demand | Track request/cancel for each subscriber individually. |
| Reusing a single `BaseSubscriber` object | Instance holds the current subscription and is not designed for reuse | Create a new subscriber instance for each subscribe call. |
| Requests sent but no new values seen | Insufficient demand, source has no data yet, or hot/backpressure strategy | Observe `doOnRequest`, lifecycle, source, and operators; do not guess from the high-level pipeline. |
| Data differs between two runs | Hot source, changing external source, nondeterminism, or side effects | Clarify cold/hot, subscribe timing, and replay policy. |
| API/database called twice | Two subscriptions to a cold source | Subscribe only at the true boundary; consider intentional sharing if needed. |
| Cancel on one client affects another connection | Shared source and lifecycle governed by `refCount`/upstream policy | Choose appropriate sharing mode, subscriber count, and resource scope. |
| Request metadata mixed across requests | Shared mutable state or `ThreadLocal` in async processing | Create per-subscription state; use `Context` for metadata. |

## 8. Self-Check

**Scenario A.** `Flux<Integer> x = Flux.range(1, 3);` After the first subscriber receives all three values, a second subscriber subscribes and requests three values. What does B receive?  
**Answer:** For this cold source, B also receives `1, 2, 3`. A's subscription does not drain B's source.

**Scenario B.** An `AtomicInteger` is declared outside `Flux.range(...).map(...)`. Two subscriptions increment the same counter. Is that per-subscription state?  
**Answer:** No. That is shared state in a closure; use `Flux.defer` to create a new counter inside the supplier for isolation.

**Scenario C.** A calls `cancel()` while B is still subscribed to a hot `share()`. Is upstream guaranteed to be cancelled?  
**Answer:** No. Under subscriber-count sharing, upstream may remain active because B still needs data. Details depend on the sharing operator and underlying source.

## Key Takeaways

**One publisher can be subscribed to multiple times; each accepted subscription has its own demand/cancellation protocol.** With cold sources, computation progress and state created properly at subscribe time are typically isolated. However, mutable variables captured outside the pipeline, hot connections, sinks, and caches can be shared. Design according to the true scope of state and source lifecycle rather than assuming every `subscribe` automatically isolates everything.

### References

- [Reactive Streams Specification for the JVM](https://github.com/reactive-streams/reactive-streams-jvm) – `Publisher`, `Subscriber`, and `Subscription` contracts.
- [Project Reactor – Hot Versus Cold](https://projectreactor.io/docs/core/release/reference/advancedFeatures/reactor-hotCold.html) – cold/hot behavior, `defer`, and `share`.
- [Project Reactor – On Backpressure and Ways to Reshape Requests](https://projectreactor.io/docs/core/release/reference/subscribe-backpressure.html) – demand, `BaseSubscriber`, and upstream requests.

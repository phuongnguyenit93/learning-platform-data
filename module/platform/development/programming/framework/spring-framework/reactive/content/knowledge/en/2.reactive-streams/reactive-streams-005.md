# Serial Signaling Within a Subscription (Reactive Streams)

## 1. Purpose and Scope

When a `Publisher` connects to a `Subscriber`, the two sides exchange data over a specific `Subscription`. "Serial signaling" is the contract governing **the order and non-concurrency of callbacks that the Publisher sends to the Subscriber within that subscription**, even when the system uses multiple threads.

After this lesson, you should be able to distinguish: (1) valid signal sequences; (2) why multiple threads may still participate while not invoking callbacks concurrently on a single Subscriber; (3) the relationship between serial signaling, backpressure, unsubscribing, and item ordering; (4) how to observe or fix violations in Spring WebFlux / Project Reactor.

The four callbacks along the data direction are `onSubscribe(Subscription)`, `onNext(T)`, `onError(Throwable)`, and `onComplete()`. `request(n)` and `cancel()` are control operations in the reverse direction (Subscriber → Subscription); they affect the lifecycle but **are not counted as `onNext` or terminal signals**.

## 2. Valid Signal Protocol

General rule of Reactive Streams:

~~~text
onSubscribe → onNext* → (onError | onComplete)?
~~~

The `*` symbol means zero, one, or many times; `?` means a terminal signal may not have appeared yet (stream still alive, cancelled, or not yet finished). An active subscription receives `onSubscribe` before any data callback; each `onNext` carries exactly one item; if the stream finishes naturally it emits `onComplete`, and if it fails it emits `onError`. The two terminal types are mutually exclusive and **no callback may be emitted after a terminal signal**.

Valid examples:

~~~text
onSubscribe → onComplete                              (empty stream)
onSubscribe → onNext(A) → onNext(B) → onComplete        (success)
onSubscribe → onNext(A) → onError(cause)               (failure)
onSubscribe → onNext(A) → ...                          (stream still open)
onSubscribe → onNext(A) → [Subscriber calls cancel]    (may have no terminal)
~~~

Invalid examples and reasons:

| Sequence or Scenario | Violation |
| --- | --- |
| `onNext(A) → onSubscribe` | Data appears before a subscription exists. |
| `onSubscribe → onComplete → onNext(A)` | Emitting data after completion. |
| `onSubscribe → onError(e) → onComplete` | Two terminal signals for the same subscription. |
| `onSubscribe → onNext(A) → onComplete → onComplete` | Duplicate terminal signal. |
| Thread 1 is sending `onNext(A)` while Thread 2 concurrently sends `onNext(B)` to the same Subscriber | Callbacks are not serialized. |

A subscription has **at most one terminal signal**. If `cancel()` is called, the producer must *eventually* stop sending signals; do not assume cancellation instantaneously removes all callbacks already queued or in flight. For continuously running streams, not having received a terminal signal yet is not an error in itself.

## 3. What Does "Serial" Mean Exactly?

Reactive Streams rule **Publisher 1.3** requires `onSubscribe`, `onNext`, `onError`, and `onComplete` to be signaled *serially*. On the JVM, this means there must be a proper **happens-before** relationship between calls and two threads must never concurrently enter callbacks for **the same subscription**. `happens-before` guarantees both observed ordering and visibility of memory writes across stages.

~~~text
Valid:   Thread A: onNext(1) ── finishes/hands off ──► Thread B: onNext(2)
Invalid: Thread A: onNext(1) ───────────────┐
         Thread B:       onNext(2) ─────────┘   (overlapping)
~~~

There is no requirement that all callbacks run on **the same thread**. A Publisher may switch from thread A to thread B using a queue, lock, or atomic mechanism, as long as ordering and happens-before are preserved. Calling `request(1)` inside `onSubscribe`/`onNext` sometimes triggers a synchronous source; therefore, a Subscriber must be written safely for callbacks invoked in the context of `request`, and a Subscription must guard against recursion causing stack overflow. Do not assume a callback is always on a different thread or that calling `request` always waits asynchronously.

**The scope is per subscription.** Two different Subscribers or two independent branches can operate concurrently; the contract does not force the entire application onto one thread. When multiple sources are merged, items may interleave by arrival time, but callbacks sent to **a single downstream Subscriber** must still be serialized.

Also distinguish:

- **Callback serialization:** no two `onNext`/terminal calls to the same Subscriber execute concurrently.
- **Preserving input item order:** e.g., A before B still emits A before B after processing. This is a property of specific sources/operators; `flatMap` may reorder items because inner publishers finish at different times.
- **Synchronous execution:** everything running on one thread, which is not necessarily required by Reactive Streams.

## 4. Backpressure, `request`, and `cancel` Within the Same Subscription

After `onSubscribe(subscription)`, the Subscriber calls `subscription.request(n)` with `n > 0` to grant demand. Total emitted `onNext` signals **must never exceed total demand received** (Publisher 1.1). Demand is cumulative: `request(2)` followed by `request(1)` allows up to three items, minus those already emitted. A Publisher is allowed to emit **fewer** than requested and terminate. `onComplete` or `onError` may arrive even before `request` is called (for example, an empty source or immediate failure).

~~~text
Subscriber                     Publisher
   |                              |
   |<---- onSubscribe(s) ---------|
   |---- s.request(2) ----------->|
   |<---- onNext(A) --------------|
   |<---- onNext(B) --------------|
   |      (cannot emit C until    |
   |       more demand arrives)   |
   |---- s.request(1) ----------->|
   |<---- onNext(C) --------------|
   |<---- onComplete() -----------|
~~~

Per Subscription 3.9, `request(0)` or a negative number while the subscription is not cancelled is invalid: the Subscription must signal `onError(IllegalArgumentException)` per the contract, and must not silently treat it as a request for "0 items." `request`/`cancel` are Subscriber operations; when invoking them from multiple threads, the Subscriber must ensure calls are synchronized per rule 2.7. Once terminated, treat the subscription as cancelled and emit no further signals. `cancel()` requests stopping *eventually*; an `onNext` already scheduled may still arrive during the transition.

Serial signaling and backpressure solve two different problems: **non-overlapping callbacks** and **item count not exceeding demand**. Satisfying the first condition does not suffice for the second, and vice versa.

## 5. Standalone Runnable Java 17+ Example: Observing Ordering

Java's `java.util.concurrent.Flow` uses a protocol equivalent to Reactive Streams in the JDK. The following example requires no extra libraries. `SubmissionPublisher` emits asynchronously, while the Subscriber requests one item at a time so you can see the boundary between `request` and callbacks.

Create `SerialSignalsDemo.java`:

~~~java
import java.util.concurrent.CountDownLatch;
import java.util.concurrent.Flow;
import java.util.concurrent.SubmissionPublisher;

public class SerialSignalsDemo {
    public static void main(String[] args) throws InterruptedException {
        CountDownLatch finished = new CountDownLatch(1);

        try (SubmissionPublisher<Integer> publisher = new SubmissionPublisher<>()) {
            publisher.subscribe(new Flow.Subscriber<>() {
                private Flow.Subscription subscription;

                @Override
                public void onSubscribe(Flow.Subscription s) {
                    subscription = s;
                    System.out.println("onSubscribe");
                    s.request(1);
                }

                @Override
                public void onNext(Integer value) {
                    System.out.println("onNext(" + value + ")");
                    subscription.request(1);
                }

                @Override
                public void onError(Throwable error) {
                    System.out.println("onError: " + error.getMessage());
                    finished.countDown();
                }

                @Override
                public void onComplete() {
                    System.out.println("onComplete");
                    finished.countDown();
                }
            });

            publisher.submit(10);
            publisher.submit(20);
            publisher.submit(30);
        } // close() requests emitting terminal after pending items
        finished.await(); // wait for callbacks to finish before exiting main
    }
}
~~~

Compile and run with JDK 17 or later:

~~~bash
javac --release 17 SerialSignalsDemo.java
java SerialSignalsDemo
~~~

Stdout output of a successful run:

~~~text
onSubscribe
onNext(10)
onNext(20)
onNext(30)
onComplete
~~~

`SubmissionPublisher` may run callbacks on a background thread, yet for a single Subscriber the order above still holds. Do not use the print order across **multiple Subscribers** to infer a global schedule. `CountDownLatch` is only there so `main` does not exit before the terminal callback finishes.

## 6. Applying in Spring WebFlux with Project Reactor

Spring WebFlux typically uses Reactor's `Flux<T>` and `Mono<T>`. They conform to the Reactive Streams Publisher/Subscriber contract; `Mono` has at most one `onNext`, while `Flux` can have many. In a project that already has `spring-boot-starter-webflux`, run the following class via your IDE or corresponding Java run configuration:

~~~java
import org.reactivestreams.Subscription;
import reactor.core.publisher.BaseSubscriber;
import reactor.core.publisher.Flux;

public class ReactorSerialSignalsDemo {
    public static void main(String[] args) {
        Flux.just("A", "B").subscribe(new BaseSubscriber<String>() {
            @Override
            protected void hookOnSubscribe(Subscription subscription) {
                System.out.println("onSubscribe");
                request(1);
            }

            @Override
            protected void hookOnNext(String value) {
                System.out.println("onNext(" + value + ")");
                request(1);
            }

            @Override
            protected void hookOnComplete() {
                System.out.println("onComplete");
            }

            @Override
            protected void hookOnError(Throwable error) {
                System.out.println("onError: " + error.getMessage());
            }
        });
    }
}
~~~

Stdout with a successful `Flux.just` source:

~~~text
onSubscribe
onNext(A)
onNext(B)
onComplete
~~~

Here `BaseSubscriber` routes `onSubscribe`/`onNext`/terminal signals into the corresponding hooks; `request(1)` permits receiving one item per turn. Reactor handles serial emission for the `Flux.just` source. This snippet is a **Reactor program with library dependencies**; the JDK example in section 5 is the one that runs with standard `javac`/`java` alone.

In a pipeline such as `Flux.just(...).publishOn(scheduler).map(...).subscribe(...)`, `publishOn` can switch the downstream execution thread without allowing two downstream signals to overlap. `flatMap` lets inner sources run concurrently and may **interleave/reorder** items; if business logic needs to preserve the original source order, consider `concatMap` (processes inner publishers sequentially) or `flatMapSequential` (runs inner publishers concurrently while preserving emission order). Do not confuse business ordering requirements with the callback serialization rule.

When multiple threads push data into a `Sinks.Many`, avoid having them emit directly and concurrently without coordination. Reactor's `tryEmitNext` API may return `Sinks.EmitResult.FAIL_NON_SERIALIZED` under contended emission, or `FAIL_TERMINATED` once the source has terminated. A proper design usually coordinates through a single queue/emitter, or uses Reactor's controlled retry/emission handler mechanism; **never ignore an error result and assume the item was delivered**.

## 7. Identifying and Debugging Violations

1. **Emitting `onNext` from multiple callbacks/threads into the same Subscriber:** risks overlapping execution and Subscriber state races. Fix at the source by routing emissions through a serialization mechanism (queue + drain, lock, or appropriate Reactor API); merely adding `synchronized` arbitrarily on the consumer side can mask bugs and does not resolve demand/terminal issues.
2. **Sending `onNext` after `onComplete`/`onError`:** the source lacks an atomic terminal state or asynchronous tasks are still emitting late. Gate emissions with a unified state machine, stop/discard remaining tasks, and report errors at the right moment.
3. **Emitting more than `request(n)`:** callback ordering may be completely valid yet still violate backpressure. Track total `requested`, total `emitted`, queues, and `request` flow through operators.
4. **Assuming `cancel()` must instantaneously block every callback:** handle races with in-flight signals and make cleanup idempotent; the contract only requires stopping eventually.
5. **Assuming `flatMap` breaks serialization because results arrive out of order:** check whether callbacks actually overlap or whether items from inner publishers are simply interleaved. If only item ordering is needed, change the operator rather than locking the entire Subscriber.

To observe in Reactor, insert `.log("signals")` on a `Flux` or `Mono` where you want to inspect: the log includes `onSubscribe`, `request`, `onNext`, `onComplete`/`onError`, and `cancel` depending on the flow. You can also use `doOnSubscribe`, `doOnNext`, `doOnError`, `doOnComplete`, and `doFinally`; note that `doFinally` is a Reactor lifecycle hook, not a fifth callback in the Reactive Streams protocol. Logs from multiple subscriptions can interleave, so attach a subscription identifier when diagnosing.

When **implementing a custom** Publisher/Subscription instead of using standard operators, test at least: empty source; multiple `onNext` calls then complete; error before/after data; incremental `request(1)`; `request(0)`; `cancel` while signals are pending; two competing emitters; and verifying no callbacks after terminal. The Reactive Streams TCK is useful for verifying protocol compliance.

## 8. Self-Check

- `onSubscribe → onNext(1) → onError(e)`: valid if demand existed for item 1 and no callbacks follow the error.
- `onSubscribe → onComplete` without `request`: **valid** for an empty stream.
- Thread A finishes emitting `onNext(1)`, then Thread B emits `onNext(2)` after proper synchronization: **valid** despite different threads.
- Thread A and B simultaneously call `onNext` on one Subscriber: **violates serial signaling**, even if total demand is sufficient.
- `flatMap` returns result B before A while callbacks are serialized: **does not violate 1.3**; if A must precede B, choose an order-preserving operator.

**Key takeaway:** Each subscription has one signal lane following `onSubscribe → onNext* → (onError | onComplete)?`. The Publisher must emit these callbacks serially, respect demand, and stop after a terminal signal. Source concurrency or thread switching does not remove that obligation.

## References

- [Reactive Streams for the JVM — API protocol and rules Publisher 1.1–1.8, Subscriber 2.7–2.10, Subscription 3.9](https://github.com/reactive-streams/reactive-streams-jvm#readme).
- [Project Reactor — `Flux` Javadoc, `flatMap` / `concatMap` / `flatMapSequential`](https://projectreactor.io/docs/core/release/api/reactor/core/publisher/Flux.html).
- [Project Reactor — `Sinks.EmitResult` and contention/terminal states](https://projectreactor.io/docs/core/release/api/reactor/core/publisher/Sinks.EmitResult.html).

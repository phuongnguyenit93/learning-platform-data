# Sequence of onSubscribe, onNext, onError, and onComplete in Reactive Streams

## 1. Purpose and Context

Reactive Streams specifies how a **Publisher** (producer) sends data asynchronously to a **Subscriber** (receiver), with receiving pace controlled via **backpressure**. In Spring WebFlux, Reactor (**Flux**, **Mono**) implements this model. To read logs, write a Subscriber, or handle errors correctly, you need to understand the order of the four callbacks:

- **onSubscribe(Subscription)**: establishes control over the data stream.
- **onNext(T)**: delivers one data item.
- **onError(Throwable)**: notifies that the stream failed and terminated.
- **onComplete()**: notifies that the stream completed successfully and terminated.

These four callbacks are **signals sent to the Subscriber**. The two operations **Subscription.request(n)** and **Subscription.cancel()** travel in the opposite direction, from Subscriber to Publisher; they control receiving demand and unsubscribing.

## 2. Ordering Protocol: One Start, Zero or More Items, At Most One Termination

A valid callback sequence is described by the expression:

~~~text
onSubscribe → onNext* → (onError | onComplete)?
~~~

Meaning of the symbols:

- **onSubscribe** arrives before any other callback and is called at most once per Subscriber.
- The **\*** means there can be 0, 1, or many **onNext** calls; each carries exactly one item.
- The **|** means a stream terminates with **onError** *or* **onComplete**, never both.
- The **?** means that at a given point of observation, a terminal signal may not have occurred yet: the stream is still active, is infinite, or was cancelled via **cancel()**. If a finite source completes normally, it must emit **onComplete**; if the source fails, it must report **onError**.

Common paths:

~~~text
Success with data:
onSubscribe → onNext(A) → onNext(B) → onComplete

Empty source:
onSubscribe → onComplete

Error before any data:
onSubscribe → onError(error)

Error mid-stream:
onSubscribe → onNext(A) → onError(error)

Cancelled while running:
onSubscribe → onNext(A) → cancel()
(there may be no onComplete/onError; in-flight signals may still arrive)
~~~

**Invalid:** calling **onNext** before **onSubscribe**; calling **onComplete** followed by **onError**; calling **onNext** after a terminal signal; sending two terminal signals; emitting two **onSubscribe** calls to the same Subscriber; or emitting **onNext** beyond the requested demand.

## 3. Meaning of Each Callback

| Callback | When does it appear? | What should the Subscriber do? | What can follow the callback? |
| --- | --- | --- | --- |
| **onSubscribe(Subscription s)** | Start of the subscription, before any other callback | Store the Subscription; call **s.request(n)** with **n > 0** when ready to receive; or **s.cancel()** if not needed | May continue with **onNext**, **onError**, **onComplete** |
| **onNext(T item)** | An item is ready **and** demand remains | Process the item; request more when able to handle them | More **onNext** calls or a terminal signal |
| **onError(Throwable error)** | Publisher/Subscription encounters an unrecoverable error | Log, report error, clean up Subscriber-owned resources | **Terminated**; no further callbacks on the same Subscription |
| **onComplete()** | Finite source finishes emitting data and completes successfully | Finalize processing, clean up Subscriber-owned resources | **Terminated**; no further callbacks on the same Subscription |

**onSubscribe** is a callback invoked by the Publisher upon subscription; it is distinct from the user's **publisher.subscribe(subscriber)** call. The **Subscription** object is passed to the callback, not returned from **subscribe**.

**onNext** does not mean "the Publisher pushes immediately whenever it has data": the Publisher may emit at most the number of items the Subscriber has requested. By the Reactive Streams contract, emitted item values must not be **null**; represent a stream with no items by an empty completion.

**onError** and **onComplete** are called **terminal signals**. Both end the current Subscription; there is no need to call **cancel()** after receiving a terminal signal. They also do not need to wait for additional **request(n)** demand to be emitted.

## 4. Backpressure and Real-World Observed Order

After receiving **onSubscribe(s)**, the Subscriber signals capacity using **s.request(n)**:

1. **request(2)** permits at most two additional **onNext** calls, not a guarantee that two items will definitely arrive.
2. Each **onNext** received fulfills one unit of demand. Additional **request(1)** or **request(k)** calls can be made to increase unfulfilled demand.
3. The Publisher must not emit **onNext** if total emitted items would exceed total requested demand. It may still emit **onComplete** or **onError** even when no requests have been made.
4. **request(0)** or **request(negative)** is invalid; the Subscription must signal **onError** with **IllegalArgumentException**. Passing **Long.MAX_VALUE** generally signifies effectively unbounded demand.
5. **cancel()** asks the source to *eventually* stop emitting and release resources; it does not guarantee immediately blocking signals already in flight and does not itself generate **onComplete**.

Example of receiving demand:

~~~text
Subscriber                         Publisher
    | -------- subscribe() ---------> |
    | <------- onSubscribe(s) ------- |
    | -------- s.request(2) --------> |
    | <--------- onNext(A) ---------- |
    | <--------- onNext(B) ---------- |
    |    (no remaining onNext demand) |
    | -------- s.request(1) --------> |
    | <--------- onNext(C) ---------- |
    | <-------- onComplete() -------- |
    |     (no further signals)        |
~~~

In the example above, if the Publisher fails before item C, it can send **onError** instead of C and **onComplete**. For an infinite stream where the Subscriber requests no more items, the stream can remain waiting rather than automatically completing.

## 5. Java 17+: Runnable Program Using the JDK Flow API

Java provides **java.util.concurrent.Flow** with roles and callbacks corresponding to Reactive Streams. The example uses **SubmissionPublisher** to illustrate two independent paths: successful completion and error termination. **CountDownLatch** keeps the program waiting for asynchronous callbacks before printing the next scenario.

Save as **SignalSequenceDemo.java**:

~~~java
import java.util.concurrent.CountDownLatch;
import java.util.concurrent.Flow;
import java.util.concurrent.SubmissionPublisher;

public class SignalSequenceDemo {
    static final class PrintSubscriber implements Flow.Subscriber<Integer> {
        private final CountDownLatch finished = new CountDownLatch(1);
        private Flow.Subscription subscription;

        @Override
        public void onSubscribe(Flow.Subscription subscription) {
            this.subscription = subscription;
            System.out.println("onSubscribe");
            subscription.request(1);
        }

        @Override
        public void onNext(Integer item) {
            System.out.println("onNext(" + item + ")");
            subscription.request(1);
        }

        @Override
        public void onError(Throwable error) {
            System.out.println(
                "onError(" + error.getClass().getSimpleName()
                + ": " + error.getMessage() + ")"
            );
            finished.countDown();
        }

        @Override
        public void onComplete() {
            System.out.println("onComplete");
            finished.countDown();
        }

        void awaitTermination() throws InterruptedException {
            finished.await();
        }
    }

    static void successfulStream() throws InterruptedException {
        System.out.println("=== Success ===");
        try (SubmissionPublisher<Integer> publisher =
                 new SubmissionPublisher<>()) {
            PrintSubscriber subscriber = new PrintSubscriber();
            publisher.subscribe(subscriber);
            publisher.submit(10);
            publisher.submit(20);
            publisher.close();
            subscriber.awaitTermination();
        }
    }

    static void failedStream() throws InterruptedException {
        System.out.println("=== Error ===");
        try (SubmissionPublisher<Integer> publisher =
                 new SubmissionPublisher<>()) {
            PrintSubscriber subscriber = new PrintSubscriber();
            publisher.subscribe(subscriber);
            publisher.closeExceptionally(
                new IllegalStateException("source failed")
            );
            subscriber.awaitTermination();
        }
    }

    public static void main(String[] args) throws InterruptedException {
        successfulStream();
        failedStream();
    }
}
~~~

Compile and run with no libraries outside the JDK:

~~~bash
javac SignalSequenceDemo.java
java SignalSequenceDemo
~~~

Program stdout result:

~~~text
=== Success ===
onSubscribe
onNext(10)
onNext(20)
onComplete
=== Error ===
onSubscribe
onError(IllegalStateException: source failed)
~~~

Reading the code in sequence:

- **publisher.subscribe(subscriber)** registers the receiver; each subscription creates its own Subscription.
- **onSubscribe** saves the Subscription and requests one item. After each **onNext** completes processing, the Subscriber requests one more item.
- **submit(10)** and **submit(20)** feed items into the Publisher; **close()** indicates the source is exhausted, so the success path receives **onComplete** after the items.
- On the error path, **closeExceptionally(...)** emits **onError** and does not emit **onComplete**.
- **awaitTermination()** only serves to wait for the example's output: callbacks may run on another thread; guaranteeing signal ordering for one Subscriber does not mean every callback must run on the same thread.

Note: **Flow** is the standard JDK API expressing the same protocol concepts. In Spring WebFlux, the commonly used API is **org.reactivestreams.Publisher/Subscriber/Subscription** via Project Reactor; do not mix the two type sets directly without an appropriate adapter.

## 6. Connection with Reactor and Spring WebFlux

The snippet below is for a project that **already includes reactor-core**, such as a Spring WebFlux application. This is an illustrative snippet using **Flux**, not a standalone Java file:

~~~java
Flux.just(10, 20)
    .doOnSubscribe(s -> System.out.println("onSubscribe"))
    .doOnNext(x -> System.out.println("onNext(" + x + ")"))
    .doOnError(e -> System.out.println("onError: " + e.getMessage()))
    .doOnComplete(() -> System.out.println("onComplete"))
    .subscribe();
~~~

With **Flux.just(10, 20)** as the source, the default subscriber of the **subscribe()** overload requests data and observes the success sequence. If you change the source to **Flux.error(new IllegalStateException("source failed"))**, the stream will emit **onError** instead of **onComplete**; when subscribing to a stream that can fail, provide an appropriate error consumer or handle errors with an operator such as **onErrorResume**.

Distinguish the **observation point**: the **onErrorResume** operator catches the error upstream and subscribes to a fallback. Thus the original source may terminate with **onError**, while a subscriber at the end of the pipeline receives the fallback data and **onComplete**. This does not break the rule "at most one terminal signal per Subscription"; the signals are being observed at different segments of the pipeline.

Application example: for a Spring WebFlux endpoint returning **Flux<T>**, Reactive Streams governs signals among publishers/operators/subscribers; an HTTP client disconnecting can trigger **cancel()**, which is not equivalent to **onComplete**. Resource cleanup logic should account for both errors and cancellation, for example with **doFinally(...)** or an appropriate resource-management mechanism.

## 7. Key Rules and Common Mistakes

| Misconception | Correct Understanding |
| --- | --- |
| "onSubscribe is the first data item" | It is the callback that sets up the **Subscription**; data appears only in **onNext**. |
| "request(3) guarantees three onNext calls" | It is the **maximum permitted additional emissions**; an empty source, fewer items, or an error can end the stream early. |
| "onComplete and onError can both appear" | On the same Subscription there is **only one of the two**, at most once. |
| "onError requires a prior onNext or request" | An error can be signaled right after **onSubscribe**, independent of demand. |
| "cancel() will invoke onComplete" | Cancellation is a control signal, usually with **no terminal callback** afterward; in-flight signals may still arrive. |
| "Callbacks run in parallel to speed things up" | For the same Subscriber, the Publisher must deliver signals **serially without overlap**, even when multiple threads are used. |
| "You can throw arbitrary exceptions inside onNext" | The Subscriber must handle them and/or **cancel()** per the contract; throwing exceptions out of callbacks can break the protocol. Publisher errors are reported via **onError**. |
| "You can send null via onNext to represent empty" | Null items are invalid under Reactive Streams; an empty source terminates with **onComplete**. |

When debugging, log events *per Subscription* (and by operator position if using Reactor). Check **whether onSubscribe appears first**, **whether request provides enough demand**, **which terminal signal occurred**, and **whether early cancellation happened**. Looking only at the **onNext** count while ignoring demand and cancellation easily leads to wrong conclusions.

## 8. Self-Check

1. A Publisher has just subscribed a Subscriber and has no items. What is the minimum sequence on normal completion? **onSubscribe → onComplete.**
2. After **request(2)**, the Publisher emits two **onNext** signals and has not terminated yet. May it emit the third item immediately? **No**, unless there is another request from the Subscriber.
3. After **onError**, can the Subscriber receive **onComplete** on the same Subscription? **No**. To recover from an error, the pipeline must handle it with an appropriate recovery mechanism, creating a new observable sequence downstream.

## 9. Reference Materials

- Reactive Streams Specification for the JVM: https://github.com/reactive-streams/reactive-streams-jvm
- JDK Flow.Subscription (Java 21): https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/util/concurrent/Flow.Subscription.html
- JDK Flow.Subscriber (Java 21): https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/util/concurrent/Flow.Subscriber.html
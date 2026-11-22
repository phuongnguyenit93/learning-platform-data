# JDK Flow API vs. BlockingQueue

## 1. Purpose and Context

In Java, both the **Flow API** and **BlockingQueue** help connect data producers with data processors when the two sides operate at different speeds. They solve this problem using different contracts:

- **BlockingQueue** is a thread-safe queue following the **producer–consumer** model. Producers actively insert elements into the queue, and consumers actively take elements out. With a bounded queue, a producer may block when the queue is full, and a consumer may block when the queue is empty.
- **Flow API** (since Java 9, package **java.util.concurrent.Flow**) is a set of interfaces following the **Publisher–Subscriber** model. A Publisher pushes events to each Subscriber, while each Subscriber signals in advance how many elements it is allowed to receive via **Subscription.request(n)**. This mechanism is called **demand-driven backpressure**.

The question of which tool to choose is not simply “which one is faster?” but rather: **do you need a work queue from which multiple workers pull tasks, or do you need a data-streaming protocol with subscriptions, demand, and completion/error signals?**

The content below discusses only JDK concurrency APIs and does not cover other frameworks.

## 2. How Does BlockingQueue Work?

**BlockingQueue<E>** is an interface in **java.util.concurrent**. Example implementations:

- **ArrayBlockingQueue<E>**: fixed capacity, FIFO order; useful when you need to bound memory and apply backpressure to producers.
- **LinkedBlockingQueue<E>**: can be given a capacity; the no-argument constructor uses a very large bound (**Integer.MAX_VALUE**), so it should not be implicitly treated as a practically bounded queue.
- **PriorityBlockingQueue<E>**: orders elements by comparison priority, does not preserve FIFO, and is not bounded by a fixed capacity.
- **SynchronousQueue<E>**: holds no backlog of elements; each insertion must pair with a corresponding removal.

### 2.1. Operations to Distinguish

| Scenario | Operation | Behavior |
|---|---|---|
| Producer waits for space | **put(e)** | Waits if the queue is bounded and full; can be interrupted. |
| Producer does not wait | **offer(e)** | Returns **false** if the element cannot be inserted immediately. |
| Producer waits with a time limit | **offer(e, timeout, unit)** | Waits up to the timeout and then returns the result. |
| Consumer waits for data | **take()** | Waits until an element is available; can be interrupted. |
| Consumer does not wait | **poll()** | Returns **null** when no element is available. |
| Consumer waits with a time limit | **poll(timeout, unit)** | Waits up to the timeout; may return **null**. |

BlockingQueue does not accept **null** elements. An element retrieved by **take()** is removed from the queue, so two ordinary consumers **compete to receive different elements**. The queue does not automatically broadcast the same element to every consumer.

### 2.2. Backpressure of a Bounded Queue

Suppose a queue has capacity = 2:

~~~text
Producer --put(A)--> [A,   ] --take()--> Consumer
Producer --put(B)--> [A, B]
Producer --put(C)--> [A, B]  (waits because it is full)
Consumer --take()--> [B,   ] (producer can continue put(C))
~~~

A finite capacity creates **backpressure at the insertion point**: a producer calling **put()** must wait or choose a timeout/drop/reject policy. This is a control mechanism based on **buffer capacity**, not the consumer granting individual “receive permissions” to the producer. If a nearly unbounded queue is used, backlog can still grow sharply when the production rate exceeds the processing rate.

### 2.3. Runnable Example with Java 17+: Bounded Queue

Create the file **BlockingQueueDemo.java**:

~~~java
import java.util.concurrent.ArrayBlockingQueue;
import java.util.concurrent.BlockingQueue;

public final class BlockingQueueDemo {
    private static final int END = -1;

    public static void main(String[] args) throws InterruptedException {
        BlockingQueue<Integer> queue = new ArrayBlockingQueue<>(2);

        Thread producer = new Thread(() -> {
            try {
                for (int n = 1; n <= 3; n++) {
                    queue.put(n);
                }
                queue.put(END);
            } catch (InterruptedException e) {
                Thread.currentThread().interrupt();
            }
        }, "producer");
        producer.start();

        while (true) {
            int item = queue.take();
            if (item == END) break;
            System.out.println("item: " + item);
        }
        producer.join();
    }
}
~~~

Compile and run:

~~~bash
javac --release 17 -encoding UTF-8 BlockingQueueDemo.java
java BlockingQueueDemo
~~~

Expected output:

~~~text
item: 1
item: 2
item: 3
~~~

**Why is this correct?** The producer sends 1, 2, 3 in order and then sends the **END** marker. **ArrayBlockingQueue** preserves FIFO; the consumer prints each value until it encounters the marker. Capacity = 2 forces the producer to wait if the buffer is full without losing order. **producer.join()** waits for the producer to finish.

**Limitations of the example:** The marker **-1** is an application-specific convention. In a system with multiple consumers, an appropriate shutdown strategy is needed (such as one marker per consumer or a centralized stop mechanism). If the producer fails before sending the marker, the consumer can wait indefinitely; real applications need error handling, timeouts, interrupts, and task cancellation.

## 3. Flow API: Publisher, Subscriber, Subscription, and Processor

**Flow** is an enclosing class containing four core interfaces, not a queue or a complete processing engine:

| Component | Role |
|---|---|
| **Flow.Publisher<T>** | Emission source; provides **subscribe(subscriber)**. |
| **Flow.Subscriber<T>** | Receives subscription, item, error, and completion signals. |
| **Flow.Subscription** | Link dedicated to a single Subscriber; supports **request(n)** and **cancel()**. |
| **Flow.Processor<T,R>** | Both an input Subscriber and an output Publisher, used to build data transformation stages. |

A basic signal flow:

~~~text
Publisher                   Subscriber
    |---- onSubscribe(s) ------>|
    |<------ request(2) --------|
    |--------- onNext(A) ------>|
    |--------- onNext(B) ------>|
    |<------ request(1) --------|
    |--------- onNext(C) ------>|
    |--------- onComplete() --->|
~~~

### 3.1. Demand Is a Countable Permission to Send

- When calling **subscription.request(n)** with **n > 0**, the Subscriber adds **n** to the unfulfilled demand of that specific subscription.
- The Publisher may only call **onNext** within the available demand. **request(3)** permits *at most* 3 additional **onNext** calls; it does not force the Publisher to produce all 3 elements immediately.
- Requests are cumulative; demand can be treated as virtually unbounded if **request(Long.MAX_VALUE)** is used.
- **request(0)** or a negative number violates the contract: the Subscriber must receive **onError(IllegalArgumentException)**.
- **cancel()** requests cancellation of the subscription on a best-effort basis; signals may still be in flight, and **onComplete()** is not guaranteed after cancellation.

**Key point:** Demand limits the number of **onNext** calls; it **does not automatically limit the amount of data a Publisher has already produced, holds in memory, or has placed in a buffer**. Retaining data, execution scheduling, overload policies, and how backpressure is propagated to the source are determined by the implementation.

### 3.2. Signal Protocol and Lifecycle

1. **onSubscribe(subscription)** arrives before any other signals for that subscription. The Subscriber should store the subscription and then request initial demand.
2. **onNext(item)** is delivered while demand remains; callbacks for **the same subscription** occur sequentially in order, not concurrently with one another.
3. **onError(throwable)** is the terminal signal for an unrecoverable error, or **onComplete()** is the normal terminal signal. After a terminal signal, no further **onNext** calls occur for that subscription.
4. **cancel()** is an action from the Subscriber side; it is not equivalent to a guaranteed **onComplete()**.
5. Each Subscriber has its own Subscription and demand; when a Publisher supports multiple Subscribers, a slow Subscriber can have different demand and backlog from a fast Subscriber.

For **Flow.Processor**, upstream and downstream demand must be kept separate. A properly implemented Processor limits upstream requests according to its buffering capacity and downstream demand, rather than requesting unboundedly and holding all data in memory.

### 3.3. Is Flow Always Asynchronous?

**No.** The Flow interfaces define the signal and demand contract; by themselves they do not require every Publisher to use a separate thread or be strictly non-blocking. How callbacks execute depends on the implementation. One Publisher may use an executor to deliver events asynchronously; another implementation may execute differently. Therefore, you must read the documentation of the **specific Publisher**.

## 4. SubmissionPublisher: The Built-In JDK Implementation

**SubmissionPublisher<T>** is a **Flow.Publisher<T>** implementation designed for publishing items to Subscribers using asynchronous delivery, with a **separate buffer per Subscriber**.

- **subscribe(subscriber)** registers a recipient and delivers **onSubscribe** according to the publisher's mechanism.
- **submit(item)** delivers the item to current Subscribers; **it may block the calling thread** if resources/buffer space for a Subscriber are unavailable. It does **not** mean “fire-and-forget, never wait.”
- **offer(item, onDrop)** and its timeout overload allow choosing a policy when the buffer cannot accept data; the handler may request a retry according to the contract. When zero data loss is required, you must design how to handle cases where offer does not accept the item.
- **close()** completes normally after delivering pending items according to the publisher's mechanism; **closeExceptionally(cause)** propagates a terminal error.
- The default buffer size can be referenced via **Flow.defaultBufferSize()**, but you must check the actual capacity and characteristics of the Publisher in use; demand and buffer capacity are two separate concepts.

### 4.1. Runnable Example with Java 17+: Receiving One Item at a Time by Demand

Create the file **FlowDemo.java**:

~~~java
import java.util.concurrent.CountDownLatch;
import java.util.concurrent.Flow;
import java.util.concurrent.SubmissionPublisher;

public final class FlowDemo {
    public static void main(String[] args) throws InterruptedException {
        CountDownLatch completed = new CountDownLatch(1);

        try (SubmissionPublisher<Integer> publisher = new SubmissionPublisher<>()) {
            publisher.subscribe(new Flow.Subscriber<Integer>() {
                private Flow.Subscription subscription;

                @Override
                public void onSubscribe(Flow.Subscription subscription) {
                    this.subscription = subscription;
                    subscription.request(1);
                }

                @Override
                public void onNext(Integer item) {
                    System.out.println("item: " + item);
                    subscription.request(1);
                }

                @Override
                public void onError(Throwable error) {
                    System.err.println("error: " + error);
                    completed.countDown();
                }

                @Override
                public void onComplete() {
                    System.out.println("done");
                    completed.countDown();
                }
            });

            for (int n = 1; n <= 3; n++) {
                publisher.submit(n);
            }
        }
        completed.await();
    }
}
~~~

Compile and run:

~~~bash
javac --release 17 -encoding UTF-8 FlowDemo.java
java FlowDemo
~~~

Expected output of a normal run:

~~~text
item: 1
item: 2
item: 3
done
~~~

**Step-by-step explanation:**

1. The Subscriber is given a **Subscription** in **onSubscribe** and calls **request(1)**.
2. Each time **onNext(item)** finishes processing, it requests one more item via **request(1)**. In this way, at most one additional **onNext** delivery is granted demand on that subscription at any time.
3. **submit()** places data into the publisher; the publisher may buffer items before callbacks run. Therefore, **request(1)** does not mean the producer must wait for the first item to finish before calling **submit()** for the next item.
4. **try-with-resources** calls **close()** on the publisher. **CountDownLatch** makes the main thread wait for the **onComplete** (or **onError**) callback before exiting, because callbacks are delivered asynchronously.

Do not use **Thread.sleep(...)** to “wait for callbacks to finish”: sleep leads to flaky tests. The example uses a latch to observe actual completion. In production applications, add timeout and cancellation policies in case the source never completes.

## 5. Direct Comparison by Design Criteria

| Criterion | Flow API / Publisher–Subscriber | BlockingQueue / Producer–Consumer |
|---|---|---|
| Communication style | Publisher **pushes** signals to registered Subscribers. | Consumer **pulls** items via **take()/poll()**. |
| Rate control | Subscriber sends **request(n)**: per-subscription demand. | Producer hits **capacity** limits on **put/offer**. |
| Buffering | Not guaranteed by the interface; depends on the Publisher. **SubmissionPublisher** uses a per-Subscriber buffer. | The queue is a shared buffer; capacity is determined by the implementation or constructor. |
| Multiple recipients | Publisher supports delivering to multiple Subscribers; exact broadcast semantics depend on the implementation. | Multiple consumers typically **share work**; each item is taken out exactly once. |
| Execution model | Depends on Publisher/executor; callbacks may be asynchronous, and the Flow contract does not guarantee non-blocking. | **put/take** may block the calling thread. |
| Normal completion | **onComplete()** signal. | No built-in completion signal; use custom markers/stop conditions. |
| Error termination | **onError(Throwable)** signal. | No built-in error channel; propagate errors via results, sentinels, or coordination mechanisms. |
| Cancellation | **Subscription.cancel()**, best-effort. | Interrupts, stop flags, timeouts, sentinels, or external lifecycle closure. |
| Common use cases | Event streams, signal-driven pipelines, fan-out to Subscribers, demand-driven processing. | Bounded work queues, worker pools, thread handoffs, per-item task processing. |
| Complexity | Requires adhering to lifecycle, demand, cancellation, and terminal signals. | Simpler for a producer–worker pipeline, but requires managing shutdown and errors manually. |

**Avoid the misconception that “Flow is newer, so it is always better.”** For a worker pool processing jobs where each job is handled by only one worker, a **bounded BlockingQueue** is usually the more direct and controllable structure. For an interface where multiple Subscribers observe a stream of items and actively grant demand, **Flow** expresses the contract more clearly.

## 6. How Do the Two Backpressure Mechanisms Differ?

### 6.1. Example: Temporarily Slow Consumer

Suppose a producer can generate 100 items/second, while a consumer processes 60 items/second.

**With ArrayBlockingQueue of capacity 200:**

- Once the backlog reaches capacity, **put()** begins to wait.
- The producer's effective rate is throttled by waiting on the queue; if **offer()** is used instead, the application must decide what to do on **false** (retry, drop, log, or reroute).
- A bounded queue prevents unbounded accumulation *inside the queue itself*, but it does not stop a producer from storing data elsewhere before calling put.

**With Flow and batch requests:**

- A Subscriber can call **request(16)**, process them incrementally, and request more as capacity becomes available.
- The Publisher must not deliver **onNext** beyond the subscription's demand; however, it may still generate or hold data in an internal buffer before delivery.
- If the Publisher has a bounded buffer, once full it must enforce its own policy: wait, reject, drop, or throttle the source. **SubmissionPublisher.submit()** can block when a slow Subscriber fills its buffer.
- Another Subscriber may have different demand, so a single system-wide capacity or backlog cannot be inferred from **request(n)**.

### 6.2. Backpressure Does Not Automatically Eliminate All Risks

You must control **both demand and where data accumulates**. Common failure scenarios:

- A Subscriber calls **request(Long.MAX_VALUE)** while processing slowly: it has effectively disabled demand limits; buffering must still be managed.
- A Publisher generates millions of items before checking demand: delivering **onNext** per the contract will not save memory already consumed beforehand.
- A queue has no capacity bound: **put()** almost never blocks due to a full queue until system resources run into trouble.
- A Subscriber calls **request(1)**, but inside **onNext** it launches asynchronous work and immediately requests again: the callback only confirms *handing off* the work, not that the work has actually completed. Demand should be tied to the number of tasks allowed to run or a separate in-flight limit.

An intuitive rule: if the arrival rate exceeds the sustained processing rate, backlog tends to grow. **Good backpressure must propagate pressure back to the data source or define a rejection/data-loss policy**, rather than merely shifting the backlog to another layer.

## 7. Lifecycle, Errors, Interruption, and Cancellation

### When Using BlockingQueue

- **InterruptedException** from **put()/take()** is a cooperative stop signal. If caught in a worker and it cannot be rethrown, you typically need **Thread.currentThread().interrupt()** and to exit according to the application's policy.
- There is no universal **queue.close()**. A marker convention must be distinct from real data; with multiple workers, shutdown must wake up all waiting workers.
- **poll(timeout)** and **offer(timeout)** allow tasks to check stop state or bound wait times.
- A failed task does not automatically notify all producers/consumers; a separate mechanism is needed, such as error results, futures, a supervisor, or shared state.

### When Using Flow

- If **onNext** performs long synchronous work, the subscription's callback throughput drops. If it processes asynchronously, the number of in-flight tasks must be managed.
- Call **request(n)** in **onSubscribe** or after processing items in batches; avoid requesting nothing, which stalls the stream even when the publisher has data.
- For unrecoverable errors, the Publisher/Subscription sends **onError** and stops; normal completion uses **onComplete**. **onError** and **onComplete** are two distinct terminal paths.
- When the application no longer needs data, keep the Subscription and call **cancel()**; do not wait for **onComplete()** as a promise after cancellation.
- Do not throw exceptions out of **onNext** assuming the runtime will retry or handle them as expected; callback error behavior is constrained by the contract and implementation. Handle or propagate errors intentionally.

## 8. Choosing a Design for Real-World Scenarios

### Scenario A: Multiple Workers Pulling Jobs from the Same Source

**Choose a bounded BlockingQueue** such as **ArrayBlockingQueue** when each job needs one worker to process it, the number of workers is fixed, and waiting or rejecting when full is appropriate.

~~~text
Producer A --\
Producer B ----> [ bounded BlockingQueue ] ---> Worker 1
                                         \----> Worker 2
~~~

Configure capacity, wait times, timeouts/shutdown, and monitor queue depth. If more complex task execution control is required, consider JDK task execution abstractions, though a queue remains the direct component for handoff.

### Scenario B: One Source Emitting Events to Multiple Listeners

**Choose Flow Publisher–Subscriber** when each listener needs its own signals, wants to adjust demand independently, and wants to receive **onComplete/onError** under a clear protocol.

~~~text
                       /--> Subscriber A (request 4)
Publisher --fan-out---<
                       \--> Subscriber B (request 1)
~~~

**SubmissionPublisher** is suitable for learning or building a simple local publisher. For high throughput, complex errors, or zero-data-loss requirements, you must additionally design buffer limits, overload policies, persistence/retry, and thorough testing; the Flow interfaces do not provide all of those features.

### Scenario C: Turning a Queue into a Flow Source

You can write a **Flow.Publisher** that pulls data from a queue, but a correct adapter must:

1. Register a separate Subscription for each Subscriber and track demand safely across threads.
2. Not pull too many elements from the queue when there is no processing capacity or matching demand.
3. Handle **cancel()**, terminal signals, interrupts, wake-ups, and shutdown.
4. Clearly specify whether delivery is **one consumer per item** or **every Subscriber receives the same item**; a shared queue does not broadcast automatically.

Conversely, if you push **onNext** into a bounded BlockingQueue using **put()**, the callback may block the signal-delivery thread. When callbacks must stay short, use **offer()** with a clear overload policy and only grant more demand when processing resources are actually freed.

## 9. Common Misconceptions

1. **“Flow is just a queue with a different name.”** False: Flow defines a streaming protocol, Subscription, demand, and terminal events; buffering is an implementation detail.
2. **“request(1) means the producer can only create one item.”** False: it limits **onNext** deliveries, not data created or buffered beforehand.
3. **“SubmissionPublisher.submit never blocks.”** False: when no buffer space remains for a Subscriber, **submit()** can block.
4. **“Multiple consumers reading a BlockingQueue means each consumer receives every item.”** False: consumers compete to take elements.
5. **“onComplete happens immediately after calling close, so main can exit.”** Do not assume asynchronous callbacks have finished; wait on an actual completion condition when needed.
6. **“Any BlockingQueue provides backpressure via capacity limits.”** False: you must choose an appropriate implementation/capacity and an insertion method with the desired behavior.
7. **“request(Long.MAX_VALUE) is the default optimal approach.”** It may fit when flow control is unnecessary, but it disables useful demand limits in slow streams.
8. **“cancel always sends onComplete.”** False: cancel is best-effort and does not guarantee a terminal callback.
9. **“Flow automatically handles all race conditions.”** False: it only provides specific guarantees on callback/demand ordering; shared state across components must still be properly synchronized.
10. **“Simply configuring capacity guarantees no data loss.”** False: overload, process failures, restarts, and using **offer** all require reliable policies.

## 10. Application Checklist

- **Semantics:** should each item be received by *one worker*, or should *each Subscriber* receive a signal?
- **Bounds:** are queue capacity, per-Subscriber buffer capacity, in-flight job count, and the data source all bounded?
- **Overload:** when downstream is slow, should upstream wait, retry, reject, or drop? Is data loss acceptable?
- **Lifecycle:** do startup, errors, timeouts, cancel, interrupts, and shutdown have clear paths?
- **Observability:** track queue depth, put/take wait times, items/second rate, processing latency, errors, dropped items, and per-Subscriber lag if supported by the implementation.
- **Testing:** test very slow consumers, zero demand, full queues, callbacks throwing exceptions, mid-stream cancellation, and stopping while workers are waiting.

**Quick rule of thumb:** use a **bounded BlockingQueue** for work streams shared among threads; use **Flow** when you need a Publisher–Subscriber contract with **demand, completion/error signals, and multiple subscriptions**. Both require appropriate buffering, resource, and shutdown policies.

## 11. Official JDK Documentation

- [Flow (Java SE 17)](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/concurrent/Flow.html)
- [Flow.Subscriber (Java SE 17)](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/concurrent/Flow.Subscriber.html)
- [Flow.Subscription (Java SE 17)](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/concurrent/Flow.Subscription.html)
- [SubmissionPublisher (Java SE 17)](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/concurrent/SubmissionPublisher.html)
- [BlockingQueue (Java SE 17)](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/concurrent/BlockingQueue.html)

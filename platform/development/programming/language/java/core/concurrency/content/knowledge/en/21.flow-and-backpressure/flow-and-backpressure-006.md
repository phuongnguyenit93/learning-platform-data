# How Does Backpressure Differ from Buffering? — Java Concurrency

## 1. Core Answer

**Buffering** means temporarily holding unprocessed items in memory or an intermediate storage location. It allows the data producer and the data consumer to operate out of sync for short periods.

**Backpressure** is a mechanism that lets the slower side push back against the sender: indicating how much more it can accept, or forcing the sender to slow down or wait when there is no longer room to receive. The goal is to control **the amount of pending work (backlog)**, especially when the data production rate exceeds the processing rate.

The two concepts are not mutually exclusive. A Java pipeline can have **both a bounded buffer and backpressure**: the buffer absorbs short-term fluctuations; demand signals or blocking the producer prevent the backlog from growing without bound.

Example: an event reader produces 1,000 items/second, while the processor only completes 100 items/second.

- If events are simply put into an unbounded queue, the backlog grows by approximately 900 items/second for as long as the mismatch lasts. Adding more RAM only delays the failure.
- If there is a buffer with a maximum of 1,800 items, starting from empty, with no throttling policy, data dropping, or rate change, the buffer will fill up in about 2 seconds. A finite buffer forces the system to decide what to do when full.
- If backpressure is present and the producer **can be slowed down**, the production/ingestion rate must decrease accordingly; the buffer only needs to be large enough for short bursts. If an external source cannot be stopped, an overflow policy is still required: blocking at an appropriate boundary, sampling/dropping, spilling to disk, rejecting, or failing with an error.

Intuitive formula when rates are roughly constant:

~~~text
Backlog growth rate ≈ max(0, arrival rate − processing rate)
Time until full ≈ remaining free capacity / backlog growth rate
~~~

This is an estimation model, not a real-time guarantee: processing speed, event delivery, memory per item, and producer blocking can all vary.

## 2. Direct Comparison

| Aspect | Buffering | Backpressure |
|---|---|---|
| Question addressed | "Where does unprocessed data sit?" | "How much more is the receiver allowing the sender to send?" |
| Mechanism | Queue, ring buffer, batch, internal buffer | Demand/credit, in-flight limits, producer waiting when full, rate throttling |
| Primary role | Absorb temporary rate mismatches | Prevent workload rate/volume from exceeding sustainable intake capacity |
| When consumer is slow | Queue continues growing until hitting its limit | Producer is asked to send less or is blocked at a boundary |
| Specific risks | Unbounded buffering causes heap pressure, GC overhead, and latency | Congestion can propagate upstream; the producer may also have to wait |
| When full | Requires block/drop/reject/spill/error rules | Must have a signaling path or an action enforcing the limit |
| Guarantees no data loss? | No; depends on capacity and overflow policy | No; depends on source cooperation, overflow policy, and storage durability |

**Key distinction:** a large queue does not by itself create backpressure. Only when there is a mechanism that makes the sender **unable to keep pushing faster than the receiver's capacity** (or actively reduce sending according to demand) does backpressure take effect. Conversely, a bounded queue with a blocking operation when full provides both buffering and backpressure at the queue boundary.

## 3. Flow API in Java: Demand as the Backpressure Signal

Since Java 9, **java.util.concurrent.Flow** defines the standard Publisher–Subscriber protocol in the JDK:

- **Flow.Publisher<T>**: event source; registers receivers via subscribe().
- **Flow.Subscriber<T>**: receives onSubscribe(), onNext(), onError(), onComplete().
- **Flow.Subscription**: private link between publisher and subscriber; request(n) increases the number of items allowed to be sent, cancel() stops the subscription on a best-effort basis.
- **Flow.Processor<T,R>**: both receives from upstream as a Subscriber and emits to downstream as a Publisher; must manage demand in both directions.

Basic sequence:

~~~text
Publisher                         Subscriber
    |                                 |
    | -------- onSubscribe(s) ------> |
    | <---------- s.request(2) ------ |
    | --------- onNext(A) ----------> |  1 receive credit left
    | --------- onNext(B) ----------> |  0 receive credits left
    |        waiting for more demand  |
    | <---------- s.request(1) ------ |
    | --------- onNext(C) ----------> |
    | -------- onComplete() --------> |  after the source completes normally
~~~

**request(2)** grants permission for at most two more onNext calls; it does not mean the publisher immediately generates two items or that the consumer has already completed two tasks. Demand is permission to **deliver events**, not a promise about throughput, storage durability, or "exactly once" delivery.

Important rules:

1. A Subscriber must receive onSubscribe before receiving data. A compliant Publisher must not call onNext beyond the total unused demand of that subscription.
2. Each onNext consumes one unit of demand. Positive request(n) calls accumulate; request(Long.MAX_VALUE) is generally treated as effectively unbounded demand, meaning the subscriber disables demand-based delivery limits.
3. request(0) or request(negative) violates the protocol; the subscriber receives onError with IllegalArgumentException.
4. onError and onComplete are terminal signals; after termination, no further valid onNext calls may occur. cancel() is best-effort, so a few in-flight signals may still arrive.
5. Flow does not require every Publisher to run asynchronously. Scheduling, queues, threads, and buffer-full policies belong to the concrete implementation; you cannot infer from the Flow interfaces alone that a source will automatically slow down.

### Runnable Example: Subscriber Requesting One Item at a Time

Save the file **FlowDemandDemo.java** (Java 17+):

~~~java
import java.util.concurrent.CountDownLatch;
import java.util.concurrent.Flow;
import java.util.concurrent.SubmissionPublisher;
import java.util.concurrent.TimeUnit;

public class FlowDemandDemo {
    public static void main(String[] args) throws InterruptedException {
        CountDownLatch done = new CountDownLatch(1);

        try (SubmissionPublisher<Integer> publisher = new SubmissionPublisher<>()) {
            publisher.subscribe(new Flow.Subscriber<Integer>() {
                private Flow.Subscription subscription;

                @Override
                public void onSubscribe(Flow.Subscription s) {
                    subscription = s;
                    subscription.request(1);
                }

                @Override
                public void onNext(Integer value) {
                    System.out.println("Nhan " + value);
                    subscription.request(1);
                }

                @Override
                public void onError(Throwable error) {
                    System.err.println("Loi: " + error);
                    done.countDown();
                }

                @Override
                public void onComplete() {
                    System.out.println("Hoan tat");
                    done.countDown();
                }
            });

            for (int i = 1; i <= 5; i++) {
                publisher.submit(i);
            }
        }

        if (!done.await(5, TimeUnit.SECONDS)) {
            throw new IllegalStateException("Subscriber chua ket thuc");
        }
    }
}
~~~

Run:

~~~bash
javac FlowDemandDemo.java
java FlowDemandDemo
~~~

Stdout on a successful run:

~~~text
Nhan 1
Nhan 2
Nhan 3
Nhan 4
Nhan 5
Hoan tat
~~~

Explanation:

- onSubscribe() calls request(1): initially grants permission to receive only one item.
- onNext() processes one item and then grants one more credit. This is the **one-item-at-a-time request** pattern; in real applications, request more only after completing the work that needs to be bounded.
- SubmissionPublisher delivers asynchronously. CountDownLatch keeps main alive until a terminal signal is received; the try block closes the publisher after submitting the items. If an error occurs, the onError branch prints to stderr, so the output above represents the **normal execution path**.
- **Do not misinterpret the example:** the subscriber calling request(1) **does not prove** the producer only creates one item at a time. SubmissionPublisher still has its own internal buffer, and the for loop can submit multiple items before the subscriber processes them. Demand limits **onNext delivery**, while the buffer and submit behavior determine the internal backlog.

This simple example does not use Thread.sleep() to "prove" backpressure. Sleeping in onNext only slows down processing and timing results easily vary by machine; to verify actual limits, you need to measure the number of items produced, delivered, buffered, and the stage rates.

## 4. Buffering Independent of Flow: Bounded Queue Example

Save the file **BufferingDemo.java**:

~~~java
import java.util.concurrent.ArrayBlockingQueue;
import java.util.concurrent.BlockingQueue;

public class BufferingDemo {
    public static void main(String[] args) {
        BlockingQueue<Integer> queue = new ArrayBlockingQueue<>(2);

        System.out.println(queue.offer(10));
        System.out.println(queue.offer(20));
        System.out.println(queue.offer(30));
        System.out.println(queue.poll());
    }
}
~~~

Run:

~~~bash
javac BufferingDemo.java
java BufferingDemo
~~~

Stdout:

~~~text
true
true
false
10
~~~

This demonstrates **buffering**: the queue has two slots; offer(30) fails because it is full, and poll() retrieves item 10. offer() returning false **does not by itself slow down the producer**; the caller must decide whether to do a bounded retry, drop, fail with an error, or throttle input.

Replacing offer() with **put()** will make the producer thread wait when the queue is full until space becomes available (unless interrupted). A bounded BlockingQueue combining put()/take() therefore has both a buffer and **blocking** backpressure. Do not call put() in the single-threaded example above when the queue is full and there is no consumer: the program will wait forever.

Common variants:

| Component | When full | What to understand |
|---|---|---|
| ArrayBlockingQueue.offer(x) | Returns false immediately | Has a buffer limit, but the caller must handle failures itself |
| ArrayBlockingQueue.put(x) | Producer waits for free space | Creates blocking backpressure as the consumer takes items |
| ArrayBlockingQueue.offer(x, timeout, unit) | Waits up to timeout, then returns false | Has a wait time limit; still needs a policy on timeout |
| Effectively unbounded or backlog-uncontrolled queue | Can grow until resource exhaustion | Absorbs load spikes but does not guarantee memory safety |
| Flow.Subscription.request(n) | No further onNext permission granted once demand is exhausted | **Demand-based** backpressure; not a queue |

"Unbounded" here only means no finite business capacity is set; every structure in the JVM is still subject to heap, item count, or physical resource limits.

## 5. How Does SubmissionPublisher Combine Both Mechanisms?

**SubmissionPublisher<T>** is a built-in Flow.Publisher implementation in the JDK. It uses an Executor to deliver events asynchronously and maintains a **separate buffer per subscriber** when needed. Therefore:

- **The Subscriber** controls receive permission via Subscription.request(n); without sufficient demand, no extra onNext calls beyond the granted credit may be delivered.
- **The Publisher** may already have accepted data via submit() even though the subscriber has not processed it yet; the data sits in the intermediate buffer.
- Each subscriber's buffer has a maximum capacity. The constructor accepts maxBufferCapacity; the effective capacity may be rounded up to a power of 2, which can be checked via getMaxBufferCapacity().
- **submit(item)** can block the calling thread when a subscriber's buffer is full until resources become available. This is backpressure at the *sender calling submit* boundary; the method does not create new processing capacity, and blocking can propagate upstream.
- **offer(item, onDrop)** or its timeout overload can drop items when resources are insufficient and invoke a drop callback. That is a **controlled data-loss policy**, not a guarantee that backpressure preserves every item.

Note on multiple subscribers: each subscriber has its own buffer and demand. One slow subscriber can affect shared submit() calls; an item might be delivered to one receiver while being dropped for another when using offer(). Clarify fan-out requirements: do all subscribers need every item, or can each drop samples independently?

Bounded configuration example (this is an **illustrative snippet**, not a standalone program):

~~~java
ExecutorService executor = Executors.newFixedThreadPool(2);
SubmissionPublisher<String> publisher =
        new SubmissionPublisher<>(executor, 8);

// ... subscribe, submit/offer, and handle terminal signals ...
// When finished, close the publisher and shut down the executor according to the application lifecycle.
~~~

Do not infer that request(1) means "the buffer has only one slot." These two quantities are independent:

- **Demand** = number of onNext calls still permitted to be delivered.
- **Capacity** = number of items that can wait in the buffer per the implementation.

Calling submit() inside a callback that holds a resource needed by the consumer, or using the same executor with too few threads for both producer and consumer blocking each other, can cause starvation/deadlock. Choose blocking boundaries, executors, and resource shutdown order carefully.

## 6. Policies When the Consumer Cannot Keep Up

**(a) Absorb short bursts.** Use a bounded queue/buffer. Allow temporary backlog, and measure queue depth and wait time. Do not expect a buffer to solve a source that is permanently faster than the consumer.

**(b) Slow down a cooperative source.** In Flow, the subscriber grants demand according to its processing capacity; a compliant publisher/processor respects demand. With queues, bounded put() or a semaphore limiting in-flight work can prevent the producer from getting too far ahead. You must decide whether waiting is appropriate on the current thread.

**(c) Non-throttlable source.** For example, an external stream receiving data with no pause/ack mechanism. Backpressure in the internal pipeline cannot "force" an external source to stop. You need an explicit policy: reject, sample, drop-oldest/drop-latest, spill to durable storage, or signal overload. Choosing the policy depends on data-loss tolerance and ordering requirements.

**(d) Multi-stage processing.** If producer → parser → aggregator → writer, downstream demand must be propagated across every stage. A processor that dumps all items into an unbounded queue and immediately calls request(Long.MAX_VALUE) from upstream defeats the goal of bounding the backlog, even though the interfaces are still named Flow.

**(e) Data preservation.** Backpressure does not replace durable queues, transactions, retries, idempotency, or acknowledgments. If the application must survive crashes without losing items, you must design dedicated persistence/recovery mechanisms.

## 7. Choosing a Strategy Under Real Conditions

| Scenario | Suitable Approach | Why |
|---|---|---|
| Incoming traffic spikes for a few hundred milliseconds then drops | Bounded buffer, measure peak | Absorbs temporary fluctuations without building a huge queue |
| Incoming load is consistently higher than processing capacity | Backpressure/rate limit + bounded buffer | Adjusts rate sustainably; adding more buffer only delays overload |
| Producer and consumer are independent Java threads | Bounded BlockingQueue with put/take or timed offer | Easy to enforce memory bounds and full-state behavior |
| Data stream uses the Flow protocol | Intentional request(n); inspect how the publisher handles buffering | Bounds item delivery by demand, but requires understanding publisher design |
| Cannot delay source; sampling/dropping is acceptable | Bounded buffer + clear drop/reject policy | Prevents unbounded accumulation at the cost of potential item loss |
| Cannot lose items and source cannot be stopped | Need ingress limits and appropriate durable storage/ack | Flow or in-heap queues do not guarantee durability on their own |

When sizing capacity, account for at least: peak rate, average and p95/p99 processing time, average/maximum item size, number of consumers, number of subscribers, remaining heap, ordering requirements, and error policy. **Latency** must be measured from creation/ingestion to processing completion; good throughput on paper can still hide a growing backlog.

Useful operational signals include queued item count, age of the oldest item, remaining demand (if applicable), producer blocked time, failed offer count, drop count, executor utilization, and end-to-end latency. Set alert thresholds before the queue fills or processing time exceeds SLOs.

## 8. Common Misconceptions

1. **"Increasing the buffer eliminates backpressure."** False. A buffer only postpones the bottleneck; when a rate mismatch persists, the queue continues to fill.
2. **"Having a queue means you have backpressure."** Not enough. An unbounded queue, or offer() returning false while the caller keeps generating work, does not throttle the source.
3. **"request(1) means the publisher only produces one item."** False. It limits delivery to the subscriber; the publisher may already have produced data sitting in a buffer.
4. **"request(Long.MAX_VALUE) makes processing faster."** No. It only removes the demand limit; the consumer still has finite capacity.
5. **"submit() never blocks because it is asynchronous."** False. onNext delivery is asynchronous, but submit() can block when the buffer needs space.
6. **"Backpressure guarantees no items are lost."** False. Drops, errors, crashes, and non-cooperative sources all require separate handling.
7. **"Using sleep() in a demo proves the mechanism."** Unreliable. You need to observe demand, queue depth, items sent/processed, and full states.
8. **"Blocking the producer is always safe."** Not always true. Blocking on an event loop, inside a callback needed for progress, or exhausting a shared executor can cause stalls or deadlocks.

### Self-Check Questions

- With a producer at 500 items/s and a consumer at 400 items/s, about how long will it take a queue with 1,000 slots to fill if starting empty with no throttling? **About 10 seconds**.
- A Subscriber called request(3), received two onNext signals, then called request(2): what is the maximum remaining unused onNext credit? **3** (ignoring terminal/cancel signals and other requests).
- Does ArrayBlockingQueue.offer() returning false when full automatically create backpressure? **No**, if the caller ignores false and keeps producing items; using put() or a throttling strategy creates meaningful feedback to the producer.
- In SubmissionPublisher, does request(1) guarantee a buffer size of 1 item? **No**; demand and maxBufferCapacity are two separate limits.

## 9. Takeaways

**Buffering manages waiting space; backpressure manages permission/rate to enter that space.** A well-designed system typically needs a bounded buffer to absorb bursts, a throttling mechanism to prevent sustained overload, and clear policies for non-cooperative sources.

The scope of this article is **JDK Java Concurrency**; Spring-specific integrations and abstractions belong to another chapter.

**Official JDK References:** [Flow (Java 21)](https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/util/concurrent/Flow.html), [Flow.Subscription (Java 21)](https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/util/concurrent/Flow.Subscription.html), [SubmissionPublisher (Java 21)](https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/util/concurrent/SubmissionPublisher.html), [ArrayBlockingQueue (Java 21)](https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/util/concurrent/ArrayBlockingQueue.html).

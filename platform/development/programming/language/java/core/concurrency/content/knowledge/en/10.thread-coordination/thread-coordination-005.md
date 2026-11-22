# BlockingQueue: put(), take(), offer(), poll() in Java

When multiple threads need to pass work or data back and forth, manually using a `List`, a flag variable, and a polling loop can cause race conditions, *busy waiting*, or data loss. `java.util.concurrent.BlockingQueue<E>` is a **thread-safe queue** abstraction that also provides operations that **wait when an element cannot yet be added or retrieved**. It is a common foundation for the **producer–consumer** pattern, task queues, bounded buffers, and *backpressure* in Java.

The four core methods are:

- `put(e)`: inserts the element, **waiting if space is not yet available**.
- `take()`: retrieves and removes the head of the queue, **waiting if the queue is empty**.
- `offer(e)`: attempts to insert **immediately**, returning `false` if it cannot be added at that moment.
- `poll()`: attempts to retrieve **immediately**, returning `null` if no element is available.

The overloads `offer(e, timeout, unit)` and `poll(timeout, unit)` provide **bounded waiting times**. Understanding these differences is essential before designing cancellation paths, timeouts, consumer shutdown, and handling a full queue.

This Knowledge article belongs to the **Thread Coordination** topic, applies to **general Java concurrency (Java 17+)**, and does not cover Spring-specific mechanisms.

After this article, you will be able to:
1. Choose the right `BlockingQueue` add/remove/wait/try operation.
2. Write a producer–consumer with safe data handoff without manually using `wait/notify`.
3. Understand the impact of **bounded** and **unbounded** queues on backpressure and memory.
4. Handle `InterruptedException`, timeouts, poison pills, and orderly worker termination.
5. Understand visibility under the Java Memory Model when transferring data through a queue.
6. Recognize limitations: a queue has no standard `close()`, does not make mutable objects inside it thread-safe, and does not automatically guarantee shutdown or exactly-once task processing.

## 1. What is BlockingQueue and why is it useful?

`BlockingQueue<E>` belongs to `java.util.concurrent` and extends the concept of `Queue<E>`. It provides concurrent operations so multiple producers can insert and multiple consumers can retrieve elements without manually locking an `ArrayList`. Depending on the implementation, retrieval order may be FIFO, priority-based, expiration-based, or direct handoff: **`BlockingQueue` does not promise that all implementations are FIFO**.

Conceptual model:

~~~text
Producer A ---- put/offer ----+
                              |
Producer B ---- put/offer ----+--> [ BlockingQueue<E> ] --> take/poll --> Consumer X
                              |                      \--> take/poll --> Consumer Y
Producer C ---- put/offer ----+

When a BOUNDED queue is full: put() waits for free space.
When the queue is empty:      take() waits for an element.
offer() and poll():           return a result immediately, without waiting.
~~~

A thread-safe queue coordinates operations on the **queue structure**, but does not by itself answer every business question: how many consumers are there? How do we stop? If processing fails, should it retry? Is exactly-once guaranteed? Is the data immutable? Those questions require a separate protocol.

### 1.1. Why not use a continuous poll loop?

~~~java
// Code only illustrates an anti-pattern; queue is already declared.
while (true) {
    Message message = queue.poll();
    if (message != null) {
        process(message);
    }
}
~~~

If the queue is empty, the loop can **spin continuously and waste CPU**. The names `Message` and `process` here are only placeholders for illustration, **not a standalone program**. For a worker that needs to wait until data arrives, `take()` is a better expression; if it needs to periodically check for shutdown, `poll(timeout, unit)` may be appropriate.

## 2. Four groups of methods: throw, return status, block, timed block

`BlockingQueue` defines options with different semantics when an operation cannot proceed immediately:

| Operation | Throws exception immediately | Returns value/status immediately | Blocks indefinitely until possible | Blocks up to a timeout |
| --- | --- | --- | --- | --- |
| **Insert** | `add(e)` | `offer(e)` | `put(e)` | `offer(e, timeout, unit)` |
| **Retrieve and remove** | `remove()` | `poll()` | `take()` | `poll(timeout, unit)` |
| **Examine head, do not remove** | `element()` | `peek()` | Not in API | Not in API |

This is the core table of the `BlockingQueue` contract, especially important for **bounded-capacity** queues.

**When the queue is full:**
- `add(e)` throws `IllegalStateException` if it cannot be inserted due to capacity restrictions.
- `offer(e)` returns `false` if it cannot be inserted immediately.
- `put(e)` waits until space becomes available; may throw `InterruptedException`.
- `offer(e, timeout, unit)` waits up to the timeout, returning `true` if inserted, `false` if timed out; may throw `InterruptedException`.

**When the queue is empty:**
- `remove()` and `element()` throw `NoSuchElementException`.
- `poll()` and `peek()` return `null`.
- `take()` waits until an element is available, then **retrieves and removes** it; may throw `InterruptedException`.
- `poll(timeout, unit)` waits up to the timeout to retrieve an element; returns `null` if timed out; may throw `InterruptedException`.

Distinguish `peek()` from `poll()`: `peek()` only inspects the head element without removing it; `poll()` removes the element from the queue when successful. There is no indefinitely blocking `peek` operation in this interface.

### 2.1. Why are null elements not allowed?

`BlockingQueue` implementations **do not allow inserting `null` into the queue**. The key reason: `poll()` and `peek()` use `null` as a signal for "no element available", so a real `null` value in the queue would cause ambiguity.

~~~java
// Illustrative code: queue is an already created BlockingQueue<String>.
queue.offer(null); // Throws NullPointerException.
~~~

If the business logic has a concept of "no data" or "end", use an **explicit message type** such as a record containing status, a non-null sentinel object, or another cancellation/shutdown mechanism.

## 3. Non-blocking example: offer() and poll()

`ArrayBlockingQueue` has a **fixed capacity**, making it suitable for demonstrating full/empty queues and backpressure. The following Java 17+ program has no extra threads, so stdout is deterministic.

~~~java
// OfferPollDemo.java
import java.util.concurrent.ArrayBlockingQueue;
import java.util.concurrent.BlockingQueue;

public class OfferPollDemo {
    public static void main(String[] args) {
        BlockingQueue<Integer> queue = new ArrayBlockingQueue<>(2);

        System.out.println("offer 10: " + queue.offer(10));
        System.out.println("offer 20: " + queue.offer(20));
        System.out.println("offer 30: " + queue.offer(30));

        System.out.println("poll: " + queue.poll());
        System.out.println("poll: " + queue.poll());
        System.out.println("poll empty: " + queue.poll());
    }
}
~~~

~~~bash
javac OfferPollDemo.java
java OfferPollDemo
~~~

Stdout:

~~~text
offer 10: true
offer 20: true
offer 30: false
poll: 10
poll: 20
poll empty: null
~~~

Reason:
1. The queue has capacity 2, so it accepts 10 and 20.
2. When full, `offer(30)` returns `false` **immediately**, without waiting.
3. `ArrayBlockingQueue` maintains FIFO order, so `poll()` retrieves 10 then 20.
4. When no elements remain, `poll()` returns `null` immediately.

Appropriate use case: a processing path that wants to **try accepting work** and decide immediately if the queue is overloaded (report busy, drop by policy, retry elsewhere). If you do not check the `false` return value from `offer` and assume submission succeeded, the application can silently **lose work**.

## 4. Blocking example: put() and take()

`put(e)` is how a producer submits an element when it accepts **waiting if the queue is full**. `take()` is how a consumer waits for work when the **queue is empty**. Both are interruptible blocking operations.

### 4.1. Producer–consumer with a bounded queue

This is a complete Java 17+ example with one producer, one consumer, and a termination sentinel. The order of results in the list is deterministic thanks to the FIFO queue; printing happens only after both threads finish.

~~~java
// ProducerConsumerDemo.java
import java.util.ArrayList;
import java.util.List;
import java.util.concurrent.ArrayBlockingQueue;
import java.util.concurrent.BlockingQueue;

public class ProducerConsumerDemo {
    private static final String END = "__END__";

    public static void main(String[] args) throws InterruptedException {
        BlockingQueue<String> queue = new ArrayBlockingQueue<>(2);
        List<String> received = new ArrayList<>();

        Thread producer = new Thread(() -> {
            try {
                queue.put("alpha");
                queue.put("beta");
                queue.put(END);
            } catch (InterruptedException e) {
                Thread.currentThread().interrupt();
            }
        }, "producer");

        Thread consumer = new Thread(() -> {
            try {
                while (true) {
                    String item = queue.take();
                    if (END.equals(item)) {
                        break;
                    }
                    received.add(item);
                }
            } catch (InterruptedException e) {
                Thread.currentThread().interrupt();
            }
        }, "consumer");

        producer.start();
        consumer.start();
        producer.join();
        consumer.join();

        System.out.println("Received: " + received);
        System.out.println("Remaining: " + queue.size());
    }
}
~~~

~~~bash
javac ProducerConsumerDemo.java
java ProducerConsumerDemo
~~~

Without unexpected interrupts, stdout:

~~~text
Received: [alpha, beta]
Remaining: 0
~~~

**Detailed explanation:**
- The queue has capacity 2; the producer may block at `put(END)` until the consumer takes some data. There is no busy waiting or manual `notify` call.
- One producer enqueues elements in order `alpha → beta → END`. `ArrayBlockingQueue` preserves FIFO, and one consumer retrieves them in the exact same order.
- `END` is a non-`null` marker; upon receiving the marker, the consumer exits.
- The `ArrayList` is written to by **only one consumer**; `main` only reads it after `consumer.join()`, so the example has no concurrent modification of the list.
- Catching `InterruptedException` in the demo code only restores the interrupt flag and exits the worker; if the producer is interrupted before sending `END`, the consumer may wait forever. **Do not treat this minimal example as a comprehensive shutdown protocol**: in production you need a supervisor with a mechanism to cancel/wake both producer and consumer, handle sentinel enqueue failure, and enforce a deadline when waiting for completion.

### 4.2. A full queue provides backpressure

With a queue of capacity B, the producer can insert at most B elements that have not yet been taken by consumers. If the producer is faster than the consumer over a sustained period, `put()` **waits for space**, slowing down work intake upstream: this is a form of **backpressure**.

Backpressure bounds queued data, but it also introduces a new wait edge. If a producer holds a lock that the consumer needs to retrieve or complete work, a producer blocked in `put()` can contribute to a deadlock. Avoid holding unnecessary external locks during blocking queue operations.

**Blocking does not mean processing succeeded:** `put()` returning means the element has been placed into the queue, **not** that the consumer has finished processing it. `take()` returning means the element has been removed from the queue, **not** that business processing succeeded. If you need result confirmation, you must have a separate ack/result channel.

## 5. Timed offer() and poll(): bounded waiting

`offer(e, timeout, unit)` and `poll(timeout, unit)` are especially useful when:
- A producer has a deadline and must not wait indefinitely.
- A consumer needs to periodically check a stop condition, metrics, or system status.
- A caller wants to choose a fallback when the queue is full/empty for too long.

The following standalone program uses a queue of capacity 1 and short timeouts:

~~~java
// TimedQueueDemo.java
import java.util.concurrent.ArrayBlockingQueue;
import java.util.concurrent.BlockingQueue;
import java.util.concurrent.TimeUnit;

public class TimedQueueDemo {
    public static void main(String[] args) throws InterruptedException {
        BlockingQueue<Integer> queue = new ArrayBlockingQueue<>(1);
        queue.put(7);

        boolean sent = queue.offer(8, 50, TimeUnit.MILLISECONDS);
        System.out.println("Offer while full: " + sent);

        System.out.println("Take: " + queue.take());

        Integer missing = queue.poll(50, TimeUnit.MILLISECONDS);
        System.out.println("Poll while empty: " + missing);

        System.out.println("Offer available: " +
            queue.offer(9, 50, TimeUnit.MILLISECONDS));
        System.out.println("Poll available: " +
            queue.poll(50, TimeUnit.MILLISECONDS));
    }
}
~~~

~~~bash
javac TimedQueueDemo.java
java TimedQueueDemo
~~~

Under normal execution without unexpected interrupts, stdout:

~~~text
Offer while full: false
Take: 7
Poll while empty: null
Offer available: true
Poll available: 9
~~~

With no other thread interfering:
- The queue is initially full with 7, so `offer(8, 50, MILLISECONDS)` waits up to the timeout and eventually returns `false`.
- `take()` removes 7, freeing space.
- `poll(50, MILLISECONDS)` waits on the empty queue and then returns `null`.
- Once space is available, timed `offer(9, ...)` returns `true`; `poll(...)` retrieves 9.

**A timeout does not mean the send request is kept to resume automatically later.** If timed `offer` returns `false`, element 8 is **not added** to the queue. The caller must decide whether to retry, reject, log, route elsewhere, or drop according to policy. If timed `poll` returns `null`, no element was removed by that call.

### 5.1. What does InterruptedException mean?

`put()`, `take()`, and the timed overloads declare `throws InterruptedException`. When a waiting thread is interrupted, the call can throw this exception so the caller can cooperatively stop. If the calling layer can declare `throws InterruptedException`, it should usually propagate it; if it must catch it, it can restore the flag:

~~~java
// Illustrative code inside a worker that has a queue variable:
try {
    process(queue.take());
} catch (InterruptedException e) {
    Thread.currentThread().interrupt();
    return; // Exit worker according to the application's protocol.
}
~~~

`process` is an assumed already-declared method; the snippet is not standalone. Do not write an infinite loop that catches and ignores interrupts, as that can prevent the worker from stopping. At the same time, do not assume `interrupt` forcibly halts arbitrary code or automatically rolls back business operations the consumer has already performed.

**Distinguish interrupt from timeout:** timed `poll` returns `null` when the timeout expires, whereas it **throws `InterruptedException` when interrupted while waiting**. The two cases require different handling policies.

## 6. Key implementations and capacity choices

Not all `BlockingQueue` implementations share the same structure, bounds, and ordering.

| Implementation | Characteristics | Capacity / ordering / use case |
| --- | --- | --- |
| `ArrayBlockingQueue<E>` | Fixed-capacity array | **Bounded**, FIFO; suitable for bounded buffers |
| `LinkedBlockingQueue<E>` | Linked nodes | FIFO; optional capacity, defaults to `Integer.MAX_VALUE` |
| `SynchronousQueue<E>` | Direct handoff between producer and consumer | **Stores no elements** (capacity 0); `put` requires a matching receiver |
| `PriorityBlockingQueue<E>` | Priority-based queue | **Logically unbounded** in API, retrieves by priority rather than general FIFO |
| `DelayQueue<E extends Delayed>` | Elements become available only after their delay expires | Unbounded in API; `take()` waits for the next expired element |
| `LinkedTransferQueue<E>` | Linked-node queue supporting transfer | Unbounded in API; can perform direct handoff/transfer depending on the operation |

### 6.1. Bounded is not the same as unbounded

With a **bounded** queue like `new ArrayBlockingQueue<>(100)`, the number of waiting elements is capped. When full:
- `put` waits.
- `offer` returns `false`.
- Timed `offer` waits up to the timeout and then decides.

With a **logically unbounded** queue, producers are generally not restricted by a finite capacity configured in the API. This **does not mean infinite RAM**: if the producer rate exceeds the consumer rate over time, backlog growth can cause memory pressure or `OutOfMemoryError`. `LinkedBlockingQueue` without a capacity argument has a default bound of `Integer.MAX_VALUE`, which is operationally huge; consider passing an explicit capacity.

`remainingCapacity()` can be useful for observation, but in a multithreaded system it is a transient value: another thread can insert or remove immediately after the check. **Do not write `if (remainingCapacity() > 0) put(...)` thinking you have an atomic reservation.** Use `offer`/`put` directly according to your policy.

### 6.2. Fairness in ArrayBlockingQueue

`ArrayBlockingQueue` has a constructor that lets you configure `fair`:

~~~java
// Illustrative code:
BlockingQueue<String> queue = new ArrayBlockingQueue<>(8, true);
~~~

With `fairness=true`, blocked producer/consumer threads are served according to a fairer queuing policy as specified by the implementation contract. This can reduce the chance of a thread waiting for a long time, though it often reduces throughput. Do not interpret queue fairness as "every task is processed in exact real-time order" or "the Java scheduler will always be fair".

### 6.3. SynchronousQueue is not a one-element queue

`SynchronousQueue` **has no internal storage capacity**: each insert must pair with a corresponding remove from another thread. Therefore, non-blocking `offer(e)` will usually return `false` if no consumer is currently waiting; `put(e)` waits until a coordinating receiver arrives.

The Java 17+ example below has two threads exchanging one element:

~~~java
// SynchronousHandoffDemo.java
import java.util.concurrent.SynchronousQueue;

public class SynchronousHandoffDemo {
    public static void main(String[] args) throws InterruptedException {
        SynchronousQueue<String> queue = new SynchronousQueue<>();

        Thread consumer = new Thread(() -> {
            try {
                queue.take();
            } catch (InterruptedException e) {
                Thread.currentThread().interrupt();
            }
        });

        consumer.start();
        queue.put("parcel");
        consumer.join();

        System.out.println("Size: " + queue.size());
        System.out.println("Handoff completed");
    }
}
~~~

~~~bash
javac SynchronousHandoffDemo.java
java SynchronousHandoffDemo
~~~

Without unexpected interrupts, stdout:

~~~text
Size: 0
Handoff completed
~~~

`put("parcel")` completes when a matching receiver is present. `size()` is 0 because `SynchronousQueue` cannot hold elements. This is a **handoff**, not a buffer of capacity 1. Waiting for `consumer.join()` to finish does not mean the consumer completed any complex business processing; in this example, the consumer only takes the element.

## 7. Visibility guarantees between producer and consumer

`BlockingQueue` is a concurrent collection in `java.util.concurrent` and has **memory consistency effects** specified by the JDK. Actions in a producer thread **prior to placing an object into a queue** *happen-before* actions subsequent to **accessing or removing that element** from the queue in another thread.

Illustrative example:

~~~java
// Illustrative code, not a standalone file.
final class Message {
    int value;
}
Message message = new Message();
message.value = 42;          // Producer prepares data.
queue.put(message);          // Handoff via BlockingQueue.

// In another consumer:
Message received = queue.take();
System.out.println(received.value); // Sees 42 if there are no other concurrent writes.
~~~

This relationship allows the producer to **safely publish prepared data** to the consumer without manually marking every field `volatile` solely for handoff. However, **putting a mutable object into a queue does not make it immutable**. If the producer continues modifying `message.value` while the consumer reads it, data races and unexpected results can still occur.

**Good pattern:** finish preparing the object → `put` → do not modify that object again, or use an immutable message (`record` with immutable components). For a queue holding references to a mutable object shared by multiple threads, you need explicit ownership/copy/synchronization rules.

### 7.1. Communicating by message instead of shared mutable state

Instead of two threads mutating the same `ArrayList`, the producer can enqueue **individual messages**, and only the consumer updates processing state. This reduces the scope of shared data and clarifies ownership boundaries.

However, the queue only protects the enqueue/dequeue handoff. If the same message reference is sent to multiple places, or if after `take` the consumer shares the reference with another thread, the responsibility to protect state remains.

## 8. Designing shutdown: BlockingQueue has no standard close()

`BlockingQueue` **does not declare a `close()` method to automatically wake all consumers**. If all producers have stopped while a consumer is still in `take()` on an empty queue, it can wait indefinitely. Therefore, you must design a termination signal.

Common approaches:
1. **Poison pill/sentinel:** send a special element; when a consumer sees it, it exits. Works cleanly when the protocol has a known number of producers/consumers.
2. **Interrupt/cancellation:** a supervisor sends an interrupt to a consumer blocked in `take()`, and the worker handles `InterruptedException` and exits per policy.
3. **Timed poll + stop flag:** the worker uses `poll(timeout, unit)` and periodically checks a properly published termination condition.
4. **Executor management:** stop accepting new work, coordinate producers/consumers, cancel when needed, and `awaitTermination`. `ExecutorService.shutdown()` alone does not wake a task waiting forever on a queue if the task has no exit path.

### 8.1. Poison pills with multiple consumers

When N consumers independently pull from the same queue, **one poison pill is taken by only one consumer**. If you want all N consumers to exit via sentinel, you typically must send **N sentinel elements** after all producers have finished submitting normal work.

Complete Java 17+ example with two consumers and four tasks. Results are printed only from `main` after `join`, so output does not depend on consumer execution order:

~~~java
// MultipleConsumersShutdownDemo.java
import java.util.concurrent.ArrayBlockingQueue;
import java.util.concurrent.BlockingQueue;
import java.util.concurrent.atomic.AtomicInteger;

public class MultipleConsumersShutdownDemo {
    record Work(int id, boolean stop) {}
    private static final Work STOP = new Work(-1, true);

    public static void main(String[] args) throws InterruptedException {
        BlockingQueue<Work> queue = new ArrayBlockingQueue<>(3);
        AtomicInteger processed = new AtomicInteger();

        Runnable consumer = () -> {
            try {
                while (true) {
                    Work item = queue.take();
                    if (item.stop()) {
                        break;
                    }
                    processed.incrementAndGet();
                }
            } catch (InterruptedException e) {
                Thread.currentThread().interrupt();
            }
        };

        Thread a = new Thread(consumer, "consumer-A");
        Thread b = new Thread(consumer, "consumer-B");
        a.start();
        b.start();

        for (int i = 1; i <= 4; i++) {
            queue.put(new Work(i, false));
        }
        queue.put(STOP); // One pill for either consumer A or B.
        queue.put(STOP); // Second pill for the remaining consumer.

        a.join();
        b.join();
        System.out.println("Processed: " + processed.get());
        System.out.println("Remaining: " + queue.size());
    }
}
~~~

~~~bash
javac MultipleConsumersShutdownDemo.java
java MultipleConsumersShutdownDemo
~~~

Without unexpected interrupts or task failures, stdout:

~~~text
Processed: 4
Remaining: 0
~~~

Because the two `STOP` items are enqueued **after all four tasks** on a FIFO `ArrayBlockingQueue`, neither consumer takes `STOP` before all four work items have been taken. Each of the two consumers exits only after taking one `STOP`. `processed.incrementAndGet()` is an atomic increment; after `main` calls `join` on both, the value is 4.

**Limitations of poison pills:**
- If there are **multiple producers** and one producer sends `STOP` while another is still submitting work, consumers may stop early and miss trailing tasks. Producer completion must be coordinated before sending pills.
- If consumers fail or exit early, `put(STOP)` calls can get stuck when the queue is full and no enough consumers remain to drain it; you need a supervisor with timeouts/cancellation.
- If one consumer re-enqueues `STOP` to notify other consumers, it must be designed very carefully because ordering and duplication can be hard to reason about. With a known consumer count, one pill per consumer is usually simpler.
- You must choose a sentinel that **cannot collide with valid data**. A record with `boolean stop` in the example clearly distinguishes a stop message from normal work.

## 9. Handling task failures, completion guarantees, and backpressure

### 9.1. A queue only hands off, it does not guarantee exactly-once processing

When `take()` returns a task, that task has already been removed from the queue. If the consumer then throws an exception before finishing processing, the queue **does not automatically put the task back**. If you need retry/ack, you need a separate mechanism:
- Storage for processing state, or durable persistence if you must prevent loss on process crash.
- Bounded retry rules, idempotency, and handling of toxic tasks (*poison messages*).
- Monitoring for unexpectedly dead consumers and queue backlog growth.
- Business-level at-most-once, at-least-once, or exactly-once contracts; an in-memory `BlockingQueue` itself does not guarantee durable delivery or exactly-once across crashes.

### 9.2. Bounded queues and overload

A system with a queue capacity of 1,000 can still overload if producers generate work faster than consumers process it over a sustained period. Different policies:

| Policy | Approximate expression | Trade-off |
| --- | --- | --- |
| **Wait when full** | `put(e)` | Strong backpressure, but can block callers indefinitely |
| **Fail fast** | `if (!offer(e)) reject()` | Bounded enqueue latency, must handle rejection |
| **Wait with deadline** | `offer(e, timeout, unit)` | Can bail out on timeout, needs a fallback policy |
| **Drop** | `offer(e)` then intentionally discard | Accepts losing some events, only valid if business rules allow |
| **Scale consumer capacity** | More consumers, if workload permits | Introduces contention, ordering, resource, and operational costs |

Do not "fix" backpressure by switching to an unbounded queue and letting the backlog grow forever. That only shifts the problem from producer waiting to **memory accumulation**.

### 9.3. FIFO does not mean in-order completion

With an `ArrayBlockingQueue` and two consumers, item A may be **taken before** B, yet processing A may **finish after** B due to differing work or thread scheduling. A FIFO queue governs **dequeue order**, not completion order across multiple workers. If result ordering is required, you must use a single consumer, a sequence/reorder mechanism, or an appropriate architecture.

## 10. Common mistakes

- **"When put() returns, the consumer has finished."** False; it only means enqueue succeeded.
- **"take() also just peeks at the head of the queue."** False; it retrieves **and removes** the element.
- **"offer() will wait automatically when the queue is full."** False for the non-timed overload; it returns `false` immediately.
- **"poll() blocks until work arrives."** False; it returns `null` immediately if empty.
- **"Timed offer returned false, but the item will be submitted later automatically."** False; that element is not enqueued.
- **"BlockingQueue can store null."** False; `null` is reserved to indicate no element is present.
- **"All BlockingQueues are FIFO."** False; priority/delay/handoff queues have different semantics.
- **"An ArrayBlockingQueue of capacity 2 grows automatically."** False; capacity is fixed.
- **"Default LinkedBlockingQueue is a small safe buffer."** False; default capacity is very large, so RAM pressure must be considered.
- **"SynchronousQueue holds one waiting element."** False; internal capacity is 0, it is a direct handoff.
- **"One poison pill stops all consumers."** False; one element is taken by only one consumer.
- **"shutdown() always releases workers blocked in take()."** False without a protocol-level signal/stop path.
- **"The queue automatically makes objects inside it immutable."** False; queue communication establishes memory ordering for data prior to handoff, not protection against subsequent concurrent writes.
- **"remainingCapacity() > 0 reserves a slot."** False; the value can change right after being read.
- **"Reading queue.size() before deciding to enqueue/dequeue is atomic."** False; that is a racy check–then–act.
- **"Queues do not need timeout/interrupt management."** False for blocking operations.
- **"Once a consumer takes a task, the queue guarantees exactly-once processing even on crash."** False; separate error-handling/durable storage is required.

## 11. Design and testing checklist

1. **Define the purpose:** is the queue for buffering work or direct handoff? Do you need FIFO, priority, or delay?
2. **Choose capacity:** allowable peak backlog, memory budget, producer/consumer rates, full-queue policy.
3. **Choose API by requirement:** `put` if waiting is acceptable; `offer` to reject fast; timed `offer` if there is a deadline; `take` to wait for work; timed `poll` to periodically check liveness.
4. **Handle every outcome:** check `offer` returning `false`, `poll` returning `null`, and handle `InterruptedException` and timeouts as distinct states.
5. **Define message ownership:** producer finishes preparing before enqueueing and avoids concurrent modification after handoff; consider immutable records.
6. **Define shutdown protocol:** which producer signals completion? Who places poison pills? How many consumers exist? What happens if a worker fails or is cancelled?
7. **Define processing guarantees:** are ack, retry, deduplication, idempotency, or durable persistence needed?
8. **Measure and monitor:** queue length, enqueue/dequeue wait time, throughput, active consumer count, backlog growth rate.
9. **Test under adverse schedules:** full queue, empty queue, interrupted producer, dead consumer, timed offer failure, multiple producers finishing together.
10. **Do not rely on a single stress test:** verify invariants and exit paths using controlled synchronization points.

### Quick code-review checklist

| If you see | Ask |
| --- | --- |
| `queue.put(item)` inside a `synchronized` block | Is there a risk of blocking on the queue while holding a lock the consumer needs? |
| `if (!queue.offer(item)) { }` | Is the rejected work handled or silently lost? |
| `while (queue.poll() == null)` | Is there a CPU-burning busy spin? |
| `queue.take()` in an infinite worker loop | Who will wake/stop it when the system shuts down? |
| A single sentinel with multiple consumers | How will the remaining consumers exit? |
| `LinkedBlockingQueue<>()` without capacity | Is there a risk of backlog consuming too much memory? |
| `queue.size()` used to decide exact remaining space | Can this value change between check and action? |
| Worker creates an object and mutates it after `put` | Is there a data race on the mutable object? |

## 12. Self-check questions

**1.** An `ArrayBlockingQueue<Integer>` has capacity 1 and currently contains 10. What does `offer(20)` return?  
**Answer:** `false` immediately, because there is no remaining capacity. `put(20)` would wait until space is available (or until interrupted).

**2.** The queue is empty. How do `poll()` and `take()` differ?  
**Answer:** `poll()` returns `null` immediately; `take()` waits for an element and can be interrupted.

**3.** `poll(100, MILLISECONDS)` times out without an item. What does it return?  
**Answer:** `null`. If the thread is interrupted while waiting, it may throw `InterruptedException`.

**4.** After `put(task)`, can the producer conclude the consumer has successfully processed the task?  
**Answer:** No. `put` only confirms successful enqueue; a separate ack/result is needed to know business processing status.

**5.** Why shouldn't `null` be inserted into a `BlockingQueue`?  
**Answer:** Because `poll`/`peek` use `null` to indicate empty; the API forbids `null` elements.

**6.** Three consumers are waiting on `take()` and the producer finishes. Is one `STOP` message enough to stop all three?  
**Answer:** No. One message is taken by only one consumer. If using poison pills, typically send three pills after all producers have finished.

**7.** How many waiting items can `SynchronousQueue` hold?  
**Answer:** Zero. Each successful send must meet a corresponding receive operation.

**8.** Is `new LinkedBlockingQueue<>()` a small bounded queue?  
**Answer:** No. Its default declared bound is `Integer.MAX_VALUE`, so you should consider configuring a capacity to avoid memory accumulation.

**9.** A producer initializes `Message.value = 42`, puts the object into a `BlockingQueue`, and a consumer takes it. Is visibility of the write before enqueue guaranteed?  
**Answer:** Yes, by the memory consistency effects of concurrent collections, provided the protocol is proper and there are no subsequent concurrent writes.

**10.** If a FIFO queue has two consumers and task A is taken before B, is A guaranteed to finish before B?  
**Answer:** No. Dequeue order does not imply parallel processing completion order.

**11.** If `offer(e, 1, SECONDS)` returns `false`, will the queue automatically submit `e` when space opens up later?  
**Answer:** No. The caller must decide whether to retry or use a fallback.

**12.** If a system needs work to survive a JVM crash, is an in-memory `BlockingQueue` enough?  
**Answer:** No. You need durable storage/ack/recovery according to business requirements; the queue only handles in-JVM coordination.

**Key takeaway:** `put/take` are **blocking** operations; non-timed `offer/poll` are **immediate attempts**; timed `offer/poll` are **bounded waits**. Choose capacity and backpressure policies explicitly, handle interrupts and shutdown proactively, and do not confuse **successful enqueue/dequeue** with **successful business processing**.

### Official references

- Java SE 17 `BlockingQueue` (table of four operation groups and memory consistency): https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/concurrent/BlockingQueue.html
- Java SE 17 `ArrayBlockingQueue`: https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/concurrent/ArrayBlockingQueue.html
- Java SE 17 `LinkedBlockingQueue`: https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/concurrent/LinkedBlockingQueue.html
- Java SE 17 `SynchronousQueue`: https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/concurrent/SynchronousQueue.html
- Java SE 17 `java.util.concurrent` package: https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/concurrent/package-summary.html
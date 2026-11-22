# TransferQueue and BlockingDeque: Direct Handoff and Double-Ended Operations

In Java Concurrency, `BlockingQueue<E>` allows multiple threads to pass data through a queue with built-in synchronization and waiting mechanisms. Two extended interfaces address specialized problems:

- **`TransferQueue<E>`** adds the concept of **transferring to a consumer**: a producer can choose between enqueuing an element normally and **waiting until a consumer actually receives that element**.
- **`BlockingDeque<E>`** (double-ended queue) adds **two ends for insertion/removal**: producers and consumers can add/take from either the head or the tail, following FIFO, LIFO, or a simple application-defined priority protocol.

Common JDK implementations:

- `LinkedTransferQueue<E>`: a concurrent queue with no configurable bounded capacity, implementing `TransferQueue<E>`.
- `LinkedBlockingDeque<E>`: a concurrent deque that can be **bounded** by a capacity in the constructor; if omitted, the capacity per the API is `Integer.MAX_VALUE`.

These two interfaces **differ from `SynchronousQueue`** and do not replace every other `BlockingQueue`. Using them correctly requires understanding **enqueue**, **dequeue**, **handoff**, **processing completion**, **backpressure**, **execution order**, and **lifecycle**. This article focuses exclusively on Java/JDK concurrency, using standalone Java 17+ examples with no external framework dependencies.

## 1. From BlockingQueue to Two Extension Mechanisms

Consider a simple producer–consumer pipeline:

```text
Producer                  Queue                    Consumer
---------                 -----                    --------
create item ----------->  store or handoff  ---->  receive item
                                                     |
                                                     v
                                               business processing
```

There are **three distinct milestones**:

1. **Enqueued:** the queue has accepted the item, though a consumer has not necessarily received it.
2. **Taken by a consumer:** a consumer has performed a valid receive operation; processing is not necessarily finished.
3. **Processing completed:** the consumer has finished the business logic and corresponding cleanup.

`TransferQueue.transfer(e)` supports waiting up to **milestone 2**, and **does not automatically create an acknowledgement for milestone 3**. `BlockingDeque` does not add acknowledgement; it adds **the choice of which end** to send to or receive from.

When there are multiple producers/consumers, choosing the end and the timing of handoff is part of synchronization design. These concepts should not be equated with "a Future task has completed" or "a transaction has committed".

## 2. What Is TransferQueue?

`TransferQueue<E>` **extends `BlockingQueue<E>`**. It retains familiar methods such as `offer`, `put`, `take`, and `poll`, while adding:

| TransferQueue API | Meaning |
|---|---|
| `transfer(e)` | Transfers the element to a consumer, **waiting** until a consumer receives it. May be interrupted. |
| `tryTransfer(e)` | Transfers directly **only** if a matching consumer is waiting; does not block. Returns `true` if transferred, `false` if no one can receive immediately. |
| `tryTransfer(e, timeout, unit)` | Waits up to the given duration for a consumer to receive, returning `true` on handoff, `false` on timeout. May throw `InterruptedException`. |
| `hasWaitingConsumer()` | Returns whether a consumer may be waiting to receive directly, **as a point-in-time snapshot**. |
| `getWaitingConsumerCount()` | **Estimated** number of waiting consumers, used for monitoring/heuristics, not for guaranteeing a subsequent transaction. |

The `take()` and `poll()` methods of `BlockingQueue` remain on the **consumer** side. If a producer calls `transfer(e)` while no consumer is present, it may have to wait and the element may be registered in the queue for a consumer to take later; only when a consumer takes it can the transfer complete.

### offer(), put(), and transfer() Are Not Equivalent

A `LinkedTransferQueue<String>` can accept an element via:

```java
queue.offer("event");      // Enqueue; does not wait for consumer to process/take.
queue.put("event");        // With LinkedTransferQueue, does not block because the queue is full.
queue.transfer("event");   // Waits for a consumer to receive the element.
```

This is a snippet that requires declaring `queue` and handling `InterruptedException`. All three deliver data to a consumer under the contract, but **how the producer knows when it may proceed differs**. Do not read `transfer()` as "wait for the consumer to finish processing": the consumer may spend a long time computing after taking the element.

### Conditions of tryTransfer(e)

`tryTransfer(e)` without a timeout is a **non-blocking** operation. If no consumer can receive immediately:

- Returns `false`.
- **Does not store the item in the queue**.
- Does not create a deferred send that will automatically happen when a consumer appears.

This is a major difference from `offer(e)` on `LinkedTransferQueue`: `offer` can enqueue even when no consumer is present, whereas non-blocking `tryTransfer` only succeeds if an immediate transfer is possible.

## 3. LinkedTransferQueue: Unbounded, Direct When Possible

`LinkedTransferQueue<E>` is a thread-safe implementation of `TransferQueue<E>`, supporting multiple producers and consumers. Key properties:

- **No capacity constructor** to set a bound like `ArrayBlockingQueue<>(capacity)`.
- `remainingCapacity()` is `Integer.MAX_VALUE` per the unbounded queue contract; **this does not mean infinite memory**.
- `offer()` and `put()` do not block due to full capacity; if backlog grows excessively, there is still a risk of running out of memory.
- `transfer()` provides a mechanism to **wait for a consumer to receive**, which is a different form of synchronization from regular enqueuing.
- Non-blocking `tryTransfer()` fits scenarios where you only want to send if a consumer is already ready.
- Inspections such as `hasWaitingConsumer()`, `getWaitingConsumerCount()`, and `size()` are observations that **can change immediately** upon reading; `size()` on a concurrent linked queue may require traversing nodes and should not be used as a correctness condition for a transaction.
- Iterators are **weakly consistent**: they do not throw `ConcurrentModificationException` solely due to concurrent updates, but you should not expect a fixed snapshot while threads are modifying the queue.

**Do not use** `if (queue.hasWaitingConsumer()) queue.tryTransfer(e)` as a guarantee against failure: the consumer may be woken up or take another item before the `tryTransfer` call. If the requirement is "transfer if immediately possible", rely solely on **the return value of `tryTransfer`**.

## 4. Example 1 — How Do tryTransfer() and transfer() Differ?

The first program attempts `tryTransfer` while no consumer exists; the attempt must fail without enqueuing. It then creates a producer that calls `transfer()`, while `main` acts as the consumer and receives via `take()`.

Create the file **`TransferQueueBasics.java`**:

```java
import java.util.concurrent.CountDownLatch;
import java.util.concurrent.LinkedTransferQueue;
import java.util.concurrent.TransferQueue;
import java.util.concurrent.atomic.AtomicBoolean;

public class TransferQueueBasics {
    public static void main(String[] args) throws InterruptedException {
        TransferQueue<String> queue = new LinkedTransferQueue<>();
        System.out.println("Immediate transfer: "
                + queue.tryTransfer("not-sent"));
        System.out.println("Queue empty: " + queue.isEmpty());

        CountDownLatch producerEntered = new CountDownLatch(1);
        AtomicBoolean transferReturned = new AtomicBoolean();

        Thread producer = new Thread(() -> {
            producerEntered.countDown();
            try {
                queue.transfer("payload");
                transferReturned.set(true);
            } catch (InterruptedException e) {
                Thread.currentThread().interrupt();
            }
        }, "producer");

        producer.start();
        producerEntered.await();

        String received = queue.take();
        producer.join();

        System.out.println("Received: " + received);
        System.out.println("Transfer returned: "
                + transferReturned.get());
        System.out.println("Remaining: " + queue.size());
    }
}
```

```bash
javac TransferQueueBasics.java
java TransferQueueBasics
```

Output on a normal run with no external interrupt:

```text
Immediate transfer: false
Queue empty: true
Received: payload
Transfer returned: true
Remaining: 0
```

**Why is the output deterministic?**

1. `tryTransfer("not-sent")` is called before any consumer exists, so it returns `false` and does not retain the item.
2. The producer starts and calls `transfer("payload")`. `main` may call `take()` before or after the exact moment the producer enters `transfer`; in both cases they pair up successfully once both sides are present.
3. `producer.join()` waits for the producer to finish, so `transferReturned` is guaranteed to be `true` after a successful handoff.
4. `size() == 0` because the only item has been taken by the consumer. There is no guarantee about how many milliseconds the producer blocks; thread scheduling is non-deterministic.

In real systems, the producer should handle interruption and timeouts if handoff might wait a long time. The demo is intentionally simple to observe the contract.

## 5. Timed Transfer: Bounding the Wait for a Consumer

If you are unsure whether a consumer will appear, use:

```java
boolean accepted = queue.tryTransfer(
        message, 500, TimeUnit.MILLISECONDS);
```

This is a snippet; `queue` and `message` must be declared, and `InterruptedException` must be caught or thrown. If no consumer receives the item before the timeout expires, the method returns `false`. If handoff occurs, it returns `true`. This timeout limits **waiting for a consumer to receive**, not how long the consumer takes to process.

### Example 2 — Timed tryTransfer Fails Then Succeeds

The program first waits a very short time while **no consumer has been created**, ensuring no receiver exists. It then starts a consumer and uses a timed transfer so the two sides meet regardless of whether the consumer enters `take()` earlier or later than the producer.

Create the file **`TransferQueueTimeout.java`**:

```java
import java.util.concurrent.CountDownLatch;
import java.util.concurrent.LinkedTransferQueue;
import java.util.concurrent.TimeUnit;
import java.util.concurrent.TransferQueue;
import java.util.concurrent.atomic.AtomicReference;

public class TransferQueueTimeout {
    public static void main(String[] args) throws InterruptedException {
        TransferQueue<String> queue = new LinkedTransferQueue<>();

        boolean noConsumer = queue.tryTransfer(
                "ignored", 30, TimeUnit.MILLISECONDS);
        System.out.println("Transfer without consumer: "
                + noConsumer);

        CountDownLatch ready = new CountDownLatch(1);
        AtomicReference<String> received = new AtomicReference<>();

        Thread consumer = new Thread(() -> {
            ready.countDown();
            try {
                received.set(queue.take());
            } catch (InterruptedException e) {
                Thread.currentThread().interrupt();
            }
        }, "consumer");

        consumer.start();
        ready.await();

        boolean transferred = queue.tryTransfer(
                "delivered", 5, TimeUnit.SECONDS);
        consumer.join();

        System.out.println("Timed transfer succeeded: "
                + transferred);
        System.out.println("Consumer received: "
                + received.get());
        System.out.println("Queue empty: " + queue.isEmpty());
    }
}
```

```bash
javac TransferQueueTimeout.java
java TransferQueueTimeout
```

Output on a normal run, assuming the consumer is scheduled within the five-second window:

```text
Transfer without consumer: false
Timed transfer succeeded: true
Consumer received: delivered
Queue empty: true
```

**Explanation:** there is no consumer during the first timed transfer call, so it returns `false` and does not enqueue. On the second attempt, `main` is allowed to wait up to five seconds for the consumer to take the item; `ready` indicates the consumer has started, though it does not by itself prove the consumer has entered `take()` at that exact instant. The timed transfer handles **waiting for the pairing**. If the consumer does not get CPU time within the timeout, the method can still return `false`, because a timeout **does not guarantee the other side runs on schedule**; that is why the example explicitly states the scheduling assumption.

Do not rely on `Thread.sleep()` to "wait until the consumer is waiting" and then call non-timed `tryTransfer()`. That creates a racy test. If you need to ensure transfer when the consumer arrives, use `transfer()` or the timed variant with timeout handling.

## 6. Handoff Does Not Mean Business Completion

A producer calling `transfer(item)` can return as soon as the consumer **receives** the item, even while the consumer has just started processing and has not finished.

```text
Producer                         Consumer
--------                         --------
transfer(item) ----- handoff ---> take()
    |                                |
    v                                v
 returns                      process(item) ... still running
```

When you need confirmation that the consumer **has finished processing**, you must add an acknowledgement mechanism such as `CompletableFuture`, `CountDownLatch`, a dedicated `Future`, a result message, or a business-layer transaction. Do not equate a queue transfer with completing a transaction outside the JVM.

### Example 3 — Transfer Returns Before the Consumer Finishes Processing

Create the file **`TransferIsNotProcessing.java`**:

```java
import java.util.concurrent.CountDownLatch;
import java.util.concurrent.LinkedTransferQueue;
import java.util.concurrent.TransferQueue;
import java.util.concurrent.atomic.AtomicBoolean;
import java.util.concurrent.atomic.AtomicReference;

public class TransferIsNotProcessing {
    public static void main(String[] args) throws InterruptedException {
        TransferQueue<String> queue = new LinkedTransferQueue<>();
        CountDownLatch received = new CountDownLatch(1);
        CountDownLatch transferReturned = new CountDownLatch(1);
        CountDownLatch finishProcessing = new CountDownLatch(1);
        AtomicReference<String> item = new AtomicReference<>();
        AtomicBoolean processed = new AtomicBoolean();

        Thread producer = new Thread(() -> {
            try {
                queue.transfer("job");
                transferReturned.countDown();
            } catch (InterruptedException e) {
                Thread.currentThread().interrupt();
            }
        }, "producer");

        Thread consumer = new Thread(() -> {
            try {
                item.set(queue.take());
                received.countDown();
                finishProcessing.await();
                processed.set(true);
            } catch (InterruptedException e) {
                Thread.currentThread().interrupt();
            }
        }, "consumer");

        producer.start();
        consumer.start();

        received.await();
        transferReturned.await();

        System.out.println("Received: " + item.get());
        System.out.println("Processed at handoff: "
                + processed.get());

        finishProcessing.countDown();
        producer.join();
        consumer.join();

        System.out.println("Processed after release: "
                + processed.get());
    }
}
```

```bash
javac TransferIsNotProcessing.java
java TransferIsNotProcessing
```

Output on a normal run:

```text
Received: job
Processed at handoff: false
Processed after release: true
```

`main` waits for both signals: the consumer has received the item and `transfer()` has returned for the producer. However, `finishProcessing` is still closed, so the consumer **cannot set `processed=true` yet**. Only after `main` opens the latch and calls `join()` on the consumer is processing confirmed complete. Key takeaway: **the queue confirms receipt of the item, not business processing**.

In production, if processing can fail, record success/failure status separately rather than using a single boolean. If a consumer crashes right after receiving an item, the producer may have already completed `transfer()` while the work remains unfinished; retry or acknowledgement is needed according to the system contract.

## 7. How Does TransferQueue Differ from SynchronousQueue?

Both involve the concept of a producer meeting a consumer, but they are **not the same**.

| Feature | `LinkedTransferQueue` | `SynchronousQueue` |
|---|---|---|
| Can hold a backlog? | **Yes**, when using `offer()`/`put()` or when transferred elements are waiting for a receiver. | **No**, capacity is 0. |
| `put(e)` | Inserts the element without waiting for a consumer due to a full queue. | Waits for a consumer to receive directly. |
| Non-timed `offer(e)` | Usually enqueues successfully if resources suffice. | Succeeds only if a matching consumer is immediately available. |
| `transfer(e)` | Yes; waits for a consumer to receive. | No method named `transfer`; `put(e)` performs handoff. |
| `tryTransfer(e)` | Yes; sends only if a consumer is waiting. | No method named `tryTransfer`; `offer(e)` has similar handoff semantics for immediate receipt. |
| `remainingCapacity()` | `Integer.MAX_VALUE`. | 0. |
| When no consumer is present | `offer` can leave a backlog; `transfer` will wait. | `put` waits, `offer` fails. |

**Choose by contract:** if you need flexibility between normal enqueuing and waiting for a consumer to actually receive → `TransferQueue`. If you need to **forbid all backlog** and allow only paired handoff → `SynchronousQueue`.

Do not treat the absence of a consumer as an automatic reason to pick `TransferQueue`: if the application needs resource limits and cannot accept an unbounded backlog, you must add your own backpressure mechanism or choose a bounded queue.

## 8. What Is BlockingDeque?

A `Deque<E>` (double-ended queue) allows adding or removing elements from **both the head and the tail**. `BlockingDeque<E>` **extends `BlockingQueue<E>` and `Deque<E>`**, adding methods that can block when the input end is full or the output end is empty.

Visualization:

```text
                   LinkedBlockingDeque
       HEAD                                 TAIL
        |                                     |
putFirst(v) --> [urgent] [normal1] [normal2] <-- putLast(v)
takeFirst() <-- [urgent] [normal1] [normal2] --> takeLast()
        ^                                     ^
       head                                  tail
```

Producers can insert at the head/`HEAD` so consumers taking from the head receive those items sooner. Alternatively, a thread can use `push`/`pop` to simulate a LIFO stack. **This is a choice of retrieval order in the deque, not an automatic CPU priority mechanism of the Java scheduler.**

## 9. Double-Ended API Table of BlockingDeque

| Operation | Head (first/head) | Tail (last/tail) |
|---|---|---|
| Insert, throws on full | `addFirst(e)` | `addLast(e)` |
| Insert non-blocking, returns boolean | `offerFirst(e)` | `offerLast(e)` |
| Insert, waits for space | `putFirst(e)` | `putLast(e)` |
| Insert, waits up to timeout | `offerFirst(e, timeout, unit)` | `offerLast(e, timeout, unit)` |
| Remove, throws on empty | `removeFirst()` | `removeLast()` |
| Remove non-blocking, returns null on empty | `pollFirst()` | `pollLast()` |
| Remove, waits for item | `takeFirst()` | `takeLast()` |
| Remove, waits up to timeout | `pollFirst(timeout, unit)` | `pollLast(timeout, unit)` |
| Examine, does not remove | `peekFirst()` | `peekLast()` |
| Remove one occurrence | `removeFirstOccurrence(e)` | `removeLastOccurrence(e)` |

Behavior across non-blocking/timed overloads differs when the queue is **full** or **empty**, following `BlockingQueue` conventions. For a bounded queue, `offerFirst`/`offerLast` return `false` when full; `putFirst`/`putLast` wait for space; `takeFirst`/`takeLast` wait for an item.

### Which End Do Inherited BlockingQueue Methods Use?

When using a `BlockingDeque` as a `BlockingQueue`, the standard methods follow these conventions:

- `add(e)`, `offer(e)`, `put(e)` correspond to **inserting at the tail** (`addLast`/`offerLast`/`putLast`).
- `remove()`, `poll()`, `take()` correspond to **removing from the head** (`removeFirst`/`pollFirst`/`takeFirst`).
- `element()`, `peek()` examine the **head**.

Therefore, using regular `put()` and `take()` on a deque gives a FIFO path in the order of successful enqueues, while using `push()`/`pop()` gives a LIFO path.

## 10. LinkedBlockingDeque: Bounded, Double-Ended, and Thread-Safe

`LinkedBlockingDeque<E>` is a linked-node implementation supporting concurrent insertion and removal at both ends by multiple threads:

```java
BlockingDeque<String> bounded = new LinkedBlockingDeque<>(100);
BlockingDeque<String> defaultCapacity = new LinkedBlockingDeque<>();
```

This is a snippet; you must import `java.util.concurrent.BlockingDeque` and `LinkedBlockingDeque`.

- The constructor with `capacity` sets an **element count limit** (must be greater than 0) applied **jointly across both ends**.
- The no-arg constructor has capacity `Integer.MAX_VALUE` per contract; this does not mean infinite memory.
- Both ends **share a single total capacity**; each end does not have its own separate capacity.
- There is no built-in priority comparator for the deque; the application decides which end to insert into and which end to take from.
- There is no fairness constructor equivalent to `ArrayBlockingQueue(capacity, true)`; you cannot assume fair ordering among waiting producers/consumers.
- `null` is not permitted; `pollFirst/Last()` returns `null` to indicate no element is available.
- Iterators are weakly consistent with respect to concurrent modifications and must not be treated as immutable snapshots.
- There is no hard guarantee that every task inserted at the head will **finish before** tasks at the tail: consumers may already have taken other items or be mid-processing.

If capacity is small, the deque can exert backpressure at both the head and the tail. However, you must still explicitly manage priority between work classes: **continuously inserting at the head** can cause items waiting at the tail to suffer **starvation**.

## 11. Example 4 — FIFO, LIFO, and Double-Ended Operations

Use a single thread to verify exact ordering: place "urgent" at the head, "normal" at the tail, attempt to insert when capacity is full, take from both ends, and then use `push`/`pop` like a stack.

Create the file **`BlockingDequeBasics.java`**:

```java
import java.util.concurrent.LinkedBlockingDeque;

public class BlockingDequeBasics {
    public static void main(String[] args) throws InterruptedException {
        LinkedBlockingDeque<String> deque =
                new LinkedBlockingDeque<>(3);

        System.out.println("Add normal1: "
                + deque.offerLast("normal1"));
        System.out.println("Add urgent: "
                + deque.offerFirst("urgent"));
        System.out.println("Add normal2: "
                + deque.offerLast("normal2"));
        System.out.println("Add overflow: "
                + deque.offerFirst("overflow"));

        System.out.println("Take first: " + deque.takeFirst());
        System.out.println("Take last: " + deque.takeLast());
        System.out.println("Take remaining: " + deque.takeFirst());

        deque.push("one");
        deque.push("two");
        System.out.println("Pop 1: " + deque.pop());
        System.out.println("Pop 2: " + deque.pop());
        System.out.println("Remaining: " + deque.size());
    }
}
```

```bash
javac BlockingDequeBasics.java
java BlockingDequeBasics
```

Output:

```text
Add normal1: true
Add urgent: true
Add normal2: true
Add overflow: false
Take first: urgent
Take last: normal2
Take remaining: normal1
Pop 1: two
Pop 2: one
Remaining: 0
```

**Explanation:** after three `offer` calls, the deque from HEAD to TAIL is `[urgent, normal1, normal2]`. The queue is full, so `offerFirst("overflow")` does not change the order. `takeFirst` removes `urgent`, `takeLast` removes `normal2`, leaving `normal1` in the middle. Next, `push("one")` places `one` at the head, and `push("two")` places `two` ahead of `one`; `pop()` removes from the head, yielding `two` then `one`.

LIFO here is the behavior of **a deque used as a stack**, not an API that suddenly turns everything into LIFO. Using regular `offerLast()` and `takeFirst()` provides FIFO ordering.

## 12. How Do push()/pop() Differ from addFirst()/removeFirst()?

`Deque.push(e)` is semantically equivalent to **`addFirst(e)`**, and `pop()` is equivalent to **`removeFirst()`**. These APIs **do not take a timeout parameter**. On a bounded `LinkedBlockingDeque`, if full, `push`/`addFirst` may throw `IllegalStateException`; if empty, `pop`/`removeFirst` may throw `NoSuchElementException`.

When you need to block and wait for space/data, use `putFirst()` and `takeFirst()`. When you only want to try once without blocking, use `offerFirst()` and `pollFirst()`.

Distinguish between:

```java
deque.push(item);       // Add to head; may throw if full.
deque.offerFirst(item); // Add to head; returns false if full.
deque.putFirst(item);   // Add to head; may block if full.
```

This is a snippet with `deque` and `item` already declared; `putFirst` may throw `InterruptedException`. These choices matter when a producer must not block on an event loop or request thread.

## 13. Example 5 — putFirst() Blocks When a Bounded Deque Is Full

The program uses a deque with `capacity=1`; `main` inserts `"existing"` first. The producer tries `putFirst("urgent")` but there is no space, so it must wait for `main` to take the old item. The goal is to illustrate **backpressure** when head and tail share capacity.

Create the file **`BlockingDequeBackpressure.java`**:

```java
import java.util.concurrent.CountDownLatch;
import java.util.concurrent.LinkedBlockingDeque;
import java.util.concurrent.atomic.AtomicBoolean;

public class BlockingDequeBackpressure {
    public static void main(String[] args) throws InterruptedException {
        LinkedBlockingDeque<String> deque =
                new LinkedBlockingDeque<>(1);

        deque.putLast("existing");
        CountDownLatch producerEntered = new CountDownLatch(1);
        AtomicBoolean producerFinished = new AtomicBoolean();

        Thread producer = new Thread(() -> {
            producerEntered.countDown();
            try {
                deque.putFirst("urgent");
                producerFinished.set(true);
            } catch (InterruptedException e) {
                Thread.currentThread().interrupt();
            }
        }, "producer");

        producer.start();
        producerEntered.await();

        String old = deque.takeLast();
        producer.join();
        String urgent = deque.takeFirst();

        System.out.println("Removed old: " + old);
        System.out.println("Received next: " + urgent);
        System.out.println("Producer finished: "
                + producerFinished.get());
        System.out.println("Queue empty: " + deque.isEmpty());
    }
}
```

```bash
javac BlockingDequeBackpressure.java
java BlockingDequeBackpressure
```

Output on a normal run:

```text
Removed old: existing
Received next: urgent
Producer finished: true
Queue empty: true
```

**Why?** When the producer starts, the deque still holds `existing`, so `putFirst("urgent")` cannot complete until the old item is taken. `main` calls `takeLast()`, freeing the slot; the producer inserts `urgent` at the head and exits, confirmed by `join()`. Then `main` takes `urgent` and observes an empty queue.

`producerEntered` only confirms that the producer reached the point just before calling `putFirst`; it **must not be used as proof that the producer was definitely blocked** at the exact moment `main` waited. However, the `capacity=1` invariant and the existing item guarantee that `urgent` cannot be inserted before `existing` is removed, so the result does not depend on lucky thread scheduling.

## 14. Is BlockingDeque Suitable as a Priority Queue?

You can use a deque to separate simple priority levels:

```java
if (urgent) {
    deque.putFirst(job);
} else {
    deque.putLast(job);
}

// Consumer prioritizes the head:
Job next = deque.takeFirst();
```

This is a snippet; `deque`, `job`, and `urgent` must be defined, and `InterruptedException` must be handled. However, this is **not general priority scheduling**:

- Two new urgent items both call `putFirst`, so a newer urgent item can end up **ahead of** an older urgent item (LIFO within the urgent group).
- If urgent items arrive continuously, normal items at the tail can suffer **starvation**.
- A consumer may already have taken a normal item before an urgent one arrives; there is no preemption.
- Multiple consumers running in parallel may finish tasks in a different order than they were taken.
- There is no comparator to sort across multiple priority levels or deadlines.

If you need **comparator-based priority**, consider `PriorityBlockingQueue`. If you want a **reserved** number of slots for urgent work, a single bounded deque with a shared capacity does not automatically provide per-class quotas; you need a semaphore, multiple queues, or custom admission logic.

## 15. Deques and Work-Stealing: Superficially Similar, Not Equivalent to ForkJoinPool

In parallel algorithms, a deque can store tasks in a model where:

- A worker prefers processing new work at one end.
- Other workers can take work from the opposite end for load balancing.

This is the **idea of a work-stealing deque**, but **it does not mean `LinkedBlockingDeque` is the internal deque mechanism of `ForkJoinPool`**. `ForkJoinPool` has its own queue structure and scheduling mechanism optimized for `ForkJoinTask`; you cannot swap in `LinkedBlockingDeque<Runnable>` one-for-one and assume the same performance or semantics.

When building a custom scheduler using `BlockingDeque`, you must also design:

1. Worker ownership and responsibilities.
2. Policies for taking from the head/tail.
3. Queue lifecycle, shutdown/cancellation, and poison pills or closing signals.
4. Task exception/timeout handling.
5. Starvation/fairness coordination and backlog monitoring.
6. Worker, memory, and backpressure limits.

If the problem is CPU-bound divide-and-conquer recursion, prefer `ForkJoinPool` as an off-the-shelf tool rather than reinventing a work-stealing engine from `BlockingDeque`.

## 16. Deque in ThreadPoolExecutor and Pitfalls to Avoid

`ThreadPoolExecutor` accepts a `BlockingQueue<Runnable>` in its constructor. Since `BlockingDeque<Runnable>` extends `BlockingQueue<Runnable>`, you can write:

```java
ThreadPoolExecutor executor = new ThreadPoolExecutor(
        2, 4, 30, TimeUnit.SECONDS,
        new LinkedBlockingDeque<Runnable>(100),
        new ThreadPoolExecutor.AbortPolicy()
);
```

This is a snippet; you need to import `java.util.concurrent.*` and manage `shutdown()`. However, **`ThreadPoolExecutor.execute()` uses `workQueue.offer(command)` per its normal contract**, which inserts at the tail of the `BlockingDeque`; workers take via `take()`, which removes from the head. Thus the configuration above behaves like a **regular bounded FIFO work queue**, and does not automatically turn the pool into a double-ended priority scheduler.

**Directly calling `executor.getQueue().putFirst(task)` to "prioritize a task" is not recommended**: manipulating the queue directly bypasses part of `execute()`'s admission/lifecycle logic, shutdown state checks, and rejection policies. If you need a priority scheduler for an executor, design a submission/admission API with an explicit contract or use an appropriate structure/`Executor`, rather than just pushing tasks into the executor-managed deque.

Also remember: with a bounded queue, once the number of core workers is reached, the pool tries to enqueue; only when the queue cannot accept more tasks does it try to create non-core workers up to `maximumPoolSize`. With an unbounded deque, non-core workers may never be created under normal load because the queue keeps accepting tasks.

## 17. Cancellation, Interruption, and Shutdown

Both queue types have operations that can **wait indefinitely**:

- `TransferQueue.transfer(e)`: waits for a consumer to receive.
- `TransferQueue.tryTransfer(e, timeout, unit)`: bounded wait.
- `BlockingDeque.putFirst/putLast(e)`: waits for space when a bounded deque is full.
- `BlockingDeque.takeFirst/takeLast()`: waits for an element when the deque is empty.
- `BlockingDeque.offerFirst/Last(e, timeout, unit)` and `pollFirst/Last(timeout, unit)`: bounded wait.

Waiting methods can throw `InterruptedException`. Workers should:

- Accept/propagate interruption when the method contract allows it.
- If catching the exception to exit without rethrowing, typically restore the flag via `Thread.currentThread().interrupt()`.
- Not swallow the exception and loop infinitely calling `transfer` or `take`.
- Set timeouts when the caller cannot wait indefinitely.
- Clearly define cleanup for resources owned by producers/consumers.

**A subtle point:** if a producer is interrupted at the exact moment a consumer also receives an item, you must rely on the actual transaction contract rather than assuming an interrupted operation "definitely did not send". For work with side effects, use IDs/idempotency or a separate acknowledgement if safe retries are needed.

`TransferQueue` and `BlockingDeque` **do not have a unified `close()` method**. To stop workers, use a cancellation flag, interruption, sentinel/poison pill, or executor lifecycle. Poison pills must be designed for the number of consumers and the appropriate retrieval order; on a double-ended deque, inserting a sentinel at the wrong end can cause consumers to skip pending items or stop too early.

## 18. JMM: Publishing Data Safely Through a Queue

Under the memory consistency contract of `BlockingQueue`, actions occurring **before a producer puts an object into the queue** have a *happens-before* relationship with actions of the consumer **after accessing/removing that object** from the queue. This applies to compliant implementations of `TransferQueue` and `BlockingDeque`.

Illustrative example:

```java
// Producer (snippet):
Message message = new Message();
message.payload = 42;
queue.put(message);

// Consumer in another thread:
Message item = queue.take();
System.out.println(item.payload);
```

This snippet is not standalone; it requires a `Message` class, a suitable queue, and `InterruptedException` handling. Passing through the queue ensures the consumer sees the object state prepared before enqueue/handoff. However, **it does not automatically make mutations after handoff thread-safe**: if the producer continues modifying the same object while the consumer reads it, synchronization or clear ownership is still required.

Specifically:

- With `LinkedTransferQueue`, `transfer(e)` waiting for receipt does not mean the object is immutable; avoid having the producer modify it while the consumer processes it.
- With `LinkedBlockingDeque`, both ends share a synchronized collection, but the objects inside may still be mutable and require their own protocol.
- For checks like `hasWaitingConsumer()`, `size()`, and `remainingCapacity()`, do not treat the observed value as the sole gatekeeper for a competing action. Only `offer/tryTransfer/put/take` itself determines success at the moment of the operation.

If a processing result needs to be reported back to the producer, use a `Future`, latch, reply queue, or another synchronization primitive; the *happens-before* of **receiving input** does not automatically publish **processing results that have not happened yet**.

## 19. Common Mistakes

| Mistake | Why It Is Wrong | How to Fix It |
|---|---|---|
| Assuming `transfer(e)` means the consumer finished processing. | It only waits for the consumer to receive the item. | Use a separate acknowledgement for business completion. |
| Calling `tryTransfer(e)`, seeing `false`, and assuming the item will be received later. | A failed call does not enqueue. | Use `offer`, `transfer`, or the timed variant as needed. |
| Calling `offer(e)` and expecting it to wait for a consumer. | `offer` only enqueues when accepted. | Use `transfer(e)` if you need to wait for receipt. |
| Calling `hasWaitingConsumer()` and assuming `tryTransfer` will definitely return `true`. | State can change before the transfer call. | Rely on the direct return value of `tryTransfer`. |
| Assuming `LinkedTransferQueue` is bounded by constructor. | The queue has no user-configured capacity bound. | Limit producers with a semaphore/quota or use a bounded queue. |
| Using `size()` for exact admission decisions. | Snapshot race and potentially expensive traversal. | Use atomic APIs or explicit external limits. |
| Confusing `BlockingDeque.put(e)` with head insertion. | It inserts at the **tail**, like `putLast`. | Use `putFirst` when head priority is needed. |
| Thinking `push()` blocks for space when the deque is full. | `push` is equivalent to `addFirst` and may throw. | Use `putFirst` or timed `offerFirst`. |
| Thinking `pop()` blocks when the deque is empty. | `pop` is equivalent to `removeFirst` and may throw. | Use `takeFirst` or timed `pollFirst`. |
| Thinking `LinkedBlockingDeque<>(2)` has two slots per end. | Total capacity is only two. | Manage a single shared capacity for the entire deque. |
| Calling `putFirst` continuously and expecting all normal tasks to get a turn. | Tail tasks can suffer starvation. | Design explicit quotas, fairness, or aging. |
| Thinking a head-inserted task will preempt an already running task. | A deque only controls retrieval order of un-dequeued items. | Do not rely on the queue to interrupt running tasks. |
| Adding tasks directly to `executor.getQueue()`. | Bypasses executor admission/rejection/lifecycle. | Use `execute`/`submit` or a custom-designed scheduler. |
| Using a deque for work-stealing and assuming it is like `ForkJoinPool`. | `ForkJoinPool` has its own mechanism optimized for `ForkJoinTask`. | Use the right abstraction/concurrency model. |
| Swallowing `InterruptedException` and waiting forever. | Cancellation is not respected. | Propagate or restore the interrupt and exit. |
| Stopping consumers with a sentinel without considering the retrieval end. | May stop before processing remaining items. | Clearly design sentinel ordering/count and completion. |

## 20. Choosing an API by Problem

| Need | Candidate Choice | Why |
|---|---|---|
| Producer wants to enqueue immediately without waiting for consumer receipt. | `LinkedTransferQueue.offer(e)` or another suitable queue. | Does not wait for handoff. |
| Producer wants to wait until a consumer receives, without waiting for processing completion. | `TransferQueue.transfer(e)`. | Waits for receipt milestone; interruptible. |
| Send only if a consumer is currently ready. | `TransferQueue.tryTransfer(e)`. | Non-blocking; does not enqueue on failure. |
| Wait for a consumer up to N ms. | `tryTransfer(e, N, unit)`. | Handoff with timeout; must handle `false`. |
| Forbid all backlog; always hand off directly. | `SynchronousQueue`. | Capacity is 0; no storage queue. |
| Bounded backlog, need insertion/removal at both ends. | `LinkedBlockingDeque<>(capacity)`. | Double-ended and backpressure. |
| Only need bounded FIFO. | `ArrayBlockingQueue` or `LinkedBlockingQueue(capacity)`. | Simpler than a deque when two ends are not needed. |
| Need priority by comparator. | `PriorityBlockingQueue` with an explicit comparator. | A deque does not sort multiple priorities. |
| Need to wait for task completion and know success/failure. | `Future`, `CompletableFuture`, or separate acknowledgement. | Queue transfer does not represent processing outcome. |

**Core distinction:** `TransferQueue` lets the producer choose **whether to enqueue or wait for consumer receipt**; `BlockingDeque` lets producers/consumers choose **head or tail**. They solve **two orthogonal dimensions** of concurrent coordination.

## 21. Design and Testing Checklist

1. **Define completion:** enqueued, received, or processing finished?
2. **Choose transfer protocol:** `offer`/`put` for normal sending, `transfer`/`tryTransfer` for handoff.
3. **Bound waiting:** use timed transfer/timed deque operations or cancellation when deadlock/liveness risks exist.
4. **Do not infer state from snapshots:** `hasWaitingConsumer`/`size`/`remainingCapacity` are for observation only.
5. **Limit memory:** `LinkedTransferQueue` and default `LinkedBlockingDeque` can hold huge backlogs; monitor arrival and service rates.
6. **Choose deque ends:** urgent at `first`, normal at `last`, consumers take `first`; understand LIFO within urgent items and starvation.
7. **Set sensible capacity:** bounded `LinkedBlockingDeque` has a total capacity, not per-end quotas.
8. **Define ownership:** who enqueues, who consumes, who stops workers, and who cleans up?
9. **Do not retry infinitely:** `false`/timeout/interruption need explicit handling paths.
10. **Protect mutable payloads:** immutable objects/records or clear post-handoff ownership and synchronization.
11. **Manage lifecycle:** queues have no common `close`; shut down executors and await termination when you are the owner.
12. **Write coordinated tests:** use latches to avoid schedule-dependent results; test timeouts, cancellation, full queues, and disappearing consumers.
13. **Separate handoff from acknowledgement:** consumer receipt does not mean success; critical business logic needs separate confirmation.
14. **Do not confuse with ForkJoin work-stealing:** two ends are a primitive, not a complete scheduler.
15. **Measure in production:** queue depth, wait duration, backlog age, transfer timeouts, active consumers, throughput, and GC.

## 22. Self-Check Questions

1. **Which interface does `TransferQueue` extend?** `BlockingQueue<E>`.
2. **What does `transfer(e)` wait for?** Waits for a consumer to receive the element, not for processing to finish.
3. **Does a `false` return from `tryTransfer(e)` enqueue the item?** No.
4. **When does `tryTransfer(e, timeout, unit)` return `false`?** When no handoff occurs within the timeout.
5. **Does `hasWaitingConsumer()` guarantee the next `tryTransfer` succeeds?** No, because concurrent state can change.
6. **Does `LinkedTransferQueue` have a constructor-bounded capacity?** No.
7. **Does `offer(e)` on `LinkedTransferQueue` wait for a consumer?** No; it can enqueue.
8. **Are `TransferQueue` and `SynchronousQueue` the same?** No; `TransferQueue` can hold a backlog with `offer`/`put`, while `SynchronousQueue` has `capacity=0`.
9. **What are the two ends of `BlockingDeque`?** First/head and last/tail.
10. **Where does `put(e)` on `BlockingDeque` insert?** At the tail, equivalent to `putLast`.
11. **Where does `take()` on `BlockingDeque` remove from?** From the head, equivalent to `takeFirst`.
12. **Which methods are `push()`/`pop()` equivalent to?** `addFirst`/`removeFirst`; they do not block when full/empty.
13. **Does `LinkedBlockingDeque<>(3)` have three slots per end?** No, three elements in total.
14. **Why can frequent `putFirst` calls cause starvation?** Older elements at the tail are continually bypassed by newer elements.
15. **Does `BlockingDeque` automatically perform priority scheduling for `ThreadPoolExecutor`?** No; a standard executor enqueues at the tail and takes from the head.
16. **Can you add tasks via `executor.getQueue().putFirst` to prioritize them?** You should not; it bypasses executor admission/lifecycle.
17. **What *happens-before* guarantee does handoff provide?** Producer actions before putting an item into the queue *happen-before* consumer actions after taking that item.
18. **Does receiving an item mean business logic has committed?** No; a separate acknowledgement/transaction is required.
19. **What is needed to stop a worker waiting on `transfer`/`take`?** Interruption, timeout, or an appropriate lifecycle protocol.
20. **When is `LinkedBlockingDeque` better than a simple FIFO `BlockingQueue`?** When there is a clear requirement to insert/remove from both ends.

**Remember:** **`TransferQueue` controls when the producer knows a consumer has received the item; `BlockingDeque` controls insertion/removal at both ends.** Do not confuse handoff with business completion, double-ended access with automatic priority scheduling, or a thread-safe queue with always-safe mutable payloads. Choose the API based on your coordination contract, timeouts, capacity, and system lifecycle.

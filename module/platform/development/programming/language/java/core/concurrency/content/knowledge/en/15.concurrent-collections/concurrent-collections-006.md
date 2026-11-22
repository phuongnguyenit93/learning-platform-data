# ConcurrentLinkedQueue and ConcurrentLinkedDeque in Java

> **Key Takeaway:** `ConcurrentLinkedQueue<E>` is a **thread-safe FIFO queue, unbounded at the API level, using a non-blocking algorithm**; `ConcurrentLinkedDeque<E>` is a **thread-safe deque, also unbounded**, allowing insertion/removal at **both ends**. Individual operations such as `offer/poll` or `offerFirst/pollLast` can be called concurrently by multiple threads without wrapping them in an application monitor. However, **non-blocking** does not mean "automatically waits when empty", and a **thread-safe collection** does not mean every multi-step sequence, snapshot, quota, or contained object becomes atomic.

This lesson belongs to the **Concurrent Collections** group, covering **general Java concurrency** (Java SE 17+). Spring is not discussed.

## 1. Context: Why Not Just Use ArrayDeque or LinkedList?

In a producer–consumer pipeline, multiple producers submit work and multiple consumers receive it. If you share a regular `ArrayDeque`/`LinkedList` and call `add/remove` concurrently without synchronization, the program can suffer from data races, lost updates, inconsistent state visibility, or data structure corruption.

One option is to use `synchronized` around every access; another option is to choose a collection designed for concurrent access.

~~~text
Multiple producers                             Multiple consumers
    P1 ── offer(J1) ─┐                 ┌─ poll() ──> C1
    P2 ── offer(J2) ─┼─> FIFO Queue ───┤
    P3 ── offer(J3) ─┘                 └─ poll() ──> C2

Each element is dequeued at most once by one successful poll.
However, processing/completion order between C1 and C2 is not guaranteed.
~~~

`ConcurrentLinkedQueue` is suitable when multiple threads need to exchange elements by inserting at the **tail** and taking from the **head**. When you need to operate on both ends, use `ConcurrentLinkedDeque`.

**Important distinction:** Both are **non-blocking** concurrent collections; they are not `BlockingQueue` / `BlockingDeque`. When empty, `poll()` returns `null` immediately without waiting for a producer. When full in terms of actual memory, there is no preconfigured operational limit for `offer` to return `false` and create backpressure.

## 2. The Two Classes: Where Are They Similar and Different?

| Property | `ConcurrentLinkedQueue<E>` | `ConcurrentLinkedDeque<E>` |
| --- | --- | --- |
| Role | FIFO queue: add at tail, take from head | Deque: add/take at head and tail |
| Primary interface | `Queue<E>` | `Deque<E>`, also a `Queue<E>` |
| Stored data | Elements `E`, linked nodes | Elements `E`, doubly linked nodes at the interface level |
| Common operations | `offer`, `poll`, `peek` | `offerFirst`, `offerLast`, `pollFirst`, `pollLast`, `push`, `pop` |
| Accepts null? | **No** | **No** |
| Capacity bounded by API? | Unbounded | Unbounded |
| Blocking `put()` / `take()`? | **None** | **None** |
| Iterator | *Weakly consistent*, not fail-fast | *Weakly consistent*, plus `descendingIterator` |
| `size()` | O(n), not a reliable snapshot under concurrent modifications | O(n), similarly |
| Bulk operations | Not inherently atomic across the whole collection | Not inherently atomic across the whole collection |
| Best suited for | Multiple producers/consumers, non-blocking FIFO handoff | Two-ended work list, FIFO/LIFO, taking work from both ends |

"Unbounded" here means **there is no predefined finite capacity** for enqueue methods; it does not mean the JVM has infinite heap. Holding too much work can retain a large object graph and cause `OutOfMemoryError`.

### Queue and Deque Diagrams

~~~text
ConcurrentLinkedQueue:
  head                         tail
   v                            v
 [A] -> [B] -> [C] -> [D] -> [E]
  ^                           |
  | poll()                    +-- offer(F) at tail

ConcurrentLinkedDeque:
  first                         last
    v                            v
  [A] <-> [B] <-> [C] <-> [D] <-> [E]
    ^                            ^
    |                            |
 pollFirst()/offerFirst()    pollLast()/offerLast()
~~~

The diagrams illustrate the **logical API**, not the exact pointer/node details or individual CAS steps in the OpenJDK implementation. Do not infer from the drawings that every operation is O(1) under contention or internal cleanup.

## 3. Queue API: offer, poll, peek, and Exception-Throwing Methods

For `ConcurrentLinkedQueue<E>`:

| Method | Meaning | If the queue is empty |
| --- | --- | --- |
| `offer(e)` | Adds element at the tail, normally returns `true` | Not applicable; `null` is rejected |
| `add(e)` | Adds at the tail | Not applicable |
| `poll()` | Retrieves **and removes** the head element | Returns `null` |
| `peek()` | Reads the head element **without removing** it | Returns `null` |
| `remove()` (no-arg) | Retrieves and removes the head element | Throws `NoSuchElementException` |
| `element()` | Reads the head without removing it | Throws `NoSuchElementException` |
| `remove(object)` | Removes a single element matching `equals` if found | Returns boolean |
| `isEmpty()` | Checks whether empty at the moment of observation | Can change immediately after the call |

Do not confuse the two overloads `remove()` and `remove(Object)`: one removes the head and can throw an exception when empty, while the other searches for and removes an element by value.

### Example 1 — FIFO, peek, and null

Create `LinkedQueueBasics.java` (Java 17+):

~~~java
import java.util.concurrent.ConcurrentLinkedQueue;

public class LinkedQueueBasics {
    public static void main(String[] args) {
        ConcurrentLinkedQueue<String> queue =
                new ConcurrentLinkedQueue<>();

        System.out.println("offer A = " + queue.offer("A"));
        System.out.println("offer B = " + queue.offer("B"));

        System.out.println("peek = " + queue.peek());
        System.out.println("poll 1 = " + queue.poll());
        System.out.println("poll 2 = " + queue.poll());
        System.out.println("poll empty = " + queue.poll());

        try {
            queue.offer(null);
        } catch (NullPointerException expected) {
            System.out.println("null rejected = true");
        }
    }
}
~~~

Compile/run:

~~~bash
javac LinkedQueueBasics.java
java LinkedQueueBasics
~~~

Deterministic stdout:

~~~text
offer A = true
offer B = true
peek = A
poll 1 = A
poll 2 = B
poll empty = null
null rejected = true
~~~

`peek` does not remove A; `poll` removes A then B, and the next `poll` returns `null`. Prohibiting `null` as an element is necessary because the API uses `null` to indicate an empty queue. In an end-of-stream protocol, use a **non-null sentinel** with a clear type, never `null` as a poison pill.

`poll()==null` does not mean the system has run out of work forever: a producer might `offer` an item right after `poll` returns. To terminate consumers, you need a completion protocol (producer-done, sentinel, lifecycle coordinator), not just a one-time emptiness check.

## 4. Queue FIFO Is Not the Completion Order Across Multiple Consumers

FIFO states that elements **enqueued in a definite order** will be taken from the head in that order. When multiple producers `offer` concurrently, **the interleaving order between producers is not fixed**.

Example:

~~~text
Producer P1: offer(A1) -> offer(A2)
Producer P2: offer(B1) -> offer(B2)

One valid enqueue order:
 A1, B1, B2, A2
Another order:
 B1, A1, A2, B2

You must not assume all of A runs before all of B.
~~~

Within each producer, `offer` calls execute in program order; however, the total order across producers is determined by interleaving. When multiple consumers `poll` concurrently, an item taken from the queue by one consumer cannot be `poll`ed by another consumer. Even so, consumer A may process slower than consumer B; **completion order can differ from dequeue order**.

This dictates how tests should be written: verify **the set of jobs, receipt counts, and final results**, rather than printing/logging thread names and expecting a fixed schedule from the scheduler.

## 5. Example 2 — Three Producers, Two Consumers, No Lost or Duplicate Items

This example uses two consumers calling `poll` **concurrently** while three producers `offer` unique IDs. A completion flag indicates that **all producers have finished**. When the queue is temporarily empty but producers are not done yet, consumers are not allowed to exit.

Create `ConcurrentQueueWorkers.java` (Java 17+):

~~~java
import java.util.Set;
import java.util.concurrent.ConcurrentHashMap;
import java.util.concurrent.ConcurrentLinkedQueue;
import java.util.concurrent.atomic.AtomicBoolean;
import java.util.concurrent.atomic.AtomicInteger;

public class ConcurrentQueueWorkers {
    public static void main(String[] args) throws InterruptedException {
        ConcurrentLinkedQueue<Integer> work =
                new ConcurrentLinkedQueue<>();
        Set<Integer> unique = ConcurrentHashMap.newKeySet();
        AtomicBoolean producersDone = new AtomicBoolean(false);
        AtomicInteger processed = new AtomicInteger();

        Runnable consumerLogic = () -> {
            while (true) {
                Integer item = work.poll();

                if (item != null) {
                    unique.add(item);
                    processed.incrementAndGet();
                    continue;
                }
                if (producersDone.get()) {
                    return; // No more producers will send items.
                }
                Thread.yield(); // Short demo; not backpressure.
            }
        };

        Thread[] consumers = {
                new Thread(consumerLogic, "consumer-1"),
                new Thread(consumerLogic, "consumer-2")
        };
        for (Thread consumer : consumers) {
            consumer.start();
        }

        Thread[] producers = new Thread[3];
        for (int p = 0; p < producers.length; p++) {
            final int producerId = p;
            producers[p] = new Thread(() -> {
                for (int i = 0; i < 1_000; i++) {
                    work.offer(producerId * 1_000 + i);
                }
            });
            producers[p].start();
        }

        for (Thread producer : producers) {
            producer.join();
        }
        producersDone.set(true);

        for (Thread consumer : consumers) {
            consumer.join();
        }

        System.out.println("processed = " + processed.get());
        System.out.println("unique = " + unique.size());
        System.out.println("queue empty = " + work.isEmpty());
    }
}
~~~

Run:

~~~bash
javac ConcurrentQueueWorkers.java
java ConcurrentQueueWorkers
~~~

Stdout after all threads finish:

~~~text
processed = 3000
unique = 3000
queue empty = true
~~~

Each producer inserts 1,000 distinct IDs, totaling 3,000 items. Each successful `poll` removes **one** item; two consumers never receive the same item. `unique` records the set of received IDs; `processed` counts how many times items were processed. After `join`ing all producers, `main` sets the volatile/atomic flag `producersDone=true`; since no one will add more items, consumers can exit when `poll` returns `null`. `join` the consumers before summarizing.

**This is a correctness demo, not a good consumer loop pattern for production.** `Thread.yield()` has no wait-time guarantee and can cause CPU spinning. When you need to wait for items to arrive without burning CPU, you should generally use **`BlockingQueue.take()`** with a clear completion protocol. `ConcurrentLinkedQueue` is better suited when the caller has other work to do if `poll` is empty, or when the system has a controlled notification/event-loop protocol.

### What Happens Without producersDone?

If each consumer only runs `while ((item = queue.poll()) != null)`, it can exit **prematurely** before a producer has enqueued the first item, or between two enqueues. Therefore, you must separate two questions:

- "Is the queue empty at this moment?"
- "Will no producer ever emit more work?"

Only the second question determines when the pipeline can close.

## 6. Deque: Two Ends and Three Access Models

`ConcurrentLinkedDeque<E>` implements `Deque<E>`. The word *deque* stands for *double-ended queue*: users can insert or remove at both head and tail.

Key methods:

| Group | Head (`first`) | Tail (`last`) |
| --- | --- | --- |
| Insert | `addFirst(e)` / `offerFirst(e)` | `addLast(e)` / `offerLast(e)` |
| Retrieve/remove if present, return null if empty | `pollFirst()` | `pollLast()` |
| Peek without removing, return null if empty | `peekFirst()` | `peekLast()` |
| Retrieve/remove, throw exception if empty | `removeFirst()` | `removeLast()` |
| Peek, throw exception if empty | `getFirst()` | `getLast()` |
| Remove by value | `removeFirstOccurrence(o)` | `removeLastOccurrence(o)` |

`Queue.offer(e)`, `Queue.poll()`, and `Queue.peek()` when invoked on a Deque are equivalent to **offerLast / pollFirst / peekFirst** in FIFO order.

Additionally, `Deque.push(e)` is equivalent to inserting at the head, while `Deque.pop()` retrieves and removes from the head (throwing `NoSuchElementException` if empty), providing **LIFO stack** semantics.

~~~text
FIFO queue on a deque:
  offerLast(A), offerLast(B), offerLast(C)
  pollFirst() -> A, then B, then C

LIFO stack on a deque:
  push(A), push(B), push(C)   (insert at head)
  pop() -> C, then B, then A

Two-ended consumption:
  pollFirst()  -> takes head element
  pollLast()   -> takes tail element
~~~

Do not confuse `Deque`'s `push`/`pop` with the legacy `java.util.Stack`; `Deque` is the modern interface for both FIFO and LIFO. However, when multiple threads operate concurrently, do not rely on an arbitrary pop/poll order as a fixed execution schedule.

## 7. Example 3 — Using Deque as FIFO, LIFO, and Removing Duplicate Elements

Create `LinkedDequeBasics.java` (Java 17+):

~~~java
import java.util.concurrent.ConcurrentLinkedDeque;

public class LinkedDequeBasics {
    public static void main(String[] args) {
        ConcurrentLinkedDeque<String> deque =
                new ConcurrentLinkedDeque<>();

        deque.offerLast("A");
        deque.offerLast("B");
        deque.offerFirst("urgent");

        System.out.println("first = " + deque.peekFirst());
        System.out.println("last = " + deque.peekLast());

        System.out.println("pop = " + deque.pop());
        System.out.println("pollLast = " + deque.pollLast());
        System.out.println("pollFirst = " + deque.pollFirst());
        System.out.println("empty = " + deque.isEmpty());

        deque.push("one");
        deque.push("two");
        System.out.println("stack pop = " + deque.pop());

        deque.clear();
        deque.offerLast("X");
        deque.offerLast("Y");
        deque.offerLast("X");

        System.out.println("remove last X = "
                + deque.removeLastOccurrence("X"));
        System.out.println("first after remove = " + deque.pollFirst());
        System.out.println("last after remove = " + deque.pollLast());
    }
}
~~~

Run:

~~~bash
javac LinkedDequeBasics.java
java LinkedDequeBasics
~~~

Stdout:

~~~text
first = urgent
last = B
pop = urgent
pollLast = B
pollFirst = A
empty = true
stack pop = two
remove last X = true
first after remove = X
last after remove = Y
~~~

The first three items are retrieved from their exact logical positions. In the stack section, `push("two")` places it before `"one"`, so `pop()` returns `two`. After clearing and adding X, Y, X, `removeLastOccurrence("X")` removes **the trailing X**, not the leading X. This program runs sequentially so stdout is deterministic; correctness with multiple writers comes from the concurrent collection contract, not from the fact that this example only uses the main thread.

### Choosing Access Directions Consistently

If consumers always take from `pollFirst` while producers use `offerFirst` for "priority work", new jobs can continually cut ahead of older jobs and delay older jobs for a very long time. That is a **relative LIFO/priority** business policy, no longer general FIFO.

If you need true priority ordering by comparator, `PriorityBlockingQueue` or a dedicated scheduling mechanism may be more appropriate. `ConcurrentLinkedDeque` does not sort by priority and does not guarantee per-task fairness.

## 8. Example 4 — Two Consumers Taking from Opposite Ends of the Same Deque

A design might use consumer A taking from the head and consumer B taking from the tail to distribute work; each successful `pollFirst`/`pollLast` removes exactly one element. However, **do not call that a ForkJoinPool work-stealing implementation**: work-stealing has its own protocol, placement, task queues, and scheduling, not merely "one deque with two threads".

Create `TwoEndedConsumers.java` (Java 17+):

~~~java
import java.util.ArrayList;
import java.util.Collections;
import java.util.List;
import java.util.concurrent.ConcurrentLinkedDeque;
import java.util.concurrent.ConcurrentLinkedQueue;

public class TwoEndedConsumers {
    public static void main(String[] args) throws InterruptedException {
        ConcurrentLinkedDeque<Integer> deque =
                new ConcurrentLinkedDeque<>();
        for (int id = 1; id <= 10; id++) {
            deque.offerLast(id);
        }

        ConcurrentLinkedQueue<Integer> consumed =
                new ConcurrentLinkedQueue<>();

        Thread headWorker = new Thread(() -> {
            Integer id;
            while ((id = deque.pollFirst()) != null) {
                consumed.offer(id);
            }
        });
        Thread tailWorker = new Thread(() -> {
            Integer id;
            while ((id = deque.pollLast()) != null) {
                consumed.offer(id);
            }
        });

        headWorker.start();
        tailWorker.start();
        headWorker.join();
        tailWorker.join();

        List<Integer> ordered = new ArrayList<>(consumed);
        Collections.sort(ordered);

        System.out.println("consumed = " + ordered);
        System.out.println("remaining empty = " + deque.isEmpty());
    }
}
~~~

Run:

~~~bash
javac TwoEndedConsumers.java
java TwoEndedConsumers
~~~

Stdout:

~~~text
consumed = [1, 2, 3, 4, 5, 6, 7, 8, 9, 10]
remaining empty = true
~~~

To prevent output from depending on OS scheduling, the demo **pre-populates all 10 items before starting the consumers**, then sorts the result after `join`. It does not print which thread received which item: one worker may take multiple items before the other gets CPU time, yet the final set must still contain all 10 items without duplicates.

Note: if a producer can add items **after** a consumer sees the deque is empty, the loop above can still exit prematurely. In a live system, you need a completion protocol as shown in the queue section above or an appropriate blocking structure.

## 9. What Does Non-Blocking Mean?

These classes use synchronization algorithms built on primitives like CAS to support concurrent operations without requiring callers to acquire an application lock around `offer/poll`. Specifically, `ConcurrentLinkedQueue` is described in the Javadoc as using a **non-blocking** algorithm based on the work of Michael & Scott; `ConcurrentLinkedDeque` also provides thread-safe concurrent insertion/removal/access operations.

However:

- **Non-blocking is not "never waits forever" at the application level.** If you write your own loop waiting until an item arrives, that loop can still wait forever if no producer sends anything.
- **Non-blocking is not wait-free.** An individual thread may be delayed or retry under contention or scheduling; there is no guarantee it completes every operation in a fixed number of steps.
- **Non-blocking is not zero-CPU.** A tight poll loop can burn CPU even without blocking on a mutex.
- **Non-blocking is not zero-memory-cost.** Nodes/objects, garbage collection, and cache-coherence traffic still incur overhead.
- **Non-blocking does not prevent starvation.** Fairness among consumers and processing rates are not guaranteed by these classes.
- **Non-blocking is not atomic batching.** `offer(x)` and `offer(y)` are two separate operations; another thread can interleave between them.

Therefore, a concurrent queue can be very effective for the right workload, but real benchmarks still need to evaluate contention, throughput, tail latency, allocation rate, and payload retention.

## 10. When poll() Returns null and Why Busy Spinning Can Be Dangerous

`ConcurrentLinkedQueue.poll()` or `ConcurrentLinkedDeque.pollFirst()` returns `null` **immediately** when no item is found at the moment of the operation. They do not have `take()` to block and wait. If you write:

~~~java
// Warning snippet, not a complete program.
while (true) {
    Job job = queue.poll();
    if (job != null) {
        process(job);
    }
}
~~~

A consumer with no jobs will continuously poll an empty queue; it can consume a significant amount of a CPU core, interfere with other threads, and still **lack a termination protocol**.

Design approaches:

1. If the task truly means **waiting until an item is available**, use `BlockingQueue.take()` (or `BlockingDeque.takeFirst/takeLast`).
2. If non-blocking polling is needed, the caller can **do other useful work** when the queue is empty.
3. If an event loop must poll, use a bounded yield/park/backoff strategy and an appropriate **wake-up signaling mechanism**; do not rely on `Thread.sleep` as the sole latency solution.
4. If consumers need to terminate, use a proper producer-completion signal or poison pill, not just `isEmpty` checks.
5. If a task has a deadline, consider the timed `poll(timeout, unit)` of **`BlockingQueue`**, not an overload on `ConcurrentLinkedQueue` (which does not have one).

### Quick Selection Table

| Need | Suitable structure to consider |
| --- | --- |
| FIFO, non-blocking poll from multiple producers/consumers | `ConcurrentLinkedQueue` |
| Two-ended, non-blocking, no capacity limit needed | `ConcurrentLinkedDeque` |
| FIFO, consumer wants to **block when empty**, optional capacity | `LinkedBlockingQueue` |
| Bounded FIFO queue, explicit backpressure | `ArrayBlockingQueue` |
| Deque, consumer wants to block and have capacity | `LinkedBlockingDeque` |
| Direct handoff when producer and consumer meet | `SynchronousQueue` |
| Shared state by key | `ConcurrentHashMap` |
| Priority ordering needed | `PriorityBlockingQueue` (also requires its own overload design) |

There is no single structure that is "always fastest". Ordering, waiting behavior, capacity, fairness, and draining requirements are part of the business requirements.

## 11. `size()` Is O(n) and Must Not Be Used as Admission Control

`ConcurrentLinkedQueue` and `ConcurrentLinkedDeque` use linked nodes, so `size()` **is not O(1)** as in many common collections. Computing the size may have to traverse the nodes: O(n). If multiple threads add/remove concurrently, the returned count may **not reflect a consistent snapshot**.

Two common misconceptions:

- "A thread-safe queue means `size()` is always the exact count of the queue at a common point in time." No.
- "If I write `if (queue.size() < LIMIT) queue.offer(x)`, the queue is bounded." No.

Even if `size()` were exact at the moment of **reading**, between the check and the `offer`, another thread can add an item. With multiple producers, the limit is exceeded.

### Example 5 — Two Producers Both Exceeding a Fake 1-Item Limit

Create `UnsafeCapacityCheck.java` (Java 17+):

~~~java
import java.util.concurrent.ConcurrentLinkedQueue;
import java.util.concurrent.CountDownLatch;

public class UnsafeCapacityCheck {
    public static void main(String[] args) throws InterruptedException {
        ConcurrentLinkedQueue<Integer> queue =
                new ConcurrentLinkedQueue<>();
        CountDownLatch bothPassedCheck = new CountDownLatch(2);
        CountDownLatch allowEnqueue = new CountDownLatch(1);

        Runnable producer = () -> {
            if (queue.size() < 1) { // WRONG: check-then-offer is not atomic.
                bothPassedCheck.countDown();
                try {
                    allowEnqueue.await();
                } catch (InterruptedException e) {
                    Thread.currentThread().interrupt();
                    return;
                }
                queue.offer(1);
            }
        };

        Thread a = new Thread(producer);
        Thread b = new Thread(producer);
        a.start();
        b.start();

        bothPassedCheck.await();
        allowEnqueue.countDown();
        a.join();
        b.join();

        System.out.println("size after offers = " + queue.size());
        System.out.println("limit respected = " + (queue.size() <= 1));
    }
}
~~~

Run:

~~~bash
javac UnsafeCapacityCheck.java
java UnsafeCapacityCheck
~~~

Stdout when there is no external interruption:

~~~text
size after offers = 2
limit respected = false
~~~

`bothPassedCheck.await()` forces **both threads to observe `size == 0` before either is allowed to `offer`**. After the latch opens, both `offer` calls succeed and the queue holds 2 items even though the intended "limit" was 1. This is a *check-then-act* bug, not a bug in `ConcurrentLinkedQueue`'s internal CAS.

**Correct solution:** When you need finite capacity and rejection/waiting semantics, use `ArrayBlockingQueue(cap)`, `LinkedBlockingQueue(cap)`, or `LinkedBlockingDeque(cap)`. If you must use a concurrent linked structure with a `Semaphore` to bound in-flight items, you must design acquire/release-once across the entire lifecycle (producer exceptions, dequeue, cancellation, shutdown), not just rely on `size()`.

`size()` can be acceptable for **rough debugging/monitoring** when you understand its cost and accuracy, especially when the collection is **quiescent** (no concurrent mutations). It is not a synchronization primitive.

## 12. `peek()` Then `poll()`: Two Operations Are Not One Transaction

A fairly common mistake:

~~~java
// BROKEN check-then-act code with multiple consumers.
if (queue.peek() != null) {
    Job job = queue.poll();
    process(job); // job can still be null!
}
~~~

`peek()` and `poll()` are individually thread-safe, but another consumer can take the item in between. `peek()` does not reserve or lock the element for the caller. The proper pattern:

~~~java
Job job = queue.poll();
if (job != null) {
    process(job);
}
~~~

Tie your processing condition to **the result of `poll()` itself** rather than inferring from a stale `peek()`.

### Example 6 — Demonstrating the peek-then-poll Race with a Latch

Create `PeekThenPollRace.java` (Java 17+):

~~~java
import java.util.concurrent.ConcurrentLinkedQueue;
import java.util.concurrent.CountDownLatch;
import java.util.concurrent.atomic.AtomicInteger;

public class PeekThenPollRace {
    public static void main(String[] args) throws InterruptedException {
        ConcurrentLinkedQueue<Integer> queue =
                new ConcurrentLinkedQueue<>();
        queue.offer(42);

        CountDownLatch bothPeeked = new CountDownLatch(2);
        CountDownLatch allowPoll = new CountDownLatch(1);
        AtomicInteger gotItem = new AtomicInteger();
        AtomicInteger gotNull = new AtomicInteger();

        Runnable consumer = () -> {
            if (queue.peek() != null) {
                bothPeeked.countDown();
                try {
                    allowPoll.await();
                } catch (InterruptedException e) {
                    Thread.currentThread().interrupt();
                    return;
                }

                Integer item = queue.poll();
                if (item == null) {
                    gotNull.incrementAndGet();
                } else {
                    gotItem.incrementAndGet();
                }
            }
        };

        Thread a = new Thread(consumer);
        Thread b = new Thread(consumer);
        a.start();
        b.start();

        bothPeeked.await();
        allowPoll.countDown();
        a.join();
        b.join();

        System.out.println("got item = " + gotItem.get());
        System.out.println("got null = " + gotNull.get());
    }
}
~~~

Run:

~~~bash
javac PeekThenPollRace.java
java PeekThenPollRace
~~~

Stdout:

~~~text
got item = 1
got null = 1
~~~

Both consumers **saw 42 in `peek`**, yet afterward only one consumer can succeed in `poll`; the other receives `null`. Using the latch to coordinate the `poll` timing keeps the example from depending on "the scheduler occasionally getting lucky and triggering the race". Remember: **individually thread-safe methods do not compose into a thread-safe business-level transaction**.

## 13. Weakly Consistent Iterator and Spliterator

Both classes provide iterators/spliterators capable of running while another thread modifies the collection. The Javadoc calls them **weakly consistent**:

- They do not fail-fast with `ConcurrentModificationException` simply due to concurrent add/remove.
- They may observe some modifications that occur while the iterator is running.
- They are not a fixed snapshot taken at the moment the iterator is created.
- They are not guaranteed to see **every** item added after the iterator is created.
- Traversal must not be treated as atomic or as representing a single point in time for the entire result.
- `ConcurrentLinkedDeque.descendingIterator()` traverses from tail to head and is also weakly consistent.
- `spliterator()` provides parallel/partitioned traversal conforming to the contract; it does not turn a mutating source into a complete snapshot.

An example of a test you should not write is asserting an exact element count while enqueuing is in progress:

~~~java
// Illustrative snippet, not standalone.
Iterator<Integer> it = queue.iterator();
queue.offer(99);
while (it.hasNext()) {
    System.out.println(it.next()); // Do not assume 99 will or won't be seen.
}
~~~

For `ConcurrentLinkedQueue`, the iterator contract provides additional guarantees regarding elements already in the queue when the iterator was created; however, this **does not** authorize using the iterator as a mathematical snapshot of mutating data. Read the exact guarantee scope in the Javadoc rather than dismissing all behavior as "completely random".

### When Do You Want a Real Snapshot?

- If **all producers/consumers have stopped**, copying/traversing the queue when there are no more mutations yields a stable result—for example, after `join`ing all threads.
- If you want **a transactional snapshot** while writers are active, a concurrent queue alone is not enough; you need a locking/snapshot/versioning protocol or a different data model.
- If you only need approximate monitoring, you can take approximate metrics and label them as estimates.
- If you need consistent totals/inventory/billing, do not use `forEach` on a mutating queue as proof of transaction reconciliation.

### Example 7 — Traversing a Snapshot After Workers Have Stopped

Create `StableQueueTraversal.java` (Java 17+):

~~~java
import java.util.ArrayList;
import java.util.List;
import java.util.concurrent.ConcurrentLinkedQueue;

public class StableQueueTraversal {
    public static void main(String[] args) throws InterruptedException {
        ConcurrentLinkedQueue<Integer> queue =
                new ConcurrentLinkedQueue<>();

        Thread producer = new Thread(() -> {
            queue.offer(1);
            queue.offer(2);
            queue.offer(3);
        });
        producer.start();
        producer.join();

        List<Integer> snapshot = new ArrayList<>(queue);
        System.out.println("snapshot = " + snapshot);
        System.out.println("queue unchanged = " + !queue.isEmpty());
    }
}
~~~

Run:

~~~bash
javac StableQueueTraversal.java
java StableQueueTraversal
~~~

Stdout:

~~~text
snapshot = [1, 2, 3]
queue unchanged = true
~~~

This is a stable snapshot because **the producer has `join`ed and no other thread is modifying the queue**. The `new ArrayList<>(queue)` constructor itself does not create a transaction against active writers. `join` also establishes a happens-before relationship from the completed producer to `main`, in addition to the publication semantics of the concurrent queue.

## 14. Bulk Operations Are Not Atomic Across the Entire Collection

Operations such as `addAll`, `removeIf`, `forEach`, `clear`, or batch traversal/processing can interact with multiple elements. The Javadoc warns that bulk operations adding, removing, or observing multiple elements **are not guaranteed to be atomic** in the presence of concurrent modifications.

Example:

~~~java
// ILLUSTRATIVE CODE, no batch transaction.
queue.addAll(List.of("A", "B", "C"));
~~~

If a consumer is running, it may observe a subset of the added items before `addAll` returns. Do not assume "batch A, B, C appears simultaneously as a single transaction".

Similarly, `removeIf(predicate)` inspects/removes elements over a span of time; items added concurrently by a producer may fall outside the traversal or behave unexpectedly relative to your assumptions. `clear()` is not a "close queue" mechanism and does not block producers from enqueuing more items.

For cases requiring **atomic batch publication**, you can place the entire batch inside **an immutable holder object** (for example, `Queue<List<Job>>`) and offer that holder as a single element; you must design batch ownership, idempotency, memory footprint, failure policy, and business-level atomicity. A queue operation only guarantees atomicity when **placing a reference to the batch** into the queue, not executing the side effects inside the batch transactionally.

## 15. Memory Visibility and Happens-Before

Concurrent collections are designed not only to prevent structural corruption, but also to provide **memory consistency** effects for handing off objects through the collection.

According to the Java SE 17 Javadoc for `ConcurrentLinkedQueue` and `ConcurrentLinkedDeque`: actions in a thread **prior to placing an object into the collection** *happen-before* actions in another thread **subsequent to the access or removal of that element** from the collection.

~~~text
Producer:
  Task t = new Task(7, "ready");
  queue.offer(t);
      |         publication via concurrent collection
      +-------------- happens-before --------------+
                                                   |
Consumer:                                          v
  Task received = queue.poll();
  // Upon receiving t, writes prior to offer are properly published.
~~~

This is very useful for producer–consumer pipelines. There is no need to hold the same external `synchronized` lock **just to publish a fully initialized object**, provided all handoffs go through the concurrent collection according to its contract.

However, distinguish between:

- **Safe publication** of state prepared before enqueuing.
- **Post-publication mutation** of that object.

If a producer `offer`s an `ArrayList` and then continues mutating the list while a consumer reads it, the queue **does not** protect those mutations. Similarly, wrapping a mutable object in `AtomicReference<Mutable>` as an element does not make the inner mutable object thread-safe. Prefer immutable values, defensive copies, strict ownership transfer with no further writes, or dedicated synchronization for mutable state.

### Example 8 — Passing an Immutable Record Through a Queue

Create `QueueSafePublication.java` (Java 17+):

~~~java
import java.util.concurrent.ConcurrentLinkedQueue;
import java.util.concurrent.CountDownLatch;

public class QueueSafePublication {
    record Message(int id, String payload) {}

    public static void main(String[] args) throws InterruptedException {
        ConcurrentLinkedQueue<Message> queue =
                new ConcurrentLinkedQueue<>();
        CountDownLatch published = new CountDownLatch(1);

        Thread producer = new Thread(() -> {
            Message message = new Message(7, "ready");
            queue.offer(message);
            published.countDown();
        });

        producer.start();
        published.await();

        Message received = queue.poll();
        System.out.println("id = " + received.id());
        System.out.println("payload = " + received.payload());

        producer.join();
    }
}
~~~

Run:

~~~bash
javac QueueSafePublication.java
java QueueSafePublication
~~~

Stdout:

~~~text
id = 7
payload = ready
~~~

`Message` is a record containing two immutable components: a primitive and an immutable `String`. The producer constructs the record completely **before `offer`**, and the consumer receives the reference through the queue. In this example, `CountDownLatch` only coordinates timing so the output deterministically has an item; even if the consumer polls continuously and succeeds without a latch, the concurrent queue's semantics still support publication of writes occurring prior to `offer`.

Do not take this code as proof that the queue guarantees atomic transactions across **multiple** messages or recovers automatically if a producer crashes before `offer`.

## 16. Empty Queue, Producer Completion, and Graceful Shutdown

There is no built-in `close()` on `ConcurrentLinkedQueue`/`ConcurrentLinkedDeque` for polling consumers to automatically detect end-of-stream. To stop cleanly, you must define a **completion protocol**.

One model:

~~~text
RUNNING
  | producers submit work
  v
STOP_ACCEPTING
  | stop accepting new work; wait for existing producers to finish enqueuing
  v
PRODUCERS_FINISHED
  | send STOP signal or set completion flag properly
  v
DRAINING
  | consumers process received work
  v
CONSUMERS_FINISHED
  | join/ack all consumers; check failures/in-flight
  v
TERMINATED
~~~

Several options exist:

1. **Completion flag:** A coordinator waits for producers and then sets `AtomicBoolean done=true`. Consumers must not exit on a `null` poll **before** the flag is true; once the flag is true, an empty queue can serve as the termination condition. Example `ConcurrentQueueWorkers` uses this approach.
2. **Poison-pill sentinel:** After all producers finish, enqueue STOP elements per protocol; if N consumers poll concurrently, you must account for token counts/ownership and ensure every consumer receives the signal.
3. **BlockingQueue:** When consumers should wait rather than spin-poll, use `BlockingQueue.take()` with sentinel/completion logic. Handle full capacity and cancellation during shutdown.
4. **In-flight management:** A consumer may have polled an item out of the queue but not finished processing it yet. `isEmpty()` is not proof that all tasks are done; you need `join`/`Future.get`/acks from tasks.

If a consumer receives STOP and exits while items are still added by a producer **after STOP**, those items can be left behind. Therefore, close admission / wait for producers before emitting the stop signal. This is an **application-level** protocol, not an automatic property of the concurrent queue.

## 17. Backpressure and Unbounded Memory Risk

A major distinction from bounded blocking queues:

- `ConcurrentLinkedQueue.offer(e)` has no configurable limit; for valid items, it is designed to enqueue rather than return `false` when a business capacity is reached.
- `ConcurrentLinkedDeque.offerFirst/offerLast(e)` are also unbounded.
- If producers outpace consumers over a sustained period, backlogged objects can grow, increasing heap retention, GC pressure, and latency.
- Tasks may hold references to payloads, closures, or large structures; memory consumption is not just node overhead.
- If memory is exhausted, the JVM can hit `OutOfMemoryError`; this is not an easily recoverable "rejection policy".
- `isEmpty()` and `size()` do not provide atomic admission control.

Simple example: producers send an average of 10,000 items/s while consumers only process 8,000 items/s. The backlog grows by roughly 2,000 items/s during that period; after 5 minutes, roughly 600,000 items can accumulate, before even accounting for load spikes and retries. This is a directional calculation, not a hard-guarantee forecast.

**Solution direction:** use a bounded structure when pending work must be capped; apply rate limiting, explicit rejection, backpressure, in-flight limits, deadlines, or deliberate load shedding. "Non-blocking" by itself does not prevent overload.

### Do Not Use ConcurrentLinkedDeque as an Unbounded Priority Queue

Some systems call `offerFirst(urgent)` to prioritize new jobs and `offerLast(normal)` for regular jobs. This is simple, but if urgent jobs arrive continuously, normal jobs can wait indefinitely. It also does not support multiple priority levels via comparators, deadline scheduling, or fairness across categories. Evaluate work starvation and SLAs before choosing this design.

## 18. When to Choose BlockingQueue or BlockingDeque?

`ConcurrentLinkedQueue` and `ConcurrentLinkedDeque` **do not have** the `put`, `take`, or timed `offer/poll` methods provided by `BlockingQueue`. If what you need is for producers to **wait when full** and consumers to **sleep when empty**, choose a collection with the appropriate blocking semantics.

| Scenario | Suitable tool |
| --- | --- |
| A consumer that should not spin when empty | `LinkedBlockingQueue.take()` |
| Fixed capacity needed, memory control | `ArrayBlockingQueue(capacity)` |
| Two ends and blocking wait needed | `LinkedBlockingDeque(capacity)` |
| Wait at most 1 second then timeout | `BlockingQueue.poll(1, TimeUnit.SECONDS)` |
| No blocking needed, fast poll, many threads | `ConcurrentLinkedQueue.poll()` |
| Non-blocking two-ended with head/tail semantics | `ConcurrentLinkedDeque.pollFirst/pollLast` |

### Example 9 — BlockingQueue Replacing Hot Polling

Create `BlockingQueueConsumer.java` (Java 17+):

~~~java
import java.util.concurrent.ArrayBlockingQueue;
import java.util.concurrent.BlockingQueue;

public class BlockingQueueConsumer {
    public static void main(String[] args) throws InterruptedException {
        BlockingQueue<String> queue = new ArrayBlockingQueue<>(2);

        Thread worker = new Thread(() -> {
            try {
                String first = queue.take();
                String second = queue.take();
                System.out.println("received = " + first + "," + second);
            } catch (InterruptedException e) {
                Thread.currentThread().interrupt();
            }
        });

        worker.start();
        queue.put("A");
        queue.put("B");
        worker.join();
    }
}
~~~

Run:

~~~bash
javac BlockingQueueConsumer.java
java BlockingQueueConsumer
~~~

Stdout:

~~~text
received = A,B
~~~

If the queue is empty, `take()` waits until a producer sends an item or the thread is interrupted. If a bounded queue is full, `put` can also wait for capacity. This is a **blocking producer–consumer protocol**, not how `ConcurrentLinkedQueue` operates.

Do not use this example for an infinite consumer loop without a shutdown plan: `take()` can wait forever if no more producers exist. Proper sentinel/interrupt/cancellation lifecycle handling is required.

## 19. Deque and Its Limited Role in Work-Stealing

Work-stealing schedulers often use the concept of a worker owning a work deque, while other workers can steal tasks from the opposite end. `ConcurrentLinkedDeque` provides thread-safe two-ended operations, but **it is not enough on its own to build a ForkJoinPool**:

- A work-stealing scheduler needs to decide task placement, ownership, and queue ordering.
- It needs a mechanism to wake workers when work arrives, avoiding uncontrolled busy spinning.
- It needs completion counting, task dependencies, cancellation, and exception reporting.
- It needs policies for bounding memory and workload admission.
- It needs executor and worker thread lifecycle management.
- It needs control over fairness, starvation, priorities, and shutdown timing.
- It needs measurement of contention, locality, cache misses, and task push/pop overhead.

In applications, if you just need to run a recursive Fork/Join algorithm on the CPU, consider `ForkJoinPool` and `RecursiveTask` instead of building your own scheduler from a concurrent deque. `ConcurrentLinkedDeque` is useful when **two-ended control is a direct requirement of the data flow**, not because its name sounds like work-stealing.

## 20. Bulk Iteration, toArray, and Snapshot Semantics

`toArray()` or `new ArrayList<>(queue)` copies the elements traversed during execution. However, if producers/consumers are still modifying the collection:

- They **do not** automatically form a transactional snapshot.
- They may reflect states from different points in time.
- Order and count can change while traversal is underway.
- Copied objects are **references**, not deep clones. If mutable objects are still modified by another writer, copying the references does not make them immutable.
- A weakly consistent iterator does not guarantee a global snapshot suitable for financial reconciliation.

If you need a snapshot for debugging, wait for a *quiescent* point confirmed by a coordinator or use a different data structure/protocol. Do not call `size()` followed by `toArray()` and expect the two results to always match under concurrent mutation.

### `descendingIterator()` on ConcurrentLinkedDeque

`deque.descendingIterator()` traverses backward from tail to head. For example, on a deque containing `[A, B, C]` with no concurrent writers, forward order is `A, B, C`; descending order is `C, B, A`. When writers add/remove concurrently, the traversal still follows the weakly consistent contract rather than producing a snapshot.

If you need to implement business logic that "processes every element exactly once" amid concurrent updates, **an iterator is not a queue consumer protocol**. Use `pollFirst`/`pollLast` to claim ownership of an item and process it, along with an ack/completion policy.

## 21. Mutable Objects in a Queue: A Thread-Safe Container Is Not Enough

Here is a broken example:

~~~java
// Illustrative snippet, unsafe under concurrent mutation.
class MutableTask {
    int attempts;
}

ConcurrentLinkedQueue<MutableTask> queue =
        new ConcurrentLinkedQueue<>();

MutableTask task = new MutableTask();
queue.offer(task);
task.attempts++; // Producer continues mutating after publication.
~~~

If a consumer concurrently reads `attempts` or also increments `attempts`, these accesses can be a data race. `offer` guarantees publication of state **prior to** `offer` per contract; it does not automatically protect mutations **after** `offer`.

Best practices:

- Prefer **records/immutable task descriptions** such as `Message(int id, String payload)`.
- If using mutable objects, perform explicit **ownership transfer**: the producer does not modify after enqueuing; the consumer owns the object upon a successful `poll`.
- If the same object is still shared by multiple threads, synchronize internal fields with locks, atomics, or a proper protocol.
- If the consumer needs to return results to the producer, use an appropriate channel/result/`Future`/ack instead of having both mutate plain unguarded fields.
- Avoid putting references to the same mutable object into two queues and thinking each queue protects it independently.

### Do Not Confuse Visibility with Workflow Atomicity

Even if a consumer correctly sees `attempts=0` at the time of receiving an item, incrementing `attempts` concurrently with another thread can still lose updates. A queue does not turn `attempts++` into an atomic read-modify-write. Use `AtomicInteger`/locks/immutable replacements when needed.

## 22. Testing Concurrency: Verify Invariants, Avoid Relying on the Scheduler

The examples in this lesson achieve deterministic output using one of the following techniques:

- **Sequential execution:** basic API examples, making FIFO/LIFO order obvious.
- **Joining all threads:** summarizing after no producers/consumers are active.
- **Generating unique IDs and sorting results:** avoiding assumptions about which consumer gets which element.
- **CountDownLatch:** deterministically coordinating an interleaving for check-then-act bugs.
- **Immutable records:** avoiding data races on state passed through the queue.
- **Completion flag with `join`:** distinguishing a temporarily empty queue from finished producers.

Keep in mind that demos using untimed `await()` are written to clarify semantics on the normal execution path; **production test suites should use timed waits**, `try/finally` cleanup, and fail-fast checks if threads do not make progress. Do not rely on `Thread.sleep(100)` and assume a race will reliably occur.

### Metrics Worth Tracking

- Enqueued/sec and dequeued/sec, including per-end rates on a deque when meaningful.
- End-to-end work latency (submit -> start -> complete), not just poll latency.
- Pending/in-flight counts via a dedicated counter/ack protocol if accuracy is needed.
- Heap retained by queued payloads, node allocations, and GC activity.
- Consumer CPU usage when the queue is empty, especially in poll loops.
- Duplicate processing/missing jobs or business-level ack counts.
- Cancellations, retries, dead-letter counts, and shutdown duration.
- Contention and tail latency under realistic workloads.

Do not implement an exact counter using `size()` every time a dashboard refreshes; an O(n) traversal on a long queue can introduce significant overhead and still not guarantee a count synchronized with producers.

## 23. Common Mistakes

| Mistake | Consequence | Correct approach |
| --- | --- | --- |
| Using plain `ArrayDeque` with multiple writers | Data race / corruption | `ConcurrentLinkedDeque` or appropriate locking |
| Treating `ConcurrentLinkedQueue.poll()` like `take()` | Consumer spins or exits prematurely | Use a blocking collection when waiting is needed |
| Enqueuing `null` as a sentinel | `NullPointerException` | Typed non-null sentinel |
| Relying on `queue.size() < capacity` | Race, limit exceeded, O(n) | Bounded queue or admission protocol |
| `if (peek() != null) poll()` assuming non-null | Another consumer can steal it | Check the return value of `poll()` directly |
| Using `forEach`/`toArray` as an exact snapshot | Weakly consistent, concurrent modifications | Quiescent point or snapshot protocol |
| Thinking `addAll` appears atomically | Consumers may see partial batches | Enqueue an immutable batch holder in one slot or use appropriate locking |
| Mutating an object after `offer` | Data race with consumer | Immutable values or ownership transfer |
| Assuming FIFO means FIFO completion across multiple consumers | Completion order differs from dequeue order | Ack/result ordering if required |
| Infinite poll loop when empty | Burns CPU and lacks termination | `BlockingQueue.take()` or wait/notification protocol |
| Using an unbounded queue with overly fast producers | Heap, GC, and latency grow | Capacity bounds, backpressure, deadlines |
| Expecting a deque to sort priorities | Normal jobs can starve | Appropriate priority/scheduling structure |
| Relying on an iterator to "claim jobs" | Same item may be processed by multiple callers | `poll` to transfer ownership |
| Using `clear` as close/shutdown | Producers can still enqueue more items | Stop admission + completion protocol |
| Confusing active tasks with queued tasks | `isEmpty` does not mean processing is finished | Count in-flight tasks, await acks |
| Thinking non-blocking = wait-free | No step bound for individual callers | Understand progress guarantees and contention |
| Building work-stealing using only CLDeque | Missing scheduler/lifecycle/fairness | Use `ForkJoinPool` when appropriate |

## 24. Self-Check Questions

**1.** Is `ConcurrentLinkedQueue` FIFO?  
**Answer:** Yes, elements are added at the tail and polled from the head. However, if multiple producers enqueue concurrently, the interleaving order between them is not fixed.

**2.** Does `poll()` on an empty queue block until an item arrives?  
**Answer:** No. It returns `null` immediately; use `BlockingQueue.take()` if waiting is needed.

**3.** Is `ConcurrentLinkedQueue.offer(null)` allowed?  
**Answer:** No, it throws `NullPointerException`. `null` is used by `poll`/`peek` to indicate an empty queue.

**4.** Why is `size()` not a queue-bounding primitive?  
**Answer:** It is O(n), may be inaccurate under concurrent modifications, and check-then-offer is not atomic.

**5.** Can you be sure that if `peek() != null`, then `poll() != null` immediately afterward?  
**Answer:** No. Another consumer may poll that element first; you must check the return value of `poll()` directly.

**6.** Which end do `ConcurrentLinkedDeque.push(x)` and `pop()` use?  
**Answer:** The first/head end, forming a LIFO stack. `offerLast` and `pollFirst` form FIFO.

**7.** Can one consumer calling `pollFirst` and another calling `pollLast` on a deque receive the same item?  
**Answer:** A specific element cannot be successfully polled by both simultaneously; each successful removal takes one element from the deque.

**8.** Does a running iterator throw `ConcurrentModificationException` when a producer keeps adding?  
**Answer:** No, per the weakly consistent iterator contract of both concurrent collections; however, it does not form an atomic snapshot.

**9.** Is `addAll(List.of(a, b, c))` atomic across the entire batch?  
**Answer:** There is no such guarantee; a consumer may see a partial batch while the operation is in progress.

**10.** Does `ConcurrentLinkedQueue` guarantee memory visibility from producer to consumer through an element?  
**Answer:** Yes, actions before the producer places the element into the queue happen-before actions after the consumer accesses/removes that element per the API; post-publication mutations still require their own protocol.

**11.** When `queue.isEmpty()` is true, can you conclude the pipeline is done?  
**Answer:** No. Producers may send more items, or consumers may have taken items that are still being processed. A completion/ack protocol is required.

**12.** An application wants producers to wait when the queue is full, consumers to wait when empty, and a limit of 128 items. What should you choose?  
**Answer:** For example, `new ArrayBlockingQueue<>(128)` or `LinkedBlockingQueue<>(128)` with `put/take` and a shutdown protocol; do not implement a limit using `ConcurrentLinkedQueue.size()`.

**13.** When new "urgent" tasks are always `offerFirst`ed and consumers call `pollFirst`, can "normal" tasks be delayed for a long time?  
**Answer:** Yes. This is not a complete priority/fairness scheduler; starvation must be evaluated.

**14.** Does a thread-safe queue also make `job.count++` on a retrieved object thread-safe?  
**Answer:** No. You must protect mutable objects or enforce clear ownership transfer.

## Official References

- [`ConcurrentLinkedQueue` — Java SE 17](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/concurrent/ConcurrentLinkedQueue.html): FIFO, non-blocking, weakly consistent iterator, O(n) size, bulk operations, and memory consistency.
- [`ConcurrentLinkedDeque` — Java SE 17](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/concurrent/ConcurrentLinkedDeque.html): two-ended deque, non-blocking concurrency, weak iterators, size, and bulk semantics.
- [`Queue` — Java SE 17](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/Queue.html): `offer/poll/peek`, `add/remove/element`.
- [`Deque` — Java SE 17](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/Deque.html): first/last, stack, and queue mappings.
- [`BlockingQueue` — Java SE 17](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/concurrent/BlockingQueue.html): blocking/timed methods and capacity.
- [`ArrayBlockingQueue` — Java SE 17](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/concurrent/ArrayBlockingQueue.html): FIFO bounded queue.
- [`LinkedBlockingDeque` — Java SE 17](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/concurrent/LinkedBlockingDeque.html): two-ended blocking deque, optional capacity.
- [Java Language Specification 17 — Threads and Locks](https://docs.oracle.com/javase/specs/jls/se17/html/jls-17.html): Java Memory Model and happens-before.

**Key Takeaway:** `ConcurrentLinkedQueue` solves non-blocking concurrent FIFO; `ConcurrentLinkedDeque` solves concurrent operations at both ends. Neither is a blocking queue, neither has an automatic capacity limit, neither turns `size/iterator/bulk operation` into an atomic snapshot, and neither protects mutations of contained objects. When requirements involve shutdown, quotas, or multi-step workflows, design explicit protocols outside the collection itself.
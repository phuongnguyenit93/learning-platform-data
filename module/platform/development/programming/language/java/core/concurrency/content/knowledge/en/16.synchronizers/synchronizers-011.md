# When to Use BlockingQueue Instead of Manual Thread Coordination in Java

## 1. The Problem: Producer–Consumer Looks Simple, Yet Has Many Hidden Contracts

One thread produces data, and another thread processes it. For example: a log-reading thread pushes events into a queue; multiple workers wait to receive them for computation or writing results. You can write `synchronized` + `wait()/notifyAll()` or `ReentrantLock` + `Condition` yourself. However, when doing so, you are also responsible for all of the following issues:

- When the queue is empty, how does a consumer **wait** without burning CPU?
- After a producer adds an element, **who should be woken up**, and at what point?
- When multiple producers/consumers run concurrently, can the wrong group of threads be woken up?
- When the queue is full, does the producer **wait, reject, or drop data**?
- If a thread is interrupted while waiting, how must the data state and interrupt status be handled?
- Could there be a **lost notification**, checking a condition outside the lock, or using `if` instead of `while`?
- On shutdown, how will a consumer waiting in `take()` terminate?
- To what extent are **FIFO, fairness, completion ordering**, and memory visibility guaranteed?

`java.util.concurrent.BlockingQueue<E>` comes with a built-in synchronized handoff protocol between producers and consumers, along with blocking, non-blocking, and timed waiting methods. When the problem is genuinely **passing elements through a queue between threads**, using this specialized collection is usually simpler and less error-prone than writing a manual wait–notify protocol.

This lesson belongs to **Synchronizers** in **Java Advance - concurrency**, directly covering **“When to Use BlockingQueue Instead of Manual Thread Coordination”**. The scope is general Java SE 17+; Spring-specific frameworks/APIs are excluded as Spring-related topics have their own chapter.

### After this lesson, you will be able to

1. Describe what contracts `BlockingQueue` provides: handoff, wait, timeout, boundedness, visibility, and ordering.
2. Distinguish `put/take`, `offer/poll`, their timed variants, `add/remove/element`, and `null` as a sentinel value.
3. Explain why manual `wait/notifyAll` requires a `while` loop, the same monitor, state invariants, and cleanup.
4. Choose `ArrayBlockingQueue`, `LinkedBlockingQueue`, `SynchronousQueue`, `PriorityBlockingQueue`, or another queue type according to your goal.
5. Recognize cases where **you should not use a queue**, such as simply waiting for a single event, granting permits, waiting for multiple threads at a barrier, or retrieving the result of a computation.
6. Design bounded queues and backpressure instead of using an unbounded queue as a dumping ground for all backlogs.
7. Handle interruption, shutdown, poison pills for multiple consumers, cancellation, producer failures, and full queues.
8. Explain the difference between **queue dequeue order** and **work completion order**.
9. Run five standalone Java 17+ programs with deterministic, verifiable output.

## 2. What Exactly Is BlockingQueue?

`BlockingQueue<E>` is an interface extending `Queue<E>`. Beyond adding/removing/inspecting elements, it provides operations that allow a thread to **wait** until the queue state satisfies a condition.

~~~text
Producer A -----\
                 \                    put / offer
Producer B ------>  [ BlockingQueue ]  --------------+
                 /          |                        |
Producer C -----/      buffer or rendezvous          v
                                             Consumer 1
                                             Consumer 2
                                             Consumer 3
~~~

A queue is a **data exchange boundary**, not a thread; it does not run `Runnable` on its own, does not create workers on its own, and does not manage business lifecycles on its own. Callers still need `Thread`/`ExecutorService` to run producers and consumers.

There are two basic waiting conditions:
- **Empty queue:** a consumer calling `take()` or timed `poll(timeout,unit)` may have to wait until an item is available.
- **Full queue (for bounded queues):** a producer calling `put()` or timed `offer(e,timeout,unit)` may have to wait until space becomes available.

These waiting conditions are synchronized and signaled by the `BlockingQueue` implementation according to its contract. You do not have to maintain `notEmpty` or `notFull` variables or call `notifyAll` on every update path.

### How Does BlockingQueue Differ from Regular Collections?

`ArrayDeque`, `LinkedList`, and `ArrayList` are not inherently thread-safe for concurrent `add/remove` by multiple threads. `Collections.synchronizedList`/`synchronizedCollection` can protect individual methods, but **do not directly provide a “wait for data / wait for space” protocol** via `put/take`. `ConcurrentLinkedQueue` supports non-blocking concurrent FIFO, but does not have `take()` to block when empty.

`BlockingQueue` provides **both concurrent access and a waiting protocol** suited for producer–consumer. This is the reason to choose it over a collection that merely has thread-safe methods.

## 3. Four Operation Groups and How They Handle Immediate Unavailability

The `BlockingQueue` contract has four response styles for the two actions **insert** and **remove**:

| Handling style | Insert element | Remove element | When not immediately possible |
| --- | --- | --- | --- |
| Throws exception | `add(e)` | `remove()` | Throws exception when queue is full/empty respectively |
| Returns special value | `offer(e)` | `poll()` | `false` when unable to insert, `null` when empty |
| Blocks indefinitely unless interrupted | `put(e)` | `take()` | Thread can wait until condition changes |
| Times out | `offer(e,t,u)` | `poll(t,u)` | Returns `false/null` when timeout expires |

For operations that **inspect the head of the queue without removing**:
- `element()` throws `NoSuchElementException` when empty.
- `peek()` returns `null` when empty.

**Note:** `poll()==null` means the queue currently has no item, because `BlockingQueue` **does not allow inserting `null` elements**. Do not design `null` to serve as both valid data and the termination signal of the BlockingQueue itself.

### Examples of Choosing Methods by Business Policy

- **Cannot lose data, waiting is acceptable:** `put(event)`, while ensuring shutdown/cancellation wakes up the producer when needed.
- **System must reject under overload:** `offer(event)` and handle `false` with appropriate logging/metrics/retry.
- **Tight deadline:** `offer(event, remaining, unit)` or `poll(remaining, unit)`.
- **Do not want to block the consumer thread:** `poll()` and use another scheduler/event mechanism to decide when to check next.
- **Consumer must wait for new work:** `take()` if a clear termination protocol exists.

Do not replace `put()` with a tight loop `while (!queue.offer(x)) {}`. This busy-spin can burn CPU, increase contention, and lacks a proper backpressure strategy.

### Interruption While Waiting

`put`, `take`, and timed variants declare `InterruptedException`. When interrupted:
- The primitive may exit waiting by throwing the exception.
- You must decide whether to propagate the exception or restore the interrupt status and **stop/transition the work state**.
- Exiting due to interruption does not mean data persistence or a remote transaction has completed.
- If a producer must guarantee no item is lost, you need to determine whether the unsent item can be retried/made idempotent or routed to another handling path.

Be careful not to **swallow `InterruptedException` and continue an infinite loop**: the request was cancelled, yet the worker keeps waiting as if nothing happened.

## 4. Memory Visibility: Handoff Is Also Synchronization

According to the memory consistency contract of `BlockingQueue`:

> Actions in a thread prior to placing an object into a BlockingQueue happen-before actions subsequent to the access or removal of that element from the queue in another thread.

This enables **publishing data before handoff** to the consumer:

~~~java
record Message(int id, String payload) {}

Message message = new Message(7, "ready");
queue.put(message);

// Consumer thread:
Message received = queue.take();
use(received.payload());
~~~

This snippet spans code across two threads, assuming `queue` and `use` are declared. Data created before `put` is published to the receiving thread per the contract, without needing `volatile` just to pass an immutable object through the queue.

**However**, memory visibility does not automatically make a mutable object safe when multiple threads continue modifying it after enqueueing:
- A producer puts an `ArrayList` into the queue and keeps adding elements while the consumer iterates over the list: a data race still exists.
- An object with multiple fields sharing an invariant does not become immutable simply by being enqueued.
- Use immutable messages, ownership transfer (the producer stops modifying after handing off), or appropriate locking.

BlockingQueue handles **handoff/visibility**, not the rules of managing shared mutable state.

## 5. Why Is Manual wait/notify Easy to Get Wrong?

A custom bounded buffer needs at least two predicates:
- `notEmpty`: `size > 0`, allowing a consumer to take.
- `notFull`: `size < capacity`, allowing a producer to add.

Predicates must be checked **under the same monitor/lock** used for waiting and waking up. The basic correct monitor pattern:

~~~java
synchronized (monitor) {
    while (queue.isEmpty()) {
        monitor.wait();
    }

    E item = queue.removeFirst();
    monitor.notifyAll();
    return item;
}
~~~

This is a snippet inside a `take` method, assuming `monitor` and `queue` are declared and the method is allowed to throw `InterruptedException`. Because `wait()` releases the monitor and reacquires it before returning, the `while` loop **re-checks the condition after waking up**.

### Mistake 1 — Using if Instead of while

Wrong:

~~~java
synchronized (monitor) {
    if (queue.isEmpty()) {
        monitor.wait();
    }
    return queue.removeFirst();
}
~~~

A thread can wake up due to a **spurious wakeup** or because another thread already took the item before it reacquired the lock. If you skip re-checking, the consumer may attempt to remove from an empty queue. `while` is a correctness requirement, not a “rare fallback measure.”

### Mistake 2 — Checking the Predicate Outside the Lock

Wrong:

~~~java
if (queue.isEmpty()) {
    synchronized (monitor) {
        monitor.wait();
    }
}
~~~

Between checking `isEmpty` and actually calling `wait`, the producer may add data and notify. The consumer then enters `wait` afterward and can **miss the signal**, even though data is already present. This bug is commonly called a **lost notification** or missed signal in an incorrect waiting protocol.

### Mistake 3 — Calling notify on an Unsuitable Waiter

When the same monitor has both producers waiting on `notFull` and consumers waiting on `notEmpty`, `notify()` wakes an arbitrary waiter; it may wake a group that cannot make progress, especially in complex designs. `notifyAll()` is usually simpler for correctness when using a single monitor, at the cost of waking many threads and causing lock contention.

If you use `ReentrantLock` and two `Condition` instances such as `notEmpty` and `notFull`, you can signal the right condition queue more accurately, but you must manage locking, predicates, interrupts, and closing yourself. **BlockingQueue encapsulates this machinery** inside its API.

### Mistake 4 — Forgetting Shutdown State

A consumer waiting in `wait()` may never wake up if the producer died before sending a signal. `BlockingQueue.take()` also **does not solve lifecycle management by itself**, but at least gives you a standard blocking protocol with interruption, timed waits, and the ability to send terminal signals.

### Mistake 5 — Writing a Custom Queue Without Backpressure

If every producer keeps calling `add` on an unbounded `ArrayDeque`, the buffer can exhaust memory. A bounded queue needs to handle `notFull` and decide whether producers wait or drop/reject. `ArrayBlockingQueue(capacity)` already provides capacity management and the corresponding blocking behavior.

**Section takeaway:** You can build a correct monitor buffer yourself, but to match a production-grade BlockingQueue, you must design and test many concurrency edge cases. Unless you have a very special invariant, prefer the standardized collection.

## 6. Example 1 — Bounded Producer–Consumer with ArrayBlockingQueue

Create **`BoundedHandoffDemo.java`**:

~~~java
import java.util.ArrayList;
import java.util.List;
import java.util.concurrent.ArrayBlockingQueue;
import java.util.concurrent.BlockingQueue;
import java.util.concurrent.ExecutorService;
import java.util.concurrent.Executors;
import java.util.concurrent.Future;
import java.util.concurrent.TimeUnit;

public class BoundedHandoffDemo {
    public static void main(String[] args) throws Exception {
        BlockingQueue<Integer> queue = new ArrayBlockingQueue<>(2);
        ExecutorService pool = Executors.newFixedThreadPool(2);

        try {
            Future<?> producer = pool.submit(() -> {
                try {
                    queue.put(10);
                    queue.put(20);
                    queue.put(30);
                    queue.put(-1); // Sentinel for one consumer.
                } catch (InterruptedException e) {
                    Thread.currentThread().interrupt();
                    throw new IllegalStateException("producer interrupted", e);
                }
            });

            Future<List<Integer>> consumer = pool.submit(() -> {
                List<Integer> received = new ArrayList<>();
                while (true) {
                    int value = queue.take();
                    if (value == -1) {
                        return received;
                    }
                    received.add(value);
                }
            });

            producer.get();
            List<Integer> result = consumer.get();

            System.out.println("received=" + result);
            System.out.println("remaining=" + queue.size());
        } finally {
            pool.shutdownNow();
            pool.awaitTermination(1, TimeUnit.MINUTES);
        }
    }
}
~~~

Run on Java 17+:

~~~bash
javac BoundedHandoffDemo.java
java BoundedHandoffDemo
~~~

Stdout when there is no external interruption/error:

~~~text
received=[10, 20, 30]
remaining=0
~~~

**Point-by-point explanation:**
1. `ArrayBlockingQueue<>(2)` allows at most two elements buffered at a time; this is the backlog limit at the queue boundary.
2. The producer puts `10,20,30,-1` in order. When the buffer is full, `put` may wait until the consumer takes items.
3. The consumer uses `take()` to wait for items when empty—no manual `wait`, no busy polling.
4. There is **one producer and one consumer**, so the received order is FIFO `10,20,30`. `-1` is reserved for termination.
5. `main` calls `Future.get()`, ensuring both producer and consumer complete successfully before reading the result and size.
6. The program does not assume which thread runs first or how many times the producer actually blocks; that depends on thread scheduling.

**Production caveat:** If the producer fails before sending the sentinel, the consumer may wait forever. `Future.get()` may also wait indefinitely. You must design deadlines, cancellation, a close protocol, or a coordinator that emits a terminal signal when the producer fails; **BlockingQueue has no general `close()` method in its interface**.

### Why Not Use LinkedList + synchronized for the Same Problem?

You could, but you would also have to write:
- Empty/full buffer checks inside `while` loops.
- Releasing and reacquiring the lock while waiting.
- Signaling the producer when the consumer takes an item and vice versa.
- Handling interruption, shutdown, capacity, and ordering.
- Testing races at points where notifications could be lost.

BlockingQueue gives the exact right abstraction: **data flowing through a queue that can block**.

## 7. Example 2 — Choosing offer/poll and Timed Methods for Backpressure

Not every application can afford to wait indefinitely. For UI requests, message ingestion, or APIs with SLOs, you can use `offer`/`poll`.

Create **`TimedQueuePolicyDemo.java`**:

~~~java
import java.util.concurrent.ArrayBlockingQueue;
import java.util.concurrent.TimeUnit;

public class TimedQueuePolicyDemo {
    public static void main(String[] args) throws Exception {
        ArrayBlockingQueue<Integer> queue = new ArrayBlockingQueue<>(2);

        boolean accepted1 = queue.offer(1);
        boolean accepted2 = queue.offer(2);
        boolean accepted3 = queue.offer(3);

        boolean timedAccepted = queue.offer(
                4, 20, TimeUnit.MILLISECONDS);

        System.out.println("accepted=" +
                accepted1 + "," + accepted2 + "," + accepted3);
        System.out.println("timedAccepted=" + timedAccepted);
        System.out.println("poll1=" + queue.poll());
        System.out.println("poll2=" + queue.poll());
        System.out.println("pollEmpty=" + queue.poll());
        System.out.println("timedPollEmpty=" +
                queue.poll(20, TimeUnit.MILLISECONDS));
    }
}
~~~

Run:

~~~bash
javac TimedQueuePolicyDemo.java
java TimedQueuePolicyDemo
~~~

Stdout without external interruption:

~~~text
accepted=true,true,false
timedAccepted=false
poll1=1
poll2=2
pollEmpty=null
timedPollEmpty=null
~~~

Here there is no other consumer, so the capacity-2 buffer is guaranteed full when `offer(4,20ms)` is called. The timed offer expires and returns `false`. Two `poll` calls retrieve `1` then `2` in FIFO order; after that the queue is empty, so both regular `poll` and timed `poll` return `null`.

**Application policy must decide what happens when `offer` returns `false`:**
- Return 429/503 or an appropriate “busy” response at the API layer.
- Record a rejected metric.
- Retry with exponential backoff and an overall deadline.
- Route to durable storage if the business cannot lose events.
- Drop/coalesce if data is droppable (e.g., sensor sampling).

`offer` returning `false` does not decide business semantics on its own. Do not retry forever inside a small thread pool without a timeout—it can starve the system of workers.

## 8. Choosing the Right BlockingQueue Implementation

| Implementation | Primary ordering | Capacity | Blocking semantics | When to consider |
| --- | --- | --- | --- | --- |
| `ArrayBlockingQueue<E>` | FIFO | **Fixed, bounded** | `put/take`, timed `offer/poll` | Pipelines with a clear backlog limit |
| `LinkedBlockingQueue<E>` | FIFO | Bounded when capacity is passed; very large by default | `put/take`, timed API | FIFO producer–consumer with linked structure |
| `SynchronousQueue<E>` | Direct handoff | **0 buffered items** | Producer/consumer wait for partner | Rendezvous, direct work handoff |
| `LinkedBlockingDeque<E>` | Double-ended, FIFO if using last/first | Optional capacity | Blocking at both ends | Work deque, custom push/pop requirements |
| `PriorityBlockingQueue<E>` | Priority/comparator | **Not bounded by constructor** | `take` when empty; `put` does not block for logical capacity | Priority scheduler without FIFO requirement |
| `DelayQueue<E extends Delayed>` | By delay expiry | Unbounded | `take` waits for item to expire | Processing events after a delay |
| `LinkedTransferQueue<E>` | FIFO, with transfer semantics | Structurally unbounded | `transfer` can wait for consumer receipt | Handoff with optional direct transfer |

### ArrayBlockingQueue: Clear Baseline for Bounded Backlogs

- Fixed backing array based on capacity.
- FIFO for elements enqueued in a given order.
- Optional `fair=true` for fairness among threads waiting for access; fairness does **not** mean FIFO completion or priority processing.
- Boundedness limits the number of waiting items, but does not replace upstream policy when the queue is full.

Usually the easiest starting point to reason about for **producer–consumer with backpressure**.

### LinkedBlockingQueue: Do Not Mistake the Default for “Just Enough”

`new LinkedBlockingQueue<>()` defaults to capacity `Integer.MAX_VALUE`; it will not block producers at a small threshold like 1,000 unless you configure it:

~~~java
BlockingQueue<Event> queue = new LinkedBlockingQueue<>(1_000);
~~~

This snippet assumes an `Event` class already exists. A very large default backlog can exhaust memory if producer rate exceeds consumer rate for an extended period. “Unbounded by practical contract” does not mean the machine has infinite memory.

### PriorityBlockingQueue: Not FIFO

`PriorityBlockingQueue` returns elements according to comparator/natural order; if multiple elements have equal priority, **stable FIFO is not guaranteed**. If tie-breaking is needed, add a sequence number to the comparator. Do not use `iterator()` assuming priority order: the iterator is not an ordered drain.

It can block consumers when empty, but producer `put` does not create bounded backpressure like `ArrayBlockingQueue`. If you need both priority and a bounded backlog, you must design separate admission control; **you cannot pass an initial constructor capacity and treat it as a hard limit**.

### DelayQueue: Waiting Until Items Expire

`DelayQueue` is a specialized BlockingQueue: elements must implement `Delayed`; consumer `take` only returns an item once its delay has expired. Even if the queue physically contains items, `poll()` may return `null` when none have expired yet. Not suitable as a replacement for a FIFO work queue if you need immediate processing.

### Deque: Which Operations Determine Ordering

`LinkedBlockingDeque` can add/remove at both head and tail. Using `putLast` + `takeFirst` gives FIFO; using `putFirst` + `takeFirst` gives LIFO for the corresponding elements. Saying “it has ordering” is not enough: you must specify **which end each operation uses**.

## 9. Example 3 — SynchronousQueue: Direct Exchange Without a Buffer

`SynchronousQueue` has a capacity of 0: each `put(x)` needs a matching consumer to receive it; it holds no items in a buffer. Therefore:
- Non-blocking `offer(x)` returns `false` if no matching consumer is waiting.
- `put(x)` can block until a `take()` receives it.
- `remainingCapacity()` is always 0.
- It is useful when you want to couple producer rate directly to consumers without building retry or durable storage into the queue.

Create **`SynchronousHandoffDemo.java`**:

~~~java
import java.util.concurrent.ExecutorService;
import java.util.concurrent.Executors;
import java.util.concurrent.Future;
import java.util.concurrent.SynchronousQueue;
import java.util.concurrent.TimeUnit;

public class SynchronousHandoffDemo {
    public static void main(String[] args) throws Exception {
        SynchronousQueue<String> queue = new SynchronousQueue<>();

        boolean offeredWithoutReceiver = queue.offer("early");

        ExecutorService pool = Executors.newFixedThreadPool(2);
        try {
            Future<?> sender = pool.submit(() -> {
                try {
                    queue.put("payload");
                } catch (InterruptedException e) {
                    Thread.currentThread().interrupt();
                    throw new IllegalStateException("sender interrupted", e);
                }
            });

            Future<String> receiver = pool.submit(queue::take);

            sender.get();
            String result = receiver.get();

            System.out.println("immediateOffer=" + offeredWithoutReceiver);
            System.out.println("received=" + result);
            System.out.println("remainingCapacity=" +
                    queue.remainingCapacity());
        } finally {
            pool.shutdownNow();
            pool.awaitTermination(1, TimeUnit.MINUTES);
        }
    }
}
~~~

Run:

~~~bash
javac SynchronousHandoffDemo.java
java SynchronousHandoffDemo
~~~

Stdout when there is no external interruption/error:

~~~text
immediateOffer=false
received=payload
remainingCapacity=0
~~~

**Why is it deterministic?** `offer("early")` runs on `main` before the consumer task is created, so no thread is waiting to receive, yielding `false`. After both tasks are submitted, sender and receiver rendezvous via `put/take`, regardless of which worker starts first. `Future.get()` waits for both to finish; no item is stored in the queue.

**Liveness:** `SynchronousQueue.put()` can wait forever if there is no consumer, and `take()` can wait forever if there is no producer. With a thread pool of only **one worker**, if the producer occupies the worker and blocks on `put` while the consumer is also submitted to that same pool, a thread-starvation deadlock can occur. Do not treat direct handoff as a silver bullet that removes the need for enough workers or a shutdown protocol.

## 10. Lifecycle and Shutdown: BlockingQueue Has No Common close()

An easy thing to overlook when moving from `wait/notify` to a queue: you no longer have to write empty/full waiting yourself, **but you still must design “no more data”**.

`BlockingQueue` does not define a `close()` method to automatically make all consumers waiting in `take()` exit. If producers finish without notifying, consumers can still wait indefinitely.

Common strategies:
1. **Poison pill/sentinel:** send one special value per consumer.
2. **Interruption:** a coordinator holds worker `Future`s or thread handles and sends cancel/interrupt per contract.
3. **Timed poll + closed flag:** consumers periodically check `closed` (and drain remaining items), avoiding indefinite waiting.
4. **Wrapper abstraction with close:** define a `closed` state, a wakeup protocol, and protect the atomicity of close relative to enqueue.
5. **Executor lifecycle:** if you do not need to write an event loop yourself, you can use `ExecutorService.submit` and `shutdown/awaitTermination` to manage the task queue and workers at a higher level.

**A poison pill is just one item**; it does not replicate itself for N consumers. If one consumer takes the pill and exits, the other N-1 consumers may still be waiting.

### Example 4 — Stopping Exactly Three Consumers with Three Sentinels

Create **`MultiConsumerStopDemo.java`**:

~~~java
import java.util.ArrayList;
import java.util.List;
import java.util.concurrent.ArrayBlockingQueue;
import java.util.concurrent.BlockingQueue;
import java.util.concurrent.ExecutorService;
import java.util.concurrent.Executors;
import java.util.concurrent.Future;
import java.util.concurrent.TimeUnit;
import java.util.concurrent.atomic.AtomicInteger;

public class MultiConsumerStopDemo {
    public static void main(String[] args) throws Exception {
        int consumerCount = 3;
        BlockingQueue<Integer> queue = new ArrayBlockingQueue<>(4);
        ExecutorService pool = Executors.newFixedThreadPool(4);

        AtomicInteger processed = new AtomicInteger();
        AtomicInteger total = new AtomicInteger();

        try {
            List<Future<?>> consumers = new ArrayList<>();

            for (int i = 0; i < consumerCount; i++) {
                consumers.add(pool.submit(() -> {
                    try {
                        while (true) {
                            int value = queue.take();
                            if (value == -1) {
                                return;
                            }
                            processed.incrementAndGet();
                            total.addAndGet(value);
                        }
                    } catch (InterruptedException e) {
                        Thread.currentThread().interrupt();
                        throw new IllegalStateException("consumer interrupted", e);
                    }
                }));
            }

            Future<?> producer = pool.submit(() -> {
                try {
                    for (int i = 1; i <= 9; i++) {
                        queue.put(i);
                    }
                    for (int i = 0; i < consumerCount; i++) {
                        queue.put(-1);
                    }
                } catch (InterruptedException e) {
                    Thread.currentThread().interrupt();
                    throw new IllegalStateException("producer interrupted", e);
                }
            });

            producer.get();
            for (Future<?> consumer : consumers) {
                consumer.get();
            }

            System.out.println("processed=" + processed.get());
            System.out.println("sum=" + total.get());
            System.out.println("remaining=" + queue.size());
        } finally {
            pool.shutdownNow();
            pool.awaitTermination(1, TimeUnit.MINUTES);
        }
    }
}
~~~

Run:

~~~bash
javac MultiConsumerStopDemo.java
java MultiConsumerStopDemo
~~~

Stdout when there is no unexpected interruption/error:

~~~text
processed=9
sum=45
remaining=0
~~~

**Reasoning:**
- The producer sends 9 real items `1..9`, followed by **exactly three sentinels** for the three consumers.
- The FIFO queue and single producer guarantee the pills are enqueued **after** all real items.
- Each of the three consumers exits immediately upon receiving one pill; no consumer can “eat two pills” because it returns after the first one.
- Every real item is taken once by a consumer; `AtomicInteger` protects the sum and processed count under concurrent updates.
- `main` waits for the producer and all consumers via `Future.get()` before reading results.
- `1+2+...+9=45`, so the output does not depend on which consumer took which element.
- The pool has four workers: three consumers can wait and the producer still has a worker to send data. If a single-worker pool were used and consumers were submitted first, the producer might never get a chance to run.

### What Poison Pills Do Not Solve

- If the producer fails **before enqueueing the pills**, consumers can hang. The coordinator must have an independent cancel/wakeup path.
- With multiple producers, **only the last producer or a coordinator that knows all producers have finished** can emit the terminal signal after all work; if a pill arrives too early, a consumer may leave another producer's work behind.
- If valid data can equal `-1`, using an `int` sentinel that collides with data is a design bug. Use a distinct marker/type (sealed hierarchy, enum/record wrapper).
- A full queue can cause the producer to **block even while enqueueing pills**. Therefore, deadlines/cancellation are needed during shutdown.
- If a consumer dies with an error before receiving a pill, a pill may remain in the queue or cause the remaining consumers to miscount termination.
- The queue guarantees each item is dequeued once in normal operations, **not** exactly-once business processing if a worker dies after `take` and before committing. You need ack/retry/durable queues and idempotency when required.

## 11. Example 5 — Manual Monitor Coordination: Possible to Get Right, Yet More Complex

For a fair comparison, here is a **monitor-based bounded buffer that is correct for the happy path**, not intentionally broken. It uses `ArrayDeque`, `synchronized`, `while`, `wait()`, and `notifyAll()`. This shows exactly what code BlockingQueue hides from you.

Create **`ManualMonitorBufferDemo.java`**:

~~~java
import java.util.ArrayDeque;
import java.util.concurrent.atomic.AtomicInteger;

public class ManualMonitorBufferDemo {
    static final class BoundedBuffer {
        private final ArrayDeque<Integer> items = new ArrayDeque<>();
        private final int capacity;

        BoundedBuffer(int capacity) {
            if (capacity <= 0) {
                throw new IllegalArgumentException("capacity <= 0");
            }
            this.capacity = capacity;
        }

        synchronized void put(int value) throws InterruptedException {
            while (items.size() == capacity) {
                wait();
            }
            items.addLast(value);
            notifyAll();
        }

        synchronized int take() throws InterruptedException {
            while (items.isEmpty()) {
                wait();
            }
            int value = items.removeFirst();
            notifyAll();
            return value;
        }

        synchronized int size() {
            return items.size();
        }
    }

    public static void main(String[] args) throws Exception {
        BoundedBuffer buffer = new BoundedBuffer(2);
        AtomicInteger sum = new AtomicInteger();

        Thread producer = new Thread(() -> {
            try {
                for (int i = 1; i <= 5; i++) {
                    buffer.put(i);
                }
            } catch (InterruptedException e) {
                Thread.currentThread().interrupt();
            }
        }, "producer");

        Thread consumer = new Thread(() -> {
            try {
                for (int i = 0; i < 5; i++) {
                    sum.addAndGet(buffer.take());
                }
            } catch (InterruptedException e) {
                Thread.currentThread().interrupt();
            }
        }, "consumer");

        producer.start();
        consumer.start();
        producer.join();
        consumer.join();

        System.out.println("sum=" + sum.get());
        System.out.println("remaining=" + buffer.size());
    }
}
~~~

Run:

~~~bash
javac ManualMonitorBufferDemo.java
java ManualMonitorBufferDemo
~~~

Stdout on a run without unexpected interruption:

~~~text
sum=15
remaining=0
~~~

**Why is it correct in this demo?**
- `put`/`take` are synchronized on the same `BoundedBuffer` instance, so `wait`/`notifyAll` use the same monitor.
- Predicates `size==capacity` and `isEmpty` are read/written under the lock, eliminating lost-notification races between check and wait.
- `wait()` releases the monitor while waiting; upon waking, it reacquires the monitor and **re-checks with `while`**.
- `notifyAll()` wakes waiters so they can verify their predicate themselves, without assuming who wakes first.
- FIFO buffer via `addLast` + `removeFirst`, capacity 2; 5 elements `1..5` sum to 15.
- `main` `join`s both threads before reading the sum and buffer size.

**Still only a minimal example**: it lacks non-blocking `offer`, `poll(timeout)`, `put(timeout)`, close, multi-consumer poison-pill protocol, producer-failure handling policy, fairness, structured diagnostics, or saturation management.

### When Does Writing a Custom Condition/Monitor Still Make Sense?

It makes sense when synchronization is tied to **a custom invariant that cannot be expressed as a queue**. For example:
- A state machine that must wait on multiple related conditions such as `state == RUNNING && count >= N`.
- Atomic transitions across multiple fields under the same lock.
- Waiting for state itself to change, **not for an item to be passed**.
- Signaling all listeners without consuming individual messages (broadcast).

In those cases, `ReentrantLock + Condition` or `synchronized + wait/notifyAll` can be the right abstraction. But if you are just reinventing a standard producer–consumer buffer, prefer a standard BlockingQueue.

## 12. BlockingQueue or Another Synchronizer? Choose by What You Wait For

| Problem | Abstraction to consider first | Why |
| --- | --- | --- |
| Pass items from producers to consumers; consumers wait when empty | **`BlockingQueue`** | Data and waiting mechanism in one abstraction |
| Limit buffer and apply backpressure to producers | **Bounded BlockingQueue** | Has capacity + `put/offer(timeout)` |
| One or more threads wait for a one-time event | `CountDownLatch` | Wait for a signal without consuming an item from a queue |
| A group of threads wait together across multiple phases | `CyclicBarrier` / `Phaser` | Phase coordination among multiple participants |
| Limit concurrent access to a shared resource | `Semaphore` | Manages permit count, not a FIFO job queue |
| A thread waits for a computation result | `Future` / `CompletableFuture` | Result and failure/cancellation of a computation |
| A lock coordinating custom conditions | `ReentrantLock + Condition` | Protects custom state invariants |
| Run many `Runnable/Callable` tasks with a worker pool | `ExecutorService` | Manages scheduling, workers, Future, and lifecycle |
| Broadcast events to multiple subscribers | Appropriate pub/sub or callback model | A multi-consumer queue distributes items, it does not broadcast |
| Always read the **latest value** instead of a backlog | `AtomicReference`/`volatile` + signal | A queue keeps old items, it does not coalesce |
| Need durable message processing across restarts | Persistent broker/storage protocol | BlockingQueue is purely in-memory, not durable |

### A Queue Does Not Replace Semaphore

`Semaphore(3)` allows at most three threads to hold permits concurrently, regardless of whether “work items” exist. `ArrayBlockingQueue(3)` limits **three items in the buffer**, **not** three tasks actively processing after they have called `take` to remove items from the queue. If you need to cap the number of in-flight HTTP requests, you may need a semaphore (or a bounded executor/admission control), not just a queue.

### A Queue Does Not Replace CountDownLatch

`CountDownLatch.await()` waits on a **non-consumed** signal for all waiters. If replaced with a queue holding a single token, the first consumer to call `take` consumes the token; the remaining waiters will not pass automatically. That breaks broadcast/one-time release semantics.

### A Queue Does Not Replace Future

A `Future<T>` represents a computation and provides its outcome with `get()`, `ExecutionException`, `CancellationException`, and completion semantics. A BlockingQueue can pass a custom `Result` wrapper, but you would have to build failure/cancel/correlation handling yourself. If you simply want to run a callable and get its result, `executor.submit(callable)` is usually simpler than rolling your own request/result queues.

## 13. Ordering: FIFO Dequeue Does Not Guarantee FIFO Completion

Suppose a producer enqueues A then B into a FIFO queue. Two consumers may:
- Consumer 1 takes A, processes for 500 ms.
- Consumer 2 takes B, processes for 10 ms.
- B is committed before A.

~~~text
FIFO enqueue/dequeue:   A -> B
Processing workers:     A ---------finish
                         B -finish
Commit order:           B -> A   (possible)
~~~

If business logic requires ordered output, design **sequence numbers, a reorder buffer, serial commit**, or a single sequential consumer. A queue does not automatically synchronize “task A finishes before task B.”

With multiple producers calling `put` concurrently, the effective enqueue order is determined by actual scheduling and synchronization. It is not automatically the order in which “requests appear in logs” if timestamps/logs are created outside the enqueue point.

With `PriorityBlockingQueue`, dequeue order is based on the comparator, not FIFO. With `SynchronousQueue`, there is no buffer; a `put` is matched with a corresponding `take`. With `DelayQueue`, an item is only ready when its delay expires.

**Do not use `size()` or `isEmpty()` as a lock:**

~~~java
if (!queue.isEmpty()) {
    E item = queue.remove();
}
~~~

This snippet is risky with multiple consumers: between `isEmpty` and `remove`, another thread may take the last element. If you only want to claim an item when available, use `poll()`; if you want to wait, use `take()`.

## 14. Boundedness, Backpressure, and Memory Limits

A more important question than “which queue is fastest” is **“what happens when the producer is faster than the consumer for 10 minutes?”**

If 10,000 items arrive per second while consumers process 8,000 items/s, the backlog grows by about 2,000 items/s. After 10 minutes that is roughly 1.2 million items, not counting memory for payloads, nodes, object graphs, and metrics. An unbounded queue can consume huge amounts of RAM before failing.

With a bounded queue of capacity `C`:
- At most C items wait in the queue (excluding items consumers have already taken and are processing).
- `put` can block the producer when full.
- `offer` can reject immediately.
- `offer(timeout)` allows bounded waiting.
- Callers can use queue depth, rejected count, and producer wait time to throttle.

**Do not equate capacity with total in-flight requests.** If 100 consumers are actively processing and queue capacity is 100, there can be up to roughly 200 items either in-flight or waiting (not counting requests not yet enqueued or in other stages).

### Backpressure Should Propagate Upstream

A bounded queue only creates pressure where the producer calls `put/offer`. If upstream accepts unlimited requests and spawns a task waiting to enqueue each one, the backlog still accumulates **at the thread/task layer instead of inside the queue**. You need admission control at the right boundary, timeouts, and a bounded executor or input throttling mechanism.

### Failure Modes and Explicit Decisions

- **Full queue:** reject, retry, shed load, or apply backpressure.
- **Empty queue:** wait, timed poll, or idle scheduler.
- **Shutdown:** stop accepting new items, drain or discard per policy.
- **Producer failure:** how are consumers notified of termination?
- **Consumer failure:** is an item taken but not finished retried?
- **Timeout/cancellation:** caller no longer needs the result; should the item be removed from the queue?
- **Duplicates:** retries may cause the same business item to appear multiple times.
- **Poison-pill admission:** a full queue can block when sending terminal messages.
- **Durability:** an in-memory queue loses data if the process dies.

If the business requires **at-least-once delivery, retries, and durable acknowledgement**, a plain BlockingQueue is not a message broker with a persistent log. A worker that `take`s an item and crashes can lose that item from the queue before committing.

## 15. Safe Shutdown Requires a Protocol Outside the Queue

For a multi-producer/consumer pipeline, treat shutdown as a **state machine**:

~~~text
RUNNING
   |
   | stop accepting new items
   v
CLOSING
   |
   | producers finish / cancel
   | drain outstanding items if policy requires
   | notify consumers via sentinel/close/interrupt
   v
STOPPED
~~~

A graceful-drain policy typically does:
1. Stop accepting new producers.
2. Wait for or cancel running producers within a deadline.
3. Ensure no new items are enqueued **after** terminal markers.
4. Deliver terminal signals to the exact number of consumers or use a close protocol.
5. Wait for consumers to actually exit and clean up, with a deadline for errors/hangs.
6. Shut down the executor according to ownership.

Do not blindly call `shutdownNow()` as soon as the queue is empty if consumers still need to commit work they already took. `ExecutorService.shutdown()` stops accepting new tasks while letting submitted tasks continue; `shutdownNow()` is only best-effort interruption. Neither creates a “closed state” for the `BlockingQueue` held by your code.

### Poison Pills Should Not Be Confused with Exceptions

A pill is **data following a special convention**. If you need to distinguish normal completion, error, cancellation, and retryable failure, define a wrapper such as:

~~~java
sealed interface Event permits Data, End, Failure {}
record Data(int id) implements Event {}
record End() implements Event {}
record Failure(String reason) implements Event {}
~~~

This snippet defines a Java 17 sealed hierarchy; it is not a standalone file. The caller decides that `End` means graceful stop while `Failure` means stop with error. If multiple consumers share one queue, design routing/broadcasting of terminal messages explicitly rather than assuming one marker covers the whole group.

## 16. Notes on Cancellation and Interrupts

When a thread is in `take/put`, `Thread.interrupt()` can cause the blocking operation to throw `InterruptedException`. However:
- If the task catches the exception and **continues looping unconditionally**, cancellation can be defeated.
- `Thread.interrupted()` (static) reads and **clears** the current thread's interrupt status; `isInterrupted()` only reads it.
- If a method can declare `throws InterruptedException`, usually propagate it so the coordinator can decide.
- If it cannot propagate, restore the flag via `Thread.currentThread().interrupt()` and **exit according to policy**.
- `Future.cancel(true)` requests interrupting the runner in supporting implementations, but does not guarantee every I/O or CPU loop stops instantaneously.
- A task that already took an item and is then cancelled must define **item ownership**: retry, return to the queue, or record failure. Blindly calling `queue.offer(item)` in `finally` can fail if the queue is full and also risks duplicates if commit already succeeded.

Do not use `Thread.stop()` for forceful cancellation. Safe cancellation must preserve invariants and resource cleanup.

### Wait Timeout Does Not Mean the Task Was Cancelled

`queue.poll(timeout)` returns `null` when the wait for an item expires, yet the thread can continue doing other work. A `future.get(timeout)` timeout only limits how long the caller waits for a computation. Define a **pipeline-wide deadline**, rather than resetting the timeout at every stage, and do not assume remote side effects were rolled back.

### What If a Consumer Took an Item and Processing Failed?

The queue already removed the item at the moment `take()` succeeded. There is no built-in `ack/nack` in the `BlockingQueue` interface. If you need retry/at-least-once:
- Wrap items in task state with an ID.
- Have an owner/coordinator track in-flight items.
- Define a retry policy and prevent duplicates with idempotency.
- For durability beyond process lifetime, use persistent storage/a broker/an appropriate protocol.

An in-memory queue is just a synchronizer/data structure; it does not solve transactional delivery semantics on its own.

## 17. Why Not Use a Queue for Every Kind of Signal?

The convenience of `take` can tempt developers into using a queue as a “tunnel for every state.” This creates tight coupling and hard-to-diagnose deadlocks.

**When a single event has occurred:** use `CountDownLatch` so multiple threads can proceed together when the count reaches 0. A queue only hands one token to one taker.

**When you need a work queue:** use `BlockingQueue` or submit tasks to an `ExecutorService`. If you are manually creating N worker threads, dequeuing `Runnable`s, and managing shutdown yourself, you may be rewriting an executor.

**When limiting DB connection access:** use a `Semaphore` or a connection pool with a clear contract. Queue capacity limits waiting items, not the number of consumers concurrently holding DB connections.

**When multiple complex state conditions apply:** use `ReentrantLock + Condition` to preserve invariants within a critical section; a queue represents one data/ordering stream, not multi-field transactions.

**When broadcasting:** a standard multi-consumer queue **distributes** each item to one consumer, rather than broadcasting each item to all; use pub/sub with per-subscriber queues or a suitable abstraction.

**When “always taking the latest value”:** an `AtomicReference` with appropriate publication and notification can be better than a queue accumulating stale values. If coalescing is needed, do not let a backlog hold every obsolete version.

## 18. Testing Producer–Consumer Without Flakiness

Do not just use `Thread.sleep(100)` to “wait for the consumer to start.” The scheduler does not guarantee a thread has reached the desired point after that time. Tests should use:
- `CountDownLatch` to confirm producer/consumer reached a specific point.
- `Future.get(timeout)` so tests are bounded instead of hanging the entire suite.
- Small bounded queues (capacity 1 or 2) to force full/empty paths.
- `AtomicInteger` or result reduction when counting across multiple consumers.
- Assertions on the **set of items and total count received**, without guessing which thread processed which item.
- Tests for interrupting a consumer in `take` and a producer in `put`.
- Tests for producer failure before the terminal signal.
- Tests with multiple consumers and the exact number of pills or a close protocol.
- Tests for shutdown while the queue is full.
- Tests for a producer adding after close or a pill enqueued too early.
- Tests for cancellation after an item is taken but before commit.
- Tests verifying no leaked permits/locks and no workers blocked past the deadline.

### Mandatory Scenarios

| Scenario | Expected behavior |
| --- | --- |
| Fast producer, slow consumer, bounded queue | `put` can wait; capacity is not exceeded |
| Empty queue, consumer calls `take` | Consumer waits, no busy spin |
| Full queue, producer calls `offer` | Returns `false`, caller handles rejection |
| Full queue, timed offer | Waits up to timeout per contract, returns `false` if no space |
| N consumers, only 1 poison pill | No guarantee all N consumers exit |
| Producer dies before pill | Coordinator cancellation/close needed to prevent hang |
| Multi-consumer and FIFO queue | Dequeue follows queue order; completion order may differ |
| Producer hands off mutable object then mutates it | Requires ownership/synchronization |
| A consumer dies after `take` | Item may be lost without external retry/ack |
| Executor shutdown while workers are still waiting | Must have protocol for handling interruption and cleanup |

### Focused Performance Testing

Compare `ArrayBlockingQueue`, `LinkedBlockingQueue(capacity)`, `SynchronousQueue`, or non-blocking queues **on the same realistic workload**:
- Producer/consumer rates, burst size, and core count.
- Throughput (items/s), p95/p99 queue wait, and end-to-end latency.
- CPU utilization when idle: busy-spin vs. blocking.
- Allocation/GC and memory by backlog size.
- Counts of rejected/timed-out/cancelled items.
- Time to graceful shutdown.
- Fairness/starvation with multiple producers/consumers.

Do not conclude “ArrayBlockingQueue is always fastest” or “LinkedBlockingQueue is always faster” from a tiny experiment. Use JMH or an appropriate benchmark harness; always verify correctness and state the JVM/hardware environment.

## 19. Common Mistakes When Applying BlockingQueue

1. **Using `ArrayList`/`ArrayDeque` concurrently without synchronization.** Causes data races/corruption; use a proper concurrent/BlockingQueue or lock.
2. **Writing `wait()` with `if`.** Spurious wakeups and post-notify contention can invalidate the predicate; use `while` under the same monitor.
3. **Reading the condition outside the lock before waiting.** Prone to missed notifications; guard check–wait with the same synchronization protocol.
4. **Calling `notify()` arbitrarily with multiple waiter types.** Can wake a group that cannot progress; consider `notifyAll` or separate `Condition`s.
5. **Assuming `BlockingQueue` has `close()`.** There is no general close method; you must design the lifecycle.
6. **Assuming `take()` returns `null` to signal completion.** `take()` waits until an item is available; it does not use a `null` sentinel.
7. **Putting `null` into a BlockingQueue.** Not allowed; `null` is reserved as the “no item” return value of `poll/peek`.
8. **Using `put()` on an unbounded queue and expecting small-scale backpressure.** There is no small capacity to apply pressure; configure a bound.
9. **Using `offer()` and ignoring `false`.** Items can be rejected while the system reports success.
10. **Busy-polling with a tight `poll()` loop.** Can burn CPU; use `take`, timed `poll`, or a scheduler.
11. **Using one pill for multiple consumers.** Only one consumer receives the pill; the others can hang.
12. **A producer emitting a pill before all producers finish.** A consumer may exit before all work is done.
13. **Using a sentinel that collides with real data values.** Consumers may mistakenly discard real data; use a typed marker.
14. **Assuming a FIFO queue guarantees FIFO processing completion.** Multiple consumers can finish out of order.
15. **Using `isEmpty` then `remove` as an atomic operation.** Check-then-act race; use `poll`/`take`.
16. **Using `PriorityBlockingQueue` as a bounded work queue.** It has no hard capacity enforced by its constructor.
17. **Using `SynchronousQueue` with one worker where the producer blocks and the consumer is queued behind it in the same pool.** Can cause starvation deadlock.
18. **Stopping the producer without notifying consumers.** Consumers keep waiting indefinitely.
19. **Swallowing `InterruptedException`.** Cancellation/shutdown is ignored.
20. **Assuming handoff automatically deep-freezes the payload.** A mutable object that continues to be modified remains unsafe.
21. **Assuming the queue guarantees exactly-once business processing.** A taken item can be lost if the consumer dies before committing.
22. **Not bounding the backlog upstream.** Even with a full queue, unbounded request threads waiting on `put` still cause overload.
23. **Using a queue to solve barrier/broadcast.** Wrong semantics; use the right synchronizer.
24. **Replacing an executor with a custom worker system unnecessarily.** Increases responsibility for queue handling, failures, lifecycle, and scheduling.
25. **Not measuring peak writes/bursts and shutdown latency.** A design may work in a demo and collapse under real load.

## 20. Decision Checklist

Before choosing BlockingQueue, answer:

1. Are **items actually being transferred from producers to consumers**?
2. Must consumers **wait when empty**, or can they poll non-blockingly?
3. Must producers **wait when full**, reject/drop, or retry?
4. Is a **hard capacity** needed for the backlog?
5. What ordering is actually required: FIFO, priority, delayed, LIFO, or sequence-ordered completion?
6. Should multiple consumers share items, or must every item be broadcast to all?
7. Is the payload immutable or does ownership transfer after enqueue?
8. Is a snapshot/multi-field transaction needed instead of just queueing items?
9. Are producers and consumers guaranteed enough workers to make progress?
10. Are there deadlines/cancellation for blocked `put/take` calls?
11. When a producer fails, how are consumers notified?
12. With multiple producers, who is authorized to emit the final terminal marker?
13. With N consumers, are there enough pills or a close protocol?
14. If the queue is full at shutdown, is there a path to make progress?
15. If a taken item fails processing, are retries/durable acks needed?
16. Is upstream backpressure needed so the backlog does not grow elsewhere?
17. Is it a one-time event signal for all waiters rather than a queue? If so, use `CountDownLatch`.
18. Is it limiting the number of resources in use? If so, look at `Semaphore`.
19. Are multiple phases/barriers needed? If so, look at `Phaser/CyclicBarrier`.
20. Is it simply a background `Callable`? If so, look at `ExecutorService.submit`.
21. Have races and worker failures been tested with latches/timed `get`?
22. Have throughput, wait latency, memory, and shutdown been measured under load?

## 21. Self-Check Questions and Answers

1. **Which parts of a producer–consumer monitor does BlockingQueue replace?** Queue data structure, add/remove synchronization, empty/full waiting, wakeups, and visibility.
2. **When the queue is empty, what does `take()` return?** It waits until an item is available or it is interrupted per contract; it does not return `null` to signal empty.
3. **When the queue is empty, what does `poll()` return?** `null` immediately, without waiting.
4. **On a full bounded queue, what does `offer(e)` return?** `false`.
5. **On a full bounded queue, what does `put(e)` do?** It can block waiting for space or be interrupted.
6. **What does an expired `offer(e,t,u)` return?** `false` if unable to insert before the timeout.
7. **Can `null` be used as a poison pill?** No; BlockingQueue does not permit `null` elements.
8. **Why must `wait` be inside a `while` loop?** Spurious wakeups and contention can make the predicate false again when waking up.
9. **Why is checking outside the lock before waiting dangerous?** A producer can change state and notify between the check and `wait`, causing a missed signal.
10. **Can you pass a mutable payload through BlockingQueue and treat it as automatically thread-safe?** No; ownership/immutability or separate synchronization is still required.
11. **Is there a memory happens-before relationship from producer `put` to consumer `take`?** Yes, per the BlockingQueue contract for the transferred object.
12. **Does `ArrayBlockingQueue` have an optional unbounded capacity?** No; capacity is fixed by the constructor.
13. **How large is the default capacity of `LinkedBlockingQueue` without an argument?** `Integer.MAX_VALUE`.
14. **Does `SynchronousQueue` have a buffer?** No, capacity 0; it requires a producer–consumer rendezvous.
15. **Is `PriorityBlockingQueue` FIFO like `ArrayBlockingQueue`?** No; it orders by comparator/natural priority.
16. **Does `PriorityBlockingQueue` bound the backlog by its constructor capacity?** No.
17. **Does a FIFO queue guarantee consumer results are committed in FIFO order?** No; parallel processing can invert completion order.
18. **Does one poison pill stop all N consumers?** No; a single pill is normally taken by only one consumer.
19. **If the producer dies before sending the pill, what is needed?** Coordinator/close/cancel/timeout so consumers do not hang.
20. **Does BlockingQueue have a common `close()` method?** No.
21. **If a consumer takes an item and then dies, does the item automatically return to the queue?** No; a retry/ack policy is required.
22. **Does queue capacity C limit active tasks after `take` to C?** No; capacity only limits items sitting in the queue.
23. **What should be used to wait for a one-shot signal across multiple threads?** `CountDownLatch`.
24. **What should be considered to limit concurrent connection usage?** `Semaphore` or a resource pool with an appropriate contract.
25. **What should be considered to run a `Callable` and retrieve its result?** `ExecutorService.submit`/`Future`.
26. **Is using a queue to replace event broadcasting correct?** Not by default; consumers share items rather than each receiving all of them.
27. **Does `poll()==null` mean the producer has closed?** No; it only means no item is currently ready.
28. **Does a `future.get(timeout)` timeout automatically cancel the producer?** No; cancellation must be decided separately.
29. **Why does an unbounded queue risk OOM?** Producers can accumulate items faster than consumers process them.
30. **When should you write a `Condition` manually instead of a queue?** When the problem involves custom state invariants or multiple predicates not well represented by item handoff.

## 22. Summary

**Use `BlockingQueue` when you genuinely need a work or data queue between threads**, especially when consumers must wait on empty, producers must wait or be rejected on full, and you want to avoid writing `wait/notify/Condition` protocols that are prone to races, missed notifications, and spurious wakeup bugs.

- Choose **`ArrayBlockingQueue`** when you want bounded FIFO and explicit backpressure.
- Choose **`LinkedBlockingQueue(capacity)`** if linked FIFO fits; do not accidentally leave capacity near-infinite when backlog risk exists.
- Choose **`SynchronousQueue`** if you need direct handoff with no buffer.
- Choose **`PriorityBlockingQueue`** or **`DelayQueue`** when priority or expiry delay is required, keeping in mind their boundedness and non-FIFO ordering.
- Use **`offer/poll`** when indefinite waiting is unacceptable; **`put/take`** when blocking is desired and the lifecycle is properly designed.
- Do not forget **interruption, poison pill/close protocols, capacity, backpressure, resource ownership, and error handling**.

If what you need **is not item handoff**, choose the right synchronizer: `CountDownLatch` for one-time signals, `Phaser` for phases, `Semaphore` for permits, `Condition` for state invariants, or `Future/ExecutorService` for the result of a computation. BlockingQueue **reduces thread coordination burden**, but does not automatically solve business transactions, retries, durable messaging, exactly-once processing, or graceful shutdown.

## Java SE 17 References

- [BlockingQueue](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/concurrent/BlockingQueue.html): method summary table, happens-before, no nulls, lack of common close protocol.
- [ArrayBlockingQueue](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/concurrent/ArrayBlockingQueue.html): bounded FIFO and fairness.
- [LinkedBlockingQueue](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/concurrent/LinkedBlockingQueue.html): optional capacity and FIFO.
- [SynchronousQueue](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/concurrent/SynchronousQueue.html): zero-capacity rendezvous.
- [PriorityBlockingQueue](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/concurrent/PriorityBlockingQueue.html): priority, unbounded, tie ordering.
- [DelayQueue](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/concurrent/DelayQueue.html): delayed items.
- [LinkedBlockingDeque](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/concurrent/LinkedBlockingDeque.html): double-ended operations.
- [CountDownLatch](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/concurrent/CountDownLatch.html): one-shot synchronization.
- [Semaphore](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/concurrent/Semaphore.html): permit limits.
- [Condition](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/concurrent/locks/Condition.html): predicate-based wait/signal.
- [ExecutorService](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/concurrent/ExecutorService.html): task/worker/lifecycle management.
- [Object.wait](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/lang/Object.html#wait()): monitor wait, spurious wakeups, and monitor ownership.
- [JMH — Java Microbenchmark Harness](https://openjdk.org/projects/code-tools/jmh/): controlled concurrency benchmarking.

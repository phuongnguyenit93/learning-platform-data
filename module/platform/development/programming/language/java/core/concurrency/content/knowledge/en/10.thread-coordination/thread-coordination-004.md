# Producer–consumer with bounded queues in Java Concurrency

> **Context:** Thread coordination in Java SE, specifically communication between producers and consumers via a **bounded blocking queue**. This lesson covers `BlockingQueue`, `ArrayBlockingQueue`, `LinkedBlockingQueue`, backpressure, error/thread-shutdown handling, and the implementation mechanism using `Lock` + `Condition`. The scope is **general Java concurrency**; Spring-specific APIs and mechanisms belong to a different chapter.

## 1. Learning objectives

After this lesson, you will be able to:

- Explain the **producer–consumer** pattern and why a **bounded-capacity queue** is needed instead of letting producers push data uncontrollably.
- Distinguish the three states—**empty / has data / full queue**—along with the corresponding waiting behaviors of producers and consumers.
- Choose the right API among `put`, `take`, `offer`, `poll`, and timeouts, and know why you must not use `sleep` to wait for data.
- Explain **backpressure** and the handling policies when a system produces data faster than it can consume.
- Use `ArrayBlockingQueue` to build a runnable Java 17 example with capacity, a termination signal, result collection, and `ExecutorService` shutdown.
- Analyze **memory visibility**, FIFO ordering, multiple producers/consumers, the "finished processing" condition, deadlock/starvation risks, and data durability limits.
- Understand that a bounded queue can be built using **one `ReentrantLock` and two `Condition`s**, while knowing when to prefer standard implementations.
- Write tests and monitoring metrics to distinguish **normal congestion with backpressure** from concurrency bugs.

**Core principle:** A bounded queue is the synchronization boundary between **production rate** and **processing rate**. Producers may have to wait when the queue is full, and consumers may have to wait when the queue is empty. Waiting and data handoff must be coordinated using primitives with real concurrency guarantees, not by guessing timing.

## 2. The producer–consumer pattern

A producer creates an **item** or **work item**; a consumer takes the item and processes it. The two roles can run on different threads and at different speeds.

```text
   Producer P1 --\
                  \
   Producer P2 ----> [ BOUNDED QUEUE: capacity = N ] ---> Consumer C1
                  /                 |                   ---> Consumer C2
   Producer P3 --/             0 <= size <= N

Producer waits when full:        size == N
Consumer waits when empty:       size == 0
When item/space is available:    the relevant thread can proceed
```

Two special cases:

- **Empty queue:** A consumer calling a waiting operation like `take()` sleeps until an item arrives, the thread is interrupted, or an event matching the primitive's contract occurs.
- **Full queue:** A producer calling `put()` waits until a consumer removes an item, or the producer is interrupted.

A bounded queue can hold at most **N elements currently in the queue**. That **does not limit the total amount of work already dequeued and being processed**, nor does it stop consumers from continuing to call a slow downstream service. You must account for **in-flight work** when bounding resources across the whole pipeline.

### Real-world examples

- Receiving log events with workers writing them to disk.
- Receiving images with workers transforming/resizing/encoding them.
- Reading data from a large file and passing small batches to multiple CPU workers for processing.
- Receiving internal JVM commands with a single owner updating state.
- Reading messages from an external source and pushing them into an in-memory pipeline with a bounded number of pending items.

This is an **in-process Java model**. When data must not be lost even if the process crashes, an in-memory `BlockingQueue` **does not replace** a broker, persistent log, or transaction store.

## 3. Why is "bounded" a critical property?

Suppose a producer generates an average of **120 items/second**, while a consumer only processes **100 items/second**. If this continues for one minute without any control mechanism, the idealized backlog grows by approximately:

```text
(120 - 100) item/s × 60 s = 1,200 items
```

This is only an estimate under steady rates, not counting bursts, variance, and in-flight items. If the queue is effectively unbounded, the backlog can keep consuming RAM until GC spikes or the application throws `OutOfMemoryError`.

With a queue capacity of 200:

- **The number of queued items** is at most 200, per the queue's invariant.
- When full, `put()` forces the producer to **wait for a consumer to take items**, so pressure propagates back to the production source.
- The system can stabilize the amount of data **held in the queue**, though no magic turns a 100 item/s consumer into a 120 item/s one.
- When the source cannot allow the producer to block (for example, network/event callback threads with deadlines), the program needs an explicit `offer`, timeout, reject, drop, retry, or throttle policy.

**Backpressure** is the ability of the consumption layer to signal "cannot accept more yet" to the production layer. The signal can be **blocking**, boolean `false`, a timeout, an exception, or a throttling mechanism at the calling layer. A bounded queue is one way to establish backpressure, though how the response is handled depends on the application contract.

### Capacity is not throughput

Increasing capacity can absorb short bursts, but it does not increase the average processing speed of consumers. Excessive capacity is not free either: it retains many objects, increases item wait time, and masks downstream bottlenecks.

Choose capacity based on item size, burst level, latency SLA, and observed throughput. Do not use `Integer.MAX_VALUE` as "bounded" if your RAM budget is finite.

## 4. Java's built-in BlockingQueue

`java.util.concurrent.BlockingQueue<E>` is the interface for thread-coordinating queues. Its APIs are designed to handle situations where an item cannot be added or removed immediately.

| Operation | Throws exception if not immediately possible | Returns immediate result | Waits indefinitely until available | Waits up to a timeout |
|---|---|---|---|---|
| Insert | `add(e)` | `offer(e)` → `false` when full | `put(e)` | `offer(e, timeout, unit)` → boolean |
| Remove | `remove()` | `poll()` → `null` when empty | `take()` | `poll(timeout, unit)` → item or `null` |
| Examine head | `element()` | `peek()` | No corresponding blocking method | No corresponding timed method |

**Quick takeaways:**

- `put(e)` waits if full and may throw `InterruptedException`.
- `take()` waits if empty and may throw `InterruptedException`.
- `offer(e)` does not wait for space: when the queue is full, it typically returns `false`.
- `poll()` does not wait for a new item: when empty, it returns `null`.
- `offer(e, time, unit)` and `poll(time, unit)` allow **bounding the wait time** and handling cases where the resource is unavailable.
- `add(e)` can throw `IllegalStateException` when the queue is bounded and has no remaining capacity; `remove()` can throw `NoSuchElementException` if empty.
- Standard `BlockingQueue` implementations **do not allow null items**, in part because `poll` uses `null` as the signal for "no item".

Do not read the result of `peek()` or `size()` and assume the queue will stay the same until the next operation: another thread can modify it between the two calls. If the goal is "wait and then take", call **`take()`** instead of check-then-act with `size()`.

## 5. Choosing the right implementation

### `ArrayBlockingQueue<E>`

```java
BlockingQueue<String> queue = new ArrayBlockingQueue<>(100);
```

This is a **method-body snippet** that requires importing `java.util.concurrent.BlockingQueue` and `java.util.concurrent.ArrayBlockingQueue`.

- Fixed capacity, **must be > 0**.
- FIFO queue ordered by item enqueue order.
- Implementation uses a fixed-size array and internal lock/condition mechanisms.
- Provides the `new ArrayBlockingQueue<>(capacity, fair)` constructor to select a fairness policy for threads waiting for access; fairness can reduce throughput and **does not guarantee** when a job will complete.
- Well suited when the maximum number of buffered items is clearly known and you want relatively predictable memory control.

### `LinkedBlockingQueue<E>`

```java
BlockingQueue<String> queue = new LinkedBlockingQueue<>(100);
```

This is an illustrative snippet requiring `java.util.concurrent.LinkedBlockingQueue`. The implementation uses linked nodes and allows setting capacity in the constructor. It also supports FIFO ordering by enqueue order.

**Be careful:** `new LinkedBlockingQueue<>()` is not bounded to your application's actual budget; it defaults to a capacity of `Integer.MAX_VALUE`. This is a common source of bugs: the system appears to use a thread-safe queue, yet when producers outpace consumers, the backlog can still grow until memory is exhausted. **Always specify a capacity if boundedness is required.**

### Implementations with different semantics

- `SynchronousQueue<E>` has **no internal item buffer**: put/take is a direct handoff mechanism between producer and consumer. It is not the same as `ArrayBlockingQueue<>(1)`.
- `PriorityBlockingQueue<E>` dequeues by **priority ordering**, not as a bounded FIFO queue; it does not provide a hard capacity like `ArrayBlockingQueue`.
- `DelayQueue<E>` uses element eligibility times; it is not a standard bounded FIFO queue.

Each queue type establishes a different contract. Do not swap implementations just because their names all end in "BlockingQueue".

## 6. Runnable Java 17 example: bounding capacity and handing off work

The program has two parts:

1. Demonstrates capacity = 2 using `offer` and `take`: add two items to fill it, attempt to add a third while full and observe `false`; take one item and then add successfully.
2. Runs **one producer and one consumer** using `ExecutorService`, passing three values (5, 7, 9) through a bounded queue and sending a **poison pill** so the consumer knows when to stop. The consumer returns a `Result` to `main` via `Future.get()`.

Create the file **`BoundedQueueDemo.java`**:

```java
import java.util.concurrent.ArrayBlockingQueue;
import java.util.concurrent.BlockingQueue;
import java.util.concurrent.ExecutorService;
import java.util.concurrent.Executors;
import java.util.concurrent.Future;

public class BoundedQueueDemo {
    private static final int STOP = -1;
    record Result(int count, long sum) { }

    public static void main(String[] args) throws Exception {
        BlockingQueue<Integer> bounded = new ArrayBlockingQueue<>(2);
        System.out.println("offer10=" + bounded.offer(10));
        System.out.println("offer20=" + bounded.offer(20));
        System.out.println("offer30WhenFull=" + bounded.offer(30));
        System.out.println("firstTake=" + bounded.take());
        System.out.println("offer30AfterTake=" + bounded.offer(30));
        System.out.println("remaining=" + bounded.take() + "," + bounded.take());

        BlockingQueue<Integer> inbox = new ArrayBlockingQueue<>(2);
        ExecutorService pool = Executors.newFixedThreadPool(2);
        try {
            Future<Result> consumer = pool.submit(() -> {
                int count = 0;
                long sum = 0;
                while (true) {
                    int value = inbox.take();
                    if (value == STOP) break;
                    count++;
                    sum += value;
                }
                return new Result(count, sum);
            });
            Future<?> producer = pool.submit(() -> {
                inbox.put(5);
                inbox.put(7);
                inbox.put(9);
                inbox.put(STOP);
                return null;
            });

            producer.get();
            Result result = consumer.get();
            System.out.println("consumedCount=" + result.count());
            System.out.println("consumedSum=" + result.sum());
        } finally {
            pool.shutdownNow();
        }
    }
}
```

Compile and run with JDK 17 or newer:

```bash
javac --release 17 BoundedQueueDemo.java
java BoundedQueueDemo
```

**Verified stdout from compiling and running:**

```text
offer10=true
offer20=true
offer30WhenFull=false
firstTake=10
offer30AfterTake=true
remaining=20,30
consumedCount=3
consumedSum=21
```

### Explanation of the capacity part

- `new ArrayBlockingQueue<>(2)` initializes an empty queue holding at most two elements.
- `offer(10)` and `offer(20)` succeed; the queue is full.
- `offer(30)` returns `false` **immediately** without waiting for a consumer.
- `take()` removes the FIFO head `10`, creating one free slot.
- The subsequent `offer(30)` succeeds; the two remaining items are `20` and `30` in order.
- This part runs in `main` to produce **deterministic output**, independent of thread scheduling.

### Explanation of the producer–consumer part

- `inbox` has capacity 2, so the producer may block at `put(9)` or `put(STOP)` if the consumer has not kept up.
- `inbox.put(...)` both inserts the item and coordinates when the queue is full; no manual `wait/notify` code is needed.
- The consumer calls `inbox.take()` in a loop; when the queue is empty, it waits for the producer.
- The value `STOP=-1` is reserved as the termination signal. The three valid items are 5, 7, 9, so the consumer accurately counts 3 and sums to 21.
- `producer.get()` waits for the producer to finish enqueuing all three items and `STOP`; `consumer.get()` waits for the consumer to actually finish processing and return the result. An empty queue alone **is not proof** that all items have been processed.
- The pool has **two worker threads**, enough for both the producer and consumer to make progress even when one is blocked.
- `finally { pool.shutdownNow(); }` in the demo is a cleanup path after the `get()` calls; on a normal run both tasks have already completed. In real applications, you need a dedicated graceful shutdown strategy and timeout/cancellation handling, not `shutdownNow` as a way to "wait for completion".

**Note on STOP:** If `-1` can be valid data, this protocol is **wrong** because the consumer will misinterpret data as a stop command. In serious designs, use an explicit message type—for example, a sealed interface `Message` with `Data` and `Stop`—or a separate shutdown protocol. With multiple consumers, you need a policy to deliver the stop signal to each consumer or use another mechanism so they do not stay blocked in `take()`.

## 7. Why can a thread-safe queue still have an unsafe payload?

`BlockingQueue` protects **the queue structure and enqueue/dequeue operations**. The Java concurrency API also specifies **memory consistency effects**: actions in a thread **prior to placing an object into a queue** *happen-before* actions in another thread **subsequent to accessing or removing that object from the queue**.

For example:

```java
// Illustration: queue is BlockingQueue<Message> and Message is immutable.
Message message = new Message(42, "ready");
queue.put(message);
// Another thread: Message received = queue.take();
// State prepared before put is safely published per the contract.
```

This is an illustrative snippet; `Message` and `queue` are declared externally, not as a standalone program.

**However, a queue does not make a mutable object thread-safe forever.** If a producer puts an `ArrayList` reference into the queue and then continues calling `add` on that same list while a consumer iterates over it, the two sides can race on the **payload**, even though `put/take` themselves are correct.

Common safe approaches:

1. **Immutable message:** Build the data completely and publish it as a record or immutable fields; if it contains collections, defensively copy them and do not share dangerous mutable elements.
2. **Ownership transfer:** After enqueuing a mutable message, the producer **stops modifying or reading-while-mutating it**; the consumer becomes the owner until it hands it off further.
3. **Synchronized payload:** Every read and write of the payload uses the same synchronization protocol if shared mutation is unavoidable.
4. **Snapshot/copy:** If the producer must keep modifying the original object, put a separate snapshot into the queue.

`Future.get()` adds a memory consistency relationship for the task result, but it does not replace queue publication when consumers need to read data while the producer is still active.

## 8. Backpressure: choosing a policy when full

There are several options depending on workload characteristics and SLOs:

| Policy | Typical primitive | Benefits | Risks / what must be defined |
|---|---|---|---|
| **Block producer** | `queue.put(item)` | No items dropped merely due to fullness; pressure propagates upstream | Producer may hang for a long time, holding resources or occupying a worker thread |
| **Fail fast / reject** | `queue.offer(item)` | Caller knows immediately that the queue is full | Caller must handle `false`; ignoring it silently loses work |
| **Bounded wait** | `queue.offer(item, timeout, unit)` | Bounds how long a producer can wait | On timeout, must retry/drop/report per contract; timeout does not mean enqueued |
| **Conditional retry** | `offer` + bounded retries | Can ride out short bursts | Unbounded retries create busy-wait loops or amplify system pressure |
| **Intentional drop** | Only for droppable data | Preserves latency, prevents backlog | Data loss; must have metrics and clearly specify which items may be dropped |
| **Rate limiting / upstream throttle** | Limiting mechanism at producer/source | Prevents backlog before entering the queue | Requires multi-layer coordination and feedback to the source |
| **Scale consumers** | Add workers when work is parallelizable | Increases consumption capacity | May overload downstream further or break ordering/invariants |

**You cannot simultaneously guarantee "no lost items", "producer never waits", "finite RAM", and "arbitrarily slow consumer" without additional storage or processing capacity.** The design must choose a trade-off or offload the backlog to a durable layer.

### Timed offer example

```java
boolean accepted = queue.offer(item, 250, TimeUnit.MILLISECONDS);
if (!accepted) {
    // Per application contract: reject, persist, record metric, or bounded retry.
}
```

This is a **method-body snippet** that must declare/handle `InterruptedException`, with `java.util.concurrent.TimeUnit` imported and `queue` and `item` already defined. `250ms` is only an illustrative number, not a fixed SLA recommendation.

A correct retry must track **whether the item was actually enqueued**. If the producer does not know whether a downstream side effect already happened, retrying can create logical duplicates. Exactly-once semantics are not guaranteed by an in-memory queue; use an idempotency key or transaction when work has external effects.

## 9. Waiting properly: do not check size and sleep

Pattern to avoid:

```java
// Anti-pattern: polling and guessing timing.
while (queue.isEmpty()) {
    Thread.sleep(10);
}
Item item = queue.remove();
```

This is an incomplete illustrative snippet; `Item` and `queue` are declared externally. Problems:

- `isEmpty()` is only a point-in-time snapshot; between the check and `remove()`, another thread can drain the queue.
- `sleep` does not wait for an exact event and can introduce unnecessary latency.
- Multiple polling consumers increase CPU/wakeups or force a trade-off between latency and sleep duration.
- `Thread.sleep()` does not establish a memory-ordering protocol for shared state outside the queue.

Direct pattern:

```java
Item item = queue.take();
process(item);
```

This is also an illustrative snippet inside a method that `throws InterruptedException`, where `queue` is a `BlockingQueue<Item>`. `take()` waits until an item is available, removes one item, and returns it; there is no need to build your own wait loop for the standard case.

Similarly, do not write:

```java
if (queue.remainingCapacity() > 0) {
    queue.add(item);
}
```

`remainingCapacity()` may have changed before `add` if another producer is active. If the goal is "try to add if space is available", call **`offer(item)`** and check the boolean return value. Only use `remainingCapacity` for observation/estimation, not to *reserve* a slot.

## 10. Multiple producers and consumers: FIFO does not guarantee completion order

With `ArrayBlockingQueue` and `LinkedBlockingQueue`, items are dequeued in FIFO order of **successful enqueue order**. However, you must distinguish several different orderings:

- **Producer creation order:** P1 may create A before P2 creates B.
- **Enqueue order:** P2 may be scheduled to `put(B)` into the queue before `put(A)`.
- **Dequeue order:** For a FIFO queue, consumers take items in the order they actually entered the queue.
- **Processing completion order:** With multiple consumers, C1 takes A first but processes slowly; C2 takes B later but finishes first.

```text
FIFO Queue:       A -> B -> C
Consumer C1:      take(A) ----------- done(A)
Consumer C2:           take(B) -- done(B)
Take order:       A, B
Completion order: B, A
```

FIFO **does not turn a multi-consumer workload into sequential execution**. If business logic requires side effects in strict order, you need a single sequential owner or an appropriate sequence/commit protocol. Increasing the number of consumers is only safe when items can be processed independently or when relevant invariants are synchronized.

### With multiple producers, data order is not absolute wall-clock order

Do not assume items from different producers will share a global order matching timestamps assigned independently by each producer. If you need a business total order, define who assigns the sequence number and at which stage (before enqueue, at enqueue, or at commit). A sequence number can be attached to the message, but **completion** order still requires separate coordination.

### Is one message processed by multiple consumers?

For a standard queue, a single `take()` **removes the item from the queue**, so an item is not broadcast to all consumers just because they all call `take()`. This is **work distribution**, not pub/sub. If every consumer must receive the same event, you need to fan out into multiple queues or use an explicit pub/sub system.

## 11. Stopping consumers safely: poison pills, interrupts, and completion

### Poison pill

A poison pill is a special item telling a consumer to exit its `take` loop:

```java
while (true) {
    Message message = queue.take();
    if (message instanceof Stop) break;
    handle(message);
}
```

This is an illustrative snippet; `Message` is a type representing data/stop, `Stop` is a subtype, `queue` is `BlockingQueue<Message>`, and `handle` is a defined method; the method must handle or declare `InterruptedException`.

You must ensure:

1. **Stop is not valid data.** Use a typed message to avoid sentinel collisions.
2. **Stop is placed after all items to be processed.** With multiple producers, you must know that **all producers have stopped enqueuing** before sending the final stop signal; otherwise data can arrive after `Stop`.
3. **Multiple consumers:** One `Stop` is usually consumed by only **one** consumer. If M consumers are blocked in `take()` using this same mechanism, you typically need M `Stop` items or a different shutdown protocol.
4. **Bounded queue:** Enqueuing `Stop` can also block when the queue is full; consumers must be making progress to free space, or you need an appropriate timed/cancel policy.
5. **Stop only confirms the consumer saw the signal**; a caller wanting to know the consumer **finished processing** must wait on `Future.get()`/`join()` or a reliable completion signal.

**Do not use `queue.isEmpty()` as a stop signal:** the queue can be temporarily empty between producer emissions, or all items may have been taken by consumers but not yet finished processing.

### Interrupts and cancellation

`put()`/`take()` can throw `InterruptedException`. A waiting thread must have a clear policy:

- When the API allows, **propagate** the exception so the caller decides on cancellation.
- When catching at a task boundary where you cannot rethrow, restore the interrupt status with `Thread.currentThread().interrupt()` and exit/clean up resources.
- Do not swallow it with an empty catch and keep waiting forever: shutdown may never complete.
- `Thread.interrupt()` does not guarantee transaction rollback. An item already dequeued and partially processed needs its own retry/idempotency policy.

Example handling inside a worker:

```java
try {
    while (running) {
        Item item = queue.take();
        process(item);
    }
} catch (InterruptedException e) {
    Thread.currentThread().interrupt();
    // Cleanup/cancel per worker contract.
}
```

This is an illustrative snippet inside a method with `running`, `Item`, `queue`, and `process` defined externally. If an interrupt occurs during non-blocking task processing, cancellation also needs other logic to detect and stop—you cannot rely solely on `take()`.

### Graceful shutdown vs. shutdownNow

`ExecutorService.shutdown()` stops accepting new tasks and lets already-submitted tasks continue per contract; it **does not wait for all tasks to finish**. Use `Future.get()`/`awaitTermination()` with a timeout when completion is required. `shutdownNow()` attempts to stop running tasks (typically via interrupt) and returns tasks that had not started, **without guaranteeing that every task stops immediately**.

A good shutdown protocol must decide: whether producers stop before or after, how to drain the backlog, when to send stop signals, how long the timeout is, and how in-flight items are handled on failure.

## 12. A subtle deadlock: producer and consumer sharing a pool that is too small

Suppose an executor has **only one worker**:

```java
// Bug illustration, not complete runnable code.
ExecutorService pool = Executors.newSingleThreadExecutor();
BlockingQueue<Integer> q = new ArrayBlockingQueue<>(1);

pool.submit(() -> {
    q.put(1);
    q.put(2); // blocks because the queue is full
    return null;
});
pool.submit(() -> q.take()); // this task is queued, with no worker to run it
```

The snippet above is a **deadlock design illustration** using `java.util.concurrent` imports. The first producer holds the sole worker, inserts 1, and then blocks on `put(2)`. The consumer task sits in the executor's queue and cannot run until the producer finishes; yet the producer is waiting for the consumer to take an item. This is a wait cycle that **cannot make progress**.

Fixes depend on architecture:

- Use separate workers/execution resources so consumers **can** run while producers block.
- Do not submit interdependent blocking producers and consumers to an executor with insufficient capacity.
- Choose appropriate nonblocking/timed submissions, or structure data flow with completion stages where the semantics fit.
- If producer and consumer share a pipeline, ensure there is always an escape path when the queue is full or when one side fails.

Do not assume "there is a thread pool, so tasks will definitely run in parallel." The pool size, the executor's task queue, and the bounded data queue are **separate queues**, and dependencies between them can cause deadlock.

## 13. Using Lock + two Conditions to understand bounded queue internals

When implementing a bounded buffer yourself, you must protect the invariant:

```text
0 <= queue.size() <= capacity

Producer may add if:     queue.size() < capacity
Consumer may take if:    !queue.isEmpty()
```

One `ReentrantLock` protects the queue alongside two conditions:

- `notFull`: producers wait for "space available".
- `notEmpty`: consumers wait for "item available".

After a successful `put`, notify a consumer via `notEmpty.signal()`. After a successful `take`, notify a producer via `notFull.signal()`.

### Educational implementation: TinyBoundedBuffer.java

```java
import java.util.ArrayDeque;
import java.util.Deque;
import java.util.Objects;
import java.util.concurrent.locks.Condition;
import java.util.concurrent.locks.ReentrantLock;

public final class TinyBoundedBuffer<E> {
    private final int capacity;
    private final Deque<E> queue = new ArrayDeque<>();
    private final ReentrantLock lock = new ReentrantLock();
    private final Condition notEmpty = lock.newCondition();
    private final Condition notFull = lock.newCondition();

    public TinyBoundedBuffer(int capacity) {
        if (capacity <= 0) throw new IllegalArgumentException("capacity must be > 0");
        this.capacity = capacity;
    }

    public void put(E element) throws InterruptedException {
        Objects.requireNonNull(element);
        lock.lockInterruptibly();
        try {
            while (queue.size() == capacity) {
                notFull.await();
            }
            queue.addLast(element);
            notEmpty.signal();
        } finally {
            lock.unlock();
        }
    }

    public E take() throws InterruptedException {
        lock.lockInterruptibly();
        try {
            while (queue.isEmpty()) {
                notEmpty.await();
            }
            E element = queue.removeFirst();
            notFull.signal();
            return element;
        } finally {
            lock.unlock();
        }
    }
}
```

This class has been **compiled successfully with `javac --release 17`**. It is a standalone Java class (`TinyBoundedBuffer.java`) without a `main` method, so it cannot be run directly via `java TinyBoundedBuffer`. You can create a separate test driver to call `put/take`.

### Detailed analysis

1. The constructor rejects `capacity <= 0` because this bounded buffer requires at least one slot.
2. `ArrayDeque` is **not thread-safe on its own**; all accesses to `queue` are protected by the same `lock`.
3. The producer acquires the lock using `lockInterruptibly()` so cancellation works even during the **lock acquisition wait** phase.
4. `while (queue.size() == capacity) notFull.await()` checks the predicate before waiting; `await()` releases the lock while waiting and **reacquires it before returning**.
5. When space is available, the producer adds the item, signals the consumer group waiting on `notEmpty`, and releases the lock in `finally`.
6. The consumer is symmetric: when empty, it awaits `notEmpty`; when an item is present, it removes from the head, signals `notFull`, and returns the item.
7. `while` is mandatory because of spurious wakeups, `signalAll` from elsewhere, or another thread grabbing the resource before the waiter reacquires the lock.
8. `signal()` does not release the lock immediately. The waiter can only proceed after the lock-holding thread exits the critical section and the waiter reacquires the lock.
9. If `await()` is interrupted, it throws `InterruptedException` per contract; `finally` still releases the lock after it has been reacquired per `ReentrantLock` `Condition` semantics.
10. `Objects.requireNonNull` rejects `null` because `ArrayDeque` does not allow `null` and because `null` is commonly used as an "empty" marker in queue APIs.

**Intentional limitations:** This class does not implement `offer`, `poll`, timeouts, `size`, fairness, close/shutdown, batch operations, metrics, cancellation on consumer failure, or production edge cases. It only illustrates the invariant and wait conditions. For most use cases, using the standard `ArrayBlockingQueue` is more maintainable and reliable.

### Why must there be two Conditions?

If producers and consumers share a single condition queue, `signal()` can wake up a waiter **from the wrong group**. For example, after a `take`, you need to wake a producer waiting on a full queue, not wake another consumer waiting on an empty queue. Two conditions cleanly separate the roles and reduce unnecessary wakeups.

`signalAll()` can be used when a state change lets multiple waiters proceed, or during shutdown to wake all groups to check a stop flag. However, waking everyone when only one new slot opens often causes a thundering herd: many threads contend for the lock only for most of them to go right back to waiting.

## 14. What happens with the Java Memory Model?

A queue is a **concurrency primitive**. The `BlockingQueue` Javadoc describes its memory-consistency effects: actions in a producer thread prior to placing an object into a queue *happen-before* actions in a consumer thread subsequent to accessing or removing that object.

This matters when an item contains data constructed by the producer before publication:

```java
// Illustration inside a method; record creates an immutable payload:
record Event(int id, String text) {}

BlockingQueue<Event> inbox = new ArrayBlockingQueue<>(10);
Event event = new Event(7, "created");
inbox.put(event);
// Another thread takes via inbox.take() and reads id and text.
```

This is an illustrative snippet without `main` and requires handling/declaring `InterruptedException`. When the consumer receives the event, it can reliably read the values prepared before enqueue per the publication contract.

However:

- A queue does not make every mutable field of an object atomic.
- If the sender continues mutating the payload after enqueue, it can create a data race.
- To preserve multi-field invariants, use an immutable snapshot or transfer ownership; safely reading a reference does not synchronize mutations inside the object graph.
- If the producer crashes while constructing the item **before enqueue**, the item is never transmitted; if the process crashes while the queue still holds data, the in-memory queue can lose the entire backlog.
- A consumer taking an item does not mean its side effect has committed successfully.

**Manual `volatile`/`synchronized` does not need to wrap every `put/take`** just to protect a standard `BlockingQueue` structure; the implementation already provides synchronization. However, if consumers and producers share **other state outside the queue**, that state still needs its own thread-safety protocol.

## 15. Failure handling: dequeue is not "processed successfully"

In producer–consumer systems, distinguish four milestones:

```text
Produce item -> enqueue succeeds -> dequeue succeeds
                                 -> process side effect -> confirm completion
```

`take()` only confirms that a consumer has removed the item. If the consumer throws an exception inside `process(item)`, the item is **no longer in the queue**. A standard `BlockingQueue` has no built-in acknowledgment/requeue mechanism like a durable broker.

For example:

```java
Item item = queue.take();
process(item); // May fail after the item has already been removed from the queue.
```

This is an illustrative snippet. Guaranteeing no job loss per contract requires a dedicated mechanism:

- Persist the job durably before enqueuing, or use a broker with proper ack/redelivery.
- Design a retry queue / dead-letter mechanism to handle errors with a bounded number of attempts.
- Use an idempotency key for side effects that may be re-executed.
- Track in-flight jobs and completion status, not just `size()`.
- Define behavior when a consumer process dies, the JVM exits, a timeout occurs, or the outcome is ambiguous.

**Do not claim "exactly once" solely because of `ArrayBlockingQueue`.** In a normal execution, an element is removed from the queue by a single `take`. That is completely different from "external side effects happen strictly once across crashes and retries."

## 16. Sizing capacity and consumer count

There is no single optimal capacity for every program. A practical process:

1. **Measure arrival rate**, in items/s under average and burst conditions.
2. **Measure service rate** per consumer, distinguishing CPU-bound and I/O-bound work.
3. **Estimate memory cost per item**, including the object graph, payload, and metadata.
4. **Choose a backlog budget** based on available RAM and maximum allowable queueing latency.
5. **Bound total in-flight work** if each consumer holds large items or expensive side-effect resources.
6. **Stress-test with bursts and slow downstreams**, measuring rejections/timeouts, blocked producer time, queue depth, and p95/p99 end-to-end latency.
7. **Tune consumer concurrency** to the actual bottleneck, avoiding opening too many concurrent requests to a quota-limited downstream.

Suppose a queue has capacity 500 and each item holds about 20 KiB of payload plus related objects: the backlog alone can occupy around **10 MiB** before counting overhead, references, GC metadata, or in-flight items. This is an illustrative estimate; measure actual heap usage on real data before choosing production capacity.

### Rate and latency relationship

If the current backlog is roughly 200 items, consumers process steadily at about 50 items/s, and no new items arrive, the idealized drain time is about `200 / 50 = 4 seconds`. When producers keep adding items, the numbers change; when processing time has high variance, p99 latency can be much higher than the mean.

Little's Law (`L = λW`) can help sanity-check measurements for a stable system with a well-defined measurement boundary, but **do not use it as a standalone formula to size capacity** in systems with large bursts or instability.

### How far back can backpressure propagate?

If the producer runs on a request thread, a blocking `put()` can push request latency past SLA and trigger timeouts. If the producer reads from a socket, blocking can cause upstream buffers to fill. If the producer is a task in an executor, blocking can starve workers needed by other important tasks.

Therefore, simply **having a bounded queue** is not enough; you must know how upstream reacts to fullness and whether there is any backlog **ahead of the queue**.

## 17. Metrics and diagnosing a bounded queue

Useful signals:

| Metric / observation | Interpretation | Caveat |
|---|---|---|
| `queue.size()` over time | Current backlog, accumulation trend | Only a snapshot; do not use for atomic coordination |
| `remainingCapacity()` | Free slots at the moment of observation | Not a reservation; changes immediately if another producer enqueues |
| `put` / timed `offer` duration | How long producers experience backpressure | Distinguish wait time from item creation time |
| `take` / `poll` duration | Consumers waiting due to lack of items | Waiting on an empty queue can be normal idle time |
| Accepted / rejected / timeouts | Work generation pressure vs. capacity | Must account for drop/retry policy and duplicate counts |
| In-flight count | Items being processed after dequeue | Cannot be inferred from `queue.size()` |
| Processing latency / throughput | Consumer and downstream performance | A full queue may be caused by slow consumers, not queue lock contention |
| Error / retry / dead-letter count | Ability to make progress after failures | Unbounded retries can create a self-inflicted storm |

While the JVM is running, you can collect a thread dump:

```bash
jcmd <PID> Thread.print -l
```

Replace `<PID>` with the actual process ID. With standard queues, stacks may show `ArrayBlockingQueue.put/take`, `ConditionObject.await`, and `LockSupport.park` when threads wait on a full/empty queue. `WAITING (parking)` usually means waiting on a condition and **is not enough to conclude deadlock**.

If you need to measure wait durations, use JFR and an appropriate profiler (depending on JDK/JVM, event settings, and workload). A thread dump is a snapshot; observing an idle consumer waiting on an empty queue can be completely expected behavior.

## 18. Testing producer–consumer properly

A good test does not just ask "did the program print the right thing once?". It must cover invariants, ordering, and waiting scenarios:

### Core invariants

- `0 <= size <= capacity` across all states observable through the queue API.
- With one producer and one consumer, items are dequeued in queue FIFO order.
- Without drops, cancellations, or errors, and once all producers complete, every enqueued item must be processed by consumers per contract.
- No data item is mistaken for a poison pill.
- On shutdown, threads do not remain blocked indefinitely in `put/take`.
- When processing fails, the system follows an explicit retry, dead-letter, or error-reporting policy.

### Testing boundary conditions

1. **Empty queue:** Consumer waits, then producer enqueues an item; consumer proceeds.
2. **Full queue:** Producer using `offer` receives `false`; with `put`, producer waits until space opens.
3. **FIFO:** One producer enqueues A, B, C; one consumer takes exactly A, B, C.
4. **Many producers:** All items with IDs are received accurately per contract; do not assume a global order without a sequence number.
5. **Many consumers:** Verify no item is processed twice on the normal path without retries; completion order may differ from dequeue order.
6. **Timeout:** Timed `offer` returns `false` when no slot opens in time; timed `poll` returns `null` when no item arrives.
7. **Interrupt:** A waiting producer/consumer can exit per the cancellation policy and does not hold resources indefinitely.
8. **Shutdown:** `STOP` is not placed before the last producer finishes; all consumers are notified to stop; the pool completes or hits its deadline.
9. **Failure:** A consumer throws an exception mid-run; `main` receives the error via `Future.get()` and triggers the recovery policy.
10. **Memory pressure:** Large payloads, sudden backlog bursts; capacity bounds queued items, but in-flight items and other queues must also be measured.

### Synchronizing tests with primitives, not guessing with sleep

`CountDownLatch` or `CyclicBarrier` can coordinate tests so you know a producer has reached a checkpoint. Use `Future.get(timeout, unit)` so tests fail cleanly if progress stalls. `Thread.sleep` can help simulate slow processing, but **it is not a tool to guarantee** that a producer has blocked or a consumer has received an item.

For example, place assertion logic after Futures complete: the number of items processed by consumers equals the number of items successfully enqueued by producers, checksums match, and all tasks exit cleanly.

## 19. Common mistakes

1. **Using `new LinkedBlockingQueue<>()` and assuming a small capacity.** Default capacity is `Integer.MAX_VALUE`; specify an explicit bound when boundedness is needed.
2. **Ignoring `offer() == false`.** Work can be lost silently. The boolean return value is part of the contract that must be handled.
3. **Using `queue.size()` to decide whether `put/take` can definitely proceed.** Race between check and action; use the atomic operations provided by the queue.
4. **Using `Thread.sleep` instead of `take`.** Polling adds latency, complicates cancellation, and is unnecessary.
5. **Treating an empty queue as meaning all work is done.** Consumers may have dequeued items and still be processing them.
6. **Sending only one poison pill for N consumers.** N−1 consumers may remain blocked in `take`.
7. **Sending a poison pill before all producers have stopped.** Data may still be enqueued after the stop signal and get left behind.
8. **Using a poison pill that can collide with valid data.** Use a typed message or a marker guaranteed not to collide.
9. **Putting interdependent producer and consumer in an executor with only one worker.** The producer blocks when the queue is full, and the consumer task never gets a worker.
10. **Assuming FIFO dequeue means FIFO completion.** With multiple consumers, tasks finish at different speeds.
11. **Continuing to mutate a mutable payload after enqueue.** A thread-safe queue does not protect internal item state.
12. **Assuming `take` means "processed/committed".** Dequeue only removes the item; side effects can still fail.
13. **Swallowing `InterruptedException`.** Shutdown or cancellation can hang indefinitely.
14. **Calling `shutdownNow` and assuming all tasks have stopped.** `shutdownNow` is a cancellation attempt; you must observe termination and handle interruption.
15. **Using an unbounded queue to "avoid losing items".** Trades that for OOM risk when upstream outpaces downstream.
16. **Increasing capacity endlessly to fix slow consumers.** Capacity absorbs bursts; it does not replace sustainable processing throughput.
17. **Signaling the wrong group in a custom queue.** Producers must wait on `notFull`, consumers on `notEmpty`; signal the right condition.
18. **Using `if` instead of `while` around `Condition.await`.** Spurious wakeups or contention after a signal can invalidate the predicate.
19. **Forgetting `finally { lock.unlock(); }` in a custom implementation.** An exception can leave an explicit lock held forever.
20. **Placing non-idempotent side effects inside unbounded retries.** Processing can repeat; you need an explicit commit/retry policy.

## 20. Choosing a model and when not to build your own queue

| Need | Starting choice |
|---|---|
| Basic bounded FIFO buffer inside the JVM | `ArrayBlockingQueue<>(capacity)` |
| Node-based bounded FIFO with explicit capacity | `LinkedBlockingQueue<>(capacity)` |
| No buffering; producer meets consumer directly | `SynchronousQueue` |
| Single task returning a result to caller, no separate data queue needed | `Callable` + `Future` / `ExecutorService` |
| Phased coordination or waiting for an event | `CountDownLatch`, `Phaser`, or `Condition` depending on predicate |
| Sequential single state owner receiving commands | Single consumer + bounded queue, shutdown/ack protocol |
| Durability, replay, and redelivery across crashes | Persistent broker/log or transactional storage |
| Protecting multi-field invariants while processing items | Properly scoped locks/atomics/immutable state **outside** the queue |

Choose **the simplest primitive that satisfies the contract**. Writing a bounded buffer with `Condition` is useful for learning, but a production implementation must handle a large set of concerns absent from the example: timeouts, fairness, exception safety, shutdown, interrupts, batch draining, and metrics.

## 21. Self-check questions with answers

**Q1.** `new ArrayBlockingQueue<>(2)` already contains two items. What does `offer(third)` do?  
**Answer:** Returns `false` immediately when no slot is available, without waiting. If you use `put(third)`, the producer waits while full.

**Q2.** `take()` is called on an empty queue; what happens?  
**Answer:** The thread waits until an item is available to take or it is interrupted; no `sleep` polling is needed.

**Q3.** Why can a bounded queue reduce OOM risk without increasing throughput?  
**Answer:** It caps the number of buffered items and can block or reject producers; consumer/downstream speed does not increase automatically.

**Q4.** Is `LinkedBlockingQueue<>()` without a capacity argument bounded to 100 items?  
**Answer:** No. Its default capacity is `Integer.MAX_VALUE`, which can allow huge backlogs; specify a limit based on resources.

**Q5.** Two consumers take A then B in FIFO order; is A guaranteed to finish processing before B?  
**Answer:** No. If C2 processes B faster than C1 processes A, B can finish first.

**Q6.** A producer puts an `ArrayList` into the queue and keeps modifying it; a consumer iterates over the same list. Does `BlockingQueue` protect the list?  
**Answer:** No. The queue synchronizes enqueue/dequeue and publication; mutable payloads still need an immutable snapshot, ownership transfer, or separate locking.

**Q7.** Three consumers are calling `take()` and there is only one poison pill; can the system hang on shutdown?  
**Answer:** Yes. Only one consumer takes `Stop`; the other consumers can keep waiting. You need to send enough signals or use another protocol.

**Q8.** Does `queue.isEmpty() == true` prove all tasks have finished processing?  
**Answer:** No. Items may still be in-flight inside consumers. Use `Future.get()` or completion tracking to verify results.

**Q9.** Why shouldn't `remainingCapacity() > 0` be used as a "slot reservation"?  
**Answer:** Another producer can enqueue between the check and the insert. `offer` is the operation that decides success or failure atomically at execution time.

**Q10.** When implementing a queue with `ReentrantLock`, why must you use `while` around `await`?  
**Answer:** A waiter can wake up spuriously, or another thread can take the item/slot before the waiter reacquires the lock. Always recheck the predicate.

**Q11.** A producer in a single-worker executor blocks in `put` when the queue is full, while the consumer task is waiting in the same executor. Why can this deadlock?  
**Answer:** The producer holds the sole worker; the consumer needs that worker to take an item but cannot run; the producer will not release the worker until the consumer makes progress.

**Q12.** Can you trigger a payment side effect right after `take` and claim it will never happen twice on retry?  
**Answer:** No. An in-JVM queue does not provide exactly-once external side effects; retries or crashes can cause duplicates, so idempotency/transactions are required.

**Q13.** Does `signal()` in a custom queue immediately release the lock and let the waiter run?  
**Answer:** No. The caller still holds the lock until `unlock`; the waiter must reacquire the lock and recheck the predicate.

**Q14.** A queue of capacity 100 has no items, and the consumer is in `WAITING (parking)`. Is this definitely a deadlock?  
**Answer:** No. The consumer may simply be waiting for items as designed. You must inspect producers, predicates, stacks, shutdown state, and ability to make progress.

**Q15.** When you want a producer to wait at most 300ms, which API should you choose?  
**Answer:** `offer(item, 300, TimeUnit.MILLISECONDS)` and handle `false` / `InterruptedException` per contract.

## 22. References

- [Java SE 17 — BlockingQueue](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/concurrent/BlockingQueue.html): method groups and memory-consistency effects.
- [Java SE 17 — ArrayBlockingQueue](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/concurrent/ArrayBlockingQueue.html): capacity, FIFO, fairness, and blocking operations.
- [Java SE 17 — LinkedBlockingQueue](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/concurrent/LinkedBlockingQueue.html): linked-node queue and capacity constructors.
- [Java SE 17 — SynchronousQueue](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/concurrent/SynchronousQueue.html): handoff with no queue storage.
- [Java SE 17 — ReentrantLock](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/concurrent/locks/ReentrantLock.html): explicit lock, unlock, and interruptible acquisition.
- [Java SE 17 — Condition](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/concurrent/locks/Condition.html): `await`, `signal`, `signalAll`, and predicate wait loops.
- [Java SE 17 — ExecutorService](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/concurrent/ExecutorService.html): lifecycle, shutdown, and submission.
- [Java SE 17 — Future](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/concurrent/Future.html): completion and handling task results/exceptions.
- [JLS Java SE 17 — Threads and Locks](https://docs.oracle.com/javase/specs/jls/se17/html/jls-17.html): Java Memory Model and happens-before.

**Conclusion:** The producer–consumer pattern with a bounded queue must simultaneously address **safe data sharing**, **backlog bounding**, **progress on both sides**, and **work lifecycle**. Start with `ArrayBlockingQueue` or `LinkedBlockingQueue` with an explicit capacity, use `put/take` or timed `offer/poll` per contract, handle interruption and shutdown decisively, do not treat an empty queue as completed processing, and do not confuse enqueue/dequeue with a durable transaction.
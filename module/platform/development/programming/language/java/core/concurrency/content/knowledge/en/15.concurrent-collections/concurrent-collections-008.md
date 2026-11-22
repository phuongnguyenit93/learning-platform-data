# PriorityBlockingQueue, DelayQueue, and SynchronousQueue in Java Concurrency

Among Java's **concurrent collections**, not every queue follows the FIFO "insert at tail, remove from head" rule. Some queues select elements by **priority**, some only allow taking an element **after its expiration time**, and some **store no elements at all**, performing only a direct handoff between two threads.

Three types to distinguish:

- **`PriorityBlockingQueue<E>`**: a thread-safe queue that retrieves elements in **priority order** defined by `Comparable` or a `Comparator`. It has no configurable capacity limit in its API.
- **`DelayQueue<E extends Delayed>`**: a queue of elements with expiration times. `take()` only returns **the head element when its delay has expired**; other elements already in the queue that have not yet expired still cannot be taken.
- **`SynchronousQueue<E>`**: a **zero-capacity queue**. Every `put` must pair with a corresponding `take` operation; no backlog is stored inside the queue.

All three belong to `java.util.concurrent` and implement `BlockingQueue<E>`, helping coordinate between producers and consumers without manually writing `wait/notify`. However, **how they wait, how they order elements, and how they accept work** differ greatly. This article focuses on core Java, without depending on Spring or libraries outside the JDK. The examples compile with Java 17+.

## 1. BlockingQueue Is a Shared Contract, Not Identical Behavior

`BlockingQueue<E>` provides these method groups:

| Need | Non-blocking | Unbounded wait | Timed wait |
|---|---|---|---|
| Insert element | `offer(e)` returns boolean; `add(e)` may throw when it cannot be accepted | `put(e)` | `offer(e, timeout, unit)` |
| Retrieve and remove element | `poll()` returns element or `null`; `remove()` may throw if no element is available | `take()` | `poll(timeout, unit)` |
| Inspect head element | `peek()` | No corresponding blocking operation | No corresponding blocking operation |

For a bounded FIFO queue like `ArrayBlockingQueue`, `put` waits when full and `take` waits when empty. However, the three queues in this article have their own conditions:

- **PriorityBlockingQueue:** has no application-imposed bound, so `put` normally **does not wait for space**; `take` waits when the queue is empty.
- **DelayQueue:** has no application-imposed bound, so `put` normally does not wait for space; `take` waits when **there is no expired element at the head**. A queue with `size() > 0` can still cause `take` to keep waiting.
- **SynchronousQueue:** has no storage slots, so `put` waits for a **pairing consumer** and `take` waits for a **pairing producer**; `offer(e)` without a timeout normally returns `false` if no consumer is immediately ready to receive.

None of these three queue types accepts `null` as an element. Therefore, `poll()` returning `null` is a signal that "nothing could be retrieved yet," but the reason may be **empty, not yet expired, or no pairing handoff**.

## 2. PriorityBlockingQueue: High-Priority Elements Are Taken First

`PriorityBlockingQueue` is a blocking queue built on a heap-based priority mechanism. The ordering at the head of the queue is determined by:

1. **Natural ordering** when type `E` implements `Comparable<E>`, or
2. A **`Comparator`** passed to the constructor.

A "high-priority" value is **not the larger number by default**. With an ascending comparator on `priority`, smaller numbers come first. If you want larger numbers to be taken first, you can reverse the comparator.

```java
PriorityBlockingQueue<Integer> queue =
        new PriorityBlockingQueue<>();

queue.offer(30);
queue.offer(10);
queue.offer(20);
// The next three poll calls return: 10, 20, 30.
```

This is a **snippet** and requires importing `java.util.concurrent.PriorityBlockingQueue`. Items are added in the order 30 → 10 → 20, but retrieved in the order 10 → 20 → 30.

### Properties to Remember

- **Not FIFO:** the queue selects elements according to comparator/natural ordering.
- **No automatic tie-breaking stability for equal elements:** two elements with `compare(a,b)==0` are not guaranteed to be retrieved in enqueue order.
- **Not bounded by user-specified capacity:** the constructor parameter `initialCapacity` only specifies the **initial storage capacity**, not a hard limit.
- **`remainingCapacity()` returns `Integer.MAX_VALUE`** by contract, which does not mean the JVM heap has that many free slots.
- **Can encounter `OutOfMemoryError`** if producers continuously enqueue faster than consumers dequeue.
- **The iterator does not guarantee returning elements in priority order.** To process in the exact order, use `poll()`/`take()` (or copy and sort for display).
- **The sort key must remain stable while the element is in the queue:** if you mutate a field affecting the comparator after `offer`, the heap structure does not automatically reorder for that change.

### Example 1 — Priority and a Stable Tie-Breaker

When multiple tasks share the same priority, we add a **sequence** to the comparator to produce a deterministic order:

Create the file **`PriorityQueueDemo.java`**:

```java
import java.util.Comparator;
import java.util.concurrent.PriorityBlockingQueue;

public class PriorityQueueDemo {
    record Job(int priority, long sequence, String name) {
    }

    public static void main(String[] args) throws InterruptedException {
        Comparator<Job> order =
                Comparator.comparingInt(Job::priority)
                          .thenComparingLong(Job::sequence);

        PriorityBlockingQueue<Job> queue =
                new PriorityBlockingQueue<>(11, order);

        queue.offer(new Job(5, 0, "report"));
        queue.offer(new Job(1, 2, "hotfix"));
        queue.offer(new Job(1, 1, "alert"));
        queue.offer(new Job(3, 3, "email"));

        while (!queue.isEmpty()) {
            Job job = queue.take();
            System.out.println(job.name() + " (" + job.priority() + ")");
        }

        System.out.println("Remaining capacity: "
                + queue.remainingCapacity());
    }
}
```

```bash
javac PriorityQueueDemo.java
java PriorityQueueDemo
```

Output:

```text
alert (1)
hotfix (1)
email (3)
report (5)
Remaining capacity: 2147483647
```

**Why is this correct?** The comparator sorts in ascending order of priority; if tied, it sorts by sequence. Both `alert` and `hotfix` have `priority=1`, but `sequence=1` is taken before `sequence=2`. `Job` is a record containing only `int`, `long`, and `String`, so the sort key cannot be mutated after enqueueing. The `11` in the constructor is the *initialCapacity*; even after the queue just retrieved four items, `remainingCapacity` still follows the unbounded queue contract.

In production code, the sequence is often issued via `AtomicLong.getAndIncrement()` so concurrent producers get unique sequences. If strict ordering across producers is required, you must clearly define the submission order and how sequences are assigned. Do not infer from multi-threaded log order that it is the exact queue offer order.

## 3. PriorityBlockingQueue Does Not Guarantee "High-Priority Tasks Finish First"

Suppose consumer A has already taken a low-priority task and started processing it. Later, a very high-priority task is enqueued. The queue **does not preempt** the task currently running on consumer A to give CPU time to the new task.

```text
t0: worker A takes a low-priority task and starts running.
t1: producer adds a high-priority task.
t2: worker B, or A on its next take, receives the high-priority task.
t3: completion order still depends on execution time.
```

Therefore, you must distinguish:

- **Priority of dequeue:** which element is taken first from the set of waiting elements?
- **Priority of execution/completion:** which task starts, consumes CPU, or finishes first?

`PriorityBlockingQueue` only directly governs the **dequeue rule**; it does not replace JVM/OS thread priority mechanisms, does not cancel already running tasks, and does not guarantee ordered completion. If multiple threads call `take()` concurrently, their retrievals can occur close together; task execution scheduling still varies.

### The Starvation Problem

If high-priority items continuously arrive in the queue, low-priority items can wait for a very long time (**starvation**). The queue does not automatically perform "aging" to raise the priority of long-waiting tasks. When designing a scheduler, you may consider deadlines, quotas, aging, separate queues per lane, or submission rate limiting; that goes beyond a simple comparator.

**Do not mutate the priority field while a task is in the queue** to naively implement aging. A safe approach requires a remove/update/reinsert protocol or a scheduler structure designed for dynamic priorities.

## 4. DelayQueue: Retrieving Elements Only When Expired

`DelayQueue<E extends Delayed>` holds objects implementing `Delayed`. This interface requires:

```java
long getDelay(TimeUnit unit);
int compareTo(Delayed other);
```

These are **method signatures**, not a standalone runnable class. `Delayed` extends `Comparable<Delayed>`. In a typical implementation:

- Each element stores an immutable **deadline** computed from a `System.nanoTime()` baseline plus a delay interval.
- `getDelay(unit)` returns the remaining time; a value **≤ 0** means it has expired.
- `compareTo` orders elements by deadline so that the **earliest deadline is at the head of the queue**.
- `take()` only returns an element when the head element's delay has expired; otherwise, it waits.
- `poll()` returns `null` when the head of the queue has not yet expired, **even if `size() > 0`**.

`DelayQueue` stores multiple items, but it *does not automatically run tasks* upon expiration. It only makes an item eligible to be taken; you still need a consumer calling `take()`/`poll()` and then executing the business action itself.

### Clocks and Ordering

Use `System.nanoTime()` to represent **relative deadlines** for delays, because it is suitable for measuring elapsed time intervals rather than wall-clock calendar time. Do not directly compare a `nanoTime` deadline against `System.currentTimeMillis()`: the two values have different meanings.

If you use `System.nanoTime() + delayNanos`, watch out for overflow with extremely large delays or deadlines created unusually far apart. For typical durations well within the safe interval range, the code below is sufficient for illustration. In real applications, standardize the `TimeUnit` and define whether negative/zero delays are accepted.

## 5. Example 2 — DelayQueue with Deterministic Expiration Times

This example inserts elements **out of expiration order**, then retrieves them with `take()`. To keep stdout deterministic, deadlines are created from the same baseline and clearly separated; actual millisecond timings are not printed because scheduling times vary between runs.

Create the file **`DelayQueueDemo.java`**:

```java
import java.util.concurrent.DelayQueue;
import java.util.concurrent.Delayed;
import java.util.concurrent.TimeUnit;

public class DelayQueueDemo {
    static final class Message implements Delayed {
        private final String name;
        private final long deadlineNanos;

        Message(String name, long deadlineNanos) {
            this.name = name;
            this.deadlineNanos = deadlineNanos;
        }

        @Override
        public long getDelay(TimeUnit unit) {
            long remaining = deadlineNanos - System.nanoTime();
            return unit.convert(remaining, TimeUnit.NANOSECONDS);
        }

        @Override
        public int compareTo(Delayed other) {
            Message that = (Message) other;
            return Long.compare(this.deadlineNanos, that.deadlineNanos);
        }
    }

    public static void main(String[] args) throws InterruptedException {
        DelayQueue<Message> queue = new DelayQueue<>();
        long now = System.nanoTime();

        queue.offer(new Message(
                "later", now + TimeUnit.MILLISECONDS.toNanos(150)));
        queue.offer(new Message(
                "ready", now - TimeUnit.MILLISECONDS.toNanos(10)));
        queue.offer(new Message(
                "soon", now + TimeUnit.MILLISECONDS.toNanos(50)));

        System.out.println("First: " + queue.take().name);
        System.out.println("Second: " + queue.take().name);
        System.out.println("Third: " + queue.take().name);
        System.out.println("Remaining: " + queue.size());
    }
}
```

```bash
javac DelayQueueDemo.java
java DelayQueueDemo
```

Output:

```text
First: ready
Second: soon
Third: later
Remaining: 0
```

**Explanation:** All three elements are enqueued before calling `take()`. `ready` is already expired, sits at the head, and is returned immediately; `soon` has an earlier deadline than `later`, so it is taken next when it expires. `take()` may wait until the deadline arrives—having elements in the queue does not mean immediate retrieval. Actual elapsed times can vary due to the JVM/OS scheduler, but **the order according to declared deadlines does not change**.

`compareTo` in this example assumes all elements in the queue are of the same `Message` class, which holds for `DelayQueue<Message>`. If you implement `Delayed` to mix multiple object types, you must define a compatible, symmetric, transitive comparator that accurately reflects ordering.

## 6. Are DelayQueue and ScheduledExecutorService the Same?

They are related in the idea of **expiration/delay**, but have different responsibilities:

| Tool | What is it responsible for? | What does it NOT do automatically? |
|---|---|---|
| `DelayQueue<E extends Delayed>` | Stores items by deadline; only allows consumers to take them after the delay expires. | Does not execute `Runnable`s itself; does not create scheduler workers. |
| `ScheduledExecutorService.schedule(...)` | Schedules execution of a `Runnable`/`Callable` after a delay. | Does not guarantee nanosecond-exact start times due to scheduling. |
| `ScheduledThreadPoolExecutor` | An executor with workers and an internal delayed work queue. | Does not automatically enforce business deadlines of tasks or I/O timeouts. |

`ScheduledThreadPoolExecutor` uses an internal delayed-queue mechanism related to the **delayed work** concept, but you should not assume its constructor takes a user-supplied `DelayQueue` the way `ThreadPoolExecutor` takes a `BlockingQueue<Runnable>`.

Direct use cases for `DelayQueue`: expiring cache entries, retry notifications that must not be processed before a deadline, items to be fed into a pipeline after a wait period, and application-managed task timeouts. However, for **a scheduler that simply needs to invoke a Runnable at a point in time**, `ScheduledExecutorService` is usually simpler.

### What Does an Item with "Delay 0" Mean?

If `getDelay(NANOSECONDS) <= 0`, the item is eligible to be taken; it does **not** mean it disappears from the queue or runs by itself. A consumer must call `take()`/`poll()`. Without a consumer, an expired item remains in the queue and `size()` still counts it.

`DelayQueue.drainTo(collection)` only transfers elements **whose delay has expired** by contract; it does not take unexpired elements as a "drain all memory" command. A `clear()` operation (if used) is different from handing off eligible items for processing.

## 7. DelayQueue: Wait Conditions, Signaling, and Cancellation

When a producer adds an item with a deadline **earlier** than the current head item, a consumer waiting in `take()` must be woken up to re-evaluate the head's expiration time. `DelayQueue` handles this coordination internally instead of forcing you to write `Condition.awaitNanos()` by hand.

Keep in mind:

- `peek()` can return an element that has **not yet expired**; `poll()` when not yet expired returns `null`.
- `size() > 0` does not guarantee `poll() != null`.
- `remainingCapacity()` is `Integer.MAX_VALUE`, so there is no natural bounded backlog; too many items can grow the heap.
- If an item mutates `deadlineNanos` **after enqueueing**, the heap does not automatically re-sort. Keep deadlines immutable.
- If a consumer is interrupted while in `take()`, it can throw `InterruptedException`; application code must manage lifecycle and cleanup appropriately.
- If an item is canceled, you must clearly define how to handle it: remove it from the queue, mark it canceled so the consumer skips it, or leave it to expire and discard; there is no automatic business-level cancellation protocol for all `Delayed` items.
- With multiple consumers, each item is taken by only one consumer; the order in which processing **starts/completes** still depends on scheduling.

If you need **exactly-once** execution across multiple JVMs, an in-memory `DelayQueue` is not sufficient: process crashes can lose items, and the queue provides no transactions or recovery.

## 8. SynchronousQueue: Zero Capacity, Direct Handoff

`SynchronousQueue<E>` is fundamentally different from the previous two queues. It holds no backlog; each `put(e)` must pair with an awaiting or arriving `take()`. You can picture a **rendezvous** between producer and consumer:

```text
Producer                             Consumer
--------                             --------
queue.put("work") ---- wait ---->    queue.take()
                                        /
              ---- transfer item ------/
                    both proceed
```

Basic contract:

- `put(e)` may block until **a consumer receives** `e`.
- `take()` may block until **a producer sends** `e`.
- Non-blocking `offer(e)` succeeds only if a matching consumer is **immediately ready to receive**.
- `offer(e, timeout, unit)` may wait up to the timeout for a consumer; if no pairing occurs, it returns `false`.
- Non-blocking `poll()` succeeds only when a producer can transfer immediately; `poll(timeout, unit)` waits up to the timeout for a producer.
- `size()` is always 0; `isEmpty()` is always `true`; `remainingCapacity()` is always 0; `peek()` is always `null`.
- No element exists *between* send and receive: the transfer occurs when the two sides pair up.

**Do not write `if (queue.isEmpty()) ...` as a way to check whether a `SynchronousQueue` has a waiting consumer.** It always reports empty by contract, regardless of how many threads are waiting on either side.

### Fairness

The constructor `new SynchronousQueue<>(true)` requests a **fair** policy for waiting thread order, whereas the default is non-fair. Fairness affects how waiting pairs are matched under contention; it **does not create capacity**, does not guarantee tasks finish in order, and does not turn handoff into a durable transaction.

Fair mode can carry performance trade-offs depending on contention; do not blindly enable or disable it without understanding your requirements.

## 9. Example 3 — SynchronousQueue: offer Fails, put Waits for Consumer

This example first calls `offer` when no consumer exists, so it is guaranteed to return `false`. Then it creates a consumer and lets `main` `put` an item; `put` completes only when the consumer receives it. A `CountDownLatch` coordinates the start step, and `join()` ensures the final printed result does not depend on thread scheduling.

Create the file **`SynchronousHandoffDemo.java`**:

```java
import java.util.concurrent.CountDownLatch;
import java.util.concurrent.SynchronousQueue;
import java.util.concurrent.atomic.AtomicReference;

public class SynchronousHandoffDemo {
    public static void main(String[] args) throws InterruptedException {
        SynchronousQueue<String> queue = new SynchronousQueue<>();
        System.out.println("Offer without consumer: "
                + queue.offer("early"));

        CountDownLatch consumerReady = new CountDownLatch(1);
        AtomicReference<String> received = new AtomicReference<>();

        Thread consumer = new Thread(() -> {
            consumerReady.countDown();
            try {
                received.set(queue.take());
            } catch (InterruptedException e) {
                Thread.currentThread().interrupt();
            }
        }, "consumer");

        consumer.start();
        consumerReady.await();

        queue.put("delivered");
        consumer.join();

        System.out.println("Received: " + received.get());
        System.out.println("Queue size: " + queue.size());
        System.out.println("Remaining capacity: "
                + queue.remainingCapacity());
    }
}
```

```bash
javac SynchronousHandoffDemo.java
java SynchronousHandoffDemo
```

Normal output without external interruption:

```text
Offer without consumer: false
Received: delivered
Queue size: 0
Remaining capacity: 0
```

`consumerReady.countDown()` is right before `take()`; `main` might call `put()` before the consumer actually enters `take()`, in which case **`main` waits**, and no item is lost. After both sides pair up, `put` completes, and `join` ensures the consumer has written `received`. This is a **backpressure-at-handoff** model: a producer cannot "push into the queue and move on" when no receiver is present.

Do not treat `SynchronousQueue` as a queue with `capacity=1`. With capacity 1, a producer can store one element when no consumer is present; `SynchronousQueue` **cannot store even a single item** and always requires a counterpart on the other side of the exchange.

## 10. Timeouts and Interruption on SynchronousQueue

A handoff can wait indefinitely if there is no counterpart. Therefore, cancellation and timeouts are especially important:

```java
boolean transferred =
        queue.offer("work", 200, TimeUnit.MILLISECONDS);
```

This snippet requires declaring `queue` and handling `InterruptedException`. If no consumer arrives within that time, `transferred` becomes `false`; if a consumer arrives and pairs successfully, it returns `true`.

A producer/consumer waiting in `put`/`take` can be interrupted. The thread should handle `InterruptedException` according to its lifecycle policy: rethrow it, or restore the `Thread.currentThread().interrupt()` flag and exit; **do not swallow the interrupt and loop forever**.

If the sender's `put` finishes **successfully**, a paired consumer has received the element. However, that does **not** prove the consumer has finished processing the work—the consumer may have just received the item and is still running. If you need confirmation of business completion, use a `Future`, latch, acknowledgment, or separate transaction.

All non-blocking `offer/poll` operations are sensitive to **the exact timing when the two threads meet**; do not write tests expecting a non-blocking `offer` to always return `true` just because a consumer thread was started. A proper test must coordinate the waiting state or choose `put/take` as appropriate.

## 11. SynchronousQueue in ThreadPoolExecutor

`ThreadPoolExecutor` uses a `BlockingQueue<Runnable>` as its **work queue**. Typical task admission sequence:

1. When the worker count is below `corePoolSize`, the executor tries to create a worker to run the task.
2. Once at core size, it calls `workQueue.offer(task)`.
3. If `offer` fails, it tries to create additional workers up to `maximumPoolSize`.
4. If it can neither enqueue the task nor add a worker, `RejectedExecutionHandler` decides the rejection behavior.

With **`SynchronousQueue`**, `offer(task)` fails whenever no idle worker is waiting for a direct handoff. Because the queue has no slots, the executor typically **scales up workers instead of accumulating a backlog** as more concurrent tasks arrive, up to `maximumPoolSize`.

This contrasts with an unbounded or large-capacity `LinkedBlockingQueue`: once core size is reached, the queue normally accepts tasks, so the executor does not create non-core workers along the standard admission path.

### Example 4 — Two Busy Workers, Third Task Rejected

We configure `core=1`, `max=2`, `SynchronousQueue`, and `AbortPolicy`. Two tasks use a latch to keep workers busy; the third task finds no idle worker and the pool is already at max, so it is rejected. Because of latch coordination, stdout does not depend on accidental task timing.

Create the file **`SynchronousExecutorDemo.java`**:

```java
import java.util.concurrent.CountDownLatch;
import java.util.concurrent.RejectedExecutionException;
import java.util.concurrent.SynchronousQueue;
import java.util.concurrent.ThreadPoolExecutor;
import java.util.concurrent.TimeUnit;

public class SynchronousExecutorDemo {
    private static Runnable blockingTask(
            CountDownLatch started, CountDownLatch release) {
        return () -> {
            started.countDown();
            try {
                release.await();
            } catch (InterruptedException e) {
                Thread.currentThread().interrupt();
            }
        };
    }

    public static void main(String[] args) throws InterruptedException {
        ThreadPoolExecutor pool = new ThreadPoolExecutor(
                1, 2, 0, TimeUnit.SECONDS,
                new SynchronousQueue<>(),
                new ThreadPoolExecutor.AbortPolicy()
        );

        CountDownLatch firstStarted = new CountDownLatch(1);
        CountDownLatch secondStarted = new CountDownLatch(1);
        CountDownLatch release = new CountDownLatch(1);

        try {
            pool.execute(blockingTask(firstStarted, release));
            firstStarted.await();

            pool.execute(blockingTask(secondStarted, release));
            secondStarted.await();

            boolean rejected = false;
            try {
                pool.execute(() -> { });
            } catch (RejectedExecutionException e) {
                rejected = true;
            }

            System.out.println("Pool size: " + pool.getPoolSize());
            System.out.println("Queue size: " + pool.getQueue().size());
            System.out.println("Third rejected: " + rejected);
        } finally {
            release.countDown();
            pool.shutdown();
        }

        boolean terminated = pool.awaitTermination(
                5, TimeUnit.SECONDS);
        System.out.println("Terminated: " + terminated);
        System.out.println("Completed worker tasks: "
                + pool.getCompletedTaskCount());
    }
}
```

```bash
javac SynchronousExecutorDemo.java
java SynchronousExecutorDemo
```

Normal output:

```text
Pool size: 2
Queue size: 0
Third rejected: true
Terminated: true
Completed worker tasks: 2
```

The first task occupies the core worker; the second task cannot be queued, so the pool creates a second worker. Both are held at `release`, so the third task finds no worker waiting for handoff and `max=2` is already reached: `AbortPolicy` throws `RejectedExecutionException`. After `release.countDown()`, both workers finish; the pool shuts down and `awaitTermination` confirms completion.

Do not assume `queue size=0` means "no tasks are running." With `SynchronousQueue`, **queue size is always 0**, even when many workers are busy; to monitor the pool, you must also inspect `getActiveCount()`, throughput, rejections, and lifecycle state.

## 12. Why Does Executors.newCachedThreadPool() Require Caution?

`Executors.newCachedThreadPool()` is configured around a **direct handoff** model using `SynchronousQueue`, capable of creating many new workers whenever no idle worker is available to receive a task; its maximum thread limit is very high in standard implementations.

Advantages: short, bursty tasks can be picked up quickly, and idle workers are reused and reclaimed after the keep-alive period.

Risks: if tasks block for a long time or the submission rate far exceeds completion capacity, the pool can create **too many threads**, consuming stack memory, increasing context switching, exhausting downstream resources, or causing `OutOfMemoryError`. Do not treat a cached pool as a capacity bound or safe backpressure mechanism.

In a service that needs resource limits, you can use `ThreadPoolExecutor` with an **explicit max worker count**, `SynchronousQueue`, and a clear rejection policy—or use a bounded queue if you want to allow a finite backlog. The choice depends on latency, CPU/I/O profile, connection limits, and SLAs, not just the queue name.

## 13. Direct Comparison of the Three Queues

| Criterion | `PriorityBlockingQueue` | `DelayQueue` | `SynchronousQueue` |
|---|---|---|---|
| Condition to take an element | By **priority/comparator**. | Head of queue has **expired delay**. | Producer and consumer **pair directly**. |
| Stores elements in queue | Yes. | Yes. | **No**, capacity=0. |
| Capacity bounded via constructor | No. | No. | Fixed at **0**. |
| Non-blocking `offer(e)` | Usually succeeds if memory allows. | Usually succeeds if memory allows. | Succeeds only if a matching consumer is immediately ready. |
| `take()` waits when | Queue is empty. | No expired item is at the head. | No pairing producer is present. |
| `poll()` returns `null` when | Empty. | Empty or head has not expired yet. | No pairing producer is immediately available. |
| `size()` | Number of stored items. | Number of items, including unexpired ones. | Always 0. |
| `remainingCapacity()` | `Integer.MAX_VALUE`. | `Integer.MAX_VALUE`. | 0. |
| Strict FIFO order | No; priority decides. | No; deadline decides. | No backlog to FIFO items. |
| Fairness constructor | No fair option equivalent to `ArrayBlockingQueue`. | No public fair option. | Has `SynchronousQueue(boolean fair)`. |
| Typical use | Prioritizing queued work, rank-based triage. | Timers, retry delays, item expiration. | Synchronous handoff, on-demand worker scaling in pools. |
| Main risks | Low-priority starvation, memory backlog. | Memory backlog, misinterpreting expiration timing. | Producer/consumer waiting indefinitely, or pool creating too many workers. |

**Choose a queue based on the condition under which an element is allowed to be taken**, not merely because all three implement `BlockingQueue`.

## 14. Java Memory Model and Safe Item Handoff

Concurrent collections like `BlockingQueue` provide a memory consistency contract: actions by a producer **prior to placing an object into a queue** *happen-before* actions by a consumer **subsequent to accessing or removing that object**.

Conceptual example:

```java
// Producer snippet.
Message message = new Message();
message.payload = 42;
queue.put(message);

// Consumer snippet (on another thread).
Message received = queue.take();
System.out.println(received.payload);
```

This snippet assumes `Message` and `queue` are appropriately defined. The happens-before relationship guarantees that data prepared **before putting into the queue** is safely handed off under Java Memory Model (JMM) rules. It does **not make arbitrary mutations after enqueueing thread-safe**.

- For `PriorityBlockingQueue`, fields affecting the comparator should be **immutable** while the element is in the heap.
- For `DelayQueue`, the deadline should be **immutable** so the scheduled time is not altered outside the protocol.
- For `SynchronousQueue`, handoff transfers access to the item to the consumer, but if the producer continues mutating the same object concurrently, you still need ownership/synchronization rules.
- If an item holds references to mutable data elsewhere, thread safety must be evaluated across the entire object graph, not just the item reference itself.

Using `record`s, `final` fields, defensive copies, or clear ownership-transfer rules reduces data races when exchanging items across threads.

## 15. Timeouts, Interruption, and Shutdown Differ

All three queues have blocking operations that can be interrupted:

- `take()` can throw `InterruptedException` when the waiting thread is interrupted.
- `put()` can block in `SynchronousQueue`, whereas in `PriorityBlockingQueue`/`DelayQueue` it does not block for capacity because they are unbounded by contract; the interface's interruption contract still applies when used.
- `offer(timeout)`/`poll(timeout)` give the caller a time bound, though the reason for not pairing/not expiring still depends on each queue.
- `BlockingQueue` **has no unified `close()` method**; shutting down producer–consumer pipelines requires sentinels, interrupts, timeouts, or lifecycle state depending on the design.

**Cancellation does not automatically roll back an already handed-off item.** With `SynchronousQueue`, once a producer's `put` finishes, the consumer has already received the item even if it has not processed it yet. With `DelayQueue`, an expired item without a consumer can still remain in the queue. With `PriorityBlockingQueue`, a task already taken by a consumer does not automatically return to the queue just because the worker is interrupted.

When using a queue with an executor, the owner must manage `shutdown()`, `shutdownNow()`, `awaitTermination()`, and pending tasks according to the executor's contract. Never confuse an empty queue with a pool having finished all tasks.

## 16. Common Pitfalls When Using the Three Queues

| Mistake | Why It Is Wrong | How to Fix |
|---|---|---|
| Treating `PriorityBlockingQueue` as FIFO. | Orders by priority; items with equal priority have no guaranteed order. | Add a sequence tie-breaker to the comparator if needed. |
| Mutating a priority field after `offer`. | The heap does not re-heapify when a mutable field changes. | Use immutable keys or follow a proper remove/update/reinsert protocol. |
| Treating `PriorityBlockingQueue`'s `initialCapacity` as a bound. | The backing array can grow; it is not a backlog limit. | Limit producers/permits explicitly or choose a bounded queue. |
| Printing the iterator and assuming it is priority order. | The iterator does not guarantee order. | Use `poll`/`take` or snapshot and sort. |
| Assuming a waiting high-priority item preempts a running task. | The queue does not manage CPU scheduling or already dequeued tasks. | Design separate scheduler/preemption/cancellation mechanisms. |
| Using `DelayQueue` with `Delayed.compareTo` inconsistent with `getDelay`. | The head does not reflect the earliest deadline. | Compare immutable deadlines using the same time base. |
| Calling `poll()` when `DelayQueue.size() > 0` and assuming it will return an item. | The head item's delay may not have expired yet. | Use `take` or timed `poll` and check the return value. |
| Thinking `DelayQueue` automatically runs a `Runnable` on time. | The queue only stores items and makes them eligible for dequeue. | Use `ScheduledExecutorService` if you need automatic task execution. |
| Changing a `Delayed` object's deadline after enqueueing. | The queue does not reorder automatically. | Use immutable deadlines; reinsert or use a scheduler with an update protocol. |
| Thinking `SynchronousQueue` has a one-slot buffer. | Capacity is always 0. | Use `ArrayBlockingQueue(1)` when you want to buffer one element. |
| Calling `SynchronousQueue.offer` without a waiting consumer. | Usually returns `false` immediately; the item is not retained. | Use `put` or timed `offer` if you want to wait for a counterpart. |
| Relying on `SynchronousQueue.size()` to know the pool's task count. | Size is always 0 even while workers are processing. | Measure active tasks, completed tasks, rejections, and throughput. |
| Using a cached pool with unbounded blocking tasks. | Can spawn too many workers and exhaust resources. | Bound max threads, set timeouts, and enforce rejection/backpressure. |
| Swallowing `InterruptedException` while waiting. | Cancellation has no effect; threads may wait forever. | Rethrow or restore the interrupt flag and exit per contract. |
| Choosing a queue based solely on a single microbenchmark's throughput. | Ignores latency, backlog, ordering, memory, and fairness. | Measure realistic workloads and define the contract first. |

## 17. Choosing the Right Queue by Scenario

**Scenario A — Processing work by urgency:** If tasks should be retrieved according to a known, rarely changing `priority`, `PriorityBlockingQueue` is a good fit. You must guard against starvation and bound the backlog since the constructor does not bound capacity.

**Scenario B — Retrying after 5 seconds:** If an item should only be picked up by a worker after a deadline, `DelayQueue<Delayed>` stores the item and makes it wait until the right time. If you simply want a scheduler to **automatically run** a callback, use `ScheduledExecutorService`.

**Scenario C — Sender must wait for receiver:** If you want no backlog and need a direct transfer between two parties, `SynchronousQueue` makes sense. Use timeouts/interrupts when no counterpart is available.

**Scenario D — Executor with no backlog, scaling workers up to a limit:** `ThreadPoolExecutor` with `SynchronousQueue`, `corePoolSize`, `maximumPoolSize`, and an explicit rejection policy. If you want a small backlog instead of pure handoff, use an appropriate bounded queue.

**Scenario E — Simple bounded FIFO producer–consumer:** Use `ArrayBlockingQueue` or `LinkedBlockingQueue(capacity)`; **do not force** one of the three queues in this article onto the wrong problem.

In all cases, the decision also depends on CPU/I/O mix, producer/consumer counts, latency, ordering importance, acceptable backlog, and shutdown behavior.

## 18. Design and Testing Checklist

1. **Define the dequeue condition:** by priority, by deadline, or only when a receiver is present?
2. **Determine capacity:** API-unbounded queues carry heap risk; zero-capacity queues require a handoff protocol.
3. **Define comparison:** a stable comparator for `PriorityBlockingQueue`; `compareTo` consistent with deadlines for `DelayQueue`.
4. **Do not mutate keys once enqueued:** immutable priorities/deadlines keep the priority structure valid.
5. **Define timeouts:** how long can a caller wait, and what should happen if no data/counterpart arrives?
6. **Handle `InterruptedException`:** never swallow cancellation requests in an unbounded loop.
7. **Define completion:** dequeuing/handoff is not the same as finishing business processing.
8. **Manage lifecycle:** producer–consumer pipelines lack a shared `BlockingQueue.close()`; executors must be shut down by their owner.
9. **Monitor overload:** queue depth/age for priority/delay queues; active workers and rejections for `SynchronousQueue`/executors.
10. **Test ordering properly:** with priority tie-breakers, clearly separated deadlines, and latches to make scheduling deterministic.
11. **Test cancellation:** when no consumer receives, when items have not expired, and while shutdown is in progress.
12. **Test both correctness and performance:** starvation, heap usage, CPU, GC, latency, and throughput.
13. **Do not infer completion order from dequeue order:** multiple concurrent workers will have varying execution durations.
14. **Do not use a concurrent queue as a durable broker:** you need persistence/idempotency if data must survive JVM restarts.

## 19. Self-Check Questions

1. **Is `PriorityBlockingQueue` FIFO?** No; elements are retrieved by comparator/natural priority. For equal priorities, order is not guaranteed.
2. **Does `new PriorityBlockingQueue<>(100)` block inserts at 100 items?** No; 100 is the initial capacity.
3. **Why is a sequence tie-breaker needed?** To establish a deterministic order among tasks with the same priority if business logic requires it.
4. **If you mutate the priority directly on an object already in the queue, does the heap automatically reorder?** No.
5. **What interface does `DelayQueue` require?** `Delayed`, with `getDelay(TimeUnit)` and `compareTo`.
6. **Does `DelayQueue.size() > 0` guarantee `poll()` returns an item?** No; the head item's delay may not have expired yet.
7. **Does `DelayQueue` automatically invoke a `Runnable` after its deadline?** No, it only allows consumers to take expired items.
8. **How many storage slots does `SynchronousQueue` have?** Zero, with no backlog.
9. **Does `SynchronousQueue.offer(e)` without a timeout always accept an item?** No; a counterpart consumer must be ready.
10. **Does `SynchronousQueue.put(e)` returning mean the consumer has finished processing?** No; it only indicates that the handoff occurred.
11. **Does `SynchronousQueue.size()` reflect active workers?** No; it is always 0.
12. **Why does `SynchronousQueue` cause `ThreadPoolExecutor` to readily spawn non-core workers?** Because the queue holds no tasks; `offer` fails whenever no idle worker is waiting to receive.
13. **What is the risk of `newCachedThreadPool()` with many blocking tasks?** The pool can spawn too many workers, exhausting resources.
14. **Does `BlockingQueue` have a common `close()` method?** No; you must design lifecycle/cancellation separately.
15. **What does queue memory consistency guarantee?** Actions before enqueue/handoff happen-before actions after the corresponding dequeue/receive; it does not protect concurrent mutations afterward.
16. **When should you use `ArrayBlockingQueue` instead of the three queues above?** When you simply need a standard bounded FIFO producer–consumer queue.

**Key takeaway:** `PriorityBlockingQueue` orders by **priority**, `DelayQueue` waits for **expiration**, and `SynchronousQueue` requires **two threads to hand off directly with no buffer**. Although all three are `BlockingQueue`s, their ordering, capacity, timeouts, backpressure, and executor impact differ; your choice must start from the work contract.

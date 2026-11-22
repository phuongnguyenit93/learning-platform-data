# ArrayBlockingQueue vs. LinkedBlockingQueue in Java Concurrency

## 1. The problem: choosing the right blocking queue

In the **producer–consumer** model, producers generate work and place it into a shared queue; consumers take work out to process. When producers are faster than consumers, the system must decide what happens to unprocessed work: **wait**, **reject**, or **accumulate backlog**.

Java provides two very popular choices in `java.util.concurrent`:

- `ArrayBlockingQueue<E>`: a **FIFO, fixed-capacity** queue backed by an array, with an optional fairness policy for waiting threads.
- `LinkedBlockingQueue<E>`: a **FIFO, linked-node-based** queue with an optional capacity bound; **if no capacity is passed**, the nominal limit is `Integer.MAX_VALUE`.

Both implement `BlockingQueue<E>`; both support `put()` and `take()`, which can **block** when the queue is full/empty. The key differences lie in **storage structure, how backlog is bounded, allocation cost, concurrency between producer/consumer, and impact on thread pools**.

After this lesson, you will be able to:

1. Distinguish the **bounded** nature of ArrayBlockingQueue from the **optionally bounded** nature of LinkedBlockingQueue.
2. Correctly use `add`, `offer`, `put`, `offer(timeout)`, `poll`, `take`, and `poll(timeout)`.
3. Understand that both are FIFO **with respect to the order elements enter/leave the queue**, without guaranteeing completion order across multiple workers.
4. Explain ArrayBlockingQueue fairness, the locks, and the storage overhead of both implementations.
5. Understand why a practically unbounded LinkedBlockingQueue can cause backlog/heap pressure and prevent `maximumPoolSize` of ThreadPoolExecutor from taking effect.
6. Apply backpressure, bounded capacity, timeouts, cancellation, poison pills, and producer–consumer shutdown.
7. Run Java 17+ examples demonstrating capacity/FIFO, blocking handoff, interruption, and ThreadPoolExecutor interaction.
8. Choose based on benchmarks rather than assuming one queue is always faster.

**Scope:** General Java SE/JVM concurrency, framework-independent. Examples use JDK 17+.

## 2. BlockingQueue as the shared contract

`BlockingQueue<E>` extends `Queue<E>` to support operations for adding/removing elements when conditions do not allow immediate execution. There are **four ways to respond** to a full or empty queue.

| Operation | Throws exception | Immediate special value | Blocks indefinitely | Blocks with timeout |
|---|---|---|---|---|
| Insert element | `add(e)` | `offer(e)` | `put(e)` | `offer(e, timeout, unit)` |
| Retrieve and remove element | `remove()` | `poll()` | `take()` | `poll(timeout, unit)` |
| Inspect head only | `element()` | `peek()` | Not in interface | Not in interface |

Key semantics to remember:

- `add(e)`: if insertion fails due to capacity limits, throws `IllegalStateException`. Do not use as the normal way to wait for space.
- `offer(e)`: tries immediately. Returns `true` if added; returns `false` if **no space is currently available**, without waiting.
- `put(e)`: can block until space becomes available; throws `InterruptedException` if the thread is interrupted while waiting per the contract.
- `offer(e, timeout, unit)`: waits up to the specified time; returns false if no space becomes available within the timeout; can also throw InterruptedException.
- `remove()`: retrieves and removes the head of the queue, throwing `NoSuchElementException` if empty.
- `poll()`: retrieves and removes the head of the queue or returns `null` if empty, without waiting.
- `take()`: waits until an element becomes available, or throws InterruptedException when cancellation is requested.
- `poll(timeout, unit)`: waits up to the specified time, returning null if no element is available within the timeout.

**Do not insert `null` into a BlockingQueue.** Both classes throw `NullPointerException` for null elements. Therefore, `poll()==null` is used to indicate **no element available** rather than a valid queue value.

~~~java
BlockingQueue<String> queue = new ArrayBlockingQueue<>(2);

queue.put("task-A");                   // may wait when full
boolean accepted = queue.offer("task-B"); // tries immediately
String first = queue.take();            // may wait when empty
String second = queue.poll();           // returns null if empty
~~~

This is a **snippet inside a method**, requiring appropriate imports and declaring/handling `InterruptedException` for `put/take`. The example has no competing threads, but these methods still preserve their blocking contract.

## 3. ArrayBlockingQueue: fixed array with mandatory capacity

Initialization:

~~~java
BlockingQueue<String> queue =
        new ArrayBlockingQueue<>(100);
~~~

`ArrayBlockingQueue` is a FIFO queue with a **fixed capacity** specified at creation time. The capacity value must be at least 1. Once initialized, there is no `setCapacity` method to resize the array at will.

Visualizing a queue of capacity 4:

~~~text
Fixed backing array with 4 slots
┌────┬────┬────┬────┐
│ A  │ B  │    │    │
└────┴────┴────┴────┘
  ↑   ↑
  head/tail advance circularly on insert/remove

size = 2
remainingCapacity = 2

put(C) → places C into empty slot
put(D) → queue is full (size=4)
put(E) → producer must wait for a consumer to take an item
~~~

ArrayBlockingQueue uses a **circular array** mechanism with indices for inserting and removing elements. Having a fixed array brings several characteristics:

- No need to allocate a **new node wrapper** for every enqueue as with typical linked nodes.
- The queue's reference slots are allocated near full capacity upfront; a very large-capacity queue still incurs the backing array cost at creation time, even when empty.
- When size reaches capacity, `offer` returns false, while `put` waits. This creates **backpressure** if producers use the blocking API properly.
- The bounded structure helps estimate the number of **waiting elements**; however, each individual element itself can be very large, so capacity alone does not guarantee memory usage stays under any given budget.
- ArrayBlockingQueue has an optional **fairness** setting for producers/consumers waiting for queue access.

Fairness constructor:

~~~java
BlockingQueue<String> fairQueue =
        new ArrayBlockingQueue<>(100, true);
~~~

The `fair=true` parameter applies a FIFO policy for threads **waiting** to insert/remove elements. By default, fairness is false. The JDK documentation notes that enabling fairness generally **reduces throughput** but can decrease variability in wait times and avoid starvation among waiters in certain workloads.

**Fairness is not FIFO completion order of tasks executed by consumers after `take`.** Consumer A takes a task first but takes 20 seconds to process it; consumer B takes a task later but finishes in 2ms. B can finish before A.

## 4. LinkedBlockingQueue: linked nodes, optional capacity

Bounded initialization:

~~~java
BlockingQueue<String> bounded =
        new LinkedBlockingQueue<>(100);
~~~

Initialization without passing a bound:

~~~java
BlockingQueue<String> effectivelyUnbounded =
        new LinkedBlockingQueue<>();
~~~

According to the Java 17 Javadoc, the no-argument constructor has a capacity of **`Integer.MAX_VALUE`**. This **does not mean truly infinite**: the queue is still subject to integer limits, heap size, per-node overhead, and the producer's ability to create/retain objects. In practice, a program can run out of memory **long before** reaching the nominal limit.

LinkedBlockingQueue uses **linked nodes** dynamically created when adding elements, unless adding would exceed capacity. Model:

~~~text
head → [node A] → [node B] → [node C] → tail
           ↑          ↑          ↑
         references to payload/task

Capacity = 100 (if 100 is passed)
Size = 3
Remaining = 97

No capacity passed:
  nominal bound = Integer.MAX_VALUE
  queue can still hold a very large backlog
~~~

Key points to note:

- LinkedBlockingQueue **can be bounded** if constructed with a positive capacity. Never claim that every LinkedBlockingQueue is unbounded.
- It does **not** have a boolean fairness parameter in its standard constructor API equivalent to `ArrayBlockingQueue(int, boolean)`.
- Each insertion may require a new node, increasing allocation and GC pressure under some workloads.
- In return, with concurrent producers/consumers, the split-lock structure can yield good throughput in many scenarios.
- Oracle JDK describes linked queues as **typically having higher throughput** than array-based queues but **less predictable performance** in many concurrent applications. This is a documented tendency, **not a benchmark guarantee**.
- When the queue is large, nodes and references retain payloads in the heap; payloads cannot be garbage-collected until taken from the queue or removed.

### LinkedBlockingQueue also provides backpressure when bounded

~~~java
BlockingQueue<Job> workQueue =
        new LinkedBlockingQueue<>(500);
~~~

This is a method snippet assuming `Job` is an application class. With capacity 500, full-queue behavior is similar in terms of the BlockingQueue contract: `offer` returns false, `put` waits, and timed `offer` can time out.

Bounded vs. unbounded is a **constructor** choice, not an immutable property of every linked queue implementation.

## 5. Comparison table of the two classes

| Criterion | ArrayBlockingQueue | LinkedBlockingQueue |
|---|---|---|
| Structure | Circular array | Linked nodes |
| Ordering | FIFO | FIFO |
| Capacity | **Mandatory**, fixed after creation | **Optional**; pass capacity or default Integer.MAX_VALUE |
| No-arg constructor | No | Yes |
| `put` when full | Blocks, interruptible | Blocks if bound is reached |
| `take` when empty | Blocks, interruptible | Blocks, interruptible |
| `offer` when full | False | False if bounded and full |
| `poll` when empty | Null | Null |
| Accepts null | No | No |
| Optional fairness | Yes, `new ArrayBlockingQueue<>(n, true)` | No equivalent constructor fairness parameter |
| Internal synchronization | One `ReentrantLock` managing the queue + notEmpty/notFull conditions | Separate locks for put and take + atomic count |
| Storage overhead | Pre-allocated backing array reference slots | Dynamically allocated linked nodes |
| High throughput | Can be good, depending on contention/fairness | Potentially higher throughput in some scenarios |
| Memory predictability | Easy to cap backlog via capacity | Easy to cap via capacity **if bound is passed**; risky if left at default |
| `ThreadPoolExecutor` when queue is full | Can expand workers up to max/reject | Bounded: similar; default: queue accepts for a long time, max rarely engages |

**There is no absolute “winner”.** Depending on producer/consumer ratio, memory, task size, queue residency time, CPU/NUMA, contention, and GC, benchmark results can vary.

## 6. Internal locking: why throughput can differ

### ArrayBlockingQueue: a single ReentrantLock

An ArrayBlockingQueue uses a single lock protecting critical operations on the array, along with `notEmpty` and `notFull` conditions. In principle, that same lock coordinates both enqueue and dequeue.

~~~text
Producer          single queue lock        Consumer
   |                    |                      |
   +---- enqueue ------►|                      |
                        |◄------ dequeue ------+
                        |
            notEmpty / notFull conditions
~~~

When many producers and consumers operate concurrently, queue operations can contend on the shared lock. However, keeping the queue simple, avoiding per-item node allocation, and having different locality can help throughput in some workloads.

### LinkedBlockingQueue: two locks for the two ends

The JDK implementation of LinkedBlockingQueue uses one lock for the `put` side and one lock for the `take` side, coordinated via `AtomicInteger count` and the appropriate conditions.

~~~text
Producer                 LinkedBlockingQueue                Consumer
   |                       putLock                              |
   +---- enqueue ----------►|                                   |
                            |     AtomicInteger count          |
                            |            |                     |
                            |         takeLock ◄----- dequeue--+
~~~

Splitting the locks can allow **one producer and one consumer** to enqueue/dequeue concurrently in many cases, improving throughput. However, each node created/reclaimed and size synchronization have overhead; there are also operations that must coordinate both locks.

**Do not assume two locks = always twice as fast.** Throughput must be measured with the same workload, JVM, GC, number of producers/consumers, capacity, CPU, queue depth, and element size.

## 7. Fairness: available on ArrayBlockingQueue, not the same as priority

~~~java
ArrayBlockingQueue<String> queue =
        new ArrayBlockingQueue<>(8, true);
~~~

`fair=true` aims for **FIFO ordering of threads that have blocked** on insert/remove. It does not:
- turn the queue into a priority queue;
- guarantee that all tasks finish processing in FIFO order;
- guarantee that all threads get equal CPU time;
- prioritize new requests by application-level arrival time;
- guarantee identical latency for all non-blocking operations;
- make worker database/I/O fair.

In particular, fairness of **queue access** is not fairness of the entire `ThreadPoolExecutor`. ThreadPoolExecutor also involves worker creation, scheduling, queueing, rejection, and task duration.

When should you consider enabling fairness?
- Many producers/consumers frequently block at the queue.
- You want to reduce the chance of a thread waiting excessively long under lock contention.
- You accept the throughput/latency tradeoff.
- You have benchmarked with realistic load characteristics.

For most typical workloads, starting with the default `fair=false` and measuring is reasonable.

## 8. Key APIs: backpressure depends on how the caller uses the queue

Suppose capacity=2, and two tasks already occupy the queue:

| Add call | Result | Impact on producer |
|---|---|---|
| `queue.add(third)` | `IllegalStateException` when queue is full | Producer must handle the error |
| `queue.offer(third)` | `false` | Producer can reject/route elsewhere |
| `queue.put(third)` | Blocks until space is available or interrupted | Producer slows down, creating backpressure |
| `queue.offer(third, 100, MILLISECONDS)` | Waits up to 100ms; false if timed out | Admission has a timeout |

You cannot say “a bounded queue automatically slows down the producer” in every case. It slows down the producer **if the application uses `put` or timed `offer` and accepts waiting**. Using non-blocking `offer` turns pressure into **rejection**, while `add` can throw an exception.

Similarly on the consumer side:

~~~java
String item = queue.take(); // waits when empty
String now = queue.poll();  // null immediately if empty
String maybe = queue.poll(1, TimeUnit.SECONDS);
~~~

Method snippet declaring/handling InterruptedException for `take` and timed `poll`.

### Two kinds of “empty”

1. A queue being empty **at the moment of inspection** does not mean producers have finished.
2. Producers having finished does not mean the queue is empty; there may still be many tasks to process.

Therefore, you need an explicit **producer–consumer termination** protocol (poison pill, close flag with timeout, executor shutdown, or other ownership) rather than inferring from a single `queue.isEmpty()`.

## 9. Standalone Example 1: capacity, FIFO, and offer

This program runs the same scenario on an ArrayBlockingQueue with capacity=2 and a LinkedBlockingQueue with capacity=2. It verifies that both implement the equivalent contract for basic operations.

Save **BlockingQueueComparisonDemo.java**:

~~~java
import java.util.concurrent.ArrayBlockingQueue;
import java.util.concurrent.BlockingQueue;
import java.util.concurrent.LinkedBlockingQueue;

public class BlockingQueueComparisonDemo {
    private static void check(String name, BlockingQueue<Integer> queue)
            throws InterruptedException {
        queue.add(10);
        queue.add(20);

        boolean thirdAccepted = queue.offer(30);
        int remaining = queue.remainingCapacity();

        int first = queue.take();
        boolean laterAccepted = queue.offer(30);
        int second = queue.take();
        int third = queue.take();

        System.out.println(name + ": offerWhenFull=" + thirdAccepted
                + ", remainingWhenFull=" + remaining
                + ", offerAfterTake=" + laterAccepted
                + ", fifo=" + first + "," + second + "," + third);
    }

    public static void main(String[] args) throws InterruptedException {
        check("array", new ArrayBlockingQueue<>(2));
        check("linked", new LinkedBlockingQueue<>(2));
    }
}
~~~

Compile/run with JDK 17+:

~~~bash
javac BlockingQueueComparisonDemo.java
java BlockingQueueComparisonDemo
~~~

Exact output when no other threads access the two queues:

~~~text
array: offerWhenFull=false, remainingWhenFull=0, offerAfterTake=true, fifo=10,20,30
linked: offerWhenFull=false, remainingWhenFull=0, offerAfterTake=true, fifo=10,20,30
~~~

Explanation: each queue accepts 10 and 20 and becomes full. `offer(30)` returns false without adding the element. `take()` removes 10; afterwards `offer(30)` returns true. The next two `take` calls return 20 and 30. `remainingCapacity()` is captured **right when full**, so it equals 0.

**Takeaway:** Under the same `BlockingQueue` contract, producer–consumer code can switch between the two implementations without changing the basic semantics of `put/take/offer/poll`; however, memory/performance/queue policy will differ.

## 10. Standalone Example 2: producer blocked on put, consumer frees space

This program uses a queue with capacity=1 and one producer. The queue already contains `"first"` before the producer attempts to add `"second"`. Main receives a start signal, takes the first element, then waits for the producer to finish and takes the new element. The result does not depend on thread names or `sleep`.

Save **QueueProducerConsumerDemo.java**:

~~~java
import java.util.concurrent.ArrayBlockingQueue;
import java.util.concurrent.BlockingQueue;
import java.util.concurrent.CountDownLatch;
import java.util.concurrent.LinkedBlockingQueue;
import java.util.concurrent.atomic.AtomicBoolean;

public class QueueProducerConsumerDemo {
    private static void run(String name, BlockingQueue<String> queue)
            throws InterruptedException {
        queue.put("first");
        CountDownLatch producerStarted = new CountDownLatch(1);
        AtomicBoolean producerInserted = new AtomicBoolean(false);

        Thread producer = new Thread(() -> {
            producerStarted.countDown();
            try {
                queue.put("second");
                producerInserted.set(true);
            } catch (InterruptedException e) {
                Thread.currentThread().interrupt();
            }
        }, name + "-producer");

        producer.start();
        producerStarted.await();

        // The producer may or may not have entered put() yet, but the queue remains full
        // until main takes "first".
        String first = queue.take();
        producer.join();
        String second = queue.take();

        System.out.println(name + ": " + first + " -> " + second
                + ", inserted=" + producerInserted.get());
    }

    public static void main(String[] args) throws InterruptedException {
        run("array", new ArrayBlockingQueue<>(1));
        run("linked", new LinkedBlockingQueue<>(1));
    }
}
~~~

Run:

~~~bash
javac QueueProducerConsumerDemo.java
java QueueProducerConsumerDemo
~~~

Output:

~~~text
array: first -> second, inserted=true
linked: first -> second, inserted=true
~~~

**Why is this safe?**

- The capacity=1 queue already contains first, so second **cannot be inserted successfully before first is taken**.
- Main waits for the signal that the producer has started, then takes first. If the producer has already entered `put`, it is woken up when space becomes available; if it has not entered `put` yet, it will insert afterwards.
- Main uses `producer.join()` to know the producer has completed before taking second; it does not rely on an arbitrary number of milliseconds of `sleep`.
- `producerInserted` is only set to true **after** `put` succeeds.
- The correctness of the example assumes no external interrupt requests and normal thread scheduling. A `put` on a full queue can **wait**; here the consumer always frees space.

Do not write tests assuming “after `Thread.sleep(50)` the producer is definitely WAITING”: the scheduler does not guarantee that timing. The latch expresses coordination order, while capacity semantics guarantee there is no room for second before take.

## 11. Interruption and cancellation while waiting on a queue

Both `put` and `take` are waiting points that support `InterruptedException`. When a worker is asked to shut down, the logic usually needs to exit cooperatively:

~~~java
void consume(BlockingQueue<Job> queue) {
    while (!Thread.currentThread().isInterrupted()) {
        try {
            Job job = queue.take();
            process(job);
        } catch (InterruptedException e) {
            Thread.currentThread().interrupt();
            return;
        }
    }
}
~~~

This is an illustrative integration method where `Job` and `process` are application-defined. When `take` is interrupted while waiting, the method restores the interrupt flag and returns. Do not catch `InterruptedException` and silently loop forever, as that can make the worker unresponsive to shutdown.

### Standalone Example 3: producer interrupted when queue is full

Save **QueueInterruptionDemo.java**:

~~~java
import java.util.concurrent.ArrayBlockingQueue;
import java.util.concurrent.BlockingQueue;
import java.util.concurrent.CountDownLatch;
import java.util.concurrent.LinkedBlockingQueue;
import java.util.concurrent.atomic.AtomicBoolean;

public class QueueInterruptionDemo {
    private static void run(String name, BlockingQueue<String> queue)
            throws InterruptedException {
        queue.put("original");
        CountDownLatch producerStarted = new CountDownLatch(1);
        AtomicBoolean cancelled = new AtomicBoolean(false);

        Thread producer = new Thread(() -> {
            producerStarted.countDown();
            try {
                queue.put("new");
            } catch (InterruptedException e) {
                cancelled.set(true);
                Thread.currentThread().interrupt();
            }
        }, name + "-producer");

        producer.start();
        producerStarted.await();
        producer.interrupt();
        producer.join();

        System.out.println(name + ": cancelled=" + cancelled.get()
                + ", remaining=" + queue.take());
    }

    public static void main(String[] args) throws InterruptedException {
        run("array", new ArrayBlockingQueue<>(1));
        run("linked", new LinkedBlockingQueue<>(1));
    }
}
~~~

Run:

~~~bash
javac QueueInterruptionDemo.java
java QueueInterruptionDemo
~~~

Output:

~~~text
array: cancelled=true, remaining=original
linked: cancelled=true, remaining=original
~~~

The capacity=1 queue is full with original. The producer cannot succeed in adding new; main sends an interrupt before any consumer takes original. Whether the interrupt arrives **just before** or **while** `put` is waiting, `put` responds with InterruptedException; `"new"` is not added. The producer marks cancelled and exits; main joins before reading the state. Afterwards, main takes original, which is still in the queue.

**Limitation:** Interruption is a **cooperative signal**, not a rollback for side effects already performed in other steps. If the producer performs a database write before calling `put`, being interrupted during `put` does not automatically undo the database write.

## 12. ThreadPoolExecutor: differences directly affect the number of workers

When the two queues are used as the `workQueue` of a `ThreadPoolExecutor`, the difference in capacity has a major impact on whether the executor creates additional workers.

The Javadoc describes the task admission policy:

1. When workers are below `corePoolSize`, prefer creating a new worker.
2. When core is reached, prefer `workQueue.offer(task)`.
3. Only when the queue cannot accept the task does it try to create an extra worker up to `maximumPoolSize`.
4. If the task cannot be queued and no additional worker can be created, use the `RejectedExecutionHandler`.

~~~text
execute(task)
    |
    +-- workers < core ? --------> create core worker
    |
    +-- queue.offer(task) ? -----> enqueue
    |
    +-- workers < max ? ---------> create extra worker
    |
    +---------------------------> reject/handler
~~~

The diagram is an **admission model**, not a full depiction of shutdown re-checks or races. The core point: **max is not used just because the queue is getting long**.

### ArrayBlockingQueue(capacity) with ThreadPoolExecutor

With `new ArrayBlockingQueue<>(10)`, the queue can reject `offer` once 10 tasks are waiting. If the worker count is still below max, the executor can create additional workers to run incoming tasks. If both max workers and the queue are full, the handler is invoked.

### LinkedBlockingQueue() without capacity

With `new LinkedBlockingQueue<>()`, the queue has a very large nominal capacity. After core workers exist, new tasks usually continue to be queued, **without triggering worker growth up to max** under normal conditions. If producers are faster than consumers, memory and queue wait time can grow very large.

### LinkedBlockingQueue(capacity) with ThreadPoolExecutor

With `new LinkedBlockingQueue<>(10)`, the queue **also becomes full** at capacity 10. Therefore, it can trigger extra workers/rejection **similarly** to an ArrayBlockingQueue of capacity 10. Choosing array vs. linked **does not by itself determine** whether max takes effect; what matters is **whether a bound is actually configured**.

Do not configure `maximumPoolSize=100` and assume the pool will scale to 100 if the default queue still has room.

## 13. Standalone Example 4: same core/max, different queue leads to different behavior

Save **QueueExecutorComparisonDemo.java**:

~~~java
import java.util.concurrent.ArrayBlockingQueue;
import java.util.concurrent.CountDownLatch;
import java.util.concurrent.LinkedBlockingQueue;
import java.util.concurrent.RejectedExecutionException;
import java.util.concurrent.ThreadPoolExecutor;
import java.util.concurrent.TimeUnit;

public class QueueExecutorComparisonDemo {
    private static Runnable gated(
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

    private static void boundedArray() throws InterruptedException {
        ThreadPoolExecutor pool = new ThreadPoolExecutor(
                1, 2, 30, TimeUnit.SECONDS,
                new ArrayBlockingQueue<>(1),
                new ThreadPoolExecutor.AbortPolicy()
        );
        CountDownLatch firstStarted = new CountDownLatch(1);
        CountDownLatch extraStarted = new CountDownLatch(1);
        CountDownLatch release = new CountDownLatch(1);
        boolean rejected = false;

        try {
            pool.execute(gated(firstStarted, release));
            firstStarted.await();
            pool.execute(() -> { }); // occupies one queue slot
            pool.execute(gated(extraStarted, release)); // extra worker
            extraStarted.await();
            try {
                pool.execute(() -> { }); // no more queue or workers
            } catch (RejectedExecutionException e) {
                rejected = true;
            }

            System.out.println("array: workers=" + pool.getPoolSize()
                    + ", queued=" + pool.getQueue().size()
                    + ", rejected=" + rejected);
        } finally {
            release.countDown();
            pool.shutdown();
            if (!pool.awaitTermination(5, TimeUnit.SECONDS)) {
                pool.shutdownNow();
            }
        }
    }

    private static void unboundedLinked() throws InterruptedException {
        ThreadPoolExecutor pool = new ThreadPoolExecutor(
                1, 2, 30, TimeUnit.SECONDS,
                new LinkedBlockingQueue<>(),
                new ThreadPoolExecutor.AbortPolicy()
        );
        CountDownLatch firstStarted = new CountDownLatch(1);
        CountDownLatch release = new CountDownLatch(1);

        try {
            pool.execute(gated(firstStarted, release));
            firstStarted.await();
            pool.execute(() -> { });
            pool.execute(() -> { });

            System.out.println("linked: workers=" + pool.getPoolSize()
                    + ", queued=" + pool.getQueue().size()
                    + ", maximum=" + pool.getMaximumPoolSize());
        } finally {
            release.countDown();
            pool.shutdown();
            if (!pool.awaitTermination(5, TimeUnit.SECONDS)) {
                pool.shutdownNow();
            }
        }
    }

    public static void main(String[] args) throws InterruptedException {
        boundedArray();
        unboundedLinked();
    }
}
~~~

Compile/run:

~~~bash
javac QueueExecutorComparisonDemo.java
java QueueExecutorComparisonDemo
~~~

Output when there is no external interruption and workers do not fail unexpectedly:

~~~text
array: workers=2, queued=1, rejected=true
linked: workers=1, queued=2, maximum=2
~~~

**Why?**

- **Array:** the core worker is held at the latch, the second task enters the capacity=1 queue. The third task causes queue `offer` to fail, so the executor creates a second extra worker. Both workers remain busy and the queue is still full, so the fourth task goes to AbortPolicy and is rejected.
- **Default Linked:** the core worker is held busy, and both subsequent tasks are queued because the capacity is very large. `maximumPoolSize=2` does not mean the executor must create a second worker while the queue still accepts tasks.
- The latches hold the workers at the exact moment of printing, without relying on `Thread.sleep()`; afterwards main releases the workers and shuts down the pool.

**Try next:** Replace `new LinkedBlockingQueue<>()` with `new LinkedBlockingQueue<>(1)` in the linked branch and adjust the scenario like the array branch. When bounded, the linked queue can also fill up and trigger an extra worker/rejection under the same admission rules.

**Do not conclude “array always scales workers while linked never does”.** The two behaviors differ in the demo because **different capacities were chosen**, not solely because of the backing representation.

## 14. Memory: a bounded queue does not mean bounded total application memory

With ArrayBlockingQueue:
- The backing array has a fixed number of slots, making it convenient to estimate queue-level overhead.
- However, each element can hold a large object graph. 100 tasks each capturing 100 MB of data can still exceed the heap.
- Tasks currently running on workers **are not in the work queue**, so total “requests in system” also includes active tasks.

With LinkedBlockingQueue:
- Each enqueue may allocate a linked node and hold references to the payload.
- If the default very large queue is used, backlog accumulates without application-level throttling.
- If a finite capacity is configured, the number of **waiting items** is still bounded, though node allocation/GC can affect throughput.
- When a task is cancelled while still in the queue, it may continue holding references until removed/reclaimed by the management mechanism; cancellation does not automatically purge every queue structure immediately by default.

Minimum capacity estimation should consider:

~~~text
Outstanding work =
  running tasks + queued tasks + upstream pending tasks

Approximate memory budget:
  queue overhead
  + payloads in queued tasks
  + state of running tasks
  + other buffers/caches
~~~

This formula is a qualitative model, **not a guaranteed byte count**. To quantify, measure object sizes, use a sampling profiler, and check heap occupancy, allocation rate, queue depth, and GC on realistic workloads.

### What is high queue length a sign of?

A long queue indicates that producers are outpacing processing capacity over a period of time, or consumers are blocked/failing/slow. It does not necessarily mean the queue implementation is poor. Common causes include:
- slow remote I/O, small connection pool;
- too few consumers;
- overly large producer bursts;
- tasks holding locks for a long time or retrying continuously;
- downstream rate limits;
- missing cancellation for expired work.

Increasing capacity can **hide bugs by increasing wait times** without automatically increasing throughput.

## 15. Backpressure: design from the consequences of being full

Clearly define the business requirements:

1. **Allowed to block the producer?** Use `put` or timed `offer`; avoid blocking an event loop or deadline-critical thread.
2. **Allowed to reject?** Use `offer`, return an “overloaded” signal, or route to a controlled retry path.
3. **Must every task be processed?** You need durable messaging/ack/retry protocols outside an in-memory queue if process crashes must be tolerated.
4. **Is there a wait deadline?** Use timed `offer` and `poll`; if expired, return a clear outcome.
5. **Can expired work be dropped?** Add business-level deadline/expiry logic; the queue does not know an HTTP request has timed out.
6. **Are there multiple consumers?** Choose the consumer count based on actual throughput, connection limits, and memory budget.
7. **Do tasks depend on each other?** Avoid producers/consumers holding a resource and blocking on the queue in a way that creates a wait-cycle.

`BlockingQueue` is not a database transaction, does not provide persistent acknowledgment, and does not guarantee exactly-once execution across process crashes. Queue operations are safe within the JVM, but system-wide durability/uniqueness must be handled separately.

## 16. Proper producer–consumer shutdown

`BlockingQueue` **does not have a standard close() method in the interface**. A consumer stuck in `take()` on an empty queue can wait forever if producers have finished without a shutdown protocol.

Common approaches:
- **Poison pill:** enqueue a special value that the consumer recognizes to exit.
- **Interrupt:** when appropriate, interrupt the consumer so `take` throws InterruptedException and the task cleans up.
- **Timed poll + lifecycle flag:** the consumer wakes up periodically, checking `producerDone` and whether the queue has been drained.
- **ExecutorService.shutdown()/awaitTermination():** manage workers when the queue is an executor's work queue, though callers must understand the difference between `shutdown` and `shutdownNow`.

### Poison pill is not null

Because `BlockingQueue` does not accept null, you cannot enqueue null as a sentinel. Use a dedicated sentinel object or a wrapper type:

~~~java
sealed interface Message permits Data, Stop {}

record Data(String payload) implements Message {}

record Stop() implements Message {}
~~~

These are Java 17 type declarations (to be placed in an appropriate file/class). The consumer checks `instanceof Stop` to exit. In multi-consumer applications, you typically need **enough stop tokens** for the number of consumers that must terminate, or an equivalent broadcast/lifecycle protocol.

**Do not send stop too early:** if a producer can still enqueue work after the stop token, consumers may stop before processing all data. Follow the order: “producers have stopped generating work → determine queue drain/stop protocol → consumers terminate”.

### Do not trust queue.isEmpty() alone

~~~java
if (queue.isEmpty()) {
    return; // May be wrong: producer is not done yet, new items will arrive.
}
~~~

This is an anti-pattern when a consumer is expected to run until all system work is complete. `isEmpty` only reports state at a single point in time; it has no transaction tied to the producers' lifecycle. If you need to wait for new work, use `take`; if you need a termination condition, use an owner signal and appropriate synchronized checks.

### Limitations of drainTo

`drainTo(collection)` transfers multiple available elements from the queue into a collection for the caller to process. It can reduce overhead compared to calling `take` repeatedly in some workloads. However:
- It does not mean concurrent producers are stopped.
- It does not guarantee the entire queue remains empty after draining, as a producer may enqueue new items.
- If the target collection throws an exception during transfer, partial transfer of some elements may require recovery handling.
- Do not call `drainTo(queue)` to drain into itself; the API rejects/disallows it.

## 17. FIFO and execution order: two different concepts

Both queues provide FIFO for elements in insertion order. However, with **two consumers**, **completion order** is not guaranteed:

~~~text
Initial queue: A, B

Consumer 1 take(A), processes for 10 seconds.
Consumer 2 take(B), processes for 1 second.

B can finish before A
even though A was taken from the queue before B.
~~~

Similarly, if the queue is `ThreadPoolExecutor.workQueue`, a task may be handed directly to an extra worker instead of being queued when the queue is full; overall pool start/completion order is not strictly FIFO.

If the business requires processing **the same entity in strict order**, consider:
- One sequential consumer per partition/key.
- Partitioning by key and serializing each partition.
- Sequence/version checking where results are committed.
- Idempotent operations and a system-wide ordering protocol.

ArrayBlockingQueue's fairness flag does not by itself solve commit ordering across multiple workers.

## 18. Thread safety does not mean every combination of operations is atomic

Both queues protect their individual operations per the concurrent collection contract; however, compound operations like the following are subject to races:

~~~java
if (!queue.isEmpty()) {
    E item = queue.poll(); // can still be null
    use(item);
}
~~~

This is **Java-like pseudocode**, assuming `E` and `use` are defined. Between `isEmpty` and `poll`, another consumer can take the last element.

Solutions:
- If you want to take immediately if available, use **a single `poll()`** and check for `null`.
- If you want to wait, use **`take()`** or timed `poll`.
- If you need to “check and update multiple resources together”, design an appropriate protocol/lock; BlockingQueue does not make external state atomic.
- Do not rely on `remainingCapacity()` followed by `offer()` as a reservation. Another producer can take the slot between the two calls.

### Memory visibility / happens-before

Per the concurrent collections contract, **actions in a producer prior to placing an object into a queue happen-before actions in a consumer subsequent to accessing/removing that element**. Therefore, a producer initializing a payload before `put` and a consumer receiving it via `take` have proper visibility guarantees.

However, if the producer **continues modifying a mutable object after enqueueing** without synchronization, a data race can still occur. The queue safely publishes the reference; it does not make future mutations of the object thread-safe.

~~~java
record Event(String message) {}

BlockingQueue<Event> queue = new ArrayBlockingQueue<>(8);
queue.put(new Event("ready"));
Event received = queue.take();
System.out.println(received.message());
~~~

This is a snippet inside a method with exception handling. An Event record with an immutable String component is well-suited for ownership transfer. If an event contains a mutable List, use a defensive copy/immutable snapshot to prevent modification after publication.

## 19. Benchmarking and tuning: do not conclude from the implementation name alone

Oracle Javadoc notes that LinkedBlockingQueue typically has higher throughput than ArrayBlockingQueue in many scenarios, but is less predictable. This does not mean:
- always faster on every CPU/JDK;
- lower latency at every percentile;
- lower memory footprint;
- always less contention;
- memory bounds can be ignored.

A proper experiment should:
1. Compare **at the same capacity** when studying array vs. linked structure.
2. Keep the same number of producers/consumers.
3. Keep the same item size/work per item.
4. Measure throughput, p50/p95/p99 enqueue/dequeue latency, allocation rate, and GC.
5. Separate cases where the queue is mostly empty, mostly full, and oscillating between the two.
6. Test fairness false/true if using ArrayBlockingQueue.
7. Test bounded/unbounded **as two separate policies**, not conflating the difference into implementation speed comparisons.
8. Measure thread blocking time, context switches, heap usage, and connection/resource pressure.
9. Use an appropriate benchmarking tool such as JMH for serious measurements; do not write a single `System.nanoTime` loop and draw conclusions.
10. Test shutdown/cancellation/overload behavior as well, not just the happy path.

In some systems, reducing queue capacity causes earlier rejection but **better protects memory and tail latency**. That can be the right operational outcome even if peak throughput drops slightly.

## 20. Decision table: which one should you use?

| Scenario | Starting recommendation | Reason |
|---|---|---|
| Need clear backlog bound, minimal node allocation | `ArrayBlockingQueue<>(capacity)` | Fixed backing array, bounded from the start |
| Need a fair policy for waiters | `ArrayBlockingQueue<>(capacity, true)` | Has fairness flag; trades off throughput |
| Want a linked queue while still needing backpressure | `LinkedBlockingQueue<>(capacity)` | Optional bound, FIFO, full put/take |
| High-contention producer/consumer workload | Benchmark both **at the same capacity** | Linked may have good throughput, but not guaranteed on every system |
| Using ThreadPoolExecutor where max should engage when queue is full | **A bounded queue**, array or linked | Queue must fill to capacity to trigger extra workers |
| Want to absorb a practically unbounded backlog | Consider carefully, usually **not by default** | Unbounded Linked easily increases memory/latency |
| Want direct handoff with no backlog | Consider `SynchronousQueue` | Different option, not Array/Linked |
| Want a non-blocking queue for multiple producers/consumers | Consider `ConcurrentLinkedQueue` | No `take/put` blocking semantics |
| Want to prioritize tasks by priority | Consider `PriorityBlockingQueue` | Not FIFO like the two queues here |
| Need persistence/ack/retry after process crash | Broker/durable store + proper protocol | In-memory BlockingQueue does not provide durability |

In practice, the decision usually depends more on **queue bounds** and **full-queue policy** than on micro-optimizations between array and linked.

## 21. Common code review mistakes

**Mistake 1 — Calling the default LinkedBlockingQueue “truly infinite”.** Nominal capacity is Integer.MAX_VALUE, but memory is finite.

**Mistake 2 — Saying LinkedBlockingQueue is always unbounded.** The `new LinkedBlockingQueue<>(n)` constructor creates a bounded queue.

**Mistake 3 — Saying ArrayBlockingQueue grows capacity automatically.** Capacity is fixed after creation; there is no auto-resize.

**Mistake 4 — Calling `offer` without checking the boolean.** When the queue is full, tasks can be silently dropped while the application assumes they were accepted.

**Mistake 5 — Using `put` directly on an event-loop or request thread that must not block.** When the queue is full, the caller can block for a long time.

**Mistake 6 — Enabling fairness and assuming all tasks will complete in strict FIFO order.** Fairness among waiting threads does not dictate processing duration.

**Mistake 7 — Configuring a very large ThreadPoolExecutor max with an unbounded LinkedBlockingQueue and expecting the pool to scale automatically.** The executor prefers the queue after core.

**Mistake 8 — Setting a large capacity to “fix” slow consumers.** Backlog/latency increases, while throughput does not automatically improve.

**Mistake 9 — Using `null` as a poison pill.** BlockingQueue does not accept null.

**Mistake 10 — Consumer exits when `isEmpty()==true` while producers are still running.** Races with new enqueues.

**Mistake 11 — Swallowing InterruptedException inside a `take/put` loop.** The worker may fail to respond to shutdown.

**Mistake 12 — Relying on `remainingCapacity` then `offer` and assuming space is guaranteed.** Check-then-act across two threads is not atomic.

**Mistake 13 — Benchmarking queue throughput at vastly different capacities and attributing it to array vs. linked structure.** Compare under the same workload/policy.

**Mistake 14 — Retaining a mutable payload after enqueue and mutating fields without synchronization.** Publication visibility does not protect subsequent mutations.

**Mistake 15 — Using `size()` as an exact coordination condition across threads.** The snapshot can change immediately; it is not a reservation.

**Mistake 16 — Assuming an empty queue means no active tasks.** Workers may still be processing dequeued elements.

**Mistake 17 — Using ArrayBlockingQueue with a capacity of millions without accounting for backing array cost.** The reference-slot array is allocated based on capacity.

**Mistake 18 — Choosing LinkedBlockingQueue thinking it is “lock-free”.** It is a blocking queue synchronized with locks; it is not lock-free.

**Mistake 19 — Assuming a FIFO queue means exactly-once processing.** Tasks can throw, processes can crash, or callers can retry; there is no durable ack.

**Mistake 20 — Placing the poison pill too early or not providing enough tokens for all consumers.** Can lose final work or leave other consumers waiting indefinitely.

## 22. Pre-deployment checklist

- [ ] Does the queue have an **explicit capacity** chosen according to the memory/latency budget?
- [ ] If using the no-arg LinkedBlockingQueue, are bound=Integer.MAX_VALUE and backlog risks understood?
- [ ] Have `offer` (non-blocking), `put` (blocking), timed offer, and `add` (exception) been distinguished?
- [ ] How long is the producer allowed to block? Are there timeouts/cancellation?
- [ ] Do consumers use take/poll appropriately for lifecycle and deadlines?
- [ ] Is fairness among waiters needed? Has the tradeoff been measured?
- [ ] Do payloads have clear immutability/ownership after enqueue?
- [ ] Is InterruptedException handled without swallowing the signal?
- [ ] Is there a valid producer–consumer termination signal (poison pill/interrupt/flag)?
- [ ] Does the queue have multiple consumers and require preserving business ordering?
- [ ] If used as a ThreadPoolExecutor workQueue, has core→queue→max→reject been verified?
- [ ] Does the RejectedExecutionHandler clearly report unaccepted tasks?
- [ ] Have queue size, time-in-queue, throughput, and tail latency been measured?
- [ ] Are running tasks, upstream backlog, and payload memory accounted for?
- [ ] Is the case where all consumers block/throw while producers continue generating work handled?
- [ ] Have saturation and process shutdown been load-tested, not just normal throughput?

## 23. Self-check questions and answers

**Question 1.** Is `new LinkedBlockingQueue<>()` a queue that never fills up?

**Answer:** No. The default capacity is `Integer.MAX_VALUE`, and the heap is finite. The application can run out of memory before hitting the nominal bound.

**Question 2.** Both queues are FIFO, so are two consumers guaranteed to finish work in the exact order items were taken from the queue?

**Answer:** No. FIFO describes the order elements are retrieved; differing processing durations can invert completion order.

**Question 3.** `ArrayBlockingQueue<>(2)` already has 2 items. What does `offer(newItem)` do?

**Answer:** Returns `false` immediately, without blocking and without adding the element.

**Question 4.** On that same queue, what does `put(newItem)` do?

**Answer:** May wait until a consumer takes an item, or throw InterruptedException if the thread is interrupted while waiting.

**Question 5.** Why does ArrayBlockingQueue often have good memory predictability for queue capacity?

**Answer:** It uses a fixed-size backing array and does not allocate a linked node per item. However, payloads held in slots and active tasks still consume memory.

**Question 6.** Can LinkedBlockingQueue be bounded?

**Answer:** Yes: `new LinkedBlockingQueue<>(capacity)` with a positive capacity.

**Question 7.** A ThreadPoolExecutor with core=2, max=10 uses an unbounded LinkedBlockingQueue. When both workers are busy, will new tasks cause the pool to scale up to 10 right away?

**Answer:** Typically no. The work queue continues accepting tasks; the executor prefers the queue once core is reached.

**Question 8.** If you want max to take effect when backlog reaches a limit, do you have to use ArrayBlockingQueue?

**Answer:** No. `LinkedBlockingQueue<>(n)` is also bounded and can trigger additional workers when full.

**Question 9.** Does fairness=true guarantee business tasks finish in FIFO order?

**Answer:** No. Fairness is a policy for threads waiting for queue access, not the completion order of worker computation.

**Question 10.** Why should you not use `queue.isEmpty()` to decide when a consumer should exit while producers are still active?

**Answer:** Producers can add an item right after the check; a separate lifecycle/termination protocol is needed.

**Question 11.** For a BlockingQueue, can `poll()==null` represent an actual null element that was enqueued?

**Answer:** No. The queue does not accept null; null signals that no element was available at the time of `poll`.

**Question 12.** With a bounded capacity, is the entire JVM guaranteed never to OOM?

**Answer:** No. Payloads can be large, running tasks/upstream queues also use memory, and there are many other allocation sources.

## 24. Official Java documentation

- **ArrayBlockingQueue (Java 17):** https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/concurrent/ArrayBlockingQueue.html
- **LinkedBlockingQueue (Java 17):** https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/concurrent/LinkedBlockingQueue.html
- **BlockingQueue (Java 17):** https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/concurrent/BlockingQueue.html
- **ThreadPoolExecutor (Java 17):** https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/concurrent/ThreadPoolExecutor.html
- **Concurrent Collections memory consistency (Java 17):** https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/concurrent/package-summary.html
- **Java Language Specification, Threads and Locks:** https://docs.oracle.com/javase/specs/jls/se17/html/jls-17.html

**Conclusion:** `ArrayBlockingQueue` and `LinkedBlockingQueue` are both **FIFO BlockingQueues**, but Array uses a **fixed array** with a fairness flag, while Linked uses **linked nodes** and is only bounded if **you specify a capacity** (default Integer.MAX_VALUE). Choosing the right one requires considering **backpressure, queue capacity, allocation/GC, contention, task latency, and interaction with ThreadPoolExecutor**. Do not treat an unbounded backlog as an overload solution; set bounds and a full-queue policy that fit your business requirements.

# Producer–Consumer and Bounded Queues in Java

## 1. Problem and Goals

**Producer–consumer** is a model where multiple threads create work (producers) and place it into a shared buffer (queue), while one or more other threads retrieve and process the work (consumers). Producers and consumers run independently at varying speeds, so a thread-safe exchange mechanism is required between them.

With a **bounded queue**, the number of waiting elements cannot exceed a chosen `capacity`. This is an important design choice to limit memory consumption, regulate production rate, and create **backpressure**: when consumers cannot keep up, producers must wait, time out, or receive an explicit rejection decision.

After this lesson, you should be able to:
- Explain the relationship between producers, queue, consumers, capacity, and backpressure.
- Choose the right `put`, `take`, `offer`, and `poll` methods and handle thread interruption.
- Build a Java work-processing pipeline with `ArrayBlockingQueue` without losing tasks due to common synchronization bugs.
- Design shutdown, overload control, performance observability, and tests for full/empty queue cases.

The scope is **general Java concurrency**, using JDK APIs without framework dependencies.

## 2. From Model to Invariants

Suppose producers receive events and consumers process each event:

~~~text
Producer P1 ──┐
              ├──> [ bounded FIFO queue: capacity = 3 ] ──> Consumer C1
Producer P2 ──┘                                    └───────> Consumer C2
~~~

At any point in time, if `size` is the number of tasks waiting in the queue, the fundamental invariant is:

~~~text
0 <= size <= capacity
~~~

- **Queue not full:** a producer can insert another element.
- **Queue full:** `put` must wait until space becomes available; untimed `offer` returns `false` immediately; `offer(timeout)` waits up to the allowed duration.
- **Queue not empty:** a consumer removes one element.
- **Queue empty:** `take` waits for new work; untimed `poll` returns `null` immediately; `poll(timeout)` waits for a bounded duration.
- **FIFO:** `ArrayBlockingQueue` removes elements in the order *they were inserted into the queue*. When multiple producers run concurrently, the order across producers is not fixed; when multiple consumers process concurrently, the **completion order** can also differ from the removal order.

Example of a queue with capacity 2, with only one producer and one consumer:

| Step | Action | Queue contents after step |
| --- | --- | --- |
| 1 | P puts A | [A] |
| 2 | P puts B | [A, B] (full) |
| 3 | P calls `put(C)` | Still [A, B]; P is waiting |
| 4 | C calls `take()`, gets A | [B]; P has a chance to proceed |
| 5 | `put(C)` completes | [B, C] |

Consumers do not need to call a manual "wake up producer" API: `BlockingQueue` handles this coordination. However, space becoming available does not mean a waiting producer will immediately get CPU time; the thread scheduler decides when it executes.

### What Does a Queue Solve, and What Does It Not Solve?

`BlockingQueue` coordinates threads and exchanges elements safely without requiring callers to lock around each `put`/`take` operation. It also provides a **happens-before** relationship: actions by one thread before placing an element into a `BlockingQueue` happen-before actions by another thread after retrieving/accessing that element from the queue. This supports safe object publication through the queue.

However, the queue does **not** make the work object itself immutable. If a producer continues modifying a mutable object after enqueuing while a consumer reads that object, you can still encounter a race condition. Prefer passing immutable data (`record` or read-only objects), or apply separate synchronization for mutable state.

A queue also does not inherently provide durable storage, retries, transactions, deduplication, or guarantees that a task has completed. A consumer succeeding in taking an element only proves the task has left the queue, not that business processing succeeded.

## 3. Key Methods of `BlockingQueue<E>`

| Intent | Unbounded wait by API design | Immediate result | Timed wait |
| --- | --- | --- | --- |
| Add element when queue is full | `put(e)` | `offer(e)` returns `false` | `offer(e, timeout, unit)` returns `false` on expiration |
| Remove element when queue is empty | `take()` | `poll()` returns `null` | `poll(timeout, unit)` returns `null` on expiration |

Other APIs to distinguish:

- `add(e)` throws `IllegalStateException` if the queue is bounded and full; `remove()` throws `NoSuchElementException` if empty.
- `peek()` reads the head element **without removing it**; returns `null` if empty.
- `remainingCapacity()` and `size()` only reflect state at a single point in time. Between checking and enqueuing, another thread may modify the queue; therefore, do not write patterns like "`if (remainingCapacity() > 0) put(...)`" expecting never to block.
- `drainTo(collection, n)` transfers multiple waiting elements into a collection to reduce per-element removals; it does not automatically turn processing the whole batch into a transaction.
- `BlockingQueue` does not accept `null` elements, because `null` is used as a "no element" signal by some methods.

**Key takeaway:** "unbounded wait" describes not specifying a timeout in the API; the thread can still be interrupted. `put`, `take`, and the timed variants declare `InterruptedException`. Do not swallow this exception and continue an infinite loop.

## 4. Runnable Java 17 Example: Two Producers, Two Consumers, Capacity 3

This example uses `ArrayBlockingQueue<Work>`, an immutable record as the message, `ExecutorService` to manage threads, and a dedicated stop message (**poison pill**) for each consumer. Main only sends the stop signal **after all producers have finished**, so no new work ends up behind the stop signal.

Save the file **ProducerConsumerDemo.java**:

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

public class ProducerConsumerDemo {
    record Work(int producerId, int sequence) {}

    // This value is outside the domain of normal work items.
    private static final Work STOP = new Work(-1, -1);

    public static void main(String[] args) throws Exception {
        int producerCount = 2;
        int consumerCount = 2;
        int workPerProducer = 6;

        BlockingQueue<Work> queue = new ArrayBlockingQueue<>(3);
        ExecutorService pool =
                Executors.newFixedThreadPool(producerCount + consumerCount);
        AtomicInteger produced = new AtomicInteger();
        AtomicInteger consumed = new AtomicInteger();

        List<Future<?>> producers = new ArrayList<>();
        List<Future<?>> consumers = new ArrayList<>();

        try {
            for (int i = 0; i < producerCount; i++) {
                final int id = i;
                producers.add(pool.submit(() -> {
                    for (int n = 1; n <= workPerProducer; n++) {
                        queue.put(new Work(id, n));
                        produced.incrementAndGet();
                    }
                    return null;
                }));
            }

            for (int i = 0; i < consumerCount; i++) {
                consumers.add(pool.submit(() -> {
                    while (true) {
                        Work work = queue.take();
                        if (work.equals(STOP)) {
                            return null;
                        }

                        // Where business processing for "work" takes place.
                        // For example, counting a successfully processed task.
                        consumed.incrementAndGet();
                    }
                }));
            }

            // get() also propagates producer errors back to main.
            for (Future<?> producer : producers) {
                producer.get();
            }

            // Each consumer must receive one stop signal.
            for (int i = 0; i < consumerCount; i++) {
                queue.put(STOP);
            }

            // Wait for consumers to finish processing, and surface any errors.
            for (Future<?> consumer : consumers) {
                consumer.get();
            }

            System.out.printf(
                    "produced=%d, consumed=%d, remaining=%d%n",
                    produced.get(), consumed.get(), queue.size());
        } finally {
            // On error, wake up any tasks still waiting via interrupt.
            // On the success path, all Futures above have already completed.
            pool.shutdownNow();
            pool.awaitTermination(5, TimeUnit.SECONDS);
        }
    }
}
~~~

Compile/run with JDK 17+:

~~~bash
javac ProducerConsumerDemo.java
java ProducerConsumerDemo
~~~

The **deterministic** final output of the example, even though thread scheduling is non-deterministic:

~~~text
produced=12, consumed=12, remaining=0
~~~

**Why is this correct?**

1. Two producers generate a total of `2 × 6 = 12` elements. `put` only returns after the queue accepts the element; `produced` is incremented immediately afterward.
2. Four threads run on a pool with four workers, so producer and consumer threads can make progress concurrently. When the queue is full, producers wait; when empty, consumers wait.
3. Main calls `get()` on **every producer** before enqueuing two STOPs. With FIFO, STOP is placed after all enqueued work; each consumer that receives STOP exits the loop.
4. `get()` on **every consumer** only finishes after the tasks before STOP have been taken and counted. Thus `consumed == 12` and the queue is empty.
5. If a task in the pool throws an exception, `Future.get()` throws `ExecutionException` instead of silently ignoring it. The `finally` block sends interrupts when cleanup is needed.

This pattern demonstrates **controlled shutdown when all producers complete normally**. In a long-running system, you must also design handling for failed producers, consumers dying early, hung work, or cancellation requests; simply calling `put(STOP)` can block forever if the queue is full and no consumers remain active.

**Verification note:** the counter here simulates instant successful processing. If you replace the comment with an operation that can fail, only increment `consumed` after the operation succeeds, and define an explicit error policy.

## 5. Under Overload: Wait, Time Out, Reject, or Drop Work?

No single policy fits every system. Choose based on acceptable wait time, cost of data loss, and how callers react.

- **`put`:** the producer waits until space is available or it is interrupted; useful when work must not be dropped and waiting is acceptable. If components depend on each other in a wait cycle, application-level deadlock can still occur.
- **Untimed `offer`:** returns `false` immediately when full; suitable for instant-response requirements. **You must check the boolean return value.**
- **Timed `offer`:** waits for a bounded time budget; upon expiration, decide to return an error, perform bounded retries, log, or route elsewhere.
- **Drop elements:** only valid when data is droppable per business requirements (for example, sampleable telemetry events). Measure the drop count.
- **Upstream throttling:** reduce intake rate, reduce work-generation concurrency, or signal overload back to the sender.

A small, standalone example using a capacity-1 queue and **no consumer**, to observe exact return values. Save the file **QueueOfferDemo.java**:

~~~java
import java.util.concurrent.ArrayBlockingQueue;
import java.util.concurrent.BlockingQueue;
import java.util.concurrent.TimeUnit;

public class QueueOfferDemo {
    public static void main(String[] args) throws InterruptedException {
        BlockingQueue<String> queue = new ArrayBlockingQueue<>(1);

        System.out.println(queue.offer("A"));
        System.out.println(queue.offer("B"));
        System.out.println(queue.offer("B", 50, TimeUnit.MILLISECONDS));
        System.out.println(queue.poll());
        System.out.println(queue.poll());
    }
}
~~~

~~~bash
javac QueueOfferDemo.java
java QueueOfferDemo
~~~

Stdout:

~~~text
true
false
false
A
null
~~~

The `offer("B", 50, MILLISECONDS)` call could wake up due to interruption (throwing `InterruptedException`), but in this single-threaded program there is no consumer and no interrupt, so the queue remains full until expiration and returns `false`. Do not assume the actual elapsed time is exactly 50 ms: CPU scheduling and system timers have jitter.

### A Timeout Is a Contract, Not Just a Number

If a request has a total budget of 200 ms, do not let enqueuing wait 200 ms **and then** run business processing for another 200 ms while still calling it a 200 ms request. Manage a deadline or split the time budget across stages, with handling when more work cannot be accepted.

Example policy:
- Enqueue succeeds within 20 ms → accept the request.
- After 20 ms the queue is still full → respond with "overloaded" and increment a rejection counter.
- The caller decides whether to retry; if retrying, use backoff, a retry limit, and duplicate-processing controls.

`InterruptedException` is an important control signal. When a method signature allows `throws InterruptedException`, you should usually **propagate** it; if you must catch it to exit a loop, call `Thread.currentThread().interrupt()` before returning or stopping so the interrupt status is preserved for callers. Never write `catch (InterruptedException e) {}`.

## 6. Choosing the Right Queue

| Structure in `java.util.concurrent` | Capacity / characteristics | When to use or caveats |
| --- | --- | --- |
| `ArrayBlockingQueue<E>` | Fixed capacity at creation; FIFO; array-backed | Clear choice for bounded producer–consumer. |
| `LinkedBlockingQueue<E>` | Capacity can be specified; otherwise defaults to `Integer.MAX_VALUE` | Valid if an explicit bound is passed; the "nearly unbounded" default easily grows memory during backlogs. |
| `LinkedBlockingDeque<E>` | Can be bounded; insert/remove at both ends | Use when double-ended operations are truly needed; define ordering policy clearly. |
| `SynchronousQueue<E>` | Stores no waiting elements (logical capacity 0); each handoff requires a matching receiver | Direct handoff with no in-queue backlog; waiting/rejection behavior differs from a typical bounded buffer. |
| `PriorityBlockingQueue<E>` | Not bounded by a capacity parameter; dequeues by priority | Not a replacement for bounded FIFO; low-priority tasks can starve. |
| `DelayQueue<E>` | Unbounded queue; only yields elements whose delay has expired | Suitable for delayed scheduling, not capacity-based backlog control. |
| `ConcurrentLinkedQueue<E>` | Non-blocking, unbounded; no `take`/`put` | When a non-blocking concurrent queue is needed and waiting/bounding is handled separately. |

Do not confuse **thread-safe** with **bounded**. A thread-safe queue without a bound can still exhaust memory if producers stay faster than consumers over time.

`ArrayBlockingQueue` supports the constructor `new ArrayBlockingQueue<>(capacity, true)` to choose fairer servicing order for waiting threads. Fair mode can reduce throughput; it does not guarantee equal latency for all business tasks or that consumers complete in exact enqueue order. Use the default unless measured data justifies otherwise.

## 7. Backpressure and Capacity Sizing

Let:
- `λ` be the arrival rate (items/second).
- `μ` be the **aggregate** processing rate of all consumers (items/second).
- `C` be the queue capacity; `Q` be the number of waiting elements.

If incoming load stays at **`λ > μ`**, the backlog grows until the queue is full. Increasing `C` only delays when it fills; it does not fix a processing capacity deficit. Even if `λ < μ` over the long term, the queue can still fill due to short bursts, jitter, GC pauses, slow I/O, or uneven task durations.

A practical capacity-sizing process:

1. Measure average and peak arrival rates, processing time distribution, and the number of consumers that can actually run.
2. Define the **maximum acceptable wait time** for work and the maximum memory budget. A queue is a staging area, not an infinite store.
3. Estimate the backlog of a burst: for example, 200 jobs/second for 0.5 seconds while consumers pause can create around 100 waiting elements; add prior backlog and variance.
4. Estimate memory = number of stored elements × actual size of each element and its referenced data + queue overhead. Do not measure only an empty record's size if it holds a large payload.
5. Test with normal traffic, bursts, and slow-consumer incidents; observe latency percentiles, timeouts/rejects, GC, and CPU. Tune intake rate, concurrency, and capacity together.

Little's Law `L = λ × W` can help analyze a **steady-state system** when you consistently define the number of items in the system, completion rate, and residence time. Do not use that formula as a capacity guarantee when load persistently exceeds capacity or during extreme bursts. Long queues can increase latency even when throughput looks good.

**For CPU-bound consumers**, adding threads beyond useful CPU capacity usually just increases context switching. **For I/O-bound work**, more consumers can increase throughput if downstream systems allow it, but can also shift the bottleneck to connections, databases, or other services. Every concurrency decision must be measured empirically.

## 8. Shutdown and Error Handling

### Approach 1 — Poison Pill When Producer Completion Is Known

The approach in the example fits a known set of producers/consumers when you want to **drain remaining work in the queue**. Correctness conditions include:

- Stop producers or wait for all producers to finish before placing STOP.
- Place **one STOP per active consumer** that will actually read STOP.
- STOP must not collide with any real work value.
- No new producer enqueues after STOP; otherwise, work may be left behind.
- If consumers have died or the queue stays full, main can get stuck at `put(STOP)`; provide a separate error/cancellation path.

A poison pill is an **application convention**, not a queue-closing feature provided by `BlockingQueue`. The queue itself has no `close()` operation in this interface.

### Approach 2 — Interrupt / Cancellation

When an immediate stop is required, keep the `Future` handles and call `cancel(true)`, or call `shutdownNow()` on the executor and await termination with a bound. Blocking operations respond to interrupts with `InterruptedException`. However, non-interruptible methods or I/O without timeouts may not stop immediately. `shutdownNow()` is a best-effort cancellation, not a guarantee that every task has stopped.

Distinguish two business requirements:
- **Graceful drain:** stop accepting new work, finish processing the queue, let consumers exit, then close resources.
- **Immediate stop:** request a fast stop, accepting or separately handling remaining items and in-flight work.

Do not call `ExecutorService.shutdown()` expecting it to make consumers waiting on `take()` exit on their own: `shutdown()` only stops accepting new tasks and waits for running tasks; it does not send sentinels or interrupt blocked tasks.

### What If Processing Fails?

As soon as `take()` succeeds, the element has been removed from the queue. If the consumer throws an exception afterward, the queue does **not automatically put the element back**. You must choose an intentional policy: log and drop, bounded retry, move to a separate retry queue, or persist to durable storage when zero data loss is required. Retries must have backoff and duplicate detection; retrying immediately into the same full queue can worsen overload.

Do not infer "exactly once" or durability from `BlockingQueue`. On process/JVM failure, in-memory elements can be lost. If durable storage and processing acknowledgment are required, design an appropriate persistence layer.

## 9. Why `wait/notifyAll` Is Still Worth Understanding

`BlockingQueue` is usually a better choice than writing your own buffer. However, understanding monitor mechanics helps analyze race condition bugs. The following is **an illustrative class**, not a standalone runnable program; to run it you need a `main` method and caller threads:

~~~java
import java.util.ArrayDeque;
import java.util.Objects;

final class MonitorBuffer<T> {
    private final ArrayDeque<T> items = new ArrayDeque<>();
    private final int capacity;

    MonitorBuffer(int capacity) {
        if (capacity <= 0) {
            throw new IllegalArgumentException("capacity must be positive");
        }
        this.capacity = capacity;
    }

    public synchronized void put(T value) throws InterruptedException {
        Objects.requireNonNull(value);
        while (items.size() == capacity) {
            wait();
        }
        items.addLast(value);
        notifyAll();
    }

    public synchronized T take() throws InterruptedException {
        while (items.isEmpty()) {
            wait();
        }
        T value = items.removeFirst();
        notifyAll();
        return value;
    }
}
~~~

Key points:

- `synchronized` ensures state checks and deque modifications are mutually exclusive, while also providing monitor visibility rules.
- `wait()` releases the monitor while waiting and reacquires it before continuing. It **must** be called while the thread holds the corresponding object's monitor.
- Use **`while` instead of `if`** because of possible spurious wakeups, or another thread claiming the element/slot before the newly awakened thread runs.
- `notifyAll()` wakes waiting parties so they can re-check their conditions; this is simple and logically safe for a buffer with both waiting producers and consumers, though it may cause extra wakeups.
- Execute slow business processing **outside** synchronized blocks to avoid holding the lock too long; the example above only manipulates the deque while holding the monitor.

A custom class needs additional concurrency tests, shutdown/cancellation handling, and observability. In application code, prefer `ArrayBlockingQueue` or appropriate JDK primitives to reduce the surface area for bugs.

## 10. Common Design Mistakes

| Mistake | Consequence | Fix |
| --- | --- | --- |
| Using default `LinkedBlockingQueue<>()` and calling it bounded | Backlog grows huge under overload | Pass an explicit capacity or use `ArrayBlockingQueue`. |
| Calling `offer` and ignoring the result | Silent work loss | Handle `false` with an explicit rejection/retry policy. |
| Checking `size` before `put` as an invariant | Check–then–act race; can still block | Use queue methods directly with the appropriate waiting policy. |
| Calling `take` on a consumer that must stop without a cancellation mechanism | Consumer waits forever when queue is empty | Design a sentinel, timeout, interrupt, or explicit lifecycle. |
| Sending only one STOP for multiple consumers | One consumer exits, others may wait forever | One stop signal per consumer or another shutdown mechanism. |
| Placing STOP before producers finish | Tasks after STOP may be left behind | Separate the producer-stop phase from the drain phase. |
| Catching and swallowing `InterruptedException` | Hard to cancel, application hangs on shutdown | Propagate or restore the interrupt and exit. |
| Keeping a mutable object and modifying it after enqueuing | Consumer sees inconsistent state | Pass immutable messages or synchronize state separately. |
| Counting `take` calls as successfully processed tasks | Success metric is wrong when processing throws | Count after completion; track failures/retries separately. |
| Increasing capacity indefinitely to fix slow consumers | Higher latency, RAM usage, OOM risk | Fix throughput, admission limits, and overload policy. |

## 11. Observability, Testing, and Boundaries to Prove

**Metrics to measure:** queue occupancy (`size / capacity`), `offer` rejections or timeouts, producer enqueue wait time, time tasks spend in the queue, processing time, producer/consumer throughput, active consumer count, errors/retries, backlog growth rate, and latency percentiles. Record over time; a `size()` snapshot does not capture short spikes.

For testing, include cases with clear expectations:

1. **Full queue:** capacity = 1; insert one element, verify subsequent `offer` returns `false` and timed offer expires when there is no consumer.
2. **Empty queue:** verify `poll` returns `null`; test `take` from a separate thread and insert an element from another thread to observe unblocking.
3. **Multiple producers and consumers:** generate unique IDs, collect processed IDs into a thread-safe structure, verify total count and that each ID appears exactly once under error-free processing.
4. **Interrupt:** let a worker block on `put` or `take`, interrupt it, and verify the worker exits per the defined contract.
5. **Shutdown:** stop producers, send enough STOPs, verify all workers terminate within a timeout; include a cleanup path when a producer or consumer fails.
6. **Burst/overload:** generate an arrival rate temporarily higher than consumption rate and verify the queue never exceeds capacity and wait/rejection times match policy.

For multi-threaded tests, prefer `CountDownLatch`/`CyclicBarrier` to coordinate start times and `Future.get(timeout, unit)` to avoid infinite hangs. Do not rely solely on `Thread.sleep(...)` to "reliably hit" a race condition: tests may randomly pass or fail depending on the machine. Use test deadlines to detect deadlocks and always clean up executors.

### Self-Check Scenarios

**Scenario A:** Producers generate 500 jobs/second, while consumers can only process 350 jobs/second continuously in total. Does increasing capacity from 1,000 to 10,000 make the system sustainable?

**Answer:** No. As long as those rates hold, the backlog grows by about 150 jobs/second until full. Larger capacity only delays when backpressure/timeouts/rejections occur and usually increases latency. You must reduce incoming load or increase actual processing capacity.

**Scenario B:** There are three consumers, two producers, and you want to drain everything and stop using poison pills. How many STOPs are needed, and when should they be placed?

**Answer:** Three STOPs, **after both producers have been confirmed finished** and no new producers are adding work to the queue. Then wait for all consumers to finish; prepare an error path in case a consumer is no longer active.

**Scenario C:** A consumer takes a task, and then processing throws an exception. Does `BlockingQueue` automatically retry it?

**Answer:** No. `take()` already removed the task from the queue; failed processing must be managed by the application with a dedicated error/retry policy.

## 12. Rules of Thumb

When implementing producer–consumer in Java, first determine **whether data loss is acceptable**, the maximum wait time, consumer count, downstream capacity, and shutdown strategy. If you need in-memory bounded FIFO, start with `ArrayBlockingQueue` with a measured and tested capacity, choose `put` or `offer(timeout)` according to your overload contract, handle `InterruptedException` properly, enforce producer–consumer shutdown ordering, and measure backlog and latency under real load.

The strength of a bounded queue is that it turns **consumers being slower than producers** into a bounded, visible, and manageable state. That choice must be paired with waiting, rejection, error-handling, and shutdown policies — simply instantiating a queue object is not enough to complete a concurrency design.

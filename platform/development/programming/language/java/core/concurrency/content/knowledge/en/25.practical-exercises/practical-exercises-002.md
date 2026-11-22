# Practical Exercise: Building a Bounded Producer–Consumer with BlockingQueue in Java

## 1. Problem Statement and Expected Outcomes

Build a multi-threaded pipeline in **Java concurrency** consisting of producers that generate work items, consumers that process work items, and a **bounded queue** in between. When producers emit faster than consumers can process, the system must apply **backpressure** or report overload, rather than holding an unbounded number of `Work` items on the heap.

The exercise uses only the Java standard library: **java.util.concurrent.BlockingQueue**, **ArrayBlockingQueue**, **ExecutorService**, **Future**, synchronization primitives, and atomic types. The content is independent of Spring or any framework.

Specific requirements:

1. Use **2 producers**, each creating 6 `Work` items with unique IDs; **12 Work** items in total.
2. Use **2 consumers** to process `Work` on separate threads.
3. Use an **ArrayBlockingQueue with capacity = 3** as the shared channel.
4. When the queue is full, producers must wait using **put**; do not create a separate unbounded backlog.
5. Only signal termination after **all producers** have finished enqueueing.
6. Each consumer receives a dedicated termination signal (**poison pill**) to exit its loop.
7. Print a **deterministic** summary confirming that the enqueued `Work` count, processed count, and unique ID count all equal 12.
8. Cooperate with interruption and propagate worker errors back to the `main` thread.

After completing this exercise, you should be able to explain why a bounded queue does not automatically mean the entire pipeline is bounded, the differences between **put/offer/take/poll**, how to avoid losing work during shutdown, and how to verify overload behavior.

## 2. Architecture Diagram and Invariants

~~~text
    producer-0 ──┐
                  │       ArrayBlockingQueue<Work>
                  ├─ put ─► [ 1 ] [ 2 ] [ 3 ] ─ take ─► consumer-0
    producer-1 ──┘                 capacity = 3  └ take ─► consumer-1

     buffer full: put must wait for a consumer's take to free a slot
~~~

**Invariants during a normal, completed run:**

- No regular `Work` items are added beyond the expected 12 `Work` items.
- Each `Work` item is taken from the queue only once by a single consumer, because the **take** operation is atomic with respect to the queue.
- Each `Work` item is marked as processed **only after processing completes**.
- By the time all consumer `Future`s finish, all 12 IDs have been recorded, and the queue is empty.
- A poison pill is not counted as business `Work` and does not increment the `processed` counter.

This exercise does not guarantee exactly-once processing in the event of a JVM crash or external side effects. `BlockingQueue` is an **in-memory** channel; crash recovery requires persistence and idempotency mechanisms outside the scope of this basic practical exercise.

### FIFO Does Not Mean Two Consumers Finish in Exact Order

`ArrayBlockingQueue` preserves FIFO arrival order for elements in the queue, but once two consumers have taken two different elements, the **completion order** also depends on the scheduler and processing time. Therefore, the final output should only print counters and verify unique IDs, rather than printing a supposedly fixed processing sequence.

## 3. Understanding the BlockingQueue API

| Operation | When queue is full/empty | When to use |
| --- | --- | --- |
| **put(e)** | Waits until space is available; can be interrupted | When you want backpressure and do not proactively drop work |
| **offer(e)** | Returns `false` immediately if no space is available | When the producer must not block |
| **offer(e, timeout, unit)** | Waits up to `timeout`, then returns `false` if still no space | When the producer has a deadline |
| **add(e)** | Can throw `IllegalStateException` when full | When you want immediate error reporting |
| **take()** | Waits until an element is available; can be interrupted | Long-lived consumers |
| **poll()** | Returns `null` immediately when empty | Non-blocking polling |
| **poll(timeout, unit)** | Waits up to `timeout`, returns `null` on expiration | When a consumer needs to check a stop condition periodically |
| **peek()** | Returns the head of the queue without removing it, or `null` if empty | Instantaneous observation; do not use as a protocol to claim `Work` |

**BlockingQueue does not accept null** as an element. Therefore, do not use **put(null)** to signal completion.

**ArrayBlockingQueue<>(3)** has a fixed array size of 3 slots. **LinkedBlockingQueue<>(3)** is also bounded, but **LinkedBlockingQueue<>()** without a capacity argument defaults to an extremely large bound (`Integer.MAX_VALUE`); do not treat it as an operationally safe bounded queue. **SynchronousQueue** holds no elements in a buffer and requires a rendezvous between sender and receiver; it is not a capacity-3 model. **PriorityBlockingQueue** uses priority ordering and does not provide a similar fixed-capacity bound.

## 4. Complete Solution: Two Producers, Two Consumers, Capacity Three

Create the file **BoundedProducerConsumer.java** with the full code below. The program runs directly on Java 17+.

~~~java
import java.util.ArrayList;
import java.util.List;
import java.util.Set;
import java.util.concurrent.ArrayBlockingQueue;
import java.util.concurrent.BlockingQueue;
import java.util.concurrent.ConcurrentHashMap;
import java.util.concurrent.ExecutorService;
import java.util.concurrent.Executors;
import java.util.concurrent.Future;
import java.util.concurrent.TimeUnit;
import java.util.concurrent.atomic.AtomicInteger;

public final class BoundedProducerConsumer {
    private static final int CAPACITY = 3;
    private static final int PRODUCERS = 2;
    private static final int CONSUMERS = 2;
    private static final int ITEMS_PER_PRODUCER = 6;

    private record Work(int id, boolean stop) {}

    private static final Work STOP = new Work(-1, true);

    public static void main(String[] args) throws Exception {
        BlockingQueue<Work> queue = new ArrayBlockingQueue<>(CAPACITY);
        ExecutorService producers = Executors.newFixedThreadPool(PRODUCERS);
        ExecutorService consumers = Executors.newFixedThreadPool(CONSUMERS);

        AtomicInteger produced = new AtomicInteger();
        AtomicInteger processed = new AtomicInteger();
        Set<Integer> uniqueIds = ConcurrentHashMap.newKeySet();

        List<Future<?>> producerTasks = new ArrayList<>();
        List<Future<?>> consumerTasks = new ArrayList<>();

        try {
            // Start consumers first so receiver threads are ready.
            for (int c = 0; c < CONSUMERS; c++) {
                consumerTasks.add(consumers.submit(() -> {
                    try {
                        while (true) {
                            Work work = queue.take();
                            if (work.stop()) {
                                return;
                            }

                            // Simulate processing; in practice this could be computation or I/O.
                            TimeUnit.MILLISECONDS.sleep(15);
                            if (!uniqueIds.add(work.id())) {
                                throw new IllegalStateException(
                                        "Duplicate ID: " + work.id());
                            }
                            processed.incrementAndGet();
                        }
                    } catch (InterruptedException e) {
                        Thread.currentThread().interrupt();
                        throw new IllegalStateException(
                                "Consumer interrupted", e);
                    }
                }));
            }

            for (int p = 0; p < PRODUCERS; p++) {
                final int producerId = p;
                producerTasks.add(producers.submit(() -> {
                    try {
                        for (int i = 0; i < ITEMS_PER_PRODUCER; i++) {
                            int id = producerId * ITEMS_PER_PRODUCER + i;
                            queue.put(new Work(id, false));
                            produced.incrementAndGet();
                        }
                    } catch (InterruptedException e) {
                        Thread.currentThread().interrupt();
                        throw new IllegalStateException(
                                "Producer interrupted", e);
                    }
                }));
            }

            // Do not send STOP while producers are still enqueueing.
            for (Future<?> future : producerTasks) {
                future.get(30, TimeUnit.SECONDS);
            }

            // Each consumer must receive exactly one STOP.
            for (int i = 0; i < CONSUMERS; i++) {
                if (!queue.offer(STOP, 5, TimeUnit.SECONDS)) {
                    throw new IllegalStateException("Cannot enqueue STOP");
                }
            }

            // Future.get() propagates worker exceptions back to main.
            for (Future<?> future : consumerTasks) {
                future.get(30, TimeUnit.SECONDS);
            }

            int expected = PRODUCERS * ITEMS_PER_PRODUCER;
            if (produced.get() != expected
                    || processed.get() != expected
                    || uniqueIds.size() != expected
                    || !queue.isEmpty()) {
                throw new IllegalStateException("Lost or duplicate work");
            }

            System.out.println("produced=" + produced.get());
            System.out.println("processed=" + processed.get());
            System.out.println("uniqueIds=" + uniqueIds.size());
            System.out.println("queueCapacity=" + CAPACITY);
            System.out.println("queueEmpty=" + queue.isEmpty());
        } finally {
            // Cooperate with interruption when an error or timeout occurs.
            producers.shutdownNow();
            consumers.shutdownNow();
        }
    }
}
~~~

**Compile and run:**

~~~bash
javac BoundedProducerConsumer.java
java BoundedProducerConsumer
~~~

**Exact stdout when the program completes successfully:**

~~~text
produced=12
processed=12
uniqueIds=12
queueCapacity=3
queueEmpty=true
~~~

The execution schedule may vary between runs, but this summary remains deterministic because it is printed only after waiting for all `Future`s to complete. If a consumer or producer fails or times out, the program throws an exception and does not print a false success.

### Walkthrough by Execution Flow

**Step 1: create a queue with an explicit bound.** The queue holds at most 3 `Work` items at a time. When full, **queue.put(work)** blocks the producer thread until a consumer successfully calls `take`. The producer does not keep creating additional `Work` items while waiting on `put`, so it does not build up an unbounded queue on the sending side.

**Step 2: consumers are long-lived workers.** Each consumer runs a loop that calls `take`, processes one `Work` item, and only then calls `take` again. In this example, each consumer holds at most one `Work` item that has been taken and is currently being processed. When it encounters a `Work` item with `stop=true`, the consumer exits.

**Step 3: non-overlapping IDs.** Producer 0 generates IDs `0..5`; producer 1 generates IDs `6..11`. The concurrent hash set from `ConcurrentHashMap` allows both consumers to verify that processed IDs are unique without a data race.

**Step 4: counters have specific meanings.** `produced` increments after `put` succeeds, so it represents the number of `Work` items that entered the queue. `processed` increments after the simulated processing sleep and successful ID recording. While the program is still running, `produced` can be greater than `processed`; that is a valid state when the queue has a backlog.

**Step 5: close the source before stopping the sink.** `main` waits for all producer `Future.get` calls to succeed. Only then does it enqueue `STOP`. Under FIFO, all regular `Work` items have already been enqueued before `STOP`; no regular `Work` item not yet taken by a consumer is bypassed by `STOP`. However, because already-taken `Work` items may still be in processing, `main` must continue waiting for all consumer `Future`s.

**Step 6: one STOP per consumer.** With 2 consumers, if only 1 `STOP` is sent, the remaining consumer may keep waiting on `take` indefinitely. Sending `STOP` too early can cause consumers to leave the pipeline while producers are still trying to enqueue new `Work`.

**Step 7: errors are surfaced to main.** `ExecutorService.submit` returns a `Future`; `Future.get` can report `ExecutionException` or `TimeoutException`. When an error occurs, `finally` calls `shutdownNow` to attempt interrupting workers blocked on `put`/`take`/`sleep`. This does not replace a business recovery workflow, but it prevents the example from silently swallowing errors.

**Note on ExecutorService's internal queue:** `Executors.newFixedThreadPool` has an unbounded internal task queue by default. This program submits exactly **4 long-lived worker runnables**, so no `Runnable` backlog grows with the number of `Work` items. If you instead replaced each `Work` item with a separate `executor.submit` call, the bounded `BlockingQueue` alongside it would no longer bound the entire pipeline.

## 5. Second Experiment: Proving Full-Queue Behavior

To directly observe the difference between **offer** and a timed wait operation, create **FullQueueBehavior.java**:

~~~java
import java.util.concurrent.ArrayBlockingQueue;
import java.util.concurrent.BlockingQueue;
import java.util.concurrent.TimeUnit;

public final class FullQueueBehavior {
    public static void main(String[] args) throws InterruptedException {
        BlockingQueue<String> queue = new ArrayBlockingQueue<>(1);

        queue.put("first");
        System.out.println("offer=" + queue.offer("second"));
        System.out.println("timedOffer=" +
                queue.offer("second", 50, TimeUnit.MILLISECONDS));

        System.out.println("take=" + queue.take());
        System.out.println("offerAfterTake=" + queue.offer("second"));
        System.out.println("takeAgain=" + queue.take());
    }
}
~~~

Run:

~~~bash
javac FullQueueBehavior.java
java FullQueueBehavior
~~~

**Exact stdout:**

~~~text
offer=false
timedOffer=false
take=first
offerAfterTake=true
takeAgain=second
~~~

When `capacity=1` and the queue already contains `"first"`, `offer` immediately returns `false`, while timed `offer` waits up to 50 ms and then returns `false` because there is no consumer. After `take` removes `"first"`, the queue is empty and the next `offer` returns `true`.

**Do not try replacing `offer("second")` with `put("second")` on the same `main` thread before `take`.** The program will block because the queue is full and no other thread is freeing a slot. If you want to demonstrate `put` blocking, create a separate producer thread and have a consumer call `take` after the queue is full; use a timeout so the test does not hang indefinitely.

## 6. A Bounded Queue Creates Backpressure, Not a Universal Memory Bound

With capacity 3 in the solution:

- At most **3 Work items waiting in the queue**.
- At most **2 Work items taken by the 2 consumers for processing**.
- At most **2 Work items temporarily held by the 2 producers while waiting on `put`**.
- In addition, there are objects for tasks, threads, `Future`s, logs, and business data.

Bounding the queue to 3 **does not mean there are only 3 Work items on the entire heap**. If a producer pre-builds a `List` of millions of `Work` items before calling `put` one by one, memory still grows before items enter the queue. If a consumer, after `take`, forwards work to an executor with an unbounded queue, backpressure is broken at the second boundary.

Performance relationship: suppose two consumers each process an average of 20 Work/s, giving an ideal processing capacity near **40 Work/s** without contention. If producers attempt to generate 100 Work/s continuously, the queue will quickly fill and `put` will start blocking. A bounded queue slows producers down; it **does not increase consumer throughput** from 40 to 100.

**Small capacity** saves memory and reduces maximum backlog, but producers are more likely to block during bursts. **Large capacity** absorbs bursts better, but increases the time `Work` spends waiting. Choosing capacity should be based on burst size, memory, latency requirements, and overload policy—not average throughput alone.

If applying **Little's Law** in steady state: `L = λ × W`, where `L` is the average number of in-flight `Work` items within the same boundary, `λ` is throughput, and `W` is mean residence time. This calculation helps sanity-check backlog; **do not use mean `L` to conclude that queue capacity is sufficient for all bursts**.

## 7. What Happens If Work Must Be Rejected?

The solution chooses **put** to preserve all `Work` items during a normal run. If producers must not wait indefinitely, replace it with **offer(timeout)** and explicitly define the policy when it returns `false`:

~~~java
// Illustrative snippet; queue and work must be declared in the calling method.
boolean accepted = queue.offer(work, 100, TimeUnit.MILLISECONDS);
if (!accepted) {
    // Record rejected metric; report overload or perform bounded retry.
}
~~~

The snippet above is an API illustration, not a standalone program. If you use this style in the exercise, **do not increment `produced` when `offer` returns `false`**. When all producers and consumers finish without error, the appropriate invariants are:

~~~text
attempted = accepted + rejected
accepted  = processed
~~~

A **`false`** result indicates that the `Work` item was not accepted into the queue; do not ignore the return value and claim successful processing.

| Policy | API | Consequence |
| --- | --- | --- |
| Wait for space | `put` | Backpressure; caller may block until a consumer is available |
| Reject immediately | `offer` | Caller must handle `false` |
| Wait within deadline | `offer(timeout)` | After timeout, can return an error or overload signal |
| Bounded poll | `poll(timeout)` | Consumer can periodically check a stop flag |
| Drop work by business rule | Custom logic | Must define exactly which `Work` may be dropped and emit metrics |

`BlockingQueue` **does not drop-oldest by default**. Do not arbitrarily call `poll` to discard an old element and then `offer` a new one when business requirements demand full processing, especially while producers/consumers are running concurrently with `STOP` markers.

## 8. Safe Shutdown and Interruption Management

### Why Not Use queue.isEmpty() to Decide When to Stop?

**queue.isEmpty()** is only a snapshot. An empty queue does not prove producers have finished; immediately afterward a producer may `put` more items. A consumer may also still be processing a `Work` item already taken from the queue. Therefore, lifecycle must be governed separately from the instantaneous empty state.

Protocol used in this exercise:

1. Start consumers.
2. Start producers.
3. Wait for all producer `Future`s.
4. Enqueue exactly one `STOP` per consumer.
5. Wait for all consumer `Future`s.
6. Verify `processed`, `uniqueIds`, and `queueEmpty`.
7. Shut down executors.

**Do not use `null`** because `BlockingQueue` rejects `null`. If different termination semantics are needed—such as closing individual producers or reporting end-of-stream errors—design an explicit message protocol rather than relying solely on item counts.

### InterruptedException and shutdownNow

Calls to **put**, **take**, **offer(timeout)**, and **sleep** all respond to interruption. Inside a worker, catch `InterruptedException`, restore the flag via **Thread.currentThread().interrupt()**, and exit or propagate the error. Swallowing the exception and looping back into an infinite loop can prevent shutdown from working.

**shutdownNow()** only attempts to stop tasks via interruption; it does not guarantee that threads terminate immediately if running code does not cooperate with interruption. For production systems, design explicit stop signals, deadlines, handling for in-flight tasks, and bounded termination waits.

### Consumer Failure While Producers Are Calling put

If a consumer dies from a business error and the remaining consumers cannot keep up, producers can become blocked. If the coordinator tries to enqueue `STOP` using `put`, it can block as well. Using `Future.get` and `offer(STOP, timeout)` in the example avoids some hangs, but **does not immediately detect all consumer failures while producers are still running**. Real-world applications should monitor consumer failures early, cancel the pipeline, and define how to handle `Work` already taken from the queue but not yet completed.

### Truly Exactly-Once?

The queue only transfers an object from the buffer to one consumer via `take`; it does not durably persist side effects. If a consumer writes to a DB successfully and crashes before recording completion, a retry can duplicate the result. If it crashes after `take` and before processing, the `Work` item can be lost. More accurately: this exercise verifies **each ID is processed once when the program terminates normally without errors**, not exactly-once delivery across failures.

## 9. Advanced Testing Guide

Run the exercise under the following scenarios. When intentionally inducing errors or hangs, use timeouts or interrupts to terminate.

| Change | Expected result | What to observe |
| --- | --- | --- |
| `CAPACITY=1` | Summary still 12/12/12 | Producers may wait more; queue never exceeds capacity |
| `CAPACITY=100` | Summary unchanged | Queue can absorb larger bursts |
| Consumer `sleep=200 ms` | Summary unchanged if no timeout | Total runtime increases; `put` waits more |
| `CONSUMERS=3` | Must send exactly 3 `STOP`s | All workers exit, none stuck on `take` |
| Send only 1 `STOP` for 2 consumers | One worker may hang | Must detect timeout and fix the protocol |
| Switch `put` to `offer(timeout)` | May have `rejected` items | `attempted=accepted+rejected` and `accepted=processed` |
| Consumer throws on a specific ID | `Future.get` must report error or timeout | Does not print a success summary |
| Producer interrupted during `put` | Worker propagates error to `Future` | Does not increment `accepted` for un-enqueued `Work` |

Add your own measurements:

- Capture **System.nanoTime()** before/after `put` to measure how long producers are blocked.
- Measure `Work` wait time from enqueue to `take`, marking the timestamp at the exact moment it is accepted; a timestamp taken before `put` already includes admission wait time.
- Measure service time from start of processing to completion.
- Measure throughput = `processed` / measurement duration, without mixing `rejected` with `completed`.
- Sample `queue.size()` periodically over time; a single snapshot is neither an accurate mean nor peak.
- Track p95/p99 latency, CPU/GC, thread states, and downstream bottlenecks.

Run multiple times because thread scheduling, JVM warm-up, and sleep timing cause measurements to vary. Do not evaluate a configuration based on a single run.

## 10. Common Mistakes

**Using an unbounded default queue.** `LinkedBlockingQueue` without a capacity argument can hold a huge number of `Work` items. Pass an explicit capacity or use `ArrayBlockingQueue`.

**Creating a bounded queue while placing an unbounded `List` or executor queue outside it.** Bounds must exist at every asynchronous boundary, otherwise memory still grows.

**Using `produced` to count `Work` created before `put`.** When `put` blocks or is interrupted, the count no longer represents accepted `Work`. Increment after `put` succeeds, or record a separate metric.

**Checking only `queue.isEmpty()` to exit.** Producers may still be active and send more items. Close the source first, then emit explicit stop signals.

**Sending too few `STOP` markers.** Some consumers will wait on `take` forever; send one per consumer.

**Sending `STOP` too early.** Consumers may exit while regular `Work` is still being generated.

**Using `null` as a poison pill.** The queue rejects `null`; use a dedicated marker object.

**Swallowing `InterruptedException` or ignoring `Future.get`.** Workers may fail silently or refuse to stop during shutdown.

**Assuming FIFO means global completion order.** Two consumers can finish `Work` out of order; if business logic requires strict ordering, use a single consumer or partition/reorder by key.

**Assuming queue capacity guarantees no data loss on crash.** An in-memory queue is not durable; use persistence/ack/retry/idempotency if required by the business.

**Adding more consumers and assuming throughput increases automatically.** Locks, CPU, DB connections, and downstream I/O may be the real bottleneck; benchmark to verify.

## 11. Exercise Self-Assessment Checklist

- [ ] Queue has a finite positive capacity, with no auxiliary queue growing unboundedly with input.
- [ ] Producers use `put` or check the `offer` result, distinguishing `attempted` from `accepted`.
- [ ] Consumers process `Work` before marking it `completed`.
- [ ] IDs are unique and the ID set uses a thread-safe structure.
- [ ] Producers finish before `STOP` is sent.
- [ ] One `STOP` per consumer and all `Future`s are awaited.
- [ ] When a worker fails or times out, `main` does not report false success.
- [ ] An interruption/shutdown path exists so the program does not hang indefinitely.
- [ ] Runs on Java 17+ and produces exact stdout in the success state.
- [ ] Can explain when a bounded queue actually creates backpressure and when the system still risks running out of memory.

## Official References

- [BlockingQueue — Java SE 21 API](https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/util/concurrent/BlockingQueue.html): `add`, `offer`, `put`, `remove`, `poll`, `take` forms and memory consistency.
- [ArrayBlockingQueue — Java SE 21 API](https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/util/concurrent/ArrayBlockingQueue.html): bounded FIFO and fairness.
- [ExecutorService — Java SE 21 API](https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/util/concurrent/ExecutorService.html): `Future` and lifecycle.
- [ThreadPoolExecutor — Java SE 21 API](https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/util/concurrent/ThreadPoolExecutor.html): worker/queue bounds and rejection policies.
- [Thread — Java SE 21 API](https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/lang/Thread.html): interruption.

**Summary:** A bounded producer–consumer requires a bounded queue, an explicit wait or rejection mechanism when full, a termination protocol covering every consumer, and verification of completed work. `BlockingQueue` handles inter-thread synchronization, but the designer remains responsible for pipeline-wide memory bounds, worker failures, and overload policies.

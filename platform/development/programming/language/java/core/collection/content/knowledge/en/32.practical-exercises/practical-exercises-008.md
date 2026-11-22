# Comprehensive Practice: Producer–Consumer with BlockingQueue in Java 17

## 1. Problem Statement and Requirements

Build a **producer–consumer** model in which producers create jobs and consumers process them on separate threads. If the two sides run at different speeds, data must be exchanged safely: producers wait when the buffer is full, consumers wait when no jobs are available yet, and the program has a clear termination mechanism.

Specific requirements of the practice exercise:

- **2 producers**, each generating **6 jobs** with distinct identifiers; **12 jobs** in total.
- **3 consumers** retrieving and processing jobs concurrently.
- The buffer holds at most **4 waiting jobs**, preventing an unbounded queue from growing when producers are faster than consumers.
- Wait for all producers to finish before sending stop signals; all consumers must be able to exit cleanly.
- Aggregate the total processed count and verify that the queue is empty upon completion.

The core focus is on `BlockingQueue`, `ArrayBlockingQueue`, `put`, `take`, *backpressure*, `ExecutorService`, `Future`, and the **poison pill** mechanism. There is no need to manually use `synchronized`, `wait()`, or `notify()` to implement the buffer.

## 2. Model and Principles

~~~text
Producer 1 ──┐
             ├── put() ──> [ ArrayBlockingQueue, capacity = 4 ] ── take() ──> Consumer 1
Producer 2 ──┘                                          ├─ take() ──> Consumer 2
                                                       └─ take() ──> Consumer 3
~~~

`BlockingQueue<E>` is a thread-safe queue interface for concurrent access by multiple threads. `ArrayBlockingQueue` implements a fixed-capacity FIFO queue:

- `put(e)` inserts a job into the queue. When full, the producer **waits** until space becomes available or the thread is interrupted.
- `take()` retrieves and removes a job from the queue. When empty, the consumer **waits** until an element is available or the thread is interrupted.
- The queue handles synchronization for its own operations internally. Callers do not need to manually lock around individual `put` and `take` calls.

When consumers process jobs slowly, all four waiting slots can fill up, causing producers to block at `put`. This is **backpressure**: the system caps the number of queued jobs and slows down the supply side when the processing side cannot keep up. A capacity of 4 counts only jobs *currently sitting in the queue*, excluding jobs that have already been taken out and are being processed.

A consumer **cannot treat an empty queue as a sign that producers are done**, because a producer might enqueue another job immediately afterward. The program uses a dedicated `STOP` object (poison pill) to signal termination. The required sequence is:

1. Producers enqueue all real jobs into the queue.
2. The main thread waits for each producer's `Future` to complete.
3. Main enqueues **one `STOP` signal per consumer** after all real jobs.
4. Each consumer exits upon reading `STOP`; main waits for the results of all three consumers.

Because the queue is FIFO, all real jobs enqueued before `STOP` will be retrieved before the stop signals. Three consumers require three signals so that none of them remains blocked at `take()` indefinitely.

## 3. Complete Implementation on Java 17+

Create the file **`BlockingQueueDemo.java`** with the following content. `Job` is an immutable `record` containing the producer ID and sequence number to identify each job. The thread pool uses **5 threads** so there is enough capacity to run both producers and all three consumers simultaneously; submitting consumers first ensures they are ready to receive work.

~~~java
import java.util.ArrayList;
import java.util.List;
import java.util.concurrent.ArrayBlockingQueue;
import java.util.concurrent.BlockingQueue;
import java.util.concurrent.ExecutionException;
import java.util.concurrent.ExecutorService;
import java.util.concurrent.Executors;
import java.util.concurrent.Future;

public class BlockingQueueDemo {
    private static final int PRODUCER_COUNT = 2;
    private static final int CONSUMER_COUNT = 3;
    private static final int JOBS_PER_PRODUCER = 6;
    private static final int QUEUE_CAPACITY = 4;

    private record Job(int producerId, int sequence) {}

    // Stop signal: only put into the queue after all producers have finished.
    private static final Job STOP = new Job(-1, -1);

    public static void main(String[] args)
            throws InterruptedException, ExecutionException {

        BlockingQueue<Job> queue = new ArrayBlockingQueue<>(QUEUE_CAPACITY);
        ExecutorService pool = Executors.newFixedThreadPool(
                PRODUCER_COUNT + CONSUMER_COUNT);

        List<Future<?>> producers = new ArrayList<>();
        List<Future<Integer>> consumers = new ArrayList<>();

        try {
            for (int i = 1; i <= CONSUMER_COUNT; i++) {
                final int consumerId = i;

                consumers.add(pool.submit(() -> {
                    int processed = 0;
                    while (true) {
                        Job job = queue.take();  // Wait if the queue is empty.

                        if (job == STOP) {
                            return processed;
                        }

                        System.out.printf(
                                "Consumer-%d xử lý P%d-#%d%n",
                                consumerId, job.producerId(), job.sequence());

                        // Simulate a relatively slow task.
                        Thread.sleep(50);
                        processed++;
                    }
                }));
            }

            for (int i = 1; i <= PRODUCER_COUNT; i++) {
                final int producerId = i;

                producers.add(pool.submit(() -> {
                    for (int n = 1; n <= JOBS_PER_PRODUCER; n++) {
                        queue.put(new Job(producerId, n)); // Wait if full.
                    }
                    return null;
                }));
            }

            // get() waits for the producer to finish and surfaces any exception thrown in the task.
            for (Future<?> producer : producers) {
                producer.get();
            }

            // Since there are three consumers, there must be exactly three stop signals.
            for (int i = 0; i < CONSUMER_COUNT; i++) {
                queue.put(STOP);
            }

            int processedTotal = 0;
            for (Future<Integer> consumer : consumers) {
                processedTotal += consumer.get();
            }

            int expected = PRODUCER_COUNT * JOBS_PER_PRODUCER;
            if (processedTotal != expected || !queue.isEmpty()) {
                throw new IllegalStateException(
                        "Sai số lượng: processed=" + processedTotal
                                + ", queueSize=" + queue.size());
            }

            System.out.printf(
                    "Hoàn tất: %d/%d công việc; hàng đợi còn %d phần tử%n",
                    processedTotal, expected, queue.size());
        } finally {
            // Wake up tasks that might be blocked in put/take/sleep
            // if a producer or consumer encounters an error or main is interrupted.
            // On a successful run, all Futures have already completed.
            pool.shutdownNow();
        }
    }
}
~~~

Compile and run in the directory containing the file:

~~~bash
javac BlockingQueueDemo.java
java BlockingQueueDemo
~~~

Example partial output:

~~~text
Consumer-2 xử lý P1-#1
Consumer-1 xử lý P2-#1
...
Hoàn tất: 12/12 công việc; hàng đợi còn 0 phần tử
~~~

The program prints **12 processing lines** and finally prints **`12/12`**, with **0** elements remaining in the queue under normal execution. The order of the processing lines (and which consumer receives each job) is **non-deterministic** and depends on thread scheduling. The initial sample lines are not a fixed required order; the final summary line is the invariant to verify.

## 4. Detailed Stage-by-Stage Explanation

**Consumers start up:** Consumers call `queue.take()` in a loop; if no work is available yet, the thread blocks without busy-polling `isEmpty()`. A consumer resumes execution only when an element arrives or the thread is interrupted.

**Producers enqueue work:** The two producers create exact ID pairs `(1,1)` through `(1,6)` and `(2,1)` through `(2,6)`. Whenever the queue holds four waiting jobs, `put()` blocks. Once a consumer removes an element, a slot is freed for a producer. `Thread.sleep(50)` merely simulates processing time to make backpressure easy to observe; the queue itself does not require sleeping to operate properly.

**Main determines when it is safe to stop:** `producer.get()` waits for a producer to finish or throws `ExecutionException` if the task failed. Because main waits for all producers before sending `STOP`, no real job from these producers can ever be enqueued after the stop signals.

**Consumers receive the stop signal:** Each `STOP` travels through the queue like a normal element, but when a consumer recognizes it, it **returns immediately** instead of processing it or incrementing its counter. The identity check `job == STOP` is intentional: all three signals reference the **exact same sentinel instance**, whereas producers only create new `Job` instances with positive IDs.

**Main verifies the result:** Once all three `consumer.get()` calls return, every consumer has stopped. Each time a consumer finishes processing a real job, it increments its own local counter; main sums those counters into `processedTotal`. Only after all tasks have completed does main check `queue.isEmpty()`; checking `size()` or `isEmpty()` while worker threads are still running does not reflect a stable final state.

**Resource cleanup:** `shutdownNow()` in the `finally` block sends interrupts to any tasks still running. `put`, `take`, and `sleep` are all interruptible operations. In a successful run of this demo, main has already waited for every `Future` to complete before shutting down the pool. For long-running production services, you should add a timed graceful shutdown procedure, failure logging, and monitoring for tasks that do not respond to interrupts.

**Memory visibility:** Actions in a thread prior to placing an element into a `BlockingQueue` *happen-before* actions subsequent to the access or removal of that element from the queue in another thread. However, the queue only guarantees thread safety for the queue operations themselves; if multiple threads mutate a shared mutable payload, proper synchronization or an immutable design is still required. Using `record Job` avoids shared mutable state in this exercise.

## 5. Related APIs and How to Choose

| Operation | API | Behavior when queue is full/empty |
| --- | --- | --- |
| Insert element and wait if necessary | `put(e)` | Waits when full; may throw `InterruptedException` |
| Try to insert immediately | `offer(e)` | Returns `false` if full |
| Insert with a maximum wait timeout | `offer(e, time, unit)` | Returns `false` on timeout; may also be interrupted |
| Retrieve element and wait if necessary | `take()` | Waits when empty; may throw `InterruptedException` |
| Try to retrieve immediately | `poll()` | Returns `null` if empty |
| Retrieve with a maximum wait timeout | `poll(time, unit)` | Returns `null` on timeout; may also be interrupted |

`add(e)` throws `IllegalStateException` if a bounded queue is full, while no-argument `remove()` throws `NoSuchElementException` if the queue is empty. They are not substitutes for `put`/`take` in models that require controlled waiting.

Example using timeouts (**illustrative snippet**; `queue` and `job` must be declared in the enclosing context):

~~~java
boolean accepted = queue.offer(
        job, 200, java.util.concurrent.TimeUnit.MILLISECONDS);
if (!accepted) {
    // Timed out waiting: report overload or perform bounded retries.
}

Job next = queue.poll(
        300, java.util.concurrent.TimeUnit.MILLISECONDS);
if (next == null) {
    // No job available yet; this does NOT mean all producers have finished.
}
~~~

Both timed overloads can throw `InterruptedException`. When handling an interrupt inside a task, you should typically either let the exception propagate or restore the interrupt status via `Thread.currentThread().interrupt()` and exit cleanly. **Never silently swallow an interrupt** and keep running indefinitely.

## 6. Common Real-World Pitfalls

| Pitfall | Why it fails | Best practice |
| --- | --- | --- |
| Consumer checks `queue.isEmpty()` and exits on its own | The queue may be temporarily empty while producers are still generating work | Distinguish "no work currently available" from "end of stream"; use an explicit shutdown protocol |
| Enqueuing `STOP` before all producers have finished | Consumers may terminate before processing all remaining data | Wait for all `producer.get()` calls to complete before sending stop signals |
| Sending only one `STOP` for three consumers | The remaining consumers will stay blocked at `take()` | Send one poison pill per consumer |
| Using a 2-thread pool and submitting both producers before any consumer | Both producers can block when the queue fills up, leaving no threads available to run consumers | Size the pool adequately or use separate thread pools for producers and consumers |
| Using an unbounded queue when work arrives rapidly | The backlog can grow without bound and exhaust memory | Choose a bounded capacity and an explicit backpressure policy |
| Checking `remainingCapacity()` before calling `put()` | The capacity can change due to another thread between the check and the insert | Call the atomic `put` or `offer` operation directly |
| Calling `shutdown()` and expecting `take()` to return automatically | `shutdown()` only stops accepting new tasks; it is not an end-of-stream signal for the queue | Use sentinel values or managed thread interruption |
| Ignoring `ExecutionException` or `InterruptedException` | Failures go unnoticed and tasks may hang indefinitely | Handle exceptions properly, shut down workers, and report clear status |
| Assuming `BlockingQueue` provides persistence, retries, or acknowledgments | In-memory queued data is lost if the JVM crashes or a worker fails | Design retry logic, persistence, processing acknowledgments, or use a message broker when needed |

With `LinkedBlockingQueue`, omitting the capacity argument defaults to `Integer.MAX_VALUE`, making it easy to overlook backlog control. `ArrayBlockingQueue` requires an explicit capacity, making backpressure visible immediately. The optional fairness parameter of `ArrayBlockingQueue` can affect the order in which waiting threads are served, but it does **not** guarantee deterministic console output ordering or improve throughput in all cases.

## 7. Verification and Extension Exercises

1. **Increase queue pressure:** Set `QUEUE_CAPACITY = 1` and change the processing delay to `Thread.sleep(300)`. Explain why the final total is still 12 jobs and why producers experience longer wait times.
2. **Scale up:** Test with 4 producers, 2 consumers, and 10 jobs per producer. The valid final summary is **`40/40`**. Remember to adjust the number of sentinels to 2 and ensure the thread pool has enough threads.
3. **Overload policy:** Replace `put()` with `offer(e, timeout, unit)` and handle timeouts explicitly. If a job is dropped, track the rejected count; do not report the processed total as if every generated job had been accepted.
4. **Duplicate detection:** Add `ConcurrentHashMap.newKeySet()` to record every processed job identifier pair; verify that `add` never returns `false` and that the final set contains all expected valid IDs. This check is stronger than comparing only the aggregate counter.
5. **Simulate producer failure:** Intentionally throw an exception inside one producer and observe how `Future.get()` throws `ExecutionException` while the `finally` block cancels waiting tasks. Propose a production-grade procedure for error reporting, retries, and service shutdown.

**Completion criteria:** The code compiles and runs on Java 17+, terminates normally with **12/12 jobs** processed and an empty queue, and you can clearly explain `put`/`take`, backpressure, when to send poison pills, why the number of poison pills matches the number of consumers, and how interrupts are handled. Keep in mind that this is an **in-process** thread coordination model: it does not natively provide durability, transactions, retries, or exactly-once processing guarantees across system failures.

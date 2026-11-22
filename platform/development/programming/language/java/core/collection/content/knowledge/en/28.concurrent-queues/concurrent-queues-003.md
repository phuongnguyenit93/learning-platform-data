# Bounded Queues and Producer Rate Throttling

In the producer–consumer model, producers create work and place it into a queue, while consumers take it out for processing. The two sides do not necessarily operate at the same speed.

If producers consistently generate work faster than it can be processed, pending work will grow. A bounded queue imposes a maximum capacity on the pending portion and forces the program to answer the question: **when space runs out, what must the producer do?**

That is the bridge between the data structure and **backpressure**: an overload state on the processing side is fed back to the submitting side, causing it to wait, reduce submission volume, or receive an explicit rejection result.

Terms used in this lesson:

- **Capacity:** the maximum number of elements that can reside in the queue buffer according to the class contract.
- **Pending work:** elements that have been admitted into the queue but not yet removed.
- **In-flight work:** elements that have left the queue but whose processing effects have not yet completed.
- **Successful admission:** the insertion or handoff operation succeeded; this is distinct from successful processing.
- **Overload policy:** how the application reacts when it cannot admit more work immediately.
- **Wait budget:** the time window or total limit that a request is allowed to spend on admission.

This lesson uses `BlockingQueue` and the implementations available in Java 17. The main goal is to understand the data contract, waiting conditions, and how signals are propagated back to producers, rather than merely picking a capacity number.

## 1. A Queue Is a Buffer, Not a Way to Make Consumers Faster

You can picture a processing flow as follows:

~~~text
Producer -> admission -> [queue with capacity C] -> consumer -> completion
~~~

A slot is freed when a consumer **removes an element**, not necessarily when processing of that element finishes.

If producers generate an average of `120` jobs per second while consumers complete around `100` jobs per second, the pending backlog tends to grow. A large buffer only delays the time until it fills up; it does not solve a sustained mismatch.

In a simplified model assuming steady rates and ignoring startup effects and fluctuations, an empty buffer of `200` slots can absorb roughly `10` seconds of a `20`-jobs-per-second surplus. This is a calculation for understanding the trend, not a guarantee of when a real system will fill up.

A bounded queue helps an application make overload decisions earlier, instead of letting unprocessed work accumulate until memory or latency exceeds tolerable limits.

### 1.1. Being Bounded Is Not Enough to Create Proper Backpressure

If the queue is full and the program ignores the failure result and keeps creating work as usual, the signal has not been propagated back to the production source.

Different reactions carry different meanings:

- Waiting for space slows down the submitting thread.
- Returning an error or rejection to the caller can cause the upstream layer to slow down.
- Dropping work is an intentional data-loss policy, if requirements permit it.
- Pushing work into an unbounded list merely moves where the backlog accumulates.

Therefore, capacity is one component; the caller's policy is what completes the throttling mechanism.

### 1.2. Not a Requests-Per-Second Rate Limiter

A queue with capacity `C` can accept a large burst when empty, then block or reject when full. It bounds the pending backlog; it does not automatically enforce a fixed rate such as "at most 50 requests per second."

If a time-based rule is needed, a separate rate-limiting mechanism is required. A queue can be combined with that mechanism, but the two tools answer two different questions.

## 2. Four Ways to Insert When Full

`BlockingQueue` provides four API groups so applications can choose how to react when an operation cannot be performed immediately. [Java 17: BlockingQueue](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/concurrent/BlockingQueue.html)

| Insertion method | If accepted | If the queue is full |
|---|---|---|
| `add(item)` | Returns `true`. | Throws `IllegalStateException` due to insufficient capacity. |
| `offer(item)` | Returns `true`. | Returns `false` immediately without waiting for space. |
| `put(item)` | Completes normally. | Waits until space becomes available or the thread is interrupted. |
| `offer(item, timeout, unit)` | Returns `true`. | Waits up to the bound; returns `false` if the timeout elapses before admission. |

These outcomes are part of the protocol, not details that can be ignored.

Illustrative example inside a method:

~~~java
java.util.concurrent.BlockingQueue<String> pending =
        new java.util.concurrent.ArrayBlockingQueue<>(128);

boolean accepted = pending.offer("task");
if (!accepted) {
    // The caller must recognize that this admission attempt was rejected.
}
~~~

The snippet above has not yet chosen a specific business policy. In real code, the rejection branch must be turned into meaningful behavior: notifying the caller, waiting within a budget, coalescing changes, or dropping the work with logging if permitted.

### 2.1. Non-Blocking offer to Check Capacity

`offer(item)` is useful when the producer is not allowed to wait for space. For example, an ingestion thread may need to return an overload result immediately to the upstream layer.

If you call `offer` and do not check the `boolean`, rejected work can vanish while the caller still believes it was accepted.

Do not use a busy loop like the following to avoid choosing a policy:

~~~java
while (!pending.offer("task")) {
    // Retry continuously.
}
~~~

This is an inappropriate pattern for waiting. It can consume CPU, contend with consumers, and has no stopping bound. If waiting is permitted, the blocking/timed APIs express that intent much more clearly.

### 2.2. put Provides Feedback Through Thread Wait Time

`put` does not reject just because the queue is full; it may have to wait. If consumers stop making progress and there is no cancellation, a wait may never end.

Throttling via `put` works when slowing down the producing thread itself is appropriate and the upstream layer actually feels that effect. If each request spawns a new thread only to block on `put`, the application can exhaust thread resources or hold too many waiting objects outside the queue.

### 2.3. Timed offer Bounds a Single Admission Attempt

Example:

~~~java
boolean accepted = pending.offer("task", 200,
        java.util.concurrent.TimeUnit.MILLISECONDS);
~~~

This illustrative snippet sits inside a method that handles or declares `InterruptedException`. A `false` result must be handled as a failed admission, not as work being processed implicitly in the queue.

The API timeout is not a real-time promise that the thread will definitely return after exactly `200` milliseconds on a wall clock. OS scheduling and contention can affect when the thread resumes. Do not write tests that require the actual elapsed milliseconds to equal an exact constant.

If retrying multiple times, giving `200` milliseconds per attempt can add up to a very long time. When a request has a total budget, track the remaining time instead of resetting the full timeout on every attempt. `System.nanoTime` is designed for measuring elapsed time in the JVM, not for wall-clock calendar time. [Java 17: System.nanoTime](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/lang/System.html#nanoTime())

### 2.4. add Fits When Fullness Is Treated as an Error at the Call Boundary

`add` can be useful when the code's contract treats fullness as an error that must be signaled via an exception. However, on an ingestion path where overload is an expected outcome, `offer` usually expresses the accepted/rejected branches more directly.

Changing `add` to `put` is not merely changing error-handling syntax: it changes thread-blocking behavior and cancellation/shutdown requirements.

## 3. Removal and What Completion Means

The removal group has a corresponding structure:

| Removal method | When an element is present | When empty |
|---|---|---|
| `remove()` (no args) | Retrieves and removes the head element. | Throws `NoSuchElementException`. |
| `poll()` | Retrieves and removes the head element. | Returns `null`. |
| `take()` | Retrieves and removes the head element. | Waits for an element or interruption. |
| `poll(timeout, unit)` | Retrieves an element if available within the wait time. | Returns `null` if the timeout elapses with nothing available. |

`BlockingQueue` does not accept `null` elements, so `null` can serve as the result meaning "no element retrieved." Do not use `null` as a stop sentinel message.

### 3.1. Removal Does Not Mean Processing Is Finished

Right after `take`, the element is no longer counted in `size`, yet the consumer may be writing a file, performing computation, or calling another system.

Therefore:

- An empty queue does not prove all work is finished.
- A successful `put`/`offer` does not prove a consumer has run.
- Even a direct handoff through `SynchronousQueue` does not prove the work has finished processing.

If the producer needs to know the outcome, use an appropriate completion-feedback mechanism such as a result object, a future, or a coordination signal. The queue only manages admission and retrieval according to its contract.

### 3.2. Capacity Usually Bounds Only Pending Work

Suppose there are `C` waiting slots and `W` consumers, each holding one in-flight job. The total work admitted but not yet completed can exceed `C`.

If each consumer drains batches using `drainTo` and holds a batch outside the queue, the work outside the queue can be even larger. To bound total active work, you must also account for items held outside the buffer.

## 4. Choosing a Queue Type by Contract

### 4.1. ArrayBlockingQueue: Fixed Array Capacity

Example:

~~~java
java.util.concurrent.BlockingQueue<String> queue =
        new java.util.concurrent.ArrayBlockingQueue<>(64);
~~~

`ArrayBlockingQueue` is a bounded buffer backed by an array, retrieved in FIFO order. Capacity cannot change after creation; `put` waits when full and `take` waits when empty. There is an optional fairness setting for waiting threads. [Java 17: ArrayBlockingQueue](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/concurrent/ArrayBlockingQueue.html)

FIFO ordering of elements does not mean multiple consumers will complete work in the same order. Two jobs retrieved in order can have different processing durations.

The fairness option governs the order in which access is granted to waiting threads; it does not guarantee OS scheduling or business completion times for individual threads. Evaluate the throughput trade-off under realistic load.

### 4.2. LinkedBlockingQueue: You Must Explicitly Choose a Bound

~~~java
java.util.concurrent.BlockingQueue<String> queue =
        new java.util.concurrent.LinkedBlockingQueue<>(64);
~~~

This class uses linked nodes and can be constructed with a bound. If the no-argument constructor is used, capacity is `Integer.MAX_VALUE`. That is a very large technical limit, usually not a useful memory or latency safeguard for an application. [Java 17: LinkedBlockingQueue](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/concurrent/LinkedBlockingQueue.html)

Do not infer from the word `Blocking` that it will necessarily slow producers down soon due to running out of space. Check the actual capacity and the API path being called.

Arrays and linked nodes have different allocation and coordination characteristics. Do not choose based solely on a claim that "this type is always faster"; measure under the same load and requirements.

### 4.3. LinkedBlockingDeque When Both Ends Are Needed

`LinkedBlockingDeque` provides APIs at both the head and tail, and also has a capacity constructor. Its default constructor uses `Integer.MAX_VALUE`. Choose it when the problem genuinely requires double-ended access; having extra APIs does not by itself improve load throttling. [Java 17: LinkedBlockingDeque](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/concurrent/LinkedBlockingDeque.html)

Specify clearly which side adds or removes at which end so work ordering is not accidentally altered.

### 4.4. SynchronousQueue: Handoff Without a Buffer

`SynchronousQueue` has no internal capacity, not even a single slot. Each insertion must meet a corresponding removal. A non-blocking `offer` fails if no receiver is ready to take; the blocking/timed forms can wait for the handoff. [Java 17: SynchronousQueue](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/concurrent/SynchronousQueue.html)

This is a direct coordination model. A `size` of `0` does not mean no threads are waiting to send or receive; zero capacity is a property of the model.

Do not create an `ArrayBlockingQueue` with capacity `0` to substitute for this model. Choose the class with the proper handoff contract.

## 5. remainingCapacity Is Not a Reservation

The following pattern has a race window:

~~~java
if (queue.remainingCapacity() > 0) {
    queue.add(item);
}
~~~

This is an illustrative snippet assuming the variables already exist. Another thread can take the slot between the two calls; `add` can still fail.

`ArrayBlockingQueue` explicitly documents that you cannot always predict whether an insertion will succeed from `remainingCapacity` alone because other threads may be inserting or removing elements. [Java 17: ArrayBlockingQueue.remainingCapacity](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/concurrent/ArrayBlockingQueue.html#remainingCapacity())

Use the operation that directly expresses your intent:

- Want to try immediately: `offer` and handle the result.
- Want to wait: `put` with a cancellation protocol.
- Want a bounded wait: timed `offer` with a budget.

`size` and `remainingCapacity` remain useful for monitoring. They do not replace the admission decision of the insertion operation itself.

## 6. Complete Verification Program

The file `BoundedQueueFlowDemo.java` uses Java 17 APIs, was compiled with `javac --release 17`, and ran on OpenJDK Zulu 24.0.2. This is not a claim that it was executed on JVM 17.

The waiting scenarios use latches to establish meaningful ordering. `Thread.sleep` is not used to guess whether a producer is blocked. Results are printed only at points explainable by queue state and coordination signals.

~~~java
import java.util.ArrayList;
import java.util.List;
import java.util.concurrent.ArrayBlockingQueue;
import java.util.concurrent.BlockingQueue;
import java.util.concurrent.CountDownLatch;
import java.util.concurrent.SynchronousQueue;
import java.util.concurrent.TimeUnit;
import java.util.concurrent.atomic.AtomicBoolean;
import java.util.concurrent.atomic.AtomicReference;

public class BoundedQueueFlowDemo {
    record Job(int value, boolean stop) {}

    static void await(CountDownLatch event) throws InterruptedException {
        if (!event.await(5, TimeUnit.SECONDS)) {
            throw new AssertionError("Event did not arrive");
        }
    }

    static void join(Thread thread, AtomicReference<Throwable> error)
            throws InterruptedException {
        thread.join(5000);
        if (thread.isAlive()) {
            thread.interrupt();
            throw new AssertionError("Thread did not terminate");
        }
        if (error.get() != null) {
            throw new AssertionError("Background failure", error.get());
        }
    }

    static Thread start(String name, Runnable action) {
        Thread thread = new Thread(action, name);
        thread.setDaemon(true);
        thread.start();
        return thread;
    }

    public static void main(String[] args) throws Exception {
        BlockingQueue<String> queue = new ArrayBlockingQueue<>(2);
        System.out.println("offer-A = " + queue.offer("A"));
        System.out.println("offer-B = " + queue.offer("B"));
        System.out.println("remaining-when-full = " + queue.remainingCapacity());
        System.out.println("offer-C-full = " + queue.offer("C"));
        try {
            queue.add("C");
            throw new AssertionError("add should have failed");
        } catch (IllegalStateException ex) {
            System.out.println("add-C-full = " + ex.getClass().getSimpleName());
        }
        System.out.println("timed-offer-C-full = "
                + queue.offer("C", 10, TimeUnit.MILLISECONDS));
        System.out.println("take-first = " + queue.take());
        System.out.println("offer-C-after-space = " + queue.offer("C"));
        System.out.println("remaining-content = " + new ArrayList<>(queue));
        queue.clear();
        System.out.println("poll-empty = " + queue.poll());
        try {
            queue.offer(null);
            throw new AssertionError("null should have failed");
        } catch (NullPointerException ex) {
            System.out.println("offer-null = " + ex.getClass().getSimpleName());
        }

        BlockingQueue<String> waiting = new ArrayBlockingQueue<>(1);
        waiting.put("first");
        CountDownLatch aboutToPut = new CountDownLatch(1);
        CountDownLatch putReturned = new CountDownLatch(1);
        AtomicReference<Throwable> putError = new AtomicReference<>();
        Thread sender = start("waiting-sender", () -> {
            try {
                aboutToPut.countDown();
                waiting.put("second");
                putReturned.countDown();
            } catch (Throwable ex) {
                putError.set(ex);
            }
        });
        await(aboutToPut);
        System.out.println("put-returned-before-space = "
                + (putReturned.getCount() == 0));
        System.out.println("released-item = " + waiting.take());
        await(putReturned);
        join(sender, putError);
        System.out.println("put-item-after-space = " + waiting.take());

        BlockingQueue<String> cancellable = new ArrayBlockingQueue<>(1);
        cancellable.put("held");
        CountDownLatch cancellationAttempt = new CountDownLatch(1);
        AtomicBoolean interrupted = new AtomicBoolean();
        AtomicBoolean restored = new AtomicBoolean();
        AtomicReference<Throwable> cancelError = new AtomicReference<>();
        Thread cancelledSender = start("cancelled-sender", () -> {
            try {
                cancellationAttempt.countDown();
                cancellable.put("not-admitted");
            } catch (InterruptedException ex) {
                interrupted.set(true);
                Thread.currentThread().interrupt();
                restored.set(Thread.currentThread().isInterrupted());
            } catch (Throwable ex) {
                cancelError.set(ex);
            }
        });
        await(cancellationAttempt);
        cancelledSender.interrupt();
        join(cancelledSender, cancelError);
        System.out.println("put-interrupted = " + interrupted.get());
        System.out.println("interrupt-restored = " + restored.get());
        System.out.println("queue-after-cancel = " + new ArrayList<>(cancellable));

        BlockingQueue<String> inFlight = new ArrayBlockingQueue<>(1);
        inFlight.put("work");
        CountDownLatch taken = new CountDownLatch(1);
        CountDownLatch finishAllowed = new CountDownLatch(1);
        AtomicBoolean completed = new AtomicBoolean();
        AtomicReference<Throwable> processingError = new AtomicReference<>();
        Thread processor = start("in-flight-processor", () -> {
            try {
                inFlight.take();
                taken.countDown();
                await(finishAllowed);
                completed.set(true);
            } catch (Throwable ex) {
                processingError.set(ex);
            }
        });
        try {
            await(taken);
            System.out.println("empty-while-processing = " + inFlight.isEmpty());
            System.out.println("completed-while-empty = " + completed.get());
        } finally {
            finishAllowed.countDown();
        }
        join(processor, processingError);
        System.out.println("completed-after-join = " + completed.get());

        BlockingQueue<Job> jobs = new ArrayBlockingQueue<>(2);
        List<Integer> processed = new ArrayList<>();
        AtomicReference<Throwable> jobError = new AtomicReference<>();
        Thread consumer = start("job-consumer", () -> {
            try {
                for (;;) {
                    Job job = jobs.take();
                    if (job.stop()) {
                        return;
                    }
                    processed.add(job.value());
                }
            } catch (Throwable ex) {
                jobError.set(ex);
            }
        });
        int admitted = 0;
        try {
            for (int value = 1; value <= 6; value++) {
                if (!jobs.offer(new Job(value, false), 5, TimeUnit.SECONDS)) {
                    throw new AssertionError("Admission timed out");
                }
                admitted++;
            }
            if (!jobs.offer(new Job(0, true), 5, TimeUnit.SECONDS)) {
                throw new AssertionError("Stop message timed out");
            }
        } catch (Throwable ex) {
            consumer.interrupt();
            throw ex;
        }
        join(consumer, jobError);
        System.out.println("pipeline-admitted = " + admitted);
        System.out.println("pipeline-processed = " + processed);
        System.out.println("pipeline-sum = "
                + processed.stream().mapToInt(Integer::intValue).sum());

        SynchronousQueue<String> handoff = new SynchronousQueue<>();
        System.out.println("handoff-offer-without-receiver = " + handoff.offer("early"));
        AtomicReference<String> received = new AtomicReference<>();
        AtomicReference<Throwable> handoffError = new AtomicReference<>();
        Thread receiver = start("handoff-receiver", () -> {
            try {
                received.set(handoff.take());
            } catch (Throwable ex) {
                handoffError.set(ex);
            }
        });
        if (!handoff.offer("direct", 5, TimeUnit.SECONDS)) {
            receiver.interrupt();
            throw new AssertionError("Handoff timed out");
        }
        join(receiver, handoffError);
        System.out.println("handoff-received = " + received.get());
        System.out.println("handoff-size = " + handoff.size());
    }
}
~~~

Compile and run in the directory containing the file:

~~~shell
javac --release 17 -encoding UTF-8 BoundedQueueFlowDemo.java
java BoundedQueueFlowDemo
~~~

Verified stdout:

~~~text
offer-A = true
offer-B = true
remaining-when-full = 0
offer-C-full = false
add-C-full = IllegalStateException
timed-offer-C-full = false
take-first = A
offer-C-after-space = true
remaining-content = [B, C]
poll-empty = null
offer-null = NullPointerException
put-returned-before-space = false
released-item = first
put-item-after-space = second
put-interrupted = true
interrupt-restored = true
queue-after-cancel = [held]
empty-while-processing = true
completed-while-empty = false
completed-after-join = true
pipeline-admitted = 6
pipeline-processed = [1, 2, 3, 4, 5, 6]
pipeline-sum = 21
handoff-offer-without-receiver = false
handoff-received = direct
handoff-size = 0
~~~

The five-second timeouts in the example are wait limits so the verification cannot hang indefinitely. They are not recommended as general business timeouts for every system.

## 7. Interpreting the Scenarios

### 7.1. Three Ways to Handle a Full Queue

A queue of capacity `2` accepts `A` and `B`:

~~~text
remaining-when-full = 0
offer-C-full = false
add-C-full = IllegalStateException
timed-offer-C-full = false
~~~

There is no consumer in this phase, so the timed offer cannot obtain space while waiting. The program only checks the `false` result, not that the actual elapsed milliseconds equaled `10`.

After `take` removes `A`, one slot is freed. `offer("C")` succeeds and the pending order is `[B, C]`.

### 7.2. put Cannot Complete Before Space Is Available

A buffer of capacity `1` already holds `first`. The sender signals that it is about to call `put("second")`. Nobody removes an element before the main thread checks the completion signal, so:

~~~text
put-returned-before-space = false
~~~

The `aboutToPut` latch marks that the thread reached the insertion attempt; it is not a tool for reading the thread's internal `WAITING` state. The usable conclusion is: while the only slot is still occupied by `first` and no consumer removes it, `put("second")` cannot complete successfully.

The main thread takes `first`, then waits for `put` to return and retrieves `second`. This is feedback through capacity: the producer only progresses past the insertion when the receiving side creates free space.

### 7.3. Cancelling a Wait

Another buffer already contains `held`, with no consumer. The sender thread is interrupted during or before the `put` wait and handles `InterruptedException`:

~~~text
put-interrupted = true
interrupt-restored = true
queue-after-cancel = [held]
~~~

The `not-admitted` item is not admitted in this scenario. The catch branch restores the interrupt flag and exits the task. It does not treat cancellation as a reason to keep retrying insertion forever.

If the method in use can declare `throws InterruptedException`, propagating the exception to the caller is also an appropriate option. If you are at a boundary that cannot propagate it, preserve and handle the cancellation signal according to the task's protocol. [Java 17: Thread.interrupt](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/lang/Thread.html#interrupt())

### 7.4. Empty Yet Not Completed

The consumer takes `work` out and then waits for a signal allowing it to finish. During that interval:

~~~text
empty-while-processing = true
completed-while-empty = false
~~~

Only after being allowed to proceed and the thread finishing does the completion flag become `true`. `isEmpty` observes pending items, not items already removed for processing.

### 7.5. A Pipeline with a Clear Termination Point

The `jobs` section has one producer and one consumer, with capacity `2`. The producer submits values `1..6` using timed offer and increments the admitted count only after the call succeeds.

The stop message is a `Job` with `stop=true`, submitted after all normal work. The consumer processes in FIFO order and stops when it takes that message. The main thread calls `join` before reading the result list:

~~~text
pipeline-admitted = 6
pipeline-processed = [1, 2, 3, 4, 5, 6]
pipeline-sum = 21
~~~

The `processed` list is modified only by the consumer during processing. The main thread reads it after the consumer terminates, so no two threads write to the same `ArrayList` concurrently.

The example checks both the admitted count and the completion results, rather than merely looking at an empty queue.

### 7.6. Handoff Without Buffer Space

`offer("early")` on `SynchronousQueue` without a receiver returns `false`. A subsequent timed offer meets a receiver that is taking or about to `take`, handing off `direct`:

~~~text
handoff-received = direct
handoff-size = 0
~~~

The queue still has no buffer. A successful handoff only confirms that the receiving side accepted the object per the contract, not that business processing has completed.

## 8. Overload Policy Is Part of the Requirements

| Policy | When appropriate | What the caller must know |
|---|---|---|
| Wait for space | The producing thread can be slowed down and a cancellation path exists. | May make no progress if the consuming side stalls. |
| Wait within a budget | Requests can tolerate only a bounded admission delay. | Exhausting the budget means not admitted; must report clearly. |
| Reject immediately | The upstream layer can slow down, retry, or report overload. | Must receive a rejection result, not a false success. |
| Intentional drop | Data loss is acceptable under a defined rule. | Must be clear which items are dropped and measure the drop count. |
| Coalesce superseding updates | Only the latest state or an aggregate matters. | Must prove coalescing does not lose required information. |
| Caller runs | The calling thread is allowed to do that work and accepts the processing time. | Execution context, latency, and error handling change. |

No single policy is right for every kind of work. A new temperature reading may supersede an old one per requirements; a payment command cannot be silently dropped for the same reason.

### 8.1. Retries Must Have Bounds and Conditions

When rejected, retrying immediately in a tight loop can amplify load. If retries are used, define a maximum attempt count or total budget, an appropriate backoff interval, and a cancellation condition. Continue only while the request is still meaningful.

In particular, never report that work was admitted and then silently move it into a retry mechanism with unbounded storage. At that point, the bound has been bypassed outside the main queue.

### 8.2. Propagate Signals Back to the Real Source

A blocked intermediate thread does not automatically stop an external source from emitting data. There may still be network buffers, lists in a reader, or tasks being created before waiting.

For backpressure to work across the entire path, you must specify how rejection/wait signals cross layers and which layer can pause accepting more input.

## 9. Choosing Capacity Based on Memory and Latency Budgets

Capacity is counted in **elements**, not bytes. One element may hold a large data array or reference an entire object graph.

When calculating the budget, consider:

- The number of elements currently in the queue.
- Jobs already removed and currently in flight.
- Batches drained from the queue.
- Objects created by producers before admission is granted.
- Requests waiting or held at other layers.
- The size and lifetime of the attached data.

Increasing capacity often helps absorb a short burst, but it can make jobs wait longer in the queue before being rejected or processed. A very large buffer can shift the problem from "reject early" to "wait a long time and still expire."

Selection should start from the requirements:

1. How long can a job tolerate waiting before starting?
2. How much memory does the system have for unprocessed work?
3. How long do load spikes typically last?
4. How far can consumers realistically scale?
5. During sustained overload, which policy is permitted?

Do not pick an arbitrary queue capacity number and treat it as proof of load tolerance. Measure throughput, queue depth, admission wait time, queue residency time, and processing time to tune based on real data.

## 10. Shutdown, Cancellation, and Consumer Failures

### 10.1. BlockingQueue Has No Common close

The `BlockingQueue` interface does not provide a built-in `close` or `shutdown` operation common to all implementations. Applications must define how they stop accepting and stop processing work using their own protocol. [Java 17: BlockingQueue lifecycle](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/concurrent/BlockingQueue.html)

In the example, a stop message is used because there are one clear producer and one clear consumer. Do not use a business value that could legitimately occur as a stop marker without a distinguishing type or field.

### 10.2. Multiple Producers/Consumers Need Stricter Rules

If using a stop message:

- Emit the stop message only after normal producers have finished or been prevented from submitting more.
- Define enough messages or a forwarding mechanism for the number of consumers that must stop.
- The stop message itself must be admitted; do not ignore an `offer` failure caused by a full queue.
- Wait for consumers to finish to confirm that items already removed also complete according to processing rules.
- Define what happens if a consumer fails mid-way and how unprocessed work will be reported or recovered.

One stop message retrieved by one consumer does not automatically wake up and stop all other consumers.

### 10.3. A Dead Consumer Can Leave Producers Waiting

A producer using `put` does not know that a consumer has stopped due to an error. If no one is taking items and the queue is full, it can remain waiting.

You need lifecycle monitoring, error feedback, and a way to cancel waiting when the processing path stops making progress. Timed offer provides checkpoints to re-evaluate liveness and budget; it does not fix the consumer by itself.

### 10.4. Do Not Wait While Holding Resources Needed by Consumers

If a producer holds a lock and waits for queue space while a consumer needs that exact lock to process or take the next step, neither side can make progress.

A similar situation occurs if all threads of a bounded pool are running blocked producers while consumer tasks are queued waiting to run on that same pool. A contract-compliant queue still cannot rescue a deadlocked execution dependency graph.

Design where producers/consumers run and the order of resource acquisition properly, rather than merely increasing capacity to delay the failure.

## 11. Publishing Objects Through a Queue

`BlockingQueue` provides visibility guarantees: actions prior to placing an object into a queue happen-before actions subsequent to the access or removal of that element from the queue in another thread. This supports handing off initialized objects. [Java 17: BlockingQueue memory consistency](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/concurrent/BlockingQueue.html)

It does not automatically deep-copy elements, nor does it prevent the producer from continuing to mutate the payload itself after insertion.

A clean pattern is to create an immutable message or transfer mutation ownership explicitly. The `Job` record in the example contains only `int` and `boolean`, so there is no mutable list or array inside for two sides to accidentally modify together.

If a message contains mutable objects, specify who is still allowed to mutate them and when. Queue thread-safety and payload data-safety are two separate contract layers.

## 12. Relation to ThreadPoolExecutor Queues

A fixed-size thread pool does not imply a usefully bounded queue. `Executors.newFixedThreadPool` uses an unbounded shared queue per its API specification, so the number of waiting tasks can still grow even though the number of worker threads is fixed. [Java 17: Executors.newFixedThreadPool](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/concurrent/Executors.html#newFixedThreadPool(int))

With a directly configured `ThreadPoolExecutor`, admission considers the thread count, whether the work queue can accept the task, and the maximum thread limit; when it cannot accept, the rejection policy decides. Passing a bounded `BlockingQueue` does not mean `execute` will automatically turn into `put` and block until space opens. [Java 17: ThreadPoolExecutor](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/concurrent/ThreadPoolExecutor.html)

`CallerRunsPolicy` is an example that slows down the submitter by running the rejected task directly on the calling thread when the executor is not shut down. However, once the executor is shut down, this policy discards the task; it also changes the calling thread's execution context and timing. Do not choose it while ignoring that contract. [Java 17: CallerRunsPolicy](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/concurrent/ThreadPoolExecutor.CallerRunsPolicy.html)

This illustrates a general principle: read the contract of the **admission layer**, not just the internal queue structure.

## 13. Common Pitfalls

| Common misconception | What is missing |
|---|---|
| "The queue is bounded, so I have bounded total memory." | Payloads, in-flight work, waiting producers, and off-queue buffers still hold data. |
| "`offer` was called, so the task was accepted." | You must check the `boolean`. |
| "`put` succeeded, so the work is done." | That only confirms admission; completion requires separate feedback. |
| "`remainingCapacity` shows space, so `add` will definitely succeed." | Observation and insertion happen at two different points in time. |
| "The queue is empty, so the system can shut down." | There may still be active producers and in-flight work. |
| "Default `LinkedBlockingQueue` will soon slow down producers." | Default capacity is `Integer.MAX_VALUE`, not an application-chosen budget. |
| "Retrying forever means no work is lost." | The budget may expire, progress may stop, or load may be held outside the queue. |
| "FIFO guarantees completion in exact order." | Multiple consumers can finish in a different order than they took items. |
| "Sending one poison object stops all consumers." | You need a protocol for the consumer count and when all producers have stopped. |

An in-memory queue is also not by itself a durable store or an exactly-once processing mechanism across process crashes. If durability or recovery guarantees are required, a component that owns those guarantees is needed.

## 14. Self-Check Exercises

### Exercise 1 — Accept or Reject?

A queue of capacity `2` is full. Compare `add`, `offer`, `put`, and timed `offer`.

**Answer:** `add` throws an exception for lack of space; `offer` returns `false`; `put` waits for space or interruption; timed `offer` waits up to the timeout and returns `false` if still not admitted.

### Exercise 2 — One Slot Remaining

Two producers both observe `remainingCapacity() == 1` and then both call `add`. Are both guaranteed to succeed?

**Answer:** No. Observation does not reserve a slot. One side can take the slot first; use the return/outcome of the appropriate admission operation instead.

### Exercise 3 — One Thousand Slots and Eight Consumers

A queue of capacity `1,000` has eight consumers, each holding one job. Can the number of admitted but unfinished jobs exceed `1,000`?

**Answer:** Yes. Capacity bounds only the items inside the queue. Work already removed for processing is counted separately; there may also be batches or data waiting in other layers.

### Exercise 4 — Empty Yet Still Working

The consumer has taken the last element and is writing the result. The producer sees `isEmpty` is `true`. Can everything be considered finished?

**Answer:** No. You need a completion signal or to wait for the corresponding consumer, while also knowing no producer will submit new work.

### Exercise 5 — Repeated Timed Offer

Each offer is allowed to wait one second, in an unbounded retry loop. Does this satisfy the requirement "each request waits at most one second total"?

**Answer:** No. Each attempt resets a new wait interval. You need a total budget and a decision when the budget is exhausted or cancelled.

### Exercise 6 — No Buffer

Why is `SynchronousQueue.size()` equal to `0` while `put` can still block?

**Answer:** This class hands off directly between sender and receiver without storing elements in a buffer. Waiting means waiting for a matching handoff, not waiting for an empty array slot.

### Exercise 7 — Stop Message

There are three consumers and multiple producers. One producer sends a stop message before the other producers finish. What are the issues?

**Answer:** One consumer can stop while work is still being added; the other consumers may keep waiting without a stop signal. You need a shared admission-stop point, a way to stop all consumers, and proper admission handling for the stop message itself.

### Exercise 8 — Does a Large Buffer Cure Sustained Overload?

Producers steadily create work faster than processing speed. Does increasing the queue from `100` to `10,000` make the system stable long-term?

**Answer:** Not by itself. It increases temporary burst absorption and pending backlog, but it does not eliminate the rate mismatch. You must throttle the source, scale processing capacity appropriately, or apply a permitted overload policy.

A bounded queue works best when capacity, admission behavior, completion signals, and cancellation paths are designed together. When space runs out, the producer's action must have a clear meaning to the source of work; that is the foundation of verifiable load throttling.

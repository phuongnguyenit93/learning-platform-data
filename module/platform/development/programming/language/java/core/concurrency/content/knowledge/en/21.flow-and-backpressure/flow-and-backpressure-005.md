# SubmissionPublisher and Executors Used in Java Flow

`SubmissionPublisher<T>` is a built-in implementation of `Flow.Publisher<T>` in `java.util.concurrent` since Java 9. It accepts items from a producer and **asynchronously delivers** signals to subscribers using an `Executor`. This is the key point: **the thread calling `submit()` is not necessarily the thread running `Subscriber.onNext()`**. The executor determines where signal delivery is executed; `Subscription.request(n)` and the per-subscriber buffer determine the rate at which items can be accepted.

This lesson focuses on **general Java concurrency**, independent of Spring. You will learn how to choose an executor, distinguish buffer from demand, recognize when `submit()` blocks, use `offer()` with a drop policy, manage errors, and close resources. The examples run on JDK 21+, though `Flow` and `SubmissionPublisher` have been available since Java 9.

## 1. From Flow to SubmissionPublisher

The four main interfaces of `java.util.concurrent.Flow`:

| Role | Interface | Responsibility |
|---|---|---|
| Data source | `Flow.Publisher<T>` | Registers subscribers; emits `onSubscribe`, `onNext`, `onError`, `onComplete` according to the protocol |
| Receiver | `Flow.Subscriber<T>` | Receives the subscription, processes items, receives completion/error signals |
| Control channel | `Flow.Subscription` | `request(n)` requests `n` more items, `cancel()` stops the subscription |
| Both receiver and emitter | `Flow.Processor<T,R>` | Acts as both a subscriber and a publisher, used when building processing pipelines |

`SubmissionPublisher<T>` implements `Flow.Publisher<T>` and `AutoCloseable`. It provides built-in logic for registration, buffering, asynchronous dispatch, and handling insufficient capacity. When calling `submit(item)`, the producer hands the item to the publisher; the executor is used to run the **signal delivery** to subscribers (such as the `onNext` callback), rather than automatically turning the producer's item-creation step into a task on the executor.

~~~text
                 PRODUCER THREAD
                      |
                submit(item)
                      |
             SubmissionPublisher
                      |
       +--------------+---------------+
       |                              |
    buffer S1                      buffer S2
       |                              |
S1's request(2)                S2's request(1)
       |                              |
       +----------- executor ---------+
                    |
         dispatch onNext(item)
             (async callbacks)
~~~

Each subscriber has its **own buffer**, which expands as needed up to the configured capacity. One subscriber may be slow or lack demand while another subscriber processes quickly. Without drops or exceptions, each active subscriber receives new items in the exact order they were submitted to that subscription; there is no guarantee of a total temporal ordering across different subscribers.

Other rules:

- `onSubscribe(subscription)` is the signal that establishes the subscription. The subscriber calls `subscription.request(n)` with **`n > 0`** to receive up to `n` items; `request(0)` or negative values are invalid requests and result in `onError`.
- `onNext` is only emitted when there is requested demand; unemitted items are held in the buffer if space remains.
- `onComplete` is normal completion; `onError` is failure completion; a subscription must not receive both terminal signals.
- `cancel()` from one subscriber is not `close()` for the entire publisher and does not automatically cancel other subscribers' subscriptions.
- `submit(null)` is invalid and throws `NullPointerException`.

## 2. Default Executor and Custom-Configured Executor

Important constructors:

~~~java
// Default executor + default capacity.
SubmissionPublisher<String> a = new SubmissionPublisher<>();

// Custom executor and maximum buffer capacity per subscriber.
SubmissionPublisher<String> b =
        new SubmissionPublisher<>(executor, maxBufferCapacity);

// Includes a callback to handle errors thrown by a subscriber's onNext.
SubmissionPublisher<String> c =
        new SubmissionPublisher<>(executor, maxBufferCapacity, onNextErrorHandler);
~~~

This is an **API illustration snippet**, not a standalone program; `executor`, `maxBufferCapacity`, and `onNextErrorHandler` are variables that must be declared beforehand.

**By default**, `new SubmissionPublisher<>()` uses `ForkJoinPool.commonPool()` if the pool supports a parallelism of at least 2; otherwise, the implementation creates a new thread for each signal-delivery task. The default buffer capacity is `Flow.defaultBufferSize()`. Therefore, you should not assume that every machine and every configuration is guaranteed to run callbacks on `commonPool`.

**Custom configuration** using `new SubmissionPublisher<>(executor, capacity)` has the following benefits:

- Control over the threads used for subscriber callbacks, thread names, number of platform workers, shutdown policy, and resources.
- Isolation of the data-delivery workload from unrelated tasks on `commonPool`.
- Choosing `newFixedThreadPool(n)` when you have a relatively predictable number of subscribers and suitable signal-delivery work.
- Using `Executors.newVirtualThreadPerTaskExecutor()` (Java 21+) when callbacks need to wait on I/O, while still limiting load, downstream resources, and the number of outstanding tasks. Virtual threads do not by themselves solve buffer saturation or slow subscribers.

The `executor` here receives the **publisher's internal dispatch tasks**; it should not be understood as "every item always creates a new thread." A single delivery task may process multiple items, with scheduling details depending on the implementation. `getExecutor()` returns the executor currently in use; `getMaxBufferCapacity()` returns the actual capacity. Capacity is **per subscriber**, and the implementation may round the requested capacity up to a power of 2 or cap it at a supported limit: check the returned value instead of assuming it always matches the literal passed to the constructor.

## 3. Complete Example: FixedThreadPool Delivering Signals

Create the file **`SubmissionExecutorDemo.java`**:

~~~java
import java.util.concurrent.CountDownLatch;
import java.util.concurrent.ExecutorService;
import java.util.concurrent.Executors;
import java.util.concurrent.Flow;
import java.util.concurrent.SubmissionPublisher;
import java.util.concurrent.TimeUnit;

public class SubmissionExecutorDemo {
    public static void main(String[] args) throws Exception {
        CountDownLatch completed = new CountDownLatch(1);

        try (ExecutorService delivery = Executors.newFixedThreadPool(2);
             SubmissionPublisher<String> publisher =
                     new SubmissionPublisher<>(delivery, 8)) {

            publisher.subscribe(new Flow.Subscriber<String>() {
                private Flow.Subscription subscription;

                @Override
                public void onSubscribe(Flow.Subscription s) {
                    subscription = s;
                    subscription.request(1);
                }

                @Override
                public void onNext(String item) {
                    System.out.println("received=" + item
                            + " virtual=" + Thread.currentThread().isVirtual());
                    subscription.request(1);
                }

                @Override
                public void onError(Throwable error) {
                    System.out.println("error=" + error.getClass().getSimpleName());
                    completed.countDown();
                }

                @Override
                public void onComplete() {
                    System.out.println("complete");
                    completed.countDown();
                }
            });

            publisher.submit("A");
            publisher.submit("B");
            publisher.close();

            if (!completed.await(5, TimeUnit.SECONDS)) {
                throw new IllegalStateException("Subscriber did not complete");
            }
        }
    }
}
~~~

Run with JDK 21+:

~~~bash
javac SubmissionExecutorDemo.java
java SubmissionExecutorDemo
~~~

Successful stdout:

~~~text
received=A virtual=false
received=B virtual=false
complete
~~~

Explanation:

1. `newFixedThreadPool(2)` creates up to two **platform worker threads**; `onNext` runs on an executor worker, so `Thread.currentThread().isVirtual()` is `false`.
2. `onSubscribe` saves the `Subscription` and requests one item. After each `onNext`, the subscriber requests one more item. This is the **one-item-at-a-time request** model.
3. `submit("A")` and `submit("B")` place the items into the publisher; callbacks are invoked **asynchronously**. The publisher preserves the order of the two items for the same subscription.
4. `close()` issues a normal completion request and stops accepting new items; it **does not mean the subscriber has finished processing the terminal callback before `close()` returns**. We use `CountDownLatch` to wait for `onComplete`/`onError`.
5. `try-with-resources` closes the publisher and the executor in reverse order upon exit. After closing the publisher, the executor still needs to be closed separately because **SubmissionPublisher does not own the authority to automatically shut down an executor provided by the caller**.
6. In the normal execution path, `onError` is not called. If an error occurs in a callback, an alternative path may print an error message or must handle it separately.

The example uses two workers to clearly show executor selection; **there is no guarantee that each subscriber is always pinned to a single thread**, nor is there a guarantee that the two items are processed on two different threads.

## 4. Backpressure Is Demand; a Buffer Is Not a License to Send Without Limit

In `Flow`, the subscriber regulates the number of items allowed to be emitted using `subscription.request(n)`. If it only requests 1 and has not finished processing it, the publisher can store subsequent items in the buffer. When the buffer reaches its limit, the producer faces the handling policy of `submit` or `offer`.

~~~text
subscriber: request(1)
producer:   A, B, C, D, E, ...
               |
publisher -> onNext(A)  (sufficient demand)
          -> buffer(B,C,... ) while capacity remains
          -> capacity full: submit waits or offer drops/times out
subscriber: onNext(A) done, request(1)
publisher -> onNext(B) ...
~~~

Points to distinguish:

- **Demand** (`request(n)`): the subscriber grants permission to emit up to `n` unfulfilled items.
- **Buffer capacity**: the number of items not yet sent to the subscriber that can be temporarily stored in the publisher; this is not the number of items the subscriber is currently permitted to receive.
- **Executor parallelism**: the resource for running callbacks. More workers can help multiple subscribers make progress, but it does not replace demand, does not increase buffer capacity, and does not force a subscriber to process faster.
- **Producer rate**: the rate at which items are created and submitted. If it is sustainably faster than the processing rate, the buffer will fill up, even if it starts very large.

For a single subscriber, `onNext` signals are delivered sequentially and do not run concurrently on the same subscription; a multi-threaded executor does not turn `onNext` calls on the **same subscriber** into unrestricted parallel processing. Independent subscribers can be dispatched in parallel if the executor has capacity.

For example: two subscribers receive the same 100 items; the fast subscriber keeps requesting continuously, while the slow subscriber stops requesting. The slow subscriber's buffer can fill up and cause `submit` from the producer to be held back, even though the fast subscriber still has demand. Therefore, you must define a policy for the **slowest subscriber** when the system cannot tolerate the producer waiting indefinitely.

## 5. `submit()` and `offer()` Have Different Contracts

| Method | When there is no space in a subscriber's buffer | Return value |
|---|---|---|
| `submit(item)` | May **wait uninterruptibly** until resources are available | Estimated **maximum lag** among subscribers; >=1 if there are subscribers, 0 otherwise |
| `offer(item, onDrop)` | Does not wait for capacity; may drop for overly slow subscribers, invoking handler | Negative: estimated drop count; non-negative: estimated maximum lag |
| `offer(item, timeout, unit, onDrop)` | May wait until timeout or interrupted; has a chance to invoke handler and retry once if it returns `true` | Same negative / non-negative convention |

`submit()` **does not wait for the subscriber to finish processing each item** if buffer space is available. However, when capacity is exhausted, this method can block. The Java 21 contract describes `submit`'s wait for resources as *uninterruptible*. Therefore, if you need a timeout in the item-publishing thread, consider the timed `offer` overload, upstream throttling, or an architecture that avoids unbounded wait loops.

`offer()` can drop an item **for one or more subscribers**; it does not mean an item is dropped everywhere. The `onDrop` callback receives the congested subscriber and the item; returning `true` only asks the publisher to **retry once** for that subscriber, with no promise that the delivery will succeed. Returning `false` accepts the drop. Do not perform complex logic, recursively call into the publisher, or block for long in the drop handler; other calls to the publisher may be held up while the handler runs.

Do not use the return value of `submit()` (lag) as an exact count of processed items. `estimateMaximumLag()` and `estimateMinimumDemand()` are **estimates intended for monitoring**, which may lag behind actual state and should not be used as a synchronization condition or proof that all items have been delivered.

## 6. Complete Example: Buffer of 1, `offer` Drop, Virtual Thread Executor

This example intentionally **does not request yet** when the subscriber is first registered. The buffer has a capacity of only 1: the first item is retained, and the second item has no space and is dropped. Afterward, the subscriber requests 1 to process the first item. The executor runs callbacks on a **virtual thread** (JDK 21+).

Create the file **`SubmissionOfferDemo.java`**:

~~~java
import java.util.concurrent.CountDownLatch;
import java.util.concurrent.ExecutorService;
import java.util.concurrent.Executors;
import java.util.concurrent.Flow;
import java.util.concurrent.SubmissionPublisher;
import java.util.concurrent.TimeUnit;
import java.util.concurrent.atomic.AtomicReference;

public class SubmissionOfferDemo {
    public static void main(String[] args) throws Exception {
        CountDownLatch subscribed = new CountDownLatch(1);
        CountDownLatch completed = new CountDownLatch(1);
        AtomicReference<Flow.Subscription> subscription = new AtomicReference<>();

        try (ExecutorService delivery =
                     Executors.newVirtualThreadPerTaskExecutor();
             SubmissionPublisher<Integer> publisher =
                     new SubmissionPublisher<>(delivery, 1)) {

            publisher.subscribe(new Flow.Subscriber<Integer>() {
                @Override
                public void onSubscribe(Flow.Subscription s) {
                    subscription.set(s);
                    subscribed.countDown();
                    // Intentionally not requesting yet, to demonstrate a full buffer.
                }

                @Override
                public void onNext(Integer item) {
                    System.out.println("received=" + item
                            + " virtual=" + Thread.currentThread().isVirtual());
                }

                @Override
                public void onError(Throwable error) {
                    System.out.println("error=" + error.getClass().getSimpleName());
                    completed.countDown();
                }

                @Override
                public void onComplete() {
                    System.out.println("complete");
                    completed.countDown();
                }
            });

            if (!subscribed.await(5, TimeUnit.SECONDS)) {
                throw new IllegalStateException("Missing onSubscribe");
            }

            int first = publisher.offer(10, (subscriber, item) -> false);
            int second = publisher.offer(20, (subscriber, item) -> false);
            System.out.println("first-accepted=" + (first >= 0));
            System.out.println("second-dropped=" + (second < 0));

            subscription.get().request(1);  // Now allow receiving item 10.
            publisher.close();

            if (!completed.await(5, TimeUnit.SECONDS)) {
                throw new IllegalStateException("Missing terminal signal");
            }
        }
    }
}
~~~

Run:

~~~bash
javac SubmissionOfferDemo.java
java SubmissionOfferDemo
~~~

Stdout:

~~~text
first-accepted=true
second-dropped=true
received=10 virtual=true
complete
~~~

Explanation of the actual mechanism:

1. `CountDownLatch subscribed` ensures the `onSubscribe` callback has executed **before** the two `offer` calls, avoiding reliance on thread-scheduling luck.
2. The subscriber has not called `request` yet, so item 10 is queued into the capacity-1 buffer. Item 20 runs out of space and `onDrop` returns `false`, so `second` is negative.
3. `request(1)` after the two `println` calls opens demand to emit item 10. Hence stdout has the order shown above.
4. `onNext` runs on a virtual thread from the provided executor and `isVirtual()` is `true`. **This does not guarantee turning every item into its own separate virtual thread**; the implementation may dispatch a batch of signals within the same task.
5. `publisher.close()` after the request asks for the completion signal; the latch holds the program until the subscriber receives `onComplete`. Item 20 was dropped, so it is not emitted.

In production code, a subscriber should request at the rate it can process and **not intentionally stop requesting forever**; here we deliberately keep demand at 0 to illustrate the difference between demand and buffer.

## 7. Choosing an Executor: Resources, Isolation, and Deadlock Risk

Executor choice directly affects the ability to drain buffers.

### 7.1. Default `ForkJoinPool.commonPool()`

Use when workloads are small and short, callbacks do not block for long, and you do not need separate executor lifecycle control. However, `commonPool` is a JVM-shared resource: other tasks can occupy workers and slow down delivery. When callbacks call heavy blocking APIs or long CPU-bound work, measure the impact on other tasks sharing the pool.

### 7.2. `Executors.newFixedThreadPool(n)`

Suitable for isolating delivery and setting a finite bound on **concurrent workers processing callbacks**. When you have a few subscribers mostly doing CPU work or short tasks, a fixed pool is usually predictable. When each `onNext` waits on long I/O, too few workers can create a bottleneck and cause buffers to fill up. Throughput also depends on the executor's queue, the number of subscribers, and callback duration.

### 7.3. `Executors.newVirtualThreadPerTaskExecutor()` (Java 21+)

Suitable if callbacks genuinely must use compatible blocking I/O APIs, you want to keep sequential coding style, and there may be many waiting delivery tasks. However, this executor does not self-limit the number of virtual threads created and does not replace DB connection limits, HTTP rate limits, or timeouts. Increasing the number of virtual threads will not make a subscriber without demand receive more items.

### 7.4. Avoiding Self-Inflicted Starvation/Deadlock

A classic mistake: the producer runs **on the same single-thread executor** used as the delivery executor. The producer calls `submit()` repeatedly, the buffer fills up, and it has to wait; however, the sole worker is occupied by the producer, so the `onNext` callback has no worker to make progress and cannot issue further `request` calls. The result can be a deadlock.

~~~text
single-thread executor:
  Worker #1 is running the producer:
    submit(A) -> submit(B) -> ... -> buffer full -> waits
  Delivery task onNext(...) is waiting to run on Worker #1 itself
  => Nobody drains the buffer or requests more demand
~~~

Reduce this risk by separating the producer from the delivery executor, ensuring callbacks can run independently, not blocking a single worker with `submit`, using `offer` with timeout/drop when appropriate, and having an upstream backpressure policy. There is no single thread-count configuration that fits all cases; test with realistic subscriber counts and rates.

**Note:** `newSingleThreadExecutor()` is not inherently wrong. It fits workflows that only need one thread for signal delivery and do not put it into a self-referential wait cycle. The problem is a dependency cycle between the producer, callbacks, and requests.

## 8. Lifecycle and Errors in Subscriber

- `publisher.close()`: stops accepting new items and emits `onComplete` once valid items have been processed according to the protocol; asynchronous notification may not be finished when `close()` returns.
- `publisher.closeExceptionally(cause)`: terminates abnormally and sends `onError(cause)`; the subscriber must stop and handle the error. `getClosedException()` helps query the cause of abnormal closure.
- `subscription.cancel()`: cancels one subscription; does not close the publisher or executor and is not a mechanism to signal success.
- `onNext` throws an exception: the corresponding subscription is canceled. The constructor overload with `BiConsumer<Subscriber,Throwable>` handles errors in `onNext` **before cancellation**, and is not a general exception handler for all callbacks.
- If `onSubscribe`, `onError`, or `onComplete` itself throws an exception, the dedicated `onNext` handler does not receive those errors.
- The executor may throw `RejectedExecutionException` (for example, if shut down too early), causing `submit`/`offer` to throw an exception and preventing some subscribers from receiving items; the system should have an appropriate abnormal-closure policy and logging/alerting.

Snippet configuring an `onNext` error handler:

~~~java
// Snippet: delivery is an Executor that was created and will be closed separately.
SubmissionPublisher<String> publisher = new SubmissionPublisher<>(
        delivery,
        32,
        (subscriber, error) -> {
            System.err.println("onNext failed: " + error.getMessage());
        }
);
~~~

This is a snippet, with no `main`. Do not use the handler to assume a canceled subscription can continue. Business errors should be reflected through an appropriate mechanism: error payloads, bounded upstream retries, or `closeExceptionally` for the entire stream.

If you provide a dedicated `ExecutorService` to the publisher, **close the publisher first and then close the executor**. Calling `close()` on the publisher does not automatically call `executor.shutdown()`. With the default `commonPool`, **do not shut down the shared common pool** just because your publisher is finished. When you need to wait for work to finish, use `CountDownLatch`/`CompletableFuture` with a timeout rather than relying on `Thread.sleep` and guessing.

## 9. Metrics, Capacity, and Data Design

The `getMaxBufferCapacity()` capacity is calculated **per subscriber**, not as a shared queue for the entire publisher. With N subscribers, each having a buffer of up to C items, the number of items held in buffers can grow on the order of N × C, not counting the objects themselves, the executor's queue/tasks, and other references. If items are large or subscribers are slow, total heap usage can be significant.

Suppose there are 40 subscribers and each buffer can hold 128 item **references**; there could be up to 5,120 reference slots across the buffers (excluding the actual objects and overhead). This is a sizing example, **not a specific memory measurement** nor a claim that every item is copied into N separate objects; multiple buffers may hold references to the same item.

Monitor these metrics:

- Number of subscribers, publish rate, `onNext` completion rate, and error-handling rate.
- `estimateMaximumLag()`, `estimateMinimumDemand()`: approximate indicators for tracking demand and lag status, **not to be used to prove synchronization**.
- Rate at which `offer` returns negative values, number of dropped subscribers, and failed retries.
- Executor pool queue/active workers, CPU, and callback duration (if using a fixed pool).
- With a virtual thread executor: number of live tasks, I/O wait time, memory, thread-local allocation, and connection limits.
- Network and downstream timeouts/cancellations, p95/p99 end-to-end latency, and how often the producer blocks on `submit`.

From there, choose capacity based on realistic peak bursts, item size, callback latency, and acceptable heap consumption. Setting a larger capacity can absorb bursts, but **cannot fix a sustained rate mismatch** between producer and subscriber.

## 10. Common Mistakes

| Mistake | Consequence | Fix |
|---|---|---|
| Thinking `submit` synchronously invokes `onNext` immediately | Races and unpredictable output ordering | Understand async dispatch, wait for terminal signals properly |
| Thinking the executor is only used to run the producer | Provisioning threads in the wrong place | The executor is used for delivery/callback tasks |
| Calling `request(0)` because you don't want items yet | Protocol error | Don't request until ready; when ready, request a positive number |
| Calling `request(Long.MAX_VALUE)` for a very slow subscriber | Can create buffer/resource pressure | Request according to processing capacity, monitor lag |
| Using `submit` when blocking is unacceptable | Producer can wait indefinitely | Use `offer` with timeout/drop and backpressure before the publisher |
| Treating a negative `offer` return as a failure for every subscriber | Misreading drop semantics | Drops may occur on only some subscriptions |
| Believing a multi-threaded executor runs a single subscriber's `onNext` in parallel | Misunderstanding the contract | Parallelism is across subscriptions, without violating single-subscription signal order |
| Producer and delivery sharing a single-thread executor, causing a wait cycle | Starvation/deadlock | Separate executors or design to avoid circular dependencies |
| Shutting down the executor before callbacks/terminal signals finish | `RejectedExecutionException`, missing signals | Close the publisher, wait for terminal signal, then close the executor |
| Treating `close()` as meaning `onComplete()` has already finished | Program exits early, flaky tests | Use a latch/future with timeout to wait for the callback |
| Treating lag estimates as exact numbers for synchronization | Wrong decisions due to stale metrics | Use only for monitoring |

## 11. Self-Check Questions

**Question 1:** Does `new SubmissionPublisher<>()` create its own new pool by default? **Not according to the API contract.** It uses the common pool if parallelism is at least 2; otherwise it has a fallback thread-creation mechanism.

**Question 2:** A producer calls `submit(A)` then `submit(B)`. Is it guaranteed that `onNext(A)` has finished before `submit(B)` returns? **No.** Publication and delivery are asynchronous; items may sit in the buffer.

**Question 3:** Two subscribers, one fast and one slow. Why can the producer be held back by `submit`? **Because the slow subscriber's buffer can fill up**, even if the fast subscriber still has demand.

**Question 4:** What does `offer(item, (s,i)->false)` returning `-1` mean? **One drop was reported in this call**; it does not mean the publisher is closed or that every subscriber encountered an error.

**Question 5:** Does using `newVirtualThreadPerTaskExecutor()` eliminate the need for `request(n)`? **No.** The executor only determines where callbacks run; it does not alter the demand protocol.

**Question 6:** Does closing `SubmissionPublisher` automatically close the `ExecutorService` passed in by the caller? **No.** The caller must manage the executor lifecycle separately.

### Exercises

1. Change `SubmissionExecutorDemo` from fixed pool 2 to fixed pool 1, and observe the thread name / `isVirtual()` flag. Explain why item ordering within a single subscriber is still preserved.
2. In `SubmissionOfferDemo`, call `request(2)` before offering. Explain why both items can be accepted (assuming the subscriber has not canceled and the executor is active); do not rely on sleep for synchronization.
3. Create two subscribers, one requesting items one by one and one intentionally withholding demand. Try `submit` with a small buffer, then try `offer` with a timeout to observe situations where the producer may have to wait and drops occur.
4. Add an `onNext` that intentionally throws `IllegalStateException` and configure the constructor handler. Observe cancellation and how the publisher closes, without using this failure as a success signal in production code.

## 12. Key Takeaways

- `SubmissionPublisher<T>` is the built-in asynchronous publisher for `Flow`; **the executor is used to deliver signals to subscribers**, while the producer decides when to create/submit items.
- By default it uses the common pool when parallelism is sufficient; you can supply a custom `Executor` and per-subscriber buffer capacity via constructors.
- **Backpressure** is based on `Subscription.request(n)`; buffers only absorb temporary rate differences.
- `submit()` can block when full; `offer()` can drop or time out with a handler and a one-time retry policy.
- The number of executor threads/virtual threads does not replace downstream limits, backpressure, timeouts, or handling slow subscribers.
- `close()` and terminal callbacks are separate events; manage the executor and wait for completion explicitly to avoid early exit or rejected tasks.

### Official References

- Java SE 21 `SubmissionPublisher` API: https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/util/concurrent/SubmissionPublisher.html
- Java SE 21 `Flow` API: https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/util/concurrent/Flow.html
- Java SE 21 `Flow.Subscription` API: https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/util/concurrent/Flow.Subscription.html
- Java SE 21 `Executor` API: https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/util/concurrent/Executor.html
- Java SE 21 `Executors` API: https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/util/concurrent/Executors.html

# Controlling Pending Tasks and Backpressure in the Java Executor Framework

## 1. The Problem: Producers Can Outpace Consumers

In Java's Executor Framework model, a **producer** calls `execute(...)` or `submit(...)` to submit work, while **worker threads** execute the tasks. When the incoming task rate exceeds processing capacity over a sufficiently long period, tasks accumulate in the queue.

For example: a system receives an average of 200 tasks/second, but the workers only complete an average of 120 tasks/second. While this rate persists, the queue grows by about 80 tasks/second (not counting rate fluctuations and other limits). After one minute, thousands of tasks can already be waiting. Increasing the queue capacity only delays when the limit is hit; **it does not increase actual processing capacity**.

Consequences:
- **Increased latency:** tasks are accepted but must wait a long time to run; request-side timeouts may occur before a worker even starts.
- **Increased memory usage:** each `Runnable`, `Callable`, closure, and the data it references remain retained while sitting in the queue; risk of `OutOfMemoryError`.
- **Stale work:** data or results are no longer valid when processed too late.
- **Cascading effects:** the producer keeps feeding more work, creating pressure on downstream systems, disk, network, or other services.

**Backpressure** is the mechanism for propagating the signal that "the consumer cannot keep up" back to the producer, so the producer **slows down, waits, gets rejected, or proactively sheds load**. It is a policy for controlling throughput and backlog; it is not synonymous with simply configuring a larger `maximumPoolSize`.

This lesson focuses on **Java Concurrency in general**, specifically `ThreadPoolExecutor`, `BlockingQueue`, `Semaphore`, and admission control mechanisms, independent of any framework.

## 2. Distinguishing the Quantities to Control

| Quantity | Meaning | Common Limiting Approach |
| --- | --- | --- |
| Running tasks | Work currently being executed by workers | Pool size, resource limits, or semaphore |
| Queued tasks | Work accepted by the executor but not yet started | `BlockingQueue` with bounded capacity |
| In-flight / outstanding tasks | Depends on the contract: usually includes accepted but not yet completed tasks, i.e., running + queued | Semaphore or permit-granting mechanism before enqueuing |
| Producers waiting to submit tasks | Calls blocked before admission; tasks have not entered the pool yet | `Semaphore.acquire()`, `tryAcquire(timeout, unit)`, bounded input queue |
| Rejected or discarded tasks | Work not accepted by the pool or dropped by a policy | Handler, metrics, timeout, fallback, and error contract |

Do not equate **queue length limit** with **total task limit**. For instance, a pool with 4 workers and a 100-element queue can hold roughly 104 running/waiting tasks at once under normal full load. While a concurrent system is active, the counts and transitions between running and queued fluctuate; the number "104" is a capacity model, not an atomic admission transaction for every call.

`getQueue().size()` and `getActiveCount()` are mainly for observation; using them to manually check "if size is small, then submit" is a **check-then-act race**: another producer can take the slot right between the two operations.

## 3. How Does ThreadPoolExecutor Decide to Queue?

With `ThreadPoolExecutor(corePoolSize, maximumPoolSize, keepAliveTime, unit, workQueue, threadFactory, handler)`, the general control flow of `execute(command)` is:

1. If the number of workers is less than `corePoolSize`, prefer creating a new worker to run the task.
2. If the core threshold has been reached and the executor is still accepting work, try to `offer` the task into `workQueue`.
3. If the queue does not accept it, try adding workers up to `maximumPoolSize`.
4. If it still cannot be accepted or the executor has shut down, delegate to `RejectedExecutionHandler`.

After enqueuing, there is also a recheck of the executor state to handle the case where shutdown occurs concurrently. Therefore, "the queue having space" is not a guarantee that the task will be accepted.

### Impact of Queue Type

| Queue Type | Behavior Under Load | Notes |
| --- | --- | --- |
| `ArrayBlockingQueue<>(capacity)` | Bounded queue; producers may encounter rejection when both workers and queue are full | Easy to set an explicit bound; does not block the caller inside `execute` |
| `LinkedBlockingQueue<>(capacity)` | Also bounded when capacity is passed | Has different node management and memory overhead compared to `ArrayBlockingQueue` |
| `LinkedBlockingQueue<>()` | Very large default bound (`Integer.MAX_VALUE`); tasks usually accumulate before hitting the limit | `Executors.newFixedThreadPool(n)` uses this model; `maximumPoolSize` barely helps grow the pool while the queue keeps accepting |
| `SynchronousQueue<>` | Stores no waiting tasks; must hand off directly to a worker | Easily creates workers up to maximum; rejects when handoff or worker creation is not possible |
| `PriorityBlockingQueue<>`, `DelayQueue<>` | Typically have no bounded capacity set by the application via standard constructors | Priority or delay does not replace task count control |

**A very common misconception:** `ThreadPoolExecutor.execute` uses a non-blocking admission path rather than waiting indefinitely for space in the queue. Using `ArrayBlockingQueue<>(100)` **does not automatically turn an `execute` call into `put()`**; under overload it will try to expand the pool and then invoke the rejection handler. To wait in a controlled manner, the producer must implement its own admission control, or accept a handler such as `CallerRunsPolicy`.

Do not call `executor.getQueue().put(task)` directly to "force" work into the pool: this bypasses the state checks and worker-creation rules of `execute`, and can leave tasks stranded when the pool closes or no worker picks them up.

## 4. Main Backpressure Strategies

### 4.1. Bounded Queue + AbortPolicy: Observable Rejection

`ArrayBlockingQueue` or `LinkedBlockingQueue` with a bounded capacity caps pending work. `AbortPolicy` (the default for `ThreadPoolExecutor`) throws `RejectedExecutionException` when the executor cannot accept a task.

```java
// Configuration fragment: the executor must be shut down when no longer needed.
ThreadPoolExecutor executor = new ThreadPoolExecutor(
        2, 4,
        30, TimeUnit.SECONDS,
        new ArrayBlockingQueue<>(100),
        new ThreadPoolExecutor.AbortPolicy());
```

Once 2 workers are busy, new tasks normally go into the queue first. When the queue is full, the pool can grow up to a maximum of 4 workers. After that, new tasks are rejected. For a newly created pool, this order explains why setting `maximumPoolSize=4` **does not mean** the pool spawns 4 workers before using the queue.

This is suitable when the producer or caller layer can react to errors: return "busy", retry with a limit/backoff, route to durable storage, or record the rejected task. Do not catch the exception and silently ignore it, as that defeats the benefit of this policy.

### 4.2. Bounded Queue + CallerRunsPolicy: Producer Bears the Cost

When overloaded **and the executor is still running**, `CallerRunsPolicy` executes `Runnable.run()` directly on the **thread calling `execute`**. The producer must wait for that task to finish before submitting the next one, so the input rate is naturally throttled.

This is suitable if the caller is allowed to execute tasks and can tolerate blocking. Be cautious if the caller is an event loop, UI thread, a worker holding a lock, or a thread with strict response-latency requirements: it can be blocked for a long time or cause a deadlock due to mutual dependencies.

Important limitations:
- When the executor **has shut down**, `CallerRunsPolicy` discards the task; it does not run a fallback.
- The task runs on the calling thread, so `ThreadLocal`, context, thread name, and error handling may differ from a worker thread.
- If a directly executed task throws an unchecked exception, the exception propagation path of `execute` may differ from running on a worker; do not assume every exception is captured by the executor.
- When the producer is a primary thread that must also serve high-priority work, running tasks itself can cause cascading delays.

### 4.3. Semaphore: Limiting Outstanding Tasks Before Submission

A `Semaphore` holds a finite number of **permits**. The producer must acquire a permit **before submitting** a task; the permit is released when the task completes. If there are 20 permits, the design targets at most 20 accepted but not yet completed tasks (including both running and queued tasks). Permits do not increase the number of workers; they limit how much work the application allows to be admitted.

Three common approaches:

- `acquire()`: waits until a permit is available or the thread is interrupted; provides blocking backpressure.
- `tryAcquire()`: returns `false` immediately if no permit is available; provides fast-fail / admission rejection.
- `tryAcquire(timeout, unit)`: waits up to a specified duration, then returns `false`; often useful when there is a deadline.

Important rule: **acquire permit -> submit task -> release permit when the task finishes; if submission is rejected, release the permit immediately**. Put `release()` in a `finally` block inside the execution wrapper to avoid leaking permits if the task throws an exception. With `AbortPolicy`, handle `RejectedExecutionException` from `execute` to return the permit before reporting the error to the producer.

```java
// Fragment: uses ThreadPoolExecutor with AbortPolicy;
// pass permits and work from the configuration site.
static boolean trySubmit(ThreadPoolExecutor executor,
                         Semaphore permits,
                         Runnable work) {
    if (!permits.tryAcquire()) {
        return false; // Not submitted to the executor.
    }

    try {
        executor.execute(() -> {
            try {
                work.run();
            } finally {
                permits.release();
            }
        });
        return true;
    } catch (RejectedExecutionException rejected) {
        permits.release(); // Task was not accepted by the executor.
        return false;
    }
}
```

In this example, `false` means the system **did not accept the task**: either no permit was available, or the executor rejected it. When you need to report the exact reason, return a more specific result type instead of just a boolean.

**Distinguish the two bounds:** the number of permits should be chosen based on the system's capacity to accept tasks, not necessarily equal to `maximumPoolSize + queueCapacity`. Even when the two bounds are equal, a semaphore does not 100% guarantee that `execute` cannot reject: shutdown, producers bypassing the same semaphore, or permit handoff right as a worker finishes can still race. You still need a handler and permit release on rejection.

### 4.4. Limiting Total Load Before Creating Executor Tasks

You can place the `Semaphore` at the start of the pipeline rather than right in front of the pool. The producer receives the out-of-capacity signal **before allocating a large number of objects/tasks**, reading data, or making auxiliary calls. If input data must be persisted durably, apply admission at the appropriate boundary and design a place to hold unprocessed work. Do not spawn unbounded producer threads only to have them block on `acquire()`: that simply shifts the buildup from the queue to a set of waiting threads.

### 4.5. Intentional Load Shedding

If work does not strictly have to be executed in full, the producer can:
- Drop non-essential samples/events and increment a dropped metric.
- Coalesce updates with the same key, keeping only the latest state.
- Apply deadlines: do not accept tasks that have already lost their value before starting.
- Prioritize essential work; isolate pools/capacities across workload types to reduce mutual interference.

`DiscardPolicy` silently drops the new task, while `DiscardOldestPolicy` drops the head of the queue and retries submitting the new task. Neither policy is reliable backpressure for work that requires a response: `submit()` can return a `Future` that never completes when a task is dropped. `DiscardOldestPolicy` also risks repeated retries with non-storing queues such as `SynchronousQueue`. It is usually better to design "replacing old tasks" and `Future` response/cancellation explicitly.

## 5. Standalone Java 17 Example: Two Ways to Control Load

The program demonstrates:

1. **`CallerRunsPolicy`** with 1 worker and a 1-slot queue: A is running, B is waiting, and C will have to run on `main`.
2. **`Semaphore(2)` + `AbortPolicy`**: accepts at most 2 outstanding tasks. While A is running and B has been accepted, task C is blocked at the admission step (`tryAcquire() == false`) without entering the executor.

`CountDownLatch` keeps A running to create a **controlled** overload state, avoiding dependence on `Thread.sleep` and machine speed. Save the file as `BackpressureDemo.java`:

```java
import java.util.ArrayList;
import java.util.Collections;
import java.util.List;
import java.util.concurrent.ArrayBlockingQueue;
import java.util.concurrent.CountDownLatch;
import java.util.concurrent.RejectedExecutionException;
import java.util.concurrent.Semaphore;
import java.util.concurrent.ThreadPoolExecutor;
import java.util.concurrent.TimeUnit;

public class BackpressureDemo {
    public static void main(String[] args) throws Exception {
        callerRunsExample();
        semaphoreExample();
    }

    private static void callerRunsExample() throws Exception {
        List<String> events =
                Collections.synchronizedList(new ArrayList<>());
        CountDownLatch started = new CountDownLatch(1);
        CountDownLatch releaseA = new CountDownLatch(1);

        ThreadPoolExecutor pool = new ThreadPoolExecutor(
                1, 1, 0L, TimeUnit.MILLISECONDS,
                new ArrayBlockingQueue<>(1),
                new ThreadPoolExecutor.CallerRunsPolicy());

        try {
            pool.execute(() -> {
                events.add("A running");
                started.countDown();
                awaitUninterruptiblyForDemo(releaseA);
                events.add("A done");
            });

            started.await(); // A occupies the worker.
            pool.execute(() -> events.add("B done")); // B is in the queue.
            events.add("before C");
            pool.execute(() ->
                    events.add("C on " + Thread.currentThread().getName()));
            events.add("after C");
        } finally {
            releaseA.countDown();
            pool.shutdown();
        }

        if (!pool.awaitTermination(5, TimeUnit.SECONDS)) {
            throw new AssertionError("CallerRuns pool did not terminate");
        }
        System.out.println("CallerRuns: " + String.join(" | ", events));
    }

    private static void semaphoreExample() throws Exception {
        List<String> events =
                Collections.synchronizedList(new ArrayList<>());
        CountDownLatch started = new CountDownLatch(1);
        CountDownLatch releaseA = new CountDownLatch(1);
        Semaphore permits = new Semaphore(2);

        ThreadPoolExecutor pool = new ThreadPoolExecutor(
                1, 1, 0L, TimeUnit.MILLISECONDS,
                new ArrayBlockingQueue<>(1),
                new ThreadPoolExecutor.AbortPolicy());

        try {
            boolean a = trySubmit(pool, permits, () -> {
                events.add("A running");
                started.countDown();
                awaitUninterruptiblyForDemo(releaseA);
                events.add("A done");
            });
            started.await(); // A is running, holding the first permit.

            boolean b = trySubmit(
                    pool, permits, () -> events.add("B done"));
            boolean c = trySubmit(
                    pool, permits, () -> events.add("C done"));

            events.add("accepted=" + a + "," + b + "," + c);
        } finally {
            releaseA.countDown();
            pool.shutdown();
        }

        if (!pool.awaitTermination(5, TimeUnit.SECONDS)) {
            throw new AssertionError("Semaphore pool did not terminate");
        }
        System.out.println("Semaphore: " + String.join(" | ", events));
    }

    // Used with AbortPolicy: rejection at execute() means the task was not accepted.
    private static boolean trySubmit(ThreadPoolExecutor pool,
                                     Semaphore permits,
                                     Runnable work) {
        if (!permits.tryAcquire()) {
            return false;
        }
        try {
            pool.execute(() -> {
                try {
                    work.run();
                } finally {
                    permits.release();
                }
            });
            return true;
        } catch (RejectedExecutionException rejected) {
            permits.release();
            return false;
        }
    }

    // For demo only: holds A's state until main releases the latch.
    private static void awaitUninterruptiblyForDemo(CountDownLatch latch) {
        boolean interrupted = false;
        while (true) {
            try {
                latch.await();
                break;
            } catch (InterruptedException e) {
                interrupted = true;
            }
        }
        if (interrupted) {
            Thread.currentThread().interrupt();
        }
    }
}
```

Compile and run with Java 17+:

```bash
javac BackpressureDemo.java
java BackpressureDemo
```

Stdout:

```text
CallerRuns: A running | before C | C on main | after C | A done | B done
Semaphore: A running | accepted=true,true,false | A done | B done
```

In the first branch, `execute(C)` cannot fit into the queue, and `CallerRunsPolicy` runs C on `main` before the submission call returns. In the second branch, C has no permit, so `trySubmit` returns `false` without putting C into the queue. These two branches demonstrate two different places where backpressure happens: **inside the handler after saturation** and **before submitting the task to the pool**.

The latch-waiting helper in the demo intentionally restores the interrupt flag after finishing the wait to demonstrate event ordering. Production code should normally have proper interrupt/shutdown handling and should not copy this uninterruptible wait mechanism for a real worker.

## 6. Blocking Admission with Timeout and Interruption

For tasks that need to wait for a slot for a bounded time, you can replace `permits.tryAcquire()` with:

```java
// Fragment inside a method that declares throws InterruptedException:
boolean admitted = permits.tryAcquire(200, TimeUnit.MILLISECONDS);
if (!admitted) {
    // Admission wait timed out: report busy / deadline exceeded.
    return;
}
try {
    executor.execute(() -> {
        try {
            work.run();
        } finally {
            permits.release();
        }
    });
} catch (RejectedExecutionException rejected) {
    permits.release();
    throw rejected;
}
```

This snippet assumes `executor` is configured with `AbortPolicy`, and `permits` and `work` are initialized. If interrupted **while waiting for a permit**, `tryAcquire(timeout, unit)` throws `InterruptedException` and **no permit needs to be returned**. The caller should usually propagate the interrupt or handle it according to the application's cancellation contract; do not silently swallow the interrupt and wait forever.

A producer can set an overall deadline and subtract elapsed time so that admission wait time + execution time does not exceed the budget. If the producer times out after the task has already been accepted by the executor, a separate cancellation/state-reconciliation strategy is needed: a producer-side timeout **does not automatically stop the worker**.

`Semaphore` does not guarantee fairness by default. `new Semaphore(n, true)` prioritizes waiting order according to the semaphore's fairness mechanism, trading off potentially different overhead/throughput; non-timed `tryAcquire()` calls can still barge ahead and acquire a permit even when threads are waiting on a fair semaphore. If strict fair queuing is truly required, choose the appropriate API and test its semantics; fairness does not replace a wait timeout.

## 7. Designing Leak-Free Permits

The `trySubmit` pattern above is suitable for teaching the **admit -> run -> complete** path when using `AbortPolicy` and `execute`. In real systems, you need to consider the full task lifecycle:

- **Exceptions from the task:** `finally` in the wrapper still releases the permit when `Runnable.run()` throws.
- **Rejection before admission:** the permit must be released on the submitting thread, otherwise capacity shrinks permanently.
- **`shutdown()`:** rejects new tasks, while already accepted tasks continue running through the controlled shutdown sequence; permits are released when they finish.
- **`shutdownNow()`:** can return a list of tasks **not yet started** in the queue. Their wrappers have not run, so the wrapper's `finally` **is never called** and permits remain held. You must reconcile the drained tasks and release permits / cancel state once, while also coordinating interrupts for running tasks.
- **`remove(runnable)`, `purge()`, Future cancellation / custom cancellation paths:** if a task never runs, a mechanism that only releases the permit when the task runs will leak permits. If `submit` is used, the executor may wrap the task in a `FutureTask`; ownership and cleanup must be designed consistently.
- **Switching to CallerRuns:** if the handler is changed to `CallerRunsPolicy`, the task may run directly on the calling thread; throwing `RejectedExecutionException` from **inside the task** could cause the producer's `catch` block to mistake it for an executor rejection and release the permit **twice**. Do not mechanically reuse an `AbortPolicy` wrapper when changing handlers.

To productionize a multi-path lifecycle, use a state token/handle with **exactly-once** permit release (for example, `AtomicBoolean.compareAndSet(false, true)`), task registration before enqueuing, and a cleanup path for canceled queued tasks. If you cannot prove all termination paths, do not claim the semaphore covers every case.

## 8. How Does Backpressure Differ from Rate Limiting?

**Rate limiting** caps the number of incoming requests or tasks over a time window (for example, a 100/s token bucket). **Concurrency limiting** caps the amount of simultaneous work. **Queue bounding** caps the number of waiting tasks. **Backpressure** is the mechanism for reacting when downstream resources cannot keep up: blocking, signaling to slow down, timing out, or rejecting.

A system may need all three kinds of limits: a rate limit to curb arrival spikes, a semaphore to prevent too many in-flight tasks, and a bounded queue to prevent memory buildup. Having a rate limit still allows a backlog to form if tasks unexpectedly slow down. Having a bounded queue while callers retry without limit can still push pressure back onto external systems.

By Little's Law in **steady state**, the average relationship `L = λ × W` connects the number of items in the system (`L`), throughput (`λ`), and time spent in the system (`W`). For example, a throughput of 100 tasks/second and an average residence time of 0.5 seconds corresponds to roughly 50 tasks in the system on average. This is an **observable relationship in steady state**, not a formula for setting absolute capacity under bursts, timeouts, constrained resources, or prolonged overload.

For CPU-bound workloads, increasing workers beyond available cores can increase CPU contention and context switching. For I/O-bound workloads, the number of tasks waiting on I/O can be higher, but you must account for connection pools, memory, external limits, and deadlines. Queue capacity depends on the burst size you want to absorb and your latency budget, and should not be chosen arbitrarily large.

## 9. Observability, Testing, and Operations

### Metrics to Monitor

- **Admission:** counts of submitted, accepted, rejected, permit-timeout, and dropped tasks; distinguish rejections caused by shutdown vs. saturation where possible.
- **Queue depth:** `getQueue().size()`, queue capacity, growth trend, and task wait time before starting.
- **Pool:** `getActiveCount()`, `getPoolSize()`, `getCompletedTaskCount()`, processing time, and actual saturation.
- **Producers:** time blocked on semaphore / `CallerRunsPolicy`, number of waiting producers, caller-side timeouts.
- **End-to-end:** p95/p99 latency, errors, canceled requests, task age at execution time, and remaining backlog in the pipeline.

`ThreadPoolExecutor` getters are instantaneous or approximate under concurrent execution—useful for monitoring, but not for read-then-submit admission checks. Every drop/rejection branch needs a clear metric or signal; measuring only queue size can miss dropped work.

### Test Scenarios to Include

1. One busy worker + full queue: verify the pool triggers the expected handler.
2. Fast producer submitting over a sustained period: verify queue depth and outstanding task count do not grow beyond target; latency remains acceptable.
3. Task throws an exception: the permit must be returned.
4. Permit wait interrupted / timed out: task is not submitted, no spurious release.
5. `shutdown` and `shutdownNow`: verify where unstarted tasks are returned, which tasks are canceled, and which permits and `Future`s need cleanup.
6. Multiple competing producers: test admission races, bounded retries, and ensure no unintended duplicates or lost tasks outside the contract.
7. Tasks depending on results from other tasks in the same pool: test for deadlocks, especially with `CallerRunsPolicy` or producers holding locks.

You can use `CountDownLatch` as in the example to deterministically create a full-queue state; `Thread.sleep` alone does not guarantee which task is running or waiting. Realistic load tests need bursts, ramping rates, variable service times, and slow downstream dependencies.

## 10. Common Design Mistakes

| Mistake | Consequence | Fix |
| --- | --- | --- |
| Setting a huge `LinkedBlockingQueue` just to avoid rejection | Backlog, latency, and memory grow silently | Set capacity based on latency budget and total load limits |
| Assuming a bounded queue automatically blocks `execute` | When full, the pool may throw `RejectedExecutionException` or invoke the handler | Put an explicit backpressure mechanism in place: abort / CallerRuns / semaphore |
| Only checking `queue.size() < limit` before submitting | Check-then-act race under multiple producers | Use `Semaphore.tryAcquire`/`acquire` or an atomic admission mechanism |
| Using `CallerRunsPolicy` on a thread that must not block | Calling thread gets hijacked, increasing latency or causing deadlock | Choose fast-fail, timeout, or move admission to an appropriate boundary |
| Swallowing `RejectedExecutionException` | Work is lost with no signal | Record metrics and respond / retry with bounds / persist durably |
| Using `DiscardPolicy` with `submit` and waiting on `Future.get()` | The `Future` may never complete | Use an explicit failure policy or manage `Future` cancellation |
| Putting `release()` only inside the task, ignoring rejected/canceled queued tasks | Permit leak; the system stops accepting work after a while | Ensure exactly-once cleanup on every termination path |
| Retrying continuously on the same saturated pool | Increases CPU pressure, creates retry loops, and prolongs overload | Use jittered backoff, retry budgets, deadlines, or return busy |
| Increasing max threads without considering downstream | Resource contention, high latency, cascading failures | Measure bottlenecks and limit concurrency to real resources |

## 11. Self-Check Questions

**1. A pool has 2 core, 4 maximum, and a 10-slot queue. When 2 workers are busy and the queue still has space, does the executor prefer spawning a 3rd worker?**  
Normally no; `execute` prefers enqueuing once core size is reached, and only adds workers when the queue does not accept the task.

**2. Does a bounded queue automatically make the producer wait?**  
No. `ThreadPoolExecutor.execute` tries to enqueue, then may add a worker or invoke the rejection handler; you need `CallerRunsPolicy`, a semaphore, or another admission mechanism if you want to slow down the producer.

**3. What exactly does `Semaphore(20)` limit?**  
It limits the number of permits granted concurrently. If every producer acquires a permit before submitting and releases it once when the task finishes, it represents at most 20 outstanding tasks under that contract. It does not limit tasks that bypass the semaphore, and it does not guarantee the pool will always accept.

**4. Why can `shutdownNow` leak permits?**  
Unstarted tasks drained from the queue will never enter the wrapper that has `finally { permits.release(); }`. The caller must process the list of unstarted tasks and run cleanup.

**5. Must backpressure always block the producer?**  
No. It can run the work on the caller, return a busy error, wait with a timeout, shed load, or route to a channel with its own capacity. Choose the behavior based on work value, deadlines, durability, and impact on the producer.

## References

- [Java SE 17 — ThreadPoolExecutor](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/concurrent/ThreadPoolExecutor.html)
- [Java SE 17 — BlockingQueue](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/concurrent/BlockingQueue.html)
- [Java SE 17 — Semaphore](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/concurrent/Semaphore.html)
- [Java SE 17 — RejectedExecutionHandler](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/concurrent/RejectedExecutionHandler.html)

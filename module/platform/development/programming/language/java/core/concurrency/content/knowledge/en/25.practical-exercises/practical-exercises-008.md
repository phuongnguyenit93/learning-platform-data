# Practical Exercise: Implementing a Semaphore to Limit Concurrent Resources in Java

## 1. Problem Statement and Objectives

A Java application has many tasks running concurrently, but a scarce resource can serve at most **3 tasks at the same time**. The resource might be a device, a connection to an external system, a special transaction session, or a very memory-intensive operation. When 12 requests arrive close together, the application needs to:

1. Allow at most 3 tasks into the resource-usage section.
2. Have the remaining tasks wait for a finite amount of time or fail in a controlled manner.
3. Regardless of whether the operation succeeds, throws an exception, or is interrupted after entering, return the access permit.
4. Verify the limit using thread-safe counters rather than inferring it from log line ordering.
5. Measure the active count, peak concurrency, wait time, and timeout count.
6. Distinguish between limiting resource access and limiting the number of tasks queued in an ExecutorService.

This exercise belongs to **pure-JDK Java Concurrency**, without using Spring or components from the Spring chapter. Examples use Java 17+.

### Acceptance Criteria

- A single **Semaphore** is shared across all tasks using the same resource budget.
- Each task must acquire a permit successfully **before** using the resource.
- Each acquired permit is returned **exactly once** via `finally`, even when an exception occurs.
- Timeouts or interrupts while waiting must not cause spurious releases.
- In multi-threaded testing: 0 ≤ active ≤ limit and peak ≤ limit.
- After all tasks complete: active = 0, availablePermits = limit.
- Be able to explain the remaining limitations: queue backlog, downstream timeout, fairness, and performance.

## 2. What is a Semaphore?

**java.util.concurrent.Semaphore** maintains a counter of access rights called **permits**. With `Semaphore(3)`, there are initially 3 permits. A successful `acquire()` call takes one permit; `release()` returns one permit.

~~~text
Initial: available = 3

Thread A: acquire -> available = 2 -> use resource
Thread B: acquire -> available = 1 -> use resource
Thread C: acquire -> available = 0 -> use resource
Thread D: acquire -> must wait for a permit

Thread B: release -> a waiter can be granted a permit
Thread D: continue -> use resource
~~~

A Semaphore is a **permit-counting** mechanism; it does not automatically manage connections, objects, transactions, or the lifecycle of the actual resource. Application code must follow this protocol:

~~~text
Request permit -> enter resource section only after granted
               -> return permit regardless of exit path
~~~

Key APIs:

| API | Behavior | When to Use |
|---|---|---|
| new Semaphore(N) | N permits, non-fair by default | Limiting concurrent tasks, prioritizing throughput |
| new Semaphore(N, true) | N permits, enables fairness by granting permits in order at the internal queue point | When you want to prevent a waiter from being continuously bypassed |
| acquire() | Blocks until a permit is available or the thread is interrupted | When waiting is acceptable, though lifecycle should still be controlled |
| tryAcquire() | Succeeds immediately or returns false without waiting | Fail-fast when the system is busy |
| tryAcquire(timeout, unit) | Waits at most a given duration, returns boolean; can be interrupted | Admission with a deadline |
| release() | Increments permit count by one; may wake a waiter | Only after a successful acquire |
| availablePermits() | Number of permits immediately available at the time of observation | Telemetry or checking when the system is quiescent |
| getQueueLength() | Estimate of the number of threads waiting for a permit | Monitoring, not as a primary synchronization condition |
| acquire(k), release(k) | Acquire/release multiple permits at once | Weighted resources |

**Crucial:** Semaphore does not have ownership semantics like `ReentrantLock`. A thread that never called `acquire` can still call `release`; if coded incorrectly, `availablePermits` can exceed the initial capacity. Therefore, `acquire`/`release` pairing must be enforced by code structure and verified with tests.

### How Semaphore Differs from synchronized/Lock

- `synchronized`/`ReentrantLock` is primarily used to protect the **consistency of shared mutable state** inside a critical section.
- `Semaphore(N)` primarily limits the **number of concurrent executions** of an activity; N can be greater than 1.
- `Semaphore(1)` can be used as a binary semaphore, but it does not replace all ownership and reentrancy characteristics of `ReentrantLock`.
- When three tasks pass through `Semaphore(3)` together, they **still run concurrently**. If all three modify a non-thread-safe `HashMap`, `Semaphore(3)` does not make the `HashMap` thread-safe.

## 3. Designing a Limiter Class with Timeout and Cleanup

We create a **SemaphoreLimiter** class with the following components:

- `limit`: maximum number of tasks using the resource simultaneously.
- `Semaphore`: issues shared permits, configured with `fair=true` in the example for easier analysis of wait scheduling.
- `execute(Callable, timeout, TimeUnit)`: waits for a permit and then runs the operation; throws `TimeoutException` if the wait time expires.
- `AtomicInteger active`: number of tasks that have entered the resource section and have not yet completed.
- `AtomicInteger peak`: maximum `active` value observed so far.

**Required execution order design:**

~~~text
tryAcquire(timeout)
    |
    +-- false --------> TimeoutException, no release
    |
    +-- InterruptedException --> propagate error, no release
    |
    +-- true ---------> increment active
                         |
                         +-- operation.call()
                         |      |
                         |      +-- success / exception / interrupt
                         |
                         +-- finally: decrement active
                         +-- finally: release 1 permit
~~~

Here, the timeout applies only to the **permit wait time**, not the duration of the operation after entering. Timeouts for network, database, or actual task execution must be handled separately.

## 4. Complete Java 17 Program

Save the file **SemaphoreLimiterDemo.java**:

~~~java
import java.util.ArrayList;
import java.util.List;
import java.util.Objects;
import java.util.concurrent.Callable;
import java.util.concurrent.ExecutorService;
import java.util.concurrent.Executors;
import java.util.concurrent.Future;
import java.util.concurrent.Semaphore;
import java.util.concurrent.TimeUnit;
import java.util.concurrent.TimeoutException;
import java.util.concurrent.atomic.AtomicInteger;

public class SemaphoreLimiterDemo {
    static final class SemaphoreLimiter {
        private final int limit;
        private final Semaphore permits;
        private final AtomicInteger active = new AtomicInteger();
        private final AtomicInteger peak = new AtomicInteger();

        SemaphoreLimiter(int limit, boolean fair) {
            if (limit <= 0) {
                throw new IllegalArgumentException("limit must be positive");
            }
            this.limit = limit;
            this.permits = new Semaphore(limit, fair);
        }

        <T> T execute(Callable<T> operation, long timeout, TimeUnit unit)
                throws Exception {
            Objects.requireNonNull(operation, "operation");
            Objects.requireNonNull(unit, "unit");
            if (timeout < 0) {
                throw new IllegalArgumentException("negative timeout");
            }

            // No permit is owned when this returns false or is interrupted.
            if (!permits.tryAcquire(timeout, unit)) {
                throw new TimeoutException("No permit available");
            }

            try {
                int current = active.incrementAndGet();
                peak.accumulateAndGet(current, Math::max);
                try {
                    return operation.call();
                } finally {
                    active.decrementAndGet();
                }
            } finally {
                // Exactly one release for each successful acquisition.
                permits.release();
            }
        }

        int limit() { return limit; }
        int active() { return active.get(); }
        int peak() { return peak.get(); }
        int available() { return permits.availablePermits(); }
        int waitingEstimate() { return permits.getQueueLength(); }
    }

    public static void main(String[] args) throws Exception {
        final int limit = 3;
        final int tasks = 12;
        SemaphoreLimiter limiter = new SemaphoreLimiter(limit, true);
        ExecutorService pool = Executors.newFixedThreadPool(8);
        List<Future<Integer>> futures = new ArrayList<>();

        try {
            for (int i = 0; i < tasks; i++) {
                final int id = i;
                futures.add(pool.submit(() ->
                    limiter.execute(() -> {
                        // Simulates holding an external scarce resource.
                        Thread.sleep(60);
                        return id;
                    }, 10, TimeUnit.SECONDS)
                ));
            }

            int sum = 0;
            for (Future<Integer> future : futures) {
                sum += future.get();
            }

            if (sum != 66) {
                throw new AssertionError("Unexpected task results");
            }
            if (limiter.peak() > limit || limiter.active() != 0) {
                throw new AssertionError("Concurrency limit violated");
            }
            if (limiter.available() != limit) {
                throw new AssertionError("Permits were not restored");
            }

            System.out.println("Completed: " + futures.size());
            System.out.println("Result sum: " + sum);
            System.out.println("Peak within limit: " +
                    (limiter.peak() <= limiter.limit()));
            System.out.println("Active after finish: " + limiter.active());
            System.out.println("Permits restored: " + limiter.available());
        } finally {
            pool.shutdownNow();
            pool.awaitTermination(10, TimeUnit.SECONDS);
        }
    }
}
~~~

Run in the directory containing the file:

~~~bash
javac SemaphoreLimiterDemo.java
java SemaphoreLimiterDemo
~~~

When all tasks finish normally before the deadline, stdout is:

~~~text
Completed: 12
Result sum: 66
Peak within limit: true
Active after finish: 0
Permits restored: 3
~~~

The **exact peak value** is not printed because it depends on scheduling, but the condition `peak <= 3` is checked. If the OS is overloaded or a task is interrupted such that a permit cannot be acquired within 10 seconds, `Future.get()` will throw `ExecutionException`, and the stdout above should not be treated as a runtime guarantee across all machines.

### How the Code Works

**The Semaphore must be shared.** A single `SemaphoreLimiter` is created before the `for` loop and passed to all tasks. If each task creates its own `Semaphore(3)`, there is no shared limit.

**Place acquire before finally.** If `tryAcquire(timeout, unit)` returns `false` or throws `InterruptedException`, no permit has been acquired and `release` must not be called. Once it returns `true`, `try/finally` wraps the entire resource-usage section.

**Atomic metrics do not replace Semaphore.** `AtomicInteger` ensures the counters do not suffer lost updates. However, `active.incrementAndGet()` does not itself limit `active`; it is the `Semaphore` that determines who enters. Metrics are for verification and observability.

**An Executor is not a Semaphore.** A fixed thread pool of 8 workers can start up to 8 tasks, of which at most 3 pass through the permit-protected section while the other workers may wait. The pool controls active threads; the Semaphore controls resource-usage slots.

**Future.get() is necessary.** It waits for tasks to complete and does not silently swallow exceptions from `Callable`. Only after all futures return successfully are the final checks `active=0` and `available=3` meaningful end-state assertions.

**Thread.sleep(60) only simulates resource hold time.** It does not model database, network, or hardware throughput and is not used to prove scheduling order. The 60ms value simply creates an easily observable active window.

## 5. Testing Timeout with Deterministic Results

To verify that a failed permit acquisition does not corrupt the counter, we proactively acquire the only permit on the main thread before calling a timed `tryAcquire`.

Save the file **SemaphoreTimeoutDemo.java**:

~~~java
import java.util.concurrent.Semaphore;
import java.util.concurrent.TimeUnit;

public class SemaphoreTimeoutDemo {
    public static void main(String[] args) throws InterruptedException {
        Semaphore semaphore = new Semaphore(1, true);
        semaphore.acquire();
        try {
            boolean acquired =
                    semaphore.tryAcquire(100, TimeUnit.MILLISECONDS);
            System.out.println("Second acquire: " + acquired);
            System.out.println("While held: " +
                    semaphore.availablePermits());
        } finally {
            semaphore.release();
        }
        System.out.println("After release: " +
                semaphore.availablePermits());
    }
}
~~~

Run:

~~~bash
javac SemaphoreTimeoutDemo.java
java SemaphoreTimeoutDemo
~~~

Stdout:

~~~text
Second acquire: false
While held: 0
After release: 1
~~~

Because the main thread holds the permit throughout the timed `tryAcquire` call, no thread can be granted the second permit. The method returns `false` after the requested wait duration, and then `finally` releases the **first permit**. This is a logic check independent of log timing.

### Anti-pattern: Releasing Even When Permit Acquisition Fails

~~~java
boolean acquired = semaphore.tryAcquire();
try {
    if (acquired) {
        useResource();
    }
} finally {
    semaphore.release();  // BUG if acquired == false
}
~~~

This is an illustrative buggy snippet and does not compile standalone because `useResource` is undefined. If `acquired=false`, `finally` still increments the permits. Because Semaphore does not check ownership, repeated over-releases can allow more tasks than the intended capacity. The correct approach is to enter `try/finally` only after a successful `acquire`, or conditionally release based on an accurately assigned `acquired` flag.

## 6. Testing the Exception Path: Permit Must Still Be Released

Add the following method inside the **SemaphoreLimiterDemo** class to practice on your own. This method must run **when no other tasks are using the same limiter**, so that the before/after comparison is meaningful.

~~~java
static void testException(SemaphoreLimiter limiter) throws Exception {
    int before = limiter.available();

    try {
        limiter.execute(() -> {
            throw new IllegalStateException("simulated failure");
        }, 1, TimeUnit.SECONDS);
        throw new AssertionError("Exception was expected");
    } catch (IllegalStateException expected) {
        // Expected failure inside the protected operation.
    }

    if (limiter.available() != before || limiter.active() != 0) {
        throw new AssertionError("Permit leak after failure");
    }
}
~~~

This case does not need a new standalone program; call `testException(limiter)` in `main` after awaiting all futures. An exception thrown by `operation.call()` does not bypass the two `finally` blocks in `execute()`, so `active` drops back to 0 and the permit is returned.

**Note:** Releasing a permit does not automatically close a connection, roll back a transaction, or release a device. If the real resource requires cleanup, the operation should use `try-with-resources` or its own `finally` block for the resource, and only after that should the limiter return the permit.

### InterruptedException and Cancellation

- While waiting on `acquire()` or `tryAcquire(timeout, unit)`, the thread may be interrupted; the API throws `InterruptedException`. In that case, `release` must not be called because no permit was granted.
- Once a **permit has been acquired**, the operation may still be interrupted (for example, `Thread.sleep` or interruptible I/O). Even though the exception propagates upward, `finally` still returns the permit.
- If a layer catches `InterruptedException` without rethrowing it, it usually needs to restore the interrupt flag via `Thread.currentThread().interrupt()` before returning or handling cancellation according to its contract.
- `Future.cancel(true)` is an interrupt request, not a guarantee that the underlying work stops immediately. Blocking I/O or non-cooperative code may continue holding the permit.
- Timed `tryAcquire` bounds the **wait time to enter**, not the **time holding the resource**. Separate deadlines are needed for I/O or actual work.

Example pattern for handling interruption at the caller layer:

~~~java
try {
    limiter.execute(operation, 500, TimeUnit.MILLISECONDS);
} catch (InterruptedException e) {
    Thread.currentThread().interrupt();
    // Stop or return according to the caller's cancellation contract.
}
~~~

This is an integration snippet and is not standalone because `limiter` and `operation` must be declared according to the application context.

## 7. Fairness: Does It Guarantee Strict FIFO?

~~~java
Semaphore fair = new Semaphore(3, true);
Semaphore nonFair = new Semaphore(3, false);
~~~

- **Non-fair** does not guarantee waiter ordering; a newly arriving task can take a permit ahead of earlier waiters, which can sometimes increase throughput.
- **Fair** selects waiters in the arrival order at the **internal queue point** of `acquire` calls. It does not guarantee that a thread calling the method earlier will finish earlier, nor does it alter OS scheduling or executor submission order.
- **An important exception:** Immediate `tryAcquire()` can grab an available permit even when the Semaphore is fair and waiters are already queued. If you want to respect fairness in a non-blocking attempt, the JDK documentation recommends `tryAcquire(0, TimeUnit.SECONDS)`, which can throw `InterruptedException`.
- Fairness can affect overhead, throughput, and tail latency. Choose `true`/`false` based on product requirements and actual benchmarks, not intuition alone.

In the demo, `fair=true` favors predictable permit-granting behavior for queued resource requests. Any start/end order measurements may still vary because the eight workers are scheduled independently by the scheduler.

## 8. How to Prove the Limit with Stress Testing

The `active` variable is incremented only after a permit is acquired and decremented before the permit is released. Therefore, if every task goes through `execute()`, the invariants to verify are:

~~~text
0 <= active <= limit
0 <= peak <= limit

After all work completes:
active == 0
availablePermits() == limit
~~~

A useful test plan:

| Scenario | How to Trigger | Expected Result to Verify |
|---|---|---|
| Low load | 2 tasks, limit=3 | No timeouts; peak ≤ 2 |
| Contended load | 12 tasks, 8 workers, limit=3 | peak ≤ 3; finally active=0 |
| Timeout | Hold all permits, call timed tryAcquire | False or TimeoutException depending on wrapper |
| Exception in operation | Throw RuntimeException after acquisition | Exception propagates, permits are returned |
| Interrupted waiter | Hold permits, interrupt waiting thread | Operation does not run, no spurious release |
| Task canceled after entering | Interrupt work currently holding a permit | Cleanup runs if operation exits/cooperates |
| Over-release regression | Intentionally call release twice in a buggy version | Test must detect permits exceeding capacity |
| Repeated task batches | Loop independent batches | No cumulative permit leak over time |

During stress testing, a `CountDownLatch` can be used as a starting gate to increase contention. However, `CountDownLatch` **does not prove** a specific execution schedule; the scheduler still decides when each worker runs. Record all exceptions and use atomic counters instead of inferring behavior from `System.out` ordering.

If you want to probe subtler Java Memory Model interactions, `jcstress` is an external tool outside the JDK. For this Semaphore exercise, the invariant `active <= limit` together with timeout/exception/interruption cases provide much more relevant evidence than searching for a specific schedule.

## 9. Semaphore Does Not Limit Total Backlog

Diagram when the pool has 8 workers, Semaphore has 3 permits, and 12 tasks are submitted:

~~~text
12 tasks submitted
       |
       v
ExecutorService: up to 8 worker threads running tasks
       |
       +-- 3 workers acquire permits --> resource usage
       |
       +-- 5 workers may wait for permits
       |
       +-- other submitted tasks remain in executor queue
~~~

The limit of 3 applies only to **the section where a permit has been acquired**. `Executors.newFixedThreadPool()` uses an essentially unbounded work queue; if producers submit continuously faster than processing capacity, the queue can grow without bound, increasing memory usage and latency even though the Semaphore is working correctly.

To protect a real-world application, also consider:

1. `ThreadPoolExecutor` with a **bounded queue** and an explicit `RejectedExecutionHandler` policy.
2. Rate limiting or backpressure at the ingress point, before the backlog grows too high.
3. Permit wait deadlines and real I/O processing deadlines, along with downstream timeouts.
4. Metrics for executor queue depth, queue wait, rejected tasks, and total end-to-end latency.
5. Resource ordering so that threads do not hold another scarce lock or connection while waiting for a permit.

### Acquire Inside the Task or Before Submitting?

**Acquire inside the task** (as in the demo): the resource is requested right before the operation, with `finally` in the same scope; easy to get right, but can block a worker thread before it performs useful work.

**Acquire before submit**: applies backpressure to the producer earlier, but makes ownership harder to manage. If `submit` throws `RejectedExecutionException` or the `Future` is canceled **before running**, an already-acquired permit can leak if it is only released inside the task. To use this approach, you need an admission wrapper that manages the full submit/cancel/reject/complete lifecycle.

With Java 21 virtual threads, waiting on a Semaphore may consume fewer platform threads. However, virtual threads do not create extra CPU, do not increase downstream capacity, and do not eliminate the need for timeouts, lifecycle management, or backlog monitoring.

## 10. Common Implementation Pitfalls

### Pitfall A — Calling acquire Inside try with Blind release

~~~java
try {
    semaphore.acquire();
    useResource();
} finally {
    semaphore.release();
}
~~~

If `acquire()` throws `InterruptedException` **before acquiring a permit**, `finally` still calls `release` and creates an extra permit. Place `acquire()` before `try/finally` or maintain an accurate `acquired` flag.

### Pitfall B — Not Using finally

~~~java
semaphore.acquire();
useResource();
semaphore.release();
~~~

If `useResource()` throws an exception, the permit is not returned. After multiple errors, waiters may hang even though the actual resource is free. `release` must be placed inside `finally`.

### Pitfall C — Each Task Creates Its Own Semaphore

~~~java
void doTask() throws InterruptedException {
    Semaphore local = new Semaphore(3);
    local.acquire();
    try {
        useResource();
    } finally {
        local.release();
    }
}
~~~

This is only an illustrative buggy snippet. Each task creates a fresh budget, so there is **no shared limit**. The Semaphore must belong to the shared service or resource limiter.

### Pitfall D — Checking availablePermits Instead of Calling acquire

~~~java
if (semaphore.availablePermits() > 0) {
    useResource(); // No permit was reserved: a race.
}
~~~

`availablePermits()` is only a snapshot, not an atomic check-and-reserve operation. Multiple threads can observe `> 0` at the same time. Use `acquire` or `tryAcquire`.

### Pitfall E — Releasing in catch and Again in finally

~~~java
semaphore.acquire();
try {
    useResource();
} catch (RuntimeException e) {
    semaphore.release(); // Double release path!
    throw e;
} finally {
    semaphore.release();
}
~~~

Every successfully acquired permit must be released **once**. Do not call `release` separately in `catch` if `finally` already does so.

### Pitfall F — Assuming Semaphore(3) Automatically Makes Shared State Safe

Three tasks can enter the protected section simultaneously. If they concurrently write to a non-thread-safe `HashMap` or update an unsynchronized balance, a data race still occurs. Use concurrent data structures, atomic updates, or appropriate locks **inside the section**.

### Pitfall G — Waiting for a Permit While Holding a Lock Needed by the Holder

T1 holds lock X and then waits for a permit; T2 holds the permit but needs lock X to finish and release. This is a deadlock cycle. Establish a consistent acquisition order across resource types and avoid blocking unnecessarily inside critical sections.

### Pitfall H — Assuming Acquire Timeout Is Operation Timeout

`tryAcquire(100ms)` only bounds waiting **to start**. Afterward, a remote call could hang for minutes, holding the permit and causing all other waiters to time out. Design timeouts and cancellation separately at the I/O layer.

### Pitfall I — Treating getQueueLength as an Exact Number

`getQueueLength()` is only an instantaneous estimate that changes as threads acquire and release. It is suitable for observing trends, not for asserting invariants or implementing custom admission logic with `if`.

## 11. Choosing the Right Number of Permits

There is no single `limit` that fits every workload.

- **Finite resource pool:** If only 3 devices or 3 connections are available, `limit` should generally not exceed 3.
- **CPU-bound:** You can start measuring around the allocated number of logical processors. However, a Semaphore is only a task-limiting tool; it does not make code run faster.
- **I/O-bound:** Tasks spend time waiting, so the number of in-flight tasks can exceed the core count; nevertheless, downstream systems have their own connection, memory, and quota limits.
- **External API:** Concurrent requests are different from requests per second. Semaphore does not enforce a time-based rate limit; if an API has a QPS quota, you need an additional rate limiter mechanism.

A steady-state estimate:

~~~text
Average in-flight work ≈ throughput × average time held
~~~

If a resource serves 20 calls/second and each call holds a permit for 0.1 seconds on average, average in-flight work is roughly 2. However, you cannot conclude that `limit=2` is sufficient for all bursts, p99 latency, or headroom needs. Measure in practice with a representative workload and the limits of the external system.

Metrics to monitor:

| Metric | Question It Answers |
|---|---|
| active, peak | How many tasks are actually using the resource, and what is the peak? |
| available permits | How much spare capacity is free at a given moment? |
| waiting estimate | Are many workers waiting on the Semaphore? |
| acquire wait duration | How long does a request wait to enter? |
| acquire timeout count | How many times could a permit not be acquired before the deadline? |
| hold duration | How long does a task hold a permit? |
| operation error rate | How often does admitted work fail? |
| executor queue length | Has backlog accumulated before tasks even reach the Semaphore? |
| end-to-end p95/p99 | Are users experiencing high latency even when throughput remains high? |

Track permit wait duration and permit hold duration separately to determine whether the bottleneck is at admission or downstream. Do not increase `limit` just to reduce waiting if the underlying resource lacks the capacity to handle it.

## 12. Further Exercises

**Exercise A — Vary the limit and measure timing.** Run the program with `limit` set to 1, 2, 3, and 5, keeping 12 tasks and the same work. Record batch duration, peak, and timeouts. Explain why a sleep demo can overlap wait times easily, whereas a real database may become overloaded if you increase connections.

**Exercise B — Fail-fast.** Replace timed `tryAcquire` with non-waiting `tryAcquire()`. When no permits remain, reject immediately. Compare latency and rejection count against waiting up to 10 seconds. Note that immediate `tryAcquire()` does not respect fairness like timed `tryAcquire` calls do.

**Exercise C — Failure injection.** Have half the tasks throw `IllegalStateException` after entering the section. Await all futures, accept and record the expected `ExecutionException`, and then verify `active=0` and `availablePermits=limit`.

**Exercise D — Interrupt a waiter.** Have a main thread hold all permits while another thread tries `acquire()`. Interrupt the waiter and verify it neither uses the resource nor calls `release`. Finally, have `main` release the exact number of permits it holds. You can use a `CountDownLatch` to synchronize the starting point, but avoid assuming a `sleep` guarantees the `WAITING` state.

**Exercise E — Auto-closing ResourceLease.** Design a `Lease` implementing `AutoCloseable` so callers can use `try-with-resources`. `Lease` should be idempotent: calling `close()` twice still releases only one permit, for example guarded by an `AtomicBoolean`. Clearly define responsibility when transferring a lease between threads.

**Exercise F — Bounded queue.** Replace the fixed thread pool with a `ThreadPoolExecutor` backed by an `ArrayBlockingQueue` and a rejection policy. Compare with the old version when the producer submits faster than consumers can process; inspect queue depth, rejections, and memory to see the difference between a semaphore and ingress backpressure.

## 13. Completion Checklist

- [ ] Exactly one Semaphore is shared per resource budget.
- [ ] Validate `limit > 0`, non-negative timeout, and non-null arguments.
- [ ] Every operation must successfully acquire a permit before using the resource.
- [ ] Release happens exactly once in `finally`, including on exception or interruption.
- [ ] Timed-out or rejected acquisitions do not cause over-release.
- [ ] `active <= limit` is verified in multi-task testing.
- [ ] After all futures complete, `active=0` and permits return to `limit`.
- [ ] Do not use `availablePermits` or log ordering as synchronization mechanisms.
- [ ] Do not confuse fairness with task completion order.
- [ ] Have policies for executor queue, downstream timeouts, and cancellation.
- [ ] Measure throughput, latency, permit wait time, and resource hold time.
- [ ] Do not use Semaphore as a substitute for synchronizing unsafe shared data.

## 14. Summary

**Semaphore(N)** limits at most N tasks **that have acquired a permit and not yet returned it** from entering the resource section, provided every task follows the `acquire`/`release` contract. Core pattern:

~~~java
semaphore.acquire();
try {
    useResource();
} finally {
    semaphore.release();
}
~~~

If a timeout is needed, replace `acquire()` with `tryAcquire(timeout, unit)` and **only** enter `try/finally` when it returns `true`. For high-load applications, combine Semaphore with a bounded queue, an admission policy, and real resource timeouts.

Official JDK references: [Semaphore (Java 21)](https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/util/concurrent/Semaphore.html), [ThreadPoolExecutor](https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/util/concurrent/ThreadPoolExecutor.html), [AtomicInteger](https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/util/concurrent/atomic/AtomicInteger.html), [TimeUnit](https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/util/concurrent/TimeUnit.html).

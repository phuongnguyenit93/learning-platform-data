# Semaphore for Limiting Access to Finite Resources in Java

## 1. The problem: many threads, a limited number of resources

Suppose an application has 100 concurrent tasks, but a downstream system only allows **5 in-flight requests**. If each task calls downstream as soon as it runs, the number of connections or request streams can exceed the allowed resource capacity, increasing timeouts, lock contention, and the risk of service collapse.

**`java.util.concurrent.Semaphore`** is a synchronizer that uses a non-negative integer representing **the number of available permits**. Before entering the section of work that uses the finite resource, a task must **acquire a permit**; when it no longer needs to hold access, the task **releases the permit**. If all permits are currently held, a caller attempting a blocking acquire will wait until a permit is released or an interruption occurs.

~~~text
              Semaphore(3)
           [permit] [permit] [permit]
               |        |        |
           worker A  worker B  worker C    -> allowed into the limited region
                                         
           worker D, E, F                  -> waiting for a permit
               |
       when A releases a permit
               |
         a waiter can acquire
~~~

**Key point to remember:** A Semaphore **does not represent a physical resource** (connection, socket, device, etc.). It only manages *the permission to start using one* by convention. The application must still ensure that the actual resource is available, released on time, and that workers follow the acquire/release protocol.

This lesson focuses on standard Java Concurrency, without depending on any other framework.

## 2. Permits, acquire, release, and the core invariant

Create a semaphore:

~~~java
Semaphore slots = new Semaphore(3);
~~~

This is an **illustrative snippet** in a context where `java.util.concurrent.Semaphore` is already imported, not a standalone class.

- **`new Semaphore(n)`** starts with n permits.
- **`acquire()`** requires one permit. If a permit is available, the available permit count decreases by one and the caller proceeds; if none is available, the caller waits and may be interrupted.
- **`release()`** increases the available permit count by one and may wake up a waiting caller.
- **`tryAcquire()`** tries immediately, returning `true` when a permit is obtained and `false` if it cannot be obtained right away.
- **`tryAcquire(timeout, unit)`** waits for a bounded time; returns `false` if the timeout expires without obtaining a permit; may throw `InterruptedException`.
- **`availablePermits()`** returns a snapshot of the number of currently available permits at the time of the call; it **does not reserve** a permit for the next acquire step.

With **n initial permits**, if the code adheres to one successful acquire ↔ one corresponding release, the number of tasks holding a permit will not exceed n. This is an **application-maintained invariant**; Semaphore itself does not track permit owners.

Example:

~~~text
Semaphore(2)
Initial: available=2
Task A acquire succeeds: available=1
Task B acquire succeeds: available=0
Task C tryAcquire(): false
Task A release(): available=1
Task C acquire succeeds: available=0
Task B release(), C release(): available=2
~~~

Do not infer that if a thread holds a permit, only that thread may release it: Java Semaphore **has no concept of ownership like ReentrantLock**. This is useful for handoffs between threads, but it also makes bugs involving **extra releases** or releasing without acquiring easy to introduce.

### Memory visibility (happens-before)

According to the Java Semaphore contract, actions in a thread **prior to calling release** *happen-before* actions in another thread **following a successful acquire** on the same semaphore. That is a useful synchronization mechanism, but it **does not make all operations on shared data thread-safe**. When n is greater than 1, multiple tasks can still access the same data inside the limited region; if tasks concurrently modify a non-thread-safe variable or structure, proper synchronization or data partitioning is still required.

## 3. Four acquire styles and choosing by deadline

| API | Behavior when permits are exhausted | Return value | Interruption |
|---|---|---|---|
| `acquire()` | Waits until a permit is available | `void` | Yes, `InterruptedException` |
| `acquireUninterruptibly()` | Waits until a permit is available | `void` | Does not throw on interrupt while waiting; preserves interrupt status upon completion |
| `tryAcquire()` | Returns immediately | `boolean` | Does not wait, so not an interruptible waiting API |
| `tryAcquire(timeout, unit)` | Waits up to timeout | `boolean` | Yes, `InterruptedException` |

There are also overloads for multiple permits:

~~~java
slots.acquire(2);
slots.release(2);
boolean accepted = slots.tryAcquire(2);
boolean timed = slots.tryAcquire(2, 100, TimeUnit.MILLISECONDS);
~~~

The lines above are **illustrative code** with `slots` as a Semaphore and `TimeUnit` already imported; `acquire(2)` may throw InterruptedException. Acquiring multiple permits requires the full requested count by contract—it does not take a partial amount and return. Avoid requesting too many permits, which can make it hard for smaller tasks to be served.

### Which one to choose?

- **`acquire()`:** when the producer can wait and the task must be processed, provided there is a shutdown/interrupt plan. If the caller is a request thread with a short deadline, unbounded waiting is usually inappropriate.
- **`tryAcquire()`:** used for **fail-fast** admission control, such as returning an overload error or dropping less important work. You must check the boolean return value.
- **`tryAcquire(timeout)`:** allows a short wait to absorb bursts while maintaining a **latency bound**. When it returns false, the task has not entered the permit-protected region; it must not release.
- **`acquireUninterruptibly()`:** use only when there is a strong reason not to give up upon receiving an interrupt. During shutdown, it can cause workers to wait for a very long time; it is not the default choice.

**Do not use `availablePermits() > 0` as a pre-check and assume the acquire will succeed immediately**: multiple threads can observe the same snapshot concurrently. Only the result of `tryAcquire()` or a completed acquire confirms that access has been granted.

## 4. Safety rule: acquire successfully first, then release in finally

The most important practical pattern:

~~~java
boolean acquired = false;
try {
    acquired = slots.tryAcquire(200, TimeUnit.MILLISECONDS);
    if (!acquired) {
        // Decision to reject/defer: do not call downstream.
        return;
    }
    useLimitedResource();
} finally {
    if (acquired) {
        slots.release();
    }
}
~~~

This is **illustrative code inside a method**, with `slots` already declared and `useLimitedResource()` representing business processing; it is not a standalone Java file. The timeout overload may throw `InterruptedException`.

With blocking `acquire()`:

~~~java
slots.acquire(); // May throw InterruptedException.
try {
    useLimitedResource();
} finally {
    slots.release();
}
~~~

**Placing `acquire()` before the try/finally block** prevents releasing if acquire did not succeed and threw InterruptedException. Once acquired, finally executes even if the work inside throws an unchecked exception.

If multiple permits are acquired, **release the exact number taken**. A very subtle bug is calling `release()` in both catch and finally, causing available permits to grow beyond the initial capacity: later, the system may run more concurrent tasks than the configured limit.

**Semaphore does not cap the maximum number of permits on release.** It does not automatically reject an extra release just because the initial permit count has been reached. You can test this invariant at the application level using metrics or a semaphore wrapper, but do not use the `availablePermits()` snapshot as the primary locking mechanism.

## 5. Java 17 example: only two tasks processed concurrently

The program uses **Semaphore(2)** and two workers that hold permits while waiting on a latch. The main thread tries to acquire a third permit: it is guaranteed to receive `false` because both permits are held. Once the two workers are allowed to finish, the permits are returned.

Save **SemaphoreLimitDemo.java**:

~~~java
import java.util.concurrent.Callable;
import java.util.concurrent.CountDownLatch;
import java.util.concurrent.ExecutorService;
import java.util.concurrent.Executors;
import java.util.concurrent.Future;
import java.util.concurrent.Semaphore;
import java.util.concurrent.TimeUnit;

public class SemaphoreLimitDemo {
    public static void main(String[] args) throws Exception {
        Semaphore slots = new Semaphore(2);
        ExecutorService pool = Executors.newFixedThreadPool(2);
        CountDownLatch bothEntered = new CountDownLatch(2);
        CountDownLatch finishWork = new CountDownLatch(1);

        try {
            Callable<String> first = () -> {
                slots.acquire();
                try {
                    bothEntered.countDown();
                    finishWork.await();
                    return "task-A";
                } finally {
                    slots.release();
                }
            };
            Callable<String> second = () -> {
                slots.acquire();
                try {
                    bothEntered.countDown();
                    finishWork.await();
                    return "task-B";
                } finally {
                    slots.release();
                }
            };

            Future<String> a = pool.submit(first);
            Future<String> b = pool.submit(second);

            if (!bothEntered.await(5, TimeUnit.SECONDS)) {
                throw new IllegalStateException("Workers not ready");
            }

            boolean thirdAccepted = slots.tryAcquire();
            System.out.println("third accepted=" + thirdAccepted);
            if (thirdAccepted) {
                slots.release(); // Defensive guard in case example conditions change.
            }

            finishWork.countDown();
            System.out.println("results=" + a.get() + "," + b.get());
            System.out.println("available after=" + slots.availablePermits());
        } finally {
            finishWork.countDown();
            pool.shutdownNow();
        }
    }
}
~~~

Run with JDK 17+:

~~~bash
javac SemaphoreLimitDemo.java
java SemaphoreLimitDemo
~~~

Expected stdout:

~~~text
third accepted=false
results=task-A,task-B
available after=2
~~~

**Why is the output deterministic?** `bothEntered.await(...)` only proceeds once both workers have successfully acquired a permit and reached the latch. At that moment, each worker is waiting on `finishWork`, so both permits remain held. Main calls `tryAcquire()` before releasing the latch; inevitably, no permits are free. After releasing the latch and completing `Future.get()` for both tasks, both `finally` blocks have released their permits. The execution order of the two workers does not affect the order of `a.get(), b.get()` printed from main.

**Note:** `pool.shutdownNow()` in finally is a defensive measure if the example fails; in a real system, a timed graceful shutdown procedure and termination check are needed.

## 6. Java 17 example: bounding wait time for a permit

With a resource that only allows one concurrent request, main acquires the permit first. Another attempt cannot acquire within the short timeout, so `tryAcquire(timeout)` returns `false`. After main releases, a new attempt succeeds. This is the timeout-based admission control pattern.

Save **SemaphoreTimeoutDemo.java**:

~~~java
import java.util.concurrent.Semaphore;
import java.util.concurrent.TimeUnit;

public class SemaphoreTimeoutDemo {
    public static void main(String[] args) throws Exception {
        Semaphore slots = new Semaphore(1);

        slots.acquire(); // Simulate the resource being occupied.
        try {
            boolean accepted = slots.tryAcquire(
                    30, TimeUnit.MILLISECONDS);
            System.out.println("accepted while busy=" + accepted);
            if (accepted) {
                slots.release();
            }
        } finally {
            slots.release();
        }

        boolean acceptedAfterRelease = slots.tryAcquire(
                30, TimeUnit.MILLISECONDS);
        System.out.println("accepted after release=" + acceptedAfterRelease);
        if (acceptedAfterRelease) {
            slots.release();
        }
        System.out.println("available=" + slots.availablePermits());
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
accepted while busy=false
accepted after release=true
available=1
~~~

**Timeout is not auto-retry**: `tryAcquire(timeout)` returning false means the caller did not obtain a permit within the wait period, so it must not start downstream work. The caller must have a policy: return an overload error, drop/defer if allowed, or retry with an appropriate budget and backoff.

Here, sleep is not used to force the outcome either: main holds the permit for the entire duration of the timed tryAcquire call, so the false result is deterministic.

## 7. Java 17 example: interrupting a worker waiting for a permit

`Semaphore.acquire()` is **interruptible**. In this example, main holds the permit, the worker starts waiting, and is then asked to stop via `Future.cancel(true)`. A CountDownLatch confirms the worker has entered the waiting logic while main still holds the permit, so the worker cannot pass acquire. The worker catches `InterruptedException`, records that it was interrupted, and does not release a permit it never acquired.

Save **SemaphoreInterruptDemo.java**:

~~~java
import java.util.concurrent.CountDownLatch;
import java.util.concurrent.ExecutorService;
import java.util.concurrent.Executors;
import java.util.concurrent.Future;
import java.util.concurrent.Semaphore;
import java.util.concurrent.TimeUnit;
import java.util.concurrent.atomic.AtomicBoolean;

public class SemaphoreInterruptDemo {
    public static void main(String[] args) throws Exception {
        Semaphore slots = new Semaphore(1);
        ExecutorService pool = Executors.newSingleThreadExecutor();
        CountDownLatch entered = new CountDownLatch(1);
        CountDownLatch finished = new CountDownLatch(1);
        AtomicBoolean interrupted = new AtomicBoolean();

        slots.acquire(); // Main holds the permit; worker cannot acquire it.
        try {
            Future<?> waiter = pool.submit(() -> {
                boolean acquired = false;
                try {
                    entered.countDown();
                    slots.acquire();
                    acquired = true;
                } catch (InterruptedException ex) {
                    interrupted.set(true);
                    Thread.currentThread().interrupt();
                } finally {
                    if (acquired) {
                        slots.release();
                    }
                    finished.countDown();
                }
            });

            if (!entered.await(5, TimeUnit.SECONDS)) {
                throw new IllegalStateException("Waiter not started");
            }
            boolean cancelled = waiter.cancel(true);
            if (!finished.await(5, TimeUnit.SECONDS)) {
                throw new IllegalStateException("Waiter did not stop");
            }

            System.out.println("cancel accepted=" + cancelled);
            System.out.println("waiter interrupted=" + interrupted.get());
            System.out.println("waiter cancelled=" + waiter.isCancelled());
        } finally {
            slots.release();
            pool.shutdownNow();
        }
        System.out.println("available=" + slots.availablePermits());
    }
}
~~~

Run:

~~~bash
javac SemaphoreInterruptDemo.java
java SemaphoreInterruptDemo
~~~

Stdout:

~~~text
cancel accepted=true
waiter interrupted=true
waiter cancelled=true
available=1
~~~

**Key distinction:** `Future.cancel(true)` sends an interrupt request to the running worker of the ExecutorService. Because the worker is blocked in `Semaphore.acquire()`, `InterruptedException` is thrown and the worker can exit cleanly. However, there is no general rule that every Java task stops immediately upon cancel(true): stopping other operations still depends on whether they support interruption and whether the code cooperates.

The `acquired` flag ensures release is only called if a permit was actually acquired. Main releases the permit **only once** in finally; the total permit count returns to 1.

## 8. Fairness: Is Semaphore fair or not?

By default, `new Semaphore(permits)` uses **nonfair** mode. You can create a semaphore with fair serving order:

~~~java
Semaphore fair = new Semaphore(3, true);
~~~

In fair mode, **blocking** acquire calls are served in arrival order at **the internal ordering points of the acquisition mechanism**. This helps reduce the risk of long-waiting threads being bypassed, but it **does not guarantee task completion times, start order at the exact moment a method is called, or fixed latency**, because the OS scheduler, task execution time, and races before the ordering point still have an impact.

An easily overlooked detail: **`tryAcquire()` without a timeout can grab a permit immediately if one is free, even when fairness=true and other threads are waiting** (*barging*). For code that must respect fairness, the **`tryAcquire(0, TimeUnit.SECONDS)`** overload is the way to attempt an immediate acquire while participating in the fairness policy (though it is interruptible).

| Property | Nonfair (default) | Fair |
|---|---|---|
| Acquisition strategy under contention | May barge, generally favors throughput | Generally serves in waiting order at permit grant points |
| Goal | Lower overhead, high throughput | Reduce starvation for waiters |
| Cost | Typically lower | Higher synchronization cost, may reduce throughput |
| Log order guarantee | No | **Also no** |
| `tryAcquire()` without timeout | May barge | **Can still barge** |

Fairness does not replace deadlines, starvation monitoring, or workload management. If a thread holds a permit for a very long time, other threads will still wait even with fair=true.

## 9. How does a binary semaphore differ from ReentrantLock?

A **binary semaphore** (`new Semaphore(1)`) limits the protected region to **one task at a time**, so it looks like a mutex. However:

| Criterion | `Semaphore(1)` | `ReentrantLock` |
|---|---|---|
| Logical holder count | 1 when protocol is followed | 1 owner thread |
| Mandatory ownership | **No**: another thread can also release | **Yes**: only the owner may unlock |
| Reentrant | **No** in the lock sense: a second acquire needs another permit | **Yes**: owner can lock multiple times |
| Extra `release` / `unlock` | Can unintentionally increase permits | `unlock` by non-owner throws IllegalMonitorStateException |
| Transferring permission between threads | Can be used for handoff/signaling | Does not have the same cross-thread release model |
| Primary use | Limiting concurrent resource access | Protecting a critical section with an owner thread |

If the goal is to **protect a shared variable** with an exclusive lock where ownership is needed, `ReentrantLock` (or `synchronized`) usually expresses the intent more clearly. If the goal is **N concurrently allowed operations**, Semaphore is the natural primitive.

A binary semaphore can also be initialized with **0 permits** to act as a one-shot signal/handoff, though releases must be managed to avoid accumulating permits if the signal repeats. For waiting on an event or multiple workers completing together, consider CountDownLatch, Phaser, or Condition depending on the problem.

## 10. Semaphore and connection pools / resource pools

Suppose there are **10 physical connections** or **10 devices**:

- Semaphore(10) limits execution to **at most 10 permit-holding processing blocks**.
- However, you still need a **manager for the 10 actual resources**: who gets which connection, checking whether a connection is still usable, when to return it, and what happens on error.
- Semaphore does not create connections, does not track broken connections, and does not make resource management operations thread-safe.

Logical flow:

~~~text
acquire permit
    |
  borrow actual resource
    |
  use resource with timeout
    |
  return/close actual resource
    |
release permit
~~~

The release order should ensure **not returning the permit before the resource is truly ready for the next user**. With `try-with-resources`, you must understand the semantics of `close()`: in some places close returns the connection to the pool, while in others it closes the physical connection. If a resource is broken, it must be replaced or effective allocation capacity must be reduced rather than still granting permits to 10 tasks when only 9 valid resources remain.

**Do not place two waiting mechanisms side by side without clarity**: for example, acquiring a Semaphore first and then waiting a long time on a connection queue with a different capacity can hold the permit uselessly. If a resource pool library already has reliable concurrency limits and borrow timeouts, consider using it directly instead of adding an unnecessary semaphore.

### Sizing permits

A reasonable limit must be based on **downstream capacity** and latency requirements, not just the application's thread count:

- How many active connections does the database allow, and how long does each query take?
- Does the external service enforce an **in-flight** limit, a rate limit, or both?
- Can a single task hold multiple permits from multiple resources simultaneously?
- Are multiple application instances sharing the same downstream?

**Semaphore only limits concurrency, not requests/second directly.** If each request finishes quickly, 5 permits can still produce many requests/second. If downstream enforces a time-window rate limit, a rate limiter/token bucket or another quota mechanism is needed. A limit of 10 permits **per instance** also does not automatically create a cluster-wide limit of 10 when the application runs across 20 instances.

## 11. Semaphore and bounded queues / backpressure

When producers continuously receive work, placing a Semaphore only at the downstream call site can cause **many tasks waiting to acquire** to pile up inside the executor or spawn threads, even though the number of tasks actively using downstream is bounded.

Therefore, distinguish between:

- **Semaphore:** limits **the number of tasks allowed to enter the resource-using region**.
- **Bounded BlockingQueue:** limits **the number of waiting tasks** in the queue when paired with an appropriate admission policy.
- **ThreadPoolExecutor:** limits worker count and coordinates queuing/rejection when saturated, depending on configuration.
- **Rate limiter:** limits the rate at which work starts over time.
- **Deadline/cancellation:** bounds how long a task waits and stops work that is no longer useful.

~~~text
Incoming requests
       |
 admission / bounded queue / reject
       |
 executing worker
       |
 tryAcquire(timeout) on Semaphore(N)
       |
   N active downstream operations
       |
 release exactly one permit
       |
 completed
~~~

**If you only have a Semaphore without admission control**, backlog growth and request timeouts at upper layers still remain a risk. True backpressure needs to **push back on the producer** when the system is full, such as returning an overload error, waiting briefly, or deferring with a bound.

When using a Semaphore inside a small worker pool, multiple workers can get blocked at `acquire()`, leaving no workers to serve other tasks. Sometimes it is better to place the semaphore at the admission point or design an async queue to avoid tying up workers just waiting for permits.

## 12. Deadlock, starvation, and acquiring multiple resources

### Deadlock from holding a permit while waiting for another resource

Suppose Task A holds semaphore X and waits for Y, while Task B holds Y and waits for X. Both can deadlock even though each semaphore works correctly. Common prevention measures are **consistent acquisition ordering**, deadlines, and not holding permits for long while waiting for other resources.

~~~text
Task A: acquire(X) -> wait(Y)
Task B: acquire(Y) -> wait(X)
=> wait cycle
~~~

### Self-deadlock with a single permit

A method holding `Semaphore(1)` that calls another method which also calls `acquire()` on the same semaphore can wait on itself forever, because Semaphore is **not reentrant**. Do not mechanically apply reentrant lock patterns to Semaphore.

### Staying too long in the protected region

A task holding a permit while waiting indefinitely on I/O, or performing slow synchronous logging, can starve other waiters. Set I/O timeouts, keep critical sections small, and detect abnormal **permit hold duration**.

### Multiple permits at once

`acquire(2)` is convenient when a piece of work genuinely uses two slots, but if many small tasks only need one permit, a task requesting multiple permits may wait a long time, especially in nonfair mode. Consider fairness and workload scheduling when permit requests vary widely.

**`reducePermits` and `drainPermits`:** advanced methods for reducing or draining currently available permits, not general-purpose resource pool APIs; they can put a semaphore into a low-permit or negative-permit state in specialized adjustment scenarios. Do not use them arbitrarily as a way to release resources or handle shutdown, as they make it hard to guarantee the number of tasks allowed to run.

## 13. Interruption, cancellation, and graceful shutdown

A thread waiting in `acquire()` or `tryAcquire(timeout)` can be interrupted, throwing `InterruptedException`. When code catches the exception and **does not propagate it**, it should normally restore the interrupt flag via `Thread.currentThread().interrupt()` and exit early so upper layers know a stop was requested.

**Do not release if acquire has not succeeded.** This is a classic bug when placing release inside a finally block that wraps the acquire call itself.

If the caller uses `Future.cancel(true)`, whether the task actually stops depends on where it is waiting or running. A task waiting in `Semaphore.acquire()` will respond to interruption by contract; a task executing non-interruptible library I/O may not stop immediately.

**Semaphore has no general `close()` operation to wake all waiters and block new acquires.** When shutting down a service, the component needs its own policy:

1. Stop accepting new tasks into the pipeline.
2. Cancel/interrupt waiting tasks according to a deadline.
3. Let tasks currently holding permits finish or escalate in a controlled manner.
4. Ensure all final releases complete; do not artificially increase permits to "wake" waiters if doing so would accidentally allow new work into the limited region.
5. Ensure actual resources are closed **after** tasks are no longer using them, or have a cleanup plan if tasks do not stop.

If shutdown monitoring is needed, distinguish between the number of waiting tasks, available permits, tasks currently holding permits, and the actual state of connections/resources. `availablePermits()` alone does not indicate whether it is safe to close all resources.

## 14. Fairness does not mean zero starvation

A fair semaphore reduces the chance of a waiter being repeatedly bypassed, but **does not guarantee** that every task will complete within a specific time. For example, a task holding a permit for too long, the OS scheduler pausing a worker, or `tryAcquire()` repeatedly barging can still cause large delays.

Monitor:

- **Wait time** to acquire a permit, e.g., p50/p95/p99;
- number of waiting tasks (`getQueueLength()` is an **estimate**, not an exact number for making admission decisions);
- rate of timed `tryAcquire` failures and rejections;
- **hold duration** from after acquire until release;
- max permits, permits in use, and downstream resources actually active;
- callbacks/exceptions causing releases to be missed;
- saturation in other queues/workers.

Avoid `if (sem.getQueueLength() == 0) ...` as a safe decision condition: it is only an estimate at the moment of observation. If you want fail-fast behavior, use `tryAcquire()` and make an explicit decision when it returns false.

## 15. Common mistakes

| Mistake | Consequence | How to handle |
|---|---|---|
| Calling `release()` when `acquire()` has not succeeded | Permits increase beyond limit, breaking concurrency cap | Place acquire before try/finally or use an acquired flag |
| Forgetting to release when work throws an exception | Permit leak; waiters block forever | Release in finally after a successful acquire |
| Calling `availablePermits() > 0` and assuming a slot is reserved | Race condition; check-then-act is not atomic | Use `tryAcquire()` |
| Calling downstream even when `tryAcquire()` returns false | Exceeds limit | Do not enter the restricted region without a permit |
| Using `acquireUninterruptibly()` for tasks that need to stop | Threads get stuck during shutdown | Use interruptible or timed acquire |
| Using Semaphore to protect shared variables like an owned lock | Side effects and release bugs from other threads | Use `ReentrantLock` if ownership is needed |
| Using `Semaphore(N)` and assuming all shared state access is safe | Data races can still occur among the N tasks | Synchronize state or partition data |
| Limiting to N permits per instance and assuming it is N system-wide | Multiple instances together exceed downstream capacity | Partition the budget or enforce limits at downstream |
| Holding a permit while waiting on another queue/resource | Reduced throughput or deadlock | Shorten permit-holding region, standardize acquire order |
| Thinking fairness=true guarantees strict ordering for every API | Overlooks barging by `tryAcquire()` | Understand ordering points and timeout overloads |
| Using only Semaphore without bounding the backlog | Waiting threads/tasks grow uncontrollably | Combine with bounded queue, rejection, and deadline |
| Believing `release()` can only be called by the owner | No ownership; easy to release erroneously | Control via API wrapper and finally |

## 16. Practical scenario: choosing permits and backpressure

A service only allows up to **8 concurrent outbound calls per JVM**:

1. Create a shared `Semaphore(8)` across **all code paths** calling that resource.
2. At the request boundary, apply a **request-wide deadline** and use `tryAcquire(remainingTime, unit)`.
3. If false, return an overload response or defer the work per an explicit policy; do **not** call downstream.
4. When acquire succeeds, measure **permit hold duration**, call downstream with an I/O timeout, and release in finally.
5. If ingress exceeds sustainable processing capacity, place a bounded queue/admission control and backpressure at the entry point.
6. If deploying 4 instances, check the total downstream budget: 8 × 4 = 32 potentially concurrent calls. If downstream only allows 20, a quota of 8 per instance is too high.

**Concurrency limiting differs from rate limiting.** With 8 permits and each call taking 10 ms, throughput can be much higher than 8 requests/second. If the API limits to 100 requests/minute, a plain semaphore is not enough: a dedicated rate limiter is required.

**Important principle:** the permission boundary should wrap the part that actually uses the resource, not long, unnecessary preprocessing. At the same time, if you release too early before the transaction/I/O actually finishes, the limit loses its meaning.

## 17. Checklist for proper usage

Before using Semaphore, answer:

1. **Which finite resource needs protection?** Connections, outbound requests, devices, CPU-bound tasks, or memory?
2. Is the permit count based on real resource capacity? Is the limit per-JVM or system-wide?
3. How long can the caller wait? Choose acquire, tryAcquire, or timed tryAcquire?
4. Do all paths have **exactly one release after one successful acquire**?
5. Is there any possibility of nested acquires on the same semaphore, multiple semaphores, or circular-wait deadlock?
6. Is fairness needed? Do you understand that `tryAcquire()` without timeout can barge?
7. Are there a bounded queue, overload policy, retry budget, and deadline, or is the semaphore hiding a growing backlog?
8. Do tasks holding permits have I/O timeouts and proper cleanup on exception/interrupt?
9. Are wait time, hold time, rejections, and downstream saturation being measured?
10. Have you tested cases where all permits are held, timeouts, interrupts, double releases, and shutdown?

**Summary:** Java `Semaphore` limits **the number of concurrent tasks allowed to enter a resource-using region** via permits. **Acquire first – do work in try – release in finally**, choose timeouts based on deadlines, understand fairness/ownership, and combine with bounded queues/backpressure when incoming traffic exceeds processing capacity. Semaphore helps prevent concurrent overload, but it does not create resources, does not automatically protect shared state, and does not replace rate limiting or lifecycle management.
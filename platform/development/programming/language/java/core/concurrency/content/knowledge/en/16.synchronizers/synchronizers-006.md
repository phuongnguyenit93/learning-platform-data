# Timeout and Interruption Operations in Java Synchronizers

## 1. Why Must Synchronizers Support Timeout and Interruption?

When multiple threads coordinate using `CountDownLatch`, `CyclicBarrier`, `Semaphore`, `Phaser`, or `Exchanger`, a thread often needs to **wait** for other threads, wait for enough participants, wait for a resource, or wait for a phase to complete. The problem is: a partner may fail, not get scheduled, never count down, or never release a permit.

If waiting **indefinitely**, the application can hang. If a request has already expired while a worker continues waiting, we waste threads and resources. Two key capabilities of Java concurrency are:

- **Timeout:** wait for at most a specified duration (or until an operation's deadline) and receive the corresponding result/exception when the condition is not yet met.
- **Interruption:** another thread calls `Thread.interrupt()` to **request** that the waiting thread cancel its work. This is a cooperative signal, **not a forced stop**.

**Very important:** even though all of them mean “waiting time expired”, **each synchronizer has a different contract**. For example:
- `CountDownLatch.await(timeout, unit)` returns **false** if the count has not reached 0.
- `Semaphore.tryAcquire(timeout, unit)` returns **false** if a permit could not be acquired.
- `CyclicBarrier.await(timeout, unit)` throws **TimeoutException** and **breaks the barrier for the current generation**.
- `Phaser.awaitAdvanceInterruptibly(phase, timeout, unit)` throws **TimeoutException**, but **does not automatically change the Phaser's state**.
- `Exchanger.exchange(value, timeout, unit)` throws **TimeoutException** if no partner is available yet.

You cannot apply a single shared catch/return policy across all five APIs without considering these consequences.

### Learning Objectives

1. Master the exact timeout/interruption APIs of Java SE synchronizers.
2. Distinguish **false/null**, **TimeoutException**, **InterruptedException**, and **BrokenBarrierException**.
3. Know when a timeout/interrupt affects only the waiting thread and when it **propagates to other threads**.
4. Use `finally` and a permit ownership variable to avoid **erroneous releases** when acquisition has not succeeded.
5. Understand that `Thread.interrupted()` clears the flag while `isInterrupted()` does not; know when to restore it with `Thread.currentThread().interrupt()`.
6. Build consistent cancellation and deadlines without granting a brand-new full timeout for each step.
7. Write Java 17+ runnable demos with predictable output, without relying on `sleep()` to “force” the scheduler.
8. Know the conditions for recovering `CyclicBarrier`, handling departing parties in `Phaser`, and avoiding wait-for cycles.

**Scope:** General Java concurrency in `java.util.concurrent`; framework-independent.

## 2. Timeout, Interruption, and Normal Completion: Three Paths

Suppose a thread needs to wait for a resource or a group of workers:

~~~text
               start waiting
                     |
           +---------+----------+
           |         |          |
    Condition met  timeout   interrupted
           |         |          |
        success    false/      InterruptedException
                  Timeout...    (if API supports it)
           |         |          |
     use valid     fallback   propagate or
      result       /cleanup   restore+exit
~~~

**Completion:** the condition is actually met, so execution can proceed to the next part of the work.

**Timeout:** the condition was not met within the allowed time. Depending on the API, the caller receives a boolean `false` or a `TimeoutException`; a timeout does not prove that the partner is dead or that the task was cancelled.

**Interruption:** the waiting thread has been requested to cancel. **Interruptible** waiting APIs can throw `InterruptedException` and typically **clear the interrupted status when throwing** according to their specific contract. The caller needs a follow-up policy.

Not every “waiting” API is interruptible. For example, `Semaphore.acquireUninterruptibly()` actively ignores interrupts during the waiting phase and preserves the interrupted status after finally acquiring a permit; `Phaser.awaitAdvance(phase)` is **non-interruptible**. Therefore, if you want deadline-based cancellation, you must choose the right overload from the start.

## 3. Quick Reference Table: Which API Returns false, Which Throws an Exception?

| Synchronizer | Unbounded Wait | Timed Wait | On Timeout | On Interrupt |
|---|---|---|---|---|
| `CountDownLatch` | `await()` | `await(long, TimeUnit)` | Returns `false` if count has not reached 0 | `InterruptedException` |
| `CyclicBarrier` | `await()` | `await(long, TimeUnit)` | `TimeoutException`, barrier becomes broken | `InterruptedException`; may break the barrier and cause other waiters to receive `BrokenBarrierException` |
| `Semaphore` | `acquire()` | `tryAcquire(long, TimeUnit)` | Returns `false` if no permit is available | `InterruptedException` |
| `Phaser` | `awaitAdvance(int)` (non-interruptible) | `awaitAdvanceInterruptibly(int, long, TimeUnit)` | `TimeoutException`; does not automatically break the phaser | Interruptible version: `InterruptedException`; phaser keeps its state |
| `Exchanger<V>` | `exchange(V)` | `exchange(V, long, TimeUnit)` | `TimeoutException` if not paired with a partner | `InterruptedException` |

**Return values to distinguish:** CountDownLatch's `await(timeout)` returns a boolean; CyclicBarrier's `await(timeout)` returns an **int arrival index on success**, and throws an exception on timeout. There is no single common timeout return type across all synchronizers.

The overloads listed belong to Java SE 17. Some classes have additional variants such as non-blocking `Semaphore.tryAcquire()` or `Semaphore.acquireUninterruptibly()`, so you must read each method's contract.

## 4. CountDownLatch: One-Shot Wait, Timeout Does Not “Break” the Latch

`CountDownLatch` has an initial count. Threads call `countDown()` to decrement the count; when the count reaches 0, all waiters are released. **The count cannot be reset.**

Two APIs:

~~~java
latch.await();
boolean ready = latch.await(500, TimeUnit.MILLISECONDS);
~~~

- `await()`: waits until count=0, or throws `InterruptedException`.
- `await(timeout, unit)`: returns `true` if the count reaches 0 before the time elapses; returns `false` if the time expires while the count is still greater than 0.
- On timeout, **the count does not decrement automatically**, the latch is not broken, and other waiters can continue waiting.
- If the count is already 0 at the time of the call, timed await returns `true` immediately.
- If the timeout <= 0 and the count has not reached 0, timed await returns `false` immediately without waiting.
- If the waiting thread is interrupted, the method throws `InterruptedException` and clears the flag per contract; the count **does not change just because of interruption**.
- Calling `countDown()` when the count is already 0 does not make the count negative.

### Practical Example: Waiting for Work Completion with a Deadline

~~~java
CountDownLatch completed = new CountDownLatch(3);
// Workers ensure completed.countDown() is called when their respective work finishes.
boolean allDone = completed.await(2, TimeUnit.SECONDS);
if (!allDone) {
    reportIncomplete(completed.getCount());
}
~~~

This is an illustrative method snippet; `reportIncomplete()` is application-defined. **Important condition:** workers need to call `countDown()` at the proper completion point, usually in `finally` so the caller is not left waiting forever if the work fails. However, calling `countDown` in `finally` only proves **the task has left the processing block**, not that it succeeded; errors must be communicated through a separate mechanism.

### Runnable Example 1: Timeout Returns false and Interrupt Does Not Decrement Count

Save as **CountDownLatchTimeoutInterruptDemo.java**:

~~~java
import java.util.concurrent.CountDownLatch;
import java.util.concurrent.TimeUnit;
import java.util.concurrent.atomic.AtomicBoolean;

public class CountDownLatchTimeoutInterruptDemo {
    public static void main(String[] args) throws InterruptedException {
        CountDownLatch gate = new CountDownLatch(1);

        // Timeout of 0: does not depend on timing/scheduler.
        boolean completed = gate.await(0, TimeUnit.MILLISECONDS);

        CountDownLatch started = new CountDownLatch(1);
        AtomicBoolean interrupted = new AtomicBoolean(false);
        Thread waiter = new Thread(() -> {
            started.countDown();
            try {
                gate.await();
            } catch (InterruptedException e) {
                interrupted.set(true);
                Thread.currentThread().interrupt();
            }
        }, "latch-waiter");

        waiter.start();
        started.await();
        waiter.interrupt();
        waiter.join();

        System.out.println("completed=" + completed);
        System.out.println("interrupted=" + interrupted.get());
        System.out.println("count=" + gate.getCount());

        gate.countDown(); // one actual signal after the test
        System.out.println("afterCountDown=" + gate.getCount());
    }
}
~~~

Compile/run:

~~~bash
javac CountDownLatchTimeoutInterruptDemo.java
java CountDownLatchTimeoutInterruptDemo
~~~

Output in an environment without external interruption:

~~~text
completed=false
interrupted=true
count=1
afterCountDown=0
~~~

**Why the result is deterministic:** `gate` has count=1 and no thread calls `countDown` before `main` prints. `await(0)` returns `false` immediately. The waiter may or may not have entered `await()` yet when `main` calls `interrupt`; in either schedule, `await` detects the flag and throws the exception. `join()` makes `main` wait for the waiter to finish. Only the final `gate.countDown()` statement brings the count down to 0.

**Do not conclude:** “Timeout means the producer task has stopped.” It only states that the calling thread **did not observe enough `countDown` calls within the deadline**.

## 5. CyclicBarrier: One Party's Timeout Affects the Whole Group

`CyclicBarrier` is used when a fixed number of `parties` must all reach a synchronization point before all can proceed. The barrier is reused across multiple **generations** when waits succeed.

~~~java
CyclicBarrier barrier = new CyclicBarrier(3);
int index = barrier.await(1, TimeUnit.SECONDS);
~~~

A successful `await` returns the **arrival index**, not a boolean:
- The value 0 belongs to the last thread to arrive in the generation (this thread may execute the barrier action, if one is provided).
- When all parties arrive, the barrier trips, waiters are released together, and a new generation can begin.
- If a party times out while waiting, it throws `TimeoutException` and the barrier **transitions to the broken state**.
- Other threads waiting in that generation typically receive `BrokenBarrierException`.
- If a party is interrupted while waiting, it throws `InterruptedException`, its interrupted status is cleared; the barrier becomes broken and may cause other waiters to receive `BrokenBarrierException`.
- `reset()` can return the barrier to its initial state, but resetting concurrently with waiting threads can cause `BrokenBarrierException` for the remaining waiters; do not reset arbitrarily before the group has an agreed protocol.

This is **all-or-none breakage**: if one participant cannot continue the coordination round, the other participants are not left waiting on a generation that can no longer complete.

### Runnable Example 2: One Party Timing Out Breaks the Barrier

Save as **CyclicBarrierTimeoutDemo.java**:

~~~java
import java.util.concurrent.BrokenBarrierException;
import java.util.concurrent.CyclicBarrier;
import java.util.concurrent.TimeUnit;
import java.util.concurrent.TimeoutException;

public class CyclicBarrierTimeoutDemo {
    public static void main(String[] args) throws InterruptedException {
        CyclicBarrier barrier = new CyclicBarrier(2);
        boolean timedOut = false;
        boolean otherBroken = false;

        // Only 1 party, timeout 0: definitely not enough for 2 parties.
        try {
            barrier.await(0, TimeUnit.MILLISECONDS);
        } catch (TimeoutException e) {
            timedOut = true;
        } catch (BrokenBarrierException e) {
            throw new AssertionError("Unexpected pre-broken barrier", e);
        }

        boolean broken = barrier.isBroken();

        // The next party cannot complete an already broken generation.
        try {
            barrier.await();
        } catch (BrokenBarrierException e) {
            otherBroken = true;
        }

        System.out.println("timedOut=" + timedOut);
        System.out.println("broken=" + broken);
        System.out.println("otherBroken=" + otherBroken);
    }
}
~~~

Commands:

~~~bash
javac CyclicBarrierTimeoutDemo.java
java CyclicBarrierTimeoutDemo
~~~

Stdout:

~~~text
timedOut=true
broken=true
otherBroken=true
~~~

**Explanation:** with no second party yet and timeout=0, `await` throws `TimeoutException` and the barrier is marked broken. The subsequent `await()` call does not wait forever because it is already broken; it throws `BrokenBarrierException`. The program intentionally avoids using `sleep` or creating waiters with no exit path.

### Differences from CountDownLatch

- CountDownLatch timeout **does not break the latch** and does not change its count.
- CyclicBarrier timeout **breaks the barrier**, a change that affects the entire group.
- CountDownLatch is **one-shot**; CyclicBarrier can **reuse generations** when not broken (or after a reset with a proper protocol).
- CountDownLatch waits for `countDown` signals to be issued; CyclicBarrier waits for **enough parties to call `await` in the same generation**.

### What If a Worker Fails Before Reaching the Barrier?

If a party exits its computation **before calling `await`**, the remaining parties may wait forever. Timed `await` helps bound the wait time. The caller needs to understand that a worker failing to arrive is a group-level failure, not just a matter of retrying the single thread that timed out. You must propagate the error/cancellation and decide to create a new barrier or stop the generation instead of resetting uncontrollably.

## 6. Semaphore: Timeout Returns false, Interrupt Must Preserve Ownership

`Semaphore` manages a number of permits. A thread needs a permit to enter a concurrency-limited region. Key APIs:

~~~java
semaphore.acquire();
boolean acquired = semaphore.tryAcquire(500, TimeUnit.MILLISECONDS);
semaphore.acquireUninterruptibly();
boolean immediate = semaphore.tryAcquire();
~~~

- `acquire()` waits if no permit is available, **interruptible**.
- `tryAcquire(timeout, unit)` waits up to the limit and returns `true` if a permit is acquired, `false` if it expires. Can throw `InterruptedException`.
- The no-arg `tryAcquire()` tries immediately without waiting and **can barge** even when `fairness=true`, because it does not honor other waiters queued in timed/blocking acquire.
- `acquireUninterruptibly()` keeps trying to acquire a permit even if interrupted while waiting, then preserves the interrupted status; do not use it when lifecycle must respond to cancellation immediately.
- `release()` adds a permit back; **Semaphore does not track which thread owns a permit** like a mutex does. If you release erroneously, `availablePermits` can increase in violation of the protocol.

### Critical Rule: Only Release When Acquisition Actually Succeeded

~~~java
boolean acquired = false;
try {
    acquired = semaphore.tryAcquire(300, TimeUnit.MILLISECONDS);
    if (!acquired) {
        handleOverload();
        return;
    }
    doWorkWithPermit();
} finally {
    if (acquired) {
        semaphore.release();
    }
}
~~~

This is an integrated method snippet; `handleOverload` and `doWorkWithPermit` are application-defined, and the method must handle or declare `throws InterruptedException`.

If `tryAcquire` throws `InterruptedException` **before receiving a permit**, `acquired` remains `false`; `finally` does not release. If timeout returns `false`, it also does not release. If `true`, even if the work throws an error, `finally` releases exactly one permit.

**Do not write:**

~~~java
try {
    semaphore.acquire();
    process();
} finally {
    semaphore.release(); // WRONG if acquire threw InterruptedException
}
~~~

The incorrect snippet above is inside a method with `throws InterruptedException` and application-provided variables. When `acquire` fails due to an interrupt, `release` creates a **permit that did not belong to that acquire**, breaking the concurrency limit. For `acquire()` which does not return a boolean, you can place `acquire()` **before** the `try/finally` so execution only enters `finally` after acquisition succeeds.

### Runnable Example 3: Interrupt Before Acquiring a Permit

Save as **SemaphoreTimeoutInterruptDemo.java**:

~~~java
import java.util.concurrent.CountDownLatch;
import java.util.concurrent.Semaphore;
import java.util.concurrent.TimeUnit;
import java.util.concurrent.atomic.AtomicBoolean;

public class SemaphoreTimeoutInterruptDemo {
    public static void main(String[] args) throws InterruptedException {
        Semaphore permits = new Semaphore(1, true);
        permits.acquire(); // main holds the only permit
        boolean timedAcquired =
                permits.tryAcquire(0, TimeUnit.MILLISECONDS);

        CountDownLatch started = new CountDownLatch(1);
        AtomicBoolean interrupted = new AtomicBoolean(false);
        Thread waiter = new Thread(() -> {
            started.countDown();
            try {
                permits.acquire();
                try {
                    throw new AssertionError("No permit should be available");
                } finally {
                    permits.release();
                }
            } catch (InterruptedException e) {
                interrupted.set(true);
                Thread.currentThread().interrupt();
            }
        }, "semaphore-waiter");

        try {
            waiter.start();
            started.await();
            waiter.interrupt();
            waiter.join();

            System.out.println("timedAcquired=" + timedAcquired);
            System.out.println("interrupted=" + interrupted.get());
            System.out.println("permitsWhileOwned=" +
                    permits.availablePermits());
        } finally {
            permits.release(); // main returns the permit it acquired
        }

        System.out.println("permitsAfterRelease=" +
                permits.availablePermits());
    }
}
~~~

Run:

~~~bash
javac SemaphoreTimeoutInterruptDemo.java
java SemaphoreTimeoutInterruptDemo
~~~

Stdout (without external interruption):

~~~text
timedAcquired=false
interrupted=true
permitsWhileOwned=0
permitsAfterRelease=1
~~~

**Reasoning:** `main` holds the single permit, so timed `tryAcquire(0)` cannot succeed. The `waiter` thread signals `started` and then tries to `acquire`, while `main` has not released the permit when sending the interrupt; whether the signal arrives before or during `acquire` waiting, the method throws `InterruptedException`. `main` joins `waiter` before printing. The semaphore count remains 0 until `main`'s `finally` block and becomes 1 after release.

**Note:** The block inside `waiter` has an `AssertionError` intentionally marking the unexpected success path. It does not execute under the described example conditions. In production, replace it with real business logic and manage ownership in `finally`.

## 7. Phaser: Timeout/Interrupt Does Not Automatically Break Phaser State

`Phaser` coordinates multiple **registered parties** across **phases**, allowing more flexible registration/deregistration than `CyclicBarrier`. A party calls `arrive()` to signal it has reached the current phase; `arriveAndAwaitAdvance()` signals arrival and waits for the phase to advance. A `Phaser` can be actively terminated via `forceTermination()` or by lifecycle.

Methods to distinguish:

| API | Signals arrival? | Interruptible? | Has timeout? |
|---|---|---|---|
| `arrive()` | Yes | Not a waiting operation | No |
| `arriveAndDeregister()` | Yes, and leaves the group | Not a waiting operation | No |
| `arriveAndAwaitAdvance()` | Yes, then waits for advance | **Non-interruptible** | No |
| `awaitAdvance(phase)` | **Does not** arrive; only waits for phase change | **Non-interruptible** | No |
| `awaitAdvanceInterruptibly(phase)` | Does not arrive | Yes | No |
| `awaitAdvanceInterruptibly(phase, timeout, unit)` | Does not arrive | Yes | Yes |

**Two especially dangerous mistakes:**

1. Calling `awaitAdvanceInterruptibly(phase)` assuming it automatically signals arrival; if nobody calls `arrive`, the phase may never advance.
2. A party calls `arrive()`, times out while waiting for the next phase, and then immediately calls `arriveAndDeregister()` for the **same phase** arbitrarily. Arriving a second time in the same phase is not a safe general cleanup pattern. You must design a registration/termination protocol aligned with the actual lifecycle.

### Major Difference Compared to CyclicBarrier

According to the `Phaser` Javadoc, **interruption and timeout when waiting via interruptible/timed methods do not automatically change the phaser's state**. There is no automatic broken-barrier model equivalent to `CyclicBarrier`.

Consequences:
- The caller may receive `TimeoutException`, while `getPhase()` remains unchanged.
- Other registered parties may still be waiting on this phase.
- If deciding to cancel the whole group, a coordinator must handle `forceTermination()` or another deregistration/protocol at the right time.
- `forceTermination()` can cause waiters to be released with a **negative phase** indicating termination; code must check the return value instead of assuming it successfully reached the next phase.
- `awaitAdvance(phase)` and `arriveAndAwaitAdvance()` **do not stop waiting solely because of an interrupt**, so do not use them when immediate cancellation responsiveness is required without another termination path.

### Runnable Example 4: Phaser Timeout Does Not Break It

Save as **PhaserTimeoutDemo.java**:

~~~java
import java.util.concurrent.Phaser;
import java.util.concurrent.TimeUnit;
import java.util.concurrent.TimeoutException;

public class PhaserTimeoutDemo {
    public static void main(String[] args) throws InterruptedException {
        Phaser phaser = new Phaser(2);
        int originalPhase = phaser.getPhase();

        boolean timedOut = false;
        try {
            // No party has arrived yet, so the phase cannot advance.
            phaser.awaitAdvanceInterruptibly(
                    originalPhase, 0, TimeUnit.MILLISECONDS);
        } catch (TimeoutException e) {
            timedOut = true;
        }

        System.out.println("timedOut=" + timedOut);
        System.out.println("samePhase=" +
                (phaser.getPhase() == originalPhase));
        System.out.println("terminated=" + phaser.isTerminated());

        phaser.forceTermination(); // actively close the group in the example
        System.out.println("afterForceTermination=" +
                phaser.isTerminated());
    }
}
~~~

Compile/run:

~~~bash
javac PhaserTimeoutDemo.java
java PhaserTimeoutDemo
~~~

Output:

~~~text
timedOut=true
samePhase=true
terminated=false
afterForceTermination=true
~~~

**Why?** The `Phaser` has 2 registered parties and nobody has called `arrive`. The timed await with `timeout=0` throws `TimeoutException`, **without modifying the phase or auto-terminating**. Afterward, `main` calls `forceTermination` as an explicit decision. This is a core difference from `CyclicBarrier.await(0, unit)`, which breaks the barrier on timeout.

### Timeout While Being a Registered Party

When a registered party times out after already arriving, cleanup requires knowing:
- Which phase did that party arrive at?
- Is any task waiting for it in the next phase?
- Will the group **fail fast as a whole** or can it continue with fewer parties?
- Who is allowed to deregister or call `forceTermination()`?
- Are any threads waiting in a non-interruptible method?
- Is there a risk that one thread reaches a new phase while an old party has not exited the lifecycle?

`Phaser` is flexible, but it is easy to introduce registration-count bugs if cancellation/shutdown is not clearly designed. Never “just catch `TimeoutException` and return” if it leaves other registered parties waiting forever.

## 8. Exchanger: Waiting for a Partner, Timeout Throws an Exception

`Exchanger<V>` pairs **two threads** to exchange values. Each thread calls `exchange(value)` and receives the partner's value when the two sides meet.

~~~java
Exchanger<String> exchanger = new Exchanger<>();

String partnerValue = exchanger.exchange(
        "my-value", 500, TimeUnit.MILLISECONDS);
~~~

- If a corresponding partner arrives in time, the method returns the object from the partner.
- If no partner is available within the deadline, it throws `TimeoutException`.
- If interrupted while waiting, it throws `InterruptedException` and clears the interrupted status per contract.
- There is no **persistent broken state** like `CyclicBarrier`. A single timeout does not turn an `Exchanger` into an unusable object.
- Even if one side times out, the other side may arrive later and will have to wait for a new partner or time out according to its own contract.
- Do not assume data has or has not been transferred to the partner if the application tracks/coordinates side effects outside `exchange`; determine the success point by a **normal return** from `exchange`.

### Runnable Example 5: Exchange Times Out If There Is No Partner

Save as **ExchangerTimeoutDemo.java**:

~~~java
import java.util.concurrent.Exchanger;
import java.util.concurrent.TimeUnit;
import java.util.concurrent.TimeoutException;

public class ExchangerTimeoutDemo {
    public static void main(String[] args) throws InterruptedException {
        Exchanger<String> exchanger = new Exchanger<>();
        boolean timedOut = false;

        try {
            exchanger.exchange("A", 0, TimeUnit.MILLISECONDS);
        } catch (TimeoutException e) {
            timedOut = true;
        }

        System.out.println("timedOut=" + timedOut);
    }
}
~~~

Commands:

~~~bash
javac ExchangerTimeoutDemo.java
java ExchangerTimeoutDemo
~~~

Stdout:

~~~text
timedOut=true
~~~

Only the `main` thread calls `exchange` with no partner; `timeout=0` causes the method not to wait and to throw `TimeoutException`. Using a 0 timeout in the example verifies the behavior without creating a sleep-based race.

### When a Partner Can Disappear

A thread waiting to exchange can be stranded if its partner throws an exception or takes an early return branch before calling `exchange`. Therefore:
- Timed exchange is usually more suitable than unbounded exchange in workflows with failures.
- The caller must handle `TimeoutException` and cancellation explicitly.
- Do not use `Exchanger` as a multi-element message queue or broadcast primitive: each pairing only exchanges between **two participants**.
- If you need multiple producers/consumers that do not rendezvous in pairs, `BlockingQueue` or another coordination abstraction may be more appropriate.

## 9. Interruption: How to Handle It Without Losing the Signal?

Interruptible operations such as `CountDownLatch.await`, `CyclicBarrier.await`, `Semaphore.acquire`, `Phaser.awaitAdvanceInterruptibly`, and `Exchanger.exchange` can throw `InterruptedException` when a thread is interrupted while waiting.

### Two Good Approaches

**Approach 1: Propagate the checked exception when the method allows**

~~~java
void waitForWorkers(CountDownLatch latch)
        throws InterruptedException {
    latch.await();
}
~~~

This method lets the caller decide on cancellation/fallback.

**Approach 2: Restore the interrupt flag when you cannot throw**

~~~java
@Override
public void run() {
    try {
        semaphore.acquire();
        try {
            doWork();
        } finally {
            semaphore.release();
        }
    } catch (InterruptedException e) {
        Thread.currentThread().interrupt();
        return;
    }
}
~~~

This is a fragment inside a class that has `Semaphore semaphore` and a `doWork()` method. `Runnable.run()` cannot declare `throws InterruptedException`, so restoring the flag and returning preserves the cancellation request for upper layers.

**Avoid:**

~~~java
try {
    gate.await();
} catch (InterruptedException ignored) {
    // Wrong when cancellation requests must be respected:
    // ignoring it and continuing the wait loop as if nothing happened.
}
~~~

With many synchronizers, `InterruptedException` is thrown and the interrupted status is **cleared** upon throwing. If you swallow the exception, the cancellation request can be completely lost.

### isInterrupted() vs Thread.interrupted()

| API | Which thread is checked? | Clears interrupted status? |
|---|---|---|
| `thread.isInterrupted()` | The referenced thread | No |
| `Thread.currentThread().isInterrupted()` | Current thread | No |
| `Thread.interrupted()` (static) | **Current thread** | **Yes** |
| `thread.interrupt()` | Sends an interrupt signal to the thread | Not a check/clear flag operation |

Do not call `Thread.interrupted()` in polling and accidentally continue working without handling a `true` result: it clears the flag so subsequent checks may no longer see the cancellation request.

### Interrupt Differs from Timeout

- Timeout = condition was not met within a duration.
- Interruption = another coordinator/caller requested cancellation.
- Timeout does not automatically set the interrupted status.
- Interruption is not a countdown/timer and has no guarantee of immediate stopping for code that does not check it.
- With `CyclicBarrier`, **both** can break the barrier; with `Phaser`, an interrupted/timed-out wait **does not automatically change the phaser**.
- In real applications, these states should have distinct metrics/logs.

## 10. Timing Rule: Per-Step Timeout Is Not the Total Deadline

Suppose a workflow has three waiting steps:
1. Wait for a permit for up to 300ms.
2. Wait for a latch for up to 300ms.
3. Wait for an Exchanger partner for up to 300ms.

If each step is given a **fresh 300ms**, the workflow can wait nearly **900ms** not counting processing time. If the total SLA is only 300ms, the code is incorrect.

Solution: compute a **deadline using a monotonic clock** (`System.nanoTime()`), then at each step compute the **remaining budget**.

~~~java
long budget = TimeUnit.MILLISECONDS.toNanos(300);
long deadline = System.nanoTime() + budget;

long remaining = deadline - System.nanoTime();
if (remaining <= 0L) {
    throw new TimeoutException("No time left");
}
boolean acquired = semaphore.tryAcquire(
        remaining, TimeUnit.NANOSECONDS);
if (!acquired) {
    throw new TimeoutException("Permit wait expired");
}
~~~

This is an illustrative snippet in a method with `semaphore`, imports, and exception handling. For extremely long deadlines you may need to consider overflow, but for reasonable short budgets, subtraction on monotonic `nanoTime` is the standard approach. Once acquired successfully, you must release in `finally`.

**Note:** If the three steps cannot be cancelled immediately on timeout because of blocking remote I/O that does not support interrupts, a synchronizer timeout does not turn into a hard deadline for the whole system. You must configure deadlines on each dependency.

### Difference Between Timeout and Absolute Timestamp

`System.currentTimeMillis()` is wall-clock time and can jump due to clock adjustments. `System.nanoTime()` is used to measure **elapsed time** and compare relative points within the same JVM; do not use its value as a Unix timestamp. Timed APIs use `TimeUnit` to express time units explicitly.

## 11. Cancelling One Member: “Group-Wide” Impact Varies Greatly

| Primitive | If one thread times out | Other threads |
|---|---|---|
| CountDownLatch | Waiter receives `false`, latch count unchanged | Can continue waiting for `countDown`; not woken up just because another waiter timed out |
| Semaphore | Waiter fails to get a permit, returns `false` | Other threads continue waiting/seeking permits per policy |
| CyclicBarrier | Barrier becomes broken | Waiters in the same generation receive `BrokenBarrierException`; subsequent `await` calls also fail until reset/replaced |
| Phaser | Timed await fails, phaser state does not auto-change | Other parties may still be waiting; coordinator must decide to deregister/terminate |
| Exchanger | One unpaired exchange times out | A later partner may have to keep waiting/time out itself; no persistent broken state |

**Do not treat a timeout as “nobody else needs cleanup.”** If a waiter exits while a resource or group is still registered, clarify ownership and the closing protocol.

### Memory Visibility Notes

Synchronizers also have memory consistency effects:
- `CountDownLatch`: actions before `countDown` happen-before actions after a successful `await` in another thread.
- `CyclicBarrier`: actions before `await` happen-before the barrier action and actions after a **successful** `await` in another party per Javadoc.
- `Semaphore`: actions before `release` happen-before actions after a successful `acquire` in another thread.
- `Exchanger`: actions before `exchange` on each side happen-before actions after a successful exchange pair on the other side.

**Do not apply the visibility guarantees of a successful synchronization to a timeout.** For example, `latch.await(timeout) == false` does not prove all workers have published their results; `BrokenBarrierException` is not a normal completed generation. If you need complete data, you must have a valid result-publication protocol and only read after the appropriate synchronization point.

## 12. Recovering After Timeout and Avoiding Deadlock

A timeout only says **the condition was not met on time**. Afterward, you need to decide:
- Should we continue with a **partial result**?
- Should we retry? If so, how much budget remains and will it increase load?
- Should we cancel the entire group? Who sends the signal?
- Are any children/participants still running?
- Are any permits/locks/resources needing release?
- For `Phaser`, who calls `deregister` or `forceTermination`?
- For `CyclicBarrier`, who is authorized to reset/create a new generation?
- Should timeout/interrupt causes be logged separately from task failures?

### A Typical Deadlock Wait-For Cycle

~~~text
Thread A: holds the last permit P
          then waits for latch L to reach 0

Thread B: needs permit P before calling countDown on L

A waits for B to countDown L.
B waits for A to release P.
=> wait-for cycle; timeout only helps A escape if A uses timed await
   and releases P in finally.
~~~

Do not fix this by increasing the timeout indefinitely. The right fix is **never holding a resource that another thread needs while waiting for that thread's completion**, or restructuring lifecycle/ownership.

### Invariant-Breaking Mistakes During Recovery

- `Semaphore.release()` when acquisition did not succeed creates extra permits.
- `Phaser.arriveAndDeregister()` after an arrival already counted for the current phase without checking phase state can double-arrive.
- `CyclicBarrier.reset()` while waiters are still participating causes them to receive `BrokenBarrierException`, rather than transparently “rescuing” a failed generation.
- Swallowing `InterruptedException` makes the group think cancellation was handled while the worker keeps waiting.
- Retrying after a timeout with a brand-new full budget can exceed the overall deadline.
- A party receives `TimeoutException` and proceeds to read shared results as if all sides had finished synchronizing.

## 13. Related Waiting Operations That Are Not Equivalent

Related Java SE APIs:

| API | On expiration | Interruption | Notes |
|---|---|---|---|
| `BlockingQueue.offer(e, timeout, unit)` | Returns `false` | `InterruptedException` | Waits for a slot to insert an item into the queue |
| `BlockingQueue.poll(timeout, unit)` | Returns `null` | `InterruptedException` | Waits for an available item |
| `Condition.await(timeout, unit)` | Returns `boolean` | `InterruptedException` | Subject to spurious wakeups; always check predicate under lock |
| `ReentrantLock.tryLock(timeout, unit)` | Returns `false` | `InterruptedException` | Waits for lock; only unlock if acquired |
| `Future.get(timeout, unit)` | `TimeoutException` | `InterruptedException` | Waits for `Future`; timeout does not auto-cancel the task |
| `Thread.join(timeout)` | Returns normally even on timeout | `InterruptedException` | Must check `thread.isAlive()` to know if thread is still alive |
| `LockSupport.parkNanos` | Returns after park/spurious wakeup/interrupt | Does not throw `InterruptedException` | Must check predicate/flag; not a synchronizer completion |
| `Phaser.awaitAdvance(phase)` | No timeout | **Does not throw** `InterruptedException` | Must have a termination/advance path if stopping is needed |

Do not conflate “method returned normally” with “condition was met” if the API does not report the outcome separately. For example, `Thread.join(timeout)` can return because the timeout elapsed; the caller needs to check `isAlive()`. With `LockSupport.parkNanos`, spurious returns are legal, so always use an explicit condition/predicate.

## 14. Common Mistakes with Timeout and Interruption

**Mistake 1 — Catching `TimeoutException` for `CountDownLatch.await(timeout)`.** The API returns **boolean `false`**, it does not throw `TimeoutException`.

**Mistake 2 — Thinking `CyclicBarrier.await(timeout)` returns `false`.** It throws `TimeoutException` and breaks the barrier.

**Mistake 3 — Thinking a `Phaser` timeout automatically makes all parties leave the group.** The phaser state does not change; explicit lifecycle/recovery is needed.

**Mistake 4 — Waiting on `Phaser` with `awaitAdvance()` and expecting an interrupt to break the wait.** This is a non-interruptible method.

**Mistake 5 — Calling `awaitAdvanceInterruptibly()` and forgetting to call `arrive()` per protocol.** The method only waits for the phase; it does not signal that the party has arrived.

**Mistake 6 — Releasing a semaphore permit in `finally` even when not acquired.** This can create extra permits and break the concurrency limit.

**Mistake 7 — Catching `InterruptedException` and ignoring it.** Many APIs clear the flag, so the cancellation signal is lost.

**Mistake 8 — Calling `Thread.interrupted()` when you only want to check.** The static method clears the flag.

**Mistake 9 — Assuming a timeout automatically cancels other threads.** Usually a timeout only ends the wait; `CyclicBarrier` has a group breakage mechanism, but it does not kill threads.

**Mistake 10 — Calling `reset()` on a barrier while multiple callers are waiting without a protocol.** This can mix old/new generations or cause unexpected `BrokenBarrierException`.

**Mistake 11 — Using `Exchanger` without a timeout when a partner might disappear.** One thread can wait forever.

**Mistake 12 — Treating each step's timeout as the total deadline without subtracting elapsed time.** This can exceed the SLA.

**Mistake 13 — Using wall-clock time to measure elapsed time without handling system clock changes.** Prefer `System.nanoTime()` with a proper budget.

**Mistake 14 — Treating `await(timeout) == false` as all workers failed.** It only means the count did not reach zero within the deadline; individual worker outcomes must be tracked separately.

**Mistake 15 — Thinking fair `Semaphore.tryAcquire()` always respects queue order.** The no-arg overload can barge.

**Mistake 16 — Thinking a semaphore knows its owner like `ReentrantLock`.** Semaphore permits are not tied to an owning thread; erroneous releases are dangerous.

**Mistake 17 — Reading generation data as if it succeeded when the barrier is broken.** `BrokenBarrierException` signals that coordination failed; there is no valid completed generation.

**Mistake 18 — Calling `Phaser.arriveAndDeregister` twice in the same phase to “fix” a timeout.** This can skew party/arrival counts.

**Mistake 19 — Assuming `timeout=0` always fails even when the condition is already ready.** If the latch count is already 0 or a semaphore has a permit, the API can succeed immediately; `timeout=0` only skips **waiting**.

**Mistake 20 — Using `Thread.sleep` to coordinate tests.** `sleep` does not guarantee a thread is waiting in the intended API; use a latch, `timeout=0`, or explicit checkpoints.

## 15. Code Review and Operations Checklist

- [ ] Is the right primitive chosen: latch, barrier, permits, phases, or exchange?
- [ ] Have the return type and exceptions of the **exact overload** been checked?
- [ ] Does timeout return `false`, `null`, or throw `TimeoutException`?
- [ ] Does interruption throw `InterruptedException`, or is the method non-interruptible?
- [ ] Does timeout/interrupt affect **group-wide** state?
- [ ] When `CyclicBarrier` breaks, is the failure propagated to the other parties?
- [ ] Does `Phaser` have a registration/arrival/termination protocol if a party cancels?
- [ ] Does `Semaphore` release only the exact number of permits acquired?
- [ ] Should the calling thread propagate or restore the interrupt flag?
- [ ] Will lost consumers/partners cause other threads to wait forever?
- [ ] Is there an overall deadline with remaining budget instead of per-step timeouts?
- [ ] After a timeout, do any tasks/workers keep running and consuming resources?
- [ ] Do logs/metrics distinguish completed, timed out, interrupted, and broken?
- [ ] Do you avoid holding a lock/permit while waiting for a task that needs that same resource?
- [ ] Do tests use `CountDownLatch` or `timeout=0` instead of `sleep` and timing assumptions?
- [ ] When using `shutdownNow`/`cancel`, is it understood that this is a **cancellation request**?
- [ ] Is memory visibility guaranteed before using shared results?
- [ ] Is ownership of the executor, barrier/phaser, and cleanup clearly defined?

## 16. Practice Exercises with Answers

**Question 1.** `CountDownLatch` has count=2; `await(0, MILLISECONDS)` is called with no `countDown` yet. What is the result?

**Answer:** `false`, without waiting; count remains 2.

**Question 2.** `CyclicBarrier` has 3 parties; only one party waits and times out. What will the other two parties receive if they are waiting on that generation?

**Answer:** The remaining waiters typically receive `BrokenBarrierException`, and the barrier is broken. A recovery protocol is needed; `reset()` is not automatically safe in all situations.

**Question 3.** `Semaphore` has permit=0; `tryAcquire(100, MILLISECONDS)` is called and nobody releases. What is the result?

**Answer:** `false` after failing to acquire a permit within the deadline (unless the thread is interrupted, in which case `InterruptedException` is thrown).

**Question 4.** `Semaphore.acquire()` throws `InterruptedException` before acquiring a permit. Should `release()` be called?

**Answer:** No. Only release if acquisition succeeded.

**Question 5.** `Phaser` has 2 parties; one thread times out in `awaitAdvanceInterruptibly(phase, timeout, unit)`. Does the `Phaser` automatically break like `CyclicBarrier`?

**Answer:** No. Timeout/interruption of the wait does not automatically alter phaser state; recovery/termination must be decided by the application.

**Question 6.** `awaitAdvance(phase)` is called, and another thread interrupts the waiter. Is it required to throw `InterruptedException`?

**Answer:** No. This is the non-interruptible version; if you need cancellation responsiveness while waiting, use `awaitAdvanceInterruptibly` and an appropriate lifecycle protocol.

**Question 7.** With `Exchanger`, only one thread calls `exchange("A", 0, MILLISECONDS)`. What is the result?

**Answer:** `TimeoutException` if there is no partner, not `false` or `null`.

**Question 8.** A thread is interrupted during `CountDownLatch.await()`. Does the count decrement automatically?

**Answer:** No. The interrupt only ends that thread's wait; `countDown` must be issued by the responsible party.

**Question 9.** A workflow has three steps, each with a 300ms timeout, and a total SLA of 300ms. What is the problem?

**Answer:** Total waiting time can be nearly 900ms. A shared deadline and remaining budget must be used.

**Question 10.** A `CyclicBarrier` is already broken. Can subsequent `await` calls succeed normally without resetting?

**Answer:** No. `await` will throw `BrokenBarrierException` until an appropriate reset or new barrier policy is applied.

**Question 11.** Is `Thread.interrupted()` the same as `currentThread().isInterrupted()`?

**Answer:** Both check the current thread when written properly, but `Thread.interrupted()` **clears the flag**, whereas `isInterrupted()` does not.

**Question 12.** Does a timeout on `Future.get(timeout)` automatically cancel the `Future` task?

**Answer:** No. That is the timeout of the caller waiting for the result. To cancel, you must explicitly call `cancel` per the `Future` contract.

## 17. Official References

- **CountDownLatch (Java SE 17):** https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/concurrent/CountDownLatch.html
- **CyclicBarrier (Java SE 17):** https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/concurrent/CyclicBarrier.html
- **Semaphore (Java SE 17):** https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/concurrent/Semaphore.html
- **Phaser (Java SE 17):** https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/concurrent/Phaser.html
- **Exchanger (Java SE 17):** https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/concurrent/Exchanger.html
- **TimeUnit (Java SE 17):** https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/concurrent/TimeUnit.html
- **Thread (Java SE 17):** https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/lang/Thread.html
- **JLS 17, Threads and Locks:** https://docs.oracle.com/javase/specs/jls/se17/html/jls-17.html

**Summary:** Timeout and interruption enable **bounded waiting and cooperative cancellation**, but each synchronizer has its own contract: **latch/semaphore return boolean `false`; barrier timeout throws an exception and breaks the barrier; phaser timeout throws an exception without automatically changing state; exchanger timeout throws an exception when no partner is present**. Proper handling includes an overall deadline, preserving interrupted status, permit ownership/cleanup, group state recovery, and avoiding resource wait-for cycles.

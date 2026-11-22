# Permit Counting and Preventing Permit Leaks in Java Synchronizers

## 1. The Problem: Concurrency Limits Must Always Hold

An application might allow at most three concurrent requests to call an external service, five tasks to share an expensive connection pool, or two heavy data transformations to run at once. Without a limit, hundreds of threads can contend for the same resource simultaneously and overload the system.

`java.util.concurrent.Semaphore` is a synchronizer that manages a **permit count**. A thread that wants to enter a bounded section of code must **acquire** the required number of permits; when it finishes using the resource, it must **release** the exact number of permits it took.

The core of this lesson is a very simple invariant that is easy to get wrong:

> **Every successful acquire must have exactly one corresponding release, with the exact same number of permits; an unsuccessful acquire must never be released.**

If a permit is acquired and forgotten, the system suffers a **permit leak**: capacity degrades over time, and eventually new work may wait indefinitely. If more permits are released than were acquired, or if `release()` is called after a failed acquire, that is an **over-release**: the system can admit more concurrent work than the intended limit, defeating the purpose of the semaphore.

This article covers **general Java concurrency**, focusing on the standard JDK APIs without relying on any specific framework.

### Objectives

After this lesson, you should be able to:

1. Understand what `Semaphore` is, what `availablePermits()` reflects, and why permits **have no ownership** like locks.
2. Write correct `acquire()`/`release()` and `tryAcquire()`/`release()` protocols, including timeouts and interrupts.
3. Place `try/finally` in the exact right position so permits are neither leaked nor released when never logically owned.
4. Distinguish between **permit leak**, **over-release**, **double release**, **starvation**, and **deadlock**.
5. Work with `acquire(n)`, `release(n)`, fairness, shutdown, and retries without corrupting the permit count.
6. Design metrics, tests, and code reviews to detect permit-return bugs under concurrent workloads.
7. Know when to choose `Semaphore`, `BlockingQueue`, `ThreadPoolExecutor`, or another resource-management mechanism.

## 2. How Does a Semaphore Count Permits?

A semaphore maintains a permit count state. With `new Semaphore(3)`:

~~~text
Initial:                    available = 3
Task A acquire():           available = 2
Task B acquire():           available = 1
Task C acquire():           available = 0
Task D acquire():           must wait
Task A release():           available = 1
Task D can acquire():       available = 0
~~~

The acquire/release operations update this state according to the concurrency contract. Multiple threads can call them concurrently without having to guard the internal counter with `synchronized`.

### 2.1. Key API Semantics

| API | Meaning and Things to Remember |
| --- | --- |
| `new Semaphore(permits)` | Creates a synchronizer with an initial permit count |
| `new Semaphore(permits, true)` | Selects a fair policy when threads contend |
| `acquire()` | Waits to acquire one permit; may throw `InterruptedException` |
| `acquire(int n)` | Waits to acquire **n permits** in a single synchronized semaphore operation |
| `acquireUninterruptibly()` | Waits without throwing `InterruptedException` like `acquire()`; consider cancellation |
| `tryAcquire()` | Attempts to acquire one permit immediately, returns boolean, does not wait |
| `tryAcquire(timeout, unit)` | Waits up to the bound if no permit is available; may be interrupted |
| `tryAcquire(n, timeout, unit)` | Attempts to acquire n permits within the specified duration |
| `release()` / `release(n)` | Returns the specified number of permits per protocol; does not verify caller acquired them |
| `availablePermits()` | Current permit count at the moment of reading, **not a reservation** |
| `drainPermits()` | Acquires and returns all immediately available permits; low-level management API |
| `getQueueLength()` | Estimate of the number of threads waiting to acquire |
| `hasQueuedThreads()` | Hint that waiters may exist, not an invariant truth |
| `isFair()` | Indicates whether the semaphore is configured with fairness |

The `acquire(n)` and `release(n)` methods require a positive `n`; an invalid `n` may throw `IllegalArgumentException`. Use the multi-permit API instead of looping single `acquire()` calls when a task needs **all n permits together** before starting. That avoids the "holding a partial set of permits while waiting for the rest" state caused by manual looping.

### 2.2. A Semaphore Is Not an Owned Lock

`ReentrantLock` has an owning thread; another thread attempting to `unlock()` without ownership is rejected. `Semaphore` **does not require the thread calling `release()` to be the thread that called `acquire()`**: one thread can release a permit that another thread previously acquired.

That capability is useful for certain handoff protocols, but it is also a source of bugs:

~~~java
// WRONG: Semaphore does not verify a prior acquire.
// Any thread can increase the permit count with this line.
semaphore.release();
~~~

Just because `release()` does not throw an exception does not mean you returned a valid permit. **Permit ownership is a rule that the program itself must enforce**, not something the semaphore enforces.

### 2.3. Permit Count Is Not Always a "Fixed Capacity"

A semaphore can be created with 0 permits to act as a **producer-consumer signal/permit**, or with another value depending on the protocol. Java's `Semaphore` also exposes low-level adjustment operations. Therefore, `availablePermits()` is not a number strictly upper-bounded by the constructor argument.

For standard concurrency-limiting usage, we define a **logical capacity N** and maintain it ourselves:

~~~text
0 <= availablePermits <= N
inFlight + availablePermits = N
~~~

This invariant holds only if every acquire/release strictly follows the protocol and there are no `drainPermits`, permit adjustments, or out-of-band grants. `inFlight` must be defined accurately (permits acquired but not yet released), not simply as the number of submitted tasks.

## 3. How Do Permit Leak and Over-Release Differ?

### 3.1. Permit Leak

A task calls `acquire()` successfully, then hits an exception, returns early, or is cancelled without calling `release()`. Each lost permit leaves the semaphore with fewer entry slots than intended.

~~~text
Initial capacity: 3
Task A takes 1 permit and exits without releasing
Max available afterward: 2
Task B leaks another 1 permit
Max available afterward: 1
Task C leaks a permit
Available = 0, no further progress if nobody releases
~~~

This is not an "object leak" or "GC failing to reclaim memory." A permit is **synchronization state**. The garbage collector cannot know that a task forgot to return a permit and will never call `release()` on its behalf.

### 3.2. Over-Release

A task that never acquired a permit calls `release()`, or a single acquire has two cleanup paths that both release. The permit count can **exceed the logical capacity**.

~~~text
Logical capacity N = 2
Initial available = 2
One mistaken release() -> available = 3
Three tasks can acquire() concurrently
=> the maximum limit of 2 has been broken.
~~~

For a semaphore guarding connections, over-release is just as dangerous as a leak: instead of reduced throughput, you can trigger **downstream overload**, resource exhaustion, and cascading timeouts.

### 3.3. Double Release

Double release is a form of over-release:

- `release()` in `catch` and then `release()` again in `finally`.
- An inner method releases on its own, and the outer caller also releases.
- A task times out and cleanup releases, then the late completion callback releases as well.
- Retry logic tracks an `acquired` flag incorrectly, releasing again after another attempt.

The fix is not merely "remember not to release twice," but establishing **one single place responsible for releasing**, following clear logical ownership.

## 4. The Safest Acquire/Release Pattern

### 4.1. Acquire Outside, `finally` Inside

The standard pattern with `acquire()`:

~~~java
// Java snippet, not a standalone program.
semaphore.acquire(); // May wait and throw InterruptedException.
try {
    performProtectedWork();
} finally {
    semaphore.release();
}
~~~

**Why is `acquire()` placed before `try`?** If `acquire()` throws `InterruptedException` because it failed to obtain a permit, `release()` must not run. Placing `acquire()` outside guarantees that execution enters the `try/finally` block only when the acquire has returned normally.

**Why is `release()` placed in `finally`?** If `performProtectedWork()` throws an exception or returns, `finally` is still executed under normal Java control flow. This prevents leaks on normal exit paths (though not against JVM crashes or `Runtime.halt()`).

### 4.2. Dangerous Pattern: `finally` Wrapping `acquire()`

~~~java
// WRONG: if acquire is interrupted before succeeding, it still releases.
try {
    semaphore.acquire();
    performProtectedWork();
} finally {
    semaphore.release();
}
~~~

If `acquire()` fails, this snippet over-releases. This mistake is especially common when developers habitually wrap any resource acquisition inside `try/finally`.

An alternative pattern when complex branching is unavoidable is keeping a boolean `acquired`, setting it to `true` **only after acquire succeeds**, and releasing only when the boolean is `true`. Unless genuinely needed, however, acquiring before `try` is shorter and less error-prone.

### 4.3. Controlling the Lifetime of External Resources

Call `release()` at the exact moment **usage of the bounded resource actually ends**. If a connection is serving asynchronous I/O, releasing right after **submitting the I/O** can be too early: the request is still using the connection while the permit has already been handed to another request.

Conversely, holding a permit across an unrelated callback after the bounded work has finished reduces throughput. Define the resource boundary before choosing where `try/finally` sits.

## 5. Example 1 — Basic Permit Accounting (Java 17+)

Create `PermitAccountingDemo.java`:

~~~java
import java.util.concurrent.Semaphore;

public class PermitAccountingDemo {
    public static void main(String[] args)
            throws InterruptedException {
        Semaphore semaphore = new Semaphore(3);

        System.out.println("initial = "
            + semaphore.availablePermits());

        semaphore.acquire(2);
        System.out.println("after acquire(2) = "
            + semaphore.availablePermits());

        try {
            System.out.println("inside = true");
        } finally {
            semaphore.release(2);
        }

        System.out.println("after release(2) = "
            + semaphore.availablePermits());
    }
}
~~~

Compile and run:

~~~bash
javac PermitAccountingDemo.java
java PermitAccountingDemo
~~~

Stdout:

~~~text
initial = 3
after acquire(2) = 1
inside = true
after release(2) = 3
~~~

Two permits are acquired in a single `acquire(2)` call; `finally` returns **exactly two** via `release(2)`. If only one permit were returned, the final available count would be 2, indicating a leak of one permit. If three were returned, the final available count would be 4, indicating an over-release of one permit.

There are no other threads in this example, so `availablePermits()` reflects the counter at deterministic points. In a multi-threaded system, the value can change immediately after being observed.

### 5.1. Why Not Loop Single-Permit Acquires?

Suppose a task needs two permits and is written as:

~~~java
// Only illustrates the risk with two independent acquire calls.
semaphore.acquire();
semaphore.acquire();
try {
    doWork();
} finally {
    semaphore.release(2);
}
~~~

If the second `acquire()` is interrupted, the first has already succeeded while the `finally` block has not yet been entered: **one permit is leaked**. This approach can also run into hold-and-wait stalls when multiple tasks each hold partial permits.

Prefer `acquire(2)` when two permits are needed simultaneously; if multiple distinct resources must be acquired, design a strict rollback or lock-ordering protocol.

## 6. `tryAcquire`: Release Only When Acquisition Actually Succeeds

`tryAcquire()` or `tryAcquire(timeout, unit)` returns a boolean:

- `true`: the call **acquired the requested permits**.
- `false`: no permits were granted by that call; **do not release**.
- The timed overload may throw `InterruptedException` if interrupted; do not release for an unsuccessful call.

Standard pattern:

~~~java
// Java snippet, not a standalone program.
boolean acquired =
    semaphore.tryAcquire(200, TimeUnit.MILLISECONDS);

if (!acquired) {
    return false;
}

try {
    performProtectedWork();
    return true;
} finally {
    semaphore.release();
}
~~~

Common buggy pattern:

~~~java
// WRONG: over-release when tryAcquire returns false.
try {
    if (!semaphore.tryAcquire()) {
        return;
    }
    doWork();
} finally {
    semaphore.release();
}
~~~

Because `return` inside `try` **still runs `finally`**, the `tryAcquire` false branch above still calls `release()`. One small mistake can push the permit count past capacity with no warning exception.

### 6.1. Example 2 — Timeout Does Not Create Phantom Permits (Java 17+)

Create `TimedAcquireDemo.java`:

~~~java
import java.util.concurrent.Semaphore;
import java.util.concurrent.TimeUnit;

public class TimedAcquireDemo {
    public static void main(String[] args)
            throws InterruptedException {
        Semaphore permits = new Semaphore(1);
        permits.acquire();

        try {
            boolean gotAnother =
                permits.tryAcquire(0, TimeUnit.MILLISECONDS);

            System.out.println("second acquired = " + gotAnother);
            System.out.println("while held = "
                + permits.availablePermits());

            if (gotAnother) {
                permits.release();
            }
        } finally {
            permits.release(); // Release the initial permit exactly once.
        }

        System.out.println("after = "
            + permits.availablePermits());
    }
}
~~~

Compile and run:

~~~bash
javac TimedAcquireDemo.java
java TimedAcquireDemo
~~~

Stdout:

~~~text
second acquired = false
while held = 0
after = 1
~~~

The same thread can call `tryAcquire` again because a semaphore **has no reentrancy/ownership** like a mutex; however, when available is 0, the attempt with timeout 0 returns `false`. Because the failed attempt granted no permit, there is no corresponding release.

The `finally` block only returns the permit acquired earlier, so the final count is 1 rather than 2. This is a direct check for catching over-release bugs.

## 7. `InterruptedException`: Why `finally` Must Sit at the Right Boundary

`Semaphore.acquire()` is an interruptible wait. If a thread is interrupted while waiting, it can throw `InterruptedException` with **no permit granted by that acquire call**.

Correct pattern:

~~~java
// Method snippet in production code; not standalone.
void guardedJob() throws InterruptedException {
    semaphore.acquire();
    try {
        work();
    } finally {
        semaphore.release();
    }
}
~~~

If `work()` reacts to an interrupt mid-critical-section, `finally` still releases when the method exits via exception or return. If `acquire()` is interrupted and does not succeed, control never enters the `try` block, so no release occurs.

### 7.1. Example 3 — Worker Interrupted Without a Permit (Java 17+)

Create `InterruptedAcquireDemo.java`:

~~~java
import java.util.concurrent.CountDownLatch;
import java.util.concurrent.Semaphore;
import java.util.concurrent.atomic.AtomicBoolean;

public class InterruptedAcquireDemo {
    public static void main(String[] args)
            throws InterruptedException {
        Semaphore semaphore = new Semaphore(0);
        CountDownLatch entered = new CountDownLatch(1);
        AtomicBoolean noticed = new AtomicBoolean();

        Thread worker = new Thread(() -> {
            entered.countDown();
            try {
                semaphore.acquire();
                try {
                    throw new AssertionError(
                        "This acquisition should not succeed"
                    );
                } finally {
                    semaphore.release();
                }
            } catch (InterruptedException ex) {
                noticed.set(true);
                Thread.currentThread().interrupt();
            }
        }, "waiting-worker");

        worker.start();
        entered.await();
        worker.interrupt();
        worker.join();

        System.out.println("interrupted = " + noticed.get());
        System.out.println("available = "
            + semaphore.availablePermits());
    }
}
~~~

Compile and run:

~~~bash
javac InterruptedAcquireDemo.java
java InterruptedAcquireDemo
~~~

Stdout with no external interference:

~~~text
interrupted = true
available = 0
~~~

`entered` confirms that the worker reached the code region before `main` sent the interrupt, though it does not need to guarantee the worker was already blocked inside `acquire()`: if the interrupt arrives **before** `acquire()`, `acquire()` still responds with `InterruptedException`; if it arrives **while waiting**, the result is the same. Nobody releases a permit into the semaphore initialized to 0.

`semaphore.release()` sits inside `finally` **only after** `acquire()` returns normally. Because that cannot happen in this interrupted example with no permit producer, the final available count remains 0. Restoring the interrupt flag in `catch` lets higher layers of the worker know the signal arrived instead of silently swallowing it.

### 7.2. `acquireUninterruptibly` Does Not Mean "More Cancellation-Safe"

`acquireUninterruptibly()` waits without propagating `InterruptedException` like `acquire()`. It can keep waiting for a permit even after the caller has requested cancellation. In systems that require responsive shutdown, using it indiscriminately can leave tasks stuck.

Unless there is a clear reason to wait uninterruptibly, prefer `acquire()` or `tryAcquire(timeout, unit)` combined with deadlines and a cancellation strategy.

## 8. Practical Concurrency Limiting with Multiple Workers

A semaphore limits **entry into a section of code**, not the number of tasks submitted to an executor. If 1,000 tasks are submitted to a pool and only two permits exist, many tasks may remain queued or blocked in `acquire()`; that can saturate the pool, increase latency, and cause **thread pool starvation** when tasks in the pool depend on one another.

### 8.1. Example 4 — Three Tasks, Maximum Two Permits (Java 17+)

Create `BoundedWorkerDemo.java`:

~~~java
import java.util.concurrent.CountDownLatch;
import java.util.concurrent.ExecutorService;
import java.util.concurrent.Executors;
import java.util.concurrent.Future;
import java.util.concurrent.Semaphore;
import java.util.concurrent.TimeUnit;
import java.util.concurrent.atomic.AtomicInteger;

public class BoundedWorkerDemo {
    public static void main(String[] args) throws Exception {
        Semaphore permits = new Semaphore(2);
        ExecutorService pool = Executors.newFixedThreadPool(3);
        CountDownLatch twoEntered = new CountDownLatch(2);
        CountDownLatch releaseWork = new CountDownLatch(1);
        AtomicInteger completed = new AtomicInteger();

        try {
            Future<?>[] tasks = new Future<?>[3];

            for (int i = 0; i < tasks.length; i++) {
                tasks[i] = pool.submit(() -> {
                    permits.acquire();
                    try {
                        twoEntered.countDown();
                        releaseWork.await();
                        completed.incrementAndGet();
                    } finally {
                        permits.release();
                    }
                    return null;
                });
            }

            twoEntered.await();
            System.out.println("available while held = "
                + permits.availablePermits());

            releaseWork.countDown();
            for (Future<?> task : tasks) {
                task.get();
            }

            System.out.println("completed = " + completed.get());
            System.out.println("available after = "
                + permits.availablePermits());
        } finally {
            releaseWork.countDown();
            pool.shutdownNow();
            pool.awaitTermination(5, TimeUnit.SECONDS);
        }
    }
}
~~~

Compile and run:

~~~bash
javac BoundedWorkerDemo.java
java BoundedWorkerDemo
~~~

Stdout when tasks complete normally:

~~~text
available while held = 0
completed = 3
available after = 2
~~~

**Why is this conclusive?**

- The first two tasks to acquire permits call `twoEntered.countDown()` and then wait on `releaseWork`; once the latch reaches 0, **two permits are definitely being held**.
- The third task cannot pass `acquire()` while both permits remain held, regardless of which worker the scheduler picks first.
- `main` prints `available = 0` and then opens `releaseWork`. All three tasks complete and each returns exactly one permit via `finally`.
- `Future.get()` waits for each task and surfaces any task failure as an `ExecutionException`; therefore the final output lines cannot print prematurely.
- None of the workers print directly, so scheduler ordering cannot alter stdout ordering.

**Looking further ahead:** A semaphore does not guarantee fairness by default. The program enforces the permit count, but it does not require tasks to receive permits in `submit` order. If your SLA requires wait ordering, evaluate fairness, queue types, or a dedicated worker model.

### 8.2. Holding Permits Across Long Blocking Calls

If every task holds a permit and waits on I/O without a timeout, two permits can stay occupied for a very long time. This is not necessarily a **permit leak**: the permits will still be returned if the I/O finishes. Yet the operational symptom—"sustained `available=0`, growing queue"—can look similar.

To diagnose it, measure **permit hold duration**, distinguish live tasks from exited tasks, and identify where downstream calls are blocking.

### 8.3. Do Not Use Semaphore to Replace Every Queue

If work has already been accepted and needs **exactly-once distribution** to workers, `BlockingQueue.take()`/`poll()` or a `ThreadPoolExecutor` with a bounded queue can express ownership more clearly. A semaphore does not store the task itself and does not confirm that a task has finished processing.

## 9. Over-Release Can Happen Without Any Exception

Unlike `ReentrantLock.unlock()`, `Semaphore.release()` does not check an owner. Consequently, an erroneous `release()` call can **inflate the permit count** without throwing `IllegalMonitorStateException`.

### 9.1. Example 5 — Intentionally Triggering an Over-Release Bug (Java 17+)

Create `OverReleaseDemo.java`:

~~~java
import java.util.concurrent.Semaphore;

public class OverReleaseDemo {
    public static void main(String[] args) {
        Semaphore semaphore = new Semaphore(1);

        // INTENTIONALLY WRONG: nobody has acquired, yet release is called.
        semaphore.release();

        System.out.println("available = "
            + semaphore.availablePermits());
        System.out.println("limit violated = "
            + (semaphore.availablePermits() > 1));
    }
}
~~~

Compile and run:

~~~bash
javac OverReleaseDemo.java
java OverReleaseDemo
~~~

Stdout:

~~~text
available = 2
limit violated = true
~~~

This is a **demonstration of buggy behavior, not a pattern to adopt**. Java does not enforce `available <= constructorValue`. If `new Semaphore(1)` is treated as a mutex limiting execution to one task, a stray `release()` allows two tasks to acquire concurrently—breaking mutual exclusion.

### 9.2. Double Release in `catch` and `finally`

~~~java
// WRONG: releases twice when doWork throws an exception.
semaphore.acquire();
try {
    doWork();
} catch (RuntimeException ex) {
    semaphore.release();
    throw ex;
} finally {
    semaphore.release();
}
~~~

The fix: **a single `finally` block** is responsible for releasing; `catch` only logs or rethrows the error and must not release if `finally` already does. If an external callback also releases, ownership handoff must be explicit; never let two layers both assume final responsibility.

## 10. Using `try-with-resources` to Reduce the Risk of Forgetting to Release

When an application has many methods that may return early, throw, or call helpers, a wrapper with explicit ownership makes code review easier. Java allows `try-with-resources` with an `AutoCloseable` object representing a **permit lease**.

### 10.1. Lease Design: Acquire Before Creating the Token

A lease should:

- Be created **only after acquire succeeds**.
- Know the number of permits acquired and the target semaphore to release to.
- Take effect **at most once** on `close()`, even if a caller accidentally closes it multiple times.
- Never transfer ownership elsewhere without an explicit protocol.
- Never perform I/O, logging, or non-deterministic business logic inside `close()`.

### 10.2. Example 6 — `PermitLease` `AutoCloseable` (Java 17+)

Create `PermitLeaseDemo.java`:

~~~java
import java.util.concurrent.Semaphore;
import java.util.concurrent.atomic.AtomicBoolean;

public class PermitLeaseDemo {
    static final class PermitLease implements AutoCloseable {
        private final Semaphore semaphore;
        private final int permits;
        private final AtomicBoolean closed = new AtomicBoolean();

        private PermitLease(Semaphore semaphore, int permits) {
            this.semaphore = semaphore;
            this.permits = permits;
        }

        static PermitLease acquire(
                Semaphore semaphore, int permits)
                throws InterruptedException {
            if (permits <= 0) {
                throw new IllegalArgumentException(
                    "permits must be positive"
                );
            }

            semaphore.acquire(permits);
            return new PermitLease(semaphore, permits);
        }

        @Override
        public void close() {
            if (closed.compareAndSet(false, true)) {
                semaphore.release(permits);
            }
        }
    }

    public static void main(String[] args)
            throws InterruptedException {
        Semaphore semaphore = new Semaphore(2);

        try (PermitLease lease =
                 PermitLease.acquire(semaphore, 2)) {
            System.out.println("inside = "
                + semaphore.availablePermits());
        }

        System.out.println("after close = "
            + semaphore.availablePermits());
    }
}
~~~

Compile and run:

~~~bash
javac PermitLeaseDemo.java
java PermitLeaseDemo
~~~

Stdout:

~~~text
inside = 0
after close = 2
~~~

`PermitLease.acquire` does not instantiate a lease object before `semaphore.acquire(permits)` succeeds. If interrupted while waiting, the method throws an exception and no lease exists to close; there is no over-release. Once acquired, `try-with-resources` invokes `close()` at the end of the scope even if the body throws an exception or returns.

`AtomicBoolean` ensures `close()` takes effect exactly once if called repeatedly. This is **object-level lease protection**, not a substitute for system-wide ownership design: two separate leases must never represent the same underlying permit grant without an explicit transfer protocol.

### 10.3. Limitations of a Wrapper

- `AutoCloseable` does not automatically return external resources if the process crashes. It only calls `close()` when leaving the `try-with-resources` scope under Java control flow.
- Do not let a lease be held for an asynchronous task **beyond the lifetime of the `try` block** if that task still needs the permit.
- If an API genuinely needs to hand off release responsibility to another thread, use an explicit transfer of ownership; a wrapper scoped to the originating block would release too early.
- When bundling multiple permits, create a single lease with the exact permit count rather than multiple leases for the same logical acquisition.
- Using `AtomicBoolean` adds an extra allocation, so do not assume a lease wrapper is throughput-optimal for every hot path. For short sections of code, a clean `try/finally` can be simpler and faster.

## 11. Bulk Permits: `acquire(n)` and `release(n)` Must Balance

If a task consumes two units of capacity, such as two logical GPU slots, use `acquire(2)` and `release(2)`.

~~~java
// Java snippet, not a standalone program.
semaphore.acquire(2);
try {
    processUsingTwoSlots();
} finally {
    semaphore.release(2);
}
~~~

Keep in mind:

- Verify `n > 0` and that it matches the required business capacity.
- Never acquire 2 and release 1 or 3.
- When using `tryAcquire(2, timeout, unit)`, call `release(2)` only when the attempt returns `true`.
- If a task requires all N permits for an exclusive operation, it may wait a long time while smaller tasks continuously acquire permits; consider fairness and starvation.
- Do not mix holding one permit while waiting for additional permits across different code paths without a deadlock-avoidance and rollback plan.

### 11.1. Example 7 — Success and Failure When Two Permits Are Needed (Java 17+)

Create `BulkPermitDemo.java`:

~~~java
import java.util.concurrent.Semaphore;
import java.util.concurrent.TimeUnit;

public class BulkPermitDemo {
    public static void main(String[] args)
            throws InterruptedException {
        Semaphore semaphore = new Semaphore(3);
        semaphore.acquire(2);

        try {
            boolean anotherTwo =
                semaphore.tryAcquire(
                    2, 0, TimeUnit.MILLISECONDS
                );

            System.out.println("second two = " + anotherTwo);
            System.out.println("available inside = "
                + semaphore.availablePermits());

            if (anotherTwo) {
                semaphore.release(2);
            }
        } finally {
            semaphore.release(2);
        }

        System.out.println("available after = "
            + semaphore.availablePermits());
    }
}
~~~

Compile and run:

~~~bash
javac BulkPermitDemo.java
java BulkPermitDemo
~~~

Stdout:

~~~text
second two = false
available inside = 1
available after = 3
~~~

After the first `acquire(2)`, only one permit remains. The `tryAcquire(2, 0, ...)` call cannot obtain two permits, returns `false`, and grants nothing. Only the `finally` block of the successful acquire calls `release(2)`, bringing the total back to 3.

**Never use `availablePermits()` to manually split or decide permit acquisition:** between reading the count and calling `acquire`, another thread can change the count. If you need a batch of `n` permits, request them via `acquire(n)`/`tryAcquire(n, ...)` for atomic acquisition per contract.

## 12. Fairness: Preventing Barging Does Not Prevent Leaks

`new Semaphore(permits, true)` applies a **fair** policy at API acquisition points. Under contention, it prioritizes waiting threads according to internal queuing order rather than letting newly arriving threads barge ahead repeatedly as in nonfair mode.

However, fairness does not solve every problem:

- **Permit leaks**: a lost permit stays lost, regardless of fairness.
- **Over-release**: a stray `release()` still inflates the count; fairness does not check ownership.
- **Owners holding permits too long**: waiters still have to wait.
- **Multi-resource deadlock**: two tasks can hold different permits/locks and wait on each other; fairness does not eliminate circular wait.
- **Scheduler fairness**: the JVM/OS does not guarantee each task gets CPU within a fixed time window.
- **Throughput**: fair mode can incur overhead handing off to older waiters, making it slower than nonfair mode under contention.

### 12.1. The Untimed `tryAcquire` Exception

The no-argument `Semaphore.tryAcquire()` can grab a permit **immediately if one is available**, even on a fair semaphore with waiters already queued. In other words, this method **allows barging**.

`tryAcquire(0, TimeUnit.SECONDS)` on a fair semaphore can be used when you want a non-waiting attempt that still honors fairness; this overload can throw `InterruptedException`. Similarly, the untimed `tryAcquire(n)` follows the barging policy of its overload.

If your application requires that new tasks never jump the queue, you must inspect **every acquire code path**, not just the `Semaphore(..., true)` constructor.

### 12.2. Starvation Is Not a Permit Leak

If a thread waits for a very long time, that alone does not prove a permit leaked:

- Another thread is holding a permit and genuinely taking a long time to finish.
- The waiting task is receiving little CPU time from the scheduler.
- Nonfair barging is starving older waiters.
- A task is holding some permits while waiting on another resource.
- A protocol bug actually lost a permit.

Measure permit owners/lifetimes and timeout rates rather than looking only at queue length.

## 13. `getQueueLength()`, `availablePermits()`, and Observability

`availablePermits()` returns the number of available permits at the moment of the call. `getQueueLength()` is an **estimate** of waiting threads; `hasQueuedThreads()` is only an instantaneous observation. Immediately after reading, another thread can acquire or release.

**Do not use these values to build check-then-act logic such as:**

~~~java
// WRONG: race condition between check and acquire.
if (semaphore.availablePermits() > 0) {
    // Assuming acquire is guaranteed not to wait is wrong.
    semaphore.acquire();
}
~~~

Another thread can take the permit right after the check. If you want **non-blocking** behavior, call `tryAcquire()` and inspect the boolean; if you have a deadline, use a timed overload.

### 13.1. Useful Metrics

| Metric | Meaning and Limitations |
| --- | --- |
| Logical capacity | Designed maximum concurrent entries |
| Available permits | Currently available permits; instantaneous snapshot |
| In-flight permits | Permits acquired and not yet released per application protocol |
| Acquire latency p50/p95/p99 | Time spent waiting to be granted permits |
| Hold duration p95/p99 | How long permits are held |
| Timeout rate | Fraction of tasks that fail to acquire within deadline |
| Interrupt/cancellation count | How many waits were interrupted |
| Estimated queue length | Hint of waiting pressure, not an exact waiter count |
| Acquire/release event balance | Are any events missing a release or releasing too many? |
| Work outcome | Task succeeded/failed/cancelled; do not conflate with permit accounting |

If the application uses n-permit acquires, **counting acquire/release calls** is not enough; you must count the **total permit units**. An `acquire(3)` event must be balanced by `release(3)`, not by a single `release()`.

### 13.2. Metrics Do Not Make a Synchronization Protocol

If multiple threads increment an "in-flight" metric, the metric itself must be thread-safe. Never place metric updates where an exception in logging could cause a permit leak. For critical code, keep the critical path simple and observe it with mechanisms unlikely to fail.

If you need an audit trail, record permit acquisitions and releases with **a lease ID**, permit count, and hold duration. Do not infer ownership from `availablePermits()` alone, because the semaphore does not track individual permit owners.

## 14. Code Paths That Commonly Leak Permits in Practice

### 14.1. Early Return

~~~java
// WRONG: early return skips release.
semaphore.acquire();
if (!isValidRequest()) {
    return;
}
doWork();
semaphore.release();
~~~

Use `finally`:

~~~java
semaphore.acquire();
try {
    if (!isValidRequest()) {
        return;
    }
    doWork();
} finally {
    semaphore.release();
}
~~~

### 14.2. Mid-Method Exception

~~~java
// WRONG if process can throw an exception.
semaphore.acquire();
process();
semaphore.release();
~~~

Even an unchecked exception skips `release()` without `finally`. Do not catch only one exception type to release; put `release()` in `finally` to cover all normal exit paths.

### 14.3. Timeout or Interrupt Before Acquire

If `tryAcquire(...)` returns `false` or `acquire()` throws `InterruptedException`, no permit was granted by that call. An unconditional `finally` outside the acquire causes an **over-release**, not a leak. Treat the acquire code and the release code as two halves of the same protocol.

### 14.4. Async Callbacks

~~~java
// Flawed design if externalCallAsync still uses the resource
// after the method returns.
semaphore.acquire();
try {
    externalCallAsync(); // Only starts the work.
} finally {
    semaphore.release(); // Too early!
}
~~~

Decide who holds the lease until the callback/`CompletionStage` actually completes, and release **exactly once** on the success/failure/cancel paths. If a callback can fire multiple times due to a bug, or if an API promises at-most-once delivery while your code adds a fallback cleanup, enforce an idempotent guard and clear ownership.

Be careful with `whenComplete(... release)` patterns: if you acquire before creating the stage, and stage creation **throws a synchronous exception before registering the callback**, the release will be skipped. Design an explicit ownership transfer from the synchronous scope to the callback with concrete state, or use a lease wrapper that closes exactly once.

### 14.5. Retries

A retrying task may acquire a fresh permit for each attempt. Each attempt must balance its own permits. If you choose to hold a permit across all attempts, ensure total hold duration and deadlines are bounded; holding a permit while sleeping for a long backoff can stall the system even without a leak.

### 14.6. Nested Acquire and Dependency Stall

Task A holds a permit and calls Task B, which needs **the same semaphore**, while capacity is exhausted; if A blocks waiting for B to finish, a dependency deadlock occurs.

~~~text
Semaphore(1)
A: acquire -> available = 0
A: submits B and waits for result
B: acquire -> waits because available = 0
A: will not release until B finishes
=> B cannot enter; A cannot finish
~~~

There is no leak in the sense of lost permits, yet there is a **deadlock**. Redesign ownership: avoid holding a permit while waiting on subtasks that also need the same semaphore, or adjust the semaphore scope and dependency flow.

## 15. Draining and Reducing Permits: Advanced APIs Requiring Caution

`Semaphore.drainPermits()` returns all immediately available permits and sets the available count to 0 in a single operation. It can be useful for certain management protocols, but without clear ownership it is very easy to "hold" drained permits and forget to return them.

~~~java
// Illustrates an advanced API; not a standalone program.
int drained = semaphore.drainPermits();
try {
    reconfigureCapacity();
} finally {
    semaphore.release(drained);
}
~~~

This pattern is appropriate only when the application protocol genuinely needs to hold the drained permits, and when returning them at the end does not violate another logical limit. If tasks are already holding permits, draining **does not revoke** permits currently in use.

`reducePermits(int reduction)` is a **protected** method intended for subclasses and specialized protocols; do not treat it as a public API for arbitrary callers to shrink capacity. If you implement dynamic capacity, you must design the relationship among available, in-flight, and target capacity as well as already-issued permits—not merely call one method and assume admitted concurrency changed immediately.

Never use `drainPermits()` as a "cancel all tasks" button: it only takes currently available permits, does not interrupt waiters, and does not reclaim permits held by running tasks.

## 16. Choosing `Semaphore` or Another Synchronizer?

| Need | Usually Better Choice | Why |
| --- | --- | --- |
| Limit at most N code sections sharing a resource | `Semaphore(N)` | Simple, supports acquire/release and timeouts |
| Limit queued tasks and worker count | `ThreadPoolExecutor` with bounded queue and rejection policy | Manages task/pool capacity, not just entry permits |
| Exchange items between producers and consumers | `BlockingQueue` | Stores items and provides consumption ownership |
| Wait for a set of operations to complete | `CountDownLatch` | One-shot countdown, no permit return needed |
| Synchronize multiple threads in phases | `CyclicBarrier` or `Phaser` | Phase protocol, not slot counting |
| Protect multi-field invariants with a single owner | `ReentrantLock` / `synchronized` | Lock ownership and mutual exclusion |
| Allow concurrent readers with exclusive writers | `ReadWriteLock` | Different semantics from a counting semaphore |
| Limit requests per second | Time-based rate limiter / token bucket | Semaphore limits **concurrency**, not rate |

**Example:** A capacity of 10 permits where each request takes 1 ms can yield high throughput; a capacity of 10 where each request holds for 10 s yields very low throughput. A semaphore does not directly enforce **10 requests/second**. If you need rate limiting, incorporate time into the protocol.

### 16.1. Does `Semaphore(1)` Replace a Mutex?

`Semaphore(1)` can limit concurrent entry to one task, but it **has no owner** and is not reentrant like `ReentrantLock`. When protecting state with a lock, strict ownership and unlock checks usually make `ReentrantLock` or `synchronized` easier to reason about and prove correct.

Do not call `Semaphore(1)` a fully equivalent mutex when you rely on monitor behavior or lock ownership.

## 17. Testing for Permit Leaks and Over-Release

### 17.1. Do Not Rely on Scheduler Timing

A test that calls `Thread.sleep(50)` and guesses a worker has acquired a permit is unreliable on busy CI machines. Use `CountDownLatch`, `Future.get()`, `join()`, or a barrier to observe deterministic points.

For code that could block indefinitely on a leak, tests must use a timeout when waiting for completion; on timeout, capture a thread dump and perform bounded cleanup so the entire test suite does not hang.

### 17.2. Critical Scenarios

1. **Success path:** acquire succeeds, `doWork` runs normally, full release occurs.
2. **Unchecked exception:** `doWork` throws; `finally` still releases.
3. **Early return:** business logic rejects the request; release still happens after acquire.
4. **Interrupted acquire:** never release an unacquired permit; restore/propagate the interrupt properly.
5. **Timeout:** `tryAcquire` returns `false`; `release` is not called.
6. **`tryAcquire` returns `true`:** exactly one release for that successful call.
7. **Bulk permits:** `acquire(n)` is balanced by `release(n)`.
8. **Nested ownership:** no two layers release the same permit.
9. **Async completion:** release exactly once on success/failure/cancel, and not too early.
10. **Cancellation:** a task holding a permit is interrupted; `finally` still releases.
11. **Contention:** concurrent tasks inside the guarded region never exceed logical capacity.
12. **Shutdown:** waiters are cancelled/woken per protocol; permits are not held forever by tasks that refuse to stop.
13. **Over-release detector:** intentionally attempt a release before acquire on a dedicated test semaphore to verify that your tests/linters/lease tracking catch or prevent application-level bugs.
14. **Retries:** each attempt balances itself without duplicate releases when late callbacks arrive.

### 17.3. Checking Invariants in Tests

Once your code guarantees nobody is still holding a permit and all test tasks have finished, check:

~~~java
// Assertion snippet after the test has waited for all tasks to finish;
// not a standalone program.
if (semaphore.availablePermits() != initialCapacity) {
    throw new AssertionError("Permit imbalance");
}
~~~

**Caution:** `available` returning to initial capacity proves only **net balance** at that instant. One leak and one over-release can cancel each other out arithmetically, while the system still temporarily exceeded capacity or stalled. Stronger tests should track currently held permits, max concurrent entries, a lease ID per acquire/release, and release timestamps.

If other writers or callers are still operating on the semaphore, asserting that `available` equals a fixed value is meaningless; close task submission and wait for workers to finish before asserting.

## 18. Code Review Checklist: Every Permit Has One Clear Return Path

- Are logical capacity and the permit count required per work type clearly defined?
- Does every successful `acquire()` enter **a single `finally`** that guarantees release?
- Is `acquire()` placed **before** the `try/finally` block when no `acquired` flag is used?
- With `tryAcquire`, is release called only when the boolean result is `true`?
- With timeouts/interrupts, is release avoided when acquire did not succeed?
- With `acquire(n)`, are **exactly `n`** permits released?
- Can any early return, checked/unchecked exception, cancellation, timeout, or callback skip release?
- Can any `catch` + `finally` or wrapper + outer caller both release?
- Does any task hold a permit longer than the actual lifetime of the resource?
- Do async operations guarantee release only after callback completion, while not skipping release if setup throws?
- Are retries bounded and idempotent, avoiding leaks across attempts?
- Is `Semaphore(1)` being misused as a lock where ownership or reentrancy is required?
- Does any task hold a permit while waiting on another task that must acquire the same semaphore?
- Was fairness chosen based on throughput/starvation metrics rather than assuming fairness fixes leaks?
- Are timeouts and cancellation paths in place so workers do not wait forever if downstream hangs?
- Is `availablePermits()` used as a metric rather than "check then assume acquire will succeed"?
- Are total in-flight permits and max concurrent entries observed in tests?
- On shutdown, do permit-holding tasks run cleanup and finish per contract?
- Are `drainPermits` and capacity adjustments avoided unless backed by a precise protocol?
- Is "task processing failed" clearly separated from "the slot permit must still be returned" in all cases?

## 19. Self-Check Questions

**1.** Why is `try { semaphore.acquire(); work(); } finally { semaphore.release(); }` a buggy pattern?

If `acquire()` is interrupted before succeeding, `finally` still calls `release()`; the semaphore gains a permit even though the caller was never granted one. Place `acquire()` outside `try`, or use a strict `acquired` flag.

**2.** `tryAcquire()` returns `false`. Should `release()` be called to "clean up"?

No. `false` means that call granted no permit; calling `release()` would be an over-release.

**3.** Why doesn't a semaphore automatically detect Thread B releasing a permit that Thread A acquired?

Because a semaphore does not bind permits to an owning thread like `ReentrantLock` does. This is a design feature, not a JVM bug. The program must manage logical ownership.

**4.** Does a prolonged `availablePermits() == 0` always mean a permit leak?

No. All permits might be held by slow tasks, tasks stuck on I/O, or a deadlock. You need holder information, hold duration, and worker lifecycle data.

**5.** A task acquires three permits and returns two. What bug is this?

A permit leak of **one permit**. You must release the exact number acquired.

**6.** Does calling `release()` twice after one successful acquire make `Semaphore` throw an exception like `ReentrantLock.unlock()`?

There is no equivalent owner check; `available` can rise above the logical capacity. This is an over-release / double release.

**7.** Does a fair semaphore prevent all starvation and permit leaks?

No. Fairness coordinates waiter ordering at acquisition points; it does not reclaim lost permits, force owners to release, or fix deadlocks and broken cancellation.

**8.** Should you hold a permit while launching an async task and release right after submitting it?

Only if usage of the bounded resource **truly ends** right after submission. If the background work still uses the bounded resource, releasing on submit is premature. Transfer release ownership to the completion path.

**9.** Why is a latch a good choice for testing a 2-permit limit?

You can hold two tasks that have acquired permits at a deterministic rendezvous point and verify `available == 0` before allowing them to release, instead of guessing scheduler timing with `sleep`.

**10.** During shutdown, what is the risk of using `acquireUninterruptibly()`?

Waiting tasks may ignore interrupt signals meant for fast cancellation; you need a separate protocol to ensure liveness, or prefer an interruptible API.

**11.** Is `Semaphore(1)` completely equivalent to a mutex?

No. A semaphore does not enforce ownership or reentrancy like `ReentrantLock`. Choose based on the protocol you need to uphold.

**12.** Why is checking that `available` equals capacity after a test not enough to prove there are no bugs?

A leak and an over-release can cancel each other out, or the system may have temporarily admitted too many tasks even though the final count balances. You also need event-balance checks and max-concurrent-entries tracking.

## 20. JDK Documentation and Conclusion

For reference against JDK behavior:

- [Semaphore — JDK 17](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/concurrent/Semaphore.html)
- [ThreadPoolExecutor — JDK 17](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/concurrent/ThreadPoolExecutor.html)
- [BlockingQueue — JDK 17](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/concurrent/BlockingQueue.html)

**Practical rules:**

~~~text
acquire() succeeds:
    try { protected work } finally { release() }

tryAcquire() == true:
    try { protected work } finally { release() }

tryAcquire() == false:
    must not release

acquire() throws InterruptedException:
    must not release for that call
    propagate or restore the interrupt signal per contract

acquire(n) succeeds:
    release(n) exactly once when resource usage ends
~~~

**Conclusion:** A semaphore only maintains a **permit count**; it knows nothing about owners or business invariants. To prevent permit leaks and over-releases, every successful acquire must establish clear ownership with exactly one release path at the end of the resource's lifetime. Combine `try/finally` or a lease wrapper, handle timeouts and interrupts accurately, measure hold times, and design deterministic interleaving tests to preserve your application's concurrency limits.

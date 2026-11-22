# Using Synchronizers in Java Concurrency Tests

## 1. Why Is Multithreaded Testing Harder Than Sequential Testing?

In a sequential test, statements execute in an order that is relatively easy to reason about. When multiple threads access shared state concurrently, the execution schedule depends on the scheduler, CPU, locks, I/O, JIT, and synchronization relationships. A test that passes once **does not prove** that the program is correct under all interleavings.

For example, suppose two workers both perform `counter++` on an ordinary field. The increment is a **read → compute → write** sequence, not an atomic transaction. Even if you run the test 100 times and get the expected result every time, a **lost update** bug may still exist and simply not have surfaced due to the execution schedule.

The goal of this lesson is to use **synchronizers in `java.util.concurrent`** to:

1. Bring multiple workers to the same **starting point** without guessing timing with `Thread.sleep()`.
2. Deliberately force specific **interleavings** to occur, thereby reproducing bugs.
3. Wait for completion using **signals with timeouts**, avoiding tests that hang indefinitely.
4. Capture exceptions from workers and **fail the test** on the test thread.
5. Verify **invariants** on data, processing counts, and concurrent access limits.
6. Distinguish **deterministic coordination tests** from stress tests and specialized tools for verifying the Java Memory Model.

This covers **general Java concurrency**, using **Java 17+** examples and JDK APIs; it does not depend on Spring or any specific testing framework.

## 2. What Is a Synchronizer in a Test?

Synchronization utilities are not only for production code; they also help tests express exact **“A must happen-before B”** relationships.

| Tool | Useful role in tests | Pitfalls to avoid |
| --- | --- | --- |
| `CountDownLatch` | Wait for N workers to reach a milestone; issue a shared start signal; wait for N tasks to finish | A latch only counts down from its initial count to 0 and **cannot be reset** |
| `CyclicBarrier` | Force N participants to meet across **multiple rounds/phases** | One failing or timed-out participant can put the barrier into a **broken** state |
| `Phaser` | Coordinate multiple phases where the number of participants can **register/deregister** dynamically | Unbounded `arriveAndAwaitAdvance()` calls can hang the test |
| `Semaphore` | Verify that at most N tasks access a resource concurrently | Only release permits that were acquired; do not infer active count from thread count |
| `BlockingQueue` | Pass data/events between workers and the test thread, waiting boundedly with `poll` | An empty queue at a point in time does not prove the entire pipeline is complete |
| `Future` / `ExecutorService` | Collect worker results and errors via `get()`; bound waiting and issue cancellation | `get(timeout)` expiring **does not automatically cancel** the task |
| `ReentrantLock` + `Condition` | Orchestrate predicates/conditions and test wakeups | `await` must check the predicate in a **`while`** loop, not just `if` |

**Synchronizers do not control the entire scheduler.** A latch confirms that a worker has reached a marked point; it does not force the worker to continue executing immediately after the gate opens, nor does it justify assuming an arbitrary unsynchronized ordering.

### Useful Milestone Names in Tests

- **Ready gate:** all workers have finished setup and are about to wait for the start signal.
- **Start gate:** opened by the main/test thread to allow workers to proceed.
- **Done gate:** all workers have passed through the block under test (including error paths, when properly designed).
- **Phase barrier:** allows participants to proceed only when all have reached a milestone in the **same round**.
- **Release gate:** holds workers at a known point until the test decides to release them.

By naming these milestones explicitly, we verify the actual **concurrency contract** rather than relying on an arbitrary number of milliseconds.

## 3. Why `Thread.sleep()` Is Not a Test Coordination Mechanism

A common anti-pattern:

```java
// Snippet with a race condition: does not guarantee the worker has done the required work.
worker.start();
Thread.sleep(100);
assertState();
```

This is a snippet; `worker` and `assertState` are undeclared. Sleeping for 100 ms **does not confirm** that the worker has started, reached the critical section, or finished. Slow CI machines, GC pauses, or scheduler load can make the test **flaky**. Conversely, on fast machines the test may always pass without ever triggering the interleaving needed to catch a bug.

**Replace it with a meaningful signal:** the worker calls `ready.countDown()` at the point you want to observe; main calls `ready.await(timeout, unit)` and checks the state. Then, if you want the worker to proceed, main opens `start.countDown()`. Signals represent concrete events, not timing guesses.

Sleep can still be used when **time itself** is what is being tested, but it should not be used as implicit proof that a thread has reached a logical state.

## 4. Basic Pattern: ready → start → done with CountDownLatch

To let N workers prepare and then receive the start command together:

```text
Main/test                            Worker 1 ... Worker N
---------                            ----------------------
Create ready(N), start(1), done(N)
                                     ready.countDown()
                                     start.await()
ready.await(timeout) ----------->    all workers have reached the start gate
start.countDown() -------------->    begin the block under test
                                     work()
                                     done.countDown() in finally
done.await(timeout) ----------->     all have finished the block
check invariants + worker errors
```

**Do not confuse** “opening the gate at the same time” with “executing at the exact same CPU instant.” After `start.countDown()`, scheduling remains nondeterministic. The pattern only guarantees that workers **do not pass the start gate before main allows it**.

### Complete Java 17+ Example: Testing Atomic Increments

Create `LatchStartTest.java`:

```java
import java.util.concurrent.CountDownLatch;
import java.util.concurrent.TimeUnit;
import java.util.concurrent.atomic.AtomicInteger;
import java.util.concurrent.atomic.AtomicReference;

public class LatchStartTest {
    public static void main(String[] args) throws InterruptedException {
        int workers = 4;
        CountDownLatch ready = new CountDownLatch(workers);
        CountDownLatch start = new CountDownLatch(1);
        CountDownLatch done = new CountDownLatch(workers);
        AtomicInteger counter = new AtomicInteger();
        AtomicReference<Throwable> workerFailure = new AtomicReference<>();
        Thread[] threads = new Thread[workers];

        for (int i = 0; i < workers; i++) {
            threads[i] = new Thread(() -> {
                try {
                    ready.countDown();
                    if (!start.await(5, TimeUnit.SECONDS)) {
                        throw new AssertionError("Start gate timed out");
                    }
                    counter.incrementAndGet();
                } catch (Throwable error) {
                    workerFailure.compareAndSet(null, error);
                    if (error instanceof InterruptedException) {
                        Thread.currentThread().interrupt();
                    }
                } finally {
                    done.countDown();
                }
            }, "worker-" + i);
            threads[i].start();
        }

        try {
            if (!ready.await(5, TimeUnit.SECONDS)) {
                throw new AssertionError("Workers not ready");
            }
            start.countDown();
            if (!done.await(5, TimeUnit.SECONDS)) {
                throw new AssertionError("Workers did not finish");
            }
            if (workerFailure.get() != null) {
                throw new AssertionError("Worker failed", workerFailure.get());
            }
            if (counter.get() != workers) {
                throw new AssertionError("Wrong counter");
            }
            System.out.println("Ready workers: " + workers);
            System.out.println("Atomic increments: " + counter.get());
        } finally {
            start.countDown(); // Prevent workers from getting stuck if the test fails.
            for (Thread thread : threads) {
                thread.interrupt();
            }
            for (Thread thread : threads) {
                thread.join();
            }
        }
    }
}
```

Compile and run:

```bash
javac LatchStartTest.java
java LatchStartTest
```

Output when there are no external interrupts and the test passes:

```text
Ready workers: 4
Atomic increments: 4
```

**Key points:**

1. Workers signal `ready` **before** waiting on `start`, so main can confirm they have reached the gate.
2. `AtomicInteger.incrementAndGet()` is an atomic update. The final result is always 4 if all four increments run successfully.
3. `done.countDown()` is inside `finally`, so a worker throwing an exception still reports that **its execution path has finished**, preventing main from waiting forever due to a missing signal.
4. Exceptions are recorded in `AtomicReference<Throwable>` so main can **read them back and fail the test**. An exception on a worker thread does not automatically become a failure on the main thread.
5. Every progress-sensitive `await` has a timeout. The `finally` block opens the start gate, interrupts threads, and calls `join` to reduce the risk of leaking workers.
6. This demo checks a single coordinated schedule; it **does not prove** that a concurrent algorithm is correct under all interleavings.

In production tests, when a worker might intentionally ignore interrupts, an untimed `join()` can still risk hanging. You can use a timed join, an executor shutdown with a deadline, and track live threads; a test timeout does not mean Java can safely force-stop a thread.

## 5. Orchestrating Interleavings to Deterministically Reproduce a Lost Update

An effective learning technique is to **deliberately write buggy code**, then use synchronizers to **force two threads to both read a stale value before either thread is allowed to write**.

Suppose the initial value is 1. Both threads execute:

```java
int snapshot = counter.value;
counter.value = snapshot + 1;
```

This is a snippet; `counter` is undeclared. If we separate the read and write with latches, both threads can read 1 and then both write 2. The result 2 **instead of 3** is a lost update bug that can be reproduced **without sleeping or guessing scheduling**.

### Complete Java 17+ Example: Proving `volatile` Does Not Make RMW Atomic

Create `LostUpdateTest.java`:

```java
import java.util.concurrent.CountDownLatch;
import java.util.concurrent.TimeUnit;
import java.util.concurrent.atomic.AtomicReference;

public class LostUpdateTest {
    private static final class Counter {
        volatile int value = 1;
    }

    public static void main(String[] args) throws InterruptedException {
        Counter counter = new Counter();
        CountDownLatch bothRead = new CountDownLatch(2);
        CountDownLatch mayWrite = new CountDownLatch(1);
        AtomicReference<Throwable> failure = new AtomicReference<>();

        Runnable nonAtomicIncrement = () -> {
            try {
                int old = counter.value;
                bothRead.countDown();
                if (!mayWrite.await(5, TimeUnit.SECONDS)) {
                    throw new AssertionError("Write gate timeout");
                }
                counter.value = old + 1;
            } catch (Throwable error) {
                failure.compareAndSet(null, error);
                if (error instanceof InterruptedException) {
                    Thread.currentThread().interrupt();
                }
            }
        };

        Thread left = new Thread(nonAtomicIncrement, "left");
        Thread right = new Thread(nonAtomicIncrement, "right");
        left.start();
        right.start();

        try {
            if (!bothRead.await(5, TimeUnit.SECONDS)) {
                throw new AssertionError("Both reads not reached");
            }
            mayWrite.countDown();
            left.join();
            right.join();

            if (failure.get() != null) {
                throw new AssertionError("Worker failed", failure.get());
            }
            System.out.println("Observed after two increments: "
                    + counter.value);
            System.out.println("Expected with atomic increments: 3");
        } finally {
            mayWrite.countDown();
            left.interrupt();
            right.interrupt();
        }
    }
}
```

Compile and run:

```bash
javac LostUpdateTest.java
java LostUpdateTest
```

Output:

```text
Observed after two increments: 2
Expected with atomic increments: 3
```

**Why is the result 2 deterministic?**

- Each worker captures `old = counter.value` **before** calling `bothRead.countDown()`.
- Main only opens `mayWrite` **after both workers have called `countDown()`**, meaning both have already read the old value.
- Because no writer has been allowed past `mayWrite.await()`, both snapshots are **1**.
- Both workers write the same value 2 regardless of order; the final `value` is 2.
- `volatile` guarantees visibility/ordering properties for individual accesses, but **does not turn a read–write pair into an atomic operation**.

This is a **bug-demonstration test**: printing `2` is the intended behavior of the demo, not the correct result of an increment algorithm. When fixing production code, use `AtomicInteger.incrementAndGet()`, `getAndAdd()`, an appropriate lock, or a CAS loop. Never try to “fix” it by inserting `Thread.sleep` between the two lines.

**A warning about test orchestration:** `mayWrite` is synchronization **used solely to force a schedule**. It does not represent a mechanism protecting the counter in production code. Avoid exposing test-only gates in the public API of domain objects when you can use internal injection/hooks or a separate test harness.

## 6. CyclicBarrier: Multi-Round Coordination, Not a Reusable CountDownLatch

`CountDownLatch` is a **one-shot** gate: once its count reaches 0, it stays open. If a test needs workers to meet across multiple rounds, `CyclicBarrier` is usually a better fit.

`new CyclicBarrier(parties, barrierAction)` lets **N participants** call `await()`. When the last participant arrives, the barrier action runs before the waiting threads are released; the barrier is then reused for the **next generation**.

- `await()` can throw `InterruptedException` or `BrokenBarrierException`.
- `await(timeout, unit)` can additionally throw `TimeoutException`.
- If one participant is interrupted or times out, the barrier can enter the **broken state**. Other participants receive corresponding exceptions; the test must clean up.
- `getNumberWaiting()` is only an observational snapshot and should not be used as the sole basis for test logic decisions.

### Complete Java 17+ Example: Two Workers and Main Across Two Phases

Create `BarrierRoundsTest.java`:

```java
import java.util.concurrent.BrokenBarrierException;
import java.util.concurrent.CyclicBarrier;
import java.util.concurrent.TimeUnit;
import java.util.concurrent.atomic.AtomicInteger;
import java.util.concurrent.atomic.AtomicReference;

public class BarrierRoundsTest {
    public static void main(String[] args) throws Exception {
        AtomicInteger completedRounds = new AtomicInteger();
        AtomicInteger workerSteps = new AtomicInteger();
        AtomicReference<Throwable> failure = new AtomicReference<>();

        CyclicBarrier barrier = new CyclicBarrier(
                3, completedRounds::incrementAndGet);

        Runnable worker = () -> {
            try {
                for (int round = 0; round < 2; round++) {
                    workerSteps.incrementAndGet();
                    barrier.await(5, TimeUnit.SECONDS);
                }
            } catch (Throwable error) {
                failure.compareAndSet(null, error);
            }
        };

        Thread first = new Thread(worker, "first");
        Thread second = new Thread(worker, "second");
        first.start();
        second.start();

        try {
            for (int round = 0; round < 2; round++) {
                barrier.await(5, TimeUnit.SECONDS);
            }
            first.join();
            second.join();

            if (failure.get() != null) {
                throw new AssertionError("Worker failed", failure.get());
            }
            System.out.println("Barrier rounds: "
                    + completedRounds.get());
            System.out.println("Worker steps: " + workerSteps.get());
        } finally {
            barrier.reset();
            first.interrupt();
            second.interrupt();
            first.join();
            second.join();
        }
    }
}
```

Run:

```bash
javac BarrierRoundsTest.java
java BarrierRoundsTest
```

Output when there are no external interrupts:

```text
Barrier rounds: 2
Worker steps: 4
```

**Analysis:**

- The barrier has **3 parties**: main + two workers.
- Each worker increments `workerSteps` before hitting the barrier in each phase; total 2 × 2 = 4.
- The barrier action increments `completedRounds` **once per successful generation**; there are two generations, so the total is 2.
- It does not matter which worker runs first.
- If a worker drops out or a wait call times out, main must not proceed to pass the test. It must fail the test, reset/break the barrier, and clean up threads.

`barrier.reset()` in `finally` is only demo cleanup after main has finished or failed; it does **not** replace proper recovery logic in a production algorithm using a barrier.

### What Bugs Can a Barrier Help Detect?

- Two data read/write stages must complete before moving to the next round.
- Blocking workers at known checkpoints to inspect intermediate state.
- Generating concurrent contention without relying on `sleep`.
- Verifying how many times a phase completes; testing participant exception/timeout paths.

However, a barrier does not automatically verify that shared data is properly protected. After each phase, **you still need assertions** on invariants according to the Java Memory Model and the system's contract.

## 7. Phaser: Multiple Phases and Dynamic Participant Counts

`Phaser` fits when the number of participating workers changes over time. Key APIs:

- `register()` / `bulkRegister(n)`: register participants.
- `arriveAndAwaitAdvance()`: report arrival at the current phase and wait for the phase to advance.
- `arriveAndDeregister()`: report arrival and **withdraw from subsequent phases**.
- `getPhase()`: current phase; when terminated, it returns a negative value by contract.
- `awaitAdvanceInterruptibly(phase, timeout, unit)`: wait for a phase change with interrupt/timeout support.

**Key difference:** `arriveAndAwaitAdvance()` is an **uninterruptible** wait by contract, so do not treat it as a timed wait. If a participant disappears without arriving or deregistering, the phase may fail to advance.

### Complete Java 17+ Example: Dynamic Worker Registration

Create `PhaserRegistrationTest.java`:

```java
import java.util.concurrent.Phaser;
import java.util.concurrent.atomic.AtomicInteger;

public class PhaserRegistrationTest {
    public static void main(String[] args) throws InterruptedException {
        Phaser phaser = new Phaser(1); // Main is one party.
        AtomicInteger operations = new AtomicInteger();
        Thread[] workers = new Thread[2];

        for (int i = 0; i < workers.length; i++) {
            phaser.register();
            workers[i] = new Thread(() -> {
                try {
                    operations.incrementAndGet();
                    phaser.arriveAndAwaitAdvance();
                } finally {
                    phaser.arriveAndDeregister();
                }
            }, "phase-worker-" + i);
            workers[i].start();
        }

        // Wait until main and both workers all reach phase 0.
        phaser.arriveAndAwaitAdvance();
        phaser.arriveAndDeregister();

        for (Thread worker : workers) {
            worker.join();
        }

        System.out.println("Operations: " + operations.get());
        System.out.println("All parties deregistered: "
                + phaser.isTerminated());
    }
}
```

Run:

```bash
javac PhaserRegistrationTest.java
java PhaserRegistrationTest
```

Output when both workers succeed:

```text
Operations: 2
All parties deregistered: true
```

**Explanation:** main starts as one party, then registers two workers. Each worker performs an operation and arrives at phase 0. Main also arrives; once all three have arrived, the phase can advance. Then each participant calls `arriveAndDeregister()`, leaving no registered parties, so the phaser terminates.

**Practical warning:** this demo prioritizes showing the register/deregister mechanism. In production tests, if a worker throws an exception before `arriveAndAwaitAdvance` or gets stuck, main can wait forever. When you need a hard deadline, use `arrive()` followed by `awaitAdvanceInterruptibly(phase, timeout, unit)`, along with `forceTermination()` and cleanup on test failure; also remember to **record worker errors** on the test thread. Do not use `Thread.sleep` to “make sure” workers have reached a phase.

## 8. Semaphore: Testing Resource Concurrency Ceilings

`Semaphore` is especially useful for testing that **no more than N tasks ever enter a resource-usage region at the same time**. A Semaphore with 2 permits limits concurrent holders to at most two **provided every entry path calls `acquire` and every exit path calls `release` properly**.

Have two workers hold all permits while a third worker waits. The test verifies that the third worker **cannot enter before main releases** the first two workers.

### Complete Java 17+ Example: Simulating a Two-Slot Resource

Create `SemaphoreLimitTest.java`:

```java
import java.util.concurrent.CountDownLatch;
import java.util.concurrent.Semaphore;
import java.util.concurrent.TimeUnit;
import java.util.concurrent.atomic.AtomicInteger;
import java.util.concurrent.atomic.AtomicReference;

public class SemaphoreLimitTest {
    public static void main(String[] args) throws InterruptedException {
        Semaphore slots = new Semaphore(2);
        CountDownLatch twoInside = new CountDownLatch(2);
        CountDownLatch release = new CountDownLatch(1);
        CountDownLatch thirdAttempted = new CountDownLatch(1);
        CountDownLatch thirdEntered = new CountDownLatch(1);
        AtomicInteger current = new AtomicInteger();
        AtomicInteger peak = new AtomicInteger();
        AtomicReference<Throwable> failure = new AtomicReference<>();

        Runnable occupant = () -> {
            boolean acquired = false;
            try {
                slots.acquire();
                acquired = true;
                int now = current.incrementAndGet();
                peak.accumulateAndGet(now, Math::max);
                twoInside.countDown();
                if (!release.await(5, TimeUnit.SECONDS)) {
                    throw new AssertionError("Release gate timed out");
                }
            } catch (Throwable error) {
                failure.compareAndSet(null, error);
                if (error instanceof InterruptedException) {
                    Thread.currentThread().interrupt();
                }
            } finally {
                if (acquired) {
                    current.decrementAndGet();
                    slots.release();
                }
            }
        };

        Thread a = new Thread(occupant, "a");
        Thread b = new Thread(occupant, "b");
        Thread c = new Thread(() -> {
            boolean acquired = false;
            try {
                thirdAttempted.countDown();
                slots.acquire();
                acquired = true;
                thirdEntered.countDown();
            } catch (InterruptedException e) {
                failure.compareAndSet(null, e);
                Thread.currentThread().interrupt();
            } finally {
                if (acquired) {
                    slots.release();
                }
            }
        }, "c");

        a.start();
        b.start();

        try {
            if (!twoInside.await(5, TimeUnit.SECONDS)) {
                throw new AssertionError("First two did not enter");
            }
            c.start();
            if (!thirdAttempted.await(5, TimeUnit.SECONDS)) {
                throw new AssertionError("Third did not attempt");
            }
            System.out.println("Third entered before release: "
                    + (thirdEntered.getCount() == 0));
            release.countDown();

            a.join();
            b.join();
            c.join();
            if (failure.get() != null) {
                throw new AssertionError("Worker failed", failure.get());
            }
            System.out.println("Peak occupied: " + peak.get());
            System.out.println("Available permits: "
                    + slots.availablePermits());
        } finally {
            release.countDown();
            a.interrupt();
            b.interrupt();
            c.interrupt();
            a.join();
            b.join();
            if (c.getState() != Thread.State.NEW) {
                c.join();
            }
        }
    }
}
```

Run:

```bash
javac SemaphoreLimitTest.java
java SemaphoreLimitTest
```

Normal output:

```text
Third entered before release: false
Peak occupied: 2
Available permits: 2
```

**Why must the value before release be `false`?** Main only starts worker `c` after `twoInside` has reached 0: workers `a` and `b` have **acquired and not yet released** their permits, because they are waiting at the `release` gate. Worker `c` may have already started calling `acquire` or is about to call it, but it cannot obtain a permit while `availablePermits == 0`. Therefore, `thirdEntered` is not counted down before main opens the gate.

**Why is `peak` equal to 2?** Only workers `a` and `b` increment `current` after acquiring; with proper release after use, there is no third increment. The example tests the slot limit rather than trying to use scheduling to push the peak higher.

In a real system, to track **all** resource usage, every caller (including worker `c`) must update metrics under the same protocol. This demo only measures occupancy for the two workers designed to hold slots and observes whether the third worker can enter early.

**Permit rule:** only call `release()` if `acquire()` succeeded. Releasing without acquiring can inflate the semaphore's permits beyond the intended limit and cause false test results.

## 9. `Future.get(timeout)`: Observing Worker Errors and Preventing Tests from Waiting Forever

`Thread.start()` does not automatically propagate worker exceptions to the test thread. If a worker throws an `AssertionError` on another thread, the main test **does not necessarily fail** just because a stack trace is printed. There are two common approaches:

- With raw `Thread`: catch `Throwable` in the worker, store it in an `AtomicReference<Throwable>`, and throw `AssertionError` on main after `join` or `done.await`.
- With `ExecutorService.submit(Callable/Runnable)`: keep the `Future` and call `get(timeout, unit)` to receive the result or exception. If the task fails, `get` throws `ExecutionException` with `getCause()`. If it times out, `get` throws `TimeoutException`.

**Note:** `get(timeout)` **does not automatically cancel** the task. The caller must decide whether to call `future.cancel(true)`, `executor.shutdownNow()`, or wait/clean up by another mechanism.

### Complete Java 17+ Example: Timeout and Cancelling a Task Waiting on a Latch

Create `FutureTimeoutTest.java`:

```java
import java.util.concurrent.CountDownLatch;
import java.util.concurrent.ExecutorService;
import java.util.concurrent.Executors;
import java.util.concurrent.Future;
import java.util.concurrent.TimeUnit;
import java.util.concurrent.TimeoutException;

public class FutureTimeoutTest {
    public static void main(String[] args) throws Exception {
        CountDownLatch started = new CountDownLatch(1);
        CountDownLatch gate = new CountDownLatch(1);
        ExecutorService executor = Executors.newSingleThreadExecutor();

        try {
            Future<String> result = executor.submit(() -> {
                started.countDown();
                gate.await();
                return "released";
            });

            if (!started.await(5, TimeUnit.SECONDS)) {
                throw new AssertionError("Task never started");
            }

            boolean timedOut = false;
            try {
                result.get(20, TimeUnit.MILLISECONDS);
            } catch (TimeoutException expected) {
                timedOut = true;
            }

            System.out.println("Timed out: " + timedOut);
            boolean cancelRequested = result.cancel(true);
            System.out.println("Cancellation accepted: "
                    + cancelRequested);
            System.out.println("Future cancelled: "
                    + result.isCancelled());
        } finally {
            gate.countDown();
            executor.shutdownNow();
            if (!executor.awaitTermination(5, TimeUnit.SECONDS)) {
                throw new AssertionError("Executor did not stop");
            }
        }
    }
}
```

Compile and run:

```bash
javac FutureTimeoutTest.java
java FutureTimeoutTest
```

Output in a normal run:

```text
Timed out: true
Cancellation accepted: true
Future cancelled: true
```

The `gate` does not open before `get(20ms)`, so the task cannot return `"released"` before the timeout. Then `cancel(true)` sends a cancellation request and transitions the `Future` to the cancelled state. `gate.countDown()` in `finally` ensures the example does not leave the worker waiting if circumstances change.

**Do not conclude:** `Future.isCancelled() == true` does not prove that the task code stopped at **the exact moment the flag was read** or that all side effects were rolled back. `awaitTermination()` gives the executor a window to finish, and the task code must cooperate with interruption if prompt cancellation is required.

### Short Example of an Exception from Future

```java
// Snippet inside a method with an appropriate executor and imports.
Future<?> failed = executor.submit(() -> {
    throw new IllegalStateException("bad task");
});
try {
    failed.get(1, TimeUnit.SECONDS);
} catch (java.util.concurrent.ExecutionException e) {
    throw new AssertionError("Worker failed", e.getCause());
}
```

This snippet is not a standalone file. If a task throws `IllegalStateException`, `Future.get` surfaces it wrapped in `ExecutionException`. The enclosing method also needs to handle `InterruptedException` and `TimeoutException`; this example focuses solely on **not ignoring worker errors**.

## 10. What Visibility Do Latch, Barrier, and Phaser Guarantee?

Synchronizers do not only block and wake threads; the APIs in `java.util.concurrent` have **memory-consistency effects** that establish happens-before relationships.

### CountDownLatch

Actions **before** `countDown()` in one thread happen-before actions **after** the corresponding `await()` returns successfully in another thread.

Writer example:

```java
data = 42;
ready.countDown();
```

Reader:

```java
ready.await();
int snapshot = data;
```

These are two non-standalone snippets; assume `data` and `ready` share the same ownership/protocol. Once the reader has waited for the latch to reach 0, writes prior to `countDown()` are published by contract. However, if the writer **continues modifying `data` afterward**, the latch does not freeze the object into a snapshot; further synchronization is needed for subsequent updates.

### CyclicBarrier

Actions of a participant prior to `await()` are published by the `CyclicBarrier` contract to the barrier action, and from the barrier action to actions after a successful `await()` in all participants. Using a barrier helps separate **phases of work**; however, if a participant exits before the barrier, you must handle the broken barrier rather than pretending the data is already in the new phase.

### Phaser

`Phaser` provides guarantees around phase completion and the publication of actions when a phase advances. When using `arriveAndAwaitAdvance` or `awaitAdvanceInterruptibly`, ensure the participant is on the **right phase**; waiting on a phase that has already passed may return immediately. Do not assume a single `arrive` is equivalent to waiting for all other parties to finish.

### Semaphore

`Semaphore` release and acquire have the appropriate memory-consistency relationships, but a semaphore also requires the **correct permit count**. Do not use `availablePermits()` as an atomic decision check for resource usage; use `acquire`/`tryAcquire` directly.

**Core takeaway:** it is the **synchronization protocol** that establishes ordering and visibility, not merely threads “waiting long enough.” Therefore, a test that inspects data after `await`/`join`/`get` stands on much firmer ground than one that sleeps for some duration and then reads state.

## 11. Designing Tests That Don't Hang and Don't Pollute Other Tests

A concurrency test should have an explicit **failure and cleanup policy**:

1. **Put timeouts on every wait that could block indefinitely:** `latch.await(timeout)`, `barrier.await(timeout)`, `future.get(timeout)`, `executor.awaitTermination(timeout)`, or timed `join`.
2. **Open critical gates in `finally`** if the test fails before releasing them. A latch is not an auto-cleaned resource; a forgotten gate can hold a worker forever.
3. **Send interrupts/cancellation** when needed, while understanding that these are cooperative requests, not forced thread kills.
4. **Never hold a lock while waiting for a worker that needs that same lock.** A test can create a self-inflicted deadlock unrelated to the target bug.
5. **Never use `Thread.sleep` to “wait long enough.”** Use real milestones and conditions.
6. **Collect worker errors back onto the test thread.** Do not just look at logs/stack traces and let the test pass.
7. **Cap the maximum number of workers**, especially under load testing; avoid exhausting CI CPU/RAM.
8. **Restore the interrupt status** when catching `InterruptedException` and not rethrowing it, depending on the layer owning the lifecycle.
9. **Distinguish timeouts caused by algorithm bugs from timeouts caused by overloaded CI environments.** A timeout is a failure to investigate, not an automatic diagnosis.
10. **Keep tests independent:** create a fresh executor/queue/state per test, and do not let static mutable state from an earlier test affect later tests.

### Pattern for Shutting Down an ExecutorService After a Test

```java
// Snippet for an executor created and owned by the test.
executor.shutdown();
try {
    if (!executor.awaitTermination(5, TimeUnit.SECONDS)) {
        executor.shutdownNow();
        if (!executor.awaitTermination(5, TimeUnit.SECONDS)) {
            throw new AssertionError("Executor did not terminate");
        }
    }
} catch (InterruptedException e) {
    executor.shutdownNow();
    Thread.currentThread().interrupt();
    throw new AssertionError("Test interrupted", e);
}
```

This is a snippet; `executor` is undeclared. The two timeouts are **two separate wait stages**, not a single 5-second total deadline. If the test has an overall deadline, compute `remaining` from `System.nanoTime()` so you do not grant the full budget again on each step.

**Note:** a worker that does not cooperate with interruption can still remain alive after the test fails. For high-risk tests (e.g., deliberate deadlocks/infinite loops), isolate the test in a separate process so an external harness can kill the **process** on timeout; do not use `Thread.stop()`.

## 12. Deterministic Tests, Stress Tests, and Java Memory Model Verification

No single set of synchronizers covers **every thread schedule**. You need to combine multiple techniques:

| Test type | Idea | What to check |
| --- | --- | --- |
| **Deterministic scenario** | Latches/barriers force a known interleaving | A specific bug, invariants at checkpoints |
| **Repeated concurrency test** | Run many times with varying worker counts and data seeds | Stability of invariants across many schedules |
| **Stress test** | Increase contention, generate many interleaved operations | Races, lost updates, deadlocks, resource leaks |
| **JMM litmus test** | Focus on visibility, ordering, atomicity | Allowed/disallowed outcomes under the JMM |
| **Performance benchmark** | Measure throughput/latency under a representative workload | Performance, not proof of absence of data races |

### jcstress and JMH: Two Different Goals

- **jcstress** is a tool in the OpenJDK ecosystem for exercising many interleavings and outcomes of concurrency/JMM checks.
- **JMH** is for controlled performance microbenchmarking. It is **not** a tool for proving a concurrent algorithm is always correct.
- Latch-coordinated tests help construct **specific schedules**, whereas jcstress helps explore many outcomes; they complement each other.
- Thread Sanitizer / race detectors may vary in support and scope; do not assume that no warnings means code is safe on every JVM.

If formal correctness proof is required, you must reason via the Java Memory Model / happens-before, linearizability, or appropriate algorithm verification; stress testing only increases the chance of finding bugs and does not constitute a mathematical proof over all interleavings.

### Avoid Using `yield()` as a Reliable Test Mechanism

`Thread.yield()` is a **hint** to the scheduler and does not force another thread to run. `Thread.sleep(1)` also cannot establish a desired happens-before order. They may increase schedule variation in load tests, but should not serve as assertions or barriers.

## 13. Example: Verifying No Data Loss with BlockingQueue

`BlockingQueue` generally provides thread-safe semantics, but tests still need to verify the exact **items sent and received**, avoiding relying on `queue.isEmpty()` alone while the producer is still running.

A solid pattern:

```text
Producer puts 100 items and signals done.
Consumer takes items and records received IDs.
Main waits for producer done + consumer done.
Main verifies:
  count = 100
  no duplicate IDs
  every ID is in the expected set
```

If the system requires exactly-once processing, you must clearly define retries, cancellation, failures, acknowledgments, and when an item is considered “processed.” `BlockingQueue.take` only guarantees retrieving an element per the queue contract; it does not automatically make business side effects exactly-once.

### Waiting with `poll(timeout)`

`queue.poll(timeout, unit)` returns `null` when no element arrives within the wait window. `null` is **not** proof that the producer has permanently finished. To detect end-of-stream, use a separate signal (such as a latch or completion `Future`) or a valid sentinel placed into the queue per the protocol.

Avoid writing `while (!queue.isEmpty())` to decide when a consumer should stop while the producer is still active; a temporary empty gap can cause later items to be missed.

## 14. Common Concurrency Testing Mistakes

1. **“I called `sleep(100)`, so the worker must have reached the target line.”** False: scheduling makes no such guarantee.
2. **“Spawning many threads guarantees a race will happen.”** False: you must control contention/interleaving; a single passing run proves very little.
3. **“If a worker throws an AssertionError, the main test automatically fails.”** False: you must propagate errors back to main or read the `Future`.
4. **“A latch can be reset for the next test round.”** False: `CountDownLatch` is one-shot; use `CyclicBarrier` or `Phaser` for multiple phases.
5. **“`CountDownLatch.await(timeout)` returning false means the workers are done.”** False: `false` reports a timeout before enough signals arrived.
6. **“Putting `done.countDown()` at the end of `try` is enough.”** Not enough if an exception is thrown partway through; put it in `finally`.
7. **“Even if one side breaks the barrier, we can treat the phase as done.”** False: a broken barrier should fail the test and trigger cleanup.
8. **“`CyclicBarrier` opens automatically when a thread drops out.”** False: it can hang if there are not enough participants and no timeout is set.
9. **“`Phaser.arriveAndAwaitAdvance()` is an interruptible timed wait.”** False: for interrupt/timeout support, use the corresponding API.
10. **“Having permits means data is protected everywhere.”** False: only paths that follow `acquire`/`release` are bounded.
11. **“`availablePermits()` is an atomic admission decision.”** False: it is an observational state that can change immediately.
12. **“When `Future.get(timeout)` expires, the task is cancelled.”** False: the timeout only bounds how long the caller waits.
13. **“`cancel(true)` proves the worker has stopped and finished cleanup.”** False: you need proper waiting and lifecycle management.
14. **“If all threads finish `join`, shared `int++` definitely lost no updates.”** False: `join` only waits for completion; the updates may have raced.
15. **“`volatile` makes `x++` atomic.”** False: `volatile` only provides semantics for individual accesses.
16. **“`queue.isEmpty()` at a point in time suffices to confirm the pipeline is done.”** False: the producer may still send more items.
17. **“Add lots of delays to reduce flaky tests.”** Unsustainable: use real conditions and synchronizers instead.
18. **“Passing a stress test 1 million times proves there is no data race.”** False: it does not cover all schedules, JVMs, or hardware.
19. **“Tests should assume the CPU count always equals the worker count.”** False: concurrency does not mean parallel execution on every core.
20. **“It's fine to create a pool in a test without shutting it down.”** It can leak threads/resources and affect other tests.

## 15. Checklist for Writing Reliable Concurrency Tests

1. **State invariants clearly**: which outcomes must hold under every schedule, and which are expected only under one specific schedule?
2. **Choose meaningful checkpoints** instead of sleep: `ready`, `start`, `done`, `phase`, `release`, or `future` completion.
3. **Control participant counts**: latch counts, barrier parties, and phaser registrations must match actual workers.
4. **Timeout every wait that could hang**; treat timeouts as test failures to investigate.
5. **Propagate worker exceptions back to main** via `Future` or `AtomicReference` and assert on them.
6. **Put `countDown`/`deregister`/permit `release` in `finally`** when matching the ownership contract, avoiding missed signals.
7. **Never release a semaphore permit you did not acquire**; never double `countDown` or forget to `deregister` and corrupt phases.
8. **Check data invariants after an appropriate synchronization point**; avoid reading state while a writer is still modifying it without a protection protocol.
9. **Fix timing bugs in the test architecture**, rather than just increasing timeouts or adding sleeps.
10. **Put cleanup in `finally`** and manage threads/executors created by the test; timeout/cancel is not a forced kill.
11. **Build dedicated error-path tests**: worker throws exception, missing participant, broken barrier, interrupt while waiting, timeout, and overload.
12. **Run repeatedly across multiple environments**, but do not treat pass counts as formal proof.
13. **Use jcstress when testing JMM outcomes**, and JMH when measuring performance; do not confuse their goals.
14. **Do not add test-only gates that alter production algorithms** in ways that hide bugs; use appropriate hooks/injection and review their impact.
15. **Document what test success means**: reproducing a fixed schedule, verifying invariants, or probabilistically detecting races.

## 16. JDK API References

- [CountDownLatch — Java 17](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/concurrent/CountDownLatch.html)
- [CyclicBarrier — Java 17](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/concurrent/CyclicBarrier.html)
- [Phaser — Java 17](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/concurrent/Phaser.html)
- [Semaphore — Java 17](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/concurrent/Semaphore.html)
- [Future — Java 17](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/concurrent/Future.html)
- [java.util.concurrent package — Java 17](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/concurrent/package-summary.html)

**Conclusion:** good concurrency tests turn invisible multithreaded milestones into **observable, coordinated events**. `CountDownLatch` builds ready/start/done gates, `CyclicBarrier` coordinates multiple rounds, `Phaser` manages changing participant counts, `Semaphore` verifies concurrency limits, and `Future` brings results and errors back to main. Synchronizers help reproduce specific interleavings and verify invariants on properly published data, but they do not cover every schedule: combine JMM reasoning, repeated/stress testing, and proper timeout, interruption, and cleanup management so tests are both useful and never hang.
# Demonstrating Race Conditions with Execution-Timing Coordinated Tests in Java

A race condition is a bug where a program's outcome depends on the order and timing in which concurrent operations interleave. Because the operating system and JVM are free to schedule threads in many different ways, faulty code can run correctly thousands of times before failing. **A test that simply "runs many threads and hopes they collide" is not enough to prove or reproduce a specific race.** We can actively create a dangerous execution schedule using synchronization utilities to prove that an invariant is violated, and then run the same scenario against the fixed design.

This lesson focuses on **pure Java concurrency** and the utilities built into `java.util.concurrent`. The goal is to learn how to write **interleaving-coordinated tests**, explain each wait point, observe bugs in a controlled manner, set timeouts to avoid hanging test suites, propagate errors from worker threads back to the test runner, and understand the limitations of this type of test. This is not a tutorial for a specific testing framework.

## 1. Why Are Race Conditions Hard to Reproduce?

Suppose two threads increment a shared variable concurrently:

```java
class UnsafeCounter {
    int count;

    void increment() {
        count++;
    }
}
```

This is an **illustrative snippet**, without a `main` method yet. `count++` is logically a read–modify–write operation: read the old value, add one, and write back the new result. It is **not atomic** with respect to other threads if it is just a plain `int` field. If A and B both read the value `0` before either of them writes, both may write back `1`; after two calls to `increment()`, the total is only `1` instead of `2`.

| Logical step | Worker A | Worker B | `count` |
| --- | --- | --- | --- |
| Initial | | | `0` |
| 1 | Read `0` | | `0` |
| 2 | | Read `0` | `0` |
| 3 | Write `0 + 1` | | `1` |
| 4 | | Write `0 + 1` | `1` |

This is a **lost update**: one business-level update is not reflected in the final state. The table describes the steps at a logical level and does not claim that the JIT compiler must emit exactly three CPU instructions for `count++`.

When writing a naive test:

```java
Thread a = new Thread(counter::increment);
Thread b = new Thread(counter::increment);
a.start();
b.start();
a.join();
b.join();
```

the test might observe `2` because A finishes before B starts, or because the steps do not overlap. Adding a loop of millions of iterations increases the chance of hitting the bug, but **does not guarantee** that the same interleaving will occur. `Thread.sleep(1)` also fails to enforce the required ordering: the scheduler makes no guarantee about which thread runs immediately after the sleep duration expires.

**A better way to test a known buggy schedule:** split the logical operation into controllable steps; place a *rendezvous* point after both workers read the state and before either writes. Once the rendezvous condition is met, allow them to proceed. The test will reliably reproduce the exact type of dangerous schedule we want to demonstrate.

## 2. Define the Invariant Before Building the Test

A race test is valuable when it clearly states the correctness condition that must be preserved:

| Use case | Invariant to preserve | Possible race |
| --- | --- | --- |
| Two counter increments | After two successful increments, value increases by exactly `2` | Lost update, result only increases by `1` |
| A seat sold only once | At most one successful booking confirmation | Both users see the seat available and get confirmed |
| Deducting inventory | Never sell more than the actual available stock | Multiple threads pass the stock check simultaneously |
| Initialize a cache entry once | A key does not undergo two business initializations with side effects | Two threads both check and then both create |
| Updating two related fields | Readers observe a snapshot satisfying the invariant | Readers observe data from two different versions |
| Lifecycle management | After shutdown, no new work is accepted in violation of the contract | Checking state and submitting is interleaved with shutdown |

**Distinction:** a *data race* is a Java Memory Model concept referring to conflicting accesses without a proper happens-before relationship. A *race condition* is broader, encompassing business logic bugs caused by **individual operations being thread-safe while their combination is not atomic**. Coordinated tests can expose check–then–act bugs even when each individual step uses synchronized structures.

Do not merely assert "no exception thrown." With races, many incorrect outcomes still return normally; tests must verify the update count, confirmation count, balance, or specific invariant.

## 3. Java Toolkit for Coordinating Timing

| Utility | Role in testing | Key points to remember |
| --- | --- | --- |
| `CountDownLatch(n)` | Wait for `n` events before opening a phase | Counter only decrements, **cannot be reset**; suited for one-shot start/done gates |
| `CyclicBarrier(n)` | Force `n` participants to reach the same point before any proceeds | Reusable across multiple rounds; if a participant times out/is interrupted, the barrier may become **broken** |
| `Phaser` | Coordinate multiple phases, with a dynamic number of participants | More flexible, but more complex than latch/barrier |
| `Thread.join()` | Wait for a thread to terminate | Does not guarantee the thread passed a desired checkpoint before terminating |
| `Future.get(timeout, unit)` | Retrieve a worker's result/exception with a deadline | Timing out while waiting does not automatically cancel the worker |
| `ExecutorService` with enough workers | Run the participants | A pool with fewer workers than tasks waiting on a barrier can deadlock itself |
| `AtomicInteger`/`AtomicBoolean` | Safely record results or signals from multiple workers | Does not automatically make a multi-step workflow atomic |
| `Semaphore` | Limit the number of workers allowed through a region | Does not create an all-participant rendezvous like a barrier |

One way to represent a schedule using a barrier:

```text
Worker A: READ count=0 -----> [barrier] -----> WRITE 1
Worker B: READ count=0 -----> [barrier] -----> WRITE 1
                                  |
                         2 participants reached
                                  |
                            both may proceed
```

When A reaches the rendezvous point first, it must wait for B; when B arrives, both are allowed to proceed. **The key point is that all READs have completed before any WRITE begins.** We do not need—and cannot—determine the exact order in which the workers run after the barrier opens; in this example, both write the same value `1`, so the outcome remains deterministic.

### Difference Between Test Coordination and Production Fixes

- **Test coordination** creates an intentional execution schedule to explore or prove a bug. It *may introduce additional happens-before edges* and affect other interleavings.
- **Production fixes** ensure the business operation is correct across **every interleaving permitted by the contract**, using mutual exclusion, CAS, atomic APIs, immutable state, message passing, or appropriate ownership design.
- If a test forces both workers to read a stale snapshot and still grants them permission to write based on that snapshot, that demonstrates a **read–modify–write protocol** bug, but one cannot mechanically infer that the test proves every access is a *formal data race* under the JMM. Latches and barriers are themselves synchronization primitives and establish happens-before relationships.

## 4. Complete Java 17 Example: Three Coordinated Tests

We will run three scenarios in a single Java 17 program:

1. **Forced lost update:** two workers both read the shared value `0`, wait together at a barrier, and then write `1`; the test verifies that two increments only produce `1`, meaning the correct invariant `2` is violated.
2. **Double booking:** two workers both check "nobody has booked yet" before the barrier, then each confirms a booking; the number of successful confirmations becomes `2`, exceeding the limit of `1`.
3. **Fix with a critical section:** use `synchronized` to combine check–then–set into a single operation. Both workers still attempt to book, but only one is confirmed.

Create the file **`CoordinatedRaceTest.java`**:

```java
import java.util.concurrent.Callable;
import java.util.concurrent.CyclicBarrier;
import java.util.concurrent.ExecutorService;
import java.util.concurrent.Executors;
import java.util.concurrent.Future;
import java.util.concurrent.TimeUnit;
import java.util.concurrent.atomic.AtomicInteger;

public class CoordinatedRaceTest {
    private static final int TIMEOUT_SECONDS = 5;

    static class Counter {
        int value = 0;
    }

    static class UnsafeSeat {
        boolean booked = false;
    }

    static class SafeSeat {
        private boolean booked = false;

        synchronized boolean bookOnce() {
            if (booked) {
                return false;
            }
            booked = true;
            return true;
        }
    }

    private static void assertEquals(int expected, int actual, String name) {
        if (actual != expected) {
            throw new AssertionError(
                    name + ": expected=" + expected + ", actual=" + actual);
        }
    }

    private static void runTwo(Callable<Void> task) throws Exception {
        ExecutorService pool = Executors.newFixedThreadPool(2);
        try {
            Future<Void> first = pool.submit(task);
            Future<Void> second = pool.submit(task);

            first.get(TIMEOUT_SECONDS, TimeUnit.SECONDS);
            second.get(TIMEOUT_SECONDS, TimeUnit.SECONDS);
        } finally {
            pool.shutdownNow();
        }
    }

    private static void reproduceLostUpdate() throws Exception {
        Counter counter = new Counter();
        CyclicBarrier bothRead = new CyclicBarrier(2);

        runTwo(() -> {
            int snapshot = counter.value; // Both read 0
            bothRead.await(TIMEOUT_SECONDS, TimeUnit.SECONDS);
            counter.value = snapshot + 1;
            return null;
        });

        // Explicitly verify that the buggy schedule was reproduced.
        assertEquals(1, counter.value, "lost update");
        System.out.println("lost update: actual=1, correct=2");
    }

    private static void reproduceDoubleBooking() throws Exception {
        UnsafeSeat seat = new UnsafeSeat();
        AtomicInteger confirmations = new AtomicInteger();
        CyclicBarrier bothChecked = new CyclicBarrier(2);

        runTwo(() -> {
            boolean available = !seat.booked; // Both see the seat as available
            bothChecked.await(TIMEOUT_SECONDS, TimeUnit.SECONDS);

            if (available) {
                seat.booked = true;
                confirmations.incrementAndGet();
            }
            return null;
        });

        assertEquals(2, confirmations.get(), "double booking");
        System.out.println("double booking: actual=2, allowed=1");
    }

    private static void verifyFixedBooking() throws Exception {
        SafeSeat seat = new SafeSeat();
        AtomicInteger confirmations = new AtomicInteger();

        runTwo(() -> {
            if (seat.bookOnce()) {
                confirmations.incrementAndGet();
            }
            return null;
        });

        // This is the business invariant that must be preserved.
        assertEquals(1, confirmations.get(), "fixed booking");
        System.out.println("fixed booking: actual=1, allowed=1");
    }

    public static void main(String[] args) throws Exception {
        reproduceLostUpdate();
        reproduceDoubleBooking();
        verifyFixedBooking();
    }
}
```

Compile and run:

```bash
javac CoordinatedRaceTest.java
java CoordinatedRaceTest
```

**Exact stdout when the program completes normally:**

```text
lost update: actual=1, correct=2
double booking: actual=2, allowed=1
fixed booking: actual=1, allowed=1
```

If the environment cannot run enough participants or a task is interrupted/times out, the test **fails with an exception** instead of printing misleading results as if it succeeded. The reason for `Future.get(timeout)` and `CyclicBarrier.await(timeout)` is to protect the test from waiting indefinitely, not to establish a sleep duration used to trigger a race.

### Analyzing Each Test Case

**Case 1 — lost update**

- `counter` is a single shared instance for both workers.
- `snapshot` is a local variable private to each `Callable` execution.
- Each worker reads `counter.value` before reaching `bothRead.await(...)`.
- The barrier opens once both workers arrive, so at the time of reading, neither had written yet.
- Both have `snapshot == 0` and both write `1`; the final state is `1`, even though two business increments occurred.

The code intentionally splits `counter.value++` into separate read and write steps to **place a checkpoint between the two steps**. This is a *test harness* simulating a non-atomic operation; it does not mean production code must split an increment into two lines for a race to happen. With a real `counter.value++`, overlapping reads can still occur when synchronization is missing.

**Case 2 — check–then–act**

- `seat.booked` is a shared flag initially set to `false`.
- Both obtain `available = !seat.booked` before the barrier and both get `true`.
- After the barrier, each worker trusts that the stale information is still valid; both confirm the booking.
- `AtomicInteger confirmations` is used solely to **accurately measure the two confirmations**, preventing the test's own counter from suffering a lost update that would mask the bug. `AtomicInteger` here **does not make the `booked` flag safe**.

The business race happens because "checking availability" and "booking the seat" are two non-atomic steps. It differs from the counter increment bug, yet shares the same root cause: **making decisions based on a snapshot that another thread may have already invalidated**.

**Case 3 — combining operations into a critical section**

- `SafeSeat.bookOnce()` guards both `if (booked)` and `booked = true` with **the monitor of the same `seat` instance**.
- One worker enters first, sees `false`, changes it to `true`, and returns `true`.
- The other worker can only enter after the monitor is released, sees `true`, and returns `false`.
- Regardless of worker ordering, exactly one confirmation is incremented.

**Why doesn't the fixed test place a barrier inside `bookOnce()`?** If one worker acquires the monitor and then waits on `CyclicBarrier(2)` **inside** the `synchronized` method, the second worker cannot enter the method to reach the barrier. The test would deadlock/time out by itself, rather than due to a bug in production code. Coordinate before lock contention or observe results after both complete; **never place a rendezvous inside a mutually exclusive critical section**.

### Why Not Use Java's Default `assert`?

Java `assert` statements can be disabled when the JVM `-ea` option is not enabled. The custom `assertEquals` helper above throws `AssertionError` unconditionally when the actual value differs from the expected value, so the test cannot be silently "disabled" by missing runtime flags. When porting to JUnit, you can use `org.junit.jupiter.api.Assertions.assertEquals`; the current example **requires no external test libraries beyond the JDK**.

## 5. Two Important Coordination Patterns: Rendezvous and One-Way Gate

### 5.1. `CyclicBarrier`: Everyone Reaches the Checkpoint

Use a barrier when you want to ensure two or more threads have all completed one phase before any thread moves to the next phase:

```java
CyclicBarrier barrier = new CyclicBarrier(2);

Runnable action = () -> {
    try {
        // Phase A: read or observe state
        barrier.await(5, TimeUnit.SECONDS);
        // Phase B: update based on the read state
    } catch (Exception e) {
        throw new RuntimeException(e);
    }
};
```

The snippet above is just a **fragment**, without `main` or workers. `await(timeout)` can throw `InterruptedException`, `BrokenBarrierException`, or `TimeoutException`; the example collapses them into one catch branch to illustrate the structure, but real applications need proper interrupt handling.

- `CyclicBarrier(2)` requires **two `await` calls within the same generation**, not just one worker.
- If there is only one worker in the pool and the first task waits on the barrier, the second task sitting in the queue will never reach the barrier; with a timeout, the test fails faster, but it is still a coordination bug.
- A barrier can be reused across multiple rounds. If one participant fails, exits early, or times out, the barrier becomes broken; this state must be handled before reusing it.
- `CyclicBarrier`'s memory consistency contract supports handing off data between phases; therefore, **do not use a barrier to prove spontaneous visibility failures on a field**.

### 5.2. `CountDownLatch`: Main Controls When to Open the Gate

A common test schedule has three milestones: both tasks are ready → main gives the start signal → main waits for both to finish. Standalone Java 17 example:

File `StartGateExample.java`:

```java
import java.util.concurrent.CountDownLatch;
import java.util.concurrent.TimeUnit;
import java.util.concurrent.atomic.AtomicInteger;

public class StartGateExample {
    public static void main(String[] args) throws Exception {
        CountDownLatch ready = new CountDownLatch(2);
        CountDownLatch start = new CountDownLatch(1);
        CountDownLatch done = new CountDownLatch(2);
        AtomicInteger completed = new AtomicInteger();

        Runnable task = () -> {
            try {
                ready.countDown();
                start.await();
                completed.incrementAndGet();
            } catch (InterruptedException e) {
                Thread.currentThread().interrupt();
            } finally {
                done.countDown();
            }
        };

        Thread first = new Thread(task, "first");
        Thread second = new Thread(task, "second");
        first.start();
        second.start();

        if (!ready.await(5, TimeUnit.SECONDS)) {
            start.countDown();
            throw new IllegalStateException("Workers not ready");
        }
        start.countDown();

        if (!done.await(5, TimeUnit.SECONDS)) {
            first.interrupt();
            second.interrupt();
            throw new IllegalStateException("Workers not finished");
        }

        first.join();
        second.join();
        System.out.println("completed=" + completed.get());
    }
}
```

```bash
javac StartGateExample.java
java StartGateExample
```

Stdout on normal completion:

```text
completed=2
```

**Role of each latch:**

- `ready`: each worker signals that it has reached the checkpoint before main opens the gate.
- `start`: main decides when workers may proceed. A single `countDown()` opens the gate for **all** waiters.
- `done`: counts workers that have passed through the `finally` block so main does not conclude prematurely.
- `AtomicInteger`: records the completed task count without lost updates.

The example uses an untimed `start.await()` in the workers to illustrate the gate, while main **is guaranteed to open the gate on the success path or if `ready` times out**; in complex test suites, you can replace this with a timed await and cancellation management to avoid leaving stray threads alive after a failure. `CountDownLatch` is single-use; to coordinate a subsequent phase, create a new latch or choose `Phaser`.

**Main difference:** `CyclicBarrier` opens automatically when enough participants arrive; `CountDownLatch` lets one or more external threads actively open the gate. For races that require forcing both threads to *finish reading* before writing, a barrier is usually more direct; for tests where main must hold all workers at a start gate, a latch is a better fit.

## 6. Placing Checkpoints at the Right Boundaries

To reproduce a suspected race, you must decompose the operation at the exact boundary:

| Race to test | Appropriate pause point | What to observe after releasing |
| --- | --- | --- |
| Lost update | After each worker reads the counter, before writing | Counter increments by less than expected |
| Double booking | After both read `available=true`, before booking | More than one confirmation |
| Duplicate cache init | After both detect a cache miss, before put/create | Create runs multiple times |
| Stock oversell | After two workers see available stock, before deducting | Sold more than available stock |
| Shutdown vs submit | After caller reads active state, before submitting | Operation may bypass lifecycle rules |
| Multi-field snapshot | Between updating field A and field B | Reader observes a broken invariant |

**Coordination does not mean modifying all production code.** In tests, you can extract the suspected logic into a small class with hooks/checkpoints or a test harness that replicates the algorithm with the same steps. However, a test with hooks only proves behavior along the constructed path. For real modules, you should add integration tests against the actual running implementation to avoid testing only a copy of the algorithm.

For example, a clean test seam design can separate `readSnapshot` and `applyUpdate`, or use a test-supplied callback interface **between two operations that are not yet synchronized**. Be careful: if you add a callback or barrier **inside a valid critical section** to force two threads to meet, the test can deadlock itself; tests must respect locking contracts.

## 7. Designing Non-Flaky Tests: Error Handling and Worker Termination

### 7.1. Why Propagate Exceptions from Workers to Main?

An exception thrown inside a `Runnable` may only appear on that thread's stderr. If the test runner does not properly await/collect results, the test can report a pass even though a worker failed. With `ExecutorService.submit` and `Future.get()`, errors from a `Callable` are wrapped in an `ExecutionException` on the caller side, causing the test case to fail instead of staying silent.

`Future.get(timeout)` also prevents main from waiting forever. When a timeout occurs, you must handle the aftermath: cancel tasks, interrupt if appropriate, shut down the executor, and investigate whether a worker is holding a lock or waiting on a barrier that can never reach its participant count. **A timeout only limits how long the caller waits; it does not automatically stop the task from running.** `shutdownNow()` attempts to interrupt running tasks; it does not guarantee that every task will cooperatively stop immediately.

### 7.2. Always Set a Deadline for Rendezvous Points That Risk Missing Participants

You can use:

```java
barrier.await(5, TimeUnit.SECONDS);
```

or:

```java
if (!ready.await(5, TimeUnit.SECONDS)) {
    throw new AssertionError("Missing worker");
}
```

These are two **snippets**, assuming `barrier` and `ready` are initialized appropriately. Deadlines help tests **fail with a clear signal** if a worker never reaches the checkpoint. Choose a timeout generous enough for slow CI machines while still reporting errors accurately; do not use a timeout so small that it causes random failures simply due to scheduler jitter.

### 7.3. Assert Only After Relevant Tasks Have Completed

Reading a counter while two workers are still writing can introduce another race right inside the test. Wait for `Future.get()` or `Thread.join()` to complete before checking results. These APIs also provide memory-consistency guarantees that ensure worker modifications are visible according to the Java specification.

### 7.4. Never Use `Thread.sleep` to Control Ordering

`sleep` pauses a thread for a minimum duration subject to the scheduler; it does not mean "thread B has definitely read the state" or "thread A has passed the checkpoint." If a test needs to prove that both workers are ready, use a latch or barrier. You may use `sleep` to simulate I/O in performance tests, but **never use it as a substitute for synchronization proof**.

### 7.5. Configure Gates with the Exact Participant Count

A `CyclicBarrier(3)` where only two workers call `await` will never open. If main also calls `await`, count main as the third participant; if main does not call it, set the count to `2`. If a pool has one worker while two tasks must meet at the same barrier, the first task occupies the worker and waits forever for the second task. In the main program, `newFixedThreadPool(2)` ensures there are enough workers for two participants waiting simultaneously.

### 7.6. Handle Interruption Properly

`InterruptedException` is an interruption signal that must be propagated or respected. If it cannot be rethrown inside a `Runnable`, restore `Thread.currentThread().interrupt()` and exit. If interrupts are ignored in an infinite wait loop, `shutdownNow` may fail to shut down all workers. With `CyclicBarrier`, an interrupted thread can break the barrier; the test should fail clearly instead of assuming all participants proceeded.

## 8. Why Is the Example Test Output Deterministic?

The three tests in `CoordinatedRaceTest` do not rely on random timing to enforce ordering. Determinism comes from:

1. Both workers are submitted to a two-thread pool.
2. Both workers **read the required value before calling `barrier.await()`**.
3. Neither worker writes to the relevant state before both have reached the barrier.
4. After the barrier opens, the write order may vary, but in the buggy scenarios both write the same value (counter `1`, seat `true`).
5. `Future.get()` returns after both tasks complete; only then does main check and print.
6. `AtomicInteger confirmations` prevents the confirmation-counting instrumentation itself from suffering a race.

The example assumes no unexpected interrupts, no deadline expirations, and sufficient machine resources to complete the tasks. If one of those operational conditions is not met, the test may fail or time out. **Do not turn a guarantee of "the same logical schedule" into a guarantee that the JVM will always finish within exactly 5 seconds** in every environment.

For the counter, the barrier establishes an ordering where reads happen before writes. Thus, this test is particularly good at proving **the lack of atomicity of the overall workflow**, but it does not simulate the full set of interleavings and reorderings permitted by the JMM when synchronization is completely absent. Do not use it to prove a visibility bug or reordering bug from a single outcome.

## 9. Writing a Test That FAILS on Buggy Code and PASSES After the Fix

In the first example, `assertEquals(1, counter.value)` verifies that **the test harness reproduced the bug**, so the program itself prints the result and does not fail. When turning the scenario into a regression test, **the expected condition must be the true business invariant**:

```java
// In a regression test for a correct counter:
if (counter.value != 2) {
    throw new AssertionError(
            "Lost update: expected=2, actual=" + counter.value);
}
```

This snippet is placed after waiting for all workers to finish. With the buggy implementation, this assertion fails intentionally; after fixing the increment operation with `synchronized` or `AtomicInteger.incrementAndGet()`, the corresponding test must pass.

**Do not simply replace a single write statement in a buggy-schedule test and expect the result to fix itself.** A test designed so that **both workers intentionally read first and later write the stale snapshot** will still produce a lost update even if each individual read/write is atomic. You must replace the **unit of business operation** with an atomic operation—for example, replacing the entire "read snapshot → write snapshot+1" pair with `AtomicInteger.incrementAndGet()`, or guarding the entire read–modify–write sequence with the same monitor. If you try to insert `CyclicBarrier(2)` **inside** a `synchronized` block wrapping the entire read–modify–write, the test will deadlock because the second worker cannot enter the critical section.

A clean testing strategy:

- **Reproduction test:** construct the interleaving that triggers the bug on the unsafe version; proves exact understanding of the race window.
- **Regression test:** spawn multiple workers invoking the **real operation**; assert the correct invariant on the fixed version. You can use a start gate so they begin close together, but do not insert a barrier between steps of an operation that has been made atomic.
- **Stress/integration test:** run many more schedules against the real code to increase coverage; use timeouts and good reporting.
- **Code review/JMM reasoning:** verify the correctness of the synchronization mechanism. A passing set of test schedules does not prove every possible schedule is safe.

## 10. Races from Two Separately Thread-Safe Operations

Coordination is very useful for detecting business-level races even when individual methods are safe.

Suppose we have a thread-safe map:

```java
// Illustrative snippet, assuming map is ConcurrentHashMap<Key, Value>.
if (!map.containsKey(key)) {
    map.put(key, createValue());
}
```

`containsKey` and `put` have their own thread-safety guarantees, but two threads can both observe that the key does not exist and both call `createValue()`. Both may trigger side effects (writing a file, calling a service, emitting an event) even though the map ultimately retains only one value.

Appropriate coordinated test: let both threads complete `containsKey` with `false`, have them wait at a barrier, and then release them to call `createValue`. Use an `AtomicInteger` inside the test to count how many times initialization runs; the invariant could be "the creation side effect occurs only once." If the requirement is merely to compute and insert a value when absent, `ConcurrentHashMap.computeIfAbsent` can solve part of the problem according to its API contract. However, external side effects require considering retries, failures, idempotency, and cross-system locking.

Placing a barrier after `containsKey` **simulates** the interleaving; do not use a barrier as a fix for a race in business code. For invariants spanning multiple resources, fixing the bug may require a transaction rather than a single atomic collection operation.

## 11. Distinguishing Schedule Tests from Visibility/JMM Tests

Not every concurrency bug can be deterministically reproduced with a barrier:

- **Lost update/check–then–act:** two workers can be coordinated to both read stale state before writing, so the buggy schedule is easy to create deterministically.
- **Visibility:** for example, one thread spins reading a plain field while another thread writes to it. Adding a latch/barrier between the write and the read can introduce a happens-before edge and **mask the very bug you want to test**.
- **Reordering/unsafe publication:** many outcomes depend on JIT optimizations, CPU architecture, and the JMM. Adding `println`, `sleep`, logging, a debugger, or locks often changes timing and outcomes.
- **Deadlock:** you can build a test with two monitors and a checkpoint to demonstrate a wait cycle, but you should not let a real test suite hang forever. Use deadlines, appropriate daemon/isolation threads, and inspect `ThreadMXBean` when needed.

For subtle JMM questions such as "what pairs of values can two reads observe?" or "how can a non-`volatile` field read a stale value?", tests need many schedules along with a model for evaluating valid outcomes, often called *litmus tests*. Specialized tools like **OpenJDK jcstress** help test many outcomes across runtimes/architectures, though not seeing an outcome still does not prove it impossible. Do not treat the results on a single machine as the definition of the JMM.

**Key difference:** a *coordinated test* usually proves that a **specific logical schedule is sufficient to expose a bug**; a *stress/litmus test* explores more possible schedules and outcomes. To conclude that code is safe, you must reason about atomicity, happens-before, and invariants—not rely solely on pass statistics.

## 12. When to Use Multi-Phase Testing with `Phaser`

A complex race has multiple phases: prepare data → workers read together → workers apply updates → main checks. `Phaser` can coordinate multiple rounds, allow dynamic registration/deregistration of participants, and wait to advance to the next phase. Conceptual example:

```java
Phaser phaser = new Phaser(2);

// Both workers complete the preparation phase.
phaser.arriveAndAwaitAdvance();

// Both workers complete the read phase.
phaser.arriveAndAwaitAdvance();

// Only then proceed to the write/update phase.
```

This is a **snippet** (it requires importing `java.util.concurrent.Phaser`, registering the right participants, and running from two workers). `arriveAndAwaitAdvance()` waits for all parties; if one worker never arrives, the test can hang. For small tests with a single checkpoint, `CyclicBarrier` or `CountDownLatch` is usually easier to understand. Only add complexity when the number of phases or participants genuinely requires it.

## 13. Common Pitfalls in Concurrency Tests Themselves

| Mistake | Consequence | How to fix |
| --- | --- | --- |
| Using `Thread.sleep(10)` to "ensure" the other worker ran | Flaky because the scheduler has no ordering contract | Use a latch/barrier with explicit checkpoints |
| Running two tasks on a single-worker pool while waiting on a two-party barrier | First task holds the worker; second task never runs | Provision enough workers or change synchronization design |
| Placing a rendezvous inside a `synchronized`/lock needed by another worker | Self-inflicted deadlock | Place checkpoints outside critical sections |
| Only observing stdout without asserting invariants | Bugs still report as passing | Assert expected values after `join`/`get` |
| Asserting values immediately after `start()` | Main reads too early; data race in the test itself | Wait for workers to finish or reach sufficient checkpoints |
| Worker throws an exception but main does not collect it | Test runner may ignore the error | Use `Future.get` or an error-collection mechanism to fail the test |
| Barrier without a timeout | Test can hang forever if a participant is missing | Use timed await and report the cause clearly |
| Timed get without cleanup | Failing worker stays alive and pollutes other tests | Cancel/interrupt, shut down executor, manage lifecycle properly |
| Counting confirmations with unsynchronized `int++` | The measurement variable itself loses updates | Use `AtomicInteger`/locks for instrumentation |
| Two workers actually use two separate state instances | Test does not exercise shared state at all | Pass the **exact same** instance to all tasks |
| Testing only a simulated copy of the algorithm | Production has different code; bug remains unfixed | Increase testing against the real operation |
| Treating "passed on CI" as JMM-safe | A finite set of schedules does not prove all schedules | Reason about synchronization and invariants |
| Adding a barrier to test visibility | Barrier can create happens-before, hiding the bug | Use appropriate litmus/stress tests and JMM review |
| Using `assert` without enabling `-ea` | Assertions may not execute | Use JUnit assertions or throw `AssertionError` directly |
| Depending on the order of two worker log lines | Output legitimately varies across runs | Collect results and print from main after `Future.get` |

## 14. Process for Designing a Useful Coordinated Test

1. **Pick a concrete invariant**: "only one person can book a seat," "2 increments produce 2," "no negative stock."
2. **Identify the real state and operation**: which object is shared across threads? Where are the read, check, and write paths?
3. **Sketch a failing execution schedule** on paper (A reads → B reads → A writes → B writes). If you cannot sketch one, investigate the logic first.
4. **Place minimal checkpoints** right at the boundary that determines the outcome. Use a barrier if all workers must finish a phase together; use a latch when main needs to open a gate.
5. **Provision enough participants and workers**; avoid placing checkpoints inside locks needed by subsequent arrivals.
6. **Observe results safely**: use `AtomicInteger` for event counts, or collect `Future`s and assert after completion. Do not let instrumentation introduce new lost updates.
7. **Set deadlines and cleanup**: timed `await`, timed `get`, executor cleanup, and detailed error messages on broken barrier or timeout.
8. **Reproduce the bug with a reproduction test**, distinguishing "a test intentionally confirming the bug" from "a regression test that must pass on correct code."
9. **Fix the right unit of atomicity**: read–modify–write under the same lock, atomic operation, transaction, or separated ownership. Never fix by adding delays or spawning more threads.
10. **Run regression and stress tests on the real implementation**, and review happens-before, visibility, and any remaining shared state.
11. **Keep tests independent**: do not reuse broken barriers, counters, or mutable static state across test cases without proper resets.
12. **Document what the test covers**: it proves a specific interleaving and expected outcome, not every possible schedule on every CPU/JVM.

## 15. Self-Check Questions

**1. Why does running `count++` 100,000 times across multiple threads and getting the right answer still not prove thread safety?** Because the test only exercises a limited set of schedules; there is no happens-before protecting the read–modify–write, so lost updates can still occur under other interleavings.

**2. If you want both threads to read `count=0` before writing, what should you choose?** `CyclicBarrier(2)` placed after the read step and before the write step, or two latches so main waits for both read signals before opening the write gate.

**3. Why shouldn't you place `barrier.await()` inside a `synchronized` method that both threads must enter?** The first thread acquires the monitor and waits for the second; the second thread waits for that same monitor and can never reach the barrier. The test deadlocks itself.

**4. If you use `volatile int count`, does that eliminate lost updates?** No. `volatile` guarantees visibility/ordering of individual accesses, not atomicity of the read–add–write sequence as a whole.

**5. Why do we need `AtomicInteger` to count booking confirmations in the test?** So the measurement itself does not lose updates. If an unsynchronized `int confirmations++` were used, the confirmation count could be underreported, masking the business race.

**6. Does `Future.get(timeout)` throwing `TimeoutException` mean the task has stopped?** Not necessarily. Only the caller's wait timed out; you must cancel/interrupt and manage the task lifecycle, and I/O operations may not respond to interrupts immediately.

**7. Are separate calls to `ConcurrentHashMap.containsKey` followed by `put` safe for a "create only once" invariant?** Not necessarily. Individual operations are thread-safe, but check–then–act is not atomic; use an appropriate atomic API or design to avoid duplicate side effects.

**8. Can a barrier be used to prove a visibility bug caused by a field missing `volatile`?** Be careful: the barrier itself introduces synchronization/happens-before, which can hide the exact bug you want to test. For JMM memory-ordering issues, design an appropriate litmus test.

## 16. Summary for Practice

A good race test has **three distinct parts**: (1) an *invariant* describing what must hold true, (2) an *interleaving* describing a specific path that can break it, and (3) *orchestration* that makes that path happen in a controlled way. `CountDownLatch` and `CyclicBarrier` are testing tools for observing or forcing checkpoints; they do not fix production logic on their own.

For read–modify–write and check–then–act bugs, step-by-step coordination lets you reproduce lost updates or double bookings almost immediately in a runnable example, instead of looping thousands of times by luck. Once the bug is observed, you must bring **the entire invariant** under the same atomic mechanism (`synchronized`, `Lock`, CAS/atomic operations, or proper ownership), and then re-verify against the real operation. Race conditions can be **detected** through testing; long-term correctness must be **explained** through synchronization contracts and the Java Memory Model.
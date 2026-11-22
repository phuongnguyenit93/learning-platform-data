# Testing Correctness When Multiple Tasks Access Shared State — Java Concurrency

## 1. Why Is Concurrency Testing Hard?

In Java, multiple threads can access the same **shared mutable state**. When reads and writes interleave across different execution schedules, code that appears correct on a single thread can suffer from lost updates, observe partially updated state, or wait on each other forever. Bugs can disappear when you attach a debugger, add logging, or rerun the test.

A single passing test run only shows that the execution schedule encountered did not reveal a problem; it **does not prove** that the implementation is always correct under every interleaving. A valuable test must express the contract accurately, actively create contention, collect results from all tasks, and check invariants that must never be violated.

This article covers **general Java concurrency** (`java.lang` and `java.util.concurrent`, the Java Memory Model, threads/executors, synchronization) and does not cover Spring-specific features or configuration.

After this article, you will know how to:

- Define correctness using **invariants**, preconditions/postconditions, safety, and liveness.
- Recognize lost updates, check-then-act races, visibility issues, ordering issues, and inconsistent multi-variable state.
- Coordinate threads with `CountDownLatch`/`CyclicBarrier`, use `Future.get()` to surface failures, and know when to assert.
- Create a Java 17+ example that deterministically reproduces a lost update and compare it against `AtomicInteger`.
- Write JUnit 5 tests for multiple workers mutating the same state and avoid bugs in the test harness itself.
- Use stress testing, operation histories, and specialized concurrency tools to broaden test coverage.

## 2. Define Correctness Before Creating Threads

### Safety — No Outcomes That Violate the Contract

For example: if 8 workers each increment a counter 2,000 times, the result **after all 8 have completed** must be `16_000`. If the result is smaller, one or more updates may have been lost.

With 1 ticket remaining and two concurrent booking requests, the contract may allow either A or B to win; what is **not allowed** is for both to succeed or for the ticket count to go negative. The test must accept every valid ordering rather than forcing a specific winner.

With multiple variables, the test needs a joint invariant: when transferring a quantity from `available` to `reserved`, the sum `available + reserved` must remain equal to the initial amount. Asserting only one field is not enough to prove overall state consistency.

### Liveness — Tasks Can Still Make Progress

A program may never write corrupted data yet suffer from deadlock, livelock, starvation, or waiting indefinitely for a resource. Tests must set a deadline when waiting for workers, capture diagnostic information, and clean up resources. A timeout **does not by itself prove deadlock**: slow CI machines, GC pauses, resource exhaustion, or slow I/O can also cause timeouts.

### Atomicity, Visibility, Ordering

- **Atomicity:** a business operation must take effect as a single unit when required by the contract. `counter++` consists of read–add–write; it is not atomic under multiple writers.
- **Visibility:** a thread must observe updates made by another thread at the point required by the contract. Writing to a plain variable without proper synchronization can lead to stale reads.
- **Ordering:** if the rule is "write data first, then publish the ready flag," there must be a happens-before relationship for the reader; `Thread.sleep()` does not establish that relationship.

A **data race** occurs when there are conflicting accesses to the same plain variable, at least one of which is a write, not ordered by happens-before. A **race condition** is broader: an incorrect outcome depends on the order of operations, even when individual `get`/`put` operations are thread-safe but a multi-step sequence is not atomic.

## 3. Designing the Test Oracle

An **oracle** is an unambiguous condition that determines pass/fail, independent of which task the scheduler runs first. Document the initial state, allowed operations, final state, runtime invariants, and completion deadlines.

| Scenario | Correctness Oracle | Notes |
| --- | --- | --- |
| N workers increment a shared counter | After all finish, value equals `N × increments` | Do not assert while workers are still running |
| Two requests claim the last resource | At most one succeeds; count is non-negative | Do not require task A to win |
| Transfer money/inventory between two buckets | Sum of source + destination is conserved | Snapshots must be consistent |
| Cache creates a key | No duplicate side effects violating the contract | `get` then `put` is a compound operation |
| Writer publishes configuration | Reader only sees validly initialized configuration | Requires safe publication |
| Multiple tasks hold locks | Completes within a preset time limit | Timeouts need thread dumps for diagnosis |

Distinguish between **asserting final state** and **asserting state during execution**. Reading two `AtomicInteger` instances sequentially does not automatically produce an atomic snapshot of the pair. If the contract requires every snapshot to be consistent, you need a synchronized snapshot, an atomically published immutable object, or an equivalent mechanism.

## 4. Coordinate Execution Schedules With Synchronization, Not Sleep

A controlled contention testing pattern:

1. Create an executor with **enough** workers for all tasks waiting together at the start gate.
2. Each worker calls `ready.countDown()` and then `start.await()`.
3. The test thread waits on `ready.await(timeout)` to confirm all workers are ready.
4. Open the gate with `start.countDown()` so the operations are allowed to begin together.
5. Wait for **all** `Future.get(timeout)` calls. If a task throws an exception, `get` throws `ExecutionException` and the test must fail.
6. Once all workers have finished, verify the oracle; release the gate and shut down the executor in `finally`, including on error paths.

`CountDownLatch` is a one-shot gate. `CyclicBarrier` is convenient when workers must rendezvous across multiple rounds with the same number of participants, though it can become broken on timeout/interrupt. `Phaser` supports more flexible phases and dynamic participant counts. Choose based on the test's goal; do not add extra mechanisms just for complexity.

**Deadlock trap in tests:** if you submit 8 tasks that all wait on a gate to an executor with only 2 workers, the first two tasks occupy the workers and wait, while the remaining six never get scheduled to signal ready. The coordinator thread also waits for all 8 to be ready, so nobody opens the gate. Use a pool of at least 8 workers for this pattern, with timeouts and cleanup, or design a different coordination approach.

**Opening the gate together does not mean running at the exact same nanosecond.** This pattern increases contention and controls when tasks are permitted to run; actual scheduling is still decided by the JVM/OS. To force a specific read–modify–write schedule, place synchronization points **between steps** of the operation in the test environment.

## 5. Java 17+ Example: Deterministically Reproducing a Lost Update

The following program intentionally splits a plain counter increment into "read first, write later." Both workers are forced to **finish reading before either writes**, so both read `0` and both write `1`. It then compares this with `AtomicInteger.incrementAndGet()`, which performs an atomic increment.

Create the file **`SharedStateCorrectnessDemo.java`** with the following complete code:

```java
import java.util.concurrent.Callable;
import java.util.concurrent.CountDownLatch;
import java.util.concurrent.ExecutorService;
import java.util.concurrent.Executors;
import java.util.concurrent.Future;
import java.util.concurrent.TimeUnit;
import java.util.concurrent.atomic.AtomicInteger;

public class SharedStateCorrectnessDemo {
    private static final class UnsafeCounter {
        int value;

        void incrementInTwoPhases(
                CountDownLatch bothRead,
                CountDownLatch allowWrite) throws InterruptedException {
            int previous = value;
            bothRead.countDown();
            if (!allowWrite.await(3, TimeUnit.SECONDS)) {
                throw new IllegalStateException("Timed out before write");
            }
            value = previous + 1;
        }
    }

    public static void main(String[] args) throws Exception {
        ExecutorService executor = Executors.newFixedThreadPool(2);
        try {
            int unsafe = runUnsafe(executor);
            if (unsafe != 1) {
                throw new AssertionError("Unexpected demo result");
            }
            System.out.println("unsafe: actual=1, required=2 (lost update)");

            int safe = runAtomic(executor);
            if (safe != 2) {
                throw new AssertionError("Atomic update was lost");
            }
            System.out.println("atomic: actual=2, required=2 (correct)");
        } finally {
            executor.shutdownNow();
            executor.awaitTermination(3, TimeUnit.SECONDS);
        }
    }

    private static int runUnsafe(ExecutorService executor) throws Exception {
        UnsafeCounter counter = new UnsafeCounter();
        CountDownLatch bothRead = new CountDownLatch(2);
        CountDownLatch allowWrite = new CountDownLatch(1);

        Callable<Void> task = () -> {
            counter.incrementInTwoPhases(bothRead, allowWrite);
            return null;
        };
        Future<Void> first = executor.submit(task);
        Future<Void> second = executor.submit(task);

        try {
            check(bothRead.await(3, TimeUnit.SECONDS),
                    "Both workers must read before writing");
            allowWrite.countDown();
            first.get(3, TimeUnit.SECONDS);
            second.get(3, TimeUnit.SECONDS);
            return counter.value;
        } finally {
            allowWrite.countDown();
        }
    }

    private static int runAtomic(ExecutorService executor) throws Exception {
        AtomicInteger counter = new AtomicInteger();
        CountDownLatch ready = new CountDownLatch(2);
        CountDownLatch start = new CountDownLatch(1);

        Callable<Void> task = () -> {
            ready.countDown();
            if (!start.await(3, TimeUnit.SECONDS)) {
                throw new IllegalStateException("Start gate timeout");
            }
            counter.incrementAndGet();
            return null;
        };
        Future<Void> first = executor.submit(task);
        Future<Void> second = executor.submit(task);

        try {
            check(ready.await(3, TimeUnit.SECONDS),
                    "Both workers must reach the start gate");
            start.countDown();
            first.get(3, TimeUnit.SECONDS);
            second.get(3, TimeUnit.SECONDS);
            return counter.get();
        } finally {
            start.countDown();
        }
    }

    private static void check(boolean ok, String message) {
        if (!ok) {
            throw new AssertionError(message);
        }
    }
}
```

Compile/run on JDK 17 or later:

```bash
javac SharedStateCorrectnessDemo.java
java SharedStateCorrectnessDemo
```

Output when the program runs successfully:

```text
unsafe: actual=1, required=2 (lost update)
atomic: actual=2, required=2 (correct)
```

**Exact explanation of the output:**

- Both tasks share the **same instance** of `UnsafeCounter`. Each task reads `value` into `previous` before calling `bothRead.countDown()`. Main only allows writing once both have signaled that they read, so both saved `previous = 0`. Both subsequent assignments are `value = 1`. The result `1` is a lost update bug.
- `runAtomic` also releases two tasks from the gate together, but `incrementAndGet()` provides an atomic read–modify–write. After both futures complete, the result is `2`.
- This demo **intentionally verifies that the bug was reproduced**; in a regression test for real code, the oracle must be `2` and an implementation returning `1` **must fail**.
- `Future.get(timeout)` waits for completion and propagates task exceptions back to main; no code assumes a worker finished just because a `sleep` interval elapsed.
- The `finally` blocks open the latches to avoid leaving workers stuck if main fails. `shutdownNow()` requests best-effort interruption and does not guarantee arbitrary tasks stop immediately.

This pattern intentionally injects synchronization points into a buggy algorithm to construct a counterexample. When testing real business code, do not alter production behavior just to "fix" a race; use a test hook or an appropriate seam when you need to observe execution schedules.

## 6. JUnit 5 Example: Verifying No Increments Are Lost Under Contention

This is a **JUnit Jupiter 5 test class**, intended for a project with JUnit Jupiter declared and a test runner configured. It illustrates a reusable test pattern where you can swap in the counter implementation under development. Do not run this file directly with `java` without dependencies/a test runner.

```java
import static org.junit.jupiter.api.Assertions.assertEquals;
import static org.junit.jupiter.api.Assertions.assertTrue;

import java.util.ArrayList;
import java.util.List;
import java.util.concurrent.CountDownLatch;
import java.util.concurrent.ExecutorService;
import java.util.concurrent.Executors;
import java.util.concurrent.Future;
import java.util.concurrent.TimeUnit;
import java.util.concurrent.atomic.AtomicInteger;
import org.junit.jupiter.api.Test;

class ConcurrentCounterTest {
    @Test
    void allConcurrentIncrementsArePreserved() throws Exception {
        int workers = 8;
        int iterationsPerWorker = 2_000;
        AtomicInteger counter = new AtomicInteger();

        ExecutorService executor = Executors.newFixedThreadPool(workers);
        CountDownLatch ready = new CountDownLatch(workers);
        CountDownLatch start = new CountDownLatch(1);
        List<Future<?>> futures = new ArrayList<>();

        try {
            for (int i = 0; i < workers; i++) {
                futures.add(executor.submit(() -> {
                    ready.countDown();
                    if (!start.await(5, TimeUnit.SECONDS)) {
                        throw new IllegalStateException("Start timeout");
                    }
                    for (int j = 0; j < iterationsPerWorker; j++) {
                        counter.incrementAndGet();
                    }
                    return null;
                }));
            }

            assertTrue(ready.await(5, TimeUnit.SECONDS),
                    "Some workers did not reach start gate");
            start.countDown();
            for (Future<?> future : futures) {
                future.get(10, TimeUnit.SECONDS);
            }
            assertEquals(workers * iterationsPerWorker, counter.get());
        } finally {
            start.countDown();
            executor.shutdownNow();
            executor.awaitTermination(5, TimeUnit.SECONDS);
        }
    }
}
```

**What does this verify?** Eight workers mutate the same state; all workers are "ready" before the gate opens; every future is observed; only after completion does it assert `8 × 2_000 = 16_000`. If a task throws an exception, `Future.get()` fails the test instead of silently ignoring it. The `finally` block releases the gate and cleans up the executor.

`AtomicInteger` already carries the JDK's atomicity guarantee; in your application, replace it with the **actual class/method under test**, keep the same oracle, and use a single shared instance. The 5- and 10-second timeouts here are illustrative; choose values suited to your CI environment and reasonable progress bounds. If `shutdownNow()` is called while a task has not yet stopped, ensure the test harness prevents still-running background workers from mutating state shared with subsequent tests.

## 7. Multi-Field Invariants: Per-Field Atomicity Is Not Enough

Suppose a system starts with `available = 100` and `reserved = 0`. Each reservation moves 30 from available to reserved. If the contract requires every snapshot to be valid, the invariants are:

- `available >= 0`.
- `reserved >= 0`.
- `available + reserved == 100`.

Two `AtomicInteger` fields with two separate `addAndGet` calls can still expose a temporary sum of 70 or 130 to a reader between the two updates. If concurrent snapshots must be consistent, updates and snapshots must be coordinated as **one logical transaction**.

Component code example (not a standalone program with `main()`):

```java
final class ReservationBook {
    private int available = 100;
    private int reserved = 0;

    synchronized boolean reserve(int amount) {
        if (amount <= 0 || amount > available) {
            return false;
        }
        available -= amount;
        reserved += amount;
        return true;
    }

    synchronized Snapshot snapshot() {
        return new Snapshot(available, reserved);
    }

    record Snapshot(int available, int reserved) {}
}
```

If two threads both request 80, **exactly one request must succeed**; after completion, the snapshot must be `(20, 80)`. To test the invariant while writers are running, use a reader thread that continuously calls `snapshot()`, asserts the invariant on each snapshot, and stops via a proper flag/synchronization once all writers finish. Do not read `available` and `reserved` separately via unsynchronized getters and conclude the class is inconsistent.

With `ConcurrentHashMap`, `get` and `put` are individually thread-safe, yet the sequence `if (map.get(key) == null) map.put(key, value)` still has a check-then-act window: two threads can both see the key as absent and both execute the side effect that creates the value. You may need `putIfAbsent` or `computeIfAbsent`, though side effects outside the map (such as recording a payment) also require separate idempotency/coordination design. A thread-safe collection **does not automatically make a multi-statement business operation atomic**.

## 8. Happens-Before and the Java Memory Model in Tests

Key memory relationships to understand:

- Program order within a single thread is a source of happens-before.
- An unlock of a monitor happens-before every subsequent lock of the **same monitor**.
- A write to a `volatile` field happens-before every subsequent read of that same `volatile` field; atomic primitives also have specified memory semantics.
- Actions before `Thread.start()` happen-before actions in the started thread; actions in a terminating thread happen-before another thread detects termination via a successful `join()`.
- For executors, actions before `submit` happen-before the task's actions; the task's actions happen-before actions after a successful `Future.get()`.
- For latches, actions before `countDown()` happen-before actions after the corresponding `await()` returns successfully.

Because `Future.get()` establishes synchronization with a completed task, main can observe state written by the tasks **after all futures complete**. However, that does not heal races between tasks: if both read stale values and overwrite each other, the final value can still be wrong.

In particular, `volatile int counter; counter++` is still not atomic: visibility is improved, but the read–modify–write can still lose updates. With multiple writers, use `AtomicInteger.incrementAndGet()`, an appropriate lock, or partition state ownership so mutable data does not need to be shared.

When testing safe publication, the reader must not rely on "waiting an extra 100 ms" to be sure it sees the value. If a writer publishes an object without synchronization, a test cannot expect the JVM to expose the bug on every run. Use a proper publication mechanism (`volatile`, correctly used final-field semantics, a monitor, a queue, or a synchronizer) before relying on test results.

## 9. Testing Ordering and Linearizability

Not all concurrent state requires a single fixed outcome order. If two requests compete for the last ticket, both A-wins/B-loses and B-wins/A-loses are valid schedules. However, a schedule where **both win** is a violation.

**Linearizability** means each operation appears to take effect atomically at a single point in time between its invocation and its response, while preserving the real-time order of non-overlapping operations. To test a complex API:

1. Record a history containing operation ID, input, invocation and completion timestamps, and output/exception.
2. Define a correct sequential model for the state and its transitions.
3. Search for a sequential schedule that matches the history and preserves the order of non-overlapping calls.
4. If no valid schedule exists, the history is a counterexample; if one exists, only **that history passed**—it does not prove all future histories are valid.

Log timestamps only provide observations; logging inside or outside a lock can alter timing and is not necessarily the point where an operation takes effect. For simple problems, assert the final invariant; for complex state-machine APIs, consider a dedicated checker or model-based testing.

## 10. Stress Testing, Randomized Testing, and jcstress

A latch-forced schedule proves one scenario; other bugs may require rare schedules or reorderings caused by JVM/hardware optimizations. Additional testing layers:

| Method | Strengths | Limitations |
| --- | --- | --- |
| Controlled interleaving tests | Reliably reproduces specific bugs, easy to debug | Only tests the orchestrated schedule |
| High-iteration contention tests | Detects lost updates and broken invariants under contention | Can pass by coincidence |
| Stress/randomized tests, repeated with seeds | Covers many schedules, helps find counterexamples | Does not provide absolute proof |
| Model-based/linearizability checking | Compares history against a sequential contract | Depends on the model and history completeness |
| OpenJDK **jcstress** | Describes actors/outcomes to test tricky Java Memory Model cases | Requires a harness and understanding of allowed/forbidden outcomes and the environment |
| Load/soak tests | Finds bottlenecks, resource leaks, and liveness issues under load | Good throughput does not prove safety |

Do not use `Thread.yield()` or `Thread.sleep()` as a guarantee of producing an interleaving. They only nudge scheduling; the fact that a bug stops reproducing after adding a sleep does not mean it is fixed.

For randomized tests, record the **seed, worker count, iteration count, JVM/OS, CPU configuration, duration, inputs, and operation history**. When a bug is found, try to distill a short test with latches/barriers that forces that exact schedule to prevent regressions. Each trial round should create fresh state or reset completely; never let threads, tasks, or caches from a previous round interfere with the next.

## 11. Diagnosing Failures and Timeouts

When a test fails, useful diagnostics include: initial state, the violated invariant, counts of succeeded/failed operations, exceptions from each future, final state, seed, and synchronization checkpoints reached.

When a test hangs, capture a thread dump to see which threads are `BLOCKED`, `WAITING`, or `TIMED_WAITING`, which monitors/locks are held, and which resources are being waited on. `ThreadMXBean.findDeadlockedThreads()` can detect monitor deadlocks and some ownable synchronizer deadlocks; it does not detect all logical waits, such as waiting on a latch because the test never opened the gate. Distinguish real deadlocks from executor worker starvation, long GC pauses, hung I/O, and CPU saturation.

Do not overuse print/log statements inside contention loops: logging changes timing and involves locks/I/O itself. Instead, record events with operation IDs into a bounded buffer, or enable selective instrumentation only when needed. Check for exceptions propagated from workers before inspecting results.

## 12. Common Mistakes in Concurrency Tests

- **Asserting too early:** `submit` only schedules work, it does not wait for completion; always wait for the contract's completion point before asserting final state.
- **Ignoring `Future.get()`:** worker exceptions stay trapped inside the future, easily producing false-green tests.
- **Using `sleep` to wait:** timing is sensitive to hardware and the scheduler, making tests flaky; use synchronization + deadlines.
- **Pool smaller than the number of tasks waiting on a barrier:** the test deadlocks because queued tasks cannot run to signal ready.
- **Not releasing latches in `finally`:** a failing test leaves workers hanging, affecting subsequent tests.
- **Testing with separate instances:** each task mutates different state, so there is no real contention.
- **Checking only a counter:** overlooking cross-field invariants, unique side effects, or ordering requirements.
- **Reading unsynchronized snapshots:** mistaking valid intermediate states for bugs, or conversely missing invalid states.
- **Using `volatile` as an atomic increment:** visibility does not imply atomicity.
- **Running a stress test 10,000 times and declaring it proven correct:** not all valid schedules have been exercised.
- **Skipping cleanup:** live executors, callbacks, or threads can keep mutating shared state after the test ends.

## 13. Practical Workflow

1. Explicitly write down initial state, concurrent operations, invariants, allowed final outcomes, and progress deadlines.
2. Identify potential interleaving points: read–modify–write, check-then-act, publication, locking, and multi-variable snapshots.
3. Write a small test that orchestrates the risky schedule using latches/barriers and asserts the **contract**.
4. Ensure all workers share the same state, enough workers are available, gates are opened, and all futures are awaited.
5. Fix the code using atomics, locks, concurrent collections, or by eliminating shared mutable state; never fix bugs with delays.
6. Add contention/stress tests, and test exceptions, cancellation, timeouts, shutdown, and tricky interleavings.
7. When a failure occurs, save the counterexample with its seed/history and turn it into a reproducible regression test.

**Key takeaway:** concurrency testing must target **correctness under all valid execution schedules**, not merely "running in parallel without throwing exceptions." Invariants form the oracle; test synchronization creates controlled contention; futures and timeouts provide completion visibility; stress testing and specialized tools uncover schedules that unit tests have not yet reached.

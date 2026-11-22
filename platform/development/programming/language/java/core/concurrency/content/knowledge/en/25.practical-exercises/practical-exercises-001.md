# Practical Exercise: Building a Racy Counter and Fixing It Step by Step with Lock and Atomic

## 1. Objectives and Expected Outcomes

This exercise sets up a shared counter in a Java program: multiple threads call **increment()** concurrently, and each call must increase the total by exactly one. We will intentionally build a broken version using **value++**, reproduce a *lost update*, and then fix it sequentially using **ReentrantLock** and **AtomicInteger**. Finally, we will run real threads on an ExecutorService and verify the expected value automatically.

After completing this exercise, you should be able to explain and verify:

1. Why incrementing a regular **int** field is unsafe when multiple threads write concurrently.
2. Why increasing the thread count or inserting Thread.sleep is not a reliable way to prove a race condition.
3. Why a lock must protect the **entire read → compute → write sequence**, not just part of it.
4. How AtomicInteger provides atomic increment operations, and when it is more suitable than a lock.
5. How to build a test with **clear pass/fail criteria**, timeouts, and worker exception checks.
6. How to choose between a lock and an atomic when the data consists of a single counter versus multiple states that must change together.

This is a **general Java** concurrency exercise using JDK 17+ APIs. No Spring or testing framework is required.

## 2. Counter Design and Correctness Criteria

Suppose there are 4 workers, each performing 25,000 increments. If the counter starts at 0 and no call fails, the result must be:

~~~text
4 workers × 25,000 increments/worker = 100,000 increments
Expected final counter = 100000
~~~

We define a minimal contract:

~~~java
interface Counter {
    void increment();
    int value();
}
~~~

This snippet is integrated into the complete program in Section 4. The **invariant** to maintain: once all increments have completed normally, the value read equals the total number of increments performed. If a counter has a race condition, the value may be less than the total count because two threads overwrite each other's results.

In terms of execution steps, a single **value++** is semantically equivalent to:

~~~java
int old = value;
int next = old + 1;
value = next;
~~~

These three lines illustrate a multi-step operation; they do not claim that the JVM must compile `++` into exactly three instructions. The read/compute/write steps can interleave with other threads.

### Execution Schedule Causing a Lost Update

| Step | Worker A | Worker B | Shared value |
| --- | --- | --- | ---: |
| 0 | — | — | 0 |
| 1 | Read 0 | — | 0 |
| 2 | — | Read 0 | 0 |
| 3 | Compute 0 + 1 | — | 0 |
| 4 | — | Compute 0 + 1 | 0 |
| 5 | Write 1 | — | 1 |
| 6 | — | Write 1 | 1 |

Two increments were requested, yet the final result is only 1. If A finishes completely before B reads, the result may be 2. **Occasionally getting the right result does not prove the code is thread-safe**.

The bug here involves **atomicity** and unsynchronized access to a shared field. Marking the field **volatile** can improve visibility, but it does not turn a read-modify-write sequence into an atomic increment; two threads can still both read 0 and both write 1.

## 3. Three Versions to Build

### Version 1 — UnsafeCounter

~~~java
private int value;

public void increment() {
    value++; // non-atomic read-modify-write
}

public int value() {
    return value;
}
~~~

This is the body of a class, not a standalone program. All threads share **the same instance** of the counter. If each thread creates its own counter, there will be no contention and the test will fail to exercise shared-data bugs.

### Version 2 — LockCounter

~~~java
private final ReentrantLock lock = new ReentrantLock();
private int value;

public void increment() {
    lock.lock();
    try {
        value++;
    } finally {
        lock.unlock();
    }
}

public int value() {
    lock.lock();
    try {
        return value;
    } finally {
        lock.unlock();
    }
}
~~~

While one thread holds the lock, another thread cannot simultaneously enter the increment region guarded by **the same lock**. The read in `value()` also uses that lock to guarantee consistency when reading while writers are active.

**finally** is mandatory in the manual locking pattern: if the body throws an exception, the lock is still released. Never let a return, exception, or conditional branch skip `unlock()`.

### Version 3 — AtomicCounter

~~~java
private final AtomicInteger value = new AtomicInteger();

public void increment() {
    value.incrementAndGet();
}

public int value() {
    return value.get();
}
~~~

`AtomicInteger.incrementAndGet` provides an atomic update on **a single variable**, so no increments are lost. Java implements the appropriate atomic update mechanism for the JVM/platform; there is no need to write a manual compare-and-set loop just to add one.

The three snippets above are combined into three complete classes in the next example. Do not combine two synchronization mechanisms just to fix a single counter variable when there is no additional requirement.

## 4. Complete, Runnable Java 17 Program

The program sets up two types of experiments:

- **Controlled reproduction experiment**: two workers both read the old value before writing so that a lost update is guaranteed to happen. This visualizes the read-modify-write bug; the synchronization point is a test harness tool, not production code.
- **Concurrent load experiment**: 4 workers, each actually calling `increment()` 25,000 times on the lock-based counter and the atomic counter. After all `Future`s complete, the result must be 100,000.

**Create the file CounterExercise.java:**

~~~java
import java.util.ArrayList;
import java.util.List;
import java.util.concurrent.Callable;
import java.util.concurrent.CountDownLatch;
import java.util.concurrent.CyclicBarrier;
import java.util.concurrent.ExecutorService;
import java.util.concurrent.Executors;
import java.util.concurrent.Future;
import java.util.concurrent.TimeUnit;
import java.util.concurrent.TimeoutException;
import java.util.concurrent.atomic.AtomicInteger;
import java.util.concurrent.locks.ReentrantLock;

public final class CounterExercise {

    private static final int WORKERS = 4;
    private static final int INCREMENTS_PER_WORKER = 25_000;

    interface Counter {
        void increment();
        int value();
    }

    static final class UnsafeCounter implements Counter {
        private int value;

        @Override
        public void increment() {
            value++;
        }

        @Override
        public int value() {
            return value;
        }

        // Used only by the harness to force a read-then-write schedule that causes a lost update.
        int snapshot() {
            return value;
        }

        void store(int updated) {
            value = updated;
        }
    }

    static final class LockCounter implements Counter {
        private final ReentrantLock lock = new ReentrantLock();
        private int value;

        @Override
        public void increment() {
            lock.lock();
            try {
                value++;
            } finally {
                lock.unlock();
            }
        }

        @Override
        public int value() {
            lock.lock();
            try {
                return value;
            } finally {
                lock.unlock();
            }
        }
    }

    static final class AtomicCounter implements Counter {
        private final AtomicInteger value = new AtomicInteger();

        @Override
        public void increment() {
            value.incrementAndGet();
        }

        @Override
        public int value() {
            return value.get();
        }
    }

    static int forceLostUpdate() throws Exception {
        UnsafeCounter counter = new UnsafeCounter();
        CyclicBarrier bothRead = new CyclicBarrier(2);
        ExecutorService pool = Executors.newFixedThreadPool(2);
        Future<Void> first = null;
        Future<Void> second = null;

        try {
            Callable<Void> unsafeReadModifyWrite = () -> {
                int seen = counter.snapshot();

                // Every worker must finish reading before any worker writes.
                bothRead.await(5, TimeUnit.SECONDS);

                counter.store(seen + 1);
                return null;
            };

            first = pool.submit(unsafeReadModifyWrite);
            second = pool.submit(unsafeReadModifyWrite);

            first.get(10, TimeUnit.SECONDS);
            second.get(10, TimeUnit.SECONDS);
            return counter.value();
        } finally {
            if (first != null) first.cancel(true);
            if (second != null) second.cancel(true);
            pool.shutdownNow();
        }
    }

    static int runConcurrentLoad(Counter counter) throws Exception {
        ExecutorService pool = Executors.newFixedThreadPool(WORKERS);
        CountDownLatch ready = new CountDownLatch(WORKERS);
        CountDownLatch start = new CountDownLatch(1);
        List<Future<Void>> futures = new ArrayList<>();

        try {
            for (int i = 0; i < WORKERS; i++) {
                Future<Void> future = pool.submit(() -> {
                    ready.countDown();

                    if (!start.await(5, TimeUnit.SECONDS)) {
                        throw new TimeoutException("Start gate timed out");
                    }

                    for (int j = 0; j < INCREMENTS_PER_WORKER; j++) {
                        if (Thread.currentThread().isInterrupted()) {
                            throw new InterruptedException("Worker cancelled");
                        }
                        counter.increment();
                    }
                    return null;
                });
                futures.add(future);
            }

            if (!ready.await(5, TimeUnit.SECONDS)) {
                throw new TimeoutException("Workers were not ready");
            }

            start.countDown();

            // Retrieve worker exceptions while waiting for all workers to complete.
            for (Future<Void> future : futures) {
                future.get(10, TimeUnit.SECONDS);
            }
            return counter.value();
        } finally {
            start.countDown(); // Release workers if main fails early.
            for (Future<Void> future : futures) {
                future.cancel(true);
            }
            pool.shutdownNow();
        }
    }

    public static void main(String[] args) throws Exception {
        int expected = WORKERS * INCREMENTS_PER_WORKER;

        int lostUpdate = forceLostUpdate();
        int locked = runConcurrentLoad(new LockCounter());
        int atomic = runConcurrentLoad(new AtomicCounter());

        System.out.println("Forced lost update: " + lostUpdate + " / 2");
        System.out.println("ReentrantLock: " + locked + " / " + expected);
        System.out.println("AtomicInteger: " + atomic + " / " + expected);

        if (lostUpdate != 1 || locked != expected || atomic != expected) {
            throw new AssertionError("Counter invariant failed");
        }
    }
}
~~~

Use JDK 17 or newer:

~~~bash
javac CounterExercise.java
java CounterExercise
~~~

**Stdout when the program runs successfully:**

~~~text
Forced lost update: 1 / 2
ReentrantLock: 100000 / 100000
AtomicInteger: 100000 / 100000
~~~

If the environment is too slow or a worker fails, the program may throw an exception instead of printing the three lines above. The 5- and 10-second timeouts are **exercise guardrails**, not performance guarantees for real-world applications.

### Why Are the Results Verifiable?

**forceLostUpdate():** Each worker reads the initial value 0. The barrier forces both to finish reading before either writes. Thus both call `store(1)`, and the final result is always 1 when the barrier completes normally. This access is intentionally unsynchronized to expose the lost update; `snapshot()`/`store()` exist solely for the harness. In buggy production code, the same issue lies inside `value++`.

**runConcurrentLoad():** Each worker signals `ready`, then waits at the `start` gate. `main` opens the gate only after all four workers have reached the ready point; this increases the chance of contention, though it **does not guarantee** catching a race if you pass `UnsafeCounter` into the load test. The sample test targets the two fixed versions, whose results always match the lock/atomic contract when workers complete normally.

**Future.get():** `main` waits for each worker to finish and receives any worker exception via `ExecutionException`. Once all `Future.get()` calls succeed, actions inside the tasks happen-before subsequent processing in `main`, so reading the value afterward has a proper synchronization point.

**Invariant check:** `main` verifies `lostUpdate = 1` for the **staged broken version**, and `locked = atomic = 100,000` for the **two fixed versions**. These are two different test oracles; never carry `expected = 1` over to tests for the fixed versions.

## 5. Step-by-Step Practice from Broken to Fixed

If you want to practice commit by commit or fix by fix, follow this sequence while keeping the same `Counter` problem.

### Step A — Reproduce a Real Bug with value++

Start with `UnsafeCounter`. Write workers that all hold a reference to it. Each worker calls `increment()` in a loop; after completion, read `counter.value()`.

If you want to run the load test on the broken counter, temporarily add the following to `main`:

~~~java
int observedUnsafe = runConcurrentLoad(new UnsafeCounter());
System.out.println("Unsafe stress: " + observedUnsafe + " / " + expected);
~~~

This is a **modification to main**, not a standalone file. The `observedUnsafe` value **cannot be predicted exactly**: it may be less than 100,000, but it can still occasionally equal 100,000. Do not use `assert observedUnsafe != expected` to prove the bug, because a single run where the bug does not manifest will cause the test to miss its purpose. Use `forceLostUpdate()` to demonstrate a schedule that causes a lost update.

Try increasing the worker count or iteration count and observe the variance, but never conclude "there is no race" from any single passing run.

### Step B — Replace with a Lock

Create `LockCounter`, keeping the `Counter` interface unchanged. Call `lock.lock()` before reading/incrementing/writing; call `unlock()` in `finally`. Put the `value()` read under **the same lock**. Re-run `runConcurrentLoad` and verify it equals exactly 100,000.

You can also write an equivalent `synchronized` version:

~~~java
static final class SynchronizedCounter implements Counter {
    private int value;

    @Override
    public synchronized void increment() {
        value++;
    }

    @Override
    public synchronized int value() {
        return value;
    }
}
~~~

This is a class integrated into `CounterExercise.java`, sharing the `Counter` interface from the main example. The `synchronized` version uses the instance's monitor as its lock. Do not pick `ReentrantLock` just because it has "lock" in its name; choose the tool based on whether you need acquisition control, `Condition`, `tryLock`, or timeouts.

### Step C — Replace with Atomic

Create `AtomicCounter`, using `incrementAndGet()` and `get()` on **a single shared AtomicInteger**. Do not copy the `int` value out to a new shared variable and increment it yourself; the update itself must be performed on the atomic object.

Re-run `runConcurrentLoad` and assert 100,000. Remove manual locking code if the problem only involves a single atomic counter.

### Step D — Guard Both the Test and Resources

Set timeouts on wait points, ensure worker exceptions are propagated to `main`, and use `finally` to shut down the executor. If a test times out:

- Verify that the pool has enough threads for all parties waiting on `CyclicBarrier`; two parties on a single-thread pool can never pass the barrier together.
- Verify the number of `countDown` calls and when `start` is opened.
- Verify that workers do not throw before reaching the barrier or loop.
- Do not treat a timeout at a barrier or `Future.get` as evidence of a lost update.

Fix the harness whenever test preconditions are not met, and only then evaluate the business invariant.

## 6. Why Does a Lock Fix the Bug?

With `LockCounter`, the increment is protected as a **critical section**:

~~~text
Thread A: lock → read 0 → compute 1 → write 1 → unlock
Thread B:                                        lock → read 1 → compute 2 → write 2 → unlock
~~~

While A holds the lock, B cannot execute the increment block using that same lock. B only reads after A has released the lock. `ReentrantLock` establishes the corresponding synchronization relationship between an `unlock` and the subsequent `lock`; locking `value()` as well ensures readers observe consistent state under the same synchronization protocol.

Common mistakes:

1. Using **two separate lock objects** for two workers: fails to protect the shared counter.
2. Locking only the read and unlocking before the write: two workers can still capture the same stale value.
3. Locking `increment` while another write path mutates `value` directly: the invariant can still break.
4. Forgetting `unlock` in `finally`: an exception inside the critical section can leave the lock held and stall other workers.
5. Holding a lock while performing blocking I/O: increases contention, latency, and deadlock risk.
6. Trying to replace a lock with `volatile`: visibility does not solve the atomicity of `value++`.

**ReentrantLock is reentrant**: the same thread already holding the lock can acquire it again, but it must call `unlock` the same number of times. This feature does not replace designing clear critical section boundaries.

Using `lock.lockInterruptibly()` or `tryLock(timeout, unit)` lets you respond more gracefully to cancellation or timeouts while waiting for a lock. However, a basic counter only needs `lock()`, `try`, and `finally`.

## 7. Why Does AtomicInteger Fix the Bug?

`AtomicInteger` is an `int` container whose read, write, and update operations have well-defined synchronization semantics. `incrementAndGet()` is a single **atomic increment**, preventing two workers from both "committing" a new value based on the same stale snapshot as happens with unsynchronized `value++`.

`AtomicInteger` supports several useful operations:

| API | Meaning |
| --- | --- |
| `get()` | Reads the current value with atomic semantics |
| `set(v)` | Sets a new value |
| `incrementAndGet()` | Increments by 1 and returns the new value |
| `getAndIncrement()` | Returns the old value, then increments by 1 |
| `addAndGet(delta)` | Adds `delta` and returns the new value |
| `compareAndSet(expect, update)` | Updates only if the current value equals `expect`; returns `boolean` |

When the problem has a conditional update based on the old value, use an appropriate atomic operation or a compare-and-set loop. For example, decrementing only if a quota has not reached zero, written with `updateAndGet`:

~~~java
AtomicInteger quota = new AtomicInteger(3);
int remaining = quota.updateAndGet(
        current -> current > 0 ? current - 1 : current);
~~~

This snippet requires importing `java.util.concurrent.atomic.AtomicInteger`. It only expresses an **atomic state transition of a single variable**; it does not automatically ensure an external business action runs exactly once.

Important: The update function passed to `updateAndGet` may be invoked multiple times due to contention. Do not place database writes, email sending, external variable increments, or non-idempotent side effects inside the update lambda. When multiple conditions, multiple fields, or side effects must be synchronized together, a lock or an appropriate state/transaction model may be clearer.

`AtomicInteger` is also bound by **`int` limits**: if increments exceed `Integer.MAX_VALUE`, the value overflows according to `int` arithmetic. Choose `AtomicLong` or check for overflow when the value range requires it. Atomicity does not make values unbounded.

## 8. Lock vs. AtomicInteger: Which One to Choose?

| Criterion | ReentrantLock | AtomicInteger |
| --- | --- | --- |
| Protection scope | A code region, potentially spanning multiple variables | A single `int` value and atomic updates on it |
| Usage pattern | `lock → try → finally unlock` | `incrementAndGet`/`get`/`addAndGet`/CAS |
| Incrementing by 1 | Safe if all accesses follow the same lock | Directly safe via `incrementAndGet` |
| Multi-field invariants | Often convenient since it can guard the whole group | A single `AtomicInteger` is usually not enough |
| Waiting behavior | May block while waiting for the lock; supports `tryLock`, interruptible acquire | Does not hold an application-managed lock per increment |
| Common pitfalls | Forgetting `unlock`, wrong lock, deadlock, long critical sections | Combining two atomic calls and assuming the pair is atomic |
| Needs performance testing? | Yes, with real workloads and realistic contention | Yes, not automatically faster in every scenario |

For example, if state has **balance** and **transactionCount** that must be updated together, using two separate `AtomicInteger`s only makes each variable atomic individually; a reader can still observe `balance` changed while `count` has not. If you need a cross-field invariant, guard both with a single lock or represent the state as an immutable object updated atomically (e.g., an `AtomicReference` to an immutable state) when appropriate.

If the requirement is purely high-frequency statistics where reading the total does not need a linearized snapshot against ongoing updates, `LongAdder` can reduce contention under certain workloads. However, `LongAdder.sum()` is **not an atomic snapshot** while threads are still updating; do not replace `AtomicInteger` with it for sequence numbers or threshold checks requiring exact read/write semantics.

## 9. Connecting Test Results to the Java Memory Model

Several key happens-before relationships:

- Actions before `unlock` on a lock happen-before actions after the corresponding `lock` by a subsequent thread.
- `AtomicInteger` methods have memory consistency semantics defined by Java's atomic API.
- Actions before calling `ExecutorService.submit` happen-before the task's actions per `ExecutorService`'s memory consistency contract.
- Actions inside a task happen-before actions following a successful `Future.get()` for its result.
- `CountDownLatch.countDown()` happens-before actions following a successful `await()` return caused by the count reaching 0.

Because `Future.get()` succeeds for all four workers, `main` can inspect the result after work is done. However, `Future.get` **does not make unsynchronized increments inside workers atomic**: it only establishes a completion/observation point, not a fix for races between workers while running.

Similarly, the `CountDownLatch` at the start of the load test only helps workers start close together; it does not protect the shared value. The `CyclicBarrier` in `forceLostUpdate` is **placed between read and write** to intentionally lock in a broken interleaving, not as advice to put barriers into real increment logic.

Do not `synchronize` on an arbitrary object and expect all shared fields to become safe automatically. Threads must agree on **the same synchronization protocol** over the right data and the right operation scope.

## 10. Designing Proper Tests Instead of Relying on Lucky Output

There are three useful testing layers:

**Layer 1 — Staged-schedule reproduction.** `forceLostUpdate` forces both workers to read the same snapshot before writing. With two increment requests, `expected` is 1 in the **intentionally broken demo**, demonstrating a schedule that breaks the invariant. Do not use `expected = 1` as the oracle for the fixed counters.

**Layer 2 — Functional verification of the fixes.** Running `runConcurrentLoad` on `LockCounter` and `AtomicCounter`, after all workers succeed, must yield `WORKERS × INCREMENTS_PER_WORKER`. Whenever the result differs from `expected` or an exception occurs, the test must fail.

**Layer 3 — Additional stress testing.** Vary the thread count, increment count, runtime environment, number of iterations, contention on the same counter, and cancellation/timeout scenarios. Stress tests can uncover more bugs, but passing many stress runs **does not prove the absence of all possible races**.

If you run JUnit in an existing Java project, assertions can live in tests instead of `if/throw AssertionError` in `main`. The `main` method here stays independent of test libraries so learners can run it directly with JDK 17. What matters is checking the invariant and worker failures, regardless of framework name.

### Additional Cases to Test Proactively

- **0 increments:** Value must remain unchanged, with no side effects.
- **1 worker:** `UnsafeCounter` may return the right result because no other thread contends with it; this does not prove thread-safety.
- **N workers:** Both fixed versions produce `N × increments` when `int` does not overflow and all tasks complete.
- **Worker throws an exception:** `Future.get` must report the failure; never assume all increments ran.
- **Timeout/interrupt:** The test must stop cleanly and not hang indefinitely at a latch or barrier.
- **Concurrent reads and updates:** `LockCounter.value()` follows the same lock; `AtomicCounter.value()` reads atomically. Reading the counter while workers are running may return valid intermediate values and need not equal the final total.

## 11. Common Mistakes During the Exercise

| Mistake | Consequence | Fix |
| --- | --- | --- |
| Each thread creates its own `Counter` | No shared state left to test | Pass the same instance to all workers |
| Using `value++` on `int` or `volatile int` | Lost updates in read-modify-write | Lock the whole operation or use atomic increment |
| A separate lock per thread | No coordination between workers | Use the same lock object on the shared counter |
| Reading under lock, writing outside lock | The update path is no longer protected | Every related access must follow the same lock |
| Forgetting `unlock` in `finally` | Lock can stay held forever on error | `try/finally` |
| Using `sleep` to "make two threads collide" | Execution schedule is not guaranteed | Use controlled coordination points for reproduction |
| A 2-party barrier with a 1-worker pool | Worker hangs waiting for the other party | Size the pool for all workers and set timeouts |
| Not waiting on `Future.get` | `main` reads while workers are still incrementing | Wait for all `Future`s to complete |
| Worker fails yet test still passes | Result is measured on incomplete work | Retrieve `Future` exceptions and fail the test |
| Testing unsafe code, getting the right result by chance, and concluding there is no race | False negative | Forced-schedule reproduction + code review |
| Combining multiple atomic operations and treating the whole sequence as atomic | Multi-step invariants still break | Expand the lock scope or update a single atomic state |
| Putting side effects inside `updateAndGet` lambdas | Lambda may be retried | Use a pure update function |
| Comparing performance in a single short run | JIT, warm-up, and scheduler distort results | Use a proper benchmark with a representative workload |

## 12. Extension Exercises and Self-Check Questions

**Exercise 1 — Write SynchronizedCounter yourself.** Use `synchronized` to guard `increment()` and `value()`; pass that class to `runConcurrentLoad`. Explain why the result is correct, which object's monitor is the lock, and why two distinct instances do not block each other.

**Exercise 2 — Add a cap condition.** The counter must not exceed 10,000. Compare the broken pattern `if (counter.value() < 10_000) counter.increment()` against a version using a single lock for the entire check-and-increment. Explain why combining two thread-safe calls is not enough to preserve the invariant.

**Exercise 3 — Write compare-and-set.** Use `AtomicInteger` to increment only if below the cap, using a loop: read `current` → if at the threshold, return `false` → attempt `compareAndSet(current, current + 1)` → retry when CAS fails. Distinguish retries due to contention from retries of external business operations.

**Exercise 4 — Measure and explain contention.** Compare lock, atomic, and `LongAdder` as the worker count grows, setting up the benchmark properly. Do not draw conclusions from a single `javac/java` run; you need warm-up, an appropriate workload, enough iterations, and a benchmarking tool like JMH for serious evaluation.

**Exercise 5 — Test task cancellation.** Make workers intentionally wait on a gate that never opens; verify that the timeout causes the test to fail clearly, futures are cancelled, the executor is shut down, and the test does not claim it found a lost update merely because workers were missing.

Answer these before finishing:

1. If you use `volatile int` instead of `int`, why can increments still be lost?
2. Why does `Future.get()` ensure `main` reads after workers finish, yet fail to fix races inside workers?
3. When an invariant depends on both `count` and `balance`, are two separate `AtomicInteger`s enough?
4. Can you call `lock.unlock()` at the end of `try` without `finally`?
5. Why does `UnsafeCounter` matching `expected` in a single stress run not prove safety?

## 13. Completion Checklist

- [ ] A shared `Counter` has `increment` called by multiple workers.
- [ ] Can explain the read-modify-write of `value++` and an interleaving that causes a lost update.
- [ ] Reproduced forced lost update = 1 after **two** increments using the harness.
- [ ] Implemented `LockCounter` holding **the same lock** for `increment` and `value`, using `finally`.
- [ ] Implemented `AtomicCounter` with `incrementAndGet` and `get`.
- [ ] Successfully ran `CounterExercise.java` with `javac` and `java` 17+; both fixes produce 100,000/100,000.
- [ ] Worker exceptions, timeouts, and shutdown are handled; never report success when the test has not completed.
- [ ] Can distinguish incrementing a single variable from a multi-variable invariant; choose lock/atomic based on business scope.

**Learning takeaway:** Fixing a race condition is not about increasing wait times or making workers "collide less." Explicitly identify the shared state and invariant, turn the update sequence into an atomic unit using a **lock** or **AtomicInteger** as appropriate, and verify with both a bug-reproducing schedule and a regression check with clear completion conditions.

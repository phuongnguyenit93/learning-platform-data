# Reproducing Race Conditions with Latches/Barriers in Java

## 1. Why are race conditions hard to reproduce?

A **race condition** occurs when the correctness of a program depends on the order or timing in which threads execute related steps. Under normal execution, the bug may appear very rarely: the scheduler may run one thread to completion before switching to another, the development machine may have low load, or adding breakpoints/logs may inadvertently change the execution order. A test that simply “spawns many threads and hopes the bug shows up” usually cannot reliably confirm either the buggy case or the fixed case.

For example, two threads incrementing the same variable:

~~~java
int old = counter.value; // read
int next = old + 1;       // compute
counter.value = next;     // write
~~~

The increment is a **read → modify → write** sequence; it is not automatically an atomic operation. If both threads read 0 and then each writes 1, the result is 1 even though there were two increment requests. This is a **lost update**.

We can use synchronization utilities in java.util.concurrent to **force a specific execution schedule**: having both workers read the same value before allowing either worker to write. That way, the bug can be reproduced in a controlled manner, diagnosed easily, and re-verified after fixing.

This lesson focuses on **general Java concurrency**: CountDownLatch, CyclicBarrier, ExecutorService, Future, AtomicInteger, ConcurrentHashMap, and the happens-before principle in the Java Memory Model. No Spring-specific testing mechanisms or concurrency configurations are used.

## 2. Distinguishing race condition, data race, and atomicity

These three concepts are related but not identical:

| Concept | Meaning | Example |
| --- | --- | --- |
| Race condition | Correctness depends on the order of actions; the order is not controlled by contract | Two requests both see one available slot and both reserve it |
| Data race (under the Java Memory Model) | Two conflicting accesses to the same variable, at least one is a write, with no proper happens-before relationship between them | Two threads write to a plain int field without synchronization |
| Non-atomic operation | A business operation consisting of multiple steps that another thread can interleave into | get → add 1 → put on ConcurrentHashMap |

A **race condition can exist even when individual methods are thread-safe**. For example, get and put on ConcurrentHashMap are designed for concurrent access, yet the sequence get → compute → put is not combined into a single atomic action. Two threads can still read the same stale value and overwrite each other's result.

An int field declared volatile provides volatile visibility and ordering guarantees, but **volatile does not make a multi-step increment atomic**. To preserve the increment, use AtomicInteger.incrementAndGet(), synchronized guarding the entire read-modify-write, or an appropriate atomic update mechanism.

A good reproduction must specify the **ordering assumption** and the **post-execution state**, rather than merely stating that two threads were run.

## 3. Different roles of CountDownLatch and CyclicBarrier

### CountDownLatch: one-way gate

CountDownLatch has an initial count. Each countDown() decrements the count; await() waits until the count reaches 0. It is suited for two coordination patterns:

- **Ready gate**: two workers signal that they have started; main waits until both are ready.
- **Start gate**: main opens a shared gate so both workers begin the section under test.

Example:

~~~java
CountDownLatch ready = new CountDownLatch(2);
CountDownLatch start = new CountDownLatch(1);

// In each worker:
ready.countDown();
if (!start.await(5, TimeUnit.SECONDS)) {
    throw new TimeoutException("Start gate timed out");
}

// In main, after submitting both workers:
if (!ready.await(5, TimeUnit.SECONDS)) {
    throw new TimeoutException("Workers did not become ready");
}
start.countDown();
~~~

This is an **integration snippet** requiring main/worker, imports, and corresponding variables; it is not a standalone Java program. The two workers are signaled close together, but the start gate **does not guarantee they actually read the variable at the same time**. The OS can still run the first worker to completion before the second worker enters the buggy region. Therefore, using only a start latch is not enough to reproduce a lost update reliably.

CountDownLatch is **one-shot**: once it reaches 0, it does not reset its count. Each scenario/round should create a new latch if the process needs to be repeated.

### CyclicBarrier: rendezvous point for multiple threads

A CyclicBarrier with parties = 2 forces both workers to reach await() before either can proceed. Place the barrier **after the read step but before the write step** to hold both stale snapshot values:

~~~text
Worker A: read 0 ──┐
                   ├─ bothRead.await() ──> write 1
Worker B: read 0 ──┘                     ──> write 1
                                      Final result: 1
~~~

Unlike a latch, a barrier can be reused across multiple generations once the required number of parties arrive. However, if one party times out, is interrupted, or the barrier action fails, the barrier can enter the **broken** state and the other parties receive BrokenBarrierException. In a test, it is better to end the round and create a new barrier rather than resetting arbitrarily while an old worker might still be running.

**Choose the tool by goal:** latch for “ready / allowed to start”; barrier for “all have completed the read phase before moving to the write phase”.

## 4. Java 17+ experiment: forcing lost update to appear

The complete program below performs three counters across **the same two workers**:

1. Plain int field, unsynchronized read-modify-write.
2. ConcurrentHashMap with a get-then-put sequence: individual operations are thread-safe, but the whole sequence is not atomic.
3. AtomicInteger.incrementAndGet(): each increment is an atomic operation.

Both workers take snapshots before the barrier; main only prints results after both Futures complete. Assuming no timeout or environment failure, the result is consistently reproducible.

**File RaceReplayDemo.java**

~~~java
import java.util.concurrent.Callable;
import java.util.concurrent.ConcurrentHashMap;
import java.util.concurrent.CountDownLatch;
import java.util.concurrent.CyclicBarrier;
import java.util.concurrent.ExecutorService;
import java.util.concurrent.Executors;
import java.util.concurrent.Future;
import java.util.concurrent.TimeUnit;
import java.util.concurrent.TimeoutException;
import java.util.concurrent.atomic.AtomicInteger;

public final class RaceReplayDemo {

    private static final class Counter {
        int value;
    }

    public static void main(String[] args) throws Exception {
        Counter unsafeCounter = new Counter();
        ConcurrentHashMap<String, Integer> map = new ConcurrentHashMap<>();
        AtomicInteger atomicCounter = new AtomicInteger();

        CountDownLatch ready = new CountDownLatch(2);
        CountDownLatch start = new CountDownLatch(1);
        CyclicBarrier bothRead = new CyclicBarrier(2);

        ExecutorService pool = Executors.newFixedThreadPool(2);

        Callable<Void> worker = () -> {
            ready.countDown();

            if (!start.await(5, TimeUnit.SECONDS)) {
                throw new TimeoutException("Start gate timed out");
            }

            // Phase 1: both workers capture the stale value.
            int oldInt = unsafeCounter.value;
            int oldMap = map.getOrDefault("hits", 0);

            // Phase 2: neither worker may write until
            // both have finished reading.
            bothRead.await(5, TimeUnit.SECONDS);

            // Phase 3: both wrong updates write the value 1.
            unsafeCounter.value = oldInt + 1;
            map.put("hits", oldMap + 1);

            // Atomic increment does not lose updates.
            atomicCounter.incrementAndGet();
            return null;
        };

        Future<Void> first = pool.submit(worker);
        Future<Void> second = pool.submit(worker);

        try {
            if (!ready.await(5, TimeUnit.SECONDS)) {
                throw new TimeoutException("Workers did not become ready");
            }

            start.countDown();
            first.get(5, TimeUnit.SECONDS);
            second.get(5, TimeUnit.SECONDS);

            System.out.println("Yeu cau tang: 2");
            System.out.println("int khong dong bo: " + unsafeCounter.value);
            System.out.println("ConcurrentHashMap get/put: "
                    + map.get("hits"));
            System.out.println("AtomicInteger: " + atomicCounter.get());

            if (unsafeCounter.value != 1
                    || !Integer.valueOf(1).equals(map.get("hits"))
                    || atomicCounter.get() != 2) {
                throw new AssertionError("Unexpected interleaving");
            }
        } finally {
            // Open the gate if main fails before signaling.
            start.countDown();
            first.cancel(true);
            second.cancel(true);
            pool.shutdownNow();
        }
    }
}
~~~

Compile and run with Java 17 or later:

~~~bash
javac RaceReplayDemo.java
java RaceReplayDemo
~~~

Stdout when both workers complete normally:

~~~text
Yeu cau tang: 2
int khong dong bo: 1
ConcurrentHashMap get/put: 1
AtomicInteger: 2
~~~

**Why is this result reproducible?**

- ready ensures both Callables have reached the ready point before main opens start.
- After start opens, each worker captures oldInt = 0 and oldMap = 0. They cannot proceed to the write yet because they wait at bothRead.
- CyclicBarrier only releases when both workers have finished reading. Thus both carry the stale value 0 into the write phase, regardless of which worker the scheduler runs first after the barrier.
- Both write 1 into int and map: the second increment is lost. AtomicInteger performs two atomic increments, so its result is 2.
- Normal completion of first.get and second.get provides the synchronization relationship for main to observe the workers' results. Do not read results before the work completes.

The result 1 is **forced by the experiment's execution schedule**; it does not mean two threads always produce a lost update in every production schedule. If the barrier is removed, one thread may read after the other has written and the result may sometimes be 2. Therefore, a single run producing 2 does not prove the original code is safe.

The test intentionally installs synchronization points in the **harness** to reproduce an incorrect schedule. Do not insert artificial barriers into business code paths just to “fix” a race; the proper fix must make the protected operation atomic.

## 5. Why is using CountDownLatch alone not enough?

Consider a version with only a start gate:

~~~text
Main:     submit(A), submit(B) -> wait ready(2) -> start.countDown()
Worker A:                                 read 0 -> write 1
Worker B:                                             read 1 -> write 2
~~~

That schedule is completely valid even though both workers wait on a start gate. If the test writes:

~~~java
start.countDown();
first.get();
second.get();
assertEquals(1, counter.value);
~~~

then the assertion can fail because the result is 2, **not because the bug was fixed**, but because the test did not control the interleaving. This is illustrative code using test-harness variables and assertions (not a standalone Java file). A test that is “sometimes red, sometimes green” is hard to use as regression evidence.

A more precise way to control it is to place a gate **right between the two conflicting operations**: finish reading → wait for the other party to finish reading → allow writing. Then the condition that causes a lost update no longer depends on luck.

However, a barrier also establishes a happens-before relationship at the await boundary itself. It can alter timing bugs or mask another visibility bug. Use a staged schedule only to prove **this specific schedule has a bug**; do not treat a single schedule as a verification of the entire Java Memory Model or all possible races.

## 6. Fixing the bug at the right atomicity level

### Simple counter field: AtomicInteger

~~~java
AtomicInteger counter = new AtomicInteger();
counter.incrementAndGet();
~~~

If two threads call incrementAndGet, the final result is 2 after both complete, with no need to wrap with synchronized. AtomicInteger fits an independent variable with simple atomic updates. Reading multiple variables or maintaining invariants across objects requires another coordination mechanism.

### Updating a field in an object: synchronized around the whole operation

~~~java
synchronized (counter) {
    counter.value = counter.value + 1;
}
~~~

This is a snippet integrated into a program that has a counter object. Every access related to the invariant must follow **the same lock** or equivalent synchronization; locking only the read or only the write is not enough. If two workers need a barrier in a test, place the barrier **before** the synchronized block; do not let the first worker hold the monitor and wait for the second worker to also enter the same monitor, because that can create a self-inflicted deadlock.

### Concurrent map: atomic per-key merge/compute

~~~java
ConcurrentHashMap<String, Integer> counts =
        new ConcurrentHashMap<>();

counts.merge("hits", 1, Integer::sum);
~~~

merge performs the combining operation for the key using ConcurrentHashMap's atomic update mechanism, avoiding a separate get → put pair. The remapping function should be short, free of external side effects, and should not block for long. If the logic cannot be expressed as a per-key update, you must design a lock/protocol for the broader invariant.

**Verification after fixing:** Reuse the schedule goal “two threads arrive at the update phase together”, but **no longer read first and write later**. With AtomicInteger or merge, each worker invokes the complete atomic update; after the Futures complete, assert the value 2. You cannot keep the broken design of taking a snapshot before a barrier, replace only the put call with another overwriting write, and expect the race to disappear on its own.

## 7. Testing compound conditions (check-then-act), not just increments

Many race conditions take the form of checking a condition and then acting on the result:

~~~java
if (!map.containsKey(key)) {
    map.put(key, createValue());
}
~~~

Each map method may be thread-safe, yet **the whole check-then-put** is still not atomic. Two threads can both observe that the key does not exist, both run createValue(), and then one result overwrites the other.

You can reproduce this by placing a barrier **after containsKey but before put**, so both are guaranteed to observe the key as absent. Then check whether createValue() ran twice, whether side effects were duplicated, and what the final value is. The fix can use putIfAbsent or computeIfAbsent depending on the contract; remember that createValue() may have side effects, so computing the value before putIfAbsent can still run multiple times. With ConcurrentHashMap's computeIfAbsent, the mapping function must avoid unsafe side effects and must not recursively update the same map in a way that violates the API contract.

Invariant races also appear in many other places: checking balance then deducting money, checking queue empty then removing, checking state then emitting an event, checking remaining tickets then booking. These problems require designing a **linearization point** for the business logic, not just adding more threads in a test.

## 8. Conditions for a reliable concurrency test

### Controlling the right number of workers and timing

When CyclicBarrier has parties = 2, there must be **at least two threads actually able to run** to await. If you use Executors.newSingleThreadExecutor with two tasks, the first task waits at the barrier while the second task has not yet been scheduled: the test will hang or time out. If main also calls await, parties must include main.

Do not call Future.get() on the first worker **before calling start.countDown()** if the worker is waiting on start. Submit both → wait for ready → open start → wait for results.

Ideally, use exactly two workers as in the example and minimize unrelated steps between gates to keep the trace easy to read.

### Setting timeouts on every wait point

Use await(timeout, unit), barrier.await(timeout, unit), and Future.get(timeout, unit) so a failing test does not hang indefinitely when a worker:

- Dies before calling ready.countDown or before reaching the barrier.
- Throws an exception during the read phase.
- Is interrupted and cannot reach the required parties.
- Is not given a thread by the executor or the runtime environment is overloaded.

CountDownLatch.await(timeout, unit) returns **false** if it times out. CyclicBarrier.await(timeout, unit) can throw TimeoutException; the other parties can receive BrokenBarrierException. Future.get(timeout, unit) can throw TimeoutException, while errors inside Callable are wrapped in ExecutionException. Do not equate these cases with “race reproduced”.

The 5-second timeouts in the program are a **test safeguard**. They do not define a production latency SLA. On a very slow CI machine, an appropriately configurable timeout may be needed; if a timeout occurs, the proper outcome is that the test failed due to unmet execution conditions, not an inference of a lost update bug.

### Always releasing workers and resources

Wrap the launch and wait logic in try/finally; when a test fails, open any still-closed start gates, cancel futures, and shut down the executor deliberately. cancel(true) requests interruption but does not guarantee every task stops immediately, especially uncooperative I/O operations. A harness that shares an executor should cancel only **the test's tasks** and let the owner manage shutdown.

Do not use Thread.sleep(...) as a mechanism to prove execution order: sleep only requests a minimum relative wait and does not guarantee two threads meet at the desired point. Thread.yield is also merely a hint to the scheduler and creates neither a barrier nor the required happens-before relationship.

### Ensuring worker errors are reported back to main

A test can easily go wrong if it only uses execute(Runnable) and main reads results too early. Submit Callable/Runnable as a Future and call get() to:

- Wait for the tasks to complete.
- Surface exceptions thrown by a worker.
- Establish a synchronization point so main reads results after workers finish.

If you use a done CountDownLatch instead of Future, place countDown in each worker's finally block so failures do not hang main; **but you still need to capture and report worker errors** to avoid false-green tests. Waiting on done without checking errors is not enough.

## 9. Happens-before: observing accurately without masking bugs

The Java Memory Model defines several key synchronization relationships:

- Actions before CountDownLatch.countDown() happen-before actions after a corresponding await returns normally because the count reached 0.
- With CyclicBarrier, actions before await() happen-before actions after other workers pass await() in the same barrier trip.
- Actions of a task before completion happen-before actions after a successful Future.get() for that task.
- An unlock of a monitor happens-before a subsequent lock on the same monitor; atomic operations have corresponding synchronization rules.

That is why main in the example reads the counters **after both Future.get() calls**, rather than reading while workers are still running. The barrier ensures both read steps complete before the write steps, but **it does not turn the two int writes after the barrier into an atomic read-modify-write transaction**. In this staged program, both workers write the value 1, so the final result is 1 regardless of write order.

Pay close attention: if you wrap the entire read → barrier → write sequence in synchronized(counter), the first thread holds the monitor and waits for the second thread, while the second thread cannot enter the monitor to reach the barrier. The scenario will deadlock/time out due to the test structure itself. When testing **the fix**, adjust gate placement so workers meet **before executing the protected atomic operation**.

Do not place synchronous logging or callbacks with side effects between two steps meant to race without considering their impact. Logging calls, blocking mock responses, debugger breakpoints, and profilers can add synchronization, change timing, and make the bug disappear.

## 10. Writing reproduction tests and regression tests as two contracts

You should distinguish:

1. **Reproduction test**: Deliberately runs the buggy algorithm along a specific interleaving. The expected result is lost update = 1 to confirm the harness genuinely forces the bug. The directly runnable example in section 4 belongs to this category.
2. **Regression test of the fixed algorithm**: Forces workers to the update boundary, then calls the atomic/locked update. Expected result = 2. This is the test used to protect the fix.
3. **Stress test**: Repeats many tasks and many execution schedules to uncover unknown bugs. Useful as a complement, but does not replace a deterministic reproduction schedule.

Do not leave the fixed code's test **asserting lost update = 1**; that is the buggy outcome to eliminate. Clearly separate the buggy version and the fixed version, or use meaningfully named scenario parameters. For a timing bug observed in production, record precisely: initial shared state, the two conflicting steps, the gates to insert, and the violated invariant.

In an automated test suite, verify both **the business output** and **that the coordination conditions were actually met**: enough workers entered the gate, no timeouts or exceptions occurred, futures completed, and the expected number of operations ran. If any of those conditions fail, the test must fail clearly rather than being treated as “the race did not occur”.

## 11. Extended techniques and limitations

### Latch, barrier, and phaser

| Tool | Best used when | Notes |
| --- | --- | --- |
| CountDownLatch | Waiting for N workers to become ready or opening a start gate | One-shot; does not reset |
| CyclicBarrier | N workers must cross a phase boundary together | Fixed parties; can become broken; reusable |
| Phaser | Multiple phases, participants can register/deregister | Requires careful registration/termination management |
| Semaphore | Limiting the number of tasks entering a resource region | Does not itself create an “all arrive together” rendezvous |
| Future | Waiting for task completion and propagating exceptions | Does not enforce read/write scheduling mid-task |

Phaser can be useful for multi-round scenarios with changing worker counts, but for a simple two-worker lost update, CyclicBarrier is clearer. Do not add complexity just to use more primitives in a single test.

### Races cannot be fully disproven by a single schedule

Staging one interleaving only shows that the program fails **on that interleaving**. It does not enumerate all possible execution paths; passing one concurrency test is not a formal proof that no data races remain. For lock-free algorithms or complex memory-ordering issues, combine code review against the Java Memory Model with specialized tools such as JCStress and controlled stress tests.

For tests involving real I/O, networking, or OS interactions, it may not be possible to insert a barrier right between internal operations. Design appropriate observation/injection points at a layer you control, and avoid faking “deterministic” guarantees for parts the test cannot control.

### Diagnostics when a test times out

When a test hangs, distinguish among:

- **Deadlock**: threads wait on locks/conditions in a cycle and cannot make progress.
- **Missing barrier party**: a worker was submitted but has not run because the pool is too small, failed before await, or branched around await.
- **Livelock/starvation**: threads remain active or are starved of CPU scheduling, yet work makes no progress.
- **Race**: an execution schedule leads to an invalid state even though threads can complete.

Use thread dumps (e.g., jcmd or jstack when supported by the JDK and process), thread names, stack traces, waiting party counts, and logs at gate points to determine the cause. Diagnosing a timeout is different from proving a lost update; a test stuck at a barrier does not by itself prove a race in the business algorithm.

## 12. Practical workflow for hunting real race conditions

**Step 1 — State the invariant.** For example, “after exactly two successful increments, the count must increase by 2”; or “a key may be created only once”. Do not start with sleep calls or infinite loops.

**Step 2 — Break down the interruptible operation.** Sketch read → check/compute → write; find where two threads can simultaneously observe stale state.

**Step 3 — Place gates at critical boundaries.** Use a ready latch to ensure both workers are running; a start latch to signal start; a barrier to force both past the read phase before the write phase. Avoid placing a gate while holding a lock that prevents the other party from arriving.

**Step 4 — Bound and observe.** Every await/get has a timeout; every worker is submitted to an executor with enough threads; check exceptions and wait for both to complete before asserting.

**Step 5 — Reproduce the wrong result.** For the lost update example, assert result 1 in the intentionally buggy harness and record that there were two increment requests. If 1 is not produced, inspect the coordination logic rather than concluding the code is safe.

**Step 6 — Fix the synchronization mechanism.** Choose AtomicInteger, synchronized, a lock, or an atomic map update at the right invariant level; eliminate separate read-modify-write sequences.

**Step 7 — Run the regression test.** Force both workers to the update boundary, verify result 2 and no exceptions/timeouts. Then add stress tests and other schedules according to the algorithm's risk level.

## 13. Common mistakes to avoid

| Mistake in the test | Impact | How to handle |
| --- | --- | --- |
| Using Thread.sleep to “time” a race | Depends on scheduler, machine, CI load | Latch/barrier at the right phase |
| Start latch only | Two workers may run sequentially | Add a rendezvous after read if forcing stale snapshots |
| Barrier parties = 2 but pool has only 1 thread | First worker waits for an unscheduled worker | Pool with enough workers and timeouts |
| Calling get before countDown | Main waits for work that is waiting on main | Release the gate before waiting on futures |
| No timeout on await/get | Test can hang indefinitely | Use finite timeouts, report error source clearly |
| Waiting on done latch while swallowing worker exceptions | Test reports green even though a worker failed | Future.get or equivalent error channel |
| Placing barrier inside a lock the other thread needs | Self-inflicted deadlock | Meet at barrier outside the locked region |
| Reading shared state before Futures finish | Assertion sees intermediate state | Wait for completion then inspect |
| Treating volatile as an atomic increment | Lost update still happens | AtomicInteger or synchronize the whole increment |
| Treating ConcurrentHashMap get+put as atomic | Two threads overwrite results | merge/compute/putIfAbsent per contract |
| Bug test still asserts 1 after fixing | Correct fix is treated as a failure | Change the regression test oracle to 2 |
| Concluding no races remain after one green schedule | Misses many other schedules | Review design, test multiple scenarios, stress/JCStress as needed |

## 14. Technical conclusion

CountDownLatch helps establish **a controlled start condition**; CyclicBarrier locks two workers at **a phase boundary**; Future.get allows **waiting, receiving errors, and observing results after completion**. Combining them lets us force two threads to read the same stale value and overwrite each other, reproducing a lost update repeatably.

A test's success lies in **pinpointing an interleaving that violates an invariant**, rather than relying on scheduler probability. After fixing, verify the invariant with a correct oracle and move the update to an atomic operation or an appropriate synchronized region. A deterministic experiment is evidence of a bug on the staged schedule; evaluating overall correctness still requires reasoning about happens-before, atomicity, and other execution schedules.

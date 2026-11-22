# CyclicBarrier Coordinates Working Rounds in Java

> **Key Takeaway:** `CyclicBarrier` is a **reusable synchronization rendezvous** for **a fixed number of threads**. Each thread performs its portion of the current round's work and then calls `await()`; when **enough parties** arrive, the barrier can run a single `barrierAction`, open the gate for the threads to continue, and **automatically become ready for the next round**. These synchronization points prevent multi-round algorithms (*iterative/phase-based computation*) from reading next-round data before all threads have completed the previous round's work. However, an absent, interrupted, or timed-out thread can stall the entire group or cause the barrier to become *broken*.

This article belongs to the **Synchronizers** group, covering **general Java concurrency**. Examples use Java SE 17+, with no dependency on Spring or any other framework.

## 1. Why Do We Need a Rendezvous Between Multiple Threads?

Suppose an array is divided into 4 regions. 4 independent workers compute the result of **round k** on their assigned region. Round `k+1` needs to see **all** results of round `k`; if a fast worker were allowed to advance to the new round immediately, it could mix old data with new data.

~~~text
              ROUND k                 ROUND k+1
Worker 1    [calc A] ----┐          [calc new A] -----┐
Worker 2    [calc B] --┐ |          [calc new B] ---┐ |
Worker 3    [calc C] ----+--> BARRIER --> [calc C] --+--> BARRIER
Worker 4    [calc D] --┘ |          [calc new D] ---┘ |
                         |                            |
              All completed               All completed
              before next round           before next round
~~~

A barrier is **phase-based synchronization**: workers in the same group must complete a shared milestone before the group proceeds. It does **not** distribute tasks, split arrays, create threads, or fix business logic algorithms. Developers still have to write each thread's work, choose the number of workers, and manage their lifecycle.

Examples of suitable scenarios:

- Multi-step iterative computation: physics simulation, grid processing, relaxation algorithms, iterative numerical processing.
- Round-based data processing: all workers complete the current round before transitioning state.
- Concurrency testing: requiring multiple threads to reach a predetermined point together to coordinate test steps.
- Pipelines with **shared phases** that all group members must complete before opening a new phase.

Do not use a barrier when tasks are completely independent and you only need to collect the final results; in that case, `Future.get()`, `invokeAll`, or `CountDownLatch` may be simpler.

## 2. Core API of CyclicBarrier

`java.util.concurrent.CyclicBarrier` has two main constructors:

~~~java
// API snippet; requires import java.util.concurrent.CyclicBarrier.
CyclicBarrier simple = new CyclicBarrier(3);
CyclicBarrier withAction =
        new CyclicBarrier(3, () -> System.out.println("round done"));
~~~

The `parties` count is the number of **arrivals** required to trip the barrier in each round; in the common model, each worker arrives **once per round**. `parties <= 0` is invalid and the constructor throws `IllegalArgumentException`.

Methods:

| API | Meaning |
| --- | --- |
| `await()` | Worker arrives at the rendezvous, **waits** until all parties arrive or the barrier is broken; returns arrival index |
| `await(timeout, unit)` | Also waits for all parties, but with a timeout; timing out can break the entire barrier |
| `getParties()` | Returns the configured number of parties at creation; this is not the current active-thread count |
| `getNumberWaiting()` | Number of parties currently waiting at the barrier; used mainly for monitoring/debugging |
| `isBroken()` | Indicates whether the barrier is in the *broken* state |
| `reset()` | Moves the barrier to a new generation, while causing existing waiters to receive `BrokenBarrierException` |

CyclicBarrier **does not have** non-blocking `arrive()`, `arriveAndDeregister()`, or `getPhase()` like `Phaser`. It also **does not automatically adjust parties** when a worker dies. If the number of workers can scale dynamically, consider another synchronizer.

### Parties Are Different from Total JVM Threads

`new CyclicBarrier(4)` does not mean the JVM only has 4 threads, nor that an executor will automatically create 4 workers. It only specifies a *rendezvous* that requires **four group arrivals** per round. Non-participating threads continue running normally. Sharing a barrier with threads outside the group can break the protocol; each thread must clearly know which round it is participating in.

## 3. Lifecycle of a Barrier: Reusable and Generation

A successful barrier follows this flow:

1. Worker A arrives and calls `await` → waits.
2. Worker B arrives → continues waiting.
3. Worker C arrives, reaching `parties=3`.
4. If a `barrierAction` is provided, the **last-arriving thread** runs the action.
5. When the action completes normally, all waiters are released from `await`.
6. The barrier **automatically resets for the next round**; the group can repeat the same flow.

~~~text
CyclicBarrier(parties=3)

Generation 0:
 A: await ──────────────┐
 B: await ────────────┐ │
 C: await ── last ────┤ │
                      ▼ ▼
                 [barrierAction]
                        |
                  release A,B,C
                        |
Generation 1:  A/B/C await again
                        |
                  [barrierAction] ...
~~~

**Distinguishing automatic reuse from manual reset:** After **a successful round**, CyclicBarrier automatically uses the next generation; `reset()` is not needed. `reset()` is primarily used when handling a broken state according to a protocol, and if there are active waiters, it **breaks the round those waiters are waiting on**.

### Not an Independent Broadcast Event

The barrier only opens when **all parties** arrive. A thread calling `await()` while members are missing will not receive a "done event" from another thread calling `countDown` elsewhere; it will wait. This is a major difference compared to `CountDownLatch`.

## 4. Example 1 — Three Workers Coordinating Across Three Rounds

This example uses 3 threads and 3 rounds. In each round, worker `i` writes a value into its **own slot `values[i]`**, then waits at the barrier. The `barrierAction` reads the three slots to aggregate them and adds to the grand total. It does not rely on OS scheduling order.

Create the file `ThreeRoundsBarrier.java` (Java 17+):

~~~java
import java.util.concurrent.CyclicBarrier;
import java.util.concurrent.atomic.AtomicInteger;

public class ThreeRoundsBarrier {
    public static void main(String[] args) throws InterruptedException {
        int workers = 3;
        int rounds = 3;
        int[] values = new int[workers];
        AtomicInteger completedRounds = new AtomicInteger();
        AtomicInteger grandTotal = new AtomicInteger();

        CyclicBarrier barrier = new CyclicBarrier(workers, () -> {
            int roundSum = 0;
            for (int value : values) {
                roundSum += value;
            }
            grandTotal.addAndGet(roundSum);
            completedRounds.incrementAndGet();
        });

        Thread[] threads = new Thread[workers];
        for (int i = 0; i < workers; i++) {
            final int slot = i;
            threads[i] = new Thread(() -> {
                try {
                    for (int round = 1; round <= rounds; round++) {
                        values[slot] = round;
                        barrier.await();
                    }
                } catch (Exception failure) {
                    throw new IllegalStateException(failure);
                }
            }, "worker-" + i);
            threads[i].start();
        }

        for (Thread thread : threads) {
            thread.join();
        }

        System.out.println("rounds completed = "
                + completedRounds.get());
        System.out.println("grand total = " + grandTotal.get());
        System.out.println("broken = " + barrier.isBroken());
    }
}
~~~

Compile/run:

~~~bash
javac ThreeRoundsBarrier.java
java ThreeRoundsBarrier
~~~

Stdout on a normal run:

~~~text
rounds completed = 3
grand total = 18
broken = false
~~~

Explanation:

- Round 1: all three workers write `1`, the action sums `1+1+1=3`.
- Round 2: each worker writes `2`, the action sums `2+2+2=6`.
- Round 3: each worker writes `3`, the action sums `3+3+3=9`.
- `grandTotal = 3+6+9 = 18`; the action is invoked **exactly once per successful round**, 3 times in total.
- `barrier.await()` in each worker blocks progression to `round+1` until all workers have finished the current round.
- After joining all three threads, `main` reads the results and prints a deterministic sequence.

Do not place `System.out.println` for each worker right before the barrier and expect the same log line order on every run: **arrival order at the barrier is not fixed by the scheduler**.

**Why use an unlocked `int[]` here?** Each thread writes to **a different slot**; no two threads write to the same slot. The `barrierAction` reads after all threads have called `await`, matching the barrier's *happens-before* guarantee. If another thread outside the group modifies `values` concurrently, or if workers write to the same slot, additional synchronization is still required.

## 5. Return Value of await(): Arrival Index

`await()` returns an `int` representing the **arrival index in the current generation**, from `getParties()-1` for the first to arrive down to **0 for the last to arrive**.

With `parties=4`, four successful calls in a generation receive four distinct values `3,2,1,0`, not necessarily in thread ID order. `0` is the **last arrival**; this is also the thread that executes the barrier action if one exists.

### Example 2 — Verifying Arrival Indices Independently of Scheduling

Create `BarrierArrivalIndices.java` (Java 17+):

~~~java
import java.util.ArrayList;
import java.util.Collections;
import java.util.List;
import java.util.concurrent.CyclicBarrier;
import java.util.concurrent.atomic.AtomicInteger;

public class BarrierArrivalIndices {
    public static void main(String[] args) throws InterruptedException {
        AtomicInteger actions = new AtomicInteger();
        CyclicBarrier barrier = new CyclicBarrier(
                4, actions::incrementAndGet);

        List<Integer> indices =
                Collections.synchronizedList(new ArrayList<>());

        Thread[] workers = new Thread[4];
        for (int i = 0; i < workers.length; i++) {
            workers[i] = new Thread(() -> {
                try {
                    indices.add(barrier.await());
                } catch (Exception failure) {
                    throw new IllegalStateException(failure);
                }
            });
            workers[i].start();
        }

        for (Thread worker : workers) {
            worker.join();
        }
        Collections.sort(indices);

        System.out.println("arrival indices = " + indices);
        System.out.println("action count = " + actions.get());
    }
}
~~~

Run:

~~~bash
javac BarrierArrivalIndices.java
java BarrierArrivalIndices
~~~

Stdout:

~~~text
arrival indices = [0, 1, 2, 3]
action count = 1
~~~

`indices` is a synchronized list because **multiple threads call `add` concurrently** after the barrier opens. `main` only sorts after all workers have finished. Do not use a plain `ArrayList` for multiple workers to `add` concurrently assuming the barrier serializes all mutations after `await`: once released, **workers resume running concurrently**.

### Should You Pick a "Leader" Using Index 0?

You can use `index==0` as a marker for the last-arriving thread to perform an operation **after the barrier has opened**, but if that operation must complete **before other workers proceed to the new round**, using **`barrierAction`** is the right choice. After `await` returns, all threads can run concurrently; other workers do not wait specifically for the index-0 thread's operation.

Logic example:

~~~java
// Illustrative snippet inside a loop that may throw Exception.
int index = barrier.await();
if (index == 0) {
    logRoundCompleted();
}
// Not guaranteed that logRoundCompleted() finishes before other workers' code.
~~~

If you need to publish an immutable snapshot at the start of the next round, publish it inside the barrier action (or add a second synchronization point after the leader's operation).

## 6. Barrier Action: Runs When All Parties Arrive, Before Opening the Gate

The constructor `new CyclicBarrier(parties, barrierAction)` lets you register a `Runnable` that executes **once per successful generation**, when the last thread arrives and **before the remaining threads are released**.

Typical roles:

- Aggregating intermediate results from workers.
- Swapping `next/current` buffers for the next round.
- Checking end-of-round invariants.
- Computing/recording per-round statistics.
- Resetting data belonging to the just-finished round, provided the reset truly happens after all workers have stopped using it.

**It is not a task running on a separate "barrier thread".** The barrier action is executed by the **last-arriving worker**. If the action blocks for a long time, both that worker and all waiters are held up, increasing total round latency. Do not perform unbounded network I/O, acquire complex locks, or wait on another worker that is at the same barrier inside the action.

### Example 3 — Swapping a Double Buffer at Round Boundaries

Create `DoubleBufferBarrier.java` (Java 17+):

~~~java
import java.util.Arrays;
import java.util.concurrent.CyclicBarrier;

public class DoubleBufferBarrier {
    static final class State {
        int[] current = new int[4];
        int[] next = new int[4];
        int completedRounds;
    }

    public static void main(String[] args) throws InterruptedException {
        State state = new State();

        CyclicBarrier barrier = new CyclicBarrier(4, () -> {
            state.current = state.next;
            state.next = new int[4];
            state.completedRounds++;
        });

        Thread[] workers = new Thread[4];
        for (int i = 0; i < workers.length; i++) {
            final int slot = i;
            workers[i] = new Thread(() -> {
                try {
                    for (int round = 0; round < 3; round++) {
                        state.next[slot] = state.current[slot] + 1;
                        barrier.await();
                    }
                } catch (Exception failure) {
                    throw new IllegalStateException(failure);
                }
            });
            workers[i].start();
        }

        for (Thread worker : workers) {
            worker.join();
        }

        System.out.println("completed rounds = "
                + state.completedRounds);
        System.out.println("values = "
                + Arrays.toString(state.current));
    }
}
~~~

Run:

~~~bash
javac DoubleBufferBarrier.java
java DoubleBufferBarrier
~~~

Deterministic output:

~~~text
completed rounds = 3
values = [3, 3, 3, 3]
~~~

Each worker only modifies its own `state.next[slot]` before `await`. When all four arrive, the action swaps the buffer references and allocates a fresh buffer for the new round. Workers only start the next round after the action finishes, so they read the new buffer. After three rounds, all values equal 3.

This is a single-value-per-slot update, not a complex numerical stencil problem. For algorithms where each new cell depends on **neighbors**, workers must likewise read **only from `current`** and write **only to `next`** during a round, avoiding modifying `current` while other workers are still reading it.

### Not All Mutations Automatically Have Consistency

Having `state.current`/`state.next` as regular fields is valid **within the synchronization scope of the barrier**: actions before `await` are synchronized with the barrier action and actions after a successful `await`. If a thread outside the barrier wants to read a snapshot while workers are still computing, that thread is not guaranteed synchronization by the barrier alone; separate safe publication/lock/volatile/immutable snapshot is required.

## 7. Java Memory Model: Happens-Before Across the Barrier

A point many overlook: `CyclicBarrier` provides *memory consistency* effects in its Javadoc:

> Actions in a thread **prior to calling `await()`** *happen-before* actions that are part of the **barrier action**, which in turn *happen-before* actions **following a successful return from the corresponding `await()`** in other threads.

Diagram:

~~~text
Worker 1: write result[0] -----+
Worker 2: write result[1] -----+--> all await()
Worker 3: write result[2] -----+
                                     |
                                     v
                               barrierAction
                              reads all results
                              updates next state
                                     |
                               happens-before
                                     v
                       workers resume after await
                       read published state
~~~

This is why `ThreeRoundsBarrier` can use individual slots of an `int[]` without making each slot an `AtomicInteger`, **provided slot ownership and phases are managed properly**.

Do not assume:

- The barrier automatically protects a shared counter when multiple workers do `counter++` before `await`. The `++` increments still race and suffer lost updates.
- Writes **after `await`** by two threads are automatically serialized. Once the barrier opens, threads run in parallel again.
- A third thread that never participates in the barrier is protected for all state reads.
- External I/O outside the JVM or database transactions automatically gain commit/visibility just because a Java thread passed a barrier.
- When a barrier is **broken** and `await` throws an exception, code can treat it as a successful phase. A failed generation must be treated as incomplete.

If one worker writes multiple cells and another thread reads those cells **before all parties arrive** via an unsynchronized path, a data race can still occur. A barrier is only correct when each phase strictly respects its ownership boundaries.

## 8. What Does a Broken Barrier Mean?

The *broken* state occurs when a generation cannot complete according to protocol. Common causes:

- A thread waiting at the barrier is `interrupt()`ed.
- A thread calls timed `await` and **times out** before all parties arrive.
- `barrierAction` throws an unchecked exception or error.
- A coordinator calls `reset()` while waiters are present.
- Certain other synchronization failure scenarios per the API contract.

`CyclicBarrier` uses an **all-or-none breakage** model: when one waiter fails due to interrupt/timeout, the remaining waiters in that generation should not proceed as if the whole group succeeded; they typically receive `BrokenBarrierException`.

When a barrier is broken:

- `isBroken() == true`.
- Subsequent calls to `await` **throw `BrokenBarrierException`** instead of waiting for a normal generation (until a reset occurs).
- Waiting threads are woken up with an error outcome.
- The barrier **does not self-heal** just because a new worker arrives.
- You must treat the entire round as failed, roll back partial work, or reset via an explicit coordinator.

### Distinguishing Three Common Exceptions

| Exception | Who receives it, and under what circumstance? |
| --- | --- |
| `InterruptedException` | The worker calling `await` is interrupted (or enters with its interrupt flag set) and the call responds to the interrupt |
| `TimeoutException` | The worker calling `await(timeout,unit)` exceeds the time limit |
| `BrokenBarrierException` | Another worker in the group broke the barrier, or the caller arrives when the barrier is already broken |

CyclicBarrier can also propagate an unchecked exception from `barrierAction` to the thread executing the action. Do not "swallow" a worker's exception by letting that worker continue to a new round while the rest of the group remains broken.

## 9. Example 4 — Timeout Breaks the Barrier, Reset and Reuse

Create `BarrierTimeoutReset.java` (Java 17+):

~~~java
import java.util.concurrent.CyclicBarrier;
import java.util.concurrent.TimeUnit;
import java.util.concurrent.TimeoutException;
import java.util.concurrent.atomic.AtomicInteger;

public class BarrierTimeoutReset {
    public static void main(String[] args) throws Exception {
        AtomicInteger actions = new AtomicInteger();
        CyclicBarrier barrier = new CyclicBarrier(
                2, actions::incrementAndGet);

        boolean timedOut = false;
        try {
            // Only main arrives: no second party.
            barrier.await(50, TimeUnit.MILLISECONDS);
        } catch (TimeoutException expected) {
            timedOut = true;
        }

        System.out.println("timed out = " + timedOut);
        System.out.println("broken before reset = "
                + barrier.isBroken());

        barrier.reset();
        System.out.println("broken after reset = "
                + barrier.isBroken());

        AtomicInteger successes = new AtomicInteger();
        Runnable workerTask = () -> {
            try {
                barrier.await();
                successes.incrementAndGet();
            } catch (Exception failure) {
                throw new IllegalStateException(failure);
            }
        };

        Thread a = new Thread(workerTask);
        Thread b = new Thread(workerTask);
        a.start();
        b.start();
        a.join();
        b.join();

        System.out.println("successful await calls = "
                + successes.get());
        System.out.println("actions = " + actions.get());
    }
}
~~~

Run:

~~~bash
javac BarrierTimeoutReset.java
java BarrierTimeoutReset
~~~

Stdout:

~~~text
timed out = true
broken before reset = true
broken after reset = false
successful await calls = 2
actions = 1
~~~

The first `await(50 ms)` has no second party so it is **guaranteed** to time out; the barrier becomes broken. `reset()` creates a new generation; the two threads in the next round wait and succeed together, and the action runs once.

This is a **coordinated reset** demo; it does not prove you can reset at any arbitrary time in a real system. If workers from the old generation are still running or recovering, calling reset too early can cause those threads to land in a different generation, falling out of sync with the group's work.

### One Waiter's Timeout Affects the Whole Group

If one worker times out and breaks the barrier, other workers already waiting there can receive `BrokenBarrierException`. Therefore, timed `await` is a **group protocol-level timeout**, not merely the caller giving up while everyone else continues to succeed on the old schedule.

This is an important difference from `Future.get(timeout)`: timing out on a `Future` wait **does not cancel the computation itself**; timing out on `CyclicBarrier.await` can **break the entire generation**.

## 10. Example 5 — Interrupting One Waiter Causes Another Waiter to Receive BrokenBarrierException

To illustrate *all-or-none* semantics, use `parties=3` but **create only two waiters**. While both are waiting, `main` interrupts thread A. A receives `InterruptedException`; B wakes up with `BrokenBarrierException`.

Create `BarrierInterruptDemo.java` (Java 17+):

~~~java
import java.util.ArrayList;
import java.util.Collections;
import java.util.List;
import java.util.concurrent.BrokenBarrierException;
import java.util.concurrent.CyclicBarrier;

public class BarrierInterruptDemo {
    public static void main(String[] args) throws InterruptedException {
        CyclicBarrier barrier = new CyclicBarrier(3);
        List<String> outcomes =
                Collections.synchronizedList(new ArrayList<>());

        Thread a = new Thread(() -> {
            try {
                barrier.await();
                outcomes.add("A-success");
            } catch (InterruptedException expected) {
                outcomes.add("A-interrupted");
                Thread.currentThread().interrupt();
            } catch (BrokenBarrierException ex) {
                outcomes.add("A-broken");
            }
        });

        Thread b = new Thread(() -> {
            try {
                barrier.await();
                outcomes.add("B-success");
            } catch (InterruptedException ex) {
                outcomes.add("B-interrupted");
                Thread.currentThread().interrupt();
            } catch (BrokenBarrierException expected) {
                outcomes.add("B-broken");
            }
        });

        a.start();
        b.start();

        // Only two threads exist, so barrier(3) cannot open yet.
        while (barrier.getNumberWaiting() != 2) {
            Thread.yield();
        }
        a.interrupt();

        a.join();
        b.join();
        Collections.sort(outcomes);

        System.out.println("outcomes = " + outcomes);
        System.out.println("broken = " + barrier.isBroken());
        System.out.println("number waiting = "
                + barrier.getNumberWaiting());
    }
}
~~~

Run:

~~~bash
javac BarrierInterruptDemo.java
java BarrierInterruptDemo
~~~

Stdout when there are no external interruptions:

~~~text
outcomes = [A-interrupted, B-broken]
broken = true
number waiting = 0
~~~

The `while(getNumberWaiting()!=2)` loop is only for **demo coordination**, not a good waiting pattern for production: it can spin CPU if a worker is not scheduled. A real test suite should have a **deadline** and cleanup/fail-fast branches rather than waiting indefinitely on a metric. `getNumberWaiting()` is a status snapshot, not a wait/notification mechanism on its own.

A is interrupted while waiting → A itself receives `InterruptedException` and restores its interrupt flag; B receives `BrokenBarrierException`. **Neither** should be considered to have completed a successful round. `main` can decide to abort the round, report an error, or execute an appropriate reset protocol.

## 11. Barrier Action Can Throw an Exception: Generation Breaks

The barrier action is part of the protocol. If the action fails, workers must not be allowed to proceed as if they completed the barrier successfully.

Per the Javadoc:

- The barrier action is executed by the **last-arriving thread**.
- If the action fails with an exception, the barrier becomes **broken**.
- The exception from the action is propagated in the thread that ran the action.
- Other waiters are released with `BrokenBarrierException`.

### Example 6 — Failing Action and Broken State

Create `BarrierActionFailure.java` (Java 17+):

~~~java
import java.util.ArrayList;
import java.util.Collections;
import java.util.List;
import java.util.concurrent.BrokenBarrierException;
import java.util.concurrent.CyclicBarrier;

public class BarrierActionFailure {
    public static void main(String[] args) throws InterruptedException {
        CyclicBarrier barrier = new CyclicBarrier(2, () -> {
            throw new IllegalStateException("action failed");
        });

        List<String> outcomes =
                Collections.synchronizedList(new ArrayList<>());

        Runnable waiter = () -> {
            try {
                barrier.await();
                outcomes.add("success");
            } catch (InterruptedException e) {
                outcomes.add("InterruptedException");
                Thread.currentThread().interrupt();
            } catch (BrokenBarrierException e) {
                outcomes.add("BrokenBarrierException");
            } catch (IllegalStateException e) {
                outcomes.add("IllegalStateException");
            }
        };

        Thread a = new Thread(waiter);
        Thread b = new Thread(waiter);
        a.start();
        b.start();
        a.join();
        b.join();

        Collections.sort(outcomes);
        System.out.println("outcomes = " + outcomes);
        System.out.println("broken = " + barrier.isBroken());
    }
}
~~~

Run:

~~~bash
javac BarrierActionFailure.java
java BarrierActionFailure
~~~

Stdout:

~~~text
outcomes = [BrokenBarrierException, IllegalStateException]
broken = true
~~~

Two threads arrive at the barrier. The last arriver runs the action and receives `IllegalStateException`; the other thread wakes up with `BrokenBarrierException`. The action threw an exception before completing successfully, so **the generation is broken**. The round's computed data must be marked **failed**, not published as a valid snapshot.

### What Should a Barrier Action Do?

It should be a **short, deterministic operation with clear error handling** such as swapping buffers, aggregating an array, or checking an invariant. For time-consuming or I/O-bound work, consider a different design: the action runs on a worker thread while the entire group waits for it to finish. If the action holds a lock or waits on a task handled by a worker currently waiting at the barrier, it can deadlock.

Do not use `try { ... } catch (Exception ignored) { }` to keep the barrier running indefinitely when data is already corrupted. You may catch an error **defined as recoverable** and record the round state, but the failure policy must be explicit.

## 12. reset() Is Not an Automatic "Deadlock Cure" Button

`reset()` advances the barrier to a new generation. However, workers **currently waiting** will receive `BrokenBarrierException`, because the generation they joined has been broken.

Mistake:

~~~java
// Snippet showing dangerous behavior.
if (barrier.getNumberWaiting() > 0) {
    barrier.reset(); // All existing waiters may receive an error.
}
~~~

Never call `reset` periodically just because waiters are present; the very nature of a barrier is **waiting for parties**. If one worker is slow, resetting cancels the entire phase; if callers do not handle the exception, the whole group can fall into an unsynchronized state.

Suggested recovery protocol:

1. The coordinator detects **broken state** or round cancellation.
2. Stop admitting into the new round, instruct all workers to handle the error and **leave the wait**.
3. Wait for/acknowledge workers from the failed generation, and triage incomplete data.
4. Only when the group has converged on a consistent state, consider `reset()` or **creating a new barrier** for a new team.
5. Resume from a consistent state; do not "stitch together" data from two rounds.
6. If the number of participants changes, `Phaser` or restructuring the worker team is usually more appropriate.

Waiting for all workers to leave a failed generation before resetting is an **application-level safe design rule**, not a Java API prerequisite for calling `reset`. The key point: avoid mixing groups/rounds when there is a race between recovery and arrivals.

## 13. A Thread Fails to Reach the Barrier: Deadlock or Infinite Wait

The plain `await()` **has no timeout**. If configured with `parties=4` but only 3 workers actually call `await` in a round, the three workers can wait forever.

Causes:

- A worker fails with an error before calling `await`.
- A worker returns early due to a business condition without notifying the group.
- The configured `parties` count does not match the number of active threads.
- A worker waits on a lock held by another worker that is already waiting at the barrier.
- The executor has **fewer worker threads than parties**, leaving queued tasks unable to run because all running workers are blocked at the barrier.
- A task is cancelled/interrupted, but error-handling code catches it improperly and fails to notify the coordinator.
- A worker calls `await` twice in one round or skips a round, causing phase mismatch.

### Anti-Pattern Example: A Pool with Two Workers When the Barrier Needs Three Parties

~~~java
// WRONG: structural demo, do not run and wait indefinitely on Future.get().
ExecutorService pool = Executors.newFixedThreadPool(2);
CyclicBarrier barrier = new CyclicBarrier(3);

for (int i = 0; i < 3; i++) {
    pool.submit(() -> {
        barrier.await();
        return null;
    });
}
~~~

The first two tasks run and wait at the barrier; the third task sits in the executor's queue because the pool only has 2 workers. With no free worker to run the third task, the barrier never reaches enough parties. This is a **thread-pool starvation deadlock** caused by scheduling design, not a bug in `CyclicBarrier`'s implementation.

**Fix:** ensure there are **at least as many workers able to reach the barrier concurrently** (or redesign task scheduling so the pool is not exhausted), and monitor exceptions/timeouts. If tasks also depend on locks or I/O, simply increasing pool size may not resolve the root cause.

## 14. Example 7 — ExecutorService with Enough Workers to Open the Barrier

Create `BarrierExecutorPool.java` (Java 17+):

~~~java
import java.util.ArrayList;
import java.util.Collections;
import java.util.List;
import java.util.concurrent.CyclicBarrier;
import java.util.concurrent.ExecutorService;
import java.util.concurrent.Executors;
import java.util.concurrent.Future;
import java.util.concurrent.TimeUnit;
import java.util.concurrent.atomic.AtomicInteger;

public class BarrierExecutorPool {
    public static void main(String[] args) throws Exception {
        AtomicInteger actions = new AtomicInteger();
        CyclicBarrier barrier = new CyclicBarrier(
                3, actions::incrementAndGet);

        ExecutorService pool = Executors.newFixedThreadPool(3);
        try {
            List<Future<Integer>> futures = new ArrayList<>();
            for (int i = 0; i < 3; i++) {
                futures.add(pool.submit(() -> barrier.await()));
            }

            List<Integer> indices = new ArrayList<>();
            for (Future<Integer> future : futures) {
                indices.add(future.get());
            }
            Collections.sort(indices);

            System.out.println("indices = " + indices);
            System.out.println("actions = " + actions.get());
        } finally {
            pool.shutdown();
            if (!pool.awaitTermination(10, TimeUnit.SECONDS)) {
                pool.shutdownNow();
            }
        }
    }
}
~~~

Compile/run:

~~~bash
javac BarrierExecutorPool.java
java BarrierExecutorPool
~~~

Stdout:

~~~text
indices = [0, 1, 2]
actions = 1
~~~

There are exactly three worker slots for three tasks, so each task has a chance to reach the barrier. When the third party arrives, the action increments the counter, and the three `await` calls return arrival indices `0,1,2` (after sorting). `Future.get()` waits for all three tasks before printing results.

**Demo scope:** No task intentionally fails; this is not a comprehensive production template with deadlines. In real programs, use `get(timeout)` / timed `await` and define cancellation, error propagation, and shutdown branches. Even if an executor has a pool size of exactly 3, if tasks wait on each other via locks or external resources, the barrier can still stall.

## 15. How CyclicBarrier Differs from CountDownLatch and Phaser

| Criterion | `CyclicBarrier` | `CountDownLatch` | `Phaser` |
| --- | --- | --- | --- |
| Primary goal | Parties **arrive together at a rendezvous** | Wait for a number of events/countdown | Multi-phase synchronization, flexible participants |
| Automatically reusable? | **Yes**, after a successful round | **No**, once count reaches 0 the latch does not reset | **Yes**, phase increments on each advance |
| Number of participants | Fixed at creation | Fixed count (but countdown threads can differ from waiting threads) | Can dynamically register/deregister |
| Must arriving thread wait? | `await()` waits | `countDown()` **does not wait**; observer's `await()` waits | `arrive()` does not wait; `arriveAndAwaitAdvance()` waits |
| Action at boundary | `barrierAction` | No built-in callback | Can override `onAdvance(...)` |
| Failure while waiting | Interrupt/timeout can make the whole barrier **broken** | Interrupting a waiting thread does not "break the latch" | Has its own termination/interruptible wait protocol |
| Supports reducing parties when worker leaves | No | Not applicable under party model | `arriveAndDeregister()` |
| Direct access to phase number? | No | No | `getPhase()` |
| Use when | Stable team, synchronized rounds | One-shot start gate or completion latch | Dynamic team/phases, complex staged work |

### CountDownLatch: One-Shot, Separates Signaling and Waiting Threads

~~~java
// Illustrative snippet, not a standalone program.
CountDownLatch done = new CountDownLatch(3);
worker1: done.countDown();
worker2: done.countDown();
worker3: done.countDown();
coordinator: done.await();
~~~

Calls to `countDown()` **do not block**. A coordinator can wait for three events to complete without requiring workers to wait at the same milestone simultaneously. Once the latch counts down to 0, it stays open; it does not return to 3. For a new round, you must create a new latch.

### Phaser: Dynamic Parties and Phases

With `Phaser`, threads can `register`, `arriveAndAwaitAdvance`, and `arriveAndDeregister`. It is a better fit if a worker needs to leave the team between phases or if the number of participants changes. `Phaser` is not a drop-in replacement: it requires its own registration/deregistration design and failure policy.

Structural example:

~~~java
// API snippet, not a standalone program.
Phaser phaser = new Phaser(2);
phaser.arriveAndAwaitAdvance();
phaser.arriveAndDeregister();
~~~

Do not call `reset` on CyclicBarrier to simulate `arriveAndDeregister`. `reset` changes the generation but **does not change** `getParties()`, and it causes `BrokenBarrierException` for existing waiters.

## 16. When Is a Barrier Unnecessary?

You do not need CyclicBarrier if:

- Tasks are independent and can finish in any order; the caller only needs `invokeAll` or multiple `Future.get` calls.
- One thread waits for N operations to return results once; `CountDownLatch` is usually clearer.
- Producers need to submit work continuously without a shared cadence; use `BlockingQueue` or a completion protocol.
- You need "multiple threads to start at the same time" in a single test; a start latch may also be more suitable.
- The team scales up and down continuously; fixed parties make adding/removing workers hard to manage.
- Only one thread performs all the steps; a barrier provides no parallelism.
- Tasks use async callbacks without a stable group of blocking workers; a barrier can cause starvation if each thread both waits and holds a scarce executor worker.

Just seeing "round-based work" does not mean CyclicBarrier is always optimal. A synchronizer should reflect **actual dependency relationships** between steps.

## 17. What to Guarantee Before and After await

A checklist for each worker:

**Before await:**

- Finish computing for **the data owned** in the current round.
- Do not hold a lock that the barrier action or another worker needs in order to reach the barrier.
- Do not bail out silently; if an error occurs, notify the coordinator so the whole group knows to cancel/reset.
- Do not update state that another worker is still reading in the round without a protocol.
- Check for cancellation/timeout if the round has a deadline.

**At await:**

- Call **exactly once** per designed round.
- Use timed `await` if a deadline is needed; understand that one party's timeout affects the whole generation.
- Handle `InterruptedException`, `TimeoutException`, and `BrokenBarrierException` explicitly.
- Do not swallow exceptions and continue to the next round as if the barrier succeeded.

**After a successful await:**

- Only after the barrier action has completed normally, read the state published for the new round.
- Do not assume all workers will resume simultaneously or in a fixed order.
- Do not use the `await` return index to infer a permanent worker ID.
- Prepare next-round data and join the next generation following the same protocol.

A pattern with error handling:

~~~java
// Illustrative snippet inside a worker loop.
try {
    computeRound();
    barrier.await(2, TimeUnit.SECONDS);
    usePublishedStateForNextRound();
} catch (InterruptedException e) {
    Thread.currentThread().interrupt();
    notifyCoordinatorOfFailure(e);
    return;
} catch (TimeoutException | BrokenBarrierException e) {
    notifyCoordinatorOfFailure(e);
    return;
}
~~~

The methods `computeRound`, `usePublishedStateForNextRound`, and `notifyCoordinatorOfFailure` are hypothetical domain methods; this snippet does not compile standalone. In production, the coordinator must know that all workers will exit and handle the failed round, rather than just logging and continuing with half-baked shared state.

## 18. Common Mistakes When Using CyclicBarrier

| Mistake | Consequence | Better Approach |
| --- | --- | --- |
| Setting `parties=4` but running only 3 workers | `await` may wait indefinitely | Match `parties` and active workers |
| Using a fixed thread pool of 2 for a barrier of 3 | Worker pool suffers starvation deadlock | Ensure sufficient capacity or redesign |
| A worker returns early before `await` | Remaining group gets stuck | Report error and cancel/break protocol |
| Calling `await` a different number of times across workers | Generation mismatch, mixing up rounds | Enforce consistent loop and membership |
| Calling `reset` after **every successful round** | Unnecessary and can break the next generation | Let the barrier reuse itself automatically |
| Calling `reset` while waiters exist and treating it as success | Waiters receive `BrokenBarrierException` | Coordinator recovery + consistent state |
| Catching `BrokenBarrierException` and continuing computation | May use partial data from a failed round | Exit/report error/restart per protocol |
| Putting long I/O or blocking work in the barrier action | Whole group waits on action, increasing latency | Keep action short, clear, and bounded |
| Assuming `arrival index 0` is a permanent leader | Last arriver changes each round | Do not tie to worker identity |
| Leader does work **after `await`** assuming the group waited | Other workers may run before leader finishes | Use barrier action or a second barrier |
| Multiple workers doing `counter++` before `await` | Data race / lost update | Per-worker slot / atomic / lock, then reduce |
| Reading shared mutable state outside the barrier | No automatic JMM visibility for external threads | Separate safe publication |
| Assuming timeout only affects the caller | Barrier generation can become broken for all waiters | Define a group failure policy |
| Ignoring task errors from `Future` | Silent failure leaves a missing party | Catch `ExecutionException`, cancel group |
| Unhandled exception in barrier action | Generation becomes broken | Monitor/cancel/recover |
| Using `getNumberWaiting()` as an exact gate | Snapshot changes with timing | Use protocol/latch/timeout in tests |
| Not joining workers at program shutdown | Main may close resources too early | Coordinated `join`/`Future.get` and shutdown |
| Using `reset` to reduce parties | Parties are fixed; `reset` does not deregister | Use `Phaser` when membership is dynamic |

## 19. Testing and Observing Barriers in Practice

### A. Running Controlled Tests

The examples above intentionally avoid tests based on `Thread.sleep(100)` to conclude "waited long enough." With real-world timing, scheduling has no hard real-time deadlines.

For production automated tests:

1. Use `CountDownLatch` to confirm tasks have entered the target section.
2. Use `await(timeout, unit)` so tests do not hang indefinitely.
3. If testing a missing-party case, prepare explicit timeouts and cleanup.
4. Ensure `join`/`Future.get` is called with an appropriate timeout.
5. In `finally`, cancel live tasks and shut down test-owned executors.
6. Do not assume thread ordering; assert **counts, sets, and final state**.
7. For exceptions, assert the **exact failure path** of waiters and `isBroken` status.
8. Do not share a global/static `CyclicBarrier` across independent test cases.

### B. Metrics Worth Tracking

- Number of rounds **completed successfully**, not just rounds started.
- Time workers spend waiting at the barrier per round.
- Slowest worker in the group, and round completion time skew.
- Counts of timeouts, interruptions, and broken barriers.
- Barrier action latency and failures.
- Number of active members vs. configured parties.
- Number of tasks cancelled or still waiting after an error.
- Thread pool active/queued counts to detect starvation.
- Total end-to-end workflow duration and per-round data validity.
- Last successful completion time, not just "worker thread is alive."

### C. `getNumberWaiting` and `isBroken` Are Not a Transaction

`getNumberWaiting()` reports the number of parties waiting at the moment of the call, but threads can arrive or leave immediately afterward. `isBroken()` can also change during reset/recovery. Do not build algorithms based on:

~~~java
// Wrong if used as the sole synchronization protocol.
if (barrier.getNumberWaiting() == barrier.getParties() - 1) {
    // Assuming I will definitely be the last to arrive.
    barrier.await();
}
~~~

Between the check and `await`, arrivals, breakage, or resets can occur. If you truly need to run work at the final arrival point, **`barrierAction`** has a far sounder contract than inspecting the waiter count to self-elect a leader.

## 20. Designing Fault-Tolerant Rounds: Decide Policies Up Front

In a real application, a round can fail due to data validation, timeout, or interruption. Before using a barrier, define:

- **Abort the entire round or retry?** If only some workers have written side effects, is a retry idempotent?
- **Where does round-local temporary state live?** Can you discard the `next` buffer and keep the previous valid `current`?
- **Who acts as coordinator?** Who decides to reset/recreate the barrier and restart the worker team?
- **Can workers leave the group?** If yes, fixed parties become problematic; consider `Phaser`.
- **Is there a time limit?** Timed `await` helps detect an incomplete group, but only helps if code handles group failure.
- **Where do worker exceptions go?** If tasks are submitted via `ExecutorService.submit`, the caller needs `Future.get` to retrieve `ExecutionException`; default logging may not adequately surface business failures.
- **Resources and cleanup?** Stop/cancel workers before tearing down shared buffers or closing active connections.
- **What does the next phase need?** You can publish an immutable snapshot, swap buffers, or report errors clearly enough that downstream does not read partial data.

A solid pattern for iterative numerical state is double buffering: all workers read `current` and write their own slots in `next`; the barrier action swaps buffers **only when the round completes**. On failure, the coordinator keeps the confirmed round's `current` and discards the incomplete `next` instead of publishing a half-finished snapshot.

## 21. Self-Check Questions

**Question 1.** `CyclicBarrier(3)` has three threads, each calling `await()` every round. Does the barrier need `reset()` after a successful round?  
**Answer:** No. It automatically becomes ready for the next generation once three parties have arrived and the action (if any) has completed.

**Question 2.** Does `await()` return a value?  
**Answer:** Yes, the arrival index from `parties-1` down to `0`. `0` is the last to arrive.

**Question 3.** A thread gets index 0 in round 1. Is it guaranteed to get index 0 in round 2?  
**Answer:** No. The last arrival varies with scheduling and workload.

**Question 4.** Does the barrier action run on a separate thread created by the JDK?  
**Answer:** No. It runs on the last-arriving thread, before the waiters are released.

**Question 5.** The barrier action updates a shared buffer; are workers after a successful `await` guaranteed to see those changes under the JMM?  
**Answer:** Yes, by the barrier's happens-before guarantee. Workers outside the protocol still require appropriate synchronization.

**Question 6.** Are three workers doing `counter++` before `await` safe because there is a barrier afterward?  
**Answer:** No. The race on `counter++` happens before the barrier; you need atomic/lock or per-worker slots followed by reduction.

**Question 7.** One thread's `await(100, MILLISECONDS)` times out while other threads are waiting. Does only that thread fail?  
**Answer:** No. The barrier can become broken; other waiters receive `BrokenBarrierException`.

**Question 8.** Does `barrier.reset()` change `parties` from 4 to 3?  
**Answer:** No. `parties` is fixed; `reset` creates a new generation and causes current waiters to receive `BrokenBarrierException`.

**Question 9.** `ExecutorService.newFixedThreadPool(2)` runs three tasks, all calling `await` on `barrier(3)`. What is the danger?  
**Answer:** Two tasks run and wait; the third task stays queued with no available worker, causing a thread-pool starvation deadlock.

**Question 10.** One worker throws an exception before `await` and returns; two other workers wait on `barrier(3)`. Will it open on its own?  
**Answer:** No. You need a failure/cancellation protocol or timeout; a missing party can cause an infinite wait.

**Question 11.** `barrierAction` throws `IllegalStateException`. Do other waiters continue as if the round succeeded?  
**Answer:** No. The generation becomes broken; the last-arriving thread receives the exception, and other waiters receive `BrokenBarrierException`.

**Question 12.** What is the most important difference between `CountDownLatch` and `CyclicBarrier`?  
**Answer:** A latch is a one-shot countdown where callers of `countDown` do not wait; `CyclicBarrier` is a rendezvous for a fixed group that is reusable across rounds.

**Question 13.** If you want a worker to be able to `arriveAndDeregister` when it finishes its work, what should you use?  
**Answer:** Consider `Phaser`; `CyclicBarrier` has no deregister API.

**Question 14.** Can one thread after `await` start the next round before another thread finishes its logic after `await`?  
**Answer:** Yes. Once the barrier opens, workers resume concurrently; only logic **before the barrier** and the barrier action are synchronized by that point.

**Question 15.** Should you use `getNumberWaiting()` as an exact condition gate to decide the round's leader?  
**Answer:** No. It is a snapshot subject to concurrency; a barrier action and arrival index are the appropriate contract.

## Java SE 17 References

- [`CyclicBarrier` — Java SE 17](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/concurrent/CyclicBarrier.html): reusable barrier, barrier action, arrival index, all-or-none breakage, memory consistency.
- [`BrokenBarrierException` — Java SE 17](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/concurrent/BrokenBarrierException.html): error when a barrier is broken or reset.
- [`CountDownLatch` — Java SE 17](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/concurrent/CountDownLatch.html): one-shot synchronization, not reusable.
- [`Phaser` — Java SE 17](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/concurrent/Phaser.html): registering/deregistering parties, phases, and advance.
- [`ExecutorService` — Java SE 17](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/concurrent/ExecutorService.html): worker pools, submit, Future, and shutdown.
- [`Future` — Java SE 17](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/concurrent/Future.html): task results, cancellation, and exceptions.
- [`TimeUnit` — Java SE 17](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/concurrent/TimeUnit.html): time units when using timed await.
- [Java Language Specification §17 — Threads and Locks](https://docs.oracle.com/javase/specs/jls/se17/html/jls-17.html): happens-before and visibility.

**Remember:** `CyclicBarrier` helps **a fixed group of workers complete each round together**, repeating without needing a reset after each round. Place a barrier action at the boundary when you need to merge/swap state, verify `parties` and executor capacity, and **handle timeouts, interruptions, and broken barriers as failures of the entire round** rather than silently letting workers continue with incomplete data.

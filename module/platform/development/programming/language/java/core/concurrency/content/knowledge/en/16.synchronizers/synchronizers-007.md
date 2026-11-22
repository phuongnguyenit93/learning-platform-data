# Barrier action, broken state, and reset in Java CyclicBarrier

`java.util.concurrent.CyclicBarrier` is a **synchronizer** that enables a fixed group of threads to meet at the same synchronization point: each party calls `await()` after finishing its part of the work; **only when enough parties arrive** does the barrier trip so that all proceed to the next phase. After tripping successfully, the same barrier **automatically reuses itself** for multiple phases, hence the name *cyclic*.

Three concepts to understand deeply are:

1. **Barrier action**: an optional `Runnable` that runs **exactly once per successful barrier trip**, on the **last-arriving thread**, after all parties have arrived but **before they are released**. It typically aggregates the results of the phase that just finished.
2. **Broken state**: if one party is interrupted, times out while waiting, or the barrier action fails, `CyclicBarrier` applies an **all-or-none breakage** mechanism: the entire waiting group is affected together, rather than the remaining parties continuing to wait as if the phase were still valid.
3. **Reset**: `reset()` establishes a **new barrier generation** after a failure. It is not a command to rescue an in-flight phase; if reset while threads are waiting, those threads receive `BrokenBarrierException`. Recovery must be coordinated at the application level.

This article presents general Java concurrency for JDK 17+, without using Spring mechanisms.

## 1. The basic picture: multiple workers, one rendezvous point

Suppose three workers compute three data partitions, synchronizing at the end of each round:

```text
Phase 0
Worker A: compute A0 ------ await()
Worker B: compute B0 -- await()       [still waiting]
Worker C: compute C0 --------- await()   <-- last to arrive
                                     |
                                     v
                            barrier action
                            combine A0+B0+C0
                                     |
                                     v
                         all allowed to proceed
Phase 1
Worker A: compute A1 ---- await()
Worker B: compute B1 -------- await()
Worker C: compute C1 -- await()
                                     |
                                     v
                            2nd barrier action
                                     |
                                     v
                         all continue/complete
```

`CyclicBarrier(3)` has **3 parties**, not “3 total await calls across its entire lifetime”. Each **generation** requires three `await` calls to participate. Once tripped successfully, the barrier advances to a new generation automatically; you do not call `reset()` every round.

### Terminology

| Term | Meaning |
| --- | --- |
| **Party** | A participating side; usually a worker/thread that calls `await` once per phase |
| **Generation** | A waiting cycle of the barrier, from before enough parties arrive until tripped or broken |
| **Arrival** | A party calling `await()` for the current generation |
| **Trip** | Enough parties arrive and the barrier action (if any) completes successfully; parties are released |
| **Barrier action** | A Runnable that runs once on the last-arriving party before parties are allowed to leave the barrier |
| **Broken barrier** | A corrupted synchronization generation; the current phase cannot be considered successfully completed |
| **Reset** | Ending/discarding the old generation and creating a new waiting generation |
| **Arrival index** | The value returned by `await()`, from `parties-1` (earliest arrival) down to `0` (last arrival) |

Syntactically, each party does not have to be a fixed `Thread`, but the algorithm usually requires **exactly N arrivals per phase**. If only N−1 threads are capable of calling `await`, the program may wait forever unless timeout/cancellation is used.

## 2. Important APIs

```java
CyclicBarrier barrier = new CyclicBarrier(3);
CyclicBarrier withAction =
        new CyclicBarrier(3, () -> doPhaseSummary());
```

This is a snippet, where `doPhaseSummary()` is an application method; `java.util.concurrent.CyclicBarrier` must be imported. The number of `parties` must be **at least 1**; otherwise the constructor throws `IllegalArgumentException`.

| API | Purpose | Notes |
| --- | --- | --- |
| `new CyclicBarrier(n)` | Creates a barrier for n parties | No action |
| `new CyclicBarrier(n, action)` | Creates a barrier and an action | The action is a `Runnable`, with no return result |
| `int await()` | Waits for enough parties | May throw `InterruptedException` or `BrokenBarrierException` |
| `int await(timeout, unit)` | Waits with a time limit | May additionally throw `TimeoutException` |
| `int getParties()` | Configured number of parties | Unchanged by reset |
| `int getNumberWaiting()` | Number of parties **currently waiting** in the current generation | Mainly for debugging/assertions, not a business predicate |
| `boolean isBroken()` | Is the current generation broken? | Usually false after reset because it is a new generation |
| `void reset()` | Resets the barrier to its initial state | Releases waiters of the old generation **with an exception** |

There is **no** `arriveAndDeregister()` on CyclicBarrier. If the number of participants needs to grow or shrink dynamically, consider `Phaser`. Do not use `reset()` to change the number of parties because it preserves `getParties()`.

## 3. When and on which thread does the barrier action run?

When a `CyclicBarrier` has an action:

```java
CyclicBarrier barrier = new CyclicBarrier(
        3,
        () -> aggregatePreviousPhase()
);
```

This is a snippet; `aggregatePreviousPhase` is application logic.

The **successful** sequence of a generation:

1. Workers finish their part and call `await()`.
2. Parties arriving before the party count is reached **wait** at the barrier.
3. The **last-arriving** thread runs `barrierAction.run()` directly within its `await` call path.
4. When the action finishes **normally**, the generation is opened and all parties are released.
5. The barrier moves to a new generation, ready for the next round.

**No separate “action thread” is created by default**: the last-arriving thread itself executes the callback. The action does not run in parallel once per party, nor is it automatically scheduled as a separate executor task.

If the number of parties is 3, the action **does not run when only 2 threads arrive**. This differs from an “at least one result available” trigger. Do not design a callback assuming a third thread will always arrive if tasks can fail or time out before `await`.

### Arrival index

`await()` returns an **arrival index** in the range `0..(parties-1)`:

- `parties - 1`: the **first** party to arrive.
- `0`: the **last** party to arrive (which runs the barrier action if present).
- Other indices: intermediate arrival order.

Do not predict which worker ID will receive index 0: that depends on scheduling. If you want **one worker to perform an operation after the barrier**, you can write:

```java
int index = barrier.await();
if (index == 0) {
    doOnceAfterTrip();
}
```

This is a snippet inside a method handling `InterruptedException`/`BrokenBarrierException`; `doOnceAfterTrip` is application-defined. Unlike a barrier action, `doOnceAfterTrip()` is placed **after `await`**, when other parties **may already have started** the next phase. Do not use the `index==0` pattern as a substitute for an action if the operation **must complete before all threads are released**.

### Behavior when the barrier action fails

If the action throws an unchecked exception, the **last-arriving thread** observes that exact exception on its `await()` path; the barrier is marked broken, and waiting parties receive `BrokenBarrierException`. Thus an exception in the callback does not merely fail one worker; it **invalidates the entire phase**.

**Do not assume the action always runs:** if the barrier times out, is interrupted, or is reset before enough parties arrive, that generation's action is not executed on the successful trip path. Cleanup logic on failure should not be placed solely inside the barrier action.

## 4. Memory consistency: does the barrier action see the parties' data?

Yes, guaranteed by the **happens-before** rules of `CyclicBarrier`:

> Actions of each worker **prior to `await()`** happen-before actions **in the barrier action**, and actions **in the barrier action** happen-before actions **following a successful `await()`** in the other workers.

Because of this, the pattern where **each worker writes to a non-overlapping region and the action reads those regions** can be correct without wrapping every assignment in `synchronized`, provided the data structures and ownership are designed appropriately:

```java
// Workers (each worker has its own index):
partialResults[workerIndex] = localCalculation();
barrier.await();

// Barrier action:
int sum = 0;
for (int value : partialResults) {
    sum += value;
}
phaseTotal = sum;
```

This is a **snippet**; `partialResults`, `phaseTotal`, and the corresponding variables/methods must be defined elsewhere. Workers **do not write to the same array element as other workers**, and the action reads after every party reaches the barrier; the result `phaseTotal` is published before the parties return successfully from `await`.

This guarantee **does not make the entire array thread-safe** if another worker still modifies the same index concurrently outside the protocol. If the action retains a reference to a mutable object and returns it, other workers may begin modifying that object for the next phase; external code must know when the data is still stable.

### Why is the action commonly used for aggregation?

If each worker checks “am I the last to arrive” and aggregates **after `await`**, the other workers have already been released and may be running the next phase. The aggregation could then read data overwritten by the new phase.

Placing aggregation **in the barrier action** guarantees that all workers remain held until aggregation finishes. This is an important reason to choose a barrier action instead of `if (await() == 0)`.

## 5. Java 17 runnable: action runs once per phase

In this example, three workers run **two phases**. Each worker writes to its own element of `partials` per phase and then calls the barrier. The action sums the three elements, records the phase total, and increments the action counter. Which thread arrives last in each phase does not matter; the program only prints statistics after all futures complete.

Create **`BarrierActionPhasesDemo.java`**:

```java
import java.util.ArrayList;
import java.util.List;
import java.util.concurrent.CyclicBarrier;
import java.util.concurrent.ExecutorService;
import java.util.concurrent.Executors;
import java.util.concurrent.Future;
import java.util.concurrent.TimeUnit;
import java.util.concurrent.atomic.AtomicInteger;

public class BarrierActionPhasesDemo {
    public static void main(String[] args) throws Exception {
        int parties = 3;
        int phases = 2;
        int[] partials = new int[parties];

        AtomicInteger actions = new AtomicInteger();
        AtomicInteger lastSum = new AtomicInteger();
        AtomicInteger successfulAwaits = new AtomicInteger();
        AtomicInteger lastArrivalReturns = new AtomicInteger();

        CyclicBarrier barrier = new CyclicBarrier(parties, () -> {
            int sum = 0;
            for (int p : partials) {
                sum += p;
            }
            lastSum.set(sum);
            actions.incrementAndGet();
        });

        ExecutorService pool = Executors.newFixedThreadPool(parties);
        try {
            List<Future<?>> futures = new ArrayList<>();
            for (int id = 0; id < parties; id++) {
                final int workerId = id;
                futures.add(pool.submit(() -> {
                    for (int phase = 0; phase < phases; phase++) {
                        partials[workerId] = workerId + 1 + phase;
                        try {
                            int arrivalIndex =
                                    barrier.await(5, TimeUnit.SECONDS);
                            successfulAwaits.incrementAndGet();
                            if (arrivalIndex == 0) {
                                lastArrivalReturns.incrementAndGet();
                            }
                        } catch (Exception e) {
                            throw new IllegalStateException(
                                    "Barrier failed", e);
                        }
                    }
                }));
            }

            for (Future<?> f : futures) {
                f.get(10, TimeUnit.SECONDS);
            }

            System.out.println("phases=" + phases);
            System.out.println("barrierActions=" + actions.get());
            System.out.println("lastSum=" + lastSum.get());
            System.out.println(
                    "successfulAwaits=" + successfulAwaits.get());
            System.out.println(
                    "indexZeroReturns=" + lastArrivalReturns.get());
            System.out.println("broken=" + barrier.isBroken());
        } finally {
            pool.shutdownNow();
        }
    }
}
```

Compile and run with JDK 17+:

```bash
javac BarrierActionPhasesDemo.java
java BarrierActionPhasesDemo
```

Stdout when all workers finish within the deadlines:

```text
phases=2
barrierActions=2
lastSum=9
successfulAwaits=6
indexZeroReturns=2
broken=false
```

**Result analysis:**

- Phase 0: `partials` has `1, 2, 3` → action records `6`.
- Phase 1: `partials` has `2, 3, 4` → action records `9`; this is the final `lastSum`.
- Each phase has three successful `await` calls → 6 in total.
- Each phase has exactly one thread receiving arrival index 0 → 2 times.
- The action runs exactly once per successful phase → 2 times; no reset is needed.
- Worker IDs are not printed because you cannot predict which thread arrives last.
- `Future.get` waits for all workers to finish before `main` prints, so the output does not depend on thread print order.

**Limitations:** each worker writes to its own `partials[workerId]` element and no other writer modifies the same index during that phase. The action runs before release, so aggregation is not mixed with the next phase's data. The example does not show behavior when a task fails; later sections cover the error paths.

## 6. What is a broken barrier?

`CyclicBarrier` uses an **all-or-none breakage** model. When one party cannot wait until enough parties arrive due to a cause that breaks the generation, all waiting parties are forced out of the rendezvous with an exception; the barrier does not let the rest proceed as a false successful trip.

Important causes:

- A waiter is **interrupted** while waiting.
- A waiter hits a **timeout** in `await(timeout, unit)`.
- The **barrier action throws an exception**.
- Someone calls **`reset()`** while waiters are present.
- A new thread calls `await` when the current barrier is **already broken**; it receives `BrokenBarrierException` (per contract, noting interruption precedence).

### State table by cause

| Cause | Thread directly encountering the error | Other waiting threads | `isBroken()` after the failure, before reset |
| --- | --- | --- | --- |
| A waiter times out | `TimeoutException` | Usually `BrokenBarrierException` | `true` |
| A waiter is interrupted | `InterruptedException` (flag is usually cleared when thrown) | Usually `BrokenBarrierException` | `true` |
| Barrier action throws unchecked exception | Thread running the action receives the original exception | `BrokenBarrierException` | `true` |
| Calling `reset()` while waiters are waiting | Thread calling reset returns normally | Waiters receive `BrokenBarrierException` | **`false` immediately after reset** because of the new generation |
| A new caller enters an already-broken barrier | `BrokenBarrierException` | Does not open the broken generation | `true` |

**Distinguish clearly:** `reset()` **breaks the old generation and creates a new generation**. Therefore there is no reason for `isBroken()` to remain true **right after reset**. However, waiters belonging to the old generation still receive `BrokenBarrierException`.

A waiter may concurrently be interrupted at the exact moment another failure occurs and receive `InterruptedException` instead of `BrokenBarrierException`. The JDK permits such interleavings; do not write tests asserting that every waiter always receives one exact exception type when multiple causes occur concurrently.

### Does `BrokenBarrierException` mean “this worker failed”?

Not necessarily. It usually indicates that **another party** or the barrier's own action caused the generation to fail. When you see this exception, look for the **first cause**: which worker timed out, who was interrupted, which action threw an exception, or whether a concurrent reset occurred. Do not handle it by catching and ignoring it so the worker continues the phase as if data had been completely aggregated.

## 7. Java 17 runnable: exception in the barrier action

This example has two parties. The barrier action always throws `IllegalStateException`. The last-arriving thread runs the action and thus receives the original exception; the remaining thread receives `BrokenBarrierException`. The program collects counters so stdout does not depend on which worker arrives last.

Create **`BarrierActionFailureDemo.java`**:

```java
import java.util.ArrayList;
import java.util.List;
import java.util.concurrent.BrokenBarrierException;
import java.util.concurrent.CyclicBarrier;
import java.util.concurrent.ExecutorService;
import java.util.concurrent.Executors;
import java.util.concurrent.Future;
import java.util.concurrent.TimeUnit;
import java.util.concurrent.atomic.AtomicInteger;

public class BarrierActionFailureDemo {
    public static void main(String[] args) throws Exception {
        AtomicInteger actionErrors = new AtomicInteger();
        AtomicInteger brokenWaiters = new AtomicInteger();

        CyclicBarrier barrier = new CyclicBarrier(2, () -> {
            throw new IllegalStateException("action failed");
        });

        ExecutorService pool = Executors.newFixedThreadPool(2);
        try {
            List<Future<?>> futures = new ArrayList<>();
            for (int i = 0; i < 2; i++) {
                futures.add(pool.submit(() -> {
                    try {
                        barrier.await();
                        throw new AssertionError(
                                "Action should not succeed");
                    } catch (IllegalStateException e) {
                        if (!"action failed".equals(e.getMessage())) {
                            throw e;
                        }
                        actionErrors.incrementAndGet();
                    } catch (BrokenBarrierException e) {
                        brokenWaiters.incrementAndGet();
                    } catch (InterruptedException e) {
                        Thread.currentThread().interrupt();
                        throw new IllegalStateException(e);
                    }
                }));
            }

            for (Future<?> f : futures) {
                f.get(5, TimeUnit.SECONDS);
            }
            System.out.println("actionErrors=" + actionErrors.get());
            System.out.println("brokenWaiters=" + brokenWaiters.get());
            System.out.println("broken=" + barrier.isBroken());
        } finally {
            pool.shutdownNow();
        }
    }
}
```

```bash
javac BarrierActionFailureDemo.java
java BarrierActionFailureDemo
```

Stdout on the normal execution path:

```text
actionErrors=1
brokenWaiters=1
broken=true
```

**Reasoning:** The barrier has two parties, so one thread arrives first and waits while one thread arrives last and runs the callback. The callback throws an unchecked exception → the last thread receives `IllegalStateException("action failed")`; the other waiter is released with `BrokenBarrierException`; the barrier is in the broken state.

If another `await()` is called on the **still-broken barrier**, it also will not open a new phase successfully and will throw `BrokenBarrierException`. To reuse after a failure, recovery and `reset`—or creating a new barrier—is required.

**Very important point:** `reset()` **does not fix a bug in the barrier action**. If you reset and two parties arrive again, the callback still throws the same error and the barrier breaks again. You must fix the root cause, replace the action implementation, or replace the barrier as appropriate, rather than just resetting in an infinite loop.

## 8. Timeout: one missing party breaks the whole generation

Use a timeout when a party might fail to arrive due to I/O, queue starvation, cancellation, or resource failure. If `await(300, TimeUnit.MILLISECONDS)` expires before enough parties arrive:

1. The timed-out thread receives `TimeoutException`.
2. The barrier is marked **broken**.
3. Other threads waiting in the same generation are woken up and usually receive `BrokenBarrierException`.
4. Subsequent arrivals also cannot use the broken generation until reset.

**Do not confuse a barrier timeout with a business-processing timeout.** A worker might take 10 seconds to compute *before calling await*; if all other waiters set a 1-second deadline at the barrier, they may time out before the slow worker arrives. Deadlines must reflect phase characteristics, end-to-end deadlines, and downstream constraints.

### Java 17 runnable: timeout, broken, reset, reuse

Create **`BarrierTimeoutRecoveryDemo.java`**:

```java
import java.util.ArrayList;
import java.util.List;
import java.util.concurrent.BrokenBarrierException;
import java.util.concurrent.CyclicBarrier;
import java.util.concurrent.ExecutorService;
import java.util.concurrent.Executors;
import java.util.concurrent.Future;
import java.util.concurrent.TimeUnit;
import java.util.concurrent.TimeoutException;
import java.util.concurrent.atomic.AtomicInteger;

public class BarrierTimeoutRecoveryDemo {
    public static void main(String[] args) throws Exception {
        CyclicBarrier barrier = new CyclicBarrier(2);
        ExecutorService pool = Executors.newFixedThreadPool(2);
        AtomicInteger successfulNextGeneration = new AtomicInteger();

        try {
            Future<Boolean> lone = pool.submit(() -> {
                try {
                    barrier.await(200, TimeUnit.MILLISECONDS);
                    return false;
                } catch (TimeoutException expected) {
                    return true;
                }
            });

            boolean timedOut = lone.get(5, TimeUnit.SECONDS);
            boolean brokenAfterTimeout = barrier.isBroken();

            boolean laterWaiterRejected;
            try {
                barrier.await();
                laterWaiterRejected = false;
            } catch (BrokenBarrierException expected) {
                laterWaiterRejected = true;
            }

            barrier.reset();
            boolean brokenAfterReset = barrier.isBroken();

            List<Future<?>> reused = new ArrayList<>();
            for (int i = 0; i < 2; i++) {
                reused.add(pool.submit(() -> {
                    try {
                        barrier.await(5, TimeUnit.SECONDS);
                        successfulNextGeneration.incrementAndGet();
                    } catch (Exception e) {
                        throw new IllegalStateException(e);
                    }
                }));
            }
            for (Future<?> f : reused) {
                f.get(10, TimeUnit.SECONDS);
            }

            System.out.println("timedOut=" + timedOut);
            System.out.println("brokenAfterTimeout=" + brokenAfterTimeout);
            System.out.println(
                    "laterWaiterRejected=" + laterWaiterRejected);
            System.out.println("brokenAfterReset=" + brokenAfterReset);
            System.out.println("successfulNextGeneration="
                    + successfulNextGeneration.get());
        } finally {
            pool.shutdownNow();
        }
    }
}
```

```bash
javac BarrierTimeoutRecoveryDemo.java
java BarrierTimeoutRecoveryDemo
```

Stdout when the program completes normally:

```text
timedOut=true
brokenAfterTimeout=true
laterWaiterRejected=true
brokenAfterReset=false
successfulNextGeneration=2
```

**Why does the result not depend on sleep/scheduling?**

- The first generation has **2 parties, yet only 1 thread calls `await`**, so it cannot trip successfully. It will time out after the configured duration.
- `main` **waits for the Future** to complete before reading `isBroken`, avoiding a race with the timeout moment.
- An `await()` call on a broken barrier throws `BrokenBarrierException` **immediately**, without waiting for enough parties.
- `reset()` creates a new generation, `isBroken=false`.
- Two new tasks are submitted to the 2-worker executor, calling `await` in the same new generation so they can trip successfully. `main` waits for both futures before printing.
- The 200 ms deadline in the demo serves an **intentional timeout path**, not to prove a worker is always scheduled at the exact 200 ms mark.

Note that `await()` on `main` when the barrier is broken throws according to the contract; if `main` happens to already be interrupted, exception precedence may differ. The program assumes `main` is not interrupted from an external source during a normal run.

## 9. Interruption and the all-or-none policy

When a waiter in `await()` is interrupted, it receives `InterruptedException`, and **the interrupt status is cleared when the exception is thrown** per contract. That barrier generation becomes broken; other waiting parties usually receive `BrokenBarrierException`.

Example **snippet**:

```java
try {
    barrier.await();
    useCompletedPhase();
} catch (InterruptedException e) {
    Thread.currentThread().interrupt();
    stopThisWorker();
} catch (BrokenBarrierException e) {
    abortThisPhase();
}
```

The methods `useCompletedPhase`, `stopThisWorker`, and `abortThisPhase` are application logic. If a method cannot propagate `InterruptedException` outward, after catching it you should usually **restore the interrupt flag** and **exit the processing path**, rather than swallowing the flag and immediately waiting again.

One interrupted party can cause **the entire barrier generation to break**, so other parties must not keep computing and assume a complete result exists. If a workflow needs partial results, a separate contract must be designed for tolerating missing workers.

### Do not swallow `BrokenBarrierException`

```java
try {
    barrier.await();
} catch (BrokenBarrierException ignored) {
    // WRONG if continuing as though the phase completed.
}
continueUsingAllPartitions();
```

This is a snippet that is **wrong in business semantics**; `continueUsingAllPartitions` is an illustrative method. When the barrier is broken, one or more participants did not arrive or the action failed. Results that require “all partitions” have not been confirmed. The coordinator should abort/retry/compensate per generation, rather than ignoring the exception.

### Should each waiter auto-reset in its catch block?

**No.** If all parties simultaneously catch `BrokenBarrierException` and each thread calls `reset()`, reset races occur: thread A joining the new generation may have it broken again by thread B's reset. Recovery requires **one coordinator/leader** following a clear protocol, or creating a new barrier for a newly coordinated group of workers.

## 10. What does `reset()` actually do?

The Javadoc describes `reset()` as resetting the barrier to its initial state. This has two distinct meanings:

**A. If the barrier is currently broken:** reset ends the old generation and opens a new **non-broken** generation so a group of parties can wait again.

**B. If the barrier currently has waiters, without enough parties yet:** reset **abnormally terminates that waiting generation**. Those waiters receive `BrokenBarrierException`; after reset, the barrier is ready for **another waiting round**. This is not like `notifyAll` “letting everyone pass successfully”.

```text
Generation G0, parties=3:
    Thread A -> await (WAITING)
    Thread B -> await (WAITING)
    Thread C -> not yet arrived

Coordinator -> reset()

    A -> BrokenBarrierException (G0 invalid)
    B -> BrokenBarrierException (G0 invalid)
    New G1: isBroken() == false, waiting == 0

After coordinator handles/resynchronizes:
    A/B/C can all await() on generation G1
```

**Do not call reset on every phase**: CyclicBarrier automatically advances the generation after a successful trip. Reset is mainly for **recovery/abandonment** after a failure, and must be coordinated so old parties and new parties do not mix.

### Beware of thinking “reset means immediately recovering every task”

Reset only changes the **barrier's** state; it does not:

- Restart dead workers.
- Roll back side effects made before the barrier broke.
- Complete a barrier action that threw an exception.
- Automatically spawn missing parties.
- Cancel submitted futures/tasks.
- Reset workers' business state and data to a synchronized snapshot.
- Fix an error caused by an executor having fewer workers than the required number of parties.

Therefore, if a serious error occurs, **creating a new barrier** may be easier to reason about than resetting in place, especially when multiple threads have entered different recovery branches.

## 11. Java 17 runnable: reset while two parties are waiting

This example has a barrier requiring three parties, but initially submits only two waiters. `main` waits until **`getNumberWaiting()==2`** (with a deadline) and then calls reset. Both waiters receive `BrokenBarrierException`. After both Futures have completed, we submit three new waiters to demonstrate that the new barrier generation works successfully.

Create **`BarrierResetWaitersDemo.java`**:

```java
import java.util.ArrayList;
import java.util.List;
import java.util.concurrent.BrokenBarrierException;
import java.util.concurrent.CyclicBarrier;
import java.util.concurrent.ExecutorService;
import java.util.concurrent.Executors;
import java.util.concurrent.Future;
import java.util.concurrent.TimeUnit;
import java.util.concurrent.atomic.AtomicInteger;

public class BarrierResetWaitersDemo {
    public static void main(String[] args) throws Exception {
        CyclicBarrier barrier = new CyclicBarrier(3);
        AtomicInteger releasedByReset = new AtomicInteger();
        AtomicInteger nextGenerationSuccess = new AtomicInteger();
        ExecutorService pool = Executors.newFixedThreadPool(3);

        try {
            List<Future<?>> oldWaiters = new ArrayList<>();
            for (int i = 0; i < 2; i++) {
                oldWaiters.add(pool.submit(() -> {
                    try {
                        barrier.await();
                        throw new AssertionError(
                                "Old generation must not trip");
                    } catch (BrokenBarrierException expected) {
                        releasedByReset.incrementAndGet();
                    } catch (InterruptedException e) {
                        Thread.currentThread().interrupt();
                        throw new IllegalStateException(e);
                    }
                }));
            }

            long deadline =
                    System.nanoTime() + TimeUnit.SECONDS.toNanos(5);
            while (barrier.getNumberWaiting() != 2) {
                if (System.nanoTime() >= deadline) {
                    throw new IllegalStateException(
                            "Two waiters not observed");
                }
                Thread.onSpinWait();
            }

            barrier.reset();
            for (Future<?> f : oldWaiters) {
                f.get(5, TimeUnit.SECONDS);
            }

            boolean brokenAfterReset = barrier.isBroken();

            List<Future<?>> nextWaiters = new ArrayList<>();
            for (int i = 0; i < 3; i++) {
                nextWaiters.add(pool.submit(() -> {
                    try {
                        barrier.await(5, TimeUnit.SECONDS);
                        nextGenerationSuccess.incrementAndGet();
                    } catch (Exception e) {
                        throw new IllegalStateException(e);
                    }
                }));
            }

            for (Future<?> f : nextWaiters) {
                f.get(10, TimeUnit.SECONDS);
            }

            System.out.println(
                    "releasedByReset=" + releasedByReset.get());
            System.out.println(
                    "brokenAfterReset=" + brokenAfterReset);
            System.out.println(
                    "nextGenerationSuccess="
                    + nextGenerationSuccess.get());
            System.out.println(
                    "waitingNow=" + barrier.getNumberWaiting());
        } finally {
            pool.shutdownNow();
        }
    }
}
```

```bash
javac BarrierResetWaitersDemo.java
java BarrierResetWaitersDemo
```

Stdout when completing normally within the deadline:

```text
releasedByReset=2
brokenAfterReset=false
nextGenerationSuccess=3
waitingNow=0
```

**Analysis:**

- G0 requires 3 parties, but only 2 threads call `await`, so both wait.
- `main` uses `getNumberWaiting()==2` as a **controlled test checkpoint** and calls `reset` after knowing both are waiting. This getter is mainly for debugging/assertions; **do not use this snapshot as a production coordination protocol** among multiple resetters.
- The two G0 waiters are not treated as successful: each receives `BrokenBarrierException` and returns.
- `main` waits for the two old Futures to complete **before** submitting three new tasks to G1, avoiding mixing generations in the test.
- G1 has all three workers and trips successfully. `getNumberWaiting()==0` after all three futures have completed.
- `reset()` does not change parties from 3 to 2; G1 still requires 3 arrivals.

**Note:** in production, when a coordinator decides to reset due to an error, there must be rules on who is allowed to reset and how workers resynchronize. A `while (getNumberWaiting()<N)` loop used for monitoring cannot replace a safe barrier/protocol when other threads can change generations concurrently.

## 12. When are `getNumberWaiting()` and `isBroken()` useful?

These two getters serve observational purposes:

```java
int configured = barrier.getParties();
int waiting = barrier.getNumberWaiting();
boolean broken = barrier.isBroken();
```

This is a snippet (requires `barrier` to be defined). They can help determine:

- How many parties is the barrier waiting for?
- How many parties are still missing for the current generation?
- Has the current generation broken due to timeout/interrupt/action failure?
- After a reset, is it in a new generation?

**However:** reading the three getters sequentially **is not an atomic consistent snapshot**. Workers may trip or reset between reads. `getNumberWaiting()` is intended by the Javadoc for **debugging and assertions**, not as a business condition to decide resets when multiple actors can run concurrently.

A waiting barrier can be completely normal (a computation phase does not yet have enough parties). Do not declare a deadlock just because you see `WAITING` in a stack trace. Check who has not arrived yet, whether the queue/executor has available workers, whether I/O has timeouts, and whether the flow has exit/cancellation handling.

### Example: pool too small

If you configure `newFixedThreadPool(2)` but submit **3 tasks** each calling `barrier.await()` on a barrier with `parties=3`, the first two workers can occupy all threads and wait for the third party sitting in the queue that **will never get to run**. This is a **thread-starvation deadlock** caused by sizing/dependency graph, not a bug in `reset`.

Solutions include a pool with enough concurrent workers, a different non-blocking/phased model, or structuring execution so parties do not block the remaining parties from running. A timeout is only a fail-fast mechanism and cannot fix an under-provisioned design.

## 13. What is the problem with a heavy or blocking action?

The barrier action runs on the **last-arriving thread**, and all other parties wait for it to finish. If the action:

- Makes long I/O calls.
- Executes heavy DB transactions.
- Waits on `Future.get` for a task that needs one of the workers currently at the barrier.
- Acquires a mutex held by an external thread or in a wait cycle.
- Calls `barrier.await` again under an invalid protocol.
- Throws an unchecked exception due to a bug.

then the entire phase can be delayed or fail. The callback should be **short, deterministic, and have clear resource/timeout bounds**. If aggregation is heavy, consider partitioning results, pre-aggregating before the barrier, or handing off processing to a separate coordinated phase, while preserving visibility and phase ownership.

**A subtle point:** waiters with timeouts cannot necessarily “interrupt” a long-running barrier action immediately if the action is holding the barrier's internal synchronization; the contract does not allow using `await(timeout)` as a force-kill button for arbitrary callbacks. Do not put unbounded I/O in a callback expecting a caller timeout to stop it.

### Action failure and cleanup

A failing barrier action can break the generation, while workers in other partitions may already hold resources or have produced side effects before waiting. Make sure to:

1. Close per-task resources in `finally`/`try-with-resources`.
2. Do not commit incomplete results after catching `BrokenBarrierException`.
3. Log the first cause (timeout/interrupt/action failure).
4. Choose a retry/abort policy at the coordinator level.
5. If retrying, create fresh state or roll back/compensate partial writes according to the business contract.

An action with non-idempotent side effects (sending payments/emails) requires extra care if the application retries a phase: a mid-flight broken generation does not provide exactly-once semantics.

## 14. Recovery is better than unconditional reset

A thoughtful recovery procedure:

**Step 1: Stop accepting work into the old generation.** Transition the phase to a failed/cancelled state at the application level, e.g. via an `AtomicReference<State>` or owner coordinator.

**Step 2: Collect failures.** Identify which party was interrupted, timed out, which action failed, and which tasks are still running. Do not just catch `BrokenBarrierException` in one worker and guess the cause.

**Step 3: Drain/terminate old work.** Cooperatively cancel workers still processing the old generation; wait for proper cleanup to avoid old and new state writing to the same data.

**Step 4: Reset or replace.** If the party group/contract is unchanged and all actors have resynchronized, you may `reset()`. When the old generation is complicated, creating a new `CyclicBarrier` and safely publishing it to new workers is often clearer.

**Step 5: Prepare new state.** Partition data and aggregation variables for the new generation; do not reuse corrupted partial results.

**Step 6: Restart only with a full participant plan.** Ensure enough parties will be able to reach `await`; avoid submitting blocking workers to an under-sized pool.

**Step 7: Verify success.** Count completed phases and business outputs; do not just check `isBroken()==false`, because a brand-new barrier with no arrivals is also false.

### Do not auto-reset every time you see broken

An infinite loop like:

```java
for (;;) {
    try {
        barrier.await();
        break;
    } catch (BrokenBarrierException e) {
        barrier.reset(); // WRONG if every worker resets on its own.
    }
}
```

is a **wrong snippet**; workers can continuously reset each other's new generation, making no progress. If you truly want to retry, have a single exclusive coordinator decide, with a stop/restart protocol and a deadline.

## 15. Barrier action vs. logic after `await()`

The two approaches differ by only a few lines but have different contracts:

### Approach A — barrier action

```java
CyclicBarrier barrier = new CyclicBarrier(
        parties, () -> publishAggregate());
```

This is a snippet; the action **finishes before** workers are allowed to proceed. There is a happens-before relationship from writes before `await` to the action, and from the action to after `await`.

### Approach B — leader after await

```java
int index = barrier.await();
if (index == 0) {
    publishAggregate();
}
```

This is a snippet; **other workers have already been released** when the leader performs aggregation. If workers can overwrite partial state for the new phase, the leader may read stale or corrupted data. You would need a second barrier after aggregation, ownership transfer / immutable snapshots, or to place aggregation inside the barrier action.

**Do not casually reuse the same barrier object to form “an extra second barrier”** if parties do not have a uniform number of `await` calls: the second generation can get mixed with the next phase's generation of another worker. The phase protocol must be explicit for every participant.

## 16. CyclicBarrier vs. CountDownLatch and Phaser

| Property | `CyclicBarrier` | `CountDownLatch` | `Phaser` |
| --- | --- | --- | --- |
| Purpose | N parties meet at a rendezvous point | One or more threads wait for count to reach 0 | Multi-phase synchronization, dynamic party count |
| Reusable after success | **Yes**, opens a new generation automatically | **No**, one-shot latch | **Yes**, advances phase |
| Register/deregister participants | Fixed `parties` | Fixed initial count | `register`/`arriveAndDeregister` |
| Phase-completion action | Constructor `Runnable barrierAction` | No built-in callback | Can override `onAdvance` |
| Failure from waiter timeout/interrupt | Generation broken, other waiters receive error | One interrupted waiter does not “break” the latch | Different semantics; requires custom termination/error design |
| Reset | Yes, **breaks old generation if waiting** | No reset | Not the same reset model; `forceTermination` and phase controls |
| How to wait | `await` by parties | `await` on latch, separate `countDown` | `arriveAndAwaitAdvance`/`awaitAdvance` |
| Best used when | Fixed group computing in rounds | One-time startup/completion | Multiple phases with dynamic participants |

**CyclicBarrier differs from CountDownLatch in that parties cross the barrier together**, whereas a latch can be `countDown()`-ed before any thread calls `await()`, and once the count reaches 0, the latch stays open forever.

**Phaser differs from CyclicBarrier** when some workers may register dynamically or leave the cycle. Do not try to “remove a party” by resetting CyclicBarrier: `getParties` stays unchanged.

If the problem is simply waiting for three Futures to complete **once**, `CompletableFuture.allOf(...)` or `CountDownLatch` is usually simpler than CyclicBarrier.

## 17. Should a barrier be used for I/O-bound workloads?

`CyclicBarrier` is better suited when a group of workers definitely needs **phase-by-phase synchronization**. For I/O-bound workloads:

- One slow API can force every party to wait for the “slowest participant”.
- Many waiting platform threads occupy worker slots even while CPU is idle.
- If one request times out/cancels, the entire generation can break.
- If the executor lacks enough workers to participate together, starvation occurs.
- Partial outputs created before the barrier still need cleanup when the generation fails.

In systems processing streams or independent requests, a barrier can reduce throughput by forcing unrelated work to “wait for the slowest”. Consider asynchronous composition, queues, futures, or a phaser depending on the dependency model. **Do not use a barrier just to create a sense of “having synchronization”**.

### Virtual threads from Java 21

Virtual threads still obey the Java Memory Model and can wait on synchronization primitives, but `CyclicBarrier` still has a **fixed number of parties and an all-or-none contract**. Using virtual threads does not make a missing party magically appear, does not prevent a barrier action from throwing an exception, and does not change `reset()` semantics.

The demos in this article run on Java 17 and do not require virtual-thread APIs.

## 18. Debugging a system stuck at a barrier

When a thread dump shows multiple tasks in `CyclicBarrier.await`:

1. **How many parties are required?** What is `getParties()`?
2. **How many threads are waiting?** `getNumberWaiting()`, read as a debug snapshot.
3. **Where is the missing party?** Computing, waiting on I/O, in the executor queue, failed with an exception, or shut down?
4. **Does the executor have enough capacity?** Are N−1 workers waiting while party N is stuck in the same pool's queue?
5. **Was there a failure before await?** Did a worker throw an exception and die without notifying the coordinator, leaving others waiting forever if there is no timeout?
6. **Is the barrier action currently running?** Is the callback heavy, holding a lock, doing I/O, or throwing an exception?
7. **What is `isBroken()`?** If true, find the root cause and do not keep calling await.
8. **Is there a reset race?** Are multiple threads resetting when catching broken, or is a manager resetting while workers are in mixed phases?
9. **Is there a timeout/cancellation policy?** Without one, a single missing party can hang the whole group.
10. **Does phase data have clear ownership?** Is a worker modifying a new partition before the action finishes reading?
11. **Take multiple snapshots/JFR recordings**: avoid drawing conclusions from a single thread dump.
12. **Correlate epoch/generation** using application-managed state; CyclicBarrier does not expose a generation identifier.

When instrumenting, you can attach an application-generated `phaseId`/runId to logs. Do not use `arrivalIndex` as a generation ID or worker identity; it is only the arrival order within a single generation.

## 19. Common mistakes

| Mistake | Consequence | Fix |
| --- | --- | --- |
| Thinking the barrier action runs on a separate thread | Wrong sizing and latency expectations | Action is run by the **last arrival** |
| Thinking the action runs when only N−1 parties arrive | Callback never runs | Ensure all parties arrive or use a timeout |
| Calling the action after `await` and assuming all parties are still held | Other workers may start the next phase | Put aggregation inside the barrier action |
| Forgetting `await` on one branch | Remaining parties wait forever | Follow the same protocol on all paths, use timeout |
| Pool size smaller than parties when all block | Thread-starvation deadlock | Provide sufficient execution capacity or redesign |
| Catching `BrokenBarrierException` and continuing normally | Using incomplete phase results | Abort/recover explicitly |
| Every waiter calling `reset` | Reset race, can keep breaking | Single coordinator/leader |
| Resetting while waiters are waiting and expecting them to succeed | They receive `BrokenBarrierException` | Distinguish abandonment from a trip |
| Treating `isBroken()==false` as proof the phase completed | A fresh barrier is also false | Measure outputs and completion state |
| Thinking reset fixes a buggy callback | Old action still throws | Fix root cause or replace barrier |
| Action throws an exception but only other waiters log it | Original error is lost | Collect failure at the last arrival |
| Ignoring `InterruptedException` | Task does not stop / enters wrong phase | Propagate or restore flag + exit |
| Thinking a timeout on await can kill a blocking callback | Action can block for a long time | Timeouts on resources/callbacks |
| Using `getNumberWaiting` as transactional state | Getter is only a snapshot | Maintain application-level state/ownership |
| Using `arrivalIndex==0` as a fixed worker | Last-arriving worker varies by schedule | Do not tie logic to worker ID |
| Calling `reset` to reduce `getParties` | Party count does not change | Phaser / new design |
| Putting non-idempotent side effects in the action and retrying blindly | May trigger duplicate side effects | State machine/idempotency |
| Assuming the barrier protects every mutable field | HB only applies per protocol | Define ownership; avoid out-of-phase races |

## 20. Testing essential interleavings

A thorough test suite does not just print one successful phase. It should cover:

1. 1-party barrier: does the action run when the single party calls `await`?
2. 2–3 parties, multiple successful phases, exact action count per phase.
3. One party arrives late but **before the deadline**, not broken.
4. One party **never arrives**, timed await throws `TimeoutException`, `isBroken=true`.
5. One waiter is interrupted, other waiters exit with `BrokenBarrierException` per contract.
6. Action throws an unchecked exception; last arrival receives the original error, remaining waiters receive broken.
7. Reset while waiters are waiting; they get broken even though `isBroken=false` after reset.
8. Reset after error, then **N new parties** reuse the barrier successfully.
9. Multiple phases with different worker IDs receiving arrival index 0; **do not assert thread order**.
10. Phase data aggregated accurately in the action before release.
11. Executor with too few workers: detect deadlock/starvation via a timeout test.
12. Race between cancel/reset/late arrival: no data mixing across generations.
13. Long-blocking callback: coordinator detects it and has out-of-band recovery.
14. Resource cleanup in `finally` when await throws an exception.
15. Multi-generation system: business outputs are not overwritten/mixed across phases.

### Do not use `Thread.sleep` as proof of scheduling

`Thread.sleep(10)` does not guarantee thread A entered `await` before thread B or that the callback finished. For testing:

- Use `CountDownLatch` for checkpoints before submit/await.
- Use `Future.get(timeout)` for deadlines to avoid hangs.
- For reset tests, check `getNumberWaiting` **only when all actors are isolated** and with a deadline.
- Aggregate counters and have `main` print after `Future.get`, independent of log order across workers.
- Do not leave tests creating thread pools without shutting them down.

## 21. Self-check questions

**1. Which thread runs the barrier action?** The **last** thread to arrive at the barrier for that generation, before the other parties are released.

**2. Does the barrier action run if a party times out before N arrive?** Not on the successful trip path; the generation breaks, and waiting parties receive an exception.

**3. What does `await()` returning `0` mean?** It is the last-arriving party in that generation, not the worker with ID 0.

**4. Is calling `reset()` after every successful phase necessary?** No. CyclicBarrier automatically reuses itself after a successful trip.

**5. If you reset while two waiters are waiting, do they proceed normally?** No. They receive `BrokenBarrierException`; reset creates a new generation.

**6. After reset, does `isBroken()==false` mean the old generation succeeded?** No. It only means the new generation is not broken.

**7. If the action throws `IllegalStateException`, which thread receives it?** The last-arriving thread that runs the action; other waiting parties receive `BrokenBarrierException`.

**8. If one waiter is interrupted, is only that thread affected?** No. The generation breaks and other waiters usually receive a broken barrier exception.

**9. Does an `await(timeout,unit)` timeout automatically reset the barrier?** No. The barrier stays broken until recovery/reset or replacement.

**10. Is `getNumberWaiting()` a strong synchronization condition?** No; it is mainly a debugging/assertions snapshot, subject to races when multiple actors change state.

**11. If a pool has 2 threads and the barrier requires 3, what happens if you submit 3 blocking tasks?** The first two tasks can occupy the workers waiting for the third task stuck in the queue; you must design sufficient execution capacity or a different protocol.

**12. When should you use a barrier action instead of `if (await()==0)`?** When state aggregation/distribution **must complete before** any worker moves to the next phase.

**13. Does `reset` change `getParties`?** No. If you need a dynamic number of participants, consider Phaser.

**14. Does a barrier action mean all shared fields are thread-safe?** No. Memory consistency only follows the protocol's happens-before; concurrent writes outside the designated region/phase can still race.

**15. Should every thread call reset in its `BrokenBarrierException` catch block?** No. A single coordinator and explicit resynchronization are needed to avoid reset races.

**16. Is `CyclicBarrier` the same as CountDownLatch?** No. A barrier waits for parties to arrive together and is reusable; a latch has a one-way counter and does not reset.

**17. Does `isBroken()` returning true mean the barrier can never be used again?** No. It can be reset according to a protocol or replaced with a new barrier; however, if the underlying cause persists, it will break again.

**18. Can reset be used as a substitute for failure compensation?** No. It does not roll back side effects or clean up workers' I/O.

## 22. Production design checklist

- Are **parties and generations** clearly defined for the workflow?
- Is every worker guaranteed to call `await` **exactly once per phase**?
- Does the pool/executor have **enough capacity to run all parties concurrently**?
- Is the barrier action **short, data-accurate, and free of unbounded blocking**?
- Does shared data before `await` have clear ownership and get aggregated **before release**?
- Is `arrivalIndex==0` understood as **last arrival**, not a fixed worker?
- Are `InterruptedException`/`TimeoutException`/`BrokenBarrierException` handled separately with proper policies?
- Can a task throw an exception **before await** and leave other parties stuck? Are there timeouts/cancellation?
- If the action fails, does the coordinator capture the **original exception**?
- Is there **a single owner for reset/recovery**, rather than every worker resetting on its own?
- Does recovery wait for old tasks/cleanup to finish before using the new generation?
- Is `reset` used only when truly needed? Is resetting on healthy phases avoided?
- Is `isBroken=false` distinguished from **business phase completed**?
- Are side effects of the action verified to be **idempotent** on retry?
- Are dynamic participants needed? If so, would Phaser be more suitable?
- Are there load/stress tests covering timeouts, interrupts, broken actions, resets, and multiple phases?
- Are worker starvation, queue depth, wait time, and callback duration measured?

**Conclusion:** `CyclicBarrier` provides a repeatable rendezvous point for a fixed group. The **barrier action** runs once on the last-arriving thread and establishes a visibility boundary before parties are released. **Broken** indicates that the entire synchronization generation is no longer valid due to a timeout, interrupt, or action failure; remaining waiters must receive an error rather than continuing with incomplete data. **Reset** discards the old generation, creates a new generation, and causes existing waiters to throw `BrokenBarrierException`; it does not automatically restore business state, workers, or callbacks. Proper design must thoroughly manage participants, actions, timeouts, cancellation, the recovery owner, and per-phase data.

### References

- Oracle Java SE 17 API: [CyclicBarrier](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/concurrent/CyclicBarrier.html)
- Oracle Java SE 17 API: [CountDownLatch](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/concurrent/CountDownLatch.html)
- Oracle Java SE 17 API: [Phaser](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/concurrent/Phaser.html)

# One-Shot Latch vs. Reusable Barrier in Java

## 1. Two Problems That Look Similar but Have Different Contracts

In multithreaded programming, multiple threads may need to wait for each other or wait for a common milestone. Two important tools in `java.util.concurrent` are **`CountDownLatch`** and **`CyclicBarrier`**. Both can make threads wait, but they model two different kinds of coordination:

- **CountDownLatch:** one or more threads **wait for N signals**. The signaling thread calls `countDown()` and **does not have to wait for the other parties**. Once the counter reaches 0, the latch opens permanently; there is no reset operation.
- **CyclicBarrier:** a group with a **fixed number of participating parties** meets at a rendezvous point. Each party calls `await()`; when enough parties arrive, all of them cross the rendezvous point together. After a successful crossing, the barrier **automatically becomes ready for the next round**, without having to be recreated.

Practical examples:

- Initialize three independent modules and then open the service when all three have reported ready: `CountDownLatch(3)`.
- Four workers compute in rounds; every worker must finish the current round before starting the next round: `CyclicBarrier(4)`.
- One coordinator thread waits for multiple workers, while the workers do not need to wait for each other: a latch is the cleaner model.
- A multi-phase pipeline where the number of participating parties changes: you may need `Phaser` instead of a fixed barrier.

**It is not true that “CountDownLatch is a less capable CyclicBarrier”.** The two tools have different semantics regarding who must wait, counting, reusability, and error handling. This lesson is scoped to JDK Java Concurrency and is unrelated to Spring.

## 2. Overview Comparison

| Criterion | `CountDownLatch` | `CyclicBarrier` |
| --- | --- | --- |
| Goal | Wait for a **milestone** of N signals | Synchronize multiple threads at a **rendezvous point**, repeatable |
| Initialization | `new CountDownLatch(count)`, `count >= 0` | `new CyclicBarrier(parties)`, `parties >= 1` |
| Who signals arrival? | `countDown()` | `await()` |
| Must the signaling thread wait? | **No**; `countDown()` returns immediately | **Yes**; `await()` waits for all parties |
| Who waits? | One or more threads calling `await()`; not necessarily the signaling parties | Typically the parties themselves calling `await()` |
| When parties/milestone are reached | Counter reaches 0; all awaiters are released | Barrier is tripped; all parties of that round are released |
| Reusability | **No**; one-shot | **Yes**; automatically advances to the next generation/round after tripping |
| Wait timeout | `await(timeout,unit)` returns `false` | `await(timeout,unit)` throws `TimeoutException` and puts the barrier into the **broken** state |
| One party interrupted while waiting | That awaiter throws `InterruptedException`; latch is **not broken** | A party throws `InterruptedException` and the barrier usually becomes **broken**; other waiting parties throw `BrokenBarrierException` |
| Action when all parties arrive | No automatic callback from the latch | Optional `barrierAction` runs before releasing the parties |
| Error recovery | Control signals/timeouts at the application layer, or create a new latch | Has `reset()`, but requires external coordination; in many situations creating a new barrier is better |
| Observation | `getCount()` | `getParties()`, `getNumberWaiting()`, `isBroken()` |

An important point about the word *reusable*: `CyclicBarrier` reuses itself automatically **after a successful round**. `reset()` is not a required operation after each round; it is a way to return the barrier to its initial state, typically for error recovery, and it carries the risk of breaking threads that are currently waiting.

## 3. How CountDownLatch Works: Opens Only Once

Create a latch with an initial count N:

```java
import java.util.concurrent.CountDownLatch;

CountDownLatch done = new CountDownLatch(3);
```

Whenever a piece of work finishes, a thread executes:

```java
done.countDown();
```

How the counter changes:

```text
Initial: 3
Event A: 2
Event B: 1
Event C: 0 → latch opens
Subsequent countDown calls: stays 0
Any await after this point: returns immediately
```

A thread that needs to wait can use:

```java
done.await(); // Wait until count reaches 0 or interrupted.
```

Calling `countDown()` does not block waiting for other parties; it only decrements the count if it is still positive. `await()` can be called **before or after** the signals arrive. If the count has already reached 0, `await()` can return immediately without requiring any new signals.

### One Signal Does Not Necessarily Correspond to One Thread

`CountDownLatch(3)` does not maintain a registry of three threads. Three workers could each signal once, or one worker could signal three distinct milestones by design. The latch only knows the **count**, not the identity or success status of the signaling party.

If one worker mistakenly calls `countDown()` twice, the latch may open early even though another task has not finished. If a worker fails without calling `countDown()`, the counter may never reach 0. You need to design the ownership of each signal and use `try/finally` if the contract is “has exited the processing block”:

```java
Runnable work = () -> {
    try {
        performWork();
    } finally {
        done.countDown();
    }
};
```

This is a fragment; `performWork()` and `done` are declared by the application. `finally` guarantees signaling when *the body has started and then exited*, not that the task succeeded. If the task is rejected or canceled before starting, `finally` inside the task **does not run**; the coordinator must handle missing signals.

### Creating a Starting Gate with count = 1

`CountDownLatch start = new CountDownLatch(1)` allows multiple threads to wait for a single gate-opening command. The coordinator thread calls `start.countDown()` once; all eligible waiters proceed. Waiters do not call `countDown()` themselves to pass through.

## 4. How CyclicBarrier Works: Parties Wait for Each Other

Create a barrier for three parties:

```java
import java.util.concurrent.CyclicBarrier;

CyclicBarrier barrier = new CyclicBarrier(3);
```

Each party, after finishing its work for the current round, calls `barrier.await()`. The first two parties wait; the third party's arrival trips the barrier and lets all three proceed. In the next round, the three parties call `await()` again on **the exact same barrier object**.

```text
Round 1:
A arrives at await ──┐
B arrives at await ──┤ wait for all three parties
C arrives at await ──┘ → tripped → A, B, C all continue

Round 2 (same CyclicBarrier):
B arrives at await ──┐
C arrives at await ──┤ wait for all three parties
A arrives at await ──┘ → tripped → A, B, C all continue
```

There is no need to call `reset()` between successful Round 1 and Round 2. The order in which parties arrive at the barrier does not have to be the same across rounds.

### Arrival Index and Barrier Action

`await()` returns the **arrival index**: the last party to arrive receives `0`, and the first party receives `parties - 1`. The index is not a thread ID or a fixed order across rounds.

Optional constructor:

```java
CyclicBarrier barrier = new CyclicBarrier(
        3,
        () -> System.out.println("One round has all three parties"));
```

`barrierAction` is executed by **the last party to arrive** after all parties have reached the barrier but **before the parties are released**. It runs once per successful round. You can use the action to aggregate round state or update a phase milestone, provided the action is short and avoids waiting on the very parties being held at the barrier.

If `barrierAction` throws an exception, that exception propagates on the thread executing the action and the barrier enters the **broken** state. Other waiting parties may receive `BrokenBarrierException`. Do not put error-prone logic or long blocking operations inside the action without designing a recovery strategy.

## 5. Standalone Java 17 Example: One-Shot Latch and Barrier Across Three Rounds

The program consists of two tests.

- With the latch: three tasks compute the values 2, 4, 6 and signal completion. The main thread waits for the latch to reach 0, computes the sum, and then calls `await()` one more time; the second wait requires no new signals.
- With the barrier: three workers compute three rounds on separate per-index array slots and wait together at the barrier at the end of each round. `barrierAction` counts the number of tripped rounds; after the workers finish, main sums the integers and prints them in a deterministic order.

Save as **`LatchVsBarrierDemo.java`**:

```java
import java.util.ArrayList;
import java.util.List;
import java.util.concurrent.CountDownLatch;
import java.util.concurrent.CyclicBarrier;
import java.util.concurrent.ExecutorService;
import java.util.concurrent.Executors;
import java.util.concurrent.Future;
import java.util.concurrent.TimeUnit;
import java.util.concurrent.atomic.AtomicInteger;

public class LatchVsBarrierDemo {
    public static void main(String[] args) throws Exception {
        latchOnce();
        barrierAcrossRounds();
    }

    private static void latchOnce() throws Exception {
        CountDownLatch completed = new CountDownLatch(3);
        ExecutorService pool = Executors.newFixedThreadPool(3);
        int[] values = new int[3];

        try {
            List<Future<?>> futures = new ArrayList<>();
            for (int index = 0; index < 3; index++) {
                final int i = index;
                futures.add(pool.submit(() -> {
                    try {
                        values[i] = 2 * (i + 1);
                    } finally {
                        completed.countDown();
                    }
                }));
            }

            completed.await();
            for (Future<?> future : futures) {
                future.get(); // Record task error, if any.
            }

            int total = values[0] + values[1] + values[2];
            System.out.println("Latch: count="
                    + completed.getCount() + ", total=" + total);

            completed.await(); // Count is still 0: does not wait for a new round.
            System.out.println("Latch second await: returned");
        } finally {
            pool.shutdown();
            if (!pool.awaitTermination(5, TimeUnit.SECONDS)) {
                pool.shutdownNow();
            }
        }
    }

    private static void barrierAcrossRounds() throws Exception {
        final int parties = 3;
        final int rounds = 3;
        int[][] results = new int[rounds][parties];
        AtomicInteger completedRounds = new AtomicInteger();
        CyclicBarrier barrier = new CyclicBarrier(
                parties,
                completedRounds::incrementAndGet);
        ExecutorService pool = Executors.newFixedThreadPool(parties);

        try {
            List<Future<?>> futures = new ArrayList<>();
            for (int index = 0; index < parties; index++) {
                final int worker = index;
                futures.add(pool.submit(() -> {
                    for (int phase = 0; phase < rounds; phase++) {
                        results[phase][worker] =
                                10 * (phase + 1) + worker;
                        barrier.await(); // Rendezvous point for each round.
                    }
                    return null;
                }));
            }

            for (Future<?> future : futures) {
                future.get(); // Wait for all workers and detect errors.
            }

            System.out.println("Barrier: phases="
                    + completedRounds.get());
            for (int phase = 0; phase < rounds; phase++) {
                int sum = 0;
                for (int value : results[phase]) {
                    sum += value;
                }
                System.out.println("Round " + (phase + 1)
                        + " total=" + sum);
            }
        } finally {
            pool.shutdownNow();
            if (!pool.awaitTermination(5, TimeUnit.SECONDS)) {
                System.err.println("Workers did not terminate");
            }
        }
    }
}
```

Compile and run with JDK 17+:

```bash
javac LatchVsBarrierDemo.java
java LatchVsBarrierDemo
```

Stdout of a successful run:

```text
Latch: count=0, total=12
Latch second await: returned
Barrier: phases=3
Round 1 total=33
Round 2 total=63
Round 3 total=93
```

In the barrier test, three workers write to three different positions in each row of the array (for example, round 1 has 10, 11, 12). They do not contend to write the same element. `Future.get()` before main reads the array also ensures completion and proper visibility relationships. The order in which workers reach the barrier may vary, but every successful round increments `completedRounds` only once; there is no printing from the workers, so stdout is deterministic.

**Limitations of the demo:** It assumes all tasks are accepted by the executor and can make progress. If the pool lacks workers or a task gets stuck before `await()`, other parties may wait indefinitely. Real applications should use timeouts, interruption/cancellation, and a policy for handling a broken barrier. The demo intentionally separates normal success from failure so basic semantics are easy to see.

## 6. Why Not Replace a Barrier with a Reused CountDownLatch?

Once a latch's counter reaches 0, there is no API to increment the count or reset it to its initial value:

```java
CountDownLatch latch = new CountDownLatch(2);
latch.countDown();
latch.countDown();
latch.await(); // Eligible to proceed.
latch.await(); // Also proceeds immediately; NOT a second round.
```

Therefore, if every worker needs to **wait for each other at the end of each round**, a single latch is not enough. You could create a new `CountDownLatch` for each round and pass it to the right signaling/waiting parties, but that requires a protocol to publish the new latch and transition phases at the right time. When the number of parties is fixed, `CyclicBarrier` is usually simpler.

Conversely, do not force `CyclicBarrier` to do the job of “main waits for three workers to finish” where **only main waits** while the three workers just signal and continue without waiting. With a barrier, every participating party must call `await()` and may be blocked. `CountDownLatch` expresses the intent of a one-way problem more clearly.

## 7. Failure: Timeout and Interruption Have Different Effects

This is the most important difference when handling errors.

### 7.1. CountDownLatch Has No Broken State

`CountDownLatch.await(timeout, unit)` returns:

- `true` if the counter reaches 0 within the wait time.
- `false` if the deadline expires before the counter reaches 0.
- `InterruptedException` if the waiting thread is interrupted.

A timeout or interruption **does not itself change the counter** and does not cancel the workers. Another waiting thread can keep waiting, and subsequent `countDown()` calls can still bring the count to 0. There is no need to call reset because a latch has no reset; nor is there an `isBroken()` method.

```java
CountDownLatch neverOpened = new CountDownLatch(1);
boolean reached = neverOpened.await(0, TimeUnit.NANOSECONDS);
System.out.println(reached); // false
System.out.println(neverOpened.getCount()); // 1
```

This is a fragment when placed with appropriate imports. With a timeout of 0 and a positive count, `await(timeout)` does not wait; the latch remains unopened and can still receive `countDown()` later.

### 7.2. CyclicBarrier Has a Broken State

`CyclicBarrier.await(timeout, unit)` can throw:

- `TimeoutException` when the call itself times out; timing out puts the barrier into the **broken** state.
- `InterruptedException` when the waiting thread is interrupted; the barrier becomes broken, except in race cases with a trip/breakpoint per API semantics.
- `BrokenBarrierException` if another party is interrupted/timed out, the barrier is already broken, `reset()` occurs while waiting, or the barrier action fails.

This model is commonly called **all-or-none breakage**: when one party cannot cross the current round's barrier together with the rest, the other parties do not keep waiting for a successful round that is no longer possible.

`barrier.isBroken()` reports the broken state; `barrier.getNumberWaiting()` returns the number of parties currently blocked in `await()` (for diagnostics, not as an atomic fact for making progress decisions). `barrier.getParties()` returns the originally required number of parties and does not change between rounds.

### 7.3. Deterministic Failure Example

Save `BrokenBarrierDemo.java`:

```java
import java.util.concurrent.CyclicBarrier;
import java.util.concurrent.TimeUnit;
import java.util.concurrent.TimeoutException;

public class BrokenBarrierDemo {
    public static void main(String[] args) throws Exception {
        CyclicBarrier barrier = new CyclicBarrier(2);

        try {
            // Only main calls await; timeout 0 makes it not wait.
            barrier.await(0, TimeUnit.NANOSECONDS);
            throw new AssertionError("Expected timeout");
        } catch (TimeoutException expected) {
            System.out.println("Timed out");
        }

        System.out.println("Broken: " + barrier.isBroken());
        barrier.reset();
        System.out.println("Broken after reset: " + barrier.isBroken());
    }
}
```

Run:

```bash
javac BrokenBarrierDemo.java
java BrokenBarrierDemo
```

Stdout:

```text
Timed out
Broken: true
Broken after reset: false
```

In this example, two parties do not arrive together, so the rendezvous cannot complete. After the timeout, the broken state is `true`. `reset()` returns the barrier to its initial state; **it does not mean the old tasks have automatically recovered**. Application code must ensure that all waiting and running parties have recognized the error, and then agree on whether to continue.

## 8. reset() Is Not an Automatic Recovery Mechanism

`CyclicBarrier.reset()` returns the barrier to its initial state, but if any parties are currently waiting, those parties receive `BrokenBarrierException`. If some threads are handling the error from the old round while other threads start a new round, an uncoordinated reset can cause races or mix generations.

Distinguish between:

- **Round ends successfully:** do not call `reset()`; the barrier reuses itself automatically.
- **Round is broken:** all parties need to know about the error and stop/cancel/rollback related work according to business logic; if recovery is desired, threads must explicitly coordinate creating a new barrier or resetting.
- **Adding or removing workers:** `CyclicBarrier` has a fixed number of parties. `reset()` **does not change** `getParties()`. If the set of participants changes, create a new barrier with the appropriate party count or use `Phaser`.

One party timing out does not automatically cancel the work of other parties running outside the barrier. After `BrokenBarrierException`, the application must design an exit path, `Future` cancellation, interruption, and cleanup if it does not want some workers to keep computing out of control.

## 9. Interruption and Task Cancellation: Must Be Handled as Coordination Conditions

Both `CountDownLatch.await()` and `CyclicBarrier.await()` can be interrupted, but the consequences for the synchronizer differ:

| Event | Latch | Barrier |
| --- | --- | --- |
| A waiting thread is interrupted | That thread throws `InterruptedException`; other threads can still wait for count to reach 0 | May break the current generation; other parties receive `BrokenBarrierException` |
| Caller times out | Counter is unchanged; caller receives `false` | Generation is broken; caller receives `TimeoutException` |
| Worker never started | May miss a `countDown()`, preventing the latch from opening | May miss a party, causing parties already at the barrier to wait forever |
| `Future` canceled before body runs | `finally` inside the body does not run; separate accounting is needed | Party does not reach the barrier; other parties need a timeout/cancellation path |
| Worker holds a lock needed by another party | May cause a circular wait | May cause a circular wait |

When using an executor, keep the `Future` references if you need to cancel; use appropriate timeouts and handle `InterruptedException`. If one party of a barrier fails before calling `await()`, the other parties **do not automatically find out** because no barrier-breaking event has occurred yet. You may need `reset()` from the coordinator thread, `Future.cancel(true)`, or timeouts on awaiters to avoid waiting indefinitely.

**Do not swallow `InterruptedException`.** In methods that allow it, propagate the exception upward. In methods that cannot propagate it, typically restore the interrupt flag with `Thread.currentThread().interrupt()` and exit. With a broken barrier, do not loop `await()` forever on the same barrier without a recovery protocol.

## 10. Happens-Before: What Is Published When Crossing the Milestone?

### CountDownLatch

The memory consistency contract of a latch: actions in a thread **prior to calling `countDown()`** *happen-before* actions **following a successful return from a corresponding `await()`** in another thread. This allows waiting threads to see state prepared before the completion signals.

Example fragment:

```java
int[] shared = new int[1];
CountDownLatch ready = new CountDownLatch(1);

// Worker:
shared[0] = 42;
ready.countDown();

// Another thread:
ready.await();
System.out.println(shared[0]); // Sees the write before countDown.
```

The lines marked “Worker” and “Another thread” represent two hypothetical execution threads, not a standalone program. If `await(timeout)` returns `false`, the milestone must not be considered reached, nor do the guarantees of a **successful** wait apply.

### CyclicBarrier

The memory consistency contract of a barrier: actions before a party calls `await()` *happen-before* actions in `barrierAction`, and actions of the action *happen-before* actions following a **successful return from `await()`** in another party in that round. Therefore, a barrier is suitable for multi-phase algorithms where each phase needs to see the results of the previous phase.

Even so, latches and barriers **do not make read-modify-write operations on shared mutable state atomic**. If two workers increment the same variable with `counter++` before the milestone without proper synchronization, lost updates can still occur. Use separate array elements, `AtomicInteger`, locks, or concurrent data structures when workers modify shared state concurrently.

## 11. Deadlock Due to Insufficient Workers in a Thread Pool

A prominent trap is **thread starvation deadlock**. For example:

- `ExecutorService pool = Executors.newFixedThreadPool(2)`.
- Submit three tasks; each task's job is to call `barrier.await()` on `CyclicBarrier(3)`.
- The first two tasks occupy both workers and wait for the third party.
- The third task remains in the queue, with no free worker to start it.
- No party can complete: both workers are waiting for each other and for the queued task.

A similar trap can occur when using a latch with a start gate: main waits for all three workers to report “ready”, but only two pool workers can start, and both are held at an unopened latch.

How to avoid it:

1. Ensure the number of workers that can actually run concurrently is at least equal to the number of parties **that will block at the barrier**, or change the design so workers do not have to be held for the entire wait.
2. Use `await(timeout, unit)` so threads do not hang indefinitely, and handle `TimeoutException`/`BrokenBarrierException`.
3. Do not hold a monitor/lock needed by another party while waiting on a barrier or latch.
4. Do not place a `barrierAction` that waits for results from another worker currently blocked at the same barrier.
5. If the number of parties changes dynamically or workers can leave the group, consider `Phaser`.

Having more threads than parties still does not solve all forms of deadlock if tasks acquire locks in a circular order or wait on I/O without timeouts.

## 12. When to Choose Phaser?

`Phaser` is a synchronizer reusable across multiple **phases** that supports a dynamic number of parties via `register()`, `bulkRegister(int)`, and `arriveAndDeregister()`. Operations such as `arriveAndAwaitAdvance()` play a role similar to arriving at a barrier and waiting for the next phase.

| Need | Suitable Tool |
| --- | --- |
| Wait for exactly N events once | `CountDownLatch` |
| Open a gate for multiple waiters | `CountDownLatch(1)` |
| Fixed group of N workers meeting at the end of each round | `CyclicBarrier(N)` |
| Group of workers that can register/deregister across phases | `Phaser` |
| Control concurrency level using permits | `Semaphore` |
| Wait for a `Future<T>` to complete and read its result/error | `Future.get()` |
| Wait for a specific `Thread` to terminate | `Thread.join()` |

A notable difference: `CyclicBarrier` has a **broken** mechanism when a party is interrupted or times out while waiting; `Phaser` has a different policy, where phase-waiting overloads with timeout/interruption **do not automatically break the phaser state** in the way `CyclicBarrier` does. Read the `Phaser` contract before switching, as error handling is not the same.

Do not choose `Phaser` just because it has more features; for a fixed-party multi-round problem, `CyclicBarrier` is often easier to read. For an independent one-time milestone, `CountDownLatch` is simpler and involves less protocol.

## 13. Safe Synchronizer Design Checklist

Before writing code, ask yourself:

1. **Milestone or rendezvous?** Does the signaling party need to wait for the remaining parties?
2. **One-shot or multi-phase?** After opening the milestone, do you actually need to close it again to wait for a new round?
3. **Fixed party count?** Who registers parties, and who is allowed to leave?
4. **Who is affected by one task's failure?** With a barrier, when one party fails, should the other parties continue to another round?
5. **What error does a timeout produce?** A latch returns a boolean; a barrier throws an exception and may become broken.
6. **Enough workers?** Could any task sit in a queue while all workers are waiting on the synchronizer?
7. **Side effects and cleanup?** Does an arriving signal mean success, that the task exited, or that resources were released?
8. **Where are results stored?** Latches/barriers do not replace `Future` or a place to collect exceptions.
9. **Memory visibility?** Are you using the proper synchronization point, and avoiding data races among workers writing data concurrently?
10. **What happens after an error?** Cancel tasks, close resources, create a new barrier, or abort the entire computation?

If a worker can be canceled **before starting**, `finally` inside the task will not run; the coordinator must handle unaccepted tasks. With a barrier, fewer parties actually arriving than expected is a classic cause of infinite waiting.

## 14. Common Mistakes

| Mistake | Consequence | Fix |
| --- | --- | --- |
| Using one `CountDownLatch` for multiple rounds thinking `await()` resets itself | After count reaches 0, every subsequent `await()` passes immediately | Create a new latch per stage or use `CyclicBarrier` |
| Using `CyclicBarrier` just for one thread to wait for N signals without blocking workers | Workers are forced to wait at `await()` | Use `CountDownLatch` |
| Assuming `countDown()` waits for other parties | Misunderstands latency and execution flow | Remember `countDown()` is non-blocking |
| Assuming a barrier resets itself even when broken | Subsequent `await()` calls continue to fail | Coordinate error handling, reset intentionally, or create a new barrier |
| Calling `reset()` after every successful round | May accidentally break a party arriving for the next round | Let the barrier reuse itself automatically |
| Using `await(timeout)` without distinguishing boolean from exception | Incorrect error handling | Latch returns boolean; barrier throws `TimeoutException` |
| Swallowing `InterruptedException` in a party | Unclear cancellation contract; barrier may become broken | Propagate/restore interrupt and coordinate error handling |
| Providing fewer workers than parties that must wait | Thread starvation deadlock | Ensure sufficient capacity, use timeouts, or redesign |
| Reading `getNumberWaiting()` and predicting for sure who will arrive | State changes concurrently | Use for diagnostics/debugging, not primary coordination |
| Using latch/barrier as an exception-storage or rollback mechanism | Tasks may fail or cause side effects even though the milestone is reached | Combine `Future`, result status, and cleanup |
| Letting multiple workers increment a plain variable | Data race despite the barrier | Use atomic/lock or separate result slots |
| Running long I/O inside a barrier action | Holds all parties at the barrier, increasing latency | Keep the action short; do I/O outside with its own timeout |

## 15. Self-Check Questions

**1. Once a CountDownLatch has reached 0, can you call reset to wait for a second round?**  
No. It is one-shot; to wait for a new milestone, create a new latch or choose another synchronizer.

**2. How many `await()` calls does `CyclicBarrier(4)` require in each round?**  
Four parties arriving in the same generation. Once all four arrive, the barrier trips, then automatically prepares for the next round.

**3. What should a worker use if it only signals completion and does not need to wait for other workers?**  
`CountDownLatch.countDown()` if the goal is to open a milestone for other threads.

**4. Does `CountDownLatch.await(1, SECONDS)` throw `TimeoutException` on timeout?**  
No; this overload returns `false` when the count has not reached 0 and the time has elapsed.

**5. If one party times out in `CyclicBarrier.await(timeout,unit)`, do the other parties keep waiting in that round until enough arrive?**  
Not under normal semantics; the barrier becomes broken and the other waiting parties receive `BrokenBarrierException`.

**6. Is it necessary to call `barrier.reset()` after a successful round?**  
No. `CyclicBarrier` reuses itself automatically. Calling `reset()` can break waiting parties.

**7. Where does `barrierAction` run?**  
On the thread of the last party to arrive, before releasing the parties of that round.

**8. Why can a 2-worker pool and a 3-party barrier deadlock?**  
Two workers can be waiting for the third party, while the third party is stuck in the queue with no worker available to run it.

**9. Does a barrier automatically make `sharedCounter++` across multiple workers safe?**  
No. A barrier only coordinates phase milestones and visibility; contended read-modify-write operations still require synchronization.

**10. When the number of parties can change dynamically across phases, what should you consider?**  
`Phaser`, because it supports registering and deregistering parties, rather than `CyclicBarrier` which has a fixed party count.

## References

- [Java SE 17 — CountDownLatch](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/concurrent/CountDownLatch.html)
- [Java SE 17 — CyclicBarrier](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/concurrent/CyclicBarrier.html)
- [Java SE 17 — Phaser](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/concurrent/Phaser.html)
- [Java SE 17 — Semaphore](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/concurrent/Semaphore.html)
- [Java SE 17 — ExecutorService](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/concurrent/ExecutorService.html)

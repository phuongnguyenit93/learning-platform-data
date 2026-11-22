# Avoiding Deadlock Caused by Missing arrive(), countDown(), or release()

## 1. Learning Objectives and Scope

After this lesson, you will be able to:

- Distinguish between **deadlock**, **indefinite waiting due to a missing signal**, **resource leak**, **starvation**, and **broken barrier**. Not every thread in the `WAITING` state proves a circular wait deadlock in the strict sense.
- Understand the role of **CountDownLatch.countDown()**, **CyclicBarrier.await()**, **Phaser.arrive()/arriveAndDeregister()**, and **Semaphore.release()** in allowing other threads to make progress.
- Identify **early return**, **exception**, **interruption**, **timeout**, **rejected task**, and **unstarted task** paths that prevent completion events from being signaled.
- Use **try/finally**, controlled participant registration/deregistration, and **release permits only when acquisition succeeds**.
- Choose **timeout, failure propagation, cancellation, and abort policies** to let the system escape indefinite waiting, without confusing a timeout with fixing state or rolling back side effects.
- Distinguish **signaling task completion** from **signaling task success**; never call `countDown` or `arrive` to fake an unmet business condition.
- Run Java 17+ programs demonstrating liveness failures and proper protocol design, with verifiable stdout using latches, `join`, and exception handling instead of relying on `Thread.sleep`.

This lesson belongs to **Synchronizers** in **general Java concurrency**. Spring-specific mechanisms are covered in their own chapter and are not used here.

## 2. Synchronizers Cannot Rescue an Abandoned Protocol

Many primitives work properly only when **all participants follow the protocol**. They cannot guess that a thread has failed, been cancelled, forgotten to signal completion, or leaked a permit.

~~~text
Thread A                              Thread B
--------                              --------
perform work                          await signal
       |
       +-- success -> signal -------------> continue
       |
       +-- exception -> forgot signal ----> still waiting
       |
       +-- early return -> forgot signal -> still waiting
~~~

Another case:

~~~text
Worker A: semaphore.acquire() -> holds permit
          encounters error and returns, forgets release()
Worker B: semaphore.acquire() -> no permits left -> waits
~~~

How to handle this depends on **signal semantics**:

- If the latch represents **“the worker has finished, including on failure”**, call `countDown` in `finally` and record errors through a separate channel.
- If the latch represents **“all steps have met the success condition”**, do not unconditionally call `countDown` in `finally` and let the consumer assume success. You need a `FAILED` state model, an error-reporting channel, or a different primitive/protocol.
- If a `Phaser` has registered participants but a worker cannot continue, deregistering at the right time can prevent a phase stall; however, you must ensure that subsequent phases still make sense.
- With a semaphore, release only when a permit has actually been acquired under the contract; over-releasing creates a different bug that can be worse than waiting too long.

**Key point:** clearly define who must signal, what the signal represents, and what each execution exit path does.

## 3. Is “Deadlock” the Right Name for Every Hang?

A program that waits forever can be caused by several distinct failure modes:

| Phenomenon | Example | Analysis |
| --- | --- | --- |
| **Circular-wait deadlock** | A holds lock L, waits for B; B needs L to finish | Resource dependency cycle exists |
| **Missing signal / liveness failure** | Latch `count=1` but no one can call `countDown` | Waiter is stuck even without a two-thread lock cycle |
| **Broken barrier** | One party times out/is interrupted in `CyclicBarrier.await()` | Barrier becomes broken; other waiters receive `BrokenBarrierException` |
| **Permit leak** | `Semaphore.acquire` succeeds without `release` | Available permits decrease; waiters may get stuck |
| **Starvation** | Tasks occupy all workers and wait for subtasks in the same pool | Subtasks never get scheduled, even without two monitors |
| **Livelock** | Multiple threads keep yielding/changing state without making progress | Activity occurs, but no business progress |

**WAITING** and **TIMED_WAITING** states in a thread dump are diagnostic clues, not proof of a single bug type. A thread can legitimately be `WAITING` because it is waiting for an event that has not arrived yet.

### Wait-for graph

~~~text
A waits for B to complete
B waits for lock L held by A
     A --> B --> L --> A  : deadlock cycle

C waits for latch count to reach 0
No producer holds responsibility for countDown
     C --> latch?        : waits forever due to lost completion
~~~

Both cases hurt liveness, but the fixes differ: the first requires breaking the dependency/lock ordering; the second requires fixing the completion and error-reporting protocol.

## 4. CountDownLatch: Missing countDown Prevents await from Finishing

**CountDownLatch(initialCount)** is a one-shot synchronizer. Each `countDown()` decrements the counter by one (stopping at 0). **await()** waits until the counter reaches 0; once the count is 0, subsequent `await` calls pass through immediately.

~~~java
// Illustration, not a standalone file:
CountDownLatch completed = new CountDownLatch(2);
workerA.start();
workerB.start();
completed.await();
~~~

If both `workerA` and `workerB` must call `countDown` once, but one returns before signaling, `completed.getCount()` may remain greater than 0 forever.

**The counter does not decrement automatically when a Thread terminates**, when a `Runnable` throws an exception, or when an executor shuts down. The primitive knows nothing about the business story behind the `completed` variable.

### Common Causes

- `countDown` is placed at the end of the `try` block, and an exception is thrown before that line.
- A branch returns immediately upon detecting invalid input.
- A task is not submitted due to `RejectedExecutionException`, yet the coordinator still included that task in the count.
- A worker dies before starting and the coordinator has no compensation/failure policy.
- A thread is interrupted while working and the handler exits without signaling completion.
- Miscounting workers/stages: creating a latch with `count=5` when only 4 participants are actually responsible for signaling.
- One side assumes the other will call `countDown`, so neither does.

**Invariant to establish:** if a latch represents `N` completions, there must be **N completion obligations**, and each obligation must reach a terminal state exactly once, including handled failure paths.

### finally Does Not Guarantee Success by Itself

~~~java
// Code snippet inside Runnable, not a standalone program:
try {
    doWork();
} catch (RuntimeException failure) {
    recordFailure(failure);
} finally {
    completed.countDown();
}
~~~

In this example, `countDown` means **“finished due to success or failure”**. After `await`, the consumer must check `recordFailure` or the result state. Naming the latch `allSucceeded` and calling `countDown` on every error path is a broken protocol.

## 5. Example 1: CountDownLatch Signals Completion, Errors via a Separate Channel

File **LatchFinallyDemo.java**:

~~~java
import java.util.concurrent.CountDownLatch;
import java.util.concurrent.atomic.AtomicInteger;

public class LatchFinallyDemo {
    public static void main(String[] args) throws InterruptedException {
        CountDownLatch completed = new CountDownLatch(2);
        AtomicInteger succeeded = new AtomicInteger();
        AtomicInteger failed = new AtomicInteger();

        Runnable good = () -> {
            try {
                succeeded.incrementAndGet();
            } finally {
                completed.countDown();
            }
        };

        Runnable bad = () -> {
            try {
                throw new IllegalStateException("demo failure");
            } catch (IllegalStateException ex) {
                failed.incrementAndGet();
            } finally {
                completed.countDown();
            }
        };

        Thread first = new Thread(good, "good");
        Thread second = new Thread(bad, "bad");
        first.start();
        second.start();

        completed.await();
        first.join();
        second.join();

        System.out.println("remaining = " + completed.getCount());
        System.out.println("succeeded = " + succeeded.get());
        System.out.println("failed = " + failed.get());
        System.out.println("all succeeded = " + (failed.get() == 0));
    }
}
~~~

~~~bash
javac -encoding UTF-8 LatchFinallyDemo.java
java LatchFinallyDemo
~~~

Stdout:

~~~text
remaining = 0
succeeded = 1
failed = 1
all succeeded = false
~~~

**Explanation:**

1. The coordinator creates a latch with `count=2` matching two completion obligations.
2. Both `good` and `bad` place `countDown` in `finally`.
3. Task `bad` intentionally throws an exception; `catch` records the failure, and `finally` still signals **completion**.
4. `await` finishes when `count=0`, without busy waiting.
5. Separate counters show that **not all tasks succeeded**.
6. `join` waits for both threads to finish before printing stdout, creating a clear point to read the results.

### When Should You Not Call countDown in finally?

If the signal means **“the stage has reached a safe condition to proceed”**, failures must not be signaled as success. A proper design usually uses an independent **result/failure state** that the coordinator checks after the latch, or uses `Future` to retrieve the result/exception. Do not fix a hang bug by letting downstream code proceed with missing data.

## 6. Example 2: Simulating Missing countDown with a Controlled Timeout

The following example does not spawn a mysterious worker just to hang the program. We create a latch where **no thread calls countDown**, then use the timed `await` overload to observe the semantics without getting stuck forever.

File **MissingLatchSignalDemo.java**:

~~~java
import java.util.concurrent.CountDownLatch;
import java.util.concurrent.TimeUnit;

public class MissingLatchSignalDemo {
    public static void main(String[] args) throws InterruptedException {
        CountDownLatch neverCompleted = new CountDownLatch(1);

        boolean completed =
                neverCompleted.await(15, TimeUnit.MILLISECONDS);

        System.out.println("completed = " + completed);
        System.out.println("remaining = " + neverCompleted.getCount());
    }
}
~~~

~~~bash
javac -encoding UTF-8 MissingLatchSignalDemo.java
java MissingLatchSignalDemo
~~~

Stdout:

~~~text
completed = false
remaining = 1
~~~

**Why is this accurate?** No code path calls `countDown()`, so after the bounded wait, `await(timeout)` returns `false` and the counter remains `1`. **Timeout does not decrement the count**, does not grant permission to proceed with success logic, and does not fix the lost completion bug.

In production, a timeout must lead to a clear policy:

- Report an error or return an **INCOMPLETE** status.
- Attempt to cancel remaining tasks if they support cooperative cancellation.
- Collect diagnostics and identify which participant failed to report.
- Retry when business logic allows, with backoff/idempotency.
- Do not loop on timeouts and keep waiting indefinitely if the request deadline has already expired.

**CountDownLatch does not reset.** If you need multiple repeating phases or a dynamic number of parties, see `CyclicBarrier`/`Phaser` and the other rules below.

## 7. CountDownLatch and Future: Better Exception Handling

If a group of tasks runs in an `ExecutorService` and the caller needs **individual results**, keeping a list of **Future**s is often more natural than using a latch solely to detect completion.

~~~java
// Illustration inside a method with an ExecutorService pool:
Future<Integer> f = pool.submit(() -> calculate());
try {
    int result = f.get();
} catch (ExecutionException ex) {
    handleFailure(ex.getCause());
}
~~~

This is not a standalone program: `calculate()`, `handleFailure()`, `pool`, and imports are assumed. `Future.get()` can throw `InterruptedException`; if using a timeout, it can also throw `TimeoutException`.

**Distinction:** A `Future` enters the **done** state even on failure or cancellation. The caller must inspect `get()`/exceptions rather than relying on `isDone()` to conclude success.

### Pitfall: Counting Obligations Before Tasks Are Accepted

~~~text
Coordinator creates latch count=10
Executor accepts only 8 tasks; 2 submits are rejected.
8 workers finish and call countDown 8 times.
Latch has 2 left; no one is responsible for countDown.
~~~

If you still want to use a latch, there must be a clear contract that **the coordinator compensates for unaccepted tasks** or aborts the entire workflow. Never emit a fake success signal. For rejected tasks, the caller must handle **RejectedExecutionException** right at `submit` instead of ignoring it.

Another solution is to **count only accepted obligations** via a dynamic registration mechanism (`Phaser`) or a collection of `Future`s, while resolving any race between register/start and closing admission.

## 8. CyclicBarrier: Missing One Party Can Stall the Entire Group

**CyclicBarrier(parties)** creates a rendezvous point for an exact fixed number of parties at each **generation**. Each party calls **await()**; when enough parties arrive, the barrier trips, the threads are released to continue, and the barrier becomes ready for the next generation.

~~~text
CyclicBarrier(3)

Thread A: ... await() ---+
Thread B: ... await() ---+-- 3 arrived --> all continue together
Thread C: ... await() ---+
~~~

If `C` **never calls await()** while `A` and `B` call `await()` without a timeout, those threads can wait forever. That is a participant protocol bug. **CyclicBarrier does not automatically know C has died** if `C` never entered the barrier.

### Differences from CountDownLatch

| Property | CountDownLatch | CyclicBarrier |
| --- | --- | --- |
| Count | `CountDown` by number of completions | Fixed number of parties that must `await` in a phase |
| Reuse | Does not reset after reaching 0 | Can be reused across multiple generations |
| Signal comes from | Workers calling `countDown` | Each party reaching `await` |
| Failure/waiting for missing party | Can wait indefinitely | Can wait indefinitely without timeout/interruption |
| Timeout | `await(timeout)` returns `boolean` | `await(timeout)` can throw `TimeoutException` and break the barrier |
| Failure state | No built-in broken flag | Has **isBroken()** |

**Do not use a countdown latch instead of a barrier just because both involve “waiting”.** A barrier synchronizes parties at **the same phase milestone**, whereas a latch lets one or more waiters observe a counter reaching 0.

### Role of the Barrier Action

The `CyclicBarrier` constructor can accept a **Runnable barrierAction** that runs when all parties arrive, before the parties are released. If the action throws an exception, it can break the barrier. Do not put long blocking side effects inside the barrier action and then be surprised that all parties are slowed down.

## 9. Example 3: Missing One Party in CyclicBarrier

File **BarrierMissingPartyDemo.java**:

~~~java
import java.util.concurrent.BrokenBarrierException;
import java.util.concurrent.CyclicBarrier;
import java.util.concurrent.TimeUnit;
import java.util.concurrent.TimeoutException;
import java.util.concurrent.atomic.AtomicBoolean;

public class BarrierMissingPartyDemo {
    public static void main(String[] args) throws InterruptedException {
        CyclicBarrier barrier = new CyclicBarrier(2);
        AtomicBoolean timedOut = new AtomicBoolean();

        Thread onlyParticipant = new Thread(() -> {
            try {
                barrier.await(20, TimeUnit.MILLISECONDS);
            } catch (TimeoutException ex) {
                timedOut.set(true);
            } catch (InterruptedException ex) {
                Thread.currentThread().interrupt();
            } catch (BrokenBarrierException ex) {
                throw new AssertionError("unexpected broken", ex);
            }
        });

        onlyParticipant.start();
        // No second party calls await().
        onlyParticipant.join();

        System.out.println("timed out = " + timedOut.get());
        System.out.println("broken = " + barrier.isBroken());
    }
}
~~~

~~~bash
javac -encoding UTF-8 BarrierMissingPartyDemo.java
java BarrierMissingPartyDemo
~~~

Stdout:

~~~text
timed out = true
broken = true
~~~

**Why?**

- The barrier requires 2 parties, but only one thread reaches `await`.
- After the timeout, `await` throws `TimeoutException` and the generation transitions to the broken state.
- `main` joins the thread and then reads the flags.
- No `Thread.sleep` is used to “hope” to catch up.
- The output demonstrates the failure path, **not successful barrier operation**.

If a thread waiting at `await` is interrupted, the barrier can also become broken and other waiters receive `BrokenBarrierException`. **Never catch InterruptedException and silently ignore it** while teammates are waiting for that party.

### Timeout Does Not Automatically Complete the Stage for All Parties

When a barrier is broken, that generation must be treated as failed. You can call **reset()** in a coordinated restart protocol, but calling `reset` arbitrarily while other parties are still using the barrier causes logic bugs. The design must define who is allowed to reset, who cancels old work, and when all parties are ready to enter a new generation.

## 10. Example 4: CyclicBarrier with All Parties, Two Phases

File **BarrierTwoPhasesDemo.java**:

~~~java
import java.util.concurrent.CyclicBarrier;
import java.util.concurrent.TimeUnit;
import java.util.concurrent.atomic.AtomicInteger;

public class BarrierTwoPhasesDemo {
    public static void main(String[] args) throws InterruptedException {
        AtomicInteger trips = new AtomicInteger();
        CyclicBarrier barrier = new CyclicBarrier(
                2, trips::incrementAndGet
        );
        AtomicInteger completed = new AtomicInteger();

        Runnable worker = () -> {
            try {
                for (int phase = 0; phase < 2; phase++) {
                    // Perform local step then arrive at the same barrier.
                    barrier.await(5, TimeUnit.SECONDS);
                    completed.incrementAndGet();
                }
            } catch (Exception ex) {
                throw new IllegalStateException("barrier failed", ex);
            }
        };

        Thread a = new Thread(worker, "a");
        Thread b = new Thread(worker, "b");
        a.start();
        b.start();
        a.join();
        b.join();

        System.out.println("barrier trips = " + trips.get());
        System.out.println("completed steps = " + completed.get());
        System.out.println("broken = " + barrier.isBroken());
    }
}
~~~

~~~bash
javac -encoding UTF-8 BarrierTwoPhasesDemo.java
java BarrierTwoPhasesDemo
~~~

Stdout under normal execution without external interruption:

~~~text
barrier trips = 2
completed steps = 4
broken = false
~~~

Both `a` and `b` reach the barrier exactly twice, so the action runs twice; each thread passes each phase and increments `completed`. **The wait duration is not a benchmark**; the 5-second limit is only an escape hatch when something goes wrong in the environment, not a fixed timing SLA.

**If a worker may leave the workflow before phase 2**, a fixed-party `CyclicBarrier` may not fit unless the coordinator has a clear protocol to terminate or recreate the group. Use `Phaser` when you need dynamic participants.

## 11. Phaser: arrived, unarrived, and registered parties

**Phaser** supports multi-phase synchronization with a **dynamic number of parties**. A party can `register`, **arrive**, **arriveAndAwaitAdvance**, or **arriveAndDeregister**.

| API | Semantics |
| --- | --- |
| `register()` | Registers one additional party |
| `bulkRegister(n)` | Registers `n` parties |
| `arrive()` | Signals that the party has arrived at the current phase, without waiting |
| `arriveAndAwaitAdvance()` | Signals arrival and waits for the phase to advance |
| `arriveAndDeregister()` | Signals arrival and leaves the party group for subsequent phases |
| `awaitAdvance(phase)` | Waits for the phase to change; does not itself count as an arrival |
| `awaitAdvanceInterruptibly(phase, timeout, unit)` | Waits with interruption/timeout support depending on overload |
| `forceTermination()` | Forces the Phaser to terminate, waking waiters according to termination semantics |
| `getRegisteredParties()`/`getUnarrivedParties()` | Number of registered / unarrived parties in the current phase |

**Crucial distinction:** **awaitAdvance(phase) does not call arrive() automatically**. If a party only calls `awaitAdvance` while it still has an arrival obligation and no one else compensates, the phase may never advance.

### Failure Examples

~~~text
Phaser registers 3 parties.
A calls arrive().
B calls arrive().
C throws an exception before arrive().
C does not deregister.
=> unarrived remains 1, phase does not advance.
~~~

If a participant disappears after calling `register` and the coordinator has no detection/compensation protocol, waiters can get stuck. **Phaser does not automatically guess that a party has died**.

**Do not register too early:** if you register before being able to start the worker and starting fails, the arrival obligation still exists. Keep register/start/deregister obligations within a scope that can handle errors.

## 12. Phaser and finally: Correct, but Not Always Needed

For a worker that participates in only one stage and then leaves, you can do:

~~~java
// Illustrative snippet; phaser is already shared and party is registered.
try {
    doWork();
} finally {
    phaser.arriveAndDeregister();
}
~~~

This is a code snippet; `doWork()` and appropriate start/exception handling are required. `finally` ensures the worker does not hold its party registration longer than its intended lifecycle when exiting normally or via an exception.

**However**, if a worker's failure makes the next phase unsafe, merely deregistering and letting everyone else continue is wrong for business logic. Record a `FAILED` state, notify the coordinator, and cancel the phase or call **forceTermination()** according to a defined protocol.

### Double-Arrival Bug

A party that has already called **arrive()** in the current phase **must not arrive again in the same phase**. Over-counting can violate the `Phaser` protocol or throw `IllegalStateException` when party/unarrived counts become invalid. If `finally` calls `arriveAndDeregister` after the body already called `arrive()`, you must track state to **avoid double arrival**.

Use a **single owner of arrival responsibility** per phase rather than having multiple branches report independently.

## 13. Example 5: Phaser with Workers Registered Before Start

File **PhaserDeregisterDemo.java**:

~~~java
import java.util.ArrayList;
import java.util.List;
import java.util.concurrent.Phaser;
import java.util.concurrent.atomic.AtomicInteger;

public class PhaserDeregisterDemo {
    public static void main(String[] args) throws InterruptedException {
        Phaser phaser = new Phaser(1); // Main is the coordinator.
        AtomicInteger completed = new AtomicInteger();
        List<Thread> workers = new ArrayList<>();

        for (int i = 0; i < 3; i++) {
            phaser.register(); // Obligation of the new worker.
            Thread worker = new Thread(() -> {
                try {
                    completed.incrementAndGet();
                } finally {
                    phaser.arriveAndDeregister();
                }
            }, "worker-" + i);
            workers.add(worker);
            worker.start();
        }

        phaser.arriveAndAwaitAdvance();
        for (Thread worker : workers) {
            worker.join();
        }

        System.out.println("completed = " + completed.get());
        System.out.println(
                "registered parties = " + phaser.getRegisteredParties()
        );

        phaser.arriveAndDeregister(); // Coordinator leaves the Phaser.
    }
}
~~~

~~~bash
javac -encoding UTF-8 PhaserDeregisterDemo.java
java PhaserDeregisterDemo
~~~

Stdout:

~~~text
completed = 3
registered parties = 1
~~~

**Explanation:**

- `main` is registered immediately via `new Phaser(1)`.
- Before starting each worker, the coordinator registers that worker's obligation.
- Each worker, even if its logic throws an unchecked exception after entering `try`, still calls `arriveAndDeregister` in `finally`.
- `main` calls `arriveAndAwaitAdvance`, waiting for the registered workers of the current phase to finish/deregister.
- After the phase advances, only `main` remains registered: `registered parties = 1`.
- `main` deregisters at the end; no participants remain.
- `completed` reflects that three workers processed the demonstration work.

**Limitation:** The example assumes `start()` succeeds and no fatal error occurs before entering `try`. Real applications must handle the case where **Thread.start() fails**, avoid leaving a registered party with no worker, and have a coordinator failure policy.

### If a Thread Fails Mid-Way Through Multiple Phases

When there are multiple rounds, you must specify at which phase a worker is allowed to leave, whether the party count is allowed to shrink, and whether a single failure invalidates that phase's result. **arriveAndDeregister** only manages the participant count; it does not compensate for business data that the departing party never produced.

## 14. Phaser Timeouts Differ from CyclicBarrier

With **CyclicBarrier.await(timeout)**, when one party times out it typically **breaks the barrier** and other waiters have a path to receive `BrokenBarrierException`.

With **Phaser.awaitAdvanceInterruptibly(phase, timeout, unit)**, a thread timing out or being interrupted **does not automatically terminate the Phaser**, and this waiting method **does not fulfill a party's arrival obligation**. If the coordination bug persists, other parties may remain stuck.

A strategy when progress cannot continue:

1. Coordinator catches `TimeoutException` or `InterruptedException`.
2. Mark the phase as failed and stop dispatching new work for that phase.
3. Decide to call **forceTermination()** if the entire group must stop.
4. Request all workers to cooperate with stopping/cancellation and release resources.
5. Separate **stopping the wait** from **rollback/compensation** for external side effects.

**forceTermination does not kill threads and does not roll back transactions.** It changes the phaser's state and wakes waiters per contract; workers may still be running if they do not check for cancellation themselves.

## 15. Semaphore: Missing release Causes Permit Leaks

**Semaphore(permits)** represents the number of available access permits. **acquire()** may block until a permit is obtained; **release()** returns a permit.

~~~java
// Illustrative anti-pattern:
sem.acquire();
doWork(); // An exception here prevents sem.release from being called.
sem.release();
~~~

This snippet is not standalone; `sem` and `doWork` must exist, and the method must handle `InterruptedException`. If a worker throws or returns before `release`, the permit count permanently decreases from the semaphore's perspective until proper compensating action is taken.

**A semaphore that leaks all its permits can cause every new caller to wait forever.** That is a liveness failure; when combined with multiple resources/locks, it can also create a circular-wait deadlock.

### Correct Pattern with Interruptible acquire

~~~java
// Code snippet inside a method that throws InterruptedException.
boolean acquired = false;
try {
    sem.acquire();
    acquired = true;
    doWork();
} finally {
    if (acquired) {
        sem.release();
    }
}
~~~

**Why is the `acquired` flag needed?** `acquire()` can throw `InterruptedException` **before obtaining a permit**. If `finally` calls `release` unconditionally, the permit count increases erroneously, causing an over-release.

### Alternative: Place try Immediately After acquire

~~~java
sem.acquire();
try {
    doWork();
} finally {
    sem.release();
}
~~~

When `sem.acquire()` throws an exception, execution has not entered this `try/finally` block, so it does not release. When `acquire` succeeds and enters `try`, `finally` returns the permit. This is a clean, correct pattern in normal flow, though you must watch out for abnormal errors between `acquire` and `try` if additional operations are placed there; keep that gap minimal.

## 16. Example 6: Interrupted Before acquire Must Not Over-Release

We use a holder that keeps the single permit. A waiter is interrupted while trying to `acquire`, so it **has no permit** to return. In `finally`, the waiter releases only when `acquired` is `true`.

File **SemaphoreInterruptDemo.java**:

~~~java
import java.util.concurrent.CountDownLatch;
import java.util.concurrent.Semaphore;
import java.util.concurrent.atomic.AtomicBoolean;

public class SemaphoreInterruptDemo {
    public static void main(String[] args) throws InterruptedException {
        Semaphore permits = new Semaphore(1);
        CountDownLatch holderReady = new CountDownLatch(1);
        CountDownLatch allowRelease = new CountDownLatch(1);
        AtomicBoolean waiterInterrupted = new AtomicBoolean();

        Thread holder = new Thread(() -> {
            boolean acquired = false;
            try {
                permits.acquire();
                acquired = true;
                holderReady.countDown();
                allowRelease.await();
            } catch (InterruptedException ex) {
                Thread.currentThread().interrupt();
            } finally {
                if (acquired) {
                    permits.release();
                }
            }
        });

        holder.start();
        holderReady.await(); // Holder is holding the only permit.

        Thread waiter = new Thread(() -> {
            boolean acquired = false;
            try {
                permits.acquire();
                acquired = true;
            } catch (InterruptedException ex) {
                waiterInterrupted.set(true);
                Thread.currentThread().interrupt();
            } finally {
                if (acquired) {
                    permits.release();
                }
            }
        });

        waiter.start();
        waiter.interrupt();
        waiter.join();

        allowRelease.countDown();
        holder.join();

        System.out.println(
                "waiter interrupted = " + waiterInterrupted.get()
        );
        System.out.println("permits = " + permits.availablePermits());
    }
}
~~~

~~~bash
javac -encoding UTF-8 SemaphoreInterruptDemo.java
java SemaphoreInterruptDemo
~~~

Stdout:

~~~text
waiter interrupted = true
permits = 1
~~~

**Reasoning:**

1. `holder` acquires the permit and signals `holderReady`; only then does `main` start `waiter`.
2. `waiter` cannot obtain the permit held by `holder`.
3. `main` interrupts `waiter`; even if the interrupt arrives before `waiter` actually blocks, interruptible `acquire` still handles the interrupt status upon starting.
4. Because `acquire` did not succeed, `acquired` remains `false`; `waiter` does not call `release`.
5. `holder` is then released via the latch and returns exactly one permit.
6. The result is `permits=1`, with no over-release.

**Note:** `Semaphore` does not tie permit ownership strictly to a thread like `ReentrantLock`; the API allows a different thread to call `release`. Because of this, **the application must enforce permit ownership discipline** at the business level and never treat arbitrary `release` calls as safe.

## 17. Example 7: Semaphore Limiting Concurrency and Returning Permits on All Paths

File **SemaphoreCapacityDemo.java**:

~~~java
import java.util.concurrent.Semaphore;
import java.util.concurrent.atomic.AtomicInteger;

public class SemaphoreCapacityDemo {
    public static void main(String[] args) throws InterruptedException {
        Semaphore slots = new Semaphore(2);
        AtomicInteger active = new AtomicInteger();
        AtomicInteger peak = new AtomicInteger();
        AtomicInteger completed = new AtomicInteger();

        Runnable task = () -> {
            boolean acquired = false;
            try {
                slots.acquire();
                acquired = true;

                int now = active.incrementAndGet();
                peak.accumulateAndGet(now, Math::max);
                try {
                    if (6 * 7 == 42) {
                        completed.incrementAndGet();
                    }
                } finally {
                    active.decrementAndGet();
                }
            } catch (InterruptedException ex) {
                Thread.currentThread().interrupt();
            } finally {
                if (acquired) {
                    slots.release();
                }
            }
        };

        Thread[] threads = new Thread[4];
        for (int i = 0; i < threads.length; i++) {
            threads[i] = new Thread(task);
            threads[i].start();
        }
        for (Thread t : threads) {
            t.join();
        }

        System.out.println("completed = " + completed.get());
        System.out.println("peak <= 2 = " + (peak.get() <= 2));
        System.out.println("permits = " + slots.availablePermits());
    }
}
~~~

~~~bash
javac -encoding UTF-8 SemaphoreCapacityDemo.java
java SemaphoreCapacityDemo
~~~

Stdout:

~~~text
completed = 4
peak <= 2 = true
permits = 2
~~~

The **2-permit** limit ensures no more than 2 tasks can enter the critical section simultaneously. Since the task is very short, the actual peak may be 1 or 2; only assert the invariant **peak <= 2**, do not print “peak = 2” when the scheduler does not guarantee it.

**Fixing missing releases is not just to avoid hangs**: if you under-release, permits drop to 0/1; if you over-release, permits can exceed 2 and break the concurrency limit.

## 18. Semaphore: Acquiring Multiple Permits Must Release the Exact Same Count

With **acquire(n)** and **release(n)**, the number of permits returned must match the number actually acquired.

~~~java
// Code snippet inside a method that throws InterruptedException:
sem.acquire(2);
try {
    useTwoResources();
} finally {
    sem.release(2);
}
~~~

If you acquire 2 and release only 1, the semaphore leaks one permit. If you acquire 1 and release 2, the limit is violated.

**Do not** do this:

~~~java
// Anti-pattern: buggy because acquire is not guaranteed to succeed.
try {
    sem.acquire(2);
    work();
} finally {
    sem.release(2);
}
~~~

If `acquire(2)` is interrupted before returning, `finally` still releases 2 even though the caller was never granted them. The same applies when `tryAcquire(timeout)` returns `false`: release only if the result was actually `true`.

### Fairness

`Semaphore` has a fairness constructor. Fair mode affects the order in which permits are granted to waiting threads under the contract, but it does not guarantee every thread gets CPU turns evenly or that every `tryAcquire` participates in the policy. **Fairness does not fix permit leaks**.

## 19. Return, Exception, Interrupt, and Cancel: Responsibility Matrix

| Exit point | CountDownLatch | Phaser/CyclicBarrier | Semaphore |
| --- | --- | --- | --- |
| Success | Signal completion per contract | Arrive in right phase / await in right generation | Release acquired permit |
| Validation failure before work | Report failure; completion depends on semantics | Abort/deregister if already registered | Do not release if not acquired |
| Runtime exception mid-way | `finally` for completion; record error | Deregister or terminate per policy, avoid double arrive | `finally` releases owned permit |
| InterruptedException | Propagate/restore and report status | Cancel phase/coordinate remaining parties per contract | If `acquire` did not succeed: do not release |
| Timeout waiting for others | Do not treat `false` as success | Broken barrier or Phaser timeout requires coordinator handling | `tryAcquire` `false`: do not hold/release permit |
| Executor rejects task | Coordinator handles unaccepted task obligation | Do not leave orphaned registration | Do not assume permit belongs to rejected task |
| Task cancelled before running | Coordinator needs completion/failure protocol | Cancel or deregister registered party | Return permit only if actually acquired |
| Shutdown while pending | Does not auto-`countDown` obligations | Does not auto-unregister missing parties | Does not auto-reclaim permits held by old tasks |

**Principle:** each primitive has a different **unit of responsibility** (count, party-phase, permit). Do not fix one unit by over-issuing another.

## 20. Use Timeout to Detect, Not to Hide Bugs

An unbounded `await()` is appropriate when the protocol proves a signal will arrive and requirements allow waiting. In systems with multiple failure sources, timed overloads are often useful:

~~~java
// Illustration with CountDownLatch:
if (!completed.await(5, TimeUnit.SECONDS)) {
    throw new IllegalStateException("completion deadline exceeded");
}
~~~

This is not a standalone program: `completed` must exist and the method must declare `InterruptedException`.

**Timeout only provides an escape hatch for the waiter.** It does not:

- Decrement a `CountDownLatch` count.
- Restore leaked permits.
- Force another thread to call `arrive`.
- Stop a running task or undo external I/O.
- Prove which worker caused the failure without telemetry.
- Turn a partial-data result into a successful result.

A good timeout policy includes **error reporting**, **cooperative cancellation**, **diagnostic collection**, **cleanup**, **bounded backoff/retry**, and returning an accurate result to the caller.

### Overall Deadline Instead of Resetting the Timeout

If a workflow has three wait steps, each with a 5-second timeout, total time can approach 15 seconds, violating a 5-second request deadline. Compute the **remaining budget** from a monotonic clock (**System.nanoTime()**) before each wait step. Do not use mutable wall-clock time to measure elapsed duration.

## 21. Never Hold a Lock While Waiting for a Signal Produced by Someone Who Needs That Lock

This is a true deadlock:

~~~text
Thread A:
  synchronized(lock L) {
      latch.await();
  }

Thread B:
  synchronized(lock L) {
      prepareData();
      latch.countDown();
  }
~~~

`A` holds `L` while waiting for the latch; `B` must acquire `L` before it can call `countDown`. We have a dependency cycle:

~~~text
A holds L -> waits for latch
B needs L -> to call countDown
      ^             |
      +-------------+
~~~

**Changing await() to await(timeout)** gives `A` an escape hatch after the deadline, but it does not make the design right. Whenever possible, **move await outside the critical section**; upon re-acquiring the lock, re-check state because it may have changed. With `Condition.await()`, `await` itself releases the **lock associated with that Condition** while waiting, but it does not release any other locks the thread may be holding.

### “Waiting While Holding a Lock” Also Happens with Future

A task holding a lock and calling `Future.get()` to wait for a subtask that needs that same lock creates the exact same cycle. You must inspect the **dependency graph**, not just `arrive`/`countDown`/`release` calls.

## 22. Thread Pool Starvation: Not Enough Workers to Emit the Signal

Another source of liveness stalls:

~~~text
Single-thread executor:
  Task A is running on the only worker.
    A submits Task B to the same executor.
    A calls futureB.get() or latch.await() waiting for B.
  Task B sits in the queue with no free worker.

=> A waits for B, B waits for the worker that A is occupying.
~~~

This is a **thread-starvation deadlock**. Increasing the pool size to 2 might let the example run under light load, but a 2-worker pool can still be occupied by 2 parent tasks each waiting for 2 subtasks. **Changing the worker count does not fix circular dependency principles.**

Solutions:

- Do not block waiting for a task **that can only run on a resource you yourself are holding**.
- Use asynchronous composition, workflow state machines, or a fork/join mechanism with the proper contract where appropriate.
- Separate resource pools if the dependency is valid and controlled.
- Bound the backlog, monitor active workers and queue age.
- Do not confuse **executor accepted the task** with **task has been executed**.

## 23. Dynamic Participants and Unstarted Tasks

For example, a `Phaser` with `N` workers must handle these cases:

1. Coordinator registers a participant.
2. Creates or submits the task.
3. Submission may **be rejected**, `Thread.start` may fail, or cancellation may happen before start.
4. If a participant is registered but no worker will ever arrive, **the phase stalls**.

A safe design keeps **register/start/rollback** within the same protocol. A simple example:

~~~text
register party
try:
    submit work (work has finally -> arriveAndDeregister)
catch rejection:
    arriveAndDeregister the exact party just registered
    report workflow failure, do not pretend the step succeeded
~~~

This is pseudocode for a protocol where the new party **has not yet arrived in the current phase**. If the worker has already started or could run concurrently with the cancellation path, the coordinator and worker must not **both deregister the same party twice**. You need an ownership/once-token mechanism for the completion obligation.

### Race Between cancel and start

A task can be cancelled just as the worker starts; the coordinator does not know whether the worker has reached `finally` yet. Do not rely on a plain boolean to decide who releases/deregisters, because check-then-act also has a race. You can use **AtomicBoolean.compareAndSet(false,true)** for *once completion* of an obligation, or a task lifecycle structure with explicit states and ownership.

**Once-completion differs from “signal success”**: even when completion is reported exactly once inside the JVM, the business outcome can still be `FAILED` or `CANCELLED`, and process crashes are not handled by `AtomicBoolean`.

## 24. Idempotency and Signal Responsibility

**CountDownLatch.countDown()** after `count=0` does not make the count negative. That does not mean over-calling `countDown` is protocol-safe: if the initial count is `N` and one worker calls `countDown` twice, the latch can reach 0 **before another worker finishes**.

**Semaphore.release()** can raise permits beyond the designed limit when over-called. It does not automatically bind ownership to a thread.

**Phaser.arrive()** carries phase/party responsibility; over-calling or wrong deregistration can break coordination.

**CyclicBarrier.await()** is an obligation to reach the rendezvous **once per generation**; one thread cannot call `await` twice in a row to substitute for a missing party, because it will block on the first call.

### Obligation Ledger

Useful during code review:

| Primitive | Obligation | Valid Release Condition |
| --- | --- | --- |
| `CountDownLatch` | One count per worker/stage | Worker has met the definition of completion |
| `CyclicBarrier` | One `await` per party per generation | Party actually reaches that generation's barrier |
| `Phaser` | One arrival per party per phase | Party arrives validly; deregisters upon leaving |
| `Semaphore` | One acquired permit | Owner returns the exact permit count per protocol |

In code, clearly document **who owns each obligation**, who is allowed to signal on its behalf, and when failure states must be published.

## 25. Metrics, Diagnostics, and Thread Dumps

When an application hangs:

1. Identify the primitive type and the missing **waiting unit**.
2. For `CountDownLatch`, log **getCount()** and the list of expected tasks; do not just see `getCount()>0` and guess which worker failed.
3. For `CyclicBarrier`, inspect **getNumberWaiting()**, **isBroken()**, party count, and protocol-level generation.
4. For `Phaser`, inspect **getPhase()**, **getRegisteredParties()**, **getUnarrivedParties()**; these are mutable snapshots.
5. For `Semaphore`, inspect **availablePermits()**, estimated queue length, and permits acquired per task; never use queue length for correctness logic.
6. Capture a **thread dump** to see threads waiting on synchronizers, locks, `Future`s, or executor queues.
7. Check **exception logs**, task rejections, cancellations, timeouts, and interrupted flags.
8. Identify **which thread can still emit the signal** or whether a dependency cycle is closed.
9. Keep a correlation id for each obligation: registered, started, arrived/released/failed/cancelled.
10. Avoid instrumenting with a hot shared atomic counter on every high-throughput step if it creates significant contention; batch metrics when needed.

**A thread dump is only a snapshot**, while the root cause often lies in an earlier event: a thrown exception, a missed release, a rejected submit, or an underegistered phase participant.

### Testing Liveness Differs from Correctness

A test verifying **no hang** does not prove correct output. For instance, adding an unconditional `countDown` can make the test finish quickly while reading uninitialized data. Every liveness fix must preserve business invariants.

## 26. Testing Properly with Invariants

Instead of running 1000 times and hoping a race shows up, **control the schedule**:

- Use `CountDownLatch` to force a worker to reach a point before `main` proceeds to the next step.
- Use **await(timeout)** for failure paths so tests do not hang forever when a protocol has a bug.
- Use **join()** to ensure workers have finished before checking final state.
- Use `AtomicBoolean`/`AtomicInteger` for observed variables updated by multiple threads.
- To test an interrupted waiter, hold the permit/latch with one worker and then interrupt the waiter per protocol.
- For `CyclicBarrier` with a missing party, start only one party in a 2-party barrier and use timed `await` for a deterministic outcome.
- For `Phaser`, register an explicit number of parties, have every worker deregister in `finally`, and have the coordinator wait for the phase transition.
- For `Semaphore`, verify **availablePermits() returns to the initial level** and **peak concurrent tasks <= permits** after `join`.

**Do not assert** that two threads interleave in a specific random order; do not print thread names or timestamps assuming scheduler ordering. Tests should prove invariants rather than relying on “long enough” sleeps.

## 27. Anti-Patterns and Fixes

| Anti-pattern | Why it is wrong | Fix |
| --- | --- | --- |
| `countDown` only at the end of `try` | Exceptions/returns skip it | `finally` if the latch represents completion |
| `countDown` in `finally` without recording errors | Waiter may assume tasks succeeded | Separate result/error state |
| Initializing latch with count larger than actual obligations | Waiter may never pass | Audit obligations and handle rejected tasks |
| Calling `countDown` twice from one worker | Latch may open prematurely | Exactly-once completion protocol |
| `CyclicBarrier.await` without timeout when a party can die | Remaining waiters get stuck | Timed `await` + abort/recovery policy |
| Catching `BrokenBarrierException` and continuing business logic | Phase data may be incomplete | Treat generation as failed, coordinated restart |
| `Phaser` `register` then task is rejected | Party never arrives | Deregister with clear ownership |
| `Phaser` `awaitAdvance` when party has not arrived | Phase does not advance | Distinguish `arrive` from `awaitAdvance` |
| `Phaser` `arrive` twice in the same phase | Violates protocol | One owner/phase, avoid double arrival |
| `forceTermination` then assuming workers are cancelled | Workers may still be running | Cooperative cancellation and cleanup |
| `Semaphore.acquire` then `release` outside `finally` | Exceptions cause permit leaks | Release exact permit count in `finally` |
| `release` in `finally` even when `acquire` failed | Over-release, breaks limit | `acquired` flag or `try` right after `acquire` |
| Releasing wrong number of permits | Leak or over-release | Acquire/release matching counts |
| Holding a lock while awaiting a signal from someone who needs the lock | Circular deadlock | Break dependency; wait outside critical section |
| Task in a single worker waits on a subtask in the same pool | Thread-starvation deadlock | Composition / avoid blocking on same worker |
| Timeout then returning success | Hides completion failure | Failure/cancel/partial-state per contract |
| Using `sleep` to fix a missing signal | Does not create the required event | Fix protocol and happens-before |
| Swallowing `InterruptedException` and continuing | Fails to respond to cancellation | Propagate or restore interrupt and exit appropriately |

## 28. Protocol Review Checklist

**CountDownLatch**

- [ ] Does the count match the actual number of completion obligations?
- [ ] Does each obligation call `countDown` only once?
- [ ] Are exception, return, interrupt, and task rejection paths handled?
- [ ] Does the latch mean “done” or “success”? Is there a separate result/error channel?
- [ ] Does the waiter have a deadline and an appropriate timeout branch?

**CyclicBarrier / Phaser**

- [ ] Is the party count for each phase/generation accurate?
- [ ] Does every party have a valid `arrive`/`await` point?
- [ ] Do parties leaving the workflow deregister or abort per policy?
- [ ] Are there no registered parties left orphaned without a worker?
- [ ] Are there no double `arrive`/`deregister` calls?
- [ ] Are broken barrier, timeout, and interruption handled?
- [ ] If a phase fails, does downstream know and stop appropriately?

**Semaphore**

- [ ] Did `acquire` actually succeed before calling `release`?
- [ ] Does `release` return the exact number of permits acquired?
- [ ] Is the entire critical section protected by `try/finally`?
- [ ] Are there no early-return paths that skip `release`?
- [ ] Is there no over-release breaking the concurrency limit?
- [ ] Is there a timeout or cancellation path when resources are unavailable?

**System-wide**

- [ ] Are you avoiding blocking while holding locks or workers needed by the signal producer?
- [ ] Is there telemetry for registered, completed, and failed obligations?
- [ ] Are you avoiding assuming timeout/cancel automatically rolls back I/O/DB?
- [ ] Have both failure and success paths been tested, not just the happy path?
- [ ] Is there a business invariant proving it is safe to proceed?

## 29. Self-Check

**1. Why can CountDownLatch hang when a worker throws an exception?**  
Because `countDown` is not called if placed at the end of `try`; the latch does not know the `Thread` died. A completion protocol with `finally` or an appropriate failure channel is required.

**2. Is putting countDown in finally always right?**  
Only when `countDown` represents “finished”. If it represents “succeeded”, you must separate status and ensure downstream does not misinterpret it.

**3. Does CountDownLatch.await(20ms) returning false decrement the counter?**  
No. The count remains unchanged; the timeout is only an escape hatch for the waiter.

**4. CyclicBarrier needs 3 parties, but only 2 reach await; what happens without timeout/interrupt?**  
The two parties may wait indefinitely if the third party never arrives.

**5. What happens to the barrier when a timed await in CyclicBarrier times out?**  
The barrier becomes broken; other waiters may receive `BrokenBarrierException`. Coordinated failure/recovery handling is required.

**6. Does Phaser.awaitAdvance(phase) automatically count the caller as having arrived?**  
No. The caller must fulfill its arrival obligation using the appropriate API; `awaitAdvance` only waits for the phase to change.

**7. A party is registered and never starts; does Phaser automatically remove it?**  
No. The coordinator must handle registrations without workers, or abort the entire workflow.

**8. When a worker participates in only one phase and then leaves, which API is appropriate?**  
`arriveAndDeregister()` per protocol, typically in `finally` if signaling completion on error paths as well, combined with separate error reporting.

**9. Does Phaser.forceTermination() stop all currently executing workers?**  
No. It transitions the phaser to the terminated state; workers must cooperate with cancellation and cleanup themselves.

**10. Semaphore.acquire throws InterruptedException before obtaining a permit; should release be called?**  
No. Releasing without acquiring increases permits erroneously. Release only if `acquire` succeeded.

**11. If Semaphore(2) has release called three times but acquire only twice, what is wrong?**  
It can raise permits above 2, breaking the designed concurrency limit.

**12. Why can lock + latch.await create a circular deadlock?**  
If the thread emitting `countDown` needs the lock held by the waiter, the two depend on each other.

**13. What happens if a single-thread executor task submits a child task to the same executor and calls get?**  
The worker waits for the child while the child waits for a free worker; this can cause a thread-starvation deadlock.

**14. Why is a timeout alone not enough to prove liveness is fixed?**  
It only stops the caller's wait; the arrival/`countDown`/permit obligation is still broken and business state may be incomplete.

**15. Do getCount/getUnarrivedParties/availablePermits prove correctness?**  
They aid diagnostics; you must analyze obligations/ownership, exception paths, and invariants rather than looking only at snapshots.

## 30. Summary

Missing a single call to **countDown(), arrive()/arriveAndDeregister(), or release()** can prevent other threads from **ever making progress**. Yet over-calling or signaling with the wrong semantics is equally dangerous: a latch can open too early, a phaser can violate its phase protocol, and a semaphore can lose its resource limit.

How to design reliably:

1. Explicitly document the **obligation** of each participant/task/permit and who owns it.
2. Structure code with **try/finally** to clean up and signal completion according to the contract.
3. **Never emit fake success signals**; propagate failures/results through a separate channel.
4. **Never release if acquire did not succeed**; avoid double-arrive and double-countDown.
5. Use **timeout + failure propagation + cancellation** for a controlled escape hatch when the other side cannot proceed.
6. Inspect the dependency graph so you do not hold locks or workers needed by the signal producer.
7. Test **exception, interrupt, rejection, and shutdown** paths with deterministic synchronization, then verify business invariants.

The core goal is not merely “to stop threads from waiting”, but to ensure **every completion event is signaled exactly once, with the right meaning, by the right owner, and all threads proceed on a valid state**.

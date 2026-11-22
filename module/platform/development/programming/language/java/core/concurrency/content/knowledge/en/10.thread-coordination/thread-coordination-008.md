# LockSupport.park()/unpark() and Permits in Java

`java.util.concurrent.locks.LockSupport` provides **park** operations for a thread to pause itself, and **unpark** for another thread to grant permission for the target thread to continue. It is a **low-level wait/wakeup primitive**, commonly used underneath other synchronization constructs in Java—not a queue, mutex, or work counter.

The core concept is the **permit**: each thread has at most **one** permit. `LockSupport.unpark(thread)` makes the target thread's permit available; `LockSupport.park()` on that thread can consume the permit and return. Because permits do not accumulate, multiple unparks before a park **do not** create multiple permits for subsequent parks to proceed. `park` can also return when interrupted or due to a *spurious return*, so correct code requires **an independent predicate, a recheck loop, and proper memory visibility**.

This lesson applies to Java concurrency in general and does not depend on any specific framework.

## 1. The One-Bit Permit Model

Think of a thread's permit as a logical state of 0 or 1:

| Event | Permit | Meaning |
| --- | --- | --- |
| Thread initialized, no signal received yet | 0 | No permit waiting |
| Another thread calls `unpark(T)` | 1 | T is granted permission for one park |
| Another thread calls `unpark(T)` again | Still 1 | Does not accumulate to 2 |
| T calls `park()` when permit is available | 0 after consumption | The call may return immediately |
| T calls `park()` when no permit is available | May wait | Waits for unpark, interrupt, or return for another reason allowed by the API |

This model is for **reasoning about behavior**, not a `boolean` field readable from the API. There is no `LockSupport.hasPermit()` or "get permit count" operation; a permit cannot be used in place of a job queue.

A few execution schedules:

```text
A: unpark(B)            -> permit(B) is available
B: park()               -> consumes permit, returns

A: unpark(B)
A: unpark(B)            -> still only one permit
B: park()               -> consumes one permit
B: park()               -> may have to wait for a new signal

B: park()               -> may pause
A: unpark(B)            -> B may be woken up
```

This does not mean the second `park` **must wait forever**: `park` can return due to an interrupt or spurious return. The important point is not to rely on the second `unpark` as a separate accumulated permit.

## 2. `unpark` Can Happen Before `park`

With `Object.notify()`, if the code violates the protocol and the notification happens before the thread enters the wait set, that notification is not automatically remembered as a "wait ticket". `LockSupport` has a permit mechanism, allowing a thread to be unparked first and then parked later.

```text
Main thread                         Worker thread
--------------------------------    ------------------------------
Worker has started                  has not called park() yet
unpark(worker)                      permit = 1
                                    park() consumes permit
                                    continues execution
```

**However, there are two important limitations to remember.** First, a permit **is not guaranteed to be preserved across an intervening `Thread.start()`**; do not rely on unparking an unstarted thread. Second, **an intermediate park call** from library code may consume the permit before your code reaches its intended `park`. Therefore, do not store a permit as a token guaranteed to survive across arbitrary blocking calls.

### Java 17 Example: Granting a Permit Before the Worker Calls Park

Create the file `PreUnparkExample.java`:

```java
import java.util.concurrent.TimeUnit;
import java.util.concurrent.atomic.AtomicBoolean;
import java.util.concurrent.locks.LockSupport;

public class PreUnparkExample {
    public static void main(String[] args) throws InterruptedException {
        AtomicBoolean started = new AtomicBoolean(false);
        AtomicBoolean proceed = new AtomicBoolean(false);
        AtomicBoolean returned = new AtomicBoolean(false);

        Thread worker = new Thread(() -> {
            started.set(true);
            while (!proceed.get()) {
                Thread.onSpinWait();
            }
            LockSupport.park();
            returned.set(true);
        }, "worker");

        worker.start();
        long deadline =
                System.nanoTime() + TimeUnit.SECONDS.toNanos(5);

        while (!started.get()) {
            if (System.nanoTime() >= deadline) {
                worker.interrupt();
                throw new IllegalStateException("Worker not started");
            }
            Thread.onSpinWait();
        }

        LockSupport.unpark(worker);
        proceed.set(true);

        worker.join(5_000);
        if (worker.isAlive()) {
            worker.interrupt();
            throw new IllegalStateException("Worker still parked");
        }
        System.out.println("parkReturned=" + returned.get());
    }
}
```

```bash
javac PreUnparkExample.java
java PreUnparkExample
```

Stdout on normal completion:

```text
parkReturned=true
```

**Explanation:** the worker started and signaled `started` before main called unpark. While waiting for `proceed`, the worker only spins, **without using another parking primitive** that could consume the permit. Main grants the permit and then opens the gate. The worker calls `park` with the permit already available, so no new unpark is needed. `join` ensures main prints after the worker finishes.

Busy-spinning here is **only to create an illustrative checkpoint** and has a deadline; it is not a recommended waiting pattern in production. A single run printing the line above also does not prove that `park` never spuriously returns; the permit contract is the basis for understanding it.

## 3. Why `unpark` Does Not Count Jobs

Suppose a producer creates 100 tasks and calls `unpark(consumer)` 100 times; if the consumer has not called `park` yet, those unparks only create **one permit**. A consumer written as "park 100 times, processing one job each time" can get stuck after the first iteration.

```java
// Incorrect business-logic expression:
for (int i = 0; i < 100; i++) {
    LockSupport.unpark(consumer);
}

// On the consumer side, also wrong if treating one park = one job:
for (int i = 0; i < 100; i++) {
    LockSupport.park();
    processOneJob();
}
```

This is a **snippet illustrating a flawed design**; `consumer` and `processOneJob` are not defined. A permit is not a queue and holds no payload. A proper design must store work in a **thread-safe queue**, or use a `BlockingQueue` which already provides `put/take`. When N resource-access permits are needed, use `Semaphore`: a semaphore's permits are counted under a completely different contract from LockSupport's one-bit permit.

## 4. `park` Can Return Without Being Unparked

Besides unpark, `park` can return due to an **interrupt** or a **spurious return**. With timed overloads, it can also return due to timeout. Therefore, the following snippet:

```java
LockSupport.park();
processJob();
```

is wrong if `processJob` should only execute when an actual business condition has occurred.

An independent predicate is required:

```java
while (!ready.get()) {
    LockSupport.park();
    if (Thread.currentThread().isInterrupted()) {
        return;
    }
}
processJob();
```

This is a snippet inside a `void` method, where `ready` is an `AtomicBoolean` and `processJob()` is the business logic. If `park` wakes up early while `ready=false`, the thread waits again. If interrupted, it exits according to the example's cancellation policy.

**Important:** `LockSupport.park()` does not throw `InterruptedException` and does not clear the interrupt flag. When the interrupt flag is set, `park` can repeatedly return immediately; if the loop only checks a false predicate without handling interruption, the worker can **hot-spin and consume CPU**.

## 5. Java 17: Coordinating with a Predicate and a Permit

The producer must **publish state**, then **unpark the right thread**. The consumer waits on the predicate rather than trusting that `park` returning automatically means "data is available".

Create `ParkPredicateExample.java`:

```java
import java.util.concurrent.CountDownLatch;
import java.util.concurrent.TimeUnit;
import java.util.concurrent.atomic.AtomicBoolean;
import java.util.concurrent.atomic.AtomicInteger;
import java.util.concurrent.locks.LockSupport;

public class ParkPredicateExample {
    public static void main(String[] args) throws Exception {
        AtomicBoolean ready = new AtomicBoolean(false);
        AtomicInteger received = new AtomicInteger(-1);
        CountDownLatch started = new CountDownLatch(1);
        int[] payload = {0};

        Thread consumer = new Thread(() -> {
            started.countDown();

            while (!ready.get()) {
                LockSupport.park("waiting-for-payload");
                if (Thread.currentThread().isInterrupted()) {
                    return;
                }
            }
            received.set(payload[0]);
        }, "consumer");

        consumer.start();

        if (!started.await(5, TimeUnit.SECONDS)) {
            throw new IllegalStateException("Consumer not started");
        }

        payload[0] = 42;
        ready.set(true);
        LockSupport.unpark(consumer);

        consumer.join(5_000);
        if (consumer.isAlive()) {
            consumer.interrupt();
            throw new IllegalStateException("Consumer did not finish");
        }
        System.out.println("received=" + received.get());
    }
}
```

```bash
javac ParkPredicateExample.java
java ParkPredicateExample
```

Stdout on normal completion:

```text
received=42
```

**Why is this correct?** The producer writes `payload[0]=42`, then `ready.set(true)`. The consumer only reads the payload after `ready.get()` observes `true`. The atomic/volatile operations on `ready` provide the memory-consistency semantics needed to publish the payload. `unpark` only gives a parked worker a chance to run and **recheck the flag**; the permit itself does not make a mutable object thread-safe.

Consider three schedules:

- Consumer parks first → producer unparks → consumer wakes up and sees the flag is true.
- Producer publishes before consumer reads the flag → consumer sees true and skips park.
- Consumer reads false, producer publishes/unparks, then consumer parks → the granted permit lets park proceed, consumer rechecks and sees true.

If `park` spuriously returns while the flag is still false, the loop continues waiting. If the consumer is interrupted before seeing the flag, the code exits per the example's policy.

**Note:** the string argument of `park(blocker)` is only **debugging metadata**, not a lock, payload, or object to unpark. `unpark` still takes the target `Thread` itself.

## 6. `park` Does Not Release Monitors

Unlike `Object.wait()` and `Condition.await()`, `LockSupport.park()` **does not release a monitor or `ReentrantLock` held by the caller**.

An example prone to deadlock:

```java
synchronized (lock) {
    while (!ready) {
        LockSupport.park();
    }
}
```

This snippet assumes the producer also needs `synchronized(lock)` to set `ready=true`. The worker is parked while **still owning the `lock` monitor**, so the producer becomes `BLOCKED` and cannot update state to let the worker proceed.

The appropriate pattern with an intrinsic monitor is:

```java
synchronized (lock) {
    while (!ready) {
        lock.wait();
    }
}
```

This snippet is inside a method with `throws InterruptedException`. `Object.wait()` releases the monitor of the object on which `wait` is called, then reacquires the monitor before returning. The producer updates the predicate and calls `lock.notifyAll()` under the same monitor.

With `ReentrantLock` and `Condition`:

```java
lock.lock();
try {
    while (!ready) {
        condition.await();
    }
} finally {
    lock.unlock();
}
```

This snippet is inside a method declaring `throws InterruptedException`; `condition` is created via `lock.newCondition()`. `await()` releases the associated lock while waiting and reacquires it before returning. **Do not replace `await` with `park` inside a critical section** expecting it to release the lock as well.

## 7. Java 17: Interrupt Wakes `park` Without Throwing an Exception

Create the file `ParkInterruptExample.java`:

```java
import java.util.concurrent.CountDownLatch;
import java.util.concurrent.TimeUnit;
import java.util.concurrent.atomic.AtomicBoolean;
import java.util.concurrent.locks.LockSupport;

public class ParkInterruptExample {
    public static void main(String[] args) throws Exception {
        CountDownLatch started = new CountDownLatch(1);
        AtomicBoolean sawInterrupt = new AtomicBoolean(false);

        Thread worker = new Thread(() -> {
            started.countDown();
            while (!Thread.currentThread().isInterrupted()) {
                LockSupport.park();
            }
            sawInterrupt.set(true);
        }, "worker");

        worker.start();
        if (!started.await(5, TimeUnit.SECONDS)) {
            throw new IllegalStateException("Worker not started");
        }

        worker.interrupt();
        worker.join(5_000);
        if (worker.isAlive()) {
            throw new IllegalStateException("Worker did not stop");
        }

        System.out.println("interruptObserved=" + sawInterrupt.get());
    }
}
```

```bash
javac ParkInterruptExample.java
java ParkInterruptExample
```

Stdout on normal completion:

```text
interruptObserved=true
```

If main interrupts **before** the worker calls park, the flag is already set and the loop can exit immediately. If the interrupt happens **while** the worker is parked, park returns and the loop condition sees the flag is true. If park wakes up early on its own, the condition is still false and the worker waits again. The outcome does not depend on the exact point the scheduler chooses.

`Thread.currentThread().isInterrupted()` only reads the flag; `Thread.interrupted()` reads **and clears** the current thread's flag. Do not accidentally use the second method and cause outer calling code to miss the cancellation request.

## 8. `parkNanos`, `parkUntil`, and Wait Deadlines

The overloads:

| API | Meaning |
| --- | --- |
| `LockSupport.park()` | Wait with no specified deadline |
| `LockSupport.park(Object blocker)` | Wait and attach a blocker for diagnostics |
| `LockSupport.parkNanos(long nanos)` | Wait for a **positive relative** duration |
| `LockSupport.parkNanos(Object blocker, long nanos)` | Same, with a blocker |
| `LockSupport.parkUntil(long deadline)` | Wait until an **absolute epoch milliseconds** timestamp |
| `LockSupport.parkUntil(Object blocker, long deadline)` | Same, with a blocker |
| `LockSupport.unpark(Thread t)` | Grant a permit to t, which may cause a waiting park to return |

**`parkNanos(0)` is not like `Object.wait(0)`.** For `parkNanos`, a non-positive duration does not produce a useful park interval; `Object.wait(0)` means wait indefinitely.

If you want a 200 ms duration-based timeout, use monotonic `System.nanoTime()` and compute remaining time after each wakeup:

```java
long deadline =
        System.nanoTime() + TimeUnit.MILLISECONDS.toNanos(200);

while (!ready.get()) {
    long remaining = deadline - System.nanoTime();
    if (remaining <= 0) {
        return false;
    }
    LockSupport.parkNanos(remaining);
    if (Thread.currentThread().isInterrupted()) {
        return false;
    }
}
return true;
```

This snippet is in a `boolean` method with `ready` as an `AtomicBoolean`, requiring `TimeUnit` and `LockSupport` imports. `parkNanos` can return **before** the timeout due to unpark, interrupt, or spurious return; you must check both the predicate and the remaining time on each iteration. The scheduler does not guarantee running the thread **at the exact** timeout instant. For very large timeouts, consider overflow of `nanoTime() + timeout`.

`parkUntil(deadline)` uses epoch milliseconds (typically computed from `System.currentTimeMillis()`), not a nanosecond duration. Because it uses calendar clock time, wall-clock adjustments can affect waiting; when measuring relative durations, `parkNanos` and `nanoTime` are usually easier to reason about.

## 9. `park(blocker)` and `getBlocker` Are Only for Observation

Example:

```java
LockSupport.park(waitQueue);
Object blocker = LockSupport.getBlocker(worker);
```

This is a snippet where `waitQueue` is an object describing the reason for waiting, and `worker` is the target thread. `blocker` **is not a locked monitor**, holds no permit, and is not the argument passed to `unpark`. It helps JFR/thread dumps and debuggers understand what the worker is waiting on.

`getBlocker(worker)` can return the blocker object while the worker is parked via a blocker overload, or `null` if the worker is no longer parked, just changed state, or parked without a blocker. **Do not use `getBlocker` as a synchronization signal**, because it is only a snapshot and is racy.

A thread waiting inside `LockSupport.park()` typically has Java thread state `WAITING (parking)`; a timed park may show `TIMED_WAITING`. Do not conclude there is a deadlock from seeing `WAITING` once: an idle thread-pool worker parked is normal. Read the stack trace, blocker, predicate, and signal source.

## 10. Comparison with Other Java Primitives

| Mechanism | Associated With | Releases Lock While Waiting? | Counts Multiple Items/Permits? |
| --- | --- | --- | --- |
| `park/unpark` | **Thread's** one-bit permit | **No** | No |
| `Object.wait/notifyAll` | Object monitor's wait set | Releases the monitor on which `wait` is called | Does not queue jobs |
| `Condition.await/signalAll` | Condition bound to a `Lock` | Releases associated lock, reacquires later | Does not queue jobs |
| `Thread.sleep` | Time duration | No | No |
| `Thread.join` | Another thread's lifecycle | Does not automatically release caller's monitors | No |
| `CountDownLatch` | One-way counter | Does not release arbitrary monitors | Has counter down to 0 |
| `Semaphore` | Resource access permits | Does not release arbitrary monitors | **Yes**, counted permits |
| `BlockingQueue` | Queue holding payloads | Manages synchronization internally | **Yes**, elements |

**Prefer higher-level abstractions**: to pass multiple work items, use `BlockingQueue`; to limit to N concurrent tasks, use `Semaphore`; to wait for N events to complete, use `CountDownLatch`; to wait on a predicate under a mutex, use `Condition` or `wait`. `LockSupport` is appropriate when building a low-level synchronizer with its own state and waiter queue.

Implementations based on `AbstractQueuedSynchronizer` may use `park/unpark` internally to park workers, but they also need atomic state, a waiter queue, cancellation, interruption, and memory semantics. **You cannot just replace a `synchronized` block with a `park` call to build a mutex**.

## 11. Race Between Checking the Predicate and Parking

Suppose the consumer executes:

```java
while (!hasWork.get()) {
    LockSupport.park();
}
```

And the producer executes:

```java
hasWork.set(true);
LockSupport.unpark(worker);
```

These are two snippets where `hasWork` is an `AtomicBoolean`; `worker` has started and there are no unexpected intermediate `park` calls.

- Producer sets true before consumer reads → consumer does not park.
- Consumer reads false, producer sets true/unparks, then consumer parks → the early permit lets it return and recheck true.
- Consumer parks first → producer unparks, consumer wakes and reads true.
- Consumer has a spurious return → if false, it parks again.
- Consumer is interrupted → must handle interruption, otherwise the loop may spin because `park` returns immediately.

A **leftover** permit when the consumer sees true without needing to park can cause a later `park` call to return immediately once. This is not an extra job. A correct algorithm always trusts the **predicate** rather than the number of wakeups.

**Do not treat a boolean flag as a multi-item queue.** If multiple producers/consumers concurrently modify the job count, you need a queue/counter with proper atomicity, not just a flag and a permit.

## 12. Memory Ordering: A Permit Does Not Replace the Java Memory Model

A correct program needs two layers:

1. **Safely published state:** use `volatile`, atomics, `synchronized`, locks, or concurrent collection operations with JDK-specified memory consistency.
2. **Wakeup mechanism:** call `unpark` on the right thread that may be waiting so it rechecks the state.

Example:

```java
// Producer:
payload = 42;
ready.set(true);
LockSupport.unpark(consumer);

// Consumer:
while (!ready.get()) {
    LockSupport.park();
}
consume(payload);
```

This is a snippet with `ready` as an `AtomicBoolean`. Writing `payload` before `ready.set(true)` and reading `ready.get() == true` before using `payload` establishes the necessary happens-before relationship. Having only `unpark` without a visibility protocol for mutable state does not make all reads and writes safe.

If `payload` continues to be modified after `ready` becomes true, publishing once **does not** make subsequent modifications safe. You need an immutable snapshot, a queue, a lock, or atomic updates matching the invariant's scope.

## 13. Java 21+ Virtual Threads and `LockSupport`

Virtual threads still must obey the Java Memory Model. `park/unpark` retains its meaning for waiting/waking a virtual thread, while the runtime may manage mounting/unmounting on carrier threads differently from how a platform thread blocks in the OS. Pinning and diagnostics details depend on the JDK version; **do not assume every parked virtual thread corresponds to a blocked OS thread**.

Whether virtual or platform threads, the principles remain unchanged: a predicate with visibility, handling spurious returns/interrupts, not holding a lock needed by the producer while parking, and measuring on the target runtime. The programs in this lesson use Java 17 and do not require virtual-thread APIs.

## 14. Common Mistakes

| Mistake | Consequence | Fix |
| --- | --- | --- |
| Calling `unpark` N times to record N jobs | Permits do not accumulate | Queue/counter to store jobs |
| Doing work immediately when `park` returns | Spurious return/interrupt | `while` loop checking predicate |
| Using a plain field as an unsynchronized predicate | Missing visibility | `volatile`/atomic/lock |
| Parking while holding a monitor needed by the producer | Deadlock | `wait`/`Condition.await` or release lock |
| Assuming `park` releases `ReentrantLock` | Lock remains held | Wait outside critical section |
| Unparking an unstarted thread | Permit not guaranteed across start | Start before signaling |
| Holding a permit across other blocking APIs | Intermediate `park` may consume it | Rely on predicate |
| Ignoring interrupts | Wait loop may hot-spin | Handle cancellation |
| Using `Thread.interrupted()` when only checking the flag | Accidentally clears flag | `isInterrupted()` |
| Treating `parkNanos(0)` like `Object.wait(0)` | Different zero convention | Use `park()` when no timeout |
| Passing a duration to `parkUntil` | Wrong unit/meaning | Absolute epoch milliseconds |
| Using `getBlocker` as a decision condition | Unstable snapshot | Real synchronization primitive |
| Using `park/unpark` as a mutex | No mutual exclusion | `synchronized`/`Lock`/atomic |
| Using `Thread.sleep` to force interleaving | Non-deterministic scheduling | Latch/barrier |
| Seeing `WAITING` and concluding deadlock | Idle workers can be parked | Inspect stack, blocker, and predicate |

## 15. Debugging a Long-Parked Thread: Checklist

1. **Which predicate is it waiting on?** Waiting for a job, a lock, a result, or shutdown?
2. **Who changes the predicate?** Does producer code definitely update the right state before signaling?
3. **Who calls `unpark`?** Is it targeting the right `Thread` instance, already started and still alive?
4. **Is there an intermediate `park`?** Was an early permit consumed by a `park` call inside another library?
5. **Does the predicate have visibility?** Are atomic/volatile or lock/happens-before semantics correct?
6. **Is the thread holding a lock?** Is a parked worker holding a monitor/`Lock` needed by the producer?
7. **Interrupt flag?** If set, `park` returns immediately causing high CPU; if code swallows interrupts, shutdown is hard.
8. **Timed wait?** Are time units and deadline calculated correctly? Is remaining time recomputed after each return?
9. **Diagnostics?** Check `getBlocker`, JFR/thread dumps, multiple snapshots, and application state.
10. **Coordination tests?** Test unpark-before-park, park-before-unpark, interrupts, and simulated spurious returns with the predicate loop.
11. **Can a higher-level JDK primitive be used?** Avoid writing a custom synchronizer unless truly necessary.

## 16. Self-Check Questions

**1. Call `unpark(T)` three times, then `T.park()` three times—are all three guaranteed to proceed immediately?** No. At most one permit exists. Later `park` calls may wait (though they may return spuriously).

**2. Is unparking before parking always safe?** A permit can be granted before parking, but you must ensure the thread has started, no intermediate `park` consumes it, and the predicate is synchronized.

**3. If `park` returns, is there guaranteed to be a job?** No. It could be due to a permit, an interrupt, or a spurious return. Use a real predicate.

**4. Does `park` release monitors?** No. Only `Object.wait`/`Condition.await` release the associated lock per their API.

**5. Does `park` throw `InterruptedException`?** No. It can return with the interrupt flag still set.

**6. Is `parkNanos(0)` the same as `Object.wait(0)`?** No. `parkNanos` does not wait usefully for non-positive durations; `Object.wait(0)` waits indefinitely.

**7. Is the blocker in `park(blocker)` the object to unpark?** No. `unpark` takes a `Thread`; the blocker is only for diagnostics.

**8. How does a `Semaphore` permit differ from a `LockSupport` permit?** A `Semaphore` counts resource permits; `LockSupport` only has a one-bit permit per thread for parking.

**9. Can `LockSupport` be used to protect `count++`?** No. It does not provide mutual exclusion or atomic read-modify-write.

**10. If a worker is interrupted and the loop only says `while (!ready) park()`, can it burn CPU?** Yes. Because `park` can return immediately while the interrupt flag is set.

**11. Why is an atomic/volatile flag needed before `unpark`?** To publish data/conditions under the Java Memory Model; the permit is only a wakeup.

**12. Why is `BlockingQueue` easier to use than combining an `ArrayList` and permits yourself?** It provides item storage, thread coordination, and memory consistency in a single contract, avoiding lost work and races on the collection.

## 17. Summary for Application

**A `LockSupport` permit is not a job, mutex, or quota.** It is **at most one unconsumed wait/wakeup permission for a thread**. An `unpark` arriving before `park` still takes effect per contract, but multiple permits do not accumulate and a permit can be consumed by an intermediate `park`. `park` does not release held locks, does not throw `InterruptedException`, and can return spuriously.

To use it correctly, you need a **safely published predicate**, a `while` loop rechecking the condition after `park`, a clear interrupt/timeout policy, and a data structure that actually holds business state. Whenever possible, prefer `BlockingQueue`, `Semaphore`, `CountDownLatch`, or `Condition`; use `LockSupport` directly only when designing a low-level synchronizer.

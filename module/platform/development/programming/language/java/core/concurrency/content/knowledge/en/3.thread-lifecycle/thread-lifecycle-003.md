# Thread State Transitions When Entering a Monitor or Waiting on a Lock in Java

> **Context:** `Thread` lifecycle and thread states when contending for a monitor or waiting on a lock. This lesson focuses on **Java SE/JVM** mechanisms, including `synchronized`, `Object.wait/notify`, `ReentrantLock`, `Condition`, and `LockSupport`; it does not cover Spring-specific concurrency.

## 1. Learning Objectives

After this lesson, you will be able to:

- Accurately explain when a Java thread typically transitions between `RUNNABLE`, `BLOCKED`, `WAITING`, and `TIMED_WAITING`.
- Distinguish between **waiting to acquire an intrinsic monitor**, **waiting on a condition on a monitor**, and **waiting on an explicit lock** such as `ReentrantLock`.
- Explain why `notify()`, `notifyAll()`, or `signal()` **does not mean** the awakened thread can immediately run through the critical section.
- Write proper condition-waiting structures, handle `InterruptedException`, release locks, and avoid lost notifications.
- Read thread dumps/JFR based on the synchronization mechanism in use, rather than inferring causes from a single `Thread.State` label alone.

Key point: **`BLOCKED` is a specific `Thread.State` for waiting on an *intrinsic monitor*; not every thread "blocked" by a lock has the `BLOCKED` state.**

## 2. What Does Thread.State Represent?

`Thread.getState()` returns one of Java's six states. This is the state observed at the moment of sampling, **not** a complete diagram of all internal OS scheduling states, nor does it describe every reason a task has not completed.

| State | Notable definition | Relation to monitor/lock |
|---|---|---|
| `NEW` | Thread has been created but `start()` has not been called yet. | Not contending for locks yet. |
| `RUNNABLE` | Running or ready to run in the JVM; may still be waiting for the OS to allocate CPU time. | The thread may be inside a critical section or about to call lock. |
| `BLOCKED` | Waiting to enter or **re-enter** an intrinsic monitor. | Commonly seen with `synchronized` and when `Object.wait()` has been notified but has not reacquired the monitor yet. |
| `WAITING` | Waiting for an action from another thread, without a specified timeout. | `Object.wait()` without timeout, `Condition.await()`, `LockSupport.park()`, and some paths of `ReentrantLock.lock()`. |
| `TIMED_WAITING` | Waiting for a specified duration. | `Object.wait(timeout)`, `Condition.awaitNanos()`, `LockSupport.parkNanos()`; `Thread.sleep()` is also here. |
| `TERMINATED` | The `run()` method has finished. | No longer contending for locks. |

Some notes to avoid misreading:

- `RUNNABLE` **does not prove** the thread is executing on a CPU at the moment of sampling.
- `WAITING` **does not prove** a deadlock: an executor worker might be idle waiting on a queue, or a thread might be waiting on a valid condition.
- `BLOCKED` in this API refers only to **monitors**, not all types of I/O, thread pools, database connections, or library-built locks.
- A thread can transition states faster than the data collection interval. Two consecutive snapshots can differ without any error.
- Java `Thread.State` is not a Linux/Windows `Process State`; do not directly infer context switch counts, CPU time, or lock wait duration from a single `getState()` snapshot.

## 3. Entering `synchronized`: `RUNNABLE → BLOCKED → RUNNABLE`

An **intrinsic monitor** is associated with each Java object, and is also used for `static synchronized` via the corresponding `Class` object. When a thread enters `synchronized (lock) { ... }`, it needs to **own the monitor** of `lock`.

- If the monitor is free, the thread can acquire it and proceed into the critical section without going through an observable `BLOCKED` period.
- If the monitor is held by another thread, the thread trying to enter will be in `BLOCKED` in Java's state model.
- When the monitor is released, contending threads have a **chance** to acquire the monitor and continue as `RUNNABLE`; there is no guarantee which thread wins first, nor any guarantee of immediate CPU scheduling.
- `synchronized` is **reentrant**: a thread that already owns the monitor can enter nested blocks using the same monitor without blocking itself.

Example:

```java
Object guard = new Object();

// Thread A
synchronized (guard) {
    doWork(); // A holds guard while executing
}

// Thread B running concurrently:
synchronized (guard) {
    updateState(); // B must wait if A has not released guard
}
```

This is an **illustrative snippet**, not a standalone program, because `doWork()` and `updateState()` are placeholder names. While A still holds `guard`, B may be in `BLOCKED`. When A exits the `synchronized` block (including via stack unwinding from an exception), the monitor is released. Thread B only proceeds with the update after it actually enters the monitor.

**Monitor entrance is not interruptible:** calling `contender.interrupt()` does not force a thread that is `BLOCKED` at the `synchronized` entrance to exit lock waiting, and does not cause `synchronized` to throw `InterruptedException`. The interrupt flag can still be set for subsequent code to handle. If you want a **lock acquisition** that can be canceled by interruption, consider `ReentrantLock.lockInterruptibly()` when design requirements allow.

Regarding memory effects, **unlocking** a monitor *happens-before* the subsequent **locking** of the same monitor. Thus, a later thread observes writes made before the previous thread released the monitor according to the Java Memory Model rules. However, this does not automatically protect data if a thread reads/writes while bypassing the same synchronization mechanism.

## 4. `Object.wait()`: From Owning a Monitor to WAITING

`Object.wait()` is completely different from waiting **to enter** `synchronized`.

1. The thread must **currently own the monitor** of the exact object on which it calls `wait()`. Otherwise, Java throws `IllegalMonitorStateException`.
2. `wait()` places the thread into that monitor's wait set and **releases that monitor** (including the corresponding reentrant monitor holds) while waiting.
3. With `wait()` without a timeout, the thread is typically observed as `WAITING`. With `wait(long timeoutMillis)` (positive timeout), it is `TIMED_WAITING`.
4. Reasons for leaving the wait set include `notify()`, `notifyAll()`, interruption, timeout (if any), or a **spurious wakeup**.
5. Before `wait()` actually returns or throws `InterruptedException`, the thread must **reacquire the monitor** of that object. If the monitor is still held by another thread, the thread may transition to `BLOCKED` while waiting to re-enter.
6. Only after successfully re-entering does the thread continue checking the condition and executing code inside the `synchronized` block.

Typical flow:

```text
RUNNABLE (holding monitor)
    |
    | calls Object.wait(), releases that object's monitor
    v
WAITING or TIMED_WAITING
    |
    | notify/notifyAll, interrupt, timeout, or spurious wakeup
    v
BLOCKED (if waiting to reacquire monitor)
    |
    | acquires monitor
    v
RUNNABLE (continues inside synchronized)
```

This diagram shows **a typical state transition sequence**, not a claim that every run will observe every single state. If the monitor can be reacquired immediately, the `BLOCKED` phase is very brief or not visible in snapshots.

### Why Does notify Not Mean Immediate Execution?

Consider:

```java
synchronized (guard) {
    available = true;
    guard.notifyAll();
    // The notified thread still cannot execute
    // inside synchronized(guard) until the monitor is released.
    performMoreWork();
}
```

This is an **illustrative snippet placed inside a method**; `guard`, `available`, and `performMoreWork()` are components assumed to be declared in context. `notifyAll()` makes waiters eligible to contend for the monitor, but **does not release the monitor itself**. The thread calling `notifyAll()` still holds the monitor until it exits the synchronized region. Therefore, prolonging `performMoreWork()` right after notification can increase the time waiters spend waiting to reacquire the lock.

- `notify()` selects **one** waiter from the corresponding wait set, with no guarantee of choosing the "oldest" or any fair order.
- `notifyAll()` wakes up the waiters in the wait set, but they must still contend for the monitor one by one.
- Not every waiter is necessarily eligible to process data upon waking: notification does not make the business condition true for all threads.

### Always Wait on a Condition (Predicate) in a Loop

Correct pattern:

```java
private final Object guard = new Object();
private boolean available;

// Producer:
void publish() {
    synchronized (guard) {
        available = true;  // update predicate first
        guard.notifyAll(); // notify while holding monitor
    }
}

// Consumer:
void awaitAvailable() throws InterruptedException {
    synchronized (guard) {
        while (!available) {
            guard.wait();
        }
        // available == true and currently holding guard
    }
}
```

These are illustrative methods of **the same class**, not a standalone Java file. Writing `available`, checking `available`, and `wait/notify` all occur under **the same monitor**, so a separate `volatile` is not needed for this variable in that model.

**Why `while` instead of `if`?** A spurious wakeup may occur, multiple consumers may be awakened while only one wins the data, or the condition may have changed while waiting to reacquire the monitor. The thread must **recheck the predicate** after every wakeup.

**Avoiding lost notifications:** do not separate checking the condition from entering the wait set. If a thread checks the condition without synchronization and then calls `wait()`, a `notify` could occur in between and be missed. Updating and checking the predicate under the same lock solves this: if the condition is already true, the thread does not call `wait`.

`wait()` **only releases the monitor of the object it is called on**. If a thread holds another monitor when calling `guard.wait()`, the other monitors **are not automatically released**; this can cause deadlock or hold locks for too long. `Thread.sleep()` also **does not release held monitors**; sleeping is not a substitute for `wait()`.

### Interruption in Object.wait

When a thread is interrupted during `Object.wait()`, `wait()` will throw `InterruptedException` after reacquiring the monitor per the API contract; **the interrupt status is cleared** when the exception is thrown. Handling should either propagate the exception to the caller, or exit cleanly and restore the interrupt flag:

```java
try {
    guard.wait();  // only call when owning guard's monitor
} catch (InterruptedException e) {
    Thread.currentThread().interrupt();
    return; // if in a void method and deciding to cancel the work
}
```

This is an **illustrative snippet in a `void` method inside `synchronized(guard)`**, not a standalone program. Do not swallow the interrupt with an empty `catch` and continue waiting indefinitely.

## 5. `ReentrantLock`: Waiting on a Lock Does Not Mean Java BLOCKED

`ReentrantLock` belongs to `java.util.concurrent.locks`. It is an **explicit lock**, not the intrinsic monitor used by `synchronized`. When `lock()` is called and the lock is unavailable, the synchronization implementation is typically based on AQS and may use `LockSupport.park()` to make the thread wait. While parked, the thread typically shows `WAITING` (or `TIMED_WAITING` for timed waits). During brief lock acquisition attempts, it may also be `RUNNABLE`. **Do not assume the `BLOCKED` state for `ReentrantLock.lock()`.**

Example pattern:

```java
ReentrantLock lock = new ReentrantLock();

lock.lock();
try {
    // Read/write data protected by lock.
} finally {
    lock.unlock();
}
```

This is a **code snippet inside a method** requiring `import java.util.concurrent.locks.ReentrantLock`. `unlock()` must be in `finally`; if the work throws an exception without unlocking, other threads may get stuck. Only the owning thread may call `unlock()`; calling it otherwise throws `IllegalMonitorStateException`.

Important differences in interruptible waiting:

| Mechanism | Can **waiting to acquire the lock** be stopped by interrupt? | Notes |
|---|---|---|
| `synchronized` enter | **No** | `interrupt()` does not make `synchronized` throw an exception. |
| `ReentrantLock.lock()` | **No by this API** | Default lock acquisition; not a cancelable acquisition. |
| `ReentrantLock.lockInterruptibly()` | **Yes** | Can throw `InterruptedException` while waiting for the lock; caller must handle it. |
| `ReentrantLock.tryLock()` | Returns immediately | Not a waiting path; returns `false` if the lock cannot be acquired. |
| `ReentrantLock.tryLock(timeout, unit)` | **Yes** | Can time out or throw `InterruptedException`. |

When writing `lockInterruptibly()`, only enter `finally { unlock(); }` **after the lock is successfully acquired**:

```java
lock.lockInterruptibly(); // may throw before owning the lock
try {
    // critical section
} finally {
    lock.unlock();
}
```

This is an **illustrative snippet in a method declaring `throws InterruptedException`**. An exception thrown while waiting will not enter the `try/finally` above, preventing accidentally unlocking a lock the thread does not hold.

### `Condition.await()`: Condition Waiting on an Explicit Lock

`Condition` is paired with a `Lock`, conceptually similar to waiting on a predicate under a monitor, but **without using** `Object.wait()`:

```java
// Fields of a class:
private final ReentrantLock lock = new ReentrantLock();
private final Condition changed = lock.newCondition();
private boolean available;

void publish() {
    lock.lock();
    try {
        available = true;
        changed.signalAll();
    } finally {
        lock.unlock();
    }
}

void awaitAvailable() throws InterruptedException {
    lock.lock();
    try {
        while (!available) {
            changed.await();
        }
    } finally {
        lock.unlock();
    }
}
```

This is a **member code snippet of a class**; it requires importing `ReentrantLock` and `Condition` from `java.util.concurrent.locks`. `await()` **releases the associated explicit lock** while waiting, and **reacquires the lock before returning**; it does not release other locks the thread holds concurrently. `signal()/signalAll()` requires owning the lock associated with this `ReentrantLock`'s `Condition`. Just like with a monitor, signaling **does not automatically transfer ownership**: the waiter must contend to reacquire the lock, and must always loop with `while` to check the predicate.

`Condition.await()`/`awaitNanos()` can be interrupted; the wait method returns or throws after reacquiring the lock per the `Condition`/`ReentrantLock` contract. Depending on the wait API and situation, a signal, timeout, interrupt, or spurious wakeup can end the wait, so the predicate remains the source of truth for the work.

### `LockSupport.park()/unpark()`: Lower-Level Waiting

`LockSupport.park()` can put a thread into `WAITING`, and `parkNanos()` into `TIMED_WAITING`. `unpark(thread)` provides a permit so that thread can proceed; permits **do not accumulate into an unbounded queue**. `park()` can return when interrupted or due to a spurious return; therefore, synchronizers built on `LockSupport` must also check their condition in a loop.

**`park()` itself does not release any monitor or `ReentrantLock` that the thread holds.** This differs from `Object.wait()` and `Condition.await()`: higher-level await APIs release only their corresponding lock per their contract. Calling park arbitrarily while still holding a lock needed by others can cause a deadlock.

`Thread.interrupt()` can cause `park()` to return, but `park()` **does not throw `InterruptedException`** and does not clear the interrupt status. To check without clearing the flag, use `Thread.currentThread().isInterrupted()`; `Thread.interrupted()` is a static method that checks **and clears** the current thread's flag.

## 6. Runnable Practice on Java 17+

The **`MonitorLockTransitions.java`** example has three parts. The first two use `CountDownLatch` to coordinate timing before observing states: a thread contending for a held intrinsic monitor is in `BLOCKED`; a thread waiting on `Object.wait()` is observed in `WAITING` and then `BLOCKED` after being notified but before reacquiring the monitor. The third part shows acquiring a `ReentrantLock` and releasing it with `finally`, **without assuming a fixed state** for the explicit lock.

```java
import java.util.concurrent.CountDownLatch;
import java.util.concurrent.TimeUnit;
import java.util.concurrent.locks.ReentrantLock;

public class MonitorLockTransitions {
    private static Thread.State awaitState(
            Thread thread, Thread.State expected) throws InterruptedException {
        long deadline = System.nanoTime() + TimeUnit.SECONDS.toNanos(5);
        while (System.nanoTime() < deadline) {
            Thread.State current = thread.getState();
            if (current == expected) return current;
            Thread.sleep(1);
        }
        throw new IllegalStateException("Cannot observe " + expected);
    }

    private static void monitorEntry() throws InterruptedException {
        Object monitor = new Object();
        CountDownLatch aboutToEnter = new CountDownLatch(1);
        Thread contender = new Thread(() -> {
            aboutToEnter.countDown();
            synchronized (monitor) {
                System.out.println("2. contender entered monitor");
            }
        }, "monitor-contender");

        synchronized (monitor) {
            contender.start();
            aboutToEnter.await();
            System.out.println("1. contender state: " +
                    awaitState(contender, Thread.State.BLOCKED));
        }
        contender.join();
    }

    private static void monitorWait() throws InterruptedException {
        Object monitor = new Object();
        boolean[] ready = {false};
        CountDownLatch entered = new CountDownLatch(1);
        Thread waiter = new Thread(() -> {
            synchronized (monitor) {
                entered.countDown();
                while (!ready[0]) {
                    try {
                        monitor.wait();
                    } catch (InterruptedException e) {
                        Thread.currentThread().interrupt();
                        return;
                    }
                }
                System.out.println("5. waiter resumed with monitor");
            }
        }, "monitor-waiter");

        waiter.start();
        entered.await();
        System.out.println("3. waiter state before notify: " +
                awaitState(waiter, Thread.State.WAITING));
        synchronized (monitor) {
            ready[0] = true;
            monitor.notifyAll();
            System.out.println("4. waiter state after notify, before unlock: " +
                    awaitState(waiter, Thread.State.BLOCKED));
        }
        waiter.join();
    }

    private static void explicitLock() throws InterruptedException {
        ReentrantLock lock = new ReentrantLock();
        CountDownLatch aboutToLock = new CountDownLatch(1);
        Thread contender = new Thread(() -> {
            aboutToLock.countDown();
            lock.lock();
            try {
                System.out.println("7. explicit lock acquired");
            } finally {
                lock.unlock();
            }
        }, "lock-contender");

        lock.lock();
        try {
            contender.start();
            aboutToLock.await();
            System.out.println("6. main still holds explicit lock");
        } finally {
            lock.unlock();
        }
        contender.join();
    }

    public static void main(String[] args) throws InterruptedException {
        monitorEntry();
        monitorWait();
        explicitLock();
    }
}
```

Compile and run from the directory containing the file:

```bash
javac --release 17 MonitorLockTransitions.java
java MonitorLockTransitions
```

Output from a verified run on OpenJDK (and the order controlled by the monitor/latches in this program):

```text
1. contender state: BLOCKED
2. contender entered monitor
3. waiter state before notify: WAITING
4. waiter state after notify, before unlock: BLOCKED
5. waiter resumed with monitor
6. main still holds explicit lock
7. explicit lock acquired
```

**Explanation of each observed point:**

1. `main` holds the monitor and the `contender` thread tries to enter: the `BLOCKED` state is held steadily until `main` exits `synchronized`.
2. When `main` releases the monitor, `contender` acquires it and prints line 2; `join()` ensures this part finishes before the next part.
3. `waiter` acquires the monitor and calls `wait()`, releasing the monitor and entering `WAITING`.
4. `main` acquires the monitor, sets `ready=true`, and calls `notifyAll()`, but still holds the monitor. `waiter` has been notified yet is still waiting to **reacquire**, so `BLOCKED` is observed.
5. After `main` leaves the monitor, `waiter` re-enters, checks `ready`, and proceeds.
6. With the explicit lock, `main` holds `ReentrantLock` while contender tries to acquire the lock. Line 6 does not assume the state is `BLOCKED`.
7. After `unlock()`, contender acquires the explicit lock and prints line 7.

`awaitState()` is only used for **state sampling in this exercise**, not as a synchronization protocol for business logic. It polls every 1 ms with a 5-second deadline to avoid hanging indefinitely if state observation has an issue. In an extremely slow or CPU-starved environment, the example may throw `IllegalStateException` if it cannot observe the state in time; there is no scheduler deadline guarantee. Do not use `getState()` polling to decide when to enter a critical section in production.

**Note on correctness:** `ready` in the example is a `boolean[]` array solely so the local variable can be accessed by the lambda; it is read/written **under the same monitor**, so `volatile` is not needed. The `entered.countDown()` checkpoint is inside `synchronized`, and `main` reads the `WAITING` state before notifying. This is experimental coordination; real applications typically use `BlockingQueue`, `CountDownLatch`, or `Condition` instead of writing low-level wait loops when existing primitives match the intent.

## 7. Quick Comparison of Waiting Behaviors

| Operation | Must hold monitor/lock before calling? | Releases lock while waiting? | Typically observed state |
|---|---|---|---|
| Entering `synchronized(obj)` when obj is held | No, attempting to acquire | Does not own this lock yet | `BLOCKED` |
| `obj.wait()` | Must hold `obj`'s monitor | **Yes**, `obj`'s monitor; reacquires afterward | `WAITING` → possibly `BLOCKED` |
| `obj.wait(t>0)` | Must hold `obj`'s monitor | **Yes**, `obj`'s monitor | `TIMED_WAITING` → possibly `BLOCKED` |
| `obj.notify()/notifyAll()` | Must hold `obj`'s monitor | **No** | Caller continues running; waiter must reacquire |
| `Thread.sleep(t)` | No | **Does not** release held locks | `TIMED_WAITING` |
| `ReentrantLock.lock()` when busy | No | Does not own the new lock yet | Usually `WAITING` when parked; may be `RUNNABLE` |
| `Condition.await()` | Must own associated lock | **Yes**, associated lock; reacquires afterward | Usually `WAITING` |
| `Condition.awaitNanos(t)` | Must own associated lock | **Yes**, associated lock | Usually `TIMED_WAITING` |
| `LockSupport.park()` | No | **Does not** automatically release locks | `WAITING` |
| `LockSupport.parkNanos(t)` | No | **Does not** automatically release locks | `TIMED_WAITING` |

The "Typically observed state" cells describe typical outcomes at a point in time. **Do not** treat this table as a mandatory schedule or a required sequence of state transitions. In particular, after a waiter leaves a condition queue, it still has to wait for the scheduler to grant CPU time and may have to contend to reacquire the lock.

## 8. Deadlock, Starvation, and Blocked Are Not Synonyms

### Deadlock

Suppose thread A holds monitor `left` and waits for monitor `right`, while thread B holds `right` and waits for `left`. Both can remain `BLOCKED` forever due to the circular dependency. With `ReentrantLock` and other resources, the wait cycle may appear as `WAITING` instead of `BLOCKED`. Deadlock is a **circular dependency that cannot make progress**, not a single state label.

Helpful practices: enforce a consistent acquisition order for multiple locks; reduce nested locking; use timeouts when allowed with a rollback strategy; avoid slow I/O while holding a monitor if it can be safely placed outside.

### Starvation

A thread goes a long time without acquiring a lock even though other threads make progress, due to CPU distribution, excessive contention, or waiter selection policy. It may change states continuously and is not necessarily deadlocked. `synchronized` does not guarantee FIFO. `ReentrantLock(true)` provides a fairness policy for acquisition under contention at the API level, but does not guarantee strict CPU scheduling and often trades off throughput; untimed `tryLock()` also has barging behavior to be aware of. Use wait metrics and SLAs to decide, rather than blindly enabling fairness.

### Valid Waiting

A thread in `WAITING` inside `BlockingQueue.take()` when the queue is empty may simply be idle by design. `Object.wait()` in a producer-consumer pattern can also be normal behavior. To diagnose a bug, you need to know which predicate is false, who is responsible for changing the predicate, whether a signal is issued, and whether work is actually progressing.

## 9. How to Diagnose in a Real Program

**Step 1 — Look at the right time and the right threads.** While the process is live, take a few thread dumps spaced apart:

```bash
jcmd <PID> Thread.print -l
```

Replace `<PID>` with the actual process ID. Depending on the JDK/OS, the tool may require appropriate permissions or an environment that supports attach.

**Step 2 — Read states together with stacks:**

- `BLOCKED (on object monitor)` and a "waiting to lock" line pointing to a monitor signal that you should find the owner, critical section, and monitor acquisition path.
- `WAITING (on object monitor)` paired with `Object.wait` suggests waiting on a monitor predicate; look for the `notify/notifyAll` logic and predicate.
- `WAITING (parking)` with `LockSupport.park`/AQS suggests an explicit lock, condition, queue, or another synchronizer; you must read the stack to distinguish them.
- `TIMED_WAITING (sleeping)` is a timed sleep; **do not** conclude that any monitor is being released.

**Step 3 — Correlate with time-series data.** Thread dumps can miss very short lock contention. Use Java Flight Recorder to inspect `jdk.JavaMonitorEnter`, `jdk.JavaMonitorWait`, and `jdk.ThreadPark` events, along with durations, event thresholds, threads, and stack traces when the environment supports it:

```bash
jcmd <PID> JFR.start name=lock-check settings=profile duration=60s filename=locks.jfr
jfr summary locks.jfr
jfr print --events jdk.JavaMonitorEnter,jdk.JavaMonitorWait,jdk.ThreadPark locks.jfr
```

The environment must support JFR; events might not be enabled or might be filtered by duration/threshold, so **seeing no events does not prove there is no contention**. A recording file is only meaningful if the workload reproduces the issue during the recording window. For a fast-running demo program, useful events might not be captured in time.

**Step 4 — Measure the cause, do not guess.** Check the lock owner, wait duration, number of contending threads, critical section length, I/O duration, and tasks waiting in queues. Distinguish between CPU starvation, lock contention, I/O waiting, and thread pool saturation; the optimization approach will differ.

### Java 21+ and Virtual Threads (Scope Note)

With virtual threads, not every Java thread is permanently bound to an OS thread. Supported blocking operations can **unmount** a virtual thread from its carrier; therefore, platform thread counts and OS scheduling rules should not be applied verbatim to all virtual thread measurements. However, monitors, conditions, lock ownership, interruption, and invariants still matter. The practical example above intentionally uses APIs available since **Java 17+** and creates **platform threads** so `Thread.State` is easy to observe.

## 10. Common Mistakes and Fixes

1. **“A thread waiting on `ReentrantLock` is definitely `BLOCKED`.”** Confuses intrinsic monitors with explicit locks. Check the call stack; AQS/park usually shows `WAITING` or `TIMED_WAITING`.
2. **“`notify()` makes the waiter run immediately.”** It only gives the waiter a chance to re-contend for the monitor; the caller still holds the monitor until it unlocks.
3. **“Calling `wait()` outside `synchronized` works fine.”** It throws `IllegalMonitorStateException` if the thread does not own the corresponding monitor.
4. **“`wait()` releases all locks.”** It only releases the monitor of the object it is called on; holding other monitors can create wait cycles.
5. **“`sleep()` releases locks for other threads.”** No. If holding a monitor or explicit lock, the thread keeps holding it during sleep.
6. **“Once notified, `if` is enough.”** Spurious wakeups can occur or another thread can change the condition; use `while (!predicate) wait()`.
7. **“Seeing `WAITING` is enough to spot a deadlock.”** You need a wait graph, owners, stacks, and evidence of no progress; valid waiting is very common.
8. **“`interrupt()` cancels any lock acquisition.”** Does not apply to monitor entrance or `ReentrantLock.lock()`; use `lockInterruptibly()` or `tryLock(timeout, unit)` to control waiting with the right API.
9. **“The lock is released upon `notifyAll()`/`signalAll()`.”** No. The lock is released when exiting `synchronized` or calling `unlock()` properly.
10. **“`Thread.getState()` can replace synchronization conditions.”** No. It is an observation tool; use locks, conditions, latches, queues, and predicates for correctness.

## 11. Self-Check Questions

**Question 1.** A holds monitor `m`, and B is trying to enter `synchronized(m)`. What state is B typically in?  
**Answer:** `BLOCKED`. B has not entered the critical section yet and must wait for monitor `m`.

**Question 2.** B is in `m.wait()` (without timeout); A acquires `m` and calls `m.notifyAll()` but keeps holding `m` for a few more seconds. What state can B be observed in during that time?  
**Answer:** B leaves `WAITING`; while waiting to reacquire monitor `m`, it will be in `BLOCKED`. B cannot resume inside `synchronized` until it reacquires `m`.

**Question 3.** A thread waiting on `ReentrantLock.lock()` appears as `WAITING (parking)` in a dump. Does this contradict the concept of "waiting on a lock"?  
**Answer:** No. `Thread.State.BLOCKED` describes waiting on an intrinsic monitor; explicit locks have a `park`-based waiting path.

**Question 4.** Why is `while (!ready) guard.wait()` better than `if (!ready) guard.wait()`?  
**Answer:** You must recheck the predicate after spurious wakeups, after competing with other waiters, and when business state may change while the thread reacquires the monitor.

**Question 5.** A thread holds `a` and `b`, then calls `a.wait()`. Which lock is released while waiting?  
**Answer:** Monitor `a` is released during `wait()`; monitor `b` **is not automatically released**.

**Question 6.** If a thread is `BLOCKED` on a monitor, does `interrupt()` cause `synchronized` to throw `InterruptedException`?  
**Answer:** No. Monitor entrance is not interruptible; if you need cancelable acquisition, design with `lockInterruptibly()` or controlled timed `tryLock`.

## References

- [Java SE 17 — Thread.State](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/lang/Thread.State.html): official definition of the six states.
- [Java SE 17 — Object.wait/notify](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/lang/Object.html): monitor ownership, wait set, notify, and reacquisition.
- [Java SE 17 — ReentrantLock](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/concurrent/locks/ReentrantLock.html): acquisition types, fairness, unlock.
- [Java SE 17 — Condition](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/concurrent/locks/Condition.html): await/signal semantics and predicates.
- [Java SE 17 — LockSupport](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/concurrent/locks/LockSupport.html): park/unpark and permits.
- [Java SE 17 — ThreadMXBean](https://docs.oracle.com/en/java/javase/17/docs/api/java.management/java/lang/management/ThreadMXBean.html): support for thread and contention observation.

**Remember:** when looking at a thread "waiting on a lock," the first question is **whether it is waiting for *monitor entry*, waiting on a *condition*, or waiting on an *explicit lock*.** Only after knowing that mechanism can you properly explain the state, lock release/reacquisition, and safe handling.

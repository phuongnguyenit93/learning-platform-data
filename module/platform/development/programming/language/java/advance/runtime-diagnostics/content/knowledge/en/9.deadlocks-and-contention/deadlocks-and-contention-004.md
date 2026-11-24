# 9.4 Diagnosing synchronized, ReentrantLock, Condition, Object.wait, and LockSupport.park

A Java application may **remain running with low CPU and emit no exceptions, yet every new request times out**. In that case, the hard part is not finding “how many threads are WAITING,” but tracing relationships: **which thread holds the resource**, **which thread is waiting to acquire the lock**, **which thread is waiting for a condition signal**, **who will send the signal**, and **what is preventing the next step from happening**.

Five APIs/mechanisms commonly appearing in thread dumps relate directly to this question:

1. `synchronized` — the intrinsic monitor lock of a Java object.
2. `ReentrantLock` — an exclusive lock with reentrancy, try/timed/interruptible acquisition options, and queue observability.
3. `Condition` — a condition wait queue associated with a `Lock`, typically `ReentrantLock`.
4. `Object.wait()` / `notify()` / `notifyAll()` — the wait-set on an object monitor, usable only while owning that monitor.
5. `LockSupport.park()` / `unpark()` — a low-level primitive using one permit per thread, used underneath by many AQS/pool/condition implementations.

**These mechanisms are not equivalent.** `synchronized` and `ReentrantLock` control **mutual exclusion**. `Object.wait` and `Condition.await` are used to **wait for a logical condition** and *temporarily release the associated lock* while waiting. `LockSupport.park` merely suspends scheduling the thread until a permit, interrupt, or spurious wakeup arrives: by itself it **does not release any held monitor or `ReentrantLock`**, nor does it know any business predicate.

This lesson focuses on **diagnosing hangs and contention**, not merely syntax usage. Examples use Java 17+ and Java SE 21 documentation; thread states, dump formats, and data completeness depend on JDK/JVM/OS/tools, especially in virtual-thread environments.

## 1. Comparison Table of the Five Mechanisms Before Inspecting Thread Dumps

| Mechanism | Primary Synchronization Target | What Happens When Waiting? | Is the Lock Released While Waiting? | Typical Signs |
| --- | --- | --- | --- | --- |
| `synchronized(lock)` | Monitor of `lock` | Waits to enter the monitor if held | **No**, enters only upon acquisition; owner releases on synchronized exit or calling `wait` on that same monitor | Contender: `BLOCKED (on object monitor)`, `waiting to lock` |
| `ReentrantLock.lock()` | Ownable synchronizer/AQS of the lock | Waits for owner to call `unlock` | Waiter does not hold the lock yet; owner holds until `unlock` | `WAITING/TIMED_WAITING (parking)` and `ReentrantLock$...Sync` |
| `Condition.await()` | Condition and its associated `Lock` | Waits for signal/interrupt/timeout/spurious | **Yes**, releases the associated lock and reacquires before returning normally or throwing per contract | `WAITING/TIMED_WAITING (parking)` on `ConditionObject` |
| `Object.wait()` | Wait-set of an object monitor | Waits for notify/interrupt/timeout/spurious | **Yes**, releases the monitor of the **exact waited object**, then reacquires before returning | `WAITING/TIMED_WAITING (on object monitor)`, `waiting on` |
| `LockSupport.park()` | Per-thread permit; optional blocker object | Waits for `unpark`/interrupt/spurious/timeout | **Does not automatically release** any monitor or `ReentrantLock` | `WAITING/TIMED_WAITING (parking)`, `parking to wait for` if blocker is set |

*Legend:* state is a snapshot. `Condition.await()`, `ReentrantLock.lock()`, and `LockSupport.park()` can all appear as `WAITING (parking)`, yet **the reason for waiting differs**. You must inspect stack frames and the blocker class rather than lumping them into “sleeping threads.”

### 1.1 Two Wait Categories to Distinguish Immediately

**Waiting for a lock to enter a critical section**:

- `synchronized`: contender has not acquired the monitor yet, typically `BLOCKED`.
- `ReentrantLock.lock()`: contender has not acquired the ownable lock yet, typically parked in AQS.
- To diagnose: **find the owner** and measure why the owner holds it so long.

**Waiting for a condition while coordinating state**:

- `Object.wait()`: waiter entered the monitor and then **released that monitor** while waiting.
- `Condition.await()`: waiter acquired the associated `Lock` and then **released the lock** to wait.
- `LockSupport.park()`: has no automatic lock-release rule; inspect the code.
- To diagnose: **find the predicate and the signal/notify/unpark sender**, checking lifecycle and happens-before.

Confusing these two groups leads to wrong fixes: “enlarging the thread pool” will not break a deadlock, “notifyAll” will not unblock a monitor owner stuck in I/O, and calling “unlock” from another thread is not how you fix `ReentrantLock`.

## 2. Diagnosing synchronized: Monitor Owners and BLOCKED Contenders

### 2.1 Where Is the Monitor Acquired?

`synchronized` can wrap a block:

```java
private final Object monitor = new Object();

void update() {
    synchronized (monitor) {
        // Critical section: only one thread holds this monitor at a time.
        updateSharedState();
    }
}
```

Or an instance `synchronized` method (the monitor is `this`) or a static synchronized method (the monitor is the `Class` object of that class). Both snippets above are **illustrative code**, not standalone Java files.

Java monitors are reentrant: a thread already holding a monitor can reenter `synchronized` on the same monitor, increasing ownership depth; exiting each level decrements depth, and the monitor is finally released upon exiting all synchronized blocks. Throwing an exception also exits synchronized control flow per Java semantics, requiring no manual unlock.

### 2.2 Under Contention, Read Both Waiter and Owner

A **hypothetical** thread dump:

```text
"request-7" ...
   java.lang.Thread.State: BLOCKED (on object monitor)
    at demo.OrderService.commit(OrderService.java:74)
    - waiting to lock <0x0000000711101000> (a java.lang.Object)

"request-2" ...
   java.lang.Thread.State: TIMED_WAITING (sleeping)
    at java.lang.Thread.sleep(Native Method)
    at demo.OrderService.commit(OrderService.java:79)
    - locked <0x0000000711101000> (a java.lang.Object)
```

Within the **same dump**, ID `<0x0000000711101000>` links the waiter to the lock holder: `request-2` holds the monitor and `request-7` wants to enter. Yet `request-2` is sleeping inside the critical section; `sleep` **does not release the monitor**. This is a **long critical section / lock contention** pattern, **not automatically a deadlock** if the owner can wake up and release the monitor.

Do not assume an owning thread must be `RUNNABLE`: the owner may be in `WAITING`, `TIMED_WAITING`, or inside native I/O while holding the lock. Find **all held-lock markers** and inspect the owner’s stack.

### 2.3 Reading Markers in the Right Direction

| Line/Field | Meaning | Mistake |
| --- | --- | --- |
| `- waiting to lock <L>` | Thread **does not hold** monitor L yet; trying to enter | Calling the thread the owner |
| `- locked <L>` | Thread **is holding** monitor L | Calling it a waiter on L |
| `getLockInfo()` when `BLOCKED` | Monitor object the contender is waiting for | Confusing with all locks the thread holds |
| `getLockOwnerId()` | Owner’s Java thread ID if known to the JVM | Using it as OS PID/nid |
| `getLockedMonitors()` | Monitors captured as held, if capture was requested | Empty array always proving no locks are held |
| `getBlockedTime()` | Accumulated monitor contention time when enabled/supported | Exact duration of the current blocking event |

If 50 threads are all waiting on the same monitor ID, that may be a **lock convoy** behind one slow owner, not necessarily 50 separate deadlocks.

### 2.4 Ways Monitors Are Accidentally Held Too Long

- Calling network/DB APIs or RPCs inside `synchronized`.
- Running CPU-heavy algorithms while holding a mutex.
- Waiting on `CountDownLatch.await()`, `Thread.sleep()`, or `LockSupport.park()` inside `synchronized`.
- Invoking callback/plugin code of unknown latency inside a critical section.
- Enabling synchronous logging I/O or calling a slow exporter inside a monitor.
- Acquiring two locks in different orders across code paths.

Fixes must preserve invariants: only move I/O outside a lock when data is snapshotted cleanly without introducing races. Never strip `synchronized` simply because many threads appear `BLOCKED`.

## 3. Diagnosing ReentrantLock: Ownership, AQS, and Timeouts

### 3.1 How Does ReentrantLock Differ from a Monitor?

`ReentrantLock` provides reentrant mutual exclusion like `synchronized` while adding `tryLock()`, `tryLock(timeout, unit)`, `lockInterruptibly()`, `isHeldByCurrentThread()`, `getHoldCount()`, and queue instrumentation. Proper syntax:

```java
lock.lock();
try {
    updateSharedState();
} finally {
    lock.unlock();
}
```

This is an illustrative snippet inside a class with a `lock` field. **Place `try` immediately after `lock()` succeeds**; never put `unlock()` outside `finally` or call it without ownership. If another thread tries to `unlock()` a `ReentrantLock` it does not hold, `IllegalMonitorStateException` can occur.

### 3.2 Why Are ReentrantLock Waiters Usually WAITING, Not BLOCKED?

HotSpot’s AQS-based implementation can use `LockSupport.park(...)` when a lock is contended. A contender will typically be captured as:

```text
"worker-lock-waiter" ...
   java.lang.Thread.State: WAITING (parking)
    at jdk.internal.misc.Unsafe.park(Native Method)
    at java.util.concurrent.locks.LockSupport.park(...)
    at java.util.concurrent.locks.AbstractQueuedSynchronizer.acquire(...)
    at java.util.concurrent.locks.ReentrantLock.lock(...)
    - parking to wait for <0x0000000711202000>
      (a java.util.concurrent.locks.ReentrantLock$NonfairSync)
```

**Do not filter solely on `BLOCKED` to look for lock contention.** For `ReentrantLock`, look for AQS/`ReentrantLock.lock` stacks and blocker objects; the owner may appear under `Locked ownable synchronizers` on another thread. The simulated dump only illustrates structure; methods/frames/classes vary by JDK release and fairness mode.

### 3.3 ReentrantLock Instrumentation Is Snapshot/Approximate

| API | What It Answers | Limitations |
| --- | --- | --- |
| `isLocked()` | Is the lock held by some thread at the snapshot? | Result can change immediately afterward |
| `isHeldByCurrentThread()` | Does the caller currently own the lock? | Caller only; does not find an arbitrary owner |
| `getHoldCount()` | Number of reentrant acquisitions by the caller | 0 if caller does not hold it |
| `hasQueuedThreads()` | Are threads waiting for the lock? | Snapshot; makes no fairness order promise |
| `getQueueLength()` | **Estimate** of waiting threads | Not an exact invariant count |
| `hasWaiters(condition)` | Are threads waiting on the associated condition? | Caller must hold the lock when checking per contract |
| `getWaitQueueLength(condition)` | Estimate of condition waiters | Depends on caller holding lock and concurrent changes |

A rising `getQueueLength()` can indicate contention, yet it does not show **how long each thread has waited** or explain the cause. Enabling fairness does not guarantee fair OS CPU scheduling for every thread; un-timed `tryLock()` also has special fairness semantics.

### 3.4 When Infinite Waiting Must Be Avoided

For business requirements with deadlines, consider timed acquisition:

```java
boolean acquired = lock.tryLock(200, java.util.concurrent.TimeUnit.MILLISECONDS);
if (!acquired) {
    // Return a classified error or perform a controlled retry.
    return;
}
try {
    updateSharedState();
} finally {
    lock.unlock();
}
```

This is **illustrative code** with a `lock` variable, `updateSharedState` method, and return from a void method. Choose timeouts based on SLOs and invariants, not 200 ms as a “Java standard.” When using `lockInterruptibly()` or timed `tryLock`, handle `InterruptedException` per your cancellation policy; never swallow the interrupt and continue indefinitely.

### 3.5 Fairness Is Not a Cure for All Contention

`new ReentrantLock(true)` may favor longer-waiting threads under its fairness policy, yet it can lower throughput and does not guarantee thread scheduling fairness. If the root cause is the owner holding the lock during a 30-second DB wait, enabling fairness will not speed up the DB. Measure lock hold time, queue depth, and work inside the critical section.

## 4. Object.wait(): Wait-Set, notify, and Logical Conditions

### 4.1 wait() Must Be Called While Holding the Right Monitor

`Object.wait()`, `notify()`, and `notifyAll()` all require the caller to own the monitor of the **exact object being called**. Correct example:

```java
private final Object signal = new Object();
private boolean ready = false;

void awaitReady() throws InterruptedException {
    synchronized (signal) {
        while (!ready) {
            signal.wait();
        }
    }
}

void markReady() {
    synchronized (signal) {
        ready = true;
        signal.notifyAll();
    }
}
```

This is an **illustrative class fragment**. Both methods protect the shared `ready` predicate with the same `signal` monitor. By using a `while` loop, the waiter rechecks the condition after notify, interrupt/timeout, or spurious wakeup. `notifyAll()` only wakes waiters; they must still reacquire the monitor to return from `wait`. The `markReady` caller keeps holding the monitor until exiting `synchronized`, **not releasing the lock immediately at the `notifyAll` line**.

### 4.2 Which Lock Does wait() Release?

When `signal.wait()` enters the wait-set, the thread **releases the `signal` monitor**, including all reentrant monitor ownership levels on it; it must reacquire that monitor before returning/throwing per semantics. However, `wait()` **does not automatically release any other monitors** the thread holds.

**Risky** example:

```java
synchronized (lockA) {
    synchronized (lockB) {
        lockB.wait(); // Releases lockB while waiting, but still holds lockA.
    }
}
```

If the thread calling `lockB.notifyAll()` needs to enter `lockA` first, the system can fall into a dependency cycle. Diagnostics must inspect **all held locks** of a waiter, not just the monitor it is awaiting notification on.

### 4.3 waiting on vs. waiting to lock

A thread waiting in `Object.wait()` may appear as:

```text
"condition-waiter" ...
   java.lang.Thread.State: WAITING (on object monitor)
    at java.lang.Object.wait(Native Method)
    - waiting on <0x0000000711303000> (a java.lang.Object)
```

Here `waiting on` means **awaiting condition notification**, not `waiting to lock` to enter `synchronized`. The thread already released this monitor during the wait phase. Once awakened, it may temporarily become `BLOCKED` if it cannot immediately reacquire the monitor.

### 4.4 Lost Signals, notify, and Spurious Wakeups

Typical bug:

```java
// Wrong pattern: no predicate and lock protecting the condition.
if (!ready) {
    signal.wait(); // Can also throw IllegalMonitorStateException.
}
```

Even when wrapped in `synchronized`, using `if` alone can still fail due to multiple waiters, condition changes, or **spurious wakeups**. Correct design requires **predicate + lock + while loop**, not merely calling `notify`.

`notify()` selects an unspecified waiter; if multiple distinct conditions share one wait-set, waking the wrong waiter can stall progress. `notifyAll()` is usually easier to reason about without strict waiter-selection invariants, though it can cause a “thundering herd.” When multiple independent condition queues need optimization, `Condition` can be a better fit.

### 4.5 A wait Timeout Does Not Guarantee Progress

`wait(long timeoutMillis)` returns upon notification, interrupt, timeout, or spurious wakeup per contract. Use clock-based deadlines/conditions and check inside a `while` loop; **never** assume “after waiting 5 seconds, the state is definitely ready.” `wait(0)` means wait indefinitely; do not confuse it with not waiting.

Some code blocks indefinitely because the producer never calls `notifyAll` or never updates the predicate. This is typically a **missed signal / protocol bug**, not necessarily a deadlock cycle detectable by `ThreadMXBean.findDeadlockedThreads()`.

## 5. Condition.await(): A Lock’s Condition Queue

### 5.1 Condition Is Tightly Bound to a Lock

With `ReentrantLock`:

```java
private final java.util.concurrent.locks.ReentrantLock lock =
        new java.util.concurrent.locks.ReentrantLock();
private final java.util.concurrent.locks.Condition changed =
        lock.newCondition();
private boolean ready = false;

void awaitReady() throws InterruptedException {
    lock.lock();
    try {
        while (!ready) {
            changed.await();
        }
    } finally {
        lock.unlock();
    }
}

void markReady() {
    lock.lock();
    try {
        ready = true;
        changed.signalAll();
    } finally {
        lock.unlock();
    }
}
```

This is a **class fragment**. `await`/`signal` require holding the **associated Lock** per `ReentrantLock`’s implementation; calling `signalAll` without holding the lock throws `IllegalMonitorStateException`. `Condition` provides **separate wait-sets** for one lock, instead of sharing one object monitor wait-set as with `Object.wait/notify`.

### 5.2 await Releases and Then Reacquires the Lock

When `changed.await()` begins waiting, the `ReentrantLock` implementation **fully releases the associated lock across its hold count** and restores that ownership upon returning. Thus a thread parked on `ConditionObject` **is not necessarily the owner of the `ReentrantLock`** at snapshot time. When signaled, it is moved to wait for lock reacquisition; it **does not immediately run** if the signaling thread still holds the lock.

Flow:

```text
WAITING thread: holds ReentrantLock
   -> while (!ready)
   -> Condition.await() : releases lock, enters condition queue
   -> receives signal / interrupt / timeout / spurious wakeup
   -> competes to reacquire lock
   -> await returns (with lock held)
   -> checks ready again
   -> eventually unlock in finally
```

`signal` moves a waiter out of the condition queue per implementation semantics, yet **does not immediately hand the lock directly to the waiter**. If the signaler continues doing long work under the lock, the waiter can still remain stuck in the acquisition queue.

### 5.3 Recognizing Condition in a Dump

**Simulated** example:

```text
"order-consumer" ...
   java.lang.Thread.State: WAITING (parking)
    at jdk.internal.misc.Unsafe.park(Native Method)
    at java.util.concurrent.locks.LockSupport.park(...)
    at java.util.concurrent.locks.AbstractQueuedSynchronizer$ConditionNode.block(...)
    at java.util.concurrent.ForkJoinPool.unmanagedBlock(...)
    at java.util.concurrent.locks.AbstractQueuedSynchronizer$ConditionObject.await(...)
    - parking to wait for <0x0000000711404000>
      (a java.util.concurrent.locks.AbstractQueuedSynchronizer$ConditionObject)
```

Internal AQS/`ForkJoinPool` stack frames **vary by JDK**; the sample only shows how to identify `ConditionObject.await` and a condition blocker. **Do not** infer an owner from `ConditionObject` as if it were a `ReentrantLock$Sync` held by another thread. What to look for next is **who will call `signal/signalAll`, which predicate must become true, and whether the producer can run**.

### 5.4 Why Condition Is Not Object.wait on the Condition Instance

`condition.await()` is completely different from `condition.wait()`. `Condition` is an interface whose operations carry semantics tied to `Lock`; `Object.wait` on the `Condition` object itself only uses that object’s intrinsic monitor, having **no defined relationship** with the associated lock/condition queue. Never replace `changed.await()` with `changed.wait()` or call `changed.notify()`.

### 5.5 Distinguishing await Variants

| Method | Ways Out of Wait | Diagnostic Expectations |
| --- | --- | --- |
| `await()` | Signal, interrupt, spurious wakeup | Can stay in WAITING/parking long-term |
| `awaitUninterruptibly()` | Signal/spurious; preserves interrupt status per contract | A single interrupt does not necessarily release the waiter |
| `awaitNanos(nanos)` | Signal/interrupt/spurious/timeout, returns remaining nanos | May show TIMED_WAITING |
| `await(time,unit)` | Returns boolean indicating signal before deadline per contract | Does not replace checking the predicate |
| `awaitUntil(Date)` | Uses an absolute wall-clock deadline | Clock changes must be understood properly |

Whichever variant you choose, use **`while (predicate)`** and manage deadlines/interrupts/cancellation. A timed await returning due to timeout does not mean the condition succeeded.

## 6. LockSupport.park(): Low-Level Permits and Traps

### 6.1 Each Thread Has at Most One Permit

`LockSupport` uses a logical single permit per thread:

- `unpark(thread)` makes the permit available (if not already available).
- `park()` consumes the permit if available and returns immediately.
- If no permit is available, `park` blocks until unparked, interrupted, timed out (timed variants), or spurious return.
- Two calls to `unpark` **do not accumulate into two permits**.
- `park` can return “for no reason”; callers must **recheck the predicate**.
- `park` does not throw `InterruptedException`; a thread may be interrupted and return immediately. Handling the interrupted flag is up to caller logic.

Many primitives such as AQS, thread pools, and schedulers use `park` underneath. Therefore seeing `Unsafe.park` in a stack **is not enough** to determine the bottleneck type.

### 6.2 park Does Not Automatically Release Any Lock

**Hang-prone** example:

```java
synchronized (monitor) {
    LockSupport.park(blocker);
}
```

The code above illustrates a design bug: if another thread needs to enter `synchronized(monitor)` to call `unpark(owner)`, the producer can be blocked by the very monitor the owner holds. `park` **has no monitor-release semantics**, unlike `monitor.wait()`.

Similarly, if holding a `ReentrantLock` while parking, the owner remains owner until calling `unlock()`. Never confuse `WAITING (parking)` with the thread having released all locks.

### 6.3 Using Blockers to Aid Diagnostics

`LockSupport.park(blocker)` sets a blocker object that tools can inspect via `LockSupport.getBlocker(thread)` or `ThreadInfo.getLockInfo()` in some cases. Example:

```java
while (!canContinue.get()) {
    LockSupport.park("waiting-for-work");
}
```

This is an illustrative snippet with an `AtomicBoolean canContinue`; production code should use a blocker object with clear identity (usually the synchronizer instance itself), avoiding placing customer/request/token data inside a blocker. `getBlocker` is a **snapshot**, can return null after the thread unparks, and a blocker is not required to have an owning thread.

### 6.4 unpark Before park Differs from notify Before wait

`unpark(thread)` can occur **before** `park()` and still leave a permit for the next `park` (if the thread has started and the permit has not yet been consumed); this differs from `notify` with no waiter: `notify` is not “saved up” for a future wait.

However, a permit can be consumed by another `park`, even from other code/frameworks; do not rely on a single permit as a **message queue**. Proper design requires a **state flag / volatile or atomic + loop**:

```java
// Consumer:
while (!ready.get()) {
    LockSupport.park(blocker);
}
// Producer:
ready.set(true);
LockSupport.unpark(consumerThread);
```

These are **two illustrative snippets** across two threads; `ready` is a shared `AtomicBoolean`, `blocker` is an object, and `consumerThread` is a started thread reference. Using state without visibility semantics can prevent the loop from observing the update despite `unpark`.

### 6.5 Park Can Be Interrupted Without Throwing an Exception

A thread interrupted while parked can return, yet if the caller only writes:

```java
while (!ready.get()) {
    LockSupport.park();
}
```

and the interrupted flag remains set, subsequent `park()` calls can return immediately, creating a **busy loop**. You must define a clear cancellation policy (check `Thread.currentThread().isInterrupted()`, terminate, or handle/restore status per contract). Do not call `Thread.interrupted()` carelessly because that method **clears the current thread’s interrupt flag**.

## 7. Thread States: BLOCKED, WAITING, and TIMED_WAITING Are Not Root Causes

| Thread State | Possible Causes | What to Observe Next |
| --- | --- | --- |
| `BLOCKED` | Waiting to enter/reenter a `synchronized` monitor | Monitor ID, `waiting to lock`, owner, and held-lock stack |
| `WAITING` | `Object.wait(0)`, `Condition.await`, `LockSupport.park`, `Thread.join`, idle pool | Stack frame, blocker type, predicate, and wake-up sender |
| `TIMED_WAITING` | `sleep`, `wait(timeout)`, timed await, `parkNanos/Until`, timed join | Deadline, locks held by owner while waiting, actual wait duration |
| `RUNNABLE` | Running Java, executing native call, waiting on some forms of I/O | CPU time, OS state, stack progression, syscalls/network |
| `TERMINATED` | Thread has exited | Do not infer history from a post-exit snapshot |
| `NEW` | Thread has not started | Not a waiter contending for a monitor |

**WAITING does not prove idleness.** A thread can be `WAITING` in `CountDownLatch.await` while still holding a monitor or `ReentrantLock` needed by many other threads. Conversely, many workers `WAITING` on a queue because there are no tasks can be a **normal state**.

**RUNNABLE does not mean consuming CPU**. A thread in native I/O or scheduling wait can also appear `RUNNABLE` from Java’s perspective. OS CPU/cgroup metrics or JFR are needed to distinguish them.

## 8. Capturing Thread Dumps and Selecting the Right Information

### 8.1 Using jcmd on HotSpot

First verify the exact PID/JVM instance, JDK tools, permissions, and host/container namespace. Then:

```bash
jcmd 4242 help Thread.print
jcmd 4242 Thread.print -l
```

`4242` is an **illustrative PID**. On modern HotSpot/JDKs, `Thread.print -l` requests `java.util.concurrent` locks / ownable synchronizers info; verify exact version and flags using the JVM’s `help`. Do not confuse `jcmd -l` (lists JVMs) with `jcmd PID Thread.print -l` (detailed thread dump).

`jstack -l 4242` can be used if available and supported on that JDK. If attach is disabled, the JVM exited, or the PID is wrong, never assume failure to dump means deadlock. Taking dumps can cost CPU/time and contain sensitive data; never run an unbounded capture loop in production.

### 8.2 Reading Markers by Wait Type

A hypothetical set of markers:

```text
"blocked-monitor" ... java.lang.Thread.State: BLOCKED (on object monitor)
    - waiting to lock <0x0000000711505000> (a java.lang.Object)

"holds-monitor" ... java.lang.Thread.State: TIMED_WAITING (sleeping)
    - locked <0x0000000711505000> (a java.lang.Object)

"waits-notify" ... java.lang.Thread.State: WAITING (on object monitor)
    - waiting on <0x0000000711506000> (a java.lang.Object)

"waits-aqs" ... java.lang.Thread.State: WAITING (parking)
    - parking to wait for <0x0000000711507000>
      (a java.util.concurrent.locks.ReentrantLock$NonfairSync)

"waits-condition" ... java.lang.Thread.State: WAITING (parking)
    - parking to wait for <0x0000000711508000>
      (a java.util.concurrent.locks.AbstractQueuedSynchronizer$ConditionObject)
```

These lines are abbreviated for explanation, **not full real output**. Depending on implementation/JDK, marker/stack wording varies; read exact values within the same artifact rather than hardcoding brittle regexes across all JDKs.

- `waiting to lock` → contending for an **intrinsic monitor**.
- `locked` → **holding** a monitor.
- `waiting on` → waiting for **`Object.wait/notify`**.
- `parking to wait for ...ReentrantLock$...Sync` → may be waiting on an **ownable `ReentrantLock`**.
- `parking to wait for ...ConditionObject` → may be waiting for a **condition signal**, not necessarily owned by a lock holder in that way.

### 8.3 Locked Ownable Synchronizers

At the end of each thread block, a dump with `-l` may show:

```text
Locked ownable synchronizers:
    - <0x0000000711507000>
      (a java.util.concurrent.locks.ReentrantLock$NonfairSync)
```

This section **is distinct from** `- locked <...>` for object monitors. When diagnosing `ReentrantLock` contention, find the owner holding the **exact same synchronizer identity** in the same dump and inspect what that owning thread is doing. Never carry object identities across a JVM restart or convert hashes/addresses arbitrarily.

### 8.4 ThreadMXBean: Monitors, Synchronizers, and Deadlocks

Java API:

```java
ThreadMXBean mx = ManagementFactory.getThreadMXBean();
if (mx.isObjectMonitorUsageSupported()
        && mx.isSynchronizerUsageSupported()) {
    ThreadInfo[] infos = mx.dumpAllThreads(true, true);
}
```

This is an **illustrative fragment** inside a method with `import java.lang.management.*`. The `ThreadInfo` array represents **platform threads** supported by the API; in Java 21 virtual threads are not fully inventoried/monitored by this interface. When monitor/synchronizer usage is unsupported, requesting full lock details can throw `UnsupportedOperationException`.

Mapping table:

| Java API | What You Want to Know | Notes |
| --- | --- | --- |
| `ThreadInfo.getThreadState()` | State at snapshot | Can change immediately |
| `getLockInfo()` | Lock/blocker thread is waiting on, if any | Blocker does not always have an owner |
| `getLockOwnerId()` | Java thread ID of owner, if known | `-1` means none/unknown |
| `getLockedMonitors()` | Monitors held when this info was captured | Empty array may mean it wasn’t requested |
| `getLockedSynchronizers()` | Ownable synchronizers held | Does not list every wait primitive |
| `getBlockedCount()` | Count of monitor entry blocks | Not per-event duration |
| `getBlockedTime()` | Total monitor block time when contention monitoring is enabled | May be `-1` and adds overhead |
| `getWaitedCount()` | Wait count per API semantics | Does not indicate missed signals |
| `getWaitedTime()` | Cumulative wait time when enabled/supported | Not a latency histogram |

`ThreadMXBean.findMonitorDeadlockedThreads()` finds object-monitor cycles; `findDeadlockedThreads()` can also find cycles with **ownable synchronizers** when supported by the JVM. However, neither method is a general detector for all stuck/livelock/starvation/queue-wait issues, and neither replaces JFR/tracing.

### 8.5 Virtual Threads and Version Limitations

Java 17 lacks finalized virtual threads; Java 21 has them. With virtual threads, stack dumps and handling of `synchronized`/monitor pinning/diagnostic support **differ by JDK release**. `ThreadMXBean` in Java 21 targets **platform threads**; a pool with only a few carrier threads does not prove only a few virtual tasks exist. Do not treat `dumpAllThreads(true,true)` as a complete inventory of virtual threads. If the system uses virtual threads, choose tools/formats/JFR suited to that running JDK.

## 9. Reading Code and Building a Dependency Graph to Find Root Cause

### 9.1 Each Edge Must Specify “Waiting on What”

An illustrative graph:

```text
request-B -- wants intrinsic monitor M --> request-A
request-C -- wants intrinsic monitor M --> request-A
request-A -- waits for DB connection --> DB pool
```

This is a **lock convoy**, not necessarily a Java-level deadlock. If `request-A` can obtain a connection and exit the monitor, the waiters can progress. Diagnosing root cause requires inspecting the DB pool, timeouts, and why the critical section wraps DB I/O.

Another graph:

```text
thread-A -- holds lock-X; waits lock-Y --> thread-B
thread-B -- holds lock-Y; waits lock-X --> thread-A
```

When owner and wait edges are verified **within the same JVM/snapshot**, this cycle is consistent with deadlock. Distinguish whether `lock-X/Y` are monitors or ownable synchronizers to choose the right detector and lock-order fix.

### 9.2 Signal Dependencies Do Not Always Have a Lock Owner

Example:

```text
consumer -- Condition.await() --> signal by producer
producer -- waits for executor slot --> thread pool
all pool threads -- waiting for consumer result --> consumer
```

Not every edge here has an object monitor or ownable owner. This can be **executor/thread-pool starvation** or a circular wait protocol, even though `findDeadlockedThreads()` returns `null`. You must read the producer/consumer architecture, queue capacity, callbacks, and signal conditions. Never invent a fake owner from `ConditionObject`.

### 9.3 Diagnostic Questions in Order

1. **Right JVM?** PID + process start time, container/host scope, UTC timestamp.
2. **Abnormal target?** Request p95/p99, throughput, queue size, timeouts, resource pressure.
3. **Waiting on a monitor/lock or waiting on a condition?** State + stack + blocker.
4. **If waiting on a lock, who is the owner?** Lock identity, `- locked`, ownable section, owner ID.
5. **If waiting on a signal, who is responsible for sending it?** Predicate, producer, notify/signal/unpark, cancellation.
6. **Is the owner/producer making progress?** Multiple snapshots and application metrics.
7. **Is it a definite cycle or just a chain?** Monitor/ownable graph vs. DB/executor/event dependencies.
8. **What changed near incident onset?** Deployment, load, flags, thread pool size, dependency latency.
9. **Does the fix preserve invariants and security?** Never arbitrarily call unlock/notify/interrupt on a production JVM.

## 10. Complete Java 17+ Example: Observing All Five Wait Types in One JVM

The example has two modes to separate **verifiable theoretical output** from **non-deterministic runtime snapshots**:

- **Default:** only prints the semantic table, deterministic stdout.
- **`--live`:** creates platform threads in the demo JVM itself. They simulate monitor owner/contender, ReentrantLock owner/contender, `Object.wait` waiter, `Condition.await` waiter, and `LockSupport.park` waiter; takes a snapshot via `ThreadMXBean`, then releases everything.

**Safety of the example:** creates no intentional deadlock, does not attach to any other JVM, does not send notify/unpark to unrelated threads; uses condition flags, latches, and `finally`. Snapshots are still subject to races, so live lines have no fixed deterministic stdout.

Save the file `SyncDiagnosticDemo.java`:

```java
import java.lang.management.ManagementFactory;
import java.lang.management.ThreadInfo;
import java.lang.management.ThreadMXBean;
import java.util.concurrent.CountDownLatch;
import java.util.concurrent.TimeUnit;
import java.util.concurrent.atomic.AtomicBoolean;
import java.util.concurrent.locks.Condition;
import java.util.concurrent.locks.LockSupport;
import java.util.concurrent.locks.ReentrantLock;

public class SyncDiagnosticDemo {
    static void printRules() {
        System.out.println("SYNCHRONIZED_CONTENDER=BLOCKED_ON_MONITOR");
        System.out.println("REENTRANT_LOCK_CONTENDER=USUALLY_PARKING");
        System.out.println("OBJECT_WAIT=RELEASES_ITS_MONITOR");
        System.out.println("CONDITION_AWAIT=RELEASES_ASSOCIATED_LOCK");
        System.out.println("LOCK_SUPPORT_PARK=DOES_NOT_RELEASE_LOCKS");
        System.out.println("WAITING_THREAD=NOT_AUTOMATICALLY_DEADLOCKED");
    }

    static void waitForRelease(CountDownLatch release) {
        try {
            release.await();
        } catch (InterruptedException e) {
            Thread.currentThread().interrupt();
        }
    }

    static void printInfo(String alias, ThreadInfo info) {
        if (info == null) {
            System.out.println(alias + ".snapshot=UNAVAILABLE");
            return;
        }
        System.out.println(alias + ".state=" + info.getThreadState());
        System.out.println(alias + ".lock_info_present="
                + (info.getLockInfo() != null));
        System.out.println(alias + ".owner_known="
                + (info.getLockOwnerId() >= 0));
        System.out.println(alias + ".held_monitors="
                + info.getLockedMonitors().length);
        System.out.println(alias + ".held_ownable="
                + info.getLockedSynchronizers().length);
    }

    static void live() throws Exception {
        ThreadMXBean mx = ManagementFactory.getThreadMXBean();
        if (!mx.isObjectMonitorUsageSupported()
                || !mx.isSynchronizerUsageSupported()) {
            System.out.println("LIVE_LOCK_DETAILS=UNSUPPORTED");
            return;
        }

        Object monitor = new Object();
        Object waitObject = new Object();
        Object parkBlocker = new Object();
        ReentrantLock exclusive = new ReentrantLock();
        ReentrantLock conditionLock = new ReentrantLock();
        Condition changed = conditionLock.newCondition();

        CountDownLatch readyOwners = new CountDownLatch(2);
        CountDownLatch releaseOwners = new CountDownLatch(1);
        CountDownLatch readyWaiters = new CountDownLatch(3);
        AtomicBoolean objectGo = new AtomicBoolean(false);
        AtomicBoolean conditionGo = new AtomicBoolean(false);
        AtomicBoolean parkGo = new AtomicBoolean(false);

        Thread monitorOwner = new Thread(() -> {
            synchronized (monitor) {
                readyOwners.countDown();
                waitForRelease(releaseOwners);
            }
        }, "demo-monitor-owner");

        Thread lockOwner = new Thread(() -> {
            exclusive.lock();
            try {
                readyOwners.countDown();
                waitForRelease(releaseOwners);
            } finally {
                exclusive.unlock();
            }
        }, "demo-lock-owner");

        Thread monitorContender = new Thread(() -> {
            synchronized (monitor) {
                // Only entered after monitorOwner has released the lock.
            }
        }, "demo-monitor-contender");

        Thread lockContender = new Thread(() -> {
            exclusive.lock();
            try {
                // Only entered after lockOwner unlocks.
            } finally {
                exclusive.unlock();
            }
        }, "demo-lock-contender");

        Thread objectWaiter = new Thread(() -> {
            synchronized (waitObject) {
                readyWaiters.countDown();
                while (!objectGo.get()) {
                    try {
                        waitObject.wait();
                    } catch (InterruptedException e) {
                        Thread.currentThread().interrupt();
                        break;
                    }
                }
            }
        }, "demo-object-waiter");

        Thread conditionWaiter = new Thread(() -> {
            conditionLock.lock();
            try {
                readyWaiters.countDown();
                while (!conditionGo.get()) {
                    try {
                        changed.await();
                    } catch (InterruptedException e) {
                        Thread.currentThread().interrupt();
                        break;
                    }
                }
            } finally {
                conditionLock.unlock();
            }
        }, "demo-condition-waiter");

        Thread parkWaiter = new Thread(() -> {
            readyWaiters.countDown();
            while (!parkGo.get() && !Thread.currentThread().isInterrupted()) {
                LockSupport.park(parkBlocker);
            }
        }, "demo-park-waiter");

        Thread[] threads = {
            monitorOwner, monitorContender,
            lockOwner, lockContender,
            objectWaiter, conditionWaiter, parkWaiter
        };
        String[] aliases = {
            "MONITOR_OWNER", "MONITOR_CONTENDER",
            "LOCK_OWNER", "LOCK_CONTENDER",
            "OBJECT_WAITER", "CONDITION_WAITER", "PARK_WAITER"
        };

        try {
            monitorOwner.start();
            lockOwner.start();

            if (!readyOwners.await(3, TimeUnit.SECONDS)) {
                System.out.println("LIVE_SETUP=OWNERS_NOT_READY");
                return;
            }

            monitorContender.start();
            lockContender.start();
            objectWaiter.start();
            conditionWaiter.start();
            parkWaiter.start();

            if (!readyWaiters.await(3, TimeUnit.SECONDS)) {
                System.out.println("LIVE_SETUP=WAITERS_NOT_READY");
                return;
            }

            // Best-effort: wait for clearer states, does not create an atomic snapshot.
            for (int attempt = 0; attempt < 100; attempt++) {
                boolean monitorBlocked =
                        monitorContender.getState() == Thread.State.BLOCKED;
                boolean ownableWait =
                        lockContender.getState() == Thread.State.WAITING
                        || lockContender.getState() == Thread.State.TIMED_WAITING;
                if (monitorBlocked && ownableWait) {
                    break;
                }
                Thread.sleep(10);
            }

            long[] ids = new long[threads.length];
            for (int i = 0; i < threads.length; i++) {
                ids[i] = threads[i].getId();
            }
            ThreadInfo[] info = mx.getThreadInfo(ids, true, true);
            for (int i = 0; i < threads.length; i++) {
                printInfo(aliases[i], info[i]);
            }
        } finally {
            releaseOwners.countDown();

            synchronized (waitObject) {
                objectGo.set(true);
                waitObject.notifyAll();
            }

            conditionLock.lock();
            try {
                conditionGo.set(true);
                changed.signalAll();
            } finally {
                conditionLock.unlock();
            }

            parkGo.set(true);
            LockSupport.unpark(parkWaiter);

            for (Thread thread : threads) {
                if (thread.isAlive()) {
                    thread.interrupt(); // Fallback exit path if the demo is delayed.
                    thread.join(2000);
                }
            }
        }
    }

    public static void main(String[] args) throws Exception {
        printRules();
        if (args.length == 1 && "--live".equals(args[0])) {
            live();
        }
    }
}
```

Compile and run the default mode:

```bash
javac SyncDiagnosticDemo.java
java SyncDiagnosticDemo
```

**Exact stdout of the default mode**:

```text
SYNCHRONIZED_CONTENDER=BLOCKED_ON_MONITOR
REENTRANT_LOCK_CONTENDER=USUALLY_PARKING
OBJECT_WAIT=RELEASES_ITS_MONITOR
CONDITION_AWAIT=RELEASES_ASSOCIATED_LOCK
LOCK_SUPPORT_PARK=DOES_NOT_RELEASE_LOCKS
WAITING_THREAD=NOT_AUTOMATICALLY_DEADLOCKED
```

These are **knowledge assertions printed by the code**, not empirical measurements. To observe live threads:

```bash
java SyncDiagnosticDemo --live
```

With `--live`, the program prints the six model lines first, followed by `ALIAS.state`, `ALIAS.lock_info_present`, `ALIAS.owner_known`, `ALIAS.held_monitors`, and `ALIAS.held_ownable` for the seven threads. Values vary by JDK/scheduler and snapshot timing; for example, you may see `MONITOR_CONTENDER.state=BLOCKED`, `LOCK_CONTENDER.state=WAITING`, `OBJECT_WAITER.state=WAITING`, `CONDITION_WAITER.state=WAITING`, `PARK_WAITER.state=WAITING`, yet **those are conditional expectations, not verified deterministic stdout**.

### 10.1 Why Does the Demo Have an Owner That Is WAITING?

`monitorOwner` holds an intrinsic monitor and `lockOwner` holds a `ReentrantLock` while waiting on `releaseOwners.await()`. Because they still hold the locks, the two contenders must wait. This illustrates a **WAITING owner causing contention**: even though the owner is `WAITING` on a latch, it has never released the monitor/ReentrantLock. The purpose is to learn to ask “why is the owner waiting?”, not to recommend holding mutexes while awaiting latches in production.

### 10.2 Why Do Object.wait and Condition.await Behave Differently?

`objectWaiter` calls `waitObject.wait()` inside `synchronized`, releasing the `waitObject` monitor while waiting. `conditionWaiter` calls `changed.await()` while holding `conditionLock`, releasing the associated `ReentrantLock` and reacquiring it upon waking. `parkWaiter` uses `LockSupport.park(parkBlocker)` and only proceeds once `parkGo` is set / unparked / interrupted or on spurious return; `park` does not manipulate any lock itself.

### 10.3 Why Not Print Exact Wait Durations?

`ThreadInfo` is a snapshot, not a stopwatch for a single wait. `getBlockedTime()`/`getWaitedTime()` are cumulative times and can be `-1` if contention monitoring is disabled/unsupported. The demo code does not mutate management flags and does not try to compute p95 from those counters. When analyzing real latency, use application histograms, JFR, or synchronized-clock traces.

### 10.4 Cleanup After the Snapshot

The `finally` block releases latches, sets predicates, calls `notifyAll`, `signalAll`, and `unpark`, and requests interrupts as a fallback exit path. `join(2000)` bounds how long main waits to join, **without guaranteeing** that arbitrary threads in a real application have all exited when the deadline passes; the example is designed to finish cleanly under normal conditions.

If you want to run this sample code in CI, run it in a separate process with an overall timeout, and do not repeat tightly in production. Thread states naturally race, so automated tests should assert **invariants/predicates and clean termination**, rather than asserting every JVM prints a specific `WAITING` state at a given millisecond.

## 11. Three Common Wait Bug Patterns and How to Diagnose Them

### 11.1 Lost Signal Due to a Broken Protocol

**Symptoms:** consumers stay `WAITING` in `Object.wait` or `Condition.await` forever even though producers “called notify.”

**Questions to ask:**

- Are predicates like `queueNotEmpty` or `ready` actually updated before signaling?
- Do both producer and consumer use the same monitor or the same associated lock?
- Does the waiter use `while (!condition) await()` or call wait blindly?
- Did the signal happen before the waiter arrived, with **no state** preserving the condition?
- Did an exception or early return skip the signal?
- Did a redeploy/DI change a lock object so the two sides wait on **two different objects**?

**Fix:** the condition must be state with proper visibility/happens-before protected by a lock or atomic; signaling must accompany state updates; waiters must always recheck. Never sprinkle `notifyAll` randomly to “cure a hang” if the underlying protocol is wrong.

### 11.2 Owner Holding a Mutex While Waiting on External Work

**Symptoms:** many threads `BLOCKED` on the same monitor or `WAITING/parking` on the same `ReentrantLock`; meanwhile the owner is sleeping, waiting on DB/network, a latch, or task-pool completion.

**Hypotheses:** overly broad critical section or circular dependency. Check lock hold times / queue metrics and the owner’s stack across multiple snapshots. If the owner needs a result from a thread blocked by that very lock, it may be a cycle. If the owner needs a DB response while the DB is still responsive, it may be a long hold / convoy.

**Fix:** shrink critical sections, keep remote I/O out of mutexes, add timeouts, and design safe transaction/state updates. Never fix by calling `unlock` from another thread or restarting immediately before collecting evidence.

### 11.3 Lock Order Inversion

**Symptoms:** thread A holds L1 and wants L2; thread B holds L2 and wants L1. These may be two monitors or ownable locks.

**Design remediation:** standardize lock acquisition order across all code paths, reduce lock nesting, isolate shared-state ownership, use timed acquisition with proper rollback/cancellation, and test under contention. Pick a global ordering (e.g., by lock ID / ordering key) if the domain allows; never use thread-dependent random orders.

## 12. Distinguishing Deadlock, Starvation, Livelock, and Long Contention

| Phenomenon | Indicators | What a Thread Dump May Show | What Must Be Proven |
| --- | --- | --- | --- |
| **Deadlock** | Dependency cycle with no exit | Threads A/B waiting on each other’s locks, or broader dependency cycle | Owner/held-lock edges in the same snapshot, unable to progress |
| **Lock contention** | Many waiters on the same lock | `BLOCKED` on monitor, or AQS park | Owner and lock-holding duration; whether progress occurs |
| **Starvation** | Some threads go unserved/resource-deprived for long periods | Pool threads `WAITING`, large queue, executor short on workers | Scheduling/resource allocation and elapsed time |
| **Livelock** | Threads remain active but finish no work | `RUNNABLE`/churning stacks changing continuously | False progress counters, retry loops, low throughput |
| **Missed signal** | Condition waiter does not wake even though business state should have changed | `WAITING (on object monitor)` or `Condition.await` park | Predicate/producer/signal protocol |
| **External I/O hang** | Thread waits on DB/network/disk | `WAITING`/`RUNNABLE`/native stack depending on API | Dependency timeouts, TCP/DB health, whether owner holds locks |

`findDeadlockedThreads() == null` only says **no cycle types supported by the detector were found at that instant**. It does not rule out I/O hangs, pool starvation, missing signals, or virtual-thread liveness issues outside API scope.

## 13. ThreadInfo, Monitoring, and Proving Duration

### 13.1 Taking Purposeful Multiple Snapshots

A single thread dump is only **one snapshot**. To state “thread A held the lock for 30 seconds,” you need a series of timestamped snapshots from the **same JVM** identity, or instrumentation measuring lock hold duration. Example:

```text
12:00:00  T1 --holds M--> 25 waiters
12:00:05  T1 --holds M--> 32 waiters
12:00:10  T1 --holds M--> 40 waiters
```

This is **illustrative** data; it suggests monitor M is a sustained bottleneck, yet does not explain why T1 holds it so long. Stack/source and application metrics are needed. If the PID/JVM restarted between snapshots, Object IDs lose meaning across runs.

### 13.2 Contention Monitoring Is Not Free

If `ThreadMXBean.isThreadContentionMonitoringSupported()` returns true, monitoring can be enabled to gather accumulated blocked/waited times. However, calling `setThreadContentionMonitoringEnabled(true)` mutates JVM state and incurs overhead. Perform it only with authorization/runbook approval when needed, never as a default in read-only demos.

**`BLOCKED` count does not equal `BLOCKED` time.** Total time divided by count yields only a rough mean, not p95 or max lock wait. To analyze tail latency, use JFR events, code instrumentation, or appropriate latency histograms.

### 13.3 Owner IDs Only Have Meaning Within the Right JVM

`ThreadInfo.getThreadId()` is a Java thread ID; `nid` in HotSpot dumps is the OS native thread ID on some platforms. Never treat `nid=0x...` as `ThreadInfo.getThreadId()` and compare them directly. `getLockOwnerId()` is a Java thread ID if known, `-1` if none/unknown. A thread parked on a condition/latch does not necessarily have an owner; never invent an owner just because `getLockInfo() != null`.

### 13.4 Thread Dumps Can Miss Data

- JVM/VM version does not support locked synchronizer usage.
- Output truncated because thread count is too large.
- Thread terminated prior to capture (`ThreadInfo == null`).
- Tool lacks attach permissions or runs in a different container PID namespace.
- Virtual threads are not covered by the API/tool in use.
- Overloaded JVM slows capture so the event passes first.

Therefore “no owner visible in dump” means **missing evidence**, not proof that no owner exists.

## 14. Logs, JFR, and Metrics That Complement Thread Dumps

A solid diagnosis connects thread dumps with other data sources:

| Source | What It Answers | Limitations |
| --- | --- | --- |
| Thread dump / ThreadMXBean | Thread state, stack, awaited/held locks, deadlock graph | Snapshot; lacks full event history |
| JFR | Monitor enter/park, thread events, CPU, execution sampling when recording is configured | Event availability/thresholds and overhead depend on JDK/recording |
| Application traces | Which request is waiting on task/DB/lock, latency path | Requires instrumentation and suitable sampling |
| Thread pool/queue metrics | Active threads, queue depth, rejections, completed tasks | Does not directly find owners or missed signals |
| OS/cgroup CPU | CPU saturation/throttling, scheduling pressure | Does not directly explain Java lock semantics |
| DB/network metrics | Pool exhaustion, slow queries, timeouts, dependency errors | Does not show which lock is held in code without stack correlation |
| GC logs/JFR | Coinciding pauses/GC events | Never blame every `WAITING`/`BLOCKED` on GC |

When capturing JFR during an incident, check whether the recording profile enables Java monitor enter/park events with appropriate thresholds; event thresholds may filter out short waits. A JFR stack event adds timestamps and durations, yet does not turn every `LockSupport.park` into a primitive with an owner.

### 14.1 Avoid Creating Useless Artifact Overload

Capturing hundreds of back-to-back thread dumps on a 10,000-thread JVM creates heavy overhead and huge artifacts; when a system is already overloaded, this makes matters worse. Choose targeted sampling, e.g., a few snapshots spaced a few seconds apart with timestamps, or size/time-bounded JFR if permitted. No single cadence fits every JVM.

### 14.2 Information Security When Sharing Dumps

Thread names, class/package names, file paths, request/session identifiers, URLs, and credentials inside stack frames/messages can be sensitive data. Store raw artifacts in repositories with proper RBAC/retention; shared excerpts should keep only aliases, lock-identity mappings, relevant stack slices, and timelines. Never randomize lock IDs inconsistently so owner-wait graphs break; if redacting, use a consistent mapping **within one incident**.

## 15. Quick-Fix Advice to Avoid

| Common “Quick Fix” | Why It Is Dangerous/Wrong | Right Direction |
| --- | --- | --- |
| Calling `notifyAll` on any arbitrary object | Must notify the exact wait-set and update the predicate | Identify the right shared state + monitor and protocol |
| Calling `Condition.signal` without holding the associated lock | Violates `ReentrantLock` Condition contract | Acquire lock, update predicate, signal inside `try/finally` |
| Calling `unlock` on behalf of the owner | `IllegalMonitorStateException`, violates ownership | Fix owner code, `finally`, and cancellation |
| Replacing `await` directly with `park` | `park` does not release locks, risking holding mutex while waiting | Keep the `Condition` abstraction for wait-sets |
| Adding `Thread.sleep` to “avoid a race” | Only masks scheduling bugs without proper happens-before | Use valid conditions/predicates/locks/latches |
| Using `if` instead of `while` around `wait/await` | Spurious wakeups/races can violate invariants | Use a `while` loop checking the predicate |
| Treating `WAITING` as idle | Thread may hold locks or wait on a blocked producer | Inspect held-locks, owners, and dependency graphs |
| Increasing thread pools indefinitely | Can increase contention, CPU, and context switches | Investigate queue/owner/blocking dependencies |
| Enabling `ReentrantLock` fairness to cure everything | Does not shorten long critical sections and may cut throughput | Reduce lock scope, measure hold/wait times |
| Using `Thread.stop()` to break locks | Unsafe, can break invariants | Valid cancellation, timeouts, or runbook-guided restart |
| Interpreting `findDeadlockedThreads()==null` as “not hung” | Does not cover all liveness failures | JFR, traces, queue/protocol analysis |
| Copying lock IDs from a dump after a restart | Object identities differ | Compare within the same JVM instance and snapshot |
| Capturing `jcmd Thread.print` on the wrong PID | May impact or misread the wrong service | Verify PID/start time/namespace |
| Sharing raw dumps in open channels | Can leak metadata/identifiers | Controlled redaction and RBAC |

## 16. Incident Procedure: From Symptom to Cause and Fix

1. **Verify target:** service, JVM instance/PID, process start time, JDK release, host/container namespace.
2. **Record symptoms and window:** request latency, error rate, throughput, thread pool queues, CPU, DB/network metrics.
3. **Capture valid snapshots:** `jcmd PID Thread.print -l` or `ThreadMXBean` with monitor/synchronizer support; record UTC timestamps and options.
4. **Group threads:** `BLOCKED` monitor entry; `WAITING/TIMED_WAITING` on `Object.wait`, `Condition.await`, AQS/`ReentrantLock`, `LockSupport.park`, idle pool, I/O.
5. **For lock contention:** find lock identity and owner, read held monitors/ownable synchronizers, and inspect the owner’s stack.
6. **For condition waits:** find the predicate, producer, signal/notify/unpark protocol, and verify queues/threads have resources for the producer to run.
7. **Draw the graph:** waiter → owner or waiter → signal producer; distinguish cycles, long holds, queue starvation, and missed signals.
8. **Re-capture in a controlled way:** confirm whether state persists, waiters grow, and the owner’s stack progresses.
9. **Cross-check other evidence:** JFR monitor/park events, application traces, DB pool, GC/CPU/cgroup, and recent deployments.
10. **Choose a minimal invariant-preserving change:** shrink lock scope, standardize lock order, add timeouts/cancellation, fix signal/predicate, avoid blocking I/O under mutexes.
11. **Test under load and failure modes:** missed signals, spurious wakeups, interrupts, timeouts, double unlocks, restarts, pool exhaustion.
12. **Post-check:** compare p95/p99 latency, throughput, queues, lock wait/hold distributions, deadlock detection, and error rates; never declare fixed solely because one later dump has fewer `WAITING` threads.

If owner/predicate/stack data is insufficient, report “unverified” rather than inferring “Java deadlock” from a single `Unsafe.park` line.

## 17. Per-Mechanism Diagnostic Checklist

### synchronized

- [ ] Is the waiting thread `BLOCKED` on monitor entry or simply `WAITING` elsewhere?
- [ ] Does the `waiting to lock` ID match the owner’s `- locked` ID in the same dump?
- [ ] Is the owner holding the monitor during sleep/I/O/await/long CPU work?
- [ ] Is there lock-order inversion or many threads sharing one monitor?

### ReentrantLock

- [ ] Is there an AQS/`ReentrantLock.lock` stack and a `...Sync` blocker?
- [ ] Is the owner identified via `Locked ownable synchronizers` / owner ID?
- [ ] Remember `getQueueLength` is only an estimate, not absolute proof?
- [ ] Are `tryLock`/`lockInterruptibly`/timeout/cancellation semantics used properly?
- [ ] Is `unlock` in `finally` on the exact owning thread?

### Object.wait / notify

- [ ] Is `wait` called while holding the right monitor?
- [ ] Is the shared predicate read/written under the lock and checked with `while`?
- [ ] Does the producer actually update the predicate and call notify/signal on the right object?
- [ ] The waiter released the waited monitor, but what other monitors does it still hold?
- [ ] Could missed signals, spurious wakeups, or mishandled timeouts/interrupts exist?

### Condition

- [ ] Do `await/signal` use the exact `Condition` of the associated `Lock`?
- [ ] Are `lock.lock()`/`unlock()` scoped properly with `finally`?
- [ ] `await` releases/reacquires the lock; did anyone mistake a waiter for an owner?
- [ ] Does the producer call `signal/signalAll` after updating the predicate while holding the lock?
- [ ] With multiple condition queues, could the wrong queue be signaled or the producer be unscheduled?

### LockSupport.park

- [ ] Is there a clear blocker object or only bare `Unsafe.park`?
- [ ] Does the thread hold any monitor/`ReentrantLock` while parked?
- [ ] Is `unpark(thread)` called with the right started thread reference?
- [ ] Are there volatile/atomic predicates, `while`-loop rechecks, and spurious-wakeup handling?
- [ ] Could interrupt status cause `park` to return repeatedly in a spin loop?
- [ ] Avoid mistaking a 1-bit permit for a multi-signal queue?

## 18. Self-Check Exercises

**Q1.** Thread A is `WAITING` in `CountDownLatch.await()` yet has `- locked <M>`; Thread B is `BLOCKED` waiting for M. Is A guaranteed to have released M because it is `WAITING`?

**Answer:** No. Latch await does not release monitor M. A still owns M; B waits for it. You must check who will countDown the latch and whether it needs monitor M to do so.

**Q2.** Thread B is `WAITING (parking)` inside `ReentrantLock.lock()`. Must a state be `Thread.State.BLOCKED` to be called lock contention?

**Answer:** No. `BLOCKED` applies to monitor entry; `ReentrantLock` contention typically uses AQS/park and shows `WAITING/TIMED_WAITING`. Inspect the `...Sync` blocker and owner.

**Q3.** A thread calls `Object.wait()` inside `synchronized(lock)`. Does it keep holding `lock` while waiting?

**Answer:** No, `wait()` releases the monitor of the exact object it was called on while waiting and reacquires it before returning. It may still hold other monitors.

**Q4.** Can `Condition.await()` be replaced by `LockSupport.park()` while preserving behavior?

**Answer:** No. `Condition.await()` releases and reacquires its associated lock; `park` only waits for permit/interrupt/spurious wakeup and releases no lock. Direct replacement can prevent the producer from ever acquiring the lock to signal.

**Q5.** A producer calls `unpark(consumer)` before the consumer calls `park`. What happens?

**Answer:** `unpark` makes the permit available so the next `park` consumes it and returns immediately; multiple permits do not accumulate. State/predicates are still required in case of spurious returns or another call consuming the permit.

**Q6.** A thread is `WAITING` in `ConditionObject.await` with `getLockOwnerId() == -1`. Does that mean there is no bug?

**Answer:** No. The waiter is awaiting a condition signal, and the waited object may not have a mutex-style owner. You must trace the producer/predicate/signal path and progress capability.

**Q7.** `notifyAll` was called, yet the waiter does not run immediately. Why?

**Answer:** The signaling thread may still hold the monitor; the waiter must reacquire it before `wait()` returns. Scheduling and predicate rechecks can also keep it waiting.

**Q8.** 100 threads are `BLOCKED` on the same monitor ID while one owner waits on the DB. Can we call this “100 deadlocks”?

**Answer:** No. This may be a single lock convoy behind an owner holding a critical section too long. Calling it deadlock requires verifying an unresolvable dependency cycle; inspect the DB and source code as well.

**Q9.** `findDeadlockedThreads()` returns `null` while the service is hung. What should we conclude?

**Answer:** No cycles supported by the detector were found in the snapshot. The service can still hang due to missed signals, executor starvation, I/O, or other liveness failures.

**Q10.** `getBlockedTime()` returns `-1`. Does that mean the JVM has no monitor contention?

**Answer:** No. Contention monitoring may be disabled or unsupported. `-1` does not mean 0 ms. Check support/configuration and enable monitoring only if authorized.

**Q11.** A thread is interrupted while parked and keeps calling `park` without handling the flag. What is the risk?

**Answer:** Subsequent `park` calls may return immediately due to the interrupted status, causing a busy loop. You must enforce a cancellation/interrupt policy alongside the predicate.

**Q12.** Why is a single thread dump insufficient to say an owner held a lock for 30 seconds?

**Answer:** A snapshot shows only one point in time. You need multiple snapshots with timestamps/JVM identity and lock hold/wait duration instrumentation or JFR events.

## References

- [Java SE 21 — ThreadInfo](https://docs.oracle.com/en/java/javase/21/docs/api/java.management/java/lang/management/ThreadInfo.html): state, lock owner, waiting object, monitors, and ownable synchronizers.
- [Java SE 21 — ThreadMXBean](https://docs.oracle.com/en/java/javase/21/docs/api/java.management/java/lang/management/ThreadMXBean.html): thread dumps, contention monitoring, and deadlock APIs.
- [Java SE 21 — Object](https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/lang/Object.html): `wait`, `notify`, `notifyAll`, monitor ownership, and spurious wakeups.
- [Java SE 21 — ReentrantLock](https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/util/concurrent/locks/ReentrantLock.html): lock ownership, timed/interruptible acquisition, queue instrumentation, and fairness.
- [Java SE 21 — Condition](https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/util/concurrent/locks/Condition.html): await/release/reacquire, signals, and independent condition queues.
- [Java SE 21 — LockSupport](https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/util/concurrent/locks/LockSupport.html): permits, park/unpark, blockers, interrupts, and spurious wakeups.
- [Oracle JDK 21 — jcmd](https://docs.oracle.com/en/java/javase/21/docs/specs/man/jcmd.html): `Thread.print` and JDK-specific options.
- [OpenJDK JEP 444 — Virtual Threads](https://openjdk.org/jeps/444): virtual thread characteristics and release-specific observability limits.

**Takeaway:** when diagnosing Java synchronization, do not only ask “is the thread WAITING or BLOCKED?”. Ask **is it waiting on a monitor or a signal/permit? what locks does it hold? who can make the condition true?** `Object.wait` and `Condition.await` release **the exact** associated lock while waiting; `LockSupport.park` releases no locks; `ReentrantLock` contention typically appears as parking; `synchronized` contention typically appears as `BLOCKED`. **Combining state + stack + lock identity + owner/predicate + time** is what separates contention, missed signals, starvation, and deadlock.
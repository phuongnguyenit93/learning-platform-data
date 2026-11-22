# `wait`, `notify`, `notifyAll` and the Relationship Between the Wait Set and Monitor Ownership in Java

In Java multithreaded programming, `Object.wait()`, `Object.notify()`, and `Object.notifyAll()` are the trio of primitives for **coordinating state between threads using an intrinsic monitor**. These methods are not commands to "pause/resume a thread at will," nor are they equivalent to `Thread.sleep()`. To use them correctly, you must understand **three different things** at the same time:

1. **Monitor ownership:** which thread currently owns the object's intrinsic lock?
2. **Wait set:** which threads have voluntarily relinquished the monitor via `wait()` on that exact object and are waiting for an event to be considered for resumption?
3. **Business condition (guarded predicate):** what data indicates that the operation can proceed, for example `ready == true`, a non-empty queue, or a buffer with available space?

Core principle: **`wait()` may only be called when the thread owns the monitor of that exact object; it places the thread into the wait set and relinquishes all ownership of that monitor. `notify()`/`notifyAll()` also require ownership of the same monitor, but do not release the monitor immediately. A signaled thread can only return from `wait()` after re-acquiring the monitor.**

Because a thread can wake up due to notification, interruption, timeout, or *spurious wakeup*, **always check the condition with `while` inside the same synchronized region**:

```java
synchronized (lock) {
    while (!condition) {
        lock.wait();
    }
    // Perform work when condition is true under the same monitor.
}
```

The snippet above is a **conceptual pattern**, not a standalone runnable file; `lock` and `condition` must have declarations and update logic. This lesson belongs to the **Threads and Synchronization** section, based on **Java SE 17 – JLS §17.1–17.4** and the `java.lang.Object` Javadoc. The standalone programs below use Java 17, include compilation instructions, have deterministic stdout on normal execution, and explain the unpredictable scheduling aspects.

## 1. Every Java Object Has a Monitor and a Wait Set

According to the Java Language Specification (`17.1, `17.2), an object is associated with:

- **Monitor:** the mutual exclusion mechanism used by `synchronized` blocks and synchronized methods.
- **Wait set:** the set of threads that have called `wait` on the object under valid conditions and have not yet completed the waiting phase according to JLS rules.

When an object is newly created, its wait set is **empty**. Adding/removing a thread from a wait set is modeled as atomic actions. Each object has its **own separate** wait set: calling `notifyAll` on object A does not wake up threads that are calling `wait` on object B.

```text
                       OBJECT lock
        ┌────────────────────────────────────┐
        │ Monitor: at any given time only    │
        │ one thread owns the monitor        │
        │                                    │
        │ Wait set: {T2, T3, ...}            │
        │ threads that called lock.wait()    │
        └────────────────────────────────────┘
                  ▲               │
     enter synchronized(lock)    lock.wait()
                  │               ▼
     T1 holds monitor      T2 yields monitor and waits
                  │               │
       lock.notifyAll()           │ removed from wait set
       while T1 still holds lock  ▼
                  │         T2 competes to re-acquire monitor
                  │               │
       T1 exits synchronized      │
          → unlock                ▼
                       T2 re-acquires lock, wait() returns
                       and only then continues checking condition
```

**Do not interpret this diagram as a scheduler with a FIFO entry queue guaranteed by the Java specification.** "Entry set/entry list", "monitor owner", and "wait set" are often drawn in JVM documentation to explain scheduling. The **wait set** and monitor ownership are semantics described by the JLS; monitor contention order, native queue structures, and fairness are not guaranteed according to textbook diagrams.

### 1.1. What Does Monitor Ownership Mean?

A thread acquires a monitor in one of the common ways:

```java
synchronized (lock) {
    // Thread currently owns the monitor of lock.
}

synchronized void instanceMethod() {
    // Owns the monitor of this.
}

static synchronized void classMethod() {
    // Owns the monitor of the corresponding Class object.
}
```

These are illustrative **snippets**; the two methods belong to an appropriate class. Note:

- `synchronized(lock)` locks **the exact instance that `lock` points to**.
- `synchronized instanceMethod()` locks **`this`**, not an arbitrary `lock` field.
- `static synchronized` locks the **Class object**, for example `Sample.class`, not an instance of `Sample`.
- `new Object()` creates a different monitor each time. You cannot use two unrelated monitors and expect `wait/notify` to communicate.
- A thread currently in `synchronized(other)` does not automatically have the right to call `lock.wait()`.

### 1.2. Reentrant Monitor

Intrinsic monitors in Java are **reentrant**: a thread that already holds a monitor can enter a synchronized block/method on the same object again without deadlocking itself.

```java
synchronized (lock) {
    synchronized (lock) {
        // Still only one thread owns lock; reentrant ownership.
    }
}
```

In the JLS model, if a thread holds the monitor of object `lock` through **n lock actions not yet matched by unlocks**, a valid `lock.wait()` call must **relinquish all n levels of ownership on that exact monitor**. When eligible to return, the thread must **re-acquire the same number of levels** to continue.

This is different from just "decrementing the lock count once". If `wait()` did not relinquish all lock ownership levels, another thread would not be able to enter the monitor to change state and send a notification in many cases.

## 2. Signatures of the Three `Object` API Groups

Java 17 defines:

```java
public final void wait() throws InterruptedException;
public final void wait(long timeoutMillis) throws InterruptedException;
public final void wait(long timeoutMillis, int nanos)
        throws InterruptedException;

public final native void notify();
public final native void notifyAll();
```

These signatures describe the API; they are not a runnable file. The untimed `wait()` version is equivalent to `wait(0L, 0)`; the `wait(long)` version with argument `0` waits indefinitely until a wakeup/interrupt/spurious wakeup event occurs, rather than "waiting 0 ms and returning".

| Method | Requires owning receiver's monitor? | Main effect |
| --- | --- | --- |
| `lock.wait()` | **Yes** | Adds current thread to `lock`'s wait set; relinquishes that monitor and waits for an event |
| `lock.wait(millis)` | **Yes** | Same as above, but allows timeout when the corresponding duration elapses |
| `lock.wait(millis, nanos)` | **Yes** | Timed wait with millisecond + valid nanosecond component |
| `lock.notify()` | **Yes** | Selects **an arbitrary thread** in `lock`'s wait set to allow it to compete for the lock again |
| `lock.notifyAll()` | **Yes** | Removes **all threads** currently in `lock`'s wait set so they can compete for the lock again |
| `Thread.sleep(...)` | **No** monitor required | Sleeps for a duration, **does not automatically release held monitors** |
| `Thread.join()` | Caller is not required to own target monitor | Waits for target thread to terminate per API, not a caller-written business signaling mechanism |

`wait`, `notify`, and `notifyAll` are all **instance methods of `Object`**, not static methods of `Thread`. To coordinate using monitor `queueLock`, call `queueLock.wait()`/`queueLock.notifyAll()`.

## 3. What Steps Does a Valid `wait()` Call Go Through?

According to JLS 17.2.1, a thread T calling `m.wait()` after holding the monitor of object `m`:

1. Verifies that T **owns monitor `m`**. If not, throws `IllegalMonitorStateException`.
2. Handles argument conditions/interrupted status per specification.
3. T is **placed into the wait set of `m`**, and relinquishes **all n lock acquisitions** held on `m`.
4. T remains in the waiting state until removed from the wait set by notification, interrupt, timed wait expiry, or spurious wakeup.
5. **T attempts to re-acquire monitor `m`**, with the appropriate reentrancy depth.
6. Only **after re-acquiring the monitor** does `wait()` return normally or throw `InterruptedException` accordingly.

```text
T is running inside synchronized(m)
    │ owns monitor m
    ▼
m.wait()
    │ add T to wait set(m), release monitor m
    ▼
T waits (does not execute code after wait)
    │ notify / notifyAll / interrupt / timeout / spurious
    ▼
T leaves wait set(m)
    │
    ▼
T MUST re-compete for monitor m
    │ if another thread holds m → still cannot enter
    ▼
T re-acquires monitor m (restored reentrancy)
    │
    ├─ interrupted per applicable case → InterruptedException
    └─ normal → returns to check predicate in while
```

**Core point:** Leaving the wait set ≠ owning the monitor. "Has been `notify`'d" is only a step allowing the thread to resume competing for monitor ownership; it is not a command forcing it to run immediately.

### 3.1. Which Monitor Does `wait()` Release?

It only releases the monitor of **the object on which `wait()` is called**, not all monitors that the thread is holding.

```java
synchronized (outer) {
    synchronized (inner) {
        inner.wait();
        // Still holding outer while waiting on inner!
    }
}
```

This is a snippet that needs declarations for `outer`/`inner` and `InterruptedException` handling. If another thread needs monitor `outer` before it can modify data and call `inner.notifyAll()`, you can create a **deadlock**. Do not rely on `wait()` to automatically release all held locks.

### 3.2. Is a Woken Thread Guaranteed to Run Immediately?

No. `notifyAll()` can cause many threads to leave the wait set, but they can only acquire the monitor **one thread at a time**. The thread that just called `notifyAll()` still holds the monitor until it exits the `synchronized` block or returns from the synchronized method.

In examples, a notifier might update `ready=true` and call `notifyAll()`, but if it also performs time-consuming computations **inside the same synchronized block**, waiters must wait for the lock to be released. This is why critical sections should be kept short, avoiding unnecessary blocking I/O inside a monitor.

## 4. `notify()` and `notifyAll()` Modify the Wait Set, Not Release the Monitor

### 4.1. Which Thread Does `notify()` Wake Up?

If `m`'s wait set is non-empty, `m.notify()` **selects an arbitrary thread** from the wait set to remove from the set. Java **does not guarantee**:

- Selecting the thread that entered the wait set earliest (FIFO).
- Selecting the thread with the highest priority.
- Selecting a thread whose predicate is currently true.
- Selecting by name/id order.
- Fair treatment by wait count.
- That the selected thread will acquire the monitor before other competing threads.

If the wait set is **empty**, the notification is **not saved as a token for a thread that waits later**. This is the source of **lost notification** bugs if code relies solely on the notify call event without storing condition state.

### 4.2. `notifyAll()` Wakes All Threads, Then What Do They Do?

`notifyAll` moves all threads currently in the wait set of **the receiver object** into a state where they can compete for the monitor again. After the notifier unlocks, one thread acquires the monitor, checks the predicate, and then:

- If the condition is true, performs the work and may update state.
- If the condition is false, goes back to `wait()` via the `while` loop, relinquishing the monitor again.
- Other threads wait their turn to acquire the monitor; they are not allowed into the critical section simultaneously.

Calling `notifyAll` **does not mean** "all threads get to do work immediately" and **does not guarantee** all will see the predicate as true afterward. When multiple waiters need the same resource, only some threads can proceed, while the remaining threads continue waiting.

### 4.3. Should You Choose `notify` or `notifyAll`?

- **`notifyAll`** is generally the safer choice when multiple kinds of predicates (producers waiting for an empty buffer, consumers waiting for an item in the buffer) share **the same wait set**, or when it is hard to prove that the notified thread can always make progress.
- **`notify`** can be used in simple designs that have **one kind of condition and can prove that a single notification is sufficient for progress**, though choosing only one arbitrary thread makes the algorithm prone to stalling if the "wrong waiter" is picked.
- `notifyAll` can cause a **thundering herd**: many threads are woken up and compete for the lock even though only one thread qualifies, wasting context switching.
- If you need to distinguish specifically between producer-condition and consumer-condition, `java.util.concurrent.locks.Condition` can provide **multiple condition queues on a single Lock**.

**There is no rule** that "`notifyAll` is always faster" or "`notify` is always right if only one variable is modified". You must verify the actual protocol and states.

## 5. `IllegalMonitorStateException`: Hold the Right Monitor, Not Just Any Lock

The following snippets are **wrong**:

```java
Object lock = new Object();
lock.wait();      // IllegalMonitorStateException if not currently owning lock.
lock.notify();    // Same.
lock.notifyAll(); // Same.
```

Calling `wait()` also has checked `InterruptedException`, so this snippet is an incomplete **counterexample** for compilation, intended solely to point out the monitor ownership error.

Correct:

```java
synchronized (lock) {
    while (!ready) {
        lock.wait();
    }
}

synchronized (lock) {
    ready = true;
    lock.notifyAll();
}
```

This is a snippet requiring `ready`/`lock` declarations and interruption handling. The `ready` data must be protected by **the same monitor** to avoid a check-then-wait race.

### 5.1. Is Holding Lock A and Calling `B.wait()` Valid?

No, unless the thread also holds monitor B.

```java
Object a = new Object();
Object b = new Object();
synchronized (a) {
    b.notifyAll(); // Wrong: owning a is not owning b.
}
```

Calling notify on `b` inside a block holding `a` will throw `IllegalMonitorStateException` if the thread does not own monitor `b`. You must keep the identity of **the object used as the monitor** consistent on both sides.

### 5.2. A Standalone Java 17 Program for Ownership Errors

Save the file **`MonitorOwnershipDemo.java`**:

```java
public class MonitorOwnershipDemo {
    public static void main(String[] args) throws InterruptedException {
        Object lock = new Object();

        try {
            lock.notify();
        } catch (IllegalMonitorStateException ex) {
            System.out.println("notifyWithoutOwner=true");
        }

        try {
            lock.wait(1);
        } catch (IllegalMonitorStateException ex) {
            System.out.println("waitWithoutOwner=true");
        }

        synchronized (lock) {
            lock.notifyAll(); // Valid even when there is no waiter.
            System.out.println("notifyAllWithOwner=true");
        }
    }
}
```

Run:

```bash
javac --release 17 MonitorOwnershipDemo.java
java MonitorOwnershipDemo
```

**Exact stdout:**

```text
notifyWithoutOwner=true
waitWithoutOwner=true
notifyAllWithOwner=true
```

Not every `notifyAll()` needs a waiter to be allowed to be called; it only needs **the current thread to own the receiver monitor**. When the wait set is empty, there are no threads to wake up.

## 6. Guarded Block: The `while` Loop Matters More Than the Notification Itself

**Wrong:**

```java
synchronized (lock) {
    if (!ready) {
        lock.wait();
    }
    useSharedState();
}
```

This is an illustrative snippet with undeclared `ready` and `useSharedState()`. Risks:

1. The thread may wake up due to a *spurious wakeup*.
2. The thread may be notified for **another condition**.
3. Another thread may acquire the monitor **before** the newly woken thread, consuming the resource or changing state.
4. A timed wait may expire even though the predicate is still false.

**Correct:**

```java
synchronized (lock) {
    while (!ready) {
        lock.wait();
    }
    useSharedState();
}
```

The `while` loop checks **the actual predicate**, not simply "whether a signal was received". When the waiter re-acquires the monitor, it re-evaluates the latest state protected by the same monitor.

### 6.1. Why Not Check the Predicate Outside `synchronized`?

**Lost-notification race counterexample:**

```java
if (!ready) {             // Reading outside synchronized(lock): can race.
    synchronized (lock) {
        lock.wait();
    }
}
```

Timeline:

```text
T1 waiter: reads ready == false
T2 notifier: synchronized(lock) {
                 ready = true;
                 lock.notifyAll();    // wait set is still empty
             }
T1 waiter: enters synchronized(lock), calls lock.wait()
           → enters wait set, but the earlier notification was lost
           → may wait forever even though ready is already true
```

Merely using a `volatile boolean ready` **cannot fix a non-atomic check-then-wait** without a shared protocol. What is needed is **checking the predicate and deciding to wait under the same monitor**, while the notifier **updates the predicate and sends notify inside the same monitor**.

### 6.2. Notification Does Not Store State

`notify/notifyAll` is not a message queue, semaphore permit, or persistent event. If the notifier sends a signal when there is no waiter, the signal is **not saved**; however, if the notifier updates `ready=true` under the monitor, a thread arriving later **sees the state is already true** and does not need to wait.

Therefore, in a good design:

- **Predicate** is the source of truth.
- **Notification** is only a hint to wake up threads that may need to **re-read the predicate**.
- **Monitor** binds reading/writing the predicate with entering/leaving the wait set safely according to the Java protocol.

## 7. Java 17 Demo 1 — A Condition Gate Without Lost Signals

Create the file **`MonitorGateDemo.java`**:

```java
public class MonitorGateDemo {
    static final class Gate {
        private boolean open;

        synchronized void awaitOpen() throws InterruptedException {
            while (!open) {
                wait(); // Receiver is this, held monitor is also this.
            }
        }

        synchronized void open() {
            open = true;
            notifyAll(); // Wake up to re-check open.
        }

        synchronized boolean isOpen() {
            return open;
        }
    }

    public static void main(String[] args) throws InterruptedException {
        Gate gate = new Gate();

        Thread worker = new Thread(() -> {
            try {
                gate.awaitOpen();
                System.out.println("workerPassed=true");
            } catch (InterruptedException ex) {
                Thread.currentThread().interrupt();
                System.out.println("workerInterrupted=true");
            }
        });

        worker.start();
        gate.open();
        worker.join();

        System.out.println("gateOpen=" + gate.isOpen());
    }
}
```

Run:

```bash
javac --release 17 MonitorGateDemo.java
java MonitorGateDemo
```

**Deterministic stdout in a normal run without external interruption:**

```text
workerPassed=true
gateOpen=true
```

Explanation:

- If worker enters `awaitOpen()` **before** main calls `gate.open()`, worker sees `open=false` and calls `wait()`, relinquishing the monitor. Main then enters `open()`, writes `open=true`, and calls `notifyAll()`.
- If main calls `gate.open()` **before** worker enters `awaitOpen()`, worker sees `open=true` and **does not call `wait()`**. The signal does not need to be saved because **the predicate is already stored**.
- Only after `worker.join()` does main print `gateOpen=true`. `join()` ensures worker finishes before the last print line, so **the order of the two lines is stable**.
- The example **does not prove** worker actually entered the wait set on every run; it proves **the protocol using state + monitor remains correct under both interleavings**.

Do not add `Thread.sleep(100)` to "force worker to wait" and draw definitive conclusions. Sleep only affects scheduling probability, not creating a reliable synchronization handshake.

## 8. Thread States: WAITING, BLOCKED, TIMED_WAITING

The Java `Thread.State` API has the following observable states:

| State | Example situation | Notes |
| --- | --- | --- |
| **RUNNABLE** | Executing or eligible to be scheduled by JVM/OS | Does not guarantee actually occupying CPU |
| **BLOCKED** | Waiting to enter an intrinsic monitor because another thread owns it | Waiting for **lock ownership**, different from waiting for a predicate in a wait set |
| **WAITING** | Untimed `Object.wait()`, untimed `Thread.join()`, `LockSupport.park()` | Waiting indefinitely until an appropriate event occurs |
| **TIMED_WAITING** | `Object.wait(timeout)`, `Thread.sleep(timeout)`, `Thread.join(timeout)` | Bounded wait; not hard real-time |
| **TERMINATED** | Thread has finished | Not in a monitor wait set |
| **NEW** | Thread object not yet `start()`ed | Has not started executing |

In particular:

```text
T1 calls lock.wait() while holding lock
    │
    └─ WAITING (has released monitor and is in wait set)

T2 calls lock.notify() while still holding lock
    │
    └─ T1 leaves wait set; T1 must wait to acquire monitor
       → BLOCKED state may be observed

T2 exits synchronized(lock)
    │
    └─ T1 can acquire lock and continue (RUNNABLE)
```

**This is a conceptual model of states**, not an API state timeline required to transition at exact nanoseconds. Polling `getState()` is a race-prone snapshot; the state can change immediately after reading and should not be used to drive signaling algorithms.

### 8.1. `Thread.sleep` Is Not Like `Object.wait`

In:

```java
synchronized (lock) {
    Thread.sleep(1000);
}
```

the thread **still holds monitor `lock`** while sleeping. No other thread can enter `synchronized(lock)` until the sleeping thread exits the critical section (except the same thread reentering). `Thread.sleep` does not place the thread into `lock`'s wait set and does not automatically release the monitor.

Conversely, `lock.wait(1000)` while owning the lock **relinquishes monitor `lock`**, allowing another thread to acquire the lock and update the predicate. However, the timed wait version still requires checking the predicate in a `while` loop.

## 9. For What Reasons Can `wait()` Return?

JLS 17.2 describes that a thread can leave the wait set due to:

1. Being selected by `notify()` on the exact object.
2. `notifyAll()` on the exact object.
3. The thread being `interrupt()`ed.
4. **Timed wait** reaching its expiration time according to timing rules.
5. **Spurious wakeup:** the JVM may remove a thread from the wait set even without a matching explicit notification/interrupt/timeout.

All of these cases lead to **the step of re-acquiring the monitor before completing the wait action**.

### 9.1. What Is a Spurious Wakeup?

A thread calls `wait()`, and may later be allowed to return even though no notifier has signaled that the business state changed. The Java specification permits this. A correct program **must not** assume "`wait()` returned normally ⇒ the condition is true".

Therefore:

```java
synchronized (lock) {
    while (queue.isEmpty()) {
        lock.wait();
    }
    Item item = queue.remove();
}
```

This is a snippet, requiring `queue`, `Item`, and interrupt handling. When waking up for any reason while the queue is still empty, the thread enters `wait()` again. This is not a JVM bug, but **permitted semantics**.

### 9.2. Interrupt Is a Cancellation/Wakeup Request with Its Own Mechanism

If a thread waiting via `wait()` is interrupted in the scenario described by the JLS, it leaves the wait set, must re-acquire the monitor, and then `wait()` throws `InterruptedException`, while **clearing the interrupt status** when throwing the exception.

Key points:

- `interrupt()` does not forcibly "kill" a thread.
- Do not by default treat every interruption as a `ready=true` signal.
- If your method wants callers to handle cancellation, **propagate `InterruptedException`** when the API permits.
- If a worker thread catches the exception at a layer that cannot throw checked exceptions, it should usually **restore the status with `Thread.currentThread().interrupt()`** and stop/cancel work per policy.
- Do not catch `InterruptedException`, ignore it, and continue an infinite wait loop if the system needs cancellation.

### 9.3. Notification and Interruption Arriving Close Together

JLS 17.2.4 explains: if a waiter can simultaneously be notified and interrupted, the JVM must behave **consistently with a valid ordering** between the events. The thread may:

- Return normally from `wait()` with the interruption **still pending**, or
- Throw `InterruptedException` in the case where the interrupt is handled first and clears the status.

Do not teach that "when notify and interrupt occur at the same time, the exception always wins". Java also sets rules so that a notification is not lost due to a race with an interrupt on an existing wait set.

### 9.4. Java 17 Demo 2 — Interrupting a Waiter Without Relying on Sleep

Save the file **`InterruptWaitDemo.java`**:

```java
import java.util.concurrent.CountDownLatch;

public class InterruptWaitDemo {
    public static void main(String[] args) throws InterruptedException {
        Object lock = new Object();
        CountDownLatch entered = new CountDownLatch(1);

        Thread worker = new Thread(() -> {
            synchronized (lock) {
                entered.countDown();
                try {
                    // Loop guarding against spurious wakeups:
                    for (;;) {
                        lock.wait();
                    }
                } catch (InterruptedException ex) {
                    System.out.println("interruptCaught=true");
                    System.out.println("interruptFlagCleared=" +
                            !Thread.currentThread().isInterrupted());
                }
            }
        });

        worker.start();
        entered.await();
        worker.interrupt();
        worker.join();
        System.out.println("done");
    }
}
```

Run:

```bash
javac --release 17 InterruptWaitDemo.java
java InterruptWaitDemo
```

**Deterministic stdout when the program runs normally:**

```text
interruptCaught=true
interruptFlagCleared=true
done
```

**Why is this more reliable than using `sleep`?** `CountDownLatch` ensures the worker has entered the synchronized region and signaled readiness before main calls interrupt. Main does not need to wait a guessed number of milliseconds. If the interrupt arrives **before** the `wait()` call, `wait()` sees the interrupt status and throws the exception; if it arrives **while** worker is waiting, the waiter leaves the wait set according to the rules. If a spurious wakeup occurs, the `for (;;)` loop returns to `wait()`, without printing a wrong result.

This is a demo for learning **interruption semantics**, not a business loop pattern. In real code, a `while(!condition)` loop is better than an infinite loop unless demonstrating waiting for an interrupt as in this lesson.

## 10. Timed Wait: Avoid Thinking `wait(timeout)` Is a Hard Deadline

`wait(long timeoutMillis)` and `wait(long timeoutMillis, int nanos)` allow waiting **up to the intended timeout of the wait set**, but when the thread actually finishes the method also requires **re-acquiring the monitor** and is subject to scheduling/OS effects.

- `timeoutMillis` must be **non-negative**.
- `nanos` in the two-argument overload must be in **0..999999**.
- `wait(0)` and `wait(0, 0)` are **indefinite waits** per API rules.
- `wait(0, 1)` is a **timed wait**, not indefinite.
- Actual wait time and when the thread gets scheduled can exceed the specified value.
- A timed wait can end **before timeout** due to notify, interrupt, or spurious wakeup.
- Timeout expiration **does not by itself make the predicate true**.

### 10.1. Deadline Waiting Style Using `System.nanoTime`

If the requirement is "wait logically for at most X", you must check **remaining time after each wakeup**, rather than calling `wait(timeout)` again with the full timeout after each spurious wakeup (which can extend waiting indefinitely).

An illustrative Java 17 pattern:

```java
long deadline = System.nanoTime() + timeoutNanos;
synchronized (lock) {
    while (!ready) {
        long remaining = deadline - System.nanoTime();
        if (remaining <= 0L) {
            break;  // logical timeout; ready may still be false.
        }

        long millis = remaining / 1_000_000L;
        int nanos = (int) (remaining % 1_000_000L);
        lock.wait(millis, nanos);
    }
}
```

This is a **snippet** requiring declarations for `timeoutNanos` (should be a positive duration with reasonable bounds), `lock`, and `ready`; the caller must handle `InterruptedException`. `System.nanoTime` is more suitable for measuring elapsed time than wall-clock time. Adding to deadline must avoid overflow with extremely large durations; for normal reasonable timeouts, this is the pattern for checking **remaining duration**, not a guarantee that the thread will be scheduled exactly at the deadline.

### 10.2. Why Not Use `System.currentTimeMillis` as a Deadline Clock?

Wall-clock time can be resynchronized/adjusted by the operating system or administrator, causing changes that do not correspond to elapsed duration. `System.nanoTime` measures relative time better for wait loops. Even so, scheduler/lock contention can still cause actual code resumption to pass the deadline.

For modern code, it is usually better to prefer APIs designed with timeouts such as `BlockingQueue.poll(timeout, unit)`, `Condition.awaitNanos`, or `CountDownLatch.await(timeout, unit)` instead of writing lots of time arithmetic manually.

## 11. Java Memory Model: Notify Does Not Replace Happens-Before Rules

Data used as a condition must be read/written **with proper synchronization**. With an intrinsic monitor, each exit from `synchronized(lock)` performs an unlock and a subsequent entry into `synchronized(lock)` performs a lock. According to JLS §17.4.4–17.4.5:

> **An unlock on monitor `m` happens-before every subsequent lock on the same monitor `m`** in the synchronization order.

Therefore:

```text
T2 notifier, holding lock:
   ready = true;
   payload = value;
   lock.notifyAll();
   [unlock lock] ────── happens-before ─────► [lock lock] T1 waiter
                                               reads ready, payload
```

The visibility guarantee in this pattern relies on **monitor unlock/lock and guarded state**, not some magic where `notify` itself "copies all variables to another thread" without needing the same lock.

### 11.1. Is `volatile` Needed for a Predicate Already Guarded by `synchronized`?

If **all accesses** to `ready`/`payload` are inside the exact `synchronized(lock)`, the unlock/lock mechanism already establishes the necessary visibility and ordering. `volatile` is not a mandatory requirement just because multiple threads use the variable.

Conversely, if one side writes `ready` outside the monitor and the other side reads inside the monitor, the protocol can break. Making `ready` alone `volatile` does not replace the **atomic check-then-wait** requirement of a guarded block.

### 11.2. Why Is `notify()` Insufficient Without a Predicate?

A notified thread **is not handed data** just by the signal. Upon acquiring the monitor, it must read shared state to know whether there is a job, whether the buffer has space, or whether the task was canceled. Without clear state invariants, a notification is an event easily missed and hard to debug.

### 11.3. `Thread.start()` and `Thread.join()` Also Have Happens-Before

JLS §17.4.4 states that the start action synchronizes-with the first action of the new thread; detecting that a thread has terminated via `join()` creates a corresponding synchronization relationship. This is why examples use `join()` to **order the final stdout**, but `join` does not replace an intrinsic lock for managing shared state **while threads are still executing concurrently**.

## 12. Producer–Consumer: Wait Set and Monitor on the Same Object

The **one-slot buffer** problem:

- Producer may only `put` when the slot is empty.
- Consumer may only `take` when the slot has a value.
- If the condition is not met, the thread must yield the monitor and wait.
- After changing state, the thread notifies so waiters re-check the condition.

A basic implementation:

```java
final class OneSlot {
    private Integer value;  // null = empty

    synchronized void put(int number) throws InterruptedException {
        while (value != null) {
            wait();          // Yields monitor of this.
        }
        value = number;
        notifyAll();
    }

    synchronized int take() throws InterruptedException {
        while (value == null) {
            wait();
        }
        int result = value;
        value = null;
        notifyAll();
        return result;
    }
}
```

This is a class snippet; the standalone file is right in the next section. Reading/writing `value` and `wait/notifyAll` all happen under **the monitor of the same OneSlot instance**. The condition `value==null` is the control data, while `notifyAll` is the signal helping waiting threads wake up to check again.

### 12.1. Why Call `notifyAll` After Both `put` and `take`?

After `put`, the slot transitions **empty → full**, so a consumer can proceed. After `take`, the slot transitions **full → empty**, so a waiting producer can proceed.

If using only one wait set and there are multiple producers/consumers, `notify()` might pick a thread **without a matching predicate**. For example, the buffer is full, yet the notifier wakes another producer instead of a consumer that needs to make progress; the producer sees it is full and waits again. There is no complete proof of progress if an arbitrary thread keeps getting picked. `notifyAll` wakes both groups, and then `while` filters by the right condition.

### 12.2. Java 17 Demo 3 — Complete One-Slot Program

Save the file **`OneSlotDemo.java`**:

```java
import java.util.concurrent.atomic.AtomicInteger;

public class OneSlotDemo {
    static final class OneSlot {
        private Integer value;

        synchronized void put(int number) throws InterruptedException {
            while (value != null) {
                wait();
            }
            value = number;
            notifyAll();
        }

        synchronized int take() throws InterruptedException {
            while (value == null) {
                wait();
            }
            int result = value;
            value = null;
            notifyAll();
            return result;
        }

        synchronized boolean isEmpty() {
            return value == null;
        }
    }

    public static void main(String[] args) throws InterruptedException {
        OneSlot slot = new OneSlot();
        AtomicInteger sum = new AtomicInteger();

        Thread producer = new Thread(() -> {
            try {
                for (int n = 1; n <= 5; n++) {
                    slot.put(n);
                }
            } catch (InterruptedException ex) {
                Thread.currentThread().interrupt();
            }
        });

        Thread consumer = new Thread(() -> {
            try {
                for (int n = 1; n <= 5; n++) {
                    sum.addAndGet(slot.take());
                }
            } catch (InterruptedException ex) {
                Thread.currentThread().interrupt();
            }
        });

        producer.start();
        consumer.start();

        producer.join();
        consumer.join();

        System.out.println("sum=" + sum.get());
        System.out.println("empty=" + slot.isEmpty());
        System.out.println("done");
    }
}
```

Compile/run:

```bash
javac --release 17 OneSlotDemo.java
java OneSlotDemo
```

**Deterministic stdout when there is no unintended interrupt:**

```text
sum=15
empty=true
done
```

Explanation:

1. Producer puts `1, 2, 3, 4, 5` in order. The slot has capacity one, so at times the producer must wait for the consumer to take.
2. Consumer takes all five values, summing to `1+2+3+4+5=15`. Either consumer or producer may start first — the protocol remains correct.
3. Each `wait()` yields the monitor **of the same `slot` object**, letting the other thread enter to update `value`.
4. `notifyAll` wakes waiters if any; threads re-check `while` upon acquiring the monitor.
5. `producer.join()` and `consumer.join()` ensure main only prints the result after both threads have finished. No `Thread.sleep` is needed to force execution order.
6. `AtomicInteger` helps describe safely publishing the result; since main reads after `join`, visibility is also established via thread termination. Using `AtomicInteger` does not replace the monitor guarding `value`.

**Limitation:** This is an example for learning monitor usage, without a full close/cancel protocol when a producer/consumer is interrupted. In a real system, if one worker dies unexpectedly while the other waits indefinitely, **shutdown state** and signaling must be added to avoid hanging.

## 13. Why Must Condition Checking and Notify Be in the Same Synchronization Protocol?

### 13.1. Scenario: Thread A Checks, Thread B Updates

Calling `lock.wait()` inside synchronized while checking the predicate **outside** synchronized creates a race window:

```text
A: if (queueEmpty)              // unguarded
B: synchronized(lock) {
     put(item);
     lock.notifyAll();           // A has not waited yet; notification lost
   }
A: synchronized(lock) { lock.wait(); }
```

At this point the queue already has an item, yet A may wait forever. Fix by placing both **check and wait** inside the same critical section, while the producer places **update and notify** under the same monitor.

### 13.2. Should You Notify When the Predicate Has Not Changed?

Notification should be tied to **state transitions that can make a waiter's condition true**, rather than arbitrarily calling notify every time a function runs. Excessive signals cause unnecessary wakeups/contention, while missing a signal after an important transition causes lost progress. If multiple predicates share a monitor, use `notifyAll` when there is no stronger protocol proof.

### 13.3. Do Not Hold a Monitor While Waiting for Something That Needs That Same Monitor

A deadlock pattern:

```java
synchronized (lock) {
    while (!ready) {
        Thread.sleep(100);
    }
}
```

This is a counterexample: `sleep` **does not release `lock`**, so if another thread needs `synchronized(lock)` to set `ready=true`, it cannot enter, and the waiter may stay stuck forever. Better is `lock.wait()` in a while loop on the predicate to **yield the monitor**.

## 14. Comparing `Thread.sleep`, `Object.wait`, `Thread.join`, `Condition.await`

| API | What does it wait for? | Releases intrinsic monitor? | Wakeup/completion mechanism |
| --- | --- | --- | --- |
| `Thread.sleep(ms)` | Time | **Does not** release held monitors | Timeout or interrupt |
| `obj.wait()` | Signal/event on `obj` | **Yes, only `obj`'s monitor** | Notify/notifyAll, interrupt, spurious wakeup |
| `obj.wait(ms)` | Signal or timeout | **Yes, only `obj`'s monitor** | Notify, interrupt, timeout, spurious |
| `thread.join()` | Target thread termination | No contract to "release all caller monitors" | Target thread termination, interruption, timeout with overload |
| `condition.await()` | Condition via explicit Lock | **Releases associated Lock per contract and re-acquires before return** | `signal`/`signalAll`, interrupt, spurious |
| `LockSupport.park()` | Permit/`unpark`/interrupt/spurious | **Does not automatically release intrinsic monitor** | Permit, interrupt, or spurious; caller checks condition |
| `CountDownLatch.await()` | Count reaching 0 | Not an intrinsic-monitor wait signaled by caller | `countDown`, interrupt, or timeout overload |
| `BlockingQueue.take()` | Item available in queue | API manages synchronization internally | Producer `put/offer` or interrupt |

**Warning:** `join()` in HotSpot/Java platform may use internal monitor-wait depending on version and implementation, but users should rely on the **API contract**, not call `thread.notifyAll()` as a way to "implement join manually". A `Thread` object should not be used as an arbitrary business monitor, because the API/runtime also uses synchronization mechanisms related to the thread lifecycle.

## 15. `Condition` on `ReentrantLock`: Multiple Business Wait Sets

An object's intrinsic monitor provides **one wait set**, so producers and consumers share waiters in one set if using the same synchronized object.

`ReentrantLock` supports multiple `Condition` objects, each having its **own condition wait queue** associated with an explicit Lock. Use when you need to manage different predicates more cleanly:

```java
final ReentrantLock lock = new ReentrantLock();
final Condition notEmpty = lock.newCondition();
final Condition notFull = lock.newCondition();

void put(Item item) throws InterruptedException {
    lock.lock();
    try {
        while (queue.isFull()) {
            notFull.await();
        }
        queue.add(item);
        notEmpty.signal();
    } finally {
        lock.unlock();
    }
}

Item take() throws InterruptedException {
    lock.lock();
    try {
        while (queue.isEmpty()) {
            notEmpty.await();
        }
        Item result = queue.remove();
        notFull.signal();
        return result;
    } finally {
        lock.unlock();
    }
}
```

This is an **illustrative snippet**, requiring `import java.util.concurrent.locks.*`, definitions of `Item`/`queue`, and placing the fields/methods in a class. It is not a standalone runnable file.

- `await()` relinquishes the associated `ReentrantLock` and waits on the condition.
- `signal()`/`signalAll()` must be called with appropriate lock ownership per normal Condition implementations.
- After notification, the waiter still must **re-acquire the Lock**, then check the predicate in `while`.
- `Condition` does not carry data itself. The guarded predicate in `queue` determines whether `take/put` can proceed.
- Multiple conditions allow waking the right group of waiters more precisely than a single intrinsic wait set on `this`, reducing unnecessary wakeups.

### 15.1. Do Not Mix Two Incompatible Synchronization Systems

**Wrong:**

```java
synchronized (lock) {
    condition.await();  // Not how to own ReentrantLock.
}
```

Here the variable `lock` is assumed to be a `ReentrantLock` object. `synchronized(lock)` only owns **the intrinsic monitor of the ReentrantLock instance**, **not** calling `lock.lock()` and not satisfying the ownership rule of `Condition.await`. With `ReentrantLock`/`Condition`, you must use `lock.lock()/unlock()` per the protocol.

Conversely, owning a `ReentrantLock` via `lock.lock()` does not grant permission to call `lock.wait()` on the intrinsic monitor of the `ReentrantLock` object itself. The two mechanisms have different ownerships.

## 16. When Can `notify()` Cause Stalling with Multiple Conditions?

Suppose a queue of capacity 1:

- Producers P1/P2 wait for "slot **empty**".
- Consumers C1/C2 wait for "slot **has item**".
- Both groups use **the wait set of the same `queue` monitor**.

If a thread calls `notify()` after a transition that should wake a consumer, yet it picks an ineligible producer, the producer wakes up, sees the slot is still full, and goes back to wait. If there are no future notifications from other threads, the system may **fail to make progress** even though an eligible consumer is also waiting.

```text
Wait set(queue) = {P1, P2, C1, C2}
state: buffer FULL

notify() → picks P1 (arbitrary)
P1 acquires monitor → sees FULL → waits again

C1/C2 remain in wait set, even though there is an item to take.
No guarantee there will be a next signal.
```

The example above describes **the risk of picking the wrong type of waiter in multi-condition protocols**; concluding a specific deadlock requires examining the interleavings and invariants of the entire producer-consumer implementation. But it is enough to prove that `notify()` does not know each thread's business predicate.

Solutions:

- Use `notifyAll()` with `while` so all waiters re-check, or
- Use separate `Condition` queues `notEmpty/notFull` and `signal` the appropriate group, or
- Use a built-in `BlockingQueue` if you do not need to write low-level synchronization yourself.

### 16.1. The Thundering Herd of `notifyAll` Is a Trade-Off

If there are 1,000 waiters and only one token/resource, `notifyAll` can cause many thread transitions and lock contention; most wake up only to wait again. In high-load production, you can choose abstractions such as `Semaphore`, `Condition`, `BlockingQueue`, or a work-queue pool instead of a shared intrinsic wait set.

Do not sacrifice correctness just to reduce wakeup counts: first prove the state machine has no lost signals, no starvation, and no deadlock across valid interleavings.

## 17. Interrupt and Shutdown in Real Systems

In `OneSlotDemo`, the worker catches interruption, restores the flag, and terminates. That is enough for an example without mid-run cancellation, but a production service needs a clearer **lifecycle protocol**:

- A `closed` or `stopping` variable guarded by the same monitor.
- When closing, set `closed=true` under the monitor and call `notifyAll()`.
- In `while` loops, check both the business condition and `closed` to decide whether to stop/throw an exception.
- Define how to handle data already in the queue: drain before closing or reject all.
- Clarify whether `interrupt()` is a request to cancel one operation or shut down the entire pipeline.
- With multiple workers, ensure no thread waits forever after a counterpart fails.

Conceptual pattern:

```java
synchronized (lock) {
    while (queue.isEmpty() && !closed) {
        lock.wait();
    }
    if (queue.isEmpty() && closed) {
        return; // or end-of-stream signal depending on API.
    }
    // process item
}
```

This is a **snippet** requiring appropriate variables/types/methods. `closed` must be updated under the same lock followed by `notifyAll` so waiting threads wake up, see the state change, and do not return to wait forever.

### 17.1. Do Not Unconditionally Swallow `InterruptedException`

**Anti-pattern:**

```java
while (!ready) {
    try {
        lock.wait();
    } catch (InterruptedException ignored) {
        // Ignore all stop requests.
    }
}
```

This is a snippet inside an appropriate `synchronized(lock)`. If a thread is canceled and `ready` never becomes true, it may wait forever again.

**Better:** propagate `InterruptedException` from the method if the API allows; otherwise, restore the flag and exit the task according to a clear decision.

### 17.2. Do Not Notify by Arbitrarily Interrupting Another Thread

`Thread.interrupt()` is an **interruption request mechanism**, not a replacement for the `ready` predicate. If a thread is waiting for a queue item and you only interrupt it without changing state, it may throw an exception and cancel the operation instead of processing the desired data.

Use the right primitive with the right semantics: `notify/notifyAll` to hint at guarded state changes; `interrupt` to signal cancellation/interruption; `Semaphore` for permits; `BlockingQueue` for exchanging items.

## 18. Deadlock: Holding Another Lock While Calling `wait()`

A tricky situation:

```text
T1:
  synchronized(A) {
      synchronized(B) {
          B.wait();    // Releases B, STILL HOLDS A
      }
  }

T2:
  synchronized(A) {    // Wants to enter to update predicate
      synchronized(B) {
          B.notifyAll();
      }
  }

T1 waits for T2 to notify on B.
T2 waits for T1 to release A.
⇒ Deadlock under this protocol.
```

**Important:** `B.wait()` is valid when T1 owns B; the problem is not `IllegalMonitorStateException` but **not releasing monitor A**. To fix, minimize nested locks, do not wait while holding another lock that the notifier needs, and enforce a consistent lock order.

### 18.1. Monitor Ordering and Lock Ordering

If a workflow must hold multiple locks, you must specify the order of acquiring them across all code paths, minimize critical section scope, and avoid long blocking I/O while holding a lock. Intrinsic monitors do not automatically detect and resolve wait cycles.

Java `ThreadMXBean.findDeadlockedThreads()` can help diagnose some deadlocks involving monitors/ownable synchronizers, but **does not replace protocol reasoning**. A program waiting on a predicate that never becomes true can also "hang" without appearing in a deadlock detector because it is not a simple monitor ownership cycle.

## 19. Analyzing Thread Dumps and Thread States

With HotSpot JDK 17, you can capture a thread dump via:

```bash
jcmd <pid> Thread.print
```

When observing a thread, states such as `WAITING (on object monitor)`, `TIMED_WAITING (on object monitor)`, or `BLOCKED (on object monitor)` can help distinguish:

- **WAITING on object monitor:** the thread called `Object.wait` and is waiting for a condition/event.
- **BLOCKED on object monitor:** the thread wants to acquire a monitor, but another thread owns it.
- **TIMED_WAITING:** a wait operation with a timeout (though detailed state depends on API and JVM).
- **Lock owner:** information about which monitor a thread is holding (if the dump can infer it).
- **Stack trace:** Java-level location, e.g., `Object.wait`, queue methods, and synchronized code.

### 19.1. Can the Wait Set Be Directly Measured Using a Public Java API?

The Java standard API does not provide `lock.getWaitSet()` returning the full list of threads calling `wait` on an object. `Thread.getState()` only returns a snapshot state of one thread, not a list precisely distinguishing "object A's wait set".

You can use thread dumps/JFR/monitor instrumentation for diagnostics, but results depend on implementation/timepoint. Do not build a protocol based on polling thread states to decide whether to call notify.

### 19.2. Why Might a Notified Thread Still Be Delayed?

A thread receiving a notify may:

1. Wait for the notifier to exit the synchronized block.
2. Compete for the monitor with many other threads.
3. Wait for CPU scheduling if the system is overloaded.
4. Re-enter the critical section, find the predicate false, and wait again.

Therefore, "called notifyAll but consumer hasn't run yet" does not by itself prove notifyAll failed. You must inspect thread dumps, lock owners, guarded state, and scheduling.

### 19.3. Starting Logs for Monitor Contention

In an application with performance issues, measure **monitor enter contention**, time spent blocked/waiting, and the number of notifications/wakeups via JFR or an appropriate profiler, then correlate with throughput/p99 latency. Do not assume `Thread.State.WAITING` means 100% CPU is being consumed; a waiting thread usually performs no active work.

## 20. Designs You Should Not Hand-Roll with `wait/notify`

Modern primitives solve many common coordination patterns:

| Need | Usually suitable API | Avoid hand-rolling |
| --- | --- | --- |
| Producer-consumer queue | `ArrayBlockingQueue`, `LinkedBlockingQueue` | Easy to miss shutdown/interrupt/fairness |
| One thread waiting for work completion | `CountDownLatch`, `Future.get`, `CompletableFuture` | Easy to lose notifications if flags are stored wrong |
| Limiting concurrent tasks | `Semaphore` | Easy to handle permits incorrectly |
| Multiple workers meeting at a phase | `CyclicBarrier`, `Phaser` | Easy to make generation/phase bugs |
| Needing multiple conditions on the same lock | `ReentrantLock` + `Condition` | One wait set makes picking the right group hard |
| Simple atomic state | `AtomicBoolean`, `AtomicInteger`, `VarHandle` | No wait set needed for non-blocking atomic updates |
| Waiting for asynchronous results | `CompletableFuture` or futures | Should not manually wait on a `Thread` object |

These APIs do not "defeat every deadlock" or "completely replace concurrency correctness reviews"; they provide **abstractions with clearer contracts** than manually designing multiple wait/notify loops and lifecycle states.

## 21. Common Misconceptions

1. **"`Object.wait()` can be called without holding a lock."** False; requires monitor ownership of the receiver itself.
2. **"Holding `synchronized(a)` is enough to call `b.wait()`."** False unless also holding monitor `b`.
3. **"`wait()` only releases one level of a reentrant lock."** False; releases all ownership levels on the receiver monitor and re-acquires accordingly.
4. **"`wait()` releases all locks held by the thread."** False; only the monitor of the object receiving the call.
5. **"`notify()` releases the monitor immediately."** False; the notifier continues holding it until unlocking per protocol.
6. **"A notified thread immediately owns the monitor."** False; it must compete to re-acquire the lock.
7. **"`notify()` always picks the thread that has been waiting longest."** False; there is no FIFO/fairness guarantee.
8. **"`notifyAll()` lets all waiters enter the critical section at the same time."** False; the monitor still enforces mutual exclusion.
9. **"`notify()` before `wait()` is saved like a permit."** False; if there is no waiter, the notification is not accumulated.
10. **"Just having `volatile ready` makes check-then-wait outside synchronized safe."** False; requires an atomic guarded check/wait protocol.
11. **"`if (!ready) wait()` is always correct."** False; spurious wakeups, state changes, and multiple conditions require `while`.
12. **"`wait()` only returns when `notify()` happens."** False; notifyAll, interrupt, timeout, and spurious wakeup.
13. **"After a timeout, the predicate is true."** False; timeout is just an event allowing the waiter to continue if it acquires the lock.
14. **"`wait(0)` means do not wait."** False; zero timeout is equivalent to an indefinite wait.
15. **"`Thread.sleep()` releases the monitor like `wait()`."** False; sleep does not release monitors.
16. **"`Thread.State.WAITING` and `BLOCKED` are the same."** False; one waits for an event, the other waits for a lock.
17. **"`notifyAll` is always the most efficient."** False; it can wake many waiters unnecessarily.
18. **"`notify` is always faster and more correct than `notifyAll`."** False; picking the wrong type of waiter can stall the system.
19. **"Interrupt during wait always kills the thread."** False; usually reports `InterruptedException`, and the caller decides.
20. **"When wait throws `InterruptedException`, the interrupt flag is still true."** False; the status is cleared when throwing the exception per API.
21. **"Simultaneous notification and interrupt always prioritizes interrupt."** False; the JLS describes multiple valid orderings.
22. **"Adding a `notifyAll` is enough to replace updating guarded state."** False; the predicate remains the source of truth.
23. **"A synchronized static method locks all instances."** False; it locks the corresponding `Class` object.
24. **"Java has a standard `lock.getWaitSet()` returning the exact list of waiters."** False; no such API exists.
25. **"`ReentrantLock.lock()` grants permission to call `reentrantLock.wait()`."** False; explicit Lock ownership is different from intrinsic monitor ownership.
26. **"`Condition.await()` does not require holding the associated Lock."** False; ReentrantLock's Condition requires appropriate lock ownership.
27. **"A thread dump showing `BLOCKED` always means deadlock."** False; it may just be temporary monitor contention.
28. **"`join` and `notifyAll` are interchangeable methods."** False; different contracts.
29. **"Not using `sleep` means concurrent code definitely has no race."** False; correctness depends on protocol and synchronization.
30. **"`wait/notify` is the best solution for every concurrent queue."** False; blocking queues and latches are usually safer and clearer.
31. **"Seeing a waiter leave the wait set is enough to conclude it read the new shared data."** False; it still must acquire the monitor, execute under synchronization, and check the predicate.
32. **"Synchronized only prevents concurrent execution, with no visibility guarantee."** False; unlock/lock creates happens-before per JMM.
33. **"`notifyAll` makes Java automatically check all predicates."** False; each waiter's code must have `while` to check itself.
34. **"Holding lock B in `B.wait` prevents thread A from updating B."** False: `wait` releases B so the notifier can acquire it; the issue is usually **other** locks still held.
35. **"Using `wait/notify` correctly guarantees hard real-time deadlines."** False; scheduling/fairness/timing have no such guarantee.

## 22. Self-Check Questions (with Answers)

**Question 1.** Why cannot `wait()` be called outside a synchronized block on the same object?

**Answer:** Because the receiver's monitor must be owned. Otherwise, `IllegalMonitorStateException` is thrown. The monitor coordinates checking the predicate with entering the wait set safely.

**Question 2.** A thread holds monitor `m` at two reentrant levels and then calls `m.wait()`. How many levels does it release?

**Answer:** It releases **all** ownership levels on monitor `m`, and then re-acquires the same number of levels before continuing; it does not release locks of other objects.

**Question 3.** A notifier calls `m.notifyAll()` while still in the middle of `synchronized(m)`. Do waiters immediately continue executing code after `wait()`?

**Answer:** No. They must re-acquire `m` after the notifier unlocks and scheduling permits.

**Question 4.** Does `m.notify()` have a FIFO guarantee?

**Answer:** No, it selects an arbitrary thread from the wait set.

**Question 5.** Why is checking `ready` outside `synchronized` prone to lost notifications?

**Answer:** The notifier may set `ready=true` and notify **after the check but before wait**; notifications are not saved and the waiter may sleep forever.

**Question 6.** Why use `while` instead of `if`?

**Answer:** To re-check the predicate after notification, spurious wakeup, timeout, or when another thread changed the state before the waiter re-acquired the monitor.

**Question 7.** Does `Thread.sleep(100)` under a monitor release the monitor?

**Answer:** No. `sleep` does not release owned intrinsic monitors.

**Question 8.** Is `wait(0)` a nonblocking call or an indefinite wait?

**Answer:** An indefinite wait per API, which can end due to notification, interrupt, or spurious wakeup.

**Question 9.** When does `InterruptedException` from `wait` occur, and does the thread hold the monitor at that time?

**Answer:** After exiting the wait set due to a valid interruption and **re-acquiring the monitor**; the thread is inside the synchronized block when catch runs if catch is inside the block.

**Question 10.** Does calling `notify()` when the wait set is empty cause an error?

**Answer:** No, as long as monitor ownership is held. However, the notification is not accumulated for a future waiter.

**Question 11.** What is the primary visibility mechanism of guarded state under `synchronized(lock)`?

**Answer:** Unlock-lock happens-before of **the same monitor**, not notify itself replacing data synchronization.

**Question 12.** In `OneSlotDemo`, why is sum guaranteed to be 15 in an uninterrupted run?

**Answer:** The producer puts all five numbers 1..5, and the consumer takes all five numbers using the guarded buffer protocol; total `1+2+3+4+5=15`.

**Question 13.** Does `Condition.await()` release the intrinsic monitor of the `ReentrantLock` object?

**Answer:** It releases **the associated explicit Lock** per the Condition contract, not "the intrinsic monitor of the ReentrantLock object"; the two ownership models are different.

**Question 14.** Why can `notifyAll` consume more CPU than `notify`?

**Answer:** Many waiters wake up and contend for the same monitor even though most predicates are still false; they must go back to wait.

**Question 15.** When a thread still holds monitor A, and then calls `wait()` on B, what is the risk?

**Answer:** It releases B but **still holds A**; if the notifier needs A to transition the predicate/signal B, it can create a deadlock.

**Question 16.** To have multiple producers/consumers use separate condition queues, which API can be suitable?

**Answer:** `ReentrantLock` with two `Condition`s `notFull` and `notEmpty`; or better for general queues, `BlockingQueue` with a built-in protocol.

**Question 17.** Does `getState() == WAITING` accurately prove a thread is in the wait set of a specific object?

**Answer:** No. WAITING also appears from `join`/`park`, and the snapshot has a race; thread dumps/diagnostics with stack/monitor are needed to investigate.

**Question 18.** Why can't a "interrupt always wins" rule be applied when interruption and notification happen close together?

**Answer:** The JLS allows different event orderings and specifies corresponding outcomes; notification/interruption interactions have their own semantics protecting state/notifications.

## 23. Summary: Visualizing Wait Set and Monitor Correctly

```text
             EVERY OBJECT M HAS:
   ┌────────────────────────────────┐
   │ intrinsic MONITOR              │
   │ current owner (or none)        │
   │                                │
   │ WAIT SET of M                  │
   │ {T2, T3, ...}                  │
   └────────────────────────────────┘

T1 notifier:
  synchronized(m) {
      predicate = true;   // state
      m.notifyAll();      // removes waiters from wait set
      ...                 // T1 still holds monitor here
  }                       // T1 unlocks

T2 waiter:
  synchronized(m) {
      while (!predicate) {
          m.wait();       // enters wait set, releases monitor M
      }                   // being woken does not mean running immediately
      doWork();           // only after re-acquiring M and predicate is true
  }

Thread States (conceptual observation):
  WAITING       waiting for event/predicate after wait()
  BLOCKED       waiting to acquire monitor M
  RUNNABLE      eligible to execute once M is re-acquired

Correctness:
  shared predicate + SAME monitor + while + state-change notify
  + clear interruption/shutdown policy.
```

**Remember:** `wait` **releases all ownership of the receiver's monitor, places the current thread into the wait set, and requires re-acquiring the monitor before continuing**. `notify` picks an arbitrary waiter; `notifyAll` wakes all waiters on **the exact object**, but **does not release the monitor immediately** and does not guarantee fairness. Notification is a transient signal; **the predicate protected by synchronized is the truth**. `while` is necessary because of spurious wakeups, timeouts, and state contention. For complex problems, prefer abstractions in `java.util.concurrent` that have clearer protocols.

### Official References (Java SE 17)

- [JLS 17.1 — Synchronization](https://docs.oracle.com/javase/specs/jls/se17/html/jls-17.html#jls-17.1): monitor ownership and synchronized.
- [JLS 17.2 — Wait Sets and Notification](https://docs.oracle.com/javase/specs/jls/se17/html/jls-17.html#jls-17.2): wait set, notify, notifyAll, spurious wakeups.
- [JLS 17.2.1 — Wait](https://docs.oracle.com/javase/specs/jls/se17/html/jls-17.html#jls-17.2.1): releasing then re-acquiring monitor and interrupt semantics.
- [JLS 17.2.2 — Notification](https://docs.oracle.com/javase/specs/jls/se17/html/jls-17.html#jls-17.2.2): selecting one/all waiters, no FIFO priority.
- [JLS 17.2.4 — Interactions of Waits, Notification, and Interruption](https://docs.oracle.com/javase/specs/jls/se17/html/jls-17.html#jls-17.2.4).
- [JLS 17.4.4–17.4.5 — Synchronization Order/Happens-Before](https://docs.oracle.com/javase/specs/jls/se17/html/jls-17.html#jls-17.4.5).
- [Java SE 17 — `Object.wait()/notify()/notifyAll()`](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/lang/Object.html).
- [Java SE 17 — `Thread.State`](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/lang/Thread.State.html).
- [Java SE 17 — `Condition`](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/concurrent/locks/Condition.html).
- [Java SE 17 — `BlockingQueue`](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/concurrent/BlockingQueue.html).
- [Java SE 17 — `CountDownLatch`](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/concurrent/CountDownLatch.html).
- [JDK 17 — `jcmd`, `Thread.print`](https://docs.oracle.com/en/java/javase/17/docs/specs/man/jcmd.html).

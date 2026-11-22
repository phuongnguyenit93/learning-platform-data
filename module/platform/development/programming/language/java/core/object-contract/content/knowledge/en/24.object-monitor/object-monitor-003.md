# Monitor Ownership Conditions and `IllegalMonitorStateException` in Java

## 1. Objectives and context

When coordinating threads using `synchronized`, `wait()`, `notify()`, and `notifyAll()`, the most important question is: **does the executing thread own the exact monitor of the target object?** If not, `Object`'s waiting or signaling operations throw `IllegalMonitorStateException`. This lesson explains the ownership requirement, how to identify a mismatched monitor, and how to write safe wait/notify code.

After this lesson, you can:
- Identify which monitor is locked by block-level `synchronized`, instance methods, and static methods.
- Explain why `obj.wait()`, `obj.notify()`, and `obj.notifyAll()` require **the current thread itself** to own `obj`'s monitor.
- Distinguish between **releasing the monitor on `wait`** and **only waking a thread on `notify`**.
- Diagnose `IllegalMonitorStateException` and fix the bug without accidentally changing the lock object.

## 2. What is monitor ownership?

Every ordinary Java object has an *intrinsic lock* (monitor) used for synchronization via `synchronized`. At any time, a monitor has at most one owning thread; the same thread can re-enter (*reentrant*) that monitor multiple times.

A thread T owns the monitor of object `lock` in the following situations:

| Executing syntax | Monitor owned by the thread |
| --- | --- |
| `synchronized (lock) { ... }` | The `lock` object itself |
| `synchronized void method() { ... }` on object `x` | `x` itself (i.e., `this` of the invocation) |
| `static synchronized void method() { ... }` of `Example` | The `Example.class` object |

For example, `synchronized (a)` does not make the thread own `b`'s monitor, even if `a.equals(b)` is `true`. What matters is **the exact same actual object reference** (identity), not equal values according to `equals()`.

`Thread.holdsLock(lock)` indicates whether **the current thread** currently holds `lock`'s intrinsic lock; this method is useful when testing/debugging. Do not use the check result as a substitute for actual locking, and do not confuse it with asking which lock another thread is holding.

When exiting a `synchronized` block/method, including via an exception, the JVM automatically releases the corresponding monitor ownership level. Thanks to *reentrancy*, the same thread can lock that same monitor again in nested calls.

## 3. Ownership contract of `Object.wait/notify/notifyAll`

All three operations are called on a **target object**, so the monitor that must be held also belongs to the **target object**:

| Operation | Requirement at call time | Primary effect |
| --- | --- | --- |
| `lock.wait()` / `wait(timeout)` | Current thread holds `lock`'s monitor | Enters `lock`'s wait set; temporarily releases `lock`'s monitor, then reacquires it before continuing |
| `lock.notify()` | Current thread holds `lock`'s monitor | Selects one thread waiting on `lock` to wake up; does not release the monitor immediately |
| `lock.notifyAll()` | Current thread holds `lock`'s monitor | Wakes up all threads waiting on `lock`; does not release the monitor immediately |

Lacking ownership of the right monitor when calling one of these three operations throws `java.lang.IllegalMonitorStateException`. This is a `RuntimeException` (*unchecked*), so declaring `throws` is not mandatory. It reflects a misuse of the synchronization mechanism, not a normal signal of an empty queue.

Distinguish other cases:
- `wait` declares `InterruptedException` when the thread is interrupted before or during waiting; this is a *checked* exception. Only after reacquiring the monitor does the wait call terminate with this exception.
- `wait(long timeoutMillis)` with a negative duration throws `IllegalArgumentException`; `wait(0)` means waiting with no timeout limit, not waiting 0 milliseconds and returning.
- `notify` does not require a waiting thread to exist; a valid call with no waiters simply wakes no one.

### Wrong: synchronizing on a different object

```java
Object gate = new Object();
Object unrelated = new Object();

synchronized (unrelated) {
    gate.notifyAll(); // IllegalMonitorStateException: does not hold gate's monitor
}
```

**Correct:** use the same object for the lock and the call:

```java
Object gate = new Object();

synchronized (gate) {
    gate.notifyAll(); // Valid, even though there may be no waiting thread at this moment
}
```

Similarly, in a `synchronized` instance method, `this.wait()` is valid while holding `this`'s monitor; however, `other.wait()` is still wrong if `other`'s monitor is not held. A `static synchronized` method locks `TenLop.class`, not a specific instance.

## 4. Runnable Java 17+ program: right and wrong monitors

Create the file `MonitorOwnershipDemo.java`:

```java
public class MonitorOwnershipDemo {
    public static void main(String[] args) throws InterruptedException {
        Object lock = new Object();

        System.out.println("outside=" + Thread.holdsLock(lock));

        try {
            lock.wait(1);
        } catch (IllegalMonitorStateException expected) {
            System.out.println("wait: IllegalMonitorStateException");
        }

        try {
            lock.notify();
        } catch (IllegalMonitorStateException expected) {
            System.out.println("notify: IllegalMonitorStateException");
        }

        try {
            lock.notifyAll();
        } catch (IllegalMonitorStateException expected) {
            System.out.println("notifyAll: IllegalMonitorStateException");
        }

        synchronized (lock) {
            System.out.println("inside=" + Thread.holdsLock(lock));

            lock.notifyAll(); // Valid even when no one is waiting
            lock.wait(1);     // Temporarily releases lock; returns after timeout or early wakeup

            System.out.println("afterWait=" + Thread.holdsLock(lock));
        }

        System.out.println("afterBlock=" + Thread.holdsLock(lock));
    }
}
```

Compile and run (JDK 17 or later):

```bash
javac MonitorOwnershipDemo.java
java MonitorOwnershipDemo
```

Expected output:

```text
outside=false
wait: IllegalMonitorStateException
notify: IllegalMonitorStateException
notifyAll: IllegalMonitorStateException
inside=true
afterWait=true
afterBlock=false
```

Explanation:
1. Before the `synchronized` block, the `main` thread does not own `lock`'s monitor; all three calls must throw the exception.
2. Upon entering `synchronized (lock)`, `Thread.holdsLock(lock)` is `true`.
3. `lock.wait(1)` may finish due to expiration or early wakeup (*spurious wakeup*), but it always reacquires `lock`'s monitor before returning normally. Thus `afterWait=true`.
4. Upon exiting the block, the monitor has been released, so `afterBlock=false`. The exact wait duration is not part of the output to verify.

## 5. Which lock does `wait()` release? What does `notifyAll()` do?

Consider the timeline of two threads coordinating through the `gate` object:

1. Thread A enters `synchronized (gate)`, sees that the condition is not satisfied, and calls `gate.wait()`.
2. A enters the *wait set* associated with `gate` and **releases all monitor hold counts of `gate`**. If A also holds monitors of other objects, those other monitors are not automatically released.
3. Thread B can enter `synchronized (gate)`, update shared state, and call `gate.notifyAll()`.
4. The notified threads move to contend for `gate`'s monitor; B continues holding the monitor until exiting the `synchronized` section.
5. A only resumes execution after reacquiring `gate`, and then **rechecks the condition**.

Therefore, a `notify()` call **does not transfer monitor ownership immediately** to the woken thread. `notify()` also does not guarantee which thread in the wait set is chosen; `notifyAll()` wakes all waiting threads, though they still must acquire the lock one by one.

Do not equate `wait` with `Thread.sleep`: `sleep` does not automatically release held monitors. If you sleep inside `synchronized` waiting for another thread to change a condition under the same monitor, you can block progress yourself.

## 6. Holding the right lock is necessary, but not sufficient

The verification snippet in section 4 proves whether a thread has monitor ownership or not. In real programs, **having the right to call `wait/notify` alone does not guarantee a correct coordination protocol**. One might hold the right `lock` yet read the condition under a different lock, fail to recheck the condition upon waking, or notify before updating the state.

To verify these two separate layers of conditions, examine the following table:

| Question | Rule to verify |
| --- | --- |
| Permitted to call `lock.wait()` / `lock.notifyAll()`? | The current thread itself holds `lock`'s monitor, which can be checked with `Thread.holdsLock(lock)` when debugging. |
| Is the condition data safe? | Every read and write of the shared predicate follows the same `lock`. |
| Can changes be missed? | Check the predicate before waiting and loop again after every return from `wait()`, right inside `synchronized (lock)`. |
| Is the right group woken to proceed? | Update state before signaling; prefer `notifyAll()` when multiple condition types wait, and let each waiter recheck its predicate. |
| Is interruption handled? | Propagate `InterruptedException`, or restore the interrupt flag and terminate cleanly if it cannot be propagated. |

A complete producer–consumer example with a `while` loop is in the lesson **"Use a `while` loop to check the condition before and after waiting"**. Here, the diagnostic focus is **whether the receiver of `wait/notify` is truly the object being synchronized on**; two distinct objects still have different monitors even if `equals()` returns `true`.

## 7. Diagnosing errors in real code

When you see a stack trace at `Object.wait`, `Object.notify`, or `Object.notifyAll` with `IllegalMonitorStateException`, check in order:

1. **Identify the receiver of the call**: for example, `queueLock.wait()` requires `queueLock`'s monitor, not implicitly `this` or `Thread.currentThread()`.
2. **Find the lock region enclosing the call**: is there actually `synchronized (queueLock)` or a `synchronized` method on that exact receiver?
3. **Check identity**: was `new Object()` accidentally created per call, was the lock variable reassigned, was a copy locked, or were two objects that are `equals` but different references used?
4. **Identify the executing thread**: one thread owning a monitor does not grant another thread permission to call `wait/notify` on its behalf.
5. **After fixing ownership**, review the `while` condition, data updates, and `notifyAll` under one monitor to avoid race conditions or lost notifications.

A few typical traps:

| Wrong pattern | Why it is wrong | How to fix |
| --- | --- | --- |
| `lock.wait()` outside `synchronized(lock)` | Does not own `lock` | Place the operation and condition check inside `synchronized(lock)` |
| `synchronized(this) { lock.notify(); }` with `lock != this` | Owns a different monitor | Synchronize on `lock` |
| `synchronized(a) { b.wait(); }` even if `a.equals(b)` | Monitors are based on identity | Use `b` itself as the lock |
| Switching `wait` to `sleep` to "avoid the exception" | `sleep` does not release the monitor, which can stall threads | Use `wait` under the right monitor, or choose an appropriate coordination tool |
| `if (!ready) lock.wait()` | Does not handle spurious wakeups / changed state | `while (!ready) lock.wait()` |
| Calling only `notify()` when multiple condition types wait | May wake a thread that cannot make progress | Consider `notifyAll()` and recheck the condition |

### Boundary with `java.util.concurrent.locks`

`ReentrantLock`/`Condition` has its own ownership rules: `Condition.await()`/`signal()` requires holding the exact `ReentrantLock` bound to the condition. Holding a `ReentrantLock` **does not** automatically mean owning the intrinsic monitor of an `Object` to call `wait/notify`. Do not mix the two locking protocols on the same condition state.

## 8. Self-check

1. In `synchronized (a) { b.notifyAll(); }`, what determines whether the call is valid? **Answer:** the current thread must simultaneously hold `b`'s monitor; holding `a` alone is insufficient if `a` and `b` are different objects.
2. Which object does `static synchronized` on `Demo` lock? **Answer:** `Demo.class`.
3. Does a thread just notified by `notify` run immediately? **Answer:** no; first it must reacquire the monitor after the current owner releases it.
4. Why must `wait()` be placed in a `while` loop? **Answer:** the state must be rechecked after spurious wakeups, lock contention, or changes from another thread.
5. Is `IllegalMonitorStateException` an `InterruptedException`? **Answer:** no; the first is a monitor ownership violation, while the second indicates waiting was interrupted.

**Key takeaway:** `synchronized (x)` grants monitor ownership **of `x` itself to the running thread**. When calling `x.wait()`, `x.notify()`, or `x.notifyAll()`, that exact monitor must be held; after waking up, always recheck the shared state's condition.

## References

- [Java SE 21 — `Object` (`wait`, `notify`, `notifyAll`)](https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/lang/Object.html).
- [Java SE 21 — `IllegalMonitorStateException`](https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/lang/IllegalMonitorStateException.html).
- [Java SE 21 — `Thread.holdsLock`](https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/lang/Thread.html#holdsLock(java.lang.Object)).

# `Object.wait()`, `notify()`, and `notifyAll()` Are `final` Methods in Java

The three methods `wait()`, `notify()`, and `notifyAll()` belong to the `java.lang.Object` class. They enable threads to coordinate through an object's **intrinsic monitor**. An important part of the API contract: all three are declared `final`, so subclasses **cannot override** them to change how these calls are resolved. However, `final` does not mean they cannot be called, cannot be used with `synchronized`, or that a program itself is automatically thread-safe.

## 1. Signatures and scope of `final`

Relevant public signatures in Java 17+ (illustrating API declarations, not a standalone Java class to compile):

```java
public final void wait() throws InterruptedException;
public final native void wait(long timeoutMillis) throws InterruptedException;
public final void wait(long timeoutMillis, int nanos) throws InterruptedException;

public final native void notify();
public final native void notifyAll();
```

- `wait()` places the current thread into the *wait set* of the receiving object while releasing that object's monitor. Before resuming execution after `wait`, the thread must reacquire the monitor.
- `wait(long)` and `wait(long, int)` are timed overloads; `wait(0)` can also wait indefinitely. Timeout expiration only provides an opportunity to wake up; it does not guarantee the application condition is true.
- `notify()` selects **one** thread waiting on the object's monitor to wake up; there is no guarantee which thread is chosen.
- `notifyAll()` wakes up **all** threads waiting on that monitor. The threads still must contend for and reacquire the monitor one by one before continuing.
- All three methods are **instance methods** inherited by every reference class from `Object`. They must be invoked on **the exact object used as the monitor**, such as `monitor.wait()` and `monitor.notifyAll()`.

In the signatures, `final` is a modifier forbidding overriding; `native` (on some overloads) is an implementation detail. The two keywords have different meanings.

## 2. Why are these methods `final`?

Any Java object can be used as a monitor by `synchronized (obj)`. `Object.wait` and `Object.notify/notifyAll` are the standard interface for interacting with the wait/wake mechanism associated with that monitor. Preventing subclasses from overriding methods with the same signatures keeps the invocation contract stable across all object types, avoiding a subclass providing behavior named `wait`/`notify` that breaks the expectations of synchronized code.

The example below **intentionally does not compile**, to demonstrate the restriction of `final`:

```java
class BadMonitor extends Object {
    @Override
    public void notify() { // Compile error: cannot override Object.notify() because it is final
        System.out.println("fake notification");
    }
}
```

Similarly, you cannot override `notifyAll()` or any `wait()` signature declared `final`. Adding a method with a different signature, such as `wait(String reason)`, is at the language level an **overload**, not an override; this naming is confusing and does not carry the monitor-waiting semantics of `Object.wait()`.

A clear distinction is needed: **`final` protects against overriding at the language/API level**; the atomicity of waiting with releasing the monitor and the monitor ownership rules are part of the semantics of Java's synchronization mechanism. `final` is no substitute for proper locking and condition checking.

## 3. Monitor contract when calling `wait` and `notify`

Suppose multiple threads share a `monitor` object and a state variable `ready`. Standard pattern:

```java
synchronized (monitor) {
    while (!ready) {
        monitor.wait();
    }
    // Here the monitor is held again and ready has been verified to be true.
}

// In another thread:
synchronized (monitor) {
    ready = true;
    monitor.notifyAll();
}
```

This is an **illustrative snippet**, assuming `monitor` and `ready` are shared state protected by the same monitor; a complete runnable example is in section 4.

Important sequence:

1. The waiting thread enters `synchronized (monitor)` and holds the monitor. `monitor.wait()` must not be called unless the monitor of `monitor` is currently held.
2. If the condition is not met, `wait()` **releases `monitor`'s monitor** and waits. This allows another thread to enter the `synchronized` block to modify the state.
3. The signaling thread enters the same monitor, updates the state first, and then calls `notify()` or `notifyAll()`. The notification call **does not immediately release the monitor**; release happens when the signaling thread exits the synchronized block (or via the corresponding lock-releasing mechanism).
4. The woken thread must reacquire the monitor. Afterward, the `while` loop **rechecks the condition**, because the condition may have changed, multiple threads may have woken up together, or a *spurious wakeup* (waking up without an expected programmatic notification) may have occurred.

**Reason for using `while` instead of `if`:** shared state decides whether execution can proceed; the wakeup event is not a guarantee that the state will always be true. Notifications are also **not stored** for a future `wait()` call.

Furthermore, `wait()` releases **only the monitor of the receiving object**; if the thread simultaneously holds other monitors, those other monitors are not automatically released by `wait()`.

## 4. Runnable Java 17+ example: waiting for a gate-open signal

File: `ObjectMonitorFinalDemo.java`

```java
import java.util.concurrent.CountDownLatch;

public class ObjectMonitorFinalDemo {
    private static final class Gate {
        private final Object monitor = new Object();
        private boolean open;

        void awaitOpen(CountDownLatch waiting) throws InterruptedException {
            synchronized (monitor) {
                while (!open) {
                    waiting.countDown();
                    monitor.wait();
                }
            }
        }

        void open() {
            synchronized (monitor) {
                open = true;
                monitor.notifyAll();
            }
        }
    }

    public static void main(String[] args) throws InterruptedException {
        Gate gate = new Gate();
        CountDownLatch waiting = new CountDownLatch(1);
        Thread worker = new Thread(() -> {
            try {
                gate.awaitOpen(waiting);
                System.out.println("Worker: continuing");
            } catch (InterruptedException e) {
                Thread.currentThread().interrupt();
            }
        });

        worker.start();
        waiting.await();
        gate.open();
        worker.join();
        System.out.println("Main: finished");
    }
}
```

Compile and run (UTF-8-capable terminal):

```bash
javac -encoding UTF-8 --release 17 ObjectMonitorFinalDemo.java
java ObjectMonitorFinalDemo
```

Stdout:

```text
Worker: continuing
Main: finished
```

Explanation:

- `monitor` is a private lock object, while `open` is the **shared condition** read/written inside the same `synchronized (monitor)` block.
- `awaitOpen` waits while `open == false`; when calling `monitor.wait()`, the thread releases the monitor so `open()` can acquire the lock, set `open = true`, and call `notifyAll()`.
- `CountDownLatch waiting` only serves as a coordination step in the **demo**: it forces the main thread to wait until the worker is about to wait. Because the worker holds `monitor` until calling `wait()`, the main thread cannot open the gate before the worker releases the monitor. This is not a mandatory requirement for using `wait/notifyAll`.
- `worker.join()` ensures the line `Worker: continuing` appears before `Main: finished`. The example was compiled and run with JDK 21 targeting `--release 17`.

In the example, `Gate` also inherits the `final` methods of `Object`, but a better practice is to declare a private, non-public `monitor` object to avoid external code interfering with the same lock.

## 5. Choosing `notify()` vs `notifyAll()`

| Method | Effect | When to use |
| --- | --- | --- |
| `notify()` | Wakes up an arbitrary thread in the object's wait set | When it has been **proven** that any waiting thread can handle the new state without stalling progress |
| `notifyAll()` | Wakes up all threads waiting on the same object; each thread must reacquire the monitor | Easier-to-reason-about choice when there are multiple conditions or multiple kinds of waiting threads; always check the condition with `while` |

`notifyAll()` can cause many threads to wake up and then wait again, so it has lock contention overhead; it **does not** let threads run concurrently inside the same monitor. `notify()` can cause stalls if it wakes a thread that cannot proceed while a thread that needs to wake up remains waiting. When the waiter-selection condition has not been clearly proven, prioritize correctness with `notifyAll()`.

## 6. Common errors and how to avoid them

**Calling without owning the right monitor.** The following snippet will throw `IllegalMonitorStateException` at runtime:

```java
Object lock = new Object();
lock.notifyAll(); // Not synchronized(lock)
```

Correct is:

```java
Object lock = new Object();
synchronized (lock) {
    lock.notifyAll();
}
```

`wait()` also requires ownership of the corresponding monitor. `synchronized (this)` does not allow calling `other.wait()` unless `other`'s monitor is also held.

**Using `if` to check the condition before waiting.** Spurious wakeups may occur or another thread may have changed the condition. Use a `while (!condition) lock.wait()` loop, reading/writing `condition` under the same lock.

**Confusing `Thread.sleep()` with `Object.wait()`.** `Thread.sleep(...)` pauses the thread but **does not release** monitors held by the thread; `Object.wait()` releases the monitor of the receiving object. `sleep` is not a mechanism for receiving `notify`.

**Assuming `notifyAll()` lets threads run immediately.** The signaling thread still holds the monitor until it exits the synchronized block; the notified threads can only contend afterward to reacquire the lock.

**Confusing signals with state.** If `notifyAll()` is called when no one is waiting, no notification is remembered. Always store meaningful state (`open`, number of elements in a queue, cancellation flag...) and check that state in a loop.

**Ignoring thread interruption.** `wait()` can throw `InterruptedException`. When interrupted while waiting, the thread must reacquire the monitor before the method finishes throwing the exception. If you catch the exception and cannot handle it there, you should typically propagate it or restore the interrupt flag with `Thread.currentThread().interrupt()` as shown in the example.

**Assuming `final` means thread-safe.** A class can call `wait()`/`notifyAll()` with the right signatures and still be wrong due to unsynchronized state access, using different monitors, waiting on the wrong condition, or cross-locking. A proper thread-coordination protocol must be designed.

## 7. How to remember and apply

- **`final`:** cannot override `wait`, `notify`, `notifyAll` with `Object`'s standard signatures.
- **Same monitor:** `synchronized(lock)`, `lock.wait()`, and `lock.notifyAll()` must refer to the exact same `lock` object.
- **The condition is what matters:** update state under the lock, wait using `while`; `notify/notifyAll` is only a signal to recheck.
- **No ordering expectations:** `notify()` does not pick a waiter in a guaranteed order; `notifyAll()` does not guarantee scheduling order.

In applications with complex coordination, higher-level APIs like `BlockingQueue`, `CountDownLatch`, or `Lock`/`Condition` are often easier to control. They do not change the core fact: the standard monitor methods inherited from `Object` remain `final`.

### Self-check

1. Why does `@Override public void notify()` in a subclass produce an error? — Because `Object.notify()` is `final`.
2. Can a thread holding `synchronized (a)` call `b.wait()`? — Only if it **also** owns `b`'s monitor; holding `a`'s monitor is not enough.
3. Right after `notifyAll()`, do all waiting threads immediately continue past `wait()`? — No. Each thread must first reacquire the monitor and recheck the condition in a `while` loop.

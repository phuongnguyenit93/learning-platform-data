# Identifying `wait()`, `notify()`, `notifyAll()`, and the Lock Object in Java

In Java, every ordinary object has an **intrinsic monitor** (also called a *monitor lock* or *intrinsic lock*). The `synchronized` mechanism enables a thread to **acquire monitor ownership** before accessing a shared-state region; the three methods `wait()`, `notify()`, and `notifyAll()` of `java.lang.Object` enable threads to **coordinate based on state conditions** when using that same monitor.

The most important question when reading multithreaded code is not just “which thread is waiting?”, but also:

> **Which object is acting as the lock? Which thread owns that object's monitor? Which threads are waiting in the wait set associated with that exact object?**

A minimal example:

```java
final Object lock = new Object();
boolean ready = false;

// Waiting thread:
synchronized (lock) {
    while (!ready) {
        lock.wait();
    }
    // Reached only when the condition is true.
}

// Signaling thread, at a different time:
synchronized (lock) {
    ready = true;
    lock.notifyAll();
}
```

These are **two snippets for two threads in a complete synchronization design**, not a standalone runnable Java file as written above. Each thread must check and modify `ready` **under the same `lock` monitor**. Learners need to remember four facts:

1. `wait()`, `notify()`, and `notifyAll()` are **instance methods on `Object`**, not static methods of `Thread`.
2. To call one of the three methods on the `lock` object, the current thread must **currently hold the monitor of `lock` itself**, typically via `synchronized (lock)`.
3. `lock.wait()` **releases the `lock` monitor atomically with transitioning the thread into the waiting state**; the thread can continue only after satisfying the wakeup mechanism and **reacquiring that monitor** (or being interrupted according to the rules).
4. `lock.notify()` wakes up **an arbitrary waiter** on the wait set of `lock` (if any); `lock.notifyAll()` wakes up **all waiters** on that wait set. The signaling thread **still holds the monitor** until it exits the `synchronized` region or releases the lock via an appropriate mechanism.

This article accurately explains monitor identity, syntax, the wait/wakeup lifecycle, the difference between `wait` and `sleep`, why `while` must be used, how to avoid missed signals (*lost notification*), `InterruptedException` handling, a producer–consumer example, and when to use `java.util.concurrent` utilities instead of low-level monitors. All standalone runnable examples use **Java 17+**, with file names, `javac`/`java` commands, and stdout designed **not to depend on arbitrary scheduling order**.

## 1. These Three Methods Belong to `Object`, Not `Thread`

The main methods have the form:

```java
public final void wait() throws InterruptedException;
public final void wait(long timeout) throws InterruptedException;
public final void wait(long timeout, int nanos)
        throws InterruptedException;

public final void notify();
public final void notifyAll();
```

These are **API signatures for identification**, not a new class declaration snippet. These methods are provided by `java.lang.Object`; `wait()`/`notify()`/`notifyAll()` are `final`, so subclasses cannot override them.

Because every ordinary class inherits from `Object`, you may see:

```java
Object lock = new Object();
lock.wait();
lock.notify();
lock.notifyAll();
```

However, **merely being able to write the syntax does not mean calling them is valid at runtime**. These methods require the current thread to hold the corresponding monitor. Calling `lock.wait()` or `lock.notify()` when not holding `lock` will cause an `IllegalMonitorStateException`. `wait` in particular can also throw `InterruptedException`.

### Do Not Confuse with `Thread.sleep`

```java
Thread.sleep(100);
```

is a static method call belonging to `Thread`. It is **not** a call into the wait set of `lock`, and `sleep` itself **does not release the monitor** that the thread is holding.

Similarly:
- `Thread.join()` is an API for waiting for a thread to finish, but its usage/contract at the application level differs from the direct `lock.wait()` mechanism.
- `Object.wait()` is coordination using a monitor and a condition predicate.
- `Condition.await()` is an analogous mechanism at the `java.util.concurrent.locks` layer, but it must be used with the corresponding `Lock`/`Condition`.

## 2. What Is a Monitor?

A **monitor** in Java's synchronization model is attached to an object. When executing:

```java
synchronized (lock) {
    // critical section
}
```

the thread must acquire the intrinsic monitor of **the object referenced by the `lock` expression**. At the same time, **no two different threads** simultaneously hold ownership of that monitor.

A thread that already holds a monitor can enter another `synchronized` region with the **same monitor** through *reentrancy*. Those nested entries belong to the **same thread**, rather than granting access to another thread.

### Two Things a Monitor Helps Solve

1. **Mutual exclusion:** protects a critical section from improper concurrent access.
2. **Ordering/visibility under the Java Memory Model:** an unlock operation on a monitor *happens-before* the next successful lock operation on that same monitor, helping the subsequent thread observe properly published updates.

`wait`/`notify` additionally uses **condition synchronization**: not only locking data, but also keeping a thread from proceeding until a business condition is true.

### A Monitor Is Not a `boolean` Variable

`boolean ready` is only the **state condition**. `Object lock` is the **object used for synchronization**.

```text
Shared state: ready = false
Protecting monitor: lock object
Waiting thread: owns lock -> checks ready -> lock.wait()
Signaling thread: owns lock -> sets ready=true -> lock.notifyAll()
```

Do not confuse “a thread is waiting for ready” with “ready is the monitor object”. The condition can be `int count`, queue size, open/closed status, job completed..., but all related accesses must be synchronized properly.

## 3. `synchronized` Determines the Lock Object

There are three common ways this appears:

| Code | Monitor Used |
| --- | --- |
| `synchronized (lock) { ... }` | The runtime object referenced by `lock` |
| `synchronized void method() { ... }` (instance method) | `this`, i.e., the receiver object |
| `static synchronized void method() { ... }` | `SomeClass.class`, i.e., the corresponding `Class` object |

It is **not** true that “all synchronized methods of a class share a single lock”. Two different instances of the same class have **two different `this` monitors**.

### ASCII Illustration

```text
Counter a = new Counter();
Counter b = new Counter();

a.increment() instance synchronized -> monitor of a
b.increment() instance synchronized -> monitor of b
Counter.resetAll() static synchronized -> monitor of Counter.class
```

These three monitors are **different**. If the state to protect belongs to a counter instance, an instance lock may be correct. If the state is static shared data, per-instance locking is not sufficient to protect the entire program.

### How to Check Whether You Hold a Monitor

`Thread.holdsLock(Object)` returns `true` if the **current thread** holds the intrinsic monitor of the specified object. It does not report “another thread is holding the lock”.

## 4. Program: Identifying Which Monitor Is Held

Save **`MonitorIdentityDemo.java`**:

```java
public class MonitorIdentityDemo {
    private final Object lock = new Object();

    private synchronized boolean holdsThis() {
        return Thread.holdsLock(this);
    }

    private boolean holdsDedicatedLock() {
        synchronized (lock) {
            return Thread.holdsLock(lock);
        }
    }

    public static void main(String[] args) {
        MonitorIdentityDemo demo = new MonitorIdentityDemo();

        System.out.println(Thread.holdsLock(demo));
        System.out.println(demo.holdsThis());
        System.out.println(demo.holdsDedicatedLock());

        synchronized (demo.lock) {
            System.out.println(Thread.holdsLock(demo.lock));
            System.out.println(Thread.holdsLock(demo));
        }
    }
}
```

Run with Java 17+:

```bash
javac -encoding UTF-8 MonitorIdentityDemo.java
java MonitorIdentityDemo
```

**Exact stdout:**

```text
false
true
true
true
false
```

Explanation:
- Initially, `main` does not hold `demo`'s monitor.
- Upon entering the `synchronized` instance method `holdsThis()`, the thread holds the monitor `this == demo`.
- Upon entering `synchronized(lock)`, the thread holds the separate monitor `demo.lock`.
- Holding `demo.lock` does not automatically make the thread hold `demo`. **Monitor identity is per specific object**, not just per class or method containing the code.

## 5. Monitor Ownership Rules When Calling `wait/notify`

For:

```java
lock.wait();
lock.notify();
lock.notifyAll();
```

the thread **must currently hold the monitor of `lock`** at the time of the call.

Valid example:

```java
synchronized (lock) {
    lock.notifyAll();
}
```

Invalid example:

```java
synchronized (otherLock) {
    lock.notifyAll(); // Not guaranteed to hold the lock monitor!
}
```

Even if both variables have type `Object` and the two objects are created close together, they still have different identities.

**The decisive point is the receiver object of the** `wait/notify/notifyAll` call, not the object of just any synchronized block.

If `lock == otherLock` because the two variables alias the same object, the thread will hold the right monitor. Otherwise, holding only `otherLock` does not satisfy the requirement.

### The Monitor of `this`

In a `synchronized` instance method, you can usually call:

```java
synchronized void awaitReady() throws InterruptedException {
    while (!ready) {
        wait();  // Equivalent to this.wait().
    }
}
```

because the implicit receiver is `this` and the thread holds the `this` monitor. However, if inside it you call `someOtherObject.wait()`, you must separately hold the monitor **of someOtherObject**.

## 6. The Clearest `IllegalMonitorStateException` Error

Save **`WrongMonitorDemo.java`**:

```java
public class WrongMonitorDemo {
    public static void main(String[] args) {
        Object first = new Object();
        Object second = new Object();

        synchronized (first) {
            try {
                second.notify();
            } catch (IllegalMonitorStateException error) {
                System.out.println("notify: wrong monitor");
            }

            try {
                second.notifyAll();
            } catch (IllegalMonitorStateException error) {
                System.out.println("notifyAll: wrong monitor");
            }

            try {
                second.wait();
            } catch (IllegalMonitorStateException error) {
                System.out.println("wait: wrong monitor");
            } catch (InterruptedException error) {
                Thread.currentThread().interrupt();
            }
        }
    }
}
```

```bash
javac -encoding UTF-8 WrongMonitorDemo.java
java WrongMonitorDemo
```

**Stdout:**

```text
notify: wrong monitor
notifyAll: wrong monitor
wait: wrong monitor
```

In the program, `main` holds `first`, yet the calls all target `second`. `wait()` does not actually transition to waiting because the monitor ownership condition has not been satisfied.

**Do not fix this by simply adding an arbitrary `synchronized`.** You must wrap the condition check and wait/signal operations with the **same consistent monitor** protecting the shared state.

## 7. What Does `wait()` Do?

With:

```java
synchronized (lock) {
    lock.wait();
}
```

and assuming the thread has not been interrupted and the monitor is properly held:

1. The thread currently holds the monitor of `lock`.
2. Calling `lock.wait()` places the thread into the **wait set** of the `lock` object and **releases ownership of the `lock` monitor** via the atomic mechanism of monitor wait.
3. While the thread is waiting, **another thread can enter `synchronized(lock)`** to modify the shared state.
4. The thread can become eligible to wake up due to `notify`, `notifyAll`, an interrupt, a timeout with a timed overload, or a **spurious wakeup**.
5. Before `wait` completes by returning or throwing `InterruptedException`, the thread must **reacquire the `lock` monitor** according to the monitor rules.
6. After `wait` returns normally, the thread is still **inside the synchronized region**, so it continues to hold the `lock` monitor until it exits that region.

**Key point:** `wait` **does not merely sleep**; it **releases the receiver's monitor**, waits, and then **reacquires the monitor before continuing**.

### Does It Release All Held Locks?

**No.** `lock.wait()` releases the monitor of **`lock`**. If the thread is holding **another** monitor due to nested synchronization, it does not automatically release that other monitor.

Conceptual example:

```java
synchronized (outer) {
    synchronized (inner) {
        inner.wait();
    }
}
```

The thread releases `inner` while waiting, yet still holds `outer`. This can create a deadlock if the signaling thread must acquire `outer` in order to update the predicate.

**Design rule:** minimize holding multiple locks while waiting; define a clear lock ordering if required.

## 8. What Does `notify()` Do?

`lock.notify()` selects **an arbitrary thread** waiting in **`lock`'s** wait set (if any) and moves it to the stage where it can compete to reacquire the monitor.

What `notify()` **does not guarantee**:
- Does not guarantee choosing the longest-waiting thread.
- Does not guarantee FIFO.
- Does not guarantee that the notified thread will run immediately.
- Does not make the predicate become true.
- Does not immediately transfer the monitor from the signaling thread to the receiving thread.
- Does not “store a token in advance” if no thread is currently waiting.

You must **update the shared state** appropriately before or together with the notification, under the same monitor.

```java
synchronized (lock) {
    ready = true;
    lock.notify();
}
```

After `notify()`, the signaling thread can still continue running **inside the synchronized block**. The receiving thread must wait until it manages to reacquire the monitor.

### `notify()` When There Is No Waiter

If `notify()` is validly called when the object's wait set is empty, the call wakes up no one and does not accumulate a notification for a future thread to consume. This is one reason why the **state condition** is the truth that must be stored, rather than “notify was sent” by itself.

## 9. What Does `notifyAll()` Do?

`lock.notifyAll()` notifies **all threads currently in the wait set of `lock`**. They then compete to reacquire the monitor according to the JVM mechanism.

**They do not all execute the synchronized region at the same time**: an intrinsic monitor can still only be owned by one thread at a time.

Some threads, after acquiring the monitor, may find that the predicate is still false, because:
- Another thread has already consumed the resource first;
- Multiple kinds of conditions share the same wait set;
- The predicate changed back;
- The thread woke up without a satisfied condition.

Therefore, each waiter must still recheck the condition inside `while`.

### Does `notifyAll` Run Every Thread in the Program?

**No.** It only affects the waiters currently in **the wait set of that exact receiver object**. Threads waiting on a different monitor, sleeping, performing I/O, or waiting on another API are not directly awakened by this `notifyAll`.

## 10. Comparison Table of `wait`, `notify`, and `notifyAll`

| Property | `wait()` | `notify()` | `notifyAll()` |
| --- | --- | --- | --- |
| Declared in | `Object` | `Object` | `Object` |
| Requires owning the receiver monitor? | Yes | Yes | Yes |
| Releases the receiver monitor itself? | Yes, while waiting | No | No |
| Purpose | Temporarily wait for a condition | Signal one arbitrary waiter | Signal all waiters of the object |
| Calling thread blocked by the API itself? | Typically may wait | Not by notify itself | Not by notifyAll itself |
| Can throw `InterruptedException`? | Yes | No | No |
| Can throw `IllegalMonitorStateException`? | Yes | Yes | Yes |
| Guarantees predicate becomes true? | No | No | No |
| Automatically modifies business data? | No | No | No |
| Guarantees FIFO/fairness? | No | No | No |

**Do not interpret `notifyAll` as replacing `while` with `if`.** The two mechanisms serve different roles: notifyAll is **notification**, and while is **proceeding only when the condition is true**.

## 11. Predicate: The Truth That Must Be Checked Inside `while`

A *condition predicate* is an expression describing **when a thread is allowed to proceed**.

Examples:
- `ready == true`.
- `!queue.isEmpty()` so a consumer can take an item.
- `queue.size() < capacity` so a producer can add an item.
- `availablePermits > 0`.
- `closed || hasWork` so a waiter does not hang forever after the service stops.

Correct pattern:

```java
synchronized (lock) {
    while (!ready) {
        lock.wait();
    }
    doWork();
}
```

Error-prone pattern:

```java
synchronized (lock) {
    if (!ready) {
        lock.wait();
    }
    doWork();
}
```

### Why Must `while` Be Used?

There are **at least three reasons**:

1. **Spurious wakeup:** Java allows `wait` to return without a corresponding notification; it must be rechecked.
2. **Condition contention:** the waiter was notified, but before it acquires the monitor, another thread may turn the predicate false or consume the resource.
3. **Multiple conditions sharing the same wait set:** `notifyAll` also wakes up waiters that do not belong to the condition that became true.

The `while` loop checks the condition **after the lock has been reacquired** before allowing the protected action to run.

## 12. Minimal Coordination Program with Deterministic Output

Save **`WaitNotifyHandshakeDemo.java`**:

```java
public class WaitNotifyHandshakeDemo {
    private static final Object LOCK = new Object();
    private static boolean ready;

    public static void main(String[] args)
            throws InterruptedException {

        Thread worker = new Thread(() -> {
            synchronized (LOCK) {
                ready = true;
                LOCK.notifyAll();
            }
        }, "worker");

        synchronized (LOCK) {
            worker.start();

            while (!ready) {
                LOCK.wait();
            }

            System.out.println("ready = " + ready);
        }

        worker.join();
        System.out.println("worker finished");
    }
}
```

```bash
javac -encoding UTF-8 WaitNotifyHandshakeDemo.java
java WaitNotifyHandshakeDemo
```

**Stdout:**

```text
ready = true
worker finished
```

Analysis not relying on chance:
1. Main enters `synchronized(LOCK)`, holding the monitor.
2. Main calls `start` on the worker while still holding the monitor; the worker must wait to enter the synchronized region.
3. Main sees `ready == false`, so it calls `LOCK.wait()`, **releasing LOCK**.
4. The worker acquires LOCK, sets `ready = true`, and then calls `notifyAll()`.
5. The worker exits the synchronized region and releases LOCK.
6. Main reacquires LOCK and checks `while`; `ready` is already true, so it prints the first line.
7. Main leaves the synchronized region and calls `join` on the completed worker; it prints the second line.

**Why does it not deadlock?** Because main **releases the monitor while waiting**, giving the worker a chance to acquire the monitor and update the condition.

**Note:** `join()` is called **outside synchronized(LOCK)**. If main holds LOCK and then calls join while the worker needs LOCK to finish, that is a form of deadlock.

## 13. What Do `wait` and Monitor Release Mean?

If main does not release the monitor, the worker cannot enter:

```java
synchronized (LOCK) {
    while (!ready) {
        // Busy-spin inside the synchronized block: WRONG.
    }
}
```

The worker needs `LOCK` to set `ready = true`, so it makes no progress. Even using `Thread.sleep(...)` inside the loop **does not release LOCK**, so it does not resolve the bottleneck.

`LOCK.wait()` is especially useful because it coordinates two things:
- **Atomically** releasing LOCK and joining the wait set, avoiding a dangerous gap between “checking the condition” and “starting to wait”.
- When resuming, reacquiring LOCK and then letting the code recheck the condition.

This mechanism makes *guarded suspension* possible to program correctly using an intrinsic monitor.

## 14. Avoiding “Lost Notification” by Checking the Predicate

Design flaw:

```java
// One thread:
synchronized (lock) {
    lock.notifyAll();
}

// Later, another thread:
synchronized (lock) {
    lock.wait(); // May wait forever.
}
```

If the notification occurred when nobody was waiting yet, the wait set is empty; the notification **is not stored**. A thread arriving later may wait forever if no further notification occurs.

A proper design stores the **meaningful event** in state:

```java
synchronized (lock) {
    ready = true;
    lock.notifyAll();
}
```

And on the receiving side:

```java
synchronized (lock) {
    while (!ready) {
        lock.wait();
    }
}
```

If the signal occurred **before** the receiver acquired the monitor, the receiver will see `ready == true` and **will not wait**. If the receiver waits first, the signal updates the predicate and wakes it up. **What needs to persist across the two points in time is the predicate**, not the notify call itself.

### What If the Predicate Turns False Again?

Depending on the domain, the condition may be “an item is currently in the queue”, rather than an event that happened once. Therefore, the consumer needs to check the queue state after each wakeup; an old notification does not grant automatic permission to take an item if the queue has become empty again.

## 15. Program That Does Not Miss Signals Even If the Signal Happens First

Save **`NotifyBeforeWaitSafeDemo.java`**:

```java
public class NotifyBeforeWaitSafeDemo {
    private static final Object LOCK = new Object();
    private static boolean ready;

    public static void main(String[] args)
            throws InterruptedException {

        synchronized (LOCK) {
            ready = true;
            LOCK.notifyAll(); // No waiters yet.
        }

        synchronized (LOCK) {
            while (!ready) {
                LOCK.wait(); // Not called in this case.
            }
            System.out.println("condition already true");
        }
    }
}
```

```bash
javac -encoding UTF-8 NotifyBeforeWaitSafeDemo.java
java NotifyBeforeWaitSafeDemo
```

**Stdout:**

```text
condition already true
```

`notifyAll` before there is a waiter does not “save up a signal”. The program is still correct because **the shared state `ready` was updated and read under the same monitor**.

### Not Every Notification Needs a Boolean Variable

With producer–consumer, a queue containing data itself forms the predicate. With a counter, `count > 0` is the predicate. With a completed request, `result != null || failed` can be the predicate if null is handled properly. What matters is designing **state that represents the actual condition**.

## 16. `notify()` Wakes Up an Arbitrary Waiter

When three threads are all calling `lock.wait()`, a single `lock.notify()`:

- Can select **any one** waiter in the wait set of `lock`.
- Does not necessarily select the waiter that entered the wait set first.
- Does not guarantee that the selected waiter will successfully handle the condition.
- Does not guarantee that the remaining two waiters will automatically be awakened when the predicate changes.

If the signal indicates **only a single new resource**, and **all waiters are waiting on the exact same condition**, `notify()` can be appropriate with a properly designed protocol. However, with multiple different conditions on the same monitor, `notify()` can wake up a waiter **that cannot proceed**, leaving another thread that could proceed unnotified.

### Conceptual Example: Two Kinds of Waiters

```text
Producer waits: queue not full
Consumer waits: queue not empty

Both wait() on lock.
A thread calls notify() -> picks an arbitrary waiter.
If it picks a waiter whose predicate is still false -> no one may make progress.
```

In a simple bounded buffer using **one intrinsic monitor for both “not empty” and “not full”**, `notifyAll()` is usually easier to prove correct.

**Do not choose notify just to “save wakeups” without proving that every state path is able to make progress.**

## 17. `notifyAll()` Does Not “Wake Up Simultaneously to Hold the Lock Together”

In an example with multiple waiters:

```java
synchronized (lock) {
    opened = true;
    lock.notifyAll();
}
```

The waiters are awakened from the wait set, yet **not all of them immediately run the code after `wait()`**. They must **compete and reacquire the lock one thread at a time**. The notifyAll call is only a signal for waiters to attempt to proceed.

This preserves the mutual exclusion of synchronized.

### Which Thread Proceeds Next Is Not Guaranteed by Java

If threads A and B wait together, the program must not assume stdout:

```text
A
B
```

instead of:

```text
B
A
```

unless an additional appropriate ordering mechanism is present. The following examples **do not print based on the scheduler**: they store results and sort them after both threads finish.

## 18. Example of Two Waiters Notified by `notifyAll` with Deterministic Output

Save **`NotifyAllBroadcastDemo.java`**:

```java
import java.util.ArrayList;
import java.util.Collections;
import java.util.List;
import java.util.concurrent.CountDownLatch;

public class NotifyAllBroadcastDemo {
    private static final Object LOCK = new Object();
    private static final CountDownLatch WAITERS_READY =
            new CountDownLatch(2);

    private static boolean opened;
    private static final List<String> resumed = new ArrayList<>();

    private static Thread waiter(String name) {
        return new Thread(() -> {
            synchronized (LOCK) {
                WAITERS_READY.countDown();

                while (!opened) {
                    try {
                        LOCK.wait();
                    } catch (InterruptedException error) {
                        Thread.currentThread().interrupt();
                        return;
                    }
                }

                resumed.add(name);
            }
        }, name);
    }

    public static void main(String[] args)
            throws InterruptedException {

        Thread a = waiter("A");
        Thread b = waiter("B");

        a.start();
        b.start();

        WAITERS_READY.await();

        synchronized (LOCK) {
            opened = true;
            LOCK.notifyAll();
        }

        a.join();
        b.join();

        Collections.sort(resumed);
        System.out.println("resumed = " + resumed);
    }
}
```

```bash
javac -encoding UTF-8 NotifyAllBroadcastDemo.java
java NotifyAllBroadcastDemo
```

**Stdout:**

```text
resumed = [A, B]
```

Why is the result consistent?

1. Each waiter decrements `WAITERS_READY` **inside synchronized(LOCK)** and then executes `LOCK.wait()` while `opened` is false.
2. Main waits for the count to reach 0. The last waiter will release LOCK when entering wait; main sets `opened` only after acquiring LOCK, so there is no “counted down but not yet waiting” gap that causes a missed signal.
3. Main sets the predicate to true and calls `notifyAll()`.
4. Each waiter in turn reacquires LOCK, exits the while loop, and adds its name to `resumed` under the same monitor.
5. Main calls `join` on both threads and then sorts the results before printing.

`CountDownLatch` here only coordinates **when both waiters are ready** so the demo is reliable; the core behavior we want to observe is still **`Object.wait/notifyAll`**.

**Do not infer that the actual execution order is A then B.** Sorting only makes stdout consistent.

## 19. Instance Monitor and Class Monitor

An instance method:

```java
synchronized void await() throws InterruptedException {
    while (!ready) {
        wait(); // this.wait()
    }
}
```

holds the `this` monitor.

A static synchronized method:

```java
static synchronized void signal() {
    SomeClass.class.notifyAll();
}
```

holds the monitor of `SomeClass.class`. If another thread is waiting on `instance.wait()`, `SomeClass.class.notifyAll()` **does not wake up** that waiter: they are **two different object monitors**.

### Common Mistake with a Static Field

Suppose `static boolean ready` is shared across all instances. If each instance uses `synchronized(this)` to protect it, two threads operating on **two different objects** can access the field without unified mutual exclusion.

A shared monitor must be used if all of the state is static:

```java
private static final Object LOCK = new Object();
private static boolean ready;
```

or consider `static synchronized` and the `Class` monitor when that matches the contract.

**Common practice:** use a dedicated `private static final Object LOCK` instead of allowing the class monitor to be used arbitrarily by external code.

## 20. Example of Independent Static and Instance Locks

Save **`InstanceVsClassLockDemo.java`**:

```java
public class InstanceVsClassLockDemo {
    private synchronized boolean instanceLockHeld() {
        return Thread.holdsLock(this);
    }

    private static synchronized boolean classLockHeld() {
        return Thread.holdsLock(InstanceVsClassLockDemo.class);
    }

    public static void main(String[] args) {
        InstanceVsClassLockDemo first = new InstanceVsClassLockDemo();
        InstanceVsClassLockDemo second = new InstanceVsClassLockDemo();

        System.out.println(first.instanceLockHeld());
        System.out.println(classLockHeld());

        synchronized (first) {
            System.out.println(Thread.holdsLock(first));
            System.out.println(Thread.holdsLock(second));
            System.out.println(
                    Thread.holdsLock(InstanceVsClassLockDemo.class));
        }
    }
}
```

```bash
javac -encoding UTF-8 InstanceVsClassLockDemo.java
java InstanceVsClassLockDemo
```

Stdout:

```text
true
true
true
false
false
```

**Explanation:** `instanceLockHeld()` and `classLockHeld()` both check the exact monitor they are holding, so they return true. However, the synchronized block on `first` does not cause the thread to hold `second` or `InstanceVsClassLockDemo.class`.

## 21. Dedicated Lock: `private final Object lock`

Recommended pattern for private state:

```java
final class Gate {
    private final Object lock = new Object();
    private boolean open;

    void open() {
        synchronized (lock) {
            open = true;
            lock.notifyAll();
        }
    }

    void await() throws InterruptedException {
        synchronized (lock) {
            while (!open) {
                lock.wait();
            }
        }
    }
}
```

Advantages:
- **Stable lock identity:** the `final` field is not reassigned after construction.
- **Encapsulation:** external callers cannot directly acquire the private lock to hold it for a long time or notify with the wrong protocol.
- **State + lock share the same owner:** reduces the likelihood of code using two different monitors.
- **Clear condition predicate:** `open` is read and written inside `synchronized(lock)`.

The `final` keyword keeps the reference to the lock unchanged; it does **not** make `open` immutable. `open` remains mutable, but it is protected by the monitor.

### Why Avoid `synchronized(this)` When Unnecessary?

Using `this` is not wrong in terms of the language, but a public object can be used as a monitor by external code:

```java
synchronized (gate) {
    // Caller holds gate's lock for a very long time.
}
```

If `Gate` internally also uses `synchronized(this)`, the caller can accidentally cause contention/deadlock. A private lock reduces **the ability of external users to interfere**.

## 22. Avoid Locking on Interned `String`s or Boxed Numbers

Objects that can be shared unintentionally:

```java
String lock = "GLOBAL";      // String literals can be interned.
Integer number = 100;        // Boxing/cache may share the object.
```

If you use them as monitors, unrelated code may accidentally lock on the same object.

**Not recommended:**

```java
synchronized ("GLOBAL") {
    // May accidentally lock on a shared interned String.
}
```

**Recommended:**

```java
private final Object lock = new Object();
```

For thread coordination, a lock object should:
- Have a distinct, intentionally chosen identity;
- Not have its reference replaced while in use;
- Not be published arbitrarily;
- Accompany a clear set of shared state/conditions.

**Do not use a mutable object that gets replaced with a new one as a lock**, for example reassigning a field `lock = new Object()` mid-lifecycle while multiple threads are still waiting on the old monitor; in that case, signals on the new monitor will not wake up waiters on the old monitor.

## 23. `wait()` vs. `Thread.sleep()`: Precise Distinction

| Property | `Object.wait()` | `Thread.sleep(duration)` |
| --- | --- | --- |
| Belongs to API | Instance method of Object | Static method of Thread |
| Requires `synchronized` receiver? | Yes | No |
| Primary purpose | Wait for predicate/monitor notification | Pause for a duration |
| Releases the waited intrinsic monitor? | Yes, **the receiver monitor** | Does not automatically release any held monitor |
| Wakes up due to `notify`? | Possible | No |
| Wakes up due to timeout? | With timed wait | Has a sleep duration |
| Can be interrupted? | Yes | Yes |
| Has spurious wakeups per contract? | Yes | Not used as a condition wait |
| Needs while predicate? | Yes, for a guarded condition | Sleep does not replace a condition protocol |

### Incorrect Code Example

```java
synchronized (lock) {
    while (!ready) {
        Thread.sleep(10);
    }
}
```

If another thread needs `lock` to modify `ready`, it is locked out. `sleep` does not help release the lock, leading to no progress.

### Correct Code for a Monitor Predicate

```java
synchronized (lock) {
    while (!ready) {
        lock.wait();
    }
}
```

Do not use “sleep 100ms to make sure the producer runs first” as a race-testing tool; thread execution scheduling is not guaranteed by sleeping.

## 24. Timeouts: `wait(long)` and `wait(long, int)`

Three overloads:

```java
lock.wait();                  // Wait with no predetermined timeout.
lock.wait(200L);             // Timed wait with a millisecond timeout.
lock.wait(200L, 500_000);    // Milliseconds + nanos part.
```

The `lock` monitor must be held for all three.

Notes:
- `wait(0)` means **wait indefinitely** except for the specified wakeup causes; it does **not** mean “wait zero and return immediately”.
- `wait(long)` accepts a non-negative millisecond timeout; a negative timeout throws `IllegalArgumentException`.
- The `wait(long, int)` overload has parameter rules in which valid `nanos` values range from `0` to `999_999`; out-of-range values throw `IllegalArgumentException`.
- A timed wait can return because of a signal, interrupt, spurious wakeup, or timeout; **it does not mean the predicate is true**.
- Scheduler/monitor contention can cause the actual elapsed time before the thread resumes to **differ from the passed duration**; do not rely on exact millisecond timing to draw conclusions.

### Using a Timeout with a Condition Loop

```java
synchronized (lock) {
    while (!ready) {
        lock.wait(500L);
        // After every return, ready must still be rechecked.
    }
}
```

This snippet does **not** mean it will exit after 500ms in total; each iteration can wait up to 500ms and repeat infinitely if `ready` stays false.

If the problem requires a **total time limit**, you must compute **remaining time** from a deadline, typically using the monotonic clock `System.nanoTime()` and handling conversion carefully so you do not accidentally call `wait(0)` when the goal is a timeout.

## 25. Timed Wait Program (Without Predicting Elapsed Time)

Save **`TimedWaitDemo.java`**:

```java
public class TimedWaitDemo {
    public static void main(String[] args)
            throws InterruptedException {

        Object lock = new Object();

        synchronized (lock) {
            lock.wait(20L);
            System.out.println("wait returned");
        }

        System.out.println("main continues");
    }
}
```

```bash
javac -encoding UTF-8 TimedWaitDemo.java
java TimedWaitDemo
```

**Stdout:**

```text
wait returned
main continues
```

There is no signaling thread. In a typical run, the timed wait returns once the timeout elapses; Java also allows spurious wakeups. Whatever the reason, the program does not measure or predict exact timing.

**Do not treat a standalone timed wait as a substitute for waiting on a business condition**: a correct program must check the predicate whenever shared state is involved.

## 26. `InterruptedException`: A Thread Can Be Requested to Stop Waiting

`wait()` declares:

```java
throws InterruptedException
```

If the thread is interrupted while waiting (or has the appropriate interrupt status at the time of the call per the contract), the call may throw `InterruptedException` after the necessary monitor steps.

**Important regarding locks:** when a thread is waiting on a monitor and is interrupted, it must perform the monitor reacquisition according to the rules before the `wait` call completes with an exception. It does not “escape the synchronized block” while bypassing monitor control.

In a handler:

```java
try {
    lock.wait();
} catch (InterruptedException error) {
    Thread.currentThread().interrupt();
    return;
}
```

**Recommendation:** if a method cannot handle the interrupt meaningfully, **propagate** `InterruptedException` up to the caller. If catching the exception at a boundary and wanting to preserve the interruption request, restore the interrupt status with `Thread.currentThread().interrupt()`, then terminate in a controlled manner.

**Do not silently swallow the interrupt:**

```java
catch (InterruptedException ignored) {
    // No handling policy: easily causes the thread to refuse to stop.
}
```

## 27. Example of Interrupting a Waiter with Deterministic Output

Save **`InterruptWaitDemo.java`**:

```java
import java.util.concurrent.CountDownLatch;
import java.util.concurrent.atomic.AtomicBoolean;

public class InterruptWaitDemo {
    public static void main(String[] args)
            throws InterruptedException {

        Object lock = new Object();
        CountDownLatch entered = new CountDownLatch(1);
        AtomicBoolean interrupted = new AtomicBoolean();

        Thread worker = new Thread(() -> {
            synchronized (lock) {
                entered.countDown();

                try {
                    lock.wait();
                } catch (InterruptedException error) {
                    interrupted.set(true);
                    Thread.currentThread().interrupt();
                }
            }
        });

        worker.start();
        entered.await();
        worker.interrupt();
        worker.join();

        System.out.println("interrupted = " + interrupted.get());
        System.out.println("worker alive = " + worker.isAlive());
    }
}
```

```bash
javac -encoding UTF-8 InterruptWaitDemo.java
java InterruptWaitDemo
```

**Stdout:**

```text
interrupted = true
worker alive = false
```

Immediately after `entered.countDown()`, the worker may or may not have entered `lock.wait()` yet. Both cases are valid:
- If the worker is already waiting, the interrupt causes wait to throw the exception after reacquiring the monitor.
- If the interrupt occurs before wait actually transitions to waiting, `wait` still handles the interrupt status per the contract.

Therefore, the test uses a latch and interrupt, **not sleep hoping the race happens in the right order**.

AtomicBoolean is used to pass information to main; `join()` also guarantees the worker has finished before main prints the status.

## 28. Easily Confused `Thread.State` States

Java defines the following states:

- `NEW`: the thread has not been started yet.
- `RUNNABLE`: currently executing or eligible to run under JVM semantics.
- `BLOCKED`: waiting to acquire a monitor to enter a synchronized block/method.
- `WAITING`: waiting indefinitely via an API such as `Object.wait()` without a timeout, `Thread.join()` without a timeout...
- `TIMED_WAITING`: waiting for a bounded duration, such as timed wait or sleep.
- `TERMINATED`: has finished.

**Key differences:**

```text
Thread B wants to enter synchronized(lock)
while Thread A is holding lock
  -> B may be in BLOCKED (waiting for monitor).

Thread B already owns lock and calls lock.wait()
  -> B releases lock, then may be in WAITING.

Thread A calls notifyAll, while still holding lock
  -> B does not run the code after wait yet;
     B still needs to reacquire the monitor, and may be in BLOCKED.
```

You should not write tests requiring the state to always be `WAITING` at a specific point in time without a race-control mechanism; `getState()` is a **racy snapshot** across threads.

### `WAITING` Does Not Mean “Waiting for an Object Lock”

A `WAITING` thread might be in `Thread.join()` or waiting on another mechanism. To determine **which monitor** is involved, you must read the code/protocol or use an appropriate thread dump/stack inspection tool.

## 29. `notify` Does Not Immediately Hand Off the Monitor

A scenario:

```java
synchronized (lock) {
    ready = true;
    lock.notifyAll();
    doSomeLongCalculation();
}
```

While `doSomeLongCalculation()` is still running and the signaling thread still holds the monitor, waiters that have already been notified still **cannot proceed past `wait()`** until they reacquire the monitor.

Therefore, it is better when possible:

```java
synchronized (lock) {
    ready = true;
    lock.notifyAll();
}

// Long work is performed outside the lock-holding region.
doSomeLongCalculation();
```

This optimization must preserve **the correctness of the invariant**. Do not arbitrarily move an operation that requires atomicity outside the critical section if doing so changes the program's meaning.

### Avoid Holding a Lock While Calling Uncontrolled Code

Callbacks/HTTP calls/SQL queries under `synchronized(lock)` can hold the monitor for a very long time, blocking both waiters and signallers. Limit the protected region strictly to the shared state.

## 30. Producer–Consumer: The Classic Problem

We have a **shared queue/buffer**:
- The producer waits when the queue is **full**.
- The consumer waits when the queue is **empty**.
- A producer `put` that turns the queue from empty to having an item can wake up a consumer.
- A consumer `take` that turns the queue from full to having room can wake up a producer.

Two conditions:

```java
while (queue.size() >= capacity) {
    lock.wait(); // Producer waits for "not full".
}

while (queue.isEmpty()) {
    lock.wait(); // Consumer waits for "not empty".
}
```

When both share the same lock object, **`notifyAll()`** is normally chosen after modifying the queue. Awakened waiters must recheck their own predicate.

### Why Is the Queue Better State Than a Notification?

The queue reflects **whether items remain or not**, even when the producer creates an item before the consumer begins waiting. A notification is not stored; an item in the queue remains there until the consumer takes it.

**This is the essence of proper condition waiting:** waiting for **state**, not waiting for “an abstract notify call”.

## 31. Simple Example: One Producer, One Consumer

Save **`SingleItemBufferDemo.java`**:

```java
import java.util.concurrent.CountDownLatch;

final class OneSlotBuffer {
    private final Object lock = new Object();
    private Integer value;

    void put(int next) throws InterruptedException {
        synchronized (lock) {
            while (value != null) {
                lock.wait();
            }

            value = next;
            lock.notifyAll();
        }
    }

    int take(CountDownLatch waiting)
            throws InterruptedException {

        synchronized (lock) {
            while (value == null) {
                waiting.countDown();
                lock.wait();
            }

            int result = value;
            value = null;
            lock.notifyAll();
            return result;
        }
    }

    boolean isEmpty() {
        synchronized (lock) {
            return value == null;
        }
    }
}

public class SingleItemBufferDemo {
    public static void main(String[] args)
            throws InterruptedException {

        OneSlotBuffer buffer = new OneSlotBuffer();
        CountDownLatch waiting = new CountDownLatch(1);
        int[] received = new int[1];

        Thread consumer = new Thread(() -> {
            try {
                received[0] = buffer.take(waiting);
            } catch (InterruptedException error) {
                Thread.currentThread().interrupt();
            }
        });

        consumer.start();
        waiting.await();
        buffer.put(42);
        consumer.join();

        System.out.println("received = " + received[0]);
        System.out.println("buffer empty = " + buffer.isEmpty());
    }
}
```

```bash
javac -encoding UTF-8 SingleItemBufferDemo.java
java SingleItemBufferDemo
```

**Stdout:**

```text
received = 42
buffer empty = true
```

Why is there no race?
1. The consumer starts and acquires the buffer's lock.
2. The queue is empty, so the consumer signals the latch and calls `lock.wait()`; releasing the lock is part of the wait operation.
3. Main waits on the latch before calling `put(42)`.
4. The producer (main) can enter the synchronized `put` only after the consumer releases the lock; it then sets the item and calls `notifyAll`.
5. The consumer reacquires the lock, sees the item, receives 42, clears the slot, calls `notifyAll`, and returns.
6. Main calls `join` on the consumer before reading the result.

**Limitation of the example:** it uses a single `Integer` slot and does not use `null` as a valid item. For a general API, there must be a clear contract on whether null can be inserted into the queue.

## 32. Multi-Threaded Producer–Consumer: Bounded Buffer

With multiple producers/consumers, you need to protect:
- `size() < capacity` before putting.
- `!queue.isEmpty()` before taking.
- Any update to the queue.
- `notifyAll` after the state may allow another waiter group to proceed.

A complete example using `ArrayDeque`, a dedicated monitor, and two methods:
- `put` waits until there is room.
- `take` waits until there is an element.

**Because the monitor is properly held across checking, modifying, and signaling**, there is no check-then-act gap that would cause two consumers to take the same item.

## 33. Complete Java 17 Bounded Buffer Program

Save **`BoundedBufferDemo.java`**:

```java
import java.util.ArrayDeque;
import java.util.ArrayList;
import java.util.Collections;
import java.util.List;

final class BoundedBuffer<T> {
    private final Object lock = new Object();
    private final ArrayDeque<T> queue = new ArrayDeque<>();
    private final int capacity;

    BoundedBuffer(int capacity) {
        if (capacity <= 0) {
            throw new IllegalArgumentException("capacity <= 0");
        }
        this.capacity = capacity;
    }

    void put(T value) throws InterruptedException {
        synchronized (lock) {
            while (queue.size() == capacity) {
                lock.wait();
            }

            queue.addLast(value);
            lock.notifyAll();
        }
    }

    T take() throws InterruptedException {
        synchronized (lock) {
            while (queue.isEmpty()) {
                lock.wait();
            }

            T value = queue.removeFirst();
            lock.notifyAll();
            return value;
        }
    }

    int size() {
        synchronized (lock) {
            return queue.size();
        }
    }
}

public class BoundedBufferDemo {
    public static void main(String[] args)
            throws InterruptedException {

        BoundedBuffer<Integer> buffer = new BoundedBuffer<>(3);
        List<Integer> received =
                Collections.synchronizedList(new ArrayList<>());

        Thread producer1 = new Thread(() -> {
            try {
                for (int i = 1; i <= 5; i++) {
                    buffer.put(i);
                }
            } catch (InterruptedException error) {
                Thread.currentThread().interrupt();
            }
        });

        Thread producer2 = new Thread(() -> {
            try {
                for (int i = 6; i <= 10; i++) {
                    buffer.put(i);
                }
            } catch (InterruptedException error) {
                Thread.currentThread().interrupt();
            }
        });

        Runnable consumeFive = () -> {
            try {
                for (int i = 0; i < 5; i++) {
                    received.add(buffer.take());
                }
            } catch (InterruptedException error) {
                Thread.currentThread().interrupt();
            }
        };

        Thread consumer1 = new Thread(consumeFive);
        Thread consumer2 = new Thread(consumeFive);

        consumer1.start();
        consumer2.start();
        producer1.start();
        producer2.start();

        producer1.join();
        producer2.join();
        consumer1.join();
        consumer2.join();

        Collections.sort(received);

        int sum = received.stream()
                .mapToInt(Integer::intValue).sum();

        System.out.println("received = " + received);
        System.out.println("sum = " + sum);
        System.out.println("buffer size = " + buffer.size());
    }
}
```

```bash
javac -encoding UTF-8 BoundedBufferDemo.java
java BoundedBufferDemo
```

**Stdout:**

```text
received = [1, 2, 3, 4, 5, 6, 7, 8, 9, 10]
sum = 55
buffer size = 0
```

### Why Does the Output Not Depend on Scheduling?

The producers produce the exact values 1..10, once each. The consumers perform a total of exactly 10 `take` calls, and each removal occurs while holding the single monitor, so the same item cannot be taken twice. After joining all threads, main **sorts the received list** before printing; it makes no claim about the original consumption order.

### Why Use `notifyAll`?

The same monitor has **two different predicates**:
- Producers wait for the queue to be not full.
- Consumers wait for the queue to be not empty.

If only `notify()` is called, it may wake up a thread whose condition is not satisfied under certain schedules; that thread goes back to waiting while a group that needs to make progress remains unnotified. `notifyAll` + `while` lets waiters filter themselves by predicate.

### Limitations to Recognize

- `ArrayDeque` does not allow null elements; code receiving null may throw `NullPointerException`. The contract should validate inputs when needed.
- The demo does not implement `close()`/shutdown; a real system needs a way to signal producers/consumers to stop waiting when the service terminates.
- If a thread is interrupted and exits midway, the design needs a cancellation policy, error reporting to the coordinator, and possibly signaling the remaining waiters.
- The program does not promise the order in which elements **are taken**; only the final result set and the sum are deterministic.

In real-world applications, `BlockingQueue` already handles many correctness details and should be preferred unless there is a specific educational or optimization reason.

## 34. Why Can `if (...) wait()` Be Wrong in a Buffer?

Suppose there are two consumers A and B:
1. The queue is empty, and both wait.
2. The producer puts an item and calls notifyAll.
3. Both A and B have a chance to wake up, yet only one consumer takes the item first.
4. When the remaining consumer acquires the monitor, it finds the queue **empty** again.

With:

```java
if (queue.isEmpty()) {
    lock.wait();
}
return queue.removeFirst();
```

the remaining consumer may try to remove from an empty queue.

With:

```java
while (queue.isEmpty()) {
    lock.wait();
}
return queue.removeFirst();
```

it sees that the predicate is still false and continues waiting.

**Spurious wakeup** is another independent reason why using `while` is mandatory for a guarded wait, even when the program “has only one producer and one consumer”.

## 35. `notifyAll` Differs from `notify` in Liveness, Not Just Speed

`notifyAll` has the cost of waking up multiple waiters, often called the *thundering herd* risk. However, **correctness first, optimization second**:

- If there is only one condition and one thread can handle the work, `notify` may suffice once the protocol is proven safe.
- If multiple conditions share a wait set, `notifyAll` is simpler for liveness.
- If there are multiple classes of waiters, `notify` risks picking the wrong group.
- If you want high optimization with two separate wait queues, consider `ReentrantLock` with **two `Condition` objects** (`notEmpty`, `notFull`), or use `BlockingQueue`.

**There is no default FIFO ordering or fairness** for `notifyAll`. It makes eligible waiters contend for the monitor, rather than queuing them according to your schedule.

## 36. Do Not Use `notify` as a Data-Passing Mechanism

The snippet:

```java
synchronized (lock) {
    lock.notifyAll();
}
```

does not pass a message payload to the waiter. Java monitor notification is only **a signal of a potentially relevant state change**.

Data must be stored where appropriate synchronization/happens-before exists:

```java
synchronized (lock) {
    result = 42;
    finished = true;
    lock.notifyAll();
}
```

Waiter:

```java
synchronized (lock) {
    while (!finished) {
        lock.wait();
    }
    int answer = result;
}
```

Because both the producer and consumer use the same lock, memory visibility is established through monitor synchronization, without needing a separate `volatile` flag for this exact protocol.

### Should You Add `volatile`?

It may be unnecessary when **all** accesses to the predicate and related data are performed under the same monitor. `volatile` **does not replace** the atomic check-predicate + wait operation under the same monitor; adding volatile while still checking outside the lock and then waiting can create a race.

## 37. Java Memory Model: Why Does Re-reading State See the Updates?

A core rule: **an unlock on monitor M happens-before every subsequent successful lock on that same M**.

In the protocol:

```java
// Thread A:
synchronized (lock) {
    ready = true;
    lock.notifyAll();
}

// Thread B:
synchronized (lock) {
    while (!ready) {
        lock.wait();
    }
    // read ready and related state
}
```

Thread A updates `ready` while holding the monitor, then releases the monitor. Thread B acquires the monitor before checking further. The memory model guarantees the proper visibility relationship according to monitor synchronization.

**Notification alone does not create the ordering:** acquiring and releasing the same monitor is an essential part. If one thread writes `ready` outside the monitor and another thread reads it outside the monitor without synchronization, you can still have a data race even if there is a notify call elsewhere.

### Do Not Evaluate the Condition Predicate “Outside the Lock”

You should not:

```java
if (!ready) {              // Not protected by lock.
    synchronized (lock) {
        lock.wait();
    }
}
```

Between checking `!ready` and entering synchronized, another thread could set `ready = true`, notify, and finish. This thread could wait forever even though the condition is already true. The right approach is for **checking the predicate and waiting to both be inside synchronized(lock)**.

## 38. Reentrancy and `wait`

Java's intrinsic monitors are **reentrant**: the same thread can acquire a monitor it already owns multiple times through nested synchronized blocks.

Example:

```java
synchronized (lock) {
    synchronized (lock) {
        // The thread is still the owner of the same monitor.
    }
}
```

When `lock.wait()` is called while holding the monitor multiple times, the JVM releases the receiver monitor for the ownership levels required for waiting, and when returning or throwing according to the rules, the thread reacquires the monitor accordingly so the nested synchronized layers remain valid.

**Do not confuse this** with releasing **all different monitors**. If a thread also holds `otherLock`, `lock.wait()` does not automatically release `otherLock`.

### Deadlock Risk When Holding an Outer Lock

```java
synchronized (outer) {
    synchronized (inner) {
        inner.wait();
    }
}
```

If another thread needs outer before it can call `inner.notifyAll()`, it will be blocked because the waiter still holds outer. When designing, avoid nesting locks on multiple monitors during wait operations or establish very clear lock ordering and boundaries.

## 39. `wait`, `notify`, and Visibility Do Not Replace Program Structure

A correct monitor protocol requires:

1. **Clearly declared state**: queue, flag, count, mode.
2. **A stable monitor**: the right lock object for each set of invariants.
3. **All accesses to protected state** are properly synchronized.
4. **Predicate inside while** to decide when a thread may proceed.
5. **Signaling after a state change** that may allow waiters to proceed.
6. **Error/cancellation path**: handling interrupts and shutdown.
7. **Never calling an indefinite wait method** when no thread can make the condition true.
8. **Not holding the lock while doing work that does not need protection**.

You should not treat a `notifyAll()` call as “fixing all synchronization bugs” if the code still has data races, deadlocks, or an inaccurate predicate.

## 40. When Should You Use `java.util.concurrent` Instead?

Many synchronization problems already have higher-level APIs:

| Need | Typically Suitable API |
| --- | --- |
| Producer–consumer buffer | `BlockingQueue` (e.g., `ArrayBlockingQueue`) |
| Waiting for N operations to complete | `CountDownLatch` |
| Synchronizing phases | `Phaser`, `CyclicBarrier` depending on use case |
| Limiting concurrent operations | `Semaphore` |
| Delivering a future result | `CompletableFuture` / `Future` |
| Exclusive lock and multiple wait conditions | `ReentrantLock` + `Condition` |
| Simple counters | `AtomicInteger` / `LongAdder` when appropriate |
| Task scheduling and thread pools | `ExecutorService` |

These APIs provide clearer contracts for many scenarios, reducing the risk of forgetting `while`, using the wrong monitor, or missing a notification.

**However, understanding `Object.wait/notify` remains important**:
- To read and maintain legacy Java code.
- To understand the nature of monitors and `synchronized`.
- To distinguish deadlock, contention, and condition waits.
- To design classes with proper internal synchronization when needed.

## 41. `BlockingQueue` Instead of Hand-Written wait/notify

An example functionally similar to a one-slot buffer, but using the standard library:

Save **`BlockingQueueAlternativeDemo.java`**:

```java
import java.util.concurrent.ArrayBlockingQueue;
import java.util.concurrent.BlockingQueue;

public class BlockingQueueAlternativeDemo {
    public static void main(String[] args)
            throws InterruptedException {

        BlockingQueue<Integer> queue =
                new ArrayBlockingQueue<>(1);

        Thread producer = new Thread(() -> {
            try {
                queue.put(42);
            } catch (InterruptedException error) {
                Thread.currentThread().interrupt();
            }
        });

        producer.start();
        int result = queue.take();
        producer.join();

        System.out.println("received = " + result);
        System.out.println("remaining = " + queue.size());
    }
}
```

```bash
javac -encoding UTF-8 BlockingQueueAlternativeDemo.java
java BlockingQueueAlternativeDemo
```

Stdout:

```text
received = 42
remaining = 0
```

`BlockingQueue` manages the necessary conditions for `put/take` itself according to its contract. Users **do not need** to call `wait/notifyAll` manually or choose a monitor themselves.

**Difference in goal:** `BoundedBufferDemo` above is for learning intrinsic monitors; the `BlockingQueue` example is the commonly preferred choice for production systems.

## 42. `Condition.await/signal` Is Not `Object.wait/notify`

`java.util.concurrent.locks.Condition` goes with a `Lock` such as `ReentrantLock`.

Illustrative example:

```java
ReentrantLock lock = new ReentrantLock();
Condition condition = lock.newCondition();

lock.lock();
try {
    while (!ready) {
        condition.await();
    }
} finally {
    lock.unlock();
}
```

- `condition.await()` releases the corresponding lock per the `Condition` contract while waiting, then reacquires it before returning.
- `condition.signal()` is close in meaning to waking up one waiter from the condition queue.
- `condition.signalAll()` is close in meaning to waking up all waiters of the condition.
- **Do not substitute `Object.wait()` and `Condition.await()` for one another** arbitrarily; each mechanism requires holding the appropriate lock/condition type.

**Advantage of using `Condition`:** a single `ReentrantLock` can have two separate condition queues such as `notEmpty` and `notFull`, making signaling more targeted compared to having only one wait set on an Object monitor.

### Similar Contract

Even when using `Condition.await`, the pattern:

```java
while (!predicate) {
    condition.await();
}
```

is still important because of spurious wakeups and state contention.

## 43. Runnable Example: Two Separate Conditions

Save **`ConditionAlternativeDemo.java`**:

```java
import java.util.concurrent.locks.Condition;
import java.util.concurrent.locks.ReentrantLock;

final class SimpleGate {
    private final ReentrantLock lock = new ReentrantLock();
    private final Condition openedCondition = lock.newCondition();
    private boolean opened;

    void open() {
        lock.lock();
        try {
            opened = true;
            openedCondition.signalAll();
        } finally {
            lock.unlock();
        }
    }

    void awaitOpen() throws InterruptedException {
        lock.lockInterruptibly();
        try {
            while (!opened) {
                openedCondition.await();
            }
        } finally {
            lock.unlock();
        }
    }
}

public class ConditionAlternativeDemo {
    public static void main(String[] args)
            throws InterruptedException {

        SimpleGate gate = new SimpleGate();

        Thread worker = new Thread(() -> {
            try {
                gate.awaitOpen();
            } catch (InterruptedException error) {
                Thread.currentThread().interrupt();
            }
        });

        worker.start();
        gate.open();
        worker.join();

        System.out.println("gate is open");
    }
}
```

```bash
javac -encoding UTF-8 ConditionAlternativeDemo.java
java ConditionAlternativeDemo
```

Stdout:

```text
gate is open
```

The program remains correct if `gate.open()` happens **before the worker actually enters `awaitOpen()`**, because `opened` is the state storing the condition. If the worker is already waiting, signalAll allows it to wake up and recheck. This shows that **the predicate protocol** is just as important as the choice of primitive.

## 44. Important Anti-Patterns

### 44.1. Calling `wait` Outside a Monitor

```java
Object lock = new Object();
// lock.wait(); // Runtime error: does not hold the lock monitor.
```

**Fix:** place it inside `synchronized(lock)` and design a predicate.

### 44.2. Synchronizing on Monitor A While Calling `notify` on B

```java
synchronized (a) {
    b.notifyAll(); // IllegalMonitorStateException if b is not held.
}
```

**Fix:** all waiters and signallers must use the **exact lock object** protecting the state.

### 44.3. `if` Instead of `while`

```java
if (!ready) {
    lock.wait();
}
```

**Fix:** `while (!ready)` to guard against spurious wakeups/contention.

### 44.4. Treating `notify` as a Stored Event

```java
lock.notifyAll();
// A future waiter does not automatically receive a prior “notified permission”.
```

**Fix:** store the state `ready/result/queue`.

### 44.5. Sleeping Under a Monitor

```java
synchronized (lock) {
    Thread.sleep(1000);
}
```

Does not release `lock`. If you only want to sleep, consider sleeping **outside the critical section**; if waiting for a predicate, use wait/condition/a higher-level API.

### 44.6. Locking on a Public or Interned Object

```java
synchronized ("READY") {
    // The lock may be shared unintentionally.
}
```

**Fix:** a private final monitor object.

### 44.7. Forgetting to Stop a Waiter on Shutdown

A waiter that only has:

```java
while (queue.isEmpty()) {
    lock.wait();
}
```

can wait forever if the service has stopped and new items will never arrive.

**Fix:** a `closed` state and the condition:

```java
while (queue.isEmpty() && !closed) {
    lock.wait();
}
```

along with `notifyAll` on close. After the loop, clearly decide whether to return end-of-stream, throw an exception, or drain remaining items depending on the contract.

### 44.8. Catching `InterruptedException` and Ignoring It

Swallowing an interrupt makes cancellation harder. Propagate it or restore the status and then exit/clean up appropriately.

### 44.9. Nesting Locks in the Wrong Order

Thread A holds M1 and waits for M2; thread B holds M2 and waits for M1 → deadlock. `wait` only releases the receiver monitor and does not automatically resolve all cycles.

### 44.10. Checking a Condition Outside the Lock

`if (!ready) synchronized(lock){lock.wait();}` is prone to a lost-notification race. The predicate must be checked and waited on atomically under the same monitor.

## 45. Analysis Problem: Which Lock Must Be Used?

Given the snippet:

```java
final Object a = new Object();
final Object b = new Object();
boolean ready = false;
```

Thread 1:

```java
synchronized (a) {
    while (!ready) {
        a.wait();
    }
}
```

Thread 2:

```java
synchronized (b) {
    ready = true;
    b.notifyAll();
}
```

**What is wrong?**

- Thread 1 waits on the wait set of **a**.
- Thread 2 calls notifyAll on the wait set of **b**.
- b's notify **does not** wake up a's waiter.
- `ready` is read/written under two different monitors, so there is also a data-race/visibility problem.
- It can hang even though thread 2 already set `ready = true`.

**A simple fix:** use **the same monitor `a` or a private final lock** on both sides; read/write `ready` under that monitor and notify that exact object.

## 46. Exercise 1 — Which Class Do the Methods Belong To?

**Question:** Are `wait()`, `notify()`, and `notifyAll()` declared by `Thread` or `Object`?

**Answer:** They belong to **`java.lang.Object`**. `Thread.sleep` belongs to `Thread` and has a different contract.

## 47. Exercise 2 — What Lock Is Required Before `lock.wait()`?

```java
Object lock = new Object();

synchronized (lock) {
    lock.wait();
}
```

**Answer:** The thread must hold **the monitor of `lock` itself**. This snippet satisfies the monitor ownership requirement, but if nobody notifies or interrupts it and no timeout is used, it can wait indefinitely. The example only illustrates the valid call requirement, not a complete program to use in production.

## 48. Exercise 3 — Does `wait` Release `lock`?

```java
synchronized (lock) {
    lock.wait();
}
```

**Answer:** Yes, **the monitor of the receiver `lock`** is released while waiting, and then reacquired before `wait` returns or throws according to the rules. It does not release other monitors that the thread still holds.

## 49. Exercise 4 — Which Thread Does `notify` Wake Up?

There are three waiters A, B, and C in the wait set of lock.

**Answer:** An **arbitrary** thread among those waiting; there is no guarantee that A arrived first or which thread the scheduler will run first. `notify` does not make the predicate true by itself.

## 50. Exercise 5 — Does `notifyAll` Run All Three Threads Simultaneously?

**Answer:** No. It notifies all waiters on the **same object**, yet the threads must **acquire the monitor one by one** to exit wait and proceed through the synchronized region.

## 51. Exercise 6 — Wrong Monitor

```java
Object a = new Object();
Object b = new Object();

synchronized (a) {
    b.notifyAll();
}
```

**Answer:** `IllegalMonitorStateException`, because the thread holds monitor a, not monitor b.

## 52. Exercise 7 — Why Use `while`?

```java
synchronized (lock) {
    while (queue.isEmpty()) {
        lock.wait();
    }
    return queue.removeFirst();
}
```

**Answer:** To check the predicate after a spurious wakeup and after another thread may have consumed the item before the waiter reacquired the monitor. `if` does not provide a sufficient guarantee.

## 53. Exercise 8 — Can `sleep` Replace `wait`?

**Answer:** Not in a monitor condition protocol. `sleep` does not release any held monitor; another thread can be blocked from updating the shared state. `wait` releases the receiver monitor and coordinates with notification/predicate.

## 54. Exercise 9 — Does `wait(0)` Return Immediately?

**Answer:** No. According to the API, `wait(0)` is a **wait with no predetermined timeout**. If you want to wait for at most a certain duration, use a positive timed overload and manage the deadline/predicate properly.

## 55. Exercise 10 — Signal Before Waiter

The producer sets `ready = true` and calls notifyAll when there is no waiter yet. Afterward, the consumer starts.

**Answer:** Notifications are not stored. The consumer still proceeds safely if it checks `while (!ready)` under the right monitor; because `ready` is already true, there is no need to wait.

## 56. Exercise 11 — Which Object Does Static Synchronized Lock On?

```java
class Cache {
    static synchronized void refresh() {
    }
}
```

**Answer:** Uses **the monitor of `Cache.class`**, not the monitor of individual `new Cache()` instances.

## 57. Exercise 12 — Which Object Does Instance Synchronized Lock On?

```java
class Counter {
    synchronized void increment() {
    }
}
```

**Answer:** The monitor of the **receiver `this`**. Two different `Counter` instances have different locks.

## 58. Exercise 13 — Holding Two Locks and Waiting on One

```java
synchronized (outer) {
    synchronized (inner) {
        inner.wait();
    }
}
```

**Answer:** The thread **releases inner** while waiting, yet still holds `outer`. If the signaller needs `outer`, a deadlock can occur.

## 59. Exercise 14 — Interrupted Waiter

A thread is interrupted during `lock.wait()`.

**Answer:** `wait` can throw `InterruptedException`, while the thread reacquires the monitor per the contract before completing the call with an exception. The caller needs an appropriate policy to propagate it, restore the interrupt status, or clean up/exit; the exception should not be swallowed.

## 60. Exercise 15 — Should a Bounded Buffer Use notify or notifyAll?

There are both producers waiting on `notFull` and consumers waiting on `notEmpty` on a single monitor.

**Answer:** `notifyAll` is usually the right choice, making liveness easier to prove in a single-wait-set multi-condition model; every waiter rechecks its predicate in `while`. With two separate `Condition` queues, targeted signaling can be used per the `ReentrantLock` contract.

## 61. Exercise 16 — Can a `volatile` Variable Replace All of Synchronized?

```java
volatile boolean ready;
```

**Answer:** No. `volatile` has its own visibility/ordering semantics, yet does not create an atomic check-then-wait protocol and does not grant monitor ownership to call `wait/notify`. To use Object.wait, you still need synchronized on the proper receiver and to check the predicate under the lock.

## 62. Exercise 17 — Calling `notifyAll` After Exiting Synchronized?

```java
synchronized (lock) {
    ready = true;
}
lock.notifyAll();
```

**Answer:** `IllegalMonitorStateException` if the current thread does not hold the monitor of lock at the `notifyAll` call. Call notifyAll **inside** the appropriate `synchronized(lock)`.

## 63. Exercise 18 — Two References to the Same Lock Object

```java
Object a = new Object();
Object b = a;

synchronized (a) {
    b.notifyAll();
}
```

**Answer:** Valid with respect to **monitor ownership**, because `a == b` refers to the same object. Wakes up no one if the object's wait set is empty. What matters is **object identity**, not the variable name.

## 64. Exercise 19 — Choosing from the Standard Library

Problem: a queue of at most 100 items, with multiple producers and consumers.

**Answer:** In real-world applications, consider `ArrayBlockingQueue<>(100)` or a suitable `BlockingQueue` rather than hand-writing `wait/notifyAll`. Understanding intrinsic monitors helps inspect legacy code, while higher-level libraries reduce bug risk.

## 65. Exercise 20 — Which Thread Order Should Stdout Be Printed In?

Two threads are awakened by `notifyAll` and each prints `A`/`B` immediately upon reacquiring the lock.

**Answer:** A fixed order cannot be predicted from notification alone. To make stdout deterministic, collect the results, then `join` and sort, or add an intentional ordering synchronization protocol.

## 66. Checklist When Reading a `wait/notify` Code Snippet

1. **Identify the actual receiver object** of `wait/notify/notifyAll`.
2. **Identify the monitor object being synchronized**: does it have the exact same identity?
3. If using an instance synchronized method, remember the monitor is **`this`**.
4. If using a static synchronized method, remember the monitor is **`ClassName.class`**.
5. Which **variable/queue** is the protected state?
6. Are all reads/writes of the predicate consistently under the **same lock**?
7. Does the waiter check the predicate inside **`while`**?
8. Could there be spurious wakeups, data contention, or signals meant for another condition?
9. Does the signaller **update the state before notifying**?
10. If the signal occurs before the waiter, does the predicate prevent the waiter from hanging?
11. Is any `notify` call made without holding the receiver monitor, causing an exception?
12. Is `wait(0)` used while mistakenly assuming it means “do not wait”?
13. Are timeouts handled with a **true deadline** when needed?
14. Is `InterruptedException` caught and cancellation handled reasonably?
15. Is `wait` being called while the thread holds another monitor that leads to deadlock?
16. Is there a `sleep` or long I/O **inside synchronized** holding the monitor for too long?
17. Are locks nested in opposite orders across threads?
18. Is a `String`/boxed number/public object used as a lock and accidentally shared?
19. Is the lock field **private final** if it needs to be stable and not exposed externally?
20. If there are multiple wait conditions on one lock, is using `notifyAll` or separating `Condition` queues appropriate?
21. Do waiters need a **shutdown/close** signal so they do not wait forever?
22. Is testing relying on scheduler order or `Thread.sleep`?
23. Are `Thread.State.BLOCKED` and `WAITING` being confused?
24. Is it understood that `notifyAll` **does not immediately hand over the monitor** to waiters?
25. If the goal is a queue, latch, or semaphore, would a `java.util.concurrent` API be more suitable?

## 67. Quick Takeaways

- **`wait()`, `notify()`, and `notifyAll()` are `final` instance methods of `java.lang.Object`.**
- Every object has an **intrinsic monitor**; all wait/notify operations must use **the same object monitor** protecting the condition state.
- **`synchronized(lock)`** holds the monitor of the `lock` object; an **instance synchronized method** holds `this`; a **static synchronized method** holds `ClassName.class`.
- **`lock.wait()` releases the `lock` monitor while waiting**, then reacquires it before continuing or completing with an interrupt exception per the rules; it does **not** release other monitors.
- **`lock.notify()`** signals **an arbitrary waiter**; **`lock.notifyAll()`** signals all waiters of **the same lock**, without granting the monitor immediately.
- Always use **`while (!predicate) lock.wait();`**, not `if`, to guard a condition wait.
- **State** such as `ready`/queue is the source of truth; notifications are **not stored** for late-arriving threads.
- `Thread.sleep` **does not release the monitor**, so it cannot replace `wait` in condition synchronization.
- Timeouts, interruption, spurious wakeups, and shutdown all require a **clear handling protocol**.
- For producer–consumer or multi-thread coordination, prefer **`BlockingQueue`, `CountDownLatch`, `Condition`**, or higher-level utilities when they fit the requirements.

When explaining “which thread gets woken up” and “why it does not deadlock”, start with **the identity of the lock object**, **the protected predicate**, and **when threads release/reacquire the monitor**. Those three factors determine the correctness of the program, not thread names or milliseconds of sleep.

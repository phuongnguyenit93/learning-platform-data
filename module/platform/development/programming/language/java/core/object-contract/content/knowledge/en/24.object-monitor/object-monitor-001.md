# Per-Object Monitors in Java and the Synchronization Mechanism

In Java, **every object can be used as an intrinsic lock (commonly called a monitor)**. When a thread enters a `synchronized` block associated with that object, it must own the object's monitor before executing the protected code. This mechanism helps coordinate access to shared data and provides guarantees about the visibility of changes across threads.

> "Every object has a monitor" is the programming model and semantics that Java provides. The JVM can optimize lock representation and allocation at the implementation level; you should not infer that every instance must have a separate monitor structure pre-allocated in memory.

## 1. **Which object** is a monitor associated with?

Example:

~~~java
Object lockA = new Object();
Object lockB = new Object();

synchronized (lockA) {
    // The thread holds the monitor of lockA.
}

synchronized (lockB) {
    // A different monitor, independent of lockA.
}
~~~

- Two threads using **the exact same object** `lockA` will contend for the same intrinsic lock: at any point in time, at most one thread owns that monitor to execute the corresponding `synchronized` section.
- A thread holding the monitor of `lockA` does not automatically prevent another thread from entering `synchronized (lockB)`. Two different locks do not protect each other.
- Every Java object can serve as a lock, including instances of user-defined classes, arrays, and `Class` objects. `null` is not an object; `synchronized (null)` throws `NullPointerException`.
- Reference variables **do not own separate monitors**. Two variables pointing to the same instance share the same lock; two different instances have different locks.

An important example regarding the locked object:

| Syntax | Monitor that must be owned |
| --- | --- |
| `synchronized (someObject) { ... }` | The object that `someObject` points to |
| `synchronized void method()` (instance method) | `this` of the calling instance |
| `static synchronized void method()` | The `SomeClass.class` object corresponding to the declaring class |

Therefore, a `static synchronized` method **does not lock all instances** in the sense of locking `this`. It locks the `Class` object; static synchronization and instance synchronization are usually two different monitors.

## 2. What happens when entering and exiting `synchronized`?

Suppose multiple threads run concurrently:

~~~java
synchronized (lock) {
    // Access shared state protected by lock.
}
~~~

Logical sequence:

1. The thread requests ownership of `lock`'s monitor.
2. If the monitor is free, the thread acquires the lock and runs the body. If another thread is holding it, the current thread cannot enter the body immediately and may transition to the `BLOCKED` state.
3. Upon exiting the block, including when exiting due to an exception, the thread releases the lock according to `synchronized` semantics; a thread waiting for the lock can continue contending to acquire the monitor.
4. Java **does not promise fairness/FIFO** regarding which thread will acquire the lock next.

Monitors are **reentrant**: a thread that already owns a monitor can enter another `synchronized` section on the same object without blocking itself. The JVM tracks the nesting level, and the lock is fully released only after the thread exits all corresponding lock levels.

~~~java
class ReentrantExample {
    synchronized void outer() {
        inner(); // The same thread continues to enter the monitor of this.
    }

    synchronized void inner() {
        // Can execute even though outer() is holding this very monitor.
    }
}
~~~

Remember that only code that actually uses **the same monitor** is protected. A method that reads or writes a shared field while bypassing the lock will not automatically become safe just because another method is `synchronized`.

## 3. Monitors solve two problems: mutual exclusion and visibility

Suppose two threads simultaneously increment a variable:

~~~java
count++;
~~~

Logically, this statement consists of reading the value, computing the new value, and writing it back. It is not automatically an atomic operation. Two threads can read the same stale value and lose an increment.

Complete example, runnable with Java 17 or later:

**File `MonitorCounterDemo.java`**

~~~java
public class MonitorCounterDemo {
    static final class Counter {
        private int count;

        synchronized void increment() {
            count++;
        }

        synchronized int get() {
            return count;
        }
    }

    public static void main(String[] args) throws InterruptedException {
        Counter counter = new Counter();

        Runnable task = () -> {
            for (int i = 0; i < 10_000; i++) {
                counter.increment();
            }
        };

        Thread first = new Thread(task);
        Thread second = new Thread(task);
        first.start();
        second.start();

        first.join();
        second.join();

        System.out.println("Increment count: " + counter.get());
    }
}
~~~

Compile and run:

~~~bash
javac MonitorCounterDemo.java
java MonitorCounterDemo
~~~

Output:

~~~text
Increment count: 20000
~~~

Both threads call `increment()` on **the same `counter` instance**, so they must take turns holding that instance's monitor. `count++` is protected as a critical section; no updates are lost between these two threads. `get()` also goes through that monitor. `join()` ensures `main` waits for both threads to finish before printing the result.

In addition to mutual exclusion, `synchronized` has a **happens-before** rule in the Java Memory Model: an **unlock of a monitor** happens-before every subsequent **lock of that same monitor**. As a result, writes performed before releasing the lock are properly visible through the next acquisition of the same monitor. The "same monitor" condition is critical; locking a different object does not establish this relationship.

Do not attribute every visibility effect to the monitor if an example also uses `Thread.start()`/`Thread.join()`: these thread lifecycle operations have their own happens-before rules as well. The core of `synchronized` is that code reading and writing shared data follows **the same locking policy**.

## 4. Monitors also allow **waiting for a condition** via `wait` / `notify` / `notifyAll`

Beyond lock ownership, every object provides thread-coordination operations inherited from `java.lang.Object`:

- `wait()`: the current thread waits for a signal/condition on the object, **temporarily releasing the monitor of that very object** while waiting.
- `notify()`: wakes up **one** thread waiting on that object, if any; there is no guarantee which thread is chosen.
- `notifyAll()`: wakes up **all** threads waiting on that object so they have a chance to recheck the condition.

To invoke these methods on `obj`, the calling thread must **currently own the monitor of `obj`** (for example, inside `synchronized (obj)` or a synchronized instance method of `obj`). Otherwise, `IllegalMonitorStateException` is thrown. Holding the monitor of **another object** is not enough.

A thread calling `wait()` must reacquire the object's monitor before exiting `wait()` and continuing execution. `notify()` and `notifyAll()` **do not immediately release the lock**: a woken thread can only proceed after the monitor becomes available to reacquire.

You can distinguish two different reasons for waiting:

| Situation | Meaning |
| --- | --- |
| A thread wants to enter `synchronized` while the monitor is held | Waiting to **acquire the lock**; typically observed in the `BLOCKED` state |
| A thread already holds the monitor and calls `wait()` | Releases that monitor and waits for a **condition/signal**; `WAITING`, or `TIMED_WAITING` for timed wait |
| A thread is woken by `notifyAll()` | Must **reacquire the monitor**; may temporarily be `BLOCKED` before exiting `wait()` |

These states help when reading thread dumps; the exact scheduling order still depends on the JVM/operating system.

## 5. Practical condition example: a single-element mailbox

One thread sends a value, another receives it. Both `send()` and `receive()` synchronize on **the `Mailbox` instance itself**. The condition is represented by `message == null`:

**File `MonitorWaitNotifyDemo.java`**

~~~java
public class MonitorWaitNotifyDemo {
    static final class Mailbox {
        private Integer message;

        synchronized void send(int value) throws InterruptedException {
            while (message != null) {
                wait();             // Wait for mailbox to be empty; releases monitor of this.
            }
            message = value;
            notifyAll();            // Signal that the mailbox state has changed.
        }

        synchronized int receive() throws InterruptedException {
            while (message == null) {
                wait();             // Wait for data; releases monitor of this.
            }
            int result = message;
            message = null;
            notifyAll();            // Signal that the mailbox is empty again.
            return result;
        }
    }

    public static void main(String[] args) throws InterruptedException {
        Mailbox mailbox = new Mailbox();
        int[] received = {-1};

        Thread reader = new Thread(() -> {
            try {
                received[0] = mailbox.receive();
            } catch (InterruptedException e) {
                Thread.currentThread().interrupt();
            }
        });
        reader.start();

        mailbox.send(42);
        reader.join();

        System.out.println("Received: " + received[0]);
    }
}
~~~

Run:

~~~bash
javac MonitorWaitNotifyDemo.java
java MonitorWaitNotifyDemo
~~~

Output when there is no thread interruption request:

~~~text
Received: 42
~~~

Execution flow explanation:

1. If `reader` enters `receive()` first, it sees `message == null` and calls `wait()`; waiting releases the monitor so the `main` thread can enter `send()`.
2. `send(42)` stores the value and calls `notifyAll()` while holding the monitor. When `send()` exits the method, it releases the monitor; `reader` reacquires the monitor, checks the condition, and receives `42`.
3. If `main` runs `send(42)` first, `reader` will see that data is already available and will not need to wait. Because the condition state is stored in `message`, the signal is not the data container.
4. After `reader.join()`, `main` reads the written result. The printed output is independent of the scheduling order of the two threads in the non-interrupted case.

**Why must `while` be used instead of `if` around `wait()`?** A thread can wake up without the desired condition being true (*spurious wakeup*), or another thread may have changed the condition during the interval while the thread was trying to reacquire the monitor. Always recheck the **state predicate** under the same monitor. With multiple waiter types/conditions, `notifyAll()` is usually easier to reason about correctly than `notify()`, even though it may cause multiple threads to wake up, check, and wait again.

When `wait()` is interrupted, it throws `InterruptedException` after reacquiring the monitor according to the API semantics; the application should propagate the exception to the coordinator or handle task cancellation explicitly. The example above restores the interrupt flag for the child thread at the `Runnable` boundary. In a real application, there should be a path to handle canceled/failed outcomes rather than assuming a message is always received.

## 6. Clearly distinguishing `wait`, `notify`, `sleep`, and lock contention

| Operation | Requires monitor ownership? | Releases held monitor? | Purpose |
| --- | --- | --- | --- |
| Entering `synchronized (obj)` | Must acquire `obj`'s monitor | No | Protect critical section |
| `obj.wait()` | Yes, of `obj` | Yes, **only `obj`'s monitor** | Wait for a condition on `obj` |
| `obj.notify()` / `notifyAll()` | Yes, of `obj` | No | Notify waiting thread(s) |
| `Thread.sleep(...)` | No | No | Pause for a duration of time |

An easily overlooked detail: if a thread holds multiple nested monitors, `obj.wait()` only releases `obj`'s monitor and **does not release other monitors** that the thread is holding. Holding other locks while waiting can cause the program to deadlock.

The `wait(long timeout)` / `wait(long timeout, int nanos)` variants can finish upon timeout, notification, or waking up for no specific reason; therefore a `while` loop checking the condition is still required. `wait(0)` means wait indefinitely, not "wait 0 milliseconds and return."

## 7. Common mistakes and how to avoid them

**Wrong: locking a new object on every call.**

~~~java
synchronized (new Object()) {
    // Each call usually creates a new lock, providing no coordination with other calls.
}
~~~

To coordinate between threads, share the same stable lock, such as a `private final Object lock = new Object();` field. Avoid locking on string literals, public `Class` objects, or objects that external code can arbitrarily lock if that causes unexpected contention.

**Wrong: calling `wait()` without owning the lock of the exact object.**

~~~java
Object lock = new Object();
lock.wait(); // IllegalMonitorStateException at runtime.
~~~

Correct usage (the snippet below only illustrates syntax; a useful program must have a condition and a signaling thread):

~~~java
synchronized (lock) {
    while (!conditionIsTrue()) {
        lock.wait();
    }
}
~~~

Here `conditionIsTrue()` is an **illustrative** name, not a method defined in the runnable example above.

**Wrong: thinking `notify()` immediately transfers the lock to the receiving thread.** The signaling thread retains the monitor until it exits `synchronized`; the receiving thread must contend again to acquire the lock.

**Wrong: putting `wait()` inside `if` or relying solely on "signals".** A signal is not stored as a "ticket" for latecomers. There must be protected condition state, updated before signaling and checked inside `while`.

**Wrong: reading/writing shared data using different locks.** If writers use `lockA` while readers use `lockB`, they do not guarantee mutual exclusion or happens-before across those two monitors. Design a convention for "which field is protected by which lock" and apply it consistently, including for reads.

**Wrong: holding a lock while running slow tasks, I/O, or calling uncontrolled code.** Other threads have to wait longer; if threads acquire multiple locks in opposite orders, there is also a risk of deadlock. Keep critical sections narrow and fix the acquisition order of multiple locks when needed.

**Wrong: assuming monitors automatically guarantee everything.** Intrinsic locks do not by default guarantee fairness, deadlock detection, timeouts when acquiring a lock with `synchronized`, or waking up only one specific type of waiter when multiple conditions share a wait-set. For queues, real-world applications usually find `BlockingQueue` more convenient; for lock acquisition with timeouts/interruptible acquisition or multiple separate condition queues, consider `ReentrantLock` and `Condition` from `java.util.concurrent.locks`. These are complementary tools and do not alter the monitor mechanism of `Object`.

## 8. Self-check understanding

1. Two variables `a` and `b` point to the same instance: do `synchronized(a)` and `synchronized(b)` contend for the same lock? **Yes**, because the lock is attached to the object, not to the variable name.
2. Do two instances of the same class automatically block each other when calling a `synchronized` instance method? **No**; each instance has its own monitor. `static synchronized` instead uses the `Class` object.
3. Why is using `volatile` alone on `count` insufficient to perform `count++` safely? **Because** visibility does not turn a multi-step read–modify–write operation into an atomic one.
4. After `notifyAll()`, does a thread in `wait()` continue executing immediately? **No**; it still has to reacquire the monitor and recheck the condition.
5. Does calling `Thread.sleep()` inside `synchronized` help another thread acquire that monitor? **No**; `sleep` does not release the lock.

## Conclusion

A monitor is an intrinsic synchronization mechanism attached to **the identity of a Java object**. `synchronized` uses that monitor to protect critical sections and establish visibility rules; `wait`/`notify`/`notifyAll` use the same monitor to coordinate on conditions. When designing multithreaded code, clearly identify **which lock object is shared, which state is protected by that lock, and which condition must be rechecked under the lock**.

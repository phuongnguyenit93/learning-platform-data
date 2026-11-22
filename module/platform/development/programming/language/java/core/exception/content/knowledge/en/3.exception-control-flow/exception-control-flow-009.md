# Releasing a Monitor When Exiting `synchronized` Due to an Exception

## 1. Learning Objectives

In Java, `synchronized` helps multiple threads coordinate access to shared state using an object's *monitor lock*. When a statement inside a `synchronized` block or method throws an exception, the program can exit the code holding the monitor abruptly. Java guarantees that **the corresponding monitor is released when actually exiting the `synchronized` scope**, even when that exit is caused by an exception.

After this lesson, you will be able to explain and verify:

- Which monitor is acquired when using a `synchronized (lock)` block, an instance `synchronized` method, and a `static synchronized` method.
- Why a monitor is released when a block/method completes abruptly (*abrupt completion*) due to `throw` or an exception from an inner call.
- The difference between having `catch` **inside** and **outside** the scope holding the monitor.
- How *reentrant* locking works when the same thread enters `synchronized` on the same object multiple times.
- Why "the lock has been released" does not mean "the data state is consistent," nor does it guarantee that another thread will run immediately.
- How to contrast this behavior with `Object.wait()`, `Thread.sleep()`, and `ReentrantLock`.

The scope of this lesson is **control flow and monitor release when an exception occurs**. Examples use Java 17 or later and only create controlled, ordinary exceptions.

## 2. Monitors and `synchronized` Regions

Every Java object has a monitor that threads can use for synchronization. A thread that wants to enter `synchronized (lock)` must acquire the monitor associated with that exact `lock` reference. While that thread owns the monitor, another thread attempting to acquire **the same monitor** must wait; code that does not synchronize on that monitor is not automatically blocked.

```java
Object lock = new Object();

synchronized (lock) {
    // The current thread holds the monitor of the lock object.
    doWork();
}
// After actually exiting the block, the monitor of lock is released.
```

This is an illustrative snippet; `doWork()` must be defined in an actual program.

Forms of locking:

| Construct | Monitor Acquired | When Is the Monitor Released? |
| --- | --- | --- |
| `synchronized (lock) { ... }` | The object that the `lock` expression evaluates to | When that `synchronized` block completes, normally or abruptly |
| `synchronized void update() { ... }` | `this`, the receiver object of the call | When the `update` method completes |
| `static synchronized void update() { ... }` | The `Class` object representing the class declaring the method | When the static method completes |

**Note:** Two different lock objects represent two different monitors, even if the methods share the same name. An instance `synchronized` method does not automatically synchronize with a `static synchronized` method of the same class: one uses `this`, while the other uses the `Class` object.

### 2.1. Core Rules When an Exception Occurs

According to the Java Language Specification §14.19, for a `synchronized (expression) { body }` block:

1. Java evaluates the expression to obtain the lock object.
2. If evaluation fails with an exception, the block does not acquire a monitor.
3. If the result is `null`, Java throws `NullPointerException`, and no monitor has been acquired either.
4. If there is a valid object, the current thread acquires the monitor and then executes the body.
5. If the body completes normally, Java releases the monitor before proceeding.
6. If the body **completes abruptly for any reason**, including throwing an exception, Java releases the monitor and then continues propagating that reason for exit.

Example of where an exception arises:

```java
synchronized (lock) {
    operationA();
    operationB(); // May throw an exception.
    operationC(); // Skipped if operationB() throws an exception.
}
```

This is illustrative code inside a method, assuming `lock` and `operationA/B/C` have been declared. If `operationB()` throws an exception that is not caught inside, the `synchronized` body exits; Java releases the monitor of `lock` before the exception continues to an outer handler.

This rule applies to checked exceptions, `RuntimeException`, and `Error` objects as long as the block's abrupt completion is still handled by the JVM. However, you cannot rely on this rule to guarantee complete cleanup in every case where the process or JVM terminates abnormally.

## 3. Complete Example: Monitor Is Released When an Exception Exits the Block

Create the file **`MonitorReleaseDemo.java`**:

```java
public class MonitorReleaseDemo {
    private static final Object LOCK = new Object();

    public static void main(String[] args) throws InterruptedException {
        try {
            synchronized (LOCK) {
                System.out.println("inside: " + Thread.holdsLock(LOCK));
                throw new IllegalStateException("boom");
            }
        } catch (IllegalStateException failure) {
            System.out.println("caught: " + failure.getMessage());
            System.out.println("after catch: " + Thread.holdsLock(LOCK));
        }

        Thread worker = new Thread(() -> {
            synchronized (LOCK) {
                System.out.println("worker acquired: "
                        + Thread.holdsLock(LOCK));
            }
        });

        worker.start();
        worker.join();
        System.out.println("done");
    }
}
```

Compile and run with JDK 17+:

```bash
javac MonitorReleaseDemo.java
java MonitorReleaseDemo
```

`stdout` output:

```text
inside: true
caught: boom
after catch: false
worker acquired: true
done
```

**Step-by-step explanation:**

1. The `main` thread acquires the monitor of `LOCK` and enters the block. `Thread.holdsLock(LOCK)` returns `true` for **the thread calling the method**.
2. `throw new IllegalStateException("boom")` causes the block to complete abruptly. Java releases the monitor before entering the outer `catch`.
3. The `catch` still runs on the `main` thread, but at this point that thread no longer holds the monitor, so `after catch: false` is accurate.
4. After `catch` finishes, the program starts the `worker` thread. This thread enters the synchronized block on the same `LOCK` and prints `true`.
5. `worker.join()` forces `main` to wait until the worker finishes, so `done` is always printed after `worker acquired: true`.

This example shows that the monitor is released when exiting the `synchronized` scope. `Thread.holdsLock(object)` only reports whether **the current thread** holds the monitor of that object; a value of `false` does **not** guarantee that no other thread holds the lock.

## 4. Where `catch` Is Placed Determines When the Monitor Is Released

The two scenarios below look similar but differ in execution order.

### 4.1. `catch` Outside `synchronized`

```java
try {
    synchronized (lock) {
        riskyOperation();
    }
} catch (RuntimeException failure) {
    // If there is no enclosing synchronized region holding the same lock,
    // the thread has already released the monitor of the block it just exited.
    recover(failure);
}
```

This is an illustrative snippet. When `riskyOperation()` throws `RuntimeException`, the `synchronized` block is exited and the monitor is released; only then does the outer handler run. The exception is still caught, but **catching the exception is not what releases the lock**. The lock is released because the thread leaves the synchronization scope.

### 4.2. `catch` Inside `synchronized`

```java
synchronized (lock) {
    try {
        riskyOperation();
    } catch (RuntimeException failure) {
        // The thread STILL holds the lock because it has not exited the synchronized block.
        recover(failure);
    }
    // The thread still holds the lock here.
}
// The monitor is released when the thread exits this outermost block.
```

This is also an illustrative snippet. Because the error is handled directly inside the body, the `synchronized` block is still executing. The monitor is not automatically released at the moment `catch` catches the error.

**Practical consequence:** If `recover(failure)` is a slow operation (I/O, network calls, or multiple retries), other threads needing the same monitor may be blocked for a long time. When possible, gather the necessary state inside the locked region and move time-consuming processing outside.

## 5. Runnable Example: Reentrant Locking and `catch` Inside the Locked Region

Java monitors are **reentrant**: a thread that already holds a monitor can acquire that same monitor again in nested calls. Each entry corresponds to an exit; only when that thread has no remaining acquisitions is the monitor actually released.

Create the file **`NestedMonitorDemo.java`**:

```java
public class NestedMonitorDemo {
    private static final Object LOCK = new Object();

    public static void main(String[] args) {
        synchronized (LOCK) {
            try {
                synchronized (LOCK) {
                    System.out.println("inner entered: "
                            + Thread.holdsLock(LOCK));
                    throw new IllegalStateException("inner failed");
                }
            } catch (IllegalStateException failure) {
                System.out.println("catch in outer: "
                        + Thread.holdsLock(LOCK));
            }

            System.out.println("before outer exit: "
                    + Thread.holdsLock(LOCK));
        }

        System.out.println("after outer exit: "
                + Thread.holdsLock(LOCK));
    }
}
```

```bash
javac NestedMonitorDemo.java
java NestedMonitorDemo
```

Output:

```text
inner entered: true
catch in outer: true
before outer exit: true
after outer exit: false
```

What happens is as follows:

- The **outer** block acquires the monitor of `LOCK` for the first time.
- The **inner** block acquires the same monitor a second time on the same thread.
- The exception causes the inner block to exit and releases the **inner block's** acquisition.
- The outer block's `catch` receives the exception; the **outer block's** acquisition still remains, so `Thread.holdsLock(LOCK)` is still `true`.
- When the program leaves the outer block, the remaining acquisition is released; afterwards, `Thread.holdsLock(LOCK)` is `false`.

The exact rule is that **each exited `synchronized` scope releases its corresponding monitor ownership**. You cannot infer that "throwing an exception releases all monitors held by the thread." If a thread holds multiple locks, any scopes still executing continue to hold their locks.

## 6. `synchronized` Methods Also Automatically Release the Monitor If an Exception Is Thrown

For an instance method with the `synchronized` keyword, the monitor belongs to `this`. Acquiring and releasing the monitor is tied to the method invocation, even when the method throws an exception.

Create the file **`SynchronizedMethodDemo.java`**:

```java
public class SynchronizedMethodDemo {
    private synchronized void fail() {
        System.out.println("inside method: " + Thread.holdsLock(this));
        throw new IllegalArgumentException("invalid input");
    }

    public static void main(String[] args) {
        SynchronizedMethodDemo demo = new SynchronizedMethodDemo();

        try {
            demo.fail();
        } catch (IllegalArgumentException failure) {
            System.out.println("caught: " + failure.getMessage());
            System.out.println("after method: " + Thread.holdsLock(demo));
        }
    }
}
```

```bash
javac SynchronizedMethodDemo.java
java SynchronizedMethodDemo
```

Output:

```text
inside method: true
caught: invalid input
after method: false
```

When `fail()` throws an error, the method invocation completes abruptly and the monitor of the `demo` object is released before the outer handler receives the error.

With `static synchronized`, the monitor is acquired on the `SynchronizedMethodDemo.class` object (if the method is declared in this class), **not** an instance of the class.

### 6.1. Difference in JVM Bytecode

At the JVM level, a `synchronized (lock)` block is typically compiled using `monitorenter` and `monitorexit` instructions, including an exception exit path to release the monitor.

An ordinary `synchronized` method, by contrast, is marked with the `ACC_SYNCHRONIZED` flag in the method metadata; the JVM coordinates acquiring and releasing the monitor upon method invocation and completion. Therefore, **you should not claim that every `synchronized` method has a `monitorenter`/`monitorexit` instruction pair in its bytecode body**.

You can inspect the structure yourself with:

```bash
javac SynchronizedMethodDemo.java
javap -c -v SynchronizedMethodDemo
```

Look for the declaration of `fail()` and the `ACC_SYNCHRONIZED` flag. The detailed output of `javap -v` depends on the compiler and classfile information; therefore, this lesson does not assume a fixed bytecode dump.

## 7. Relationship to `finally`

A useful mental model is that a `synchronized` region has a **built-in lock cleanup mechanism on both the success path and the error path**. This is close to the idea of using `finally`, except that the language/JVM's monitor release does not depend on whether the programmer writes a `finally` block.

```java
synchronized (lock) {
    try {
        operation();
    } finally {
        // Clean up application resources within the locked region, if appropriate.
        // At this point, the thread STILL holds the monitor lock.
        cleanup();
    }
}
// When exiting synchronized, the monitor is released.
```

This is an illustrative snippet; `operation()`, `cleanup()`, and `lock` need to be defined. If `operation()` throws an exception, the inner `finally` runs while the monitor is still held. When the synchronized block ends, the monitor is released.

**Note on a new exception from `finally`:** If `cleanup()` also throws an error, that exception may replace the propagating exception. The monitor is still released when exiting the `synchronized` block, but information about the original cause may be masked. Design cleanup operations so they do not lose the primary error.

Monitor release does not depend on whether `catch` catches the exception:

| Exit Path | Monitor of the Exited Scope |
| --- | --- |
| Running to the end of the block | Released |
| `return` from inside the block | Released before the return completes |
| `break` / `continue` exiting that scope | Released |
| `throw` or a call throwing an exception out of the block | Released |
| Exception caught by `catch` inside the block, continuing inside it | Still held until exiting the block |
| Exception occurs while evaluating the lock expression, or lock expression is `null` | No monitor was acquired, so there is no new monitor to release |

Do not equate Java language execution semantics guarantees with cases where the process is forcibly terminated, the VM crashes, or power is lost.

## 8. `Object.wait()`, `Thread.sleep()`, and Other Lock Types

There are cases where a thread **temporarily releases a monitor while still inside a `synchronized` block**, which differs from exiting due to an exception. The most important one is `Object.wait()`.

### 8.1. `wait()` Temporarily Releases the Monitor of the Waited-On Object

`Object.wait()` requires the current thread to own the monitor of **the exact object on which `wait()` is called**. When a thread validly calls `lock.wait()`, it enters a waiting state and temporarily releases **all monitor ownership counts of `lock`**. After being awakened, interrupted, or finishing the wait under the appropriate condition, the thread must reacquire the monitor of `lock` before `wait()` returns normally or throws `InterruptedException`.

```java
synchronized (lock) {
    while (!conditionReady()) {
        lock.wait(); // Temporarily releases the monitor of lock while waiting.
    }
    consume();
}
```

This is an **illustrative snippet**, which must be inside a method that handles/declares `InterruptedException` and defines `conditionReady()` and `consume()`. Use `while` to recheck the condition because a *spurious wakeup* may occur or the condition may have changed.

When `wait()` is interrupted and throws `InterruptedException`, the thread has already reacquired the monitor before throwing. If that exception **continues exiting outside the `synchronized` block**, the block-exit mechanism releases the monitor afterward. If it is caught by `catch` **inside the block**, the thread still holds the monitor after `wait()` throws.

`notify()` or `notifyAll()` wakes up waiting threads but **does not release the monitor at the call site**. A waiting thread can only proceed after it reacquires the monitor.

### 8.2. `sleep()` Does Not Release Monitors

If a thread calls `Thread.sleep(...)` inside a `synchronized` region, it **continues holding** the monitors it owns while sleeping. Therefore, sleeping or performing long I/O waits inside a locked region can significantly slow down other threads.

### 8.3. `ReentrantLock` Does Not Have `synchronized`'s Auto-Release Rule

`java.util.concurrent.locks.ReentrantLock` is an explicit locking API. If you acquire the lock with `lock()`, you must call `unlock()` in a balanced way, typically in `finally`. Otherwise, an exception in between can leave the lock **held**.

```java
java.util.concurrent.locks.ReentrantLock lock =
        new java.util.concurrent.locks.ReentrantLock();

lock.lock();
try {
    performOperation();
} finally {
    lock.unlock();
}
```

This is an illustrative snippet; `performOperation()` must be defined. Only place `unlock()` in `finally` after the lock has been successfully acquired. Distinguish this explicit lock from the intrinsic monitor managed by `synchronized`.

## 9. Releasing the Monitor Does Not Mean Data Is Safe

`synchronized` provides mutual exclusion among threads synchronizing on **the same monitor** and establishes a memory visibility ordering (*happens-before*) relationship when one thread unlocks a monitor and another thread subsequently locks the same monitor. Thus, writes made before releasing the lock can be seen by the thread that acquires the lock later, according to the Java Memory Model rules.

However, Java **does not roll back changes made to objects** when a `synchronized` block completes abruptly. If a thread updates half of the state and then throws an error, the next thread may read an invalid state, even though the monitor was properly released.

Example of an unsafe design:

```java
synchronized (lock) {
    available -= amount;      // Partially modifies state.
    saveToExternalSystem();   // May throw an exception.
    reserved += amount;       // Does not run if the call above fails.
}
```

This is an **illustrative snippet**, assuming `lock`, `available`, `reserved`, `amount`, and `saveToExternalSystem()` are defined. If the application requires `available + reserved` to remain constant, a failure between the two updates can break the invariant. The lock is released, but the state does not automatically roll back.

One fix for **in-memory-only** updates is to validate and compute the new values before mutating state, place the operation that may fail before the commit phase, and then apply the assignments under the same monitor:

```java
synchronized (lock) {
    validate(amount);
    int newAvailable = available - amount;
    int newReserved = reserved + amount;
    operationThatMayFail();

    available = newAvailable;
    reserved = newReserved;
}
```

This is also an **illustrative snippet**; the relevant methods and variables must be defined. This pattern assumes the commit phase consists only of internal assignments that do not actively throw errors, and that all accesses to the related state follow the same locking discipline. For multiple resources, database transactions, networks, or other external side effects, an appropriate transaction/compensation mechanism is required; `synchronized` does not turn a sequence of operations into a rollback-capable transaction.

### Runnable Example: Preserving Invariants Before Receiving an Error

Create the file **`InvariantSafetyDemo.java`**:

```java
public class InvariantSafetyDemo {
    private static class Counters {
        private int available = 10;
        private int reserved = 0;

        synchronized void reserve(int amount, boolean fail) {
            if (amount <= 0 || amount > available) {
                throw new IllegalArgumentException("invalid amount");
            }

            int nextAvailable = available - amount;
            int nextReserved = reserved + amount;

            if (fail) {
                throw new IllegalStateException("simulated failure");
            }

            available = nextAvailable;
            reserved = nextReserved;
        }

        synchronized String snapshot() {
            return available + "," + reserved;
        }
    }

    public static void main(String[] args) {
        Counters counters = new Counters();

        try {
            counters.reserve(4, true);
        } catch (IllegalStateException failure) {
            System.out.println("operation failed");
        }

        System.out.println(counters.snapshot());
        counters.reserve(4, false);
        System.out.println(counters.snapshot());
    }
}
```

```bash
javac InvariantSafetyDemo.java
java InvariantSafetyDemo
```

Output:

```text
operation failed
10,0
6,4
```

The first time, the exception is thrown **before updating** the two fields, and the `synchronized` method automatically releases the monitor. The value read afterward is still `10,0`. The second time succeeds without error, so the two fields are updated to `6,4`. This pattern demonstrates how to preserve in-memory invariants for expected failure paths; it does not guarantee recovery from every `Error` or external failure.

## 10. Easily Overlooked Consequences

### 10.1. Releasing a Lock Does Not Force Another Thread to Run Immediately

When a thread releases a monitor, waiting threads can contend for that monitor, but **there is no FIFO ordering guarantee** or guarantee that a specific thread will run immediately. Actual scheduling depends on the system and active threads.

### 10.2. Releasing One Monitor Does Not Unblock All Access Paths

Another thread only has to wait for the monitor if it enters a synchronized region **on the same lock object**. If some methods read/write shared data without using the right lock or another valid synchronization mechanism, they can still access inconsistent data.

### 10.3. Deadlocks Can Still Happen

If two threads hold monitors A and B respectively, and then each waits for the other monitor, they can deadlock. Automatically releasing a monitor when **exiting** `synchronized` does not help a thread that is permanently stuck inside a locked region get out. Reduce nested locking, establish a fixed lock acquisition order, and use thread dump tools when diagnosing.

### 10.4. Do Not Use Severe JVM Errors for Routine Synchronization Testing

Monitor exit rules apply when abrupt completion is handled by Java/the JVM. However, deliberately provoking `OutOfMemoryError` or `StackOverflowError` can leave the system without resources to log, allocate objects, schedule work, or initiate recovery. Use `IllegalStateException` in normal test examples.

## 11. Summary of Common Misconceptions

| Claim | Accurate Assessment |
| --- | --- |
| "Throwing an exception releases all locks held by the thread." | **False.** Each exited scope releases its own ownership; any enclosing scope still in effect continues holding its monitor. |
| "A `catch` inside `synchronized` causes the lock to be released." | **False.** The lock remains held until actually exiting the synchronized block/method. |
| "You must write `finally { unlock(); }` for `synchronized`." | **False.** Intrinsic monitors are managed by the JVM. Calling `unlock()` in `finally` is for explicit `Lock`s. |
| "When an exception is caught outside, the monitor of the exited block is held until the end of the handler." | **False** if there is no enclosing synchronized region holding the same lock. The block already released the monitor before the outer handler ran. |
| "`wait()` throws `InterruptedException` without reacquiring the monitor." | **False.** With `Object.wait()`, the thread reacquires the monitor before the method returns or throws `InterruptedException`. |
| "`Thread.sleep()` releases the monitor like `wait()`." | **False.** `sleep()` keeps all currently owned monitors held. |
| "Releasing the monitor means the incomplete operation is rolled back." | **False.** Changes already made are not automatically undone. |
| "Releasing a monitor wakes up waiting threads in strict FIFO order." | **False.** Intrinsic monitors have no FIFO guarantee. |

## 12. Self-Check

1. A call inside `synchronized(lock)` throws `IOException` and is not caught inside the block. Is the monitor released? **Yes**, when abrupt completion exits that block.
2. What if `catch (IOException e)` is placed *inside* the same `synchronized` block? **The monitor remains held** in the handler and subsequent statements inside the block.
3. When the same thread holds a monitor twice due to nested `synchronized(lock)`, does exiting the inner block via an exception make the monitor completely free? **No**, the outer block still holds one ownership count.
4. If `synchronized(null)` throws `NullPointerException`, which lock must be released? **No monitor was acquired**, because the lock expression is `null`.
5. If an instance `synchronized` method throws a `RuntimeException` to the caller, what happens to the monitor of the receiver object? **It is released** during the method's abrupt completion.
6. If `wait()` is interrupted, at the moment `InterruptedException` is received in a handler inside the synchronized block, does the thread hold the monitor? **Yes**; it reacquired the monitor before `wait()` threw the error.
7. Why must invariants be checked after an error in a synchronized region? Because **releasing a lock does not roll back assignments that have already occurred**.

## 13. Official References

- [Java Language Specification 17 — §14.19, The synchronized Statement](https://docs.oracle.com/javase/specs/jls/se17/html/jls-14.html#jls-14.19): semantics of acquiring and releasing a monitor when a block completes normally or abruptly.
- [Java Language Specification 17 — §17.1, Synchronization](https://docs.oracle.com/javase/specs/jls/se17/html/jls-17.html#jls-17.1): reentrant monitors, synchronized methods, and automatic unlock on exit.
- [Java Language Specification 17 — §17.4.5, Happens-before Order](https://docs.oracle.com/javase/specs/jls/se17/html/jls-17.html#jls-17.4.5): unlock/lock relationship and visibility between threads.
- [Java Virtual Machine Specification 17 — §2.11.10, Synchronization](https://docs.oracle.com/specs/jvms/se17/html/jvms-2.html#jvms-2.11.10): monitorenter, monitorexit, and the ACC_SYNCHRONIZED flag.
- [Java SE 17 API — Thread.holdsLock](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/lang/Thread.html#holdsLock(java.lang.Object)): checking monitor ownership of the current thread.
- [Java SE 17 API — Object.wait](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/lang/Object.html#wait()): temporarily releasing a monitor and reacquiring it before returning.
- [Java SE 17 API — ReentrantLock](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/concurrent/locks/ReentrantLock.html): differences of explicit locking.

**Core principle:** When a thread actually exits a `synchronized` scope due to an exception, Java releases the monitor of the exited scope. Always consider `catch` placement, enclosing locked regions, and data consistency to reason completely about multithreaded behavior.

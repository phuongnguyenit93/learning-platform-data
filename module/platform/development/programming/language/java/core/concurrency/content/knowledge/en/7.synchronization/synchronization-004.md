# What Is Reentrant Synchronization in Java?

## 1. Definition and Why Reentrancy Is Needed

**Reentrant synchronization** means that **a thread currently holding a lock is allowed to acquire the same lock again** without blocking itself. The rule excluding other threads still holds: another thread cannot acquire the lock until the owner has released all of its holds.

Java has two key mechanisms:

- **Intrinsic monitor of `synchronized`:** a thread can enter additional synchronized blocks or methods that use the **same monitor**.
- **`ReentrantLock` in `java.util.concurrent.locks`:** the same thread can call `lock()` in a nested manner; the lock tracks the *hold count* and requires a matching number of `unlock()` calls.

Reentrancy lets a locked method call a locked helper, make a recursive call, or call a superclass method **without deadlocking on itself when re-acquiring the same lock**. It does not mean multiple threads can execute the critical section concurrently.

**Key point:** reentrancy is tied to **the same thread and the same lock object**, not to variable names, method names, or the fact that two objects share the same type. A thread holding the monitor of instance A may still have to wait for the monitor of instance B.

## 2. How Does the `synchronized` Monitor Reenter?

Common forms:

```java
// Snippet: lockObject is a reference to a declared lock object.
synchronized (lockObject) {
    // Critical section.
}
```

- `synchronized (object)` acquires the monitor of **object**.
- A `synchronized` instance method acquires the monitor of `this`.
- A `static synchronized` method acquires the monitor of the `Class` object, for example `Account.class`. A class monitor is **different** from an instance monitor.

The JVM manages ownership and the reentry depth. When the owner enters the same monitor again, the hold level increases. When it exits one level, the hold level decreases. Another thread can only acquire the monitor after the owner has exited all levels.

**Difference from explicit locks:** exiting a synchronized block or method automatically releases the monitor by the exact number of levels, even on `return` or an exception. You do not need to, and cannot, call an `unlock()` method for an intrinsic monitor as you do with `ReentrantLock`.

### Complete Java 17+ Example

Create the file `IntrinsicReentrancy.java`:

```java
public class IntrinsicReentrancy {
    private int balance = 10;

    public synchronized void withdraw(int amount) {
        System.out.println("Outer entered");
        decrease(amount);
        System.out.println("Outer resumed");
    }

    private synchronized void decrease(int amount) {
        balance -= amount;
        System.out.println("Inner balance: " + balance);
    }

    public synchronized int balance() {
        return balance;
    }

    public static void main(String[] args) {
        IntrinsicReentrancy account = new IntrinsicReentrancy();
        account.withdraw(3);
        System.out.println("Final balance: " + account.balance());
    }
}
```

Run:

```bash
javac IntrinsicReentrancy.java
java IntrinsicReentrancy
```

Output:

```text
Outer entered
Inner balance: 7
Outer resumed
Final balance: 7
```

The main thread acquires `account`'s monitor when entering `withdraw`, then reenters that same monitor when calling `decrease`. When `decrease` returns, `withdraw` **still holds the monitor**; only when `withdraw` finishes is the monitor completely released for this call. The `balance` method uses the same monitor for reading.

This example only illustrates the reentry mechanism; `withdraw` does not check the balance, so it is not a complete financial transaction design. When another thread calls a synchronized method on the **same account**, that thread must wait until the owner exits all levels.

### Reentry via Recursion and Inheritance

A synchronized method can call itself or another synchronized helper on the same receiver. Each recursive level re-acquires the monitor owned by the same thread. Reentrancy **does not** prevent infinite recursion or `StackOverflowError`; it only avoids self-deadlock on the monitor.

A subclass calling `super.someSynchronizedMethod()` on the same receiver can also reenter if both lock on `this`. However, `synchronized(other)` uses a different monitor, and `static synchronized` also does not use the receiver's monitor.

## 3. `ReentrantLock`, Owner Thread, and Hold Count

`ReentrantLock` is an explicit reentrant lock that additionally supports `tryLock()`, `lockInterruptibly()`, `newCondition()`, and `getHoldCount()`.

Safe lock acquisition pattern:

```java
// Snippet: lock is a declared ReentrantLock.
lock.lock();
try {
    // Operate on the protected state.
} finally {
    lock.unlock();
}
```

`finally` guarantees unlocking even when an exception occurs. Only call `unlock()` if acquisition succeeded. Do not place `unlock()` in a `finally` block that runs after `tryLock()` returns false.

| Action by thread T | Hold count of T | Effect |
| --- | --- | --- |
| T acquires an unheld lock | 1 | T becomes the owner |
| T calls `lock()` again on the same lock | 2 | T remains the owner |
| T calls `unlock()` once | 1 | Other threads must still wait |
| T calls `unlock()` a second time | 0 | The lock is released |

`getHoldCount()` counts the number of times the **current thread** holds the lock. `isHeldByCurrentThread()` checks ownership for the calling thread. Do not infer a snapshot of another thread's state from these methods.

### Java 17+ Example with Hold Count

Create the file `ReentrantLockDepth.java`:

```java
import java.util.concurrent.locks.ReentrantLock;

public class ReentrantLockDepth {
    private final ReentrantLock lock = new ReentrantLock();

    private void outer() {
        lock.lock();
        try {
            System.out.println("Outer: " + lock.getHoldCount());
            inner();
            System.out.println("Back in outer: " + lock.getHoldCount());
        } finally {
            lock.unlock();
        }
        System.out.println("After outer: " + lock.getHoldCount());
    }

    private void inner() {
        lock.lock();
        try {
            System.out.println("Inner: " + lock.getHoldCount());
        } finally {
            lock.unlock();
        }
    }

    public static void main(String[] args) {
        new ReentrantLockDepth().outer();
    }
}
```

Run:

```bash
javac ReentrantLockDepth.java
java ReentrantLockDepth
```

Output:

```text
Outer: 1
Inner: 2
Back in outer: 1
After outer: 0
```

Only one thread executes the code, yet it acquires the same lock twice. `inner` releases one level, and `outer` releases the remaining level. If `inner` forgets to unlock, then after `outer` unlocks, the lock still has a hold count of 1, causing other threads to potentially wait forever. If a thread other than the owner calls `unlock()`, or unlocks more times than it holds the lock, `ReentrantLock` throws `IllegalMonitorStateException`.

**Practical takeaway:** every successful `lock()` needs a matching `unlock()`. Both `synchronized` and `ReentrantLock` are reentrant, but one relies on lexical scope for automatic release while the other requires the programmer to balance calls manually.

## 4. Reentrancy Does Not Break Mutual Exclusion

Reentry is permitted only for the **owning thread**; it does not grant other threads permission to interleave. Consider a class with a private monitor:

```java
final class Counter {
    private final Object mutex = new Object();
    private int count;

    public void incrementTwice() {
        synchronized (mutex) {
            incrementOne();
            incrementOne();
        }
    }

    private void incrementOne() {
        synchronized (mutex) {
            count++;
        }
    }

    public int get() {
        synchronized (mutex) {
            return count;
        }
    }
}
```

This is a helper class with no `main` method. When thread T enters `incrementTwice`, T holds `mutex`. The two calls to `incrementOne` re-acquire the same `mutex`, so T can proceed. Another thread U attempting `get` or `incrementTwice` must wait until T has released all holds.

Using `private final Object mutex` keeps control of the object's lock internal, preventing callers from intentionally or accidentally holding the monitor externally. If the helper locks **a different object**, that is not reentry and may block.

### Java 17+ Example: Multiple Workers and Nested Locking

Create the file `NestedCounter.java`:

```java
public class NestedCounter {
    private final Object mutex = new Object();
    private int count;

    public void addBatch(int size) {
        synchronized (mutex) {
            for (int i = 0; i < size; i++) {
                incrementOne();
            }
        }
    }

    private void incrementOne() {
        synchronized (mutex) {
            count++;
        }
    }

    public int get() {
        synchronized (mutex) {
            return count;
        }
    }

    public static void main(String[] args) throws InterruptedException {
        NestedCounter counter = new NestedCounter();
        Thread[] workers = new Thread[4];

        for (int i = 0; i < workers.length; i++) {
            workers[i] = new Thread(() -> counter.addBatch(1_000));
            workers[i].start();
        }
        for (Thread worker : workers) {
            worker.join();
        }
        System.out.println("Final count: " + counter.get());
    }
}
```

Run:

```bash
javac NestedCounter.java
java NestedCounter
```

Output:

```text
Final count: 4000
```

Four threads update the same counter; scheduling order may vary, but the result is always 4000 once all finish. The shared monitor prevents two threads from modifying `count` simultaneously; within each thread, the helper reenters the same monitor. `join()` ensures `main` waits for all workers before reading the result.

Nested locking on every step here is intentional for illustration. For large loops, you can write a helper that requires the caller to already hold the lock to reduce overhead, provided that precondition is enforced consistently. Reentrancy does not mean every helper should acquire the lock on its own.

## 5. Self-Deadlock and the Limits of Reentrancy

**Self-deadlock** can occur if a thread holds a resource and then waits for that very same resource through a non-reentrant mechanism. For example, `Semaphore(1)` does not track an owner the way `ReentrantLock` does: a thread calling `acquire()` twice without an intervening `release()` will wait for a second permit, potentially blocking indefinitely. Do not run such a hanging example as a demo program.

With a Java monitor or `ReentrantLock`, the owner can re-acquire **the same lock it already holds**, thereby avoiding this reentry-induced self-deadlock.

However, **reentrancy does not prevent deadlocks across different locks**:

```text
Thread T1                  Thread T2
---------                  ---------
holds lock A               holds lock B
waits for lock B           waits for lock A
       \                    /
          lock wait cycle
```

A and B may both be `ReentrantLock`s. T1 does not own B; T2 does not own A. Therefore, reentrancy does not help them break out of the wait cycle.

Prevention techniques include enforcing a consistent acquisition order for multiple locks, avoiding I/O waits or callbacks while holding multiple locks, keeping critical sections small, considering `tryLock(timeout, unit)` when a recovery path exists, and analyzing thread dumps/JFR when a hang occurs.

**A common pitfall:** thread T holds lock L and calls `worker.join()` while the worker needs L to finish. T waits for the worker, and the worker waits for L held by T: this is still a deadlock even though L is reentrant. Never hold a lock that a worker needs while waiting for that worker.

## 6. Comparing `synchronized` and `ReentrantLock`

| Feature | `synchronized` | `ReentrantLock` |
| --- | --- | --- |
| Reentrant | Yes | Yes |
| Lock target | Monitor object or `Class` object | `ReentrantLock` instance |
| Release on exception | Automatically released on scope exit | Must `unlock()` in `finally` |
| Hold count | Managed by JVM, no `getHoldCount` API | Provides `getHoldCount()` |
| Non-blocking acquisition | No `tryEnter` syntax | `tryLock()` |
| Timed acquisition | No monitor acquisition timeout | `tryLock(long, TimeUnit)` |
| Interruptible acquisition | No equivalent acquisition form | `lockInterruptibly()` |
| Wait conditions | `wait()`, `notify()`, `notifyAll()` | `Condition.await()`, `signal()` |
| Fairness | Not directly configurable | Optional `new ReentrantLock(true)` |

**A fair lock does not guarantee fair OS scheduling or task completion order.** Even on a fair `ReentrantLock`, a non-timed `tryLock()` can barge in and acquire the lock immediately if it is free, even when other threads are waiting. Do not rely on fairness to prove that one business request will complete before another.

If you only need a short protected region and no extra API features, `synchronized` is usually easier to maintain. Use `ReentrantLock` when you genuinely need timeouts, interruptible lock waiting, or separate condition queues.

## 7. `wait()`, `Condition.await()`, and Reentrant Locks

When a thread holds a lock and needs to **wait for a condition**, you must distinguish **reentering a lock** from **temporarily releasing a lock to wait**:

- `Object.wait()` must be called while the thread owns that exact monitor object. While waiting, the thread releases **that** monitor across the appropriate reentry levels and must re-acquire it before `wait()` returns. It does not automatically release other monitors.
- `Condition.await()`, created from `ReentrantLock` via `newCondition()`, releases the associated lock's holds while waiting and re-acquires them per the `Condition` contract before returning. The lock must be held before calling `await`.
- `Thread.sleep()` **does not release any monitor or `ReentrantLock`** held by the thread.
- `notify()` or `signal()` does not transfer lock ownership immediately; the awakened thread still has to re-acquire the lock.
- `wait()`/`await()` can wake up unexpectedly (*spurious wakeup*); always check the condition in a **`while`** loop.

Conceptual example:

```java
// Snippet: mutex, ready, and consume() are declared in the class.
synchronized (mutex) {
    while (!ready) {
        mutex.wait();
    }
    consume();
}
```

This is a snippet, **not a standalone compilable program**. The signaling thread must update `ready` under the same `mutex` and then call `mutex.notifyAll()` as appropriate. The `while` loop guards the condition even in the event of a spurious wakeup or if another thread changes the state.

## 8. Reentrant Callbacks and Invariants

Reentrancy carries an easily overlooked risk: code holding a lock invokes a caller-supplied callback. The callback runs **on the same thread** and may call back into the API using the same lock; because the lock is reentrant, the callback **is not blocked**. It can mutate state while the outer operation still assumes the state has not changed.

```java
// Illustrative snippet; mutex, state, callback, and use() are already declared.
synchronized (mutex) {
    int previous = state;
    callback.run();
    use(previous); // May no longer be valid if the callback changed state.
}
```

The lock prevents **other threads** from interleaving, but it does not stop the owner itself from reentering through an unexpected call path. A callback can also block on I/O, acquire a second lock, recurse infinitely, or throw an exception.

To stay safe: avoid running untrusted or uncontrolled code inside a lock unless necessary; clearly document whether callbacks are permitted to reenter; maintain invariants at every point observable by a callback; and consider taking a snapshot and invoking the callback outside the lock if business logic allows. However, if an atomic check-then-act is required, **do not** arbitrarily drop the lock between the check and the update.

## 9. Common Misconceptions About Lock Scope

- Two instances of the same class have **different instance monitors**. `accountA` and `accountB` do not exclude each other.
- `static synchronized` locks on `SomeClass.class`; an instance `synchronized` method locks on `this`. These are two different locks even though the code is in the same class.
- Two `new ReentrantLock()` objects are two different locks; giving variables the same name is irrelevant.
- Using a publicly accessible object such as a String literal as a monitor can cause unintended lock sharing; prefer `private final Object mutex = new Object()` for private state.
- A monitor inside one JVM does not automatically protect data written by another process. When an invariant spans a file, database, or external service, you must use an update protocol at that data source itself.
- Reentrancy does not replace a policy protecting all read/write paths. Even if helpers reenter properly, a getter reading mutable state outside the lock can still be a data race.

## 10. Common Mistakes

1. **"One synchronized method cannot call another synchronized method."** False if it is the same owner thread and the same monitor.
2. **"Reentrant means two threads can hold the lock at the same time."** False; only the currently owning thread can reenter.
3. **"If you lock twice, unlocking once is enough."** False for `ReentrantLock`; the hold count must drop to 0 to release the lock.
4. **"Another thread can unlock on behalf of the owner to fix a deadlock."** False; `ReentrantLock` requires the owning thread, otherwise it throws `IllegalMonitorStateException`.
5. **"All deadlocks disappear when using `ReentrantLock`."** False when two different locks or a wait dependency cycle are involved.
6. **"Sleep releases the monitor so another thread can run."** False: `sleep` never releases a monitor.
7. **"Static and instance synchronized methods lock the same object."** False: the class lock and the receiver lock are different.
8. **"Fairness in `ReentrantLock(true)` guarantees processing order."** False: it does not guarantee OS scheduler behavior or completion order.
9. **"A callback cannot modify state when invoked under a lock."** False: a callback on the same thread can reenter.
10. **"Reentrant means thread-safe for all data."** False: correctness still depends on invariants, lock scope, and safe publication.

## 11. Selection and Usage Checklist

1. Identify the **exact lock object**: `this` monitor, `Class` object, private mutex, or `ReentrantLock`.
2. Identify the **owner thread**: only the thread already holding **the same lock** can reenter.
3. Analyze nested calls: do helpers, recursive calls, and superclass methods use the same lock?
4. With `ReentrantLock`, every successful `lock()` must have a matching `unlock()` in a `finally` block.
5. Protect the **entire invariant**: nested locks cannot fix a broken check-then-act protocol that has been split apart.
6. Avoid multi-lock dependency cycles; establish a consistent lock ordering; never wait on a worker that needs a lock you hold.
7. Account for timeouts, interrupts, and failures while waiting for a lock; only unlock if acquisition succeeded.
8. Do not let uncontrolled callbacks arbitrarily mutate intermediate state; watch out for unexpected reentry.
9. Test with multiple threads, exception paths, and lock exposure; do not rely on scheduler ordering.
10. Choose `ReentrantLock` only when you need its extra capabilities; `synchronized` is sufficient for many simple critical sections.

**Remember:** reentrant synchronization allows **the same thread to re-acquire the same lock** for nested or recursive calls without blocking itself, while still excluding other threads. Java's `synchronized` manages monitor levels automatically; `ReentrantLock` tracks a hold count and requires balanced unlocks. Reentrancy is a property of the lock itself, whereas thread safety depends on designing invariants and state-access protocols properly.

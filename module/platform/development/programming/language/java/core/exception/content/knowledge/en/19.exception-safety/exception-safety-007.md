# Lock.lock Combined with unlock in finally — Preserving Locks and State in Java

## 1. Learning Objectives

After this lesson, you will be able to:

- Explain why a critical section using <code>Lock</code> must have a reliable lock-release path even when code throws an exception.
- Write the <code>lock.lock()</code> → <code>try</code> → <code>finally</code> → <code>lock.unlock()</code> pattern correctly.
- Distinguish between **releasing a lock** and **preserving data invariants** when an update operation can fail.
- Understand lock ownership, reentrancy, and why only the thread holding the lock may call <code>unlock()</code>.
- Use the <code>tryLock()</code>, <code>tryLock(timeout, unit)</code>, and <code>lockInterruptibly()</code> variants appropriately when needed.
- Recognize bugs such as forgetting <code>finally</code>, unlocking from the wrong thread, catching and ignoring exceptions, and corrupting state before releasing the lock.

The scope of this lesson focuses on <code>java.util.concurrent.locks.Lock</code> and its common implementation <code>java.util.concurrent.locks.ReentrantLock</code> in Java 17+.

## 2. The Problem: An Exception Occurs While Holding a Lock

A *critical section* contains operations that read/modify shared data and must be protected from other threads using the **same lock**. With <code>ReentrantLock</code>, a thread calls <code>lock()</code> to acquire access and must call <code>unlock()</code> the matching number of times to release that ownership.

Unsafe way to write it:

~~~java
lock.lock();
updateSharedState();
lock.unlock();
~~~

The snippet above is **illustrative code**, assuming <code>lock</code> and <code>updateSharedState()</code> already exist. If <code>updateSharedState()</code> throws a <code>RuntimeException</code>, an <code>IOException</code> propagated through a related call, or the code exits via <code>return</code> before the last line, the <code>unlock()</code> call may never execute.

Consequences:

- The lock remains held by the thread that acquired it.
- Other threads needing the same lock may have to wait indefinitely or until the holding thread releases it elsewhere.
- A subsequent operation on **that same thread** may still run because <code>ReentrantLock</code> is reentrant; this easily hides lock-leak bugs.
- If the update operation was interrupted midway, the shared state may also become inconsistent even if the lock is later released.

Standard Java approach:

~~~java
lock.lock();
try {
    updateSharedState();
} finally {
    lock.unlock();
}
~~~

Once <code>lock.lock()</code> returns successfully, the thread holds the lock before entering the <code>try</code> block. Whether the code inside <code>try</code> completes normally, executes <code>return</code>, or throws an exception, Java executes <code>finally</code> upon exiting the block under normal execution semantics.

**Key takeaway:** <code>finally</code> protects the **lock release statement**. It does not automatically roll back data changes already made inside <code>try</code>.

## 3. Standard Structure and Execution Order

~~~text
Thread calls lock.lock()
          |
          v
  Wait until lock is acquired
          |
          v
       enter try
          |
          +---- normal completion -------+
          |                              |
          +---- return/throw -----------+----> finally: lock.unlock()
                                                  |
                                                  v
                                       continue/return/throw exception
~~~

### Why place lock.lock() before try?

Recommended pattern:

~~~java
lock.lock();
try {
    // Operations that require holding the lock.
} finally {
    lock.unlock();
}
~~~

This ties <code>finally</code> to the execution **after the lock has been acquired**. If a lock-acquisition method can fail or throw an exception **before owning the lock**, the code will not enter the <code>try</code> block, so it will not release a lock it does not hold.

With <code>ReentrantLock.lock()</code>, normal execution waits until the lock is acquired; it does not declare <code>InterruptedException</code>. Thread interruption while waiting does not behave the same way as <code>lockInterruptibly()</code>; do not assume every lock-acquisition method has the same contract.

With <code>tryLock()</code> returning <code>false</code>, it is even clearer: **if the lock was not acquired, <code>unlock()</code> must not be called**.

### Why finally instead of catch?

A <code>catch</code> block only runs for the exception types it catches. If you write:

~~~java
lock.lock();
try {
    updateSharedState();
} catch (IllegalArgumentException e) {
    lock.unlock();
    throw e;
}
lock.unlock();
~~~

then other exception types and certain early-exit paths can still skip the unlock call. This snippet is **non-standalone illustrative code** intentionally showing an error-prone structure.

<code>finally</code> centralizes the release operation in a single place. If you need <code>catch</code> to add context or translate an exception, you can place it **inside the same <code>try</code> block or around the lock region**, while keeping <code>finally</code> responsible for releasing the lock.

In exceptional failures such as the JVM halting abruptly or the process being killed, Java does not guarantee that every <code>finally</code> block will execute. This mechanism addresses lock management in normal Java execution paths, not system recovery after every physical failure.

## 4. Standalone Java 17 Example: Exceptions Do Not Leak ReentrantLock

The example below combines three scenarios:

1. A valid balance update.
2. An operation rejected with an exception inside the locked region; another thread can still acquire the lock afterward.
3. Four threads incrementing a counter concurrently; consistent lock release ensures every increment is performed safely.

Create the file **LockFinallyDemo.java**:

~~~java
import java.util.concurrent.locks.ReentrantLock;

public class LockFinallyDemo {

    static final class Wallet {
        private final ReentrantLock lock = new ReentrantLock();
        private int balance;

        Wallet(int initialBalance) {
            if (initialBalance < 0) {
                throw new IllegalArgumentException("Số dư ban đầu âm");
            }
            balance = initialBalance;
        }

        void deposit(int amount) {
            lock.lock();
            try {
                if (amount <= 0) {
                    throw new IllegalArgumentException("Số tiền phải dương");
                }
                balance = Math.addExact(balance, amount);
            } finally {
                lock.unlock();
            }
        }

        void withdraw(int amount) {
            lock.lock();
            try {
                if (amount <= 0) {
                    throw new IllegalArgumentException("Số tiền phải dương");
                }
                if (amount > balance) {
                    throw new IllegalStateException("Không đủ số dư");
                }
                balance -= amount;
            } finally {
                lock.unlock();
            }
        }

        int balance() {
            lock.lock();
            try {
                return balance;
            } finally {
                lock.unlock();
            }
        }

        // Only for demonstrating/testing lock ownership.
        boolean probeLock() {
            if (!lock.tryLock()) {
                return false;
            }
            try {
                return true;
            } finally {
                lock.unlock();
            }
        }
    }

    static final class Counter {
        private final ReentrantLock lock = new ReentrantLock();
        private int value;

        void increment() {
            lock.lock();
            try {
                value++;
            } finally {
                lock.unlock();
            }
        }

        int get() {
            lock.lock();
            try {
                return value;
            } finally {
                lock.unlock();
            }
        }
    }

    public static void main(String[] args) throws InterruptedException {
        Wallet wallet = new Wallet(100);
        wallet.deposit(50);

        try {
            wallet.withdraw(200);
        } catch (IllegalStateException e) {
            System.out.println("Giao dịch bị từ chối: " + e.getMessage());
        }

        boolean[] probeResult = {false};
        Thread probe = new Thread(
                () -> probeResult[0] = wallet.probeLock());
        probe.start();
        probe.join();

        System.out.println("Luồng khác lấy được khóa: " + probeResult[0]);

        wallet.withdraw(20);
        System.out.println("Số dư cuối: " + wallet.balance());

        Counter counter = new Counter();
        Thread[] workers = new Thread[4];

        for (int i = 0; i < workers.length; i++) {
            workers[i] = new Thread(() -> {
                for (int n = 0; n < 5_000; n++) {
                    counter.increment();
                }
            });
        }

        for (Thread worker : workers) {
            worker.start();
        }
        for (Thread worker : workers) {
            worker.join();
        }

        System.out.println("Tổng số lần tăng: " + counter.get());
    }
}
~~~

Compile and run with Java 17+:

~~~bash
javac -encoding UTF-8 LockFinallyDemo.java
java LockFinallyDemo
~~~

Stdout:

~~~text
Giao dịch bị từ chối: Không đủ số dư
Luồng khác lấy được khóa: true
Số dư cuối: 130
Tổng số lần tăng: 20000
~~~

### Result Analysis

- Initially the wallet has 100 units; depositing 50 brings it to 150.
- <code>withdraw(200)</code> throws <code>IllegalStateException</code> **before subtracting the balance**. The thread exits the <code>try</code> block, runs <code>finally</code>, and the exception reaches <code>catch</code> in <code>main</code>.
- The lock probe runs on **another thread**, because <code>ReentrantLock</code> allows **the thread currently owning the lock** to call <code>tryLock()</code> successfully even if it has not released all its hold counts. Checking again on the same thread would not prove the lock was released.
- The program calls <code>probe.join()</code> before reading the result array, so the probe thread's work has finished and its update is visible after <code>join()</code>.
- Withdrawing 20 more leaves a balance of 130. In this example, the invalid operation does not mutate data; <code>finally</code> guarantees the lock is not held when an error is thrown.
- Four threads increment <code>Counter</code> 5,000 times each, producing exactly 20,000 increments. The threads are joined with <code>join()</code> before reading the total, so the result does not depend on scheduling order.

In real implementations, a <code>probeLock()</code> method solely for observing lock state should generally not be part of a business API; it is present here to demonstrate a specific check.

## 5. finally Preserves the Lock, but Is Not Enough to Preserve State

Suppose a shopping cart stores two fields:

- <code>stock</code>: the quantity of items still available for sale.
- <code>reserved</code>: the quantity already reserved.

A reservation operation must both decrement <code>stock</code> and increment <code>reserved</code>. If code mutates the first field and then throws an exception before mutating the second, the state can become inconsistent **even though the lock is released in finally**.

Dangerous design example:

~~~java
lock.lock();
try {
    stock -= amount;
    callPotentiallyFailingOperation();
    reserved += amount;
} finally {
    lock.unlock();
}
~~~

This is **illustrative code**, assuming the corresponding variables and method already exist. If <code>callPotentiallyFailingOperation()</code> throws an error, <code>stock</code> has already been decremented while <code>reserved</code> has not been incremented. <code>finally</code> only releases the lock; it cannot know how to restore the data.

**Design principle:** protect two separate goals:

1. **Lock safety:** every exit path after acquiring the lock releases it properly.
2. **State safety:** every operation completes or fails according to defined rules, never publishing state that violates invariants.

### Preferred approach: validate first, mutate later

Whenever possible, perform all checks that may fail **before state mutations**, and then update fields using small, deterministic operations without calling external code in between.

The example below is a **snippet placed inside a class with appropriately typed <code>lock</code>, <code>stock</code>, and <code>reserved</code> fields**:

~~~java
void reserve(int amount) {
    lock.lock();
    try {
        if (amount <= 0) {
            throw new IllegalArgumentException("Số lượng phải dương");
        }
        if (amount > stock) {
            throw new IllegalStateException("Không đủ hàng");
        }
        int newReserved = Math.addExact(reserved, amount);

        stock -= amount;
        reserved = newReserved;
    } finally {
        lock.unlock();
    }
}
~~~

The checks for positive quantity, sufficient stock, and integer overflow all complete before mutating data. After that, only two primitive assignments remain, with no arbitrary code invoked in between. If the project has other invariants, those invariants must also be checked.

If updating multiple objects or performing I/O, a "validate-first" approach may not be enough: external code can still fail mid-sequence. In such cases, you may need to prepare new state in memory before publishing, implement a reliable rollback mechanism, use a database transaction, or design a dedicated consistency protocol. An in-memory lock **does not create a database transaction** and does not undo external side effects.

### The Math.addExact case in the demo

The line:

~~~java
balance = Math.addExact(balance, amount);
~~~

has a useful property: if the sum exceeds the <code>int</code> range, <code>Math.addExact</code> throws <code>ArithmeticException</code> before the assignment updates <code>balance</code>. <code>finally</code> still releases the lock, and the balance remains unchanged. This is better than unchecked <code>int</code> addition in a domain that requires a valid balance.

## 6. Four Principles When Working with ReentrantLock

### 6.1. Every successful lock acquisition must have a matching release

<code>ReentrantLock</code> is a **reentrant** lock: the same thread can call <code>lock()</code> multiple times without deadlocking itself. Each successful acquisition increments the *hold count*. Each matching <code>unlock()</code> decrements that count; ownership is actually released when the hold count reaches 0.

Illustrative snippet inside a method:

~~~java
lock.lock();       // Hold count: 1
try {
    lock.lock();   // Hold count: 2
    try {
        doWork();
    } finally {
        lock.unlock(); // Hold count: 1
    }
} finally {
    lock.unlock();     // Hold count: 0
}
~~~

Assume <code>doWork()</code> and <code>lock</code> exist. If one <code>unlock()</code> is forgotten, the thread still holds the lock, even though one <code>finally</code> block executed. In real code, unnecessary nested acquisitions of the same lock should be avoided to keep code easy to review.

### 6.2. Only the thread owning the lock may call unlock

With <code>ReentrantLock</code>, calling <code>unlock()</code> from a thread that does not own the lock throws <code>IllegalMonitorStateException</code>. Another thread cannot "clean up" a lock it does not hold. Therefore, place <code>unlock()</code> in the <code>finally</code> block of **the exact thread and control flow that acquired the lock**.

Do not split "thread A locks; thread B unlocks" when using <code>ReentrantLock</code>. If you need to coordinate work between threads, design a synchronization mechanism suited for that requirement rather than violating lock ownership.

### 6.3. All accesses to shared state must follow the same locking protocol

A lock only synchronizes operations that participate in the same protocol. For example, if <code>Counter.increment()</code> acquires the lock but another place reads the <code>value</code> field directly without protection, the reader does not get the same consistent visibility guarantee.

With a <code>Lock</code> on the same lock object, an <code>unlock()</code> and a subsequent successful <code>lock()</code> have a happens-before synchronization relationship that ensures visibility of memory changes published under the lock. For consistent reads and writes, that convention must be upheld on **every access path** to the protected data.

### 6.4. Do not hold the lock longer than necessary

If a locked region performs network I/O, slow file writes, waits for user input, or invokes uncontrolled callbacks, other threads will have to wait a long time. Therefore, narrow the locked region around the operations that need protection, but only move work outside after reviewing invariants and required ordering.

Do not arbitrarily split a check and an update into two separate locked regions:

~~~java
lock.lock();
try {
    if (balance < amount) {
        throw new IllegalStateException("Không đủ số dư");
    }
} finally {
    lock.unlock();
}

// Another thread may modify balance in this gap.

lock.lock();
try {
    balance -= amount;
} finally {
    lock.unlock();
}
~~~

This is **non-standalone illustrative code**. It creates a *check-then-act* bug: two separate blocks are locked, but the overall operation is no longer atomic. Checking a condition and performing an update that depends on it usually must belong to the same lock acquisition.

## 7. When Lock Acquisition Is Uncertain: tryLock

The <code>tryLock()</code> method on <code>Lock</code> returns <code>true</code> if the call acquires the lock immediately at that moment, or <code>false</code> if it cannot according to the implementation's contract. With <code>ReentrantLock</code>, the same thread already holding the lock can still call <code>tryLock()</code> successfully due to reentrancy.

Safe pattern:

~~~java
boolean acquired = lock.tryLock();
if (!acquired) {
    return false;
}
try {
    updateSharedState();
    return true;
} finally {
    lock.unlock();
}
~~~

This snippet is **illustrative code inside a method returning <code>boolean</code>**. The <code>false</code> branch exits before entering <code>try</code> because it does not own the lock. If successful, <code>finally</code> releases the lock even if <code>updateSharedState()</code> throws an exception or executes <code>return</code>.

Do not write:

~~~java
try {
    if (lock.tryLock()) {
        updateSharedState();
    }
} finally {
    lock.unlock();
}
~~~

This is **intentionally wrong code**: if <code>tryLock()</code> returns <code>false</code>, <code>finally</code> still calls <code>unlock()</code> when the thread does not own the lock, and <code>ReentrantLock</code> may throw <code>IllegalMonitorStateException</code>.

In real code, a variable named <code>acquired</code> helps reviewers verify the unlock condition accurately, especially when there are multiple exit paths.

## 8. Cancellable Lock Waiting: lockInterruptibly and Timed tryLock

### 8.1. lockInterruptibly()

<code>lockInterruptibly()</code> allows a thread waiting for a lock to respond to an interrupt signal per the <code>Lock</code> contract and declares <code>throws InterruptedException</code>. Standard structure when the method allows propagating the exception:

~~~java
void update() throws InterruptedException {
    lock.lockInterruptibly();
    try {
        updateSharedState();
    } finally {
        lock.unlock();
    }
}
~~~

This illustrative snippet assumes <code>lock</code> and <code>updateSharedState()</code> already exist. If the thread is interrupted **before acquiring the lock**, <code>lockInterruptibly()</code> can throw <code>InterruptedException</code> and the code does not enter <code>try</code>: <code>unlock()</code> is not called. If the lock was already acquired and an exception occurs **inside <code>try</code>**, <code>finally</code> releases the lock along the normal execution path.

If you cannot declare <code>throws InterruptedException</code> and must convert it to an unchecked exception, the handler typically needs to restore the interrupt flag via <code>Thread.currentThread().interrupt()</code> while passing the original exception as the cause. However, the exact handling depends on the task's contract.

### 8.2. tryLock(timeout, unit)

A method that waits at most for a bounded duration can be written as:

~~~java
boolean acquired = lock.tryLock(200, java.util.concurrent.TimeUnit.MILLISECONDS);
if (!acquired) {
    return false;
}
try {
    updateSharedState();
    return true;
} finally {
    lock.unlock();
}
~~~

This snippet is **illustrative code belonging to a method that returns <code>boolean</code> and declares or handles <code>InterruptedException</code>**. Do not forget:

- Returning <code>false</code> due to timeout or failure to acquire the lock means **do not unlock**.
- The method can throw <code>InterruptedException</code> while waiting; in that case, no lock ownership was obtained from this call.
- Only after <code>acquired == true</code> do you enter the block with the corresponding <code>finally</code>.

If <code>tryLock</code> is called from a thread that already held the <code>ReentrantLock</code> previously, the hold count may increase; the <code>unlock()</code> call in this method only releases the acquisition made by the current call, not all holds from outer contexts.

## 9. return, break, and Exceptions Inside try

Java runs <code>finally</code> before completing an exit from a <code>try</code> block caused by <code>return</code>, <code>break</code>, <code>continue</code>, or an exception under normal rules. Therefore, you can return a result directly inside the locked region:

~~~java
int readBalance() {
    lock.lock();
    try {
        return balance;
    } finally {
        lock.unlock();
    }
}
~~~

Illustrative code in a class with <code>lock</code> and <code>balance</code>. The <code>return balance</code> expression is evaluated before the method actually exits; the <code>finally</code> block releases the lock before the caller receives the result.

However, **do not write <code>return</code> or throw a new exception gratuitously inside <code>finally</code>**. A <code>return</code> statement in <code>finally</code> can overwrite the return value or suppress an exception from <code>try</code>.

Wrong example:

~~~java
lock.lock();
try {
    return readData();
} finally {
    lock.unlock();
    return null;
}
~~~

This is illustrative code in a method returning a reference type. The <code>return null</code> in <code>finally</code> can mask the result or exception from <code>readData()</code>. <code>finally</code> should be reserved for mandatory cleanup/release, not changing how the method reports its result.

### What about exceptions from unlock()?

<code>ReentrantLock.unlock()</code> can throw <code>IllegalMonitorStateException</code> if called when the thread does not own the lock. If <code>finally</code> throws a new exception, that exception can **suppress** the exception being thrown from <code>try</code>. With the proper pattern, each successful lock acquisition is released once by the owning thread, so this error is not part of normal handling.

Do not add <code>catch (Exception ignored)</code> around <code>unlock()</code> just to hide an ownership-management bug. Fix the root cause of the invalid unlock, because it reflects a synchronization logic flaw.

## 10. Exceptions Inside a Locked Region: Where Should They Be Handled?

The pattern below both preserves lock release and lets meaningful errors propagate:

~~~java
lock.lock();
try {
    validateRequest();
    changeState();
} finally {
    lock.unlock();
}
~~~

This is an **illustrative code snippet** where <code>lock</code>, <code>validateRequest()</code>, and <code>changeState()</code> already exist.

If an API layer needs to translate a technical exception into a more appropriate one, it can catch and wrap it while keeping the lock-release rule intact:

~~~java
lock.lock();
try {
    return dataStore.load();
} catch (java.io.IOException original) {
    throw new DataAccessException("Không thể tải dữ liệu", original);
} finally {
    lock.unlock();
}
~~~

This is **illustrative code** in a method with an appropriate return type; it assumes <code>dataStore.load()</code> declares <code>IOException</code> and a constructor <code>DataAccessException(String, Throwable)</code> exists. <code>finally</code> still runs before the new exception escapes. Passing <code>original</code> as the cause preserves the I/O stack trace for diagnostics.

From a design standpoint, if the I/O operation can run for a long time, consider whether the lock truly needs to be held across that call. You may be able to separate the preparation step and the result-publishing step to reduce lock hold time, provided ordering and data invariants are still preserved.

### Should you swallow exceptions?

Do not write an empty <code>catch</code> block and release the lock as if the operation succeeded. If the error has been fully recovered according to the contract, the application can continue; otherwise, it must report an appropriate error. Also do not turn every error into a fake success value (<code>0</code>, <code>null</code>, empty string) if the API does not define that as an error representation.

## 11. When Multiple Locks Are Needed: finally Still Does Not Prevent Deadlock

Suppose a transfer between two accounts needs to acquire the locks of both. If thread A acquires account X's lock first and then waits for Y, while thread B acquires Y's lock first and then waits for X, the system can deadlock.

Even if both threads are written as:

~~~java
first.lock();
try {
    second.lock();
    try {
        transfer();
    } finally {
        second.unlock();
    }
} finally {
    first.unlock();
}
~~~

this illustrative snippet **can still deadlock** if threads acquire the same two locks in different orders. <code>finally</code> only executes when the program leaves running blocks; it does not help a thread escape a <code>second.lock()</code> call that is waiting indefinitely.

Common design approaches:

- Define a fixed, consistent lock-acquisition order across all threads.
- Reduce the number of locks held simultaneously when possible.
- Consider bounded <code>tryLock</code> and how to release already-acquired locks if the next lock cannot be obtained.
- Do not assume that increasing timeouts or adding <code>finally</code> is enough to solve deadlock.

**Never forcibly unlock a lock owned by another thread** to "break a deadlock"; <code>ReentrantLock</code> ownership semantics do not permit that.

## 12. Condition.await() and Temporary Lock Release

<code>Condition</code> is commonly created via <code>ReentrantLock.newCondition()</code>. Wait methods such as <code>await()</code> have a special mechanism: while waiting, the thread **temporarily releases the lock associated with the condition**, and when waiting ends per its contract, it **reacquires the lock before returning or throwing <code>InterruptedException</code>**.

A typical pattern:

~~~java
lock.lock();
try {
    while (!ready) {
        condition.await();
    }
    consumeReadyData();
} finally {
    lock.unlock();
}
~~~

This is an **illustrative snippet** in a method that declares/handles <code>InterruptedException</code>, with <code>lock</code>, <code>condition</code>, <code>ready</code>, and <code>consumeReadyData()</code> already defined. The <code>while</code> loop is necessary because the condition may no longer hold after waking up, and <code>await()</code> can wake up even without a corresponding signal.

The <code>finally</code> rule still applies: after <code>lock.lock()</code> succeeds, the thread ends the processing block with a proper <code>unlock()</code>. The fact that <code>await()</code> temporarily releases and reacquires the lock is part of the <code>Condition</code> contract, not an invitation for users to call <code>unlock()</code> arbitrarily right after <code>await()</code>.

Do not call <code>await()</code> or <code>signal()</code> of a condition on a <code>ReentrantLock</code> without holding the corresponding lock; with this implementation, doing so results in <code>IllegalMonitorStateException</code>.

## 13. Comparing synchronized and Lock

Java also has the syntax:

~~~java
synchronized (monitor) {
    updateSharedState();
}
~~~

The illustrative code above uses a declared monitor object. When a thread leaves a <code>synchronized</code> block, the JVM automatically releases the monitor per language semantics, even if the block throws an exception. With <code>Lock</code>, releasing the lock is the **explicit responsibility of the programmer**, because it is a method-based API.

| Aspect | <code>synchronized</code> | <code>ReentrantLock</code> |
| --- | --- | --- |
| Entering locked region | <code>synchronized (monitor)</code> | <code>lock.lock()</code> |
| Exiting locked region | JVM automatically releases monitor on block exit | Must call <code>unlock()</code>, typically in <code>finally</code> |
| Immediate lock attempt | No direct API equivalent like <code>tryLock()</code> | Has <code>tryLock()</code> |
| Interruptible wait on lock acquisition | No monitor-enter equivalent to <code>lockInterruptibly()</code> | Has <code>lockInterruptibly()</code> |
| Condition | <code>wait/notify/notifyAll</code> tied to monitor | <code>Condition</code> created by the lock |

Using <code>ReentrantLock</code> is not automatically better than <code>synchronized</code>. If you only need to protect a short region and do not need flexible lock-acquisition features, <code>synchronized</code> can be simpler. Once you choose <code>Lock</code>, the <code>try/finally</code> rule is a mandatory part of safe design.

## 14. Testing to Ensure Lock Release

Tests should evaluate **exception exit paths**, not just the success path.

| Test scenario | Expectation |
| --- | --- |
| Critical section completes normally | Lock is released |
| Input validation inside locked region throws an exception | Exception is still propagated and lock is released |
| Code throws <code>ArithmeticException</code> before assignment | Data is unchanged, lock is released |
| <code>return</code> inside <code>try</code> | Correct value is returned and lock is released |
| <code>tryLock()</code> returns <code>false</code> | <code>unlock()</code> must not be called |
| <code>lockInterruptibly()</code> interrupted before owning lock | Interrupt exception is propagated/handled, unowned lock is not released |
| Multiple threads mutating data concurrently | Results and invariants are preserved under the same locking protocol |

To test for lock leaks on <code>ReentrantLock</code>, test from **another thread**. If you only call <code>lock()</code> again on the same thread, reentrancy can make the test think the lock was released even when the hold count is still positive.

In concurrency tests, avoid letting a lock bug hang the test indefinitely. You can use timeouts, <code>tryLock(timeout, unit)</code>, or synchronization mechanisms in the test to proceed only once state has been established. Do not assert correctness from a single run that "did not get stuck"; tests should verify invariants, results, and intentional exception paths.

For classes with multiple shared fields, add tests verifying that after each expected error, the state remains valid. A "lock was released" check alone is not enough to prove the data remains consistent.

## 15. Common Mistakes During Code Review

1. **Placing <code>unlock()</code> after the operation block without <code>finally</code>:** errors, <code>return</code>, or early exits can skip it.
2. **Unlocking even when the lock was not acquired:** common with <code>tryLock()</code> or <code>lockInterruptibly()</code> when <code>try</code> boundaries are placed incorrectly.
3. **Calling <code>unlock()</code> twice for a single acquisition:** can lead to <code>IllegalMonitorStateException</code> or corrupt the hold count.
4. **Unlocking on a different thread:** violates <code>ReentrantLock</code>'s ownership contract.
5. **Wrapping the entire <code>finally</code> block in an empty catch:** hides lock-management bugs and makes diagnostics harder.
6. **Assuming finally rolls back state automatically:** the lock is released, but state may have been partially updated.
7. **Checking then updating in two separate locked regions:** creates a gap where another thread can modify the data.
8. **Forgetting to lock on reads:** read values may not be synchronized with writes protected by the lock.
9. **Running slow work or uncontrolled callbacks inside the locked region:** increases wait times and deadlock risk.
10. **Acquiring multiple locks in different orders:** <code>finally</code> cannot fix a deadlock caused by waiting for the next lock.
11. **Using <code>return</code> inside finally:** can mask the critical section's return value or exception.
12. **Testing lock release from the same thread:** reentrancy allows <code>tryLock()</code> to succeed even if the lock is still held.
13. **Catching and swallowing all exceptions:** easily continues with invalid state, even though the lock was released.
14. **Ignoring interruption while waiting for a lock:** prevents cancellation mechanisms from working as expected.

## 16. Application Checklist

Before completing a method that uses <code>Lock</code>, ask yourself:

- Did the method acquire the lock **successfully** before entering <code>try</code>?
- Is there exactly one <code>finally</code> path releasing that lock acquisition on the same thread?
- With <code>tryLock()</code> and <code>lockInterruptibly()</code>, do paths that fail to acquire the lock avoid calling <code>unlock()</code>?
- When code throws an exception, does the caller receive the appropriate error, and has the lock been released?
- When an error occurs mid-update, does the data still satisfy invariants? Do you need pre-preparation, rollback, or a transaction?
- Do all threads reading/writing shared data use the same locking protocol?
- Are there unnecessary network calls, I/O, or slow callbacks inside the locked region?
- If multiple locks are used, is the acquisition order consistent across threads?
- Have tests simulated exceptions and verified that **another thread** can still acquire the lock?

**Conclusion:** Placing <code>lock.lock()</code> before <code>try</code> and <code>lock.unlock()</code> in <code>finally</code> is the fundamental <code>Lock</code> management pattern to avoid holding a lock after an error path. To truly **preserve state**, you must also protect invariants, update data under a consistent rule, and handle exceptions according to contract.
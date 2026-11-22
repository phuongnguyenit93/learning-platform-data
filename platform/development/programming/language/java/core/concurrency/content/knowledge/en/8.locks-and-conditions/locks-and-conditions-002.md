# ReentrantLock: lock(), unlock(), and finally in Java

## 1. Objectives and Scope

After this lesson, you will be able to:

- Explain **java.util.concurrent.locks.ReentrantLock** and the relationship between the lock object, the owning thread, the critical section, and the protected data.
- Write the **lock.lock() → try → finally → lock.unlock()** pattern correctly, even when code inside the critical section throws an exception or returns early.
- Understand **reentrancy** (a thread can reacquire a lock it already holds), **hold count**, owner state, and the consequences of calling unlock() incorrectly.
- Distinguish **lock()**, **lockInterruptibly()**, **tryLock()**, and **tryLock(timeout, unit)** by their waiting behavior, interruptibility, and lock release conditions.
- Recognize the **mutual exclusion** and **happens-before** guarantees of Lock, the limitations of fairness, and how to avoid deadlocks through lock ordering.
- Know when **Condition.await()/signal()/signalAll()** is more appropriate than sleep/yield loops or custom condition-waiting implementations.
- Choose appropriately between **synchronized** and ReentrantLock, keep locks short, and protect the entire shared invariant.

The scope is strictly **JDK Java concurrency**. Spring-specific mechanisms are covered in another chapter.

## 2. What Is ReentrantLock?

**ReentrantLock** is a concrete class in **java.util.concurrent.locks** that implements the **Lock** interface. It provides a **reentrant** mutual exclusion lock similar to the intrinsic monitor used by **synchronized**, but with an explicit lock-control API.

~~~java
import java.util.concurrent.locks.ReentrantLock;

// Illustrative snippet inside a Java class/method.
ReentrantLock lock = new ReentrantLock();

lock.lock();
try {
    // Read/write shared data under the same lock.
} finally {
    lock.unlock();
}
~~~

This is a syntax illustration, not a standalone program with main().

When one thread holds a ReentrantLock, other threads attempting to acquire the same lock object will either wait or fail depending on the method used. Unlike **synchronized**, Java **does not automatically call unlock()** when exiting a code block normally, returning, or throwing an exception. Therefore, **finally** is essential to preserve lock ownership integrity.

Key concepts:

| Concept | Meaning |
| --- | --- |
| **Lock object** | The shared ReentrantLock instance used across all code paths protecting the same invariant |
| **Owner** | The thread currently holding the lock |
| **Critical section** | The data read/write section that must execute while the owner holds the lock |
| **Acquisition** | Successfully acquiring the lock via lock(), lockInterruptibly(), or tryLock() |
| **Release** | Calling unlock() the exact number of times by the **owner itself** |
| **Hold count** | The number of lock levels still held by the current thread due to reentrant acquisition |
| **Waiter/contender** | Another thread attempting to acquire the lock while the current owner has not yet released it |

Safety depends on **all relevant access paths** using **the same ReentrantLock object**, or another synchronization protocol with sound JMM reasoning. Simply having a variable named `lock` in each thread is not enough: if threads each create their own **new ReentrantLock()**, there is no mutual exclusion between them.

## 3. Mandatory Pattern: lock() Followed by try/finally

Correct basic pattern:

~~~java
lock.lock();
try {
    updateSharedState();
} finally {
    lock.unlock();
}
~~~

This is illustrative code; **lock** and **updateSharedState()** must be defined in an actual class. Notable points:

1. **lock.lock()** is called before **try** and must succeed for the thread to be considered the owner.
2. Immediately upon acquiring the lock, enter **try** so that every exit path from the critical section reaches **finally**.
3. All operations requiring protection remain inside the try block.
4. **finally** calls unlock() exactly once, matching the lock() just acquired.
5. If the body returns, breaks, or throws an exception, **finally is still executed** as the stack unwinds through that block; unlocking does not depend on normal exit.
6. If code in finally contains additional logic that itself throws an exception before unlock, the lock may remain held. Therefore, keep finally simple and perform only the necessary release operation.

**Why does try come after lock()?** If an acquisition attempt can fail and the program still calls unlock(), a non-owner thread will encounter **IllegalMonitorStateException**. With ordinary lock(), the call waits until the lock is acquired, yet placing try **immediately after** remains the standard pattern to avoid releasing a lock you do not own.

### Mistake 1: Forgetting finally

~~~java
lock.lock();
updateSharedState(); // If this throws an exception...
lock.unlock();        // ...this statement does not run.
~~~

This is an erroneous illustration, not a standalone program. The lock may remain held indefinitely by the thread that threw the exception. Other threads needing the lock may wait forever, especially if the owner thread stays alive. Even if the owner thread terminates after the exception, ReentrantLock **does not have an automatic unlock mechanism when a thread dies**; waiting threads still cannot enter the critical section because of that.

### Mistake 2: Calling unlock() Without Ownership

~~~java
// Anti-pattern if tryLock fails:
if (lock.tryLock()) {
    updateSharedState();
}
lock.unlock(); // May throw IllegalMonitorStateException.
~~~

If tryLock() returns false, the caller was not granted the lock. If tryLock() succeeds but updateSharedState() throws an exception, the outer unlock may also be skipped.

Correct approach:

~~~java
if (lock.tryLock()) {
    try {
        updateSharedState();
    } finally {
        lock.unlock();
    }
}
~~~

Only release the lock when acquisition succeeds. With **tryLock(timeout, unit)** and **lockInterruptibly()**, you must also place finally on the **path where the lock was actually acquired**.

### Mistake 3: Early Return Without Releasing the Lock

~~~java
lock.lock();
try {
    if (isRejected()) {
        return;
    }
    updateSharedState();
} finally {
    lock.unlock();
}
~~~

This is illustrative code inside a void method; **isRejected()** is a hypothetical helper. Returning inside try still executes finally before the method finishes. Thus, the try/finally structure is safer than trying to remember to call unlock in every if/else branch.

## 4. Java 17+ Example: Accurate Counting with ReentrantLock

File **ReentrantCounterDemo.java**:

~~~java
import java.util.concurrent.locks.ReentrantLock;

public class ReentrantCounterDemo {
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

        int snapshot() {
            lock.lock();
            try {
                return value;
            } finally {
                lock.unlock();
            }
        }
    }

    public static void main(String[] args) throws InterruptedException {
        Counter counter = new Counter();

        Runnable task = () -> {
            for (int i = 0; i < 10_000; i++) {
                counter.increment();
            }
        };

        Thread a = new Thread(task, "worker-a");
        Thread b = new Thread(task, "worker-b");
        a.start();
        b.start();
        a.join();
        b.join();

        System.out.println("count = " + counter.snapshot());
    }
}
~~~

Run:

~~~bash
javac -encoding UTF-8 ReentrantCounterDemo.java
java ReentrantCounterDemo
~~~

Stdout:

~~~text
count = 20000
~~~

**Correctness reasoning:** both threads share the same **Counter**, so both lock **the same Counter.lock**. Each read–modify–write of value occurs while one thread holds the lock. Two increments never overwrite each other from the same stale value. snapshot() also reads under that lock. The two join() calls ensure main waits for all increments to finish before checking the result.

If increment() uses ReentrantLock while snapshot() reads value freely while workers are still running, that is an inconsistent visibility design. For lock-protected data, unify the access rule across all relevant paths.

### Critical Section Granularity

Do not hold the lock for an entire loop if the requirement only needs each individual increment to be atomic; conversely, for an invariant spanning multiple variables, you must wrap **the entire multi-step decision** into one critical section.

Business example of checking then decrementing stock:

~~~java
// Illustrative code inside a boolean reserve() method:
lock.lock();
try {
    if (stock <= 0) {
        return false;
    }
    stock--;
    return true;
} finally {
    lock.unlock();
}
~~~

**stock** is a shared field of the same object, protected by the existing lock. Placing the check outside and only locking around stock-- would leave a **logic race** because another thread could modify stock between the two operations.

## 5. finally Works Even When an Exception Occurs

File **UnlockOnExceptionDemo.java**:

~~~java
import java.util.concurrent.locks.ReentrantLock;

public class UnlockOnExceptionDemo {
    public static void main(String[] args) {
        ReentrantLock lock = new ReentrantLock();

        try {
            lock.lock();
            try {
                System.out.println("inside = " + lock.isHeldByCurrentThread());
                throw new IllegalStateException("example failure");
            } finally {
                lock.unlock();
            }
        } catch (IllegalStateException ex) {
            System.out.println("caught = " + ex.getMessage());
        }

        System.out.println("after = " + lock.isHeldByCurrentThread());

        lock.lock();
        try {
            System.out.println("acquired again = true");
        } finally {
            lock.unlock();
        }
    }
}
~~~

~~~bash
javac -encoding UTF-8 UnlockOnExceptionDemo.java
java UnlockOnExceptionDemo
~~~

Stdout:

~~~text
inside = true
caught = example failure
after = false
acquired again = true
~~~

**Explanation:** the exception exits the try block containing the critical section, but finally releases the lock before the outer catch handles the error. The check after catch returns false because the current thread no longer owns the lock. The subsequent lock() call is able to acquire the lock again.

Be careful: finally **releases the lock**, but **does not automatically roll back modified data**. If you are updating multiple fields and an exception is thrown halfway through, you must keep invariants consistent or provide an explicit recovery strategy; do not confuse lock release with a transaction.

## 6. Reentrancy and Hold Count

Reentrant means that a thread **already owning** a ReentrantLock can call **lock() again** on the same object without deadlocking itself. Each successful lock increments the hold count; each unlock by the owner decrements the count. The lock only becomes available to other threads when the hold count returns to 0.

Diagnostic helper methods:

- **isHeldByCurrentThread()**: whether the calling thread currently owns this lock.
- **getHoldCount()**: the number of holds on this lock by the current thread; returns 0 for non-owning threads.
- **isLocked()**: whether any thread currently owns the lock; this is a snapshot and cannot be used as a safety condition in place of lock().
- **isFair()**: whether the lock was created with a fair policy.
- **getQueueLength()**: an estimate of the number of waiting threads, not an exact figure for business decisions.

### Java 17+ Example: Nested Locking

File **ReentrantHoldDemo.java**:

~~~java
import java.util.concurrent.locks.ReentrantLock;

public class ReentrantHoldDemo {
    public static void main(String[] args) {
        ReentrantLock lock = new ReentrantLock();

        lock.lock();
        try {
            System.out.println("outer hold = " + lock.getHoldCount());

            lock.lock();
            try {
                System.out.println("inner hold = " + lock.getHoldCount());
            } finally {
                lock.unlock();
            }

            System.out.println("after inner = " + lock.getHoldCount());
        } finally {
            lock.unlock();
        }

        System.out.println("after outer = " + lock.getHoldCount());
    }
}
~~~

~~~bash
javac -encoding UTF-8 ReentrantHoldDemo.java
java ReentrantHoldDemo
~~~

Stdout:

~~~text
outer hold = 1
inner hold = 2
after inner = 1
after outer = 0
~~~

This runs on a single thread, so the stdout order is deterministic. **Every successful lock must have a corresponding unlock**. If you unlock only once after two locks, the thread still holds the lock at level 1; other threads cannot acquire it yet.

Reentrancy is useful when a method holding a lock calls another method of the same class that also uses the exact same lock. Even so, avoid arbitrarily overusing deeply nested locks or mutually calling methods that become hard to reason about.

### Unlocking by the Wrong Owner

**ReentrantLock.unlock()** requires the current thread to hold the lock. If another thread calls unlock(), or the caller does not own the lock, it throws **IllegalMonitorStateException**. Never ask another thread to "clean up a lock on someone else's behalf" when the owner is stuck; design tasks and cancellation/timeouts properly instead of unlocking from a non-owner thread.

## 7. Four Acquisition Paths

### 7.1. lock(): Wait Until the Lock Is Acquired

~~~java
lock.lock();
try {
    performCriticalAction();
} finally {
    lock.unlock();
}
~~~

If another owner holds the lock, the caller waits until it can acquire it. **lock() is not an acquisition call that can be cancelled via InterruptedException**. When a thread is interrupted while waiting, lock() may continue waiting until the lock is acquired; exact interrupt status behavior follows the implementation contract, but you must not assume it will exit the wait with a checked exception.

Use lock() for critical sections that must complete and have short hold times, where cancelling the **wait to acquire the lock** is not required.

### 7.2. lockInterruptibly(): Interruptible Lock Acquisition

~~~java
lock.lockInterruptibly();
try {
    performCriticalAction();
} finally {
    lock.unlock();
}
~~~

**lockInterruptibly() throws InterruptedException** if interrupted before acquiring the lock; in that case the caller **does not own the lock**, so the finally block above must not run. Because try begins after the acquisition call, this pattern is correct.

Once the lock has been acquired, a subsequent interrupt does not automatically release the lock: code inside try must cooperate in handling interrupts according to the operation's policy, and finally must still unlock.

### 7.3. tryLock(): Try Immediately, Return boolean

~~~java
if (lock.tryLock()) {
    try {
        performCriticalAction();
    } finally {
        lock.unlock();
    }
} else {
    // Cannot enter the critical section right now.
}
~~~

**tryLock()** returns true if the lock is acquired immediately, false if not; it is not a bounded wait call. If the thread already holds the lock, it can acquire reentrantly and return true. The caller must explicitly decide the fallback when false; do not silently skip critical work or execute the critical section unlocked.

### 7.4. tryLock(timeout, unit): Bounded Wait

~~~java
// Illustration in a method declaring throws InterruptedException:
boolean acquired = lock.tryLock(500, java.util.concurrent.TimeUnit.MILLISECONDS);
if (!acquired) {
    return;
}
try {
    performCriticalAction();
} finally {
    lock.unlock();
}
~~~

This snippet illustrates a void method where lock and performCriticalAction() are already declared. **tryLock(timeout, unit)** can wait up to the specified duration, returning **false** if the lock is not acquired before the deadline, or throwing **InterruptedException** if interrupted while waiting. Timeout timing is subject to timer resolution and scheduling; do not use it to promise exact wall-clock deadlines.

**Only release the lock when acquired == true.** A timeout or interruption before acquisition creates no obligation to unlock.

### Comparison

| Method | When Lock Is Busy | InterruptedException | When Must You unlock()? |
| --- | --- | --- | --- |
| **lock()** | Waits until acquired | Not declared | After lock() returns having acquired it |
| **lockInterruptibly()** | Waits, cancellable by interrupt | Yes | Only after successful acquisition |
| **tryLock()** | Returns false immediately | Not declared | Only when it returns true |
| **tryLock(timeout, unit)** | Waits within bound, or returns false | Yes | Only when it returns true |

All of them obey ownership: the acquiring thread must release the lock the matching number of times itself.

## 8. tryLock() Example: Skipping Work When the Lock Is Unavailable

This example uses latches to control when main attempts to acquire the lock, avoiding tests that rely on sleep for expected outcomes.

File **TryLockDemo.java**:

~~~java
import java.util.concurrent.CountDownLatch;
import java.util.concurrent.locks.ReentrantLock;

public class TryLockDemo {
    public static void main(String[] args) throws InterruptedException {
        ReentrantLock lock = new ReentrantLock();
        CountDownLatch locked = new CountDownLatch(1);
        CountDownLatch release = new CountDownLatch(1);

        Thread holder = new Thread(() -> {
            lock.lock();
            try {
                locked.countDown();
                try {
                    release.await();
                } catch (InterruptedException ex) {
                    Thread.currentThread().interrupt();
                }
            } finally {
                lock.unlock();
            }
        }, "holder");

        holder.start();
        locked.await();

        boolean acquiredWhileBusy = lock.tryLock();
        System.out.println("while busy = " + acquiredWhileBusy);
        if (acquiredWhileBusy) {
            lock.unlock();
        }

        release.countDown();
        holder.join();

        boolean acquiredAfter = lock.tryLock();
        System.out.println("after release = " + acquiredAfter);
        if (acquiredAfter) {
            try {
                System.out.println("main owns lock = " + lock.isHeldByCurrentThread());
            } finally {
                lock.unlock();
            }
        }
    }
}
~~~

~~~bash
javac -encoding UTF-8 TryLockDemo.java
java TryLockDemo
~~~

Stdout under normal execution without external interrupts:

~~~text
while busy = false
after release = true
main owns lock = true
~~~

When locked.await() on main completes, holder has already acquired the lock and is not yet permitted to leave release.await(). Main's first tryLock returns false. After signaling and join(), holder has unlocked; the next tryLock acquires the lock. In both cases, the program only calls unlock when main itself successfully acquired the lock.

In real applications, after tryLock() returns false, you need a concrete policy: skip non-critical work, perform bounded retries, enqueue, or report busy. Never turn false into "success" when the task was not actually executed.

## 9. lockInterruptibly() Example: Cancelling a Lock Wait

File **InterruptibleLockDemo.java**:

~~~java
import java.util.concurrent.CountDownLatch;
import java.util.concurrent.locks.ReentrantLock;

public class InterruptibleLockDemo {
    public static void main(String[] args) throws InterruptedException {
        ReentrantLock lock = new ReentrantLock();
        CountDownLatch attempting = new CountDownLatch(1);

        lock.lock();
        try {
            Thread worker = new Thread(() -> {
                attempting.countDown();
                try {
                    lock.lockInterruptibly();
                    try {
                        System.out.println("worker: acquired");
                    } finally {
                        lock.unlock();
                    }
                } catch (InterruptedException ex) {
                    Thread.currentThread().interrupt();
                    System.out.println("worker: interrupted");
                }
            }, "interruptible-worker");

            worker.start();
            attempting.await();
            worker.interrupt();
            worker.join();
            System.out.println("main: still owns lock = "
                    + lock.isHeldByCurrentThread());
        } finally {
            lock.unlock();
        }
    }
}
~~~

~~~bash
javac -encoding UTF-8 InterruptibleLockDemo.java
java InterruptibleLockDemo
~~~

Stdout:

~~~text
worker: interrupted
main: still owns lock = true
~~~

**Explanation:**

1. Main acquires the lock before starting worker and holds it until after worker.join().
2. Worker prepares to call lockInterruptibly(), signaling its start via the latch.
3. Main sends an interrupt before releasing the lock. Whether the signal arrives before or while worker is waiting, lockInterruptibly() handles the interrupt and throws InterruptedException instead of granting the lock while main still holds it.
4. Worker does not run finally unlock on the failed acquisition path; it only restores its interrupt status and reports being interrupted.
5. Main waits for worker to finish, confirms it still holds the lock, and then finally unlocks.

If you replace lockInterruptibly() with lock(), you cannot rely on interrupt to make worker exit the wait as above; avoid running that same join structure while main still holds the lock, as it can self-deadlock.

## 10. ReentrantLock and the Java Memory Model

**Lock** guarantees more than letting only one thread enter a critical section: Lock implementations such as ReentrantLock have memory-synchronization semantics corresponding to monitors.

- A successful **unlock** on a lock has a *happens-before* relationship with a subsequent successful **lock** on the same lock.
- Writes occurring before the unlock are published to the thread after acquiring the lock according to JMM rules.
- **A failed tryLock()** has none of the synchronization effects of a successful lock acquisition.
- **isLocked()**, **getQueueLength()**, and **hasQueuedThreads()** are diagnostic observations; do not use snapshot values in place of acquiring the lock.
- Lock/unlock does not automatically make data accesses from code **not following the same protocol** safe.

~~~text
Thread A                       Thread B
--------                       --------
lock.lock()                    lock.lock()  [waiting]
try {                          try {
  shared = 42;                    read shared -> 42
} finally {                   } finally {
  lock.unlock();                  lock.unlock();
}                              }

A unlock ---- happens-before ----> B lock
(if B acquires the lock after A with no intervening writes)
~~~

This diagram assumes two critical sections and no intervening writers. In real programs, you must account for all write paths and all relevant locks.

### ReentrantLock Does Not Provide Multi-Step Atomicity If the Lock Scope Is Wrong

~~~java
// Illustrative logic race: two separate critical sections.
lock.lock();
try {
    if (stock <= 0) {
        return false;
    }
} finally {
    lock.unlock();
}

lock.lock();
try {
    stock--;
    return true;
} finally {
    lock.unlock();
}
~~~

Even though each critical section is valid, another thread can decrement stock between the release and the second acquisition. You must lock **around the entire decision** of checking and decrementing, as in the `reserve` example in Section 4.

## 11. Fair and Nonfair ReentrantLock

Default constructors:

~~~java
ReentrantLock fastLock = new ReentrantLock();
ReentrantLock fairLock = new ReentrantLock(true);
~~~

This declaration snippet can be placed inside a Java method; it has no standalone main().

- **Nonfair lock** is the default; a new thread may acquire the lock ahead of waiting threads, depending on scheduling.
- **Fair lock** is designed to favor waiting threads in arrival order under contention, but **does not guarantee absolute CPU scheduler fairness**, does not guarantee equal turns for every thread, and can reduce throughput.
- **Untimed tryLock()** can acquire the lock immediately even when other threads are waiting, **even if the lock is configured as fair**. This is documented barging behavior; do not assume "fair" applies identically to every call.
- When using **tryLock(0, TimeUnit.SECONDS)** on a fair lock, the call uses timed acquisition mechanics, honors the fairness policy of the timed overload, and can be interrupted.
- Do not choose `fair=true` out of habit. Evaluate your application's actual progress, latency, fairness, and throughput requirements.

**Important:** Fairness does not solve **deadlocks**, does not protect data outside the lock, and does not guarantee nanosecond-precise timeout execution.

## 12. Condition: Waiting for Signals Bound to ReentrantLock

**Condition** is created from **lock.newCondition()**, providing wait/signal operations analogous to Object.wait()/notify()/notifyAll(), but bound to an explicit Lock.

- **condition.await()**: requires the current thread to hold the lock; it releases the associated lock while waiting and reacquires it before returning or throwing InterruptedException per contract.
- **condition.signal()**: wakes up one waiter on the condition; the waiter still must reacquire the lock to proceed.
- **condition.signalAll()**: wakes up all waiters on the condition; they will contend for the lock and recheck the condition.
- Because **spurious wakeups** can occur, always use **while (!predicate) condition.await()**, never a single `if`.
- You must invoke **await/signal under the exact lock** associated with the condition. Calling from a non-owner throws IllegalMonitorStateException on ownership-checked operations.

Example pattern:

~~~java
// Illustrative snippet: lock, ready, and condition are already declared.
lock.lock();
try {
    while (!ready) {
        condition.await();  // throws InterruptedException
    }
    consume();
} finally {
    lock.unlock();
}
~~~

This is illustrative code inside a method handling/declaring InterruptedException; consume() is hypothetical logic. Another thread sets ready=true and calls signal/signalAll while holding the same lock.

### Java 17+ Example: Waiting on a Condition and Unlocking Properly

File **ConditionDemo.java**:

~~~java
import java.util.concurrent.CountDownLatch;
import java.util.concurrent.locks.Condition;
import java.util.concurrent.locks.ReentrantLock;

public class ConditionDemo {
    public static void main(String[] args) throws InterruptedException {
        ReentrantLock lock = new ReentrantLock();
        Condition readyCondition = lock.newCondition();
        boolean[] ready = {false};
        CountDownLatch started = new CountDownLatch(1);

        Thread worker = new Thread(() -> {
            lock.lock();
            try {
                System.out.println("worker: waiting");
                started.countDown();

                while (!ready[0]) {
                    try {
                        readyCondition.await();
                    } catch (InterruptedException ex) {
                        Thread.currentThread().interrupt();
                        return;
                    }
                }

                System.out.println("worker: resumed");
            } finally {
                lock.unlock();
            }
        }, "condition-worker");

        worker.start();
        started.await();

        lock.lock();
        try {
            ready[0] = true;
            System.out.println("main: signaled");
            readyCondition.signalAll();
        } finally {
            lock.unlock();
        }

        worker.join();
        System.out.println("main: done");
    }
}
~~~

~~~bash
javac -encoding UTF-8 ConditionDemo.java
java ConditionDemo
~~~

Stdout without external interrupts:

~~~text
worker: waiting
main: signaled
worker: resumed
main: done
~~~

Worker acquires the lock, prints the first line, and calls await() if ready is not yet true. await() releases the lock and waits. Main waits on `started`, so only after worker reports starting does main try to acquire the lock, set ready, and call signalAll. If main arrives before worker actually enters await(), it waits for the lock; afterward the condition remains consistent because both read/write under the same lock. When worker resumes, it reacquires the lock and checks ready in the while loop.

If the condition is already true beforehand, `while` skips await; thus no signal is lost even if scheduling order changes. **Lock/Condition only serves synchronization**, not the business outcome of the task.

### How Condition Differs from CountDownLatch

A Condition can be used repeatedly with a predicate that changes over time. CountDownLatch is a countdown counter down to 0 that does not reset to its initial value; it is useful for one-shot events such as "ready" or "completed." For producer/consumer scenarios, you should usually consider BlockingQueue rather than hand-rolling every condition protocol.

## 13. Deadlock: ReentrantLock Does Not Save You from Wait Cycles

A thread can acquire multiple ReentrantLocks. If two threads acquire two locks in opposite orders, a wait cycle can occur:

~~~text
Thread A                          Thread B
--------                          --------
lock(first)                       lock(second)
  wants lock(second)                wants lock(first)
  -> waits for B                    -> waits for A
                 DEADLOCK
~~~

**Reentrancy** only allows a thread to reacquire **the same lock it already holds**. It does not resolve Thread A holding lock 1 and waiting for lock 2 held by B, while B waits for lock 1.

Prevention measures:

1. Define a **consistent lock ordering** (e.g., by immutable ID) whenever an operation must hold multiple locks.
2. Keep critical sections short; avoid I/O, uncontrolled callbacks, or waiting for other threads to finish while holding a lock.
3. Consider tryLock(timeout) if you must avoid waiting forever; **when unable to acquire all locks, release all currently held locks and retry safely**.
4. Avoid designs where Thread A holds a lock and calls join() waiting for Thread B while B needs that exact lock to finish.
5. Never use sleep/yield to "solve deadlocks": neither method releases locks, nor do they establish lock ordering.

With multiple ReentrantLocks, inspect lock owners/stack traces and wait relationships via thread dumps, ThreadMXBean, or appropriate diagnostic tools. ReentrantLock provides queue-inspection APIs, but snapshots do not replace reasoning about ordering and ownership.

## 14. Choosing Between synchronized and ReentrantLock

| Criterion | synchronized | ReentrantLock |
| --- | --- | --- |
| Usage | Language syntax, intrinsic object monitor | Lock class with explicit API |
| Lock release | Automatic on exiting synchronized | **Must call unlock() in finally** |
| Reentrant | Yes | Yes |
| Mutual exclusion and happens-before | Yes, when using the same monitor | Yes, when using the same lock |
| Immediate try-acquire | No direct try-enter | tryLock() |
| Timed wait | No timeout parameter for monitor enter | tryLock(timeout, unit) |
| Interruptible acquisition | Waiting to enter monitor does not throw InterruptedException | lockInterruptibly() |
| Condition queue | Object.wait/notify/notifyAll | Condition.await/signal/signalAll |
| Fairness configuration | No fairness parameter | ReentrantLock(true), with limitations |
| Risk of forgetting release | Lower due to language construct | Higher if finally is omitted |

**Prefer synchronized** when you only need short, readable mutual exclusion without special acquisition features. **Choose ReentrantLock** when you genuinely need tryLock, timeouts, interruptible lock acquisition, multiple separate Conditions, or explicit lock control backed by evidence.

Do not choose ReentrantLock merely because it is "faster than synchronized." The JIT, contention level, critical section length, topology, and throughput/latency requirements all affect real-world results. Run a methodical benchmark if performance is the deciding factor.

## 15. Common Real-World Mistakes and Fixes

| Mistake | Consequence | Fix |
| --- | --- | --- |
| Calling lock() with unlock outside finally | Exception/return leaves lock held | Use try/finally immediately after acquire |
| Calling unlock() even when tryLock() returns false | IllegalMonitorStateException | Only unlock if acquisition succeeded |
| Each thread creates its own new ReentrantLock | No mutual exclusion on shared variables | Share a single lock object |
| Reading shared state without using the lock protocol | Missing visibility/atomicity | Read and write under the same protocol |
| Locking check and update steps separately | Logic race between the two acquisitions | Protect the entire invariant |
| Calling lock() twice and unlock() once | Hold count remains 1, blocking other threads | Balance every acquire/release |
| Calling Condition.await() without holding the lock | IllegalMonitorStateException | Acquire lock before await and finally unlock |
| Using `if` when waiting on a condition | Spurious wakeups or interleaved scheduling can break logic | Use `while` to check the predicate |
| Calling sleep() while holding a lock | Holds lock throughout sleep, increasing contention | Move waiting outside the critical section if possible |
| Calling join()/Future.get() while holding a lock needed by the worker | Can self-deadlock | Check dependencies, release lock before waiting |
| Trusting getQueueLength()/isLocked() as a safe check before updating | Snapshot changes immediately | Use actual acquire/CAS/condition |
| Assuming fair=true means zero starvation in all cases | Scheduler and tryLock have exceptions; long waits can still occur | Define SLAs and measure in practice |
| Expecting interrupting a lock-holding worker to auto-release the lock | Not auto-released; thread must reach finally | Write cooperative cleanup and exit code |
| Using ReentrantLock to protect state across multiple JVMs | Lock is only shared among threads referencing the same object in one JVM | Coordinate at the shared data store |

### Special Note: unlock() Is Not wait/notify

**unlock()** decrements the hold count and, when it reaches 0, allows another thread to acquire the lock. It is **not Condition.signal()**. If a worker is waiting on a condition predicate, another thread's unlock does not itself act as a signal the worker can use to leave await(). You must update the predicate and issue a signal according to Condition's contract.

### Should You Call isLocked() Before lock()?

It is unnecessary and can be coordinationally wrong. **isLocked()** is only a snapshot: immediately after it returns false, another thread can acquire the lock. If you do not want to wait, use **tryLock()**. If you want to wait until acquired, call **lock()**. Choose the API based on your requirement rather than checking a snapshot and then acting.

## 16. Code Application Checklist

1. Identify **the data and invariants** being protected; all relevant access paths must use the same protocol.
2. Store ReentrantLock as a **private final** field if the lock protects an object's internal state.
3. Place **lock.lock()** immediately before **try**. Any path with a successful acquisition must reach **finally unlock()**.
4. If using **tryLock()**, enter try only when it returns true. If using **lockInterruptibly()/timed tryLock**, handle InterruptedException on the unowned path.
5. Do not hold a lock during I/O or long waits unless the invariant requires it; avoid uncontrolled callbacks inside critical sections.
6. With multiple locks, define acquisition ordering and cleanup when not all locks can be acquired.
7. With Condition, hold the lock during await/signal, guard the predicate under the same lock, and check the predicate in a **while** loop.
8. Write tests that verify invariants after workers finish via join/Future/latch; do not rely solely on logs or sleep to prove correctness.
9. If errors/timeouts/cancellations can occur, define a policy for **partial work** and business state; finally only releases the lock, it does not roll back side effects.
10. If data spans multiple JVMs/processes, a local ReentrantLock does not replace synchronization mechanisms in the shared data store.

## 17. Self-Check

**Q1.** Why shouldn't you write `lock.lock(); doWork(); lock.unlock();`?  
**Answer:** If doWork throws an exception or returns before unlock, the lock remains held. finally guarantees cleanup when exiting the scope.

**Q2.** If tryLock() returns false, should you call unlock()?  
**Answer:** No. The caller does not own the lock; unlock() may throw IllegalMonitorStateException.

**Q3.** If ReentrantLock.lock() is called twice and unlock() once, can another thread acquire the lock?  
**Answer:** Not yet; the hold count is still 1. A matching unlock is required for the remaining acquisition.

**Q4.** How does lockInterruptibly() differ from lock()?  
**Answer:** It allows aborting the wait for the lock via InterruptedException when interrupted, rather than waiting uninterruptibly under that mechanism.

**Q5.** If main calls lock.isLocked(), sees false, and immediately modifies a variable, is that safe?  
**Answer:** No. The snapshot can change before the modification; you need a successful acquisition or a proper synchronization mechanism.

**Q6.** Does Condition.await() automatically release the lock?  
**Answer:** Yes, it releases the associated lock while waiting and reacquires it before resuming per contract. The waiter must hold the lock when starting await and check the condition in a while loop.

**Q7.** If a class uses ReentrantLock to protect a counter, will an unlocked reader always see the latest value?  
**Answer:** No. The reader must participate in the appropriate synchronization/happens-before protocol.

**Q8.** When a thread holds a lock and calls Future.get() waiting for a worker that needs the same lock, what can happen?  
**Answer:** Deadlock: the calling thread does not release the lock before the worker finishes, and the worker cannot finish because it cannot acquire the lock.

**Q9.** Does a fair lock guarantee that tryLock() will never barge ahead of the queue?  
**Answer:** No. Untimed tryLock() can acquire the lock immediately even when a fair lock has other threads waiting.

**Q10.** Can you replace every `synchronized` with ReentrantLock and always improve performance?  
**Answer:** No. The two mechanisms have different trade-offs, and you must benchmark on real workloads. ReentrantLock is appropriate when you need its specific API features, not as an automatically faster choice.

## 18. Key Takeaways

**ReentrantLock** provides mutual exclusion and memory-ordering guarantees like a monitor lock, but requires explicit ownership management. **When acquisition succeeds, always unlock in finally; when acquisition fails, do not unlock.** With ordinary lock(), place try immediately after lock(). With tryLock, run try/finally only when granted the lock. With lockInterruptibly or timed tryLock, clearly separate the InterruptedException path, the failed-acquisition path, and the owned path.

Use **reentrancy** deliberately, keep **hold count** balanced, use Condition with predicates in a while loop, and consider lock ordering when multiple locks are involved. Design critical sections around **complete invariants** of your data and choose the Java API that matches your waiting, cancellation, and timeout requirements rather than relying on incidental timing.

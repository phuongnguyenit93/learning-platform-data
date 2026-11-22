# Intrinsic Lock and Monitor of Every Object in Java

## 1. Lesson Objectives

After this lesson, you will be able to:

- Explain the **intrinsic lock** (or **monitor lock**) associated with every Java object and why the lock is tied to **object identity**, not the variable name or the object's value.
- Use the three forms of **synchronized**: synchronized blocks, synchronized instance methods, and synchronized static methods; accurately identify which monitor object is locked in each case.
- Understand **mutual exclusion**, **reentrancy**, when monitors are acquired/released, and the **happens-before** relationship between unlock and lock to protect shared data.
- Distinguish **BLOCKED** (waiting for a monitor) from **WAITING/TIMED_WAITING** (waiting for a condition); understand how **Object.wait()**, **notify()**, and **notifyAll()** interact with the monitor.
- Identify bugs such as locking the wrong object, locks that do not cover invariants, exposing locks externally, holding locks while sleeping or performing I/O, and deadlocks caused by multiple monitors.
- Run Java 17+ examples and explain the results yourself without relying on random scheduling order.

This lesson covers **general Java concurrency**, based on the Java Language Specification, the Java Memory Model (JMM), and the JDK API. Spring-specific synchronization mechanisms are outside the scope of this lesson.

## 2. What is an Intrinsic Lock?

In Java's semantics, **every object, including arrays and Class objects, has a monitor associated with it**. When a thread executes synchronized on an object, it must acquire ownership of that object's monitor before entering the critical section; when leaving the critical section, it releases the corresponding monitor. The JVM may implement or optimize this mechanism in various ways; you should not assume a specific object header layout or OS-level operation solely from the language contract.

~~~java
// Syntax illustration, placed inside a Java class method:
Object lock = new Object();

synchronized (lock) {
    // Only one thread at a time owns the monitor of lock
    // to execute this code region.
}
~~~

This is a syntax illustration, **not a standalone program with main()**.

### Locks are Tied to Object Identity

Two reference variables pointing to the **same object** use the same monitor:

~~~java
Object a = new Object();
Object alias = a;

synchronized (a) {
    // Owning the exact same monitor that synchronized(alias) will require.
}
~~~

Conversely, two different objects, even with the same logical content, are still **two separate monitors**:

~~~java
Object a = new Object();
Object b = new Object();
// a != b, so synchronized(a) and synchronized(b) do not block each other.
~~~

Do not confuse **equals()** with locking: a monitor is determined by object identity (**==**), not the result of equals(), hashCode(), or string representation. If two threads intend to share a lock, they must actually hold **the same reference to the lock object**.

**A practical limitation:** the synchronized expression must evaluate to a **non-null reference**. Executing synchronized(null) throws a **NullPointerException** before entering the critical section. You cannot synchronize directly on a primitive such as int; only object references have monitors under this mechanism.

## 3. Mutual Exclusion: Same Monitor, One Owner

A monitor can be owned by **one thread** at a time. If thread A already holds the monitor of lock, thread B wanting to enter synchronized(lock) must wait until A releases it. If thread C synchronizes on a different object, C is not blocked by lock's monitor, unless it also requires another lock/resource.

This protects the **critical section**: a sequence of operations that needs to be observed as a single unit without interference from threads using the **same monitor**.

~~~text
Thread A                         Thread B
--------                         --------
synchronized(lock) {             synchronized(lock) {
  read count                       wait for lock's monitor
  count = count + 1                ...
  write count                      when A releases lock -> enter
} // release lock                  ...
                                 } // release lock
~~~

If a thread modifies count **outside** synchronized(lock), this mutual exclusion rule does not automatically prevent it. Both readers and writers of the data must follow the same protection strategy, or another compatible JMM protocol.

### Example 1: Protecting a Non-Atomic Increment

File **MonitorCounterDemo.java**:

~~~java
public class MonitorCounterDemo {
    public static void main(String[] args) throws InterruptedException {
        Object monitor = new Object();
        int[] counter = {0};

        Runnable increment = () -> {
            for (int i = 0; i < 10_000; i++) {
                synchronized (monitor) {
                    counter[0]++;
                }
            }
        };

        Thread a = new Thread(increment, "counter-a");
        Thread b = new Thread(increment, "counter-b");
        a.start();
        b.start();
        a.join();
        b.join();

        synchronized (monitor) {
            System.out.println("counter = " + counter[0]);
        }
    }
}
~~~

Compile and run with Java 17+:

~~~bash
javac -encoding UTF-8 MonitorCounterDemo.java
java MonitorCounterDemo
~~~

Stdout:

~~~text
counter = 20000
~~~

**Why is this correct?** Both workers use the **same monitor object**, so the entire read–increment–write sequence of counter[0] is inside a single critical section each time. There are no lost updates between the two workers. The two join() calls make main wait for both to finish before printing; main also reads inside synchronized(monitor) to stay consistent with the variable's protection strategy.

If you replace each synchronized(monitor) with synchronized(new Object()), each thread/iteration will lock a different object, no longer protecting the shared counter. If you only place synchronized around the final print statement, the preceding increments still lack synchronization.

### The Locked Region Must Cover the **Invariant**, Not Just a Single Statement

Suppose a requirement is "if stock is available, reserve exactly one item". The following snippet is wrong because the check and decrement are separated from a shared critical section:

~~~java
// Buggy illustration: stock is a shared variable, lock is a shared lock.
synchronized (lock) {
    if (stock <= 0) {
        return false;
    }
}
synchronized (lock) {
    stock--;
}
return true;
~~~

Between the two synchronized blocks, another thread can modify stock. If all operations on stock go through the same monitor, the check and update must be **within a single lock acquisition**:

~~~java
// Illustration inside a method returning boolean:
synchronized (lock) {
    if (stock <= 0) {
        return false;
    }
    stock--;
    return true;
}
~~~

The snippets above illustrate business logic and require appropriate variable/method declarations to compile standalone. **The goal of locking is to protect the overall correctness rule**, not just individual reads or writes.

## 4. The Three Forms of synchronized and Their Corresponding Monitors

### 4.1. synchronized on an Expression

~~~java
synchronized (lock) {
    // critical section
}
~~~

The JVM evaluates the **lock** expression to obtain an object reference, then owns that object's monitor while executing the body. When the body exits via normal completion, return, break, or an exception, the monitor is released according to synchronized semantics. Note that the expression can have side effects; it is best to lock on a clear **private final Object** field rather than an expression whose reference might change.

### 4.2. Instance synchronized Method Locks this

~~~java
public synchronized void update() {
    // Equivalent in monitor to synchronized (this) { ... }
}
~~~

A synchronized instance method acquires the **monitor of this**. Each instance has its own monitor: two instances of the same class can execute their synchronized methods concurrently.

If an object has two synchronized instance methods, two threads calling those two methods **on the same instance** will contend for the same monitor. However, if another method accesses a field without acquiring the lock, that method can still violate the synchronization strategy.

### 4.3. Static synchronized Method Locks the Class Object

~~~java
public static synchronized void updateGlobal() {
    // Monitor of the Class object of the class declaring the method.
}
~~~

A **static synchronized** method acquires the monitor of the **Class object** corresponding to the class declaring the method (for example: **Example.class**). It does **not** lock this, because static methods have no this. **Instance synchronized** and **static synchronized** typically use two different monitors; you should not expect them to mutually exclude each other.

### Example 2: Inspecting Which Monitor is Held

File **MonitorKindsDemo.java**:

~~~java
public class MonitorKindsDemo {
    synchronized void instanceWork() {
        System.out.println(
            "instance lock held = " + Thread.holdsLock(this)
        );
        System.out.println(
            "class lock held = "
                + Thread.holdsLock(MonitorKindsDemo.class)
        );
    }

    static synchronized void classWork() {
        System.out.println(
            "static class lock held = "
                + Thread.holdsLock(MonitorKindsDemo.class)
        );
    }

    public static void main(String[] args) {
        MonitorKindsDemo service = new MonitorKindsDemo();
        service.instanceWork();
        classWork();

        Object explicitLock = new Object();
        synchronized (explicitLock) {
            System.out.println(
                "explicit lock held = " + Thread.holdsLock(explicitLock)
            );
        }

        System.out.println(
            "explicit lock after exit = "
                + Thread.holdsLock(explicitLock)
        );
    }
}
~~~

~~~bash
javac -encoding UTF-8 MonitorKindsDemo.java
java MonitorKindsDemo
~~~

Stdout:

~~~text
instance lock held = true
class lock held = false
static class lock held = true
explicit lock held = true
explicit lock after exit = false
~~~

**Thread.holdsLock(Object)** returns true if the **current** thread owns the monitor of that object. It is suitable for assertions/diagnostics within a specific scope. Do not use it to query whether another thread holds a monitor or as a substitute for a synchronization protocol.

## 5. Reentrant Monitor: The Same Thread Can Re-Acquire the Lock It Holds

Java's intrinsic lock is **reentrant**. If thread A already owns the monitor of lock, A can enter another nested synchronized(lock) without blocking itself. The JVM maintains an ownership level/reentry count accordingly; each exit from synchronized decrements the hold count, and the monitor is fully released only when the thread has exited all hold levels.

### Example 3: Nested synchronized

File **ReentrantMonitorDemo.java**:

~~~java
public class ReentrantMonitorDemo {
    public static void main(String[] args) {
        Object lock = new Object();

        synchronized (lock) {
            System.out.println("outer = " + Thread.holdsLock(lock));

            synchronized (lock) {
                System.out.println("inner = " + Thread.holdsLock(lock));
            }

            System.out.println("after inner = " + Thread.holdsLock(lock));
        }

        System.out.println("after outer = " + Thread.holdsLock(lock));
    }
}
~~~

~~~bash
javac -encoding UTF-8 ReentrantMonitorDemo.java
java ReentrantMonitorDemo
~~~

Stdout:

~~~text
outer = true
inner = true
after inner = true
after outer = false
~~~

The same thread can call between synchronized methods on the same instance without causing self-deadlock simply by re-acquiring that monitor. However, **reentrancy does not prevent deadlock** when multiple threads contend for **multiple different monitors** in opposite orders.

## 6. When is a Monitor Released?

When a synchronized block or synchronized method **exits its scope** due to normal execution, return, or an exception, the corresponding monitor is automatically released. There is no explicit unlock command for an intrinsic lock.

Example:

~~~java
// Illustrative body of a Java method:
synchronized (lock) {
    if (invalid) {
        throw new IllegalStateException("invalid");
    }
} // When the exception exits synchronized, the monitor is released.
~~~

**lock** and **invalid** are hypothetical variables; this snippet does not run standalone. Releasing the monitor on exception exit **does not automatically roll back** fields modified before the exception. If you update multiple fields and fail midway, you need separate invariant design and consistency recovery.

### Example 4: Exceptions Still Release the Monitor

File **MonitorExceptionDemo.java**:

~~~java
public class MonitorExceptionDemo {
    public static void main(String[] args) throws InterruptedException {
        Object lock = new Object();

        Thread worker = new Thread(() -> {
            try {
                synchronized (lock) {
                    System.out.println("worker: acquired");
                    throw new IllegalStateException("failed");
                }
            } catch (IllegalStateException ex) {
                System.out.println("worker: caught");
            }
        }, "worker");

        worker.start();
        worker.join();

        synchronized (lock) {
            System.out.println("main: acquired");
        }
    }
}
~~~

~~~bash
javac -encoding UTF-8 MonitorExceptionDemo.java
java MonitorExceptionDemo
~~~

Stdout:

~~~text
worker: acquired
worker: caught
main: acquired
~~~

Main acquires the monitor after the worker has exited the synchronized block even though the worker threw an exception. In this example, join() also forces main to wait for the worker to finish, so stdout has a deterministic order.

## 7. Monitors in the Java Memory Model: Not Just Blocking Access

Synchronized provides two important guarantees:

**Mutual exclusion:** at any time only one thread holds the monitor in question; critical sections sharing the same monitor do not overlap.

**Memory ordering/visibility:** an **unlock** action by thread A on a monitor **happens-before** a **subsequent lock** action by thread B on the **same monitor**. By transitivity of happens-before, writes performed before A releases the monitor become visible under JMM constraints to B after it acquires the monitor.

~~~text
Thread A                               Thread B
--------                               --------
synchronized (lock) {                 synchronized (lock) {
    shared = 42;      -------- HB -->     read shared -> 42
} // monitor unlock                     } // monitor unlock
                     (assuming no other writes intervene)
~~~

This is an idealized diagram of two critical sections with the same lock and no intervening updates. The key point is the **same monitor**. If A writes under lock1 while B reads under an unrelated lock2, the mere presence of synchronized in both places does not guarantee HB for those two accesses.

### Why is Locking Only on the Writer or Reader Side Still Wrong?

~~~java
// Anti-pattern: writer locks, reader does not lock.
// shared is a regular shared field.
void writer() {
    synchronized (lock) {
        shared = 42;
    }
}

int reader() {
    return shared; // Does not participate in the same monitor protocol.
}
~~~

The snippet above illustrates methods in a class, with the lock and shared fields defined elsewhere. Without another synchronization relationship, the reader has no proper guarantee of seeing the update. Locking does not automatically broadcast signals to arbitrary unguarded reads.

**Thread.sleep()** and **Thread.yield()** do not replace monitor unlock/lock or volatile/atomic operations for memory visibility.

### Do Not Confuse Monitors with Overall Thread Safety

Even if a class locks properly during initialization, its internal mutable state still needs protection according to the update scope. A counter can use AtomicInteger; an invariant spanning multiple fields may require a monitor or a safely published immutable structure. Choose the mechanism based on the data and invariant, not just whether "synchronized is used somewhere".

## 8. How Do BLOCKED, WAITING, and TIMED_WAITING Relate?

A thread can be observed in the following states:

| Thread.State | Related Case | Meaning |
| --- | --- | --- |
| **RUNNABLE** | Running or eligible to run | Not necessarily currently on a CPU |
| **BLOCKED** | Waiting for a **monitor** to enter synchronized | Does not yet own the required monitor |
| **WAITING** | Object.wait() without timeout, join() without timeout, latch await() without timeout | Waiting for another action/event |
| **TIMED_WAITING** | Thread.sleep(), Object.wait(timeout), join(timeout) | Waiting with a time limit |
| **TERMINATED** | run() has finished | Does not indicate business success or failure |

**getState()** is a snapshot; the state can change immediately after being read. Thread.State alone is not a contract for coordinating a program.

Note: a thread waiting on **ReentrantLock.lock()** does not necessarily show BLOCKED. Thread.State.BLOCKED is specifically tied to acquiring an **intrinsic monitor**. Wait mechanisms in java.util.concurrent typically rely on park/condition mechanisms with different observable states.

## 9. Do sleep(), yield(), and Other Waits Automatically Release Monitors?

**No.** If a thread calls Thread.sleep(...) or Thread.yield() while holding a monitor, it **keeps holding the monitor** while sleeping/hinting to yield the CPU. Other threads needing that same monitor still cannot enter synchronized until the owner exits the block or uses the corresponding wait mechanism.

**CountDownLatch.await()**, **Thread.join()**, and I/O operations inside synchronized also **do not automatically release monitors owned by the caller**. They can cause the thread to wait for a long time, blocking other threads that need the monitor.

**Object.wait() is an exception with its own semantics:** when a thread holds an object's monitor and calls wait() on that exact object, the wait operation **releases the monitor of that waited-on object** while waiting, and the thread must re-acquire that monitor before continuing. Wait does not release other monitors the thread holds.

### Example 5: Waiting on a Latch Does Not Release the Monitor

File **WaitKeepsMonitorDemo.java**:

~~~java
import java.util.concurrent.CountDownLatch;

public class WaitKeepsMonitorDemo {
    public static void main(String[] args) throws InterruptedException {
        Object monitor = new Object();
        CountDownLatch entered = new CountDownLatch(1);
        CountDownLatch release = new CountDownLatch(1);

        Thread holder = new Thread(() -> {
            synchronized (monitor) {
                System.out.println("holder: acquired");
                entered.countDown();

                try {
                    release.await(); // Does not automatically release the monitor.
                } catch (InterruptedException ex) {
                    Thread.currentThread().interrupt();
                }

                System.out.println("holder: releasing");
            }
        }, "holder");

        holder.start();
        entered.await();
        release.countDown();

        synchronized (monitor) {
            System.out.println("main: acquired");
        }

        holder.join();
    }
}
~~~

~~~bash
javac -encoding UTF-8 WaitKeepsMonitorDemo.java
java WaitKeepsMonitorDemo
~~~

Stdout (without external interruption):

~~~text
holder: acquired
holder: releasing
main: acquired
~~~

Even when holder is in **WAITING** due to the latch, it can still hold the monitor. Main must wait for holder to leave synchronized. The example uses latches to create a clear waiting condition rather than guessing timing with sleep.

**Avoid deadlock designs:** if main holds the monitor and only then calls release.countDown(), while the worker needs that exact monitor to count down another latch, a circular wait can occur. Clearly map out which resources are held and which are being waited on.

## 10. Object.wait(), notify(), and notifyAll(): Monitor-Based Conditions

Every object has **wait()**, **notify()**, **notifyAll()**, and its own wait set. This protocol is for waiting on **a condition of shared state**, not for creating a payload queue or remembering past notifications.

- A thread calling **wait()** must hold the monitor of the object being waited on; it releases **that specific monitor** while waiting and must re-acquire it before proceeding. Other held monitors are not automatically released.
- A thread calling **notify()/notifyAll()** must hold the corresponding monitor. **notify()** selects an unspecified waiter; **notifyAll()** wakes up all current waiters, though they must still contend to re-acquire the monitor after the signaling thread releases the lock.
- **Spurious wakeups**, signals intended for other conditions, and state changes by other threads are why you must wait inside **while (!predicate)**, not a single **if** check.
- Updating the predicate and signaling must be protected by the **same monitor**, otherwise signals can be missed or stale state can be read. Calling wait/notify without holding the monitor throws **IllegalMonitorStateException**.

~~~java
// Illustrative snippet in a method with lock, ready, and consume:
synchronized (lock) {
    while (!ready) {
        lock.wait(); // Must handle or declare InterruptedException.
    }
    consume();
}
~~~

This is an introduction to monitor semantics. Choosing between notify and notifyAll, timed waits, interrupts, producer–consumer patterns, and multiple waiters with different predicates are practiced in depth in the lesson **Waiting on a monitor with wait() and waking with notify()/notifyAll()**. A correct implementation does not treat notify as a token, but relies on state re-checked after re-acquiring the monitor.

## 11. Designing Safe Lock Objects

### Use a private final Lock When Internal Locking is Needed

~~~java
public final class Balance {
    private final Object lock = new Object();
    private long cents;

    public Balance(long initialCents) {
        cents = initialCents;
    }

    public void deposit(long amount) {
        if (amount < 0) {
            throw new IllegalArgumentException("amount < 0");
        }
        synchronized (lock) {
            cents = Math.addExact(cents, amount);
        }
    }

    public long snapshot() {
        synchronized (lock) {
            return cents;
        }
    }
}
~~~

This is a compilable Java class without main(). A **private final lock** reduces the chance of external code accidentally acquiring the same monitor, while preserving a stable identity over the object's lifetime. The cents field is read/written under the same lock.

This example illustrates state safety within a single JVM; if the object manages transactions in a shared store or across multiple processes, synchronized does not replace proper transactions or idempotency.

### Avoid Locking Public Objects or Objects with Changing Identity

Do not arbitrarily use **String literals**, cached Integer objects, shared Class objects, or objects received from uncontrolled code as locks for internal state. Such objects may be locked by other threads for unrelated purposes, causing unexplained contention or deadlocks.

~~~java
// Anti-pattern: String literals can be interned and shared.
synchronized ("shared-lock") {
    // Should not be used as a private monitor for application data.
}
~~~

Avoid:

~~~java
// Anti-pattern: using a field whose object reference can change as a monitor.
private Object lock = new Object();

void replaceLock() {
    lock = new Object();
}
~~~

These snippets illustrate design flaws, not standalone programs. If one thread holds the old monitor while another switches to the new monitor, supposedly shared critical sections no longer exclude each other.

### Are synchronized(this) and synchronized Methods Always Wrong?

No. They are valid if **the monitor of this is an intentional part of the locking contract** and other code acquiring that lock is accounted for. However, for classes with private internal data, a **private final Object lock** usually defines clearer synchronization boundaries.

## 12. Deadlock and Lock Ordering

A reentrant monitor can still participate in a deadlock when two threads acquire two **different** monitors in opposite orders:

~~~text
Thread A                         Thread B
--------                         --------
lock(monitor1)                   lock(monitor2)
  wants lock(monitor2)             wants lock(monitor1)
  -> waits for B                   -> waits for A
             === DEADLOCK ===
~~~

If neither thread gives up its lock, both can wait forever. The JVM does not automatically release a monitor just because a thread has waited a long time. Deadlocks commonly occur when locking multiple objects during money transfers, updating multiple structures, or invoking callbacks while holding a lock.

One prevention principle is **enforcing a consistent lock acquisition order**: for example, always acquire the monitor of the object with the smaller ID first, then the larger ID, and release in reverse scope order. If two distinct objects can share the same ID, a total ordering / tie-breaking strategy is needed; do not just compare hashCode() and assume uniqueness. Other options include reducing the number of locks, avoiding external code calls while holding a lock, or using data-ownership / message-passing models.

**Do not use intentionally deadlocking programs in default runnable exercises**, as they can hang indefinitely. Use resource diagrams and diagnostic tools such as thread dumps to analyze them without turning learning examples into non-terminating processes.

## 13. Differences from ReentrantLock and Other JDK Utilities

An **intrinsic lock** is a monitor used via synchronized syntax; Java handles monitor enter/exit automatically. **java.util.concurrent.locks.ReentrantLock** is an explicit lock class with lock(), unlock(), tryLock(), and Condition support. Both are reentrant, but **they are not the same lock** even when associated with the same object holding data.

Sample usage of ReentrantLock:

~~~java
// Illustrative snippet: lock is an initialized ReentrantLock.
lock.lock();
try {
    updateSharedState();
} finally {
    lock.unlock();
}
~~~

This is not a standalone program; updateSharedState() is a hypothetical method. With ReentrantLock, you must ensure unlock() is in finally because Java does not automatically release explicit locks on scope exit. If you need timeouts or interruptible lock acquisition, appropriate APIs exist such as tryLock(timeout, unit) and lockInterruptibly(), provided the contract is used properly.

With intrinsic locks, there is no direct equivalent **try-enter synchronized with timeout** API, nor a configurable fairness parameter. A thread waiting to enter a monitor does not become the monitor owner simply because another thread calls interrupt() on it; interruption is not a command to force monitor release.

Utilities such as CountDownLatch, Semaphore, BlockingQueue, and AtomicInteger serve different purposes; choose them when the problem is waiting for events, limiting concurrency, exchanging data, or atomically updating a single variable. A monitor is usually appropriate when you need to protect a short, clear invariant of shared state.

## 14. Performance, Scope, and Diagnostics

- **Keep synchronized regions short and focused.** Do not hold a monitor across network I/O, sleep, long waits, callbacks that may re-enter the system, or heavy CPU work when not required for the invariant.
- **Do not make every method unconditionally synchronized.** If using multiple monitors, document the relationship between data and locks; if using a single overly broad monitor, you may create contention.
- **Do not assume synchronized is always slow.** The JVM has optimizations; evaluate using real application measurements and contention data rather than assumptions from older JVM versions.
- **Do not synchronize only on the writer side.** Readers and writers must follow a corresponding memory visibility strategy.
- **Monitors do not protect state across multiple JVMs/processes.** If data is shared via a DB or external service, you need a protocol at the layer managing that data.
- **Inspect thread dumps when suspecting deadlock or contention.** Stack traces, held/waited monitor lists, and BLOCKED/WAITING states help identify lock paths; combine with logs containing task IDs and timestamps for analysis.
- **Thread.State is not a business state.** A BLOCKED thread may be processing a RUNNING task; a TERMINATED thread does not by itself prove the work succeeded.

### Practical Decision Table

| Need | Mechanism to Consider | Reason |
| --- | --- | --- |
| Protect a multi-step invariant on an object within a JVM | synchronized(private final lock) | Mutual exclusion and happens-before via the same monitor |
| Single integer increment operation | AtomicInteger.incrementAndGet() | Compact atomic operation, avoids a monitor when there is no complex invariant |
| Wait for a thread to finish | Thread.join() | Waits for actual completion, no guessing with sleep |
| Wait for a one-time signal | CountDownLatch | Clearer event protocol than hand-rolled wait/notify |
| Exchange items between producer/consumer | BlockingQueue | Thread-safe waiting and data exchange via API |
| Need tryLock, timeout, interruptible acquisition | ReentrantLock | Explicit API suited to the requirements |
| Protect multi-process state | Synchronization mechanism of the shared data source | Monitors are scoped to a single JVM/classloader |

## 15. Common Misconceptions

| Misconception | Correct Understanding |
| --- | --- |
| Two objects that are equals() share the same monitor | Locking is based on identity, not equals |
| synchronized protects the entire object regardless of who reads/writes | Only code using the appropriate locking protocol receives the guarantee |
| synchronized on a field whose reference changes still uses the same lock | Changing the lock object can split the critical section in two |
| static synchronized locks all instances | It locks the Class object; instance synchronized locks this |
| A thread cannot enter the same monitor twice | Intrinsic locks are **reentrant** |
| sleep/yield/join/CountDownLatch.await release all held monitors | They do not automatically release the caller's monitors |
| notify() immediately transfers the CPU and monitor to a waiter | The notifier keeps the monitor until it releases it; waiters must contend for the lock and re-check the predicate |
| wait() and sleep() are the same | wait() on an object releases **that object's monitor** while waiting; sleep() does not |
| Object.wait() always returns when the condition is true | Spurious wakeups, timeouts, and interrupts can occur; use a while loop to check the predicate |
| BLOCKED covers all kinds of waiting | BLOCKED specifically describes waiting to enter an intrinsic monitor |
| synchronized only prevents two threads from running at the same time | Monitor unlock/lock also has memory happens-before semantics |
| A critical section split into two synchronized blocks is still atomic | Another thread can interleave in between; the lock must be held across the entire decision |
| Monitors automatically prevent deadlocks | Two or more monitors can form a circular wait |
| Every object monitor is an application-wide singleton lock | Each object's monitor has its own identity and scope |

## 16. Self-Check Questions

**Q1.** If two variables a and b point to the same object, do synchronized(a) and synchronized(b) mutually exclude each other?  
**Answer:** Yes. Both expressions require the same monitor because the object identity is the same.

**Q2.** Do two different instances calling an instance synchronized method of the same class necessarily block each other?  
**Answer:** No. Each instance has its own monitor, unless the code inside also uses a shared monitor.

**Q3.** Which lock does a static synchronized method acquire?  
**Answer:** The monitor of the Class object of the class declaring the method, for example Example.class.

**Q4.** Why is the counter increment in MonitorCounterDemo correct?  
**Answer:** Both workers lock the same monitor across the entire read–modify–write, so no updates are lost; join waits for completion before main prints.

**Q5.** When a thread holds a monitor and calls Thread.sleep(100), can another thread enter synchronized on the same monitor?  
**Answer:** No, not until the owner releases the monitor. Sleeping does not mean releasing the lock.

**Q6.** Why must wait() be placed inside a while loop?  
**Answer:** Spurious wakeups, multiple waiters competing for the condition, or condition changes before re-acquiring the monitor can occur; the predicate must be re-checked.

**Q7.** Does notifyAll() cause all waiters to run simultaneously inside the critical section?  
**Answer:** No. They must still re-acquire the monitor, and only one thread can hold the monitor at any given time.

**Q8.** Can you resolve a deadlock by calling interrupt() on a thread that is BLOCKED waiting for a monitor?  
**Answer:** You should not rely on interrupt as a mechanism to break an intrinsic monitor deadlock. Designing lock ordering and avoiding circular waits is the primary prevention.

**Q9.** If a writer synchronizes on lock1 while a reader synchronizes on a different lock2, is visibility guaranteed?  
**Answer:** It cannot be inferred from those two synchronized blocks. You must use the same happens-before protocol or another appropriate synchronization form.

**Q10.** Will a synchronized block that exits via an exception hold the monitor forever?  
**Answer:** No. Java automatically releases the monitor when exiting synchronized due to an exception; however, partial side effects are not automatically rolled back.

## 17. Conclusion

An **intrinsic lock** is monitor ownership associated with an object. synchronized uses that monitor to **exclude concurrent access** and establish **happens-before** between matching lock acquisitions. Instance synchronized locks this; static synchronized locks the Class object; synchronized(expression) locks the object that the expression evaluates to.

When designing for concurrency, identify **which data is protected by which monitor**, preserve lock **identity**, cover the **entire invariant**, avoid holding locks during long waits, and use **wait/notifyAll with a predicate in a while loop** when waiting on a monitor condition. For other problems, choose the appropriate JDK primitive instead of making every operation synchronized.

# Monitor Lock/Unlock Rules in the Java Memory Model

> **Scope:** ownership rules, entering/exiting an intrinsic monitor, mutual exclusion, and *happens-before* guarantees for lock/unlock in **Java SE/JVM**. This lesson focuses on the Java Memory Model (JMM), `synchronized`, and `Object.wait/notify`. Spring-specific mechanisms are covered separately.

## 1. Learning Objectives

After studying this lesson, you should be able to answer:

- Which object is a **monitor** associated with? How do the different forms of `synchronized` acquire and release a monitor?
- How are **one thread holding a monitor at a time**, reentrancy, normal/exception release timing, and other threads waiting understood?
- What does the formal rule **an unlock on monitor m *synchronizes-with* all subsequent locks on the same monitor m** mean?
- Why does that rule provide **visibility/ordering** through the *happens-before* relationship, in addition to preventing two threads from entering the critical section together?
- How do you use the **same monitor** to protect data fields, invariants, a read-modify-write operation, and a wait/notify protocol?
- What are the limitations of `synchronized`: no fixed lock-granting order, does not automatically protect operations outside the lock, and does not automatically make a sequence of multiple calls atomic.

**Key takeaway:** `synchronized` provides **two kinds of guarantees** when used consistently: (1) mutual exclusion within the critical section on the same monitor and (2) a memory relationship between an **unlock** and a **subsequent lock on the same monitor**. Correct functionality requires both when threads exchange mutable data.

## 2. What Is an Intrinsic Monitor?

Every Java object has a monitor used for intrinsic synchronization (intrinsic lock). To enter a `synchronized (monitor) { ... }` block, a thread must acquire **ownership of the monitor** of the **exact object referenced by the `monitor` expression** at that time.

- If the monitor is not held by another thread, the thread can enter the critical section.
- If another thread is holding it, a thread contending for the monitor must wait; the observable Java state is `Thread.State.BLOCKED`.
- At any given time, only **one thread** can own each monitor, though that same thread can re-enter the monitor multiple times (*reentrant*).
- When leaving the synchronized region, the ownership count is decremented accordingly; the monitor only becomes available to other threads when the ownership count returns to 0.
- A monitor is a property of **object identity**, not variable names, method names, or identical source text of the lock expression.

Instance-level locking example:

```java
final class Inventory {
    private final Object guard = new Object();
    private int stock = 10;

    void sellOne() {
        synchronized (guard) {
            if (stock > 0) {
                stock--;
            }
        }
    }

    int remaining() {
        synchronized (guard) {
            return stock;
        }
    }
}
```

This is a standalone class that can be compiled when placed in `Inventory.java` (a non-public class). If all access paths to `stock` go through `guard`, a sale and a snapshot read cannot interleave arbitrarily *inside* the critical section. With multiple threads calling `sellOne()`, the quantity will not be oversold into negative values due to two threads simultaneously observing `stock > 0` before decrementing. Calls can still arrive in any schedule; `synchronized` does not promise the order in which callers are served.

### Three Common Forms of synchronized

| Java Form | Actual Monitor Used | Contention Scope |
|---|---|---|
| `synchronized (lockObject) { ... }` | Object referenced by `lockObject` | All synchronized regions using the **same object** |
| `synchronized void method() { ... }` in an instance | `this` | Other synchronized instance methods on the **same instance**, or `synchronized(this)` |
| `static synchronized void method() { ... }` | The corresponding `SomeClass.class` object | Static synchronized methods on the same Class object |

An instance synchronized method on object A **does not share a monitor** with the same method on object B. An instance synchronized method also **does not use the class monitor** unless the programmer explicitly uses `synchronized (SomeClass.class)`.

`synchronized` is a language construct: entering a block can correspond to `monitorenter` and exiting to `monitorexit` in bytecode; instance/static synchronized methods can be represented by the `ACC_SYNCHRONIZED` flag, with the JVM enforcing the corresponding semantics. There is no need—and no way—to manually call an `unlock()` method for an intrinsic monitor. A `synchronized` block automatically releases when control leaves the block, including via an exception; this differs from explicit locks that require `finally { lock.unlock(); }`.

## 3. Mutual Exclusion and Reentrancy

### Mutual Exclusion Prevents Interleaving Inside the Same Critical Section

Suppose two threads both call:

```java
synchronized (guard) {
    balance = balance + 100;
}
```

The snippet above is merely an **illustration inside a class**, where `guard` and `balance` have already been declared. One thread's read–compute–write cannot be interleaved inside the synchronized region by another thread also trying to enter **the same `guard`**. Provided all updates/reads needing protection adhere to that monitor, a logical addition will not suffer lost updates like an unlocked `balance += 100`.

However, a monitor **does not prevent** code that does not use `guard` from accessing the variable directly. If another method reads/writes `balance` outside the lock without a suitable independent HB mechanism, a data race or invariant violation can still occur.

### The Same Thread Can Re-enter a Monitor (Reentrant)

`synchronized` allows a thread that already holds a monitor to call another method that also requires **that same monitor** without deadlocking itself:

```java
final class ReentrantExample {
    private int count;

    synchronized void outer() {
        inner(); // outer already holds the monitor this
    }

    synchronized void inner() {
        count++;
    }

    synchronized int getCount() {
        return count;
    }
}
```

This is a standalone class that can be saved as `ReentrantExample.java`. The thread calling `outer()` acquires the `this` monitor, `inner()` re-enters that exact monitor, and then both scopes end and ownership is released accordingly. **Reentrancy does not mean multiple threads can simultaneously own the monitor**: it is still one thread with a reentrant depth greater than one.

When using nested monitors, pay special attention to the **acquisition order of different monitors**. Reentrancy on the same monitor does not solve a deadlock caused by A holding monitor X waiting for Y, while B holds Y waiting for X.

## 4. The Lock/Unlock Rule in the JMM

This is the **formal rule in JLS `17.4.4**:

> An **unlock** action on monitor `m` *synchronizes-with* all subsequent **lock** actions on the same `m`; "subsequent" is defined in the **synchronization order**.

Note the three components of this statement:

1. **`m` must be the same monitor/object**. Unlocking `leftLock` does not automatically create a *synchronizes-with* edge for a lock on `rightLock`.
2. The rule applies between **releasing and acquiring a monitor**, not automatically between arbitrary statements occurring in two threads.
3. **Synchronization order** is a total order of synchronization actions in an execution that is consistent with program order within each thread. It is a formal JMM concept, not a promise about FIFO, fairness, or which thread runs first in practice.

In the JMM:

- **Program order** places before–after actions within the same thread into the *happens-before* relation.
- **Synchronizes-with** creates cross-thread edges, such as unlock→subsequent lock on the same monitor.
- **Happens-before (HB)** includes program order and synchronizes-with, and takes the **transitive** closure.

Thus we have the diagram:

```text
Thread A                          Thread B
--------------------------------  --------------------------------
synchronized (m) {                 synchronized (m) {
    sharedData = 42;                  int seen = sharedData;
} // unlock(m)                    } // unlock(m)
   |                                   ^
   +--- synchronizes-with ------------+
        lock(m) after unlock(m)

Write sharedData = 42  --program order--> unlock(m)
unlock(m)              --synchronizes-with--> B's lock(m)
B's lock(m)            --program order--> read sharedData
=> A's write happens-before B's read (if B acquires the lock after A releases it).
```

In the example above, you cannot deduce that B will always read 42 merely from the fact that two threads were created. **If B enters the critical section before A**, B can read the old value under a valid execution order. What is guaranteed is: when B's monitor acquisition occurs **after** A's unlock in synchronization order, A's writes before unlock are published under HB to operations after B's lock, assuming no other valid updates alter the result.

### Concrete Example: Passing Data Under the Same Monitor

```java
final class SharedMessage {
    private final Object monitor = new Object();
    private String message;

    void publish(String value) {
        synchronized (monitor) {
            message = value;
        } // release monitor
    }

    String snapshot() {
        synchronized (monitor) { // acquire same monitor
            return message;
        }
    }
}
```

This is a standalone class that can be placed in `SharedMessage.java`. If `snapshot()` acquires the monitor after `publish()` has released it, the change to `message` before unlock has an HB relationship with the read in `snapshot()`. **However**, a caller invoking `snapshot()` before any publish can receive `null`, and multiple publishes can produce different values depending on execution order. If the requirement is "the consumer must wait for a message," you need a predicate and `wait/notify` (later section), or an appropriate tool such as `BlockingQueue`.

### "Release/Acquire" Is Not a Manual Cache Flush Instruction

Describing this as "unlock flushes all caches, lock reloads all of RAM" is an **incorrect or overly crude** explanation. The JMM is an **observation/ordering contract** for an execution; the JVM/JIT/CPU may use barriers or other mechanisms to uphold the contract on each platform. Java developers should rely on HB and atomicity, not on an assumed physical cache diagram.

Worth remembering: **mutual exclusion** prevents threads using the same monitor from executing protected code simultaneously; **HB** ensures writes before unlock are properly observed by subsequent locks. The two effects complement each other. If a thread only reads without holding the same lock, the monitor alone does not create an HB edge from the unlock to that read.

## 5. When Do Lock and Unlock Actually Happen?

### Entering/Exiting a synchronized Block

```java
synchronized (m) {        // attempt to acquire monitor m
    doCriticalWork();
}                         // release monitor m when exiting the block
```

This is illustrative code with `m` and `doCriticalWork()` defined in the enclosing class. If `doCriticalWork()` throws an exception, Java still guarantees releasing the monitor ownership corresponding to that block. If `m == null`, attempting to enter the block throws `NullPointerException`: no valid monitor was acquired.

### synchronized Method

```java
public synchronized void update() {
    state++;
}
```

This is an illustrative method on an instance with a `state` field. Acquires monitor `this` before executing the body; unlocks when the method finishes. For `static synchronized`, the monitor is the `Class` object. Making a call `this.update()` while already inside `synchronized(this)` is an example of **reentrance**.

### Exceptions, return, break

You do not need to write `finally` to release an intrinsic monitor when `return` or an exception exits `synchronized`. However, **business rollback logic does not happen automatically**: if code modifies two fields and throws an exception in between, the monitor is released, but the data may remain in an intermediate state. You must design invariants, exception safety, or commit/rollback logic yourself if needed.

### While Waiting to Acquire a Monitor

Another thread holds `m` → a contender enters `synchronized(m)` → it may be in `Thread.State.BLOCKED`. There is no contract that contenders acquire the lock in the order they started waiting. `Thread.interrupt()` **does not cause a monitor entry to throw `InterruptedException`**, and does not turn entering `synchronized` into an interruptible lock acquisition.

**Do not conflate different waiting states**: a thread waiting on `ReentrantLock.lock()` typically uses a parking mechanism and may be observed as `WAITING`; that is not the monitor `BLOCKED` of `Thread.State`. An explicit lock has equivalent memory-effect contracts for acquire/release under the `Lock` API, but it is a different primitive from the `synchronized` monitor.

## 6. One Stable Lock Object for the Same Invariant

A design principle: **all accesses to shared state forming the same invariant must be coordinated by the same synchronization protocol.**

Example of two fields that must stay consistent:

```java
final class Account {
    private final Object guard = new Object();
    private long balance;
    private long version;

    Account(long initial) {
        balance = initial;
    }

    void deposit(long amount) {
        if (amount <= 0) throw new IllegalArgumentException();
        synchronized (guard) {
            balance += amount;
            version++;
        }
    }

    String snapshot() {
        synchronized (guard) {
            return "balance=" + balance + ", version=" + version;
        }
    }
}
```

This is a standalone compilable class in `Account.java`. In the example, `balance` and `version` are updated inside the same critical section, and `snapshot()` reads both under the same monitor so it never observes a half-completed update. The code only illustrates locking/invariants and **does not** include `long` overflow handling; real financial code must add overflow checks and exact monetary rules.

### Monitor Choices to Avoid Without Good Reason

- `synchronized (new Object())` inside each call creates a **new monitor** every time, providing no exclusion between two calls.
- Using different locks for writer and reader does not establish the same HB rule from unlock to the reader's lock.
- Using a mutable lock reference (`lock = anotherObject`) causes threads to synchronize on different objects.
- `synchronized (this)` in a public API allows external callers to hold `this` and stall internal operations; a `private final Object guard` monitor is usually easier to control.
- Synchronizing on string literals/interned strings, boxed/cached wrappers, or an object that can be unintentionally shared creates contention and risk of interference with other code.
- A single global lock protecting unrelated state can reduce concurrency; conversely, using too many locks for one invariant easily breaks atomicity.

**Note:** `final` on the `guard` reference variable only guarantees it is not reassigned in normal code flow; `final` does not make other mutable fields thread-safe on its own. It is the consistent use of the same monitor and safe publication of the enclosing object that form the foundation of a correct design.

## 7. Deterministic Java 17+ Experiment

The program below demonstrates **mutual exclusion** when two workers increment the same counter and **visibility/ordering** when a producer notifies a consumer via a monitor. The output does not depend on which worker runs first.

Create **`MonitorRulesDemo.java`**:

```java
public final class MonitorRulesDemo {
    private static final class Counter {
        private int count;

        synchronized void increment() {
            count++;
        }

        synchronized int get() {
            return count;
        }
    }

    private static final class Mailbox {
        private final Object monitor = new Object();
        private boolean ready;
        private String message;

        void publish(String text) {
            synchronized (monitor) {
                message = text;
                ready = true;
                monitor.notifyAll();
            }
        }

        String awaitMessage() throws InterruptedException {
            synchronized (monitor) {
                while (!ready) {
                    monitor.wait();
                }
                return message;
            }
        }
    }

    public static void main(String[] args) throws InterruptedException {
        Counter counter = new Counter();

        Runnable work = () -> {
            for (int i = 0; i < 10_000; i++) {
                counter.increment();
            }
        };

        Thread first = new Thread(work, "first");
        Thread second = new Thread(work, "second");
        first.start();
        second.start();
        first.join();
        second.join();
        System.out.println("count=" + counter.get());

        Mailbox mailbox = new Mailbox();
        Thread receiver = new Thread(() -> {
            try {
                System.out.println("message=" + mailbox.awaitMessage());
            } catch (InterruptedException e) {
                Thread.currentThread().interrupt();
            }
        }, "receiver");

        receiver.start();
        mailbox.publish("ready");
        receiver.join();
        System.out.println("receiverFinished=" + !receiver.isAlive());
    }
}
```

From the directory containing `MonitorRulesDemo.java`, compile and run:

```bash
javac --release 17 MonitorRulesDemo.java
java MonitorRulesDemo
```

**Verified stdout:**

```text
count=20000
message=ready
receiverFinished=true
```

**Analysis of why no updates are lost:**

1. Both workers each call `increment()` 10,000 times; the method is an instance `synchronized` method, so **both acquire the monitor of the same `counter` object**.
2. `count++` inside the monitor executes completely for each call; no other worker can enter a synchronized method on the same monitor in between.
3. `first.join()` and `second.join()` wait for both workers to finish. When `main` calls `get()` afterward, no increment tasks are still running; the exact result is 20,000. `join()` also has its own HB relation for thread termination, but **join does not replace locking to protect the increments**.
4. If you remove `synchronized` from `increment()` while keeping `join()`, the result can lose updates because the two workers raced before `main` finished waiting.

**Analysis of why the message is always "ready":**

1. `publish()` holds `mailbox.monitor`, writes `message`, then sets `ready = true`.
2. `notifyAll()` only notifies; the monitor remains held by the producer until it exits `synchronized`.
3. `awaitMessage()` holds the **same monitor** and checks `ready` in a `while` loop. If data is not ready yet, `wait()` releases the monitor and waits. Upon waking up, it **must reacquire the monitor** before returning from `wait()` and re-checking `ready`.
4. The case where the producer publishes **before** the receiver enters `wait()` is also handled correctly: the receiver reads `ready == true` under the monitor and does not wait. Thanks to the predicate, there is no "missed notification" as happens when using `notify` without state.
5. The producer's writes to `message/ready` before unlock are guaranteed HB with the consumer's subsequent lock/reacquire; the consumer reads the data inside the critical section with proper visibility.
6. `receiver.join()` ensures the `message=ready` line has executed before the final line and `receiverFinished=true`.

This code intentionally uses **platform threads** and runs cleanly on Java 17+. The scheduler may choose any internal ordering, but the output above is guaranteed when the program completes normally. In production, data-passing structures like `BlockingQueue` are usually more convenient than managing wait sets manually, but this lesson uses monitors to explain Java's semantics.

## 8. How Do `wait()` and `notify()` Change Ownership?

A common misconception: `Object.wait()` **releases the monitor**, whereas `Object.notify()/notifyAll()` **does not release the monitor by itself**.

### Proper Waiting Procedure

When a thread holds the monitor of object `m` and calls `m.wait()`:

1. The thread **must own** monitor `m`; otherwise, Java throws `IllegalMonitorStateException`.
2. The thread is placed into `m`'s wait set, **releases all ownership levels on monitor `m` itself**, and waits to be awakened.
3. An event such as `notify`/`notifyAll`, an interrupt, a timeout (in timed overloads), or a spurious wakeup can end the waiting phase.
4. The thread must **reacquire monitor `m`** before `wait()` actually returns normally or throws `InterruptedException`; if the monitor is still busy, it may be `BLOCKED` while reacquiring.
5. Because the condition may have changed, **check the predicate in a `while` loop** every time execution resumes.

`wait()` **does not release any other monitors** the thread also holds. Therefore, nesting multiple `synchronized` blocks and calling `wait` on one object while still holding another can cause deadlock.

### Ownership Ordering Diagram

```text
Thread consumer                          Thread producer
---------------------------------------  -----------------------------
lock(m)
while (!ready):
    wait(m): release(m)
            [waiting]                  lock(m)
                                       message = "ready"
                                       ready = true
                                       notifyAll(m)
                                       ... still holds m ...
                                       unlock(m)
    [reacquire(m) succeeded]
    read message
unlock(m)
```

That the consumer reads the producer's published writes after reacquiring is a consequence of HB through the monitor (along with the related synchronization rules). **`notifyAll()` by itself does not immediately transfer ownership**. If the producer calls `notifyAll()` and then does lengthy work inside the monitor, the awakened waiter still has to wait.

Common error example:

```java
// INCORRECT ILLUSTRATION: must not call wait/notify without owning the monitor.
Object m = new Object();
m.notifyAll(); // IllegalMonitorStateException
m.wait();      // IllegalMonitorStateException
```

These are illustrative statements not in a complete runnable program; `m.wait()` must also be placed in a method context that declares or handles `InterruptedException`. To use them correctly: call `m.wait()` and `m.notifyAll()` **inside `synchronized(m)`**, and only wait when the predicate is not yet satisfied.

### Difference from sleep

`Thread.sleep(...)` does not release any monitors the thread holds; `sleep` also does not create a *synchronizes-with* edge merely because time passes. If you want to wait for a condition tied to a monitor, use `wait` with a predicate or an appropriate higher-level concurrency primitive; do not substitute `sleep`/`yield` to "wait for another thread to finish."

## 9. Why Can Single-Operation Locking Still Be Insufficient?

### Check-Then-Act Must Be Inside **One** Critical Section

Incorrect business atomicity:

```java
// Suppose getBalance()/withdraw() are each synchronized
if (account.getBalance() >= 100) {
    account.withdraw(100);
}
```

This is an illustrative snippet and `account` has a hypothetical API. Even though each method locks properly on its own, **between `getBalance()` and `withdraw()` the monitor is released**. Two threads can both see sufficient balance and then both withdraw. The right approach is a single method on `account` that performs **check + update** under the same monitor:

```java
synchronized boolean withdrawIfEnough(long amount) {
    if (amount < 0 || balance < amount) return false;
    balance -= amount;
    return true;
}
```

The snippet above is a method of a class with a `long balance` field. The `return` statement exits the synchronized method and releases the monitor. In a real system you must also define overflow handling, transactions, persistence, and access control, but as far as the Java monitor is concerned, the check and deduction here belong to the same critical section.

### Two Different Locks Do Not Coordinate via the Monitor Rule

```java
// INCORRECT illustration: two different monitors for the same sharedValue.
private final Object writerLock = new Object();
private final Object readerLock = new Object();
private int sharedValue;

void set(int v) {
    synchronized (writerLock) { sharedValue = v; }
}

int get() {
    synchronized (readerLock) { return sharedValue; }
}
```

These are illustrative members of a class. `writerLock` and `readerLock` are different objects, so the first unlock **does not** synchronize-with the second lock via the monitor rule. Moreover, writer and reader can enter their "protected" regions simultaneously. Fix this by using **a single monitor** for all conflicting accesses, or another protocol with proven equivalent memory semantics.

### volatile Differs from a Monitor

`volatile` has a *synchronizes-with* rule for **write → read** of the same volatile variable in the JMM. However, `volatile int count` still does not make `count++` atomic; it is a read–modify–write. `synchronized` provides exclusion via a monitor and HB via unlock→lock; `AtomicInteger.incrementAndGet()` is a dedicated atomic operation. Choose based on the **invariant**:

| Requirement | Usually Suitable Tool |
|---|---|
| Multiple read/write steps must be atomic together | `synchronized` or `Lock` protecting the whole group |
| Independent atomic updates to an integer | `AtomicInteger` / `AtomicLong` |
| Publishing a flag and data with a proper visibility protocol | `volatile` when sufficient, or a monitor/queue |
| Consumer waiting for producer to hand off items | `BlockingQueue`, `Condition`, or `wait/notify` with a proper predicate |
| Multiple fields must be consistent in a snapshot | Same monitor/lock or immutable data design |

`ReentrantLock` in `java.util.concurrent.locks.Lock` specifies memory synchronization effects for lock/unlock equivalent to monitor lock/unlock; it has a different API such as timeouts and interruptible acquisition. **Do not treat `Lock` and `synchronized` as the same monitor object**. Switching to another primitive requires replacing the acquire/release protocol consistently.

## 10. Visibility, Liveness, and Fairness Are Not the Same Thing

The HB rule answers: **once accesses are ordered appropriately, which writes must be visible?** It **does not answer** whether a thread is guaranteed CPU time or will acquire the monitor before a competitor.

- **Safety:** data and invariants are not corrupted, e.g., a counter does not lose updates.
- **Visibility:** updates published via the same monitor are observed according to HB.
- **Liveness:** a thread is able to make progress and complete, without indefinite deadlock/starvation.
- **Fairness:** whether the policy for distributing progress opportunities favors certain threads.

`synchronized` guarantees mutual exclusion and ordering; **it makes no FIFO/fairness guarantee** among contenders. Holding a monitor while performing slow I/O can reduce throughput and force other threads to wait long periods. Acquiring monitor A then B in one thread, but B then A in another, can cause **deadlock**. These liveness bugs require designing acquisition order, shrinking critical sections, using timeouts where feasible, and measuring under realistic load; HB does not fix them automatically.

A basic deadlock-avoidance pattern when two monitors must be acquired is a **global ordering convention** for all callers. However, if the design does not require holding two monitors simultaneously, switching to a single short critical section or message passing is usually easier to verify.

## 11. Why Do Lock/Unlock Still Matter for Non-volatile Data?

The counter example in `MonitorRulesDemo` uses a plain `private int count`, **not volatile**. This is valid if all accesses from multiple threads follow the counter's `this` lock:

- The writer calls `increment()`, acquires the monitor, updates `count`, and releases the monitor.
- The reader calls `get()` and acquires the same monitor after that unlock.
- The sequence "write count → unlock → lock → read count" is connected by HB, so `count` does not need to be declared `volatile` just to update/read under that protocol.
- If the reader drops the lock and just does `return count;`, it can no longer claim memory visibility guarantees **from the monitor rule** for that read. Other HB edges may sometimes still exist (such as `join` in the example), but library code should not implicitly depend on such a specific caller situation.

Similarly, using `private final Object guard` does not make the data inside immutable. "Final lock" and "lock-protected mutable data" are two distinct roles: `final` keeps the monitor object's identity stable, while mutual exclusion/HB come from the actual acquire/release actions.

Also distinguish **atomicity of a single access** from **atomicity of a multi-step behavior**. Reading/writing a reference or `int` is atomic as an individual access under the JMM, but that does not mean check-then-act is protected. Even when reading a value "without tearing," the read can be stale or interleave with other updates if HB is missing.

## 12. Observing Monitor Rules in Practice

### Thread Dumps

While a Java application is running, you can use:

```bash
jcmd <PID> Thread.print -l
```

Replace `<PID>` with the actual process ID. Inspect stack traces and monitor info to distinguish:

- `BLOCKED (on object monitor)` threads are waiting to acquire an intrinsic monitor (usually `synchronized`).
- `WAITING (on object monitor)` threads at `Object.wait()` are in the wait set, **having released the monitor being waited on**.
- `WAITING (parking)` threads at `LockSupport.park()` may be waiting on a `ReentrantLock`, queue, or other synchronizer; not necessarily `synchronized`.
- `RUNNABLE` threads are not necessarily using CPU right now; they may be waiting on OS scheduling.

A thread dump is only a **point-in-time snapshot**. You cannot infer contention duration, state-transition frequency, or invariant logic from a single `Thread.State` line.

### Java Flight Recorder (JFR)

For a workload long enough to generate events:

```bash
jcmd <PID> JFR.start name=monitor-profile settings=profile duration=60s filename=monitor.jfr
jfr summary monitor.jfr
jfr print --events jdk.JavaMonitorEnter,jdk.JavaMonitorWait monitor.jfr
```

`jdk.JavaMonitorEnter` helps inspect monitor contention durations; `jdk.JavaMonitorWait` helps inspect monitor wait operations. Pay attention to thresholds and event settings: **seeing no events does not prove there is no lock contention**. Combine with thread dumps, CPU profiling, and application metrics; very short example runs often do not produce useful recordings.

### ThreadMXBean

`java.lang.management.ThreadMXBean` can provide blocked/waited counts and times. To measure contention time, check `isThreadContentionMonitoringSupported()` first before considering `setThreadContentionMonitoringEnabled(true)`, as monitoring has overhead and may be restricted by the JVM. `getBlockedCount()/getBlockedTime()` are tied to **monitor contention**, not total wait time across all explicit locks or OS context-switch counts. Track metrics over time rather than concluding from one snapshot.

### Systematic Monitor Debugging Procedure

1. Identify the **state/invariant** that is broken (lost update, stale read, inconsistent snapshot, hang).
2. Record **every read/write location** of the state and the exact object used for locking.
3. Trace the required HB path: on which monitor does the writer unlock? Does the reader acquire the **same monitor** afterward? Is there another primitive providing valid HB?
4. Distinguish **atomicity bugs** (two operations interleaving) from **visibility bugs** (missing HB observation) and **liveness bugs** (no progress).
5. Reproduce using `CountDownLatch`/barriers in tests when needed; use invariant assertions rather than `Thread.sleep()`/`yield()` to "fix" a race.
6. After fixing, verify correctness across multiple schedules/loads, and only then measure throughput/latency/lock contention to decide lock granularity.

## 13. Misconceptions to Avoid

1. **"`synchronized` is only a mutex, unrelated to visibility."** False: unlock and subsequent lock on the same monitor have a *synchronizes-with* edge, establishing HB.
2. **"Releasing a monitor makes all threads see the data immediately, even without acquiring the lock."** There is no such guarantee **from the monitor rule alone**; a proper HB path is required.
3. **"Having both methods synchronized is enough."** Not enough if the two methods belong to **two different instances** or if check-then-act steps need to be atomic across multiple calls.
4. **"`static synchronized` locks each instance."** False: it uses the `Class` monitor of that class.
5. **"`synchronized(lock)` and `synchronized(new Object())` are the same."** False: object identity determines whether threads contend on the same monitor.
6. **"An exception leaves the monitor held forever."** For `synchronized` blocks/methods, the JVM releases it when the scope exits; however, data is not automatically rolled back.
7. **"`notifyAll` immediately hands the lock to a waiter."** False: the caller retains the monitor until unlock; the waiter must reacquire it.
8. **"`wait` releases all locks the thread holds."** False: it only releases the monitor of the object on which `wait` is called, not other monitors.
9. **"`Thread.sleep` releases the monitor."** False: sleeping does not release locks.
10. **"If there is HB, B always runs after A in wall-clock time."** HB is an ordering/visibility constraint on actions, not a guarantee that the scheduler gives B CPU time after a specific duration.
11. **"`volatile++` is equivalent to incrementing under a monitor."** False: individual volatile reads/writes do not make read-modify-write atomic.
12. **"Monitors grant access fairly in FIFO order."** `synchronized` has no FIFO/fairness guarantee.
13. **"If `synchronized` adds overhead, remove it and use `join` to read afterward."** `join` provides HB for thread completion, but does not prevent workers from racing while updating concurrently during execution.
14. **"A Java lock always executes a full-cache flush instruction."** Not an accurate description of the JMM contract; reason using formal HB relations.

## 14. Self-Check Exercises with Answers

**Q1.** A writes `x=17` inside `synchronized(m)` and exits the block. B later enters `synchronized(m)` and reads `x`, with no other competing writes. Can B see the old value because `x` is not `volatile`?  
**Answer:** No, provided B's lock comes after A's unlock on the same `m` in synchronization order. The program-order + unlock→lock chain establishes HB.

**Q2.** A releases monitor `m1`; B acquires monitor `m2` and reads the same `x`. Can the monitor rule above be cited to guarantee visibility?  
**Answer:** No. This unlock→lock edge requires the same monitor. **Other** HB edges might exist, but visibility cannot be inferred solely from two different monitors.

**Q3.** A calls an instance synchronized method on `obj1`, and B calls the same method on `obj2`. Are the two calls mutually exclusive?  
**Answer:** No, because the monitors are `obj1` and `obj2` respectively, unless they internally coordinate on another shared monitor.

**Q4.** Why is `count++` completely inside `synchronized(guard)` along with all related accesses correct, whereas two synchronized methods `get()` and `set()` called back-to-back may be insufficient for a transaction?  
**Answer:** The increment is protected as a single critical section; a get-then-set pair involves two acquire/release cycles, allowing another thread to interleave in between.

**Q5.** A thread inside `synchronized(m)` calls `m.wait()`. Does it still hold `m` while waiting? What happens when `wait` returns?  
**Answer:** It temporarily releases monitor `m` when entering the wait set, and must reacquire `m` before `wait` completes. Other monitors it holds are not released automatically.

**Q6.** A holds the monitor and calls `notifyAll()`. Does B, which is waiting on the condition, run immediately inside the critical section?  
**Answer:** No. B must still be scheduled and reacquire the monitor after A releases it. Use `while` to re-check the condition.

**Q7.** Can Thread A enter `synchronized(this)` when it already holds the `this` monitor via another synchronized method?  
**Answer:** Yes, because intrinsic monitors are reentrant. Thread B, meanwhile, must wait until A releases all ownership levels.

**Q8.** Does calling `Thread.join()` after two workers perform unsynchronized `counter++` eliminate lost updates?  
**Answer:** No. `join` confirms they have finished and creates HB for `main`'s subsequent read; the lost updates can already have occurred earlier between the two workers.

**Q9.** Why should you avoid using a string literal as a private monitor?  
**Answer:** Literals can be interned and shared across unrelated parts of the codebase; accidentally sharing a lock causes unexpected contention or deadlock. Usually you should use `private final Object guard = new Object()`.

**Q10.** One thread holds a monitor for too long, leaving many other threads `BLOCKED`. Is the Java Memory Model violated?  
**Answer:** Not necessarily. Mutex/HB may still be intact, but the design has a **liveness/performance issue**. Investigate lock hold times, I/O inside critical sections, and lock acquisition order.

## Official References

- [JLS Java SE 17 `17 — Threads and Locks](https://docs.oracle.com/javase/specs/jls/se17/html/jls-17.html): especially `17.1` on synchronization, `17.4.4` on synchronization order, and `17.4.5` on happens-before.
- [JLS Java SE 17 `14.19 — The synchronized Statement](https://docs.oracle.com/javase/specs/jls/se17/html/jls-14.html#jls-14.19): entering/exiting a synchronized statement and abrupt completion handling.
- [JLS Java SE 17 `8.4.3.6 — synchronized Methods](https://docs.oracle.com/javase/specs/jls/se17/html/jls-8.html#jls-8.4.3.6): instance/static methods and associated monitors.
- [Java SE 17 Object API](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/lang/Object.html): `wait()`, `notify()`, `notifyAll()`, and monitor ownership rules.
- [Java SE 17 Thread API](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/lang/Thread.html): start, join, interrupt, and thread states.
- [Java SE 17 Lock API](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/concurrent/locks/Lock.html): memory synchronization semantics of explicit locks.
- [Java SE 17 ThreadMXBean](https://docs.oracle.com/en/java/javase/17/docs/api/java.management/java/lang/management/ThreadMXBean.html): contention metrics when supported.

**Technical summary:** an **unlock(m)** creates a *synchronizes-with* edge to subsequent **lock(m)** actions. Combined with program order, this establishes *happens-before* to guarantee visibility/ordering; meanwhile, having only one thread own `m` at a time protects the atomicity of the critical section. Using the **same monitor**, the right **invariant scope**, and a proper **waiting protocol** turns JMM guarantees into program correctness.
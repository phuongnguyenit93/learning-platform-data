# Object Monitors and Reentrancy of synchronized

## 1. Overview and Learning Objectives

In Java, **synchronized** helps multiple threads coordinate access to shared data through a **monitor** associated with **a specific object**. A thread must own the corresponding monitor before entering the synchronized code region protected by that monitor. Once a thread owns a monitor, it can **reenter** the same monitor multiple times instead of blocking itself. This capability is called **reentrant synchronization**.

Three key ideas:

1. **A monitor is tied to object identity, not to method names.** Two synchronized blocks are mutually exclusive only if they use **the exact same monitor object**.
2. **Synchronized is reentrant.** A thread holding a monitor can reenter a synchronized method/block using the same object, even across a chain of method calls or recursion. The JVM tracks the number of entries not yet balanced by exits.
3. **Monitor locking is not just mutual exclusion.** According to the Java Memory Model (JMM), an **unlock on monitor M happens-before every subsequent lock on M**; this is an important visibility/ordering mechanism for shared mutable state.

After this lesson, you will know:

- What a monitor is and why every Java object can be used as a monitor.
- **Owner thread**, **reentrancy/entry count**, and how monitors are acquired and released.
- How to distinguish **synchronized instance method**, **static synchronized method**, and **synchronized(lock)**.
- Why one synchronized method can call another synchronized method on the same object without deadlocking.
- How the Java compiler/JVM represents **monitorenter/monitorexit** and the **ACC_SYNCHRONIZED** flag.
- The difference between **BLOCKED** waiting to enter a monitor and **WAITING/TIMED_WAITING** in Object.wait().
- Why **wait()** releases all entry counts on the target monitor and **reacquires** them before returning, while notify()/notifyAll() **does not automatically release** the signaling thread's monitor.
- Consequences of IllegalMonitorStateException, NullPointerException, exception exits, and common misconceptions.
- The happens-before model, visibility, atomicity, lock identity, deadlock, and lock scope design principles.
- How to use Java 17+, Thread.holdsLock, jcmd, jstack, and JFR to observe and analyze monitor contention issues.

**Scope:** Java SE/JLS/JVMS 17 semantics. **HotSpot** monitor optimization details such as object header, lock records, monitor inflation, spinning, or biased locking are implementation details and may change between JDK versions. Do not treat them as stable interfaces guaranteed by the Java language.

## 2. What is a Monitor?

A Java object has **one monitor associated with that object identity**. A monitor has the conceptual mechanisms:

- **Owner:** the thread currently holding the monitor, or no owner.
- **Entry/hold count:** the number of times the owner has acquired the monitor without a corresponding release.
- **Entry contention:** other threads wanting to acquire the same monitor may have to wait.
- **Wait set:** the set of threads that have validly called Object.wait() on that object and are waiting for notification/interrupt/timeout/spurious wakeup according to Java rules.

Model:

~~~text
                Monitor associated with object LOCK
              +--------------------------------------+
 Thread T1 -->| Owner: T1                            |
              | Entry count: 2                       |
              | Wait set: {...}                      |
              +--------------------------------------+
                   ^
                   |
 Thread T2 --------+-----> BLOCKED if T2 wants to lock LOCK

T1 calls synchronized(LOCK) again:
   T1 is already owner -> entry count 2 -> 3, does not self-block.

T1 exits one synchronized:
   entry count 3 -> 2, still holds monitor.

T1 exits enough times:
   entry count 1 -> 0, no longer owner.
   Other threads can now compete to enter.
~~~

**Entry count is a semantic model**, not an int field with a public getter on java.lang.Object. JVMs may represent monitor ownership/reentrancy differently in native data structures; Java only provides the correct behavior.

### 2.1. A monitor is tied to an object, not automatically tied to "important data"

~~~java
// Illustrative code inside a method:
Object a = new Object();
Object b = new Object();
synchronized (a) {
    // Owns the monitor of a; does not own the monitor of b.
}
~~~

Both are of type **Object**, but **a != b**, so they are two independent monitors. If one thread synchronizes on a and another thread synchronizes on b, they do not block each other just because they use the synchronized keyword.

This is very important when designing private lock fields and when evaluating synchronized instance/static methods.

### 2.2. Each monitor has at most one owner at a time

When T1 owns monitor M with a positive hold count, T2 cannot simultaneously become the owner of M. However, T1 can still reenter M. This rule provides **mutual exclusion for critical sections using the same M**.

This does not mean all data of the object is automatically protected. If another thread accesses a mutable field **without going through the same monitor or an equivalent synchronization mechanism**, a data race can occur.

## 3. Three Forms of synchronized in Java

### 3.1. Instance synchronized method

~~~java
final class Counter {
    private int value;

    public synchronized void increment() {
        value++;
    }

    public synchronized int get() {
        return value;
    }
}
~~~

The monitor used is **this**, i.e., the specific Counter instance. With:

~~~java
Counter first = new Counter();
Counter second = new Counter();
~~~

A thread locking first and another thread locking second can run concurrently because these are two different object monitors. Two threads calling first.increment() at the same time must contend for first's monitor.

**A synchronized instance method does not automatically protect a static field with a global class lock.** It uses the **this** monitor.

### 3.2. Static synchronized method

~~~java
final class GlobalCounter {
    private static int value;

    public static synchronized void increment() {
        value++;
    }
}
~~~

The monitor used is **GlobalCounter.class**, i.e., the Class mirror object representing the runtime class **GlobalCounter** defined by the corresponding class loader.

Therefore **static synchronized** does not contend with the monitor of an ordinary GlobalCounter instance. An instance synchronized method and a static synchronized method of the same class use **two different monitors**; they do not protect against each other just because both have synchronized.

**Class loaders note:** two runtime classes with the same binary name but defined by two different defining class loaders may have two separate Class objects, two static states, and two separate monitors.

### 3.3. Synchronized statement/block

~~~java
final class Ledger {
    private final Object lock = new Object();
    private long balance;

    void add(long amount) {
        synchronized (lock) {
            balance += amount;
        }
    }

    long balance() {
        synchronized (lock) {
            return balance;
        }
    }
}
~~~

Here the lock object is a **private final lock**, not Ledger.this. This is often a good way to prevent external code from accidentally acquiring the monitor that protects internal state. All related accesses to balance must follow the same synchronization policy.

**final only fixes the lock field reference**, it does not make other fields thread-safe. All reads/writes of the protected state need to coordinate on the right monitor.

### 3.4. Comparison Table

| Syntax | Monitor actually acquired | Code kind | Note |
| --- | --- | --- | --- |
| **synchronized void m()** | this | Instance method | Each instance has its own monitor |
| **static synchronized void m()** | DefiningClass.class | Static method | Not the instance monitor |
| **synchronized (this) { ... }** | this | Statement/block | Can reenter with instance synchronized method |
| **synchronized (lock) { ... }** | object referenced by lock expression | Statement/block | Must use the same object identity |
| **synchronized (SomeClass.class) { ... }** | Class mirror object | Statement/block | Can coordinate with static synchronized of that class |

## 4. Synchronized is Reentrant: Monitor Entry/Exit Rules

Suppose T1 is at:

~~~java
synchronized (lock) {
    // First acquire.
    synchronized (lock) {
        // T1 acquires the exact same monitor again.
    }
}
~~~

T1 does not need to wait for itself to release the first lock. An entry count model:

~~~text
Initially:              owner = none; count = 0

T1 enters outer block:  owner = T1;   count = 1
T1 enters inner block:  owner = T1;   count = 2
T1 exits inner block:   owner = T1;   count = 1
T1 exits outer block:   owner = none; count = 0
~~~

Only when **count reaches 0** does T1 completely release ownership. There is no semantic guarantee about fairness or the order in which the next thread receives the monitor.

### 4.1. Reentrancy across a method call chain

~~~java
final class BankAccount {
    private long balance;

    public synchronized void deposit(long amount) {
        validate(amount);
        applyDeposit(amount);
    }

    private synchronized void applyDeposit(long amount) {
        balance += amount;
    }

    private synchronized void validate(long amount) {
        if (amount < 0) {
            throw new IllegalArgumentException("negative amount");
        }
    }

    public synchronized long getBalance() {
        return balance;
    }
}
~~~

**deposit**, **validate**, and **applyDeposit** all lock **this**. While deposit owns the monitor, it can call validate and then applyDeposit because **that same thread is the owner**. Each entry into a synchronized method has semantic entry/exit accounting, but it does not deadlock just by calling nested synchronized methods on the same receiver.

**Do not misunderstand:** reentrancy only exempts **the owner thread itself on the same monitor** from blocking. Thread T2 still has to wait.

### 4.2. Reentrancy vs. recursion

**Recursion** means a method calls itself; **lock reentrancy** means the same thread can reacquire the same lock. One can happen without the other:

- Two different synchronized methods on the same object calling each other: **lock reentrancy**, not recursion.
- Recursive pure function without synchronized: recursion without using a monitor.
- Recursive synchronized method: both recursion and lock reentrancy.
- Two different lock objects in nested blocks: nested locking, not reentering the **same** monitor.

## 5. Java 17 Runnable Demo #1: Proving Reentrancy

Create the file **ReentrantMonitorDemo.java**:

~~~java
public class ReentrantMonitorDemo {
    static final class Service {
        private int count;

        synchronized void outer() {
            inner(); // Reenter this monitor.
            synchronized (this) {
                inner(); // Another nested reentrance.
            }
        }

        private synchronized void inner() {
            if (!Thread.holdsLock(this)) {
                throw new AssertionError("monitor not held");
            }
            count++;
        }

        synchronized int getCount() {
            return count;
        }
    }

    public static void main(String[] args) {
        Service service = new Service();

        System.out.println("before="
                + Thread.holdsLock(service));

        synchronized (service) {
            System.out.println("inside="
                    + Thread.holdsLock(service));
            service.outer();
        }

        System.out.println("after="
                + Thread.holdsLock(service));
        System.out.println("count=" + service.getCount());
    }
}
~~~

Compile/run with JDK 17+:

~~~bash
javac --release 17 -encoding UTF-8 ReentrantMonitorDemo.java
java ReentrantMonitorDemo
~~~

**Exact stdout:**

~~~text
before=false
inside=true
after=false
count=2
~~~

Execution path:

1. In main before the block, the thread does not own the Service monitor.
2. Entering synchronized(service), owner is main, conceptual count = 1.
3. Calling **service.outer()**, which is a synchronized instance method, reenters the same service monitor.
4. **outer()** calls **inner()**, continuing to reenter the monitor; Thread.holdsLock(this) returns true.
5. Entering synchronized(this) right inside outer, then calling inner() again: still the owner thread, not self-blocked.
6. The scopes/methods exit in reverse order; outside the block, main no longer holds the monitor.
7. inner is called exactly twice, count=2.

**Thread.holdsLock(Object obj)** only returns a **boolean** indicating whether the current thread holds the monitor of obj; it does not return the hold count, does not check another thread's monitor ownership, and is not a tool for measuring lock contention.

## 6. One Monitor Used for Multiple Methods, Without Automatically Locking the Whole Object

A typical bug:

~~~java
final class Box {
    private int value;

    synchronized void increment() {
        value++;
    }

    int unsafeRead() {
        return value;
    }
}
~~~

**increment** locks this, but **unsafeRead** does not lock or use another visibility mechanism. If one thread reads while another thread writes, this can be a **data race**. Synchronized does not automatically apply protection to every access to the object's fields.

A simple fix:

~~~java
synchronized int safeRead() {
    return value;
}
~~~

This is **a method snippet to add to Box**, not a standalone Java file. Both increment and safeRead acquire the monitor of the same Box instance.

### 6.1. A field protected by two different locks is not enough

~~~java
private final Object writeLock = new Object();
private final Object readLock = new Object();
private int value;

void update() {
    synchronized (writeLock) {
        value++;
    }
}

int read() {
    synchronized (readLock) {
        return value;
    }
}
~~~

Even though both methods have synchronized blocks, **writeLock != readLock**. They do not establish mutual exclusion/happens-before through the same monitor. This is code **illustrating a bug**, not a complete standalone class. You must use **the same lock** or another proper Java concurrency strategy.

## 7. Java 17 Runnable Demo #2: Safely Incrementing a Counter Across Multiple Threads

Create the file **SynchronizedCounterDemo.java**:

~~~java
public class SynchronizedCounterDemo {
    static final class Counter {
        private int value;

        synchronized void increment() {
            doIncrement(); // Reentrant synchronized call.
        }

        private synchronized void doIncrement() {
            value++;
        }

        synchronized int get() {
            return value;
        }
    }

    public static void main(String[] args)
            throws InterruptedException {
        Counter counter = new Counter();
        Thread[] threads = new Thread[4];

        for (int t = 0; t < threads.length; t++) {
            threads[t] = new Thread(() -> {
                for (int i = 0; i < 5_000; i++) {
                    counter.increment();
                }
            });
        }

        for (Thread thread : threads) {
            thread.start();
        }
        for (Thread thread : threads) {
            thread.join();
        }

        System.out.println("count=" + counter.get());
        System.out.println("expected=" + (4 * 5_000));
        System.out.println("correct="
                + (counter.get() == 4 * 5_000));
    }
}
~~~

Run:

~~~bash
javac --release 17 -encoding UTF-8 SynchronizedCounterDemo.java
java SynchronizedCounterDemo
~~~

**Exact stdout if the program completes normally:**

~~~text
count=20000
expected=20000
correct=true
~~~

Explanation:

- Four threads, each calling increment 5,000 times.
- **increment()** acquires Counter.this and reenters when calling **doIncrement()**; the same owner thread is allowed to execute.
- The **value++** operation is protected by a single monitor, so no two threads modify the variable in overlapping critical sections.
- **Thread.join()** waits for all workers to finish; under the JMM, actions in a joined thread happen-before another thread detects that the join completed successfully.
- **counter.get()** also acquires the corresponding monitor, so reading after completion is safe.
- Thread execution order is nondeterministic, but the total result after join is deterministic.

**Do not use this code to prove fair monitor scheduling.** Thread order, the number of times threads are BLOCKED, and elapsed runtime vary across runs.

## 8. Synchronized Method vs. monitorenter/monitorexit in the Class File

There are two important ways synchronization is encoded in the JVMS.

### 8.1. Synchronized statement

~~~java
void work(Object lock) {
    synchronized (lock) {
        System.out.println("work");
    }
}
~~~

The standard Java compiler generates bytecode with **monitorenter** and **monitorexit**, along with an **exception handler** to ensure the monitor is exited when an exception leaves the block. Conceptually:

~~~text
aload lock
monitorenter
  ...
monitorexit
goto end

exceptionHandler:
  monitorexit
  athrow

end:
  return
~~~

The diagram omits exact stack/locals, offsets, and exception tables; it is not fixed javap output. What is true per the JVMS is that **monitorenter** increments the entry count if the thread already owns the monitor, while **monitorexit** decrements the count; when it reaches 0, the owner is released.

### 8.2. Synchronized method

~~~java
synchronized void task() {
    System.out.println("task");
}
~~~

A synchronized method in a class file carries the **ACC_SYNCHRONIZED** flag. The JVM handles monitor acquire/release **implicitly** upon invocation/return/abrupt completion of the method; it does not necessarily generate monitorenter and monitorexit in the method body bytecode.

**A point very often taught incorrectly:** "Every synchronized method will have a monitorenter/monitorexit pair in javap -c." For a normal synchronized method, look at **ACC_SYNCHRONIZED**; do not expect to see those two opcodes in the method instructions.

### 8.3. How to observe the bytecode

After compiling ReentrantMonitorDemo.java:

~~~bash
javap -c -v 'ReentrantMonitorDemo$Service'
~~~

This quoting syntax suits Unix-like terminals. On PowerShell, single quotes around a class name containing `$` also avoid variable expansion. Look at **flags: ACC_SYNCHRONIZED** for the outer/inner/getCount methods and **monitorenter/monitorexit** around the explicit synchronized(this) block.

**Note:** javap only shows Java bytecode/class-file metadata; it does not reveal HotSpot's native lightweight lock records or CPU-level locking instructions generated by the JIT.

## 9. Java Memory Model: Monitors Are Not Just Mutual Exclusion

According to JLS §17.4.5, an **unlock action on monitor M synchronizes-with every subsequent lock action on M**, creating a **happens-before** relationship.

Example:

~~~java
final class SharedState {
    private final Object lock = new Object();
    private int data;

    void publish() {
        synchronized (lock) {
            data = 42;
        } // unlock lock
    }

    int observe() {
        synchronized (lock) { // lock the same object
            return data;
        }
    }
}
~~~

If thread T1 completes **publish()** before thread T2 acquires the same lock to run **observe()**, T2 has the appropriate happens-before relationship to observe the update 42, assuming no other mutation and proper object usage/publication.

### 9.1. Acquire and release semantics

Intuition:

- **Unlock/release**: publishes writes that occurred before it through synchronization ordering.
- **Subsequent lock/acquire on the same M**: after acquiring, the next thread has proper visibility of the writes before the unlock.
- Those accesses must actually be organized around **the same monitor object**.
- Synchronization also places constraints on compiler/CPU reordering to preserve the JMM.

**Happens-before does not mean "all writes in all threads become instantly visible when synchronizing on any object."** If the writer uses lockA and the reader uses lockB, two different locks alone do not provide a monitor happens-before edge between the two operations.

### 9.2. Synchronized provides atomicity at the critical section level

When **value++** occurs inside synchronized(lock) and all other threads also follow the same lock to access state, mutual exclusion prevents the read-modify-write from interleaving with another critical section on the same monitor.

However, a synchronized method protecting one operation **does not automatically turn a sequence of two separate calls into a transaction**:

~~~java
if (account.getBalance() > 0) {
    account.withdraw(1);
}
~~~

Even if getBalance and withdraw are individually synchronized, another thread can interleave between the two calls. If atomic check-then-act is needed, combine both into **a single synchronized region using the same monitor**, or define an atomic business method.

### 9.3. A reentrant monitor is not a distributed lock

A Java process monitor only coordinates threads within the same runtime object model. It does not automatically protect a DB record from another process, does not replace transaction isolation, and is not a distributed locking system.

## 10. When Does a Thread Become BLOCKED?

Suppose T1 has acquired the monitor lock:

~~~text
T1: synchronized(lock) {
        // long-running work
    }

T2: synchronized(lock) {
        // must wait for T1 to release completely
    }
~~~

T2 wanting to enter a critical section using the same monitor can be observed in the Java **Thread.State.BLOCKED** state. A thread that is **BLOCKED** waiting for monitor entry is **not** a thread that has acquired the monitor.

Other points:

- T1 can reenter while the count is positive.
- T2 can acquire only when the monitor is completely free, not when T1 merely exits a nested block.
- The JVM does not guarantee FIFO fairness.
- Java intrinsic monitor entry does not provide the same public **tryLock(timeout)**/**lockInterruptibly()** as ReentrantLock.
- **Thread.interrupt()** is not guaranteed to make a thread waiting to enter an intrinsic monitor immediately throw InterruptedException and abort acquiring.

### 10.1. Object.wait() vs. BLOCKED-to-enter

**BLOCKED:** wants to enter a synchronized region, but the monitor is currently owned by another thread.

**WAITING:** after owning a monitor, a thread can validly call **wait()**, **release that monitor**, and remain in the wait set until notification/interrupt/spurious wakeup.

**TIMED_WAITING:** can occur when calling **wait(timeout)** or **sleep(timeout)**; however, sleep **does not release the monitor** the thread is holding.

Thread state is a **snapshot**; it can change very quickly. Do not define correctness algorithms by polling getState() and waiting for a specific state name.

## 11. wait()/notify()/notifyAll(): Coordinating on the Same Monitor

Java provides instance methods in **Object**:

- **wait()**, **wait(long)**, **wait(long,int)**.
- **notify()**.
- **notifyAll()**.

The thread calling these methods must **own the monitor of the receiver object itself**. Otherwise, **IllegalMonitorStateException** is typically thrown.

Example:

~~~java
final Object lock = new Object();

synchronized (lock) {
    lock.wait();
}
~~~

This is **illustrative** code, not an example to run as-is: without a signal/interrupt and without a spurious wakeup, it can wait indefinitely. The method also needs to handle **InterruptedException**.

### 11.1. What does wait() actually do?

According to JLS §17.2:

1. If the thread does not own the receiver's monitor, throw IllegalMonitorStateException.
2. The thread is placed into the receiver object's **wait set**.
3. The JVM performs a number of **unlocks matching all unbalanced acquisitions on the receiver's monitor itself**.
4. The thread waits until notification/interrupt/timeout/spurious wakeup according to the semantics.
5. When removed from the wait set, the thread must **reacquire the same monitor with its previous ownership count** before wait completes/returns or throws InterruptedException as appropriate.

**Specifically:** if a thread owns monitor m twice due to nested synchronized(m), calling **m.wait()** releases **both levels** for m. It does not just decrement count 2→1; otherwise, a notifier thread could not acquire m and the wait/notify pattern would easily deadlock.

### 11.2. wait() does not release other monitors

~~~java
synchronized (lockA) {
    synchronized (lockB) {
        lockB.wait();
    }
}
~~~

The thread temporarily releases acquisitions of **lockB**, but still holds **lockA** while waiting. Therefore, this can cause a deadlock if the notifier must acquire lockA before it can notify lockB.

**Design rule:** avoid holding an unrelated lock across a wait call on another monitor, unless lock ordering has been carefully analyzed.

### 11.3. notify()/notifyAll() does not release the monitor immediately

~~~text
T1 owns monitor M:
  synchronized(M) {
      condition = true;
      M.notifyAll();        // removes waiters from wait set
      doMoreWork();         // T1 is still the owner
  }                        // T1 unlocks here

T2 waiting on M:
  M.wait() cannot finish returning
  until T2 reacquires M after T1 releases it.
~~~

Notify is a **signal**, not an immediate monitor handoff operation. After notifyAll(), waiters still have to **re-compete to acquire** the same monitor. Java does not guarantee which specific thread receives the lock first.

### 11.4. Always wait in a while loop checking the condition

~~~java
synchronized (lock) {
    while (!condition) {
        lock.wait();
    }
    // Proceed only if condition is actually true.
}
~~~

Because:

- **Spurious wakeups** can occur.
- notifyAll may wake multiple threads, but only one thread takes the resource.
- Condition may have changed before the waiter reacquires the lock.
- notify() only picks an arbitrary waiter, with no promise of picking the desired waiter.
- InterruptedException needs to be handled according to the application contract.

**Do not** use if instead of while when correctness depends on a predicate. Also do not use Thread.sleep() instead of wait() inside a critical section: sleep does not release the monitor.

## 12. Java 17 Runnable Demo #3: wait Releases All Reentrant Holds

Create the file **ReentrantWaitDemo.java**:

~~~java
import java.util.concurrent.CountDownLatch;

public class ReentrantWaitDemo {
    public static void main(String[] args)
            throws InterruptedException {
        Object lock = new Object();
        CountDownLatch entered = new CountDownLatch(1);
        boolean[] ready = {false};
        boolean[] reacquired = {false};

        Thread waiter = new Thread(() -> {
            synchronized (lock) {
                synchronized (lock) {
                    entered.countDown();
                    while (!ready[0]) {
                        try {
                            lock.wait();
                        } catch (InterruptedException ex) {
                            Thread.currentThread().interrupt();
                            return;
                        }
                    }
                    reacquired[0] = Thread.holdsLock(lock);
                }
            }
        });

        waiter.start();
        entered.await();

        synchronized (lock) {
            ready[0] = true;
            lock.notifyAll();
        }

        waiter.join();
        System.out.println("condition=" + ready[0]);
        System.out.println("reacquired=" + reacquired[0]);
        System.out.println("completed=" + !waiter.isAlive());
    }
}
~~~

Compile/run:

~~~bash
javac --release 17 -encoding UTF-8 ReentrantWaitDemo.java
java ReentrantWaitDemo
~~~

**Exact stdout in a normal run, with no external interrupt:**

~~~text
condition=true
reacquired=true
completed=true
~~~

Why:

1. Waiter acquires the same **lock** twice using nested synchronized blocks.
2. Waiter calls entered.countDown() while owning lock, then checks ready=false and calls lock.wait().
3. **wait() temporarily releases all 2 reentrant holds** of lock. Main can acquire lock, set ready=true, and notifyAll().
4. Main must exit synchronized(lock) to actually release; the notifier **does not hand over the monitor immediately** at notifyAll().
5. Waiter reacquires the monitor to the exact required depth, checks the while loop; ready=true, so it records Thread.holdsLock(lock)==true.
6. Waiter exits the nested blocks, then main joins waiting for waiter to finish.
7. No need to use Thread.sleep to coordinate timing; CountDownLatch only lets main know waiter has reached the required point.

**If a spurious wakeup occurs:** waiter rechecks the while loop, continues waiting when ready=false, so it does not go wrong. If abnormally interrupted by another thread, the demo has a return branch; stdout is described for a normal environment without external interruption.

**Note:** CountDownLatch does not replace the monitor protocol in the demo. It is wait() that releases the monitor so main can acquire and signal the condition; the latch is only a synchronization point ensuring the experiment's starting order.

## 13. IllegalMonitorStateException and Null Monitor

### 13.1. wait/notify without holding the right monitor

~~~java
Object lock = new Object();
lock.notifyAll(); // Does not own lock's monitor -> IllegalMonitorStateException.
~~~

If the code only holds **another monitor**:

~~~java
Object a = new Object();
Object b = new Object();

synchronized (a) {
    b.notifyAll(); // Still wrong: does not own b's monitor.
}
~~~

You must call wait/notify on **the exact object the thread has acquired**. Holding monitor a does not grant permission to send notifications on b.

### 13.2. synchronized(null)

~~~java
Object lock = null;

synchronized (lock) {
    // Not entered: NullPointerException.
}
~~~

According to the JVMS, **monitorenter** with a null object reference throws NullPointerException. This is not a "null lock so just run unsynchronized" situation.

### 13.3. Does an exception inside synchronized leak the monitor?

Java guarantees that a synchronized statement/method performs the appropriate monitor release on **normal or abrupt** completion, including exception propagation. The compiler generates an exception path for a synchronized block; a method with ACC_SYNCHRONIZED is handled with implicit release by the VM.

~~~java
void fail(Object lock) {
    synchronized (lock) {
        throw new IllegalStateException("boom");
    } // monitor is exited during exception propagation.
}
~~~

Illustrative code; a runtime exception does not automatically "lock the monitor forever." However, a thread hung indefinitely **inside** synchronized (without exiting the block/method) can still hold the lock for a very long time.

### 13.4. Thread.stop() and unsafe threading APIs

Do not use historical APIs like **Thread.stop()** to "force a thread holding a monitor to release the lock." Abrupt stopping mechanisms can bypass object invariants and corrupt shared state. Use cancellation/cooperative interruption with a clear lifecycle.

## 14. Java 17 Runnable Demo #4: Static Lock and Instance Lock Are Different

Create **MonitorIdentityDemo.java**:

~~~java
public class MonitorIdentityDemo {
    static synchronized boolean classOwned() {
        return Thread.holdsLock(MonitorIdentityDemo.class);
    }

    synchronized boolean instanceOwned() {
        return Thread.holdsLock(this);
    }

    public static void main(String[] args) {
        MonitorIdentityDemo instance =
                new MonitorIdentityDemo();

        System.out.println("classMethod="
                + classOwned());
        System.out.println("instanceMethod="
                + instance.instanceOwned());

        synchronized (MonitorIdentityDemo.class) {
            System.out.println("classBlock="
                    + Thread.holdsLock(MonitorIdentityDemo.class));
            System.out.println("instanceInClassBlock="
                    + Thread.holdsLock(instance));
        }
    }
}
~~~

Run:

~~~bash
javac --release 17 -encoding UTF-8 MonitorIdentityDemo.java
java MonitorIdentityDemo
~~~

**Stdout:**

~~~text
classMethod=true
instanceMethod=true
classBlock=true
instanceInClassBlock=false
~~~

Explanation:

- classOwned() is **static synchronized**, so the method holds **MonitorIdentityDemo.class** when calling holdsLock.
- instanceOwned() holds **this**, which is the instance monitor.
- Main acquires the Class monitor; that does not automatically acquire the instance monitor.
- The experiment uses only one thread to demonstrate the **object identity** of monitors; it does not prove scheduling order between threads.

## 15. Fairness, Scheduling, and Interruption Issues

**Intrinsic monitors have no FIFO fairness contract** for all waiters. When a monitor is released, the JVM/OS may choose which thread acquires next based on scheduling/implementation.

Things that must not be assumed:

- If thread T2 waits before T3, T2 is guaranteed to get the lock first.
- notify() will choose the thread that has been waiting the longest.
- Thread.interrupt() will always make a thread BLOCKED waiting for monitor entry stop waiting and throw InterruptedException.
- Thread.yield() will cause the monitor to be released.
- Thread.sleep() inside synchronized will release the monitor.
- A synchronized block has a built-in timeout parameter equivalent to tryLock(timeout).

### 15.1. ReentrantLock vs. intrinsic synchronized

**java.util.concurrent.locks.ReentrantLock** is also reentrant, but has additional APIs:

- **lock()** and **unlock()**.
- **tryLock()** and **tryLock(timeout)**.
- **lockInterruptibly()**.
- Can create a fair-mode lock via API, though a fairness policy has trade-offs.
- Condition objects supporting multiple logical wait sets.
- **getHoldCount()** and some introspection capabilities.

Conversely, intrinsic synchronized has concise syntax, automatic release by lexical scope, and built-in monitor wait/notify. **Do not assume ReentrantLock is always faster than synchronized**; the JVM has many optimizations for intrinsic monitors.

Example of using ReentrantLock properly:

~~~java
// Illustrative code, assuming Lock lock is declared:
lock.lock();
try {
    // Critical section.
} finally {
    lock.unlock();
}
~~~

With ReentrantLock, **unlock() is an operation the programmer must call**, so forgetting finally can leak lock ownership. Intrinsic synchronized exits automatically when the block ends.

## 16. Deadlock: Reentrancy Cannot Cure Cross-Locking

Reentrancy prevents **self-deadlock when the same owner thread reacquires the same monitor**, but it does not prevent **deadlock across multiple monitors**.

Example scenario:

~~~text
T1:
  acquire monitor A
  attempt acquire B -> BLOCKED because T2 holds B

T2:
  acquire monitor B
  attempt acquire A -> BLOCKED because T1 holds A

Result:
  T1 waits for B held by T2
  T2 waits for A held by T1
  -> Circular wait / deadlock
~~~

This is a conceptual example; you should not try to run an infinite deadlock program in a shared environment.

### 16.1. Nested synchronized vs. lock reentrancy

~~~java
synchronized (a) {
    synchronized (b) {
        // Holds two monitors a and b.
    }
}
~~~

If a and b are two different objects, this is **nested multi-locking**, not **reentering the same lock**. T2 locking b then a can create a lock-order inversion.

### 16.2. How to prevent deadlock

1. Establish a **global lock ordering** and always acquire multiple monitors in the same order.
2. Keep critical sections short; avoid long I/O/blocking operations inside synchronized.
3. Do not call uncontrolled external code while holding a monitor if the callback might acquire other locks.
4. Reduce the number of monitors that must be held simultaneously.
5. If timeout or interruptible acquisition is required, consider ReentrantLock.tryLock/lockInterruptibly instead of an intrinsic monitor.
6. Use thread dumps/JFR to determine actual ownership; do not guess from a single source snippet.

### 16.3. Calling wait() on monitor B while still holding A can cause deadlock

~~~java
synchronized (a) {
    synchronized (b) {
        b.wait();
    }
}
~~~

The thread will release B when waiting, but **still holds A**. If the notifier needs to acquire A first before it can notify B, the two threads can get stuck. This is a different failure mode from an owner reentering the same monitor.

## 17. Visibility Does Not Extend Across Different Locks

Wrong design example:

~~~java
final class WrongLockExample {
    private final Object writeLock = new Object();
    private final Object readLock = new Object();
    private int value;

    void set(int newValue) {
        synchronized (writeLock) {
            value = newValue;
        }
    }

    int get() {
        synchronized (readLock) {
            return value;
        }
    }
}
~~~

Even though both methods use synchronized, they lock **different objects**. The Java Memory Model has no monitor happens-before edge between unlocking writeLock and locking readLock just because both are synchronized.

Fix:

~~~java
final class RightLockExample {
    private final Object lock = new Object();
    private int value;

    void set(int newValue) {
        synchronized (lock) {
            value = newValue;
        }
    }

    int get() {
        synchronized (lock) {
            return value;
        }
    }
}
~~~

With every thread following the same lock discipline, get() reads properly synchronized state. If other code reads value directly without synchronization, overall thread-safety guarantees can still be broken.

### 17.1. synchronized on String literals, boxed Integer, public locks

~~~java
synchronized ("LOCK_NAME") {
    // Should not use an interned public String as a private lock.
}
~~~

String literals can be interned/shared across unrelated code; other components may accidentally lock the same monitor. Similarly, boxed values such as Integer.valueOf(1) can be cached; public locks create hard-to-control lock coupling risks.

Prefer **private final Object lock = new Object()** for internal data. Do not use a newly created object **on every method call** like synchronized(new Object()) if the goal is coordination among callers; each object identity is a different monitor.

### 17.2. Locking on this: convenient but public exposure

An instance synchronized method uses **this**, so any code holding a reference to the instance can intentionally or accidentally do synchronized(instance). When designing library/service internals, a private lock object lets you avoid unexpected lock sharing between internal and external components.

However, a private lock is only valuable if all relevant reads/writes use the exact same lock; it is not a magic thread-safe marker.

## 18. Performance of synchronized and JVM Implementation

On HotSpot, monitors can be optimized so uncontended locking is cheap. Terms you may encounter in diagnostics/historical explanations:

- **Thin/lightweight locking**: version-dependent optimization mechanism for uncontended monitor entry/exit.
- **Inflated monitor/ObjectMonitor**: the implementation may use a heavier monitor structure under contention/waiting or other conditions.
- **Lock coarsening/elision**: the compiler can optimize synchronized operations when proven valid.
- **Biased locking**: a historical HotSpot optimization, disabled by default and deprecated since JDK 15 per JEP 374; do not teach it as default behavior for JDK 17.

**Do not hardcode** object header bit widths, Monitor owner pointers, or thin-lock encodings to a single scheme for JDK 17 and JDK 25. These internals can change due to lightweight locking improvements or virtual-thread monitors.

### 18.1. Contention can burn CPU and reduce scalability

If 32 worker threads continuously call synchronized on **one global lock**, only one thread can execute the critical section at any given time. Wait time can be large even if the operation is a small addition. Reasonable tuning goals:

- Reduce contention by partitioning/sharding locks by independent data.
- Shorten critical sections.
- Avoid I/O/DB calls inside locks.
- Consider concurrent collections, atomics, or LongAdder for counters where semantics fit.
- Benchmark throughput/tail latency before and after.

**You cannot optimize by removing synchronized** if mutual exclusion/visibility requirements still exist. Replace it with an equivalent synchronization strategy that does not introduce data races.

### 18.2. Monitor reentrancy does not mean every nested synchronized is free

When reentering the same monitor in JIT-optimized code, the VM can optimize many operations; however, there can still be semantic/safepoint/deoptimization/monitor bookkeeping costs under other conditions. Do not assume reentrant entry always has zero CPU cost or is always as expensive as contended acquisition.

## 19. Observing Monitors with Thread.holdsLock, jcmd, jstack, and JFR

### 19.1. Thread.holdsLock

~~~java
Object lock = new Object();
System.out.println(Thread.holdsLock(lock)); // false on a thread that has not locked it.
synchronized (lock) {
    System.out.println(Thread.holdsLock(lock)); // true.
}
~~~

This snippet runs in a method and applies to the current thread. The API only tells you whether the current thread owns the object monitor; it **does not return recursion depth** and does not return information about other threads.

### 19.2. jcmd Thread.print

On HotSpot JDK 17, while the process is running:

~~~bash
jcmd
jcmd <PID> help
jcmd <PID> Thread.print
~~~

Replace **<PID>** with the actual PID; output can list Java thread states, monitor ownership/blocked-on details, and deadlock information depending on the tool/build. Use appropriate permissions; the output contains stack traces and application information that must be handled securely.

### 19.3. jstack

~~~bash
jstack <PID>
jstack -l <PID>
~~~

**-l** requests additional lock-related information depending on the jstack implementation. Depending on the JDK and attach mechanism, jstack may not be available; on newer JDKs, **jcmd Thread.print** is often a convenient starting point.

A thread dump may describe:

~~~text
Thread-1: BLOCKED (on object monitor)
    - waiting to lock <...> (a java.lang.Object)

Thread-2: RUNNABLE
    - locked <...> (a java.lang.Object)
~~~

This is an **illustrative format**, not fixed output from a specific snippet. When seeing BLOCKED, find the exact object monitor and owner thread, then compare both call stacks.

### 19.4. Java Flight Recorder

JFR has relevant events to observe monitor contention and wait durations when enabled, such as **jdk.JavaMonitorEnter** and **jdk.JavaMonitorWait**, depending on the JDK/recording profile.

Launch a real application with main:

~~~bash
java -XX:StartFlightRecording=filename=monitors.jfr,duration=30s,settings=profile MyMain
~~~

Use the jfr CLI:

~~~bash
jfr summary monitors.jfr
jfr print --events jdk.JavaMonitorEnter,jdk.JavaMonitorWait monitors.jfr
~~~

**MyMain** and the file name are examples; the application may finish before the duration. Events may be absent due to recording settings/thresholds, no significant contention, or JVM configuration. Do not say "no JavaMonitorEnter event" means the program never synchronized.

### 19.5. ThreadMXBean

The Java management API **java.lang.management.ThreadMXBean** has methods to retrieve thread information, deadlock detection, and monitor information on supporting VMs. For example, reading full stack traces can have overhead; remember that thread/monitor states are continuously changing snapshots.

### 19.6. Measuring latency: is the bottleneck a monitor?

If request latency increases, ask:

1. Do thread dumps/JFR show many threads **BLOCKED on the same object monitor**?
2. What work is the owner thread performing inside the critical section?
3. Is the owner waiting on I/O, another lock, or calling an uncontrolled callback?
4. Is there heavy monitor contention from using a global singleton lock?
5. Is there a real deadlock (circular waits) or just brief contention?
6. Are many threads WAITING because a condition is not being signaled properly?
7. Is the issue GC/safepoint/CPU throttling rather than a monitor?
8. Is throughput optimization needed, or a correctness bug fix?

Do not diagnose thread-safety just by reading a single file with the synchronized keyword. You need to know **object identity** and runtime paths.

## 20. Monitors and Virtual Threads: Version Notes

**Java 17 does not yet have virtual threads as an official feature.** Java 21 made virtual threads a production feature per JEP 444. In JDKs 21–23, a virtual thread executing synchronized code can lead to **carrier-thread pinning** when blocking, reducing scalability in certain situations.

**JDK 24 / JEP 491** improves the monitor mechanism so virtual threads can **unmount** in many synchronized/monitor waiting situations instead of pinning as before. Therefore:

- Do not assume all JDKs using virtual threads have the same synchronized pinning behavior.
- Do not apply JDK 21–23 advice "avoid all synchronized to avoid pinning" verbatim to JDK 24+.
- Still keep critical sections short and avoid lock contention even with virtual threads.
- **Monitor ownership/reentrancy/JMM** semantics for Java code must still be preserved across these implementation changes.

This information is meant to prevent misinterpretation when studying older materials; it **does not replace** Java 17's synchronized principles.

## 21. Common Misconceptions

1. **"synchronized locks the method name."** False: it acquires a specific monitor, usually this or a Class object.
2. **"All synchronized methods in the same class use a single lock."** False for instance methods on different instances or static vs. instance.
3. **"A thread calling a synchronized method and then calling another synchronized method on the same object will deadlock."** False: monitors are reentrant.
4. **"Reentering a monitor does not need to track the ownership count."** False: reentrant acquisitions must be balanced.
5. **"Exiting an inner synchronized releases the entire monitor."** False if there is still an outer hold count.
6. **"Another thread can interleave between two nested synchronized blocks of the same owner."** No, while the owner still holds the monitor.
7. **"Thread.holdsLock returns the recursion count."** False: only a boolean for the current thread.
8. **"synchronized instance protects a static field with a global class monitor."** False: it locks this.
9. **"static synchronized locks all instances of the same class."** It locks the Class monitor, and does not automatically acquire instance monitors.
10. **"synchronized on lockA protects reads using lockB."** False: lacks same-monitor synchronization.
11. **"Synchronized using a new Object on every invocation will make callers block each other."** False: different object identities.
12. **"Having the synchronized keyword makes every field in the class thread-safe."** False: other accesses can data race.
13. **"unlock monitor A happens-before lock monitor B."** Not just because both monitors have synchronized; a matching monitor or other HB edges are needed.
14. **"Synchronized guarantees FIFO fairness."** False: intrinsic monitors have no fairness guarantee.
15. **"Thread.sleep inside synchronized releases the monitor."** False: sleep does not release monitors.
16. **"Object.wait does not release the monitor."** False: it releases **all acquisitions of the receiver monitor**.
17. **"wait on B releases all monitors A/B that the thread is holding."** False: only the receiver B.
18. **"notifyAll transfers the lock immediately to a waiter."** False: the notifier still holds the monitor until it unlocks.
19. **"notify() always chooses the longest-waiting waiter."** False: there is no guaranteed selection order.
20. **"if(condition) wait is enough."** False: use a while predicate because of spurious wakeups/state races.
21. **"wait/notify can be called without holding the receiver's monitor."** False: IllegalMonitorStateException.
22. **"synchronized(null) is a no-op."** False: NullPointerException.
23. **"An exception thrown out of a synchronized block leaks the monitor."** False: released on abrupt exit per semantics.
24. **"A synchronized method always generates monitorenter/exit in bytecode."** False: it uses the ACC_SYNCHRONIZED method flag.
25. **"monitorenter is only for non-reentrant locking."** False: reentrant count is part of instruction semantics.
26. **"Reentrancy automatically prevents deadlock across two monitors."** False: A→B/B→A can still deadlock.
27. **"Thread.interrupt will immediately abort waiting on synchronized monitor entry."** Not according to intrinsic lock rules.
28. **"Thread.State.WAITING and BLOCKED are the same."** False: waiting on a condition vs. monitor acquisition.
29. **"JIT implementation lock encoding is part of the Java SE API."** False: VM implementation details.
30. **"Biased locking is always enabled by default on Java 17."** False: disabled-by-default since JDK 15.
31. **"GC/HotSpot lock improvements make happens-before unnecessary."** False: JMM semantics remain unchanged.
32. **"Removing synchronized will always make a program faster."** False if it causes data races/corruption or requires a more expensive synchronization mechanism.
33. **"A monitor is a distributed lock protecting a DB across multiple JVMs."** False.
34. **"Class loaders defining the same binary name share one Class monitor."** Not necessarily; runtime class identity depends on the defining loader.
35. **"wait will return immediately upon receiving notify even if the monitor is still held by the notifier."** False: it must reacquire the monitor first.
36. **"Virtual threads in Java 21 and Java 25 always have the same monitor pinning."** False: JDK 24/JEP 491 changes this significantly.

## 22. Exercises with Solutions

**Question 1.** Two threads simultaneously call a synchronized instance method on **two different instances**. Do they block each other?

**Answer:** Not just because the method has the same name. Each instance has its own monitor.

**Question 2.** Thread T1 enters synchronized(lock) and then nested synchronized(lock). How does the logical entry count change?

**Answer:** 0→1→2, then exiting inner leaves 1, exiting outer returns to 0.

**Question 3.** What does a synchronized static method lock?

**Answer:** DefiningClass.class, i.e., the Class mirror object of the runtime class.

**Question 4.** What does a synchronized instance method lock?

**Answer:** this, i.e., the monitor of the receiver instance.

**Question 5.** Can a static synchronized method and an instance synchronized method of the same class run in parallel?

**Answer:** Yes, because the Class monitor is different from the instance monitor, unless the code uses other locks.

**Question 6.** While owning a monitor lock, does calling another synchronized method on the same object self-deadlock?

**Answer:** No; the monitor is reentrant for that owner thread.

**Question 7.** What does Thread.holdsLock(lock) return if the current thread has reentered lock 3 times?

**Answer:** true, it does not return 3.

**Question 8.** Which synchronized construct is represented by monitorenter/monitorexit? What does a synchronized method use?

**Answer:** Synchronized statement uses monitorenter/exit; synchronized method uses ACC_SYNCHRONIZED and VM implicit monitor entry/exit.

**Question 9.** T1 holds M twice and then calls M.wait(). How many times does T1 temporarily release?

**Answer:** Temporarily releases both acquisitions on M; upon returning, it reacquires to the same hold depth.

**Question 10.** T1 holds A and B and then calls B.wait(). Is monitor A released?

**Answer:** No; only B is released by wait on B.

**Question 11.** T1 calls notifyAll() inside synchronized(lock). Does T2 immediately run in the critical section before T1 exits?

**Answer:** No; T2 must reacquire the monitor after T1 releases enough holds.

**Question 12.** Why is while (!condition) lock.wait() better than if?

**Answer:** Because of spurious wakeups or the condition changing before the waiter reacquires; the predicate must be rechecked.

**Question 13.** What does calling Object.notify() without holding the receiver's monitor lead to?

**Answer:** IllegalMonitorStateException.

**Question 14.** What does synchronized(null) lead to?

**Answer:** NullPointerException on monitor entry.

**Question 15.** Does a synchronized block throwing a RuntimeException always keep the monitor forever?

**Answer:** No. Synchronized semantics guarantee unlock on normal/abrupt completion.

**Question 16.** How does a thread that is BLOCKED waiting for a monitor differ from WAITING after wait()?

**Answer:** BLOCKED has not acquired the monitor; WAITING after wait() has released the receiver monitor and is waiting for an event/notification.

**Question 17.** Using synchronized(lockA) to write state, synchronized(lockB) to read state. Is there a direct monitor HB edge?

**Answer:** No if lockA and lockB have different identities, and no other synchronization guarantees it.

**Question 18.** One thread holds A waiting for B and another thread holds B waiting for A. Can reentrancy solve this?

**Answer:** No; deadlock is caused by two owners and a circular wait on two different monitors.

**Question 19.** Why is synchronized("shared") not a good private lock?

**Answer:** String literals can be interned/shared; other parts of the code can unintentionally lock the same object.

**Question 20.** When should you use private final Object lock?

**Answer:** When you want to hide the lock identity so only internal code uses the same monitor to protect a state.

**Question 21.** Is biased locking still enabled by default in JDK 17?

**Answer:** No, JEP 374 disabled it by default and deprecated it since JDK 15.

**Question 22.** Java 21–23 virtual threads can pin carriers with synchronized. What does JDK 24 change?

**Answer:** JEP 491 improves unmounting of virtual threads when monitor blocked/waiting, reducing pinning.

**Question 23.** Why does Thread.join() help the counter demo have deterministic output?

**Answer:** Main waits for the four threads to perform all operations; thread completion/join provides the appropriate HB.

**Question 24.** Can a synchronized method be used to protect a DB transaction between two JVM processes?

**Answer:** No; a monitor only coordinates threads within one JVM runtime; separate database/distributed coordination is needed.

**Question 25.** What does ReentrantWaitDemo prove beyond Thread.holdsLock?

**Answer:** It shows that a thread holding the same monitor twice can still wait, the notifier acquires the monitor and signals, and the waiter reacquires before continuing. holdsLock only confirms ownership, and cannot measure depth.

## 23. Monitor Design and Debugging Workflow

1. **Identify the state to protect** and which threads can access it concurrently.
2. **Choose the right lock identity**: this, Class monitor, or private final Object, and use it consistently.
3. **Design small critical sections**: protect invariants, avoid unnecessary I/O/blocking while holding a monitor.
4. **Consider reentrancy** for nested calls/recursion: the same owner thread can reacquire, but balanced releases are required.
5. **Ensure visibility through the same lock** or another JMM-compliant synchronization scheme.
6. **With wait/notify**, have an explicit condition predicate, use while, handle interruption, and do not confuse notify with immediate unlock.
7. **Limit multi-lock nested ordering**; if multiple monitors must be used, establish a global order.
8. **Do not arbitrarily expose lock objects** to code outside the class; avoid interned Strings/boxed caches.
9. **Test correctness** with multiple threads and assertions; do not write tests relying on Thread.sleep/coincidental scheduling.
10. **Observe in practice** using jcmd Thread.print, jstack/JFR, and ThreadMXBean when contention/deadlock occurs.
11. **Separate bugs from performance**: high mutex contention differs from a race condition, and deadlock differs from a wait-set waiting on a valid condition.
12. **When using virtual threads**, verify the JDK version and monitor improvements.
13. **When optimizing**, inspect data structures/lock granularity before changing implementations; preserve exact semantics.
14. **Distinguish source vs. JVM bytecode**: a method's ACC_SYNCHRONIZED differs from a statement's monitorenter/exit.
15. **Clearly document lock owner/state lifecycle**, helping maintainers avoid accidentally adding methods that access state outside the lock discipline.

### Official Documentation

- **Java Language Specification SE 17 — §17.1 Synchronization:** https://docs.oracle.com/javase/specs/jls/se17/html/jls-17.html#jls-17.1
- **Java Language Specification SE 17 — §17.2 Wait Sets and Notification:** https://docs.oracle.com/javase/specs/jls/se17/html/jls-17.html#jls-17.2
- **JLS SE 17 — §17.4.5 Happens-before Order:** https://docs.oracle.com/javase/specs/jls/se17/html/jls-17.html#jls-17.4.5
- **JVMS SE 17 — §2.11.10 Synchronization:** https://docs.oracle.com/javase/specs/jvms/se17/html/jvms-2.html#jvms-2.11.10
- **JVMS SE 17 — monitorenter/monitorexit instructions:** https://docs.oracle.com/javase/specs/jvms/se17/html/jvms-6.html#jvms-6.5.monitorenter
- **Java SE 17 API — Object.wait/notify:** https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/lang/Object.html
- **Java SE 17 API — Thread.holdsLock:** https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/lang/Thread.html#holdsLock(java.lang.Object)
- **Java SE 17 API — Thread.State:** https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/lang/Thread.State.html
- **Java SE 17 API — ReentrantLock:** https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/concurrent/locks/ReentrantLock.html
- **Oracle Java SE 17 — jcmd:** https://docs.oracle.com/en/java/javase/17/docs/specs/man/jcmd.html
- **OpenJDK JEP 374 — Disable and Deprecate Biased Locking:** https://openjdk.org/jeps/374
- **OpenJDK JEP 491 — Synchronize Virtual Threads without Pinning:** https://openjdk.org/jeps/491

**Conclusion:** Java monitors are tied to **object identity**. Only one thread owns a monitor at a time, but **that same owner can reenter as many times as needed**, and the lock is truly released when the number of exits balances the number of entries. Instance synchronized locks **this**, static synchronized locks the **Class object**, and explicit synchronized locks the specified object. **wait()** temporarily releases all reentrant holds of the receiver and reacquires them before completing; **notify() does not immediately transfer the lock**. To write correct concurrent code, keep lock identity consistent, use a while-predicate for condition waits, and leverage happens-before on **the same monitor**.
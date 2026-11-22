# Instance Locks vs. Class Locks in Java Synchronization

## 1. Using `synchronized` Does Not Necessarily Mean Using the Same Lock

In Java, every object has an **intrinsic lock**, also called a **monitor**. When a thread enters a `synchronized` method or block, it must acquire the **corresponding monitor**. Two threads only exclude each other when they require **the same monitor**, not simply because both pieces of code use the `synchronized` keyword.

Two common forms:

- **Instance lock:** `synchronized` on an instance method or `synchronized(this)`. The monitor belongs to the **specific object** on which the method is called.
- **Class lock:** `static synchronized` or `synchronized(MyType.class)`. The monitor belongs to the **`Class` object representing `MyType`** in the JVM.

Therefore, two objects of the same class normally have **two different instance monitors**, whereas `static synchronized` methods declared on the same class are coordinated through **the same class monitor**.

Conceptual example:

```text
Counter a = new Counter()       Counter b = new Counter()
       │                               │
       ▼                               ▼
  monitor of a                    monitor of b
       │                               │
 a.increment()                   b.increment()
       └─── two different monitors ────┘

                  Counter.class
                        │
                  class monitor
                        │
                 Counter.reset()
                 Counter.nextId()
       (static synchronized on same class)
```

**Key takeaway:** synchronization is a *protocol about lock identity*. The `synchronized` keyword alone does not serialize all operations within the same class.

This topic belongs to **general Java concurrency and synchronization**; it is framework-independent.

## 2. Four Syntactic Forms and Their Corresponding Monitors

Suppose a class is named `Ledger`:

```java
class Ledger {
    synchronized void instanceMethod() {
        // Holds the monitor of this.
    }

    void instanceBlock() {
        synchronized (this) {
            // Holds the exact same monitor of this.
        }
    }

    static synchronized void staticMethod() {
        // Holds the monitor of Ledger.class.
    }

    static void classBlock() {
        synchronized (Ledger.class) {
            // Holds the exact same monitor of Ledger.class.
        }
    }
}
```

This is an **illustrative class definition snippet**, not a standalone program. Two pairs are equivalent in terms of **monitor identity**:

1. `synchronized void instanceMethod()` corresponds to locking `this` inside an instance method.
2. `static synchronized void staticMethod()` corresponds to locking `Ledger.class` when executing the body of a static method declared on `Ledger`.

However, the lock-holding scope of a `synchronized` method is **the entire method invocation**, whereas a `synchronized(lock)` block only holds the lock inside the block. The two forms can differ in **critical section width**, even when using the same monitor.

Summary table:

| Syntax | Monitor acquired | When can two calls run concurrently? |
| --- | --- | --- |
| `synchronized void work()` | `this` | On two different instances |
| `synchronized (this) { ... }` | `this` | When threads use two different instances |
| `static synchronized void work()` | `DeclaringClass.class` | If they are on two different declaring classes with different class monitors |
| `synchronized (Ledger.class) { ... }` | `Ledger.class` | If the other code uses a different monitor |
| `synchronized (sharedLock) { ... }` | The exact object referenced by `sharedLock` | If `sharedLock` in the two calls refers to two different objects |

`Ledger.class` is a `java.lang.Class` object, so it is also an object with an intrinsic monitor like any other object. It is not a "whole-JVM lock." A class can be loaded by multiple class loaders; each runtime definition has its own `Class` object. Normally, within an application using the same class loader, every reference to `Ledger.class` refers to the same monitor.

### 2.1. How many locks are there actually?

With:

```java
Ledger a = new Ledger();
Ledger b = new Ledger();
```

there are at least three objects that can serve as monitors of interest in this article:

- `a`: the monitor of the first instance.
- `b`: the monitor of the second instance.
- `Ledger.class`: the monitor of `Ledger`'s `Class` object.

Since `a != b`, holding monitor `a` does not automatically lock `b`. `a` and `Ledger.class` are also two distinct objects, so holding monitor `a` **does not** prevent another thread from acquiring `Ledger.class`, unless that thread has to wait under a different protocol.

## 3. Runnable Example: Identifying Monitors with `Thread.holdsLock`

The static method `Thread.holdsLock(object)` reports whether the **current thread** currently owns the intrinsic monitor of that object. It can be used to confirm the difference without depending on thread scheduling order.

Create the file `MonitorIdentityDemo.java`:

```java
public class MonitorIdentityDemo {
    synchronized void checkInstance() {
        System.out.println("instance owns this="
                + Thread.holdsLock(this));
        System.out.println("instance owns class="
                + Thread.holdsLock(MonitorIdentityDemo.class));
    }

    static synchronized void checkClass() {
        System.out.println("static owns class="
                + Thread.holdsLock(MonitorIdentityDemo.class));
    }

    void checkExplicitBlocks() {
        synchronized (this) {
            System.out.println("block owns this="
                    + Thread.holdsLock(this));
        }
        synchronized (MonitorIdentityDemo.class) {
            System.out.println("block owns class="
                    + Thread.holdsLock(MonitorIdentityDemo.class));
        }
    }

    public static void main(String[] args) {
        MonitorIdentityDemo demo = new MonitorIdentityDemo();
        demo.checkInstance();
        checkClass();
        demo.checkExplicitBlocks();
    }
}
```

Commands to run with JDK 17+:

```bash
javac MonitorIdentityDemo.java
java MonitorIdentityDemo
```

Output:

```text
instance owns this=true
instance owns class=false
static owns class=true
block owns this=true
block owns class=true
```

These lines show **which monitor belongs to the current thread**:

- `checkInstance()` is an instance synchronized method, so it holds `demo` (`this`), and does not automatically hold `MonitorIdentityDemo.class`.
- `checkClass()` is a static synchronized method, so it holds `MonitorIdentityDemo.class`.
- `checkExplicitBlocks()` demonstrates that both monitors can also be acquired using synchronized blocks.

Here all calls run sequentially on `main` for deterministic observation; the example is not intended to measure throughput or concurrent thread execution. In a large application, `Thread.holdsLock` is useful for assertions or diagnostics, but should not be used to "check and skip locking" when updating state.

## 4. Instance Lock: Isolating Synchronization per Object

A `synchronized` instance method uses the monitor of the **receiver** (the object to the left of the dot at the call site). If thread A calls `a.deposit(...)` and thread B calls `a.withdraw(...)` where both methods are synchronized, they contend for **the same monitor `a`**. Both cannot execute their protected bodies simultaneously on the same `a`.

Conversely, when thread A calls `a.deposit(...)` and thread B calls `b.deposit(...)` with `a != b`, the two threads acquire **two different monitors**. They can make progress concurrently. This is usually desirable if `a` and `b` hold independent data.

Create the file `PerInstanceCounterDemo.java`:

```java
import java.util.concurrent.CountDownLatch;

public class PerInstanceCounterDemo {
    private static final class Counter {
        private int value;

        synchronized void increment() {
            value++;
        }

        synchronized int get() {
            return value;
        }
    }

    public static void main(String[] args) throws InterruptedException {
        Counter a = new Counter();
        Counter b = new Counter();
        CountDownLatch begin = new CountDownLatch(1);

        Thread first = new Thread(() -> {
            try {
                begin.await();
                for (int i = 0; i < 1_000; i++) {
                    a.increment();
                }
            } catch (InterruptedException e) {
                Thread.currentThread().interrupt();
            }
        }, "first");

        Thread second = new Thread(() -> {
            try {
                begin.await();
                for (int i = 0; i < 1_000; i++) {
                    b.increment();
                }
            } catch (InterruptedException e) {
                Thread.currentThread().interrupt();
            }
        }, "second");

        first.start();
        second.start();
        begin.countDown();
        first.join();
        second.join();

        System.out.println("a=" + a.get());
        System.out.println("b=" + b.get());
    }
}
```

```bash
javac PerInstanceCounterDemo.java
java PerInstanceCounterDemo
```

Output when there is no external interrupt:

```text
a=1000
b=1000
```

Each `Counter` object protects **its own `value` field**. `a.increment()` and `b.increment()` do not contend on the same monitor, avoiding serialization of truly independent updates. `join()` ensures `main` reads the results after both workers finish.

Note: the example does not guarantee that the two threads always run in parallel on two CPU cores. It only shows that they are **not forced into mutual exclusion by a shared instance lock**.

### 4.1. Instance lock scope must match state scope

If `value` is a separate instance field for each `Counter`, locking per instance makes sense. However, if multiple instances actually reference an external mutable object—for example, sharing a static `HashMap`—then two different instance locks are **not enough** to protect the shared structure.

Rule: **the lock must be tied to the data/invariant unit being protected**, not just to the method name.

## 5. Class Lock: Coordinating Shared State at the Class Level

A `static` field is shared across all instances belonging to the same runtime definition of the class. If multiple threads access this field, per-instance locking may fail to protect it because threads can use different instances.

Risky example:

```java
class TicketIssuer {
    private static int nextId;

    synchronized int issue() {
        return ++nextId;
    }
}
```

This is an illustrative class definition snippet. `issue()` is an **instance synchronized method**, so:

- `issuerA.issue()` holds the lock of `issuerA`.
- `issuerB.issue()` holds the lock of `issuerB`.
- Both modify **the same `TicketIssuer.nextId`** without sharing a monitor.
- `++nextId` is a read-modify-write operation, which can suffer lost updates; another thread may observe incorrect values due to missing synchronization.

A straightforward approach if the requirement is a shared ID issuer within the JVM:

```java
class TicketIssuer {
    private static int nextId;

    static synchronized int issue() {
        return ++nextId;
    }
}
```

Now calls to `TicketIssuer.issue()` use the `TicketIssuer.class` monitor. If all related read and update paths follow the same lock, `nextId` is protected within the corresponding JVM/class loader scope.

Or using a block:

```java
class TicketIssuer {
    private static int nextId;

    static int issue() {
        synchronized (TicketIssuer.class) {
            return ++nextId;
        }
    }
}
```

Both are **illustrative class snippets**, not Java programs with `main`. In practice, if you only need an atomic counter, `AtomicInteger.incrementAndGet()` can be used; however, if you must protect **multiple related fields**, you must define a critical section or snapshot covering the entire invariant.

### 5.1. A class lock does not "lock all objects of the class"

While one thread holds `TicketIssuer.class`, another thread can still enter `issuer.synchronizedInstanceMethod()` because that method requires `issuer`'s monitor, not `TicketIssuer.class`.

Similarly, two static synchronized methods belonging to **two different classes** will not automatically exclude each other just because they run in the same JVM. Monitor identity—not the `static` keyword—determines contention.

## 6. Deterministic Lost Update Demo When Locking at the Wrong Scope

The snippet below has two threads using **two different instances** to modify the same `static volatile int` field. Latches force both threads to read the old value before either writes, demonstrating that putting `synchronized` on an instance method **does not protect shared static state**.

Create the file `WrongScopeLockDemo.java`:

```java
import java.util.concurrent.CountDownLatch;

public class WrongScopeLockDemo {
    private static volatile int sharedCounter;

    synchronized void badIncrement(
            CountDownLatch bothRead,
            CountDownLatch allowWrite) {
        int oldValue = sharedCounter;
        bothRead.countDown();
        try {
            allowWrite.await();
        } catch (InterruptedException e) {
            Thread.currentThread().interrupt();
            return;
        }
        sharedCounter = oldValue + 1;
    }

    static synchronized void safeIncrement() {
        sharedCounter++;
    }

    public static void main(String[] args) throws InterruptedException {
        WrongScopeLockDemo a = new WrongScopeLockDemo();
        WrongScopeLockDemo b = new WrongScopeLockDemo();
        CountDownLatch bothRead = new CountDownLatch(2);
        CountDownLatch allowWrite = new CountDownLatch(1);

        Thread first = new Thread(
                () -> a.badIncrement(bothRead, allowWrite));
        Thread second = new Thread(
                () -> b.badIncrement(bothRead, allowWrite));

        first.start();
        second.start();
        bothRead.await();
        allowWrite.countDown();
        first.join();
        second.join();
        System.out.println("wrong lock result=" + sharedCounter);

        sharedCounter = 0;
        Thread safeA = new Thread(WrongScopeLockDemo::safeIncrement);
        Thread safeB = new Thread(WrongScopeLockDemo::safeIncrement);
        safeA.start();
        safeB.start();
        safeA.join();
        safeB.join();
        System.out.println("class lock result=" + sharedCounter);
    }
}
```

```bash
javac WrongScopeLockDemo.java
java WrongScopeLockDemo
```

Output when there is no external interrupt:

```text
wrong lock result=1
class lock result=2
```

**Step-by-step analysis:**

1. `first` holds monitor `a`; `second` holds monitor `b`. Since `a != b`, they do not prevent each other from entering `badIncrement`.
2. Both read `sharedCounter = 0` before `main` signals `allowWrite`. The latches make this outcome deterministic.
3. Each thread saves `oldValue = 0` and then writes `oldValue + 1`. The final result is `1` even though two increments were requested.
4. `main` waits for `join()` and resets `sharedCounter = 0` to start the second test.
5. Both calls to `safeIncrement()` contend for **the `WrongScopeLockDemo.class` monitor**. Because the entire read-modify-write is inside one class critical section, both increments are preserved, resulting in `2`.

The `sharedCounter` field is `volatile` in this example to avoid shifting focus to stale reads, **but `volatile` does not make `x++` atomic**. If `badIncrement` were changed to a `static synchronized` method on the class, the two calls would wait on the same class monitor, eliminating the lost-update interleaving above.

The general lesson is not "every static field must be locked with the class monitor"; what is required is that **all threads agree on the same synchronization mechanism protecting the shared state**. A dedicated `private static final Object LOCK` or `AtomicInteger` can also be appropriate depending on the invariant.

## 7. Instance Locks and Class Locks Are Independent of Each Other

A thread holding an instance lock **does not** mean it also holds the class lock. The reverse is also true. This can be demonstrated programmatically without guessing log order across threads.

Create the file `IndependentMonitorsDemo.java`:

```java
import java.util.concurrent.CountDownLatch;

public class IndependentMonitorsDemo {
    synchronized void holdInstance(
            CountDownLatch entered,
            CountDownLatch release) {
        entered.countDown();
        try {
            release.await();
        } catch (InterruptedException e) {
            Thread.currentThread().interrupt();
        }
    }

    static synchronized void useClassMonitor() {
        System.out.println("class method can enter");
    }

    public static void main(String[] args) throws InterruptedException {
        IndependentMonitorsDemo object = new IndependentMonitorsDemo();
        CountDownLatch entered = new CountDownLatch(1);
        CountDownLatch release = new CountDownLatch(1);

        Thread holder = new Thread(() ->
                object.holdInstance(entered, release));
        holder.start();
        entered.await();

        useClassMonitor();  // Does not need to wait for the object's monitor.
        release.countDown();
        holder.join();

        System.out.println("holder finished");
    }
}
```

```bash
javac IndependentMonitorsDemo.java
java IndependentMonitorsDemo
```

Output when there is no external interrupt:

```text
class method can enter
holder finished
```

The `holder` thread is holding `object`'s monitor and waiting on the `release` latch. `main` calls the static synchronized method and acquires `IndependentMonitorsDemo.class`'s monitor **before** signaling `release`. If the two methods contended for the same monitor, this arrangement would hang; it completes because the monitors are different.

This program is an isolated test of lock identity. You should not introduce deadlock-prone latch waits just to "test" a production system. In tests, use `await(timeout)` and fail clearly if no signal arrives.

## 8. One Object/Thread Can Hold Both Monitors, but Not Automatically

Inside an instance method, you are allowed to write:

```java
class GlobalLedger {
    private static int total;
    private int local;

    synchronized void addToBoth() {
        synchronized (GlobalLedger.class) {
            local++;
            total++;
        }
    }
}
```

This is illustrative code. When `object.addToBoth()` is called, the thread acquires `object`'s monitor first, then attempts to acquire `GlobalLedger.class`'s monitor. It owns **both** inside the inner block. Upon exiting the inner block, it releases the class monitor while still holding the instance monitor until the instance method returns.

This can be reasonable if the operation genuinely needs to protect an invariant spanning instance state and class state, but it creates a **lock-ordering deadlock** risk if another code path acquires the class monitor first and then tries to acquire the instance monitor.

Alternatively, you can synchronize on **a single dedicated lock** instead of holding two locks:

```java
class GlobalLedger {
    private static final Object GLOBAL_LOCK = new Object();
    private static int total;
    private int local;

    void addToBoth() {
        synchronized (GLOBAL_LOCK) {
            local++;
            total++;
        }
    }
}
```

This is still illustrative code, but every instance uses `GLOBAL_LOCK`, protecting the joint update. The trade-off is that updates on different instances are serialized even when data could be partitioned into independent regions. You must weigh invariant boundaries against contention.

**Do not mechanically put `synchronized` on every method:** protecting each object or a shared state properly is the right requirement; holding locks more broadly than necessary can slow down the application.

## 9. Deadlock When Mixing Instance and Class Locks

Suppose there are two execution paths:

```text
Thread A: holds instance lock -> waits for class lock
Thread B: holds class lock    -> waits for instance lock

A waits for B to release class lock
B waits for A to release instance lock
=> wait cycle, potential deadlock
```

A risky structural example (illustrative, **not a standalone program and should not be run to induce deadlock**):

```java
class Risky {
    synchronized void instanceThenClass() {
        synchronized (Risky.class) {
            // Shared update.
        }
    }

    static void classThenInstance(Risky target) {
        synchronized (Risky.class) {
            synchronized (target) {
                // Another update.
            }
        }
    }
}
```

If Thread A has acquired `target`'s monitor in `instanceThenClass`, while Thread B holds `Risky.class` in `classThenInstance`, each can end up waiting for the monitor held by the other.

**How to prevent it:**

1. Avoid holding multiple monitors at the same time when the design allows.
2. If multiple locks must be held, enforce **a consistent lock ordering** across all code—for example, always acquire the class lock before the instance lock.
3. Avoid invoking callbacks, plugins, or methods that may run untrusted/uncontrolled code while holding a lock; they might acquire another lock in the reverse order.
4. Do not rely on `Thread.sleep()` to prevent deadlock. Sleeping does not release monitors.
5. Use thread dumps, Java Flight Recorder, or deadlock diagnostic tools when needed. Tools only help detect deadlocks; the primary defense remains designing lock ordering.

A deadlock caused by two intrinsic monitors cannot be fixed by "retrying `synchronized` with a timeout" because the language does not provide a try-lock operation for `synchronized`. If the business logic requires a lock acquisition timeout, consider `ReentrantLock.tryLock(timeout, unit)` along with an appropriate rollback protocol and lock ordering.

## 10. Reentrancy: The Same Thread Can Re-enter a Monitor It Already Holds

Java's intrinsic locks are **reentrant**. If a thread already holds the `this` monitor, it can call another synchronized instance method on **the same object** without blocking itself.

```java
class ReentrantCounter {
    private int count;

    synchronized void addTwo() {
        increment();
        increment();
    }

    synchronized void increment() {
        count++;
    }

    synchronized int value() {
        return count;
    }
}
```

This is an illustrative class definition snippet. When calling `obj.addTwo()`, the thread already holds `obj`'s monitor and can call `obj.increment()` twice. The monitor tracks the reentrancy count; only when all corresponding synchronized regions have exited is the monitor released for other threads.

Similarly, a static synchronized method of `ReentrantCounter` can call another static synchronized method on the same `ReentrantCounter.class` without deadlocking itself.

However, **reentrancy applies only to the same monitor and the same thread**. Holding an instance monitor does not mean "re-entering" the class monitor; if the next method requires the class monitor, that is still acquiring a **different monitor** that could be held by another thread.

When a synchronized block or method throws an exception, the JVM still releases the monitor when exiting the method/block appropriately; you do not need to write `unlock()` manually for intrinsic locks. This differs from `ReentrantLock`, where `try/finally` is required to call `unlock()`.

## 11. Java Memory Model: happens-before Requires the Same Monitor

`synchronized` provides more than mutual exclusion. The JMM also specifies:

> An **unlock** action on monitor M *happens-before* every subsequent **lock** action on M in the synchronization order.

This ensures a reading thread sees the modifications a writing thread made before releasing **that exact same monitor**.

Example with an instance monitor:

```java
class Status {
    private int value;

    synchronized void set(int next) {
        value = next;
    }

    synchronized int get() {
        return value;
    }
}
```

On the same `status` object, if thread A's call to `status.set(42)` completes before thread B subsequently acquires `status`'s monitor to call `status.get()`, the synchronization order supports B observing the written value. If other writers update it afterward, B may see a different value consistent with the actual order; you cannot claim every `get` will return `42` while ignoring other writes.

**Wrong monitor, missing guarantee:**

```java
class BadStatus {
    private static int value;

    synchronized void set(int next) {
        value = next;
    }

    synchronized int get() {
        return value;
    }
}
```

If Thread A calls `a.set(42)` and Thread B calls `b.get()` with `a != b`, the two methods lock **two different monitors** even though they read/write **the same static field**. There is no unlock/lock relationship on the same monitor between these two calls. Having the same `synchronized` keyword is not enough to conclude that the static field is safely published.

Nor should you infer that `volatile` or `AtomicInteger` protects multiple related fields as a transaction. They can provide visibility or atomicity per variable/operation, but multi-field invariants require a shared protocol.

## 12. `wait()`, `notify()`, and `notifyAll()` Are Tied to a Specific Monitor

Each object monitor has its own wait set of waiting threads. `wait` and `notify/notifyAll` are methods on `Object`, not "class-wide signals."

Example using an **instance monitor**:

```java
synchronized (this) {
    while (!ready) {
        this.wait();
    }
}
```

Example using a **class monitor**:

```java
synchronized (SignalBus.class) {
    while (!sharedReady) {
        SignalBus.class.wait();
    }
}
```

These are **two separate illustrative snippets**, assuming `ready` and `sharedReady` are properly guarded conditions and `SignalBus` is a declared class. Every `wait()` call requires the current thread to **own the monitor of the exact object on which `wait` is called**. Otherwise, it throws `IllegalMonitorStateException`.

- `this.wait()` releases and waits on **the instance `this` monitor**.
- `SignalBus.class.wait()` releases and waits on **the `SignalBus.class` `Class` object monitor**.
- `this.notifyAll()` **does not** wake up a thread waiting on `SignalBus.class.wait()`, and vice versa.
- After being notified, the thread must reacquire **the exact corresponding monitor** before resuming from `wait`.
- Always check the condition inside a `while` loop to handle spurious wakeups or condition changes before the thread reacquires the monitor.

Do not call `wait/notify` on a monitor just because of "the same class name"; you must match **object identity** across participating threads. For producer/consumer needs, higher-level constructs such as `BlockingQueue` or `Condition` typically reduce protocol errors.

## 13. Inheritance, Method Hiding, and `getClass()`: Subtle Traps

### 13.1. Inherited synchronized instance methods still lock the actual receiver

If class `Base` has `synchronized void work()` and `Derived extends Base`, calling the inherited method on `new Derived()` holds the monitor of **that `Derived` instance**, not `Base.class`. The instance monitor does not change simply because the method was declared in the superclass.

If two different synchronized methods (inherited or declared in the subclass) are called on **the same receiver**, they contend for the same `this` instance monitor.

### 13.2. Static synchronized methods belong to the declaring class of the method

Consider:

```java
class Base {
    static synchronized void baseGlobal() {
        // Base.class monitor.
    }
}

class Derived extends Base {
    static synchronized void derivedGlobal() {
        // Derived.class monitor.
    }
}
```

This is illustrative code. `Base.baseGlobal()` and `Derived.derivedGlobal()` use **two different class monitors**, so they do not automatically exclude each other.

If `Derived` simply inherits the name of a static synchronized method declared in `Base` without declaring a new one, the executed method is still declared by `Base` and locks `Base.class`. Static methods use **hiding**, not polymorphic overriding like instance methods. What matters is the monitor of **the class declaring the static synchronized method being executed**.

### 13.3. `this.getClass()` is not always equal to `DeclaringType.class`

Inside an instance method of `Base`, the expression `this.getClass()` may return `Derived.class` if the receiver is a subclass object. Meanwhile, `Base.class` always refers to `Base`'s class monitor.

Therefore, using:

```java
synchronized (getClass()) {
    // For a subclass, locks the subclass's Class object.
}
```

**is not generally equivalent** to:

```java
synchronized (Base.class) {
    // Always locks Base.class.
}
```

The two snippets above illustrate code inside an instance method of `Base`. If the goal is to protect `static` state declared in `Base`, use `Base.class` or a clearly defined private static lock, rather than `getClass()`, which changes the lock depending on the runtime subclass.

### 13.4. Class loaders create an additional boundary

The same class name does not guarantee the same `Class` object if loaded by two different class loaders. `synchronized(MyType.class)` coordinates threads accessing **the same runtime definition of `MyType`**, not all processes or all class loaders with that name.

Data truly shared outside a single JVM is not protected by `static synchronized` alone. Coordinating across JVMs/processes requires mechanisms at the shared resource layer, such as database transactions, distributed locks, or appropriate protocols—outside the scope of Java intrinsic monitors.

## 14. When to Use Private Monitors Instead of Locking `this` or `Class` Directly

You can choose a **private, final, unexposed** lock:

```java
class Inventory {
    private final Object instanceLock = new Object();
    private static final Object CLASS_LOCK = new Object();

    private int localUnits;
    private static int globalUnits;

    void addLocal(int n) {
        synchronized (instanceLock) {
            localUnits += n;
        }
    }

    static void addGlobal(int n) {
        synchronized (CLASS_LOCK) {
            globalUnits += n;
        }
    }
}
```

This is illustrative code. Advantages:

- `instanceLock` is a separate object per `Inventory`; it protects per-instance state just like locking `this` intends.
- `CLASS_LOCK` is a single object per runtime class definition; it protects shared static state.
- External callers normally **cannot arbitrarily acquire** these private locks, unlike `synchronized(inventory)` or `synchronized(Inventory.class)`, which external code can perform. This reduces the risk of unintended lock sharing.
- You can separate multiple independent state groups under different private locks to reduce contention, though cross-group invariants must be carefully designed.

**Major trap:** do not create `new Object()` on every method call and synchronize on it if the intent is for calls to block each other:

```java
void wrong() {
    Object localLock = new Object();
    synchronized (localLock) {
        // Each call holds a new lock, providing no protection for shared state.
    }
}
```

Similarly, if you want all instances to share one monitor, `private final Object lock` is **not enough** because each instance gets its own lock object. You must use `private static final Object LOCK` or a controlled shared lock object passed in.

Do not use `String` literals, interned objects, boxed integer types, or global objects you do not own as monitors. They can be accidentally shared elsewhere, causing hard-to-trace contention or deadlocks. Choose private lock objects with clear ownership.

## 15. Performance Impact and Contention

**Instance locking** generally allows good concurrency when each instance holds independent state. A service with 1,000 independent accounts can update multiple accounts concurrently instead of waiting on a single class lock. However, if every operation must also update a shared total, a mechanism to protect that total is still needed.

**Class locking** serializes calls that require the same class monitor. It is simple when changes affect class-wide global state, but can become a bottleneck if code holding the lock performs slow I/O, `sleep`, waits on a `Future`, invokes external callbacks, or does heavy CPU work.

Practical guidelines:

- **Keep critical sections as short as possible yet wide enough** to protect the entire invariant; do not over-split and expose intermediate states.
- **Do not sleep inside `synchronized`** to wait for another thread to update state protected by the same monitor: `Thread.sleep()` does not release the monitor. If waiting on a condition via a monitor, use `wait()` properly; in general, consider `java.util.concurrent` primitives.
- **Do not assume a class lock is always slower than an instance lock.** Speed depends on contention, critical section size, JVM, and workload.
- **Use proper benchmarking** such as JMH when measuring throughput/latency; a few `System.nanoTime` calls can be skewed by JIT, warmup, and scheduling.
- **Choose based on data scope**, not on how "global" a method feels. A static method can operate on private state passed into it; an instance method can modify static state. Lock identity must match the invariant, not the method modifier at all costs.

## 16. Rules for Choosing a Lock by Use Case

| State to protect | Typically appropriate lock | Why | Notes |
| --- | --- | --- | --- |
| `balance` belonging to an `Account` object | Instance monitor `this` or private instance lock | Operations on the same account exclude each other; other accounts remain independent | Readers must also use the same lock |
| `static nextId` counter shared across instances | Class monitor, private static lock, or atomic counter | All writers agree on the same mechanism | `synchronized instanceMethod` across multiple instances is insufficient |
| Two instance fields that must change together | One monitor protecting **both updates and snapshot reads** | Prevents reading mixed generations of data | Do not only synchronize individual getters separately |
| A shared mutable static cache | Private static lock or appropriate concurrent collection | Class-level sharing scope | Check whether invariants require atomicity across multiple entries |
| Mutable state inside a singleton service | Lock on that service object may suffice | All callers use the same receiver | Changes if multiple instances later modify a static field |
| Two accounts transferring money as a transaction | Protocol locking both accounts in a fixed order, or a coordinator lock | Must protect invariant across accounts | Avoid deadlocks and partial failures |
| Config replaced as a whole version | Immutable snapshot + `volatile`/`AtomicReference` | Readers can read without a monitor per field | Readers take one snapshot; multiple writers need CAS/lock |

There is no mechanical rule that "every static field must be `static synchronized`" or "every instance field only uses `synchronized` methods." You must identify **where the shared state lives, who can touch it, what invariant must hold, and whether all readers/writers follow the same protocol**.

## 17. Common Pitfalls and How to Spot Them

### 17.1. Each instance locks itself, yet all update a static field

The symptom is a non-static `synchronized` method containing `++staticCounter` that is called on multiple different receivers. This can cause lost updates. Fix it with a class lock/private static lock, `AtomicInteger` if it is just a counter, or redesigning state ownership.

### 17.2. Assuming a static synchronized method and an instance synchronized method block each other

They do not block each other simply because they belong to the same class. The static method locks the `Class` object; the instance method locks the receiver. If both modify the same state, they must use **the same monitor**.

### 17.3. Synchronizing getters individually when a multi-field snapshot is needed

Calling two `synchronized` getters in a row still releases the monitor in between. A writer can update between the two calls. You need a `snapshot()` method that reads the group of fields under **one critical section**, or an atomically published immutable snapshot.

### 17.4. Locking a different object from the one other threads lock

`synchronized(this)` on two different objects uses two monitors. `synchronized(new Object())` on every call also uses different monitors. When the same lock is needed, ensure **the same identity**, not just the same object class/type.

### 17.5. Locking too broadly and calling uncontrolled code

Holding a class monitor while making network calls, database calls, callbacks, or long `join()` calls can block every other thread needing that monitor. Expensive computation should be moved outside the critical section when doing so does not expose an invariant. Check lock ordering on all call paths.

### 17.6. Using `getClass()` and assuming it always locks the base class

For subclasses, `getClass()` returns the runtime class. If you want to lock the base class's static state, reference `Base.class` directly or the base's private static lock.

### 17.7. Overlooking deadlock when using two monitors

Thread A acquires instance then class; Thread B acquires class then instance. Establish a global order for acquiring multiple locks, or reduce to a single lock protecting the required invariant.

### 17.8. Confusing `volatile` with a lock

`volatile` provides visibility/ordering for that variable, but does not lock a read-modify-write such as `counter++`, let alone make multiple fields transactional. Use `synchronized`, atomic operations, or another appropriate construct.

## 18. Self-Check Exercises

**Q1.** Two objects `a` and `b` of the same class have a method `synchronized void f()`. Thread A calls `a.f()`, and Thread B calls `b.f()`. Must the two threads enter the method one after the other?

**Answer:** No. Each method acquires the monitor of its receiver; since `a != b`, they are two different monitors. They can run concurrently unless another synchronization mechanism prevents it.

**Q2.** What object does `static synchronized void g()` lock?

**Answer:** The monitor of the `Class` object representing the class **that declares the executing `g` method**. For example, `Ledger.g()` declared in `Ledger` locks `Ledger.class`, not an instance of `Ledger`.

**Q3.** Thread A is inside `synchronized(a)`, and Thread B wants to call `static synchronized h()` on class `A`. Do they block each other?

**Answer:** Not if `a` is a normal instance of `A`: `a` and `A.class` are different monitors. If B's code also needs another monitor currently held, it could still wait for that separate reason.

**Q4.** Why can `synchronized void inc() { ++sharedStatic; }` be wrong when used across multiple instances?

**Answer:** Each instance locks itself, yet all modify the same static field. Two threads using two instances do not block each other, so the read-modify-write can lose updates.

**Q5.** A thread holds `Ledger.class` and then calls a synchronized instance method on `ledger`. Is that guaranteed to be a reentrant acquisition?

**Answer:** No. These are two different monitors. Reentrancy only applies when the thread reacquires **the same monitor** it already owns.

**Q6.** Are `synchronized(Base.class)` and `synchronized(this.getClass())` always the same inside a method of `Base`?

**Answer:** No. If the receiver is `Derived extends Base`, `this.getClass()` can be `Derived.class`. Those are two different class monitors.

**Q7.** If all writers acquire the class monitor, while readers only acquire an instance monitor to read a static field, is happens-before guaranteed through the locks?

**Answer:** Not from those two synchronized regions alone. Unlock/lock must be on the same monitor to establish the corresponding synchronization edge; readers need the same class lock or another publication mechanism with a clear contract.

**Q8.** When transferring money between two different `Account` objects, is locking only the source account enough?

**Answer:** Usually not if the operation updates both accounts and requires an invariant across them. You need a protocol that protects both objects in a deadlock-free order, or a coordinator lock with all read/write APIs following the same contract.

## 19. Summary

An **instance lock** is the monitor of **a specific object**: `synchronized instanceMethod()` and `synchronized(this)` lock the receiver. A **class lock** is the monitor of a **`Class` object**: `static synchronized staticMethod()` and `synchronized(DeclaringClass.class)` lock a specific class definition. Two instances have two different monitors; an instance monitor and a class monitor are also distinct.

Safety does not come from "putting `synchronized` everywhere," but from ensuring **all related operations protect an invariant using the right monitor or a single consistent synchronization protocol**. When choosing a lock, identify the actual shared state scope, reader/writer alignment, happens-before relationships, contention level, and lock acquisition order to avoid deadlocks. That is the foundation for using synchronization correctly in Java.

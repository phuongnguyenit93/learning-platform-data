# Avoid Locking on String Literals or Public Objects in Java

`synchronized` uses the **monitor attached to a specific object**. If the lock object is accessible to other components, they can also acquire that exact monitor and block your code. Two common design mistakes are locking on a **String literal**, which can be interned and shared, or locking on a **public object**, which allows callers to actively hold an internal monitor.

This lesson belongs to the **Synchronization** section in **general Java concurrency (Java 17+)**. It only covers the Java language and standard library, without going into Spring-specific mechanisms.

Objectives: understand monitor identity, why String literals are shared, the risks of public locks and `this`/class monitors; create properly scoped `private final Object` locks; recognize contention/deadlock, ensure all readers/writers use the same lock, and avoid modifying an existing API in a way that breaks its synchronization contract.

## 1. The Monitor of synchronized Is Object Identity

A synchronized block in Java has the form:

~~~java
// Illustrative code: lock has already been declared.
synchronized (lock) {
    // Critical section uses the monitor of the object referenced by lock.
}
~~~

When a thread enters the block, it **acquires the monitor** of the object. When it exits the block, even due to an exception, the monitor is **released**. Another thread that wants to enter a `synchronized` block using the **exact same object** must wait for the monitor to be released.

Locks are distinguished by **reference identity** (`==`), not by `equals()`, hash code, or variable name. Two references pointing to the same object use the same monitor; two different objects, even with identical contents, do not automatically share a monitor.

~~~java
Object a = new Object();
Object b = a;
Object c = new Object();

System.out.println(a == b); // true
System.out.println(a == c); // false
~~~

This is an illustrative snippet demonstrating identities, not a standalone runnable file.

### Why Do Locks Matter for Memory?

If all accesses to an invariant use the **same monitor**:

- **Mutual exclusion:** only one thread holds the monitor at a time, so two critical sections using the same monitor do not interleave.
- **Visibility and ordering:** an unlock of monitor `m` *synchronizes-with* a subsequent lock on the same monitor `m` according to the Java Memory Model. Combined with program order and the transitivity of *happens-before*, a thread that acquires the lock later can rely on the writes performed by the previous thread within the synchronized scope.

Using two different monitors will **not protect the same invariant** if two threads update the same data. Conversely, accidentally using **one shared monitor** for two independent operations can cause unnecessary contention.

## 2. String Literals Can Point to the Same Global Object

String literals in Java are **interned**; literals with the same content can point to the same `String` instance, even if they are located in unrelated classes. A String is immutable, yet it is still an object with a monitor; **immutability of content does not make it a private lock**.

Standalone runnable Java 17+ example:

~~~java
// StringLiteralIdentityDemo.java
public class StringLiteralIdentityDemo {
    public static void main(String[] args) {
        String first = "shared-lock";
        String second = "shared-lock";
        String constantExpression = "shared-" + "lock";
        String distinct = new String("shared-lock");

        System.out.println("same literal: " + (first == second));
        System.out.println("constant expression: " +
            (first == constantExpression));
        System.out.println("new String same object: " +
            (first == distinct));
        System.out.println("intern returns literal: " +
            (first == distinct.intern()));
    }
}
~~~

~~~bash
javac StringLiteralIdentityDemo.java
java StringLiteralIdentityDemo
~~~

Stdout:

~~~text
same literal: true
constant expression: true
new String same object: false
intern returns literal: true
~~~

Explanation:
- Two identical literals point to the same interned object.
- The constant concatenation `"shared-" + "lock"` is a constant expression, compiled into the corresponding literal.
- `new String(...)` creates a separate String object, even though the content is equal.
- `intern()` returns the canonical reference for the interned string.

### Two Unrelated Classes Can Still Block Each Other

~~~java
// Two illustrative code snippets in two different classes.
// Class A:
synchronized ("CACHE_LOCK") {
    updateCache();
}

// Class B:
synchronized ("CACHE_LOCK") {
    writeAuditLog();
}
~~~

Two blocks with the same literal `"CACHE_LOCK"` can **contend for the same monitor**, even though `updateCache()` and `writeAuditLog()` are independent. If B holds the lock for a long time, A must wait. If other locks are already held, unintended wait edges can also contribute to a deadlock.

**An easily overlooked mistake:** declaring `private static final String LOCK = "CACHE_LOCK";` is **not enough**. The field is private, but **the String object it points to is still an interned literal that can be obtained using the same string**. `final` only prevents the field's reference from being reassigned.

You should not fix this by using `new String("CACHE_LOCK")` as a pattern: the new object has a distinct identity in simple cases, but the `String` type does not communicate locking intent, can be assigned elsewhere, and easily misleads readers into confusing equality with identity. Using `private final Object` or `private static final Object` as a dedicated monitor is easier to control.

## 3. Public Objects Give External Code Permission to Hold Internal Monitors

Pattern to avoid:

~~~java
// Illustrative code of an API lacking encapsulation:
public class Counter {
    public static final Object LOCK = new Object();
    private static int value;

    public static void increment() {
        synchronized (LOCK) {
            value++;
        }
    }
}
~~~

External code can do:

~~~java
synchronized (Counter.LOCK) {
    // Slow work or waiting on some arbitrary condition.
}
~~~

From the moment external code holds the monitor until it releases it, every `Counter.increment()` call will have to wait. `public static final` keeps the identity stable, but **does not prevent callers from obtaining the object**. Exposing a monitor creates an API dependency on progress and can cause lock contention, application-level DoS, or wait cycles.

Similar ways of exposing a lock: a `public`/`protected` field holding the lock, a getter returning the lock reference, passing the lock into a callback or uncontrolled component, or using a publicly exposed instance object of the class as a monitor.

### Deterministic Example: External Code Interfering with Progress

The program below intentionally provides a public lock. Two `CountDownLatch` instances establish a clear ordering, avoiding `Thread.sleep` to guess scheduling.

~~~java
// PublicLockInterferenceDemo.java
import java.util.concurrent.CountDownLatch;

public class PublicLockInterferenceDemo {
    static class UnsafeCounter {
        public final Object lock = new Object();
        private int value;

        void increment() {
            synchronized (lock) {
                value++;
            }
        }

        int valueAfterCoordination() {
            return value;
        }
    }

    public static void main(String[] args) throws InterruptedException {
        UnsafeCounter counter = new UnsafeCounter();
        CountDownLatch outsideHasLock = new CountDownLatch(1);
        CountDownLatch release = new CountDownLatch(1);

        Thread outside = new Thread(() -> {
            synchronized (counter.lock) {
                outsideHasLock.countDown();
                try {
                    release.await();
                } catch (InterruptedException e) {
                    Thread.currentThread().interrupt();
                }
            }
        });

        outside.start();
        outsideHasLock.await();

        Thread worker = new Thread(counter::increment);
        worker.start();

        System.out.println("Before release: " +
            counter.valueAfterCoordination());
        release.countDown();

        outside.join();
        worker.join();
        System.out.println("After release: " +
            counter.valueAfterCoordination());
    }
}
~~~

~~~bash
javac PublicLockInterferenceDemo.java
java PublicLockInterferenceDemo
~~~

Stdout:

~~~text
Before release: 0
After release: 1
~~~

Key guarantee: `main` only starts `worker` **after** the external thread confirms it has acquired the monitor. `worker` cannot update `value` before the monitor is released. `main` reads `value == 0` before opening the latch; after `outside.join()` and `worker.join()`, the value is 1. The `join()` calls also provide visibility guarantees for the final read.

This is an **example that intentionally exposes the lock**, not a recommended API for production. The getter `valueAfterCoordination()` is only read at these coordination points; in real code, reads and updates to an invariant must be synchronized using the same protocol.

## 4. synchronized(this) and synchronized Instance Methods

A method:

~~~java
public synchronized void update() {
    // ...
}
~~~

uses the monitor of `this`, which is equivalent in terms of monitor to:

~~~java
public void update() {
    synchronized (this) {
        // ...
    }
}
~~~

The two snippets above are illustrative code showing **two ways of writing it**, not standalone programs. If the object instance has been handed out to a caller, the caller can also call `synchronized(instance)`. Thus, a **public synchronized method** can be blocked by an external caller holding the object's monitor.

This is **not always wrong**: some APIs intentionally publish their synchronization protocol through the object instance. However, if acquiring the lock is strictly an **implementation detail** protecting private data, you should use a separate lock object and never return it to callers.

Also, do not mistake `final class` for a private monitor: `final` prevents subclassing, not external code from holding the monitor of a published instance.

## 5. A Commonly Suitable Design: private final Object

For state tied to an instance:

~~~java
private final Object lock = new Object();
~~~

For `static` state shared across a class:

~~~java
private static final Object LOCK = new Object();
~~~

All three parts serve a purpose:
- `private`: external code cannot obtain the lock through the normal API.
- `final`: the field cannot be reassigned a new reference, ensuring every locking site uses the **same stable identity**.
- `new Object()`: creates an object dedicated solely to acting as a monitor, which cannot be accidentally shared via interning or a shared singleton.

### Java 17+ Example: Thread-Safe Counter with a Private Lock

~~~java
// PrivateLockCounterDemo.java
public class PrivateLockCounterDemo {
    static final class Counter {
        private final Object lock = new Object();
        private int value;

        void increment() {
            synchronized (lock) {
                value++;
            }
        }

        int getValue() {
            synchronized (lock) {
                return value;
            }
        }
    }

    public static void main(String[] args) throws InterruptedException {
        Counter counter = new Counter();
        Runnable add = () -> {
            for (int i = 0; i < 1000; i++) {
                counter.increment();
            }
        };

        Thread a = new Thread(add);
        Thread b = new Thread(add);
        a.start();
        b.start();
        a.join();
        b.join();

        System.out.println("Count: " + counter.getValue());
    }
}
~~~

~~~bash
javac PrivateLockCounterDemo.java
java PrivateLockCounterDemo
~~~

Stdout:

~~~text
Count: 2000
~~~

Each `Counter` instance has its own monitor. Both `increment()` and `getValue()` use the **same monitor** to protect `value`. A caller holding a `Counter` reference still cannot hold the private monitor through the normal API. `main` calls `join()` on both workers and prints the exact result 2000.

If there is an access path to `value` that does not use the lock or uses a different lock, the design can still be incorrect. A private lock does not automatically solve every race condition.

### Why Shouldn't You Reassign a Lock?

If `lock` is not `final` and is replaced with a new object, thread A may hold the old monitor while thread B acquires the new monitor. In that case, two threads enter a critical section that appears to protect the same data. Keeping a stable identity and never replacing the reference is a fundamental design condition.

## 6. static synchronized and Locking on the Class Object

A `static synchronized` method uses the monitor of the corresponding **class object** (`MyClass.class`), which is distinct from an instance monitor:

~~~java
// Illustration inside class MyClass:
public static synchronized void refresh() {
    // Locks MyClass.class
}
~~~

Equivalent in terms of monitor to:

~~~java
public static void refresh() {
    synchronized (MyClass.class) {
        // ...
    }
}
~~~

The Class object is accessible to other code via the class literal; therefore, external code can also `synchronized(MyClass.class)` and block a `static synchronized` method. All `static synchronized` methods in the same class share the class monitor, even when they protect independent state.

If you only need a lock to protect internal static state, `private static final Object LOCK = new Object()` avoids publishing the monitor. Instance `synchronized` methods typically lock `this`; they **do not automatically synchronize** with `static synchronized` methods.

**Choosing a lock based on invariant scope:**

| State scope | Recommended lock | Why |
| --- | --- | --- |
| Instance fields not shared across objects | `private final Object lock` | Each object has its own monitor |
| Static fields shared within a class | `private static final Object LOCK` | One stable monitor for static state |
| Multiple fields forming a single invariant | One shared lock for all related fields | Prevents readers from seeing half-updated state |
| Two independent groups of state | Two different locks may be used | Avoids contention, though lock ordering must be controlled if nested |

Do not split locks when an invariant requires updating multiple fields atomically; nor should you lock the entire application with a single static lock just because it is simpler to write.

## 7. Types of Objects You Should Not Arbitrarily Use as Monitors

The general rule is: **do not use an object whose ownership, identity, or lifecycle lies outside your synchronization scope**.

| Lock object | Main risk |
| --- | --- |
| `"string literal"` | Interned String can be used by other code |
| `String.intern()` on dynamic input | Monitor is shared by content with other code, with no clear ownership |
| `Boolean.TRUE` / `Boolean.FALSE` | Widely used singletons |
| Boxed values such as `Integer.valueOf(1)` | Shared cache/identity; value-based wrappers are not reliable locks |
| `SomeClass.class` | Publicly accessible Class object |
| `this` when the instance is exposed externally | Callers can hold the instance monitor |
| `public final Object LOCK` | Others know the exact lock identity |
| Objects provided by external libraries | The library may have its own monitor protocol |
| A mutable lock reference that gets reassigned | Threads may end up using different monitors |

For boxed primitives, Java/JDK also issues warnings regarding synchronizing on **value-based classes**. You should not use a numeric or boolean value as a monitor for private state.

### Should You Lock by String Key?

Example:

~~~java
// Illustrative code to avoid:
synchronized (userKey.intern()) {
    updateAccount(userKey);
}
~~~

Keys with the same content share the same lock, even if they come from unrelated code; interning input strings also makes it difficult to manage monitor sharing and data lifecycles. **Do not use `intern()` as a default way to create per-key locks.**

If you genuinely need per-key locking, build a lock object registry with clear **atomic creation, ownership, and lifecycle/eviction**, or use atomic operations on `ConcurrentHashMap` (such as `compute`/`computeIfAbsent` when appropriate for the invariant). Creating a `new Object()` on every call will **not** synchronize two requests with the same key. A custom lock registry must also avoid races when adding/removing locks and avoid holding locks for long periods during I/O.

## 8. Consequences for Liveness and Diagnostics

### Unexpected Contention

A shared literal or public monitor causes unrelated tasks to **queue up** on the same monitor, increasing latency and reducing throughput. A new library adding `synchronized("CACHE_LOCK")` can unintentionally slow down existing code that uses the same string.

In a thread dump, threads waiting to acquire an intrinsic monitor are typically in the `BLOCKED` state. However, **BLOCKED alone does not prove a deadlock**: waiting for a normal locked section is valid. You need to inspect the monitor owner, stack traces, wait duration, and task progress.

### Deadlock from Wait Cycles

Suppose T1 holds monitor A and waits for B, while T2 holds B and waits for A:

~~~text
T1: holds A -> waits for B
T2: holds B -> waits for A
=> Both can wait indefinitely.
~~~

An exposed monitor allows external code to introduce wait edges that the internal component does not control. A private lock reduces unexpected interference, but **does not eliminate deadlock** if your own code still acquires multiple locks in an inconsistent order. You should establish lock ordering, keep critical sections short, and avoid calling callbacks or performing long I/O while holding locks whenever possible.

### wait/notify on an Exposed Monitor

`Object.wait()`, `notify()`, and `notifyAll()` operate on an object's monitor. If the condition monitor object is exposed, external code can send notifications outside your protocol. Even with a private monitor, `wait()` is subject to **spurious wakeups**, so waiting on a predicate must be placed inside a `while` loop that rechecks the condition.

### Security Limitations

A private lock provides **encapsulation and synchronization control**, not an absolute security boundary against all code running in the same JVM. If untrusted code has reflection, bytecode instrumentation, or privileged access to internals, appropriate isolation measures are needed at the application/system level. The primary problem addressed here is reducing implicit monitor dependencies among ordinary components.

## 9. ReentrantLock Still Requires Similar Encapsulation

`ReentrantLock` is not an intrinsic `synchronized` monitor, but a public `ReentrantLock` reference still gives external code the ability to call `lock()` and hold the lock. The same principle applies: if a lock is an implementation detail, use `private final ReentrantLock` and do not return the reference through the API.

~~~java
// PrivateReentrantLockDemo.java
import java.util.concurrent.locks.ReentrantLock;

public class PrivateReentrantLockDemo {
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

        int getValue() {
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
        Thread a = new Thread(counter::increment);
        Thread b = new Thread(counter::increment);
        a.start();
        b.start();
        a.join();
        b.join();

        System.out.println("Value: " + counter.getValue());
    }
}
~~~

~~~bash
javac PrivateReentrantLockDemo.java
java PrivateReentrantLockDemo
~~~

Stdout:

~~~text
Value: 2
~~~

With `ReentrantLock`, you must call `unlock()` in a `finally` block **after successfully acquiring the lock**. If using `tryLock()`, only unlock when it returns `true`. `tryLock`/timeouts can help build appropriate waiting protocols, but they do not automatically fix incorrect lock scoping or all deadlock possibilities.

## 10. Code Review and Safe Refactoring

A review checklist:

1. **Locate the lock expression** in every `synchronized(x)` block and `synchronized` method. Identify the actual object that `x` points to.
2. **Check identity:** is there a String literal, `intern`, boxed cache, class literal, singleton, or public object? Could two different names refer to the same object?
3. **Check ownership:** is the lock exposed via a field/getter/callback? Can callers or other libraries hold the lock?
4. **Identify the invariant:** which fields does the lock protect? Do all read/write paths follow the same protocol?
5. **Ensure stable identity:** prefer `private final`/`private static final`; never reassign the lock.
6. **Evaluate nested locking:** is there a clear lock acquisition order? Is a lock held while calling external code, waiting on network I/O, or acquiring another lock?
7. **Check the API contract before changing a monitor:** a public `synchronized` method or **intentionally** published monitor object might already be part of a contract that callers rely on. Switching to a private lock could break caller synchronization.
8. **Verify after changes:** use concurrency tests, invariant assertions, thread dumps, and contention metrics when needed; stress test results do not replace ownership analysis.

| Pattern to consider avoiding | Clearer alternative | Purpose |
| --- | --- | --- |
| `synchronized("LOCK")` | `private final Object lock = new Object()` | Monitor does not collide with interned literals |
| `private static final String LOCK = "LOCK"` | `private static final Object LOCK = new Object()` | Private field **and** private identity |
| `public static final Object LOCK` | `private static final Object LOCK` | Does not expose internal monitor |
| `public synchronized void update()` on a publicly used object | `synchronized(privateLock)` block inside a regular method | External code cannot lock the instance directly |
| `synchronized(MyClass.class)` | `synchronized(PRIVATE_STATIC_LOCK)` | Avoids using the broad class monitor |
| `synchronized(key.intern())` | Managed lock registry or per-key atomic operations | Avoids unintended collisions |

Switching a lock from `this` to a private lock is not a mechanical refactor: if existing consumers rely on `synchronized(instance)` for coordination, you must evaluate compatibility and update the protocol consistently.

## 11. Common Mistakes

- **"Two String variables with different names are two different locks."** False: if they point to the same interned literal, they share the same monitor.
- **"A private String literal is a private monitor."** False: `private` only applies to the field; the object itself is still shared.
- **"Because it is final, public Object LOCK is safe."** False: callers can still obtain the identity even though the field cannot be reassigned.
- **"synchronized(this) is always private."** False: callers holding the instance can also hold that monitor.
- **"static synchronized locks an instance."** False: it locks the class object.
- **"Two Strings that are equal under equals() synchronize on the same lock."** False if their identities differ; monitors are based on `==`.
- **"A private lock guarantees no deadlocks."** False: internal nested locks can still form wait cycles.
- **"Every BLOCKED thread is deadlocked."** False: it may simply be waiting for a monitor that is legitimately held.
- **"Using new String to create a lock is the best solution."** Unnecessary; a dedicated Object monitor is much clearer.

## 12. Self-Check

**1.** Two independent classes both use `synchronized("CACHE")`. Why can they block each other?  
**Answer:** Because identical String literals are interned, so both `synchronized` blocks hold the same monitor.

**2.** Why is `private static final String LOCK = "X"` still risky?  
**Answer:** Any code using the corresponding `"X"` literal can obtain the same interned object.

**3.** Does `public final Object lock = new Object()` guarantee that only the owning class holds the monitor?  
**Answer:** No. `final` only fixes the reference; a `public` field exposes the lock.

**4.** Which monitor does `public synchronized void increment()` use?  
**Answer:** The monitor of `this`; callers with the instance can use `synchronized(instance)`.

**5.** Do `static synchronized` and `synchronized(this)` automatically share the same monitor?  
**Answer:** No. The former uses the class object, while the latter uses the instance object.

**6.** What is the problem if a lock object is reassigned while the program is running?  
**Answer:** Threads can end up holding different monitors, breaking mutual exclusion even though they appear to protect the same field.

**7.** When is `private final Object` not enough for safety?  
**Answer:** When code has unguarded access paths without the lock, incorrect lock ordering, invariants spanning multiple locks, or resources outside the same ownership scope.

**8.** With `ReentrantLock`, when should you unlock?  
**Answer:** In a `finally` block after successfully acquiring the lock; if `tryLock` fails, you must not unlock.

**Key takeaway:** The monitor of `synchronized` is identified by **object identity**. Choose a lock with a private, stable, and unexposed identity when it only protects an implementation detail. Avoid literal/interned Strings and public objects, while maintaining a consistent synchronization protocol across all read/write paths and respecting existing API contracts.

### Standard References

- Java Language Specification 17, `17.1 (Locks), `17.4 (Memory Model): https://docs.oracle.com/javase/specs/jls/se17/html/jls-17.html
- Java Language Specification 17, `3.10.5 String Literals: https://docs.oracle.com/javase/specs/jls/se17/html/jls-3.html#jls-3.10.5
- JDK 17 `String.intern()`: https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/lang/String.html#intern()
- JDK 17 `ReentrantLock`: https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/concurrent/locks/ReentrantLock.html
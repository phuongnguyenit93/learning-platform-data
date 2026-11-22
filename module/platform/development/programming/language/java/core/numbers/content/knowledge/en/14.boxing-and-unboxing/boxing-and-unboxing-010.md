# Do Not Use Wrappers as Synchronization Locks in Java

**Rule:** Do not use wrapper objects such as `Integer`, `Long`, `Boolean`, `Double`, or `Character` as lock objects for `synchronized`. When you need to protect data shared across threads, use a **dedicated lock object with a stable identity**, such as `private final Object lock = new Object()`, or use an appropriate concurrency utility like `AtomicInteger` or `ReentrantLock`.

Wrappers exist to **represent primitive values as objects**, not to represent a shared resource with stable identity for synchronization. Boxing, object caching, and wrapper immutability make synchronizing on them prone to subtle bugs.

Example **not to use in applications**:

~~~java
Integer count = 0;

// DO NOT DO THIS: may lock on a cached wrapper object.
synchronized (count) {
    count++; // Unboxing -> addition -> re-boxing; count points to a different object.
}
~~~

This is an **illustrative snippet of bad code**, not a standalone runnable program. On modern JDKs, the compiler can emit warnings when `synchronized` is used directly on a value-based class. Compiling cleanly does not mean synchronization is correct.

## 1. A synchronized monitor is bound to an object, not a numeric value

In Java, the block:

~~~java
synchronized (lock) {
    // Critical section.
}
~~~

uses the **monitor** of the object to which the `lock` expression evaluates at the moment of entering the block. Two threads exclude each other only when they attempt to acquire **the same monitor of the exact same object**.

- Two references pointing to the **same object**: use the same monitor and can block each other.
- Two **distinct** objects, even with equal numeric contents: have two different monitors and do **not** exclude each other.
- If the `lock` reference variable is reassigned: a subsequent `synchronized(lock)` can lock a different object. The previous monitor does not automatically transfer to the new object.

Synchronization does not rely on `equals()`, `hashCode()`, numeric value, or an unboxed `int`. It relies on the **reference identity** of the object the JVM locks on. Likewise, the *happens-before* relationship between an unlock and the next lock is established when operating on **the same monitor**, not on two objects that merely hold the same value.

This is precisely why wrappers, designed to represent **values**, are not a safe lock choice.

## 2. Boxing, unboxing, and wrapper object lifecycles

Common primitive wrappers:

| Primitive | Wrapper |
| --- | --- |
| `boolean` | `Boolean` |
| `byte` | `Byte` |
| `short` | `Short` |
| `char` | `Character` |
| `int` | `Integer` |
| `long` | `Long` |
| `float` | `Float` |
| `double` | `Double` |

With boxing, a primitive becomes a wrapper object; unboxing extracts the primitive value.

~~~java
Integer n = 42;       // Autoboxing: int -> Integer
int rawValue = n;     // Unboxing: Integer -> int
n = n + 1;            // Unbox n, add int, box 43, then reassign n
~~~

Wrappers are **immutable**: the numeric value inside an `Integer` object cannot be modified. When using `n++`, Java does not increment the Integer object's value “in place”; instead, it computes a new primitive value and updates the variable `n`'s **reference** after boxing.

This is especially dangerous if that same wrapper variable is used as a lock. Each numeric update can change the object used by subsequent lock acquisitions.

### 2.1. Cached wrappers can share identity

Java often reuses wrappers for certain values. For instance, `Integer.valueOf(int)` guarantees caching at least values from **-128 to 127**:

~~~java
Integer a = Integer.valueOf(42);
Integer b = Integer.valueOf(42);

System.out.println(a == b);       // true: same object in the cache range
System.out.println(a.equals(b));  // true: same numeric value
~~~

Therefore:

~~~java
// DO NOT DO THIS: two unrelated pieces of code could use the same monitor!
synchronized (Integer.valueOf(42)) {
    // ...
}
~~~

Two unrelated components both locking on `Integer.valueOf(42)` can accidentally **block each other**. If they hold other locks in different orders, unintended lock sharing can even contribute to deadlocks. There is also the risk of external code interfering with another component's execution schedule, because the cached object is not privately owned by you.

**Do not invert the conclusion:** a wrapper *outside* the cache range does not mean the JVM is guaranteed to return a fresh object. For example, do not rely on the outcome of `Integer.valueOf(1000) == Integer.valueOf(1000)` to determine lock safety; object reuse is a detail unsuitable as a synchronization contract.

Other wrapper types also have their own boxing/caching rules, and some wrappers can be reused. The core lesson does not depend on a specific cache: **wrappers are designed with value semantics, not stable lock-identity semantics**.

### 2.2. Creating a new wrapper is not the right solution

It used to be possible to write `new Integer(42)` to try to force a distinct object. However, wrapper constructors like this have been **deprecated for removal**, and wrappers themselves are considered **value-based**. Using them as locks remains wrong in purpose, hard to read, and misaligned with Java's direction.

To get a dedicated monitor, explicitly create:

~~~java
private final Object lock = new Object();
~~~

This is an object dedicated to serving as a lock, carrying no numeric semantics and never accidentally recreated by value increments.

## 3. Bug number one: the lock changes when incrementing a wrapper variable

Look at the following **unsafe** code (illustrative example, do not use):

~~~java
class UnsafeCounter {
    private Integer count = 0;

    void increment() {
        synchronized (count) { // Locks the current count object at this moment
            count++;           // count is unboxed, incremented, boxed, reassigned
        }
    }

    int get() {
        return count;          // Read lacks a consistent synchronization policy
    }
}
~~~

Analysis:

1. Initially `count` references the wrapper for 0; thread A enters `synchronized(count)` and holds the monitor of **object 0**.
2. `count++` produces numeric value 1 and makes `count` reference a wrapper representing 1.
3. Thread B can enter `synchronized(count)` at this moment and acquire the monitor of **object 1**, while A has not yet exited the critical section protected by monitor 0.
4. The two threads do not necessarily exclude each other because they are locking **two different objects**. Intended thread-safe increments can race and lose updates; reading `get()` is also unprotected.
5. Wrapper caching does not fix this bug: caching may cause two objects with the **same** value to share a monitor, yet whenever the value changes, the lock object usually changes as well.

Note: the code can simultaneously trigger compiler warnings about synchronizing on a value-based object. **Races do not always appear on a single run**; the bug is the lack of proper concurrency guarantees under the Java Memory Model.

### 3.1. Putting final on a wrapper lock also fails to solve the root issue

~~~java
// Should not be used as a lock, even if the reference is final:
private final Integer lock = Integer.valueOf(42);
~~~

`final` prevents reassigning the `lock` reference within the instance, yet **does not make that Integer object an exclusive resource**. It can still be a cached object shared with other code. And the rule against locking on value-based wrappers still applies.

## 4. Wrappers are value-based classes: warnings from modern Java

JDK primitive wrappers are described as **value-based classes**. These classes represent values; programmers must not rely on their object identity to coordinate systems. Java platform documentation explicitly warns against using value-based objects for synchronization.

Since JDK 16, via JEP 390, compiler tooling supports **warnings for synchronizing on value-based objects**. When writing:

~~~java
Integer guard = Integer.valueOf(42);
// synchronized (guard) { /* Do not do this */ }
~~~

If the `synchronized` line is uncommented, `javac` on modern JDKs can emit a warning like “attempt to synchronize on an instance of a value-based class”; observable with the related lint option `-Xlint:synchronization`. Exact warning wording varies by compiler version/configuration.

The warning is not merely a style hint: it reflects compatibility issues with how Java evolves value-oriented classes. Some advanced diagnostic JVM modes can warn or treat synchronization on value-based instances more strictly. **Do not take the fact that code currently runs as proof that wrappers can serve as locks long-term.**

Distinguish these concepts:

- `wrapper.equals(other)`: compares content per the specific class contract.
- `wrapper == otherWrapper` when both are references: compares **object identity**; caching can make results surprising.
- `synchronized(wrapper)`: locks the monitor of the **wrapper object**, not using numeric value.
- `synchronized(lockObject)` with a dedicated lock: locks a monitor created specifically to guard shared state.

If the goal is protecting a counter or state, the identity of the guarded counter is not its numeric value itself.

## 5. Right way: private final Object lock

Standard pattern:

~~~java
class SafeCounter {
    private final Object lock = new Object();
    private int value;

    void increment() {
        synchronized (lock) {
            value++;
        }
    }

    int get() {
        synchronized (lock) {
            return value;
        }
    }
}
~~~

This is an **illustrative class snippet** that can be placed in a Java file. Because `lock` is created with `new Object()` and held in a `private final` field, methods on **the same instance** use a stable monitor. No external code can obtain the `lock` reference through a public API, so mutual exclusion occurs within the intended scope.

Ensure **all accesses involving the same data invariant follow the locking protocol**. Locking only on writes while reading elsewhere without a matching visibility mechanism can break memory guarantees.

For `static` state shared across multiple instances, the lock must also belong to that `static` state:

~~~java
class GlobalCounter {
    private static final Object LOCK = new Object();
    private static int value;

    static void increment() {
        synchronized (LOCK) {
            value++;
        }
    }

    static int get() {
        synchronized (LOCK) {
            return value;
        }
    }
}
~~~

An instance lock protects instance state; a static lock protects static state. Do not use `synchronized(this)` or `synchronized(SomeClass.class)` indiscriminately if that monitor object can be accessed by external code and cause unintended contention. A dedicated lock with `private` visibility is usually clearer.

## 6. Another right way: AtomicInteger, AtomicLong, and LongAdder

If you only need an independent counter, instead of `Integer` and `synchronized` you can use `AtomicInteger`:

~~~java
import java.util.concurrent.atomic.AtomicInteger;

class AtomicCounter {
    private final AtomicInteger count = new AtomicInteger();

    void increment() {
        count.incrementAndGet();
    }

    int get() {
        return count.get();
    }
}
~~~

`AtomicInteger.incrementAndGet()` performs an atomic update and provides visibility guarantees per the class contract. It does not require callers to pick a monitor. `AtomicLong` fits when `long` range is needed, though it still overflows if the range is exceeded.

For statistical counters updated very frequently under high contention, `LongAdder` is often worth considering. However, `LongAdder.sum()` does not produce an atomic snapshot while other threads are updating. Therefore:

- `AtomicInteger`/`AtomicLong`: suitable when atomic operations on **a single variable** and reads consistent with those atomic updates are required.
- `LongAdder`: typically optimal for high-concurrency statistics/accumulation, not a replacement for every synchronization protocol needing instantaneous snapshots.
- A dedicated `Object lock` or `ReentrantLock`: suitable when protecting **multiple related fields/conditions** within a single logical transaction.

Using an atomic counter also does not mean every combination of multiple separate operations is automatically atomic. For example, checking `get()` and deciding to update in a separate statement can race; check `compareAndSet` or an appropriate lock design.

## 7. Another right way: ReentrantLock

When advanced control such as `tryLock()`, timed locking, or interruptible lock acquisition is required, the JDK provides `java.util.concurrent.locks.ReentrantLock`.

~~~java
import java.util.concurrent.locks.ReentrantLock;

class LockBasedCounter {
    private final ReentrantLock lock = new ReentrantLock();
    private int count;

    void increment() {
        lock.lock();
        try {
            count++;
        } finally {
            lock.unlock(); // Important: always release, even if an error occurs.
        }
    }

    int get() {
        lock.lock();
        try {
            return count;
        } finally {
            lock.unlock();
        }
    }
}
~~~

This is an API-illustrative standalone class; to run it, place it in a Java file and call its methods from a program with `main`. With `ReentrantLock`, never forget `unlock()` in `finally`. `synchronized` automatically releases its monitor upon exiting the block, even when an exception occurs.

There is no need to convert all `synchronized` blocks to `ReentrantLock` without a reason. A simple `private final Object` is often sufficient and easy to audit.

## 8. Standalone runnable Java 17+ example

Create file `WrapperLockDemo.java`. The example **does not synchronize directly on wrappers**; it only demonstrates boxing/caching and then has four threads update counters using two safe approaches.

~~~java
import java.util.concurrent.atomic.AtomicInteger;

public class WrapperLockDemo {
    static final class SafeCounter {
        private final Object lock = new Object();
        private int value;

        void increment() {
            synchronized (lock) {
                value++;
            }
        }

        int get() {
            synchronized (lock) {
                return value;
            }
        }
    }

    public static void main(String[] args) throws InterruptedException {
        Integer a = Integer.valueOf(42);
        Integer b = Integer.valueOf(42);
        System.out.println("cached identity: " + (a == b));
        System.out.println("numeric equality: " + a.equals(b));

        Integer boxed = 42;
        Integer before = boxed;
        boxed++;
        System.out.println("after increment: " + boxed);
        System.out.println("same boxed object: " + (before == boxed));

        SafeCounter counter = new SafeCounter();
        AtomicInteger atomic = new AtomicInteger();

        Thread[] workers = new Thread[4];
        for (int i = 0; i < workers.length; i++) {
            workers[i] = new Thread(() -> {
                for (int j = 0; j < 1_000; j++) {
                    counter.increment();
                    atomic.incrementAndGet();
                }
            });
        }

        for (Thread worker : workers) {
            worker.start();
        }
        for (Thread worker : workers) {
            worker.join();
        }

        System.out.println("lock counter: " + counter.get());
        System.out.println("atomic counter: " + atomic.get());
    }
}
~~~

Compile/run with JDK 17 or higher:

~~~bash
javac WrapperLockDemo.java
java WrapperLockDemo
~~~

Output:

~~~text
cached identity: true
numeric equality: true
after increment: 43
same boxed object: false
lock counter: 4000
atomic counter: 4000
~~~

**Analysis:**

1. `Integer.valueOf(42)` returns the same wrapper object in the guaranteed cache range. Thus the identity expression `a == b` is `true`; this is precisely why that object is not a private lock.
2. After `boxed++`, the `boxed` variable represents 43, whereas `before` still points to the wrapper representing 42. The two references differ; the old wrapper value is unchanged.
3. `SafeCounter` uses a stable `private final Object`. Each increment runs under the **same monitor** for the same counter.
4. `AtomicInteger` has atomic `incrementAndGet()`. Four threads increment 1,000 times each; after calling `join()` on all, both counters give 4,000.
5. The example intentionally does not simulate a race using `synchronized(Integer)` because race outcomes can vary across runs and encourage bad habits.

Calling `join()` makes the main thread wait for workers to finish before reading results, making counter output predictable. It does not replace the need to protect increments inside the workers themselves.

## 9. Common mistakes and how to spot them

| Practice | Issue | Appropriate replacement |
| --- | --- | --- |
| `synchronized (Integer.valueOf(1))` | Cached object unintentionally shared | `private final Object lock = new Object()` |
| `synchronized (count) { count++; }` with `Integer count` | `count` can change reference upon increment | `int` + private lock or `AtomicInteger` |
| `private final Integer lock = 42` | `final` does not guarantee an exclusive monitor | Create `new Object()` for the lock |
| `synchronized (Boolean.TRUE)` | Shared object, lock scope crosses modules | Dedicated private lock |
| `synchronized (Double.valueOf(x))` | Value-based wrapper; identity should not serve as a lock | Dedicated private lock |
| `volatile Integer count; count++;` | `volatile` does not make `++` atomic | AtomicInteger or proper synchronized |
| Locking only on writes while reading state uncoordinated | Lacks visibility/happens-before guarantees | Synchronize both reads and writes under one protocol |
| Using `ReentrantLock.lock()` without safe `unlock()` | Can hold lock forever on exception | `try/finally` |
| Replacing `Integer` with `new Integer(...)` as a lock | Deprecated constructor, violates value-based design | `new Object()`, do not create wrappers as monitors |

### 9.1. Why can't volatile save wrapper increments?

~~~java
// STILL WRONG if accessed by multiple concurrent threads:
private volatile Integer value = 0;

void increment() {
    value++; // Read -> unbox -> add -> box -> write, not atomic.
}
~~~

This is an illustrative snippet placed inside a class, not a standalone runnable program. `volatile` provides visibility and ordering guarantees for reads/writes of the volatile field itself, yet **does not combine the entire read–compute–write sequence into an atomic operation**.

### 9.2. Why is a public lock also not ideal?

If you use a monitor object accessible to external code, such as `synchronized(this)` on a public object, external code can also write `synchronized(obj)` and create unexpected lock contention. Therefore, even without wrappers, keeping locks in a `private final` field usually clarifies lock ownership.

### 9.3. Can you synchronize on a wrapper if single-threaded?

When single-threaded, `synchronized` generally solves no concurrent-sharing need. Still, using a wrapper as a lock remains poor design; code may be reused in multi-threaded contexts or across JDK upgrades. Switch to a dedicated lock instead of relying on coincidental current assumptions.

## 10. Self-check exercises

**Question 1.** Two different modules both use `synchronized(Integer.valueOf(42))`. Can they block each other even without sharing a variable?  
**Answer:** Yes. `Integer.valueOf(42)` is cached; both can lock the exact same object. This is unintended lock sharing.

**Question 2.** Why is `private final Integer lock = 42` not yet a good lock?  
**Answer:** `final` stabilizes **the field's reference**, yet the wrapper object can be cached and shared elsewhere. Value-based wrappers are not designed as monitors. Use `private final Object lock = new Object()`.

**Question 3.** Does `synchronized(count) { count++; }` protect `count++` when `count` is an `Integer`?  
**Answer:** Not guaranteed. `count++` unboxes, adds, boxes, and assigns a new reference; subsequent threads can lock a different monitor. Increments can happen concurrently and lose updates.

**Question 4.** Can you replace `Integer count` with `volatile Integer count` and increment safely with `count++`?  
**Answer:** No. `volatile` ensures certain visibility relationships but does not make a read–add–write sequence an atomic increment. Use `AtomicInteger.incrementAndGet()` or a dedicated lock.

**Question 5.** When do you choose `private final Object lock` over `AtomicInteger`?  
**Answer:** When you need to protect multiple variables together, maintain a related invariant, or run multiple steps inside a critical section. `AtomicInteger` suits atomic operations on a single integer variable.

**Question 6.** Should every counter be switched to `LongAdder`?  
**Answer:** No. `LongAdder` is advantageous in many high-contention statistics scenarios, yet `sum()` is not an atomic snapshot under concurrent updates. For consistent check–update logic, a different design is needed.

**Question 7.** What is the most important condition for `synchronized` to provide mutual exclusion?  
**Answer:** Threads must lock **the same monitor on the exact same object**, and all accesses needing protection must follow the same locking protocol. Merely having two wrappers holding the same numeric value is not enough.

## 11. Takeaways

- `Integer`, `Long`, `Boolean`, `Double`, and primitive wrappers are **value-based**, not objects designed to have their identity used as locks.
- Caching/autoboxing can cause wrappers to be **unintentionally shared**; unboxing then boxing on updates can cause wrapper variables to **switch lock references**.
- `synchronized` locks an **object's monitor**, not an `int` value or an abstract arithmetic expression.
- Choose `private final Object lock = new Object()` for critical sections with related state; use `AtomicInteger`/`AtomicLong` for atomic updates on a single variable, and consider `ReentrantLock` for advanced locking needs.
- Avoid using `volatile` or `final Integer` as a “workaround” for wrapper locking; they do not satisfy the monitor identity contract.
- When you see the warning “synchronization on an instance of a value-based class”, **replace the locking model**, do not merely suppress the warning.
# What Makes a Class Thread-Safe?

A **thread-safe class** is one whose objects continue to fulfill **their published contract** when accessed concurrently by multiple threads, under any valid interleaving of execution, without requiring callers to **add external synchronization** for operations that the class guarantees to be safe.

Being “correct” means more than just not throwing exceptions: data must preserve its invariants, updates must not be lost, and results must obey the memory visibility rules of the **Java Memory Model (JMM)**. Different threads do not necessarily have to observe results in a fixed order; a contract may allow non-deterministic ordering, consistent snapshots, or eventual consistency. What matters is that every observation remains **consistent with the contract**.

For example, a class that allows at most two reservations may let any two of three competing threads claim a slot. However, the invariant `used <= 2` must always hold. If all three ever succeed, the class has violated thread safety.

## 1. Start from State, Invariants, and Operation Boundaries

Before choosing `synchronized` or `AtomicInteger`, identify:

- **Mutable shared state:** which fields can change and are accessed by multiple threads? Are there `static` variables, passed-in objects, collections, or external dependencies?
- **Invariants:** which relationships must always hold? For example, `0 <= used <= limit` or `available + reserved == total`.
- **Atomic operations:** which operations must execute as a logically indivisible unit? “Check whether a slot is available and then reserve it” is a single logical operation, even if the code spans multiple statements.
- **Publication:** how are objects and results published to other threads? Is construction complete, and is there a valid *happens-before* relationship?
- **Encapsulation:** can callers obtain a reference to an internal mutable collection or array and modify it outside the protection boundary?

A safe class must preserve its invariants **across all relevant read and write paths**, including public methods, callbacks, initialization logic, and objects exposed to external code.

| Phenomenon | Why is it dangerous? |
|---|---|
| *Lost update* | Two threads both read the same old value and both write back, losing one update. |
| *Check-then-act race* | Two threads observe the same condition as true and both perform an action allowed only once. |
| *Stale read* | A thread reads data without a synchronization relationship that guarantees visibility of the required update. |
| *Inconsistent snapshot* | Reading multiple fields while another thread is updating them, producing an invalid combination. |
| *Representation exposure* | A caller can directly mutate internal state, bypassing the class’s locks and invariants. |

**Thread-safe is not a special modifier.** Having `final`, `volatile`, or `synchronized` on a few members is not enough to prove the entire class is safe.

## 2. Core Strategies

### Stateless: no shared mutable state

```java
public final class StatelessFormatter {
    public String greet(String name) {
        return "Hello, " + name.trim();
    }
}
```

This is a valid class, though only an illustrative snippet (without `main`). Each invocation uses only parameters and temporary variables on that call’s stack. `String` is immutable, and the class holds no mutable fields. Multiple threads can call `greet` concurrently.

**Exception:** “having no instance fields” is not enough if a method secretly uses a mutable `static HashMap`, a global counter, or an unsafe dependency. Truly stateless code must not depend on uncoordinated shared mutable state.

### Immutable: state cannot be modified after construction

Immutable objects are often a very strong choice for sharing: data is fully constructed, exposes no setters or reference paths allowing deep mutation, and is published according to JMM rules. `final` on a reference field only fixes **the reference**, not the mutability of the object behind it.

A `record` containing a `List<String>` does not automatically become immutable if it retains an `ArrayList` passed in by the caller. Defensive copying is required, and if elements are mutable, deeper copying or design is needed. A runnable example is in Section 5.

### Mutable but properly coordinated

A mutable class can still be thread-safe if all shared state is accessed according to a consistent protocol, such as:

- `synchronized` or `ReentrantLock` covering a *critical section* that protects the invariant;
- `AtomicInteger` / `AtomicReference` / compare-and-set (CAS) for appropriate atomic state updates;
- concurrent collections with atomic operations that **match the specific contract**;
- replacing an entire immutable snapshot via a reference that is atomically published and updated.

No single mechanism is optimal for every situation; what must be protected is the **logical operation** and the observations exposed by the API.

## 3. Visibility Is Not Atomicity: volatile Can Still Fail

`volatile` provides visibility and read/write ordering guarantees for that variable. However, `count++` is not an atomic update; it consists of a read, a computation, and a write. If two threads both read `0` and then both write `1`, one increment is lost.

The following example uses a latch to force two threads to read the value before writing, making the bug easier to reproduce than a loop running millions of times.

Create the file **`VolatileCounterRace.java`**:

```java
import java.util.concurrent.CountDownLatch;

public class VolatileCounterRace {
    static final class Counter {
        private volatile int value;
        private final CountDownLatch bothRead = new CountDownLatch(2);

        void increment() throws InterruptedException {
            int oldValue = value;
            bothRead.countDown();
            bothRead.await();
            value = oldValue + 1;
        }

        int get() {
            return value;
        }
    }

    public static void main(String[] args) throws InterruptedException {
        Counter counter = new Counter();
        Runnable task = () -> {
            try {
                counter.increment();
            } catch (InterruptedException e) {
                Thread.currentThread().interrupt();
            }
        };

        Thread first = new Thread(task);
        Thread second = new Thread(task);
        first.start();
        second.start();
        first.join();
        second.join();

        System.out.println("Expected increments: 2");
        System.out.println("Actual value: " + counter.get());
    }
}
```

```bash
javac VolatileCounterRace.java
java VolatileCounterRace
```

Output in a normal, uninterrupted run:

```text
Expected increments: 2
Actual value: 1
```

Both threads read `0` before the latch opens; afterward, both write `1`. `volatile` does not combine the read-modify-write steps. The latch is only for the experiment to force this interleaving; the `Counter` class itself is still not a thread-safe counter. When you only need to increment a single variable, `AtomicInteger.incrementAndGet()` or an appropriate `synchronized` block can solve this.

## 4. A Safe Mutable Class: Locking the Entire Check-Then-Act

Suppose a class limits the number of granted slots: `0 <= used <= limit`. Checking whether a slot is available and incrementing `used` must happen in a single logically atomic operation.

Create the file **`SafeQuota.java`**:

```java
import java.util.concurrent.atomic.AtomicInteger;

public final class SafeQuota {
    private final int limit;
    private int used;

    public SafeQuota(int limit) {
        if (limit < 0) {
            throw new IllegalArgumentException("limit must be >= 0");
        }
        this.limit = limit;
    }

    public synchronized boolean tryAcquire() {
        if (used >= limit) {
            return false;
        }
        used++;
        return true;
    }

    public synchronized int used() {
        return used;
    }

    public int limit() {
        return limit;
    }

    public static void main(String[] args) throws InterruptedException {
        SafeQuota quota = new SafeQuota(2);
        AtomicInteger accepted = new AtomicInteger();

        Runnable task = () -> {
            if (quota.tryAcquire()) {
                accepted.incrementAndGet();
            }
        };

        Thread a = new Thread(task);
        Thread b = new Thread(task);
        Thread c = new Thread(task);
        a.start();
        b.start();
        c.start();
        a.join();
        b.join();
        c.join();

        System.out.println("Accepted: " + accepted.get());
        System.out.println("Used: " + quota.used());
        System.out.println("Limit: " + quota.limit());
    }
}
```

```bash
javac SafeQuota.java
java SafeQuota
```

Output:

```text
Accepted: 2
Used: 2
Limit: 2
```

**What provides the guarantee:** `used` is `private`; every read and write path to `used` uses the monitor of the same `quota` object. Inside `tryAcquire()`, no thread can interleave between the `used >= limit` check and `used++`. `used()` also uses the monitor to read a consistent state. `limit` is immutable after construction and validated in the constructor.

Because three threads compete, there is no guarantee which threads win. However, exactly two calls receive `true`. `accepted` is an `AtomicInteger` so the demo program can count successful acquisitions, and `join()` ensures `main` reads the results only after all three threads finish.

`synchronized` on an instance method locks **that specific instance**. Two distinct `SafeQuota` objects have separate monitors and separate state: they do not automatically coordinate to enforce a global quota. If an invariant spans multiple objects or JVMs, you must design a corresponding shared owner or arbitrator.

## 5. Immutable Classes and Defensive Copying

Create the file **`ImmutableSettings.java`**:

```java
import java.util.ArrayList;
import java.util.List;

public class ImmutableSettings {
    public record Settings(List<String> roles) {
        public Settings {
            roles = List.copyOf(roles);
        }
    }

    public static void main(String[] args) {
        List<String> source = new ArrayList<>();
        source.add("reader");

        Settings settings = new Settings(source);
        source.add("writer");

        System.out.println("Roles: " + settings.roles());
        try {
            settings.roles().add("admin");
        } catch (UnsupportedOperationException e) {
            System.out.println("External modification rejected");
        }
    }
}
```

```bash
javac ImmutableSettings.java
java ImmutableSettings
```

Output:

```text
Roles: [reader]
External modification rejected
```

The record’s compact constructor replaces the `roles` parameter with an unmodifiable copy created by `List.copyOf`. Modifying `source` by the caller does not affect the record’s state; the `roles()` accessor does not expose a list that supports adding elements. Because the elements are immutable `String` instances, the data can be safely read concurrently after proper creation and publication.

**Do not overgeneralize:** `List.copyOf` does not deep-copy elements. With a `List<MutableOrder>`, another thread can still mutate fields inside each `MutableOrder` if it holds a reference. `Collections.unmodifiableList(original)` is only a view that forbids mutation through the view; if `original` changes, the view can observe those changes. Immutability must consider **the entire reachable object graph**.

## 6. AtomicInteger: Thread-Safe for Single Updates

Create the file **`AtomicCounter.java`**:

```java
import java.util.concurrent.atomic.AtomicInteger;

public final class AtomicCounter {
    private final AtomicInteger count = new AtomicInteger();

    public int increment() {
        return count.incrementAndGet();
    }

    public int value() {
        return count.get();
    }

    public static void main(String[] args) throws InterruptedException {
        AtomicCounter counter = new AtomicCounter();
        Runnable task = () -> {
            for (int i = 0; i < 1000; i++) {
                counter.increment();
            }
        };

        Thread a = new Thread(task);
        Thread b = new Thread(task);
        a.start();
        b.start();
        a.join();
        b.join();

        System.out.println("Value: " + counter.value());
    }
}
```

```bash
javac AtomicCounter.java
java AtomicCounter
```

Output:

```text
Value: 2000
```

`incrementAndGet()` is an atomic increment; after both `join()` calls, `main` observes exactly 2,000 updates. However, caller-side code like `if (counter.value() < max) counter.increment()` is still **not atomic as a compound operation**. Two threads can both pass the check and then both increment.

When a single variable holds the entire invariant, a CAS loop using `compareAndSet(old, new)` can combine the check and the update: if another thread changes the value in between, CAS fails and the loop must **re-read and re-check the condition**. With `AtomicReference.updateAndGet`, the update function may be retried under contention, so avoid side effects such as sending data, creating invoices, or performing external I/O inside the lambda.

## 7. Per-Method Thread Safety Does Not Guarantee Client-Side Compound Operations

Consider a class whose `get()` and `increment()` methods are both `synchronized`. The client-side snippet below is still broken if the goal is to cap the number of increments:

```java
// Illustrative UNSAFE code; counter/limit are assumed to be declared.
if (counter.get() < limit) {
    counter.increment();
}
```

Two threads can both finish `get()` and both see “not yet at the limit” before either calls `increment()`. Each individual method is safe, but **the check → act sequence is not an atomic transaction**. API design should place the entire decision inside a method like `SafeQuota.tryAcquire()`, while clearly documenting what the class guarantees.

A similar example with a concurrent collection:

```java
// Illustrative code; cache is a ConcurrentHashMap<String, String>.
if (!cache.containsKey("key")) {
    cache.put("key", expensiveCreate());
}
```

`containsKey` and `put` each have their own thread-safety guarantees, but two threads can both observe that the key is absent and both invoke `expensiveCreate()`. On `ConcurrentHashMap`, `computeIfAbsent(key, mappingFunction)` provides an atomic contract suitable for **computing a value if the key is absent**. The mapping function should be short, must not modify the map being computed, and should avoid non-idempotent side effects when business constraints involve more than a single map operation.

`putIfAbsent(key, expensiveCreate())` also requires caution: Java evaluates `expensiveCreate()` **before** calling `putIfAbsent`, so resource creation may still happen multiple times even though the insertion itself is atomic.

## 8. Multi-Field Invariants Require a Consistent Protocol

Suppose a class has `available` and `reserved` with the invariants:

```text
available >= 0
reserved >= 0
available + reserved == total
```

If a thread decrements `available` first and only then increments `reserved`, another thread reading between the two assignments can observe an invalid sum. Using two `AtomicInteger` fields **does not automatically create an atomic snapshot across both**.

A straightforward solution is to guard all updates and compound state reads with the same monitor:

```java
// Method excerpts inside a class, not standalone.
private int available = 10;
private int reserved;

public synchronized boolean reserve() {
    if (available == 0) {
        return false;
    }
    available--;
    reserved++;
    return true;
}

public synchronized String snapshot() {
    return "available=" + available + ", reserved=" + reserved;
}
```

`snapshot()` and `reserve()` use the same instance lock, so no thread can observe a half-updated state. Another option is to encapsulate **all** related fields in an immutable object and swap the entire reference via `AtomicReference.compareAndSet` (replacing the whole snapshot at once). Choose the approach that fits the complexity and real-world contention.

With `ReentrantLock`, always release the lock in `finally`:

```java
lock.lock();
try {
    // Check and update the same invariant under one lock.
} finally {
    lock.unlock();
}
```

This is an illustrative excerpt assuming `lock` is an initialized `ReentrantLock`. Two operations guarded by **two different locks** do not exclude each other. Avoid calling uncontrolled external code or performing long I/O while holding a lock unless necessary: holding locks too long increases contention or risks deadlock.

## 9. Safe Publication Under the Java Memory Model

Even a properly constructed object must still be **published** to other threads through a path with appropriate memory guarantees. Common mechanisms include:

- static initialization of a class under JVM guarantees;
- writing/reading a `volatile` field or `AtomicReference`;
- releasing/acquiring the same monitor or lock;
- passing the object to a new thread after construction is complete: actions before `Thread.start()` *happen-before* actions inside the started thread;
- exchanging via a concurrent structure with synchronization guarantees such as `BlockingQueue`.

`final` fields also carry special initialization guarantees when the object is **properly constructed**. Avoid letting `this` escape from a constructor:

```java
// DANGEROUS illustrative snippet inside a constructor.
public SomeClass() {
    new Thread(() -> useFieldsOfThis()).start();
    importantField = 42;
}
```

The worker thread may access `importantField` before the constructor assigns it. The guarantee from `start()` only covers actions **prior** to the `start()` call, not assignments afterward. Fully construct the object before publishing it or starting threads that use it.

Do not mistake `final` on a reference for “all data behind the reference is immutable”; likewise, `volatile` on a reference does not turn deep mutations inside the object into atomic updates.

## 10. Encapsulation: Do Not Expose Mutable Collections

A design that appears to use proper locking can be broken by a getter that returns the real mutable reference:

```java
// Illustrative UNSAFE snippet.
private final List<String> tasks = new ArrayList<>();

public List<String> tasks() {
    return tasks; // Caller can add/remove outside the locking protocol.
}
```

If you want to expose an independent snapshot while all mutations are guarded by the instance monitor, you can do:

```java
public synchronized List<String> tasksSnapshot() {
    return List.copyOf(tasks);
}
```

Both snippets require importing `java.util.List` and `java.util.ArrayList`; the example assumes immutable `String` elements. If elements are mutable, you must also avoid exposing references to those elements.

Similarly, `Collections.synchronizedList` synchronizes individual methods, but **iteration** must still be coordinated according to the collection’s contract. `CopyOnWriteArrayList`, on the other hand, provides a snapshot iterator, trading write cost for stable iteration. Do not generalize that “every operation on every concurrent collection is transactional.”

## 11. Distinguishing Concurrency Properties

| Property | Meaning | Key Takeaway |
|---|---|---|
| **Thread safety** | Concurrent access still preserves the contract and invariants. | The overall goal of the class. |
| Atomicity | An operation cannot be interleaved in a way that breaks its promised logical semantics. | Required for multi-step updates. |
| Visibility | Other threads observe memory effects according to the JMM. | Necessary, but not sufficient for check-then-act. |
| Immutability | State cannot be modified after creation. | A safe sharing strategy when properly constructed and published. |
| Linearizability | Each operation can be viewed as taking effect at a single point between invocation and return. | A strong, useful guarantee, though not required of every concurrent API. |
| Liveness | The system/threads continue making progress without indefinite waiting. | Distinct from safety; locks can protect data yet cause deadlock. |
| Lock-free | A progress guarantee that does not depend on traditional mutual-exclusion locks. | Not a synonym for thread-safe. |
| Reentrancy | A function can be safely re-entered under specific conditions. | Does not by itself prove safety for shared data. |

A class can be thread-safe even when **the order of outcomes is non-deterministic**; for instance, it may be unspecified which thread gets a slot, as long as no one exceeds the quota. Conversely, code that produces the same execution order in a few test runs can still race when load or scheduling changes.

## 12. Common Mistakes That Make a “Locked” Class Unsafe

1. Locking setters while getters read fields without synchronization.
2. Using a different lock object per method; `synchronized(new Object())` on every call does not coordinate across threads.
3. Splitting check and update into two public methods and expecting callers to compose them safely.
4. Returning an internal mutable list, array, or map to callers, allowing out-of-lock mutation.
5. Letting `this` escape from the constructor before state is completely initialized.
6. Allowing subclasses to override invariant-protecting methods without a clear inheritance contract.
7. Invoking uncontrolled callbacks while holding a lock, potentially creating lock-ordering cycles.
8. Assuming `volatile` makes multi-field updates atomic or `AtomicInteger` protects a multi-state transaction.
9. Assuming all dependencies are thread-safe just because the outer wrapper class uses locks.
10. Relying on `Thread.start()` order or `Thread.sleep()` to assume a fixed execution order.

For classes with `static` shared mutable state, also consider **cross-instance scope**. Two instances of a class have two separate `this` monitors; instance-level locking cannot protect a shared `static` field. Use an appropriate strategy for truly shared state or eliminate shared global state.

## 13. Process for Designing and Testing Thread-Safe Classes

**Design:** first write down the invariants and the guarantees of each public method. Identify mutable state, who may hold aliases, and all read/write paths. Prefer stateless or immutable designs when possible. When mutability is required, choose a protection mechanism that matches the scope of the invariant. Encapsulate full business decisions in methods such as `tryAcquire()`, protect all related reads and writes, publish objects safely under the JMM, and document concurrent API semantics clearly.

**Testing:** construct targeted interleavings using `CountDownLatch` or `CyclicBarrier`, wait for all workers with `join()` or an appropriate primitive, and then assert invariants and side-effect counts. Repeat under varying loads to increase coverage. A test passing thousands of times **cannot by itself prove** a class is thread-safe; confidence comes from both design/happens-before reasoning and testing evidence.

Do not use `Thread.sleep()` to “prove” two tasks finished or assume a race cannot occur. If deadlock or contention is suspected, inspect thread dumps and analyze lock acquisition. A class with data safety can still suffer from liveness issues; evaluate wait timeouts, interruption/cancellation, and lock acquisition order.

**Scope boundaries:** a monitor inside one JVM cannot lock a file or database row being written by another JVM. Cross-process invariants require atomic operations, transactions, or unique constraints in the system that owns the resource. Proper Java synchronization is only part of the solution if data is also modified outside the process.

## 14. Self-Check Questions

1. **Is `private volatile int count` with `count++` thread-safe?** No. `volatile` does not make read-modify-write atomic.
2. **Why is `SafeQuota.tryAcquire()` safe?** Because checking and incrementing `used` occur under the same monitor, and all access paths to `used` follow that protocol.
3. **If two methods are both `synchronized`, is calling `get()` followed by `increment()` atomic?** No. Another thread can interleave between the two calls.
4. **Is a class with no instance fields guaranteed to be safe?** No, if it uses static mutable state or unsafe dependencies.
5. **Is `final List<String>` always immutable?** No; the list behind the reference may still be mutable or modified through another alias.
6. **Does `List.copyOf` deep-copy objects inside the list?** No. Mutable elements require an additional strategy.
7. **Do two `AtomicInteger` fields automatically protect an invariant spanning both fields?** No; each individual update is atomic, but the combined state may be inconsistent.
8. **Can a thread-safe class still deadlock?** Yes. Data safety and liveness are distinct properties.
9. **Does `ConcurrentHashMap` turn any sequence of calls on the map into a transaction?** No; you must choose an atomic operation matching the contract, such as `computeIfAbsent` when appropriate.
10. **When must a caller use a lock outside a class?** When coordinating a sequence of operations beyond the atomicity scope promised by the class, provided the contract supports it; it is often better to consider a composite API that protects the invariant inside the class.

**Remember:** a thread-safe class **upholds its contract under concurrent access**. Identify state and invariants, protect the entire logical operation, encapsulate mutable state, publish data safely under the JMM, and distinguish the safety of *each method* from the atomicity of *caller-composed sequences*.

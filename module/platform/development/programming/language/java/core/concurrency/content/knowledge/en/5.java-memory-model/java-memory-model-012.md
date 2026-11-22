# Double-Checked Locking and Conditions for Using `volatile` in Java

## 1. Learning Objectives

After this lesson, you will be able to:

- Understand what **double-checked locking (DCL)** is and explain the different problems solved by the two `null` checks.
- Analyze the roles of **`synchronized`**, **`volatile`**, the *happens-before* relationship, visibility, ordering, and **safe publication** in the Java Memory Model (JMM).
- Correctly write a lazy initializer using DCL on **Java 17+**, and know why the DCL pattern without `volatile` is not considered safe under the JMM.
- Distinguish between **preventing duplicate object creation** and **publishing a fully constructed object**; recognize why `volatile` alone or a single check outside the lock is insufficient.
- Identify the **conditions for applying DCL**, the limitations of the design pattern, and simpler alternatives such as eager initialization, **initialization-on-demand holder**, enum, and `synchronized` access.
- Avoid confusing DCL with protecting **mutable** state inside an object after initialization, or with a singleton mechanism across multiple JVMs/processes.

The scope is **general Java concurrency**. This lesson does not cover container singletons, lifecycle, dependency injection, or Spring-managed beans.

## 2. The Problem: Lazy Initialization Under Contention

Suppose a service object has a significant creation cost and is only needed when first used:

~~~java
// Simple illustrative snippet; not yet thread-safe:
private static Resource instance;

public static Resource getInstance() {
    if (instance == null) {
        instance = new Resource();
    }
    return instance;
}
~~~

If two threads both observe `instance == null`, both may create the object. Beyond **duplicate creation**, unsynchronized access to a plain field can also violate **visibility** and **safe publication** requirements.

Typical requirements for a lazy singleton within **one classloader of a single JVM**:

1. Do not create the resource when the class is loaded; create it only on first use.
2. Under contention, **only one successful initialization** is published as the shared instance.
3. A thread that reads the **properly initialized** instance sees all necessary writes from construction.
4. After initialization, common calls do not contend on a monitor every time.
5. If the constructor fails, do not publish a reference without a valid object.

DCL arises from the requirement to **avoid acquiring a lock on the fast access path after initialization**, while still locking and re-checking when object creation is actually needed.

Do not use DCL just because the word "singleton" appears: resource initialization with side effects, configuration changes, destruction/re-initialization, or multiple owners require their own contracts before choosing this pattern.

## 3. Correct DCL in Java 17+

The standard pattern uses **a `static volatile` field**, **a fixed lock**, and **two `null` checks**:

~~~java
public final class LazyResource {
    private static volatile LazyResource instance;

    private final int value;

    private LazyResource() {
        value = 42;
    }

    public static LazyResource getInstance() {
        LazyResource result = instance; // Single volatile read.
        if (result == null) {           // Check 1: fast path.
            synchronized (LazyResource.class) {
                result = instance;      // Re-read volatile under the lock.
                if (result == null) {   // Check 2: prevent duplicate creation.
                    result = new LazyResource();
                    instance = result;  // Volatile write: publish instance.
                }
            }
        }
        return result;
    }

    public int value() {
        return value;
    }
}
~~~

This is a **complete, compilable class**, though not a standalone runnable application because it has no `main()`. Program examples with `main()` appear in subsequent sections.

Part-by-part analysis:

- **`private static volatile LazyResource instance`**: every thread accessing the DCL path must read/write the same `volatile` field. `volatile` participates in guaranteeing the visibility and ordering required for object publication in the modern JMM.
- **`LazyResource result = instance`**: takes a snapshot from a volatile read. Using a local variable avoids reading the `volatile` field multiple times on the common path; this is a minor optimization and makes the check flow easier to follow.
- **First `if (result == null)`**: if the instance has already been published, return the reference directly without acquiring the monitor.
- **`synchronized (LazyResource.class)`**: only one thread at a time can execute the guarded initialization section. This lock is tied to the class itself, is stable, and is shared by all threads.
- **Inner `result = instance` and `if (result == null)`**: while a thread was waiting for the lock, another thread may have already created the instance. Re-read the `volatile` field and perform the second check to avoid creating it again.
- **`new LazyResource()` before `instance = result`**: the constructor completes normally before the code performs the volatile write that publishes the reference. Other threads observing the reference from a subsequent volatile read have the appropriate happens-before relationship.
- **`return result`**: returns the reference that was read or initialized, without needing another volatile read.

### Contention Flow with Two Threads

Suppose both A and B observe `null` at check 1:

~~~text
A: read instance == null
B: read instance == null
A: acquire LazyResource.class monitor
B: wait for monitor
A: re-read instance == null
A: new LazyResource() completes
A: volatile write instance = object
A: exit synchronized
B: acquire monitor
B: re-read instance -> object
B: check 2 sees non-null, does NOT create another
B: return the same object
~~~

If B enters the lock first, the roles are reversed; the conclusion does not change. Threads may interleave in many orders, but the locking rule and check 2 preserve single shared instance creation.

DCL solves **lazy initialization**. It does not automatically make every method in `LazyResource` thread-safe. If the object has mutable state after initialization, that state still needs an appropriate synchronization protocol.

## 4. Three Different Problems: Mutual Exclusion, Publication, and Logic

Do not conflate these mechanisms:

| Mechanism | What does it protect? | Sufficient on its own for DCL? |
| --- | --- | --- |
| Check 1 outside the lock | Skips the monitor when the instance is already ready | No: two threads can both see `null` |
| `synchronized` around instance creation | Mutual exclusion and ordering among threads using **the same lock** | No, if the fast read path outside the lock still lacks safe publication |
| Check 2 inside the lock | Prevents duplicate creation after waiting for another thread to create it | No, if the reference published outside the lock is unsafe |
| `volatile instance` | Visibility, ordering, and volatile publish/read of the reference | No, if the "if null then create" decision is not guarded |
| `final` in Resource | Initialization semantics for `final` fields when the object is properly constructed | Does not replace the rules for creating a single instance and safely publishing all state |

**The formula for the correct pattern:** volatile reference **and** critical section **and** two checks. Omitting any part requires a different justification rather than relying on test run results.

## 5. Why Is Missing `volatile` Dangerous?

A commonly seen older version:

~~~java
// Buggy illustrative code, do not use in concurrent code:
private static Resource instance; // Missing volatile!

public static Resource getInstance() {
    if (instance == null) {
        synchronized (Singleton.class) {
            if (instance == null) {
                instance = new Resource();
            }
        }
    }
    return instance;
}
~~~

This is **illustrative pseudocode inside a class named `Singleton`**; `Resource` is a hypothetical type. It is not a complete runnable Java file.

The problem: **the first `instance` read path does not go through the same monitor**, nor is it a volatile read. Therefore, the creating thread's write of the reference and another thread's unsynchronized read outside the lock **are not ordered by happens-before** in the required way. The reading thread can observe data that was not safely published.

### What Does "Seeing a Reference Before Initialization Completes" Mean?

We often describe it in three conceptual steps:

~~~text
1. Allocate memory for Resource.
2. Assign initial data/state of Resource.
3. Publish the object address via instance.
~~~

These are **not three fixed bytecode instructions** of every constructor/JIT. It is a conceptual explanation of the visibility of memory effects. Without JMM constraints, another thread may observe the reference via an unsynchronized access with no guarantee that it observes the full state set up by the creating thread.

This is especially important if `Resource` has **non-final** fields assigned by the constructor. The JMM provides specific guarantees for **`final` fields** of a properly constructed object, but they do not turn DCL without `volatile` into a generally safe pattern, nor do they guarantee all dependent state and all singleton requirements.

Do not try to build a demo that "always prints 0" to prove this bug. **Publication/ordering** bugs may not manifest in most runs on a given CPU/JVM. **The lack of happens-before is already sufficient to invalidate correctness**; passing a test does not create a JMM guarantee.

### Volatile Write/Read Establishes Happens-Before

According to the Java Memory Model rules, a **volatile write** to a variable *happens-before* every **subsequent volatile read of that same variable** in synchronization order.

When thread A finishes creating the object and writes `instance = result` to the `volatile` field:

1. Writes before the volatile write in A, including proper object construction, are ordered before publication by program order.
2. Thread B reading a non-null reference from the same `volatile` field afterward has the necessary memory ordering to see the published effects.
3. Actions after the volatile read in B can rely on the state initialized before the volatile write.

Event diagram:

~~~text
Thread A                         Thread B
---------                        ---------
new Resource()
  constructor initializes fields
volatile write: instance = r
          └──── happens-before ──> volatile read: r = instance
                                   reads published r.fields
~~~

**`volatile` must be on the field holding the reference**; simply marking an arbitrary field inside `Resource` as `volatile` is not enough. Making `instance` `volatile` is an essential part of the standard DCL pattern in Java 17+.

## 6. Why Is the Second `null` Check Required?

Even when `instance` is `volatile`, both A and B can still read `null` before either thread writes a valid reference. If the code only checks outside the lock and then unconditionally creates the object upon entering the lock, there will be **two creations**.

Version missing check 2:

~~~java
// Illustrative logic bug:
if (instance == null) {
    synchronized (LockHolder.class) {
        instance = new Resource(); // Did not re-check after waiting for the lock.
    }
}
~~~

This is an illustrative code snippet, where `instance`, `LockHolder`, and `Resource` must be defined in a real program.

The issue is not necessarily a data race: even with a `volatile` reference whose individual reads/writes obey the memory contract, **the check-then-initialize sequence still has a race condition**. Check 2 turns checking and deciding to create into a single unified critical section.

### Runnable Example: Missing Check 2 Still Initializes Twice

Use a latch so both workers pass the outer check before either thread can create the object. This makes the example deterministic and avoids relying on `sleep()` timing.

File **MissingSecondCheckDemo.java**:

~~~java
import java.util.concurrent.CountDownLatch;
import java.util.concurrent.ExecutionException;
import java.util.concurrent.ExecutorService;
import java.util.concurrent.Executors;
import java.util.concurrent.Future;
import java.util.concurrent.atomic.AtomicInteger;

public class MissingSecondCheckDemo {
    private static volatile Resource instance;
    private static final CountDownLatch bothSawNull = new CountDownLatch(2);
    private static final AtomicInteger created = new AtomicInteger();

    static final class Resource {
        final int id;

        Resource(int id) {
            this.id = id;
        }
    }

    static Resource getInstance() throws InterruptedException {
        Resource result = instance;
        if (result == null) {
            bothSawNull.countDown();
            bothSawNull.await();

            synchronized (MissingSecondCheckDemo.class) {
                // Bug: missing re-check of instance inside the lock.
                result = new Resource(created.incrementAndGet());
                instance = result;
            }
        }
        return result;
    }

    public static void main(String[] args)
            throws InterruptedException, ExecutionException {
        ExecutorService pool = Executors.newFixedThreadPool(2);
        try {
            Future<Resource> first =
                    pool.submit(MissingSecondCheckDemo::getInstance);
            Future<Resource> second =
                    pool.submit(MissingSecondCheckDemo::getInstance);

            Resource one = first.get();
            Resource two = second.get();

            System.out.println("constructed = " + created.get());
            System.out.println("same instance = " + (one == two));
        } finally {
            pool.shutdown();
        }
    }
}
~~~

~~~bash
javac -encoding UTF-8 MissingSecondCheckDemo.java
java MissingSecondCheckDemo
~~~

Stdout:

~~~text
constructed = 2
same instance = false
~~~

**Why is this deterministic?** The first thread that reads `null` must wait for `bothSawNull` to reach 0 before creating the object; thus the second thread also reads `null`. Then the two threads acquire the monitor one after another, **but without re-checking**, so each thread creates a different `Resource`. `result` is a local variable storing each thread's newly created object, so the two `Future` results are two different references.

- `volatile` only maintains the memory contract for the reference.
- `synchronized` ensures that each initialization inside the monitor does not happen concurrently.
- Missing check 2 still allows **two sequential initializations** after both threads have passed check 1.

In this example, the latch is a **test-scheduling tool to reproduce the bug**, not something used in a correct DCL implementation.

## 7. Complete Runnable DCL Example on Java 17+

Below is a runnable version applying all three conditions: `volatile`, locking, and re-checking `null`. The example uses concurrent threads, yet the final result is deterministic.

File **VolatileDclDemo.java**:

~~~java
import java.util.concurrent.CountDownLatch;
import java.util.concurrent.atomic.AtomicInteger;
import java.util.concurrent.atomic.AtomicReference;

public class VolatileDclDemo {
    private static volatile Resource instance;
    private static final AtomicInteger constructions = new AtomicInteger();

    static final class Resource {
        final int value;

        Resource(int value) {
            this.value = value;
            constructions.incrementAndGet();
        }
    }

    static Resource getInstance() {
        Resource result = instance;
        if (result == null) {
            synchronized (VolatileDclDemo.class) {
                result = instance;
                if (result == null) {
                    result = new Resource(42);
                    instance = result;
                }
            }
        }
        return result;
    }

    public static void main(String[] args) throws InterruptedException {
        CountDownLatch start = new CountDownLatch(1);
        AtomicReference<Resource> first = new AtomicReference<>();
        AtomicReference<Resource> second = new AtomicReference<>();

        Thread a = new Thread(() -> {
            try {
                start.await();
                first.set(getInstance());
            } catch (InterruptedException ex) {
                Thread.currentThread().interrupt();
            }
        }, "caller-a");

        Thread b = new Thread(() -> {
            try {
                start.await();
                second.set(getInstance());
            } catch (InterruptedException ex) {
                Thread.currentThread().interrupt();
            }
        }, "caller-b");

        a.start();
        b.start();
        start.countDown();
        a.join();
        b.join();

        System.out.println("constructed = " + constructions.get());
        System.out.println("same instance = " + (first.get() == second.get()));
        System.out.println("value = " + first.get().value);
    }
}
~~~

~~~bash
javac -encoding UTF-8 VolatileDclDemo.java
java VolatileDclDemo
~~~

Stdout under normal execution without external interrupts:

~~~text
constructed = 1
same instance = true
value = 42
~~~

**Exact reasoning:**

1. `start.await()` only coordinates the starting point of the two workers; it does not force both threads to see `null`. DCL must be correct whether one thread arrives first or both arrive simultaneously.
2. Both read `instance` via `volatile`.
3. The thread that acquires the monitor first creates the object once and writes the `volatile` `instance`.
4. The thread that enters the monitor later re-reads `instance`; it sees the already published object and does not create another.
5. `join()` makes `main` wait for both workers to finish before observing the results. `AtomicReference` and `AtomicInteger` also provide thread-safe shared operations for observed data.
6. `Resource.value` is `final` and set in the constructor before publishing the reference; the program does not mutate the object after initialization.

For real business-logic demos, errors should be propagated from workers to the caller or recorded as error state; this example focuses on the instance publication rule when no interrupts or unexpected exceptions occur.

### Note on Exceptions During Initialization

If `new Resource(...)` throws an exception **before the assignment** `instance = result`, the DCL code above does not publish a failed object; `instance` remains `null` and subsequent calls can attempt creation again. A specific policy may be needed if initialization has partial side effects or if failures should not be retried.

DCL does not provide atomicity for side effects outside the constructor (such as writing files, opening remote connections, or calling services). Design cleanup, retry, and idempotency when those requirements actually exist.

## 8. Conditions for Applying `volatile` in DCL

### 8.1. The Reference Must Be `volatile` in the Standard DCL Model

In Java 17+, the simple and clear choice is:

~~~java
private static volatile Resource instance;
~~~

All paths—reading outside the lock, re-reading inside the lock, and writing to publish—must use that same field. If a reference is cached in a **non-volatile** field or read through another shortcut, happens-before must be re-analyzed for that path.

### 8.2. Do Not Let `this` Escape from the Constructor

The example below is an illustrative **anti-pattern**, not a standalone program:

~~~java
class EscapingResource {
    EscapingResource(EventBus bus) {
        bus.register(this); // this is published externally inside the constructor!
        // Important initialization steps may not be finished yet.
    }
}
~~~

`EventBus` is a hypothetical type. This is the **`this` escape** problem: another thread may receive the reference before the constructor finishes through another publication channel. DCL only publishes the instance **after the constructor returns**, but it cannot fix the constructor itself sending `this` to another thread earlier.

Good design requires fully constructing the object before sharing it; avoid invoking callbacks, registering listeners that expose `this`, or starting threads from the constructor if they might use incomplete state.

### 8.3. `volatile` Does Not Protect Mutable State After Initialization

Suppose a singleton has a field:

~~~java
final class CounterService {
    int count;

    void increment() {
        count++;
    }
}
~~~

This is an illustrative class without `main()`. Even if published using `volatile` DCL, the object may be **created and safely published**, yet two threads calling `increment()` concurrently still have a data race on `count` and can lose updates.

To make `count` safe, you must use locks, an atomic counter, or a design without mutable state. **`volatile` on the reference only guarantees publication**; it does not "spread" thread safety to all methods, data structures, or fields inside the object.

Similarly, if configuration is modified after initialization, keeping the reference `volatile` **does not automatically make multiple fields in the configuration update atomically as a snapshot**. When the entire configuration needs to change, you can create a **new immutable object** and publish the entire reference via a `volatile`/`AtomicReference`; that is a different model from lazy DCL creating a single instance.

### 8.4. `final` Fields Support Immutable Design but Do Not Replace DCL

Marking `Resource`'s state components as `final` and not modifying them after construction makes reasoning easier. However:

- `final` has special semantics in the JMM when an object is properly constructed, but it does not by itself guarantee that **only one thread creates the object**.
- A `final` reference elsewhere does not make **check-null-then-create** on a plain field atomic.
- A mutable object pointed to by a `final` field still needs protection if multiple threads update it.

### 8.5. If You Don't Need Lazy Initialization, Don't Use DCL

If initialization cost is low and resource creation does not need to be deferred, using static/class initialization is usually simpler. DCL has more preconditions, is easy to modify incorrectly, and requires clear tests/invariants.

## 9. Simpler Alternatives

### 9.1. Eager Initialization with `static final`

~~~java
public final class EagerSingleton {
    private static final EagerSingleton INSTANCE = new EagerSingleton();

    private EagerSingleton() {}

    public static EagerSingleton getInstance() {
        return INSTANCE;
    }
}
~~~

This is a complete, compilable class. **JVM class initialization** provides synchronization guarantees for class initialization. The object is created when the class is initialized—not necessarily at the exact moment `getInstance()` is first called—and there is no `null` check in the getter.

Pros: minimal code, hard to make publication mistakes. Cons: creates the object when the class is initialized, which may be earlier than when the resource is actually needed.

### 9.2. Initialization-on-Demand Holder

This is usually the preferred approach for a **static** lazy singleton when custom initialization policies are not needed:

File **HolderSingletonDemo.java**:

~~~java
public class HolderSingletonDemo {
    static final class Resource {
        final int value;

        Resource(int value) {
            this.value = value;
        }
    }

    private static final class Holder {
        static final Resource INSTANCE = new Resource(42);
    }

    static Resource getInstance() {
        return Holder.INSTANCE;
    }

    public static void main(String[] args) {
        Resource first = getInstance();
        Resource second = getInstance();

        System.out.println("same instance = " + (first == second));
        System.out.println("value = " + first.value);
    }
}
~~~

~~~bash
javac -encoding UTF-8 HolderSingletonDemo.java
java HolderSingletonDemo
~~~

Stdout:

~~~text
same instance = true
value = 42
~~~

**Mechanism:** class `Holder` is initialized on first use of the non-constant static field `INSTANCE`. JVM class initialization rules guarantee safety across multiple threads without user code having to write locks or `volatile`. Subsequent calls simply read the already initialized reference.

Limitation: this is still **one instance per classloader that initialized the corresponding class**, not a system-wide distributed singleton. If `Holder` initialization fails under the class initialization mechanism, the JLS specifies distinct initialization error behavior; unlike DCL, subsequent calls do not retry the constructor.

### 9.3. Enum Singleton

File **EnumSingletonDemo.java**:

~~~java
public class EnumSingletonDemo {
    enum Service {
        INSTANCE;

        int calculate() {
            return 6 * 7;
        }
    }

    public static void main(String[] args) {
        Service first = Service.INSTANCE;
        Service second = Service.INSTANCE;

        System.out.println("same instance = " + (first == second));
        System.out.println("value = " + first.calculate());
    }
}
~~~

~~~bash
javac -encoding UTF-8 EnumSingletonDemo.java
java EnumSingletonDemo
~~~

Stdout:

~~~text
same instance = true
value = 42
~~~

Enums have JVM-managed initialization as well as enum-specific serialization behavior. This is often a good choice if you need a single instance for an enum type and have no standard class-inheritance requirements. As with other singleton options, mutable fields inside an enum still need protection under concurrent access.

### 9.4. Simple `synchronized` Getter

~~~java
public final class SynchronizedSingleton {
    private static SynchronizedSingleton instance;

    private SynchronizedSingleton() {}

    public static synchronized SynchronizedSingleton getInstance() {
        if (instance == null) {
            instance = new SynchronizedSingleton();
        }
        return instance;
    }
}
~~~

This class can compile standalone; it has no `main()`. Because **every call to the getter goes through the same monitor**, the code has mutual exclusion and happens-before guarantees without needing `volatile` on `instance`.

The advantage is clarity and maintainability. The disadvantage is entering `synchronized` on every call, even after the singleton has been created. Do not assume this cost is significant: measure in the real application context if performance is an evidence-backed requirement.

## 10. Comparison Table: DCL and Alternatives

| Approach | Lazy on first use? | Safe publication mechanism | Cost / complexity | When to choose |
| --- | --- | --- | --- | --- |
| `static final` / eager | Does not wait for getter; initialized at class initialization | JVM class initialization | Simple | Eager creation is acceptable |
| Holder idiom | Yes, on first use of `Holder` | JVM class initialization | Simple | Standard static lazy singleton |
| Enum singleton | At enum initialization | JVM class initialization; enum semantics | Simple | Singleton naturally modeled as an enum |
| Synchronized getter | Yes | Monitor on every call | Easy to understand, repeated locking | Getter does not need fast-path optimization |
| Volatile DCL | Yes | Volatile write/read + monitor + check 2 | More complex | Need lazy initialization and a lock-free post-initialization read path |

**Practical decision rules:**

1. Do you really need lazy initialization? If not, consider `static final`.
2. Do you need a static instance with a no-arg or self-managed constructor? Consider Holder.
3. Can the singleton be modeled as an enum without class/API constraints? Consider enum.
4. Is the getter called frequently enough that monitor overhead is significant in measurements? If not, a `synchronized` getter is usually sufficient.
5. If you still need DCL, use the full **`volatile` + check 1 + lock + check 2 + publish** pattern and document the invariants.

## 11. Common Mistakes When Using DCL

| Incorrect code / reasoning | Problem | Fix |
| --- | --- | --- |
| `instance` is a plain field | Read path outside the lock lacks safe publication | Make the reference `volatile` or choose an approach where all accesses are synchronized |
| Only checking `null` outside the lock | Multiple threads pass the check and create multiple objects | Re-check **inside** the same monitor |
| Using only `volatile` and `if (null) new` | `volatile` does not make check-then-act atomic | Add proper synchronization / CAS |
| Reading/writing through different locks | No shared mutual exclusion for initialization | Use **the same fixed monitor** |
| Passing `this` to a callback in the constructor | Can be observed before construction finishes | Avoid `this` escape |
| Initializing then updating plain fields from multiple threads | DCL only protects initial publication | Add separate synchronization for mutable state |
| Concluding DCL is right because 1,000 test runs passed | Failing schedules can be rare and vary by JIT/CPU | Reason using the JMM, invariants, and controlled testing |
| Using `Thread.sleep()` before reading `instance` | `sleep` does not establish happens-before for the reference | Use `volatile` / `synchronized` / class initialization |
| Initializing an object and swapping instances at runtime while treating it as a fixed singleton | Lifetime rules differ completely from lazy DCL | Design reload, versioning, and atomic swap separately |
| Assuming a singleton means one instance across multiple JVMs | Each process/classloader has its own state scope | Use out-of-JVM coordination if a system-wide resource is needed |

### Can You Fix Non-`volatile` DCL by Locking Only When `null`?

No. The problem lies in **the lock-free fast read path**: even though the constructor and reference write happen inside `synchronized`, a thread reading when `instance != null` still skips the monitor, so it does not receive the guarantee of reading under the same lock. If you do not want `volatile`, every read path must use the same monitor (such as a `synchronized` getter) or use class initialization according to contract.

### Should You Use `AtomicReference` Instead of `volatile`?

`AtomicReference` supports atomic reads/writes and CAS, but **does not automatically turn "if null then create object" into a single constructor invocation**. For example, two threads may both create a candidate and one CAS wins: only one reference is finally published, but **the constructor ran twice**. If the constructor has side effects or creation is expensive, that can violate requirements.

DCL uses `synchronized` to **prevent duplicate creation**, not just to pick a winning reference. If you use CAS, you must analyze both the side effects of candidate creation and the policy for discarding the losing candidate.

### Does `volatile` Prevent Concurrent Data Modification?

No. It provides visibility/ordering for the field and individual reads/writes according to contract, but it does not make a multi-field transaction atomic. For example, `volatile int count; count++;` still has a read-modify-write race. If the singleton manages a counter, use `AtomicInteger` or a lock protecting that action.

## 12. Limitations to Know

### Scope of "One Instance"

A `static` field belongs to the class defined by a **classloader** within a single JVM. Different classloaders can load separate definitions of the class, so DCL does not guarantee "system-wide uniqueness." Multiple processes, containers, or application instances also have separate state.

If you need **one system-wide task/resource**, a local Java lock or singleton is not enough: you must design a coordination mechanism at the shared data store or infrastructure level. This is a general Java concurrency principle, not a framework-specific mechanism.

### Constructors, Callbacks, and Circular Dependencies

DCL is only simple when the constructor completes before publication and has no circular dependencies. If `Resource` calls `getInstance()` from its own constructor, or calls a dependency that calls back into this singleton, recursion, initialization cycles, or unpublished state can occur. Synchronization does not automatically resolve logical circular dependencies.

If the constructor spawns a background thread or emits a callback referencing `this`, another thread may observe the object before the constructor finishes. Avoid side-effecting work in constructors and separate the start/registration step when needed.

### Reflection, Serialization, and Cloning

Standard DCL only ensures that the **`getInstance()`** path does not create duplicates within the same class/lock scope. If the class has other instantiation or copying paths (accessible constructors from elsewhere, serialization without singleton handling, `clone()`, etc.), those paths must be examined independently if "one instance" is a strict requirement. Enums help manage some of these via enum semantics, but the choice must fit the API being designed.

### Retrying After Failed Initialization

If the constructor throws an exception, DCL does not assign the reference and subsequent calls may retry. However, if external resources were already created before the failure, the next attempt may produce additional side effects. Before applying lazy initialization to critical resources, decide: **retry, cache the error, close partial resources, or treat the failure as unrecoverable**. DCL does not provide this policy on its own.

## 13. How to Test DCL?

**Useful tests:**

1. Place a counter in the constructor via **`AtomicInteger`**, have multiple threads call the getter concurrently, and verify the construction count equals 1 when calls succeed.
2. Use **`CountDownLatch`** or a barrier to maximize contention at the same point (do not rely on `sleep()`).
3. Compare returned references using **`==`** when the contract requires the same instance within a classloader.
4. Verify fields set by the constructor before publication and exercise methods according to contract.
5. Test constructor failures, retries, and cleanup if the code has error-handling requirements.
6. When mutable state exists, separately test concurrent read/write paths of that state; do not treat a singleton test as a test of the object's thread safety.

**Testing cannot prove** that every schedule on every JVM/CPU is correct. Safety conclusions must rest on synchronization structure and JMM rules. `MissingSecondCheckDemo` reproduces a logic bug through deliberate scheduling; by contrast, a missing-`volatile` bug usually cannot rely on a guaranteed stdout to prove in a specific runtime.

If benchmarking `synchronized` versus DCL, use appropriate measurement tools, account for warmup/JIT time, and distinguish throughput from latency. Optimization costs only matter when measured; never trade correctness for speculation.

## 14. Self-Check Questions

**1. Why is `volatile` needed even though `synchronized` is used?**  
Because the fast read path can bypass acquiring the lock. `volatile` provides the publication and visibility contract for threads observing the reference outside `synchronized`.

**2. Why is check 2 still mandatory when `instance` is `volatile`?**  
Two threads can both read `null` before either publishes the instance. After waiting for the lock, the reference must be re-read to prevent duplicate creation.

**3. If you use `private static final Resource INSTANCE = new Resource()`, do you need DCL?**  
No. JVM class initialization already safely manages static initialization; the trade-off is that the instance may be created during class initialization rather than when the getter is called.

**4. If a singleton has a field `int count` and multiple threads call `count++`, does `volatile` DCL protect `count`?**  
No. DCL protects initial reference publication. A mutable counter needs separate atomicity/synchronization.

**5. If the constructor fails before `instance = result`, does DCL store a valid object?**  
No; the volatile write statement has not executed. Subsequent calls may retry, though partial side effects require a separate cleanup/retry policy.

**6. Can `synchronized` be replaced with CAS on an `AtomicReference` to guarantee the constructor runs only once?**  
Not necessarily. Multiple threads can construct candidates before CAS, even though only one candidate is published.

**7. Does a singleton in one JVM mean a singleton across the entire system?**  
No. Different processes and classloaders can have separate instances. DCL only protects the corresponding static field/monitor scope.

**8. When is the holder idiom more suitable than DCL?**  
When you need a standard lazy static singleton and do not need custom control over the initialization path with special locks/policies. JVM class initialization provides thread safety with less code.

## 15. Takeaways

For the **standard double-checked locking pattern on Java 17+**, three conditions go together: a **`volatile` instance field**, **a shared monitor during initialization**, and **a `null` re-check after acquiring the lock**. `volatile` handles **safe publication and visibility**; `synchronized` and check 2 handle **preventing duplicate creation under contention**. DCL only guarantees initial construction and reference publication; the safety of mutable state, external non-JVM resources, and complex lifecycles must be designed separately.

When there is no clear requirement making DCL beneficial, consider **holder**, **enum**, or **static initialization** to reduce complexity and the risk of introducing bugs during maintenance.

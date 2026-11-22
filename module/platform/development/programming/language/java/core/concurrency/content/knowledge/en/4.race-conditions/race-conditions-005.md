# Check-then-act and Check-Then-Act Bugs in Java Concurrency

**Check-then-act** is the code pattern of "check a condition, then perform an action based on the check result." In a single-threaded program, the two steps are normally understood as sequential. In a multi-threaded program, another thread can **modify the state used for the condition right after the check step and before the act step**. When that happens, the action is performed based on stale information, forming a type of **race condition**.

An example that looks reasonable:

```java
// Illustrative snippet; assumes 'cache' is already declared.
if (!cache.containsKey("config")) {    // Check
    cache.put("config", loadConfig());   // Act
}
```

If two threads both see that the key does not exist yet, **both may run `loadConfig()` and write the result**. Even if `containsKey()` and `put()` themselves are thread-safe, this pair of operations is not necessarily an *atomic operation*. The goal is to recognize that dangerous window, understand why naive "check-then-write" solutions fail, and choose the appropriate Java mechanism to combine the check with the action.

## 1. What is check-then-act?

A condition can inspect state and then decide to perform an action:

- "If the configuration is not in the cache yet, create the configuration."
- "If one slot remains, book it and decrement the available count."
- "If the count is below the limit, increment the count."
- "If the resource has not been initialized yet, initialize it."

The problem lies in the **integrity of the entire `check → act` sequence**, not necessarily in each individual statement. Each statement may be valid when executed independently, but interleaving between threads breaks the condition that the action assumes.

Suppose a resource is allowed to be created only **once**:

| Time | Thread A | Thread B | Shared state |
|---|---|---|---|
| T0 |  |  | Resource does not exist yet. |
| T1 | Read: not present. |  | Not present. |
| T2 |  | Read: not present. | Not present. |
| T3 | Create resource A. |  | A created. |
| T4 |  | Create resource B. | B also created. |
| T5 | Write A to cache. |  | Cache contains A. |
| T6 |  | Write B to cache. | Cache contains B; A is overwritten. |

In the end, the cache may hold only one value, but that **does not prove that initialization happened only once**. If creation has side effects (connections, writing data, emitting events, allocating resources), those side effects can occur twice.

The technical term *TOCTOU* (*time of check to time of use*) also describes this class of bug: state is verified at one point in time but used at another, when the truth may have already changed.

## 2. Properties to distinguish

**Atomicity:** the critical set of operations is executed as a single unit with respect to competing threads, without letting another thread observe or interfere with intermediate state in a way that breaks an invariant. With check-then-act, **the check and the update** must belong to the same coordination mechanism.

**Visibility:** a value written by one thread is seen by another thread according to the synchronization relationships in the Java Memory Model. `volatile` or `AtomicInteger.get()` can help reads see the latest value, **but they do not automatically turn two separate actions into one atomic operation**.

**Ordering:** `happens-before` constrains visibility and memory ordering between related operations. Having a valid `happens-before` relationship for a write/read still does not make `if (condition) act()` automatically safe without protecting the entire decision.

**Invariant:** a rule that must always hold, such as `available >= 0`, a code being issued only once, or `available + reserved == capacity`. The fix must protect the **invariant**, not merely patch a single line of code that looks risky.

It is important to separate two types of bugs that often appear together: a *data race* under the Java Memory Model is conflicting access to the same variable without synchronization/`happens-before`; whereas a *race condition* is an outcome that depends on undesirable interleaving. For example, two separate operations on `ConcurrentHashMap` may not create a data race in the internal structure, yet still create a **logic-level race condition** if the condition and action are not combined.

## 3. Reproducing the bug with ConcurrentHashMap

Using `ConcurrentHashMap` **eliminates unsafe data-structure access bugs** and isolates the check-then-act bug itself: `get()` and `put()` are individually thread-safe, yet the two calls do not automatically combine into a single action. Two `CountDownLatch` instances are unnecessary; a single latch counting two checks is enough to deliberately force the faulty interleaving.

Create the file **`CheckThenActRace.java`**:

```java
import java.util.concurrent.ConcurrentHashMap;
import java.util.concurrent.CountDownLatch;
import java.util.concurrent.atomic.AtomicInteger;

public class CheckThenActRace {
    public static void main(String[] args) throws InterruptedException {
        ConcurrentHashMap<String, String> cache = new ConcurrentHashMap<>();
        AtomicInteger initializations = new AtomicInteger();
        CountDownLatch bothSawMissing = new CountDownLatch(2);

        Runnable worker = () -> {
            if (cache.get("config") == null) {
                bothSawMissing.countDown();

                try {
                    bothSawMissing.await();
                } catch (InterruptedException e) {
                    Thread.currentThread().interrupt();
                    return;
                }

                int attempt = initializations.incrementAndGet();
                cache.put("config", "created-" + attempt);
            }
        };

        Thread first = new Thread(worker, "first");
        Thread second = new Thread(worker, "second");

        first.start();
        second.start();
        first.join();
        second.join();

        System.out.println("Initializations: " + initializations.get());
        System.out.println("Cache entries: " + cache.size());
    }
}
```

Run with JDK 17+:

```bash
javac CheckThenActRace.java
java CheckThenActRace
```

Output:

```text
Initializations: 2
Cache entries: 1
```

Here both threads read `null`, then each thread decrements `bothSawMissing` and waits until **both have passed the check**. Because neither thread writes to the cache before that point, both enter the value-creation branch. `AtomicInteger` only guarantees that counting `initializations` is safe; it does **not** protect the `get() == null` condition. The two `put()` calls can happen in either order, so the example does not print the final value (that value is non-deterministic).

Key takeaway: replacing `HashMap` with `ConcurrentHashMap` solves thread-safe map access, **not** the business-level `get() → if → put()` sequence.

## 4. Fixing cache initialization with a single atomic operation

For `ConcurrentHashMap`, `computeIfAbsent(key, mappingFunction)` provides an atomic operation for "if the key does not have a value yet, compute and associate the value." While the key is unmapped and not removed or modified elsewhere, competing threads share the initialization result instead of each thread running the computation on its own.

Create the file **`AtomicCacheInitialization.java`**:

```java
import java.util.concurrent.ConcurrentHashMap;
import java.util.concurrent.CountDownLatch;
import java.util.concurrent.atomic.AtomicInteger;

public class AtomicCacheInitialization {
    public static void main(String[] args) throws InterruptedException {
        ConcurrentHashMap<String, String> cache = new ConcurrentHashMap<>();
        AtomicInteger initializations = new AtomicInteger();
        CountDownLatch startTogether = new CountDownLatch(1);

        Runnable worker = () -> {
            try {
                startTogether.await();
            } catch (InterruptedException e) {
                Thread.currentThread().interrupt();
                return;
            }

            cache.computeIfAbsent("config", key -> {
                initializations.incrementAndGet();
                return "created";
            });
        };

        Thread first = new Thread(worker, "first");
        Thread second = new Thread(worker, "second");
        first.start();
        second.start();

        startTogether.countDown();
        first.join();
        second.join();

        System.out.println("Initializations: " + initializations.get());
        System.out.println("Cache entries: " + cache.size());
        System.out.println("Config: " + cache.get("config"));
    }
}
```

```bash
javac AtomicCacheInitialization.java
java AtomicCacheInitialization
```

Output:

```text
Initializations: 1
Cache entries: 1
Config: created
```

Unlike the buggy example, "check whether the key is present and compute a value if missing" lives inside **a single method with an atomic contract**. With `ConcurrentHashMap.computeIfAbsent`, the mapping function is applied at most once per invocation needing to establish a mapping per the map's contract; concurrent calls for the same key do not produce multiple successful values for the same missing-key episode as in the earlier example.

**Conditions that must not be overlooked:**

- `mappingFunction` should be short, non-blocking, and must not modify the same map being computed. Other updates may be blocked during computation.
- If the function returns `null` or throws an exception, no new mapping is established; future calls may recompute. If the mapping is removed after creation, a later call may also recreate it.
- Contracts across `Map` types are not identical: the default `Map.computeIfAbsent` **does not guarantee synchronization or atomicity**. When relying on atomicity, use and read the contract of the specific concurrent implementation, such as `ConcurrentHashMap`.
- `putIfAbsent(key, value)` can also atomically insert a value if the key is absent, but when written as `putIfAbsent(key, expensiveCreate())`, the expression `expensiveCreate()` is evaluated **before** the method call; multiple threads can still create redundant values. Choose `computeIfAbsent` when you need to avoid redundant computation and can satisfy the mapping function constraints.

## 5. "Check limit then increment" bug: AtomicInteger does not fix two separate statements

Consider the requirement "allow at most one slot." The following snippet can still fail even when `booked` is an `AtomicInteger`:

```java
// Illustrative code that is NOT safe under concurrent thread contention.
if (booked.get() < 1) {
    booked.incrementAndGet();
}
```

Two threads can both read `0 < 1` and then both increment. `incrementAndGet()` is atomic for **a single increment**, but the entire "read to check → increment" sequence is not. `AtomicInteger` does not automatically lock any surrounding block of code.

A correct approach for **a single state variable** is a compare-and-set (CAS) loop: read the old value, check the condition, and write the new value only if the value is still equal to the one read. If CAS fails because another thread won first, re-read and re-check.

Create the file **`AtomicReservation.java`**:

```java
import java.util.concurrent.atomic.AtomicInteger;

public class AtomicReservation {
    private static boolean reserveOne(AtomicInteger available) {
        while (true) {
            int current = available.get();

            if (current <= 0) {
                return false;
            }

            if (available.compareAndSet(current, current - 1)) {
                return true;
            }
            // Value changed: re-read and re-check the invariant.
        }
    }

    public static void main(String[] args) throws InterruptedException {
        AtomicInteger available = new AtomicInteger(1);
        AtomicInteger accepted = new AtomicInteger();

        Runnable request = () -> {
            if (reserveOne(available)) {
                accepted.incrementAndGet();
            }
        };

        Thread first = new Thread(request);
        Thread second = new Thread(request);
        first.start();
        second.start();
        first.join();
        second.join();

        System.out.println("Accepted: " + accepted.get());
        System.out.println("Available: " + available.get());
    }
}
```

```bash
javac AtomicReservation.java
java AtomicReservation
```

Output:

```text
Accepted: 1
Available: 0
```

Even though which thread wins is non-deterministic, the overall result is always right: only one CAS can change `1 → 0`; the other thread reads `0` or fails CAS and re-reads, so it never drops below 0. This is how **check + act** are combined at the same atomic point for a single variable.

You can consider `AtomicInteger.updateAndGet` or `getAndUpdate` when the update expression is clear enough, but the supplied function **may be invoked multiple times** under CAS contention: do not place side effects such as sending emails, writing files, or incrementing an independent counter inside the update lambda. The CAS code in the example increments `accepted` only after CAS actually succeeds.

## 6. For multiple related variables, use the same protection scope

CAS on a single `AtomicInteger` does not automatically protect an invariant spanning **multiple fields**. For example, a system tracking `available` and `reserved` must maintain `available + reserved == capacity`. If one variable is updated and another thread reads the other variable in between, it may observe a temporarily invalid state.

A straightforward approach is to place both the condition and the related updates inside the same `synchronized` region on **the same lock object**.

Create the file **`SynchronizedReservation.java`**:

```java
import java.util.concurrent.atomic.AtomicInteger;

public class SynchronizedReservation {
    static final class Inventory {
        private int available = 1;
        private int reserved = 0;

        synchronized boolean reserve() {
            if (available == 0) {
                return false;
            }

            available--;
            reserved++;
            return true;
        }

        synchronized String snapshot() {
            return "Available: " + available
                    + ", Reserved: " + reserved;
        }
    }

    public static void main(String[] args) throws InterruptedException {
        Inventory inventory = new Inventory();
        AtomicInteger accepted = new AtomicInteger();

        Runnable request = () -> {
            if (inventory.reserve()) {
                accepted.incrementAndGet();
            }
        };

        Thread first = new Thread(request);
        Thread second = new Thread(request);
        first.start();
        second.start();
        first.join();
        second.join();

        System.out.println("Accepted: " + accepted.get());
        System.out.println(inventory.snapshot());
    }
}
```

```bash
javac SynchronizedReservation.java
java SynchronizedReservation
```

Output:

```text
Accepted: 1
Available: 0, Reserved: 1
```

Both threads use the same `inventory` instance. Only one thread can execute `reserve()` inside the object's monitor at a time. Because the check and both updates are in **the same protected region**, the second thread sees that the slot has already been decremented and cannot over-reserve. The `snapshot()` method also uses that monitor to observe both fields consistently.

In real code, **every read/write path for the same invariant** must follow the protection mechanism. Two `synchronized` blocks using different lock objects do not protect against each other. If you need `tryLock`, timeouts, or interruptible locking, `ReentrantLock` is an option; always call `unlock()` in `finally`:

```java
lock.lock();
try {
    // Check the condition and update the protected state.
} finally {
    lock.unlock();
}
```

This is an illustrative snippet; it assumes `lock` is an already created `ReentrantLock`. Avoid performing I/O or unbounded waiting inside a critical section unnecessarily, because holding a lock for a long time reduces progress and can cause deadlocks if locks are acquired in inconsistent orders.

## 7. Choosing the right tool for each invariant

| Check-then-act requirement | Usually appropriate Java tool | Notes |
|---|---|---|
| Unconditionally increment a counter | `AtomicInteger.incrementAndGet()` | Already a single atomic increment; do not write `get() + set()` yourself. |
| Decrement quota if balance remains | CAS loop with `compareAndSet`, or a suitable atomic update | Re-check the condition after CAS fails; do not run side effects before winning CAS. |
| Initialize a missing key in a concurrent map | `ConcurrentHashMap.computeIfAbsent()` | Short mapping function, do not modify the same map, handle null/exceptions. |
| Insert only if key is absent and value is already ready | `ConcurrentHashMap.putIfAbsent()` | Atomic insertion, but evaluating arguments before the call may be repeated. |
| Read/modify multiple fields that must stay consistent | `synchronized` or `ReentrantLock` for the whole internal transaction | Same lock, same state object, every access path obeys it. |
| Create a resource in an external system (file/database) | Atomic operation or transaction constraint provided by **that system** | JVM locks do not protect other processes or JVMs. |

**"Thread-safe collection" does not mean "thread-safe business operation."** With `ConcurrentHashMap`, individual methods may be thread-safe while `containsKey() → put()` is still buggy; with `Collections.synchronizedMap`, performing a compound action requires holding the right monitor across the entire sequence per its contract, and all related access code must cooperate.

## 8. TOCTOU outside JVM memory

Check-then-act also happens with files and out-of-process systems:

```java
// Not safe if used to guarantee on its own that the file is still absent.
if (!Files.exists(path)) {
    Files.createFile(path);
}
```

This is an illustrative snippet; it assumes `Path path` and the appropriate imports are present. Another process can create the file after `exists()` and before `createFile()`. `Files.createFile(path)` **performs the check and creation atomically with respect to other filesystem operations affecting the directory**, per the API contract; if the file already exists, the API can throw `FileAlreadyExistsException`. Therefore, for "create only if not present," invoke the atomic operation directly and handle the result:

```java
try {
    Files.createFile(path);
    // File created successfully.
} catch (FileAlreadyExistsException e) {
    // File already exists: handle according to business logic.
}
```

This snippet requires `import java.nio.file.Files;`, `import java.nio.file.FileAlreadyExistsException;`, and an appropriate `Path path`; in a real method you also need to handle `IOException`.

For data in a database, "SELECT to see if a code exists, then INSERT" has the same race window. A `synchronized` lock in **one JVM** cannot stop another application or JVM from inserting the same code. The invariant must be enforced where the data is owned using a unique constraint, transaction, or atomic upsert/conditional write per that system's contract. This is a cross-process coordination principle and does not require any specific Java framework.

## 9. Solutions that look right but are not enough

**Adding `volatile` to a check flag and then setting the flag:**

```java
// Illustrates the idea only; 'initialized' is a volatile variable.
if (!initialized) {
    initialized = true;
    initialize();
}
```

Two threads can still both read `false` and both run `initialize()`; `volatile` only provides visibility/ordering rules for accessing the flag, **it does not combine check and act**. Even if the flag becomes `true` before `initialize()` finishes, another thread may mistakenly assume the object is ready. You need an initialization mechanism with the right contract, such as synchronization, the holder idiom, or an appropriate concurrent utility.

**Using `Thread.sleep()` to "reduce the probability" of a race:** changing scheduling can only hide the bug; it does not guarantee correctness. The race can reappear under higher load, on a different machine, or with different JVM scheduling.

**Locking only part of the sequence:** if code locks when writing but leaves the check outside, a race window remains between the two steps. Protect the entire `if (condition) update()` when the condition and update depend on each other.

**Locking in two different places:** `synchronized(lockA)` does not prevent another thread from entering `synchronized(lockB)`. Operations on an invariant must follow a single, clear synchronization protocol.

**Putting side effects into CAS retries:** if the computation runs multiple times under contention, side effects such as sending HTTP requests, writing business logs, or creating orders can be duplicated. Separate deciding whether the state update succeeded from executing side effects, and design idempotency or transactions when cross-system reliability is needed.

**Checking only the final map size:** a size of 1 does not prove single initialization, as shown in the first example; you must also measure the initialization count or critical side effects.

## 10. Testing and diagnosing race conditions

Races depend on execution scheduling; running a test "a thousand times without failure" does not prove the logic is correct. Effective testing means:

1. **Identify the invariant** that must hold: non-negative counts, one initialized value per key, or the allowed number of side-effect executions.
2. **Control scheduling at the dangerous point** using `CountDownLatch`, `CyclicBarrier`, or an explicit coordination mechanism. The first example deliberately forces both threads to see the missing value before allowing writes.
3. **Wait for completion** with `join()` or an appropriate primitive, then verify the invariant and how many times side effects occurred. Do not rely on `sleep()` to assume workers have finished.
4. **Stress test across schedules** as a supplement, not a replacement for atomicity analysis. Use thread dumps or a profiler when suspecting lock contention or deadlocks.
5. **Inspect all update paths**, including other code that calls setters directly, updates the map, removes keys, or modifies fields outside the lock.

When describing a bug, specify: the initial state, the two independent checks, the interleaving point, the violated invariant, and the **atomic point** provided by the fix. That is stronger evidence than simply saying "adding synchronized will fix it."

## 11. Self-check questions

1. **Why are `ConcurrentHashMap.get()` and `put()` both thread-safe yet `if (get == null) put` is still buggy?** Because the separate pair of operations is not atomic: the value can change between the read and the write.
2. **Can `volatile` fix check-then-act?** No, when multiple steps must be combined; it does not create an atomic transaction on its own.
3. **Is `AtomicInteger.incrementAndGet()` always enough for "increment only if below the limit"?** No; the condition check and update must execute within an atomic mechanism such as a CAS loop or a lock.
4. **Why is `computeIfAbsent()` usually better than `putIfAbsent(key, expensiveCreate())` for lazy initialization?** Because `expensiveCreate()` is evaluated before calling `putIfAbsent`, whereas `ConcurrentHashMap.computeIfAbsent`'s mapping function is coordinated within the atomic operation.
5. **When updating two fields that share an invariant, can a single `AtomicInteger` protect both?** No; you need an appropriate atomic state representation or to protect the entire update region with a shared lock or coordination mechanism.
6. **Can a Java lock prevent another JVM from creating a duplicate file or database record?** No. The invariant must be enforced by an atomic operation or constraint of the shared resource.
7. **Why is having one entry in the final cache not enough to prove the program is correct?** Because two creations/writes may still have occurred, causing redundant side effects before the map retains only one value.

**Remember:** check-then-act is only correct when **the condition and the action depending on it are protected within the same atomic operation** across the data's ownership boundary. Choose an atomic API for a single variable, a concurrent collection's atomic operation for a single key, a consistent lock for multiple fields, and an external system's atomic mechanism when the resource lives outside the JVM process.

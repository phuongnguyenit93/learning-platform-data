# Mutable Values in ConcurrentHashMap Still Need Their Own Thread-Safety Contract

## 1. Learning Objectives

After this lesson, you will be able to:

- Explain that **ConcurrentHashMap** protects **operations on the key → value mapping structure**, but does not automatically protect mutable fields or collections inside the value.
- Distinguish between **atomic map operations**, **safety of the object returned from get()**, **safe publication**, **visibility**, **atomicity of business updates**, and **consistent snapshots**.
- Detect bugs when multiple threads concurrently use **map.get(key).count++**, **map.get(key).list.add(...)**, or a **get → mutate → put** sequence without proper synchronization.
- Choose the right solution: **AtomicInteger / AtomicLong**, **LongAdder**, **synchronized value**, **immutable record + compute/merge**, **copy-on-write immutable collection**, or ownership design.
- Analyze the limitations of **computeIfAbsent**, **compute**, **computeIfPresent**, **merge**, **putIfAbsent**, and **replace** when the value is mutated via external references.
- Recognize subtle bugs: replacing a value while another thread holds an old reference, **remove/reset races**, mutating an object affecting equals/hashCode, **multi-key compound invariants**, and mistaking weakly consistent iteration for a snapshot.
- Write and run Java 17+ tests coordinated with CountDownLatch and deterministic outputs; without using sleep to "make a race appear."

This lesson belongs to the **Concurrent Collections** group, with a scope of **general Java concurrency**. Configurations or components specific to Spring are covered in another chapter.

## 2. The Most Important Statement

**ConcurrentHashMap<K,V> allows multiple threads to operate on the map concurrently, but V does not automatically become thread-safe just because it is stored in a ConcurrentHashMap.**

Example:

~~~java
// Illustrative snippet; requires importing the corresponding types.
ConcurrentHashMap<String, Counter> map =
        new ConcurrentHashMap<>();
map.put("orders", new Counter());

Counter c = map.get("orders");
c.count++;  // Not protected by ConcurrentHashMap.
~~~

This is not a standalone runnable program: Counter is a hypothetical mutable type with a count field.

A **map.get("orders")** operation can safely retrieve the published reference of Counter. However, after obtaining the reference, **c.count++** is a **read → increment → write** sequence on the Counter object. If multiple threads run concurrently, there is a risk of **lost updates** even though all get() calls are valid.

Treat these two layers of guarantees as **two different contracts**:

| Layer | What is protected | What is not automatically protected |
| --- | --- | --- |
| ConcurrentHashMap | The key → value relationship and concurrent operations per the map API | Mutable fields and collections inside V |
| Value object | Depends on V's design: immutable, atomic, lock, confinement... | Not automatically guaranteed just because the reference is in the map |
| Business workflow | Depends on invariants and transaction/synchronization protocols | Not automatically guaranteed by a single get() or put() call |

**Memorable slogan:** *A thread-safe map does not mean a thread-safe object graph.*

## 3. What Does ConcurrentHashMap Actually Guarantee?

**ConcurrentHashMap** in java.util.concurrent is a Map that supports concurrent access without locking the entire map for every operation. Independent operations such as **get**, **put**, **remove**, **putIfAbsent**, **replace**, **compute**, and **merge** have their respective contracts.

Key properties to remember:

- **get(key)** returns the current value or null when there is no mapping; it **does not copy** the value and does not make a mutable value immutable.
- **put(key, value)** replaces the mapping for the key, but does not make prior/subsequent operations on the value itself atomic.
- **putIfAbsent** can set a value if the key has no mapping yet; unlike a manual get-then-put when multiple threads contend for the same key.
- **replace(key, expected, newValue)** only replaces the mapping when the condition is met; it does not automatically "freeze" the object whose reference other threads have already obtained.
- **compute/computeIfPresent/merge** provide a way to atomically update the corresponding mapping per key when used according to contract.
- ConcurrentHashMap **does not support null keys or null values**. For remapping methods, returning **null** typically means removing/not creating the mapping per the specific API.
- Traversal operations are **weakly consistent**, may reflect some concurrent changes, and do not create an instantaneous consistent snapshot of the entire map.
- Operations like size, mappingCount, and statistics on a changing map are suitable for monitoring/estimation; do not use them as an exact admission-control protocol.

**Map-level atomicity** only tells you what happens to the **mapping**. It does not mean the value object is locked for its entire lifetime starting from the first get.

## 4. Safe Publication Does Not Mean Safety for Subsequent Mutations

Suppose one thread constructs a Counter and then **puts** it into a ConcurrentHashMap. Another thread later **gets** and sees that Counter. The memory consistency effects of the concurrent collection help publish the state completed before inserting the object into the map according to the API contract.

This is **completely different** from the constructing thread continuing to mutate Counter after put while the reading thread also mutates it at the same time:

~~~text
Thread A                          Thread B
--------                          --------
Counter c = new Counter();
c.count = 10;
map.put("x", c);  --------->
                                  Counter ref = map.get("x");
c.count++;   (A)                  ref.count++;  (B)
        |                              |
        +------ Same mutable object ---+
                        |
              No atomic increment.
~~~

Publication only solves **visibility of the published data** at a synchronization boundary; it does not create a permanent monitor around the object or a happens-before relationship between all subsequent modifications.

### Why Final Fields Are Not Enough

~~~java
final class Holder {
    final Counter counter = new Counter();
}
~~~

Even though the **counter** field is final, the **Counter** object can still be mutated. A **final reference** prevents reassigning that reference through Holder's field after construction; it does not make the fields inside Counter final or thread-safe.

Similarly, **Collections.unmodifiableList** only creates a view that prevents modification through the view. If a reference to the original mutable list still exists, another thread can still mutate it. **List.copyOf** creates a list that cannot be modified through its API, but if the list elements are mutable objects, this is still only **shallow immutability**.

## 5. Example 1: Reproducing a Lost Update Deterministically

A race condition does not always occur during test runs. To prove the bug **without relying on scheduler luck**, two threads both read count before being allowed to write. Because both read 0, both write 1.

File **UnsafeMutableValueDemo.java**:

~~~java
import java.util.concurrent.ConcurrentHashMap;
import java.util.concurrent.CountDownLatch;

public class UnsafeMutableValueDemo {
    static final class Counter {
        int value;
    }

    public static void main(String[] args) throws InterruptedException {
        ConcurrentHashMap<String, Counter> map =
                new ConcurrentHashMap<>();
        map.put("orders", new Counter());

        CountDownLatch bothRead = new CountDownLatch(2);
        CountDownLatch allowWrite = new CountDownLatch(1);

        Runnable increment = () -> {
            Counter counter = map.get("orders");
            int before = counter.value;

            bothRead.countDown();
            try {
                allowWrite.await();
                counter.value = before + 1;
            } catch (InterruptedException ex) {
                Thread.currentThread().interrupt();
            }
        };

        Thread first = new Thread(increment, "first");
        Thread second = new Thread(increment, "second");
        first.start();
        second.start();

        bothRead.await();
        allowWrite.countDown();
        first.join();
        second.join();

        System.out.println("expected = 2");
        System.out.println("actual = " + map.get("orders").value);
    }
}
~~~

~~~bash
javac -encoding UTF-8 UnsafeMutableValueDemo.java
java UnsafeMutableValueDemo
~~~

Stdout:

~~~text
expected = 2
actual = 1
~~~

**Analysis:**

1. The map publishes a Counter initially at 0.
2. Both threads obtain **the same Counter reference** via get().
3. Each thread reads 0 into its local variable before, then signals bothRead.
4. Main only opens allowWrite after **both threads have read**.
5. Both write **before + 1 = 1**; the final total remains 1 instead of 2.
6. **join()** lets main know both threads have finished before reading.
7. The latches create a controlled interleaving; without relying on Thread.sleep().

This is a simple model of a **lost update**. In a real application, simply writing **counter.value++** might make the bug reproduce less often, but the root cause is still a non-atomic read-modify-write.

**Do not fix this by calling map.put("orders", counter) after incrementing**: if two threads both mutate Counter before put, a thread-safe put operation cannot recover the lost increment.

## 6. Solution A: Store Atomic Values Instead of Plain Mutable Counters

When each key only needs an independent increment, placing **AtomicInteger** or **AtomicLong** as the value is a direct choice.

~~~java
// Illustration:
ConcurrentHashMap<String, AtomicInteger> counts =
        new ConcurrentHashMap<>();

counts.computeIfAbsent("orders", k -> new AtomicInteger())
      .incrementAndGet();
~~~

Two different guarantees work together:

- **computeIfAbsent** ensures a mapping exists for the key, avoiding a hand-written get-null-then-put.
- **incrementAndGet()** guarantees the increment on the **AtomicInteger value** is atomic.

Note that **computeIfAbsent does not make incrementAndGet part of the mapping operation**; after obtaining the AtomicInteger, the increment is performed on the value object. This remains correct as long as threads share **the same stable AtomicInteger for that key**.

### Example 2: AtomicInteger per Key

File **AtomicValueMapDemo.java**:

~~~java
import java.util.concurrent.ConcurrentHashMap;
import java.util.concurrent.atomic.AtomicInteger;

public class AtomicValueMapDemo {
    public static void main(String[] args) throws InterruptedException {
        ConcurrentHashMap<String, AtomicInteger> map =
                new ConcurrentHashMap<>();

        Runnable worker = () -> {
            for (int i = 0; i < 10_000; i++) {
                map.computeIfAbsent(
                        "orders", k -> new AtomicInteger()
                ).incrementAndGet();
            }
        };

        Thread first = new Thread(worker);
        Thread second = new Thread(worker);
        first.start();
        second.start();
        first.join();
        second.join();

        System.out.println("orders = " + map.get("orders").get());
    }
}
~~~

~~~bash
javac -encoding UTF-8 AtomicValueMapDemo.java
java AtomicValueMapDemo
~~~

Stdout:

~~~text
orders = 20000
~~~

Both threads increment a shared AtomicInteger; no increment suffers a lost update. However, this example assumes **no third thread removes or replaces the "orders" mapping while incrementing**.

### The Remove and Replace Trap

Imagine:

~~~text
T1: AtomicInteger old = map.get("orders");
T2: map.remove("orders");
T2: map.put("orders", new AtomicInteger());
T1: old.incrementAndGet();
~~~

T1 just incremented **old** after it had already been removed from the map. The current entry in the map does not reflect that increment. Each atomic operation is still correct **on the object it acts upon**, but business logic like "total of all orders regardless of reset" is wrong.

If **reset/removal concurrently with increment** is required, you must clearly define the semantics (epoch, generation, version, or updating the mapping via compute under a single protocol), not just swap the value for an atomic type.

## 7. Solution B: LongAdder for High-Contention Statistics

**LongAdder** is a common value type for counters incremented by many threads, especially under high contention. A typical pattern:

~~~java
// Illustration: ConcurrentHashMap<String, LongAdder> frequencies
frequencies.computeIfAbsent(
        "java", k -> new LongAdder()
).increment();
~~~

**LongAdder.sum()** returns the observed sum of internal counter cells. When **concurrent updates are occurring**, sum() **is not an atomic snapshot**; it may not reflect all in-flight updates at a single linearizable point in time.

### Example 3: LongAdder After Two Workers Complete

File **LongAdderMapDemo.java**:

~~~java
import java.util.concurrent.ConcurrentHashMap;
import java.util.concurrent.atomic.LongAdder;

public class LongAdderMapDemo {
    public static void main(String[] args) throws InterruptedException {
        ConcurrentHashMap<String, LongAdder> map =
                new ConcurrentHashMap<>();

        Runnable work = () -> {
            for (int i = 0; i < 5_000; i++) {
                map.computeIfAbsent(
                        "events", key -> new LongAdder()
                ).increment();
            }
        };

        Thread a = new Thread(work);
        Thread b = new Thread(work);
        a.start();
        b.start();
        a.join();
        b.join();

        System.out.println("events = " + map.get("events").sum());
    }
}
~~~

~~~bash
javac -encoding UTF-8 LongAdderMapDemo.java
java LongAdderMapDemo
~~~

Stdout:

~~~text
events = 10000
~~~

**sum() after join** is called when all illustrative updates have completed, so the result is deterministic. If main calls sum() while the two workers are updating, that number must not be used as an exact transaction quota.

| Tool | Advantages | Points to Note |
| --- | --- | --- |
| AtomicInteger | Increment, get, compareAndSet; good for single-variable decisions | Contention if many threads update the same point |
| AtomicLong | Same as AtomicInteger but long range | Still only protects a single value |
| LongAdder | Higher throughput in some high-contention stats workloads | sum() during updates is not an atomic snapshot |
| Plain int in value | Simple when owned by a single thread or covered by a lock | Not automatically safe with multiple writers |

**Same remove/replace trap as AtomicInteger:** if a thread holds an old LongAdder and increments it after the mapping is replaced, the update may no longer be reflected in the new value. **sumThenReset()** is also not a transaction that blocks all concurrent increments; to cleanly separate epochs and reset accurately, a dedicated protocol is needed.

## 8. Solution C: Immutable Values and Updating Mappings via Compute

For invariants spanning **multiple fields**, you can use an **immutable record** as the value and use **compute** or **computeIfPresent** to replace **the entire mapping** for that key.

For example, Inventory has two numbers: available and reserved. Invariant:

- available is non-negative;
- reserved is non-negative;
- **available + reserved** always equals the initial total;
- a reservation request changes both numbers **at the same time**.

If you put two separate AtomicIntegers inside the value and update them one by one, a reader might see an intermediate state. Instead, each update creates a **new record** and replaces **one mapping** using compute.

### Example 4: Immutable Record + computeIfPresent

File **ImmutableInventoryMapDemo.java**:

~~~java
import java.util.concurrent.ConcurrentHashMap;

public class ImmutableInventoryMapDemo {
    record Inventory(int available, int reserved) {}

    static void reserveOne(
            ConcurrentHashMap<String, Inventory> inventory) {
        inventory.computeIfPresent("book", (key, old) -> {
            if (old.available() == 0) {
                return old;
            }
            return new Inventory(
                    old.available() - 1,
                    old.reserved() + 1
            );
        });
    }

    public static void main(String[] args)
            throws InterruptedException {
        ConcurrentHashMap<String, Inventory> map =
                new ConcurrentHashMap<>();
        map.put("book", new Inventory(100, 0));

        Runnable buyer = () -> {
            for (int i = 0; i < 50; i++) {
                reserveOne(map);
            }
        };

        Thread[] threads = new Thread[4];
        for (int i = 0; i < threads.length; i++) {
            threads[i] = new Thread(buyer);
            threads[i].start();
        }
        for (Thread thread : threads) {
            thread.join();
        }

        Inventory end = map.get("book");
        System.out.println("available = " + end.available());
        System.out.println("reserved = " + end.reserved());
        System.out.println(
                "total = " + (end.available() + end.reserved())
        );
    }
}
~~~

~~~bash
javac -encoding UTF-8 ImmutableInventoryMapDemo.java
java ImmutableInventoryMapDemo
~~~

Stdout:

~~~text
available = 0
reserved = 100
total = 100
~~~

**Why is this correct?**

1. Inventory only contains two primitive ints and is an **immutable record** in this example.
2. Every reserveOne call for **the same key "book"** goes through computeIfPresent.
3. The remapping function uses a **consistent old snapshot of that mapping**, creating a new Inventory or keeping old if no tickets remain.
4. Replacing the mapping is performed under the atomic semantics of computeIfPresent for the corresponding key; threads cannot concurrently commit two updates based on the same old version and lose a turn.
5. The reader calls **map.get("book") once**, then reads both available/reserved from **the same snapshot**.
6. Four workers attempt 200 times total, but there are only 100 tickets; the final result remains consistent.

**Condition:** there must be no other path mutating state inside Inventory. In this example the record only has ints so no mutable reference is exposed. If a record contains an ArrayList that can be mutated externally, **record does not automatically create deep immutability**.

### Reading Twice Is Not a Snapshot

~~~java
// Incorrect illustration if data from the same version is needed:
int available = map.get("book").available();
int reserved = map.get("book").reserved();
~~~

Between the two gets, a writer could replace the mapping, causing the two fields to be read from **two different Inventory instances**. Instead:

~~~java
Inventory snapshot = map.get("book");
int available = snapshot.available();
int reserved = snapshot.reserved();
~~~

The snippet above assumes Inventory is already declared and the mapping is non-null. A single get retrieves **one snapshot object**; if its fields are immutable, subsequent getters reflect that same version.

## 9. compute Does Not Automatically Lock Every Value Object

A particularly dangerous misconception:

~~~java
// Illustration: if Counter is mutable,
map.compute("x", (key, counter) -> {
    counter.value++;
    return counter;
});
~~~

The remapping operation itself is coordinated per key. However, if thread T2 holds an old reference:

~~~java
Counter same = map.get("x");
same.value++; // T2 mutates outside compute.
~~~

Then T2 **is not forced to acquire the same internal lock** as T1's compute. The fact that compute manages the mapping does not force every caller holding Counter to synchronize on that object.

**Do not design around ConcurrentHashMap's internal lock as a public lock for the value.** For safe in-place mutation, all access paths to the value must participate in a synchronization protocol **defined and controlled by the application**.

### Remapping Functions Should Be Short and Controlled

The compute/merge APIs may need to lock/coordinate other updates on the same region of the map during remapping. Therefore:

- Do not perform network calls or long blocking I/O inside a remapping function.
- Do not perform non-retryable/non-idempotent side effects without considering the consequences of exceptions or retries.
- Do not use a remapping function to recursively update mappings of **the same map**; recursive updates are prohibited or have no progress guarantee and may throw IllegalStateException.
- Handle exceptions from the remapping function explicitly: if the function throws, the mapping may remain unchanged per the operation contract, but external side effects already performed are not automatically rolled back.
- **computeIfAbsent** is suitable for constructing a value when a key has no mapping yet; once a mutable value is created, every use of it still needs thread safety.

**Do not treat compute as a transaction covering a database, external API, or multiple different keys.**

## 10. Solution D: Protecting the Value with Its Own Lock

When a value has complex mutable logic, a valid design is for **the value to manage synchronized/lock itself** within its methods. All readers/writers must use **the same protocol**.

~~~java
// Illustration of a value object:
final class SafeCounter {
    private int value;

    synchronized void increment() {
        value++;
    }

    synchronized int get() {
        return value;
    }
}
~~~

Each synchronized method holds SafeCounter's monitor, preventing two threads from concurrently mutating the value field through those methods; unlock/lock establishes the corresponding happens-before relationship.

**Important conditions:**

- Mutable fields must be **private** or impossible to mutate outside protected methods.
- Readers must also use synchronized getters or an appropriate visibility mechanism, not read raw fields outside the lock.
- If an invariant spans multiple fields, put **the entire check–then–act in one critical section**, rather than synchronizing individual getters/setters and composing them in the caller.
- If multiple value objects participate in one business operation, a per-value lock may not protect invariants across multiple keys.
- If a mapping can be **removed/replaced**, a thread holding an old value reference can still call methods on the old object. The old object's locking protocol does not automatically synchronize with the new value.

### Example 5: Self-Protecting Value

File **SynchronizedValueMapDemo.java**:

~~~java
import java.util.concurrent.ConcurrentHashMap;

public class SynchronizedValueMapDemo {
    static final class SafeCounter {
        private int value;

        synchronized void increment() {
            value++;
        }

        synchronized int snapshot() {
            return value;
        }
    }

    public static void main(String[] args)
            throws InterruptedException {
        ConcurrentHashMap<String, SafeCounter> map =
                new ConcurrentHashMap<>();

        map.put("jobs", new SafeCounter());

        Runnable worker = () -> {
            for (int i = 0; i < 10_000; i++) {
                map.get("jobs").increment();
            }
        };

        Thread first = new Thread(worker);
        Thread second = new Thread(worker);
        first.start();
        second.start();
        first.join();
        second.join();

        System.out.println(
                "jobs = " + map.get("jobs").snapshot()
        );
    }
}
~~~

~~~bash
javac -encoding UTF-8 SynchronizedValueMapDemo.java
java SynchronizedValueMapDemo
~~~

Stdout:

~~~text
jobs = 20000
~~~

**Why is this correct?** Both threads increment a stable SafeCounter and share that object's monitor; main reads via synchronized snapshot() after join.

**Assumption limit:** the "jobs" mapping is not removed or replaced while workers are running. If a reset is needed, clearly define reset synchronized with increment, such as via per-key mapping computation or a shared epoch/state object with an appropriate lifetime.

### When to Use ReentrantLock Instead of synchronized?

If the value needs **tryLock**, timeouts, interruptible acquisition, Condition, or multiple critical sections with separate policies, **ReentrantLock** can be appropriate. The pattern is **lock.lock() → try → finally unlock()**. Do not use a different lock on each call; all relevant readers/writers must participate in the same lock held stably inside the value.

Do not claim ReentrantLock is always faster than synchronized. Performance depends on contention and workload; prefer the simplest approach that satisfies the contract.

## 11. Solution E: Copy-on-Write for Collections Inside Values

Suppose a map stores **List<String>** by key:

~~~java
ConcurrentHashMap<String, java.util.List<String>> map =
        new ConcurrentHashMap<>();

map.put("logs", new java.util.ArrayList<>());
map.get("logs").add("A"); // Unsafe with multiple concurrent writers.
~~~

ConcurrentHashMap only protects the **List reference** held by the map, not **ArrayList.add()**. Two threads can race on the size and internal data of ArrayList, causing lost elements or structural corruption.

One solution for **not-too-large, low-write-frequency** lists is copy-on-write at the mapping level:

~~~java
// Illustration of a mapping mutation:
map.compute("logs", (key, oldList) -> {
    java.util.List<String> next = new java.util.ArrayList<>(
            oldList == null ? java.util.List.of() : oldList
    );
    next.add("new");
    return java.util.List.copyOf(next);
});
~~~

- On each compute, the code creates a new list without mutating the old list.
- The published list is **unmodifiable** and String elements are immutable.
- Readers can hold the old list reference as a **snapshot** that writers will not alter.
- Writers on the same key update the mapping via compute, so elements are not lost due to separate get–modify–put operations.
- The **O(n) copy cost per append** can be very high for long lists or heavy writes; do not treat this as a general performance solution.

### Example 6: Appending to an Immutable List via compute

File **ImmutableListMapDemo.java**:

~~~java
import java.util.ArrayList;
import java.util.List;
import java.util.concurrent.ConcurrentHashMap;

public class ImmutableListMapDemo {
    public static void main(String[] args)
            throws InterruptedException {
        ConcurrentHashMap<String, List<String>> map =
                new ConcurrentHashMap<>();

        map.put("events", List.of());

        Runnable add = () -> {
            for (int i = 0; i < 100; i++) {
                map.compute("events", (key, old) -> {
                    List<String> next = new ArrayList<>(old);
                    next.add("e");
                    return List.copyOf(next);
                });
            }
        };

        Thread first = new Thread(add);
        Thread second = new Thread(add);
        first.start();
        second.start();
        first.join();
        second.join();

        List<String> result = map.get("events");
        System.out.println("size = " + result.size());
        System.out.println("immutable = " + rejectsMutation(result));
    }

    static boolean rejectsMutation(List<String> list) {
        try {
            list.add("unexpected");
            return false;
        } catch (UnsupportedOperationException ex) {
            return true;
        }
    }
}
~~~

~~~bash
javac -encoding UTF-8 ImmutableListMapDemo.java
java ImmutableListMapDemo
~~~

Stdout:

~~~text
size = 200
immutable = true
~~~

**Why is this correct?** Each compute operation for the same key reads the current list, copies it, adds one element, and publishes a new list. No writer mutates a published list. Two threads run 100 times each, resulting in 200 "e" strings.

**Note:** "immutable = true" only proves the list API rejects additions; since the elements are Strings, their contents are also immutable. If elements are mutable Person/Address objects, **List.copyOf does not deep-copy each element**. Readers could still observe unintended mutations on element objects.

### Should You Use CopyOnWriteArrayList?

**CopyOnWriteArrayList** is a separate thread-safe collection with a snapshot iterator and copy-on-mutation mechanism; it can be suitable when **reads vastly outnumber writes**. If the value is directly a CopyOnWriteArrayList, updates through its own API are synchronized per its contract. However, the copy cost on writes and the possibility of mapping removal/replacement still need to be considered.

Do not confuse a **copy-on-write list object** with **compute + replacing an immutable mapping**: the two techniques have different ownership and snapshot boundaries.

## 12. Concurrent Collections as Values Still Require Choosing the Right Operations

Some values are themselves concurrent collections:

- **ConcurrentLinkedQueue<E>** supports concurrent addition/removal of elements.
- A nested **ConcurrentHashMap<K2,V2>** inside a map has thread-safe operations at the nested map level.
- **ConcurrentHashMap.newKeySet()** provides a concurrent set.
- **CopyOnWriteArrayList<E>** is useful for read-heavy/write-rare workloads.
- **Collections.synchronizedList(list)** uses a monitor around its methods, but **when iterating** you must synchronize externally per the wrapper's contract.

Even with a concurrent collection as the value, **multi-step operation sequences** can still be wrong:

~~~java
// Illustration of a logic race with a concurrent collection:
if (!queue.isEmpty()) {
    Item first = queue.poll();
    // first can still be null if another thread takes it first.
}
~~~

This illustrative snippet assumes queue and Item exist. To retrieve an element if present, **poll() then check for null** is the appropriate single operation. If you need to wait for an element, use **BlockingQueue.take()** or poll(timeout), rather than spinning on isEmpty().

**Atomicity of individual methods does not imply atomicity of the entire workflow.**

## 13. putIfAbsent, computeIfAbsent, and Value Stability

An error-prone pattern:

~~~java
// Illustration of a race when multiple threads create Counter concurrently:
if (map.get(key) == null) {
    map.put(key, new Counter());
}
~~~

Two threads can both observe null and then both put two different Counter instances; the first thread might have already incremented its Counter, only for the mapping to be overwritten by the second thread. This is a **lost reference/update due to check–then–act**.

**putIfAbsent** lets you insert a mapping if absent and returns the existing value if already present. **computeIfAbsent** lets you create a value when missing under the map's atomic contract for that key.

~~~java
// Illustration:
AtomicInteger counter = map.computeIfAbsent(
        key, k -> new AtomicInteger()
);
counter.incrementAndGet();
~~~

If keys **are not concurrently removed/replaced**, all threads receive the same stable present value and perform atomic increments.

### Rules for Mapping Functions

- Do not perform long I/O or call external services inside a mapping function, as this can block related updates.
- Do not recursively modify mappings of the same ConcurrentHashMap inside a remapping callback; the JDK may throw IllegalStateException when it detects a recursive update that cannot complete.
- Do not place non-idempotent business side effects inside a callback without understanding the exact commit timing and failure paths.
- Do not return null when intending to store a null value; ConcurrentHashMap does not support null mappings, and null means remove/do not create the mapping depending on the API.
- When **computeIfAbsent returns a mutable value**, the job of protecting the value's fields **is not done**; you must still use atomics/locks/confinement.

## 14. The get → mutate → put Trap and replace

An anti-pattern:

~~~java
// Illustration:
Counter c = map.get("x");
c.count++;
map.put("x", c);
~~~

**put() does not make c.count++ atomic.** If two threads hold the same c, increments can be lost just like in Example 1. If two threads each create a copy of Counter and then put it, the later writer can overwrite the earlier writer's result.

### Using Conditional replace

You can read an **immutable value**, create a new version, and then call:

~~~java
// Illustration with an immutable value:
boolean swapped = map.replace(key, oldValue, newValue);
~~~

If false, re-read and recompute. However, **replace(key, oldValue, newValue)** relies on value equality comparison per the Map/ConcurrentHashMap contract, not pure reference CAS when equals differs from identity. If the value defines **equals on mutable fields**, the comparison can have issues when fields change concurrently.

In many cases, **compute** for the same key is clearer to express than an optimistic replace loop. If version/historical change detection is needed, consider a **version inside an immutable value** and an explicit protocol.

### equals/hashCode of Mutable Values

Key hashing matters because the map locates mappings by key. A **mutable key** whose equals/hashCode changes while inside the map can make lookups fail or behave incorrectly. For **values**, equals depending on mutable fields can make remove(key, expected) and replace(key, expected, replacement) unstable under concurrent updates.

Prefer **immutable keys with stable equals/hashCode**. For conditional replace/remove, also clearly understand the value's equality semantics and avoid unsynchronized mutations.

## 15. Multi-Key Invariants Are Not Automatically Atomic

ConcurrentHashMap supports updating **a single key's mapping** per its operation contract. However, business logic may need to update two keys together.

Example with accounts A and B:

~~~text
balance[A] = 100
balance[B] = 200
Total balance must always = 300.

Transfer 10 from A to B:
  A -> 90
  B -> 210
~~~

If using two independent compute calls:

~~~java
// Illustration: two separate steps, not a multi-key transaction.
balances.compute("A", (k, old) -> old - 10);
balances.compute("B", (k, old) -> old + 10);
~~~

A thread reading in between might see A=90 and B=200; the temporary sum is 290. Two independent compute calls do not form an **atomic multi-key transaction**.

Options:

- A **lock** covering both the updates and the reads that need a snapshot, using the same protocol across all relevant access paths.
- Packaging both A/B into **one immutable aggregate value** under **one key** and replacing it via compute/CAS if the problem allows.
- Designing an **owner thread** that serializes all state of a small subsystem.
- If the state lives in a **database** or across multiple JVMs, use transactions/conditional updates/optimistic versioning at the authoritative data store.

### An Atomic Snapshot of the Entire Map Is Not Free

A loop reading all of a changing ConcurrentHashMap may observe mappings from different points in time. Weakly consistent iterators **do not create a transactional snapshot of the entire map**. If a consistent view across multiple keys is required, a dedicated snapshot protocol is needed.

**Do not use map.size() and then compare against a quota** in a get → check → put sequence as if it were a transaction: multiple threads can interleave between steps.

## 16. Stable Value Identity, Reset, and Generation

A class of bugs that does not appear in increment-only examples is **reset**:

~~~text
Thread 1: obtains reference V1 from map.get(key)
Thread 2: map.replace(key, V2)
Thread 1: increments V1
Thread 3: reads map.get(key) -> V2

Thread 1's increment is no longer visible in the current mapping.
~~~

This case does not mean AtomicInteger is broken. It shows that **object-level atomicity** is different from **key-level atomicity across value generations**.

To design reset cleanly:

1. Define **the meaning of reset**: discard all old increments, start a new generation, or take a snapshot and continue counting?
2. Choose an immutable **version/generation** alongside the value so updating threads check the right generation.
3. Route **both increment and reset** through the same per-key mapping computation protocol if linearizable per-key semantics are required.
4. Or keep the value object fixed and perform reset/increment under the same lock if the contract allows.
5. Ensure readers understand **which version** the read number belongs to.
6. If there are side effects in a DB or across multiple JVMs, a Java map does not automatically create cross-process transactions.

**Do not promise a counter that reflects every historical increment** if the concurrent system allows removing/recreating the same key without a rule for increments holding old references.

## 17. Escaping Value Objects and Encapsulation

Suppose a Cache class holds a ConcurrentHashMap and returns the mutable value directly to callers:

~~~java
// Illustration of a class that should not return the reference directly:
public List<String> getEvents(String key) {
    return events.get(key); // Caller can add/remove.
}
~~~

If the caller receives an ArrayList and mutates it directly, every invariant Cache thought it controlled via compute is broken. Even if other Cache writers use compute properly, the caller can still mutate the list inside the current mapping.

Ways to protect the API:

- Return an **immutable snapshot** or read-only DTO with immutable elements.
- Only expose **semantic operations** such as addEvent(key, event), reserve(key), snapshot(key).
- Do not expose references to locks, mutable collections, or internal objects if callers can mutate them outside the protocol.
- If returning a live concurrent collection, document the contract clearly: which operations callers are allowed to perform, and what consistency level traversal and snapshots have.
- Design **immutable values** from the start to shrink the API surface that requires synchronization.

**Encapsulation is part of thread safety.** You cannot control all mutations if any caller can hold a mutable reference and write to it at will.

## 18. Bugs with Nested Object Graphs

Sometimes the value itself is an object with final fields that point to mutable objects:

~~~java
record UserStats(String user, List<Integer> values) {}
~~~

This record is not deeply immutable. If values points to a shared ArrayList and another caller adds to it, stats still changes observably even though the values field is final.

To get a true snapshot:

~~~java
record UserStats(String user, List<Integer> values) {
    UserStats {
        values = List.copyOf(values);
    }
}
~~~

Since Integer is immutable, copying the list provides an appropriate layer of immutability. If elements are mutable objects, a **deeper defensive copy or immutable element types** are needed as required.

Nested maps/lists are similar: an outer ConcurrentHashMap does not protect an inner HashMap, ArrayList, or mutable element that threads can share.

### How Far Does SynchronizedList Go?

**Collections.synchronizedList(list)** protects each method called on the wrapper. However, when iterating:

~~~java
// Illustration with an already created synchronizedList:
synchronized (synchronizedList) {
    for (String value : synchronizedList) {
        process(value);
    }
}
~~~

You must hold the corresponding monitor around iteration per the wrapper's contract. If a caller holds a reference to the backing list and mutates it outside the wrapper, the synchronization protocol is still broken.

## 19. Choosing a Solution by Invariant

| Need | Starting Choice | Limitations to Remember |
| --- | --- | --- |
| Independent per-key counter increments | ConcurrentHashMap<String, AtomicInteger> | Concurrent remove/replace needs separate semantics |
| High-contention additive statistics | ConcurrentHashMap<String, LongAdder> | sum() during updates is not an atomic snapshot |
| Multiple fields must change atomically within one key | Immutable record + compute/computeIfPresent | Does not cover multiple keys or external side effects |
| Mutable object with complex critical sections | Synchronized methods / ReentrantLock in value | All readers/writers must use the same protocol |
| Small read-heavy, write-rare list | Immutable list + compute / CopyOnWriteArrayList | Copy on every write, shallow immutability |
| Multi-threaded event queue | ConcurrentLinkedQueue / BlockingQueue | Choose based on whether blocking/backpressure is needed |
| Updating state of two keys together | Lock for aggregate or transaction at the data store | Per-key compute is not multi-key atomicity |
| Single owner handles all updates | Single-thread executor/actor-style ownership | Callers must not mutate state directly |
| Reading snapshot of a changing whole map | Explicit snapshot protocol, lock/version/aggregate | Weakly consistent iteration is not enough |

**The key to choosing:** identify the **unit of invariant** that needs protection. If the invariant lies completely inside an AtomicInteger, choose atomic. If it spans two fields of a record, use an immutable snapshot + compute or a lock. If it spans multiple keys or external systems, a higher-level protocol is needed.

## 20. Thread Confinement Is Still an Option

Instead of multiple threads directly mutating values in the map, you can use **a worker that owns each group of state**; other threads send commands to the worker and read results via Future or messages.

Advantages:

- No multiple concurrent writers on the same mutable object.
- Multi-step invariants can be expressed sequentially.
- Reduces the need for fine-grained locking on every field.

Disadvantages:

- A single worker can become a bottleneck under high load.
- Queues and shutdown must be controlled to avoid losing requests.
- Callers must not bypass the owner by calling value.setXXX directly.
- If multiple processes/JVMs access a DB concurrently, an owner in one JVM is not enough.

**ConcurrentHashMap can still be used as an owner lookup registry**, while the correctness of mutable state is determined by the **ownership protocol**.

## 21. Performance: Thread-Safe Does Not Always Mean Fast

There are multiple correct approaches with different trade-offs:

- **AtomicInteger** can suffer contention when all threads increment a single hot key.
- **LongAdder** often improves throughput for hot-key statistics, at the cost of sum() not being linearizable during updates.
- **compute + immutable record** makes consistent snapshots easy, but allocates new objects and can serialize multiple updates to the same key.
- **synchronized value** is simple for clear critical sections, but holding the lock for long causes contention.
- **Copy-on-write list** is convenient for read-heavy, write-rare workloads; appending to a large list can require an O(n) copy.
- **Nested concurrent collections** have their own overhead and do not automatically protect compound operations.

When benchmarking:

1. Define invariants and verify correctness first.
2. Measure on both **hot keys** and **many distributed keys**.
3. Separate CPU-bound operations from blocking I/O.
4. Warm up the JVM and run multiple iterations; avoid single-shot benchmarks.
5. Measure throughput, p95/p99 latency, contention, allocations/GC, and memory.
6. Consider **JMH** for important microbenchmarks to avoid dead-code elimination.
7. Evaluate complexity and code reviewability, not just peak speed.

**A fast solution that reads inconsistent snapshots is still invalid.**

## 22. Testing Concurrency Properly

**Test logic, not probability.**

### Use CountDownLatch to Orchestrate Lost Updates

Example 1 ensures both threads have read the same old value before being allowed to write. This is a clear proof that map-level thread safety does not solve lost updates.

### Use join/Future to Verify Final Results

Examples 2–6 only print after all writers have finished. Thus stdout reflects a known terminal state, avoiding guesswork about thread scheduler timing.

### Stress Testing and Model Checking

Stress tests with high thread counts, many keys, and many runs can help uncover bugs, but **they do not prove code is always correct**. You must combine them with reasoning about:

- All **read/write** paths to the value.
- **Happens-before** and visibility of updates.
- Atomicity of **the entire business operation**.
- Concurrent **remove/replace/reset** cases.
- Deep immutability and API value reference escaping.
- Exception/retry/cancellation rules and idempotency of side effects.

### Additional Tests Worth Having

- Two threads concurrently calling compute for the same key.
- One thread reading a snapshot while another thread updates.
- One thread removing/replacing while another holds an old reference.
- Multiple threads concurrently calling computeIfAbsent and incrementing a counter.
- Iterating the map while writers change mappings: assert only the weakly consistent contract, not a stable snapshot.
- Nested lists/maps and mutable elements.
- Multi-key compound invariants.
- ExecutionException/InterruptedException and cleanup on failure paths if the application has async tasks.

## 23. Anti-Pattern Summary

| Anti-pattern | Why it is wrong | How to fix |
| --- | --- | --- |
| map.get(key).count++ | V's field is not atomic | AtomicInteger or synchronized value |
| map.get(key).list.add(x) with ArrayList | ArrayList is not thread-safe | Concurrent collection or immutable copy-on-write |
| get → mutate → put | Mutation occurs outside map atomic operation | compute with immutable replacement or appropriate lock |
| get null → put(new Counter()) | Two threads can create/overwrite and lose references | computeIfAbsent/putIfAbsent |
| compute then mutate same value outside compute | Internal map synchronization does not protect external references | Encapsulate mutation, immutable value, same lock |
| Assuming a record containing ArrayList is immutable | Record is only shallowly immutable | Defensive copy and immutable elements |
| Assuming LongAdder map value resets safely automatically | Old reference may be incremented after replace | Generation/epoch/reset protocol |
| size() then put to enforce a quota | Check–then–act sequence is not atomic | Dedicated admission control/permits |
| Two computes on two keys as a transaction | Multi-key intermediate state is visible | Lock/aggregate/DB transaction |
| Treating CHM iterator as a transactional snapshot | Weakly consistent | Appropriate snapshot protocol |
| Returning mutable value directly to caller | Caller can bypass all invariants | Return snapshot/operations instead of live mutable |
| Value equals depending on concurrently mutated fields | replace/remove conditions are hard to uphold | Immutable value, version, and stable equality semantics |
| Thinking volatile int++ is safe | Visibility does not make read-modify-write atomic | Atomic increment or lock |
| Synchronized getter with unlocked writer | Inconsistent reader/writer protocol | All access paths must use the same lock |
| Switching everything to concurrent collections | Compound invariants can still break | Choose the right atomic unit for the business logic |

## 24. Code Review Checklist

**State and ownership:**

- [ ] Is the value truly immutable or just a final reference?
- [ ] Are any mutable nested objects exposed externally?
- [ ] Can callers hold a live value reference and mutate it directly?
- [ ] Does the key have immutable, stable equals/hashCode?
- [ ] Can the mapping be removed/replaced/reset while the value is in use?

**Synchronization:**

- [ ] Does every increment/check–then–act have the right atomic unit?
- [ ] Are there multi-field operation sequences that need the same critical section?
- [ ] If using synchronized/ReentrantLock, do all readers/writers use the same lock object?
- [ ] If using compute, is the callback short, without recursive updates or long-blocking I/O?
- [ ] If using LongAdder, do callers understand sum() during updates is not an atomic snapshot?
- [ ] If using immutable snapshots, do readers get one reference for fields of the same version?
- [ ] If using a thread-safe collection inside V, are there compound operations that still need locking?

**Business logic and operations:**

- [ ] Are there invariants spanning multiple keys or multiple JVMs/DBs?
- [ ] Is there a generation/version policy for resets?
- [ ] Is the current mapping distinguished from old references still held by others?
- [ ] Are there stress tests, deterministic concurrency tests, and exception handling?
- [ ] Have throughput and contention been measured under realistic hot-key workloads?
- [ ] Does the API avoid promising what CHM does not provide, such as whole-map snapshots or multi-key transactions?

## 25. Self-Check Questions

**1. Does ConcurrentHashMap<String, Counter> make Counter.count++ safe?**  
No. The map protects the mapping; incrementing a mutable int field requires its own mechanism.

**2. Is it correct for two threads to fetch the same value and call AtomicInteger.incrementAndGet()?**  
Yes, if it is the same AtomicInteger and only an atomic increment on that object is needed. However, removing/replacing the mapping can cause increments on an old reference to no longer be reflected in the current map.

**3. Does compute(key, ...) guarantee that all mutations on the value object outside the callback are also locked?**  
No. It coordinates the mapping per key during the compute call; it does not force threads holding a value reference to use the same synchronization.

**4. Is LongAdder.sum() an atomic snapshot while multiple threads are incrementing?**  
No. Reading the sum after writers have finished is appropriate for obtaining the final result.

**5. When two fields available and reserved must change together, should two separate AtomicIntegers be used?**  
If readers must observe a consistent invariant, do not update them separately without an additional protocol. Use an immutable record + compute or a lock covering both.

**6. Does List.copyOf(list) make element objects inside the list immutable?**  
No. It does not deep-copy mutable elements; immutable elements or appropriate defensive copies are required.

**7. Why can calling map.get(key) twice to read two fields be wrong?**  
The mapping may be replaced between the two reads, mixing two versions. Fetch an immutable snapshot once.

**8. Does using computeIfAbsent and then AtomicInteger's get() solve concurrent resets?**  
Not automatically. A thread can hold an old value and update it after the mapping has been replaced.

**9. Do two computes for two keys form a multi-key transaction?**  
No. A reader can observe an intermediate state; a higher-level protocol is needed.

**10. Does SynchronizedList make iteration completely thread-safe automatically?**  
Individual methods are synchronized by the wrapper, but iteration requires external synchronization per contract to prevent interleaved updates.

**11. Is reading the entire ConcurrentHashMap with forEach a point-in-time snapshot?**  
No. Traversal is weakly consistent and may observe partial concurrent updates.

**12. When should immutable values be preferred?**  
When you want readers to obtain easily verifiable consistent snapshots and updates can be expressed as atomic mapping replacements via compute/merge.

**13. Why doesn't calling put after mutating make the mutation atomic?**  
Because the mutation already occurred on the object before put and could race with another thread; put only updates the mapping.

**14. If a key has a large hot counter, should LongAdder always be used?**  
No. If you need CAS, quota checks, linearizable get-and-increment, or exact resets, AtomicLong or another protocol may be more appropriate.

**15. What is more important than picking a concurrent class?**  
Clearly defining invariants, the atomic unit, ownership of mutable state, memory consistency, and all read/write paths.

## 26. Summary

**ConcurrentHashMap only solves thread safety at the map/mapping level**; it does not automatically make a Counter, ArrayList, nested HashMap, or object graph placed in the value thread-safe. A map.get call may be safe, but code that continues to **mutate the returned object** still needs its own contract.

Common choices:

1. **AtomicInteger/AtomicLong** for a single value needing atomic read-modify-write.
2. **LongAdder** for high-update statistics, accepting snapshot limitations.
3. **Immutable record + compute/merge** to atomically update an invariant within one key.
4. **synchronized/ReentrantLock** to protect a mutable value under the same read/write protocol.
5. **Immutable copy-on-write or concurrent collections** for nested collections, matching the load pattern.
6. **Higher-level owner/transaction** when invariants span multiple keys or multiple processes.

Always check for **get → mutate → put**, escaping object references, remove/replace/reset, shallow immutability, weakly consistent iteration, and external side effects. **The safety of the outer collection cannot substitute for proper design of mutable state inside the value.**
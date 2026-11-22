# Why are ArrayList and HashMap unsafe when accessed concurrently?

`ArrayList` and `HashMap` are among the most familiar collections in Java. They are suitable for managing data within a single thread, or when **the application itself protects all shared accesses with a proper synchronization protocol**. However, if multiple threads concurrently read/write an instance without coordination, they **do not provide thread safety**: updates may be lost, inconsistent data may be observed, exceptions may occur, incorrect results may be returned, or assumptions about the data lifecycle may be broken.

This does not mean "as soon as two threads use `ArrayList`/`HashMap`, it immediately fails". If a collection is **fully initialized, safely published, and then only read** without any thread mutating it, multiple readers can use it. The risk mainly arises when there is **mutable shared state** and the synchronization protocol fails to satisfy all three conditions: **atomicity, visibility, and ordering**.

This article explains the specific internal structures prone to races, why `volatile` cannot fix them, the difference between "a thread-safe method" and "an atomic workflow", how to write tests with deterministic interleaving, and how to choose among `Collections.synchronizedList/Map`, `CopyOnWriteArrayList`, `ConcurrentHashMap`, immutable collections, or ownership.

Scope: **general Java concurrency**, Java 17+, independent of Spring or any framework.

## 1. What does thread-safe mean in the context of collections?

A thread-safe collection must have a **clear contract** for concurrent operations: which operations are allowed to be called, the atomicity of each operation, which memory-consistency mechanism readers use to observe values, how iterators see data, and whether compound operations require external locking.

Some criteria to check:

| Criterion | Question |
| --- | --- |
| **Atomicity** | Do two threads calling `add`/`put` simultaneously lose an operation or overwrite an update? |
| **Visibility** | Can a reading thread observe state published by another thread according to the Java Memory Model? |
| **Ordering** | Is there a happens-before relationship between an update and a read that depends on that update? |
| **Structural invariants** | Do `size`, backing array, buckets, links, and resize state remain consistent when multiple writers operate? |
| **Compound atomicity** | Is `contains` followed by `add`, or `get` followed by `put`, an atomic decision? |
| **Iteration semantics** | Is the iterator fail-fast, snapshot, weakly consistent, or protected by the same lock? |
| **Lifecycle/ownership** | Who is allowed to mutate, when is the collection published, and when does its usage end? |

**Thread-safe does not mean every sequence of method calls is atomic.** For example, a map whose individual `get` and `put` methods are thread-safe can still suffer from business logic bugs when code does `get`, computes a new value, and then `put`. The entire read–modify–write sequence must be synchronized or replaced with an appropriate atomic operation.

## 2. Why is `ArrayList`'s internal structure prone to races?

Conceptually, `ArrayList<E>` stores data in a **backing array** and maintains the count of current elements. When calling `add(E)`, it must coordinate at least the following steps:

1. Determine the next position from `size`.
2. If necessary, grow or replace the backing array.
3. Write the element into the array at the new position.
4. Update `size` and structural modification metadata used by iterators.

Those steps are **not protected by mutual exclusion** in a standard `ArrayList`. If threads A and B call `add` at the same time:

```text
Initial: size = 0

Thread A                       Thread B
--------------------------     --------------------------
read size = 0                  read size = 0
choose index 0                 choose index 0
write element A at index 0     write element B at index 0
update size                    update size

The result may not contain both A and B.
```

This is **an illustrative interleaving**, not a single schedule or exact bytecode-level pseudocode for every JDK version. Symptoms can include **lost elements, wrong size, unexpected null slots, exceptions**, or hard-to-reproduce results. When growing capacity concurrently, writers can also contend over replacing the backing array.

Some important points:

- `new ArrayList<>(1000)` only sets the **initial capacity**; it does not make `add` calls thread-safe.
- `Collections.synchronizedList(...)` wraps methods with synchronization, but **still requires external locking** for many compound operations or when iterating with an iterator.
- `ArrayList.set(index, value)` does not make all forms of concurrent access safe; you must analyze index ownership, absence of structural mutation, publication, and visibility. Do not take the case where each thread writes to its own slot as proof that `ArrayList` in general is thread-safe.
- A `volatile List<T>` reference variable only guarantees semantics for the **reference**, not automatic synchronization of the internal fields of `ArrayList`.

### Can `size()` be a source of truth during concurrent writes?

It should not be. If threads mutate an `ArrayList` without happens-before or mutual exclusion, reading `size()` in another thread is not guaranteed to reflect a valid snapshot. For example, "seeing `size=5`" does not prove that the five corresponding elements have been safely published and read under an unsynchronized protocol.

## 3. Why is `HashMap`'s internal structure unsafe?

`HashMap<K,V>` manages a table of buckets. Depending on hashes and size, entries in a bucket may be in a linked structure or a tree; when the number of entries exceeds a threshold, the map may **resize** and redistribute entries into a new table. `put` must coordinate finding the key, updating or adding a node, modifying bucket links, and updating statistics such as `size`.

When multiple threads concurrently call `put`, `remove`, `compute`, or mutate state without synchronization:

- Two insertions with different keys can modify the structure concurrently or trigger a resize together.
- A `put` can overwrite a value computed from another thread's stale snapshot.
- A reader may fail to observe updates properly due to a missing happens-before relationship.
- Iteration over a structure being modified can throw `ConcurrentModificationException` or observe inconsistent data; the exception is not guaranteed to be thrown.
- Internal buckets/links/size can be updated in interleavings outside the map's safety contract.

**Do not use `HashMap` for concurrent structural mutations just because "every key is different".** Mutations on different keys can still touch the table, resize, `size`, and bucket metadata together. Even when the table has enough capacity, the Java API still makes no safety guarantee for multiple unsynchronized writers.

### Note on "HashMap infinite loop" stories

Some well-known examples in older documentation describe situations where linked structures became tangled when multiple threads resized a `HashMap` concurrently in older JDK versions. This is a historical example, **and one should not claim that every JDK 17 execution will necessarily enter an infinite loop**. A more reliable conclusion is: `HashMap` **has no contract for concurrent writes**, so the outcome is not guaranteed. Rely on the specification and proper synchronization rather than expecting a specific failure mode.

## 4. Two categories of bugs to keep separate

### 4.1. Data race / unsafe structural mutation

For example, two threads concurrently calling `ArrayList.add` on an unprotected list, or one thread calling `HashMap.put` while another thread reads/iterates the map. Methods not designed for concurrent access may read/write the same mutable fields without synchronization.

The consequence is not just wrong "business logic"; both the collection's internal data and update visibility can become inconsistent under the Java Memory Model.

### 4.2. Non-atomic check–then–act / read–modify–write

Even if each individual method is **locked separately**, the following workflow is still wrong if the intent is to add a value only once:

```java
if (!list.contains("job-A")) {
    list.add("job-A");
}
```

This snippet is not standalone; `list` is a shared list. Two threads can both see that `"job-A"` is absent, and then both add it. If you use `Collections.synchronizedList` without wrapping the entire `contains + add` in **one shared lock**, the logic bug still occurs.

With a map:

```java
Integer old = map.get("hits");
map.put("hits", old == null ? 1 : old + 1);
```

This is also a snippet. Two threads can both see `old=0`, and then both put `1`: a **lost update**. Using `Collections.synchronizedMap` and calling each method individually still does not make the whole sequence atomic.

**Distinguish two levels of bugs:** "The collection protects its own internal state" and "The entire business operation preserves its invariant" are two different questions. `ConcurrentHashMap` solves many concurrency needs at the collection level, but a complex workflow spanning multiple keys/resources still requires designing overall atomicity.

## 5. Java 17: a coordinated test to expose check–then–act bugs

Many demos try "running two threads really fast" and hope for a lost update. That approach is easily flaky. The following example deliberately makes two threads **read the old snapshot first**, and then **write one after another** using latches. This produces a **predictable** wrong result without trying to trigger internal corruption via concurrent structural writes.

Create the file **`CheckThenActTrapDemo.java`**:

```java
import java.util.ArrayList;
import java.util.HashMap;
import java.util.List;
import java.util.Map;
import java.util.concurrent.Callable;
import java.util.concurrent.CountDownLatch;
import java.util.concurrent.ExecutorService;
import java.util.concurrent.Executors;
import java.util.concurrent.Future;
import java.util.concurrent.TimeUnit;

public class CheckThenActTrapDemo {
    public static void main(String[] args) throws Exception {
        List<String> names = new ArrayList<>();
        Map<String, Integer> counts = new HashMap<>();

        CountDownLatch bothRead = new CountDownLatch(2);
        CountDownLatch firstWritten = new CountDownLatch(1);
        ExecutorService pool = Executors.newFixedThreadPool(2);

        Callable<Void> first = () -> {
            boolean absent = !names.contains("A");
            int old = counts.getOrDefault("hits", 0);
            bothRead.countDown();
            if (!bothRead.await(5, TimeUnit.SECONDS)) {
                throw new IllegalStateException("Read rendezvous failed");
            }

            try {
                if (absent) names.add("A");
                counts.put("hits", old + 1);
            } finally {
                firstWritten.countDown();
            }
            return null;
        };

        Callable<Void> second = () -> {
            boolean absent = !names.contains("A");
            int old = counts.getOrDefault("hits", 0);
            bothRead.countDown();
            if (!bothRead.await(5, TimeUnit.SECONDS)) {
                throw new IllegalStateException("Read rendezvous failed");
            }

            if (!firstWritten.await(5, TimeUnit.SECONDS)) {
                throw new IllegalStateException("First write missing");
            }
            if (absent) names.add("A");
            counts.put("hits", old + 1);
            return null;
        };

        try {
            Future<Void> a = pool.submit(first);
            Future<Void> b = pool.submit(second);
            a.get(5, TimeUnit.SECONDS);
            b.get(5, TimeUnit.SECONDS);

            System.out.println("listCount=" + names.size());
            System.out.println("mapCount=" + counts.get("hits"));
            System.out.println("expectedMapCount=2");
        } finally {
            pool.shutdownNow();
        }
    }
}
```

Compile/run with JDK 17+:

```bash
javac CheckThenActTrapDemo.java
java CheckThenActTrapDemo
```

Stdout when both workers complete within the deadline:

```text
listCount=2
mapCount=1
expectedMapCount=2
```

**How to explain the output:**

1. `bothRead` forces A and B to **both read** the empty list and the map without key `hits` before either writer proceeds.
2. The first worker adds `"A"` and writes `hits=1`.
3. `firstWritten` ensures the second worker **writes only after** the first worker has finished its writes.
4. B still uses the **stale snapshot**: `absent=true`, `old=0`. It adds another `"A"` and overwrites `hits=1`.
5. Two business actions occurred, yet the map holds `1` and the list has two duplicate elements. The latch protocol makes the result deterministic without needing `Thread.sleep`.

**Precise analysis of the experiment's scope:** The two threads perform **reads before writes**, and the **writes are serialized** by the latch. Therefore, this example intentionally demonstrates **non-atomic compound check–then–act**, **not** proof that the internal structure of `ArrayList` or `HashMap` was corrupted by two concurrent writers. Testing unsafe concurrent structural writes requires separate stress/lincheck/JMM reasoning; do not use a single "lucky correct" run to validate non-thread-safe code.

## 6. Fix 1: use a single lock for the entire workflow

If a collection is frequently shared across multiple threads, you can use an **intrinsic monitor** to protect all related reads/writes.

```java
private final Object lock = new Object();
private final List<String> names = new ArrayList<>();

boolean addIfAbsent(String name) {
    synchronized (lock) {
        if (names.contains(name)) {
            return false;
        }
        names.add(name);
        return true;
    }
}
```

This is a snippet inside a class; `List`/`ArrayList` imports are required. When all code that reads/writes the list uses **the same lock**, two threads cannot concurrently decide that `name` does not exist yet. The `contains + add` operation becomes a single critical section.

A map counter is similar:

```java
private final Object lock = new Object();
private final Map<String, Integer> counts = new HashMap<>();

int increment(String key) {
    synchronized (lock) {
        int next = counts.getOrDefault(key, 0) + 1;
        counts.put(key, next);
        return next;
    }
}
```

This is a snippet in another class or an appropriate part of a class; do not redeclare fields with the same names in one class. **All paths** reading/writing state that serves the invariant must follow the lock protocol: if one thread sneaks in an unlocked `counts.put`, the guarantee is broken.

### Lock granularity

A single shared lock is simple and easy to prove correct, but it can cause contention if many threads update **independent keys**. In that case, `ConcurrentHashMap` is often a better choice. However, if an invariant spans **two or more collections** (for example, recording an order and deducting quota), a lock or transaction with sufficient scope may still be necessary.

**Do not hold a lock while doing long I/O, calling untrusted callbacks, or calling `Future.get`** without good reason; doing so can cause deadlocks and tail latency. Separate computation/side effects so that the invariant remains intact.

## 7. Fix 2: `Collections.synchronizedList` and `synchronizedMap`

The JDK provides wrappers:

```java
List<String> names =
        java.util.Collections.synchronizedList(
                new java.util.ArrayList<>());

Map<String, Integer> counts =
        java.util.Collections.synchronizedMap(
                new java.util.HashMap<>());
```

Collection methods on the wrapper are synchronized according to its contract. For individual operations like `add/get/put` through the wrapper, this is a simple way to protect internal state.

**However:** synchronizing individual calls **does not automatically combine** a pair of methods into a transaction:

```java
if (!names.contains("A")) {
    names.add("A");
}
```

Even though `names` here is a synchronized wrapper, two threads can still interleave between `contains` and `add`. To make it atomic:

```java
synchronized (names) {
    if (!names.contains("A")) {
        names.add("A");
    }
}
```

With a map:

```java
synchronized (counts) {
    int old = counts.getOrDefault("hits", 0);
    counts.put("hits", old + 1);
}
```

**Condition:** every caller must use **the wrapper itself** and the corresponding lock. If a reference to the original `new ArrayList<>()`/`new HashMap<>()` is retained and mutated through that reference, the wrapper cannot protect those bypassing paths.

### Iteration over a synchronized wrapper still requires an external lock

According to the JDK documentation for synchronized collection wrappers, when traversing with an `Iterator`/`Spliterator` or stream, the caller must manually synchronize on the wrapper throughout the traversal:

```java
synchronized (names) {
    for (String name : names) {
        consume(name);
    }
}
```

This is a snippet where `consume` is an application method. Similarly:

```java
synchronized (counts) {
    for (Map.Entry<String, Integer> e
            : counts.entrySet()) {
        inspect(e);
    }
}
```

This is a snippet; `inspect` is defined by the application. Calling only `names.iterator()` inside `synchronized` and then calling `next()` outside is **not enough** if writers can mutate between steps.

If the callback during iteration is expensive or blocking, you can **copy a snapshot under the lock** and then iterate outside the lock. A snapshot only captures references/values at one point in time; if elements are mutable and modified later, immutable values or ownership are also needed.

## 8. Fix 3: `ConcurrentHashMap` and atomic map operations

`ConcurrentHashMap<K,V>` is designed for concurrent access. It allows multiple reads and updates according to its contract, without using a single global monitor for every operation as a synchronized wrapper does in many cases. It provides operations such as:

- `putIfAbsent(key, value)`: inserts only if the key is not already present, as an appropriate atomic update.
- `computeIfAbsent(key, mappingFunction)`: computes the value if the key is not yet mapped and updates according to an atomic contract.
- `compute(key, remappingFunction)`: recomputes the value based on the current mapping for that key.
- `merge(key, value, remappingFunction)`: atomically combines a new value with the current value on the mapping being processed.
- `replace(key, oldValue, newValue)`: CAS-like conditional replacement for a mapping.
- `remove(key, value)`: removes only if still mapped to the expected value.

Instead of:

```java
Integer old = concurrentMap.get("hits");
concurrentMap.put("hits", old == null ? 1 : old + 1);
```

which still has a **lost update logic bug** because two separate atomic operations do not form a transaction, use:

```java
concurrentMap.merge("hits", 1, Integer::sum);
```

This is a snippet; `concurrentMap` is a `ConcurrentHashMap<String,Integer>`. `merge` protects the operation updating the mapping for that key. For the same key, two valid `merge("hits",1,Integer::sum)` calls will increment the total twice instead of overwriting each other's snapshot.

**Do not conclude that `ConcurrentHashMap` solves every multi-key invariant.** For example, checking whether `mapA` still has quota and then writing to `mapB` in another map does not become atomic just because both maps are concurrent maps. A lock, transaction, state machine, or ownership model is needed for the entire workflow.

### Some important limitations

- `ConcurrentHashMap` does not allow **null keys/values**, unlike `HashMap`. Code that uses `map.get(key)==null` to distinguish absent from "mapped to null" must be adjusted.
- Iterators/views are generally **weakly consistent**: they may observe some updates occurring during traversal; they are not a frozen snapshot of the entire map.
- The mapping/remapping function of `compute/merge` should be **short, pure with respect to business side effects, and non-blocking**. In some situations, other updates may be affected while the computation runs; do not call back into the same map recursively in ways that risk being prohibited or causing deadlock.
- A method with the `computeIfAbsent` suffix is not the right place to send an email or charge a payment while assuming system-wide exactly-once semantics; process/network failures and data lifecycles still need to be designed for.
- Compound operations across multiple entries still do not have an atomic snapshot by default.

### `putIfAbsent` vs. `containsKey` followed by `put`

```java
String old = concurrentMap.putIfAbsent("id-7", "reserved");
if (old == null) {
    // This thread placed a new mapping when the key was previously absent.
}
```

This is a snippet; assume `concurrentMap` has type `ConcurrentHashMap<String,String>`. Compared to `containsKey + put`, this method has proper atomicity for **a single key**. However, when "reserving" also requires writing to a DB, deducting quota, processing payment, and sending an email, the map accepting the new key does **not** prove the entire business operation has committed.

## 9. Fix 4: `CopyOnWriteArrayList` for read-mostly workloads

`CopyOnWriteArrayList<E>` is suited for many readers and a low frequency of additions/removals. Each structural write creates a new backing array under a copy-on-write design; readers and iterators can observe the **snapshot** that existed at the time the iterator was created.

Advantages:
- Traversal does not throw `ConcurrentModificationException` like `ArrayList`'s fail-fast iterator.
- Iteration does not require holding a global monitor around the entire read loop.
- Useful for small lists of listeners/configurations that rarely change.

Disadvantages:
- `add/remove` incurs array copy and allocation overhead, making it unsuitable for write-heavy workloads or very large lists.
- The snapshot iterator **does not see** elements added after the iterator was created.
- Mutable elements inside the list **do not automatically become immutable/thread-safe**.
- A check–then–act using two methods is still not automatically atomic. `CopyOnWriteArrayList.addIfAbsent` is a dedicated operation with more appropriate semantics if the goal is to add a value at most once.

Example:

```java
CopyOnWriteArrayList<String> listeners =
        new CopyOnWriteArrayList<>();

listeners.addIfAbsent("listener-A");
listeners.addIfAbsent("listener-A");
// Only one "listener-A" element after two sequential calls.
```

This is a snippet; `java.util.concurrent.CopyOnWriteArrayList` must be imported. If uniqueness must be guaranteed by a **business key** on objects with different semantics, you must analyze `equals` and choose an appropriate structure/operation.

## 10. Java 17: concurrent solution and snapshot iterator

The following program runs two producers, each updating `ConcurrentHashMap.merge` and `Collections.synchronizedList.add` 500 times. `main` reads the results only after `Future.get` confirms both have finished. It also illustrates `CopyOnWriteArrayList`'s snapshot iterator.

Create **`ConcurrentCollectionsFixDemo.java`**:

```java
import java.util.ArrayList;
import java.util.Collections;
import java.util.Iterator;
import java.util.List;
import java.util.concurrent.Callable;
import java.util.concurrent.ConcurrentHashMap;
import java.util.concurrent.CopyOnWriteArrayList;
import java.util.concurrent.CountDownLatch;
import java.util.concurrent.ExecutorService;
import java.util.concurrent.Executors;
import java.util.concurrent.Future;
import java.util.concurrent.TimeUnit;

public class ConcurrentCollectionsFixDemo {
    public static void main(String[] args) throws Exception {
        ConcurrentHashMap<String, Integer> counts =
                new ConcurrentHashMap<>();
        List<Integer> values =
                Collections.synchronizedList(new ArrayList<>());

        CountDownLatch start = new CountDownLatch(1);
        ExecutorService pool = Executors.newFixedThreadPool(2);

        Callable<Void> worker = () -> {
            if (!start.await(5, TimeUnit.SECONDS)) {
                throw new IllegalStateException("Start gate failed");
            }
            for (int i = 0; i < 500; i++) {
                counts.merge("hits", 1, Integer::sum);
                values.add(i);
            }
            return null;
        };

        try {
            Future<Void> a = pool.submit(worker);
            Future<Void> b = pool.submit(worker);
            start.countDown();
            a.get(5, TimeUnit.SECONDS);
            b.get(5, TimeUnit.SECONDS);

            long sum = 0;
            synchronized (values) {
                for (int value : values) {
                    sum += value;
                }
            }

            CopyOnWriteArrayList<String> copyOnWrite =
                    new CopyOnWriteArrayList<>();
            copyOnWrite.add("before");
            Iterator<String> snapshot = copyOnWrite.iterator();
            copyOnWrite.add("after");

            System.out.println("mapCount=" + counts.get("hits"));
            System.out.println("listSize=" + values.size());
            System.out.println("listSum=" + sum);
            System.out.println("snapshotFirst=" + snapshot.next());
            System.out.println("snapshotHasNext=" + snapshot.hasNext());
            System.out.println("currentSize=" + copyOnWrite.size());
        } finally {
            pool.shutdownNow();
        }
    }
}
```

Run on JDK 17+:

```bash
javac ConcurrentCollectionsFixDemo.java
java ConcurrentCollectionsFixDemo
```

Typical stdout:

```text
mapCount=1000
listSize=1000
listSum=249500
snapshotFirst=before
snapshotHasNext=false
currentSize=2
```

**Explanation:**

- `ConcurrentHashMap.merge` ensures the two threads do not lose increments on the `hits` key.
- The `synchronizedList` wrapper protects each `add`, so the final list has all 1,000 elements.
- Iteration is wrapped in `synchronized (values)`; once both workers have completed, the sum of two sequences of `0..499` is `2 × (499 × 500 / 2) = 249500`.
- The copy-on-write iterator is created **before** `"after"` is added, so the snapshot has one element `"before"`, whereas the current collection has two.
- `Future.get(5,SECONDS)` sets a deadline for the demo and propagates worker exceptions; the code uses `shutdownNow()` in `finally` for pool cleanup. A deadline does not guarantee cancelling every kind of blocking work in production.

**Correct, but not necessarily optimal:** Under write-heavy workloads, `synchronizedList` can become a contention point, while `CopyOnWriteArrayList` incurs copy overhead. Choose the right collection for the usage pattern rather than applying any "concurrent" name to every situation.

## 11. `ConcurrentModificationException`: not a "thread safety protection mechanism"

Iterators of `ArrayList` and `HashMap` typically exhibit **fail-fast** behavior: if the collection's structure is modified outside the iterator during traversal, it may throw `ConcurrentModificationException`. However, the JDK documentation emphasizes that detecting all concurrent modifications cannot be guaranteed; fail-fast is a **best-effort mechanism to detect bugs**, not to be relied upon as a correctness protocol.

Even a single-threaded program can throw this exception:

Create **`FailFastIsNotSafetyDemo.java`**:

```java
import java.util.ArrayList;
import java.util.ConcurrentModificationException;
import java.util.Iterator;
import java.util.List;

public class FailFastIsNotSafetyDemo {
    public static void main(String[] args) {
        List<String> names = new ArrayList<>();
        names.add("A");
        names.add("B");

        Iterator<String> iterator = names.iterator();
        names.add("C"); // Structural modification outside iterator.

        boolean detected = false;
        try {
            iterator.next();
        } catch (ConcurrentModificationException e) {
            detected = true;
        }

        System.out.println("detected=" + detected);
        System.out.println("size=" + names.size());
    }
}
```

Compile/run:

```bash
javac FailFastIsNotSafetyDemo.java
java FailFastIsNotSafetyDemo
```

Typical stdout on JDK 17 for this sequence:

```text
detected=true
size=3
```

This example **does not have two threads**, yet it still throws `ConcurrentModificationException` due to a structural modification after the iterator was created. That proves the exception's name **does not imply a race between two threads**.

With actual concurrent mutation, sometimes it throws the exception and sometimes it does not. **Do not write logic like "if no ConcurrentModificationException has been seen, the list is safe".** Protect traversal with the same lock, use a snapshot, or use a collection with suitable iteration semantics.

### Iterators of synchronized wrappers

`Collections.synchronizedList`/`synchronizedMap` protect individual methods, but their iterators **do not automatically lock the entire traversal**. You must manually synchronize on the wrapper when obtaining the iterator and iterating. Meanwhile, `CopyOnWriteArrayList` has a snapshot iterator, and `ConcurrentHashMap` has a weakly consistent iterator. The two do not share the same semantics and cannot be swapped arbitrarily if a single logical snapshot is required.

## 12. Can `volatile` fix `ArrayList`/`HashMap`?

Example:

```java
private volatile List<String> shared = new ArrayList<>();

void add(String value) {
    shared.add(value);
}
```

This is a snippet inside a class. `volatile` applies to **reading/writing the `shared` reference**, not to automatically placing a monitor/CAS around `ArrayList.add` operations. If two threads call `add` concurrently, they are still mutating **the same object** whose fields are not designed for concurrent access.

Similarly:

```java
private volatile Map<String, Integer> map = new HashMap<>();
```

does not make `map.put` thread-safe.

### When `volatile` can help: publishing a snapshot, no mutation after publication

Another design is:

```java
private volatile List<String> snapshot = List.of();

void replaceAllNames(List<String> source) {
    snapshot = List.copyOf(source);
}

List<String> readSnapshot() {
    return snapshot;
}
```

This is a snippet inside a class, using `java.util.List`. The idea is to **create a new collection** and publish the reference via `volatile`; readers observe a fully constructed snapshot list and do not mutate it. However, if multiple writers concurrently replace the snapshot based on old state, a lock/CAS is needed to avoid **lost updates between snapshots**. In addition, `List.copyOf` provides **shallow immutability** with respect to elements: if an element is a shared mutable object, it can still be mutated externally.

**Note:** immutable snapshots suit configuration/read-mostly workloads; they are not a replacement for per-element concurrent updates in write-heavy workloads.

## 13. When can read-only concurrent access be correct?

An `ArrayList`/`HashMap` that is **no longer mutated** after construction can be read concurrently by multiple threads, provided the object and its related data are **safely published**.

Some publication mechanisms with appropriate contracts:

- Initialize before `Thread.start()` and pass the reference safely to threads started afterward.
- Publish via `volatile` or `AtomicReference`.
- Publish under `synchronized`/`Lock` and have readers read with the same mechanism.
- Pass through `BlockingQueue`/concurrent structures with an appropriate memory-consistency contract.
- Use immutable values/`List.of`/`Map.of` when mutation is not needed.

**This does not mean "read-only means no need to think about visibility".** If one thread creates and mutates a map and then leaks the reference to another thread through an ordinary unsynchronized field, the reader may not see a properly published state.

### Immutable collections do not automatically make elements immutable

`List.of(person1, person2)` prevents adding/removing/replacing elements through the list API, but if `person1` is a mutable object modified by another thread, the internal data still has a race. An immutable collection protects **the collection structure**; the underlying data model must still follow ownership/immutability/JMM rules.

### `Collections.unmodifiableList` is not a synchronized snapshot

`Collections.unmodifiableList(mutableList)` typically only creates a **read-only view** of the underlying list. If another thread holds `mutableList` and modifies it, the view can observe updates and the corresponding issues. Do not call an unmodifiable view over mutable shared state "thread-safe immutable" while the underlying data is still being mutated.

## 14. Is `HashMap.get` concurrent with `HashMap.put` safe?

There is no thread-safety guarantee if thread A is mutating the map while thread B calls `get` without synchronization. Even though B is "read-only", the same object is being modified, so B may fail to see the new value or observe inconsistencies under the JMM. Do not use `HashMap` as a concurrent cache just because "an occasional cache miss is fine".

Solutions depend on the contract:

- **Concurrent mutable cache:** use `ConcurrentHashMap` with atomic APIs like `computeIfAbsent` and `putIfAbsent` as needed.
- **Rarely changing config/map snapshot:** build a new map, make an immutable copy, and publish safely via `volatile`/atomic reference.
- **Multiple related keys in one transaction:** use a shared lock or a state snapshot with multi-key invariants.
- **Cache with eviction, expiry, loading, capacity:** consider a dedicated cache implementation; `ConcurrentHashMap` does not inherently provide TTL, bounded memory, or exactly-once external loading.

### Why is `getOrDefault + put` still wrong even with a concurrent map?

`ConcurrentHashMap.getOrDefault` and `put` each have proper semantics when called individually, but another thread can still interleave between them. To increment a counter, use `merge` or `compute` on the same key; to register only if absent, use `putIfAbsent`. A **thread-safe method** does not automatically elevate every business sequence to atomicity.

## 15. `HashMap` keys, `hashCode`, and mutable keys

Even within **a single thread**, using a mutable object as a key whose `equals/hashCode` changes after `put` can cause `get` to no longer find the mapping. This is a bug **distinct** from concurrency.

With multiple threads, the risk is greater: if threads concurrently mutate fields affecting `hashCode/equals` of a key currently in the map, key lookup and hash computation can become inconsistent. **`ConcurrentHashMap` does not cure mutable-key bugs.** Choose immutable keys or keys with stable semantics for as long as the key remains in the map.

Illustrative example:

```java
record Key(String region, long id) {}
```

A Java 17 `record` with immutable reference/primitive components is a reasonable choice for a simple key. However, a record containing a mutable object can still carry risk if that component is modified.

**An independent rule:** do not mutate state that determines a key's `equals/hashCode` after inserting it into a hash-based map.

## 16. Choosing the right collection for the workload

| Need | Usually suitable choice | What to understand |
| --- | --- | --- |
| Single thread owns the list | `ArrayList` | No overhead of concurrent abstractions |
| Multiple readers after construction | Safely published immutable/snapshot | Do not mutate after publish; watch out for mutable elements |
| Multiple threads mutate list, order/index | `Collections.synchronizedList` + lock protocol | Compound operations/iteration require a shared lock |
| Small listener list, very few writes | `CopyOnWriteArrayList` | Write copies cost memory/CPU; snapshot iteration |
| Concurrent map with many independent keys | `ConcurrentHashMap` | Per-key atomic operations when using the right methods |
| Rarely accessed map, easy to lock as a whole | `Collections.synchronizedMap` | Avoid bypassing the wrapper and missing compound atomicity |
| Ordered concurrent set/map | `ConcurrentSkipListMap/Set` when ordering is needed | Different cost and semantics from hash map |
| Per-key counter | `ConcurrentHashMap.merge/compute` | Avoid `get + put` |
| Heavy writes to the same hot counter | `AtomicLong`/`LongAdder` depending on semantics | `LongAdder` is not an atomic snapshot during concurrent updates |
| Strong multi-object invariant | Shared lock/transaction/immutable aggregate CAS | One atomic method on one map is not enough |

**Do not mechanically replace every `ArrayList` with `CopyOnWriteArrayList` and every `HashMap` with `ConcurrentHashMap`.** If an instance is only used inside a single worker's method and does not escape, a thread-safe collection is unnecessary. If an invariant spans multiple collections, choosing a collection name alone is also insufficient.

## 17. Synchronizing with a lock: why can deadlocks still happen?

If you use a synchronized wrapper or a shared monitor, you must ensure a clear lock order. For example, thread A holds `lockA` and calls into code that needs `lockB`, while thread B holds `lockB` and waits for `lockA`: there is a risk of deadlock. If a lock is held during long I/O calls, other threads are delayed.

Good policies:

1. Hold the lock only when reading/modifying **the exact state that needs protection**.
2. Maintain a consistent **lock acquisition order** across the entire application when multiple locks are needed.
3. Do not invoke arbitrary callbacks or blocking operations inside a critical section if avoidable.
4. Do not expose the mutable backing collection for external code to bypass the protocol.
5. Encapsulate access through methods with clear invariants instead of handing out the raw list/map everywhere.
6. When using a synchronization wrapper, lock on **the wrapper itself** if the iterator contract requires it; do not pick a different monitor in the caller.

If code has many readers, a `ReadWriteLock` may help in some workloads, but it is **not always faster** than a monitor or `ConcurrentHashMap`. Measure under realistic load.

## 18. Do not rely on a single stress test to prove thread safety

A test like:

```java
List<Integer> list = new ArrayList<>();
for (int i = 0; i < 10_000; i++) {
    new Thread(() -> list.add(1)).start();
}
```

is a **bad snippet to use in production code**: it spawns too many threads, does not wait for them to finish, defines no shutdown, and stresses the wrong thing. Sometimes you will see the expected result, sometimes not; it may OOM or fail for reasons unrelated to `ArrayList`.

To test meaningfully:

- **Define invariants:** no lost jobs, no duplicate bookings, accurate counts, order preserved if required by the contract.
- **Force interleavings:** use `CountDownLatch`/`CyclicBarrier` to place checkpoints before read–modify–write, like `CheckThenActTrapDemo`.
- **Real stress testing:** use a bounded number of workers, `Future.get(timeout)`, check results/consistency, repeat many times, but never call "no errors observed" a proof.
- **Check publication/JMM:** reason about happens-before and data races; a stress test on one CPU/JDK does not cover all schedules.
- **Distinguish internal tests from business logic:** check–then–act can still be wrong even when structural writes are serialized; unsafe concurrent structural mutations can occur outside deterministic tests.
- **Use the right tools:** JMH is for performance benchmarks, not for using benchmark results to prove thread safety; JCStress or coordinated tests help inspect interleavings/memory effects, yet sound reasoning about the contract is still required.
- **Do not run forever:** set timeouts, clean up executors, and propagate worker exceptions back to the main thread.

### Tests should not catch `ConcurrentModificationException` as a required signal

Fail-fast is only best-effort; a concurrent mutation may go undetected by the iterator. Conversely, CME also appears when **the same thread** mutates a list improperly while using an iterator. Assert invariants and synchronize properly instead of expecting an exception to report the bug.

## 19. Three core principles from the Java Memory Model

### 19.1. Mutual exclusion/atomicity

A shared lock ensures only one thread executes the critical section at a time, or an atomic operation (such as `ConcurrentHashMap.merge`) updates the target key according to its contract. Without atomicity, two writers can act on a stale snapshot.

### 19.2. Visibility and happens-before

If a writer modifies state and publishes it via `volatile`/atomic/lock or a concurrent queue, a reader observes the state according to the appropriate happens-before relationship. Otherwise, a reader calling `HashMap.get` may not reliably see the new state, and reading `ArrayList.size` does not equate to having a valid snapshot.

### 19.3. Ordering

The compiler, JIT, and CPU may perform optimizations permitted by the Java Memory Model. Do not use the assumption "on my machine two statements always run in source order" to infer that another thread sees fields in that order without valid synchronization.

A `final` reference or an immutable list/map container can assist the design, but safe publication and mutation ownership requirements must still be analyzed for each object.

## 20. Common mistakes

| Mistake | Why it is wrong | How to fix it? |
| --- | --- | --- |
| Treating `ArrayList.add` as atomic with multiple writers | `size`/backing array are unprotected | Lock or thread-safe collection |
| Treating `HashMap.put` as safe because keys differ | Resize, table, and size are shared structures | `ConcurrentHashMap` or lock |
| `volatile List/Map` then mutating internally | `volatile` only applies to reference access | Protect the mutable object |
| `Collections.synchronizedList` then unlocked `contains + add` | Compound operation can still interleave | `synchronized(list)` around the whole block |
| Unlocked iterator on a synchronized wrapper | `next` runs while a writer mutates | Lock the wrapper for the entire traversal |
| `ConcurrentHashMap.get + put` to increment a counter | Two separate methods do not combine atomically | `merge`/`compute` |
| Using a mutable key whose `hashCode` changes | Mapping can no longer be looked up reliably | Immutable/stable keys |
| Assuming `ConcurrentModificationException` always appears | Fail-fast is best-effort | Do not rely on exceptions for correctness |
| Assuming no CME means it is safe | Data races can be silent | Choose the right synchronization contract |
| Testing only with `Thread.sleep` | Scheduling is non-deterministic | Latch/barrier with deadlines |
| Treating `ConcurrentHashMap` as a multi-key transaction | Per-key updates do not protect the whole workflow | Lock/transaction/aggregate state |
| Thinking `CopyOnWriteArrayList` is free | Writes copy the entire array | Use only for read-mostly workloads |
| Using `List.copyOf` with mutable elements | Shallow immutability | Deep immutability/ownership |
| Using `Collections.unmodifiableList` on a still-mutated list | View is not a snapshot | Snapshot/immutable publication |
| Exposing the backing map via a getter | Callers can bypass the protocol | Return a snapshot or a narrow interface |
| Holding a lock during long I/O/callbacks | Contention/deadlock | Shrink the critical section |
| Thinking picking a "concurrent" collection is enough | Business invariants may span multiple steps | Design an atomic workflow |
| Treating error-free stress runs as proof | Lacks coverage of all interleavings | JMM reasoning + targeted tests |

## 21. Self-check questions

**1. Why is `new ArrayList<>(1000)` unsafe when two threads call `add`?** Pre-allocated capacity does not turn choosing an index, writing to the array, and updating `size` into an atomic operation.

**2. If two threads call `HashMap.put` on two different keys, is it always safe?** No. They still mutate shared buckets/table/size and can resize concurrently.

**3. Are two readers only reading a `HashMap` safe?** Possibly, if the map has been constructed and **safely published** and is never mutated afterward, along with proper management of its element data.

**4. Does `volatile Map` make `map.put` thread-safe?** No. A `volatile` reference does not protect the mutable fields inside the map.

**5. Why can `Collections.synchronizedList` still add duplicates?** `contains` and `add` are two separate synchronized method calls. A shared lock covering the whole workflow or an appropriate atomic API is required.

**6. Does `ConcurrentHashMap` make `get + put` counter increments atomic?** No. Use `merge("hits",1,Integer::sum)` or `compute`.

**7. Does seeing `ConcurrentModificationException` guarantee two threads are involved?** No. The same thread mutating outside an iterator can also throw it.

**8. If no `ConcurrentModificationException` is seen, is the list/map safe?** No. Fail-fast is best-effort and is not a safety mechanism.

**9. Does a `CopyOnWriteArrayList` iterator see elements added after the iterator was created?** No; it traverses a snapshot from the time the iterator was created.

**10. Is a `ConcurrentHashMap` iterator an absolute transactional snapshot?** No. It is weakly consistent and may observe partial updates while iterating.

**11. Is `Collections.unmodifiableList` an immutable snapshot?** Not necessarily. It may be a view over an underlying mutable list.

**12. When is `HashMap` still reasonable in concurrent code?** When the map belongs to only one thread, or is immutable after safe publication, or all mutable reads/writes are protected by a valid synchronization protocol.

**13. Does using `ConcurrentHashMap.putIfAbsent` prevent a race when registering a key?** Yes for the atomic mapping of that key, but it does not automatically create a transaction covering external DB/payment/resources.

**14. Why can a two-thread test with latches still fail logically even when writes are serialized?** Because both threads read the same stale snapshot before the first write occurred. That is a check–then–act race, which does not require simultaneous concurrent writes.

**15. What should be used to update multiple keys under one invariant?** A lock/transaction/immutable aggregate and appropriate state machine are needed; atomic operations on individual keys do not automatically form an atomic multi-key operation.

## 22. Selection and implementation checklist

1. **Is the collection shared across multiple threads?** If not, use a regular `ArrayList`/`HashMap`.
2. **Are there mutations after publication?** If not, use a safely published immutable/read-only snapshot.
3. **Are there multiple concurrent writers?** Choose synchronization or a collection with the right contract.
4. **Does the invariant involve one key or multiple keys?** `ConcurrentHashMap.merge/compute` fits per-key; locks/transactions fit multi-state.
5. **Does the list need snapshot iteration or frequent updates?** `CopyOnWriteArrayList` for read-mostly; synchronized list for other patterns.
6. **Is there a compound check–then–act?** Choose an atomic method or a shared lock wrapping the entire operation.
7. **Is iteration over a wrapper properly locked?** `synchronized(wrapper)` when required.
8. **Is a reference to the backing collection exposed externally?** Prevent protocol bypasses.
9. **Are elements/keys mutable?** Stabilize `equals/hashCode`, consider deep immutability.
10. **Are there waits/side effects inside the critical section?** Minimize or restructure them.
11. **Are there tests with latches and invariants?** Do not rely on the luck of `Thread.sleep`.
12. **Are failures/timeouts/executor cleanup tested?** Do not leave workers alive forever.
13. **Are contention, throughput, and allocation measured before optimizing?** Correctness comes first.
14. **Are memory visibility and publication explained for readers?** Thread safety is not just about locking writes.
15. **Are the right iteration semantics chosen?** Fail-fast differs from weakly consistent and snapshot.

**Conclusion:** `ArrayList` and `HashMap` **do not automatically protect their mutable internal state when read/written by multiple threads without synchronization**. Bugs occur at two levels: **data races/structural inconsistency** from unsafe mutations, and **non-atomic business check–then–act** from combining separate operations. The fix must be based on the invariant: using a shared lock, a synchronized wrapper with an external lock for iteration/compound operations, `ConcurrentHashMap` with `merge/compute/putIfAbsent`, `CopyOnWriteArrayList` for read-mostly workloads, or a safely published immutable snapshot. Most importantly, **design an ownership and happens-before policy for the entire workflow**, rather than just renaming the collection.
# Collections.synchronizedMap/List and Locking Requirements During Iteration

## 1. The Problem: Regular Collections Are Not Automatically Safe for Concurrent Access

`ArrayList` and `HashMap` are designed primarily for regular (single-threaded) access. If one thread modifies them while another thread reads or modifies them without proper synchronization, the program can encounter race conditions, inconsistent results, or unexpected behavior. You should not assume that just because a `get()` or `add()` call looks simple, using the same collection from multiple threads is safe.

Java provides synchronized wrappers in `java.util.Collections`:

```java
Map<String, Integer> map =
        Collections.synchronizedMap(new HashMap<>());

List<String> list =
        Collections.synchronizedList(new ArrayList<>());
```

These methods create a **wrapper** around the backing collection. The wrapper uses a shared monitor to synchronize the operations it provides, such as `get`, `put`, `add`, `remove`, or `size`. This is a useful option when you want to use the familiar `Map`/`List` interface with a simple locking mechanism.

However, **each individual call being synchronized does not mean a sequence of multiple calls is atomic**. And one very important point: **when iterating using an `Iterator`, enhanced `for`, `Spliterator`, or `Stream`, the caller must typically lock the wrapper explicitly for the entire duration of the iteration**.

This lesson focuses on Java Concurrency in general, unrelated to Spring.

## 2. How Do Synchronized Wrappers Work?

Example:

```java
List<String> raw = new ArrayList<>();
List<String> safe = Collections.synchronizedList(raw);
```

The idea is that all shared access to the data must go through `safe`. The wrapper's implementation uses a consistent internal lock to guard its calls. For a wrapper returned directly by `Collections.synchronizedList(...)` or `synchronizedMap(...)`, **external locking must use the wrapper object itself**:

```java
synchronized (safe) {
    // Multiple related operations are held under the same monitor.
    safe.add("a");
    safe.add("b");
}
```

This kind of synchronization establishes *happens-before* relationships when a thread releases the monitor and another thread acquires the same monitor. As a result, the data protected by the wrapper can be observed properly according to Java's synchronization rules. However:

- The wrapper **does not protect** accesses that go directly through `raw` if other code still holds a reference to the backing collection.
- The wrapper cannot fix multi-step logic with a race condition unless the entire sequence is locked.
- It does not make a mutable element inside the collection thread-safe. For example, a `Person` with mutable fields still needs its own synchronization mechanism for `Person`'s state.
- It does not turn the collection into an immutable snapshot or allow an iterator to traverse safely while other threads modify it without locking.
- All threads that want to be protected by the same contract must consistently use the exact same wrapper/monitor.

To avoid unsynchronized access paths, you should create the backing collection and the wrapper at the same time, and **only publish the wrapper** to other threads. Safe publication of the reference is also part of shared-data design: use mechanisms such as initializing before starting threads, properly constructed `final` fields, or handoff through an appropriate concurrent structure.

## 3. What Is Protected by synchronizedMap and synchronizedList?

### A Single Method Call

```java
Map<String, Integer> counts =
        Collections.synchronizedMap(new HashMap<>());
counts.put("ok", 1);        // A single synchronized call.
Integer value = counts.get("ok"); // A single synchronized call.
```

Each call above is guarded by the wrapper using its monitor. Similarly, with `synchronizedList`, standard operations such as `add`, `get`, `set`, `remove`, and `size` are synchronized at the method level.

Since Java 8, the JDK wrappers also implement synchronization for many appropriate default methods, such as `Map.computeIfAbsent`, `Map.merge`, `Map.forEach`, or `List.replaceAll`. When using a single method, read the exact contract of that method rather than combining it with multiple separate calls on your own.

### Multiple Consecutive Calls

Example of logic that is not safe regarding atomicity:

```java
if (!counts.containsKey("hits")) {
    counts.put("hits", 0);
}
counts.put("hits", counts.get("hits") + 1);
```

This is an illustrative fragment. Each step—`containsKey`, `get`, and `put`—has its own lock, but **other threads can interleave between them**. Specifically, two threads can both read the same old value and both write the same new value, causing a lost increment.

When you need to turn multiple operations into a single logical unit, synchronize **around the entire sequence**:

```java
synchronized (counts) {
    counts.put("hits", counts.getOrDefault("hits", 0) + 1);
}
```

Now other threads using the same wrapper/monitor cannot interleave between `getOrDefault` and `put`. Keep the code inside the lock short enough to avoid increasing wait times.

Another option, when the problem is genuinely per-key updates and high concurrency is needed, is `ConcurrentHashMap` with `compute`, `merge`, or `AtomicInteger` used appropriately. You do not always need to stick with `synchronizedMap`.

## 4. The Most Important Rule: Lock the Entire Iteration

The JDK explicitly specifies: when iterating over a synchronized collection via `Iterator`, `Spliterator`, or `Stream`, the user must perform the iteration inside a `synchronized` block on the appropriate wrapper. This is because creating an iterator or obtaining a stream does not make **the entire sequence of iteration steps** atomically locked.

### 4.1. Iterating Over a synchronizedList

**Wrong:**

```java
List<String> items =
        Collections.synchronizedList(new ArrayList<>());
items.add("A");
items.add("B");

for (String item : items) { // No lock covering the traversal.
    System.out.println(item);
}
```

The `for-each` loop actually calls `iterator()` and multiple `hasNext()`/`next()` steps. Another thread can modify the list between steps. The fact that each `items.add(...)` call is synchronized **does not guarantee** that traversal is free from races.

**Correct:**

```java
synchronized (items) {
    for (String item : items) {
        System.out.println(item);
    }
}
```

While the loop is running, threads modifying the list through the same `items` wrapper must wait for the monitor to be released. This creates a consistent observation window under the shared-monitor contract.

### 4.2. Iterating Over a synchronizedMap

**Wrong:**

```java
Map<String, Integer> scores =
        Collections.synchronizedMap(new HashMap<>());
scores.put("A", 10);
scores.put("B", 20);

for (Map.Entry<String, Integer> entry : scores.entrySet()) {
    System.out.println(entry.getKey() + "=" + entry.getValue());
}
```

**Correct:**

```java
synchronized (scores) {
    for (Map.Entry<String, Integer> entry : scores.entrySet()) {
        System.out.println(entry.getKey() + "=" + entry.getValue());
    }
}
```

For map views such as `keySet()`, `entrySet()`, and `values()`, the lock that must be acquired is the **original map wrapper**, which is `scores` in the example.

Do not use `synchronized(scores.entrySet())` as a substitute. The returned view may share an internal mutex with the original map, but the monitor of the view object itself is not necessarily the monitor protecting calls on the wrapper. The API contract requires locking `scores`.

### 4.3. With Iterator, Spliterator, and Stream

Apply the same principle:

```java
synchronized (items) {
    Iterator<String> it = items.iterator();
    while (it.hasNext()) {
        String value = it.next();
        // Keep processing short without complex side effects.
        System.out.println(value);
    }
}
```

And with streams:

```java
long count;
synchronized (items) {
    count = items.stream()
            .filter(s -> !s.isBlank())
            .count();
}
```

Note: you must hold the lock **until the terminal operation completes**, not just when creating `stream()`. With `parallelStream()`, holding the monitor on the calling thread does not automatically ensure safety for callbacks running on other worker threads if they access external state. Consider taking a snapshot first and then processing in parallel, rather than trying to hold a long lock across a complex pipeline.

### 4.4. Why Fail-Fast Iterators Do Not Replace Locking

Iterators of regular `ArrayList` and `HashMap` have a structural modification detection mechanism that throws `ConcurrentModificationException` in certain situations. This is **best-effort error detection**, not a synchronization mechanism, and it is not guaranteed to always throw an exception when a race occurs.

It is a mistake to write:

```java
try {
    for (String item : items) {
        use(item);
    }
} catch (ConcurrentModificationException ignored) {
    // Does not make the iteration operation safe.
}
```

This is a fragment; `use(...)` is application-defined. Catching the exception only hides the problem. The solution is to lock properly or change the collection/traversal design. Even when no `ConcurrentModificationException` is observed, an unlocked traversal can still miss elements, duplicate elements, or produce inconsistent results under concurrent modification.

## 5. Which Monitor to Choose When Iterating Views and subList?

A subtle mistake is locking the wrong object returned by a view-creating method.

| Collection used for iteration | Monitor to lock |
| --- | --- |
| `Collections.synchronizedList(list)` directly | The synchronized-list wrapper object itself |
| `list.subList(from, to)` returned from a synchronized-list | **The original list wrapper** that created the sublist |
| `Collections.synchronizedMap(map)` directly | The synchronized-map wrapper itself |
| `map.keySet()` | **The original map wrapper** |
| `map.entrySet()` | **The original map wrapper** |
| `map.values()` | **The original map wrapper** |

Example:

```java
List<Integer> numbers = Collections.synchronizedList(
        new ArrayList<>(List.of(1, 2, 3, 4)));

List<Integer> tail = numbers.subList(2, 4);

synchronized (numbers) { // Lock the original wrapper, not tail.
    for (Integer n : tail) {
        System.out.println(n);
    }
}
```

A view is backed by the original collection; changes to the original collection can change the view or invalidate a sublist according to the `List` contract. You should not publish views to multiple threads without clearly controlling the monitor and lifecycle.

Map example:

```java
Map<String, Integer> map =
        Collections.synchronizedMap(new HashMap<>());
Set<String> keys = map.keySet();

synchronized (map) {
    for (String key : keys) {
        System.out.println(key);
    }
}
```

The fact that `keys` may be a synchronized view does not change the locking rule: **use `map`** for the entire traversal.

## 6. Standalone Java 17 Example: Lost Update and Properly Locked Iteration

This program creates a **controlled** race using `CountDownLatch`. Both tasks read the old value before being allowed to write; the result deterministically shows a lost increment even though both `get` and `put` are synchronized methods. Then the program switches to external locking around the entire read–modify–write operation and verifies both increments.

The second half demonstrates how to iterate over a synchronized-list and a synchronized-map with deterministic results. To avoid depending on `HashMap` iteration order, we take a snapshot inside the lock and sort the snapshot after releasing the lock.

Save the file as **`SynchronizedCollectionsDemo.java`**:

```java
import java.util.ArrayList;
import java.util.Collections;
import java.util.HashMap;
import java.util.List;
import java.util.Map;
import java.util.concurrent.Callable;
import java.util.concurrent.CountDownLatch;
import java.util.concurrent.ExecutorService;
import java.util.concurrent.Executors;
import java.util.concurrent.Future;
import java.util.concurrent.TimeUnit;

public class SynchronizedCollectionsDemo {
    public static void main(String[] args) throws Exception {
        Map<String, Integer> counts =
                Collections.synchronizedMap(new HashMap<>());
        counts.put("hits", 0);

        ExecutorService pool = Executors.newFixedThreadPool(2);
        CountDownLatch bothRead = new CountDownLatch(2);
        CountDownLatch mayWrite = new CountDownLatch(1);

        try {
            Callable<Void> unsafeIncrement = () -> {
                int old = counts.get("hits");  // get() alone is synchronized.
                bothRead.countDown();
                mayWrite.await();             // Both have read old=0.
                counts.put("hits", old + 1);   // put() alone is synchronized.
                return null;
            };

            Future<Void> first = pool.submit(unsafeIncrement);
            Future<Void> second = pool.submit(unsafeIncrement);

            bothRead.await();
            mayWrite.countDown();
            first.get();
            second.get();
            System.out.println("Separate get/put = " + counts.get("hits"));

            counts.put("hits", 0);
            Callable<Void> safeIncrement = () -> {
                synchronized (counts) {
                    int old = counts.get("hits");
                    counts.put("hits", old + 1);
                }
                return null;
            };

            first = pool.submit(safeIncrement);
            second = pool.submit(safeIncrement);
            first.get();
            second.get();
            System.out.println("Atomic get/put = " + counts.get("hits"));
        } finally {
            mayWrite.countDown();
            pool.shutdown();
            if (!pool.awaitTermination(5, TimeUnit.SECONDS)) {
                pool.shutdownNow();
            }
        }

        List<String> words = Collections.synchronizedList(
                new ArrayList<>(List.of("beta", "alpha")));
        List<String> wordSnapshot = new ArrayList<>();

        synchronized (words) {
            for (String word : words) {
                wordSnapshot.add(word);
            }
        }
        Collections.sort(wordSnapshot);
        System.out.println("List snapshot = "
                + String.join(",", wordSnapshot));

        Map<String, Integer> scores =
                Collections.synchronizedMap(new HashMap<>());
        scores.put("b", 2);
        scores.put("a", 1);
        List<String> entries = new ArrayList<>();

        synchronized (scores) {
            for (Map.Entry<String, Integer> entry : scores.entrySet()) {
                entries.add(entry.getKey() + "=" + entry.getValue());
            }
        }
        Collections.sort(entries);
        System.out.println("Map snapshot = " + String.join(",", entries));
    }
}
```

Compile and run with Java 17 or later:

```bash
javac SynchronizedCollectionsDemo.java
java SynchronizedCollectionsDemo
```

Deterministic stdout:

```text
Separate get/put = 1
Atomic get/put = 2
List snapshot = alpha,beta
Map snapshot = a=1,b=2
```

Explanation:

- In the first test, `bothRead` forces **both tasks to read `0`** before either is allowed to write. Therefore, each task writes `1`; there is no chance of accidentally getting `2` because one thread finished first.
- In the next test, each task holds the `counts` monitor throughout reading the old value and writing the new value. No thread can interleave between the two steps, so the result is `2`.
- Both the List and the Map create a snapshot inside the `synchronized` block and then sort/print the snapshot after releasing the lock. Thus, code outside the lock does not hold the monitor for long, and the printed output does not depend on `HashMap` ordering.
- Two `Future.get()` calls make `main` wait for the tasks to finish while also surfacing exceptions if a task fails. `shutdown()` stops the pool from accepting new tasks; `awaitTermination` is used for clean termination in the demo.

This is an educational example using `CountDownLatch` to intentionally trigger a race condition. In real applications, we do not use latches to slow down every variable increment; the example simply shows that **method-level synchronization is different from transaction-level synchronization**.

## 7. Snapshots: Reducing Lock Hold Time and Avoiding Iteration Over a Changing Collection

If the iteration performs slow work (writing files, calling external services, CPU-intensive computation), holding the lock throughout can block all threads that want to modify the collection. When you need a consistent point-in-time view, create a copy **while holding the lock**, then process the copy outside the lock:

```java
List<String> snapshot;
synchronized (items) {
    snapshot = new ArrayList<>(items);
}

for (String value : snapshot) {
    slowOperation(value);
}
```

This fragment assumes `items` is a synchronized-list wrapper and `slowOperation` is application-defined. Effect: the lock is only held while copying the list structure. However, **this snapshot is a shallow copy**: if the elements are mutable objects, the element objects themselves can still be modified by other threads. If you want a truly immutable data snapshot, you need to copy/freeze the elements or use an appropriate immutable design.

Similarly for a map:

```java
Map<String, Integer> snapshot;
synchronized (scores) {
    snapshot = new HashMap<>(scores);
}
for (Map.Entry<String, Integer> entry : snapshot.entrySet()) {
    slowOperation(entry);
}
```

The map copy after releasing the lock does not automatically update when `scores` changes. This is often desirable for reporting or point-in-time consistent processing, though you must accept that the data can become stale immediately after the snapshot.

### Lock Hold Time Comparison

| Strategy | Consistency | Impact on producers |
| --- | --- | --- |
| Iterate directly inside `synchronized(list)` | No monitor-respecting thread can interleave modifications during iteration | Threads modifying/reading via the wrapper may wait until the entire traversal finishes |
| Create snapshot under lock, process outside lock | Snapshot is structurally stable after copying | Producers only wait during the copy |
| Iterate without locking on a synchronized wrapper | Not guaranteed safe under concurrent modification | Race condition; do not use |
| Use a concurrent collection with weakly consistent or snapshot iterator | Depends on each collection's contract | Usually reduces blocking, trading off different semantics and costs |

Snapshots are useful when the traversal takes longer than the copy cost; if the collection is huge or copying creates memory/GC pressure, consider a different design.

## 8. How Do Synchronized Wrappers Differ from Concurrent Collections?

`Collections.synchronizedMap/List` uses a **single shared lock** for calls that require synchronization. This model is easy to understand, but contention can be high when many threads access it continuously.

| Option | Best suited for | Notes on traversal and updates |
| --- | --- | --- |
| `Collections.synchronizedMap(new HashMap<>())` | Wanting HashMap-like semantics with external locking for multi-step sequences | Iterating views must lock the original map |
| `Collections.synchronizedList(new ArrayList<>())` | Wanting ArrayList-like semantics and explicit external locking | Iterating via iterator/list must lock the list wrapper |
| `ConcurrentHashMap<K,V>` | Many threads reading/updating independently, needing lower contention | *Weakly consistent* iterator, may reflect partial changes; no need to lock the entire map to avoid internal races |
| `CopyOnWriteArrayList<E>` | Heavy reads/iteration, very rare modifications | Iterator is a snapshot at creation time; each modification typically copies the array, high cost |
| Immutable collections (`List.of`, `Map.of`, appropriate copies) | Read-only after safe publication | Updates not supported; mutable elements still require attention |

`ConcurrentHashMap` provides atomic per-key update operations such as `compute`, `merge`, and `putIfAbsent`. However, it does **not** guarantee that a full-map traversal is an atomic snapshot while threads continue updating. In addition, `ConcurrentHashMap` does not allow `null` keys or values, unlike `HashMap` (and a `synchronizedMap` wrapper around `HashMap`).

`CopyOnWriteArrayList` is suitable for few writes and many traversals, such as a listener list that rarely changes. Its iterators are based on an array snapshot and do not support `remove()` via the iterator; every array modification incurs a copy overhead.

`Collections.unmodifiableList` and `Collections.unmodifiableMap` only prevent modification **through the view**; they do not add locking and do not make a mutable backing collection thread-safe. Do not use "unmodifiable" as a substitute for synchronization on data that is still modified by other threads.

### When Is a Synchronized Wrapper Still a Reasonable Choice?

- Small data size or low contention.
- Wanting to preserve `HashMap`/`ArrayList` semantics and API, including their respective `null` key/value behavior.
- Needing multi-step operations with an externally lockable monitor.
- Not requiring high throughput when many threads read and write concurrently.

When throughput or latency degrades because of a single shared monitor, consider concurrent collections or changing the data design—do not just add more threads.

## 9. Other Multi-Step Operations Prone to Races

### 9.1. Check-Then-Add to a List

```java
if (!items.contains("task-A")) {
    items.add("task-A");
}
```

Two threads may both see that it does not exist yet and both add it. If you want "add only once" under the list contract:

```java
synchronized (items) {
    if (!items.contains("task-A")) {
        items.add("task-A");
    }
}
```

If the goal is truly a unique set, `Set` is more appropriate; you can use `Collections.synchronizedSet` or a concurrent set depending on your needs.

### 9.2. Check Size Then Remove First Element

```java
if (!items.isEmpty()) {
    String first = items.remove(0);
}
```

Between `isEmpty()` and `remove(0)`, another thread may remove the element; in that case, the code can throw `IndexOutOfBoundsException` even though each method is synchronized.

```java
String first = null;
synchronized (items) {
    if (!items.isEmpty()) {
        first = items.remove(0);
    }
}
```

This is a fragment; for producer/consumer operations that need to wait until an item is available, `BlockingQueue` usually expresses the business logic better than a synchronized list.

### 9.3. Controlled Iteration and Removal

When you need to iterate and remove elements conditionally, use an iterator inside the lock:

```java
synchronized (items) {
    Iterator<String> it = items.iterator();
    while (it.hasNext()) {
        if (it.next().startsWith("old-")) {
            it.remove();
        }
    }
}
```

You must not concurrently call `items.remove(...)` from another thread without holding the same monitor, nor modify the underlying backing list directly. Whether `Iterator.remove()` is valid depends on the collection and iterator state; a synchronized-list wrapper around `ArrayList` allows this operation when `Iterator` preconditions are met.

### 9.4. Using compute/merge Instead of Manual Sequences?

If your wrapper and JDK support `Map.merge` or `compute` with synchronization on the wrapper, a single call can replace a multi-step operation. For example:

```java
counts.merge("hits", 1, Integer::sum);
```

With `Collections.synchronizedMap` in modern JDKs, the `merge` method is synchronized by the wrapper during execution. This is cleaner than separate `get` then `put` calls when updating a single key. However, the callback in `compute/merge` may execute while holding the monitor; avoid long I/O, calling uncontrolled external code, or creating circular lock dependencies inside the callback.

## 10. Deadlock and Lock Hold Time

Monitor-based locking can easily lead to deadlocks if multiple threads acquire locks in different orders.

Example fragment illustrating the risk:

```java
// Thread 1
synchronized (listA) {
    synchronized (listB) {
        transferAtoB();
    }
}

// Thread 2
synchronized (listB) {
    synchronized (listA) {
        transferBtoA();
    }
}
```

If two threads acquire the outer locks at the same time, they can wait on each other indefinitely. The two transfer functions are only illustrative symbols, not a standalone program. The solution is to enforce **a consistent lock ordering** or a clearly designed application-level lock.

A loop like:

```java
synchronized (items) {
    for (String item : items) {
        sendOverNetwork(item);
    }
}
```

can lock the list during slow network operations, stalling producers for a long time. If you do not need to keep the collection unchanged all the way through sending, copy a snapshot under the lock and send outside the lock. Do not invoke uncontrolled callbacks, wait on a `Future`, or perform long I/O inside a monitor without evaluating latency/deadlock risks.

The wrapper's internal synchronized methods have no timeout mechanism when contending for the monitor. If you need locking with a timeout, you may need a design based on `ReentrantLock.tryLock(...)` or a different collection; do not try to use a `sleep` loop to simulate a timeout for `synchronized`.

## 11. Notes on Memory Visibility and Publication

A monitor guarantees a *happens-before* relationship from an unlock to a subsequent lock on the **same monitor**. Therefore, if multiple threads only read/write the collection's contents properly through the wrapper, the corresponding updates are observed according to the Java memory model rules.

However, the following still require separate design:

1. **Exposed backing collection:** a thread holds `raw` and modifies it without locking, breaking the contract.
2. **Mutable elements:** the wrapper only protects structural access/modification to the collection through it; fields inside contained objects require synchronization or an immutable design.
3. **Using different monitors:** `synchronized(raw)` and `synchronized(wrapper)` are two different locks if the wrapper is a different object from the backing collection; locking the wrong one does not protect against all updates.
4. **Dropping the lock when obtaining an Iterator:** an iterator does not hold the lock from creation until `next()`.
5. **Unsafe wrapper initialization/publication:** a reference can be shared improperly if there is no happens-before relationship ensuring reading threads see a fully constructed state.

For data that is read-only after initialization, building an immutable snapshot and publishing it safely often reduces the need for locking significantly.

## 12. How to Test Concurrency for synchronizedMap/List

You should not write tests that rely solely on `Thread.sleep(10)` to "hope" two threads hit a race. Execution timing depends on the JIT, OS scheduler, CPU, and system load.

Instead, use:

- `CountDownLatch` to coordinate two threads to both read before writing, as in the program in Section 6.
- `ExecutorService` and `Future.get()` to wait for task completion and surface task exceptions.
- Multiple runs to check invariants under load, while not relying solely on iteration counts to prove a race cannot happen.
- Dedicated tests for compound actions such as "contains-then-add", "read-modify-write", and "check-then-remove".
- Tests iterating via `Iterator`, map views, and `subList` while another thread modifies; assert that proper external locking provides the expected contract rather than waiting for a random `ConcurrentModificationException`.
- Measurements of lock hold time, number of waiting threads, and p95 latency if the collection is a bottleneck.

Do not use `ConcurrentModificationException` as a synchronization signal: it may or may not occur under a race; its behavior is not a consistent observation contract.

## 13. Checklist for Using synchronizedMap/List

1. **Create the wrapper once** and make it the primary shared access path; do not let the mutable backing collection be modified outside the wrapper.
2. **Single calls** such as `get/add/put/remove` use the wrapper's synchronization.
3. **Compound operations** needing atomicity must wrap the entire sequence in `synchronized(wrapper)` or use an appropriate atomic operation.
4. **Iterate with Iterator, Spliterator, Stream** inside a `synchronized(wrapper)` block per the API contract.
5. **Map views** (`keySet/entrySet/values`) must always be iterated under the lock of the original map wrapper.
6. **List subList** must be iterated under the lock of the original list wrapper.
7. **Avoid holding locks for long** when there is I/O, callbacks, waiting, or heavy computation; consider snapshots.
8. **Mutable elements** must be protected independently if threads modify the state of the elements themselves.
9. **Control lock ordering** if an operation involves multiple different wrappers.
10. **Choose the right collection** if thread count and update frequency are high: `ConcurrentHashMap`, `CopyOnWriteArrayList`, or `BlockingQueue` may have more suitable semantics.

## 14. Self-Check Questions

**1. Do two threads calling `map.get()` and `map.put()` on a synchronizedMap form an atomic increment?**  
No. Each individual call is synchronized, but another thread can interleave between steps. Lock the entire read-modify-write or use an appropriate atomic operation.

**2. Why does an enhanced `for` loop on a synchronizedList require external locking?**  
Enhanced `for` uses an `Iterator` across multiple steps; the wrapper does not hold the monitor for the entire traversal when the caller obtains an `Iterator` and iterates.

**3. When iterating `map.entrySet()`, should you lock `entrySet()` or `map`?**  
Lock the **original synchronized-map wrapper** (`map`). Locking the view itself does not satisfy this contract.

**4. If you call `list.subList(...)` and then iterate, which lock is correct?**  
Lock the **original synchronized-list wrapper**, not just the returned sublist.

**5. If you have never encountered `ConcurrentModificationException`, is an unlocked iteration safe?**  
No. Fail-fast detection is best-effort and does not prove the absence of races.

**6. Does a snapshot protect against state modifications of individual objects inside it?**  
Not when the snapshot only copies references. Mutable elements still share the same objects.

**7. Why does `ConcurrentHashMap` not require locking the entire map for its iterator to avoid internal errors?**  
It has a weakly consistent iterator designed for concurrent updates. However, the iterator does not provide an atomic snapshot of the entire map.

**8. When is `CopyOnWriteArrayList` more useful than synchronizedList?**  
When traversals/reads are very frequent, updates are very rare, and the array copy cost on each modification is acceptable.

**9. Does calling `Collections.unmodifiableList(raw)` make `raw` thread-safe?**  
No. An unmodifiable view only prevents modification through the view; the backing collection can still be modified and requires synchronization.

## References

- [Java SE 17 — Collections](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/Collections.html)
- [Java SE 17 — List](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/List.html)
- [Java SE 17 — Map](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/Map.html)
- [Java SE 17 — ConcurrentHashMap](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/concurrent/ConcurrentHashMap.html)
- [Java SE 17 — CopyOnWriteArrayList](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/concurrent/CopyOnWriteArrayList.html)

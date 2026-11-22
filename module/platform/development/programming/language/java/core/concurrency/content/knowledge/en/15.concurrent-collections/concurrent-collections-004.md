# Weakly Consistent Iteration and Snapshot Semantics in Java Concurrent Collections

## 1. When a Collection Is Modified During Iteration

A collection is not only used to store data; many concurrent workflows must **iterate** over data: sending notifications to connected users, collecting metrics, scanning a cache, finding pending tasks, or generating reports. While one thread is iterating, another thread may call `add`, `remove`, or `put`.

Three questions must be distinguished:

1. Does the iterator **throw an exception** when the collection is modified?
2. Does the iterator **observe changes** made after it was created?
3. Do the elements observed by the iterator form **a consistent state at a single point in time**?

You cannot infer from the first answer that the third answer is also "yes". An iterator that does not throw `ConcurrentModificationException` **does not mean** it provides an atomic snapshot.

In Java, the mechanisms to understand include:

- **Fail-fast iterator**: many standard collections, such as `ArrayList` and `HashMap`, have iterators that attempt to detect improper structural modifications during iteration.
- **Weakly consistent iterator**: many concurrent collections, such as `ConcurrentHashMap`, `ConcurrentLinkedQueue`, and `ConcurrentSkipListMap`, allow iteration concurrently with updates, may reflect some changes, and do not promise a point-in-time snapshot.
- **Snapshot iterator**: `CopyOnWriteArrayList` and `CopyOnWriteArraySet` use a structural snapshot taken at **the time the iterator is created**, so subsequent structural updates do not appear in that traversal.
- **Explicit snapshot**: the program explicitly creates a copy with guarantees matching the data's invariants. Merely copying a concurrent collection **does not automatically** make the copy represent an atomic point in time for the entire collection.

This lesson focuses on **Java concurrency and Concurrent Collections in general**, without going into frameworks.

### Learning Objectives

After this lesson, you will be able to:

1. Accurately explain fail-fast, weak consistency, and snapshot semantics.
2. Understand why `ConcurrentHashMap` can be iterated during updates without guaranteeing visibility of every update.
3. Use `CopyOnWriteArrayList` when reads/iterations outnumber updates, understanding copy-on-write overhead and the limits of mutable elements.
4. Distinguish a structurally stable snapshot from a **multi-field/multi-key consistent** snapshot.
5. Use a shared lock, immutable state, or protocol versioning when a report needs to observe a consistent overall state.
6. Design tests with deterministic output instead of assuming scheduling order or concurrent iteration order.
7. Choose a collection based on workload, correctness, performance, and data semantics.

## 2. Quick Comparison Table

| Mechanism | Java Examples | Concurrent Modification During Iteration | May See New Updates? | Fixed Structural Snapshot? |
| --- | --- | --- | --- | --- |
| Fail-fast | `ArrayList`, `HashMap` | Not freely supported with standard iterators; may throw `ConcurrentModificationException` | No stable concurrent iteration contract | No |
| Weakly consistent | `ConcurrentHashMap` | Designed to iterate concurrently with updates | **Yes, possibly**; not guaranteed to see all | **No** |
| Weakly consistent | `ConcurrentLinkedQueue` | Supported | Possibly | No |
| Weakly consistent, key-ordered | `ConcurrentSkipListMap` | Supported | Possibly | No |
| Snapshot iterator | `CopyOnWriteArrayList` | Structural updates after iterator creation do not alter that traversal | No, for the captured array structure | **Yes**, snapshot of the array |
| Snapshot iterator | `CopyOnWriteArraySet` | Similar to copy-on-write list | No, for the captured set structure | **Yes**, structural snapshot |
| External synchronization | `Collections.synchronizedList` and shared lock | Caller must hold the monitor while iterating | Does not change while lock is held if all writers comply | Can build a snapshot under the lock |
| Immutable copy | `List.copyOf` / `Map.copyOf` | Copy does not allow structural updates | Structure does not change after creation | Yes, **if the source was read consistently** |

Here, "structural snapshot" does not mean the element objects inside are immutable. For example, if a copied list holds a mutable `Box`, `Box.value` can still change even though the iterator still points to the same original `Box` instances.

**Decision point:** choose the iterator type based on the business question you need to answer, not simply out of a desire to "avoid throwing exceptions".

## 3. Fail-Fast Iterators: Bug Detection, Not a Synchronization Protocol

Many non-concurrent collections record a structural modification counter. The iterator can compare the expected state with the actual state and throw `ConcurrentModificationException` when it detects an improper modification.

Risky example:

~~~java
// Unsafe illustration; not a standalone program.
List<String> list = new ArrayList<>(List.of("A", "B"));
for (String item : list) {
    if (item.equals("A")) {
        list.add("C");  // Structural modification of the list outside Iterator.remove().
    }
}
~~~

With a typical `ArrayList`, this can cause `ConcurrentModificationException` on the next iterator operation. However, **the Javadoc emphasizes that fail-fast is best effort**: it cannot guarantee that every race condition will be detected. Therefore, **never use that exception as a correctness mechanism or synchronization signal**.

### 3.1. "Not Throwing CME" Does Not Prove Safety

If you run buggy code on `ArrayList` many times without seeing `ConcurrentModificationException`, the program can still have data races, observe inconsistent data, or produce non-deterministic results. Conversely, `ConcurrentHashMap` does not throw CME during concurrent iteration **because it has a different iterator contract**, not because it makes multi-element operations atomic.

A series of `get`/`put` operations on a thread-safe map is also not enough to protect multi-key invariants. "Thread-safe collection" does not mean "thread-safe workflow".

### 3.2. Updating Through an Iterator

For some standard collection iterators, `Iterator.remove()` is the valid way to remove the current element. However, whether `remove()` is supported depends on the implementation. For example, the snapshot iterator of `CopyOnWriteArrayList` **does not support** `remove()`, `set()`, or `add()` and will throw `UnsupportedOperationException`.

Do not apply a single iterator-removal pattern across all collections; check the contract of the specific iterator you are using.

## 4. What Is Weakly Consistent Iteration?

A weakly consistent iterator allows progress while the collection undergoes concurrent updates without having the same fail-fast behavior as `ArrayList`. Typically, it:

- Can iterate concurrently while other threads add, remove, or update values.
- Does not throw `ConcurrentModificationException` simply because the collection is modified concurrently.
- May reflect some of the state as of when the iterator was created **and** some subsequent modifications.
- Does not promise to see all changes, or that all returned elements belong to the state at a single point in time.
- Does not lock the entire collection to provide a point-in-time snapshot.

The word **weakly** refers to the observation guarantees during iteration; it does **not** mean the underlying storage is "not thread-safe". `ConcurrentHashMap.get/put/compute` have their own thread-safety and atomicity contracts for individual operations. It is only whole-map iteration that does not provide a consistent multi-key read transaction at a single point in time.

### 4.1. An Interleaving Schedule Can Mix Points in Time

~~~text
Time            Reader thread                      Writer thread
t0              Create iterator on map
t1              Read key A and old value
t2                                                 Update A, add C, remove B
t3              Read some other entries
t4              Iterator completes
~~~

The reader's result may contain some old values and some new values, and may or may not see C. You must not interpret it as "the exact map state at t0" or "the exact map state at t4".

For audits or reports that require a clear cutoff timestamp, a stronger snapshot protocol is needed. For approximate observation of a connection list or metrics, weak iteration can be a very good fit.

## 5. ConcurrentHashMap: Atomic Operations Do Not Turn Iteration Into a Snapshot

`ConcurrentHashMap<K,V>` is designed so multiple threads can update and read the map concurrently. `keySet()`, `values()`, and `entrySet()` provide views whose iterators are **weakly consistent**. Their iterators and spliterators do not throw CME when the map changes concurrently.

### 5.1. There Is No Map-Wide Lock Held Throughout Iteration

An iterator may observe different buckets/entries at different points in time. Therefore:

~~~java
// In-method illustration, not a standalone program.
for (Map.Entry<String, Integer> e : concurrentMap.entrySet()) {
    audit(e.getKey(), e.getValue());
}
~~~

This snippet may be suitable for **approximate reading** or work that can tolerate concurrent updates. It is not suitable if the audit requires 100% accuracy at a shared timestamp—for example, when the sum of balances across multiple accounts must satisfy an invariant.

### 5.2. `size()`, `mappingCount()`, and Aggregates

When concurrent updates occur, aggregate methods such as `size()`, `mappingCount()`, `isEmpty()`, or bulk reductions should not be treated as a whole-map transactional snapshot. `mappingCount()` returns `long` so it can represent sizes exceeding the `int` limit, but it can still be only an **estimate during concurrent modifications**.

Do not write a workflow like this:

~~~java
// Incorrect if size and contents are treated as a single transaction.
int expected = map.size();
for (var e : map.entrySet()) {
    process(e);
}
assert processedExactly(expected);
~~~

The map may change between the `size()` call and reading each entry. The number of elements observed can also change while iterating.

### 5.3. `compute`/`merge` Only Provide Atomicity Within Their Scope

`ConcurrentHashMap.compute(key, ...)` or `merge` guarantees atomicity for updating the mapping of **that specific key** according to its contract. A sequence of updates to `keyA` and then `keyB` can still be interleaved by a reader in between. Do not infer overall atomicity from the fact that each individual operation is thread-safe.

### 5.4. No Insertion-Order Iteration

Do not use `ConcurrentHashMap` like `LinkedHashMap` to infer insertion order. Even when an iterator runs with no writers, iteration order is not a "by put time" contract; when writers are present, you must certainly not treat output order as a transaction history.

If you need key ordering, consider `ConcurrentSkipListMap` with its own semantics; however, **sort order still does not mean a point-in-time snapshot**.

## 6. Example 1 — Weak Iterator Tolerating Updates (Java 17+)

To avoid guessing whether "the iterator sees the newly put element or not", this example only prints things that can be verified deterministically. We create an iterator, read one element, update the map on another thread, and then finish the traversal.

Create `WeakIteratorDemo.java`:

~~~java
import java.util.Iterator;
import java.util.Map;
import java.util.concurrent.ConcurrentHashMap;

public class WeakIteratorDemo {
    public static void main(String[] args)
            throws InterruptedException {
        ConcurrentHashMap<Integer, String> map =
            new ConcurrentHashMap<>();

        map.put(1, "one");
        map.put(2, "two");
        map.put(3, "three");

        Iterator<Map.Entry<Integer, String>> iterator =
            map.entrySet().iterator();

        if (iterator.hasNext()) {
            iterator.next();
        }

        Thread writer = new Thread(() -> {
            map.put(4, "four");
            map.remove(2);
        }, "map-writer");

        writer.start();
        writer.join();

        int visitedAfterUpdate = 0;
        while (iterator.hasNext()) {
            iterator.next();
            visitedAfterUpdate++;
        }

        System.out.println("iteration completed = true");
        System.out.println("map has key 4 = " + map.containsKey(4));
        System.out.println("map has key 2 = " + map.containsKey(2));

        // Do not print visitedAfterUpdate as a fixed constant:
        // a weak iterator may see a timing-dependent set of entries.
        if (visitedAfterUpdate < 0) {
            throw new AssertionError("Impossible count");
        }
    }
}
~~~

Compile/run with JDK 17+:

~~~bash
javac WeakIteratorDemo.java
java WeakIteratorDemo
~~~

Stdout:

~~~text
iteration completed = true
map has key 4 = true
map has key 2 = false
~~~

Here, the writer finishes before `main` checks the two `containsKey` conditions, so the final state of the map is clear. However, **the set of entries seen by the iterator** is not fixed in the output: you should not assert that it definitely saw key 4 or definitely did not see key 2.

The program does not catch `ConcurrentModificationException` because there is no need to "suppress errors"; `ConcurrentHashMap`'s iterator itself is designed for concurrent iteration patterns. Note that the example arranges the modifications after the iterator is created and before iteration ends; it does not prove a single execution schedule that every JVM must choose.

### When Is Weak Iteration a Good Choice?

- Scanning sessions/caches for **best-effort tasks**; a newly joined session can be handled in the next pass.
- Collecting approximate metrics or dashboards that do not require an exact cutoff point.
- Scanning to clean up stale entries with an appropriate atomic removal condition, such as `remove(key, expectedValue)` when you need to avoid mistakenly deleting an entry that was already replaced.
- Resource lists that change frequently, as long as the correctness of each action does not depend on the traversal seeing **every single entry**.

**Not suitable** if a single pass must uniquely/completely cover every transaction up to a cutoff, or if the result is the authoritative source for reconciliation.

## 7. ConcurrentLinkedQueue and ConcurrentSkipListMap

### 7.1. ConcurrentLinkedQueue

`ConcurrentLinkedQueue<E>` is a non-blocking concurrent queue implemented using appropriate atomic operations. Its iterator is **weakly consistent**: it can coexist with `offer`/`poll` calls from other threads and does not throw CME just because the queue is modified.

However, iterating over a queue is not "taking each element to process it exactly once". If you want a worker to **claim ownership** of a task, use `poll()`/`remove()` or `BlockingQueue.take()` following the queue pattern—do not just use a for-each loop and assume tasks have been claimed.

`ConcurrentLinkedQueue.size()` may have to traverse the elements, and the result can be inaccurate if the queue is modified while counting. Do not use `size()` on that queue as a reservation counter or an exact backpressure mechanism.

### 7.2. ConcurrentSkipListMap

`ConcurrentSkipListMap` provides a concurrent map with **sorted key order** according to a comparator or natural order. Its iterator is also weakly consistent and does not create an atomic snapshot of all keys/values.

Having key order does not mean having **time order** of updates. When the key set changes during a scan, correctness must still be determined by the contract of individual operations. If you want point-in-time auditing, you need transactions, snapshots, or versioning—not just a sorted concurrent map.

### 7.3. Weakly Consistent Does Not Mean Identical Semantics Across All Classes

Do not turn "may see some updates" into a concrete guarantee that every iterator must see at least one update made after creation. Each collection has its own traversal details, ordering, supported removal operations, and race contracts.

Read the exact Javadoc of the specific collection. Classes may all be grouped under "weakly consistent" while differing in key ordering, null support, counting cost, or removal behavior.

## 8. CopyOnWriteArrayList Snapshot Iterators

`CopyOnWriteArrayList<E>` stores elements in an array, performing structural updates by **creating/publishing a new array**. When an iterator is created, it is bound to **the array at the time the iterator was created**.

If another thread later adds, removes, or replaces an element in the list, the old iterator continues traversing the array it captured initially. It does not throw CME due to concurrent structural changes, and **unlike a weakly consistent iterator**, it does not observe subsequent structural updates during that traversal.

### 8.1. Example 2 — Stable Iterator Snapshot (Java 17+)

Create `CopyOnWriteSnapshotDemo.java`:

~~~java
import java.util.Iterator;
import java.util.List;
import java.util.concurrent.CopyOnWriteArrayList;

public class CopyOnWriteSnapshotDemo {
    public static void main(String[] args) {
        CopyOnWriteArrayList<String> list =
            new CopyOnWriteArrayList<>(List.of("A", "B"));

        Iterator<String> before = list.iterator();

        list.add("C");
        list.set(0, "X");

        System.out.print("iterator snapshot = [");
        boolean first = true;
        while (before.hasNext()) {
            if (!first) {
                System.out.print(", ");
            }
            System.out.print(before.next());
            first = false;
        }
        System.out.println("]");
        System.out.println("current list = " + list);

        try {
            list.iterator().remove();
        } catch (UnsupportedOperationException expected) {
            System.out.println("iterator remove unsupported");
        }
    }
}
~~~

Compile/run:

~~~bash
javac CopyOnWriteSnapshotDemo.java
java CopyOnWriteSnapshotDemo
~~~

Stdout:

~~~text
iterator snapshot = [A, B]
current list = [X, B, C]
iterator remove unsupported
~~~

**Why?**

1. The `before` iterator captures a reference to the array containing A, B at the time it is created.
2. `add("C")` and `set(0, "X")` create/publish a new list structure; the `before` iterator still uses the old array.
3. Calling `iterator().remove()` is not supported, because the snapshot iterator is not a view that edits the current structure.
4. There are no background threads, so stdout is deterministic. When multiple threads are involved, the iterator's snapshot property still applies, though when the iterator is created relative to updates is determined by the scheduler.

**Note:** `set(0, ...)` in `CopyOnWriteArrayList` is still a list update operation under the implementation's mechanism; the old iterator's snapshot does not change by itself.

### 8.2. Why Is CopyOnWriteArrayList Suitable for Read-Heavy, Write-Rare Workloads?

- Reads/iterations can run on the snapshot array without holding the writer lock for the duration of the traversal.
- Iteration reflects a stable structure, making it easy to reason about listener/configuration lists whose membership is effectively fixed per pass.
- Structural additions/removals/modifications typically require **copying the array**, increasing allocations and cost proportional to the list size.
- Frequent updates while the list is large cause write amplification, GC pressure, and temporary memory retention for old iterators still holding old arrays.
- Not suitable when mutations are very frequent or the data is very large and would have to be copied continuously.
- A snapshot iterator does not necessarily reflect a newly added listener immediately; the design must accept visibility delay until subsequent traversals.

### 8.3. A Snapshot Iterator Does Not Provide Deep Immutability

A snapshot array can hold **references to mutable objects**. Those referenced objects can continue to be modified through other references. Thus, the snapshot is stable in **membership and reference positions**, not in automatically freezing the internal state of each element.

This is an important distinction when a list holds mutable `Account` or `Session` objects. A traversal may see the same set of accounts, while the balance/attributes inside each account can change between reads.

## 9. Example 3 — Immutable Structural Copies Are Still Shallow (Java 17+)

Create `ShallowSnapshotDemo.java`:

~~~java
import java.util.ArrayList;
import java.util.List;

public class ShallowSnapshotDemo {
    static final class Box {
        int value;

        Box(int value) {
            this.value = value;
        }
    }

    public static void main(String[] args) {
        Box box = new Box(1);
        List<Box> original = new ArrayList<>();
        original.add(box);

        List<Box> snapshot = List.copyOf(original);

        original.add(new Box(2));
        box.value = 9;

        System.out.println(
            "snapshot size = " + snapshot.size()
        );
        System.out.println(
            "snapshot first value = " + snapshot.get(0).value
        );
        System.out.println(
            "original size = " + original.size()
        );
    }
}
~~~

Compile/run:

~~~bash
javac ShallowSnapshotDemo.java
java ShallowSnapshotDemo
~~~

Stdout:

~~~text
snapshot size = 1
snapshot first value = 9
original size = 2
~~~

`List.copyOf(original)` creates an unmodifiable list that is **structurally independent** of later add/remove changes on `original`. However, both lists still reference the same original `Box`; when `box.value` changes from 1 to 9, the snapshot reads 9.

To get a **deep snapshot** when needed, convert elements to an immutable value type (such as a record containing primitive/immutable fields) or perform a deep copy according to proper ownership. Avoid copying only the outer layer and claiming the entire object graph is immutable.

### 9.1. `List.copyOf` and Nulls

`List.copyOf` does not accept `null` elements. If the source contains null, it throws `NullPointerException`. Do not replace `new ArrayList<>(source)` with `List.copyOf(source)` in a system that allows nulls without checking the contract.

### 9.2. `Map.copyOf` / `Set.copyOf`

`Map.copyOf` and `Set.copyOf` also create unmodifiable collections with their own null restrictions. However, **just because the copy is complete and the result cannot be modified does not mean the source data was read in an atomic transaction** if writers were still modifying the source during the copy.

## 10. The Difference Between a Snapshot Copy and a Point-in-Time Consistent Snapshot

There are at least three levels that people all call a "snapshot":

1. **Membership/reference snapshot**: an iterator traverses a stable set of references, such as `CopyOnWriteArrayList.iterator()`.
2. **Structural copy snapshot**: there is a new `List`/`Map` that does not change when the source later adds/removes elements, assuming the copy completed successfully.
3. **Invariant-consistent snapshot**: all related fields/entries together describe a valid business state at **a single logical point in time**, without mixing old and new parts.

Level 1 and Level 2 **do not automatically imply Level 3**.

### 10.1. Why Might `new HashMap<>(concurrentMap)` Not Be Enough?

`ConcurrentHashMap` allows per-entry operations while writers remain active. A copy constructor may walk the source via traversal without holding a map-wide read transaction. The resulting copy is structurally independent, but it can contain a set of entries observed at different points in time.

A snapshot that is **immutable after creation** can still have been **inconsistent at creation time**. These are two different properties.

### 10.2. CopyOnWriteArrayList Can Have a Structural Snapshot With Mutable Data

If the list stores immutable records containing all data needed for reporting, the snapshot iterator is very strong for membership. However, if the list stores mutable objects referenced externally, those objects themselves can change. A snapshot of pointers does not equal a deep snapshot of all values.

## 11. Example 4 — Reading Two ConcurrentHashMap Keys Produces a State That Never Existed (Java 17+)

This example **forces a controlled interleaving** using latches to demonstrate the difference between per-key atomic operations and a multi-key atomic snapshot. It does not rely on timing or lucky scheduler behavior.

Initially A=60, B=40, total = 100. The writer changes A to 40 and then changes B to 60. The reader deliberately reads A **before** both updates and reads B **after** both updates:

~~~text
Initial       A = 60, B = 40, total = 100
Reader        reads A = 60
Writer        writes A = 40    -> temporary actual total = 80
Writer        writes B = 60    -> actual total = 100
Reader        reads B = 60
Reader        computes A+B = 120 (not the map state at any of the points above)
~~~

Create `NonAtomicSnapshotDemo.java`:

~~~java
import java.util.concurrent.ConcurrentHashMap;
import java.util.concurrent.CountDownLatch;

public class NonAtomicSnapshotDemo {
    public static void main(String[] args)
            throws InterruptedException {
        ConcurrentHashMap<String, Integer> map =
            new ConcurrentHashMap<>();
        map.put("A", 60);
        map.put("B", 40);

        CountDownLatch firstRead = new CountDownLatch(1);
        CountDownLatch writerDone = new CountDownLatch(1);

        Thread writer = new Thread(() -> {
            try {
                firstRead.await();
                map.put("A", 40);
                map.put("B", 60);
            } catch (InterruptedException ex) {
                Thread.currentThread().interrupt();
            } finally {
                writerDone.countDown();
            }
        }, "balance-writer");

        writer.start();

        int oldA = map.get("A");
        firstRead.countDown();
        writerDone.await();
        writer.join();

        int newB = map.get("B");

        System.out.println("mixed total = " + (oldA + newB));
        System.out.println(
            "final total = " + (map.get("A") + map.get("B"))
        );
    }
}
~~~

Compile/run:

~~~bash
javac NonAtomicSnapshotDemo.java
java NonAtomicSnapshotDemo
~~~

Stdout when there is no external interrupt:

~~~text
mixed total = 120
final total = 100
~~~

This result does not mean `ConcurrentHashMap`'s thread-safety is broken. Every individual `get`/`put` obeys its contract, but **a sequence of multiple get calls is not a transaction**. If you replace the two `get` calls with copying the map while a writer is active, there is no guarantee that the whole-map snapshot represents an atomic, consistent state.

This is a lesson about **the risk of aggregate reads**. Business data that requires the total to always equal 100 also needs **atomic updates of the balance pair** on the writer side; in the example, the writer performs two separate `put` calls, so in between there is also a temporary state with a total of 80. Both the read protocol and the write protocol must be designed if invariants must be preserved across multiple keys.

## 12. Creating a Consistent Snapshot Using the Same Lock

When all writers and readers follow a **shared lock**, a copy operation can run inside the same critical section without interference from writers. That is the difference compared to simply calling `List.copyOf` unlocked on a mutating source.

### 12.1. Synchronized Collections Still Require Locking During Iteration

`Collections.synchronizedList(...)` makes individual methods synchronized on the wrapper. However, when performing a multi-step traversal, **the caller must manually synchronize on that wrapper**:

~~~java
// Java 17+ pattern, not a standalone program.
List<String> shared =
    Collections.synchronizedList(new ArrayList<>());

List<String> snapshot;
synchronized (shared) {
    snapshot = List.copyOf(shared);
}

// Use the snapshot outside the lock.
for (String item : snapshot) {
    use(item);
}
~~~

The code requires importing `java.util.List`, `java.util.Collections`, and `java.util.ArrayList`. The key condition is that **all writers go through the same wrapper**, without retaining and modifying the underlying `ArrayList` externally. If a reference to the backing list leaks and a writer uses a different lock or no lock, consistency guarantees are still broken.

`Collections.unmodifiableList(shared)` is different: it only blocks modifications **through that view reference** and still reflects updates from `shared`. It does not create a snapshot. `List.copyOf` creates a structurally independent copy when the source is read safely.

### 12.2. Example 5 — Copying Under a Monitor and Keeping a Stable Snapshot (Java 17+)

Create `LockedSnapshotDemo.java`:

~~~java
import java.util.ArrayList;
import java.util.Collections;
import java.util.List;

public class LockedSnapshotDemo {
    public static void main(String[] args) {
        List<Integer> shared =
            Collections.synchronizedList(
                new ArrayList<>(List.of(1, 2))
            );

        List<Integer> snapshot;
        synchronized (shared) {
            snapshot = List.copyOf(shared);
        }

        shared.add(3);

        System.out.println("snapshot = " + snapshot);
        System.out.println("current = " + shared);
    }
}
~~~

Compile/run:

~~~bash
javac LockedSnapshotDemo.java
java LockedSnapshotDemo
~~~

Stdout:

~~~text
snapshot = [1, 2]
current = [1, 2, 3]
~~~

Because `snapshot` is taken inside `synchronized (shared)`, any concurrent update performed through the wrapper must wait for the lock to be released. Afterward, `shared.add(3)` modifies the source, while the snapshot's structure remains `[1, 2]`. The example uses immutable integers, so there is no issue of mutable elements changing after the snapshot is created.

**Performance:** Copying takes time and memory proportional to the number of elements; during the copy, writers must wait. If snapshots are needed very frequently on a large list, this pattern can cause contention; choose another solution depending on your SLA.

### 12.3. Can We Use ReadWriteLock?

Yes. A `ReadWriteLock` allows multiple readers to hold the read lock concurrently and prevents writers from holding the write lock while a reader is copying. However, **every modification** must use the write lock, and every snapshot reader must hold the read lock throughout reading the entire state. You must not lock only around each individual `get` and unlock between parts of the snapshot.

Pay attention to writer starvation, fairness, lock ordering, and the cost of holding locks for too long. If the data is an immutable snapshot, sometimes an `AtomicReference` is simpler.

## 13. Consistent Snapshots With Immutable State + AtomicReference

Another pattern is to create an **immutable object containing all state that must be consistent**, and then swap **a single reference** atomically. A reader only reads the reference once, so it always gets a complete, consistent state.

For example, two balances that always sum to 100:

~~~java
// Conceptual Java record structure:
record State(int a, int b) {}
AtomicReference<State> current =
    new AtomicReference<>(new State(60, 40));
~~~

Writers compute a new state and use `compareAndSet` or `updateAndGet` to swap the whole pair. Readers call `current.get()` once; the fields in the record are final primitives and do not change after creation.

### 13.1. Example 6 — Coherent Immutable Snapshot (Java 17+)

Create `AtomicStateSnapshotDemo.java`:

~~~java
import java.util.concurrent.atomic.AtomicReference;

public class AtomicStateSnapshotDemo {
    record State(int left, int right) {
        State {
            if (left < 0 || right < 0 || left + right != 100) {
                throw new IllegalArgumentException("Invalid state");
            }
        }
    }

    public static void main(String[] args)
            throws InterruptedException {
        AtomicReference<State> current =
            new AtomicReference<>(new State(60, 40));

        Thread first = new Thread(() ->
            current.updateAndGet(s ->
                new State(s.left() - 10, s.right() + 10)
            )
        );

        Thread second = new Thread(() ->
            current.updateAndGet(s ->
                new State(s.left() - 20, s.right() + 20)
            )
        );

        first.start();
        second.start();
        first.join();
        second.join();

        State snapshot = current.get();

        System.out.println("left = " + snapshot.left());
        System.out.println("right = " + snapshot.right());
        System.out.println(
            "snapshot total = "
                + (snapshot.left() + snapshot.right())
        );
    }
}
~~~

Compile/run:

~~~bash
javac AtomicStateSnapshotDemo.java
java AtomicStateSnapshotDemo
~~~

Stdout:

~~~text
left = 30
right = 70
snapshot total = 100
~~~

Regardless of the order in which the two threads update, each function decreases `left` and increases `right` by the same amount (10 or 20). `AtomicReference.updateAndGet` uses an atomic update mechanism and may **re-invoke the transformation function** under contention; the lambda in the example is pure, with no side effects other than constructing a new `State`. When both updates finish, `left = 60 - 10 - 20 = 30`, `right = 40 + 10 + 20 = 70`.

Every `State` record created satisfies the sum-100 invariant; readers hold **an immutable reference** and therefore cannot mix `left` from an old state with `right` from a new state as in the map example.

**Warning:** `record` only makes the record's fields `final`; if a record field is a reference to a `List` or a mutable object, the record is **not automatically deep-immutable**. Defensive copying is required for mutable fields.

### 13.2. Why Is AtomicReference Good for Low-Write Snapshots?

When writes create a new immutable object and swap the reference, readers can read quickly without holding a lock while traversing the retrieved state. However, every update must allocate a new state, increasing GC pressure. CAS can retry and the update function can run multiple times, so **do not place side effects** such as network calls or charging money inside the `updateAndGet` lambda.

If the state is very large or writes are extremely frequent, copying overhead will be high. Measure and consider partitioning, locking, or an appropriate ownership design.

## 14. Snapshots With Versioning and Retry: When to Use?

An advanced protocol is to read a **version**, read the data, and then read the version again; if the version changed, retry. Conceptual example:

~~~text
reader:
  v1 = version
  data = readAll()
  v2 = version
  if v1 != v2: retry
~~~

However, **this snippet is not yet sufficient to be a correct protocol**:

- If a writer can start updating before the version changes, a reader may observe a half-written state while both versions are equal.
- The version must **mark both the start and end of a write**, typically distinguishing an "in-progress" state from a "stable" state.
- Proper memory ordering is required to prevent reordering or hiding updates.
- Every writer must obey the protocol; if another writer modifies the data without updating the version, the snapshot can be corrupted.
- Infinite reader retries under contention cause starvation; a deadline, backoff, or fallback lock is needed.
- If the data consists of fields with data races, a hand-rolled seqlock in Java can violate the JMM even if the algorithm looks plausible.

Therefore, for critical business data, **prefer primitives with clear contracts**: a shared lock covering the entire snapshot or an immutable object published via `AtomicReference`. Only build a custom versioned snapshot after analyzing the memory model and testing thoroughly.

## 15. How Do Weak Iterators and Snapshots Affect Performance?

### 15.1. Iteration Cost of ConcurrentHashMap

Weak iteration avoids blocking writers across the entire map during traversal. It is useful when writers update continuously and readers can accept non-point-in-time results.

However, if readers repeatedly scan a large map to count or sort, the work still consumes CPU and causes extra allocations. If high-frequency metrics are needed, consider dedicated accumulators/counters with appropriate semantics; do not scan the whole map just because the concurrent iterator is "lock-free".

### 15.2. Cost of CopyOnWriteArrayList

For a list of N elements, structural additions/removals/modifications typically copy the array, with cost growing with N. Snapshot iterators are cheap to create and traverse without holding a writer lock for long, but old arrays can be retained in memory by long-lived iterators.

Good fit: sets of **listeners/subscribers** that rarely change but are iterated very frequently, where each listener reference is properly managed.

Poor fit: data queues changing thousands of times per second, very large lists, or continuous structural updates during traversal.

### 15.3. Copying a Snapshot Under a Lock

A snapshot copy under a lock typically costs O(N) for a list of N elements. If snapshots must be taken continuously, writers may be blocked during the copy. When rare ad-hoc reports are needed and consistency is mandatory, this remains a very clear and easy-to-verify solution.

### 15.4. Immutable Snapshots With CAS

Readers can be very cheap (read a single reference and work on immutable state). Writers bear the cost of building a new state, CAS, and retries under contention. If reads are very heavy and writes are infrequent, this option is worth considering.

**There is no "fastest collection" for every problem.** You must measure throughput, latency, allocation/GC, contention, long-lived data retention, iterator lifetime, and consistency requirements.

## 16. Common Misconceptions

### 16.1. Linearizability of One Operation Does Not Make Multiple Operations a Transaction

A `ConcurrentHashMap.put(key, value)` can have an atomic linearization point for **a single mapping**. However, reading A and then B are **two operations**; a writer can interleave between them. There is no linearizability guarantee for a multi-key snapshot unless a protocol provides it.

### 16.2. Weakly Consistent Does Not Mean Eventually Consistent in the Distributed-Systems Sense

A weakly consistent iterator describes **concurrent traversal within the same JVM**, not guarantees about replication, lag, eventual convergence, or multi-node distribution. It does not guarantee that "if you wait long enough, the current iterator will see every update". A single iterator may finish before an update arrives.

### 16.3. Snapshot Iterator Does Not Mean a Snapshot of the Entire Object Graph

`CopyOnWriteArrayList` captures array references; mutable elements inside can still change. To get a deep snapshot, you need immutable data or an appropriate deep defensive copy.

### 16.4. An Unmodifiable View Differs From an Independent Copy

~~~java
// Illustration, not a standalone program.
List<Integer> source = new ArrayList<>(List.of(1, 2));
List<Integer> view = Collections.unmodifiableList(source);
List<Integer> copy = List.copyOf(source);

source.add(3);

// view sees [1, 2, 3]; copy remains [1, 2].
~~~

`Collections.unmodifiableList` is a view that forbids modification **through the view**; it remains backed by the underlying list. `List.copyOf` is an unmodifiable copy with an independent structure. On a source being modified concurrently, **both iterating the view and copying** still require an appropriate synchronization protocol.

### 16.5. An Immutable Snapshot Can Be "Stale" Yet Still Correct

A snapshot created at t0 and used until t2 may be **stale** relative to the current state. That does not mean it is incoherent: it can accurately represent **a valid point in time**. Conversely, a recent read across multiple keys may be partially "fresher" while producing a combination that **never existed**.

Two independent requirements:

- **Freshness:** how recent is the data?
- **Consistency:** does the data belong to a single valid state at one logical point in time?

The application must decide whether it needs both or only one, along with appropriate deadlines and tolerances.

## 17. Testing Concurrent Iteration Properly

### 17.1. Do Not Hardcode Key Order Not Guaranteed by the API

The following test is invalid if the map is being updated concurrently:

~~~java
// WRONG expectation; illustration only.
assertEquals(List.of("A", "B", "C"),
             new ArrayList<>(concurrentMap.keySet()));
~~~

A weak iterator's result may miss or include new updates depending on timing; `ConcurrentHashMap`'s key order is also not insertion order. Tests should assert **invariants guaranteed by the contract**, rather than enforcing an arbitrary order.

### 17.2. Use CountDownLatch to Coordinate Key Moments

To prove that mixed-time data can be read, `NonAtomicSnapshotDemo` uses latches to force the reader to read the old A before the writer updates, and then read the new B afterward. That makes the output verifiable without relying on random races.

To test a snapshot iterator, create the iterator before updating and iterate after updating; `CopyOnWriteSnapshotDemo` is completely deterministic because no scheduler coordination is needed.

### 17.3. Test Classification

| Goal | Verification Check |
| --- | --- |
| Weak iterator does not fail-fast on update | Run traversal concurrently with updates; do not hardcode the exact set of seen elements |
| Correctness of each map operation | Test contracts of `put/get/compute/remove(key,value)` |
| Snapshot iterator fixes structure | Create iterator, update list, verify iterator still sees old contents |
| Snapshot element immutability | Mutate element via alias; verify need for deep copy |
| Coherent multi-field snapshot | Test invariants under concurrent writers |
| Cancellation during scan | Add deadlines/interrupts in realistic workflows |
| Performance | Measure read/write mix, copy allocations, GC, duration |
| No missed task processing | Use queue ownership/poll/ack, not just weak iteration |

A passing test run does not prove every interleaving is safe; you must reason from the API and the Java Memory Model. For workloads where missing an element has consequences, do not rely on weak iterators as a work-distribution mechanism.

## 18. Selection Checklist

| Practical Requirement | Recommended Approach |
| --- | --- |
| Map with many writers/readers, approximate scan is sufficient | `ConcurrentHashMap` weak iteration |
| Queue with multiple producers/consumers, each item needs one owner to process | `BlockingQueue.take` or `ConcurrentLinkedQueue.poll` |
| Very frequent listener list traversal, rare list changes | `CopyOnWriteArrayList` |
| Iteration with sorted keys under concurrent updates | `ConcurrentSkipListMap`, accepting weak consistency |
| List snapshot must be independent of the source | `List.copyOf` after safely reading the source |
| Need a multi-field snapshot that always preserves invariants | Shared lock or `AtomicReference<ImmutableState>` |
| Iterator must not see updates made after creation | Snapshot iterator, if shallow semantics are acceptable |
| Need very fresh and consistent state at a deadline | Dedicated transaction/snapshot protocol with clear linearization point |
| Mutable data source copied without a lock | **Do not** assume the copy is point-in-time |
| Must process every task completely, exactly once | Ownership/ack protocol, not traversal |

### Self-Check Questions

**1.** Iterating over `ConcurrentHashMap.entrySet()` while a writer adds keys without throwing `ConcurrentModificationException`. Can we conclude the iterator saw all new keys?

No. A weakly consistent iterator may observe some updates but does not promise to see all of them; the result is also not an atomic snapshot.

**2.** `CopyOnWriteArrayList.iterator()` is created before `add("C")`. Will that iterator see C?

No. The snapshot iterator uses the array as of the time the iterator was created, so subsequent structural updates are not reflected in that traversal.

**3.** Can you call `iterator.remove()` on a `CopyOnWriteArrayList` snapshot iterator?

No. It throws `UnsupportedOperationException`; the iterator is not a cursor for modifying the current array.

**4.** Does `List.copyOf` freeze all mutable objects inside its elements?

No. It copies the structure and keeps the references; to preserve deep data, you need immutable elements or a proper deep copy.

**5.** Both `ConcurrentHashMap.get("A")` and `get("B")` are thread-safe. Does that guarantee the pair of results is a snapshot from the same point in time?

No. A writer can change state between the two `get` calls; the example in this lesson produced a sum of 120 even though the actual states were 100, 80, and 100.

**6.** Why is `Collections.unmodifiableList` not a snapshot?

Because it is a view over the backing list and still reflects updates made through other references. It only forbids mutation through the view, rather than creating an independent copy.

**7.** `ConcurrentSkipListMap` has sorted key order. Does that make multi-key snapshots atomic?

No. Sorted traversal and point-in-time consistency are two different properties.

**8.** If you need a consistent snapshot of two variables that change together, what approaches can you use?

Use the same lock covering **both updates and snapshot reads**, or swap an immutable object containing both variables using an `AtomicReference`. Every writer/reader path must obey the protocol.

**9.** Can an immutable snapshot be stale?

Yes. Consistency says whether the snapshot represents a valid state; freshness says how close it is to the present. A consistent snapshot can be stale.

**10.** Should you use a weak iterator to distribute each task exactly once?

Do not rely solely on iteration. Use a **claim/ownership** mechanism via queue `poll/take` or atomic state and acknowledgment.

**11.** When does copy-on-write tend to cause performance issues?

When the list is large and structural updates are frequent. Each update may have to copy the array; old snapshots still held by iterators can also cause memory pressure.

**12.** Does calling `size()` and then iterating over `ConcurrentHashMap` guarantee the number of iterated items equals the size read earlier?

No, when concurrent updates occur. `size()` and the traversal are separate observations and do not form a transaction.

## 19. API References and Conclusion

Official JDK contracts should be checked against the Java version you are using:

- [ConcurrentHashMap — JDK 17](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/concurrent/ConcurrentHashMap.html)
- [ConcurrentLinkedQueue — JDK 17](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/concurrent/ConcurrentLinkedQueue.html)
- [ConcurrentSkipListMap — JDK 17](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/concurrent/ConcurrentSkipListMap.html)
- [CopyOnWriteArrayList — JDK 17](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/concurrent/CopyOnWriteArrayList.html)
- [Collections.synchronizedList — JDK 17](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/Collections.html)
- [List.copyOf — JDK 17](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/List.html)

**Key Takeaways:**

~~~text
Fail-fast iterator:
  Detects improper structural modifications on a best-effort basis.
  Not a thread coordination mechanism.

Weakly consistent iterator:
  Can traverse concurrently with updates.
  Does not guarantee seeing all updates.
  Not a point-in-time snapshot.

CopyOnWriteArrayList snapshot iterator:
  Holds the array structure as of iterator creation time.
  Does not see subsequent structural changes.
  Does not deep-copy mutable objects.

Coherent business snapshot:
  Requires a multi-field/multi-key protocol (shared lock, immutable state, etc.).
  Preserves invariants and provides a consistent point of observation.
~~~

**Conclusion:** A thread-safe collection can allow iterators to traverse concurrently with writers, but **thread-safety of individual operations** does not mean **consistency of an entire report**. Choose between weak iteration, structural snapshots, and business snapshots based on your tolerance for stale data, invariant requirements, and the update/copy cost of your system.
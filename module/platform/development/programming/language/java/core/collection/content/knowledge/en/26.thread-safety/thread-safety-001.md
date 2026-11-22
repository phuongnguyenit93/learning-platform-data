# Contention When Multiple Threads Read and Write a Collection

## 1. The Problem Starts with Shared State

A collection holds multiple related pieces of information: elements, size, positions or links between elements, and internal state used for searching or iteration. When multiple threads access it concurrently, a single operation at the source-code level may require multiple internal reads and writes.

For example, the intention to “increment the counter for code A by one” is often written as:

~~~java
int oldValue = counts.get("A");
counts.put("A", oldValue + 1);
~~~

These two lines do not automatically become an uninterruptible action. Another thread can read the same old value and also write the incremented result, causing one update to be lost.

For collections not designed for concurrent access, there are also structural and data-visibility issues. Even with thread-safe collections, errors can still occur in a **sequence of business operations** if individual steps are protected while the entire sequence is not.

This lesson distinguishes four questions:

1. Are individual methods safe to call concurrently?
2. Do multiple steps need to be treated as a single atomic operation?
3. Do reader threads see updates under a valid synchronization relationship?
4. Does iteration need to see live data, a snapshot, or a globally consistent state?

There is no single answer like “use a List” or “switch to a concurrent Map” that solves all of these questions at once.

## 2. Two Layers of Contention: Internal Data and External Logic

### 2.1. Contention on Improperly Synchronized Shared Data

Under the Java Memory Model, conflicting accesses to a shared variable, where at least one access is a write and they are not properly ordered by a happens-before relationship, form a data race. The happens-before relationship describes guarantees of ordering and visibility between actions. [Java Language Specification 17 — Happens-before Order](https://docs.oracle.com/javase/specs/jls/se17/html/jls-17.html#jls-17.4.5).

In an ordinary collection, reading internal fields while another thread modifies them without an appropriate protocol is not valid usage simply because each element is a Java reference.

Outcomes should not be predicted by imagining that all statements of all threads merely interleave as complete blocks. Compiler optimizations and the memory model also affect what a thread is allowed to observe.

### 2.2. Safe Methods Can Still Combine into an Incorrect Algorithm

A ConcurrentHashMap protects its own operations. However:

~~~java
int oldValue = map.get("item");
map.put("item", oldValue + 1);
~~~

still has a time window between the read and the write. Each method may be correct according to its own contract, but the overall requirement to “increment by one” is not expressed as an atomic update.

That is why we must distinguish between **data-structure safety** and **business-invariant correctness**. An algorithm can leave the collection's internals intact and still produce wrong results.

The demonstration program intentionally uses collections with thread-safe individual methods to reproduce contention at the operation-sequence layer. It does not need to corrupt an unprotected ArrayList and hope for a random failure.

## 3. ArrayList and HashMap Do Not Protect Concurrent Reads and Writes

Standard `ArrayList` and `HashMap` have no built-in synchronization for arbitrary concurrent use from multiple threads. Their documentation requires external synchronization when multiple threads access them and at least one thread modifies the structure. [Java SE 17 — ArrayList](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/ArrayList.html), [Java SE 17 — HashMap](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/HashMap.html).

The following example only illustrates incorrect usage, not a program to rely on for fixed stdout:

~~~java
// shared is the same ArrayList accessed by multiple threads without protection.
// Writer thread:
shared.add("new");

// Reader thread:
for (String value : shared) {
    consume(value);
}
~~~

Iteration failures or observed data that violates requirements may occur. Do not turn one specific symptom into a conclusion that every erroneous run must throw the same exception.

### Reading a Single Position Is Not Safe Just Because No Iterator Is Used

`get`, `size`, and `contains` all read state. While the source is changing without a proper contract, switching from a foreach loop to an index-based loop does not cure the contention.

Even keeping the size unchanged is not enough to claim all updates are safe. A `set` replacing an element reference or a `put` replacing a value is still a write to shared data; visibility guarantees and coordination appropriate for the application are still required.

### Read-Only Access Can Be Simpler If Writes Have Stopped

Multiple threads can safely read a structure that has finished being built, has been safely published, and is no longer modified. The “no longer modified” condition must cover every reference path capable of mutating the relevant parts.

If the elements inside are mutable objects, keeping the collection's structure unchanged still does not solve multiple threads reading and writing element state. The collection and the element objects are two separate layers to consider.

## 4. Lost Updates: Two Increments Leave Only One

Suppose a counter is currently `0`. Two threads execute the get–put sequence:

| Step | First Thread | Second Thread | Value in Map |
| --- | --- | --- | --- |
| 1 | Read `0` | | `0` |
| 2 | | Read `0` | `0` |
| 3 | Write `1` | | `1` |
| 4 | | Write `1` | `1` |

Neither write increments from `1` to `2` because both threads computed from the same old value. This is a lost update.

Switching the Map to ConcurrentHashMap gives `get` and `put` a concurrent-access contract, but it does not merge them into a single read–modify–write operation.

For a per-key counter, you can use:

~~~java
counts.merge("item", 1, Integer::sum);
~~~

`ConcurrentHashMap.merge` performs the per-key update atomically according to the class contract. If no value is present, it sets `1`; if one is already present, it merges it with `1`. [Java SE 17 — ConcurrentHashMap.merge](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/concurrent/ConcurrentHashMap.html#merge(K,V,java.util.function.BiFunction)).

Do not infer the same atomicity from calling `merge` on an arbitrary Map just because the `Map` interface declares that method. You must check the contract of the implementation in use.

The remapping function should be short, simple, and not modify other mappings in ways that violate the contract. A single-key atomic operation also does not automatically create a transaction across multiple keys, such as transferring a balance between two accounts.

## 5. Check-Then-Act: contains–add and size–get

### 5.1. contains Followed by add Can Insert Duplicates

Consider the requirement “add X only if it is not already present”:

~~~java
if (!list.contains("X")) {
    list.add("X");
}
~~~

If two threads both check before either adds, both see that `X` is absent, and then both add it. The result can be `[X, X]`.

This still happens with `Collections.synchronizedList` if you rely solely on the per-method lock. The lock for `contains` is released before `add` is called; another thread can step in between the two operations.

If you use a synchronized wrapper list and need this invariant, guard the entire block:

~~~java
synchronized (list) {
    if (!list.contains("X")) {
        list.add("X");
    }
}
~~~

All relevant call sites must follow the access protocol on the same wrapper object. Another thread modifying the backing list directly or using a different lock can break the protection.

For a uniqueness requirement, a Set suited for concurrent access may model the problem better. With `CopyOnWriteArrayList`, the `addIfAbsent` method provides the exact operation needed; do not split it into `contains` and `add` when that atomicity is required.

### 5.2. size Followed by get Can Use a Stale Index

~~~java
int lastIndex = list.size() - 1;
String value = list.get(lastIndex);
~~~

Between those two lines, another thread can remove an element or clear the list. `lastIndex` was computed from the prior state, whereas `get` reads the later state.

In the demonstration program, the synchronized wrapper list initially has one element. The reader thread obtains index `0`, the writer thread clears the list, and then the reader thread calls `get` and hits `IndexOutOfBoundsException`. Individual methods are still protected; the precondition between them changed.

How to handle this depends on the requirement: lock the whole sequence if an element must be read against the checked state, use a snapshot, or choose an appropriate atomic API. With concurrent queues, for instance, it is usually better to use a retrieval method with a clear contract like `poll` rather than separating `isEmpty` and `remove`.

## 6. A Lock Only Works When Every Party Uses the Same Protocol

A shared lock serves two important roles:

- Preventing protected sections from interleaving in a way that breaks invariants.
- Establishing a synchronization relationship so updates before a lock release are visible to the next acquisition of the same lock.

Locking writes while letting reads bypass the protocol does not automatically provide all required guarantees. Locking different objects also fails to protect the same region of state.

Example of a design error:

~~~text
thread 1 locks lockA and modifies shared
thread 2 locks lockB and reads shared
~~~

The two threads do not contend on the same lock, so their blocks can still run concurrently. Having the `synchronized` keyword on both sides is not enough.

A class managing a collection can use a private lock and expose access only through its own methods. Crucially, it must not leak the underlying collection reference for external code to mutate outside that protocol.

### Do Not Hold a Lock Longer Than Necessary

The atomic section should be wide enough to preserve invariants, while avoiding pulling in unnecessary work such as slow I/O, uncontrolled callbacks, or waiting on another thread that needs the same lock.

Do not place a “both threads must arrive” waiting point inside a lock that only one thread can enter. When the first thread holds the lock and waits, the second thread cannot enter to reach the waiting point: the program creates a situation where it cannot make progress.

In the demonstration, the fixed case places the barrier **before** the synchronized block. That way, startup coordination does not make the two threads wait on each other inside the mutual-exclusion region.

## 7. Iteration Is a Sequence of Accesses, Not a Single Call

A foreach loop creates and uses an `Iterator` across multiple steps. If the source is wrapped by `synchronizedList`, calling `iterator()` does not hold the lock for the entire loop.

Correct usage according to the wrapper's contract:

~~~java
synchronized (list) {
    for (String value : list) {
        consume(value);
    }
}
~~~

This snippet assumes `list` is the corresponding synchronized wrapper and `consume` adheres to the application's design.

The `synchronizedList` documentation requires synchronizing on the returned list itself when iterating via `Iterator`, `Spliterator`, or `Stream`. All accesses to the backing source must go through the wrapper to uphold the protocol. [Java SE 17 — Collections.synchronizedList](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/Collections.html#synchronizedList(java.util.List)).

With `synchronizedMap`, when iterating over `keySet`, `values`, or `entrySet`, you must lock on the wrapper Map per its contract—do not switch to locking on the view just obtained.

### Streams Do Not Automatically Lock the Source for the Entire Pipeline

`list.stream().filter(...).toList()` still has to traverse the source. Changing syntax from foreach to Stream does not turn a shared mutable source into a snapshot or a thread-safe source.

If a lock must be held across a sequential Stream traversal, the synchronized block must span the terminal operation's execution per the wrapper's policy. For slow processing or parallel execution, it is usually better to take a snapshot under the lock and process the snapshot outside the lock rather than holding the lock for the entire job.

Also avoid having a parallel pipeline run tasks that try to acquire a lock already held by the calling thread while it waits for them to finish. Choose a clear source strategy and ownership model before adding `parallelStream`.

## 8. ConcurrentModificationException Helps Detect Bugs, Not Replace Protection

Fail-fast iterators of collections like `ArrayList` may throw `ConcurrentModificationException` when they detect improper modification.

However, do not conclude:

~~~text
no exception thrown => all accesses are safe
~~~

Detection is only best-effort. A run without an exception may simply mean the thread schedule did not expose the bug, or an improper write pattern was not caught by that mechanism in the way assumed.

Nor does this exception prove that two threads were involved. Even on a single thread, modifying a collection directly in an unsupported way while an `Iterator` is traversing it can cause the iterator to detect the change.

Catching the exception and retrying in an infinite loop does not make a correct algorithm. You must decide whether the data should be read as a snapshot, as live state with a concurrent policy, or under a lock that preserves a consistent state.

## 9. Three Models for Reading Data During Updates

| Model | What the Reader Needs to Understand | Trade-off |
| --- | --- | --- |
| Read under a shared lock | Relevant state stays stable inside the lock region if all parties comply | May block other threads |
| Read a snapshot | The reader uses a fixed set of elements for the processing pass | Pays the cost of creating/holding a copy and accepts potentially stale data |
| Traverse a concurrent source | Updates can continue per the data structure's contract | Does not automatically provide a full atomic snapshot |

### 9.1. Creating a Snapshot Must Also Read a Valid Source

With a `synchronizedList`:

~~~java
List<String> snapshot;
synchronized (source) {
    snapshot = List.copyOf(source);
}
~~~

The copy is made inside the appropriate protected region. Afterward, the snapshot can be processed outside the lock if element guarantees and result publication are handled properly.

`List.copyOf` returns an unmodifiable list that does not reflect subsequent positional changes in the source; it does not accept null elements. If valid data can contain null, choose another appropriate copying and publication approach. [Java SE 17 — List.copyOf](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/List.html#copyOf(java.util.Collection)).

Do not take an `ArrayList` undergoing unsynchronized writes and call `copyOf` to “make it safe.” Before the copy exists, the copying operation itself still has to read the contended source.

### 9.2. CopyOnWriteArrayList Keeps a Snapshot for Its Iterator

The `Iterator` of `CopyOnWriteArrayList` uses the array state at the time the iterator was created. Subsequent updates do not make that iterator see new elements. [Java SE 17 — CopyOnWriteArrayList](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/concurrent/CopyOnWriteArrayList.html).

In the test case, the iterator is created from `[A, B]`, and then `C` is added to the collection. The iterator still collects `[A, B]`, while the current collection is `[A, B, C]`.

This approach is useful when reads vastly outnumber writes, but every update incurs the cost of copying the underlying array. Do not pick it as the default answer for a large dataset under continuous writes.

### 9.3. ConcurrentHashMap Does Not Freeze All Keys During Iteration

`ConcurrentHashMap` traversals are weakly consistent, matching concurrent updates per the class contract. They do not automatically create a global point-in-time snapshot. [Java SE 17 — ConcurrentHashMap](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/concurrent/ConcurrentHashMap.html).

An atomic per-key increment may be right, but summing multiple keys while other threads update them still requires checking the consistency requirements of your report. Do not conflate single-method atomicity with a transaction across the entire Map.

## 10. Data Publication, final, volatile, and Element Objects

### 10.1. Safe Publication Is Required for Readers to Use Constructed State

Building a collection and handing it to another thread requires a proper publication path, such as via `Thread.start`, a shared lock, a `volatile` reference, or data-transfer constructs with memory-consistency contracts.

Concurrent utilities specify happens-before relationships for handing off work or data between threads. [Java SE 17 — Memory consistency properties](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/concurrent/package-summary.html#MemoryVisibility).

The demonstration program initializes data before starting threads, uses barriers/latches to coordinate, and waits for threads to finish before printing results. It does not use `sleep` to guess that “the other thread has probably finished writing.”

### 10.2. final Does Not Make a Collection Immutable

~~~java
final List<String> names = new ArrayList<>();
names.add("A");
~~~

This is valid code. `final` prevents reassigning the `names` variable; it does not forbid calling `add`, `clear`, or mutating element state.

Do not treat a `final` field holding a collection as a substitute for a data-modification contract. Consider what state can still change after the object is constructed and who is allowed to change it.

### 10.3. volatile on a Reference Does Not Lock Collection Contents

A `volatile List<String>` field can be used to publish swapping the entire reference to a new snapshot. However, it does not turn `add`/`get` calls on the same `ArrayList` into serialized operations.

The right pattern is to prepare a data version that will no longer be mutated and then publish the new reference. If multiple parties still mutate the same referenced collection, a separate mechanism is needed for those mutations.

### 10.4. A Thread-Safe Map Does Not Protect an ArrayList Stored as a Value

An example that requires caution:

~~~java
map.computeIfAbsent(key, ignored -> new ArrayList<>()).add(value);
~~~

If `map` is a `ConcurrentHashMap`, establishing the mapping follows the Map's atomic contract. Yet the returned `ArrayList` object can still have `add` called concurrently by multiple threads. The Map does not lock future actions on the value.

You can choose an appropriate value structure, a dedicated lock by design, or replace values with new data objects in an atomic update. Ownership and inner state must be clearly defined, not just the outer Map's class.

## 11. Reproducing Bugs with Coordinated Scheduling, Not Luck

An incorrect multithreaded program does not necessarily fail on every run. Running a huge loop and waiting for “different numbers to show up occasionally” can be hard to learn from and hard to test.

The demonstration uses two mechanisms:

- `CyclicBarrier` forces both threads to finish reading/checking before allowing them to write.
- `CountDownLatch` forces the clear operation to happen after the size is read but before the element is read.

These tools create a valid interleaving schedule that exposes the gap between individual methods. They do not make `get–put` atomic; they only make the buggy schedule reliably reproducible. [Java SE 17 — CyclicBarrier](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/concurrent/CyclicBarrier.html), [Java SE 17 — CountDownLatch](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/concurrent/CountDownLatch.html).

Every test case waits for both threads to finish and propagates errors from worker threads back to the calling thread. Otherwise, the main thread might print figures before tasks finish or see seemingly valid output while a thread died with an exception.

The wait timeouts in the helpers exist to detect an example that fails to make progress, not to determine business ordering. Ordering is created by the barriers and latches, not by CPU speed or an estimated `sleep` duration.

## 12. Full Demonstration Program

Save the following code as **CollectionRaceDemo.java**. The program uses Java 17 APIs and the standard library.

Three logic-bug cases are constructed on collections whose individual methods are thread-safe: a `get–put` lost update, a `contains–add` duplicate insertion, and a `size–get` stale index. The program does not try to trigger an internal data race on a plain `ArrayList` and assert a random stdout.

The fixed cases protect the entire `check–add` sequence with a lock and use `ConcurrentHashMap.merge` for per-key increments. The `addIfAbsent` case uses the proper `CopyOnWriteArrayList` operation. The snapshot and mutable-element cases verify the remaining guarantee boundaries.

~~~java
import java.util.ArrayList;
import java.util.Collections;
import java.util.Iterator;
import java.util.List;
import java.util.concurrent.ConcurrentHashMap;
import java.util.concurrent.CopyOnWriteArrayList;
import java.util.concurrent.CountDownLatch;
import java.util.concurrent.CyclicBarrier;
import java.util.concurrent.TimeUnit;
import java.util.concurrent.atomic.AtomicReference;

public class CollectionRaceDemo {
    @FunctionalInterface
    interface CheckedTask {
        void run() throws Exception;
    }

    private static Thread taskThread(CheckedTask task, AtomicReference<Throwable> failure) {
        return new Thread(() -> {
            try {
                task.run();
            } catch (Throwable problem) {
                failure.compareAndSet(null, problem);
            }
        });
    }

    private static void runPair(CheckedTask first, CheckedTask second) throws Exception {
        AtomicReference<Throwable> failure = new AtomicReference<>();
        Thread a = taskThread(first, failure);
        Thread b = taskThread(second, failure);
        a.start();
        b.start();
        a.join(8000);
        b.join(8000);
        if (a.isAlive() || b.isAlive()) {
            a.interrupt();
            b.interrupt();
            throw new AssertionError("Tasks did not finish");
        }
        if (failure.get() != null) {
            throw new AssertionError("Task failed", failure.get());
        }
    }

    private static void await(CountDownLatch latch) throws InterruptedException {
        if (!latch.await(5, TimeUnit.SECONDS)) {
            throw new AssertionError("Timed out at latch");
        }
    }

    public static void main(String[] args) throws Exception {
        ConcurrentHashMap<String, Integer> counts = new ConcurrentHashMap<>();
        counts.put("item", 0);
        CyclicBarrier bothRead = new CyclicBarrier(2);
        CheckedTask splitIncrement = () -> {
            int oldValue = counts.get("item");
            bothRead.await(5, TimeUnit.SECONDS);
            counts.put("item", oldValue + 1);
        };
        runPair(splitIncrement, splitIncrement);
        System.out.println("lost-update=" + counts.get("item"));

        List<String> separate = Collections.synchronizedList(new ArrayList<>());
        CyclicBarrier bothChecked = new CyclicBarrier(2);
        CheckedTask checkThenAdd = () -> {
            boolean absent = !separate.contains("X");
            bothChecked.await(5, TimeUnit.SECONDS);
            if (absent) {
                separate.add("X");
            }
        };
        runPair(checkThenAdd, checkThenAdd);
        System.out.println("separate-check-add=" + separate);

        List<String> locked = Collections.synchronizedList(new ArrayList<>());
        CyclicBarrier ready = new CyclicBarrier(2);
        CheckedTask lockedAdd = () -> {
            ready.await(5, TimeUnit.SECONDS);
            synchronized (locked) {
                if (!locked.contains("X")) {
                    locked.add("X");
                }
            }
        };
        runPair(lockedAdd, lockedAdd);
        System.out.println("locked-check-add=" + locked);

        ConcurrentHashMap<String, Integer> atomicCounts = new ConcurrentHashMap<>();
        CheckedTask atomicIncrement = () -> {
            for (int i = 0; i < 1000; i++) {
                atomicCounts.merge("item", 1, Integer::sum);
            }
        };
        runPair(atomicIncrement, atomicIncrement);
        System.out.println("atomic-merge=" + atomicCounts.get("item"));

        List<String> shrinking = Collections.synchronizedList(
                new ArrayList<>(List.of("A")));
        CountDownLatch sizeRead = new CountDownLatch(1);
        CountDownLatch cleared = new CountDownLatch(1);
        AtomicReference<String> readOutcome = new AtomicReference<>();
        runPair(() -> {
            int index = shrinking.size() - 1;
            sizeRead.countDown();
            await(cleared);
            try {
                readOutcome.set(shrinking.get(index));
            } catch (IndexOutOfBoundsException expected) {
                readOutcome.set("IndexOutOfBoundsException");
            }
        }, () -> {
            await(sizeRead);
            shrinking.clear();
            cleared.countDown();
        });
        System.out.println("size-then-get=" + readOutcome.get());

        List<String> source = Collections.synchronizedList(
                new ArrayList<>(List.of("A", "B")));
        List<String> snapshot;
        synchronized (source) {
            snapshot = List.copyOf(source);
        }
        source.add("C");
        System.out.println("snapshot=" + snapshot);
        System.out.println("source-after-snapshot=" + source);

        CopyOnWriteArrayList<String> copyOnWrite =
                new CopyOnWriteArrayList<>(List.of("A", "B"));
        Iterator<String> iterator = copyOnWrite.iterator();
        copyOnWrite.add("C");
        List<String> seen = new ArrayList<>();
        iterator.forEachRemaining(seen::add);
        System.out.println("copy-on-write-iterator=" + seen);
        System.out.println("copy-on-write-current=" + copyOnWrite);

        CopyOnWriteArrayList<String> unique = new CopyOnWriteArrayList<>();
        CheckedTask addIfAbsent = () -> unique.addIfAbsent("X");
        runPair(addIfAbsent, addIfAbsent);
        System.out.println("add-if-absent=" + unique);

        StringBuilder sharedItem = new StringBuilder("seed");
        List<StringBuilder> objectSnapshot = List.copyOf(List.of(sharedItem));
        sharedItem.append("!");
        System.out.println("shallow-snapshot-element=" + objectSnapshot.get(0));
    }
}
~~~

Compile and run:

~~~shell
javac --release 17 -encoding UTF-8 CollectionRaceDemo.java
java CollectionRaceDemo
~~~

Exact stdout:

~~~text
lost-update=1
separate-check-add=[X, X]
locked-check-add=[X]
atomic-merge=2000
size-then-get=IndexOutOfBoundsException
snapshot=[A, B]
source-after-snapshot=[A, B, C]
copy-on-write-iterator=[A, B]
copy-on-write-current=[A, B, C]
add-if-absent=[X]
shallow-snapshot-element=seed!
~~~

The code was compiled with `--release 17` and run on JDK 24.0.2. The compiler flag checks Java 17 language/API level; the run was verified on the stated JVM.

Result explanation:

| Output Line | What Was Tested |
| --- | --- |
| `lost-update=1` | Two threads both read 0, both compute 1 and write; one increment is lost |
| `separate-check-add=[X, X]` | `contains` and `add` are individually safe, but the gap between them allows two additions |
| `locked-check-add=[X]` | The entire check–add sequence is protected by the same lock |
| `atomic-merge=2000` | Two threads, each performing 1000 atomic per-key updates |
| `size-then-get=IndexOutOfBoundsException` | The index computed before the list was cleared is no longer valid at `get` |
| `snapshot=[A, B]` | The positional copy preserves the data from the copy pass |
| `source-after-snapshot=[A, B, C]` | The source can continue changing afterward |
| `copy-on-write` group | The iterator holds a snapshot, differing from the current collection state |
| `add-if-absent=[X]` | Two threads use the proper duplicate-free operation of `CopyOnWriteArrayList` |
| `shallow-snapshot-element=seed!` | Structural copying does not clone the `StringBuilder` inside |

These results demonstrate the coordinated schedules and the APIs used. They do not prove that every algorithm using these classes is safe, nor are they a performance benchmark.

## 13. Choosing an Approach Based on the Invariant to Preserve

| Need | Design Direction |
| --- | --- |
| Data is read-only after construction | Publish safely and prevent any invalid updates |
| Multiple operations must observe the same state | A locking protocol covering the full invariant or an appropriate atomic API |
| Independent per-key updates | `ConcurrentHashMap` with `merge`/`compute`/`putIfAbsent` per its contract |
| Heavy iteration, rare updates, and snapshots are acceptable | Consider `CopyOnWriteArrayList` or immutable data versions |
| Slow processing without holding a lock for long | Copy a valid source under the lock, then process outside the lock |
| Passing elements between producers and consumers | A queue structure with an appropriate concurrent/blocking contract |

Choosing a data structure should start from what must always remain true about the data, not merely from the number of threads. A concurrent collection can support thousands of safe individual calls yet fail to preserve a rule spanning multiple collections if that rule is not explicitly enforced.

With external locking, document which lock protects which state. With snapshots, document when the snapshot is taken and the copy depth. With concurrent structures, check the atomicity scope and iteration policy. This information prevents future maintainers from accidentally using an access path that breaks the protocol.

## 14. Practice Exercises with Answers

### Exercise 1 — ConcurrentHashMap Still Loses Increments

Two threads both run `map.put(k, map.get(k) + 1)`. Why does the Map not corrupt, yet the counter can still be wrong?

**Answer:** `get` and `put` have individual contracts, but the sequence as a whole is not atomic. Both threads can read the same old value and then write the same result. Use an atomic per-key update such as `merge` if it fits the requirement.

### Exercise 2 — Is synchronizedList Enough for contains–add?

A list is wrapped with `synchronizedList`. Two threads check that `X` is absent and then add `X`. Why can the list still end up containing two `X`s?

**Answer:** The lock of `contains` does not extend to `add`. Both threads can check before either adds. Protect the entire block with the same lock, or choose a structure/API that provides the single operation needed.

### Exercise 3 — The synchronized Keyword Is on Both Sides

The writer thread locks `lockA`, and the reader thread locks `lockB`, while both access the same list. Is that sufficient protection?

**Answer:** No. Two independent locks do not exclude each other and do not establish a shared protocol for that data. All related accesses must follow the same designed protection mechanism.

### Exercise 4 — No ConcurrentModificationException

One run of reading and writing an `ArrayList` throws no exception. Can we conclude that an index-based loop or the current schedule makes it safe?

**Answer:** No. Fail-fast only detects issues on a best-effort basis and does not replace synchronization. Not seeing an error in one run does not prove compliance with the memory contract or business invariants.

### Exercise 5 — Copying to Be Safe

Can you call `List.copyOf` on an `ArrayList` undergoing unsynchronized modifications and consider all risks resolved?

**Answer:** No. The copy process itself must still read a valid source. You must keep the source stable with an appropriate protocol while creating the snapshot, and then publish the result properly. A structural copy can still share element objects.

### Exercise 6 — Does a volatile List Lock add?

A `volatile` field points to an `ArrayList`. Are two threads calling `add` on that `ArrayList` automatically serialized?

**Answer:** No. `volatile` on a reference does not turn the collection's contents into a locked region. It can be suitable for publishing a new data version that will not be mutated further; updates to the same object still require their own mechanism.

### Exercise 7 — Values Inside a Concurrent Map

Why does `concurrentMap.computeIfAbsent(k, x -> new ArrayList<>()).add(v)` not guarantee that multiple threads adding to the value list is safe?

**Answer:** The Map protects creating/inserting the mapping per its contract, but the `ArrayList` stored as the value is still a separate object that is not thread-safe on its own. You must design an appropriate value structure or update protocol.

### Exercise 8 — Reading a Snapshot or the Latest Data?

An `Iterator` of `CopyOnWriteArrayList` is created before `C` is added. Why does it still return `A`, `B`? If a report must reflect a newer consistent state, is it enough to simply claim “the collection is thread-safe”?

**Answer:** The iterator holds a snapshot from the time of creation, so `C` is not in that pass. Thread safety alone does not define the freshness and consistency requirements of a report. You must choose the read timing, lock scope, or snapshot version that matches the requirement.

## 15. How to Spot Contention in Real Code

Find where state is shared, then mark all read–check–write sequences or traversals that depend on multiple reads. For each sequence, ask what can change between steps and which mechanism preserves the invariant.

Next, check access paths: is there any path that mutates the backing collection directly, uses a different lock, retains a value object to mutate it externally, or publishes a reference before the state is ready? Do not inspect only the single method being edited while ignoring other parties sharing the data.

The key takeaway of this lesson is: **a thread-safe collection protects only what its contract promises; the algorithm must still protect every sequence of operations that the business logic treats as one action.** Combining clear ownership, proper publication, atomic operations, and an appropriate traversal policy is what produces a reliable multithreaded read–write design.

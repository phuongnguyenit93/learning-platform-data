# size, Iteration, and Bulk Operations Under Concurrent Updates

A concurrent map or set allows threads to continue reading, inserting, and removing without stopping the entire structure for every operation. In return, a measurement or multi-element traversal does not automatically observe **a single consistent version of all data**.

For example, a monitoring dashboard only needs the approximate current number of connections. A reconciliation report, however, might require every row to belong to the same cut-off point in time. Those two requirements demand different consistency levels even when reading from the same `ConcurrentHashMap`.

This lesson distinguishes three tasks:

1. **Counting or querying aggregate state:** `size`, `mappingCount`, `isEmpty`, `containsValue`.
2. **Iterating and reading multiple mappings/elements:** iterators, views, `forEach`, streams.
3. **Bulk processing:** both write operations such as `putAll`, `clear`, `replaceAll`, and `ConcurrentHashMap`'s own `forEach`/`search`/`reduce` family.

Key concepts:

- **Transient observation:** information read while the structure can still change.
- **Weak consistency:** a policy that allows traversal concurrently with updates, without providing a monolithic snapshot of the source.
- **Consistent snapshot:** data determined to belong to a single shared state under a snapshot protocol.
- **Quiescent source:** no relevant updates occur during the reading window, and writer results have been properly published.
- **Per-element/per-key atomicity:** the guarantee of an individual operation does not automatically extend into a guarantee for the entire collection.

`ConcurrentHashMap` is used as the primary example. `ConcurrentSkipListMap`, `ConcurrentSkipListSet`, and sets backed by `ConcurrentHashMap` share similar traits regarding data changing during reads, though each class's specific contract must still be checked.

## 1. size Is an Observation, Not a Reservation

`size()` queries the number of mappings/elements. When other threads are still adding or removing entries, the observed count can change during or immediately after the measurement.

The `ConcurrentHashMap` documentation notes that aggregate status methods such as `size`, `isEmpty`, and `containsValue` reflect transient state when updates occur, making them more suitable for monitoring or estimation than for controlling a protocol that requires strong invariants. [Java 17: ConcurrentHashMap](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/concurrent/ConcurrentHashMap.html)

The following illustration assumes `sessions` is a concurrent map:

~~~java
if (sessions.size() < 100) {
    sessions.put(sessionId, session);
}
~~~

This does not guarantee at most `100` sessions. Two threads can both observe `99` and then insert two different keys.

Notice an important point: this bug still exists even if each thread's `size` call returns an exact count at the moment of reading. The problem lies in the gap between **checking for space** and **claiming space**. Measurement accuracy and decision atomicity are two separate questions.

To enforce a strict limit, use a reservation protocol or guard both the check and the insertion together. Do not treat `size` as a "ticket" that multiple threads can consume concurrently.

### 1.1. mappingCount Does Not Increase Consistency

`ConcurrentHashMap.size` returns an `int`; if the number of mappings exceeds `Integer.MAX_VALUE`, the result is capped at that value. `mappingCount` returns a `long`, which is a better numeric range for very large maps, yet the documentation still describes the result as an estimate when concurrent insertions/removals occur. [Java 17: size and mappingCount](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/concurrent/ConcurrentHashMap.html#mappingCount())

Switching from `size` to `mappingCount` does not turn a query into a reservation or a whole-map lock.

### 1.2. isEmpty Does Not Prove Work Has Finished

A single `isEmpty()` call returning `true` does not prove that new work will not be added immediately afterward. If the application needs to know that all work is complete, it must also have rules for producers, when intake stops, in-flight tasks, and how completion is awaited.

For instance, "the queue/map is currently empty" differs from "all producers have stopped and no tasks are still executing." A query on a collection only answers for the data it manages.

### 1.3. Not Every size Has the Same Cost

Do not assume from familiarity with `ArrayList.size` or `HashMap.size` that every concurrent collection has a cheap `size`. `ConcurrentSkipListSet` explicitly states that counting is not a constant-time operation and may be inaccurate if the set is modified while traversing to count. [Java 17: ConcurrentSkipListSet](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/concurrent/ConcurrentSkipListSet.html)

If counts need to be queried frequently, consider both the consistency semantics and the cost of the specific class in use.

## 2. A Safe Traversal Is Not a Snapshot

Weakly consistent iterators are designed to proceed alongside other operations. They do not use `ConcurrentModificationException` like standard fail-fast iterators to report updates permitted by the concurrency policy. [Java 17: Concurrent Collections](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/concurrent/package-summary.html#ConcurrentCollections)

However, you should not interpret this as either extreme:

- "It is always an exact snapshot at the moment the iterator was created."
- "Every new update is guaranteed to appear during the traversal."

Read the class contract. For `ConcurrentHashMap`, elements returned by a traversal may reflect different points in time since traversal began. Seeing a value for one key does not force the value seen for another key to belong to the same common version.

### 2.1. Combining Individually Valid Observations Can Produce a Composite That Never Existed

Suppose there are two keys, P and Q, both initially `0`. A writer updates them in order:

~~~text
P=0, Q=0
P=1, Q=0
P=1, Q=1
~~~

A traversal might read P before the update, and then read Q after both updates finish:

~~~text
Traversal observes: P=0, Q=1
~~~

Each value was read from valid data for its respective key, yet the pair `P=0, Q=1` never appeared in any of the three actual states above.

This is a critical limitation for aggregate reporting: results are not merely "slightly stale," they can also **mix points in time** across rows. The complete program below reproduces that exact schedule regardless of which key is visited first.

### 2.2. Key Ordering and Data Timestamp Are Separate Properties

`ConcurrentSkipListMap` maintains key ordering, but its iterators and spliterators are still weakly consistent. Reading keys in ascending order does not make all values belong to a single point in time. Multi-element operations do not automatically become whole-map atomic either. [Java 17: ConcurrentSkipListMap](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/concurrent/ConcurrentSkipListMap.html)

Likewise, sorting results after a traversal only creates presentation order. It does not turn back time to synchronize the reads.

### 2.3. Views Live With the Source

`keySet`, `values`, and `entrySet` are views into the map, not snapshots merely because they are assigned to a variable.

Storing `Set<K> keys = map.keySet()` does not freeze the key set at that assignment line. Subsequent use of the view must still be understood in terms of the backing source and its traversal policy.

If you hold an iterator, do not assume you can share that single iterator instance across multiple threads just because the source is a concurrent map. In `ConcurrentHashMap`, an iterator is designed to be used by one thread at a time.

## 3. Bulk Writes Are Not Whole-Map Transactions

The word "all" describes the intended scope of work, not an atomic boundary.

| Operation | What to understand when concurrent readers/writers exist |
|---|---|
| `putAll(source)` | Readers may observe some mappings inserted before the rest. |
| `clear()` | Does not create an exclusive empty window for subsequent operations; updates may interleave. |
| `replaceAll(function)` | Not all values transition to the new version in a single transaction. |
| `removeIf` on a view or set | Multiple individual checks/removals do not equate to a single monolithic decision across all elements. |
| `addAll` on a concurrent set | Does not force readers to see only the state before or after the entire batch of additions. |

Each class's contract governs the details. For example, `ConcurrentSkipListSet` explicitly states that bulk operations such as `addAll`, `removeIf`, and `forEach` are not guaranteed to be performed atomically. [Java 17: Bulk Operations on ConcurrentSkipListSet](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/concurrent/ConcurrentSkipListSet.html)

### 3.1. putAll Involves Both a Source and a Destination

When `destination.putAll(source)` runs, you must ask two independent questions:

1. How does the destination expose the batch update to other readers?
2. Can the source be safely read while another thread modifies it?

Making the destination a `ConcurrentHashMap` does not make an unsynchronized `HashMap` source safe while it is being mutated elsewhere. If the source is also a concurrent map, reading the source can still mix points in time. Destination thread-safety does not upgrade the source's semantics into a snapshot.

### 3.2. clear Is Not a Data-Closing Barrier

After `clear`, another thread can `put` an entry right before the caller's next `isEmpty` check. When `clear` and writes overlap, do not use `clear` as a "wipe everything and forbid new entries" protocol.

If the requirement is to close a registry and then clear it, you need a closed state and coordination with registrants. Clearing contents and transitioning the registry's lifecycle are two separate concerns that must be modeled explicitly.

### 3.3. replaceAll Can Leave Partial Results

If the remapping function returns new values for several keys and then throws an exception on the next key, the earlier updates are not automatically rolled back.

In addition, the default implementation of `ConcurrentMap.replaceAll` may retry under contention and invoke the function multiple times for a single key. Do not use it as a place to trigger side effects under the assumption that the function is called at most once per key. [Java 17: ConcurrentMap.replaceAll](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/concurrent/ConcurrentMap.html#replaceAll(java.util.function.BiFunction))

If an entire dataset must transition from an old version to a new version together, building a new instance and publishing it via a versioning protocol may be more appropriate than replacing mappings one by one.

## 4. ConcurrentHashMap's Own Bulk Operations

`ConcurrentHashMap` provides dedicated bulk operations that accept an additional `parallelismThreshold` parameter. They are designed to be usable while the map is being updated, though results are not automatically atomic across the entire map.

The three main families are:

- `forEach`: processes the visited keys, values, key-value pairs, or entries.
- `search`: finds a non-`null` result from a search function.
- `reduce`: combines results into an aggregate value.

Variants accept keys, values, key-value pairs, or entries. There is no requirement to use these methods for every read; choose them when aggregate semantics over a changing source are appropriate.

### 4.1. Parallelism Threshold Is an Execution Choice, Not a Data Lock

`Long.MAX_VALUE` disables parallel splitting for these methods. A threshold of `1` enables aggressive splitting; intermediate thresholds use the estimated size to decide how to split. That does not mean a fixed number of threads is always used.

Parallel computations use `ForkJoinPool.commonPool`. This pool is a shared resource; long-blocking functions or I/O inside callbacks can affect other work. [Java 17: ForkJoinPool.commonPool](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/concurrent/ForkJoinPool.html#commonPool())

Keep two things separate:

- **Sequential vs. parallel:** whether one or multiple threads execute the traversal.
- **Consistency:** whether observations come from a single source state.

A `forEach(Long.MAX_VALUE, ...)` call can still have its source modified by other writers while running. Disabling parallelism does not acquire a whole-map lock.

### 4.2. forEach Does Not Protect a Destination Collection Written by the Callback

Analyze this example:

~~~java
List<String> lines = new ArrayList<>();
map.forEach(1L, (key, value) -> lines.add(key + "=" + value));
~~~

This is an unsafe snippet, assuming `map` is a `ConcurrentHashMap` and the list types are imported. The callback can run concurrently across multiple tasks; the external `ArrayList` is not automatically protected.

You can use a collector with an appropriate contract such as `ConcurrentLinkedQueue`, and then sort after the bulk operation completes. That solves the destination-writing issue, though it still does not turn a concurrently updated source into a consistent snapshot.

Entries passed to entry-based bulk operations do not support `setValue`. To conditionally modify mappings, use an update API with the appropriate contract rather than treating bulk-operation entries as live transactional handles.

### 4.3. search Returns One Result, Not the Smallest or Newest

The search function returns `null` to indicate no match at that element. Once a non-`null` result is found, further processing is curtailed/stopped according to the method's mechanism; other tasks may already have started.

Therefore:

- When multiple matches exist, it does not automatically pick the smallest key.
- Do not use the search function to perform a side effect assuming it runs only once.
- A `null` result reflects the data observed by the search process, not a proof that no matching element existed at any point during updates.
- A found result may already have been modified or removed from the map before the caller uses it.

If you need "find and claim exclusively," you must add a conditional operation or a work-claiming model; `search` is only the observation step.

### 4.4. reduce Requires an Appropriate Combiner

Because `ConcurrentHashMap` has no fixed traversal order and can be partitioned differently, the reducer function must be associative and commutative by contract so the result does not depend on partitioning or order.

Commonly valid examples over a well-defined domain are non-overflowing integer addition, counting, or finding extrema. Order-dependent string concatenation, sequential subtraction, or functions relying on mutating external variables do not automatically satisfy this requirement.

For object-returning variants, `null` signals no contributing result. A transformer function can return `null` to filter out elements. For primitive variants, choose the proper identity element: `0` for sum, the maximum domain value for min, and the minimum domain value for max.

An **identity element** is a value that leaves the other value unchanged when combined with it. Do not pass `100` as the basis for addition hoping it will only be added once when execution splits into multiple parts.

### 4.5. A Safe Aggregation May Still Not Belong to a Single Point in Time

A `reduce` may read an old value for one key and a new value for another. Its result reflects per-mapping visibility relationships, not necessarily the sum of the entire map at one instant. This limitation is documented in the bulk operation contract. [Java 17: Bulk Operation Consistency](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/concurrent/ConcurrentHashMap.html)

For monitoring metrics, that may be acceptable. For balance reconciliation or closing reports, a stronger protocol is required.

## 5. Verification Program

The file `ConcurrentObservationDemo.java` runs standalone using Java 17 APIs. It was compiled with `javac --release 17` and run on OpenJDK Zulu 24.0.2. Do not treat this as a claim that it was executed on a Java 17 JVM.

The aggregations at the start of the program use a source with no writers to verify APIs and clear stdout. Later sections actively orchestrate update schedules using latches/barriers rather than predicting outcomes from a random race.

~~~java
import java.util.ArrayList;
import java.util.Collections;
import java.util.List;
import java.util.Map;
import java.util.TreeMap;
import java.util.concurrent.ConcurrentHashMap;
import java.util.concurrent.ConcurrentLinkedQueue;
import java.util.concurrent.ConcurrentSkipListSet;
import java.util.concurrent.CountDownLatch;
import java.util.concurrent.CyclicBarrier;
import java.util.concurrent.TimeUnit;
import java.util.concurrent.atomic.AtomicInteger;
import java.util.concurrent.atomic.AtomicReference;

public class ConcurrentObservationDemo {
    static void await(CountDownLatch signal) {
        try {
            if (!signal.await(5, TimeUnit.SECONDS)) {
                throw new AssertionError("Signal timed out");
            }
        } catch (InterruptedException ex) {
            Thread.currentThread().interrupt();
            throw new AssertionError("Interrupted", ex);
        }
    }

    static Thread launch(String name, Runnable action,
                         AtomicReference<Throwable> error) {
        Thread thread = new Thread(() -> {
            try {
                action.run();
            } catch (Throwable ex) {
                error.compareAndSet(null, ex);
            }
        }, name);
        thread.setDaemon(true);
        thread.start();
        return thread;
    }

    static void finish(Thread thread, AtomicReference<Throwable> error)
            throws InterruptedException {
        thread.join(5000);
        if (thread.isAlive()) {
            thread.interrupt();
            throw new AssertionError("Thread timed out: " + thread.getName());
        }
        if (error.get() != null) {
            throw new AssertionError("Thread failed", error.get());
        }
    }

    public static void main(String[] args) throws Exception {
        ConcurrentHashMap<String, Integer> stable = new ConcurrentHashMap<>();
        stable.put("a", 2);
        stable.put("b", 5);
        stable.put("c", 7);
        System.out.println("stable-size = " + stable.size());
        System.out.println("stable-mappingCount = " + stable.mappingCount());
        System.out.println("sum-sequential = "
                + stable.reduceValuesToLong(Long.MAX_VALUE, Integer::longValue,
                                            0L, Long::sum));
        System.out.println("sum-parallel-enabled = "
                + stable.reduceValuesToLong(1L, Integer::longValue, 0L, Long::sum));
        System.out.println("odd-value-sum = "
                + stable.reduceValues(Long.MAX_VALUE,
                        value -> value % 2 == 1 ? value : null, Integer::sum));
        System.out.println("search-b = "
                + stable.search(Long.MAX_VALUE,
                        (key, value) -> key.equals("b") ? value : null));
        System.out.println("search-absent = "
                + stable.searchValues(Long.MAX_VALUE, value -> value > 100 ? value : null));

        ConcurrentLinkedQueue<String> collected = new ConcurrentLinkedQueue<>();
        stable.forEach(1L, (key, value) -> collected.add(key + "=" + value));
        List<String> ordered = new ArrayList<>(collected);
        Collections.sort(ordered);
        System.out.println("collected-sorted = " + ordered);

        ConcurrentHashMap<String, Integer> empty = new ConcurrentHashMap<>();
        System.out.println("empty-reference-reduce = "
                + empty.reduceValues(Long.MAX_VALUE, Integer::sum));
        System.out.println("empty-sum = "
                + empty.reduceValuesToLong(Long.MAX_VALUE, Integer::longValue,
                                           0L, Long::sum));

        ConcurrentHashMap<String, Integer> slots = new ConcurrentHashMap<>();
        AtomicInteger ids = new AtomicInteger();
        AtomicReference<Throwable> limitError = new AtomicReference<>();
        CyclicBarrier checked = new CyclicBarrier(2);
        Runnable attempt = () -> {
            int id = ids.incrementAndGet();
            boolean hasRoom = slots.size() < 1;
            try {
                checked.await(5, TimeUnit.SECONDS);
            } catch (Exception ex) {
                throw new AssertionError("Barrier failed", ex);
            }
            if (hasRoom) {
                slots.put("slot-" + id, id);
            }
        };
        Thread first = launch("limit-first", attempt, limitError);
        Thread second = launch("limit-second", attempt, limitError);
        finish(first, limitError);
        finish(second, limitError);
        System.out.println("capacity-one-final-size = " + slots.size());

        ConcurrentHashMap<String, Integer> changing = new ConcurrentHashMap<>();
        changing.put("a", 0);
        changing.put("b", 0);
        List<Map<String, Integer>> actualStates = new ArrayList<>();
        actualStates.add(Map.copyOf(changing));
        AtomicReference<String> firstKey = new AtomicReference<>();
        CountDownLatch firstObserved = new CountDownLatch(1);
        CountDownLatch updated = new CountDownLatch(1);
        AtomicReference<Throwable> updateError = new AtomicReference<>();
        Thread updater = launch("two-updates", () -> {
            try {
                await(firstObserved);
                String visited = firstKey.get();
                changing.put(visited, 1);
                actualStates.add(Map.copyOf(changing));
                String other = visited.equals("a") ? "b" : "a";
                changing.put(other, 1);
                actualStates.add(Map.copyOf(changing));
            } finally {
                updated.countDown();
            }
        }, updateError);

        Map<String, Integer> observations = new TreeMap<>();
        changing.forEach(Long.MAX_VALUE, (key, value) -> {
            observations.put(key, value);
            if (firstKey.compareAndSet(null, key)) {
                firstObserved.countDown();
                await(updated);
            }
        });
        finish(updater, updateError);
        List<Integer> observedValues = new ArrayList<>(observations.values());
        Collections.sort(observedValues);
        System.out.println("mixed-observed-values = " + observedValues);
        System.out.println("observed-map-was-actual-state = "
                + actualStates.contains(observations));
        System.out.println("current-values = " + new TreeMap<>(changing));

        ConcurrentHashMap<String, Integer> partial = new ConcurrentHashMap<>();
        partial.put("x", 1);
        partial.put("y", 2);
        partial.put("z", 3);
        AtomicInteger calls = new AtomicInteger();
        boolean failed = false;
        try {
            partial.replaceAll((key, value) -> {
                if (calls.incrementAndGet() == 2) {
                    throw new IllegalStateException("Stop on second callback");
                }
                return value * 10;
            });
        } catch (IllegalStateException ex) {
            failed = true;
        }
        long changed = partial.values().stream().filter(value -> value >= 10).count();
        System.out.println("replaceAll-failed = " + failed);
        System.out.println("replaceAll-changed-entries = " + changed);
        System.out.println("replaceAll-size = " + partial.size());

        ConcurrentSkipListSet<Integer> sortedSet =
                new ConcurrentSkipListSet<>(List.of(3, 1, 2));
        System.out.println("quiescent-sorted-set = " + sortedSet);
        System.out.println("quiescent-set-size = " + sortedSet.size());

        AtomicReference<Map<String, Integer>> published =
                new AtomicReference<>(Map.of("a", 0, "b", 0));
        Map<String, Integer> captured = published.get();
        published.set(Map.of("a", 1, "b", 1));
        System.out.println("captured-version = " + new TreeMap<>(captured));
        System.out.println("published-version = " + new TreeMap<>(published.get()));
    }
}
~~~

Compile and run in the directory containing the file:

~~~shell
javac --release 17 -encoding UTF-8 ConcurrentObservationDemo.java
java ConcurrentObservationDemo
~~~

Verified stdout:

~~~text
stable-size = 3
stable-mappingCount = 3
sum-sequential = 14
sum-parallel-enabled = 14
odd-value-sum = 12
search-b = 5
search-absent = null
collected-sorted = [a=2, b=5, c=7]
empty-reference-reduce = null
empty-sum = 0
capacity-one-final-size = 2
mixed-observed-values = [0, 1]
observed-map-was-actual-state = false
current-values = {a=1, b=1}
replaceAll-failed = true
replaceAll-changed-entries = 1
replaceAll-size = 3
quiescent-sorted-set = [1, 2, 3]
quiescent-set-size = 3
captured-version = {a=0, b=0}
published-version = {a=1, b=1}
~~~

This program does not claim that arbitrary bulk operations on any changing source will always produce the same stdout. The contention-related outcomes here are orchestrated to construct a specific scenario.

## 6. Why Do These Results Matter?

### 6.1. Quiescent Source: Comparing Execution Modes

The `stable` source holds values `2`, `5`, `7` and is not modified during processing:

~~~text
sum-sequential = 14
sum-parallel-enabled = 14
odd-value-sum = 12
~~~

Both sums yield `14`. A threshold of `1` merely enables parallelism; you must not infer from this output exactly how many threads ran. Returning `null` from the transformer for even numbers excludes `2` from the odd-value sum, leaving `5 + 7 = 12`.

Searching for key `b` has a single answer, `5`. Searching for a value greater than `100` finds nothing and returns `null`. On an empty map, the reference-returning reduction produces `null`, while the primitive sum uses the identity `0` and returns `0`.

Results gathered into the queue are sorted **after the bulk operation completes**, so stdout does not depend on callback execution order.

### 6.2. Both size Checks Are Accurate, Yet the Limit Is Still Exceeded

Both threads check `slots.size() < 1` before anyone inserts an element. The barrier holds both after the check; once released, both insert their own keys.

~~~text
capacity-one-final-size = 2
~~~

Here, you do not need any internal counting inaccuracy to explain the bug: each thread could have accurately observed an empty map. What was missing was an atomic capacity-allocation decision.

### 6.3. Traversal Produces a Composite That Was Never a Source State

The program does not assume whether `a` or `b` is visited first. The first key read by the callback is called the **visited key**; the other is the **unvisited key**.

The schedule is orchestrated as follows:

~~~text
Source: (visited key=0, unvisited key=0)
Callback records value 0 for the first key and then waits.

Updater thread:
    updates visited key to 1
    updates unvisited key to 1
    signals completion

Callback resumes:
    records value 1 for the remaining key
~~~

The source history only ever had three states:

~~~text
(0, 0) -> (1, 0) -> (1, 1)
~~~

The collected composite is `(0, 1)` in visited/unvisited key order, so:

~~~text
mixed-observed-values = [0, 1]
observed-map-was-actual-state = false
~~~

`actualStates` is recorded by the updater thread after each change, with no other writers present. The main thread only reads the history list after `join` completes, so there is no race on the `ArrayList` storing the history itself.

Waiting inside the callback is an experimental tool to force a schedule, not advice to block callbacks for long periods in production bulk operations. The example demonstrates that even a sequential traversal does not lock the source.

### 6.4. replaceAll Does Not Roll Back Updates Before an Exception

The first invocation multiplies a value by `10`. The second invocation throws an exception. Regardless of which key is processed first, we can verify that exactly one value changed:

~~~text
replaceAll-failed = true
replaceAll-changed-entries = 1
replaceAll-size = 3
~~~

There are no other writer threads in this section. It isolates the "not an all-or-nothing rollback transaction" property. Under concurrent updates, you must also account for interleaved modifications and the possibility of the function being invoked multiple times.

### 6.5. A Captured Version Differs From Re-Reading a New Reference

At the end of the program, an `AtomicReference` holds an unmodifiable map containing two integers. The reader captures a reference `captured`, and then the publisher swaps the reference to a new map.

~~~text
captured-version = {a=0, b=0}
published-version = {a=1, b=1}
~~~

The captured version remains the old map. The entire read pass over it uses the same data object, which is never mutated. This is a data-versioning model, distinct from updating two keys sequentially inside the same live map.

`AtomicReference` provides atomic access/updates to a single reference. It does not automatically freeze the referenced object; the map's immutability in the example is part of the data design. [Java 17: java.util.concurrent.atomic](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/concurrent/atomic/package-summary.html)

## 7. Copying Does Not Automatically Guarantee a Single Point in Time

The following operations create a separate result object, yet the source can still change during copying:

~~~java
Map<String, Integer> copy = new HashMap<>(liveMap);
Map<String, Integer> frozen = Map.copyOf(liveMap);
~~~

This is an in-method snippet using types from `java.util`, where `liveMap` is a concurrent map. Once copying finishes, the separate result may be stable in how it is managed. However, the copied entries can still originate from different points in the source's timeline.

`Map.copyOf` creates an unmodifiable map; that property does not turn reading the source into a whole-source snapshot transaction. Furthermore, key and value objects may still be the same references, so there is no automatic deep copy. [Java 17: Map.copyOf](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/Map.html#copyOf(java.util.Map))

A copy can satisfy "from now on, my result will not receive further membership changes." To satisfy the stronger requirement "all entries belong to a single source state," an appropriate acquisition mechanism is needed.

Sorting the copy, converting to a `TreeMap`, or calling `toArray` afterward cannot fix time-mixing that already occurred while reading the source.

## 8. When Is a Stronger Mechanism Needed?

### 8.1. Only Monitoring or Estimation Needed

Count dashboards, activity statistics, or finding a candidate can tolerate shifting results. In those cases, using concurrent APIs and communicating the exact guarantee level is usually appropriate.

Do not label or interpret metrics as "exact count at cut-off time" if the acquisition process lacks a cut-off protocol. Clarity about what the result means helps system users make sound decisions.

### 8.2. Capacity Limits Needed

You can use a `Semaphore` to grant slot permissions or a shared lock block guarding the check-and-insert. `Semaphore` manages permits through contracted acquire/release operations, rather than letting multiple threads infer capacity from the same `size` reading. [Java 17: Semaphore](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/concurrent/Semaphore.html)

However, you must design the entire lifecycle: return the acquired permit if insertion fails, release exactly once on successful removal, ensure all write paths obey the protocol, and prevent duplicate keys from leaking or over-releasing permits. Merely placing a semaphore next to a map does not automatically bind the two structures into a correct protocol.

### 8.3. Consistent Snapshot Needed for Reporting

Common design approaches include:

- Pause or wait for all relevant writers to finish, then read during the quiescent window.
- Use a shared external lock that **all relevant writers** obey; hold the lock for the entire copy window requiring consistency.
- Publish immutable data versions and have readers capture one version for the entire processing pass.
- Use the versioning/transaction mechanism of the actual data owner when the data lives in another system.

None of these can be achieved by a single `synchronized(liveMap)` block if other threads still call `ConcurrentHashMap` methods directly without participating in that monitor.

### 8.4. If Using a Synchronized Wrapper

`Collections.synchronizedMap` has a different protocol: access through the wrapper and manually synchronize on the wrapper when iterating over views. For a copy pass that needs to block writers, all relevant accesses must obey the wrapper/shared lock rather than bypassing it to the underlying map. [Java 17: Collections.synchronizedMap](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/Collections.html#synchronizedMap(java.util.Map))

Additionally, if a multi-step business update must be observed as a single batch, writers must also hold the shared lock around the entire batch. Locking individual calls alone does not protect multi-key invariants.

### 8.5. If Publishing Immutable Versions

Readers must capture the version reference **once** and use it throughout the entire processing pass. Re-reading the published reference for each key can still pull one key from the old version and another from the new version.

Mutable elements still require separate design. An unmodifiable map containing mutable balance objects is not a deep snapshot of all balances.

If multiple writers produce new versions from an old one, publication must also be coordinated to avoid overwriting updates. The final example in the program only demonstrates a single publication, not a complete multi-writer coordination solution.

## 9. Concurrent Sets and Multi-Element Queries

`ConcurrentHashMap.newKeySet()` inherits the backing map's properties for an unordered set. `ConcurrentSkipListSet` provides element ordering. In both cases, distinguish:

- A single element addition or removal.
- A multi-element traversal.
- An aggregate condition such as size or subset checks.
- A batch addition/removal of multiple elements.

The fact that `set.add(x)` returns a contracted boolean does not make `if (set.size() < limit) set.add(x)` atomic. Similarly, `containsAll` or comparing two sets that are under active modification should not be treated as reconciling two frozen datasets.

If a set tracks in-flight tasks, removing an element does not by itself prove the task finished properly. Task lifecycle requires its own completion mechanism.

When conditional removal by version or owner is needed, a map storing a version token often expresses the condition more clearly than a key-only set; the choice depends on the data that actually needs protection.

## 10. Streams Do Not Upgrade the Source's Consistency

`liveMap.values().stream()` or `parallelStream()` still starts from the live source. A pipeline does not automatically copy the map before running. Streams are lazily evaluated; constructing a pipeline does not mean all data has been read at that moment. [Java 17: Streams and Traversal Timing](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/stream/package-summary.html)

If the source allows concurrent updates, processing must be understood under the source's policy. Switching from `forEach` to `stream` does not turn observations into a single version.

`parallelStream` also places additional requirements on the processing function and the destination. Do not write to a shared `ArrayList` from multiple tasks assuming the map's concurrency protects that list as well.

Once you have a dataset that meets your consistency requirements, you can then decide between sequential or parallel computation on it. Input consistency and computation performance are two separate decisions.

## 11. Conclusions to Avoid

| Common Misconception | What to Actually Check |
|---|---|
| "No ConcurrentModificationException means I have a snapshot." | Does the traversal have a snapshot contract or only weak consistency? |
| "size was below the limit, so inserting is guaranteed to fit." | Are the check and capacity allocation part of a single operation/protocol? |
| "mappingCount returns a long, so it is always more point-in-time accurate." | A larger numeric type does not create a stronger consistency level. |
| "Sequential forEach means writers cannot modify the data." | Is there a mechanism preventing or coordinating writers for the entire read pass? |
| "putAll/replaceAll has 'all', so readers only see before or after." | Is the contract whole-structure atomic or just multiple individual updates? |
| "Map.copyOf gives me a single point-in-time snapshot." | How was reading from the source coordinated? |
| "Using an ordered set means all elements belong to the same version." | Element ordering is different from temporal consistency. |
| "Bulk callbacks can write results freely because the source is thread-safe." | Are the result destination and callback side effects thread-safe under concurrent execution? |

Measurements and logging can also perform traversals. For example, `toString` or formatting an entire map can produce a time-mixed description while the source is updating. Use such output for diagnostics with appropriate caution, rather than treating it as cut-off-state evidence without a snapshot protocol.

## 12. Self-Check Exercises

### Exercise 1 — Accurate Counts Are Still Not Enough

Two threads both see a map with `9` elements when the limit is `10`, and then each inserts a distinct key. Do you need to prove `size` returned a wrong number to explain the final count of `11`?

**Answer:** No. Both measurements could have been accurate at the moment of reading. The issue is that checking and inserting were not combined into an atomic capacity-allocation decision.

### Exercise 2 — The Long.MAX_VALUE Threshold

`map.forEach(Long.MAX_VALUE, action)` runs sequentially. Can it be used to guarantee that data does not change during the traversal?

**Answer:** No. It disables parallel splitting for that traversal itself; it does not lock out other writers.

### Exercise 3 — A Composite That Never Existed

A source transitions through `(P=0,Q=0)`, `(P=1,Q=0)`, `(P=1,Q=1)`. Why can a traversal observe `(P=0,Q=1)` without any structural corruption?

**Answer:** It can read P before the update batch and Q after the update batch. Each observation is valid per key, just not from the same point in time.

### Exercise 4 — replaceAll Fails Midway

The function updates three keys and then throws an exception on the next key. Should you expect the first three keys to revert to their old values automatically?

**Answer:** No. This is not an all-or-nothing rollback transaction. You must handle partial state or use a new-version publication model if the entire set must change together.

### Exercise 5 — Collecting Results in Parallel

A bulk `forEach` with threshold `1` writes strings into a shared `ArrayList`. The source is a `ConcurrentHashMap`. What contract is missing?

**Answer:** The destination list is not automatically protected. Use an appropriate collector or a different aggregation approach. Even then, you must still consider whether the source mixes points in time.

### Exercise 6 — The Identity Element

Why does summing counts use `0` as the basis instead of `100` in a parallel reduction?

**Answer:** `0` leaves combined values unchanged. A non-identity value may be factored into multiple partitions of the reduction; it is not guaranteed to be added only once.

### Exercise 7 — Copy Then Sort

`new TreeMap<>(liveConcurrentMap)` produces an ordered result. Is that enough to claim all entries were captured at the same point in time?

**Answer:** No. Presentation order does not change how data was read from a changing source. A dedicated consistent-snapshot mechanism is required.

### Exercise 8 — Holding One Version

An `AtomicReference` points to maps that are never mutated after publication. A reader calls `get` separately before reading each key. Can it still mix two versions?

**Answer:** Yes. The reference may have been swapped between two `get` calls. Capture one version reference and use it for the entire read pass if all keys must belong to the same version.

Before performing a `size` check, traversal, or bulk operation, determine whether the needed result is a live estimate, a per-key action, or a frozen dataset. The required consistency level dictates the read/write protocol; method names and the absence of exceptions are no substitute for that decision.

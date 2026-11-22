# Thread-Safe Collections and Non-Atomic Compound Actions in Java

## Objectives and Scope

A collection advertised as **thread-safe** does not mean **every piece of code using that collection is atomic**. Two method calls that are safe individually can still be interleaved by another thread. Therefore, a sequence such as "check-then-act", "read-then-increment", "count-then-access", or "update two related keys" can violate business invariants even though the collection's internal structure is not corrupted.

This lesson focuses on **general Java concurrency**: `Collections.synchronizedList/Map`, `ConcurrentHashMap`, `ConcurrentLinkedQueue`, `BlockingQueue`, `CopyOnWriteArrayList`, external locks, and immutable snapshots. Spring-specific APIs, annotations, or configurations are not used because they are covered in another Spring chapter.

After this lesson, you will be able to:
- Accurately explain **thread safety**, **atomicity**, **visibility**, **compound action**, and **linearization point** when operating on collections.
- Distinguish between "a thread-safe method" and "a sequence of multiple methods as a transaction".
- Find and fix bugs involving `containsKey` → `put`, `get` → `put`, `isEmpty` → `remove/take`, `size` → `get`, and concurrent iteration.
- Choose the right atomic API such as `putIfAbsent`, `compute`, `merge`, `remove(key,value)`, `replace(key,old,new)`, `poll`, or protect the entire compound action with the same lock.
- Understand why **per-key atomicity** does not mean **multi-key atomicity**, and why a **weakly consistent** or **snapshot** iterator is not a consistent collection-wide transaction.
- Run **Java 17+** examples with controlled stdout to observe races occurring and how to fix them.

## 1. What Does "Thread-Safe" Guarantee?

In Java, thread-safe collections are designed so that **multiple threads can access them according to a defined concurrency contract** without violating the data structure's guarantees. However, the contract differs depending on the collection type and each method:

| Collection / wrapper | Core property | Limitations to understand |
| --- | --- | --- |
| `Collections.synchronizedList(...)` | Synchronizes multiple operations on the wrapper's single monitor | Loops and sequences of multiple calls usually require manual `synchronized(list)` on the wrapper |
| `Collections.synchronizedMap(...)` | Protects operations per the wrapper contract | `get` then `put` are two separate operations without an external lock around the entire sequence |
| `ConcurrentHashMap<K,V>` | Allows multiple concurrent operations; supports **per-key** atomic updates | Does not automatically turn multi-key updates into a transaction; iteration is not a fixed snapshot |
| `ConcurrentLinkedQueue<E>` | Lock-free queue with concurrency-friendly algorithm; `poll` retrieves an element if present in one operation | `isEmpty` → `poll` and `peek` → `poll` are not a single atomic operation |
| `BlockingQueue<E>` | `put/take/offer/poll` coordinate producer–consumer with wait/timeout semantics | Checking `size/isEmpty` then calling `take` does not lock the queue state at check time |
| `CopyOnWriteArrayList<E>` | Creates a copy of the array on update; iterator is a snapshot | Iterator does not reflect updates made after it was created; every modification incurs a copy cost |
| `List.of` / `List.copyOf` | List that disallows structural modification after creation | Mutable objects **inside** can still change; appropriate safe publication is required |

There is no blanket statement that "every call on every thread-safe collection is a linearizable transaction" without considering the **method contract and data scope**. Similarly, `Collections.synchronizedList` and `ConcurrentHashMap` are both safe for their designed purposes, but they **differ in locking, iteration behavior, and atomic APIs**.

### An Operation and an Invariant

Suppose a map stores visit counts:

~~~java
Integer old = visits.get("home");
visits.put("home", old + 1);
~~~

Even if `visits.get` and `visits.put` are each individually synchronized, the operation **"increment by exactly one"** is not guaranteed. Two threads can both read 0 and both write 1. The collection remains structurally intact, but the **business result is wrong**.

An **invariant** is a condition that must hold after a business operation; for example: "after N successful increments, the counter increases by exactly N", "a job is claimed by only one worker", or "the total balance between two accounts remains constant". To fix a compound action, you must identify **all steps that need to be protected to preserve the invariant**.

## 2. Atomicity Differs from Visibility and Thread-Safe Methods

Imagine two threads running concurrently:

~~~text
Thread A                       Thread B
--------                       --------
old = map.get("count")  -> 0
                               old = map.get("count") -> 0
map.put("count", 1)
                               map.put("count", 1)

Both gets are safe; both puts are safe.
The result after two additions can still be 1.
~~~

In the Java Memory Model:

- **Visibility:** whether changes made by one thread are properly observed by another thread according to a happens-before relationship.
- **Atomicity:** whether the steps of a logical operation can be interleaved; whether there is an observation point at which the entire operation has taken effect.
- **Ordering:** which actions are ordered before/after others according to the synchronization contract, independent of the mere line order of code across threads.
- **Linearization point:** the conceptual point in time at which each atomic operation takes effect as a single operation, helping reason about the order of competing operations.

A `get` operation can be completely thread-safe and see the latest value per the collection's contract, yet **after `get` returns**, another thread is still allowed to modify the collection. Therefore, a check result at `t1` does not automatically remain valid when the thread performs an action at `t2`.

**Key takeaway:** if correctness is needed for the entire sequence, use **a compound API guaranteed to be atomic**, or **a lock/ownership protocol protecting all steps**. Simply choosing a thread-safe collection without changing check-then-act code is not enough.

## 3. Deterministic Example: synchronizedMap Still Has Lost Updates

`Collections.synchronizedMap` provides a synchronized wrapper for operations per its contract, but a separate `get` then `put` still leaves a gap. The following example intentionally forces both threads to **read before either writes** so the bug does not depend on scheduler luck.

Create the file **`SynchronizedMapRaceDemo.java`**:

~~~java
import java.util.Collections;
import java.util.HashMap;
import java.util.Map;
import java.util.concurrent.CountDownLatch;

public class SynchronizedMapRaceDemo {
    public static void main(String[] args) throws InterruptedException {
        Map<String, Integer> counts =
                Collections.synchronizedMap(new HashMap<>());
        counts.put("views", 0);

        CountDownLatch readByBoth = new CountDownLatch(2);
        CountDownLatch allowWrite = new CountDownLatch(1);

        Runnable increase = () -> {
            int old = counts.get("views");
            readByBoth.countDown();

            try {
                allowWrite.await();
            } catch (InterruptedException e) {
                Thread.currentThread().interrupt();
                return;
            }

            counts.put("views", old + 1);
        };

        Thread first = new Thread(increase, "writer-1");
        Thread second = new Thread(increase, "writer-2");
        first.start();
        second.start();

        readByBoth.await();
        allowWrite.countDown();
        first.join();
        second.join();

        System.out.println("expected=2 actual=" + counts.get("views"));
    }
}
~~~

Compile and run with JDK 17+:

~~~bash
javac SynchronizedMapRaceDemo.java
java SynchronizedMapRaceDemo
~~~

Stdout when threads complete normally:

~~~text
expected=2 actual=1
~~~

Why is the result deterministically 1?
1. The map initially stores `"views" -> 0`.
2. Both threads call `get` and receive 0 before the `allowWrite` latch is released.
3. Each thread computes `0 + 1` and calls `put`; the two individual write operations are valid, yet both set the value to 1.
4. `join` makes main wait for both to finish before reading and printing the result.

This is a **business-operation-level race**, not evidence that the `synchronizedMap` wrapper's structure is broken. The latch only serves to reproduce the bug; production code does not use latches this way to "fix" a counter.

## 4. Solution A: Lock the Entire Compound Action

### 4.1. One Lock for Both Reading and Modifying

With `Collections.synchronizedMap`, you can use the wrapper's own monitor:

~~~java
Map<String, Integer> counts =
        java.util.Collections.synchronizedMap(new java.util.HashMap<>());

synchronized (counts) {
    counts.put("views", counts.getOrDefault("views", 0) + 1);
}
~~~

This is an **illustrative snippet inside a method**; the `counts` variable needs to be shared in the appropriate scope. Because the wrapper synchronizes on its own monitor for protected methods, the `synchronized(counts)` block encloses the entire check–update sequence. When another thread also uses the wrapper according to its contract, it cannot interleave into this sequence via operations synchronized on the same monitor.

If you use a `Collections.synchronizedMap(backing)` wrapper, **do not continue letting other threads access `backing` directly**: they can bypass the wrapper and break the entire protocol. If multiple access paths use different locks, they will not coordinate either.

### 4.2. Iterating a synchronizedList Requires the Same Monitor

Another misconception: every method of `Collections.synchronizedList` is synchronized, so a `for-each` loop is automatically safe. In reality, an iterator is created and then used across multiple steps. Another thread can modify the list while the iterator is traversing it.

~~~java
List<String> names =
        java.util.Collections.synchronizedList(new java.util.ArrayList<>());

names.add("An");
names.add("Bình");

synchronized (names) {
    for (String name : names) {
        System.out.println(name);
    }
}
~~~

This is a snippet inside a method, not a standalone program. **Lock on the `names` wrapper itself** throughout the entire iteration, provided all threads use that same wrapper for competing operations. Similarly, if calling `Iterator`/`Spliterator`/`Stream` on the wrapper, follow the collection's synchronization documentation and hold the appropriate lock while traversing.

**Do not rely on `ConcurrentModificationException` to "detect" or prevent races.** For collections using fail-fast iterators, the exception is a best-effort mechanism to report misuse, not a synchronization barrier; *not* throwing the exception does not mean the traversal is safe.

### 4.3. Check-Then-Act on a List

Still wrong when concurrent removal can occur:

~~~java
if (names.size() > 0) {
    String first = names.get(0);
}
~~~

Right after `size() > 0`, another thread can remove the first element. Even though `size()` and `get(0)` are individually synchronized, `get(0)` can throw `IndexOutOfBoundsException`.

How to fix when you want to read the first element under a valid snapshot:

~~~java
synchronized (names) {
    if (!names.isEmpty()) {
        String first = names.get(0);
        System.out.println(first);
    }
}
~~~

If the business logic actually needs to **remove an element so no one else claims the same one**, it is better to choose an atomic queue `poll()` API (next section) rather than manually combining `isEmpty` + `remove(0)`.

### 4.4. Lock the Right Invariant Scope

A shared monitor protects both read and write steps, but too wide a scope can cause contention. You should not hold a lock while making network I/O calls, invoking uncontrolled callbacks, or performing long computations if the invariant does not require it. Conversely, shrinking the lock to the point of **losing atomicity** brings the race back.

How to check a locking solution:
- Do **all** writers and important readers use the **same lock**?
- Does the critical section cover both the check and the update?
- Is there any path accessing the backing collection directly and bypassing the lock?
- Can an exception prevent the lock from being released (with `ReentrantLock`, `unlock()` must be in `finally`)?
- Are multiple locks acquired in different orders, leading to deadlock?

## 5. Solution B: Use Atomic Compound Operations Per Contract

For `ConcurrentHashMap`, several operations combine check and update into a single call with per-key atomic semantics. For example:

| Need | Error-prone pattern | Appropriate method |
| --- | --- | --- |
| Set value only when key does not exist | `if (!containsKey(k)) put(k,v)` | `putIfAbsent(k,v)` |
| Increment value associated with a key | `put(k, get(k)+1)` | `compute(k, fn)` or `merge(k, 1, Integer::sum)` |
| Remove key only if value still matches observed one | `if (get(k).equals(v)) remove(k)` | `remove(k,v)` |
| Replace value only if it still equals old value | `if (get(k).equals(old)) put(k,next)` | `replace(k, old, next)` |
| Create value for missing key | `if (get(k)==null) put(k, factory())` | `computeIfAbsent(k, factory)` when contract fits |

In `ConcurrentHashMap`, internal locking/algorithms support atomicity of these updates **for a single key**, but an operation involving **two keys** or another collection does not automatically become a transaction.

**Be careful with `null`:** `ConcurrentHashMap` does not allow `null` keys or values. `compute`/`merge` use a `null` result with removal or no-mapping semantics depending on the method. If the business logic needs to store "null value as a valid state", design a sentinel/Optional/value object instead of trying to sneak `null` into the map.

### 5.1. Java 17 Example: ConcurrentHashMap.compute Fixes Lost Updates

Create the file **`ConcurrentMapAtomicDemo.java`**:

~~~java
import java.util.ArrayList;
import java.util.List;
import java.util.concurrent.ConcurrentHashMap;
import java.util.concurrent.ExecutorService;
import java.util.concurrent.Executors;
import java.util.concurrent.Future;
import java.util.concurrent.TimeUnit;

public class ConcurrentMapAtomicDemo {
    public static void main(String[] args) throws Exception {
        ConcurrentHashMap<String, Integer> counts =
                new ConcurrentHashMap<>();
        counts.put("views", 0);

        ExecutorService pool = Executors.newFixedThreadPool(8);
        try {
            List<Future<?>> tasks = new ArrayList<>();

            for (int worker = 0; worker < 8; worker++) {
                tasks.add(pool.submit(() -> {
                    for (int i = 0; i < 1_000; i++) {
                        counts.compute("views", (key, oldValue) ->
                                oldValue == null ? 1 : oldValue + 1);
                    }
                }));
            }

            for (Future<?> task : tasks) {
                task.get();
            }

            System.out.println("expected=8000 actual=" + counts.get("views"));
            System.out.println("keys=" + counts.size());
        } finally {
            pool.shutdown();
            if (!pool.awaitTermination(1, TimeUnit.MINUTES)) {
                pool.shutdownNow();
            }
        }
    }
}
~~~

Compile and run:

~~~bash
javac ConcurrentMapAtomicDemo.java
java ConcurrentMapAtomicDemo
~~~

Stdout when all tasks succeed:

~~~text
expected=8000 actual=8000
keys=1
~~~

Eight tasks, each incrementing a thousand times: 8,000 updates in total. `ConcurrentHashMap.compute` guarantees that the computed update for **a single mapping key** is performed atomically per the class's contract. Threads may contend and wait when updating this key, but there is no interleaving between the caller's `get` and `put` because the read-modify-write sequence has been moved into a compound method.

**Conditions for using `compute` properly:**
- The remapping function must be short, reliable, non-blocking (not blocking for long), and ideally free of external side effects.
- Do not modify other mappings of the same map inside the callback itself; `ConcurrentHashMap` documentation prohibits attempting to update other mappings from a compute function in certain cases and may trigger recursive updates that never complete.
- Do not assume that logic adding two keys or updating an external database is included in the atomic operation.
- `Future.get()` lets main know that all tasks have actually completed and detects exceptions, rather than just reading a value while the pool is still running.

With another implementation that only conforms to the `Map` or `ConcurrentMap` interface, read the **exact class contract**; do not extrapolate all strong atomic guarantees of `ConcurrentHashMap` to every custom map.

### 5.2. putIfAbsent and the "Only One Winner" Pattern

Instead of:

~~~java
if (!jobs.containsKey(id)) {
    jobs.put(id, "running");
}
~~~

use:

~~~java
String previous = jobs.putIfAbsent(id, "running");
boolean claimed = (previous == null);
~~~

This is a snippet inside a method where `jobs` is `ConcurrentHashMap<String,String>` and `id` is a non-null `String`. Only the first caller that sets the mapping from absent to `"running"` receives `null` per the contract. Subsequent callers receive the existing value.

**However:** if the state needs to transition from `"queued"` to `"running"` rather than absent → present, `putIfAbsent` is not the right API. In that case, use `replace(id,"queued","running")` to perform a **compare-and-update** against the expected value, or `compute` when the logic is more complex.

An atomic operation on a map only guarantees **the state of the map**. If after `putIfAbsent` you must send an email, write to a database, or make an HTTP call, those external actions **do not automatically belong to the same transaction**. You need to design idempotency, retries, and compensation for business side effects at the system scope.

### 5.3. merge for Per-Key Counters

With `ConcurrentHashMap<String, Integer>`, you can write concisely:

~~~java
counts.merge("views", 1, Integer::sum);
~~~

If the key is not present, it sets 1; if a value already exists, it combines old and 1. The update of a single mapping is atomic per the `ConcurrentHashMap` contract. Writing `getOrDefault` followed by `put` yourself defeats this purpose.

For very high-frequency statistics updates, another pattern is a map from key to `LongAdder`. However, `LongAdder.sum()` under concurrent updates **is not an atomic snapshot**. Choose it only if the business logic accepts approximate values observed during updates; balances, credit limits, and "sell only if in stock" decisions usually require stricter invariants.

## 6. Solution C: Remove an Element from a Queue in One Operation

A common check-then-act bug in consumers:

~~~java
if (!queue.isEmpty()) {
    String task = queue.remove();
    process(task);
}
~~~

This is an illustrative snippet with `queue` and `process` already declared. Right after `isEmpty() == false`, another consumer can drain the remaining element. Then `remove()` on an empty queue throws `NoSuchElementException`. If `take()` is used after `isEmpty()`, the thread can **block** when the element has already been taken by another thread.

When you do not want to wait, use **`poll()` alone**:

~~~java
String task = queue.poll();
if (task != null) {
    process(task);
}
~~~

`poll()` atomically checks and removes the head element of the queue (or returns `null` if empty) per the queue's contract. With `ConcurrentLinkedQueue`, `null` is not a valid element, so `null` indicates no task was retrieved.

### Java 17 Example: Two Consumers, One Element

Create the file **`QueueClaimDemo.java`**:

~~~java
import java.util.concurrent.Callable;
import java.util.concurrent.ConcurrentLinkedQueue;
import java.util.concurrent.CountDownLatch;
import java.util.concurrent.ExecutorService;
import java.util.concurrent.Executors;
import java.util.concurrent.Future;
import java.util.concurrent.TimeUnit;

public class QueueClaimDemo {
    public static void main(String[] args) throws Exception {
        ConcurrentLinkedQueue<String> queue =
                new ConcurrentLinkedQueue<>();
        queue.add("job-1");

        ExecutorService pool = Executors.newFixedThreadPool(2);
        CountDownLatch start = new CountDownLatch(1);

        try {
            Callable<String> claim = () -> {
                start.await();
                return queue.poll();
            };

            Future<String> first = pool.submit(claim);
            Future<String> second = pool.submit(claim);

            start.countDown();
            String a = first.get();
            String b = second.get();

            int claimed = (a != null ? 1 : 0) + (b != null ? 1 : 0);
            int empty = (a == null ? 1 : 0) + (b == null ? 1 : 0);

            System.out.printf(
                    "claimed=%d empty=%d remaining=%d%n",
                    claimed, empty, queue.size());
        } finally {
            pool.shutdown();
            if (!pool.awaitTermination(1, TimeUnit.MINUTES)) {
                pool.shutdownNow();
            }
        }
    }
}
~~~

Run:

~~~bash
javac QueueClaimDemo.java
java QueueClaimDemo
~~~

Stdout:

~~~text
claimed=1 empty=1 remaining=0
~~~

You cannot predict which thread wins. But because there is only **one element** and each worker calls `poll()` exactly once, only one worker receives `"job-1"`, and the other receives `null`. `Future.get()` ensures main reads the results after both operations have completed.

**Note on queue types:** `BlockingQueue.take()` intentionally **waits** when empty; `poll(timeout, unit)` waits for a bounded time, and `poll()` does not wait. Choose according to consumer needs. Do not use `isEmpty()` before `take()` as a guarantee that `take()` will not block.

## 7. Iteration: Fail-Fast, Weakly Consistent, and Snapshot

Each collection family has a different iterator contract; "thread-safe" does not mean "traversing the entire collection at a single point in time".

| Observation model | Common examples | Meaning |
| --- | --- | --- |
| Fail-fast (best effort) | Standard `ArrayList`, `HashMap` iterators | May throw `ConcurrentModificationException` if structurally modified outside the iterator; not a mechanism guaranteeing concurrent safety |
| Iterator requiring external synchronization | `Collections.synchronizedList/Map` | Hold the wrapper's monitor throughout the **entire traversal** per the contract |
| Weakly consistent | `ConcurrentHashMap`, `ConcurrentLinkedQueue` | Does not fail-fast on concurrent updates; may see some updates and miss others; not an atomic snapshot |
| Snapshot iterator | `CopyOnWriteArrayList` | Sees the array state at the time the iterator was created, not subsequent changes |

### 7.1. Java 17 Example: CopyOnWriteArrayList Snapshot Iterator

Create the file **`CopyOnWriteSnapshotDemo.java`**:

~~~java
import java.util.ArrayList;
import java.util.Iterator;
import java.util.List;
import java.util.concurrent.CopyOnWriteArrayList;

public class CopyOnWriteSnapshotDemo {
    public static void main(String[] args) {
        CopyOnWriteArrayList<String> names =
                new CopyOnWriteArrayList<>();
        names.add("A");

        Iterator<String> before = names.iterator();
        names.add("B");

        List<String> seen = new ArrayList<>();
        before.forEachRemaining(seen::add);

        System.out.println("iterator=" + seen);
        System.out.println("current=" + names);
    }
}
~~~

Run:

~~~bash
javac CopyOnWriteSnapshotDemo.java
java CopyOnWriteSnapshotDemo
~~~

Stdout:

~~~text
iterator=[A]
current=[A, B]
~~~

The iterator was created before B was added to the list, so it traverses the snapshot containing A. The current list has A and B. This is intentional behavior: stable traversal, minimal reader/writer coordination, well suited for **read-heavy, write-rare** scenarios.

In return, every structural update typically allocates/copies the underlying array; frequent writes or very large lists can create significant allocation/copy overhead. The snapshot iterator of `CopyOnWriteArrayList` does not support `Iterator.remove()`; attempting to remove via the iterator throws `UnsupportedOperationException`.

### 7.2. Weakly Consistent Does Not Mean a Consistent Snapshot

`ConcurrentHashMap.entrySet().iterator()` can traverse while other threads update the map without an external lock like `synchronizedMap`. However, the entries obtained **are not necessarily a snapshot at a single point in time**. For example, if a system transfers money from key A to key B via two independent updates, a traversal might see A after the deduction and B before the addition, even though both individual map operations are safe.

Therefore:
- Use weakly consistent iterators for observation/monitoring that **tolerates fluctuation**.
- If you need financial reporting or a multi-key invariant at a point in time, you must design separate synchronization/snapshotting.
- Do not use `size()`, `isEmpty()`, or aggregate results during concurrent mutation as absolute proof for a multi-step decision. Those values can be stale as soon as they are returned.
- Do not rely on `ConcurrentModificationException` for control flow.

## 8. Per-Key Atomicity Is Still Not Multi-Key Atomicity

Suppose accounts A and B are stored in a `ConcurrentHashMap<String,Integer>`. We need to transfer 70 units from A to B, initially `A=100, B=0`, with the invariant `A+B=100`.

~~~java
balances.compute("A", (key, old) -> old - 70);
balances.compute("B", (key, old) -> old + 70);
~~~

Both `compute` calls may be atomic **for their respective keys**. But in between them, a reader can see `A=30, B=0` and conclude the total is 30. If another operation interleaves or the second step throws an exception, the system can also end up in a business-invalid state.

**Do not assume you can use a `ConcurrentHashMap.compute` callback to modify another key in the map** to turn two keys into a transaction; that is outside the callback's safety contract and can cause errors or progress issues.

### 8.1. Fix with a Lock Protecting the Entire Invariant

Create the file **`MultiKeyTransferDemo.java`**:

~~~java
import java.util.concurrent.ExecutorService;
import java.util.concurrent.Executors;
import java.util.concurrent.Future;
import java.util.concurrent.TimeUnit;

public class MultiKeyTransferDemo {
    private record Balances(int a, int b) {}

    private static final class Ledger {
        private int a = 100;
        private int b = 0;

        synchronized boolean transferAToB(int amount) {
            if (amount <= 0 || a < amount) {
                return false;
            }
            a -= amount;
            b += amount;
            return true;
        }

        synchronized Balances snapshot() {
            return new Balances(a, b);
        }
    }

    public static void main(String[] args) throws Exception {
        Ledger ledger = new Ledger();
        ExecutorService pool = Executors.newFixedThreadPool(2);

        try {
            Future<Boolean> first =
                    pool.submit(() -> ledger.transferAToB(70));
            Future<Boolean> second =
                    pool.submit(() -> ledger.transferAToB(70));

            int accepted = (first.get() ? 1 : 0) +
                    (second.get() ? 1 : 0);

            Balances view = ledger.snapshot();
            System.out.printf(
                    "accepted=%d A=%d B=%d total=%d%n",
                    accepted, view.a(), view.b(), view.a() + view.b());
        } finally {
            pool.shutdown();
            if (!pool.awaitTermination(1, TimeUnit.MINUTES)) {
                pool.shutdownNow();
            }
        }
    }
}
~~~

Compile and run:

~~~bash
javac MultiKeyTransferDemo.java
java MultiKeyTransferDemo
~~~

Stdout:

~~~text
accepted=1 A=30 B=70 total=100
~~~

Two concurrent tasks attempt to transfer 70, but the lock on the **same Ledger object** forces each check–debit–credit sequence to execute atomically with respect to other Ledger operations. Only one transfer succeeds; the other sees `a=30` and returns `false`. `snapshot()` also locks that monitor, so it never observes the state between the debit and credit steps.

The example uses two fields to highlight the invariant; if the actual state lives in a map, you can protect **all updates and snapshots** via a lock on the service owning the map. Another option is to hold both A/B in **an immutable record** and update the record via `AtomicReference.compareAndSet`/`updateAndGet`. Choose based on invariant complexity, write frequency, contention, and data scope.

**Boundary to remember:** `synchronized`/`AtomicReference` in a single JVM only coordinates threads **within the same process**. If two processes concurrently modify a database or a distributed resource, you need that system's own transaction/coordination protocol; thread-safe collections do not solve inter-process concurrency.

## 9. Careful Inspection of Common Compound Actions

### 9.1. containsKey + put

~~~java
if (!map.containsKey(key)) {
    map.put(key, value);
}
~~~

Another thread can insert the key after `containsKey`. With `ConcurrentHashMap`, use `putIfAbsent` when you need **put only if absent**. If `null` values have special semantics, read the specific contract.

### 9.2. get + put to Increment a Counter

~~~java
map.put(key, map.getOrDefault(key, 0) + 1);
~~~

If the map is modified by multiple writers, lost updates occur. Use `compute`/`merge` of `ConcurrentHashMap`, or lock the entire sequence if using a synchronized wrapper.

### 9.3. contains + add to Avoid Duplicates in a List

~~~java
if (!list.contains(item)) {
    list.add(item);
}
~~~

Two threads can both see the item is absent and both add it. If the invariant is a **set with no duplicate elements**, use an appropriate `Set` structure (e.g., `ConcurrentHashMap.newKeySet()`) and a single `add(item)` call with atomic membership semantics. If ordering is still needed and duplicates are allowed under other rules, you must lock the entire sequence under a single unified monitor.

### 9.4. size + get or isEmpty + remove

~~~java
if (list.size() > index) {
    return list.get(index);
}
~~~

Another thread can remove or reorder the list after the check. With `synchronizedList`, lock the wrapper for the entire sequence. If using a queue to claim an element, use `poll()` instead of check-then-remove.

### 9.5. peek + poll

~~~java
String expectedHead = queue.peek();
String removed = queue.poll();
~~~

Both calls are individually safe, but another thread can take the head in between; `removed` does not necessarily equal `expectedHead`. If you only want to **claim an element**, use only the result of `poll()`. If you must "check that the head satisfies a condition before taking it", you need an appropriate atomic API/protocol, such as a lock protecting the whole operation or a queue with dedicated semantics designed for that requirement.

### 9.6. Iteration + Update

~~~java
for (String value : list) {
    if (shouldRemove(value)) {
        list.remove(value);
    }
}
~~~

This is an illustrative snippet with `shouldRemove`. With a normal `ArrayList`, calling `list.remove` inside an enhanced for-loop can cause `ConcurrentModificationException` even in **a single thread**. With concurrent lists, semantics depend on the type; snapshot iterators cannot modify the snapshot. Use `removeIf` if the collection's contract satisfies the exact atomic scope you need, or lock and operate via `Iterator.remove()` when the collection supports it. **Do not assume** every implementation of `removeIf` is atomic with respect to all other updates.

## 10. Choosing the Right Tool for the Requirement

| Practical requirement | Approach |
| --- | --- |
| One writer, multiple threads need to submit commands | Ownership + queue/actor-like executor |
| Increment independent counters in a map | `ConcurrentHashMap.compute/merge`; or map key -> `LongAdder` if non-atomic snapshots are acceptable |
| Register a key if not yet present | `putIfAbsent` |
| Transition state based on old value | `replace(key, expected, next)` or `compute` |
| Multiple consumers competing for a task | `BlockingQueue.take/poll` or `ConcurrentLinkedQueue.poll` |
| Read-heavy, rarely modified, stable iteration | `CopyOnWriteArrayList` or publish an immutable list |
| Synchronized wrapper with a multi-step sequence | `synchronized(wrapper)` around the entire sequence, all access paths following the same protocol |
| Consistent updates/snapshots across multiple fields or keys | Shared lock or immutable aggregate + `AtomicReference` |
| Approximate reporting during concurrent updates | Weakly consistent iteration, metric snapshots with clearly stated limitations |
| Transactions spanning multiple JVMs/databases | Synchronization/transaction protocol outside the scope of Java collections |

**There is no single best solution for every workload.** Locks protect large invariants but introduce contention; `ConcurrentHashMap` provides good per-key concurrency but does not offer multi-key transactions; copy-on-write optimizes read-heavy iteration but incurs copy costs on writes; queues handle item-by-item work but do not automatically maintain consistency between two systems.

## 11. Liveness and Performance After Fixing Races

Fixing atomicity correctly is only the first step. You also need to check **liveness** and throughput:

- **Overly broad locks:** multiple threads wait even when working on independent data. You can partition state into independent shards if the invariant allows.
- **Deadlock:** two threads acquire multiple locks in opposite orders. Use a global lock ordering and limit callback invocations inside locks.
- **Long-running compute callbacks:** `ConcurrentHashMap.compute` can block competing updates on related entries while the callback is running; avoid I/O or heavy computation inside callbacks.
- **Backpressure:** producers push work into a queue faster than consumers drain it, increasing backlog and latency. Choose bounded queues and rejection/timeout policies where appropriate.
- **Write-heavy copy-on-write:** frequently creates copy overhead and GC pressure. Do not use it for large, continuously modified lists just for convenient iteration.
- **CAS retries:** atomic solutions do not automatically have low latency under high contention. Measure retry counts and p95/p99 before drawing conclusions.
- **Lack of atomic snapshots:** `size()` statistics, map traversal, or reading multiple keys during updates can still yield inconsistent views; explicitly document their approximate nature.

When benchmarking, always use workloads of the same size, proper warm-up, wait for tasks to complete, and monitor **successful throughput**, latency, contention, CPU, GC, and errors. **A fast result that violates an invariant is not a valid optimization.**

## 12. How to Verify Your Own Thread-Safe Code

1. **Write invariants as concrete conditions**: "each job is claimed only once", "counter equals the number of successful increments", "sum A+B remains constant".
2. **List every read/write path**, including iterators, callbacks, getters, snapshots, background threads, and external APIs that might modify a backing collection.
3. **Specify the atomic scope** of each operation that must take effect as a single step. Ask: "between these two method calls, can another thread interleave?".
4. **Read the exact implementation contract**, not just the interface. A plain `Map`, a synchronized wrapper, and `ConcurrentHashMap` have different guarantees.
5. **Choose a single-step API or lock the entire sequence**: `putIfAbsent`, `compute`, `poll`; or a shared lock/ownership/immutable snapshot when the invariant is broader.
6. **Design coordinated race tests**, using `CountDownLatch`/`CyclicBarrier` to force dangerous interleavings. Do not use `Thread.sleep` as proof of ordering.
7. **Await and check every task** via `Future.get()`/`join()`; if a task in an executor fails without reading the Future, the test may falsely report green.
8. **Assert during updates**, not just after all tasks finish. A multi-field snapshot can be temporarily wrong and then become right again at the end.
9. **Test failures and cancellation**, ensuring `finally` releases locks/closes resources; queues do not grow unboundedly and compute callbacks do not carry unexpected side effects.
10. **Measure performance once correct**, checking contention, backlog, CPU/GC, and p99 rather than just operations/s.

Stress tests can catch regressions, but they cannot prove the absence of all races. Reasoning based on the **Java Memory Model, business invariants, and collection contracts** is the foundation.

## 13. Common Misconceptions

1. **"Because the collection is thread-safe, any code using it is thread-safe."** False when the code contains multi-call compound actions.
2. **"SynchronizedMap cannot have lost updates."** The wrapper protects operations per its contract; separate `get` and `put` calls can still lose updates.
3. **"If I see the key does not exist, my put is guaranteed to be first."** Another thread can insert the key after the check; use `putIfAbsent`.
4. **"ConcurrentHashMap makes transferring money between two keys atomic."** `compute` is atomic per mapping/key, not automatically across two keys.
5. **"size() > 0 guarantees get(0) will succeed."** Another thread can remove the element after size is read.
6. **"isEmpty() == false guarantees take() will not block."** Another consumer can drain the queue; choose `poll/take` per the contract.
7. **"A concurrent iterator provides a consistent snapshot."** Weakly consistent iterators do not hold a fixed version of the entire map.
8. **"The iterator didn't throw ConcurrentModificationException, so it's safe."** Fail-fast is only best-effort; it is not synchronization.
9. **"CopyOnWriteArrayList immediately shows new elements in an old iterator."** The iterator is a snapshot; create a new iterator if you want the newer version.
10. **"Per-key atomicity is atomic with external databases and services."** Side effects outside the map are not automatically transactional.
11. **"Once a HashMap is wrapped with synchronized, other callers can still use the backing map directly."** Bypassing the wrapper breaks the protocol.
12. **"Use sleep to prevent threads from interleaving."** Sleep does not establish happens-before or mutual exclusion.
13. **"No need to check Futures."** Tasks can throw exceptions and the final test state may not adequately reflect the failure.
14. **"Fixing only the writers is enough."** Multi-field snapshot readers must also follow the consistency mechanism.

## 14. Self-Check Questions

1. Two threads perform `get("x")` then `put("x", old+1)` on `Collections.synchronizedMap`. Can updates be lost? **Yes**, because two separate operations are not wrapped in a single critical section.
2. Which API is suitable for inserting `id -> "running"` only when no mapping exists in `ConcurrentHashMap`? **`putIfAbsent`**.
3. Which API is suitable for incrementing a counter associated with a key in `ConcurrentHashMap`? **`compute` or `merge`**, per the class's atomic contract.
4. Why should a `compute` callback not make slow I/O calls or modify other mappings of the same map? **It can force competing updates to wait and violate callback/progress constraints**.
5. With `ConcurrentLinkedQueue`, why does `peek` then `poll` not guarantee retrieving the exact element just seen? **Another consumer can take the head in between**.
6. If two consumers call `poll` concurrently on a queue with only one item, how many consumers can receive that item? **At most one**.
7. How should you iterate a `Collections.synchronizedList` when other modifiers use the same wrapper? **Hold `synchronized(list)` throughout the entire iteration**.
8. Is a `ConcurrentHashMap` iterator an atomic snapshot? **No**, it is weakly consistent.
9. Does a `CopyOnWriteArrayList` iterator created before `list.add("B")` see B? **No**, the iterator reads the old snapshot.
10. An invariant is `balanceA + balanceB == 100`. Why do two separate `compute` calls not protect the invariant for an observer? **There is an intermediate gap between the two updates**.
11. Why might a test that only checks data after all threads finish miss a bug? **While running, a reader can observe an invalid intermediate state that later becomes valid again**.
12. What must accompany the claim "this is a thread-safe collection"? **Explicitly stating the contract of each operation, iterator behavior, compound action limits, and the invariants that must be protected**.

## Conclusion

**A thread-safe collection protects the operations guaranteed by the collection's own contract; it does not automatically turn a sequence of business operations into a transaction.** For compound actions, identify the invariant and data scope: use `ConcurrentHashMap.compute/putIfAbsent/replace` for **single-key** updates, `poll` for **claiming a queue element**, `synchronized(wrapper)` for **a sequence on a synchronized collection**, and **a shared lock/ownership/immutable snapshot** for multi-field or multi-key invariants.

Always distinguish thread safety, atomicity, and snapshot consistency; verify correctness first, then measure performance.

## Java SE 17 References

- [Collections.synchronizedList / synchronizedMap](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/Collections.html): external synchronization requirements during iteration and synchronized wrapper contract.
- [ConcurrentHashMap](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/concurrent/ConcurrentHashMap.html): `compute`, `merge`, `putIfAbsent`, weakly consistent iterators.
- [ConcurrentLinkedQueue](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/concurrent/ConcurrentLinkedQueue.html): `poll` and concurrent queue semantics.
- [BlockingQueue](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/concurrent/BlockingQueue.html): `take`, `offer`, `poll`, timeouts.
- [CopyOnWriteArrayList](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/concurrent/CopyOnWriteArrayList.html): snapshot iterators and write-copy tradeoff.
- [Java Language Specification 17, Chapter 17](https://docs.oracle.com/javase/specs/jls/se17/html/jls-17.html): threads, locks, happens-before, and the Java Memory Model.

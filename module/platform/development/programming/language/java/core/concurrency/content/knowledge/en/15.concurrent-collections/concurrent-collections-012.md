# Choosing a Concurrent Collection by Read/Write Ratio and Ordering Requirements in Java

## 1. Why Is a Thread-Safe Collection Not Necessarily the Right Choice?

Java has many collections supporting concurrent access: `ConcurrentHashMap`, `ConcurrentSkipListMap`, `CopyOnWriteArrayList`, `ConcurrentLinkedQueue`, `LinkedBlockingQueue`, `ArrayBlockingQueue`, `PriorityBlockingQueue`, synchronized wrappers, and many other structures. They each solve part of the problem of sharing data across threads, but **no single collection is optimal for every read/write pattern and every kind of ordering**.

For example:
- A configuration list that is read millions of times and updated a few times a day fits a snapshot mechanism, even though each modification incurs a copy.
- An event-counting map updated continuously should not mechanically use a copy-on-write list or a global lock.
- A task processed in **FIFO** order cannot arbitrarily be replaced by a priority queue: the dequeue contract has changed.
- A map that must iterate keys in **ascending order** differs from a map that only needs fast key lookup.
- A queue used to throttle producers when consumers are slow needs **capacity/backpressure**, which an unbounded queue cannot provide on its own.

**Key takeaway:** choosing a collection must be based on **the type of read/write operations, number of contending threads, element cost, ordering requirements, iterator consistency, boundedness/backpressure, and business invariants**, not just an "80% reads, 20% writes" ratio.

This lesson belongs to **Concurrent Collections** in **Java Advance - concurrency** and focuses on **"Choosing a collection by read/write ratio and ordering"** in Java SE 17+. It does not use Spring-specific frameworks or APIs because Spring concurrency has its own chapter.

After this lesson, you will be able to:
1. Classify workloads into read-mostly, write-heavy, mixed, queue/stream, and sorted/range query.
2. Distinguish **insertion order**, **key/comparator order**, **FIFO**, **priority order**, **encounter order**, **fairness**, and **global ordering under concurrency**.
3. Choose between `ConcurrentHashMap` and `ConcurrentSkipListMap`; between `CopyOnWriteArrayList` and synchronized lists; and among nonblocking, blocking, bounded, and priority queues.
4. Understand **snapshot, weakly consistent, and fail-fast iteration**, avoiding the mistake of trusting a concurrent collection's iterator as an absolutely consistent transaction/snapshot.
5. Identify **single-method** atomicity, **check-then-act** hazards, and non-atomic operations across multiple collections/keys.
6. Design benchmark experiments based on real read/write ratios and verify correctness, ordering, and backpressure.
7. Run complete Java 17 programs with deterministic output when concurrency is controlled.

## 2. Read/Write Ratio Must Be Measured by Operation Type

A ratio such as `read:write = 95:5` only makes sense if the denominator and the types of reads and writes are clearly defined. For example:

- `get(key)` is a short read operation, unlike `forEach` scanning an entire map of one million entries.
- `contains` or `size` has a different cost and meaning from `take()` on a queue.
- `add(element)` on a copy-on-write list typically creates a copy of the backing array, unlike `put` into a `ConcurrentHashMap`.
- `computeIfAbsent` is an operation capable of atomically updating a mapping, not simply equivalent to one read followed by one write.
- `removeIf` is a bulk operation over many elements, not "one write" in terms of cost.
- Reading a list by index differs from iterating a snapshot; writing at the head of a list differs from writing at the tail.

### Three Basic Workloads

**Read-mostly:** many `get/contains/iteration` calls, few `put/add/remove` calls. Examples include listener lists registered at startup, configurations published occasionally, and metadata that rarely changes.

**Mixed:** many readers and writers operating concurrently, typically `get/put/remove/compute`. Examples include session registries, key-value caches, and online user status.

**Write-heavy:** many threads continuously updating, enqueuing/dequeuing, or incrementing. Examples include event counters, work queues, state transitions, and logging intake.

**Do not try to measure a read/write ratio without knowing whether a read is a snapshot or a point lookup, and whether a write is an append, replace, or remove.** A 99%-read workload where every read must hold a lock and traverse the entire dataset still suffers significant contention and latency.

### A Ratio Is Not Enough; More Variables Are Needed

A workload profile should record at least:

| Question | Example | Why it determines the collection |
| --- | --- | --- |
| How are reads performed? | `get(key)`, `get(index)`, `forEach` | Access cost and iterator semantics differ |
| How are writes performed? | `add`, `remove`, `merge`, `compute` | Copying, contention, and atomicity differ |
| Read/write ratio at peak? | 99:1, 70:30, 20:80 | Daily averages can hide write bursts |
| Number of concurrent threads? | 2, 16, 200 | Degree of contention and lock behavior |
| Average/peak size? | 100, 100,000, 10 million | Copy-on-write cost and memory footprint |
| How heavy are elements? | Small ref vs large object graph | Allocation, GC, and cache cost |
| What ordering is required? | FIFO, sorted key, priority, insertion | Collection type and comparator |
| Is a consistent snapshot needed? | All elements at the same point in time | Weakly consistent iterator may not suffice |
| Is backpressure needed? | Capacity 1,000, producers must wait | Bounded `BlockingQueue` |
| Are deadlines/cancellation needed? | `poll(timeout)`, interruption | Choose appropriate blocking/timed API |
| Are there multi-key invariants? | Transferring money between two accounts | Per-key atomicity is not enough |
| Ordering across multiple producers? | Global sequence / per-source ordering | FIFO queue does not define every race |

There is no JDK-guaranteed "90% reads threshold" for `CopyOnWriteArrayList`. You must account for **write cost ~ collection size** and the **read pattern**, then measure on a real workload.

## 3. Multiple Meanings of Ordering: Easiest to Choose Wrong

The word "ordered" in Java concurrency can refer to completely different contracts.

### 3.1. Insertion Order

In a sequential collection like `LinkedHashMap` or `LinkedHashSet`, iteration can preserve insertion order (depending on mode and contract). However, they are **not thread-safe on their own**. Using `LinkedHashMap` directly from multiple reading/writing threads is unsafe.

If an **insertion-order snapshot** is needed, you can capture the data inside a critical section or publish an immutable snapshot after each batch update, depending on write frequency. Do not replace `ConcurrentHashMap` with `LinkedHashMap` and let multiple writers run in parallel without synchronization.

### 3.2. Sorted Order by Key/Comparator

`ConcurrentSkipListMap<K,V>` maintains keys in **sorted order** according to natural ordering or a comparator, supporting `firstKey`, `lastKey`, `floorKey`, `ceilingKey`, `subMap`, `headMap`, and `tailMap`.

**Sorted by key is not insertion order.** If you insert key 30, then 10, then 20, iterating in ascending key order still visits 10, 20, 30. If the comparator cannot distinguish two keys (`compare(a,b) == 0`), they may be treated as the same key under map ordering; the comparator must be consistent with domain identity.

`ConcurrentSkipListSet` serves similar requirements for a set of sorted keys. In return, ordered/range operations have different costs and structures from a hash table; it is not faster than `ConcurrentHashMap` by default for point lookups.

### 3.3. FIFO — First In, First Out

`ConcurrentLinkedQueue`, `LinkedBlockingQueue`, and `ArrayBlockingQueue` provide a **FIFO contract** for elements enqueued in a well-defined order.

However, when multiple producers call `offer()` concurrently, the **absolute order between two overlapping calls** is not automatically determined by log order, timestamps taken by individual threads, or the order in which workers are scheduled by the OS. Successful operations have an effective order according to the queue protocol; if the business requires "the order requests arrived at the gateway", you must assign a sequence at the **exact ingress point** and apply appropriate handling.

Queue FIFO also **does not guarantee completion order** when multiple consumers process items in parallel:

~~~text
Queue dequeues in order: A, then B.
Consumer 1 processes A in 500ms.
Consumer 2 processes B in 10ms.
Result B may be published before result A.
~~~

If output must complete in dequeue order, you need a separate reorder/sequence/commit layer, or sequential processing.

### 3.4. Priority Order

`PriorityBlockingQueue` orders elements by **priority / natural ordering or a comparator**, not by general FIFO. Higher-priority elements according to the comparator are dequeued first; in Java `PriorityQueue` semantics, the smallest element according to the comparator is at the head.

**There is no constructor-enforced bounded capacity in `PriorityBlockingQueue`** like in `ArrayBlockingQueue`. It is structurally unbounded (though of course limited by memory resources). `put()` does not create backpressure like a bounded queue.

For equal priorities, `PriorityBlockingQueue` **does not guarantee stable ordering**. If a tie-breaker is needed, include a sequence number in the comparator. Even then, when workers pull items in parallel, **completion order** can still differ from priority order.

### 3.5. Waiting-Thread Fairness vs. Item Order

`ArrayBlockingQueue(int capacity, boolean fair)` supports a fairness policy for **the order in which waiting producer/consumer threads are granted access**. `fair=true` does NOT mean:
- The queue becomes a priority queue.
- Tasks finish processing in enqueue order in a multi-consumer system.
- Concurrent producers create an external timestamp ordering outside the queue.

Fairness typically trades throughput for reduced variance/starvation among blocked threads; weigh actual latency and contention.

### 3.6. Encounter Order / Snapshot Order

`CopyOnWriteArrayList` preserves element order as a List in the **backing array snapshot** at the time the iterator is created; the iterator does not reflect subsequent writes. Meanwhile, `ConcurrentHashMap` has no meaningful key iteration order. A `ConcurrentSkipListMap` iterator follows sorted key order, but can be weakly consistent when concurrent writers modify the map.

**Conclusion:** before asking "which collection is ordered?", you must answer **ordered by what, at what point in time, under what concurrent writers, and what order the output must preserve**.

## 4. Map Selection Matrix: ConcurrentHashMap or ConcurrentSkipListMap?

| Criterion | `ConcurrentHashMap<K,V>` | `ConcurrentSkipListMap<K,V>` |
| --- | --- | --- |
| Thread-safe concurrent access | Yes | Yes |
| Key iteration order | **Not guaranteed** | Ascending by comparator/natural order |
| Point key lookup | Hash-based; generally suited for fast `get/put/compute` | Sorted structure; supports range/navigation |
| Range `subMap/headMap` | Not a core API | Yes |
| `firstKey/ceilingKey` | Not supported as a `NavigableMap` | Yes |
| Iterators with concurrent writes | Weakly consistent | Weakly consistent, following the view's key ordering |
| Global atomic snapshot | No; aggregate reads may see changing state | No; bulk operations are not atomic |
| `null` keys/values | Not supported | Not supported |
| Multi-key transaction | Not built in | Not built in |
| Common use | Registry, counters, cache lookup | Key-sorted leaderboard, time index, range query |

**Prefer `ConcurrentHashMap` when:** the primary goal is key-based lookup/update without iteration-order requirements; use `putIfAbsent`, `compute`, `merge`, and conditional `replace` per key to avoid check-then-act.

**Prefer `ConcurrentSkipListMap` when:** business requirements **reading in key order or querying key ranges** are core; and you accept the overhead of a sorted structure.

### What NEITHER Provides

- Neither automatically creates an atomic transaction across **two different keys**.
- Neither guarantees that `size()` followed by `get()` reflects the same snapshot while writers are running.
- Neither turns a `for-each` loop into an **instantaneous snapshot** of the entire map.
- Neither automatically makes mutable objects stored as values thread-safe.
- Neither allows map keys whose comparator/`hashCode`/`equals` are unstable due to mutated fields.

### Observed Hash Order Is Not a Contract

In a given run, you might observe `ConcurrentHashMap`'s iterator printing keys in insertion order or seemingly ascending order. That is merely an artifact of that specific data/hash state, **not an API guarantee**. Changing the JDK, resizing, key distribution, or thread interleaving can change it.

When you only need to print a report **in key order at a point in time after writers have stopped**, you can copy into a `TreeMap` to sort. If writers are still running, copying from a `ConcurrentHashMap` is not an **atomic snapshot** on its own.

## 5. Example 1 — Write-Heavy ConcurrentHashMap, Reading Results After Join

Problem: four threads update the counters `apple` and `banana`, each adding 1,000 times to each key. The safe pattern uses `merge`, performing read-modify-write **atomically per key**.

Create file **`ConcurrentMapRatioDemo.java`**:

~~~java
import java.util.Map;
import java.util.TreeMap;
import java.util.concurrent.ConcurrentHashMap;
import java.util.concurrent.ExecutorService;
import java.util.concurrent.Executors;
import java.util.concurrent.Future;
import java.util.concurrent.TimeUnit;

public class ConcurrentMapRatioDemo {
    public static void main(String[] args) throws Exception {
        ConcurrentHashMap<String, Integer> counts =
                new ConcurrentHashMap<>();
        ExecutorService pool = Executors.newFixedThreadPool(4);

        try {
            Future<?>[] jobs = new Future<?>[4];
            for (int w = 0; w < jobs.length; w++) {
                jobs[w] = pool.submit(() -> {
                    for (int i = 0; i < 1_000; i++) {
                        counts.merge("apple", 1, Integer::sum);
                        counts.merge("banana", 1, Integer::sum);
                    }
                });
            }

            for (Future<?> job : jobs) {
                job.get();
            }

            Map<String, Integer> sortedAfterCompletion =
                    new TreeMap<>(counts);

            System.out.println("apple=" + counts.get("apple"));
            System.out.println("banana=" + counts.get("banana"));
            System.out.println("sorted=" + sortedAfterCompletion);
        } finally {
            pool.shutdown();
            pool.awaitTermination(1, TimeUnit.MINUTES);
        }
    }
}
~~~

Run with JDK 17+:

~~~bash
javac ConcurrentMapRatioDemo.java
java ConcurrentMapRatioDemo
~~~

Stdout when there is no external exception/interruption:

~~~text
apple=4000
banana=4000
sorted={apple=4000, banana=4000}
~~~

**Explanation:**
- `merge("apple",1,Integer::sum)` is a per-key update per the `ConcurrentHashMap` contract, avoiding the buggy separate `get` then `put` pattern.
- Four workers, 1,000 iterations each, so each key reaches 4,000.
- `main` waits for all `Future.get()` calls before copying the map; at that point **no demo writers are active**, so the copied snapshot is stable.
- `TreeMap` is **only used to output sorted results** after workers have stopped; copying does not turn the original map into an ordered one.
- Do not print `counts.toString()` directly and claim an ordering, because `ConcurrentHashMap` has no ordering contract.

### If the Workload Is Actually a Counter

If many threads add to **a single hot key**, updating `Integer` via `merge` can suffer contention. `ConcurrentHashMap<String,LongAdder>` with `computeIfAbsent(k, x -> new LongAdder()).increment()` is a common frequency-counting pattern. However, reading `LongAdder.sum()` while writes are ongoing is **not an atomic snapshot** of all updates; and if you remove/replace a `LongAdder` entry, you must define ownership/lifecycle so increments are not lost.

Do not apply `LongAdder` to problems requiring multi-key transactions or linearizable counts across multiple variables at every instant.

## 6. Example 2 — Sorted Keys and Range Queries with ConcurrentSkipListMap

We need to store integer keys and iterate in ascending order regardless of insertion order. `ConcurrentSkipListMap` maintains key ordering.

Create file **`SortedConcurrentMapDemo.java`**:

~~~java
import java.util.concurrent.ConcurrentSkipListMap;

public class SortedConcurrentMapDemo {
    public static void main(String[] args) {
        ConcurrentSkipListMap<Integer, String> map =
                new ConcurrentSkipListMap<>();

        map.put(30, "thirty");
        map.put(10, "ten");
        map.put(20, "twenty");
        map.put(40, "forty");

        System.out.println("keys=" + map.navigableKeySet());
        System.out.println("first=" + map.firstKey());
        System.out.println("ceiling25=" + map.ceilingKey(25));
        System.out.println("range=" + map.subMap(20, true, 40, false));
    }
}
~~~

Run:

~~~bash
javac SortedConcurrentMapDemo.java
java SortedConcurrentMapDemo
~~~

Stdout (with no concurrent writer in the demo):

~~~text
keys=[10, 20, 30, 40]
first=10
ceiling25=30
range={20=twenty, 30=thirty}
~~~

When multiple writers modify the map concurrently:
- Navigation/range views still obey comparator ordering for the elements they observe.
- Iterators are **weakly consistent**, and may or may not see some concurrent updates.
- `subMap` creates a **range view**, not an immutable copy or an atomic snapshot of the entire range.
- If the business requires a range report at the **same logical point in time**, you need a snapshot/locking/versioning protocol outside the collection.

### The Comparator Decides Whether "Two Keys Are the Same"

Example using a case-insensitive string comparator:

~~~java
ConcurrentSkipListMap<String, Integer> m =
        new ConcurrentSkipListMap<>(String.CASE_INSENSITIVE_ORDER);
m.put("ABC", 1);
m.put("abc", 2);
~~~

This is a snippet; because the comparator treats both strings as equal for ordering, the two `put` calls affect **the same mapping according to the comparator**, rather than creating two independent keys as `String.equals` would. The comparator must be chosen from **the definition of data identity**, not merely display criteria.

## 7. Read-Mostly Lists: CopyOnWriteArrayList

`CopyOnWriteArrayList<E>` has a distinct trade-off:
- Updates such as `add` or `set` typically create a **copy of the backing array** and publish the new version.
- Reads/iteration can access a stable backing array without needing the writer's lock for each element.
- Iterators follow a **snapshot** at creation time. Subsequent additions, removals, or modifications **do not appear in older iterators**.
- Iterators do not support `remove/set/add` through the iterator itself; those operations throw `UnsupportedOperationException`.
- The list preserves **index order of the snapshot version**, not sorted key order.
- `null` elements are permitted by the class contract, unlike many concurrent maps/queues.

**Good when:** the dataset is relatively small, reads/iterations are very frequent, writes are rare, and iterators must not be blocked by concurrent updates. Examples include listener lists, callbacks, and feature flags published in batches.

**Bad when:** the collection is large and continuously undergoes `add/remove/set`, because every update pays a copy cost proportional to array size along with allocation/GC pressure. A write burst makes a read-heavy average ratio fail to reflect peak cost.

### What Is Immutable About the Snapshot?

A snapshot iterator fixes **the set of references and element order** of the backing array at creation time. It **does not deep-copy referenced objects**. If an element is a mutable bean and another thread mutates that bean, the list snapshot **does not freeze the bean's internal state**.

This is the difference between:
- **A snapshot of the List structure**.
- **An immutable snapshot of the entire object graph**.

If you need a truly immutable snapshot, use **immutable elements** (for example, records with immutable fields) or deep-copy according to business requirements.

## 8. Example 3 — Snapshot Iterator and Writes to CopyOnWriteArrayList

Create file **`CopyOnWriteReadMostlyDemo.java`**:

~~~java
import java.util.ArrayList;
import java.util.Iterator;
import java.util.List;
import java.util.concurrent.CopyOnWriteArrayList;

public class CopyOnWriteReadMostlyDemo {
    public static void main(String[] args) {
        CopyOnWriteArrayList<String> listeners =
                new CopyOnWriteArrayList<>();

        listeners.add("alpha");
        listeners.add("beta");

        Iterator<String> snapshot = listeners.iterator();
        listeners.add("gamma");
        listeners.remove("alpha");

        List<String> oldView = new ArrayList<>();
        snapshot.forEachRemaining(oldView::add);

        System.out.println("snapshot=" + oldView);
        System.out.println("current=" + listeners);
    }
}
~~~

Compile and run:

~~~bash
javac CopyOnWriteReadMostlyDemo.java
java CopyOnWriteReadMostlyDemo
~~~

Stdout:

~~~text
snapshot=[alpha, beta]
current=[beta, gamma]
~~~

**Why?**
1. The `snapshot` iterator was created when the list contained `alpha,beta`.
2. `add("gamma")` and `remove("alpha")` changed the current backing array version.
3. The old iterator still traverses the references of the old version.
4. When printing `listeners` itself, we see the current contents `beta,gamma`.

The example executes sequentially to isolate snapshot semantics from scheduler timing. When writers run concurrently, older iterators still use the snapshot of the list structure, but as noted, **mutable fields of elements are not frozen**.

### Iterator.remove() Is Unsupported

~~~java
Iterator<String> iterator = listeners.iterator();
iterator.remove(); // UnsupportedOperationException
~~~

This is an illustrative snippet. If you need to remove elements, use the collection method `listeners.remove(x)` or an appropriate update operation, understanding that it may create a new backing array copy.

### Read-Heavy Does Not Mean "CopyOnWrite for Every Map"

`CopyOnWriteArrayList` is a **List**, not a replacement for `ConcurrentHashMap`:
- Looking up an element with `contains` can scan linearly.
- There is no `get(key)` like a map.
- Duplicates, list positions, and callback order have their own semantics.
- Copying the backing array on every write is a major trade-off.

If you have a large read-mostly map, consider **an immutable map snapshot published via `volatile`/`AtomicReference`**, or `ConcurrentHashMap` if there are still many incremental updates, depending on snapshot cost and atomic read requirements.

## 9. Write-Heavy Lists: synchronizedList, Locking, or Another Architecture?

If writes to a List happen frequently, copying the entire array every time can be too expensive. One option is:

~~~java
List<String> list =
        Collections.synchronizedList(new ArrayList<>());
~~~

This snippet requires `import java.util.*;`. The wrapper uses synchronization to protect **each individual method call** through the wrapper, but it does not automatically turn **multiple calls** into a single transaction. For example:

~~~java
if (!list.contains("x")) {
    list.add("x");
}
~~~

Two threads can both see that `x` is not present and both add it, creating a duplicate. If an atomic check-then-add is needed, you must hold **the same monitor** of the list around the entire sequence:

~~~java
synchronized (list) {
    if (!list.contains("x")) {
        list.add("x");
    }
}
~~~

**Iterating a synchronizedList requires manual synchronization during traversal**:

~~~java
synchronized (list) {
    for (String value : list) {
        consume(value);
    }
}
~~~

This snippet assumes `consume` is an existing method. If you use collection views/`subList`, check the wrapper documentation for the exact monitor to use. If the `consume` callback is slow, holding the monitor throughout iteration can block writers for a long time; you can **copy a snapshot under the lock** and iterate outside the lock when appropriate.

### When Should You Change the Architecture Instead of Locking a List?

- If you continuously append and drain, use a **queue** instead of a List with `add` + `remove(0)`.
- If you need lookup by ID, use a **map** instead of scanning a List.
- If you need key ordering, use a **sorted concurrent map/set**.
- If many readers need a stable version while writers build a new batch, use **immutable snapshot + atomic publication**.
- If you need concurrent index-stable mutation, you need explicit locking/ownership; there is no general-purpose concurrent list that replaces every `ArrayList` at negligible cost.

**List ordering** also needs clarification: List index order is not thread completion order. If multiple writers call `add` concurrently, the final order is the order in which updates are accepted by the collection mechanism, not an ad-hoc logical timestamp order of the threads.

## 10. Weakly Consistent Iteration vs. Snapshot vs. Fail-Fast

Three common behaviors:

| Iterator type | Characteristics | Example |
| --- | --- | --- |
| **Fail-fast (best effort)** | May throw `ConcurrentModificationException` when illegal structural modification is detected; not a safety guarantee mechanism | `ArrayList` iterator when modified improperly |
| **Weakly consistent** | Does not throw CME merely due to concurrent updates; may reflect some changes during traversal, does not create a global snapshot | `ConcurrentHashMap`, `ConcurrentLinkedQueue`, `ConcurrentSkipListMap` |
| **Snapshot** | Traverses the backing snapshot at creation time; does not see subsequent structural changes | `CopyOnWriteArrayList` |

### A Serious Misconception

**"Does not throw `ConcurrentModificationException`" does not mean the iterator saw all records at a single point in time.** With a weakly consistent iterator, data may be observed as updates progress; this is reasonable for monitoring, scanning, or best-effort operations, but is not suitable on its own for reports that must reflect a single logical point in time.

**"Fail-fast" is also not a synchronization mechanism.** `ConcurrentModificationException` is a best-effort bug detector, not guaranteed to be thrown in every race. Do not write correctness tests relying on "it will definitely throw CME".

### A CopyOnWriteArrayList Snapshot Is Not a Snapshot of Two Collections

If you have a `CopyOnWriteArrayList` and a `ConcurrentHashMap`, reading the list iterator and then reading the map does not automatically create a **multi-collection atomic snapshot**. If an invariant requires both sources to be at the same epoch/version, publish an immutable aggregate state under a single reference, use a lock, or design a separate snapshot/transaction mechanism.

## 11. Queues: FIFO, Priority, Blocking, and Boundedness

| Collection | Dequeue order | Blocking API | Bounded? | Guidance |
| --- | --- | --- | --- | --- |
| `ConcurrentLinkedQueue<E>` | FIFO | `offer/poll` nonblocking; no `take` | Structurally unbounded | High-throughput event handoff with external load control |
| `LinkedBlockingQueue<E>` | FIFO | `put/take/offer(timeout)/poll(timeout)` | Optional capacity; default is practically very large | Producer-consumer needing blocking when empty |
| `ArrayBlockingQueue<E>` | FIFO | `put/take` and timed methods | **Fixed capacity** | Explicit backpressure and memory bound |
| `LinkedBlockingDeque<E>` | Both ends; FIFO with `putLast/takeFirst` | Blocking at both ends | Optional capacity | Work deque with distinct head/tail semantics |
| `PriorityBlockingQueue<E>` | Comparator/natural priority | `take` when empty | **No practical bounded capacity** | Priority-based scheduler, not FIFO |
| `SynchronousQueue<E>` | Direct handoff, no buffer | `put/take` wait for partner | **Capacity 0** | Producer-consumer rendezvous |
| `LinkedTransferQueue<E>` | FIFO with transfer semantics | `transfer` can wait for consumer receipt | Structurally unbounded | Direct transfer coordination when appropriate |

Here "unbounded" does not mean infinite memory: the program can still hit `OutOfMemoryError` when producers outpace consumers without backpressure.

### FIFO Queue ≠ Tasks Finish in FIFO Order

If a queue returns item A before B but there are two consumers, B can finish before A. This is a question of **processing/commit order**, not the queue's dequeue contract.

### A Bounded Queue Is a Resource Protection Mechanism

With `ArrayBlockingQueue<>(capacity)`:
- `put` waits when full.
- `offer` returns `false` when full.
- `offer(timeout)` waits for a bounded time.
- `take` waits when empty.
- `poll` returns `null` when empty.
- `poll(timeout)` waits for a bounded time.

These are business-level backpressure/timeout choices. When producers outpace consumers, a bounded queue prevents uncontrolled backlog growth, but if all producers block inside a small thread pool, you must consider **thread-starvation deadlock and throughput**. Backpressure is a pipeline-wide policy, not just a constructor argument.

### Priority Can Cause Starvation

If high-priority items keep arriving, low-priority items may wait indefinitely. `PriorityBlockingQueue` does not automatically guarantee **aging/fairness by item age**. If the business needs to prevent starvation, design an appropriate comparator/aging mechanism or scheduler, paying attention to comparator consistency and synchronization of priority fields.

## 12. Example 4 — FIFO, Capacity, and Priority: Three Different Requirements

Create file **`QueueOrderingDemo.java`**:

~~~java
import java.util.concurrent.ArrayBlockingQueue;
import java.util.concurrent.PriorityBlockingQueue;

public class QueueOrderingDemo {
    public static void main(String[] args) {
        ArrayBlockingQueue<String> fifo =
                new ArrayBlockingQueue<>(2, true);

        boolean first = fifo.offer("A");
        boolean second = fifo.offer("B");
        boolean third = fifo.offer("C");

        System.out.println("fifoAccepted=" +
                first + "," + second + "," + third);
        System.out.println("fifoPoll1=" + fifo.poll());
        System.out.println("fifoPoll2=" + fifo.poll());

        PriorityBlockingQueue<Integer> priority =
                new PriorityBlockingQueue<>();
        priority.offer(30);
        priority.offer(10);
        priority.offer(20);

        System.out.println("priorityPoll1=" + priority.poll());
        System.out.println("priorityPoll2=" + priority.poll());
        System.out.println("priorityPoll3=" + priority.poll());
    }
}
~~~

Run:

~~~bash
javac QueueOrderingDemo.java
java QueueOrderingDemo
~~~

Stdout:

~~~text
fifoAccepted=true,true,false
fifoPoll1=A
fifoPoll2=B
priorityPoll1=10
priorityPoll2=20
priorityPoll3=30
~~~

**Analysis:**
- Bounded FIFO capacity 2: `offer("C")` is rejected when full without blocking. This is observable and handleable backpressure.
- `fair=true` governs **fairness among waiting threads**, and does not change the order of A then B into priority order.
- `PriorityBlockingQueue` dequeues the smallest number according to the natural comparator first, even though items were inserted in the order 30, 10, 20.
- The example is single-threaded to test the contract; when multiple producers contend, actual enqueue order is affected by timing, and with multiple consumers, completion order is a separate concern.
- Do not rely on `PriorityBlockingQueue.iterator()` to produce a **sorted** sequence; a priority queue's iterator does not necessarily traverse in priority order. To observe priority order, use `poll/take` or snapshot and sort.

### Elements with Equal Priority

Suppose two items have the same priority. `PriorityBlockingQueue` does not guarantee they will be dequeued in FIFO insertion order. If tie-breaking is needed, include a **sequence number** in the item and comparator:

~~~java
record Job(int priority, long sequence, String payload) {}

Comparator<Job> comparator =
        Comparator.comparingInt(Job::priority)
                  .thenComparingLong(Job::sequence);
~~~

This is a snippet; it requires `import java.util.Comparator`. If multiple producers need unique sequences, use `AtomicLong.getAndIncrement()` at the point where ordering is defined. However, **acquiring the sequence and enqueuing are not a single transaction**, so if the business requires strict ingress order, design the sequence/tie-break assignment policy right at the admission boundary.

## 13. Example 5 — ConcurrentLinkedQueue and Multiple Consumers: Claiming with poll()

A concurrent FIFO queue lets multiple workers compete to take elements. If each item must be received by exactly one consumer, use **`poll()` itself to claim**, rather than a check-then-act pattern like `if (!queue.isEmpty()) queue.remove()`.

Create file **`ConcurrentQueueClaimDemo.java`**:

~~~java
import java.util.concurrent.ConcurrentLinkedQueue;
import java.util.concurrent.ExecutorService;
import java.util.concurrent.Executors;
import java.util.concurrent.Future;
import java.util.concurrent.TimeUnit;
import java.util.concurrent.atomic.AtomicInteger;

public class ConcurrentQueueClaimDemo {
    public static void main(String[] args) throws Exception {
        ConcurrentLinkedQueue<Integer> queue =
                new ConcurrentLinkedQueue<>();

        for (int i = 1; i <= 1_000; i++) {
            queue.offer(i);
        }

        AtomicInteger processed = new AtomicInteger();
        AtomicInteger sum = new AtomicInteger();
        ExecutorService pool = Executors.newFixedThreadPool(4);

        try {
            Future<?>[] workers = new Future<?>[4];
            for (int w = 0; w < workers.length; w++) {
                workers[w] = pool.submit(() -> {
                    Integer value;
                    while ((value = queue.poll()) != null) {
                        processed.incrementAndGet();
                        sum.addAndGet(value);
                    }
                });
            }

            for (Future<?> worker : workers) {
                worker.get();
            }

            System.out.println("processed=" + processed.get());
            System.out.println("sum=" + sum.get());
            System.out.println("remaining=" + queue.size());
        } finally {
            pool.shutdown();
            pool.awaitTermination(1, TimeUnit.MINUTES);
        }
    }
}
~~~

Run:

~~~bash
javac ConcurrentQueueClaimDemo.java
java ConcurrentQueueClaimDemo
~~~

Stdout:

~~~text
processed=1000
sum=500500
remaining=0
~~~

**Proof of result:**
1. The queue is pre-populated with 1,000 numbers `1..1000`, with no producer running during the consumer phase.
2. Each successful `poll()` claims exactly one item. No two consumers receive the same element from the same dequeue operation.
3. Consumers stop when `poll()` returns `null`; since there are no new producers, that is a valid termination condition for the demo.
4. `Future.get()` waits for all workers; `AtomicInteger` protects `processed/sum` during multi-threaded updates.
5. The sum of the sequence is `1000*1001/2=500500`; the queue is empty afterward.

**In production with continuous producers:** `poll()==null` only means there is **currently** no item to take, not that producers will not send more. You need a lifecycle mechanism such as a `closed` flag, poison pill, scheduler/wakeup, or an appropriate `BlockingQueue.take()`. Also do not use `ConcurrentLinkedQueue.size()` to decide a precise business invariant across multiple writers: `size()` can be O(n) and change while counting.

### FIFO Does Not Dictate Completion Time

Even though the queue hands out items in FIFO order, the four workers may process and update the aggregate in any order. Only the final result after `get()` is deterministic; no stdout like "worker 1 processed 1, worker 2 processed 2" is guaranteed.

## 14. Example 6 — Bounded BlockingQueue and Producer-Consumer

For **backpressure** and waiting for data without busy-polling, `ArrayBlockingQueue` or `LinkedBlockingQueue` with an explicit capacity is a common choice.

Create file **`BoundedPipelineDemo.java`**:

~~~java
import java.util.ArrayList;
import java.util.List;
import java.util.concurrent.ArrayBlockingQueue;
import java.util.concurrent.BlockingQueue;
import java.util.concurrent.ExecutorService;
import java.util.concurrent.Executors;
import java.util.concurrent.Future;
import java.util.concurrent.TimeUnit;

public class BoundedPipelineDemo {
    public static void main(String[] args) throws Exception {
        BlockingQueue<Integer> queue = new ArrayBlockingQueue<>(2);
        ExecutorService pool = Executors.newFixedThreadPool(2);

        try {
            Future<?> producer = pool.submit(() -> {
                try {
                    queue.put(1);
                    queue.put(2);
                    queue.put(3);
                    queue.put(-1); // Termination sentinel for a single consumer.
                } catch (InterruptedException e) {
                    Thread.currentThread().interrupt();
                }
            });

            Future<List<Integer>> consumer = pool.submit(() -> {
                List<Integer> received = new ArrayList<>();
                while (true) {
                    int value = queue.take();
                    if (value == -1) {
                        return received;
                    }
                    received.add(value);
                }
            });

            producer.get();
            System.out.println("received=" + consumer.get());
            System.out.println("remaining=" + queue.size());
        } finally {
            pool.shutdownNow();
            pool.awaitTermination(1, TimeUnit.MINUTES);
        }
    }
}
~~~

Run:

~~~bash
javac BoundedPipelineDemo.java
java BoundedPipelineDemo
~~~

Stdout when there is no external interruption/error:

~~~text
received=[1, 2, 3]
remaining=0
~~~

**Analysis:**
- Queue capacity 2 means the producer **may have to wait** if the consumer has not taken items yet; this is backpressure rather than unbounded memory backlog growth.
- One producer puts `1,2,3,-1` in order, and one consumer takes in FIFO order, so the List receives `[1,2,3]`.
- The sentinel is only for the **single-consumer** example, and `-1` is defined as a non-data value.
- If there are N consumers and you want to use poison pills, you must design the appropriate number of termination signals rather than a single sentinel, or use a separate `closed`/coordinator protocol.
- If the producer is interrupted before sending the sentinel, the consumer could wait forever; production code needs robust timeout/cancellation/shutdown handling.
- Calling `shutdownNow()` after all futures have completed in the demo is just executor cleanup; do not use it implicitly to cut off business tasks that are still committing.

### When to Use LinkedBlockingQueue?

`LinkedBlockingQueue` provides node-based FIFO with optional capacity. `new LinkedBlockingQueue<>()` defaults to capacity `Integer.MAX_VALUE`, so if producers can outpace consumers for an extended period, pass a **finite capacity** to protect the system.

`ArrayBlockingQueue` uses a backing array with fixed capacity, making it easier to control the memory footprint of references. Do not assume `ArrayBlockingQueue` is always faster than `LinkedBlockingQueue`: workload contention, operation patterns, allocation, GC, and fairness all play a role.

## 15. Choosing a Queue for Real-World Requirements

### 15.1. Nonblocking Handoff

If producers and consumers should operate without waiting for the queue to have items, use `ConcurrentLinkedQueue.offer/poll`. The caller decides what to do when `poll()==null`, such as stopping a batch, waiting for a signal at another layer, or returning to the scheduler. Do not write loops like:

~~~java
while (queue.isEmpty()) {
    // busy-spin without timeout / without efficient waiting
}
~~~

This is an anti-pattern when there is no backoff/yield strategy or event notification; it can peg the CPU.

### 15.2. Blocking FIFO with Backpressure

If consumers should wait when items are missing and producers should wait when the queue is full, use a `BlockingQueue` with capacity:
- `ArrayBlockingQueue`: fixed bounded array, with optional fairness.
- `LinkedBlockingQueue(capacity)`: linked FIFO with configurable capacity.

Choose timed `offer/poll` if there are deadlines or you do not want indefinite blocking. On shutdown, transition state according to the proper protocol and wake up waiting workers.

### 15.3. Direct Handoff

`SynchronousQueue` holds no items in a buffer. Producer `put` waits for a matching consumer to receive; consumer `take` waits for a producer. This is a **rendezvous** model, not a queue with a backlog. It can be useful when you want direct handoff without item accumulation, but you must avoid deadlocks caused by both sides running in a pool that is too small.

### 15.4. Priority Scheduling

Use `PriorityBlockingQueue` when priority order is a true contract. A key question to answer: if items have equal priority, is FIFO needed? If so, add a consistent sequence/tie-breaker. If low-priority tasks must not starve, add aging or a higher-level scheduler.

### 15.5. Double-Ended Queue

`LinkedBlockingDeque`/`ConcurrentLinkedDeque` allow adding/removing at both ends, suitable for work queues/deques when head/tail semantics are clear. If you only use `addLast/pollFirst`, you get FIFO behavior; if you use `push/pop`, you get LIFO stack behavior. Saying "a deque is ordered" does not sufficiently describe the contract.

## 16. Atomicity: A Thread-Safe Collection Does Not Create Transactions

A thread-safe collection protects the contract of each individual operation, but composed steps may not be atomic.

### 16.1. Check-Then-Act on a Map

Wrong:

~~~java
if (!map.containsKey(key)) {
    map.put(key, value);
}
~~~

Two writers can both see that the key does not exist and both put; the "only one writer creates it" requirement is violated. With a concurrent map, use `putIfAbsent` if you only need to insert a mapping when absent:

~~~java
V old = map.putIfAbsent(key, value);
~~~

This snippet assumes appropriate `K/V` types and `map`. If the value must be computed, use `computeIfAbsent` with a mapping function that does not recursively modify the same map and avoids long I/O or side effects when the implementation's contract expects a short function.

### 16.2. Updating a Per-Key Counter

Wrong:

~~~java
map.put(key, map.get(key) + 1);
~~~

Each `get`/`put` call may be thread-safe, but the combination is not atomic. Use `compute` or `merge` for single-key mappings, or `LongAdder` for frequency counters when the semantics fit.

### 16.3. Per-Key Atomicity Is Not Multi-Key Atomicity

Suppose we transfer 100 units from account A to B stored in a `ConcurrentHashMap`:

~~~java
balances.compute("A", (k, v) -> v - 100);
balances.compute("B", (k, v) -> v + 100);
~~~

Each per-key update may be atomic individually, but there is a moment where an observer sees A reduced while B has not yet increased. If an invariant requires the total balance to remain constant across **every business snapshot**, you need a lock/transaction protocol protecting both keys, or to publish an immutable aggregate state via an atomic reference. No single `ConcurrentHashMap` method creates a multi-key transaction for you.

### 16.4. size/isEmpty Does Not Replace Claiming

On a concurrent queue, calling `isEmpty()` followed by `remove()` races with other consumers. Use `poll()` to claim an item; when waiting is required, use `take()`. On a map under concurrent writes, `size()` and `containsValue()` are not always suitable as decision-critical status; they are usually only useful for monitoring/estimation.

### 16.5. Mutable Values Still Need Protection

`ConcurrentHashMap<String,ArrayList<Event>>` does not make operations on the inner `ArrayList<Event>` instances thread-safe. The collection protects **the map structure**; objects stored as values have their own contracts. Choose immutable values, concurrent value types, or an explicit lock/ownership protocol.

## 17. Consistent Snapshots and Publishing Immutable State

When the requirement is "very many readers, writers update in batches, and each reader needs **a consistent version of the data**", it can be better to use an **immutable snapshot** instead of a mutable concurrent collection directly.

Pattern:

~~~java
record Config(int version, Map<String, String> options) {}

AtomicReference<Config> current = new AtomicReference<>(
        new Config(1, Map.of("mode", "safe")));

Config before = current.get();
Config next = new Config(2, Map.of("mode", "fast"));
current.set(next);
~~~

This snippet requires imports `java.util.Map` and `java.util.concurrent.atomic.AtomicReference`. `Map.of` creates an immutable map; the `Config` object is a record holding immutable references in the example.

- A reader fetches `Config snapshot = current.get()` once, then uses **that exact object** for all fields that must be consistent.
- The writer builds the entire new state **before** publishing with `set`/`compareAndSet`.
- A single reference read is atomic, fitting read-heavy/write-rare workloads that need a coherent snapshot across multiple fields.
- If multiple writers contend, use a `compareAndSet`/update loop to avoid lost updates; a blind `set` can overwrite another writer's state.
- Do not reuse an old mutable map and mutate it after publishing; readers could still see the state changing.

**CopyOnWriteArrayList** provides a snapshot of its backing array per iterator, whereas immutable aggregate publication lets you organize **multiple related structures** under one version. These are two different options, depending on invariants.

## 18. Benchmarks and Read/Write Ratio: What Should You Measure?

To choose well, you cannot just look at "Concurrent" in the class name. Measure a representative workload across multiple ratios and contention levels:
- 99:1, 90:10, 50:50, 10:90, and write bursts, but use them only as **test scenarios**, not default optimization targets.
- Point lookup, index read, full iteration/range query, add/remove, put/compute/merge.
- Small/medium/large datasets, realistic element/value sizes, and number of hot keys.
- 1, 2, 4, 8, ... threads depending on machine and CPU quota.
- Producer/consumer rates, capacity/backpressure, and rate of dropped/blocked operations.
- Ordering correctness: sorted keys, FIFO dequeue, priority tie-breaking, snapshot epoch, and result completion order.
- Allocation/GC, p95/p99 latency, throughput, CPU utilization, lock contention, and memory footprint.

### Suggested Experiment Matrix

| Workload | Candidate collections | Key metrics |
| --- | --- | --- |
| 99% list iteration, rare writes | `CopyOnWriteArrayList` vs synchronized immutable snapshot | p99 iteration latency, write copy cost, GC |
| Frequent map get/merge | `ConcurrentHashMap` vs `ConcurrentSkipListMap` (only when ordering is truly needed) | Per-key throughput, contention, latency |
| Sorted range query | `ConcurrentSkipListMap` vs sorted snapshot publication | Range latency, freshness, memory |
| FIFO handoff | `ConcurrentLinkedQueue` vs bounded `BlockingQueue` | Consumer wakeup, throughput, CPU spin |
| Bounded producer-consumer | `ArrayBlockingQueue` vs `LinkedBlockingQueue(capacity)` | Queue wait time, backlog, memory |
| Priority tasks | `PriorityBlockingQueue` + policy | Ordering, starvation, latency by priority |
| Multi-field snapshot read | Immutable aggregate `AtomicReference` | Coherent versions, write latency |

### JMH and Measuring System Conditions

For microbenchmarks, use **JMH**:
- Warm up the JVM/JIT before measuring.
- Avoid dead-code elimination by consuming results.
- Avoid logging/console output on the hot path.
- Use multiple iterations/forks, and verify correctness outside the benchmark.
- Record JVM, OS, CPU, cores/threads, GC, and collection sizes.
- Be careful of benchmarks sharing a single hot lock or hot key that skews the ratio.

Do not state a result like "ConcurrentHashMap is 3x faster than SkipListMap" without measuring the actual workload. Nor should you treat a single `System.nanoTime()` sample as a universal conclusion.

### Size Workloads for Peak Moments, Not Just Averages

A configuration that is 99% reads over the whole day might have a rollout that updates the entire list in one second. With `CopyOnWriteArrayList`, every `add/remove` copies the array; a continuous write burst on a large list can cause an allocation spike. If the application has **batch updates**, you can build a new immutable snapshot and publish it once instead of 10,000 `add` calls.

## 19. Scenario-Based Selection Guide

### Scenario A: Key-Based Cache, No Ordering Needed

**Starting choice:** `ConcurrentHashMap<K,V>`. If values are computed when missing, use `computeIfAbsent` appropriately with a short callback. If true eviction/TTL/LRU is needed, a plain concurrent hash map **does not provide cache eviction on its own**; you need a cache abstraction with the right contract.

### Scenario B: Read-Many / Write-Rare Listener List

**Starting choice:** `CopyOnWriteArrayList<E>`. Iterators see a snapshot of the callback list; a listener registering or unregistering mid-dispatch does not alter the running iterator. If listener objects are mutable or callbacks have side effects, the list itself does not guarantee thread-safety for the listener.

### Scenario C: ID Registry with Sorted/Range Iteration

**Starting choice:** `ConcurrentSkipListMap<K,V>`. If point lookups dominate and sorted reports are very rare, consider `ConcurrentHashMap` + sorting a snapshot at report time (when the freshness/consistency policy allows).

### Scenario D: FIFO Producer/Consumer with Bounded Memory

**Starting choice:** `ArrayBlockingQueue` or `LinkedBlockingQueue(capacity)`. Choose `put/take` if waiting is acceptable, `offer/poll(timeout)` if deadlines are needed. Define a full-queue policy: block, reject, drop, retry, or shed load.

### Scenario E: Nonblocking Handoff with Externally Controlled Backlog

**Starting choice:** `ConcurrentLinkedQueue`. Use `poll` to claim items. If the backlog can grow without bound and there is no throttling mechanism, do not pick an unbounded queue just because it has high throughput in a small benchmark.

### Scenario F: Priority Work Queue

**Starting choice:** `PriorityBlockingQueue` when comparator order is the primary requirement. Design a sequence for tie-breaking and aging against starvation if needed. Because it is not bounded by constructor, add admission control/backpressure at an outer layer.

### Scenario G: Reading an Entire Consistent Configuration Version

**Starting choice:** immutable aggregate snapshot published via `AtomicReference`/`volatile`, or `CopyOnWriteArrayList` when only a versioned list of references is needed. If the snapshot is very large and updates are frequent, copy costs can become too high.

### Scenario H: Insertion Order Must Be Preserved with Multi-Step Atomic Mutation

There is no "JDK 17 `ConcurrentLinkedHashMap`" in the standard collections library equivalent to `LinkedHashMap` with built-in ordering and general thread-safety. You can use a synchronized wrapper and hold the lock for the entire sequence, or design immutable state publication, or choose a library with an explicit contract. **Do not assume `ConcurrentHashMap` preserves insertion order.**

## 20. Common Mistakes

| Mistake | Consequence | Fix |
| --- | --- | --- |
| Choosing a collection solely from average read/write ratio | Ignores iteration cost, bursts, and contention | Measure workload by operation and peak |
| Using `ConcurrentHashMap` and relying on iterator order | Output has no ordering contract | `ConcurrentSkipListMap` or sorted snapshot |
| Confusing sorted key order with insertion order | Data appears ordered by key, not arrival | Choose the right ordering semantics |
| Confusing FIFO with completion order | Multiple consumers finish out of dequeue order | Sequence/reorder/serial commit |
| Confusing `fair=true` with priority order | Waiting-thread policy does not change item order | Distinguish fairness from queue comparator |
| Using `PriorityBlockingQueue` when bounded backpressure is needed | Backlog can grow beyond memory limits | Admission control / bounded design |
| Using `CopyOnWriteArrayList` for a write-heavy large list | Array copies and GC spike | Choose lock / batch snapshot / different architecture |
| Assuming snapshot iterators deep-copy elements | Mutable fields can still change | Immutable elements / deep snapshot |
| Using `Collections.synchronizedList` and iterating without locking | Iteration contract is unprotected | `synchronized(list)` around traversal |
| Using `containsKey` + `put` to ensure a single creator | Check-then-act race | `putIfAbsent/computeIfAbsent` |
| Using `get` + `put` to increment | Lost update | `compute/merge/LongAdder` |
| Using `size/isEmpty` as a claim condition on a concurrent queue | Race condition, `size` can be O(n) | `poll/take` |
| Using `ConcurrentHashMap<String,ArrayList>` assuming values are safe | Values are still mutable and not thread-safe | Protect values / immutable structures |
| Using a weakly consistent iterator as an atomic audit snapshot | Missing/mixed updates across epochs | Snapshot/version/transaction |
| Trusting fail-fast CME to protect correctness | Exception is a best-effort detector | Proper synchronization or concurrent collection |
| Treating `poll()==null` as end-of-stream while producers are running | Late-arriving data is lost | Closed flag / sentinel / wakeup protocol |
| Using `PriorityBlockingQueue.iterator()` as sorted traversal | Iterator does not promise priority order | Drain with `poll` or snapshot and sort |
| Using a comparator that depends on a mutable priority field | Heap/tree invariant may not update | Immutable priority; remove/reinsert |
| Mixing multi-key updates and treating per-key atomicity as a transaction | Observers see intermediate states | Lock / immutable aggregate / transaction |
| Using an unbounded queue for uncontrolled bursts | Memory pressure / OOM | Capacity + backpressure |
| Assuming every concurrent collection supports `null` | NPE / ambiguous contract | Check class contract |
| Failing to manage executor and timeouts in blocking queue demos | Threads hang when no producer remains | Lifecycle / poison pill / interrupt / timeout |

## 21. Pre-Design Checklist

1. **Define read/write ratio:** by method calls, bytes, time, or business events?
2. **Peak workload:** do add/remove bursts break the read-mostly assumption?
3. **Ordering:** do you need sorted keys, insertion order, FIFO, priority, or output completion order?
4. **Consistency:** is weakly consistent acceptable, or is a same-epoch snapshot required?
5. **Point lookup vs. full scan:** is the read count high, or is each read expensive?
6. **Mutable elements:** does the collection protect the data inside values?
7. **Write atomicity:** single key, or invariants across multiple keys/collections?
8. **Capacity/backpressure:** can unbounded backlog growth be tolerated?
9. **Blocking policy:** wait, timeout, drop, or reject when the queue is full?
10. **Number of producers/consumers:** does high concurrency cause lock contention?
11. **Priority starvation:** do low-priority items have an aging mechanism?
12. **Fairness:** is reducing waiting-thread starvation more important than maximizing throughput?
13. **Cancel/shutdown:** does every blocking consumer have a clean termination path?
14. **Null semantics:** does the collection allow `null`? Is `poll()==null` used to signal empty?
15. **Key consistency:** are comparator/`equals`/`hashCode` stable and aligned with domain identity?
16. **Versioning:** do you need to publish an immutable snapshot synchronized across multiple fields?
17. **Memory:** what is the allocation/GC/backlog behavior during write bursts?
18. **Benchmark:** do you have a sequential baseline and correctness checks?
19. **Optimization goal:** throughput, p95 latency, memory, or fairness? You cannot always optimize all of them together.
20. **Operations contract:** does the API provide the right atomic compound method?
21. **Ordered output:** if there are multiple consumers, where does the reorder/commit policy live?
22. **Validation:** have you tested concurrent writers and readers, edge cases, timeouts, and shutdown?

## 22. Self-Check Questions and Answers

1. Does `ConcurrentHashMap` iterate in insertion order? **No**, it has no ordering guarantee.
2. When you need `firstKey/ceilingKey/subMap` concurrently with writes, which class should you look at? **`ConcurrentSkipListMap`**.
3. Does sorted by key mean FIFO? **No**, one is by comparator, the other is by enqueue order.
4. Does `CopyOnWriteArrayList.iterator()` see items added after the iterator was created? **No**, the iterator uses a snapshot of the backing array.
5. Does a snapshot iterator freeze fields of mutable elements? **No**, only the reference structure of the list.
6. If a list is 99% reads, but a writer updates 1 million elements with individual `add` calls, is `CopyOnWriteArrayList` definitely best? **No**, write copies/GC can be huge.
7. Does `Collections.synchronizedList` automatically synchronize an entire `for-each` loop? **No**, you must hold the wrapper's monitor during traversal.
8. Does `ConcurrentLinkedQueue` have `take()`? **No**, use `poll` with a separate wait/lifecycle protocol, or choose a `BlockingQueue`.
9. Does a FIFO queue guarantee workers finish processing in FIFO order? **No**, when there are multiple consumers.
10. Does `ArrayBlockingQueue` with `fair=true` order items by priority? **No**, fairness governs waiting-thread access.
11. Does `PriorityBlockingQueue` have a bounded capacity like `ArrayBlockingQueue`? **No**, separate admission control is required.
12. If two items have the same comparator priority, are they guaranteed to be dequeued in FIFO order? **No**, tie order is not guaranteed.
13. Does `PriorityBlockingQueue.iterator()` have sorted order? **It is not** guaranteed to match `poll` order.
14. Does `ConcurrentSkipListMap.subMap` create an immutable snapshot? **No**, it is a range view.
15. Is a weakly consistent iterator an atomic snapshot? **No**.
16. Does the absence of `ConcurrentModificationException` prove that updates were read from the same epoch? **No**.
17. What bug does `ConcurrentHashMap.merge` help fix? **Atomic read-modify-write on a single key**, avoiding the `get`+`put` race.
18. Do two `compute` calls updating keys A and B automatically form a transaction? **No**.
19. Does `ConcurrentHashMap<String,ArrayList>` automatically protect `add` calls on each `ArrayList`? **No**.
20. When multiple consumers compete for an item, should they claim with `isEmpty()` then `remove()`, or `poll()`? **`poll()`**.
21. Does `poll()==null` while producers are running mean the stream has ended? **No**, only that it is empty at that moment.
22. Is `ConcurrentLinkedQueue.size()` always O(1) and exact under writes? **No**, it may traverse and the result can change.
23. When you need a consistent snapshot read of multiple fields at the same version, what is the option? **Publish an immutable aggregate via an atomic reference / appropriate lock / transaction**.
24. Does `ConcurrentSkipListMap` allow `null` keys/values? **No**.
25. Does `CopyOnWriteArrayList` allow `null` elements? **Yes**.
26. Why can a `LinkedBlockingQueue` without a configured capacity be dangerous? **The default is very large; a backlog can exhaust memory**.
27. If a map needs a full LRU/TTL cache, does `ConcurrentHashMap` provide eviction on its own? **No**.
28. Why should you measure write bursts instead of only the average read/write ratio? **Bursts can cause write-copy/lock/backlog spikes**.
29. With equal priorities and a need for stability, what must you do? **Use a sequence number as a tie-breaker, assigning it at the exact ordering boundary**.
30. What is the primary optimization target? **Based on SLOs: throughput, p99 latency, memory, fairness, and correctness, not just the collection name**.

## 23. Summary

**Do not choose a concurrent collection just because it is "thread-safe".** Start from the requirements:
- **Read-mostly List + snapshot iteration:** consider `CopyOnWriteArrayList` or immutable snapshot publication.
- **Mixed/write-heavy Map without order:** `ConcurrentHashMap` with atomic per-key operations.
- **Sorted/range keys:** `ConcurrentSkipListMap` or `ConcurrentSkipListSet`.
- **FIFO nonblocking handoff:** `ConcurrentLinkedQueue` if appropriate admission control/lifecycle is in place.
- **FIFO blocking + capacity/backpressure:** `ArrayBlockingQueue` or `LinkedBlockingQueue(capacity)`.
- **Priority:** `PriorityBlockingQueue` with comparator, tie-breaker, and external backlog control.
- **Multiple fields needing a same-epoch snapshot:** immutable aggregate + atomic publication or transaction.

A read/write ratio is only **a starting point**. Ordering, atomicity, iteration consistency, boundedness, deadlines, cancellation, and ownership principles determine correctness. After choosing a candidate, **check the Java 17 contract, measure on a real workload, and verify business invariants**.

## Java SE 17 References

- [ConcurrentHashMap](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/concurrent/ConcurrentHashMap.html): atomic per-key operations and weakly consistent iteration, no ordering.
- [ConcurrentSkipListMap](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/concurrent/ConcurrentSkipListMap.html): sorted key views, navigation/range, weakly consistent.
- [ConcurrentSkipListSet](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/concurrent/ConcurrentSkipListSet.html): concurrent sorted set.
- [CopyOnWriteArrayList](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/concurrent/CopyOnWriteArrayList.html): snapshot iterator, read-mostly tradeoff.
- [ConcurrentLinkedQueue](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/concurrent/ConcurrentLinkedQueue.html): FIFO nonblocking queue, weak consistency, and `size()` cost.
- [ArrayBlockingQueue](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/concurrent/ArrayBlockingQueue.html): bounded FIFO, fairness.
- [LinkedBlockingQueue](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/concurrent/LinkedBlockingQueue.html): FIFO, optional capacity, blocking.
- [PriorityBlockingQueue](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/concurrent/PriorityBlockingQueue.html): comparator ordering, unbounded, and iterator order.
- [SynchronousQueue](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/concurrent/SynchronousQueue.html): direct handoff.
- [Collections.synchronizedList](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/Collections.html#synchronizedList(java.util.List)): manual synchronization for iteration.
- [Java Language Specification `17](https://docs.oracle.com/javase/specs/jls/se17/html/jls-17.html): memory model and happens-before.
- [JMH — Java Microbenchmark Harness](https://openjdk.org/projects/code-tools/jmh/): controlled Java benchmarking.

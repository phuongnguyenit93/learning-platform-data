# Unsafe Concurrent Use of Standard Collections in Java

An `ArrayList`, `HashMap`, or `HashSet` works properly when used according to its API contract. However, when **multiple threads access a mutable collection concurrently**, especially when at least one thread modifies its contents or structure, standard collections in `java.util` **do not provide the required synchronization on their own**. The consequences can include lost elements, inaccurate counts, reading stale data, violating internal invariants, or encountering unexpected exceptions. Not every bug manifests after running a few test trials.

This article belongs to the **Race Conditions** group and focuses on **general Java concurrency**: identifying thread-safety boundaries, analyzing race conditions, choosing protection mechanisms, and using appropriate replacement collections. It does not cover concurrency components specific to the Spring Framework.

## 1. Why aren't standard collections thread-safe by default?

Most commonly used Java collections are designed to provide efficient operations when the program **manages access properly**. For example:

- `ArrayList<E>`: a dynamic array-backed list with internal state fields such as element count and backing storage.
- `HashMap<K,V>`: a hash table with buckets and linked/tree structures for lookup, insertion, and deletion.
- `HashSet<E>`: a set backed by a `HashMap` to store unique elements.
- `LinkedList<E>`: a linked list that updates size and node links on addition or removal.
- `TreeMap<K,V>`, `TreeSet<E>`: tree structures that must maintain ordering and invariants during updates.
- `ArrayDeque<E>`, `PriorityQueue<E>`: structures maintaining head/tail pointers or a heap when adding or removing elements.

These structures **are not designed to withstand arbitrary concurrent modifications on their own**. A `list.add(x)` operation looks like a single call at the API level, but the implementation may need to read the current size, check capacity, write the element, and update the element count. When two threads interleave these steps, there is no default guarantee that the two calls produce the effect of having executed sequentially in some order.

Distinctions to keep in mind:

| Scenario | Safety Assessment |
| --- | --- |
| One thread owns an `ArrayList` and only that thread reads/modifies it | Generally safe regarding cross-thread sharing since there is no contention |
| Multiple threads only read a collection that is **no longer modified** and whose reference was safely published | Can be safe if contents are fully published and no mutable values are unexpectedly modified |
| One thread calls `add/remove` while another calls `get/iterate` | Unsafe without a coordination mechanism |
| Multiple threads concurrently call `add/remove` | Unsafe without a coordination mechanism |
| Collection wrapped with `Collections.synchronizedList` | Individual operations through the wrapper are synchronized; iteration and compound sequences still require separate consideration |
| Using `ConcurrentHashMap` or `BlockingQueue` per their contracts | Provides API-specific concurrency guarantees; does not mean every business workflow is atomic |

**`final` does not mean thread-safe.** For example, `private final List<String> tasks = new ArrayList<>();` only prevents reassigning the `tasks` reference. `tasks.add(...)` still mutates the shared list itself.

## 2. Race conditions when two threads concurrently modify a collection

A **race condition** occurs when the correctness of a program depends on the execution order and timing of interleaved operations from multiple threads, while the program has not imposed sufficient coordination rules.

Imagine two threads concurrently adding elements to a list. This is a simplified logical diagram, not a description of exact bytecode instructions across all JDKs:

```text
Initial: size = 10

Thread A                          Thread B
read size = 10
                                  read size = 10
write element A at index 10
                                  write element B at index 10
update size to 11
                                  update size to 11

add() was called twice in total
but one element may be overwritten / the count may be wrong.
```

The failure can unfold under different schedules: sometimes the result is right, sometimes wrong, or an exception is thrown. One should not assert which exact outcome will occur on a specific JDK version; that unpredictability is the danger of a program with a data race.

An easy-to-make mistake:

```java
List<Integer> results = new ArrayList<>();

// Multiple tasks running concurrently:
results.add(result);
```

This is an illustrative snippet, not a complete program. If `results` is **the same instance** and multiple workers concurrently call `add`, each call is not automatically safe just because the `result` values are immutable.

**Data races and visibility:** It is not only mutating operations that have issues. If thread A modifies the list while thread B reads its size without a happens-before relationship, B has no guarantee of seeing the update at the expected time. Reading a field after `Thread.sleep(...)` does not establish a synchronization relationship with the writing thread.

### An intentionally unsafe example to recognize the bug

The following snippet demonstrates an **anti-pattern**, not something to assert stdout against:

```java
import java.util.ArrayList;
import java.util.List;

final class UnsafeListExample {
    private final List<Integer> results = new ArrayList<>();

    void record(int value) {
        results.add(value); // Not safe if called concurrently from multiple threads.
    }

    int count() {
        return results.size(); // Also problematic if another thread is modifying it.
    }
}
```

Do not try to force-reproduce the bug by adding `Thread.sleep` calls or relying on a specific printed output. The unsafety lies in the fact that **`ArrayList`'s contract does not guarantee these concurrent operations**, even if some test runs happen to return all elements.

## 3. Typical failure modes by collection

### `ArrayList` and `LinkedList`: overwrites, wrong size, unstable iteration

When multiple threads concurrently call `add`/`remove`, updates to the element count and backing storage can race with each other. Index-based reads may not correspond to the expected state. Iterating while another thread modifies the structure may throw `ConcurrentModificationException`, skip elements, observe inconsistent state, or exhibit other unspecified behavior.

With `LinkedList`, changes to node links and size must also preserve invariants; unsynchronized sharing does not solve this.

### `HashMap` and `HashSet`: lost updates, unreliable query results

`HashMap` must maintain its buckets and corresponding entries. During resize, put, or remove, another thread reading or modifying the same map without synchronization may observe unexpected data. `HashSet` is backed by a map, so it is not immune either.

Avoid repeating absolute claims like "`HashMap` always falls into an infinite loop during resize": implementations differ across Java versions, and specific failure modes are not guaranteed by the API. The solid conclusion is **never rely on unsynchronized concurrent operations on `HashMap`**.

### `TreeMap`, `TreeSet`, `PriorityQueue`, and `ArrayDeque`

Each structure maintains internal invariants (balanced tree, heap, head/tail positions). When multiple threads mutate them, those guarantees depend on how access is coordinated. Using them unprotected does not become safe merely because APIs like `add` or `put` are concise.

If a multi-threaded producer–consumer queue is needed, consider `BlockingQueue` or `ConcurrentLinkedQueue` instead of a shared `ArrayDeque`.

### Collections containing mutable objects

Even when using a collection with built-in synchronization, **the objects stored inside remain a separate concern**:

```java
ConcurrentHashMap<String, ArrayList<String>> map = new ConcurrentHashMap<>();
// ... threads retrieve the same value and call value.add(...)
```

`ConcurrentHashMap` protects the map structure according to its contract; an `ArrayList` stored inside the map does not become thread-safe as a result. If there are multiple writers, you must protect the value, change how it is stored, or change the ownership structure.

## 4. `ConcurrentModificationException` is not a data race detector

Standard collections often have **fail-fast** iterators: if they detect a structural modification outside the iterator during traversal, they may throw `ConcurrentModificationException`.

For example, **even a single thread** can encounter this exception:

Save as `FailFastDemo.java`:

```java
import java.util.ArrayList;
import java.util.Iterator;
import java.util.List;

public class FailFastDemo {
    public static void main(String[] args) {
        List<String> names = new ArrayList<>(List.of("A", "B"));
        Iterator<String> iterator = names.iterator();

        names.add("C"); // Structural modification outside the iterator.

        try {
            iterator.next();
            System.out.println("Unexpected");
        } catch (java.util.ConcurrentModificationException e) {
            System.out.println("Detected a structural modification");
        }
    }
}
```

```bash
javac FailFastDemo.java
java FailFastDemo
```

Stdout of the example:

```text
Detected a structural modification
```

This scenario happens in **a single thread**, showing that the exception is related to how the iterator is used and does not always prove multi-threaded access.

In a concurrent environment:

- Fail-fast is **best effort**; it is not guaranteed to throw an exception for every modification from another thread.
- **Not throwing an exception does not prove the program is thread-safe**.
- Catching `ConcurrentModificationException` to ignore it and continue **does not fix** the lack of synchronization.
- If you need to remove elements while iterating in a single thread, `Iterator.remove()` (if supported by the iterator) is more appropriate than calling `list.remove(...)` outside the iterator. If multiple threads are involved, a synchronization policy or an appropriate concurrent collection is still required.

Do not use this exception as a control-flow mechanism or as a way to "test whether a collection is safe."

## 5. Three factors to guarantee: atomicity, visibility, and invariants

When protecting a shared collection, you must identify **what needs to remain consistent**, not just "add locks everywhere."

**Atomicity:** Can an operation or a business sequence of operations be observed as an uninterrupted action at the required boundary? For example, `if (!set.contains(x)) set.add(x)` is a check-then-act pattern: if two threads both check before adding, the condition "only one thread claims processing for x" can be broken, even if each individual `contains` and `add` call is thread-safe.

**Visibility:** After thread A updates the collection, does thread B have a Java Memory Model guarantee of seeing that update? A happens-before relationship can come from the same monitor lock, concurrent collection operations per their contracts, `Thread.start/join`, `Future.get`, or an appropriate synchronization mechanism.

**Invariants:** Related data must be maintained at any point where external code is allowed to observe it. For instance, a business rule might require that the total number of elements across two collections equals N; locking each collection individually may not be enough to make moving an element between the two collections an atomic transaction.

The goal is not always to lock everything globally, but to **identify the logical operation boundaries that need to be atomic and the proper data publication paths**.

## 6. Approach 1: avoid sharing mutable collections when unnecessary

This is often the easiest approach to prove correct: each task creates its own collection and returns a complete result.

```java
static List<String> transform(List<String> input) {
    List<String> local = new ArrayList<>();

    for (String value : input) {
        local.add(value.toUpperCase());
    }

    return List.copyOf(local);
}
```

This is a method illustration; it requires importing `java.util.List` and `java.util.ArrayList` if placed in a standalone class.

Here, the worker owns `local` while building it. The published result is a list that cannot be modified through its API; with immutable `String` elements, the inner data cannot be mutated either. **Condition:** `input` must be used under an appropriate protocol; if another thread concurrently modifies `input` during the transform, the input race still exists. `List.copyOf` also does not make a copy safe if it is racing against an external writer.

Another design pattern is **single-writer ownership**: multiple producers send work/values through a queue, and only one consumer owns and updates the accumulating collection. In that case, the collection needs no protection for multiple writers because only one thread touches it. If the consumer wants to share results, it creates an immutable snapshot or publishes them via an appropriate synchronization mechanism.

## 7. Approach 2: protect the collection with the same lock

If multiple threads must use the same `ArrayList` or `HashMap` and you want to preserve invariants across multiple operations, the direct approach is to guard all relevant access paths with **the same monitor** or **the same lock**.

A runnable Java 17+ example that does not depend on worker scheduling order:

Save as `LockedListDemo.java`:

```java
import java.util.ArrayList;
import java.util.Collections;
import java.util.List;

public class LockedListDemo {
    private static final class SharedResults {
        private final List<Integer> values = new ArrayList<>();

        synchronized void add(int value) {
            values.add(value);
        }

        synchronized List<Integer> snapshot() {
            return List.copyOf(values);
        }
    }

    public static void main(String[] args) throws InterruptedException {
        SharedResults shared = new SharedResults();

        Runnable work = () -> {
            for (int i = 0; i < 1_000; i++) {
                shared.add(i);
            }
        };

        Thread first = new Thread(work);
        Thread second = new Thread(work);

        first.start();
        second.start();
        first.join();
        second.join();

        List<Integer> result = new ArrayList<>(shared.snapshot());
        Collections.sort(result);

        System.out.println("Size: " + result.size());
        System.out.println("Zeros: " + Collections.frequency(result, 0));
        System.out.println("Last: " + result.get(result.size() - 1));
    }
}
```

```bash
javac LockedListDemo.java
java LockedListDemo
```

Exact stdout:

```text
Size: 2000
Zeros: 2
Last: 999
```

Analysis:

- Both workers call `shared.add`, but **both must acquire the monitor of the `SharedResults` instance**. Inside the locked region, the `ArrayList` is modified by only one thread at a time.
- `snapshot()` uses the same monitor to copy the data, so it never reads the list while another thread is updating it. `List.copyOf` returns an unmodifiable list, which is well-suited for results consisting of immutable `Integer`s.
- `join()` ensures `main` waits for both workers to finish. Sorting the copy afterward keeps stdout independent of execution interleaving.
- To truly maintain control, `values` is `private` and no getter returns the mutable list directly. If the internal reference escapes and callers invoke `add` themselves, they can bypass the lock and break the design.

### Locking individual operations may not protect compound operations

The following example **still has a logic race**, even if both `size()` and `add()` are synchronized:

```java
if (shared.size() < limit) {
    shared.add(item);
}
```

Two threads can both observe that capacity is not yet full and then both add an item. If the requirement is "add only when under the limit," both the check and the addition must be placed **inside the same critical section**, for example by providing a `synchronized` `tryAddWithinLimit(item, limit)` method. An API that is thread-safe for single operations does not automatically make a check-then-act sequence atomic.

## 8. Approach 3: use `Collections.synchronizedXxx` properly

Wrappers such as:

- `Collections.synchronizedList(new ArrayList<>())`
- `Collections.synchronizedMap(new HashMap<>())`
- `Collections.synchronizedSet(new HashSet<>())`

synchronize individual operations through the wrapper per their contract. They are useful when you want to keep using the traditional collection API with a straightforward layer of protection.

**Important pitfall: iterating still requires manual synchronization** on the wrapper itself for the entire duration of the iteration. Otherwise, another thread can modify the collection between iteration steps.

Save as `SynchronizedIterationDemo.java`:

```java
import java.util.ArrayList;
import java.util.Collections;
import java.util.List;

public class SynchronizedIterationDemo {
    public static void main(String[] args) {
        List<String> items =
                Collections.synchronizedList(new ArrayList<>());

        items.add("Java");
        items.add("Concurrency");

        synchronized (items) {
            for (String item : items) {
                System.out.println(item);
            }
        }
    }
}
```

```bash
javac SynchronizedIterationDemo.java
java SynchronizedIterationDemo
```

Exact stdout:

```text
Java
Concurrency
```

In a multi-threaded problem, all code must **access through the wrapper** and not retain or directly mutate the underlying `ArrayList`/`HashMap` after wrapping. When using an iterator, spliterator, stream, or operation sequences that require a consistent view, follow the wrapper's synchronization guidelines and lock on the proper object. Avoid holding the lock during long I/O operations or uncontrolled callbacks, as that will block other operations.

### Why wrapping with `synchronizedList` alone is not enough

Example:

```java
List<String> items =
        Collections.synchronizedList(new ArrayList<>());

if (!items.contains("A")) {
    items.add("A");
}
```

Both individual `contains` and `add` calls are protected by the wrapper, but **between the two calls** another thread can modify the list. If the requirement is "A appears only once," use a single synchronized block:

```java
synchronized (items) {
    if (!items.contains("A")) {
        items.add("A");
    }
}
```

or choose an appropriate `Set` and use the atomic operations provided by that concurrent structure's API.

## 9. Approach 4: use collections designed for concurrency

`java.util.concurrent` provides several data structures with distinct characteristics. Choose based on **the problem and access pattern**, not merely the word "concurrent."

| Need | Typically Suitable API | Key Points to Remember |
| --- | --- | --- |
| Map updated and read by multiple threads | `ConcurrentHashMap<K,V>` | Has atomic per-key APIs, weakly consistent iterators, disallows `null` keys/values |
| Set needing concurrent operations | `ConcurrentHashMap.newKeySet()` | Used for membership; safe add/remove through the Set API |
| Multi-producer/consumer queue, non-blocking when empty | `ConcurrentLinkedQueue<E>` | Non-blocking queue; `poll()` may return `null` |
| Queue where producers/consumers wait and capacity can be bounded | `ArrayBlockingQueue<E>` | `put` blocks when full; `take` blocks when empty |
| Blocking queue with configurable capacity | `LinkedBlockingQueue<E>` | Consider bounding capacity to avoid unbounded queue growth |
| List that is mostly read, rarely written | `CopyOnWriteArrayList<E>` | Snapshot iterators; each mutation typically copies the backing array; heavy writes are expensive |
| Map needing key ordering under concurrent access | `ConcurrentSkipListMap<K,V>` | Sorted concurrent structure; different cost profile from `ConcurrentHashMap` |
| Set needing ordering | `ConcurrentSkipListSet<E>` | Concurrent sorted set, not a `HashSet` |
| Accumulating metrics under high contention | `LongAdder` or `LongAccumulator` | Not a collection; good for counters/statistics, though `sum()` under concurrent updates is not an atomic snapshot |

No single collection is the optimal replacement for every case. You must consider element ordering, write overhead, backpressure, memory footprint, and the atomicity of business operations.

### `ConcurrentHashMap`: use `merge` for per-key updates

A common race is:

```java
Integer old = map.get(key);
map.put(key, old == null ? 1 : old + 1);
```

Even when `map` is a `ConcurrentHashMap`, **the get-then-put sequence is not automatically atomic**: two workers can read the same old value and write the same new value.

Use an atomic per-key update API, such as `merge`. Save as `ConcurrentMapCounterDemo.java`:

```java
import java.util.concurrent.ConcurrentHashMap;

public class ConcurrentMapCounterDemo {
    public static void main(String[] args) throws InterruptedException {
        ConcurrentHashMap<String, Integer> counts =
                new ConcurrentHashMap<>();

        Runnable work = () -> {
            for (int i = 0; i < 10_000; i++) {
                counts.merge("done", 1, Integer::sum);
            }
        };

        Thread first = new Thread(work);
        Thread second = new Thread(work);

        first.start();
        second.start();
        first.join();
        second.join();

        System.out.println("Done: " + counts.get("done"));
    }
}
```

```bash
javac ConcurrentMapCounterDemo.java
java ConcurrentMapCounterDemo
```

Exact stdout:

```text
Done: 20000
```

`merge("done", 1, Integer::sum)` updates the value **per key** as a single `ConcurrentHashMap` operation, avoiding the lost update of the `get/put` pair in the earlier example. The two `join()` calls ensure the final count is read after both workers have finished.

**Note:** functions passed to `compute`/`merge` should be short, clear, and avoid calling other map updates in ways that could cause reentrancy or cross-key dependencies. Each method's contract determines the kind of guarantee; do not infer from "thread-safe map" that multi-key transactions or operations on mutable values are also atomic.

### Unique set case

Instead of `if (!set.contains(id)) set.add(id)` to decide "only one worker processes id," use the return value of `add` itself on a concurrent set:

```java
Set<String> seen = ConcurrentHashMap.newKeySet();

if (seen.add(id)) {
    // Only the thread whose add succeeds for this id executes this branch.
}
```

This is an illustrative snippet: it requires importing `java.util.Set`, `java.util.concurrent.ConcurrentHashMap`, and providing `id`. The `add` condition is an atomic step per the concurrent set's contract, though ensuring "the business action runs only once across the entire system" also depends on how errors, retries, and external state are designed.

## 10. Queues for multiple producers: transfer ownership instead of mutating a shared list

When multiple threads produce results and one thread aggregates them, instead of having all threads call `list.add(...)` on the same `ArrayList`, you can use **producer–consumer**:

```text
Producer A --+
             +--> BlockingQueue --> Consumer owns aggregating ArrayList
Producer B --+                          |
                                        +--> final result after completion
```

Producers only send messages; a single consumer manages the list. `BlockingQueue` handles synchronization and data handoff between threads. Using a bounded-capacity queue provides **backpressure** when producers are faster than the consumer.

Standalone Java 17+ example; two producers send numbers and one consumer computes the sum. Each producer sends exactly 1,000 items, and the caller uses `Future.get()` to wait for both producers to finish before sending the sentinel `-1` to stop the consumer.

Save as `ProducerConsumerDemo.java`:

```java
import java.util.concurrent.ArrayBlockingQueue;
import java.util.concurrent.BlockingQueue;
import java.util.concurrent.ExecutorService;
import java.util.concurrent.Executors;
import java.util.concurrent.Future;

public class ProducerConsumerDemo {
    public static void main(String[] args) throws Exception {
        BlockingQueue<Integer> queue = new ArrayBlockingQueue<>(32);
        ExecutorService pool = Executors.newFixedThreadPool(3);

        try {
            Future<?> first = pool.submit(() -> {
                for (int i = 0; i < 1_000; i++) {
                    queue.put(1);
                }
                return null;
            });

            Future<?> second = pool.submit(() -> {
                for (int i = 0; i < 1_000; i++) {
                    queue.put(1);
                }
                return null;
            });

            Future<Integer> consumer = pool.submit(() -> {
                int sum = 0;

                while (true) {
                    int item = queue.take();
                    if (item == -1) {
                        return sum;
                    }
                    sum += item;
                }
            });

            first.get();
            second.get();
            queue.put(-1); // Send only after both producers have finished.

            System.out.println("Total: " + consumer.get());
        } finally {
            pool.shutdownNow();
        }
    }
}
```

```bash
javac ProducerConsumerDemo.java
java ProducerConsumerDemo
```

Exact stdout on the success path:

```text
Total: 2000
```

Both producers can concurrently update the **thread-safe queue**, while the `sum` variable belongs exclusively to the consumer, so no mutex is needed around `sum`. `Future.get()` confirms both producers completed successfully before `main` enqueues the sentinel. The FIFO queue ensures the sentinel is taken after all items previously `put` successfully; the example has exactly one consumer and the data values are only `1`, so `-1` never collides with real data.

This is a simple happy-path model. In a real application, if a producer fails while the consumer is blocked in `take()`, the coordinating code must have an error/cancellation protocol and wake the consumer appropriately; `shutdownNow()` only requests interruption and does not forcibly stop arbitrary operations. Do not copy this single-sentinel pattern verbatim into a multi-consumer system without adapting the termination protocol.

### Queues do not automatically make enqueued objects immutable

If a producer sends an `ArrayList` and then **continues mutating the same instance** while the consumer reads it, the data race still exists. The safe rule is to **transfer ownership** to the consumer (with the producer stopping any use of the object), or send an immutable copy such as `List.copyOf(...)` (after ensuring snapshot creation is properly protected).

## 11. `CopyOnWriteArrayList`: safe for read-heavy workloads

`CopyOnWriteArrayList` is suited for configurations like listener sets or small lists that are read/iterated frequently and updated rarely. Each structural modification typically creates a new backing array, while iterators hold **a snapshot taken at the time the iterator was created**.

Save as `CopyOnWriteDemo.java`:

```java
import java.util.Iterator;
import java.util.concurrent.CopyOnWriteArrayList;

public class CopyOnWriteDemo {
    public static void main(String[] args) {
        CopyOnWriteArrayList<String> listeners =
                new CopyOnWriteArrayList<>();

        listeners.add("A");
        listeners.add("B");

        Iterator<String> snapshot = listeners.iterator();
        listeners.add("C");

        while (snapshot.hasNext()) {
            System.out.println("Snapshot: " + snapshot.next());
        }

        System.out.println("Current size: " + listeners.size());
    }
}
```

```bash
javac CopyOnWriteDemo.java
java CopyOnWriteDemo
```

Stdout:

```text
Snapshot: A
Snapshot: B
Current size: 3
```

This is snapshot behavior designed into the API, not a lost-data bug. `CopyOnWriteArrayList`'s iterator does not use fail-fast behavior the way `ArrayList`'s iterator does, and it does not support `remove()` on the iterator. Users must understand that **the snapshot does not see modifications made after the iterator was created**.

Avoid using `CopyOnWriteArrayList` for write-heavy workloads or large lists that change frequently, as array copying and allocation costs can be high. It also does not make mutable objects stored as elements immutable.

## 12. Immutable collections, unmodifiable views, and safe publication

Three concepts that are easily confused:

1. **Mutable collection:** contents can be changed through the API (e.g., `ArrayList`).
2. **Unmodifiable view:** callers cannot modify it through the view, **but the underlying collection may still change**.
3. **Immutable snapshot:** a copy that disallows structural modification through the API and is detached from subsequent changes to the input collection; mutable elements remain a separate responsibility.

Consider this Java 17+ example:

Save as `SnapshotVsViewDemo.java`:

```java
import java.util.ArrayList;
import java.util.Collections;
import java.util.List;

public class SnapshotVsViewDemo {
    public static void main(String[] args) {
        List<String> mutable = new ArrayList<>(List.of("A"));

        List<String> view = Collections.unmodifiableList(mutable);
        List<String> snapshot = List.copyOf(mutable);

        mutable.add("B");

        System.out.println("View: " + view);
        System.out.println("Snapshot: " + snapshot);
    }
}
```

```bash
javac SnapshotVsViewDemo.java
java SnapshotVsViewDemo
```

Exact stdout:

```text
View: [A, B]
Snapshot: [A]
```

`Collections.unmodifiableList(mutable)` is a **view**, so it reflects changes made through `mutable`. `List.copyOf(mutable)` creates an unmodifiable list that does not reflect the subsequent `add` when given a mutable input as in this example.

However, note:

- `List.copyOf` **does not make copying safe while another thread is unsafely mutating the list**. You must stop writers, hold a lock during the copy, or use an appropriate publication protocol.
- An unmodifiable collection can still contain **mutable elements**: if it is a `List<Account>` and the `Account` objects are still mutated, the whole object graph cannot be called deeply immutable.
- `List.of(...)` and `List.copyOf(...)` reject `null` elements; `List.copyOf` may reuse an existing unmodifiable instance, so do not rely on snapshot object identity.
- After constructing the data, **safe publication** is still required for other threads to see the complete state under the Java Memory Model—for example, via properly ordered `Thread.start()`, a synchronized queue, a `volatile` reference, or a monitor lock.

Swapping a reference to an **immutable snapshot** is sometimes simpler than trying to synchronize every read and write across multiple fields of a mutable collection.

## 13. Parallel streams: avoid side effects on shared collections

A common mistake in Java is writing:

```java
List<Integer> output = new ArrayList<>();

IntStream.range(0, 100_000)
        .parallel()
        .forEach(output::add);
```

This is an **anti-pattern** when `output` is a shared `ArrayList`. `parallel()` can cause multiple workers to call `add` concurrently, whereas `ArrayList` is not safe for multiple writers. Element order is not guaranteed, and the program risks missing elements or failing.

A correct approach is to use library-supported **collection** rather than mutating a shared list as a side effect. Save as `ParallelCollectDemo.java`:

```java
import java.util.List;
import java.util.stream.IntStream;

public class ParallelCollectDemo {
    public static void main(String[] args) {
        List<Integer> result = IntStream.range(0, 10_000)
                .parallel()
                .boxed()
                .toList();

        long sum = result.stream()
                .mapToLong(Integer::longValue)
                .sum();

        System.out.println("Size: " + result.size());
        System.out.println("First: " + result.get(0));
        System.out.println("Sum: " + sum);
    }
}
```

```bash
javac ParallelCollectDemo.java
java ParallelCollectDemo
```

Exact stdout:

```text
Size: 10000
First: 0
Sum: 49995000
```

`IntStream.range` has an encounter order, and `Stream.toList()` preserves encounter order when present, even in a `parallel()` pipeline. The result of `toList()` is an unmodifiable list. The pipeline itself handles proper collection without requiring the author to call `add` from multiple threads on the same `ArrayList`.

**Do not assume all stream operations automatically protect side effects.** If a `map`/`forEach`/`peek` callback still mutates an external object outside the pipeline, that object's thread safety must still be handled. To group by key under concurrency, consider `Collectors.groupingByConcurrent` depending on ordering and result-type requirements; read the collector's contract rather than creating a map and updating it without synchronization.

## 14. Read-only case: is concurrent reading by multiple threads safe?

If a collection is **fully initialized before publication**, and afterward no thread modifies its structure or the contents being read, multiple threads reading in parallel generally do not need locks around each read.

However, all of the following must hold simultaneously:

- No concurrent writers (including "hidden" writers holding an alias to the same instance).
- The reference is handed to readers using a **safe publication** mechanism per the Java Memory Model. Simply assigning the reference to an ordinary field while other threads are running and hoping readers see it immediately is not a complete publication protocol.
- Mutable values or elements inside are not mutated in a conflicting way while readers are using them.
- Do not assume an **unmodifiable view** means the underlying collection is immutable.

Therefore, "a collection where nobody happens to be calling `add` right now" is different from "a properly published immutable snapshot." Choose a design whose ownership and publication are easy to explain.

## 15. Operations that look safe but are not atomic at the business level

| Code Pattern | Problem | How to Handle |
| --- | --- | --- |
| `if (!list.contains(x)) list.add(x)` | Gap between check and add allows interleaving | Hold a single shared lock or use a concurrent set with atomic `add` |
| `map.put(key, map.get(key) + 1)` | Two workers can overwrite each other's increment | `ConcurrentHashMap.merge/compute` or locking |
| `if (queue.size() < limit) queue.add(x)` | Capacity check and addition are not one transaction | Bounded queue with appropriate `offer/put` |
| `for (x : synchronizedList) ...` without locking | Iterator can race with writers | `synchronized(list)` across the entire iteration or use a snapshot |
| `map.get(key).add(value)` when value is `ArrayList` | Thread-safe map does not protect mutable values | Protect the value, use immutable replacement, or use single ownership |
| `if (map.isEmpty()) launchCleanup()` | State can change immediately after the check | Appropriate state synchronization or shutdown protocol |
| `collection.size()` read while multiple writers run | Not necessarily a business-level snapshot | Wait for workers to finish or use a proper lock/snapshot design |

**Method-level thread safety does not mean workflow-level thread safety.** If a requirement spans multiple steps and multiple collections, define the atomicity boundaries and coordination mechanism rather than simply swapping `HashMap` for `ConcurrentHashMap` and assuming all invariants are protected.

## 16. Common design mistakes

### 16.1. Thinking `volatile List<T>` is enough

`volatile` on a list reference provides visibility/ordering for reads and writes of **that reference itself**. It **does not make `add`/`remove` operations inside `ArrayList` atomic**. If the design uses immutable snapshots and swaps the whole reference via `volatile`, that is a different approach from multiple workers mutating the existing list.

### 16.2. Calling `Collections.synchronizedList` and still passing around the raw list

If another part of the code still holds a reference to the underlying `ArrayList` and mutates it directly, accesses outside the wrapper do not obey the wrapper's lock. Control aliases, enforce encapsulation, and expose only the protected API.

### 16.3. Wrapping a collection but returning an iterator outside the lock

Creating an iterator under a lock and then iterating **after releasing the lock** does not make the traversal atomic. With a synchronized wrapper, you must hold the proper monitor throughout traversal when excluding writers. Another option is to copy a snapshot under the lock and process the snapshot outside.

### 16.4. Using `ConcurrentModificationException` as the sole proof

The absence of an exception does not prove thread safety. The presence of an exception does not necessarily mean multiple threads are involved; a single thread mutating a list directly during iteration is enough.

### 16.5. Believing `ConcurrentHashMap` makes all values safe

Mutable values need their own policy. An `ArrayList` retrieved from a concurrent map is still an ordinary `ArrayList`.

### 16.6. Using `CopyOnWriteArrayList` on a very hot write path

Copying the backing array on every mutation can make write-heavy workloads expensive in both time and memory. It fits read-heavy/write-rare cases, not every problem.

### 16.7. Waiting with `Thread.sleep` and then reading the collection

Sleeping does not guarantee workers have finished or that writes have been properly published. Use `join()`, `Future.get()`, a latch, a queue, or an appropriate synchronization mechanism.

### 16.8. Sharing via static fields

A `static` collection can be accessed from many parts of a program, making ownership hard to control. `private static final List<?>` only prevents reassigning the reference; it does not prevent mutating the list. Consider narrowing scope, using explicit dependencies, and passing immutable snapshots instead of global mutable state.

### 16.9. Leaving queues and pending work unbounded

A non-blocking concurrent queue may have no fixed capacity. If producers outpace consumers, a growing backlog can lead to high memory consumption. Thread safety only addresses the correctness of concurrent access, not load or resource management.

### 16.10. Confusing stress testing with a proof of correctness

Running 10,000 times without seeing a failure does not prove there is no race. Rely on proper API contracts, check invariants, and establish happens-before relationships. Stress tests remain useful for uncovering bugs, but they do not replace reasoning about thread safety.

## 17. Guide to choosing a solution for real-world scenarios

| Context | Design to Consider | Why |
| --- | --- | --- |
| Each task builds its own result list | Local `ArrayList`, then return a snapshot | No shared mutable state during construction |
| Need to read a rarely updated configuration | Immutable snapshot and safe publication | Readers do not contend for locks on every read |
| Multiple workers update a map by key | `ConcurrentHashMap.compute/merge` | Contract supports atomic per-key updates |
| Multiple workers emit items, one worker aggregates | `BlockingQueue` with consumer-owned state | Decouples producers from the mutable accumulator and enables backpressure |
| Frequently iterating a listener list, rarely modifying | `CopyOnWriteArrayList` | Snapshot iterators, suitable for high read-to-write ratios |
| Need to maintain an invariant across two collections | One lock guarding the entire transaction, or an owner protocol | Individual collection concurrency alone is insufficient |
| Need a standard list with simple locking | Properly encapsulated `synchronized` or synchronized wrapper | Easy to control access if locking discipline is consistent |
| Need an ordered concurrent map | `ConcurrentSkipListMap` | Provides ordering and concurrency guarantees per its contract |

**The deciding questions** are not just "which class to pick," but:

1. How many threads actually read or modify **the same instance**?
2. Can we avoid sharing mutable data by using immutable snapshots or single-writer ownership?
3. Does the business invariant belong to a single operation or multiple operations?
4. Does the intended API guarantee atomicity at that exact boundary?
5. Do consumers and producers have a protocol for completion, errors, and timeouts/backpressure?
6. If multiple threads access it, which happens-before relationship guarantees visibility?
7. Are mutable values/elements protected separately?
8. Does the chosen solution fit the read/write ratio and data volume?

## 18. Self-check questions

**Q1:** Two workers both call `list.add(x)` on the same `ArrayList`; should we rely on `list.size()` equaling the total number of additions?

**Answer:** No, not without synchronization. `ArrayList`'s structural update operations are not guaranteed to be safe with multiple writers. You need a single owner, a lock, or an appropriate concurrent collection.

**Q2:** If using `Collections.synchronizedList`, is a `for-each` loop over the list already safe enough?

**Answer:** Not necessarily. You must hold the wrapper's monitor for the entire traversal when concurrent writers exist, or iterate over a safely created snapshot.

**Q3:** Does `ConcurrentHashMap` make a `get` followed by `put` to increment a counter atomic?

**Answer:** No. Use per-key `merge`/`compute`, an appropriately designed atomic counter, or an enclosing synchronized block.

**Q4:** Does `List.copyOf` guarantee deep immutability?

**Answer:** No. It creates a list that cannot be modified via its API and is detached from subsequent structural changes to a mutable input under valid copy conditions, but mutable elements inside can still change.

**Q5:** Can we conclude "there is no data race" because no `ConcurrentModificationException` was thrown?

**Answer:** No. Fail-fast behavior is best effort and may not throw an exception. The absence of an exception does not prove thread safety.

**Q6:** If multiple producers send work to a single consumer, why can the consumer use a regular `ArrayList`?

**Answer:** Because the consumer is the sole owner and no other thread modifies or reads that list during mutation. Producers only communicate through a thread-safe queue; when publishing results to other threads, proper snapshotting/publication is still required.

**Q7:** Is a `ConcurrentHashMap<String, ArrayList<Event>>` safe if multiple workers modify the same value?

**Answer:** Not automatically. The concurrent map protects map operations; each value is still a regular `ArrayList` that needs its own synchronization protocol, immutable replacement, or ownership change.

## 19. Key takeaways

- `ArrayList`, `HashMap`, `HashSet`, and many standard collections **are not thread-safe for concurrent access with mutation**.
- A race can corrupt data without throwing any exception; `ConcurrentModificationException` is **not** a thread-safety validator.
- `synchronized` or a unified lock can protect **entire sequences of operations** and invariants; synchronized wrappers still require locking during iteration.
- `ConcurrentHashMap`, `BlockingQueue`, and `CopyOnWriteArrayList` solve **different needs**; read each API's contracts for atomicity, visibility, snapshots, and cost carefully.
- **Immutable snapshots**, task-local collections, and **single-writer ownership** often reduce complexity better than freely sharing mutable state.
- Controlling collection aliases, mutable elements, safe publication, lifecycle, and backpressure is also part of correctness.

When designing multi-threaded processing in Java, start by asking **"Who owns and has the right to modify this collection?"**. If the answer is multiple threads, you must specify the synchronization protocol or choose the right concurrent collection **and the right atomic operations**, rather than assuming a standard collection will handle contention on its own.
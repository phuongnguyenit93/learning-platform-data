# CopyOnWriteArrayList: Pros and Cons Under Heavy Writes

## 1. The Problem to Solve

`CopyOnWriteArrayList<E>` belongs to `java.util.concurrent` and implements the `List<E>` interface using a **copy-on-write** strategy: when the structure or elements of the list need to be modified, the update operation typically creates a new backing array and publishes the new array to reading threads. Meanwhile, reading threads can access the current array without locking the list for each read.

This is a good choice when **the number of reads/iterations far exceeds the number of modifications**, such as a listener list or a configuration that rarely changes. Conversely, if elements are added, removed, or replaced continuously, array copying, memory allocation, and contention among writer threads can make it far more expensive than many other alternatives.

Lesson objective: understand read/iteration consistency, see the true cost of each write, and know when to use or replace `CopyOnWriteArrayList`. The scope is Java concurrency in general.

## 2. How It Works

Suppose the initial backing array is `[A, B, C]`:

1. A reading thread calls `iterator()`, and the iterator holds a reference to **the array at the time the iterator was created**.
2. A writing thread calls `add(D)`. It synchronizes the write operation, allocates a new array, copies the element references from the old array, and appends `D`.
3. The writing thread publishes the array `[A, B, C, D]`. New read calls can see the published state.
4. The old iterator continues traversing `[A, B, C]`. It does not see `D`, does not change mid-iteration, and does not throw `ConcurrentModificationException` due to concurrent modification of the list.

`CopyOnWriteArrayList` uses an array publication mechanism with cross-thread visibility guarantees; modification operations on the same list are coordinated so that updates are not lost. In the JDK 17 implementation, writing threads use an internal lock, while normal read operations obtain the published array state. Do not misunderstand this to mean that any high-level operation consisting of **multiple separate calls** automatically becomes an atomic transaction.

**The snapshot here is a snapshot of the reference array**, not a deep copy of each object. If an element is a mutable object, a thread directly modifying fields of that object can still affect the data seen by an old iterator; thread safety of that object must be ensured separately.

## 3. Read and Write Costs

| Operation | Typical characteristic/cost | Meaning |
| --- | --- | --- |
| `get(index)` | O(1), does not copy the whole array | Suitable for index-based reads. |
| `iterator()` then iterate | Iterator creation O(1), iterating n elements O(n) | A single traversal sees a stable snapshot of element references. |
| `add(element)`, `add(index, element)` | O(n) to create a new array and copy references | The larger the list, the more expensive each addition becomes. |
| `remove(index)` or removing an existing element | Usually O(n) to find/shift and create a new array | Repeatedly removing elements one by one easily produces many intermediate arrays. |
| `set(index, value)` | Usually O(n) when replacing an element in a new array is needed | Do not treat `set` as an O(1) update like `ArrayList`. |
| `contains(value)` | O(n) linear search | Should not be used for very high-frequency membership checks on large lists. |
| `addIfAbsent(value)` | Searches for the element and, if absent, adds it in a thread-safe manner; usually O(n) | Avoids the race condition of a `contains` + `add` pair, but does not eliminate copying cost. |

The complexities above describe the common costs of operations that actually mutate data; they do not assert that every implementation branch copies the array (for example, removing a non-existent element may not create a new array). Bulk update operations such as `addAll`, `removeIf`, or `clear` have their own behavior and cost; when possible, batching changes appropriately is usually better than calling `add`/`remove` element by element.

**Why are heavy writes so expensive?** With n elements, each successful addition typically has to copy about n references. If there are m independent additions at a size near n, the amount of copying work is approximately O(m × n), not counting synchronization, allocation, and garbage collection. If n elements are added one by one to an initially empty list via n calls to `add`, the total number of references copied is on the order of O(n²).

Estimation example: an array holding 100,000 references has a reference payload of about 0.4 MB if the JVM uses 4-byte references, or 0.8 MB if it uses 8-byte references, excluding headers/alignment. One thousand successful updates per second at that scale can generate hundreds of MB of array allocations per second. This is an **illustrative estimate based on JVM configuration**, not a benchmark result or a specific latency prediction. Element objects are not deep-cloned; what is copied is mainly the references.

## 4. Advantages in Read-Heavy, Write-Rarely Workloads

- **Reads have low contention with writes:** normal read operations do not need to hold the write lock; another thread can publish a new version of the array while an old iterator is traversing.
- **Stable iterators:** there is no need to wrap the entire loop in `synchronized` just to guard against concurrent modification of the list; iterators do not encounter `ConcurrentModificationException` due to structural changes to the list.
- **Ordering and `List` API:** preserves insertion order and supports index-based access, useful when listener ordering matters.
- **Simple for rarely changing registration lists:** listeners, callbacks, handlers, and configurations that are only occasionally added/removed but read very frequently.
- **Useful concurrency convenience operations:** `addIfAbsent` and `addAllAbsent` help add non-existent elements without manually combining a check and an update into two separate calls.

These benefits only outweigh write costs when the workload is a good fit. "Thread-safe" does not mean "fast in all multithreaded scenarios."

## 5. Disadvantages Under Heavy Writes

### 5.1. O(n) copying for many updates

Suppose a list has 50,000 listeners and each event adds/removes multiple listeners. Write operations may repeatedly copy a large reference array. As size grows, total CPU cost and memory bandwidth become increasingly significant. In particular, `CopyOnWriteArrayList` should not be used as a work list where threads continuously `add`/`remove` like a queue.

### 5.2. Allocation and garbage collection pressure

Old array versions become eligible for collection once no one holds a reference to them. However, live snapshot iterators can **keep old arrays alive longer**, so many long-lived iterators combined with continuous updates increase the amount of concurrently retained memory. High allocation throughput can trigger frequent GC cycles and latency fluctuations.

### 5.3. Contention among writers

Multiple threads can read conveniently, but modification operations still have to coordinate/serialize on the same list. If writers are heavily active, they contend with each other on write work that already involves O(n) copying; increasing the number of writers does not guarantee higher throughput.

### 5.4. Iterators do not see new changes

An iterator created before an addition/removal still sees the old snapshot. This is an advantage for consistent traversal, but unsuitable if an algorithm requires a loop to **immediately observe** newly modified data. Each new `iterator()` call takes a snapshot at its own point in time; there is no guarantee that all concurrently running loops see the same state.

### 5.5. No direct modification through iterators

`Iterator.remove()` and `ListIterator.remove()`, `ListIterator.set()`, `ListIterator.add()` are not supported; they throw `UnsupportedOperationException`. If removal is needed, operate through the list itself, for example `removeIf(predicate)`; previously created iterators still traverse the old snapshot.

### 5.6. Do not confuse list safety with element safety

`CopyOnWriteArrayList<Account>` protects the list structure; it does not automatically make additions and subtractions on `Account.balance` safe. Similarly, code like `if (!list.contains(x)) list.add(x);` consists of two separate calls and can be interleaved by another thread. For adding if absent, use `addIfAbsent(x)`; for multi-step business rules, design appropriate synchronization/coordination at the business level.

## 6. Java 17+ Example: Snapshots and Safe Addition

Create the file `CowSnapshotDemo.java`:

```java
import java.util.ArrayList;
import java.util.Iterator;
import java.util.List;
import java.util.concurrent.CopyOnWriteArrayList;

public class CowSnapshotDemo {
    public static void main(String[] args) {
        CopyOnWriteArrayList<String> names =
                new CopyOnWriteArrayList<>(List.of("An", "Bình"));

        Iterator<String> beforeAdd = names.iterator();
        names.add("Chi");

        List<String> snapshot = new ArrayList<>();
        beforeAdd.forEachRemaining(snapshot::add);

        System.out.println("Snapshot: " + snapshot);
        System.out.println("Current : " + names);
        System.out.println("Add Chi again: " + names.addIfAbsent("Chi"));
        System.out.println("Add Dũng: " + names.addIfAbsent("Dũng"));
        System.out.println("Final   : " + names);
    }
}
```

Compile and run with JDK 17 or later:

```bash
javac -encoding UTF-8 CowSnapshotDemo.java
java CowSnapshotDemo
```

Deterministic output:

```text
Snapshot: [An, Bình]
Current : [An, Bình, Chi]
Add Chi again: false
Add Dũng: true
Final   : [An, Bình, Chi, Dũng]
```

The `beforeAdd` iterator holds the array from before `Chi` was added. Calling `names.add("Chi")` updates the list but does not change that snapshot. `addIfAbsent("Chi")` returns `false` because `Chi` already exists; `addIfAbsent("Dũng")` adds the new element and returns `true`.

## 7. Multithreaded Example: Using addIfAbsent Instead of contains + add

Create the file `CowConcurrentDemo.java`:

```java
import java.util.ArrayList;
import java.util.List;
import java.util.concurrent.CopyOnWriteArrayList;
import java.util.concurrent.CountDownLatch;
import java.util.concurrent.ExecutorService;
import java.util.concurrent.Executors;
import java.util.concurrent.Future;

public class CowConcurrentDemo {
    public static void main(String[] args) throws Exception {
        CopyOnWriteArrayList<String> jobs =
                new CopyOnWriteArrayList<>(List.of("seed"));
        int writers = 4;
        CountDownLatch start = new CountDownLatch(1);
        ExecutorService pool = Executors.newFixedThreadPool(writers);
        List<Future<?>> futures = new ArrayList<>();

        try {
            for (int i = 0; i < writers; i++) {
                futures.add(pool.submit(() -> {
                    start.await();
                    jobs.addIfAbsent("job-42");
                    return null;
                }));
            }

            start.countDown();
            for (Future<?> future : futures) {
                future.get();
            }
        } finally {
            pool.shutdown();
        }

        long count = jobs.stream().filter("job-42"::equals).count();
        System.out.println("Count: " + count);
        System.out.println("Jobs : " + jobs);
    }
}
```

```bash
javac -encoding UTF-8 CowConcurrentDemo.java
java CowConcurrentDemo
```

```text
Count: 1
Jobs : [seed, job-42]
```

All four workers are released by `CountDownLatch` and simultaneously attempt to add the same value. `addIfAbsent` ensures the "check and add if absent" operation does not create four duplicate copies of the element in this list. The return value simply reflects which worker succeeded in adding it; the final result has exactly one `job-42`. Using `if (!jobs.contains("job-42")) jobs.add("job-42");` would risk two workers both seeing "not present" and both adding it. Even though duplicates are avoided with `addIfAbsent`, if many different values are continuously added to a large list, the copy-on-write cost still remains.

## 8. Choosing Another Structure When the Workload Changes

| Practical need | Option to consider | Things to watch out for |
| --- | --- | --- |
| Small/medium listener list, nearly read-only | `CopyOnWriteArrayList` | Best suited when iteration dominates updates and snapshots are acceptable. |
| List needing continuous adds/removes, with index access | `ArrayList` guarded by `synchronized` or `ReentrantReadWriteLock` | Must protect **all** compound operations and iteration loops; reads may be blocked. Measure against the workload. |
| Need a multi-producer/consumer queue | `ConcurrentLinkedQueue`, or a `BlockingQueue` such as `LinkedBlockingQueue`/`ArrayBlockingQueue` | Queues have FIFO/work-intake semantics, not an index-based `List`. Choose a bounded queue if backlog needs to be limited. |
| Need key-based storage, concurrent updates and lookups | `ConcurrentHashMap<K,V>` | Map semantics, does not preserve list order; better suited when the primary need is key-based lookup. |
| Need a set of unique elements, frequent add/remove operations | `ConcurrentHashMap.newKeySet()` | No index ordering like `List`; iterators are weakly consistent rather than fixed snapshots. |

No single structure is a 1:1 replacement for every requirement. Before switching, clarify: whether element ordering and indexing are needed, what state iterators must see, what the concurrency level is, whether memory/queue bounds are required, and which operations need atomicity.

### A Common Structure Selection Mistake

If listeners need to be registered/unregistered very frequently, while each event emission only iterates once, `CopyOnWriteArrayList` can become a bottleneck. Do not just increase the thread pool size to fix it: writers still serialize and copy. Evaluate switching data structures, reducing update frequency, batching updates appropriately, or providing immutable snapshots published in batches when application requirements allow.

## 9. How to Evaluate by Measuring

Do not decide based solely on the name "concurrent". Collect representative load and measure:

1. **Read/write ratio**: number of `get`/iterations versus `add`/`remove`/`set` per unit of time.
2. **List size**: average, p95, and peak, because copy cost depends on element count.
3. **Concurrent reader/writer count**: determine whether writer threads experience heavy contention.
4. **Latency and throughput**: especially p95/p99 of write operations and of the main processing path.
5. **Allocation and GC**: allocation rate, heap occupancy, and pause time under continuous updates.
6. **Consistency requirements**: is an iterator snapshot appropriate, or must new changes be visible immediately?

You can use JMH for microbenchmarking Java operations and integration benchmarks for real processing flows. Benchmarks need JVM warm-up, realistic data sizes, multiple readers/writers, dead-code elimination control, and comparison under the same consistency specification. Do not draw performance conclusions from a simple `System.nanoTime()` loop.

## 10. Self-Check Questions and Conclusion

**Q:** Read-heavy, write-rarely, callbacks needed in order: what to use?  
**A:** `CopyOnWriteArrayList` is a reasonable candidate; snapshot iterators keep traversal stable even when threads register/unregister.

**Q:** With 200,000 elements and many writers continuously calling `add` and `remove`: why is it slow?  
**A:** Each successful update typically has to copy a large number of references, allocate a new array, and coordinate writers; additionally, GC pressure increases and old snapshots can retain memory.

**Q:** Does an iterator created before `list.add(x)` see `x`?  
**A:** No. That iterator traverses the old array. A new iterator created after `add` completes can see `x` if it has not been modified again.

**Q:** Can you call `iterator.remove()` to remove an element?  
**A:** No; this method throws `UnsupportedOperationException`. Modify through the list API instead, such as `removeIf`.

**Q:** Does `CopyOnWriteArrayList` make every object inside it thread-safe?  
**A:** No. It protects the list structure and reference publication, not automatically synchronizing mutable state inside objects.

**Key takeaway:** `CopyOnWriteArrayList` trades **write cost and memory** for **stable, low-contention reads/iterations**. It typically shines in *read-mostly* models; for *write-heavy* workloads, reconsider the data structure and measure latency, allocation volume, and consistency requirements.

Official reference: [Oracle Java 17 API — CopyOnWriteArrayList](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/concurrent/CopyOnWriteArrayList.html).

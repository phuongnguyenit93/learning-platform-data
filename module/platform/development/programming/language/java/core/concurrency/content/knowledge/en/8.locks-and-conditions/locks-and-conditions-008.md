# ReadWriteLock for Read-Heavy Workloads in Java

> **Key takeaway:** `ReadWriteLock` has two paired lock modes: **multiple readers** can hold the read lock concurrently, while a **writer** requires the exclusive write lock. It is useful for certain read-heavy/write-light workloads, but **there is no guarantee it is always faster** than `synchronized` or `ReentrantLock`. Critical section length, read/write ratio, contention, fairness, and data characteristics determine the outcome.

This lesson belongs to **Locks & Conditions** and focuses solely on Java SE concurrency using Java 17+ APIs. Spring-related topics are reserved for their own chapter and are outside the scope of this lesson.

## 1. Why do we need a read/write lock?

Suppose a dictionary structure has thousands of entries, with many threads reading to look up values and rarely modifying it. If a single `synchronized(lock)` monitor protects every operation, even read-only threads must queue up one after another. With a read/write lock, multiple **pure reads** can execute concurrently, while a write temporarily blocks other readers/writers to update state consistently.

~~~text
No writer:
  Reader A -- READ lock --┐
  Reader B -- READ lock --+-- can be in the critical section together
  Reader C -- READ lock --┘

When a writer needs to modify:
  Writer -- WRITE lock ------- exclusive once acquired
  Other Readers/Writers ------ wait according to the acquisition policy
~~~

This represents concurrent access capability under the lock contract; it **does not guarantee that the CPU actually runs readers in parallel** or that a writer will acquire the lock before a deadline.

| Who currently holds the lock? | New reader | New writer |
| --- | --- | --- |
| No one | Can acquire read | Can acquire write |
| One or more readers | Can also acquire read if the waiting policy allows | Must wait for readers to release |
| One writer | Cannot enter, except for the writer's own reentrant read | Cannot enter, except for the writer's own reentrant write |

Do not misunderstand this as "as long as a reader is present, a new reader can always enter": when a writer is waiting, the fairness/acquisition policy may require new readers to wait to prevent writer starvation.

## 2. Interface and implementation in Java

`ReadWriteLock` is an interface in `java.util.concurrent.locks`. Each instance returns **a linked pair** via `readLock()` and `writeLock()`. `ReentrantReadWriteLock` is the standard Java SE implementation, supporting reentrancy and optional fairness.

~~~java
// Snippet illustrating declaration; not a standalone program.
ReadWriteLock rw = new ReentrantReadWriteLock();
Lock read = rw.readLock();
Lock write = rw.writeLock();
~~~

Two standard critical sections:

~~~java
read.lock();
try {
    // Only read shared data and create a snapshot if needed.
} finally {
    read.unlock();
}

write.lock();
try {
    // Check invariants and update shared data.
} finally {
    write.unlock();
}
~~~

Always use `try/finally` after a successful acquisition. `Lock` does not have an automatic release construct upon exiting a block like `synchronized`. On an exception or early `return`, `finally` still releases the lock. Calling `unlock()` from a thread that does not own the lock, or unlocking more times than valid holds, will throw an error.

**All readers/writers protecting the same state must use the same `rw` instance.** If one thread acquires `rwA.readLock()` and another acquires `rwB.writeLock()`, the two locks have no mutual exclusion relationship, regardless of having similar variable names.

### Happens-before mechanism

`ReadWriteLock` requires the memory synchronization effects of the write lock to also apply to the associated read lock. After a writer updates data and releases the write lock, subsequent readers that acquire the read lock are guaranteed to observe those updates under the Java Memory Model. Therefore, a regular `int` can be read/written correctly under this locking protocol; adding `volatile` to individual fields is unnecessary if all concurrent accesses follow the protocol.

A single unlocked write path or a reader reading directly outside the read lock is enough to break the correctness of the design.

## 3. When does read-heavy actually pay off?

A good candidate typically has: very many reads; very few updates; many readers contending for the same structure; reads with non-trivial duration; writers holding the write lock briefly; and a clear data design and invariants.

Conversely, `ReentrantReadWriteLock` manages reader counts, write ownership, and queues that are more complex than an exclusive lock. If each read only fetches a single variable or performs an ultra-short lookup, the overhead may outweigh the benefit. With a high write ratio, frequent exclusive write locks leave shared reads little opportunity to run together.

The JDK `ReadWriteLock` documentation notes that effectiveness depends on the read/write ratio, operation duration, contention, and number of physical processors. Therefore, **read-heavy is a hint to benchmark, not a proof of speed**.

| Workload type | Suitability |
| --- | --- |
| Large map with long lookups, rare modifications, many readers | Potentially reasonable |
| Immutable configuration replaced a few times per hour | A `volatile` reference to an immutable snapshot is usually simpler |
| A counter updated very frequently | `AtomicLong`/`LongAdder` or other tools are more suitable |
| Each request gets/puts an independent key | `ConcurrentHashMap` may be more efficient than locking the whole map |
| Each read operation actually updates LRU/hit count | No longer read-only; requires a mutation protocol |
| Critical sections are always very short and contention is low | An exclusive lock may be easier to reason about and faster |

## 4. Example 1: a read-mostly, write-rarely dictionary

`HashMap` by itself must not be used for concurrent reads/writes when mutations occur. However, we can **completely encapsulate** it and only access it under the corresponding read/write lock.

Create `ReadMostlyDictionary.java` (Java 17+):

~~~java
import java.util.HashMap;
import java.util.Map;
import java.util.concurrent.locks.ReadWriteLock;
import java.util.concurrent.locks.ReentrantReadWriteLock;

public class ReadMostlyDictionary {
    private final Map<String, String> values = new HashMap<>();
    private final ReadWriteLock rw = new ReentrantReadWriteLock();

    public String get(String key) {
        rw.readLock().lock();
        try {
            return values.get(key);
        } finally {
            rw.readLock().unlock();
        }
    }

    public void put(String key, String value) {
        rw.writeLock().lock();
        try {
            values.put(key, value);
        } finally {
            rw.writeLock().unlock();
        }
    }

    public int size() {
        rw.readLock().lock();
        try {
            return values.size();
        } finally {
            rw.readLock().unlock();
        }
    }

    public static void main(String[] args) throws InterruptedException {
        ReadMostlyDictionary dictionary = new ReadMostlyDictionary();
        dictionary.put("language", "Java");

        Thread firstReader = new Thread(() -> {
            for (int i = 0; i < 1_000; i++) {
                String value = dictionary.get("language");
                if (!"Java".equals(value) && !"Java 17".equals(value)) {
                    throw new AssertionError(value);
                }
            }
        });
        Thread secondReader = new Thread(() -> {
            for (int i = 0; i < 1_000; i++) {
                dictionary.size();
            }
        });
        Thread writer = new Thread(
                () -> dictionary.put("language", "Java 17"));

        firstReader.start();
        secondReader.start();
        writer.start();
        firstReader.join();
        secondReader.join();
        writer.join();

        System.out.println("size = " + dictionary.size());
        System.out.println("language = " + dictionary.get("language"));
    }
}
~~~

Compile/run:

~~~bash
javac ReadMostlyDictionary.java
java ReadMostlyDictionary
~~~

Expected stdout:

~~~text
size = 1
language = Java 17
~~~

During execution, a reader may observe `Java` or `Java 17` depending on interleaving; **there is no fixed observation order**. Because map reads and writes use locking properly, readers never access the map's internal structure while the writer is mutating it. After `join()` on the writer, the final value is `Java 17`.

`String` is immutable. If the map returned a `MutableValue` and another thread modified that object after `get()` returned, the lock would only protect the **map lookup**, not mutations to the returned object. Prefer immutable values, defensive copies, or a locking protocol that protects the internal state as well.

Never expose `values` directly via a getter; callers could mutate the map without locking and break the entire model.

## 5. Example 2: two readers enter together, writer must wait

To demonstrate that multiple readers can hold the read lock concurrently, coordinate them with `CountDownLatch` instead of `Thread.sleep`.

Create `ReadLockCoordination.java` (Java 17+):

~~~java
import java.util.concurrent.CountDownLatch;
import java.util.concurrent.atomic.AtomicBoolean;
import java.util.concurrent.locks.ReentrantReadWriteLock;

public class ReadLockCoordination {
    public static void main(String[] args) throws InterruptedException {
        ReentrantReadWriteLock rw = new ReentrantReadWriteLock();
        CountDownLatch bothInside = new CountDownLatch(2);
        CountDownLatch release = new CountDownLatch(1);
        AtomicBoolean writerEntered = new AtomicBoolean(false);

        Runnable reader = () -> {
            rw.readLock().lock();
            try {
                bothInside.countDown();
                release.await();
            } catch (InterruptedException interrupted) {
                Thread.currentThread().interrupt();
            } finally {
                rw.readLock().unlock();
            }
        };

        Thread a = new Thread(reader, "reader-a");
        Thread b = new Thread(reader, "reader-b");
        a.start();
        b.start();

        bothInside.await(); // Both readers are currently holding the read lock.
        System.out.println("both readers inside = true");

        Thread writer = new Thread(() -> {
            rw.writeLock().lock();
            try {
                writerEntered.set(true);
            } finally {
                rw.writeLock().unlock();
            }
        }, "writer");
        writer.start();

        System.out.println("writer before release = "
                + writerEntered.get());

        release.countDown();
        a.join();
        b.join();
        writer.join();

        System.out.println("writer after release = "
                + writerEntered.get());
    }
}
~~~

Run:

~~~bash
javac ReadLockCoordination.java
java ReadLockCoordination
~~~

Stdout assuming no external interruption:

~~~text
both readers inside = true
writer before release = false
writer after release = true
~~~

`bothInside.await()` only completes when **both readers** have acquired the read lock and decremented the latch; if the read lock excluded other readers, the second reader could not enter while the first reader waited on `release`. The line `writer before release = false` is guaranteed because both readers still hold the read lock; the writer cannot enter the write critical section yet. After `release.countDown()` and `join()` on all three threads, the writer has had its chance to update the flag.

This is an experiment to learn lock semantics; **do not hold a read lock across a wait/blocking operation like this in real applications** if the signaling work itself needs the write lock. A wait cycle can cause deadlock.

## 6. A method named `get()` can be a write operation

"Read" in read lock means **not modifying the protected shared state**, not "a method named getter".

Examples of reads with side effects:

- `LinkedHashMap` initialized with `accessOrder=true`: a `get()` call can change internal node order.
- A cache that self-populates on read (`computeIfAbsent` or lazy load).
- LRU eviction, updating `lastAccess`, or cache hit/miss metrics stored in regular fields.
- A getter that creates a memoized value or mutates a child object.
- Iteration that removes or mutates mutable elements.

~~~java
// Illustrative snippet; lru is an access-order map.
java.util.Map<String, String> lru =
        new java.util.LinkedHashMap<>(16, 0.75f, true);
String value = lru.get("key"); // May modify access order.
~~~

If this map is shared across multiple threads, the `get` operation performs a **mutation** and must not be casually called under a shared read lock. You may need to use the write lock or a specialized cache structure. When every "read" updates state, the value of `ReadWriteLock` drops significantly.

## 7. Consistent snapshots when state has multiple fields

Suppose a ledger has `total` and `version`, with the invariant that each increment to `total` increments `version` once. Writers must update both **under the same write lock**, and readers must read both **under the same read lock**.

Create `ReadWriteSnapshot.java` (Java 17+):

~~~java
import java.util.concurrent.locks.ReentrantReadWriteLock;

public class ReadWriteSnapshot {
    private record Snapshot(long total, long version) {}

    private static final class Ledger {
        private final ReentrantReadWriteLock rw =
                new ReentrantReadWriteLock();
        private long total;
        private long version;

        void addOne() {
            rw.writeLock().lock();
            try {
                total++;
                version++;
            } finally {
                rw.writeLock().unlock();
            }
        }

        Snapshot snapshot() {
            rw.readLock().lock();
            try {
                return new Snapshot(total, version);
            } finally {
                rw.readLock().unlock();
            }
        }
    }

    public static void main(String[] args) throws InterruptedException {
        Ledger ledger = new Ledger();
        Runnable writer = () -> {
            for (int i = 0; i < 1_000; i++) {
                ledger.addOne();
            }
        };
        Thread first = new Thread(writer);
        Thread second = new Thread(writer);
        first.start();
        second.start();
        first.join();
        second.join();

        Snapshot snapshot = ledger.snapshot();
        System.out.println("total = " + snapshot.total());
        System.out.println("version = " + snapshot.version());
        System.out.println("consistent = "
                + (snapshot.total() == snapshot.version()));
    }
}
~~~

Run:

~~~bash
javac ReadWriteSnapshot.java
java ReadWriteSnapshot
~~~

Stdout:

~~~text
total = 2000
version = 2000
consistent = true
~~~

`snapshot()` creates an immutable record right inside the critical section, so callers using the snapshot outside the lock still have a matching pair of fields. Do not read the two fields under **two separate** read lock acquisitions: a writer could interleave in between and produce a snapshot mixing two versions.

If the snapshot contains a list or mutable object, make an immutable/defensive copy of what needs protection. Merely copying the reference to a collection being mutated does not make that copy thread-safe.

## 8. Do not upgrade directly from a read lock to a write lock

With `ReentrantReadWriteLock`, a reader holding the read lock **cannot** also acquire the write lock to "upgrade". The write lock is only granted when no other readers remain; the caller's own read lock is still held, which can cause the caller to wait on itself indefinitely.

~~~java
// INCORRECT CODE: do not run without a timeout and an escape hatch.
rw.readLock().lock();
try {
    if (missing) {
        rw.writeLock().lock(); // Upgrade is not supported.
        try {
            initialize();
        } finally {
            rw.writeLock().unlock();
        }
    }
} finally {
    rw.readLock().unlock();
}
~~~

The proper approach is:

1. Read the cache and condition under the read lock.
2. **Release the read lock** before attempting to acquire the write lock.
3. Acquire the write lock.
4. **Re-check** the condition because in the gap between the two locks, another thread may have already completed the work.
5. Perform the update only if the condition still holds.
6. Release the write lock in `finally`.

Crucial point: read-unlock → write-lock **is not an atomic upgrade**. Re-checking is a correctness requirement, not an unnecessary step.

### Example 4: double-checking a cache miss

Create `ReadWriteCache.java` (Java 17+):

~~~java
import java.util.HashMap;
import java.util.Locale;
import java.util.Map;
import java.util.concurrent.locks.ReentrantReadWriteLock;

public class ReadWriteCache {
    private final Map<String, String> values = new HashMap<>();
    private final ReentrantReadWriteLock rw =
            new ReentrantReadWriteLock();

    public String getOrLoad(String key) {
        rw.readLock().lock();
        try {
            String existing = values.get(key);
            if (existing != null) {
                return existing;
            }
        } finally {
            rw.readLock().unlock();
        }

        // Pure computation; can be done outside the lock.
        String loaded = key.toUpperCase(Locale.ROOT);

        rw.writeLock().lock();
        try {
            // May have already been loaded by another thread while we held no lock.
            String existing = values.get(key);
            if (existing != null) {
                return existing;
            }
            values.put(key, loaded);
            return loaded;
        } finally {
            rw.writeLock().unlock();
        }
    }

    public int size() {
        rw.readLock().lock();
        try {
            return values.size();
        } finally {
            rw.readLock().unlock();
        }
    }

    public static void main(String[] args) throws InterruptedException {
        ReadWriteCache cache = new ReadWriteCache();
        String[] result = new String[2];

        Thread a = new Thread(() -> result[0] = cache.getOrLoad("java"));
        Thread b = new Thread(() -> result[1] = cache.getOrLoad("java"));
        a.start();
        b.start();
        a.join();
        b.join();

        System.out.println("same = " + result[0].equals(result[1]));
        System.out.println("value = " + result[0]);
        System.out.println("size = " + cache.size());
    }
}
~~~

Run:

~~~bash
javac ReadWriteCache.java
java ReadWriteCache
~~~

Stdout:

~~~text
same = true
value = JAVA
size = 1
~~~

Two threads may both observe a miss and **compute `loaded` multiple times**; the uppercase computation is pure, so there is no issue. However, only one thread stores the value in the map because the re-check occurs under the write lock. If the loader has side effects (network calls, DB writes, sending email), do not assume the loader is called only once; you would need single-flight, per-key futures, or a different protocol.

If the computation outside the lock depends on changing shared state, you must protect consistency with a version/retry mechanism or move the critical decision into the write section. You cannot simply release-read/acquire-write and assume the old snapshot is still current.

## 9. Downgrading from write lock to read lock is supported

`ReentrantReadWriteLock` **allows** a thread already holding the write lock to acquire the read lock (reentrantly), and then release the write lock while retaining the read lock. This lets the writer that just updated state continue observing it under the read lock **without another writer intervening during the mode transition**.

~~~text
acquire WRITE
update state
acquire READ while WRITE is still held
release WRITE
read/continue processing under READ
release READ
~~~

Create `DowngradeExample.java` (Java 17+):

~~~java
import java.util.concurrent.locks.Lock;
import java.util.concurrent.locks.ReentrantReadWriteLock;

public class DowngradeExample {
    public static void main(String[] args) {
        ReentrantReadWriteLock rw = new ReentrantReadWriteLock();
        Lock read = rw.readLock();
        Lock write = rw.writeLock();
        String[] state = {"old"};

        write.lock();
        try {
            state[0] = "new";
            read.lock();  // Writer also acquires the read lock.
        } finally {
            write.unlock();
        }

        try {
            System.out.println("state = " + state[0]);
        } finally {
            read.unlock();
        }
    }
}
~~~

Run:

~~~bash
javac DowngradeExample.java
java DowngradeExample
~~~

Stdout:

~~~text
state = new
~~~

This snippet focuses on the **happy path**. When performing multiple acquisitions in complex code that may throw exceptions, carefully track which locks have been acquired before unlocking. Downgrading does not make arbitrary operations atomic or replace protection for mutable objects returned outside the lock.

| Case | Supported |
| --- | --- |
| Reentrant read lock (same reader) | Yes |
| Reentrant write lock (same writer) | Yes |
| Writer holds write then acquires read | Yes |
| Reader holds read then acquires write | **Upgrade not supported** |
| Downgrade write → read without a writer intervening | Yes, acquire read before releasing write |

## 10. Fairness and the risk of writer starvation

Defaults:

~~~java
ReentrantReadWriteLock regular = new ReentrantReadWriteLock();
ReentrantReadWriteLock fair = new ReentrantReadWriteLock(true);
~~~

This is an API snippet. `regular` uses **non-fair mode**; `fair` uses an **approximately arrival-order** policy when contending for the lock.

- **Non-fair:** the order in which read/write locks are granted is not fixed to FIFO; throughput is usually higher, though under continuous contention a reader or writer may be delayed for a very long time, or even indefinitely.
- **Fair:** uses a policy approximating request order, selecting the longest-waiting writer or an appropriate group of readers in order. It can reduce the risk of starvation, usually at the cost of throughput. Fair does not mean deadline guarantees or absolute fairness from the OS scheduler.
- **Exception:** `readLock().tryLock()` and `writeLock().tryLock()` do not honor the fair setting; if the lock is immediately available, `tryLock()` can acquire it even if other threads are waiting.

When a writer must wait for many readers to release the lock, **writer latency** can suffer even when read throughput is high. Work inside a read lock should focus on what needs the protected state; independent I/O, callbacks, rendering, or heavy parsing can run after copying a snapshot and releasing the lock.

## 11. Condition: supported by write lock, not read lock

`ReentrantReadWriteLock` supports `Condition` on the **write lock**:

~~~java
ReentrantReadWriteLock rw = new ReentrantReadWriteLock();
java.util.concurrent.locks.Condition changed =
        rw.writeLock().newCondition();
~~~

`rw.readLock().newCondition()` throws `UnsupportedOperationException`; there is no `Condition` on the read lock.

To use `Condition.await()/signalAll()` properly, the thread must hold the associated write lock and follow a predicate protocol; `await` releases the write lock while waiting and reacquires it before returning. Illustrative pattern (not standalone):

~~~java
rw.writeLock().lock();
try {
    while (!ready) {
        changed.await();
    }
    // Read/modify state according to invariants.
} finally {
    rw.writeLock().unlock();
}
~~~

In a real example, another thread must update `ready` under that same write lock and call `signalAll()` when the condition changes. The `while` loop is essential because of spurious wakeups and because the predicate may have changed by the time the thread wakes up. For producer-consumer queues, `BlockingQueue` can express coordination more simply.

## 12. Interruption, timeouts, and tryLock

Locks implementing `Lock` support different acquisition operations:

| API | Usage |
| --- | --- |
| `lock()` | Wait for the lock; use `try/finally` to release |
| `lockInterruptibly()` | Can be interrupted while waiting; throws `InterruptedException` |
| `tryLock()` | Try immediately; returns `true` if acquired, `false` otherwise |
| `tryLock(timeout, unit)` | Wait up to the limit; returns boolean or throws `InterruptedException` |
| `unlock()` | Call only when the current thread actually holds the lock |

~~~java
// Snippet of a method returning boolean; not standalone.
if (!rw.writeLock().tryLock(100,
        java.util.concurrent.TimeUnit.MILLISECONDS)) {
    return false;
}
try {
    updateState();
    return true;
} finally {
    rw.writeLock().unlock();
}
~~~

If it times out, do not call `unlock()` because the lock was never acquired. This timeout only limits **how long to wait to acquire the lock**, not how long work runs inside the write section. When catching `InterruptedException`, have an appropriate stop/propagate policy; do not swallow the signal and wait forever.

## 13. Comparing options for read-heavy workloads

### A. `synchronized` or `ReentrantLock`

If critical sections are very short and contention is low, an exclusive lock can be both simpler and more efficient. Measure before switching to an RW lock. Exclusive locks are also easier to manage when multiple check-then-act steps and invariants require both reads and writes to be serialized.

### B. `ConcurrentHashMap`

Suitable when most operations read/write independent keys and a whole-map snapshot is not needed. `get`, `put`, `compute`, and `merge` each have their own contracts; **a `get` followed by `put` sequence is not automatically atomic**. If you need a multi-key transaction or a consistent snapshot of the entire map, another protocol may be necessary.

### C. `volatile` reference to an immutable snapshot

Small configurations that change rarely but are read very frequently can be represented as:

~~~java
// Snippet describing fields/methods in a class.
record Settings(String host, int port) {}

private volatile Settings current = new Settings("primary", 8080);

// Writer: build a complete new instance, then assign the reference.
current = new Settings("backup", 9090);

// Reader: capture the snapshot into a local variable.
Settings snapshot = current;
~~~

Here, there is no need to hold a read lock on every read; the volatile write/read publishes the initialization writes. However, if multiple writers read `current` → compute a new one → assign `current`, updates can still be lost. If `Settings` has a component pointing to a mutable object, a `record` does not make it deeply immutable.

### D. `AtomicReference<ImmutableState>`

Useful when multiple writers want to replace **the entire state** via CAS/`updateAndGet`. The update function should be pure because it may be retried. Atomicity applies to the reference being replaced, not to external side effects.

### E. `StampedLock`

Provides optimistic reads (`tryOptimisticRead`/`validate`), but it is a different kind of lock, is **not reentrant**, and has complex validation/visibility rules. Do not switch to `StampedLock` just for speed without understanding the code and benchmarking first.

**Selection summary:** An RW lock fits when you want **multiple readers of the same large structure** to enter the protected area concurrently, while still wanting exclusive writer updates and consistent reader snapshots.

## 14. Benchmarking properly

A useful benchmark must compare **the same logic and the same semantics** across `synchronized`, `ReentrantReadWriteLock`, `ConcurrentHashMap`, or immutable snapshots. Do not compare designs with different safety guarantees while looking only at throughput.

Vary the following dimensions:

1. **Read/write ratio**: e.g., 99/1, 90/10, 50/50.
2. **Reader/writer count, CPU cores**: are multiple reads actually executing concurrently?
3. **Read lock hold time**: reading 1 primitive or building a snapshot from a large map?
4. **Write lock hold time**: quick update or slow I/O?
5. **Fairness**: non-fair throughput versus p95/p99 write waiting latency.
6. **GC/allocation**: does snapshot copying create heap pressure?
7. **Realistic load**: peaks, writer bursts, thread counts, contention, starvation.

Use a benchmark harness like JMH with warmup, multiple runs, and statistical results; do not draw conclusions from a single short run with `System.nanoTime()` in `main`. In production, monitor read latency, write latency, queue wait time, and lock contention.

Instrumentation APIs such as `getReadLockCount()`, `getQueueLength()`, or `isWriteLocked()` are for monitoring only; a value measured at time `t` **is not a synchronization basis** for deciding to access state without a lock at time `t+1`.

## 15. Common implementation mistakes

| Mistake | Consequence | Correct approach |
| --- | --- | --- |
| Using a read lock for a getter with mutation | Concurrent writers/readers cause races | Distinguish pure reads from actual writes |
| Forgetting `unlock` on exception | Lock is never released, other threads hang | `try/finally` |
| Taking read lock and write lock from two different `rw` instances | No mutual exclusion between them | One shared instance for the state |
| Reader holds read then requests write | Can self-deadlock | Release read, acquire write, re-check |
| Not re-checking after transitioning read→write | Overwrites newer data, computes from stale snapshot | Re-check the condition under write lock |
| Reader holds read lock across slow HTTP/logging | Writers must wait a long time | Copy snapshot, process outside the lock |
| Returning a mutable object and mutating it outside the lock | Bypasses protection | Immutable value/copy or lock protocol |
| Snapshotting multiple fields in two separate reads | Mixes versions | One shared read section |
| Enabling fair mode and assuming no starvation/deadline issues | Misunderstands scheduling contract | Benchmark, timeouts, monitoring |
| Assuming `tryLock` is FIFO in fair mode | Barges ahead of waiting threads | Read the `tryLock` contract |
| Creating a `Condition` from the read lock | Unsupported operation | `Condition` from the write lock |
| Treating every cache `get` as read-only | LRU/lazy mutation causes reader conflicts | Classify operations by side effects |
| Wrapping a single `AtomicInteger` in a ReadWriteLock | Unnecessary overhead | Use atomic operations at the right scope |
| Choosing RW lock without benchmarking | May be slower than a simple exclusive lock | Measure on a representative workload |

## 16. Knowledge check questions

**1.** Why can 10 readers hold the read lock concurrently while a writer must wait?  
**Answer:** Because pure reads do not modify shared state, whereas a write needs exclusivity to protect invariants. The acquisition policy may make new readers wait when a writer is waiting.

**2.** A `HashMap` is protected by an RW lock; a getter returns a reference to an internal `ArrayList` and the caller mutates the list outside the lock. Is this safe?  
**Answer:** No. Protection only holds when callers follow the protocol for mutable state; you must copy or lock mutations to child objects as well.

**3.** Why must you not hold the read lock when calling `writeLock().lock()`?  
**Answer:** `ReentrantReadWriteLock` does not support upgrading. A write requires all read locks to be released, including the read lock held by the waiting thread itself.

**4.** After releasing the read lock and acquiring the write lock, do you need to re-check the cache miss state?  
**Answer:** Yes. Another thread may have populated the cache during the lock transition.

**5.** How does downgrading write→read differ from upgrading read→write?  
**Answer:** A writer can acquire the read lock while still holding the write lock and then release the write lock; a reader cannot request the write lock while holding the read lock.

**6.** Does `readLock().newCondition()` work?  
**Answer:** No, it throws `UnsupportedOperationException`. `Condition` belongs to the write lock.

**7.** Does fair mode force `tryLock()` to follow the waiting queue order?  
**Answer:** No. `tryLock()` does not honor the fairness setting.

**8.** An application is 99% reads, but every read is just a short single-key lookup. Is an RW lock guaranteed to be the fastest?  
**Answer:** No. Higher overhead, low contention, or `ConcurrentHashMap`/volatile snapshots may be better choices.

**9.** Is reading `total` and `version` under two separate read lock acquisitions always consistent?  
**Answer:** No. A writer can interleave in between; capture both fields in a single read critical section.

**10.** Should you measure only read throughput to decide on an implementation?  
**Answer:** No. Also consider writer latency, starvation, tail latency, memory, and correctness.

## Official references

- [`ReadWriteLock` — Java SE 17](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/concurrent/locks/ReadWriteLock.html): shared readers, exclusive writer, memory synchronization, performance tradeoffs.
- [`ReentrantReadWriteLock` — Java SE 17](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/concurrent/locks/ReentrantReadWriteLock.html): reentrancy, fairness, lock downgrading, no upgrading, Condition.
- [`Lock` — Java SE 17](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/concurrent/locks/Lock.html): acquisition, `tryLock`, interruption, `unlock`.
- [`Condition` — Java SE 17](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/concurrent/locks/Condition.html): predicate-based waiting/signaling.
- [`ConcurrentHashMap` — Java SE 17](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/concurrent/ConcurrentHashMap.html): concurrent map operations.
- [`StampedLock` — Java SE 17](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/concurrent/locks/StampedLock.html): alternative with optimistic reads.
- [Java Language Specification 17 — Threads and Locks](https://docs.oracle.com/javase/specs/jls/se17/html/jls-17.html): happens-before and synchronization.

**Remember:** Multiple readers can hold the read lock concurrently; a writer requires the exclusive write lock. Use the read lock only for **read-only critical sections**, always release locks in `finally`, never upgrade directly, and benchmark to prove benefits on your real workload.
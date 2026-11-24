# Locks, Atomic Variables, and Concurrent Data Structures in Java

In a Spring application, multiple HTTP requests, `@Async` tasks, `@Scheduled` jobs, or background threads may access the same object. If the object holds mutable state, simply using a `HashMap` or a plain `int` variable is not enough to guarantee correct results. This lesson focuses on synchronization mechanisms in Java (`java.util.concurrent`) and how to choose among them when writing Spring applications.

## 1. Learning Objectives

After this lesson, you will be able to:

- Explain **race conditions**, **visibility**, **atomicity**, **happens-before**, and distinguish data safety from thread progress (liveness).
- Choose among `synchronized`, `Lock`, `ReadWriteLock`, `StampedLock`, atomic variables, and immutable designs.
- Correctly use `ConcurrentHashMap`, `CopyOnWriteArrayList`, concurrent queues, and synchronized-wrapped collections.
- Spot non-atomic compound operations, handle interruption, avoid deadlocks, and apply these principles to Spring singleton beans.

## 2. Why Does Shared Data Break?

Suppose two threads concurrently execute `counter++` with `counter = 0`. The increment consists of three logical steps: reading the value, adding 1, and writing back. Both threads may read 0 and then both write 1; the final result is 1 instead of 2. This is a **lost update**, a form of race condition. When multiple threads read/write data without proper synchronization, issues also include observing stale values or seeing an inconsistent combination of state.

Three properties to keep distinct:

| Property | Question | Example |
| --- | --- | --- |
| **Atomicity** | Does the operation appear as an indivisible unit without interleaving? | Incrementing a counter with `AtomicInteger.incrementAndGet()` |
| **Visibility** | Is an update in one thread visible to another thread on time? | Writing then reading a `volatile` field |
| **Ordering / happens-before** | Is there a memory ordering constraint so a reader sees published state? | Releasing a lock before another thread acquires **the same lock** |

The Java Memory Model (JMM) defines **happens-before** relationships. Common ones include: an `unlock` happens-before a subsequent `lock` on the same lock; a `volatile` write happens-before a subsequent read of that same variable; `Thread.start()` publishes actions prior to start to the new thread; actions of a thread happen-before another thread successfully returns from `join()`. Atomic classes and concurrent collections provide their own API-documented memory guarantees.

**`volatile` does not make `counter++` atomic**: it primarily solves visibility and ordering for individual accesses. Only `synchronized`, `Lock`, or an appropriate atomic operation can protect a compound update. Never use `Thread.sleep()` to fix a race condition: delays do not create a reliable synchronization contract.

A **thread-safe** system preserves data invariants across multithreaded execution. However, it can still suffer from **deadlock** (threads waiting on each other), **starvation** (a thread continually denied service), or slowness due to lock contention. You must verify both correctness and liveness.

## 3. Intrinsic Locks: `synchronized`

Every Java object has a monitor, usable with `synchronized`. Inside a locked region, only one thread owns the monitor at a time; the monitor also provides visibility guarantees when releasing and acquiring the lock. `synchronized` methods on the same instance use that instance's monitor; `static synchronized` uses the `Class` object's monitor.

Example of a counter using the same lock for both reads and writes:

~~~java
public final class SynchronizedCounter {
    private final Object monitor = new Object();
    private int value;

    public void increment() {
        synchronized (monitor) {
            value++;
        }
    }

    public int get() {
        synchronized (monitor) {
            return value;
        }
    }
}
~~~

This is a standalone compilable class (without `main`); calls to `increment()` and `get()` both use the same lock object. If `get()` reads `value` directly outside a `synchronized` block, the state-protection protocol is broken. Prefer a `private final` lock; avoid locking on string literals, public objects, or objects that external code could also lock on.

Monitors are **reentrant**: a thread holding a lock can re-enter another method locking on the same monitor without deadlocking itself. `synchronized` automatically releases the monitor when exiting the block, even on exceptions. It suits short critical sections and simple logic. When you need timed lock attempts, interruptible lock acquisition, or multiple wait conditions, consider `ReentrantLock`.

## 4. `Lock`, `ReentrantLock`, and `Condition`

`java.util.concurrent.locks.Lock` separates lock acquisition/release from `synchronized` block syntax. `ReentrantLock` is the most commonly used implementation. Key operations:

- `lock()`: waits until the lock is acquired; this form of waiting itself does not respond to interruption with `InterruptedException`.
- `lockInterruptibly()`: can abort waiting if the thread is interrupted.
- `tryLock()` or `tryLock(timeout, unit)`: attempts to acquire immediately or within a duration; the timed overload can throw `InterruptedException`.
- `unlock()`: must be called **in `finally` after successfully acquiring the lock**; calling it when not holding the lock throws an error.

The following complete example combines `ReentrantLock` for a balance invariant and `AtomicInteger` for completed operation count. File **LockAtomicDemo.java**, Java 17+:

~~~java
import java.util.concurrent.CountDownLatch;
import java.util.concurrent.ExecutorService;
import java.util.concurrent.Executors;
import java.util.concurrent.TimeUnit;
import java.util.concurrent.atomic.AtomicInteger;
import java.util.concurrent.locks.ReentrantLock;

public final class LockAtomicDemo {
    private static final class Wallet {
        private final ReentrantLock lock = new ReentrantLock();
        private int balance;

        void add(int amount) {
            lock.lock();
            try {
                balance += amount;
            } finally {
                lock.unlock();
            }
        }

        int balanceValue() {
            lock.lock();
            try {
                return balance;
            } finally {
                lock.unlock();
            }
        }
    }

    public static void main(String[] args) throws InterruptedException {
        final int operations = 1_000;
        Wallet wallet = new Wallet();
        AtomicInteger processed = new AtomicInteger();
        CountDownLatch finished = new CountDownLatch(operations);
        ExecutorService pool = Executors.newFixedThreadPool(4);

        try {
            for (int i = 0; i < operations; i++) {
                pool.execute(() -> {
                    try {
                        wallet.add(2);
                        processed.incrementAndGet();
                    } finally {
                        finished.countDown();
                    }
                });
            }

            finished.await();
            System.out.println("processed=" + processed.get());
            System.out.println("balance=" + wallet.balanceValue());
        } finally {
            pool.shutdown();
            if (!pool.awaitTermination(5, TimeUnit.SECONDS)) {
                pool.shutdownNow();
            }
        }
    }
}
~~~

Run:

~~~bash
javac LockAtomicDemo.java
java LockAtomicDemo
~~~

Stdout:

~~~text
processed=1000
balance=2000
~~~

`finished.await()` waits for all 1,000 tasks to call `countDown()` before reading the results; hence the output does not depend on specific execution order. In production you must handle task errors, bound executor queues, and define a shutdown strategy; this example intentionally focuses on correctness of the two state types.

### `Condition`: Waiting for a State Condition

A `ReentrantLock` can create one or more `Condition` instances via `newCondition()`. When calling `await()`, the thread **releases the lock while waiting**, then must reacquire it before `await()` returns. A thread changing the condition can call `signal()`/`signalAll()` while holding the corresponding lock. Always check the condition in a `while` loop, never an `if`: spurious wakeups can occur or the condition may have changed before the thread runs.

Logic pattern (illustrative snippet inside a method holding `lock`, where `notEmpty` is a `Condition` and `queue` is protected by that lock):

~~~java
while (queue.isEmpty()) {
    notEmpty.await();
}
var item = queue.removeFirst();
~~~

Only use this pattern when you genuinely need custom conditions. For standard producer/consumer queues, `BlockingQueue` already encapsulates all waiting and signaling logic and is usually simpler and less error-prone.

### Read/Write Locks and Optimistic Reads

- `ReentrantReadWriteLock` provides a **read lock** for multiple concurrent readers and an exclusive **write lock**. Helpful when reads dominate writes and read sections are non-trivial. Do not use by default due to overhead and because a reader attempting to upgrade directly to a write lock can get stuck. Fairness is optional, though it carries a cost.
- `StampedLock` supports read/write locks and **optimistic reads** via stamps: read data, then call `validate(stamp)`; if invalid, re-read under a read lock. Never use a combination of optimistically read values before validation succeeds. This lock is **not reentrant** and has no `Condition` like `ReentrantLock`; exercise caution with complex data structures.
- Fair locks such as `new ReentrantLock(true)` can reduce unfair waiting, but typically lower throughput; they do not make OS scheduling completely fair.

## 5. Atomic Variables and Compare-and-Set (CAS)

Classes in `java.util.concurrent.atomic` provide atomic updates on a single variable/state without writing `synchronized` manually. Common choices:

| Class / Tool | Purpose |
| --- | --- |
| `AtomicInteger`, `AtomicLong` | Counting, incrementing/decrementing, updating numbers atomically |
| `AtomicBoolean` | Status flags needing atomic toggling/read-write |
| `AtomicReference<T>` | Atomically swapping a reference, optionally pointing to immutable state |
| `AtomicStampedReference<T>` | Attaching a version/stamp to detect certain forms of **ABA** |
| `LongAdder`, `DoubleAdder` | Accumulating statistics under high update contention |
| `AtomicIntegerArray` and atomic array family | Atomic updates on individual array elements |

Selected `AtomicInteger` APIs:

- `get()`, `set(v)`, `getAndSet(v)`: read/write/swap values.
- `incrementAndGet()` returns the value **after** incrementing; `getAndIncrement()` returns the value **before** incrementing.
- `addAndGet(delta)`, `updateAndGet(f)`, `accumulateAndGet(x, f)`: arithmetic/functional updates.
- `compareAndSet(expected, newValue)` (CAS): writes only if the current value still equals expected; returns `true` on success.

CAS creates an **optimistic retry** mechanism. Under contention, a thread re-reads state and retries; a successful atomic variable update is atomic. Example keeping available seats non-negative:

~~~java
AtomicInteger seats = new AtomicInteger(3);
boolean reserved = false;

while (true) {
    int remaining = seats.get();
    if (remaining == 0) {
        break;
    }
    if (seats.compareAndSet(remaining, remaining - 1)) {
        reserved = true;
        break;
    }
}
~~~

This is an **illustrative snippet**, requiring `import java.util.concurrent.atomic.AtomicInteger` and placement inside a method. If CAS fails because another thread changed the value, the loop re-reads and decides again. Seat deduction is protected; payment or database writes are separate tasks needing a consistency contract at the appropriate layer. Do not put network calls, side-effecting logs, or transactions inside functions passed to `updateAndGet`: the lambda may be recomputed when CAS retries.

**ABA** happens when state transitions A → B → A: a CAS comparing only current A against expected A may not know the state changed in between. Versioning/stamping is only needed when transition history matters to the algorithm; it is not a bug for every atomic counter.

**Atomic does not mean a multi-field transaction.** Two independent `AtomicInteger`s only guarantee their individual updates, not invariants like `available + reserved = capacity` while multiple threads read/write. When multiple fields must change together, share a single lock, or encapsulate immutable state in an `AtomicReference<State>` and swap the entire reference via a CAS retry loop.

### `AtomicLong` or `LongAdder`?

`AtomicLong` is convenient when you need an exact value on each atomic operation, such as generating the next sequence number. `LongAdder` distributes updates across internal cells to reduce contention, usually fitting **metrics and event counts**. `LongAdder.sum()` is not an atomic snapshot while threads are still updating; once all updates finish, the sum is exact. `reset()`/`sumThenReset()` also require considering races under concurrent updates.

## 6. Concurrent Data Structures

A thread-safe collection protects operations guaranteed by its API. That does **not** mean sequences of multiple calls are automatically atomic or that every iteration sees a consistent snapshot.

| Collection / Mechanism | How It Works and Use Cases | Limitations to Remember |
| --- | --- | --- |
| `ConcurrentHashMap<K,V>` | Map for concurrent readers/writers, key-level ops like `putIfAbsent`, `compute`, `merge` | Rejects `null` keys/values; weakly consistent iterators; compound operations are not automatically atomic |
| `ConcurrentSkipListMap/Set` | Sorted map/set with concurrent access | Usually higher overhead than hash-based structures when sorting is unneeded |
| `CopyOnWriteArrayList` / `CopyOnWriteArraySet` | Copies on write; iterators view a snapshot | Writes incur copy overhead and memory cost; fits read/iteration-heavy, rare-write workloads |
| `ConcurrentLinkedQueue` / `ConcurrentLinkedDeque` | Non-blocking concurrent queue/deque, does not wait for elements | Provides no backpressure and does not block when empty; `size()` can be O(n) and fluctuating |
| `ArrayBlockingQueue` | Fixed-capacity queue; `put/take` can wait | Waits indefinitely without a counterpart; needs shutdown/interruption handling |
| `LinkedBlockingQueue` | Blocking queue with configurable capacity | Without a specified capacity, default bound is huge; easy to accumulate unexpected backlog |
| `PriorityBlockingQueue` | Dequeues elements by priority | Unbounded by default capacity; equal-priority items do not guarantee FIFO |
| `Collections.synchronizedList/Map` | Wraps a regular collection to synchronize each method | Must manually lock around operation sequences and during iteration |

### A Thread-Safe Map Can Still Lose Updates

The following snippet is **wrong** when multiple threads increment the same key:

~~~java
ConcurrentHashMap<String, Integer> counts = new ConcurrentHashMap<>();
counts.put("ok", counts.getOrDefault("ok", 0) + 1);
~~~

Each `get` and `put` call is thread-safe, yet **the get → put pair is not atomic**. Use an API that combines the update into one operation:

~~~java
counts.merge("ok", 1, Integer::sum);
~~~

`ConcurrentHashMap`'s `merge`/`compute` protects the update for the target key. Keep mapping/remapping functions **short and pure**, avoiding long I/O or mutating the same map inside the function. For high-contention frequency counters, the standard idiom is:

~~~java
ConcurrentHashMap<String, LongAdder> frequencies = new ConcurrentHashMap<>();
frequencies.computeIfAbsent("ok", k -> new LongAdder()).increment();
~~~

In this example, `computeIfAbsent` ensures the same key receives a single `LongAdder`; the adder's `increment()` handles updates from multiple threads. Requires importing `java.util.concurrent.ConcurrentHashMap` and `java.util.concurrent.atomic.LongAdder`. Consistency when reading the entire map or summing across keys still requires separate design.

### Iterating Collections: Snapshots, Weak Consistency, and External Locking

- `ConcurrentHashMap` iterators are typically **weakly consistent**: they do not throw fail-fast `ConcurrentModificationException`, may reflect some recent changes, and do not promise a transactional snapshot.
- `CopyOnWriteArrayList` iterators view a snapshot taken when the iterator was created; later modifications do not appear in the ongoing iteration. `Iterator.remove()` is unsupported.
- With `Collections.synchronizedList(list)`, iterating requires synchronizing on the **wrapper list**: `synchronized (list) { for (var item : list) { ... } }`. Synchronizing only individual methods still leaves iteration exposed to interference.
- Immutable collections like `List.of(...)` eliminate structural changes to the list itself; if elements inside are mutable objects, those objects may still need synchronization. `Collections.unmodifiableList` is a view disallowing mutation through the view; it does not make the backing list immutable.

### `BlockingQueue`: Producer/Consumer and Backpressure

`BlockingQueue.put` waits when the queue is full and `take` waits when empty; `offer(value, timeout, unit)`/`poll(timeout, unit)` support timeouts. When producers outpace consumers, a **bounded** queue limits queued work and creates backpressure. Do not raise capacity endlessly just to hide overload issues.

Standalone Java 17+ example, file **QueueMapDemo.java**:

~~~java
import java.util.concurrent.ArrayBlockingQueue;
import java.util.concurrent.BlockingQueue;
import java.util.concurrent.ConcurrentHashMap;
import java.util.concurrent.atomic.LongAdder;

public final class QueueMapDemo {
    public static void main(String[] args) throws InterruptedException {
        BlockingQueue<String> queue = new ArrayBlockingQueue<>(2);
        ConcurrentHashMap<String, LongAdder> counts = new ConcurrentHashMap<>();

        Thread consumer = new Thread(() -> {
            try {
                while (true) {
                    String event = queue.take();
                    if ("STOP".equals(event)) {
                        break;
                    }
                    counts.computeIfAbsent(event, k -> new LongAdder())
                          .increment();
                }
            } catch (InterruptedException ex) {
                Thread.currentThread().interrupt();
            }
        });

        consumer.start();
        queue.put("ok");
        queue.put("ok");
        queue.put("fail");
        queue.put("STOP");
        consumer.join();

        System.out.println("ok=" + counts.get("ok").sum());
        System.out.println("fail=" + counts.get("fail").sum());
    }
}
~~~

Run:

~~~bash
javac QueueMapDemo.java
java QueueMapDemo
~~~

Stdout:

~~~text
ok=2
fail=1
~~~

The queue holds at most two elements at once; `put` may wait for the consumer to drain items. The string `"STOP"` serves as a **sentinel** to terminate the consumer in the demo; real systems must use a signal that cannot collide with valid data and, if multiple consumers exist, a shutdown strategy for each consumer. `join()` ensures main waits for the consumer to finish processing before reading results. Real applications must also handle producer/consumer errors, timeouts, cancellation, and draining the queue on shutdown.

## 7. Applying This in Spring

Normally `@Service`, `@Controller`, and many other beans have singleton scope: multiple requests can call **the same instance** concurrently. Spring creates and safely publishes beans, yet fields that are **mutable after initialization** are not thereby thread-safe. Example of an in-memory event counter per application instance:

~~~java
import java.util.concurrent.ConcurrentHashMap;
import java.util.concurrent.atomic.LongAdder;
import org.springframework.stereotype.Service;

@Service
public final class EventStats {
    private final ConcurrentHashMap<String, LongAdder> counts =
            new ConcurrentHashMap<>();

    public void record(String event) {
        counts.computeIfAbsent(event, k -> new LongAdder()).increment();
    }

    public long count(String event) {
        LongAdder value = counts.get(event);
        return value == null ? 0L : value.sum();
    }
}
~~~

This is an **illustrative Spring component**, file `EventStats.java`, requiring the Spring Framework dependency and having no `main`. The map and adders handle concurrent access within **one JVM**; `count` returns an observed sum, not an atomic snapshot during ongoing updates. Do not use such data as account balances, inventory, or a source of truth requiring durability.

When adding `@Async`, `@Scheduled`, or configuring `TaskExecutor`/`ThreadPoolTaskExecutor`:

1. Identify fields shared across calls; prefer local variables, immutable objects, and passing state via parameters. Avoid holding per-request details on singleton fields.
2. If sharing is required, document the **invariants** and protect **every access point** with the same protocol: atomics, locks, or concurrent structures.
3. Configure appropriate thread/queue bounds, and handle exceptions, timeouts, interruption, and lifecycle-aligned resource closing. Certain internal calls within the same bean can bypass the default `@Async` proxy.
4. Avoid holding JVM locks while waiting on HTTP, databases, or long-running tasks when an asynchronous design, queue, or transaction can be used instead.

**Crucial boundary:** `synchronized`, `ReentrantLock`, and `ConcurrentHashMap` synchronize only within **a single JVM process**. If a Spring application runs 3 replicas, each replica has its own state and locks. For cross-process business data, consider database transactions, optimistic locking with version fields, conditional updates, unique constraints, or appropriate distributed mechanisms. `@Transactional` handles transactional semantics for resources like databases; it **does not automatically lock** Java fields in a singleton bean. Conversely, holding a JVM lock does not substitute for a database transaction.

## 8. Solution Selection Table by Scenario

| Practical Requirement | Starting Choice to Consider | Why |
| --- | --- | --- |
| Incrementing a single counter needing atomic read/update | `AtomicInteger` / `AtomicLong` | Simple, no manual lock management |
| High-thread-count event counting, metrics not needing an instant snapshot | `LongAdder` | Reduces update contention |
| Multiple fields must change together under one invariant | `synchronized` / `ReentrantLock` | Protects the entire update region as a unit |
| Need timeout or interruption while waiting for a lock | `ReentrantLock.tryLock` / `lockInterruptibly` | Controls liveness and wait cancellation |
| Read-heavy, write-rare with significant lock hold time | `ReentrantReadWriteLock`; sometimes `StampedLock` | Can increase reader parallelism after measurement |
| Multi-threaded map; per-key operations | `ConcurrentHashMap.compute/merge` | Key updates atomic per API contract |
| Listener list read very often, mutated very rarely | `CopyOnWriteArrayList` | Snapshot iteration, no manual iterator locking needed |
| Producer/consumer pipeline with bounded backlog | `ArrayBlockingQueue` / bounded `LinkedBlockingQueue` | Provides backpressure, supports waiting |
| Need sorted order and concurrent updates | `ConcurrentSkipListMap/Set` | Sorted concurrent structure |
| Data needs no mutation after initialization | Immutable objects / immutable collections | Eliminates shared mutable state |
| Inventory/balance shared across multiple replicas | Database transactions / optimistic versioning | JVM locks do not span replicas |

No single structure is always fastest. Cost depends on contention, read/write ratio, key count, data size, critical section length, and consistency needs. Benchmark with realistic workload data before optimizing.

## 9. Common Mistakes and How to Prevent Them

1. **Using `volatile int count` followed by `count++`.** This is still a non-atomic read-modify-write. Replace with `AtomicInteger` or appropriate synchronization.
2. **Thinking `ConcurrentHashMap` makes every command sequence safe.** The pattern `if (!map.containsKey(k)) map.put(k,v)` still has a race. Use `putIfAbsent`, `computeIfAbsent`, `compute`, or `merge` as required.
3. **Reading part of state under a lock and another part outside.** Multi-field invariants can be violated. Clearly define the protected region and use the same lock consistently.
4. **Forgetting `unlock()` or holding locks during I/O.** Always use `try/finally`; separate short in-lock computation from network/DB calls where possible.
5. **Acquiring multiple locks in arbitrary order.** Two threads can lock A then wait for B and lock B then wait for A. Enforce a global lock order, reduce nesting, or use `tryLock` with timeouts and bounded retry strategies.
6. **Ignoring `InterruptedException`.** If unable to propagate, typically restore the flag via `Thread.currentThread().interrupt()` and exit/cancel logic appropriately rather than silently continuing to wait.
7. **Using `CopyOnWriteArrayList` for frequently updated lists.** Every write copies the backing array, easily costing CPU/memory.
8. **Using `LongAdder.sum()` for decisions needing a linearizable snapshot.** `sum()` is not atomic during updates; consider an atomic counter or lock.
9. **Iterating `Collections.synchronizedMap/List` without external locking.** The wrapper does not protect the entire loop; synchronize on the wrapper throughout iteration.
10. **Assuming a test passing once with no visible race proves thread safety.** Interleavings depend on timing; check invariants, use barriers/latches to reproduce scenarios, and stress-test repeatedly. Use JFR/thread dumps to analyze contention/deadlocks; use JMH when comparing performance.
11. **Storing business data in singleton fields and scaling horizontally.** Each replica's state diverges; choose a shared data store or an appropriate partitioned architecture.
12. **Thinking virtual threads eliminate race conditions.** Virtual threads (Java 21+) still access shared state like other threads; proper synchronization is still required, and long blocking lock regions should be minimized.

## 10. Self-Check Questions

1. Why does `volatile` make changes visible across threads yet fail to keep `x++` accurate?
2. When is an `AtomicReference` to an immutable state object more sensible than multiple separate atomic variables?
3. Why are `map.get` followed by `map.put` unsafe even when `map` is a `ConcurrentHashMap`? Would you choose `merge` or `compute`?
4. `LongAdder` fits metrics, yet why should `sum()` not be used to decide whether exactly one reservation slot remains?
5. What happens if `ReentrantLock.unlock()` is not inside `finally` or `Condition.await()` checks its condition with only an `if`?
6. Can a Spring service running three replicas use `synchronized` to guarantee not overselling database inventory? Why or why not?

## 11. Official References

- [Java SE 17 – java.util.concurrent](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/concurrent/package-summary.html)
- [Java SE 17 – concurrent locks](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/concurrent/locks/package-summary.html)
- [Java SE 17 – atomic variables](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/concurrent/atomic/package-summary.html)
- [Java SE 17 – ConcurrentHashMap](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/concurrent/ConcurrentHashMap.html)
- [Spring Framework – Task Execution and Scheduling](https://docs.spring.io/spring-framework/reference/integration/scheduling.html)

**Takeaway:** Start from your data invariants and sharing scope (one object, one JVM, or multiple processes). Choose the smallest tool that satisfies atomicity, visibility, and liveness; optimize only based on observed contention and real monitoring data.
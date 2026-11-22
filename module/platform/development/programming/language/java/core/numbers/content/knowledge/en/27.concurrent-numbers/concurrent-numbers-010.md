# Choosing Synchronization Levels Based on the Required Consistency Contract

## 1. The Problem: What Does "Correct" Mean When Multiple Threads Update Numbers?

In a multithreaded application, multiple workers may concurrently increment a counter, accumulate revenue totals, deduct inventory, or update both counts and total amounts. Even though all of these involve numeric data, each business case needs a **different level of consistency**:

- A dashboard only needs an approximate request count *at observation time* while requests continue arriving.
- A sequence-number API requires every caller to receive a unique value without losing increments.
- A reservation transaction must guarantee two threads cannot both claim the last remaining slot.
- A report containing `count` and `total` must reflect **the same state**; you must not read a new `count` paired with an old `total` when they are constrained together.

Thus, the right question before choosing `volatile`, `AtomicLong`, `LongAdder`, or `synchronized` is: **What consistency contract must be guaranteed, and at what point in time?**

This lesson focuses on choosing synchronization mechanisms for numeric data within **a single JVM process** on Java 17+. Synchronization across multiple JVMs, databases, and distributed services requires different transaction/coordination contracts; the primitives below do not solve that scope on their own.

## 2. Three Foundational Concerns: Atomicity, Visibility, and Ordering

### 2.1. Atomicity — Can an Update Be Interleaved and Lose Data?

```java
class UnsafeCounter {
    private long count;

    void increment() {
        count++; // read -> add 1 -> write; not an atomic operation
    }

    long get() {
        return count;
    }
}
```

If two threads both read `count == 5` and both write `6`, the application can lose an increment. This is a **race condition**. Even when a single `long` read or write is atomic on a given platform/JVM, the expression `count++` remains a read–modify–write sequence and is unprotected against lost updates.

### 2.2. Visibility — Do Other Threads See the Change?

Without proper synchronization relationships, a thread may continue using stale values, or the compiler/CPU/JVM may reorder operations under optimizations permitted by the Java Memory Model (JMM). `volatile` guarantees visibility and certain *happens-before* ordering relationships:

```java
class ShutdownSignal {
    private volatile boolean stopped;

    void stop() {
        stopped = true;
    }

    void work() {
        while (!stopped) {
            // Check stop signal from another thread.
        }
    }
}
```

This snippet illustrates a signal; a busy spin is not necessarily good design for real workloads. You can use a blocking queue, interruption, or another coordination mechanism to avoid burning CPU.

A write to a `volatile` variable *happens-before* subsequent reads of that same variable under JMM rules. However, `volatile` **does not** make `count++` atomic and **does not** turn a group of variables into a transaction.

### 2.3. Ordering — Do Operations Appear in the Required Order?

The JMM permits certain instruction reorderings as observed from other threads, provided legal rules are respected. `synchronized`, `volatile`, atomic operations, and standard concurrency constructs establish ordering/visibility boundaries per their contracts.

For example, when one thread writes data fields and then signals via a `volatile` variable, another thread that properly reads the signal and then reads the data obtains the appropriate happens-before relationship. This holds only when the full publication/read protocol is followed properly; merely adding an arbitrary `volatile` variable does not make all shared data safe.

## 3. Choose the Consistency Level Before Choosing the Tool

| Required contract | Commonly suitable mechanism | Primary guarantee |
| --- | --- | --- |
| An independent status flag published/read across threads | `volatile` or `AtomicBoolean` | Visibility and proper ordering; no compound updates |
| Every increment of a single counter must be recorded with immediate exact reads | `AtomicInteger` / `AtomicLong` | Atomic operations on **one variable** |
| Counting total events with very many writers, tolerating non-atomic snapshot reads during updates | `LongAdder`, `DoubleAdder` | High-throughput aggregation; `sum()` is not an atomic snapshot under concurrent updates |
| Maintaining max/min/accumulated total via consistent merges across writers | `AtomicLong` with CAS/update, `LongAccumulator` when appropriate | Atomic single-state updates or parallel accumulation with rules |
| Must check a condition and update as **one action** | `compareAndSet` loop or lock | Condition and mutation share one decision point |
| Multiple related fields must always satisfy an invariant and consistent snapshots | `synchronized`, `ReentrantLock`, or immutable state in `AtomicReference` | Updating and reading **the whole state** under one protocol |
| Multiple DB rows or multiple services must remain consistent | DB transactions, optimistic locking/versioning, distributed protocols | Contract outside local JVM scope |

These choices are **guidelines**, not automatic substitutes. `AtomicLong` does not fix bugs when business logic spans multiple variables; `LongAdder` is unsuitable for issuing exact sequence numbers at increment time; locks can be safe while hurting parallelism if scoped too broadly.

## 4. Case 1 — Only Needing Visibility of One State

For an independent flag such as `enabled`, `stopped`, or `ready`, `volatile boolean` is usually sufficient if all operations are simple state writes/reads with proper publication.

```java
private volatile boolean enabled = true;

// Control thread:
enabled = false;

// Workers:
if (!enabled) {
    return;
}
```

These are embedded snippets of a class, not a standalone Java program.

**Distinguish from check-then-write conditions:** if two workers require "only one transitions from `false` to `true` and executes the job," the code:

```java
if (!started) {
    started = true;
    startJob();
}
```

still races even when `started` is `volatile`. Two threads can both read `false`. The "only one thread wins" contract needs an atomic action:

```java
AtomicBoolean started = new AtomicBoolean(false);

if (started.compareAndSet(false, true)) {
    startJob(); // only the thread that succeeds false -> true runs this
}
```

This snippet requires `import java.util.concurrent.atomic.AtomicBoolean;`. `compareAndSet` performs the conditional swap atomically on one variable. For jobs that can fail, add appropriate recovery/retry design for `started`; CAS only solves single-start ownership, not reliable workflow execution on its own.

## 5. Case 2 — Single Counter Needing Exact Results at Observation Points

`AtomicInteger` and `AtomicLong` work well when all information to protect resides in **a single value**:

```java
import java.util.concurrent.atomic.AtomicLong;

AtomicLong count = new AtomicLong(0);

long afterIncrement = count.incrementAndGet();
long beforeIncrement = count.getAndIncrement();
long current = count.get();
```

Each atomic call updates/reads that variable's state in a consistent (*linearizable*) order, losing no increments if all workers use that same variable properly. `getAndIncrement()` returns the old value; `incrementAndGet()` returns the new value.

However, two consecutive calls **do not create a transaction**. For example:

```java
if (count.get() < 100) {
    count.incrementAndGet(); // can still exceed 100 because another worker interleaves
}
```

Both `get()` and `incrementAndGet()` are individually atomic, yet the **check-then-update** is not performed atomically.

### 5.1. Using CAS for Conditional Updates

Example of a quota counter with bound `limit`:

```java
static boolean tryClaim(AtomicInteger used, int limit) {
    if (limit < 0) {
        throw new IllegalArgumentException("limit must be non-negative");
    }

    while (true) {
        int current = used.get();
        if (current >= limit) {
            return false;
        }
        if (used.compareAndSet(current, current + 1)) {
            return true;
        }
        // Another thread changed used: re-read and retry.
    }
}
```

This is an **embedded method** requiring `import java.util.concurrent.atomic.AtomicInteger;`. Assume `used` is initialized non-negative and only modified via valid protocols. With a positive `int` limit within range, the addition avoids overflow since `current < limit`. A successful `compareAndSet` is the **linearization point** for claiming a slot; competing threads vying for the last slot cannot both win if they share `used`.

A CAS loop may retry multiple times under contention and requires proper state/overflow handling. If business logic involves multiple variables, CAS on `used` alone is insufficient; bundle the entire state into one immutable object updated atomically or use a lock.

### 5.2. `updateAndGet` and Side Effects

```java
AtomicLong maxSeen = new AtomicLong(0);

long newMax = maxSeen.updateAndGet(
        current -> Math.max(current, 42L));
```

Update lambdas on certain atomic methods **may be re-invoked** under contention. They must be side-effect-free: avoid calling payment APIs, writing to DBs, sending emails, or incrementing another counter inside the lambda. Compute only the new state from the old state; perform side effects afterward once the result is determined per your business design.

`AtomicLong` can overflow like an ordinary `long`; atomicity **does not** add automatic overflow checks. If counts must never wrap around, place overflow checks/exceptions inside a properly designed atomic update.

## 6. Case 3 — High-Writer Statistics: `LongAdder`

For goals like "counting requests seen" in a system with many threads, `LongAdder` distributes updates internally to reduce contention on a single hotspot:

```java
import java.util.concurrent.atomic.LongAdder;

LongAdder requests = new LongAdder();

requests.increment();
requests.add(5L);

long currentlyObserved = requests.sum();
```

**Crucial contract:** `LongAdder.sum()` **is not an atomic snapshot** while multiple threads are updating. The result may omit some ongoing concurrent updates. If you must check a quota limit at the exact moment of each update or need a unique return value after each `increment`, use a mechanism with the right atomic contract rather than mechanically swapping `LongAdder` for `AtomicLong`.

After all writers complete and a synchronization edge confirms completion (such as awaiting all `Future.get()` calls), `sum()` reflects the completed updates. Section 9's example verifies this.

`LongAdder.reset()` and `sumThenReset()` should likewise not be used assuming an **exact snapshot while writers are still updating**. Apply them when no concurrent updates occur, or when the business accepts monitoring metrics over intervals that are not strictly crisp.

If values are floating-point, `DoubleAdder` follows the same idea, except that because floating-point addition order can vary across threads, results are not guaranteed to match bit-for-bit across runs.

### 6.1. Per-Label Counters in `ConcurrentHashMap`

```java
import java.util.concurrent.ConcurrentHashMap;
import java.util.concurrent.atomic.LongAdder;

ConcurrentHashMap<String, LongAdder> counts = new ConcurrentHashMap<>();

counts.computeIfAbsent("success", key -> new LongAdder()).increment();
counts.computeIfAbsent("failure", key -> new LongAdder()).increment();

long success = counts.get("success").sum();
```

`computeIfAbsent` safely creates/looks up values per key under concurrent access on `ConcurrentHashMap`. Each `LongAdder` then records increments. However, reading multiple labels sequentially **does not form a whole-map snapshot**; the sum of labels observed during ongoing updates may not match a system-wide counter at a single point in time.

If "success + failure = total requests" must hold in one exact snapshot for reconciliation, design a consistent snapshot mechanism or collect results after the entire write period finishes.

## 7. Case 4 — Multiple Values Must Preserve a Joint Invariant

Suppose every accepted transaction does two things together:

1. Increments `count` by 1.
2. Increases `total` by 2 units.

The business invariant requires every snapshot to satisfy `total == 2 * count`. Two separate `AtomicLong` variables cannot guarantee reading a consistent pair of states:

```java
AtomicLong count = new AtomicLong();
AtomicLong total = new AtomicLong();

// Writer:
count.incrementAndGet();
total.addAndGet(2);

// Reader:
long seenCount = count.get();
long seenTotal = total.get();
// These two values may come from two different instants.
```

Each variable updates atomically, yet **the pair is not updated simultaneously**. A reader can observe the new `count` and old `total`. Putting `volatile` on both fields does not turn two writes into one transaction either.

### 7.1. `synchronized`: One Lock Protecting the Entire State

```java
record Snapshot(long count, long total) {}

final class Ledger {
    private long count;
    private long total;

    synchronized void add(long value) {
        count++;
        total += value;
    }

    synchronized Snapshot snapshot() {
        return new Snapshot(count, total);
    }
}
```

This is a class/record example you can place in a program in the same package. Every writer calls `add`, every reader obtains the pair via `snapshot`, and **no other access path bypasses the lock**. Then modifying both fields and reading both fields are serialized through the same monitor.

`snapshot()` returns an immutable record containing **the pair of values read inside the same critical section**. As soon as the monitor is released, another worker may update `Ledger`; the snapshot may become stale, yet it remains **internally consistent**. Stale does not mean torn across fields.

If only `add` is marked `synchronized` while `snapshot` reads the fields directly without synchronization, there is no complete contract for reading the same state. All access paths must follow the same protection protocol.

### 7.2. Explicit Locks When Finer Control Is Needed

`ReentrantLock` can protect the same invariant:

```java
import java.util.concurrent.locks.ReentrantLock;

final class LockedTotal {
    private final ReentrantLock lock = new ReentrantLock();
    private long count;

    void increment() {
        lock.lock();
        try {
            count++;
        } finally {
            lock.unlock();
        }
    }

    long snapshot() {
        lock.lock();
        try {
            return count;
        } finally {
            lock.unlock();
        }
    }
}
```

Use `try/finally` to ensure unlocking if an exception occurs. `ReentrantLock` is suitable if you need `tryLock`, interruptible lock waiting, multiple conditions, or finer control. For a simple invariant, `synchronized` is often easier to read and harder to get wrong.

When multiple locks exist, define a lock acquisition order to avoid deadlocks; never hold locks too broadly while waiting on I/O, calling slow services, or invoking uncontrolled callbacks.

`ReadWriteLock` can support multiple concurrent readers when reads dominate and operations are structured properly, though it is not guaranteed to outperform a monitor; lock overhead and contention depend on the workload.

### 7.3. Immutable State in One `AtomicReference`

Another option for a pair of states is representing **the entire invariant as one immutable object** and swapping the whole object in one atomic operation:

```java
import java.util.concurrent.atomic.AtomicReference;

record State(long count, long total) {}

AtomicReference<State> state =
        new AtomicReference<>(new State(0L, 0L));

state.updateAndGet(previous ->
        new State(previous.count() + 1, previous.total() + 2));

State snapshot = state.get();
```

This is an embedded snippet. Reading `state.get()` yields a consistent snapshot of **both fields inside the immutable object**. `updateAndGet` may call the lambda multiple times under contention; the lambda must be pure and free of side effects. Every update allocates a new object, incurring allocation and retry costs; do not assume this approach beats a lock for all workloads.

If the invariant spans multiple objects or resources outside the JVM (DB accounts, message brokers), atomic publication of a `State` inside the JVM is insufficient to create a system-wide transaction.

## 8. `happens-before`, Observation Timing, and Operation Boundaries

A consistency contract must specify **when** callers are allowed to treat data as finalized.

In Java, common happens-before relationships include:

- A monitor unlock *happens-before* every subsequent lock acquisition on the same monitor.
- A `volatile` write *happens-before* every subsequent matching read of that volatile variable.
- Atomic classes and constructs in `java.util.concurrent` provide memory guarantees per their API documentation.
- Actions of a task in an executor happen before another thread retrieves the result via `Future.get()` under the API's memory consistency rules.

Once **all** `Future.get()` calls have completed, a reader can fetch final counter totals with no concurrent writers remaining from that group of tasks. Conversely, reading mid-flight across multiple separate structures may not reflect one shared instant, even if each structure is individually thread-safe.

### Distinguishing Three Commonly Confused Contracts

**Freedom from data races:** Accesses are properly synchronized; no illegal reads/writes under the JMM.

**Atomic/linearizable for one operation:** A single call like `AtomicLong.incrementAndGet()` can be reasoned about as taking effect at a single point between invocation and return.

**Consistent snapshot of multiple variables:** All components must originate from one valid state (such as under the same monitor or the same immutable object published atomically).

A system can satisfy the first and second criteria per variable while still violating the third. That is precisely why you **choose synchronization levels by contract**, rather than merely asking "is it thread-safe?"

## 9. Complete Java 17+ Program: Comparing `AtomicLong`, `LongAdder`, and Locked Snapshots

Save **`ConsistencyContractDemo.java`**:

```java
import java.util.ArrayList;
import java.util.List;
import java.util.concurrent.ExecutionException;
import java.util.concurrent.ExecutorService;
import java.util.concurrent.Executors;
import java.util.concurrent.Future;
import java.util.concurrent.atomic.AtomicLong;
import java.util.concurrent.atomic.LongAdder;

public class ConsistencyContractDemo {
    record Snapshot(long count, long total) {}

    static final class Ledger {
        private long count;
        private long total;

        public synchronized void add(long value) {
            count++;
            total += value;
        }

        public synchronized Snapshot snapshot() {
            return new Snapshot(count, total);
        }
    }

    public static void main(String[] args)
            throws InterruptedException, ExecutionException {

        int workers = 4;
        int iterations = 10_000;

        AtomicLong atomicCount = new AtomicLong();
        LongAdder adderCount = new LongAdder();
        Ledger ledger = new Ledger();

        ExecutorService executor = Executors.newFixedThreadPool(workers);
        try {
            List<Future<?>> futures = new ArrayList<>();

            for (int i = 0; i < workers; i++) {
                futures.add(executor.submit(() -> {
                    for (int j = 0; j < iterations; j++) {
                        atomicCount.incrementAndGet();
                        adderCount.increment();
                        ledger.add(2);
                    }
                }));
            }

            // Wait for all writers to complete before reading final metrics.
            for (Future<?> future : futures) {
                future.get();
            }

            Snapshot snapshot = ledger.snapshot();

            System.out.println("atomic count = " + atomicCount.get());
            System.out.println("adder count = " + adderCount.sum());
            System.out.println("snapshot count = " + snapshot.count());
            System.out.println("snapshot total = " + snapshot.total());
            System.out.println("snapshot invariant = "
                    + (snapshot.total() == 2 * snapshot.count()));
        } finally {
            executor.shutdown();
        }
    }
}
```

Compile and run:

```bash
javac ConsistencyContractDemo.java
java ConsistencyContractDemo
```

Exact stdout when tasks complete normally:

```text
atomic count = 40000
adder count = 40000
snapshot count = 40000
snapshot total = 80000
snapshot invariant = true
```

**Mechanism and meaning of the output:**

1. Four workers, each running 10,000 iterations. Total iterations equal 40,000.
2. `AtomicLong` receives one atomic increment per iteration; it fits when an exact counter needs to be read at an observation point.
3. `LongAdder` also receives 40,000 increments. `sum()` is read **after** all `Future.get()` calls complete, so the final result is 40,000. Reading while writers remain active would not have an atomic snapshot contract.
4. `Ledger.add(2)` guards `count++` and `total += 2` together; `snapshot()` holds the same monitor while capturing both values. The invariant `total == 2 * count` is preserved in the snapshot.
5. Although all three counters yield the same final count, **the three calls inside each loop iteration are not a joint transaction**. If read concurrently while workers are running, `atomicCount`, `adderCount`, and `ledger` can report different values because they are updated sequentially. The example illustrates separate contracts, not instantaneous agreement across all three sources.

The program uses `try/finally` to call `shutdown()` on the executor in Java 17. Real applications also need policies for timeouts, task cancellation, interruption, and awaiting termination; `shutdown()` does not mean waiting for all tasks to finish. Here, the `Future.get()` loop already awaited the submitted tasks before reading.

## 10. Decisions That Can Break Consistency

### 10.1. Splitting One Invariant Across Multiple Atomic Primitives

If `availableSlots` and `reservedSlots` must together satisfy a fixed sum, updating two `AtomicInteger` variables separately can create a window where readers see an invalid pair. To protect related state, use a shared lock or a single immutable snapshot inside `AtomicReference`.

### 10.2. Putting `volatile` on `int` and Calling `++`

`volatile int count` still does not turn `count++` into an atomic operation. Choose `AtomicInteger.incrementAndGet()` or a monitor if the counter must reflect every increment.

### 10.3. Using `LongAdder.sum()` to Decide "Is Quota Available?"

`sum()` during updates does not guarantee a linearized snapshot; "`if(sum() < limit) increment()`" suffers from both snapshot skew and check-then-act races. Use CAS/locks/transactions designed for reservation.

### 10.4. Guarding Writers While Forgetting Readers

`synchronized void update()` does not make an unsynchronized method reading fields directly see a consistent snapshot. You must guard **all** read and write paths of the state under the same protocol.

### 10.5. Holding Locks While Calling External Services

Calling databases, HTTP APIs, or uncontrolled callbacks inside a lock lengthens the critical section, causing contention and deadlock risks. When atomicity across external resources is required, you cannot simply "wrap the whole API call in synchronized" and expect a distributed transaction to appear.

### 10.6. Assuming `ConcurrentHashMap` Makes All Compound Operations Atomic

`ConcurrentHashMap.compute`, `putIfAbsent`, and per-key operations have their own concurrency contracts, yet the map's thread safety does not make operations across **multiple keys** a single transaction. For example, transferring a value between two accounts under two keys requires a broader consistency protocol.

### 10.7. Forgetting Overflow, Floating-Point Error, and Exact Definitions

`AtomicLong` preserves atomicity yet does not stop `long` addition from overflowing. `DoubleAdder` is a floating-point sum that can differ bit-for-bit due to non-fixed addition order. When summing money, choose appropriate numeric types and consistency designs (such as integer minor units within non-overflowing bounds, or `BigDecimal` after evaluating performance needs); concurrency primitives do not fix arithmetic precision.

## 11. Measuring and Testing the Contract

**Before benchmarking**, write assertions matching the contract. For example, in the final-total case like the demo: once all tasks complete, `atomicCount.get() == workers * iterations`, `adderCount.sum() == workers * iterations`, and `snapshot.total() == 2 * snapshot.count()`.

If readers read while writers remain active, assert only invariants **actually guaranteed by the mechanism**. For `Ledger`, every snapshot must be internally consistent. Do not assert that three independent structures always hold identical counts at every instant, since the program never created a transaction across them.

Race tests should run enough threads, iterations, and varied inputs, yet passing 100 runs without exposing a bug **does not prove** an unsynchronized program is correct. Reasoning via happens-before, atomicity, and invariants is foundational; concurrency testing tools can help uncover subtle interleavings.

For performance, consider:

- Contending writer count, update frequency, and read frequency.
- Lock contention costs, immutable state allocations, and CAS retries.
- Read/write ratio and critical section scope.
- Throughput vs. latency requirements, and the specific CPU/JVM/JIT environment.
- Business value of reading an exact snapshot versus approximate monitoring metrics.

`LongAdder` can provide strong throughput at high-writer hotspots, yet there is no fixed "N times faster" multiplier. Use benchmarks like JMH for micro-comparisons and measure real workloads for architectural decisions.

## 12. Decision Checklist for Shared Numeric Data

When receiving a new requirement, answer sequentially:

1. **What state is shared?** A flag, a number, a pair of numbers, a map, or a cross-service transaction?
2. **When must it be exact?** On every update, whenever a reader calls an API, at batch end, or only at period close?
3. **Is an "approximate value during writes" acceptable?** If yes, statistical counters like `LongAdder` may fit. If no, an explicit snapshot mechanism is needed.
4. **Is there a check-then-modify step?** CAS/locks must cover both, avoiding separate `get` then `set`.
5. **Is there an invariant across multiple fields?** Protect under one critical section or publish immutable state atomically.
6. **Is the scope within one JVM?** If a DB or other service participates, design transactions/idempotency/versioning outside the JVM.
7. **Who can write and who can read?** Encapsulate state and unify the protocol; leave no "shortcut" reads/writes bypassing synchronization.
8. **Does the numeric type have sufficient range and precision?** Guard against overflow, distinguish `double` from exact decimals; synchronization does not replace arithmetic policy.

Quick summary table:

| You need | Consider first |
| --- | --- |
| Simple stop/ready signal | `volatile`/`AtomicBoolean` |
| Every increment of one value counted accurately, atomic reads | `AtomicLong`/`AtomicInteger` |
| Very many writers updating metrics, `sum()` only for observation | `LongAdder`/`DoubleAdder` |
| Conditional slot allocation | CAS loop or lock spanning check–update |
| Multiple fields with invariants and snapshots | `synchronized`, `ReentrantLock`, or `AtomicReference` to immutable state |
| Reconciliation across multiple JVMs or DBs | Transactions, versioning, appropriate distributed protocols |

## 13. Self-Practice Exercises

1. Why can `volatile int count; count++;` still lose increments? Describe two interleavings of two workers.
2. A service must issue 100 tickets and never exceed 100. Why is `if (atomic.get() < 100) atomic.incrementAndGet()` still wrong? Design a claim operation using CAS.
3. A dashboard displays requests/sec every second with hundreds of workers. Does it need a linearized snapshot on every read, or is `LongAdder.sum()` enough? Which contract does the answer depend on?
4. `successCount` and `failedCount` are incremented in two different structures. Why does reading both counters sequentially not guarantee capturing the same snapshot?
5. If you replace `Ledger` in the demo with two `AtomicLong` fields, is the invariant `total == 2 * count` still guaranteed on every read during updates? Explain.
6. Write a `Ledger` version using `AtomicReference<State>` with `record State(long count, long total)`. Show that the update lambda has no side effects.
7. Why does awaiting `Future.get()` of all workers change what can be asserted about final totals, yet **does not** turn mid-run updates into a transaction across the three counters?
8. A service runs two JVM replicas that both modify one inventory row in a DB. Why is `synchronized` inside each replica insufficient? Propose an appropriate transaction boundary.

**Suggested answers:** (1) `++` involves read–compute–write; two threads can both read the old value. (2) Conditional CAS on the same variable is needed. (3) If monitoring tolerates non-linearized metrics while writers update, `LongAdder` can be valid. (4) Each read occurs at a different instant with no shared snapshot. (5) No; updates and reads across two variables are not atomic as a group. (6) `AtomicReference` publishes the immutable pair in one swap; the lambda may re-run. (7) Once all tasks complete, no writers from that group remain, whereas mid-run reads can reflect different instants. (8) JVM locks apply only within one process; DB transactions/row locks/versioning protect shared state.

## 14. Takeaways for Practice

Choosing a synchronization mechanism starts from **the business unit of invariance**, then considers performance. A flag needs visibility, a counter needs atomic increments, statistics can tolerate non-linearized reads during updates, and a group of variables must be updated and observed under a unified protocol. Make sure every caller understands whether the promised state is **one exact value**, **an internally consistent snapshot**, or **an observational metric at read time**.

Java SE 17 Documentation:
- [`java.util.concurrent.atomic`](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/concurrent/atomic/package-summary.html) (`AtomicLong`, `AtomicReference`, `LongAdder`).
- [`ExecutorService`](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/concurrent/ExecutorService.html), [`Future`](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/concurrent/Future.html).
- [Java Language Specification §17 — Threads and Locks](https://docs.oracle.com/javase/specs/jls/se17/html/jls-17.html).

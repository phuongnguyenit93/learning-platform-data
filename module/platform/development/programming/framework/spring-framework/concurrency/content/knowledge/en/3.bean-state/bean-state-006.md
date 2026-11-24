# Choosing `synchronized`, `Lock`, or Atomics by Invariant Scope

**Module:** Spring Framework - concurrency  
**Group:** Bean state  
**Objective:** When a Spring bean is accessed by multiple threads, accurately identify the **invariants to protect**, which operations must occur as a unit, and how wide the synchronization boundary must be; then choose `synchronized`, `Lock`, or `Atomic*` classes to fit the context.

## 1. Start from the Invariant, Not from the Tool Name

An **invariant** is a condition that must always hold on shared state at valid observation points. For example:

- An independently incremented counter: each call to `increment()` increases by exactly one unit, with no lost updates.
- Available stock for booking cannot go negative: `available >= 0`. One booking action **checks sufficient stock and deducts stock**.
- Two fields together describe one inventory: `available >= 0`, `reserved >= 0`, `available + reserved == initialTotal`. A single booking must update both `available` and `reserved` in **the same logical state transition**.
- Two accounts in the same ledger: total balance remains unchanged during a transfer; the transfer must protect both accounts together. If data lives in a database or across multiple services, an in-JVM lock is not enough.

The question is not "is this variable locked yet?" but:

1. **Where is the shared state?** Singleton bean field, cache object, collection, DB record, or multiple resources?
2. **Which conditions must hold?** Write down preconditions and postconditions explicitly.
3. **Which steps form a business operation?** Must they be kept atomic together?
4. **Who can read/write?** Multiple HTTP requests, `@Async`, `@Scheduled`, callbacks, multiple application instances?
5. **Where is the observation boundary?** One value, one group of fields, multiple objects, one DB row, or multiple systems?
6. **What is needed beyond data protection?** Non-blocking lock attempts, timeouts, cancellation on interrupt, condition waiting, latency measurement?

Only from there do you choose the mechanism.

### Race Condition Example

Suppose a bean holds `available = 1`. The following implementation is **unsafe** when two threads call concurrently:

```java
private int available = 1;
private int reserved = 0;

public boolean reserveOne() {
    if (available == 0) {
        return false;
    }
    available--;
    reserved++;
    return true;
}
```

Both threads can observe `available > 0`, both pass the check branch, and both report booking success. Both `available--` and `reserved++` are read–compute–write operations; neither is an atomic transaction on its own. Overselling, lost updates, or mid-update snapshots can occur. Marking both fields `volatile` **does not** turn three check/update steps into one atomic action.

## 2. Why Does State in a Spring Bean Require Attention?

`@Component`, `@Service`, and `@Repository` default to **singleton scope**: one bean instance per bean definition within a Spring IoC container. Multiple request threads or workers can call the same instance. Singleton only describes **instance count and lifecycle**, and does not automatically guarantee thread-safety.

```java
@Service
public class VisitService {
    private int visits;

    public int registerVisit() {
        return ++visits;  // race condition when multiple threads call concurrently
    }
}
```

This is an **illustrative snippet inside a Spring application** (requires `import org.springframework.stereotype.Service;`). Multiple calls can read the same old value and overwrite each other's results.

A **stateless** service is usually easy to share: per-request data stays in local variables, while dependencies are objects used according to their thread-safety contracts. "No mutable fields" is a good starting point, yet insufficient if the service still mutates a mutable object shared by a dependency.

Other scopes do not cure all races either:

- `prototype` creates an instance per bean request, yet if a prototype is directly injected once into a singleton, the singleton keeps that same instance.
- `request` creates per-request state, yet a request can dispatch work to another thread; context passing and lifecycle must be handled explicitly.
- `session` can still be accessed concurrently by multiple requests in **the same session**.
- Each application replica has **its own** singleton beans; `synchronized` cannot lock another replica.

Therefore, determine whether state lives within **one JVM** or is business data **shared across multiple JVMs and a DB** before picking a lock.

## 3. Distinguishing Atomicity, Visibility, and Ordering

Three related yet distinct properties:

| Property | Question | Example |
| --- | --- | --- |
| **Atomicity** | Can another thread interleave between logical steps of the operation? | `if (stock > 0) stock--` must be one business step |
| **Visibility** | Does another thread see the written value or still see a stale copy? | A stop flag observed by a worker |
| **Ordering / happens-before** | Is a write properly published in order before a related read? | State updated under a lock and then read under that same lock |

In the Java Memory Model:

- Exiting `synchronized` on **the same monitor** happens-before a subsequent entry into that monitor; operations under the same monitor are mutually exclusive.
- Standard `Lock`s (such as `ReentrantLock`) provide corresponding memory effects when calling `unlock()` followed by `lock()` on the same lock.
- `AtomicInteger`, `AtomicLong`, and `AtomicReference` provide atomic operations and memory semantics defined by the API documentation; `compareAndSet` has effects equivalent to appropriate volatile accesses.
- `volatile` suits publishing/reading **a single value** or flag without compound operations; `volatile int count; count++;` still loses updates.
- `final` aids designing immutable objects and safe publication when properly constructed, yet does not make an internal mutable object immutable.

**Principle:** every **read and write** path touching the same invariant must follow **the same synchronization protocol**. Locking only writer methods while letting getters read multiple fields raw yields inconsistent snapshots.

## 4. Quick Decision Table by Invariant Boundary

| Invariant and requirement | Typical choice | Why | Common mistake |
| --- | --- | --- | --- |
| One independent counter (increment/decrement/get) | `AtomicInteger`/`AtomicLong` | One atomic update operation; no monitor needed | Splitting `get()` and `incrementAndGet()` and thinking it is atomic |
| One conditional number, e.g., non-negative quota | `AtomicInteger` + CAS loop | Condition and subtraction execute as **one** update of **one value** | `if (get() > 0) decrementAndGet()` is unsafe |
| Several fields that must change together | `synchronized` on a shared monitor | Readable, hard to forget unlocking; protects both invariant and snapshots | Locking fields separately, or un-synchronized getters |
| Several fields, needing `tryLock`, timeout, interrupt handling, `Condition` | `ReentrantLock` | Controls lock waiting/acquisition while protecting the critical section | Forgetting `unlock()` in `finally`; using a different lock for readers/writers |
| Multiple fields representable as **one immutable snapshot** | `AtomicReference<State>` + CAS | Replaces the logical state atomically in one operation | Mutable objects inside state; side effects in CAS loop |
| Many readers, few writers, and measured contention | Consider `ReentrantReadWriteLock` | Readers run concurrently when no writer is active | Multiple lock modes add complexity; performance is not automatically better |
| Multiple JVMs/replicas or DB data must stay consistent | DB constraints, transactions + conditional updates/locking/optimistic versioning | Invariant scope exceeds one JVM | Mistaking a bean's `synchronized` for a system-wide lock |

**Priority rule:** If you need ordinary locking within one JVM, start with `synchronized`. Choose `ReentrantLock` when you genuinely need its extra capabilities. Use atomics when the entire update can be accurately expressed as **one atomic state**; atomics are not automatically better than locks for every invariant.

## 5. `AtomicInteger`: One Variable, Optionally Conditional

For independent statistics:

```java
private final java.util.concurrent.atomic.AtomicLong totalRequests =
        new java.util.concurrent.atomic.AtomicLong();

public long onRequest() {
    return totalRequests.incrementAndGet();
}
```

Each call performs one atomic increment. However, if the requirement is "decrement only while positive," the following code is still wrong:

```java
if (stock.get() > 0) {
    stock.decrementAndGet(); // checking and decrementing are TWO operations
}
```

Two threads can both read `1` and both decrement, leaving `stock = -1`. Fix with **compare-and-set (CAS)**:

```java
public boolean takeOne() {
    for (;;) {
        int current = stock.get();
        if (current == 0) {
            return false;
        }
        if (stock.compareAndSet(current, current - 1)) {
            return true;
        }
        // Another thread updated first: re-read and try again.
    }
}
```

`compareAndSet(expected, update)` writes only if the current value still equals `expected`. If contention causes CAS to fail, the loop re-reads; thus two subtractions cannot both succeed on the same unit of stock. For quotas that could become negative due to bad data, check `current <= 0`, not just `== 0`, and validate initial data.

**Limitation of atomics:** updating an `AtomicInteger` does not concurrently protect `reserved`, a `Map`, a DB transaction, or sending an email. When an invariant spans multiple fields, use a shared lock or bundle the fields into **one immutable state value**.

`updateAndGet`/`getAndUpdate` may re-invoke the update function under CAS contention. The function supplied to them must **have no side effects** (no business audit logging, emails, charges, HTTP calls) since it can run multiple times. `LongAdder` suits write-heavy statistical counters, yet `sum()` is not an atomic snapshot against concurrent updates; avoid it when exact quota checks are needed.

## 6. `synchronized`: Protecting Multiple Fields with **One** Monitor

When `available` and `reserved` must satisfy `available + reserved == total`, enclose the entire operation in the same critical section:

```java
private final Object mutex = new Object();
private int available = 10;
private int reserved;

public boolean reserveOne() {
    synchronized (mutex) {
        if (available == 0) {
            return false;
        }
        available--;
        reserved++;
        return true;
    }
}

public StockSnapshot snapshot() {
    synchronized (mutex) {
        return new StockSnapshot(available, reserved);
    }
}

public record StockSnapshot(int available, int reserved) {}
```

This is a member snippet illustrating a class/bean; the `record` also belongs to that class. When both numbers start at `10` and `0`, after every successful `reserveOne()`, the sum is always `10`. The getter must synchronize on **the same** `mutex` to obtain a consistent snapshot. `StockSnapshot` is immutable so it can be safely returned outside the lock.

**Characteristics to remember:**

- `synchronized (mutex)` uses the monitor of **the `mutex` object itself**; each monitor is an independent exclusion zone. Two distinct `new Object()` instances **do not** coordinate with each other.
- Upon exiting the block, even via an exception, the JVM automatically releases the monitor. This is why `synchronized` is often the easiest option to maintain.
- `synchronized` is reentrant: a thread already holding a monitor can re-enter it; it has no direct API for `tryLock(timeout)` or interruptible waiting.
- `synchronized` on `this` or `synchronized` methods are valid in the language, yet `private final Object mutex` prevents external code from accidentally using the same monitor. Never lock on String literals, boxed integers, or shared objects you do not own.
- Keep locked sections short: compute/transition in-memory state; avoid holding locks while waiting on networks, databases, sleeps, or uncontrolled callbacks. Overly wide locks increase latency and deadlock risk.
- If protecting two objects with two different locks, enforce a uniform lock acquisition order to prevent thread A holding lock 1 waiting for lock 2 while thread B holds lock 2 waiting for lock 1.

There is no need to add `volatile` to `available`/`reserved` if **all** related accesses happen under the same monitor; the locking protocol supplies both the required visibility and atomicity.

## 7. `ReentrantLock`: Same Problem, Additional Waiting Control

`java.util.concurrent.locks.Lock` is an interface; `ReentrantLock` is its common implementation. For multiple fields sharing an invariant, protection resembles `synchronized`, except lock lifecycle must be managed explicitly:

```java
private final java.util.concurrent.locks.ReentrantLock lock =
        new java.util.concurrent.locks.ReentrantLock();

private int available = 10;
private int reserved;

public boolean reserveOne() {
    lock.lock();
    try {
        if (available == 0) {
            return false;
        }
        available--;
        reserved++;
        return true;
    } finally {
        lock.unlock();
    }
}
```

This is an illustrative Java member snippet, not a standalone program. **Always** call `unlock()` inside `finally` after confirming the lock was acquired; if an error occurs mid-way and unlocking is skipped, other requests can hang.

`Lock` is worth choosing when you need:

- `tryLock()`: can return immediately when the system is busy instead of blocking.
- `tryLock(timeout, unit)`: waits up to a bounded duration and supports interruption while waiting.
- `lockInterruptibly()`: allows cancellation while the thread waits to acquire the lock.
- `Condition`: multiple condition wait queues attached to the same `Lock`, using `await()`/`signal()` under the lock protocol. `await()` releases the lock while waiting and reacquires it before continuing.

Dedicated example for a "do not wait long" policy:

```java
public boolean reserveWithTimeout(
        int quantity, long timeoutMillis) throws InterruptedException {
    if (quantity <= 0) {
        throw new IllegalArgumentException("quantity must be positive");
    }
    if (!lock.tryLock(timeoutMillis, java.util.concurrent.TimeUnit.MILLISECONDS)) {
        return false; // Timed out waiting for the lock.
    }
    try {
        if (available < quantity) {
            return false; // Insufficient stock.
        }
        available -= quantity;
        reserved += quantity;
        return true;
    } finally {
        lock.unlock();
    }
}
```

The example above **assumes** the `lock`, `available`, and `reserved` fields from the previous snippet; it is not a standalone class. In a real API, distinguish "lock wait timeout" from "insufficient stock" using an enum/result type or coded error, rather than collapsing both into `false`.

`new ReentrantLock(true)` requests a fairness policy under contention, yet can lower throughput and does not mean every lock acquisition follows strict order (especially the untimed `tryLock()`). **Do not** choose `ReentrantLock` just assuming it is always faster than `synchronized`; measure workload behavior and choose based on required semantics.

## 8. `AtomicReference` When Multiple Fields Form an Immutable State

An invariant spanning multiple fields does not require a monitor if you can **bundle all fields into one immutable object** and swap the entire state via CAS:

```java
import java.util.concurrent.atomic.AtomicReference;

record StockState(int available, int reserved) {}

final class StockCas {
    private final AtomicReference<StockState> current =
            new AtomicReference<>(new StockState(10, 0));

    boolean reserve(int quantity) {
        if (quantity <= 0) {
            throw new IllegalArgumentException("quantity must be positive");
        }
        for (;;) {
            StockState before = current.get();
            if (before.available() < quantity) {
                return false;
            }
            StockState after = new StockState(
                    before.available() - quantity,
                    before.reserved() + quantity);
            if (current.compareAndSet(before, after)) {
                return true;
            }
        }
    }

    StockState snapshot() {
        return current.get();
    }
}
```

This is a syntactically standalone Java 17+ example containing package-private top-level `StockState` and `StockCas`; to run it, add a class with `main` or place it in a test. `StockState` is a `record` holding only two integers so it is immutable. A single CAS swaps both `available`/`reserved`, preserving the total and providing consistent snapshots.

**Trade-offs:** under high contention, CAS may retry and allocate many snapshots; measure before optimizing. The CAS loop must contain no side effects because it can repeat. `AtomicReference` only makes operations on **the reference** atomic; if the reference points to a `List` or mutable object and you mutate it in place, you still have a race.

## 9. Runnable Java 17 Program: Same Load, Three Protection Approaches

This complete example intentionally runs 100 "take one unit" attempts on an 8-thread pool, while each inventory holds only 10 units. It shows deterministic final outcomes despite non-deterministic thread scheduling. `AtomicQuota` protects **one** quantity; `MonitorLedger` and `LockLedger` protect **the pair** `available`/`reserved`.

Save **verbatim** to `ConcurrencyChoiceDemo.java`:

```java
import java.util.ArrayList;
import java.util.List;
import java.util.concurrent.CountDownLatch;
import java.util.concurrent.ExecutorService;
import java.util.concurrent.Executors;
import java.util.concurrent.Future;
import java.util.concurrent.TimeUnit;
import java.util.concurrent.atomic.AtomicInteger;
import java.util.concurrent.locks.ReentrantLock;
import java.util.function.BooleanSupplier;

public class ConcurrencyChoiceDemo {

    record Snapshot(int available, int reserved) {}

    static final class AtomicQuota {
        private final AtomicInteger available;

        AtomicQuota(int initial) {
            if (initial < 0) {
                throw new IllegalArgumentException("initial < 0");
            }
            available = new AtomicInteger(initial);
        }

        boolean takeOne() {
            for (;;) {
                int before = available.get();
                if (before <= 0) {
                    return false;
                }
                if (available.compareAndSet(before, before - 1)) {
                    return true;
                }
            }
        }

        int remaining() {
            return available.get();
        }
    }

    static final class MonitorLedger {
        private final Object mutex = new Object();
        private int available;
        private int reserved;

        MonitorLedger(int initial) {
            if (initial < 0) {
                throw new IllegalArgumentException("initial < 0");
            }
            available = initial;
        }

        boolean reserveOne() {
            synchronized (mutex) {
                if (available == 0) {
                    return false;
                }
                available--;
                reserved++;
                return true;
            }
        }

        Snapshot snapshot() {
            synchronized (mutex) {
                return new Snapshot(available, reserved);
            }
        }
    }

    static final class LockLedger {
        private final ReentrantLock lock = new ReentrantLock();
        private int available;
        private int reserved;

        LockLedger(int initial) {
            if (initial < 0) {
                throw new IllegalArgumentException("initial < 0");
            }
            available = initial;
        }

        boolean reserveOne() {
            lock.lock();
            try {
                if (available == 0) {
                    return false;
                }
                available--;
                reserved++;
                return true;
            } finally {
                lock.unlock();
            }
        }

        Snapshot snapshot() {
            lock.lock();
            try {
                return new Snapshot(available, reserved);
            } finally {
                lock.unlock();
            }
        }
    }

    static int compete(int attempts, BooleanSupplier operation) throws Exception {
        ExecutorService pool = Executors.newFixedThreadPool(8);
        CountDownLatch start = new CountDownLatch(1);
        List<Future<Boolean>> results = new ArrayList<>();

        try {
            for (int i = 0; i < attempts; i++) {
                results.add(pool.submit(() -> {
                    start.await();
                    return operation.getAsBoolean();
                }));
            }

            start.countDown();
            int accepted = 0;
            for (Future<Boolean> result : results) {
                if (result.get()) {
                    accepted++;
                }
            }
            return accepted;
        } finally {
            start.countDown(); // Avoid leaving waiting tasks stuck if an error occurs.
            pool.shutdown();
            if (!pool.awaitTermination(10, TimeUnit.SECONDS)) {
                pool.shutdownNow();
            }
        }
    }

    public static void main(String[] args) throws Exception {
        AtomicQuota atomic = new AtomicQuota(10);
        int atomicAccepted = compete(100, atomic::takeOne);
        System.out.printf(
                "atomic: accepted=%d remaining=%d%n",
                atomicAccepted, atomic.remaining());

        MonitorLedger monitor = new MonitorLedger(10);
        int monitorAccepted = compete(100, monitor::reserveOne);
        Snapshot monitorState = monitor.snapshot();
        System.out.printf(
                "synchronized: accepted=%d available=%d reserved=%d%n",
                monitorAccepted, monitorState.available(), monitorState.reserved());

        LockLedger locking = new LockLedger(10);
        int lockAccepted = compete(100, locking::reserveOne);
        Snapshot lockState = locking.snapshot();
        System.out.printf(
                "lock: accepted=%d available=%d reserved=%d%n",
                lockAccepted, lockState.available(), lockState.reserved());
    }
}
```

Run with JDK 17 or later:

```bash
javac ConcurrencyChoiceDemo.java
java ConcurrencyChoiceDemo
```

**Exact stdout when the program completes normally:**

```text
atomic: accepted=10 remaining=0
synchronized: accepted=10 available=0 reserved=10
lock: accepted=10 available=0 reserved=10
```

Since each option has 10 units and does not replenish, **exactly 10** out of 100 attempts succeed. The scheduling of the 8 workers and which requests win are non-deterministic, yet the success count and final state are deterministic. `CountDownLatch` merely helps many tasks start competing together; CAS/monitor/lock itself protects the invariant. `Future.get()` is used in this **test** program to await all tasks before printing, not as a pattern to drop into a real API's request thread.

Lessons from the program:

- `AtomicQuota` only needs to protect **one value**, `available`.
- `MonitorLedger` updates both fields under one monitor, and `snapshot()` reads them under the same monitor.
- `LockLedger` achieves the same correctness with an explicit lock; its extra benefits appear when you need `tryLock`/timeout/interrupt/condition, not because this example necessarily runs faster.

## 10. Putting the Decision Inside a Singleton `@Service`

Here is the Spring version of the two-field problem using a private monitor. Place in `src/main/java/com/example/inventory/InventoryService.java` of a Spring Boot application with Spring Context dependencies (such as `spring-boot-starter-web`):

```java
package com.example.inventory;

import org.springframework.stereotype.Service;

@Service
public class InventoryService {
    private final Object mutex = new Object();
    private int available = 10;
    private int reserved;

    public boolean reserve(int quantity) {
        if (quantity <= 0) {
            throw new IllegalArgumentException("quantity must be positive");
        }

        synchronized (mutex) {
            if (available < quantity) {
                return false;
            }
            available -= quantity;
            reserved += quantity;
            return true;
        }
    }

    public Snapshot snapshot() {
        synchronized (mutex) {
            return new Snapshot(available, reserved);
        }
    }

    public record Snapshot(int available, int reserved) {}
}
```

This is a **complete class file for a Spring project**, not a program with `main` runnable directly via `javac` without a classpath. With one bean instance in one JVM, all request threads passing through this bean and accessing state only through these two methods can never make `available` negative or produce a snapshot summing to anything other than 10.

A controller can call `reserve(quantity)` and return an error code when stock is insufficient; the controller does not need to lock on its own because the service enforces the business boundary. If another method directly mutates `available`/`reserved`, uses a different lock, or the bean has multiple instances not sharing the same object, that guarantee breaks.

A **better option if in-memory state is not needed** is designing the singleton service without holding stock counts in fields, delegating the invariant to a repository/DB. A stateless singleton with proper transactions/SQL is usually much easier to operate across multiple replicas.

### A Few Easily Confused Spring Cases

- `@Async`, `@Scheduled`, and request handlers can hit the singleton concurrently; threads created by Spring do not automatically synchronize bean state.
- `@Transactional` manages database transactions via the transaction manager; it **does not** make `++` on a Java field atomic, nor does it create a JVM mutex for the bean.
- `@Transactional` on a DB-updating method does not automatically resolve all check-then-write races; you need isolation/locking/versioning/SQL suited to the invariant.
- If a method performs I/O while holding `synchronized`/`Lock`, many other requests may wait a long time; consider splitting it or moving the invariant to where the data actually lives.

## 11. Boundaries of In-JVM Locks: Databases and Multiple Instances

Suppose you run **three Spring Boot replicas**, each with its own `InventoryService`. `synchronized (mutex)` in replica A **knows nothing** about locks in B/C. If all three read stock from the DB and decrement it, a local monitor cannot prevent overselling.

For **an inventory row in the DB**, you can use a conditional update and inspect the affected row count (illustrative SQL syntax; adapt to your actual dialect/schema):

```sql
UPDATE inventory
SET available = available - :quantity,
    reserved = reserved + :quantity
WHERE id = :id
  AND available >= :quantity;
```

If `quantity > 0` has been validated and exactly **one** row is updated, the DB transaction has transitioned that record's state conditionally. If **0** rows, either stock is insufficient or the record was not found; the API must distinguish these per business rules. Add DB constraints, transactions, isolation, or optimistic locking (`@Version`) depending on schema and contention; handle version conflicts or deadlocks properly when they occur.

If an invariant spans **multiple tables, multiple rows, or multiple services**, choose appropriate transaction boundaries, DB lock ordering, cross-service synchronization mechanisms, or compensating workflows. Distributed invariants cannot be solved solely with `AtomicInteger`, `ReentrantLock`, or an annotation on a bean.

## 12. Signs of a Wrong Choice and How to Test

| Mistake | Why it is dangerous | How to fix |
| --- | --- | --- |
| `volatile int count; count++` | Visibility does not imply atomic increment | `AtomicInteger.incrementAndGet()` or a lock |
| `if (atomic.get() > 0) atomic.decrementAndGet()` | Check and decrement are two actions that can interleave | CAS loop or pure `updateAndGet` |
| Two separate `AtomicInteger`s for `available` and `reserved` | Each field is atomic yet the sum can be mis-observed and transitions split | One shared monitor/lock or `AtomicReference` holding one immutable state |
| Writing inside `synchronized`, reading in an un-synchronized getter | Getter can observe an inconsistent combination of fields | Same monitor for every read/write path of the invariant |
| `Lock.lock()` then only `unlock()` at the end of the normal path | Exceptions leak the lock, hanging subsequent threads | `try/finally` |
| Locking on `this`, string literals, or objects owned by others | External code can unexpectedly contend on the same monitor | `private final Object mutex` |
| CAS loop calling HTTP, sending email, or writing DB | CAS can retry and cause duplicate side effects | Only pure state computation in CAS loop; side effects have separate contracts |
| Each bean/replica has its own lock for shared data | No mutual exclusion across the whole data source | Move invariant to a single owner/DB |
| Adding `@Transactional` to fix a Java field race | DB transactions do not lock objects on the heap | Choose the proper JVM primitive, or move state to the DB |
| Lock enclosing a long network request | Increases contention, timeouts, and deadlock risk | Shrink critical section; avoid I/O while holding locks |

### Pre-Production Checklist

1. **Write down the invariants:** e.g., `available >= 0` and `available + reserved = initialTotal`.
2. **List all readers/writers:** requests, background jobs, schedulers, listeners, test helpers; no backdoor bypassing the lock.
3. **Pick the right owner:** one value → atomic/CAS; a group of fields in one JVM → monitor/lock; multiple replicas → shared data source and proper transactions.
4. **Check observation points:** getters need a synchronized snapshot, or must read an atomically published immutable state.
5. **Handle errors:** validate positive quantities, counter overflow, rejecting on insufficient resources, interrupts while waiting for locks, CAS retries under contention.
6. **Measure:** throughput, tail latency, lock wait times, CAS retry counts; do not optimize by intuition.
7. **Concurrent testing:** launch multiple threads via `CountDownLatch`/`CyclicBarrier`, await every `Future`, assert final invariants, repeat many runs. Tests catch races, yet do not replace proving every access path obeys the locking protocol.

For critical data, also test across **restarts, multiple instances, and failed DB transactions**. Unit tests inside a single JVM do not prove distributed correctness.

## 13. Self-Check

1. A singleton only stores `AtomicLong requestCount`. Is `synchronized` needed around `incrementAndGet()`?  
   **Answer:** No, if the invariant is solely each increment of that single variable.
2. Why are two `AtomicInteger available/reserved` insufficient to protect `available + reserved == total` when a getter reads both?  
   **Answer:** There is no single atomic state-transition point across the **pair** of values; a getter can interleave between the two updates.
3. You need to try acquiring a lock for at most 50 ms and cancel on interrupt. What do you choose?  
   **Answer:** `ReentrantLock.tryLock(50, TimeUnit.MILLISECONDS)` and `unlock()` in `finally` after acquiring the lock.
4. Why can a singleton `@Service` hit races?  
   **Answer:** Multiple requests/workers share one instance; scope does not provide a mutex.
5. Two replicas concurrently update one DB inventory row. Is `synchronized` on each replica enough?  
   **Answer:** No. The invariant boundary lies at the shared data source; concurrency-safe DB operations are required.
6. When does `AtomicReference<StockState>` make more sense than two independent atomics?  
   **Answer:** When both fields belong to one immutable snapshot and the whole state can transition via a single pure CAS, accepting retry overhead.

## 14. Key Takeaways and Resources

**Choose the tool based on the scope of the invariant to protect:**

- **One independent value:** atomic; if updates are conditional, use CAS properly.
- **A group of fields that must stay consistent in one JVM:** `synchronized` is the simple default; `ReentrantLock` when needing timeouts, interrupts, try-lock, or `Condition`.
- **A group of fields replaceable by one immutable snapshot:** consider `AtomicReference<State>` with CAS.
- **Multi-JVM/DB data:** use consistency mechanisms where the data lives; a singleton's lock does not span processes.

Official references:

- [Spring Framework — Bean Scopes](https://docs.spring.io/spring-framework/reference/core/beans/factory-scopes.html): singleton, prototype, and web scopes.
- [Oracle Java 17 — Intrinsic Locks and Synchronization](https://docs.oracle.com/javase/tutorial/essential/concurrency/locksync.html): monitors, locks, and visibility.
- [Java SE 17 — `AtomicInteger`](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/concurrent/atomic/AtomicInteger.html): `compareAndSet`, `getAndUpdate`, atomic semantics.
- [Java SE 17 — `Lock`](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/concurrent/locks/Lock.html): `lock`, `tryLock`, `lockInterruptibly`, `unlock`.
- [Java SE 17 — `ReentrantLock`](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/concurrent/locks/ReentrantLock.html): lock control and fairness.
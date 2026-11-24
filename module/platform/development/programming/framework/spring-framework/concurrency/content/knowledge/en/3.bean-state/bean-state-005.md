# Check-Then-Act and Multi-Step Operations That Must Be Protected

## 1. The Problem: A Business Decision Often Has Multiple Steps

In a Spring application, a `@Service` bean typically has `singleton` scope: multiple HTTP requests, callbacks, `@Async` tasks, or jobs can use **the same object**. If the bean holds mutable state, threads can read and write that state concurrently.

For example, suppose a business rule allows only one remaining registration slot:

```java
// WRONG when multiple threads call concurrently and share the available variable
if (available > 0) {
    available--;
    return true;
}
return false;
```

This snippet involves at least two actions: **checking** the condition and then **updating** the data. They do not become one atomic operation simply by sitting next to each other in source code. Two threads can both observe `available == 1`, both conclude "a slot is available," and both succeed: the system sells two slots when only one existed.

This is a **check-then-act** bug, a form of **TOCTOU** (*time of check to time of use*). The core issue is not which thread is faster; it is that the data can change **between the time of check and the time of act**.

Common variants in practice:

- **Check-then-act:** "If in stock, decrement inventory"; "If the record does not exist yet, create it"; "If this request has not been processed yet, process it."
- **Read-modify-write:** `counter++`, `balance = balance - amount`, `visits.put(key, visits.get(key) + 1)`.
- **Compound action:** transferring funds must debit one account and credit another; booking a ticket must decrement `available`, increment `reserved`, and create a ticket record; updating configuration must change multiple fields into a single valid state.
- **Check-then-use on external resources:** checking whether a file exists then opening it, checking permissions then performing an action, checking the DB has no row then inserting. Steps spanning different systems usually cannot be protected by a single Java lock alone.

**Learning goal:** identify the atomic boundary of a business rule, choose one consistent protection mechanism, understand the scope each mechanism covers, and verify correctness under concurrent requests.

## 2. Seeing Race Conditions via Interleaving Schedules

Initially `available = 1`. Two requests A and B run on two threads:

| Step | Thread A | Thread B | Outcome |
| --- | --- | --- | --- |
| T1 | Reads `available == 1` | | A sees a slot available |
| T2 | | Reads `available == 1` | B also sees a slot available |
| T3 | Updates, returns success | | A is granted a slot |
| T4 | | Updates, returns success | B is also granted a slot |

Even if the decrement statements use individual atomic operations, **the check and the decrement can still be interleaved**. With `AtomicInteger`, the following pattern is **still wrong**:

```java
private final AtomicInteger available = new AtomicInteger(1);

public boolean reserveWrong() {
    if (available.get() <= 0) {
        return false;
    }
    available.getAndDecrement(); // The decrement itself is atomic, the overall flow is not.
    return true;
}
```

When A and B both pass `get()` before either decrements, both can call `getAndDecrement()`. The result can be `available == -1` while both requests are confirmed successful.

Three properties must be distinguished:

1. **Atomicity:** the steps involved in a business rule are observed as a single decision uninterrupted by competing operations.
2. **Visibility:** whether one thread sees another thread's updates under the rules of the Java Memory Model.
3. **Consistency/invariant:** conditions that must always hold, such as `available >= 0` and `available + reserved == capacity`.

`volatile` helps with visibility and certain ordering rules, yet **does not make** a "read → check → write" sequence atomic, nor does it make `counter++` atomic. `AtomicInteger` protects individual operations and provides CAS; you need a **CAS loop** or a lock spanning the entire decision to solve check-then-act.

## 3. Identifying the Boundary That Must Be Protected

A sound solution starts from the **invariants**, not from an annotation name.

Suppose total initial capacity is 5; the bean stores two fields `available` and `reserved`. The invariants to preserve are:

```text
available >= 0
reserved >= 0
available + reserved == 5
```

A reservation must perform the **entire** sequence "check slot availability → decrement available → increment reserved" inside the same protection boundary. Synchronizing only the decrement leaves the check racing. Synchronizing updates while allowing another thread to read the two fields piecemeal lets readers observe an inconsistent snapshot.

Questions to answer:

- **What state is shared?** Singleton bean fields, caches, static fields, maps, database rows, or other system resources?
- **Who can access it?** Request threads, executor workers, scheduled tasks, listeners, other beans, or multiple application instances?
- **Which invariants must hold?** Non-negative, no double allocation, conserved totals, cannot transition back from a terminal state to an initial state, etc.
- **What is the unit of atomicity?** One variable, one map key, multiple fields of an object, multiple DB rows, or multiple external systems?
- **Where is the protection scope?** Within one object/JVM, one DB transaction, or a distributed system?

Calling one piece of code "thread-safe" is not enough to conclude **the entire workflow** is thread-safe. For instance, `ConcurrentHashMap` is safe per guaranteed operation, yet `containsKey(key)` followed by `put(key, value)` is two separate operations and still has a race window.

## 4. Standalone Java 17 Example: Reproducing the Bug and Fixing It

The following example **deliberately** uses `CountDownLatch` so two workers pass the check step together before performing the decrement step. That makes the failure deterministically reproducible rather than relying on scheduler luck. Then it compares two fixes: CAS for a single variable and a lock for a multi-field invariant.

Create the file **`CheckThenActDemo.java`**:

```java
import java.util.concurrent.CountDownLatch;
import java.util.concurrent.ExecutorService;
import java.util.concurrent.Executors;
import java.util.concurrent.Future;
import java.util.concurrent.atomic.AtomicInteger;

public final class CheckThenActDemo {
    private static final class BrokenInventory {
        private final AtomicInteger remaining = new AtomicInteger(1);

        boolean reserve(CountDownLatch bothChecked, CountDownLatch proceed)
                throws InterruptedException {
            if (remaining.get() <= 0) {
                return false;
            }

            // Demo: force both threads past the check before either can decrement.
            bothChecked.countDown();
            proceed.await();

            remaining.getAndDecrement();
            return true;
        }

        int remaining() {
            return remaining.get();
        }
    }

    private static final class CasInventory {
        private final AtomicInteger remaining = new AtomicInteger(1);

        boolean reserve() {
            while (true) {
                int observed = remaining.get();
                if (observed <= 0) {
                    return false;
                }
                if (remaining.compareAndSet(observed, observed - 1)) {
                    return true;
                }
                // Another thread changed the value: re-read and try again.
            }
        }

        int remaining() {
            return remaining.get();
        }
    }

    private static final class ProtectedLedger {
        private final Object lock = new Object();
        private int available = 1;
        private int reserved = 0;

        boolean reserve() {
            synchronized (lock) {
                if (available <= 0) {
                    return false;
                }
                available--;
                reserved++;
                return true;
            }
        }

        Snapshot snapshot() {
            synchronized (lock) {
                return new Snapshot(available, reserved);
            }
        }
    }

    private record Snapshot(int available, int reserved) {}

    private static int accepted(Future<Boolean> first, Future<Boolean> second)
            throws Exception {
        return (first.get() ? 1 : 0) + (second.get() ? 1 : 0);
    }

    public static void main(String[] args) throws Exception {
        ExecutorService pool = Executors.newFixedThreadPool(2);
        try {
            BrokenInventory broken = new BrokenInventory();
            CountDownLatch checked = new CountDownLatch(2);
            CountDownLatch proceed = new CountDownLatch(1);

            Future<Boolean> b1 = pool.submit(() -> broken.reserve(checked, proceed));
            Future<Boolean> b2 = pool.submit(() -> broken.reserve(checked, proceed));
            checked.await();
            proceed.countDown();

            int brokenAccepted = accepted(b1, b2);
            System.out.println("Broken accepted: " + brokenAccepted);
            System.out.println("Broken remaining: " + broken.remaining());

            CasInventory cas = new CasInventory();
            int casAccepted = accepted(pool.submit(cas::reserve),
                                       pool.submit(cas::reserve));
            System.out.println("CAS accepted: " + casAccepted);
            System.out.println("CAS remaining: " + cas.remaining());

            ProtectedLedger ledger = new ProtectedLedger();
            int lockAccepted = accepted(pool.submit(ledger::reserve),
                                        pool.submit(ledger::reserve));
            Snapshot current = ledger.snapshot();
            System.out.println("Lock accepted: " + lockAccepted);
            System.out.println("Lock available: " + current.available());
            System.out.println("Lock reserved: " + current.reserved());
        } finally {
            pool.shutdown();
        }
    }
}
```

In the directory containing the file, using **JDK 17+**:

```bash
javac CheckThenActDemo.java
java CheckThenActDemo
```

Stdout result:

```text
Broken accepted: 2
Broken remaining: -1
CAS accepted: 1
CAS remaining: 0
Lock accepted: 1
Lock available: 0
Lock reserved: 1
```

**Explanation of results:**

- **Broken:** both threads checked the positive value before `proceed` opened. Both `getAndDecrement()` calls are atomic, yet the allocation decision is not atomic, so both requests were accepted and remaining inventory became -1.
- **CAS:** when 1 slot remained, only one thread could change it to 0 via `compareAndSet(1, 0)`. The other thread's CAS fails, re-reads 0, and returns `false`. No overselling occurs.
- **Lock:** both the check and the two updates `available--`, `reserved++` sit inside the same monitor. `snapshot()` also acquires that monitor so it never sees a half-completed update. The sum `available + reserved` is always 1 at protected observation points.

Note: `CountDownLatch` in the Broken branch only serves to intentionally reproduce the race; it is **not** a business protection mechanism. The example does not claim a given execution schedule will always fail in code without latches. When evaluating a real system, you must prove the invariant holds under all possible interleavings.

## 5. Choosing the Right Tool for the Atomic Boundary

### 5.1. `synchronized` or `ReentrantLock` When Protecting a Group of State

The straightforward approach for a multi-field invariant inside one JVM is sharing a single lock:

```java
private final Object stateLock = new Object();
private int available = 5;
private int reserved = 0;

public boolean tryReserve() {
    synchronized (stateLock) {
        if (available <= 0) {
            return false;
        }
        available--;
        reserved++;
        return true;
    }
}
```

This is a snippet inside a class with the declared fields, not a standalone program. Every method reading/modifying **fields sharing the invariant** must obey the same lock. A lock is only effective among threads accessing **the exact same lock object**. Avoid using interned strings, Class objects, or publicly exposed objects as monitors if unrelated code might lock on them unexpectedly. Using `private final Object` expresses clear ownership.

`synchronized` provides both mutual exclusion and a happens-before relationship when one thread releases the monitor and another subsequently acquires the same monitor. A consistent snapshot must read all related fields while holding the same lock.

`ReentrantLock` is useful when you need `tryLock()`, timeouts, interruptibility while waiting for the lock, or dedicated conditions. Always unlock in `finally`:

```java
lock.lock();
try {
    // Check and update the fields sharing the invariant.
} finally {
    lock.unlock();
}
```

This is an illustrative snippet with `lock` being a `ReentrantLock` initialized on the class. Never acquire multiple locks in arbitrary order. For example, transferring A→B locking A then B while B→A locks B then A can cause a **deadlock**. You need a consistent lock ordering by ID or another suitable data-layer mechanism.

Do not hold locks across HTTP calls, network access, `Thread.sleep`, uncontrolled callbacks, or long processing whenever avoidable. Those operations block other requests and invite deadlocks. Yet you must also never release the lock between "check" and "update" if the invariant depends on both steps: design data and transaction boundaries to shrink the critical section **while keeping it atomic**.

### 5.2. `AtomicInteger` and CAS Loops When Updating Only One Value

For a counter or quota stored in **one variable**, the CAS pattern from the standalone Java example fits well:

```java
public boolean reserveOne(AtomicInteger remaining) {
    while (true) {
        int current = remaining.get();
        if (current <= 0) {
            return false;
        }
        if (remaining.compareAndSet(current, current - 1)) {
            return true;
        }
    }
}
```

This snippet accepts an `AtomicInteger` shared across threads. CAS turns "change only if the value is still what I just read" into an atomic decision on **that variable**. If it fails due to contention, the loop must **re-read** instead of trying to write based on the stale value. Under contention, it may retry multiple times; avoid placing I/O or side effects inside the retry loop.

Do not use two separate `AtomicInteger`s and assume they form a transaction across two fields. If an invariant spans both `available` and `reserved`, another thread can still observe state between the two updates. You can bundle the fields into **one immutable state object** and CAS the reference, or use a lock to keep reasoning and correctness simpler.

### 5.3. Concurrent Collections: One Atomic Operation Differs from a Multi-Operation Sequence

For example, marking a key as "already processed" in memory:

```java
private final java.util.Set<String> processed =
        java.util.concurrent.ConcurrentHashMap.newKeySet();

public boolean markOnce(String requestId) {
    return processed.add(requestId); // true only for the first successful add.
}
```

This is a snippet inside a shared class. `add` on a concurrent key set supports atomic marking for **a single key**. By contrast, `if (!processed.contains(id)) processed.add(id)` separates check and act, so you cannot rely on `contains` to decide who has the right to process.

`ConcurrentHashMap.putIfAbsent`, `compute`, and `computeIfAbsent` also provide atomic operations **per key** per their API contracts. A `compute` callback must be short, simple, must not recursively modify the same map, and must not send emails, debit funds, or make network calls inside: a map callback does not create a transaction with external systems. For conditions spanning multiple keys, higher-level coordination is required.

`LongAdder` can optimize high-contention counting statistics, yet `sum()` during concurrent updates is not a system-wide atomic snapshot. Do not use `sum() >= limit` followed by `increment()` as a way to enforce an exact quota.

## 6. Placing Protection Inside a Spring Bean Properly

The following example is a **Spring-managed service** in a Spring Boot/Spring Framework project that already has the relevant dependencies. This is a complete class to place into project source code in an appropriate package; it is not a standalone `javac` program because it uses Spring annotations.

**`LocalSeatService.java`:**

```java
import org.springframework.stereotype.Service;

@Service
public class LocalSeatService {
    private final Object stateLock = new Object();
    private int remaining = 3;
    private int booked = 0;

    public boolean bookOne() {
        synchronized (stateLock) {
            if (remaining <= 0) {
                return false;
            }
            remaining--;
            booked++;
            return true;
        }
    }

    public State state() {
        synchronized (stateLock) {
            return new State(remaining, booked);
        }
    }

    public record State(int remaining, int booked) {}
}
```

A controller can call `bookOne()`; when three requests arrive concurrently, at most three calls will succeed **within a single bean instance**. The `state()` method returns an immutable record containing two values read together under the same lock.

Assumptions that must be documented when using this approach:

- **`@Service` defaults to singleton per `ApplicationContext`.** This does not mean singleton across an entire cluster. Two JVMs/pods have two `LocalSeatService` instances and two separate locks.
- **State lives in RAM:** restarting wipes the counts. If the business rule is real seat reservation, data must live in a database; an in-memory bean is not an appropriate source of truth.
- **Request scope or prototype is not a cure for races:** different objects can still point to a shared resource, or a single object can still be used by multiple threads. Analyzing actual ownership matters more than changing scope.
- **`@Async` does not guarantee thread-safety:** it offloads work to an executor and actually makes concurrent access more likely if state is shared.
- **Invariants must be protected across every entry point:** HTTP endpoints, scheduled tasks, listeners, and other services must not update `remaining`/`booked` via shortcuts.

When business logic includes DB operations, you should not hold a Java lock and call the DB inside it as a default habit. That lock only covers threads inside one JVM and can be held for a long time due to I/O; use database transactions, constraints, and atomic updates for persistent state.

## 7. Multi-Step Operations in a Database: `@Transactional` Must Be Paired with Race Protection

A common buggy example:

```java
@Transactional
public boolean reserveWrong(long eventId) {
    int available = jdbc.queryForObject(
            "SELECT available FROM event_capacity WHERE event_id = ?",
            Integer.class, eventId);

    if (available <= 0) {
        return false;
    }

    jdbc.update(
            "UPDATE event_capacity SET available = available - 1 WHERE event_id = ?",
            eventId);
    return true;
}
```

This is an illustrative snippet with an injected `JdbcTemplate jdbc`, not a standalone class. **Adding `@Transactional` alone is not enough to eliminate races** between two concurrent transactions under common isolation configurations such as READ COMMITTED: both can read the old value before updating. Exact behavior on lock/isolation conflicts depends on the database. Never assume "transaction = automatically serializes all requests."

When the rule is simply "decrement by 1 if a slot remains," you can turn both check and decrement into **a single conditional UPDATE statement**:

```sql
UPDATE event_capacity
SET available = available - 1
WHERE event_id = :event_id
  AND available > 0;
```

In a compliant RDBMS supporting transactions and row locking, this statement evaluates the condition and updates consistently against competing updates on the same row. **The affected row count** determines success: `1` means a slot was reserved; `0` means no slots remained or the ID does not exist. Verify behavior with your specific database/driver.

If a registration record is also created afterwards, both DB operations must belong to **a single transaction**. The Spring JDBC example below can be used in an application configured with `JdbcTemplate`, a datasource, and a transaction manager:

**`DatabaseReservationService.java` (Spring integration snippet):**

```java
import org.springframework.jdbc.core.JdbcTemplate;
import org.springframework.stereotype.Service;
import org.springframework.transaction.annotation.Transactional;

@Service
public class DatabaseReservationService {
    private final JdbcTemplate jdbc;

    public DatabaseReservationService(JdbcTemplate jdbc) {
        this.jdbc = jdbc;
    }

    @Transactional
    public boolean reserve(long eventId, String requestId) {
        int updated = jdbc.update(
                "UPDATE event_capacity " +
                "SET available = available - 1 " +
                "WHERE event_id = ? AND available > 0",
                eventId);

        if (updated != 1) {
            return false;
        }

        jdbc.update(
                "INSERT INTO event_registration (request_id, event_id) VALUES (?, ?)",
                requestId, eventId);

        return true;
    }
}
```

The example assumes a minimal schema of `event_capacity(event_id PRIMARY KEY, available)`, `event_registration(request_id UNIQUE, event_id)`, a `CHECK (available >= 0)` constraint if supported by the database, and real database transactions. The unique `request_id` prevents creating two registrations with the same identifier. If INSERT violates the unique constraint and Spring JDBC throws a runtime exception, the transaction rolls back the decrement as well by default. Duplicate `requestId` errors should be handled at the **outer call boundary outside the transaction** to look up the previous result if business rules require idempotent retries; the illustrative class above does not implement the full idempotency workflow itself.

**Distinguishing other DB mechanisms clearly:**

| Mechanism | Suitable when | Notes |
| --- | --- | --- |
| `UPDATE ... WHERE condition` + check affected rows | Rule can be expressed as a single conditional update | Usually simple for stock/quota; check affected rows and errors |
| Unique constraint | Two records must not share the same business key | `SELECT` before `INSERT` does not replace a unique constraint |
| Optimistic locking with `@Version` | Multiple requests edit the same entity, conflicts relatively rare | Failed transactions due to stale versions need a retry or conflict strategy |
| Pessimistic row lock, e.g., `SELECT ... FOR UPDATE` or JPA `PESSIMISTIC_WRITE` | Multi-step read and update across related rows | Locks can block, deadlock, or time out; lock ordering must be consistent |
| Stronger isolation, such as SERIALIZABLE | Complex rules needing transactional consistency guarantees | Contention cost and possible transaction aborts/retries; RDBMS-dependent |
| Queue/outbox or workflow coordinator | Business flow spans DB plus external services and must survive restarts/retries | Cross-system atomicity cannot be achieved with `synchronized` or a normal DB transaction alone |

Do not wrap sending emails or calling an external REST service inside a DB lock/transaction and assume they will roll back with the database. If events must be emitted reliably after a DB write, consider a transactional outbox and idempotent downstream consumers.

## 8. Common Issues That Break "Already Locked" Solutions

### Locking at the Wrong Scope

`synchronized` on one instance only protects **that instance**. Multiple application instances sharing a DB do not share monitors. For persistent data, use atomic DB constraints/transactions or an appropriately designed distributed coordinator. Distributed locks must account for lease expiration, fencing tokens, and failures; they should not be used merely to replace a conditional SQL statement.

### Reading Without the Same Protection Mechanism

If a writer updates `available` and `reserved` inside a lock while a reader reads them independently outside the lock, the reader can observe a "half-old, half-new" snapshot. Reading multiple related fields requires the same monitor, a properly published immutable snapshot, or an appropriate DB transaction/snapshot level.

### "Every Individual Call Is Thread-Safe" Yet the Workflow Is Not

`AtomicInteger.get()` and `getAndDecrement()` are each individually atomic, yet combined they do not protect the condition. The same applies to `ConcurrentHashMap.containsKey()` + `put()`, or DB `SELECT` + `UPDATE` without an appropriate guard/lock. You must inspect **the entire decision**.

### Misunderstanding Spring Proxy and Transaction Boundaries

Spring handles `@Transactional` via AOP proxies by default; internal `this.methodAnnotated()` calls inside the same bean normally bypass the proxy and do not open a transaction as expected. Imperative transactions are thread-bound; work offloaded to another thread with `@Async` does not automatically inherit the caller thread's transaction. When an async task needs a transaction, place the transaction boundary on the service/method executing on that thread via a properly Spring-managed call.

### Overly Broad Locks or Inconsistent Lock Nesting

A global lock can sharply degrade throughput, especially when it encloses I/O. Multiple locks acquired in differing orders can deadlock. Choose the right lock granularity (per-key/per-account when appropriate), a fixed lock order, timeouts, and wait-time metrics. Optimize locks only after invariants hold.

### Errors, Retries, and Non-Idempotent Operations

If state is updated and then an exception occurs before recording/returning the result, the caller may retry and execute it a second time. In-memory locks cannot survive crashes/retries across JVMs. You need request IDs/idempotency keys, unique constraints, transaction rollbacks, outboxes, or corresponding business techniques. Correctness covers **what happens on failure**, not only when two threads run normally.

## 9. How to Test and Evaluate a Solution

Concurrency problems cannot be proven by a single run that "looks right." Verify invariants across many interleavings and design tests with active synchronization points:

1. **Define invariants:** successful grants do not exceed quota; `remaining >= 0`; component totals remain constant; a given request ID is accepted at most once.
2. **Create controlled concurrent contenders:** use `CountDownLatch` or `CyclicBarrier` so multiple workers reach the check point simultaneously; tests should not rely solely on `Thread.sleep`.
3. **Collect every task's result:** await `Future.get()`/`join()` so you do not assert before tasks complete; handle exceptions; do not assume thread completion order.
4. **Assert invariants, not log order:** e.g., with 1 slot and 2 contenders, exactly one must succeed and remaining stock must be 0; it does not matter whether request A or B wins.
5. **Exercise failure conditions:** timeouts, exceptions in step two, retries with the same request ID, transaction rollbacks, restarts, and multiple JVMs if applicable.
6. **Observe resource limits:** lock contention counts, wait times, deadlocks/timeouts, throughput, DB errors, and optimistic-lock retry counts.

The Java test in section 4 proves one specific failing schedule for the broken approach and correct outcomes for two fixes in a small scenario. It is **not a formal proof** that every application deployment is bug-free. For DB state or multi-instance setups, real integration tests must use the actual database, isolation level, pool settings, and target deployment topology.

## 10. Choosing an Approach per Scenario

| Problem | Required atomic boundary | Preferred approach |
| --- | --- | --- |
| Temporary in-memory quota of one singleton bean in one JVM | One integer | `AtomicInteger` + CAS loop or synchronized |
| Two or more fields on the same bean must satisfy an invariant | The whole field group | One consistent lock / immutable state CAS; snapshot under the same mechanism |
| Deduplicating a key in a concurrent cache | One key | `putIfAbsent`/`newKeySet().add()`/`compute` as appropriate |
| Durable inventory deduction accessed by multiple pods | One row/condition in the database | Conditional UPDATE + affected rows + DB constraints |
| Transferring balances between two accounts | Multiple rows and one transaction | Database transaction, locking/isolation, update ordering, and retries |
| Duplicate requests from network/queues | Request ID and durable outcome | Idempotency key, unique constraint, state record |
| Writing DB then reliably publishing an event | DB commit + eventual event delivery | Outbox/queue and idempotent consumer |

You can self-audit a method with five questions: **(1)** What is the "only if..." rule checking? **(2)** What data can change immediately after the check? **(3)** What mechanism makes the entire decision atomic? **(4)** Does that mechanism cover one object, one JVM, one database, or the whole cluster? **(5)** If a crash or retry happens mid-way, do the invariants and business outcome remain valid?

## 11. References

- [Java SE 17 – AtomicInteger](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/concurrent/atomic/AtomicInteger.html): `get()`, `compareAndSet()`, `getAndDecrement()`.
- [Java SE 17 – ConcurrentHashMap](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/concurrent/ConcurrentHashMap.html): `putIfAbsent`, `compute`, and per-key atomic guarantees.
- [Java SE 17 – Lock](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/concurrent/locks/Lock.html): acquire/release, interruptibility, and `tryLock`.
- [Spring Framework – Understanding Declarative Transaction Implementation](https://docs.spring.io/spring-framework/reference/data-access/transaction/declarative/tx-decl-explained.html): transaction proxies, thread-bound transactions, and differences with reactive.
- [Spring Framework – Using @Transactional](https://docs.spring.io/spring-framework/reference/data-access/transaction/declarative/annotations.html): proxy invocation rules and self-invocation.

**Remember:** thread-safety of an individual field, collection, or statement does not automatically make a **check-then-act workflow** correct. Start from the invariants, enclose the decision point in an atomic mechanism with a wide enough scope, and test concurrent execution, failures, retries, and multiple instances.

# Distinguishing Between Concurrency Control and Business Transactions in Java

## 1. Two Different Problems That Often Appear Together

Suppose a system transfers 200 currency units from account A to account B, while multiple users can concurrently transfer money from the same account.

There are **two independent questions**:

1. **Concurrency control:** When multiple threads/requests touch the same state, which operation is allowed to proceed first, and which must wait or be rejected? How do we avoid *race conditions*, *lost updates*, reading intermediate state, data not being visible across threads, or deadlocks?
2. **Business transaction:** When is a business action considered complete, and what rules must it preserve? A money transfer is only considered successful if all required steps succeed together; if it fails, the final state needs to be restored/compensated according to the system's guarantees.

**Concurrency control manages the interaction between simultaneous activities; business transactions manage the correctness and lifecycle of a business operation.** An application often needs both, but they cannot replace one another.

The term `transaction` sometimes has the narrow meaning of a **database transaction (ACID)**, and sometimes the broad meaning of a **business transaction** spanning multiple operations or multiple services. It is important to be clear which meaning is being used. A business transaction may contain one or more database transactions; it may also include external calls that a DB rollback cannot undo.

### Comparison by Responsibility

| Perspective | Concurrency control | Business transaction |
|---|---|---|
| Core question | How do multiple actors executing simultaneously affect each other? | Under what conditions is a business request considered successful or failed? |
| Managed target | Shared state regions, execution order, access rights, data visibility | Business unit, *invariants*, steps, and committed outcome |
| Common Java mechanisms | `synchronized`, `ReentrantLock`, `volatile`, `AtomicInteger`, `ConcurrentHashMap`, CAS, executors | Operation orchestration, rule validation, request state; with DBs using JDBC `commit`/`rollback`; across multiple systems using idempotency/compensation |
| Typical guarantees | Mutual exclusion, ordering/happens-before, atomic updates on a single variable, or conflict detection | Business-meaningful success; consistency with business rules; depending on infrastructure, atomicity/rollback/durability or compensation |
| On failure | Threads may wait, retry, time out, or fail due to contention | May roll back a DB transaction, mark as failed, or execute a compensation step |
| Boundary | Threads, objects, processes; with databases also locks and isolation levels | A request/order/transfer; may span threads, processes, and services |

> Java locks coordinate threads within **a single JVM**. They do not inherently create durable transactions, do not roll back already-written data, and cannot lock across other JVMs. Conversely, `Connection.commit()` does not make Java variables outside the DB thread-safe.

## 2. Seeing the Problem Through an Execution Schedule

Account A has 100. Two requests X and Y both want to withdraw 80, both mistakenly implemented as `read → check → write` without coordination:

| Time | Request X | Request Y |
|---|---|---|
| t1 | Read balance A = 100 | |
| t2 | | Read balance A = 100 |
| t3 | Check 100 ≥ 80: valid | |
| t4 | | Check 100 ≥ 80: valid |
| t5 | Write A = 20, return success | |
| t6 | | Write A = 20, return success |

The final state is 20, yet **both requests claimed to have spent 80 out of 100**. This is a *lost update* and simultaneously violates the business rule. Wrapping each request as "one transaction" at the method-call level is not enough: we need an appropriate DB/Java mechanism so that two read-check-write sequences cannot accept the same stale balance.

On the flip side, merely placing `synchronized` around the balance subtraction can prevent a race within a single JVM, but if a request has already debited A and then encounters an error before crediting B, a Java lock **does not automatically undo** the debit on A. The execution order can be right while the business outcome is still wrong.

Distinguish three properties:

- **Mutual exclusion:** two threads do not execute the locked region at the same time.
- **Atomicity:** an operation or group of operations appears as an indivisible unit under the mechanism in question. `AtomicInteger.incrementAndGet()` is atomic on **a single variable**, not turning multiple transfer steps into a transaction.
- **Durability:** committed results survive failures according to the storage guarantee. `synchronized`, `volatile`, and CAS do not provide durability.

An operation can be safe on a single variable yet still fail to protect **invariants involving multiple objects** (for example, A + B remains constant).

## 3. Concurrency Control at the Java Level

The tools below solve different parts of the problem:

- `synchronized` and `ReentrantLock`: mutual exclusion for code sections accessing shared state. `synchronized` also establishes a *happens-before* relationship from a monitor release to the next monitor acquisition on the same monitor; `ReentrantLock` provides equivalent memory synchronization effects when locked/unlocked properly.
- `volatile`: provides visibility and ordering rules for a single field; it does **not** turn `counter++` into an atomic increment. Use it for simple state flags, not by itself to protect multi-field invariants.
- `AtomicInteger`, `AtomicLong`, `AtomicReference`: CAS/atomic update operations on individual variables or references; if a multi-field invariant is needed, you can use an immutable state object replaced atomically or use appropriate locking.
- `ConcurrentHashMap`: thread-safe for the operations guaranteed by its API; a `get → if → put` sequence is not automatically atomic, so use `compute`, `putIfAbsent`, or other coordination when the entire computation must be consistent.
- `ExecutorService`, `CompletableFuture`, `CountDownLatch`: organize work and coordination; running/starting/awaiting multiple tasks is **not a transaction** by itself. `CompletableFuture.allOf(...)` does not roll back completed tasks if another task fails.

Choose the right **locking granularity**: all read/write paths for a piece of state must follow the same convention. Protecting each field with a separate lock is not enough if a rule needs to read multiple fields together; locking an object only works if every participant locks on that exact same object. Coarser locks make invariants easier to maintain but can reduce parallel execution.

### Runnable Java 17 Example: Safe In-Memory Money Transfer

The following example only simulates a *business unit within a single JVM*. All account data and snapshot reads go through the same monitor; expected failure conditions are checked **before** modifying balances. This is not a real banking system: there is no durable storage, transaction log, crash-recovery guarantee, or cross-service communication.

Create the file `LedgerDemo.java`:

```java
import java.util.HashMap;
import java.util.Map;

public class LedgerDemo {
    public static void main(String[] args) {
        Ledger ledger = new Ledger();
        ledger.open("A", 1_000);
        ledger.open("B", 500);

        ledger.transfer("A", "B", 200);
        System.out.println(ledger.snapshot());

        try {
            ledger.transfer("A", "B", 900);
        } catch (IllegalStateException ex) {
            System.out.println("Rejected: insufficient funds");
        }
        System.out.println(ledger.snapshot());
    }

    static final class Ledger {
        private final Object mutex = new Object();
        private final Map<String, Long> balances = new HashMap<>();

        void open(String id, long cents) {
            if (cents < 0) throw new IllegalArgumentException("negative balance");
            synchronized (mutex) {
                if (balances.putIfAbsent(id, cents) != null) {
                    throw new IllegalArgumentException("duplicate account");
                }
            }
        }

        void transfer(String from, String to, long cents) {
            if (cents <= 0 || from.equals(to)) {
                throw new IllegalArgumentException("invalid transfer");
            }
            synchronized (mutex) {
                Long debit = balances.get(from);
                Long credit = balances.get(to);
                if (debit == null || credit == null) {
                    throw new IllegalArgumentException("unknown account");
                }
                if (debit < cents) {
                    throw new IllegalStateException("insufficient funds");
                }
                // Compute upfront so an overflow error does not occur after debiting.
                long nextCredit = Math.addExact(credit, cents);
                balances.put(from, debit - cents);
                balances.put(to, nextCredit);
            }
        }

        String snapshot() {
            synchronized (mutex) {
                long a = balances.get("A");
                long b = balances.get("B");
                return "A=" + a + ", B=" + b + ", total=" + (a + b);
            }
        }
    }
}
```

Compile and run:

```bash
javac LedgerDemo.java
java LedgerDemo
```

Output:

```text
A=800, B=700, total=1500
Rejected: insufficient funds
A=800, B=700, total=1500
```

In this example:

1. **Concurrency control:** the `mutex` monitor forces operations involving the map to enter the protected region; other threads cannot observe an intermediate state via `snapshot()`.
2. **Business transaction logic:** only allows transferring a positive amount, between two different accounts, with sufficient balance; the total balance is preserved across a successful transfer. The insufficient-funds case fails before any write occurs.
3. **Limitations:** if power is lost, the JVM stops, or an unrecoverable error occurs while writing to memory, there is no rollback/durability like a DB transaction. The lock does not span across other JVMs; the printed total uses `long`, whereas a real application must have an overflow-prevention policy and an appropriate monetary representation.

Trying to invoke `transfer` across multiple threads still preserves the rules because the methods coordinate through a single monitor. However, using one lock for the entire ledger becomes a bottleneck when the number of accounts is large; real systems typically offload update isolation to the DB, using fine-grained locking or optimistic concurrency with clearly defined invariant boundaries.

## 4. Business Transactions and Database Transactions

A **business transaction** is a business commitment such as "an order succeeds when inventory is reserved and the order is recorded." A business transaction can be executed using a single **database transaction** if all changes reside in the same database, backed by the same transaction manager.

ACID in a database transaction is commonly understood as:

- **Atomicity:** all changes belonging to the transaction commit or roll back together according to the DB mechanism.
- **Consistency:** the transaction transitions from a state satisfying the modeled constraints to another state satisfying those constraints; the DB cannot automatically know business rules that have not been declared or programmed.
- **Isolation:** the extent to which one transaction sees or affects another depends on the **isolation level** and how queries/writes are structured; it does not mean every concurrent schedule is automatically equivalent to serial execution.
- **Durability:** committed data survives failures according to the DB's guarantee mechanisms and configuration.

A DB transaction typically follows the sequence: open connection → disable auto-commit → read/check/update → `commit()` when everything succeeds, or `rollback()` on failure → close connection. A transaction is bound to a specific connection/resource; it **does not automatically cover** arbitrary Java objects, HTTP requests, message brokers, or payment services.

### JDBC Snippet: Commit/Rollback Boundaries

This is an illustrative method snippet inside a class importing `javax.sql.DataSource` and `java.sql.*`; it requires an `account(id, balance_cents)` table, a real connection/driver, and a schema to run. Assume `balance_cents` is a range-checked integer and the DB enforces a non-negative balance constraint. It is not a standalone program.

```java
void transfer(DataSource dataSource, long fromId, long toId, long amount)
        throws SQLException {
    if (amount <= 0 || fromId == toId) {
        throw new IllegalArgumentException("invalid transfer");
    }

    try (Connection connection = dataSource.getConnection()) {
        connection.setAutoCommit(false);
        try {
            try (PreparedStatement debit = connection.prepareStatement(
                    "UPDATE account SET balance_cents = balance_cents - ? " +
                    "WHERE id = ? AND balance_cents >= ?")) {
                debit.setLong(1, amount);
                debit.setLong(2, fromId);
                debit.setLong(3, amount);
                if (debit.executeUpdate() != 1) {
                    throw new IllegalStateException("insufficient funds");
                }
            }

            try (PreparedStatement credit = connection.prepareStatement(
                    "UPDATE account SET balance_cents = balance_cents + ? " +
                    "WHERE id = ?")) {
                credit.setLong(1, amount);
                credit.setLong(2, toId);
                if (credit.executeUpdate() != 1) {
                    throw new IllegalStateException("destination missing");
                }
            }

            connection.commit();
        } catch (SQLException | RuntimeException failure) {
            try {
                connection.rollback();
            } catch (SQLException rollbackFailure) {
                failure.addSuppressed(rollbackFailure);
            }
            throw failure;
        }
    }
}
```

Key points to read carefully:

- Both `UPDATE` statements run on **the same connection and the same DB transaction**; if the debit fails or the destination account does not exist, `rollback` is triggered. Whether the DB actually guarantees atomicity/durability also depends on the storage engine and storage configuration.
- `UPDATE ... SET balance_cents = balance_cents - ? WHERE ... balance_cents >= ?` checks the condition and updates on the DB side under the DB's concurrency control. It avoids the error-prone pattern of "SELECT balance into Java → compute → UPDATE new value" when multiple transactions touch the same row.
- A transaction **still needs** appropriate isolation and concurrency control (row locks, version checks, constraints, or a stronger isolation level). Many RDBMSs can report deadlock/serialization failures under contention; errors must be handled and the **entire** transaction retried only when safe.
- This illustrative pattern does not solve all production requirements: overflow checks, limits and currency units, ledger/audit entries, idempotency keys, authorization, durability, and retry policies must be designed separately. On a specific DB or driver, you must verify data types, lock behavior, timeouts, and supported SQL syntax.
- `rollback()` can fail due to a lost connection; the application must handle **unknown outcomes** after a network error during commit, rather than assuming "an exception was thrown = it did not commit."

**Crucial point:** A DB transaction and a Java monitor are two independent scopes. Holding a Java lock around JDBC calls does not make other service instances wait on that lock. Wrapping a `HashMap` inside a JDBC transaction does not roll back changes to the map.

## 5. Three Common Contention-Handling Strategies

### 5.1. Pessimistic Locking

Acquire a lock before working with the resource; in Java use `synchronized` or `ReentrantLock`; in a DB use locking mechanisms held for the duration of the transaction (such as `SELECT ... FOR UPDATE` on supported DBs). Suitable when conflicts are frequent or computations must preserve an invariant before writing.

Trade-offs: operations may wait a long time, deadlock, or suffer reduced throughput. Keep the lock scope small yet sufficient to cover the invariant, acquire locks in a consistent order, avoid slow API calls while holding a lock, and define timeout/failure policies.

### 5.2. Optimistic Concurrency Control

Do not hold an application lock during computation; on write, verify that the data is still at the version that was read. For example, a row has a `version` column:

```sql
UPDATE account
SET balance_cents = :new_balance, version = version + 1
WHERE id = :id AND version = :version_read;
```

If the number of updated rows is **0**, the version has changed or the record no longer exists: treat this as a conflict/not found, and do **not** report success. You must reload, re-check the invariant, and decide whether to retry, return an error to the user, or reconcile. Using `AtomicReference.compareAndSet(expected, updated)` follows the same idea of verifying the old value, but only within that JVM's memory.

Note: overwriting with a `new_balance` computed from stale data after hitting a conflict is wrong. If the business rule spans multiple rows or predicates across multiple records, a single row's version is not enough to protect the entire invariant.

### 5.3. Conditional Updates and Database Constraints

For example: `UPDATE stock SET quantity = quantity - 1 WHERE sku = ? AND quantity > 0` and then checking the affected row count; combined with `CHECK`, `UNIQUE`, foreign keys, and appropriate transaction boundaries. This moves critical conditions right next to where contention happens; a unique constraint on `idempotency_key` can prevent two duplicate requests from both producing an effect.

Choose a strategy based on **actual contention points and business invariants**, not on how many threads appear in the code.

## 6. When a Business Operation Spans Multiple Resources

For example, placing an order involves: reserving inventory in the DB, calling a payment service, publishing a confirmation event, and sending an email. A local DB transaction **does not automatically roll back** a payment already accepted by another system or an email already sent.

Safe ways to think about this:

1. Define clear business states: `PENDING`, `CONFIRMED`, `CANCELLED` (or states appropriate to the domain).
2. Use a local transaction to commit changes within the same DB; use a **transactional outbox** when you need to record state and the event to be published as a single durable decision. A publisher processes the outbox afterward, accepting possible redelivery and keeping consumers idempotent.
3. Across multiple services, use a saga/workflow with explicit **compensation** steps (such as refunding money or releasing inventory). Compensation is a new business action, **not** equivalent to an instant ACID rollback; it can fail and needs retries and monitoring.
4. Attach an **idempotency key** to retryable requests; store the result/effect atomically with an appropriate unique constraint. Idempotency does not replace locking or isolation for two different requests contending for the same resource.
5. Distinguish timeouts from confirmed failures. A timed-out HTTP request may have already created a transaction on the receiving side; before retrying, you must query its status or use an appropriate deduplication key.

Distributed transaction models such as two-phase commit can be used when systems and resources support them, but they carry major trade-offs in coupling, availability, and operations. Do not assume that just because there are multiple services, a single Java call can synchronously commit/roll back across all of them.

## 7. Combining Both Layers Properly

Consider booking an available seat. *Business invariant*: each seat has at most one successful booking, and a single request must not create two bookings due to retries.

- **Concurrency control:** multiple users click to book the seat at the same time; use locks/conditional updates/unique constraints at the shared data source to pick exactly one winner. A `synchronized` block in a Java class on one instance does not stop another instance from booking the same seat.
- **Business transaction:** only mark the booking as successful when both the seat status and the booking record are committed consistently; errors before commit must roll back. If payment was already taken in a separate service and the booking then fails, a refund/compensation flow is required.
- **Idempotency:** the same user resending the same request due to a retry must not create an extra booking or charge twice; use a durable business key/idempotency key.
- **Observing outcomes:** only return "booking succeeded" after reaching the corresponding commit/business confirmation point; if the outcome is unknown, do not assert success or failure without reconciliation.

### Table for Choosing Mechanisms by Problem

| Symptom | Check first | Typical mechanism |
|---|---|---|
| `counter++` loses increments across multiple threads | Is a single variable shared within one JVM? | `AtomicInteger.incrementAndGet()` or a lock |
| Two requests concurrently deduct inventory and produce a negative number | Are check and write atomic at the shared store? | Conditional UPDATE, DB constraint, lock, or version |
| Debiting A succeeds but crediting B fails | Is there a commit/rollback boundary covering both changes? | A single DB transaction with complete error handling |
| Two individual rows are valid, but their sum/relationship is wrong | How many rows does the invariant span? Does isolation prevent *write skew*? | Serializable transaction, appropriate locking, invariant/constraint design |
| Payment API is called twice due to retry | Is the same request being identified? | Persisted idempotency key, unique constraint |
| DB rolls back, but email is still sent | How are side effects outside the DB coordinated? | Outbox, state machine, and compensation |
| Error reappears when scaling to multiple JVMs | Is the lock/counter shared across instances? | Mechanism at the DB/shared data source, distributed coordination when truly needed |

## 8. Isolation, the Java Memory Model, and Guarantee Scopes

Do not equate two different kinds of "visibility":

- **Java Memory Model (JMM):** describes relationships between Java thread operations within the same JVM. `volatile`, monitors, locks, atomic APIs, and coordination primitives establish *happens-before* per their API contracts. For example, writing data and then unlocking a monitor allows another thread that locks the same monitor to see the properly published data.
- **Database isolation:** describes interactions between DB transactions. Depending on the DB/isolation level, non-repeatable reads, phantoms, lost updates, or *write skew* can occur if the algorithm does not properly protect the invariant. `READ COMMITTED` does not inherently mean serializable; exact protections must be checked against the DB in use.

A `Connection` should also not be casually shared across threads to "join the same transaction"; concurrent usage and thread safety depend on the driver/API, and transaction boundaries are usually tied to the connection. When work is handed off via `CompletableFuture` or an executor, worker threads do not automatically inherit transaction/lock state from the calling thread.

**Practical rule:** verify guarantees at the layer where data is actually shared: Java fields within one JVM → Java concurrency primitives; multi-instance data in a DB → transactions, isolation, locking/constraints; effects across multiple systems → workflows, idempotency, and compensation.

## 9. How to Design and Test

A short checklist you can use during code reviews:

1. **Write down the invariants first:** e.g., `balance >= 0`, `A+B sum is constant`, `a seat has only one booking`, `each request-id has at most one successful outcome`.
2. **Identify the authoritative state store:** heap of one JVM, relational DB, distributed cache, message broker, or another service. Count all writers, including background jobs and multiple instances.
3. **Identify the linearization/commit point:** which step determines that an operation succeeded? Do earlier/later steps need rollback or compensation?
4. **Trace bad interleavings:** two requests read together and check together, a failure between two writes, a crash right after commit, a lost response with a client retry.
5. **Choose minimal yet sufficient protection:** locks/CAS in Java; conditional updates, versions, constraints, isolation in the DB; idempotency/outbox/workflows across multiple systems.
6. **Define failure policies:** lock timeouts, DB deadlocks, optimistic conflicts, rollback failures, uncertain outcomes, retries with backoff and limits; every retry must preserve business meaning.
7. **Test at the real boundaries:** test multiple threads with `ExecutorService` + `CountDownLatch` to create contention and await `Future.get()`; assert invariants after completion. With multiple JVMs, test against a shared DB; add fault injection between steps, crash/restart, and duplicate idempotency-key retries.

In concurrency testing, do not rely on `Thread.sleep(...)` to prove the presence or absence of a race: scheduler timing is non-deterministic. Use latches/barriers to increase reproducibility, run many iterations, and above all **assert invariants**; a single passing test run does not prove an algorithm is correct under all interleavings.

## 10. Common Misconceptions to Avoid

- **"Using `synchronized` makes a money transfer a transaction."** False: locks only coordinate access within a monitor/JVM scope; they provide neither rollback nor durability.
- **"Having a DB transaction makes races impossible."** False: outcomes still depend on isolation, query style, constraints, and update algorithms. Two transactions can still read the same stale condition if unprotected.
- **"`volatile` is enough for all shared updates."** False: visibility is different from an atomic read-modify-write operation.
- **"`AtomicInteger` makes an entire business operation atomic."** False: a single atomic variable does not protect a sequence of changes across multiple resources.
- **"Retrying any error is safe."** False: retries can duplicate payments/orders when the first attempt already committed but the response was lost.
- **"A DB rollback undoes HTTP calls or emails."** False: such side effects require separate compensation or orchestration mechanisms.
- **"Application-level locks are enough for a cluster."** False: multiple JVMs have separate monitors and heaps. Enforce consistency at the shared source or use appropriate coordination.
- **"A successful transaction means the business rules were respected."** False: ACID does not automatically encode domain rules; missing invariants, constraints, or timely checks still lead to wrong outcomes.
- **"The broader the lock, the safer it is."** Not entirely: holding locks across I/O and long work increases latency, invites deadlocks, and hurts scalability; you can still lock the wrong object or miss a writer.

## Conclusion

**Concurrency control** ensures concurrent actors coordinate properly over shared state; a **business transaction** defines the success, failure, and invariants of a business action. A database transaction is one tool for implementing that commitment for DB data, with isolation and locking chosen appropriately. Start from the invariants, identify all writers and system boundaries, and then choose locks/CAS/constraints/transactions/idempotency/compensation accordingly.
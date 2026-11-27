# Isolation, Read Phenomena, and Database Support

## 1. What is transaction isolation?

An application can process multiple transactions simultaneously. When two transactions read or modify the same data, what one transaction sees depends on read timing, write timing, and how the database coordinates concurrent access.

**Isolation** is the ACID property defining the degree to which one transaction is affected by other concurrently running transactions. The higher the isolation level, the closer the outcome resembles running transactions sequentially, though the system may need to hold locks longer, wait more, or abort a transaction when conflicts are detected.

Isolation does not mean only one transaction can execute at a time. Databases can use locking, row versioning (MVCC), or a combination of both to allow multiple transactions to proceed concurrently while upholding the chosen rules.

In Spring Data JPA, isolation is configured at the Spring transaction boundary. JPA works with the persistence context and transaction manager; the actual effective isolation level is enforced jointly by the transaction manager, JDBC connection, and database management system.

## 2. Three common read phenomena

To make this easy to follow, assume an `account` table has one account with `id = 1` and `balance = 1000`.

### 2.1. Dirty read — reading uncommitted data

A dirty read occurs when transaction T2 reads a change that T1 has written but not yet committed. If T1 rolls back, the value T2 read never became committed data.

~~~sql
-- T1
BEGIN;
UPDATE account SET balance = 500 WHERE id = 1;
-- T1 has not COMMITted yet

-- T2, if the isolation level permits dirty reads
SELECT balance FROM account WHERE id = 1;
-- May read 500 even though T1 has not committed

-- T1
ROLLBACK;
-- The value 500 is discarded; committed data remains 1000
~~~

Consequence: T2 may make decisions based on data that gets discarded, such as recording a payment that never actually existed. READ COMMITTED and higher must prevent dirty reads by standard definition. Some databases do not permit dirty reads even if the application requests READ UNCOMMITTED.

### 2.2. Non-repeatable read — reading the same row and getting different values

A non-repeatable read occurs when T1 reads a row, T2 modifies and commits that row, and T1 reads the same row again and receives the new value.

~~~sql
-- T1
BEGIN;
SELECT balance FROM account WHERE id = 1; -- 1000

-- T2
BEGIN;
UPDATE account SET balance = 800 WHERE id = 1;
COMMIT;

-- T1
SELECT balance FROM account WHERE id = 1; -- may be 800 under READ COMMITTED
COMMIT;
~~~

T1 does not receive the same value across two reads. This phenomenon can cause a calculation within the same transaction to use inconsistent values. REPEATABLE READ and higher prevent non-repeatable reads by standard definition.

### 2.3. Phantom read — the set of rows matching a condition changes

A phantom read occurs when T1 re-runs a query with a condition and receives a different set of rows because another transaction inserted, deleted, or modified rows so that they start or stop matching the condition.

~~~sql
-- T1
BEGIN;
SELECT id FROM orders WHERE total >= 100;
-- Result: orders 10 and 11

-- T2
BEGIN;
INSERT INTO orders(id, total) VALUES (12, 150);
COMMIT;

-- T1
SELECT id FROM orders WHERE total >= 100;
-- At levels permitting phantom reads, the result now includes order 12
COMMIT;
~~~

Non-repeatable reads focus on the values of an already-read row; phantom reads focus on the membership of a result set matching a condition. To prevent phantoms, a database may lock a key range or maintain a consistent snapshot throughout the transaction.

### 2.4. Other concurrency anomalies

The three phenomena above are the read phenomena used in the SQL standard definition of isolation levels. They do not cover every concurrency anomaly that can occur.

- **Lost update:** T1 and T2 both read balance 1000. T1 adds 100, T2 subtracts 50. If both write values based on the stale read, the second write can overwrite the result of the first write.
- **Read skew:** T1 reads account A's balance before T2 transfers funds from A to B, then reads B's balance after T2 commits. T1 may observe a state combining two different points in time.
- **Write skew:** Two transactions read the same snapshot satisfying a business rule, then update two different rows. Each write is individually valid, yet together they violate the rule—for example, two doctors both mark themselves off-call even though the system requires at least one doctor on duty.

These anomalies must be distinguished from the three standard read phenomena. For example, REPEATABLE READ does not automatically protect every business invariant or prevent every lost update across all database systems.

## 3. The four standard SQL isolation levels

The following table describes minimum guarantees under the SQL standard definition:

| Isolation level | Dirty read | Non-repeatable read | Phantom read |
|---|---|---|---|
| READ UNCOMMITTED | May occur | May occur | May occur |
| READ COMMITTED | Prevented | May occur | May occur |
| REPEATABLE READ | Prevented | Prevented | May occur per standard |
| SERIALIZABLE | Prevented | Prevented | Prevented |

### 3.1. READ UNCOMMITTED

This is the lowest isolation level. Transactions can read uncommitted changes from other transactions. This level can reduce read wait times in some systems, but the risk of reading data that later rolls back makes business results unreliable.

Do not choose this level just for faster queries. Many database systems do not implement true dirty reads or map this request to READ COMMITTED.

### 3.2. READ COMMITTED

Each statement only reads data committed at the time the statement starts or according to the database's corresponding mechanism. Dirty reads are prevented, yet two SELECT statements in the same transaction can still see different committed versions.

This is a common default, balancing consistency and concurrency. It suits many routine operations, though a workflow that reads multiple times and makes decisions based on a transaction-wide snapshot may need a higher level or explicit locking.

### 3.3. REPEATABLE READ

Repeated reads within a transaction must preserve consistency for already-read rows according to this level's guarantees. By standard definition, phantom reads can still occur because a conditional query may pick up newly matching rows.

Implementation varies by database system. Some systems use transaction-level snapshots and also prevent phantom reads in ordinary read queries; that does not mean all concurrency anomalies disappear. Write skew or serialization anomalies can still occur in some snapshot isolation models.

### 3.4. SERIALIZABLE

This is the highest of the four standard isolation levels. The outcome of concurrent transactions must be equivalent to some serial execution order. Databases can achieve this via locking or conflict detection.

This level is appropriate when multiple transactions touch a complex business rule that single-row locks or application-level checks cannot adequately protect. In return, transactions may wait, encounter deadlocks, or be aborted due to serialization conflicts. The application must handle and potentially retry the entire transaction when the database returns an appropriate serialization error.

## 4. Support across major database management systems

Identical isolation level names do not guarantee identical behavior across all database systems. The table below describes common configurations; versions, engines, database options, and session settings can alter behavior.

| Database system | Common default | Support and key caveats |
|---|---|---|
| PostgreSQL | READ COMMITTED | Accepts all four standard levels. READ UNCOMMITTED is treated as READ COMMITTED, so it does not produce dirty reads. REPEATABLE READ uses transaction-level snapshots and prevents phantom reads too, though serialization anomalies can still happen. SERIALIZABLE uses conflict detection and can abort transactions to guarantee serializability. |
| MySQL with InnoDB | REPEATABLE READ | Supports all four standard levels. Under REPEATABLE READ, ordinary consistent reads use a snapshot established in the transaction; locking reads and range operations use locking mechanisms including next-key locks to control phantoms. READ UNCOMMITTED can read uncommitted changes. Confirm tables use a transaction-capable engine, typically InnoDB. |
| Microsoft SQL Server | READ COMMITTED | Supports all four standard levels plus a vendor-specific SNAPSHOT level. REPEATABLE READ holds locks on read rows while still allowing newly matching rows to appear; SERIALIZABLE uses key-range locks to prevent phantoms. The READ_COMMITTED_SNAPSHOT option makes READ COMMITTED use statement-level row versioning; transaction-level SNAPSHOT must be explicitly enabled via database configuration. |
| Oracle Database | READ COMMITTED | Selectable transaction isolation levels are READ COMMITTED and SERIALIZABLE; Oracle does not offer READ UNCOMMITTED or REPEATABLE READ as selectable levels. Oracle uses read consistency to avoid dirty reads; READ COMMITTED provides statement-level consistency, while SERIALIZABLE provides transaction-level snapshots. READ ONLY mode is a separate transaction mode, not a third level among the four standard levels. |

Several implications when reading the table:

- Setting READ_UNCOMMITTED on PostgreSQL still prevents reading dirty data because PostgreSQL implements it as READ_COMMITTED.
- You cannot conclude that every database with REPEATABLE_READ handles phantoms identically. SQL Server may allow phantoms at this level; PostgreSQL and InnoDB typically provide stronger guarantees for their respective snapshot reads.
- SQL Server's SNAPSHOT is a vendor-specific level, not one of Spring's four standard constants.
- For MySQL, the exact storage engine must be considered. Do not infer that every table or MySQL configuration shares InnoDB's transaction semantics.

## 5. Configuring isolation in Spring Data JPA

Spring provides the `Isolation` enum in the `org.springframework.transaction.annotation` package. You can set the isolation level on `@Transactional`:

| Spring value | Meaning |
|---|---|
| Isolation.DEFAULT | Uses the database or connection default; this is the annotation's default value. |
| Isolation.READ_UNCOMMITTED | Requests READ UNCOMMITTED. |
| Isolation.READ_COMMITTED | Requests READ COMMITTED. |
| Isolation.REPEATABLE_READ | Requests REPEATABLE READ. |
| Isolation.SERIALIZABLE | Requests SERIALIZABLE. |

Example of an order confirmation service:

~~~java
import org.springframework.stereotype.Service;
import org.springframework.transaction.annotation.Isolation;
import org.springframework.transaction.annotation.Transactional;

@Service
public class OrderService {
    private final OrderRepository orders;

    public OrderService(OrderRepository orders) {
        this.orders = orders;
    }

    @Transactional(isolation = Isolation.READ_COMMITTED)
    public void confirm(Long id) {
        Order order = orders.findById(id)
                .orElseThrow(() -> new IllegalArgumentException("Order not found: " + id));

        order.confirm();
    }
}
~~~

This is an illustrative service snippet; Order, OrderRepository, and confirm() belong to the application's model. When the method is called via the Spring proxy, the transaction opens according to the transaction manager's configuration. Managed entities in the persistence context are synchronized to the database on flush or commit.

Transaction boundaries should be placed at the service when a business operation involves multiple repository calls. That way, reads and writes share one transaction and the isolation policy applies to the entire operation. Inherited CRUD methods of Spring Data repositories have default transaction configurations; for custom query methods, configure transactions explicitly or call them inside a service transaction.

### 5.1. Important limitations of @Transactional

**Isolation is only applied when starting a new transaction.** With the default `REQUIRED` propagation, if a service is called inside an already-existing transaction, the call joins that transaction and uses the outer transaction's isolation. Declaring a different isolation on the inner method does not change the running transaction's isolation.

Spring's transaction manager has a `validateExistingTransaction` option to reject joining a transaction with incompatible isolation. This is a configuration option when the application needs to detect passing a transaction with the wrong level; it does not upgrade the current transaction's isolation.

**The transaction manager and database must support the requested level.** `@Transactional` is Spring configuration; it does not make a database support a level it lacks. Whether an isolation level is applied also depends on the transaction manager, JPA dialect, and JDBC driver. With `JpaTransactionManager`, the dialect must be able to apply the isolation setting to the JDBC connection. Verify actual configuration and behavior on the target database.

**Internal calls within the same bean can bypass the proxy.** In default proxy mode, a method calling another `@Transactional` method on the same object does not go through the Spring proxy. In that case, the transaction configuration on the called method may not take effect. Call via another Spring bean or reorganize transaction boundaries.

**Isolation does not replace data-layer concurrency mechanisms.** `@Version` supports optimistic locking by detecting updates based on a stale entity version. `@Lock` with `PESSIMISTIC_WRITE` can request a write lock for a repository query. `UNIQUE`, `FOREIGN KEY`, `CHECK` constraints, and conditional update statements are also tools for protecting data invariants. Choose mechanisms tailored to business rules instead of simply raising isolation for every transaction.

### 5.2. Specific notes on JPA's persistence context

JPA caches loaded entities in the persistence context's first-level cache. If `findById()` is called again within the same persistence context, `EntityManager` may return the already-managed entity without issuing a new SELECT. Therefore, when testing non-repeatable reads or phantom reads, results observed in Java can be affected by JPA's cache.

To properly test database behavior, control flush timing, clear the persistence context, inspect the actual SQL issued, and isolate transactions per thread. Calling a repository method again does not necessarily mean the database re-executed the exact SELECT statement.

## 6. Choosing an isolation level by business need

- **Use DEFAULT when possible:** let the database apply its tested, operational default configuration. This is usually a good choice for standard CRUD.
- **Use READ COMMITTED for most typical business operations:** prevents dirty reads and enables good concurrency. If an operation needs a stable snapshot across multiple reads, evaluate further.
- **Use REPEATABLE READ when consistent repeated reads are required:** check the exact phantom, snapshot, and concurrent-update behavior of your database system.
- **Use SERIALIZABLE when complex invariants must be protected:** e.g., total seat limits, shared quotas, or multi-row rules. Design retries when transactions are aborted due to conflicts.
- **Avoid READ UNCOMMITTED:** use only when uncommitted data is acceptable and you understand how the database implements it. For business data, dirty reads usually pose greater risk than benefit.

When handling concurrent updates, also consider:

1. Use `@Version` for optimistic locking when multiple users can edit the same entity. If the version has changed, the application detects a conflict instead of silently overwriting.
2. Use pessimistic locking for data regions requiring short-duration locks, such as holding an inventory record before deducting stock. Keep transactions short to avoid long locks and deadlocks.
3. Put rules into constraints or conditional update statements where possible. For example, update stock only when `quantity >= :requestedQuantity`, then check the affected row count.
4. With SERIALIZABLE or snapshot isolation, prepare to handle conflict errors and retry the entire unit of work. Do not merely retry a single statement inside an aborted transaction.
5. Test on the same database type and configuration close to production. H2 or in-memory databases may have different isolation semantics than PostgreSQL, MySQL, SQL Server, or Oracle.

## 7. How to test read phenomena

An isolation test needs at least two independent transactions, usually running on two threads or two connections. Coordinate operation ordering with latches/barriers to ensure T1 reads first, T2 writes and commits, and then T1 reads again. Using the same `EntityManager` or the same transaction may fail to simulate true contention between two transactions.

Basic test procedure:

1. Create initial committed data.
2. Open transaction T1 and perform the first read.
3. Open independent transaction T2, modify or insert data, then commit.
4. In T1, re-run the query under test.
5. Compare results against the isolation level guarantees on the database in use.
6. Also test rollback, lock wait, deadlock, or serialization failure cases if the business flow may encounter them.

Do not rely solely on a sequential unit test to conclude isolation works properly. Use integration tests against a real database (such as Testcontainers for your target engine), because locking, MVCC, snapshots, and concurrency errors depend on the database system.

## 8. Common misconceptions

- **Isolation differs from propagation:** isolation governs data visibility/isolation between transactions; propagation governs how transactions are created, joined, or separated from the current transaction.
- **Isolation differs from locking:** an isolation level is an overall policy; the database may use locks, MVCC, or both to implement that policy.
- **readOnly = true is not an isolation level:** it is an optimization hint or write-restriction mode depending on the transaction manager/database; it does not prevent other transactions from updating data.
- **REPEATABLE READ does not mean SERIALIZABLE:** anomalies such as write skew can still happen under snapshot isolation.
- **@Version does not replace isolation:** it protects updates to a versioned entity, but does not automatically protect multi-row rules.
- **Do not assume all databases behave identically:** always verify engine documentation, session settings, and test on the target system.

When designing transactions in Spring Data JPA, start from the business invariant to protect, identify which concurrency phenomena could corrupt results, and then choose the appropriate isolation level or locking mechanism. This balances correctness, concurrency throughput, and operational cost.
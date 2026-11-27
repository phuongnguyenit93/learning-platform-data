# Limitations of @Lock with @Query and SQL locking alternatives

## 1. Why is locking needed when multiple transactions access data concurrently?

Suppose a product has 5 units in stock. Two nearly simultaneous requests each want to order 4 units:

~~~text
Transaction A                         Transaction B
-------------                         -------------
SELECT available = 5
                                      SELECT available = 5
Check 5 >= 4
                                      Check 5 >= 4
UPDATE available = 1
                                      UPDATE available = 1
COMMIT                                COMMIT
~~~

If the application reads the value first, checks it in Java, and then writes a new value computed from stale data, both requests can pass the check. This is a form of race condition in a read-modify-write flow.

Databases provide locking mechanisms to coordinate concurrent transactions. With Spring Data JDBC, two common approaches are:

- Using `@Lock` on a **derived query method** so Spring Data generates a SELECT with a dialect-specific lock clause.
- Writing the lock clause directly in SQL inside `@Query` or `JdbcTemplate` when an explicit SQL query is needed.

There is an important limitation: **Spring Data JDBC currently does not apply `@Lock` to query methods declared with string-based `@Query`**. If both annotations are placed on the same method, the locking metadata from `@Lock` is ignored and Spring logs a warning. Therefore, once you use `@Query`, include the lock syntax in the SQL itself if the database supports it.

This lesson explains that limitation, how to choose between PESSIMISTIC_READ and PESSIMISTIC_WRITE, how to write FOR UPDATE/FOR SHARE, lock lifetimes in transactions, and alternatives such as optimistic locking or conditional UPDATEs.

## 2. Pessimistic locking in Spring Data JDBC

Pessimistic locking assumes contention is possible and asks the database to lock data while a transaction is processing. Another transaction wanting to modify or lock the same rows may have to wait, or fail depending on the statement and database configuration.

Spring Data JDBC provides two lock modes:

| Lock mode | Meaning |
| --- | --- |
| PESSIMISTIC_READ | Requests a read lock; intended to prevent other transactions from modifying data being read while the lock is active. |
| PESSIMISTIC_WRITE | Requests a write lock; suited for read-then-update flows. |

Some databases do not clearly distinguish between these two modes; the dialect may map both to a write lock. Thus, the mode name expresses application intent, while actual behavior depends on the database and dialect.

The Spring Data JDBC types used in the examples reside in these packages:

~~~java
import org.springframework.data.relational.repository.Lock;
import org.springframework.data.relational.core.sql.LockMode;
~~~

This is the Spring Data Relational API. Do not confuse this Lock/LockMode with jakarta.persistence.LockModeType or Spring Data JPA's locking annotations.

## 3. @Lock is supported on derived query methods

A derived query method is inferred from the method name, such as findBySku. Spring Data JDBC parses the properties and generates SQL. When the method has @Lock, the framework appends the appropriate lock clause for the dialect.

Example:

~~~java
import java.util.Optional;

import org.springframework.data.relational.repository.Lock;
import org.springframework.data.relational.core.sql.LockMode;
import org.springframework.data.repository.CrudRepository;

public interface InventoryRepository
        extends CrudRepository<Inventory, Long> {

    @Lock(LockMode.PESSIMISTIC_WRITE)
    Optional<Inventory> findBySku(String sku);
}
~~~

The method findBySku is a derived query because it does not declare SQL with @Query. Spring Data JDBC generates the SELECT from the mapping and adds a write lock according to the dialect.

You can use PESSIMISTIC_READ when a use case only needs to read a row and wants to prevent other transactions from modifying it while the current transaction holds the lock:

~~~java
@Lock(LockMode.PESSIMISTIC_READ)
Optional<Inventory> findForInspectionBySku(String sku);
~~~

If you need two different lock modes, declare separate method names or pick one mode per use case. Both methods above are derived queries; the property portion after By must still match domain properties.

### 3.1. Generated SQL depends on the dialect

Spring Data JDBC uses the dialect to express the lock mode. The Spring Data Relational documentation gives a MySQL example for PESSIMISTIC_READ with the syntax:

~~~sql
SELECT *
FROM user
WHERE lastname = ?
LOCK IN SHARE MODE;
~~~

This is an illustrative example from the dialect/documentation, not universal syntax across all databases. Another dialect may use FOR SHARE, FOR UPDATE, or its own syntax.

Do not assume every database produces the exact same SQL string or that PESSIMISTIC_READ is always lighter than PESSIMISTIC_WRITE. Inspect the generated SQL and your database documentation.

## 4. Important limitation: @Lock is ignored on string-based @Query

This is an easy pitfall when moving from Spring Data JPA or from derived queries to custom SQL queries.

The following example does not produce the expected lock:

~~~java
@Lock(LockMode.PESSIMISTIC_WRITE)
@Query("SELECT id, sku, available FROM inventory WHERE sku = :sku")
Optional<Inventory> findForUpdate(@Param("sku") String sku);
~~~

The method above is a string-based query because it uses @Query. According to current Spring Data Relational documentation, @Lock is not supported on string-based queries. The query method still executes the declared SQL, but the lock mode from @Lock is ignored; the framework logs a warning. The documentation also notes that future versions may turn this into an exception.

Therefore, do not rely on @Lock to protect a @Query SQL statement. If you want to use @Query, write the lock clause directly in the SQL:

~~~java
@Query("SELECT id, sku, available FROM inventory WHERE sku = :sku FOR UPDATE")
Optional<Inventory> findForUpdate(@Param("sku") String sku);
~~~

In this example, the lock comes from the database's FOR UPDATE clause. No @Lock annotation is needed; the SQL explicitly describes the locking behavior.

### 4.1. Distinguishing the mechanisms

| Declaration | How does Spring Data JDBC handle locking? |
| --- | --- |
| Derived method + @Lock | Supported; Spring Data generates a dialect-specific lock clause. |
| String-based @Query + @Lock | Lock metadata is ignored; logs a warning per current documentation. |
| @Query with FOR UPDATE in SQL | Database performs locking per SQL syntax and transaction. |
| JdbcTemplate with SQL containing FOR UPDATE | Database performs locking per SQL syntax and transaction. |

Do not apply this conclusion to Spring Data JPA. Spring Data JPA has different lock metadata mechanics; this lesson covers Spring Data JDBC.

## 5. Locking with SQL inside @Query

When explicit SQL is needed, use FOR UPDATE in the SELECT statement if your database supports it.

Repository:

~~~java
import java.util.Optional;

import org.springframework.data.jdbc.repository.query.Query;
import org.springframework.data.repository.CrudRepository;
import org.springframework.data.repository.query.Param;

public interface InventoryRepository
        extends CrudRepository<Inventory, Long> {

    @Query("SELECT id, sku, available FROM inventory WHERE sku = :sku FOR UPDATE")
    Optional<Inventory> findForUpdate(@Param("sku") String sku);
}
~~~

The service holds the transaction across reading and updating:

~~~java
import org.springframework.stereotype.Service;
import org.springframework.transaction.annotation.Transactional;

@Service
public class InventoryService {

    private final InventoryRepository inventory;

    public InventoryService(InventoryRepository inventory) {
        this.inventory = inventory;
    }

    @Transactional
    public void reserve(String sku, int quantity) {
        if (quantity <= 0) {
            throw new IllegalArgumentException("quantity must be positive");
        }

        Inventory item = inventory.findForUpdate(sku)
                .orElseThrow(() -> new IllegalArgumentException(
                        "Unknown SKU: " + sku));

        if (item.available() < quantity) {
            throw new IllegalStateException("Insufficient inventory");
        }

        inventory.save(item.withAvailable(item.available() - quantity));
    }
}
~~~

Execution flow:

1. Spring opens a transaction when the service method is invoked through the transaction proxy.
2. The SELECT with FOR UPDATE reads the row and asks the database to lock the matching row.
3. Another transaction wanting to modify or lock the same row may have to wait.
4. The service checks the quantity and saves the new state.
5. When the transaction commits or rolls back, the database releases the lock.

Methods like withAvailable and the Inventory mapping are domain examples; replace them with your actual model. The critical point is that the locking SELECT and the UPDATE must execute in the same transaction.

### 5.1. When using JdbcTemplate

When a query requires specialized SQL or does not fit a repository method, you can use NamedParameterJdbcTemplate:

~~~java
@Repository
public class InventoryLockDao {

    private final NamedParameterJdbcTemplate jdbc;

    public InventoryLockDao(NamedParameterJdbcTemplate jdbc) {
        this.jdbc = jdbc;
    }

    public InventoryRow findForUpdate(String sku) {
        String sql = """
                SELECT id, sku, available
                FROM inventory
                WHERE sku = :sku
                FOR UPDATE
                """;

        return jdbc.queryForObject(
                sql,
                Map.of("sku", sku),
                (rs, rowNum) -> new InventoryRow(
                        rs.getLong("id"),
                        rs.getString("sku"),
                        rs.getInt("available")
                )
        );
    }
}
~~~

Call the DAO from a `@Transactional` service sharing the same DataSource and transaction manager. Do not open an independent connection and close it immediately after SELECT if you need to keep the lock for a subsequent update.

## 6. SQL lock clauses differ by database

FOR UPDATE is common but not uniform across all database systems. For example:

### PostgreSQL

~~~sql
SELECT id, sku, available
FROM inventory
WHERE sku = :sku
FOR UPDATE;
~~~

PostgreSQL also supports variants such as FOR NO KEY UPDATE, FOR SHARE, and FOR KEY SHARE. They have different lock conflict levels; choose according to the types of modifications to prevent.

### MySQL with InnoDB

~~~sql
SELECT id, sku, available
FROM inventory
WHERE sku = :sku
FOR UPDATE;
~~~

MySQL 8 supports FOR SHARE for read locks. Older versions used LOCK IN SHARE MODE. Check your MySQL version, storage engine, and supported syntax.

### SQL Server

SQL Server typically expresses locking with table hints, such as:

~~~sql
SELECT id, sku, available
FROM inventory WITH (UPDLOCK, ROWLOCK)
WHERE sku = @sku;
~~~

UPDLOCK requests an update lock when reading; ROWLOCK is a granularity hint, not an absolute guarantee that the engine will always lock strictly row-by-row. Parameter and hint syntax depend on SQL Server.

### Oracle

Oracle supports SELECT ... FOR UPDATE, along with options such as NOWAIT and SKIP LOCKED depending on database version syntax.

These examples only illustrate how databases express locking. SQL must be written for your actual dialect; never copy a SQL statement verbatim from one database to another without testing.

## 7. NOWAIT and SKIP LOCKED

Some databases let you control what happens when a row is already locked by another transaction.

### 7.1. NOWAIT

NOWAIT instructs the query not to wait for an existing lock. If the lock cannot be acquired immediately, the database returns an error instead of waiting for the other transaction to finish.

PostgreSQL example:

~~~sql
SELECT id, status
FROM jobs
WHERE id = :id
FOR UPDATE NOWAIT;
~~~

Useful when the application wants to return "currently being processed" or retry later rather than blocking the request for a long time. Catch and classify lock conflict errors according to your database/driver.

### 7.2. SKIP LOCKED

SKIP LOCKED skips rows currently locked by other transactions. This is useful for worker queues where multiple workers pull different jobs:

~~~sql
SELECT id, payload
FROM jobs
WHERE status = 'READY'
ORDER BY id
FOR UPDATE SKIP LOCKED
LIMIT 20;
~~~

The ordering of LIMIT and lock clauses may vary by dialect; adjust the example for your specific database. One worker claims unlocked rows, updates their status, and commits. Other workers can pull other rows without waiting on rows held by the first worker.

SKIP LOCKED intentionally produces a partial view: locked rows do not appear in that query's result. Therefore, do not use it for screens requiring a full listing or normal existence checks. It fits queue/claim-work patterns equipped with retries and recovery for abandoned jobs.

## 8. Transactions govern lock lifetime

A SELECT with a lock clause generally holds locks only for the duration of the transaction. If the database runs in autocommit mode and the SELECT finishes with the statement, the lock can be released immediately after the statement; the service is left unprotected during the subsequent update step.

Therefore, wrap the entire critical section in a transaction:

~~~java
@Transactional
public void updateInventory(String sku, int quantity) {
    Inventory item = dao.findForUpdate(sku);
    // Check conditions.
    // Perform update.
}
~~~

Avoid splitting lock acquisition and updating into two separate service calls with separate transactions:

~~~text
Service A: open transaction
  SELECT ... FOR UPDATE
Service A: commit, lock is released

Service B: open another transaction
  UPDATE inventory
Service B: commit
~~~

Between the two transactions, another request can modify the row. The lock no longer protects the window between read and write.

### 8.1. Calling through the Spring proxy

Under normal proxy configuration, `@Transactional` applies only when calls pass through the Spring proxy. Self-invocation—where a method in the same object directly calls another annotated method—may not start a transaction as expected.

Place the transaction on a public application service method invoked from another bean, or configure transaction handling appropriately for your application architecture.

### 8.2. Do not hold locks during external service calls

Do not hold row locks while waiting on an HTTP API, sending an email, or processing a large file:

~~~java
@Transactional
public void approve(Long id) {
    Order order = orders.findForUpdate(id).orElseThrow();
    remoteBilling.capture(order); // Can take several seconds.
    orders.save(order.approve());
}
~~~

Long-running external calls keep connections, transactions, and locks open longer than necessary. This increases lock contention and the risk of timeouts/deadlocks. For multi-system workflows, consider updating state/outbox in a short transaction and handling side effects after commit.

## 9. Which rows does a SQL lock lock?

A `SELECT ... FOR UPDATE` statement locks the rows actually selected by the database under its semantics and execution plan. Do not assume locking an aggregate root automatically locks every row in the aggregate.

Example aggregate structure:

~~~text
PurchaseOrder (root row)
  |
  +-- purchase_order_lines (child rows)
  |
  +-- order_notes (child rows)
~~~

If a query selects only from purchase_orders, the database lock clause may lock only the root row. Child tables are not automatically locked just because Spring Data JDBC maps them into an aggregate.

If business logic must protect multiple rows:

- Lock the related rows with an appropriate statement.
- Use a consistent locking order across transactions.
- Consider updating/checking with constraints or a single atomic SQL statement.
- Redesign aggregate boundaries if multiple transactions frequently need to edit different parts concurrently.

Actual lock scope also depends on indexes, isolation level, and storage engine. For instance, InnoDB may take record locks, gap locks, or next-key locks in certain queries/range predicates. Never treat a row lock as a guarantee that strictly one physical row is locked.

## 10. Locking multiple rows and avoiding deadlocks

Deadlocks can occur when two transactions acquire locks in opposite orders:

~~~text
Transaction A                 Transaction B
-------------                 -------------
Lock row 1                    Lock row 2
Request lock row 2            Request lock row 1
Wait                          Wait
~~~

The database detects the wait cycle and aborts one transaction to break the deadlock. To reduce the risk:

1. Lock rows in the same order, e.g., ascending ID order.
2. Keep transactions short.
3. Lock only the required data scope.
4. Index filter conditions so scans do not lock overly broad ranges.
5. Do not perform network I/O while holding locks.
6. Monitor lock waits, deadlocks, and transaction durations in production.

Not all deadlocks can be eliminated completely. When retrying, retry only appropriate transient errors, bound the attempts, and use backoff. Use cases should be idempotent so a retry does not produce duplicate side effects.

## 11. When should you use pessimistic locking?

Pessimistic locking fits when:

- A transaction must read and then update one or a group of rows.
- Conflicts happen relatively often.
- Allowing two transactions to pass the check simultaneously causes a business error.
- Transactions can be kept short inside the critical section.

Examples: reserving inventory, transitioning the state of a claimed job, or updating a limited-quantity resource.

Do not apply pessimistic locking to every read query. Locking reduces concurrency and can force other requests to wait. For read-only display screens, locks are usually unnecessary; for low-contention updates, optimistic locking may fit better.

## 12. Alternatives to SELECT FOR UPDATE

Pessimistic locking is not the only solution to race conditions.

### 12.1. Optimistic locking with @Version

Spring Data JDBC supports optimistic locking using a numeric property on the aggregate root annotated with @Version:

~~~java
@Table("inventory")
public record Inventory(
        @Id Long id,
        String sku,
        int available,
        @Version Long version
) {
}
~~~

When saving the aggregate, Spring Data JDBC checks the current version in the database. If another transaction has already updated the row, saving can throw OptimisticLockingFailureException instead of silently overwriting.

Optimistic locking works well when conflicts are rare and the application can ask callers to reload data or retry the use case.

### 12.2. Conditional UPDATE

For decrementing stock, you may not need a separate read-and-lock step:

~~~sql
UPDATE inventory
SET available = available - :quantity
WHERE sku = :sku
  AND available >= :quantity;
~~~

The service checks the affected row count:

- 1: update succeeded.
- 0: SKU does not exist or stock is insufficient.

The database checks the condition and performs the update in a single statement. This is often a clean, efficient choice for a simple conditional transformation.

### 12.3. Comparing options

| Mechanism | How conflicts are detected/coordinated | Best suited when |
| --- | --- | --- |
| PESSIMISTIC_WRITE / FOR UPDATE | Locks before reading/modifying; other transactions may wait | Conflicts are relatively frequent and the critical section is short |
| PESSIMISTIC_READ / FOR SHARE | Read lock per database capability | Preventing changes during reads when the dialect has suitable semantics |
| @Version | Detects changed version on save | Conflicts are rare and reload/retry can be handled |
| Conditional UPDATE | Condition and mutation execute in one statement | Single atomic update with a clear predicate |
| Unique/check/foreign key constraints | Database rejects states violating constraints | Invariants expressible as schema constraints |

Mechanisms can be combined. For instance, a unique constraint prevents duplicate reservation keys; transactions and conditional updates protect stock decrements; @Version detects concurrent writes in other aggregate update flows.

## 13. Notes on @Lock and repository transactions

A lock is meaningful only while the database holds it. A repository method returning a loaded entity does not mean the lock persists after the transaction finishes.

For a derived query with @Lock, invoke it from a `@Transactional` service wrapping subsequent operations:

~~~java
@Service
public class AccountService {

    private final AccountRepository accounts;

    public AccountService(AccountRepository accounts) {
        this.accounts = accounts;
    }

    @Transactional
    public void debit(Long id, BigDecimal amount) {
        Account account = accounts.findForUpdate(id)
                .orElseThrow();

        if (account.balance().compareTo(amount) < 0) {
            throw new IllegalStateException("Insufficient balance");
        }

        accounts.save(account.debit(amount));
    }
}
~~~

Repository method:

~~~java
@Lock(LockMode.PESSIMISTIC_WRITE)
Optional<Account> findForUpdateById(Long id);
~~~

This method is a derived query if the parser recognizes the property path and there is no @Query string. If you need custom SQL, use @Query with a lock clause in the SQL instead of attaching @Lock.

## 14. Testing locking against a real database

Single-threaded unit tests cannot prove locks work when two transactions compete. Use integration tests running against a database and isolation level close to production.

### 14.1. Test scenario

1. Create an inventory row with available = 5.
2. Open transaction A and call SELECT ... FOR UPDATE.
3. Keep transaction A uncommitted.
4. From transaction B, attempt to update or lock the same row.
5. Verify transaction B waits, times out, or receives an error per database and configuration.
6. Commit or roll back transaction A.
7. Verify transaction B proceeds or handles the error as designed.

To test concurrency reliably, use two threads and two independent transactions. Do not wrap both flows in a single test transaction because they need to observe real contention.

### 14.2. Testing the @Lock with @Query limitation

Create a derived query with @Lock and a string-based @Query also annotated with @Lock. Inspect the logs and actual SQL:

- Derived query: dialect generates the lock clause.
- String-based query: warning indicates lock metadata is not applied per documented behavior.
- String-based query with FOR UPDATE: database receives SQL with an explicit lock clause.

Do not merely assert return values; verify that the second transaction actually blocks or behaves according to expected semantics.

### 14.3. Testing on the target database

H2 can be helpful for basic repository tests, but it does not guarantee identical locking semantics to PostgreSQL, MySQL, or SQL Server. Use Testcontainers or an equivalent integration environment when locking is critical to correctness.

## 15. Common mistakes

| Symptom | Possible cause | Fix |
| --- | --- | --- |
| Attached @Lock but @Query still does not block other transactions | @Lock is ignored on string-based queries | Add FOR UPDATE/appropriate lock clause to SQL or switch to a derived query. |
| Lock released immediately after SELECT | No transaction wrapping read and update; autocommit ends statement | Put `@Transactional` on the service holding the critical section. |
| SQL FOR UPDATE works on one database but fails on another | Lock clause is dialect-specific | Write SQL for the target database or use a derived query with @Lock. |
| Requests wait too long | Another transaction holds locks too long or query locks too many rows | Shorten transactions, narrow predicates, and configure appropriate timeouts. |
| Deadlock when updating multiple rows | Transactions lock rows in different orders | Lock in a consistent order and bound retries on deadlock errors. |
| PESSIMISTIC_READ blocks writers just like a write lock | Database/dialect does not distinguish read and write locks | Check database semantics; do not predict behavior solely from the mode name. |
| Locked root but child data still changed | SQL locks only selected rows; aggregate mapping does not auto-lock all child tables | Lock additional needed rows or redesign the operation/aggregate boundary. |
| SKIP LOCKED skips some jobs | Those rows are locked by another transaction | Intentional queue semantics; add retry/claim recovery. |
| Retries cause duplicate processing | Use case is not idempotent or retries already-succeeded side effects | Use idempotency keys, checkpoints, and bounded retries. |

## 16. Workflow for choosing a locking approach

When designing a contended operation, answer these questions in order:

1. **Is locking really needed?** Would a constraint or conditional UPDATE solve the problem?
2. **Are conflicts frequent or rare?** Frequent leans toward pessimistic locking; rare may use @Version.
3. **Is the query derived or custom SQL?** Derived queries can use @Lock; string-based @Query must put the lock clause in SQL.
4. **Which database is running?** Check syntax, isolation, lock modes, and driver behavior.
5. **How long does the transaction hold the lock?** Keep scope short and avoid external calls inside the critical section.
6. **Which rows are locked?** Identify root rows, child rows, indexes, and predicates.
7. **What if the lock cannot be acquired?** Wait, timeout, NOWAIT, SKIP LOCKED, or return a business error?
8. **Is a deadlock possible?** Use a consistent locking order.
9. **Has concurrency been tested on the target database?** Verify with two truly independent transactions.

## 17. Self-practice exercises

**Exercise 1 — Derived query with @Lock.** Create findForUpdateBySku with PESSIMISTIC_WRITE. Enable SQL logging and identify which lock clause the dialect adds.

**Exercise 2 — @Lock with @Query.** Add both @Lock and @Query to a method. Observe the warning and verify lock metadata is ignored in your version of Spring Data JDBC.

**Exercise 3 — SQL FOR UPDATE.** Remove @Lock and add FOR UPDATE to the @Query SQL. Use two transactions to test how the second transaction waits.

**Exercise 4 — Holding the transaction.** Put the locking query inside a `@Transactional` service, then try moving the annotation to a method that just returns the entity. Compare when the lock is released.

**Exercise 5 — NOWAIT and SKIP LOCKED.** On a database supporting them, try both options. Note the difference between immediate failure and skipping locked rows.

**Exercise 6 — Optimistic locking.** Add @Version to the aggregate and run two transactions that both read and save. Compare with FOR UPDATE.

**Exercise 7 — Conditional UPDATE.** Replace read-lock-update with `UPDATE ... WHERE available >= :quantity`. Check row counts when two concurrent requests order stock.

**Exercise 8 — Deadlock.** Create two transactions locking two rows in opposite orders. Observe the deadlock and fix it by locking in ascending ID order.

## 18. Key takeaways

In Spring Data JDBC, @Lock is supported for derived query methods. The two modes are PESSIMISTIC_READ and PESSIMISTIC_WRITE; the dialect determines the generated SQL lock clause, and some databases may map both modes to the same behavior.

@Lock currently does not apply to string-based queries declared with @Query; Spring Data ignores the lock metadata and logs a warning per current documentation. When custom SQL is required, put FOR UPDATE, FOR SHARE, or your database's lock syntax directly in the SQL. Keep both the locking SELECT and the update inside the same transaction, because locks are typically released when the transaction ends.

Pessimistic locking fits short critical sections with frequent conflicts. For rare conflicts, consider @Version; for simple conditional updates, a conditional UPDATE is often cleaner. Always test locking on the real target database, narrow lock scope, and design appropriate timeout/deadlock handling.

### References

- [Spring Data Relational – JDBC Locking](https://docs.spring.io/spring-data/relational/reference/jdbc/transactions.html)
- [Spring Data Relational – Lock Annotation API](https://docs.spring.io/spring-data/jdbc/docs/current/api/org/springframework/data/relational/repository/Lock.html)
- [Spring Data Relational – LockMode API](https://docs.spring.io/spring-data/data-jdbc/docs/current/api/org/springframework/data/relational/core/sql/LockMode.html)
- [PostgreSQL – Explicit Locking](https://www.postgresql.org/docs/current/explicit-locking.html)
- [MySQL – InnoDB Locking Reads](https://dev.mysql.com/doc/refman/8.4/en/innodb-locking-reads.html)

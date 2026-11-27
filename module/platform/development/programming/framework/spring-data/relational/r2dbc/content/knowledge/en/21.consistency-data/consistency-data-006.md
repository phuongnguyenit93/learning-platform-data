# Pessimistic Locking with SQL and Database Support Scope

Pessimistic locking is a way to coordinate concurrent transactions by locking the records that a transaction is about to read or modify. Another transaction wanting to update or acquire a conflicting lock on the same data must wait, immediately receive an error, or skip locked rows, depending on the database's syntax and policies.

In Spring Data R2DBC, pessimistic locking is typically requested using database-specific SQL such as `SELECT ... FOR UPDATE`. Spring Data sends the statement through the R2DBC driver; the database decides the lock type, lock scope, and release timing. For the lock to protect a read-then-write sequence, the locking query and subsequent operations must run inside the same reactive transaction.

## 1. What Problem Does Pessimistic Locking Solve?

Suppose an inventory has 1 item left. Two requests simultaneously try to order one item:

1. Transaction A reads the remaining quantity as 1.
2. Transaction B also reads the remaining quantity as 1.
3. A reduces the quantity to 0 and creates an order.
4. B also reduces the quantity based on the stale value and creates another order.

Without proper coordination, the system can oversell or overwrite changes.

Pessimistic locking allows transaction A to lock the inventory row before reading/checking. When transaction B requests a lock on the same row, it must wait for A to commit/roll back or act according to policies like NOWAIT/SKIP LOCKED. After A finishes, B reads the new state and decides whether it can proceed.

Conceptual flow:

~~~mermaid
sequenceDiagram
    participant A as Transaction A
    participant DB as Database
    participant B as Transaction B
    A->>DB: SELECT inventory FOR UPDATE
    DB-->>A: Row locked, quantity = 1
    B->>DB: SELECT same row FOR UPDATE
    Note over B,DB: B waits for conflicting lock
    A->>DB: UPDATE quantity = 0
    A->>DB: COMMIT
    DB-->>B: Lock granted
    B->>DB: Read current quantity = 0
    DB-->>B: Insufficient stock
    B->>DB: ROLLBACK
~~~

Pessimistic locking is useful when contention is likely, an operation needs to read and then decide a write based on current state, or business logic requires one transaction to hold exclusive control over rows during a short processing block.

## 2. SELECT FOR UPDATE

Many relational database systems support similar syntax:

~~~sql
SELECT id, available
FROM inventory
WHERE id = :id
FOR UPDATE;
~~~

`FOR UPDATE` asks the database to acquire a write lock on the selected rows. Other transactions attempting to update or acquire conflicting locks on the same rows will wait or behave according to other specified options.

Key points to remember:

- Locks apply to the rows actually queried and locked according to database rules.
- Locks are usually held until the transaction commits or rolls back.
- A plain SELECT query may still read data depending on MVCC and the database; pessimistic locking does not necessarily block all readers.
- If no rows match the condition, there are no corresponding data rows to lock.
- Syntax and lock scope differ across PostgreSQL, MySQL/InnoDB, SQL Server, Oracle, and other database systems.

Do not treat `FOR UPDATE` as strictly portable SQL syntax. Check documentation and run integration tests against the application's actual database.

## 3. Why Must It Run Inside a Transaction?

The common goal of pessimistic locking is holding lock ownership while the application reads, validates, and updates data. If the SELECT runs in autocommit mode, the implicit transaction may end immediately after the statement; the lock is then released before the application runs the subsequent UPDATE.

An example insufficient to protect the sequence of operations:

~~~java
// Calling only a locking query and ending transaction/autocommit.
return inventoryRepository.findForUpdate(id)
        .flatMap(inventory -> inventoryRepository.save(decrease(inventory)));
~~~

If both operations do not execute in the same transaction, the lock from SELECT may already be released before the UPDATE runs.

Wrap the entire pipeline in a reactive transaction:

~~~java
@Transactional
public Mono<Inventory> reserve(Long id, int quantity) {
    return inventoryRepository.findForUpdate(id)
            .switchIfEmpty(Mono.error(
                    new InventoryNotFoundException(id)
            ))
            .flatMap(inventory -> {
                if (inventory.available() < quantity) {
                    return Mono.error(
                            new InsufficientStockException(id)
                    );
                }

                Inventory changed = new Inventory(
                        inventory.id(),
                        inventory.available() - quantity
                );
                return inventoryRepository.save(changed);
            });
}
~~~

For methods returning `Mono` or `Flux`, Spring uses reactive transaction management when an appropriate `ReactiveTransactionManager` is present. The method must be invoked through a Spring proxy for `@Transactional` to take effect; self-invocation within the same bean may bypass the proxy.

You can use `TransactionalOperator` to define an explicit boundary:

~~~java
public Mono<Inventory> reserve(Long id, int quantity) {
    Mono<Inventory> work = inventoryRepository.findForUpdate(id)
            .switchIfEmpty(Mono.error(
                    new InventoryNotFoundException(id)
            ))
            .flatMap(inventory -> {
                if (inventory.available() < quantity) {
                    return Mono.error(
                            new InsufficientStockException(id)
                    );
                }

                return inventoryRepository.save(new Inventory(
                        inventory.id(),
                        inventory.available() - quantity
                ));
            });

    return transactionalOperator.transactional(work);
}
~~~

The transaction manager, repository, and DatabaseClient must use the same matching `ConnectionFactory`. Spring binds transaction resources into the Reactor Context so reactive operations within the same pipeline share the connection belonging to that transaction.

## 4. Declaring Locking Queries in Spring Data R2DBC

You can declare SQL directly in a repository using `@Query`:

~~~java
public interface InventoryRepository
        extends ReactiveCrudRepository<Inventory, Long> {

    @Query("""
            SELECT id, available
            FROM inventory
            WHERE id = :id
            FOR UPDATE
            """)
    Mono<Inventory> findForUpdate(@Param("id") Long id);
}
~~~

This example uses PostgreSQL syntax and applies to databases supporting `FOR UPDATE`. Spring Data maps the returned row to Inventory; the driver/database executes the locking clause of the SQL.

Spring Data R2DBC should not be viewed as an ORM that automatically locks entire entity graphs. The application must explicitly express which rows to lock in SQL and ensure the query runs within a transaction. Do not assume a JPA-style `@Lock` annotation translates automatically into compatible syntax across all R2DBC drivers and databases.

If SQL needs options like `NOWAIT`, `SKIP LOCKED`, or locking a specific alias in a JOIN, write explicit SQL and verify the database dialect.

## 5. Using DatabaseClient to Control Locking SQL

`DatabaseClient` is suitable when queries need dynamic parameters, JOINs, or specific locking syntax:

~~~java
public Mono<Inventory> lockInventory(Long id) {
    return databaseClient.sql("""
            SELECT id, available
            FROM inventory
            WHERE id = :id
            FOR UPDATE
            """)
            .bind("id", id)
            .map((row, metadata) -> new Inventory(
                    row.get("id", Long.class),
                    row.get("available", Integer.class)
            ))
            .one();
}
~~~

This method only constructs a publisher. The SQL executes when the publisher is subscribed to. For the lock to remain held during validation and writing, the caller must wrap both `lockInventory(...)` and the subsequent UPDATE in the same transaction.

Do not call `block()` to fetch the locked row and continue on another imperative flow; do not manually call `subscribe()` inside a service. Those practices can detach the query from the Reactor Context and managed transaction.

## 6. Example: Updating Inventory with Pessimistic Locking

Suppose the table is:

~~~sql
CREATE TABLE inventory (
    id BIGINT PRIMARY KEY,
    available INTEGER NOT NULL CHECK (available >= 0)
);
~~~

Locking repository:

~~~java
public interface InventoryRepository
        extends ReactiveCrudRepository<Inventory, Long> {

    @Query("""
            SELECT id, available
            FROM inventory
            WHERE id = :id
            FOR UPDATE
            """)
    Mono<Inventory> findForUpdate(@Param("id") Long id);
}
~~~

Service:

~~~java
@Transactional
public Mono<Inventory> reserve(Long id, int quantity) {
    if (quantity <= 0) {
        return Mono.error(
                new IllegalArgumentException("Quantity must be positive")
        );
    }

    return inventoryRepository.findForUpdate(id)
            .switchIfEmpty(Mono.error(
                    new InventoryNotFoundException(id)
            ))
            .flatMap(current -> {
                if (current.available() < quantity) {
                    return Mono.error(
                            new InsufficientStockException(id)
                    );
                }

                return inventoryRepository.save(new Inventory(
                        current.id(),
                        current.available() - quantity
                ));
            });
}
~~~

The transaction holds the lock from SELECT FOR UPDATE until the save operation and any remaining steps in the transaction finish. If stock is insufficient and the publisher emits an error, the transaction rolls back and the lock is released once rollback completes.

This example assumes the Inventory entity and repository mapping match the schema. If the entity has `@Version`, combine your understanding of optimistic locking; pessimistic locking and versioning can coexist, though they serve two different control mechanisms.

## 7. A Conditional UPDATE Can Replace Explicit Locking

Not every concurrency problem requires SELECT FOR UPDATE. For simple operations like deducting stock, a single conditional atomic UPDATE is often shorter:

~~~sql
UPDATE inventory
SET available = available - :quantity
WHERE id = :id
  AND available >= :quantity;
~~~

Repository:

~~~java
@Modifying
@Query("""
        UPDATE inventory
        SET available = available - :quantity
        WHERE id = :id
          AND available >= :quantity
        """)
Mono<Integer> reserveIfAvailable(
        @Param("id") Long id,
        @Param("quantity") int quantity
);
~~~

The database executes the statement as an atomic operation. If the row exists and has sufficient stock, one row is updated; otherwise, the affected row count is 0. Concurrent transactions targeting the same row are coordinated by the UPDATE statement's internal locking mechanism.

This approach works well when business conditions can be expressed in a single statement. Explicit pessimistic locking is more useful when you must read multiple fields, perform multiple checks, or update multiple tables based on the locked state.

Do not use SELECT FOR UPDATE just to feel "safer" when a conditional UPDATE already expresses the full rule. Fewer operations and shorter transactions usually scale better.

## 8. Lock Modes in PostgreSQL

PostgreSQL supports multiple row-locking modes:

| Syntax | General meaning |
| --- | --- |
| `FOR UPDATE` | Strong lock for updating/deleting rows |
| `FOR NO KEY UPDATE` | Lighter update lock when referenced key columns are not modified |
| `FOR SHARE` | Shared lock, conflicting with certain write/lock operations |
| `FOR KEY SHARE` | Protects key columns against modification/deletion per PostgreSQL locking rules |

Typically, `FOR UPDATE` is the clearest choice when a transaction is about to modify the read rows. Lighter modes can improve concurrency, but require understanding PostgreSQL's lock conflict matrix.

You can restrict which table is locked in a JOIN query using `OF`:

~~~sql
SELECT i.id, i.available, p.name
FROM inventory i
JOIN product p ON p.id = i.product_id
WHERE i.id = :id
FOR UPDATE OF i;
~~~

In PostgreSQL, `OF i` specifies locking rows of the inventory alias. Omitting `OF` may cause rows from other eligible tables in the query to be locked according to statement rules. Lock only the rows you need to minimize contention.

## 9. NOWAIT and SKIP LOCKED in PostgreSQL

### NOWAIT

`NOWAIT` tells the database not to wait if the row to lock already has a conflicting lock held by another transaction:

~~~sql
SELECT id, available
FROM inventory
WHERE id = :id
FOR UPDATE NOWAIT;
~~~

If the lock cannot be acquired immediately, the database returns a lock-busy error instead of waiting. The application can translate the error into a "currently being processed" response or retry with backoff if business rules allow.

### SKIP LOCKED

`SKIP LOCKED` skips rows that currently hold conflicting locks:

~~~sql
SELECT id, status
FROM job
WHERE status = 'READY'
ORDER BY created_at, id
LIMIT 10
FOR UPDATE SKIP LOCKED;
~~~

This is a common pattern for multiple workers claiming tasks from a database queue. The second worker does not wait on rows locked by the first worker; it picks up other READY rows.

`SKIP LOCKED` produces an incomplete view of the data: locked rows are skipped, not absent. Do not use it for screens requiring a complete list or consistent reporting queries.

When using it to claim work, a worker must update the locked rows to RUNNING or assign an owner before committing. If it only runs SELECT and commits, the lock is released and another worker can pick up the same work again.

## 10. Worker Queue Claim Pattern with SKIP LOCKED

PostgreSQL example:

~~~sql
SELECT id, payload
FROM job
WHERE status = 'READY'
ORDER BY created_at, id
LIMIT 10
FOR UPDATE SKIP LOCKED;
~~~

Within the same transaction, update the claimed rows:

~~~sql
UPDATE job
SET status = 'RUNNING',
    claimed_at = CURRENT_TIMESTAMP,
    worker_id = :workerId
WHERE id = :id;
~~~

The service can chain the operations:

~~~java
@Transactional
public Flux<Job> claimJobs(String workerId) {
    return jobRepository.findReadyForUpdateSkipLocked()
            .flatMap(job -> jobRepository.markRunning(
                    job.id(),
                    workerId
            ).thenReturn(job));
}
~~~

This snippet illustrates requiring both repository queries to participate in one reactive transaction. In practice, return the updated data or include an update-verification step, and design batch claiming with a bounded size.

Once the transaction commits, rows have transitioned to RUNNING so other workers no longer pick them under the READY condition. A lease/timeout or recovery mechanism is still required for jobs left unfinished by crashed workers; database locks do not replace long-running job lifecycle management.

## 11. Support and Syntax Across Different Database Systems

Pessimistic locking does not have a single SQL syntax supported identically across all databases. The table below summarizes common patterns; versions, storage engines, and isolation levels can influence behavior.

| Database | Common syntax | Notes |
| --- | --- | --- |
| PostgreSQL | `SELECT ... FOR UPDATE`, `NOWAIT`, `SKIP LOCKED` | Row locking with MVCC; supports lock modes and `FOR UPDATE OF alias` |
| MySQL / InnoDB | `SELECT ... FOR UPDATE`, `FOR SHARE` | Locking depends on indexes, isolation, and next-key/gap locking |
| SQL Server | `WITH (UPDLOCK, ...)` | Uses table hints; does not use PostgreSQL FOR UPDATE syntax |
| Oracle | `SELECT ... FOR UPDATE`, `NOWAIT`, `WAIT n`, `SKIP LOCKED` | Supports lock-wait options per Oracle syntax |
| SQLite | No standard row-level SELECT FOR UPDATE | Locking operates differently at database/file and transaction levels |

The R2DBC driver does not make a database support syntax that the server lacks. The driver forwards SQL and translates results/errors across the SPI; locking syntax must match the running database engine and version.

## 12. MySQL and InnoDB

With InnoDB, you can lock rows using:

~~~sql
SELECT id, available
FROM inventory
WHERE id = ?
FOR UPDATE;
~~~

Another transaction wanting to update or acquire a conflicting lock on the same row will have to wait. The lock is held until the transaction finishes.

MySQL 8.0 supports common options:

- `NOWAIT`: fails immediately if the lock cannot be acquired right away.
- `SKIP LOCKED`: skips locked rows, suited for worker queues.
- `FOR SHARE`: acquires a shared lock; older versions may use `LOCK IN SHARE MODE`.

InnoDB can use record locks, gap locks, or next-key locks depending on the query, indexes, and isolation level. For range conditions at `REPEATABLE READ`, the lock scope may cover gaps between index records to prevent phantom inserts per InnoDB semantics.

A lookup by unique primary key typically locks a narrower scope than a range query missing an index. Therefore, indexes affect not only speed, but also how many rows/ranges get locked and overall concurrency.

Verify the actual engine is InnoDB. Other MySQL storage engines may exhibit different transaction and locking behavior.

## 13. SQL Server

SQL Server uses table hints to request a locking strategy:

~~~sql
SELECT id, available
FROM inventory WITH (UPDLOCK, ROWLOCK)
WHERE id = @id;
~~~

- `UPDLOCK` requests taking update locks on read and holding them until the transaction ends per transaction rules.
- `ROWLOCK` hints at using row-level locks, though SQL Server does not guarantee it will always maintain the exact requested granularity.
- `HOLDLOCK` has semantics equivalent to SERIALIZABLE for that table reference within the statement/transaction scope per SQL Server documentation.
- `READPAST` can skip certain locked rows, often used for queue patterns; understand its limitations with isolation, lock types, and settings such as READ_COMMITTED_SNAPSHOT.

For example, you cannot literally reuse PostgreSQL's `FOR UPDATE` on SQL Server. Use the appropriate hint syntax and test under the application's isolation level.

## 14. Oracle

Oracle supports:

~~~sql
SELECT id, available
FROM inventory
WHERE id = :id
FOR UPDATE;
~~~

Common lock-wait options:

- `NOWAIT`: do not wait for the lock; return an error if rows are locked.
- `WAIT n`: wait at most the specified number of seconds.
- `SKIP LOCKED`: skip rows that are currently locked.

Example:

~~~sql
SELECT id, payload
FROM job
WHERE status = 'READY'
FOR UPDATE SKIP LOCKED;
~~~

Oracle also has specific locking rules when using JOINs, views, pagination, and subqueries. Check the documentation for the exact Oracle version before applying SQL patterns in production.

## 15. Lock Scope: Row, Page, Table, and Range Locks

The name `FOR UPDATE` often suggests row locks, but actual scope depends on the database and execution plan:

- **Row/record lock:** locks the queried rows.
- **Page lock:** locks a data page or index page.
- **Table lock:** locks the entire table or table-level structures during certain operations.
- **Gap/next-key lock:** locks gaps in an index to restrict inserts into that range.
- **Predicate/range protection:** prevents other transactions from creating rows that change a predicate's result set per isolation semantics.

PostgreSQL uses MVCC and row-level locks for locked rows; it still acquires table-level locks accompanying statements. InnoDB uses gap/next-key locking in certain cases. SQL Server can escalate locks (lock escalation) from row/page to table locks when needed.

Consequently, do not assume a statement locks only a single row if the WHERE condition can match multiple rows or uses a range. Inspect execution plans, indexes, and database documentation.

## 16. Indexes Affect Lock Scope and Lock Hold Time

Example:

~~~sql
SELECT id, status
FROM job
WHERE status = 'READY'
ORDER BY created_at
FOR UPDATE;
~~~

Without a suitable index, the database may have to scan many rows to find READY rows. Depending on the engine, this can increase work, widen lock scope, or prolong lock hold times.

A potentially suitable index:

~~~sql
CREATE INDEX idx_job_status_created_id
    ON job(status, created_at, id);
~~~

Indexes must be chosen based on execution plans and actual workloads. Indexes speed up finding rows, while also adding overhead to inserts, updates, deletes, and storage.

## 17. Isolation Levels and Pessimistic Locking

Isolation levels and explicit locks are related but not identical:

- Isolation levels define which read/write anomalies a database allows between transactions.
- Explicit pessimistic locks request specific locks on rows or resources.
- Databases may acquire internal locks even when the application does not write `FOR UPDATE`, such as when running UPDATE.
- A higher isolation level does not mean every read row is locked in the way the application intends.

In PostgreSQL, `READ COMMITTED` is typically the default; `SELECT FOR UPDATE` locks rows, and if it has to wait for another transaction updating a row, it proceeds against the appropriate new version once that transaction completes per PostgreSQL semantics.

In InnoDB, `REPEATABLE READ` is typically the default; range queries may acquire next-key locks. Behavior changes under `READ COMMITTED` or when queries traverse different indexes.

Choose isolation according to overall consistency requirements, and use explicit locks when a specific workflow needs to protect rows. Do not use SERIALIZABLE isolation as a mechanical replacement for every locking query.

## 18. NOWAIT, Timeouts, and Error Handling

When another transaction holds a lock, a lock-acquiring request may wait. Waiting too long consumes connections, stalls requests, and can grow queues.

Options:

- Use `NOWAIT` when you want to fail immediately if the row is busy.
- Use `WAIT n` or lock timeouts if supported by the database.
- Configure an appropriate lock wait timeout at the session, transaction, or database level if needed.
- Bound overall request duration and transaction duration.
- Log lock waits, timeouts, and deadlocks to identify hot spots.

Lock timeout or deadlock errors are typically propagated through the publisher as driver/database errors. The application can translate them into retryable business errors, but should retry only when the operation is safe and bounded.

Do not retry immediately without limits. Many requests retrying simultaneously can worsen contention. Use backoff, jitter, and an overall request deadline.

## 19. Deadlocks and Lock Acquisition Ordering

Deadlocks occur when transactions hold locks that each other need, forming a wait cycle.

Example:

1. A locks row 1.
2. B locks row 2.
3. A waits for row 2.
4. B waits for row 1.

The database detects the cycle and picks one transaction as the deadlock victim to roll back. The application must handle the error and may retry the aborted transaction if business rules permit.

One way to reduce deadlocks is acquiring locks in the same order across all flows:

~~~sql
SELECT id, balance
FROM account
WHERE id IN (:firstId, :secondId)
ORDER BY id
FOR UPDATE;
~~~

This example locks two accounts in ascending ID order. When all transactions follow the same order, the chance of forming wait cycles drops. Collection parameter binding syntax and locking behavior with IN must be verified for your driver/database; for dynamic lists, you can query by each sorted ID sequentially within the same transaction.

Other practices:

- Keep transactions short.
- Lock only the rows genuinely needed.
- Create appropriate indexes to avoid wide scans.
- Do not call external services while holding locks.
- Do not perform long-running interactive user steps inside a transaction.

## 20. Do Not Hold Locks While Calling External Systems

An anti-pattern is:

~~~java
return transactionalOperator.transactional(
        inventoryRepository.findForUpdate(id)
                .flatMap(inventory ->
                        paymentClient.authorize(order)
                                .then(inventoryRepository.save(
                                        decrease(inventory)
                                ))
                )
);
~~~

The transaction holds the lock while waiting on the payment network call. If the external service is slow, locks and connections are held for a long time; if the payment succeeds but the database rolls back, the two systems can fall out of sync.

A better design is usually:

1. Perform short database operations inside the transaction.
2. Write status or an outbox event.
3. Commit the transaction to release locks.
4. Call the external system after commit through an appropriate process.
5. Use idempotency and compensating workflows when needed.

If business logic requires a distributed workflow, consider a saga or transactional outbox rather than holding row locks throughout remote communication.

## 21. Pessimistic Locking vs. Optimistic Locking

| Criterion | Pessimistic locking | Optimistic locking |
| --- | --- | --- |
| Mechanism | Lock resources before modifying | Check that data has not changed at write time |
| Common tools | `SELECT FOR UPDATE`, locking hints | Version column and version condition |
| On conflict | Other transaction waits, skips, or errors | Update fails when version no longer matches |
| Cost | Holds locks and connections during transaction | May require handling/retrying conflicts |
| Best suited for | Frequent contention, read-modify requires exclusivity | Rare conflicts, avoid holding locks during reads |

Optimistic locking example:

~~~sql
UPDATE inventory
SET available = :newAvailable,
    version = version + 1
WHERE id = :id
  AND version = :expectedVersion;
~~~

If the updated row count is 0, another transaction may have modified the row. This approach does not hold a lock from initial read until write, while still relying on the atomicity of UPDATE.

You can combine both mechanisms when business logic calls for it, but avoid unnecessary complexity. Pick a strategy based on contention levels, transaction length, and conflict-handling requirements.

## 22. Testing Pessimistic Locking with Two Transactions

Pure unit tests do not prove a real database holds locks properly. You need integration tests against the target database and driver:

1. Create a shared data row.
2. Transaction A starts and executes SELECT FOR UPDATE.
3. Keep transaction A open before committing.
4. Transaction B attempts to lock the same row.
5. Verify B waits, receives a NOWAIT error, or skips the row with SKIP LOCKED depending on the scenario.
6. Let A commit/roll back.
7. Verify B proceeds or receives the expected state.

You can use `StepVerifier`, two independent publishers, and coordination signals in the test. Avoid flaky long sleeps; prefer latches/barriers or deterministic test synchronization with explicit deadlines.

Scenarios worth testing:

- Locking a row by unique ID.
- Two transactions updating the same row simultaneously.
- NOWAIT when the row is locked.
- SKIP LOCKED when multiple workers claim jobs.
- Rollback releasing locks.
- Deadlocks or lock timeouts.
- Cancellation behavior.
- Lock scope of JOINs or range queries if business logic relies on them.

Run tests on the same engine and version as production. Embedded databases may not support the same locking syntax or semantics.

## 23. Common Pitfalls

1. **Using SELECT FOR UPDATE outside a transaction.** The lock may be released immediately after SELECT/autocommit.
2. **Locking during read but updating in a different transaction.** Locks do not protect the operation sequence unless both share the same transaction.
3. **Assuming every SELECT is blocked.** MVCC and lock modes determine which readers are affected.
4. **Using PostgreSQL syntax on SQL Server or SQLite.** Pessimistic locking is not strictly portable.
5. **Assuming the R2DBC driver creates locks itself.** SQL and the database determine locking; the driver only forwards commands and results.
6. **Not checking for the same ConnectionFactory.** Repositories might not participate in the transaction managed by the operator.
7. **Holding locks during HTTP calls.** Transactions stretch out, connections stay pinned, and deadlocks become more likely.
8. **Locking too many rows.** Missing indexes or overly broad conditions increase contention.
9. **Ignoring lock timeouts and deadlocks.** Requests may stall or fail unhandled.
10. **Using SKIP LOCKED for lists requiring completeness.** Results may omit currently locked rows.
11. **Relying solely on Java checks to prevent duplicate writes.** Constraints and transactions are needed to protect against concurrency.
12. **Using pessimistic locks for a simple UPDATE.** A conditional UPDATE statement may already be sufficient and more efficient.

## Quick Selection Rules

- Use `SELECT ... FOR UPDATE` when you must read and then validate/update the same row inside one transaction.
- Use reactive `@Transactional` or `TransactionalOperator` to hold locks across the entire pipeline.
- Use `NOWAIT` when you do not want to wait on busy rows and can handle errors immediately.
- Use `SKIP LOCKED` for worker queues or shared job claiming, not for queries needing complete data.
- Use `DatabaseClient` or `@Query` to write dialect-accurate locking syntax.
- Verify database, version, engine, isolation level, indexes, and driver.
- Lock as few rows as possible, acquire locks in a consistent order, and keep transactions short.
- Use a single conditional UPDATE statement if the business rule can be expressed atomically in SQL.
- Test with multiple concurrent transactions against the target database.

SQL-based pessimistic locking lets a transaction retain exclusive control over rows needing protection, but effectiveness depends on transaction boundaries and how the database implements locks. In Spring Data R2DBC, write explicit locking queries, wrap the entire read-modify sequence in a reactive transaction, and share the same ConnectionFactory. Syntax such as FOR UPDATE, NOWAIT, and SKIP LOCKED varies across database systems; lock scope also depends on indexes, isolation levels, and execution plans. Keep transactions short, avoid remote calls while holding locks, and test on a real database to manage concurrency safely.

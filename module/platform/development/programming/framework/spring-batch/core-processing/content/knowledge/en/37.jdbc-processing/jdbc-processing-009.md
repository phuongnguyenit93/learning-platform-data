# Isolation Levels and Repeatable Read

In Spring Batch, a chunk-oriented Step typically reads, processes, and writes database data inside repeated transactions. When multiple Jobs or applications access the same table, data can change between the moment the reader queries and the moment the processor/writer finishes. The transaction isolation level determines the degree to which one transaction observes changes made by other transactions.

`REPEATABLE_READ` is an isolation level in JDBC and Spring. Its goal is to ensure that if a transaction re-reads the same row, it does not see that row's value changed by another transaction before the current transaction ends. However, exact behavior regarding phantom rows and snapshots depends on the database. Furthermore, in Spring Batch, transactions are usually created per chunk; therefore, `REPEATABLE_READ` on chunks does not inherently create a consistent snapshot for the entire Job.

To choose the right isolation level, you must understand which anomalies need to be prevented, where the Step's transaction boundaries lie, whether the reader shares a connection with the chunk transaction, and whether the database enforces isolation via locks or MVCC.

## 1. What Is Transaction Isolation?

Transaction isolation describes how much concurrent transactions can observe each other's changes. When multiple transactions read and write the same data, the isolation level decides whether a transaction can see uncommitted data, data modified between two reads, or newly appearing rows matching the same query predicate.

Suppose two transactions operate on an account concurrently:

```text
Transaction A                         Transaction B
-------------                         -------------
BEGIN                                 BEGIN
SELECT balance -> 1,000
                                      UPDATE balance = 800
                                      COMMIT
SELECT balance -> ?
COMMIT
```

What value A's second `SELECT` sees depends on the isolation level and how the database implements it. Isolation does not serialize all transactions completely in every case; it establishes guarantees over what data each transaction is allowed to observe.

In Spring Batch, this matters when the reader fetches data from the database, the processor checks or computes based on read data, and the writer updates tables within the same or different transactions.

## 2. Isolation Levels in JDBC

JDBC defines isolation constants on `Connection`:

| JDBC constant | Spring constant | General meaning |
|---|---|---|
| `TRANSACTION_READ_UNCOMMITTED` | `ISOLATION_READ_UNCOMMITTED` | May read uncommitted changes from other transactions |
| `TRANSACTION_READ_COMMITTED` | `ISOLATION_READ_COMMITTED` | Reads only committed data; two reads can see different values |
| `TRANSACTION_REPEATABLE_READ` | `ISOLATION_REPEATABLE_READ` | Stronger guarantee when re-reading the same row; phantom behavior depends on database |
| `TRANSACTION_SERIALIZABLE` | `ISOLATION_SERIALIZABLE` | Strongest isolation under serializable transaction semantics; may increase contention or transaction aborts |
| — | `ISOLATION_DEFAULT` | Uses the database/driver default isolation |

Not every database supports every level identically. Some databases map JDBC isolation constants to distinct internal mechanisms, or do not support `READ_UNCOMMITTED` independently. Read your database documentation and test with the real driver.

## 3. Dirty Reads

A dirty read happens when transaction A reads data modified by transaction B before B commits. If B rolls back, A has read a value that never became committed data.

```text
Transaction A                         Transaction B
-------------                         -------------
BEGIN                                 BEGIN
                                      UPDATE account
                                      SET balance = 0
SELECT balance -> 0
                                      ROLLBACK
```

If A uses the value `0` to build a report or decide other writes, the outcome may be wrong because B rolled back.

`READ_COMMITTED` and higher prevent dirty reads under the standard model. `READ_UNCOMMITTED` permits this anomaly, though some databases still never expose dirty reads due to their storage/MVCC engine.

For financial, inventory, or critical business state, never choose `READ_UNCOMMITTED` just for throughput unless you have proven uncommitted data is acceptable.

## 4. Non-Repeatable Reads

A non-repeatable read occurs when a transaction reads the same row twice and gets different values because another transaction updated and committed that row between the two reads.

```text
Transaction A                         Transaction B
-------------                         -------------
BEGIN                                 BEGIN
SELECT price -> 100
                                      UPDATE product
                                      SET price = 120
                                      COMMIT
SELECT price -> 120
COMMIT
```

`READ_COMMITTED` permits this scenario: each `SELECT` statement can see the latest committed snapshot/version as of the moment that statement runs.

`REPEATABLE_READ` is designed to prevent re-reading the same row from seeing values modified by another transaction while the current transaction remains open. Databases may implement this via row locks, snapshot/MVCC, or a combination of mechanisms.

## 5. Phantom Reads

A phantom read occurs when a transaction re-runs a predicate query and sees added or missing rows satisfying that condition because another transaction inserted/deleted/updated rows affecting the result set.

```text
Transaction A                         Transaction B
-------------                         -------------
BEGIN                                 BEGIN
SELECT * FROM orders
WHERE status = 'NEW' -> 10 rows
                                      INSERT new order
                                      SET status = 'NEW'
                                      COMMIT
SELECT * FROM orders
WHERE status = 'NEW' -> 11 rows
COMMIT
```

In the standard SQL model, `REPEATABLE_READ` prevents non-repeatable reads yet can still permit phantom reads. `SERIALIZABLE` aims to prevent these anomalies by making outcomes equivalent to some serial execution order.

However, do not apply phantom conclusions mechanically to every database. For example, PostgreSQL uses snapshot isolation for `REPEATABLE READ`, so plain `SELECT`s within the same transaction see the same snapshot and do not see phantoms as shown above; yet snapshot isolation can still allow certain serialization anomalies. MySQL InnoDB has its own rules distinguishing consistent reads from locking reads, along with next-key/gap locks in certain cases. Check the exact semantics of the database you run.

## 6. What Does Repeatable Read Guarantee?

At a high level, `REPEATABLE_READ` ensures a transaction re-reading the same row receives the same data it observed earlier, regardless of another transaction committing updates to that row after the first read.

Example:

```text
Transaction A (REPEATABLE_READ)       Transaction B
--------------------------------       -------------
BEGIN
SELECT balance -> 1,000
                                       BEGIN
                                       UPDATE balance = 800
                                       COMMIT
SELECT balance -> 1,000
COMMIT
```

On snapshot/MVCC databases, A continues seeing the row version at A's snapshot. On locking databases, B may have to wait or A holds locks depending on the statements and implementation.

Key takeaway: `REPEATABLE_READ` applies within the scope of a single transaction. Once the transaction ends, that guarantee ends. A new transaction can see newly committed values.

## 7. Repeatable Read Does Not Equal Serializable

`REPEATABLE_READ` and `SERIALIZABLE` are not interchangeable in all scenarios.

| Criterion | `REPEATABLE_READ` | `SERIALIZABLE` |
|---|---|---|
| Dirty reads | Prevented | Prevented |
| Non-repeatable reads | Prevented | Prevented |
| Phantom reads | Permitted by standard; database may offer stronger guarantees | Prevented per serializable semantics |
| Concurrent throughput | Usually higher than serializable | May be lower due to locks or transaction aborts |
| Deadlock/serialization failure risk | Possible depending on DB and queries | Usually requires retry handling on conflicts |
| Best suited for | Stable row re-reads within a transaction | Business rules requiring outcomes equivalent to serial execution |

Snapshot isolation in some databases prevents more anomalies than the minimal SQL definition of repeatable read, yet it is not automatically equivalent to serializable. For instance, two transactions can both read a dataset and then update two distinct rows based on the same condition, leading to write skew if the database does not detect serialization conflicts.

If a business rule relies on a multi-row invariant, choosing `REPEATABLE_READ` alone may not suffice. You may need database constraints, explicit locking, or `SERIALIZABLE`.

## 8. Isolation Levels in a Chunk-Oriented Step

Spring Batch usually creates one transaction per chunk. With a chunk size of 100, one transaction wraps a group of items being read, processed, written, and committed.

```text
Step starts
   |
   +--> Transaction chunk 1
   |       read/process/write 1..100
   |       update stream state
   |       commit
   |
   +--> Transaction chunk 2
   |       read/process/write 101..200
   |       update stream state
   |       commit
   |
   +--> Transaction chunk 3
           read/process/write 201..300
           update stream state
           commit
```

The isolation level is configured for the transactions created by the Step. When `REPEATABLE_READ` is used, repeatable-read guarantees hold inside each corresponding chunk transaction.

This does not mean the entire Step holds a single snapshot from the first item to the last. After chunk 1 commits, chunk 2 begins a new transaction and can see data changed after chunk 1 committed.

For example, suppose the same table is queried in chunk 1 and chunk 5, and another application updates the table between those chunks. `REPEATABLE_READ` on chunk 1 does not force chunk 5 to keep seeing chunk 1's snapshot.

## 9. Configuring Isolation on a Step

You can set the isolation level on a chunk Step's transaction attribute. Example:

```java
@Bean
public Step reconcileOrdersStep(
        JobRepository jobRepository,
        PlatformTransactionManager transactionManager,
        ItemReader<Order> orderReader,
        ItemProcessor<Order, ReconciledOrder> processor,
        ItemWriter<ReconciledOrder> writer) {

    DefaultTransactionAttribute transactionAttribute =
            new DefaultTransactionAttribute();
    transactionAttribute.setIsolationLevel(
            TransactionDefinition.ISOLATION_REPEATABLE_READ);
    transactionAttribute.setTimeout(120);

    return new StepBuilder("reconcileOrdersStep", jobRepository)
            .<Order, ReconciledOrder>chunk(100, transactionManager)
            .transactionAttribute(transactionAttribute)
            .reader(orderReader)
            .processor(processor)
            .writer(writer)
            .build();
}
```

Key imports:

```java
import org.springframework.transaction.TransactionDefinition;
import org.springframework.transaction.interceptor.DefaultTransactionAttribute;
import org.springframework.transaction.PlatformTransactionManager;
```

`transactionAttribute(...)` configures the chunk's transaction properties. `ISOLATION_REPEATABLE_READ` is the Spring constant matching JDBC `Connection.TRANSACTION_REPEATABLE_READ`.

If no isolation is specified, Spring usually uses `ISOLATION_DEFAULT`, meaning the database/connection default. That is generally a reasonable starting point; raise isolation only when a specific anomaly must be prevented and its impact has been measured.

## 10. Distinguishing Step Isolation from @Transactional

You may see annotations such as:

```java
@Transactional(isolation = Isolation.REPEATABLE_READ)
public void processBatch() {
    // database operations
}
```

This annotation takes effect when Spring opens a new transaction for a proxy-managed method. In a chunk Step, a transaction has usually already been opened by Spring Batch via `PlatformTransactionManager` before invoking the reader/processor/writer.

If a writer/processor method uses propagation `REQUIRED`, it typically joins the existing transaction. Declaring isolation on that method cannot upgrade the isolation of an already-started transaction. Therefore, to set isolation for chunk transactions, configuring the transaction attribute on the Step is far clearer.

If `REQUIRES_NEW` is used, the method creates an independent transaction. It then no longer shares the same atomic boundary as the chunk transaction; the inner method's commit can persist even if the outer chunk rolls back. Never use this propagation merely to try changing isolation without evaluating checkpoint and consistency consequences.

With multiple transaction managers or multiple `DataSource`s, each transaction manager manages its own connections/resources. Isolation on the Step's transaction manager does not automatically apply to another database.

## 11. DataSourceTransactionManager and JDBC Connections

A JDBC transaction manager manages connections bound to transactions. When starting a transaction, it borrows a connection from the `DataSource`, applies read-only/isolation/auto-commit settings as needed, and binds the connection to the transaction context so JDBC operations participating in that transaction share the same connection.

When a Step requests `REPEATABLE_READ`, the transaction manager attempts to set that isolation on the connection before the transaction executes SQL. When the transaction finishes, the connection returns to the pool and its properties must be restored by the transaction manager or connection pool.

Important conditions:

- Reader/writer must use a `DataSource` participating in the same transaction manager to share the transaction.
- JDBC access must acquire connections through Spring-aware mechanisms, such as `JdbcTemplate` or `DataSourceUtils`.
- Calling `dataSource.getConnection()` directly in code may obtain a separate connection outside the active transaction.
- The database/driver must support the requested isolation level.
- The connection pool must not leak stale isolation state across borrowed connections.

Do not change isolation on a connection after a transaction has already begun. Databases may reject the change or fail to apply it as expected.

## 12. Does the Reader Use the Same Transaction Connection?

Not every database reader reads through the same connection the chunk writer uses. This is a crucial detail when reasoning about isolation.

| Component | Typical access mechanism | What to verify |
|---|---|---|
| `JdbcTemplate` in processor/service | Can join current transaction if using same `DataSource` | Uses matching transaction manager/`DataSource` |
| `JdbcBatchItemWriter` | Usually joins Step transaction when sharing `DataSource` | Proper transaction manager configuration |
| `JdbcPagingItemReader` | Executes page queries through JDBC infrastructure | Check connection and transaction participation for your version/config |
| Default `JdbcCursorItemReader` | Opens cursor on a separate connection to keep cursor open across Step | Cursor connection isolation is not automatically set by chunk transaction attribute |
| Custom reader using `dataSource.getConnection()` | Usually opens a separate connection if not using Spring transaction-aware access | Must enlist in transaction or configure isolation separately |

A `SELECT` statement is protected only by the isolation level of the transaction on the connection executing that `SELECT`. Configuring `REPEATABLE_READ` on chunks cannot protect a query running on an independent connection in a separate transaction.

## 13. Special Note on JdbcCursorItemReader

`JdbcCursorItemReader` usually opens a separate connection to keep the `ResultSet` cursor open while chunk transactions commit one after another. Consequently, the chunk Step's transaction attribute does not necessarily set isolation for the connection holding the cursor.

The cursor connection has its own isolation and transaction behavior determined by reader config, driver, and database. If you need a consistent snapshot across the entire cursor, verify the isolation of that specific connection and how the database retains snapshots while a cursor remains open.

`useSharedExtendedConnection` lets certain setups share an extended connection with Step transactions via `ExtendedConnectionDataSourceProxy` and requires a driver supporting holdable cursors across commits. This is an advanced configuration; not every driver/database supports it.

Do not enable shared extended connections just to "turn on repeatable read." First determine which connection the cursor uses, when the database snapshot is taken, how the cursor survives commits, and how write transactions affect the cursor.

## 14. JdbcPagingItemReader and Repeatable Read

`JdbcPagingItemReader` splits reading into multiple page queries. If page queries run under different chunk transactions, each transaction can see a different snapshot. Newly inserted rows or modified older rows between pages can alter the dataset seen by the reader, depending on isolation and sort keys.

If all page queries ran inside one long-lived `REPEATABLE_READ` transaction, the snapshot could be more consistent, but that would keep transactions and snapshots open for a long time, increasing database pressure. In a standard chunk Step, transactions finish after each chunk; never assume every page in the Step belongs to a single transaction.

For stable paging:

- Use a deterministic, unique sort key.
- Fix the data scope with a batch ID, business date, or high-water mark.
- Prevent new records from slipping between pages in sort order.
- Use snapshots/staging if the exact same dataset is required across the whole Step.
- Test with concurrent inserts/updates/deletes while the Job is reading.

## 15. Repeatable Read Does Not Guarantee a Job-Wide Snapshot

Suppose a Step has 10,000 items and chunk size 100. The Step creates roughly 100 chunk transactions. Under `REPEATABLE_READ`, each chunk can have its own snapshot.

```text
Chunk 1 transaction: snapshot S1
       commit
Chunk 2 transaction: snapshot S2
       commit
Chunk 3 transaction: snapshot S3
       commit
       ...
Chunk 100 transaction: snapshot S100
```

If a reference table is updated between chunk 1 and chunk 2, chunk 2 may see the new version. Within chunk 1 itself, repeated reads of a row will still see the old version.

If business logic requires the entire Job to process a single version of reference data, consider:

- Creating a snapshot/version ID of reference data and passing that version into every query.
- Copying the dataset to process into a staging table keyed by batch ID before running chunks.
- Using temporal tables or querying by a fixed `effective_at`/version.
- Using database snapshots or long-lived transactions only when database and operations allow, after evaluating locks, MVCC retention, and connection lifetime.

Do not hold a single transaction across millions of items just for a snapshot without accounting for long locks, transaction logs, undo/MVCC retention, timeouts, and restartability.

## 16. Repeatable Read and Multi-Row Business Rules

A transaction can read two rows consistently yet still encounter dataset-level anomalies or multi-row rule violations depending on database isolation.

Example rule: a department must always keep at least one employee on duty. Two concurrent transactions read employees A and B, and then each deactivates a different person. Both may believe one employee remains on duty, yet the final result leaves zero.

This is a form of write skew possible under snapshot isolation. Repeatable reads on individual rows do not necessarily preserve invariants across the whole dataset.

Protections include:

- Using constraints or data models that let the database enforce the invariant directly.
- Locking a representative/parent row to serialize related operations.
- Using `SERIALIZABLE` when the database must detect and prevent anomalies.
- Using optimistic locking/version columns and handling conflicts.
- Designing updates as atomic SQL statements instead of multi-step read-then-write flows.

Choose the solution based on the business invariant. Raising isolation for the entire Step can be costlier than a narrow lock or constraint.

## 17. Pessimistic Locking and SELECT FOR UPDATE

Isolation levels are not the only tool for coordinating concurrent access. Pessimistic locking locks rows or data ranges while a transaction processes them.

SQL example:

```sql
SELECT order_id, status
FROM orders
WHERE order_id = ?
FOR UPDATE;
```

`FOR UPDATE` is common syntax, though details vary across databases. It instructs the database to lock matching rows so other transactions cannot perform conflicting updates/deletes on them until the transaction completes.

In Spring Batch, locking queries can be used when each chunk needs to claim a set of rows. Consider:

- Locks are held until the chunk commits or rolls back.
- Large chunks hold more locks for longer durations.
- Inconsistent lock acquisition order can cause deadlocks.
- Multiple workers need an explicit claim strategy.
- `SKIP LOCKED` or equivalent syntax depends on the database.

Do not lock an entire table just to avoid non-repeatable reads. Scope locks to the right rows/ranges and transaction boundaries to minimize contention.

## 18. Optimistic Locking and Version Columns

Optimistic locking lets multiple transactions read the same data while detecting conflicts at update time. A version column increments on every update:

```sql
UPDATE account
SET balance = ?, version = version + 1
WHERE account_id = ?
  AND version = ?;
```

If the updated row count is 0, another transaction changed the version. The application knows the data changed since it was read and can retry/reload or report a conflict.

Optimistic locking works well when conflicts are infrequent and you do not want long-held locks. In batch jobs, a version column prevents overwriting fresher updates from online applications.

Repeatable read and optimistic locking solve different problems: isolation governs snapshot/visibility inside a transaction; versioning checks whether a row changed since the application read it.

## 19. Read-Only Transactions and Isolation

Some readers or services only read data. You can mark a transaction read-only so the database/driver can optimize or reject accidental writes depending on the system:

```java
DefaultTransactionAttribute attribute = new DefaultTransactionAttribute();
attribute.setReadOnly(true);
attribute.setIsolationLevel(TransactionDefinition.ISOLATION_REPEATABLE_READ);
```

However, a chunk Step usually both reads and writes. Marking an entire chunk read-only when the writer must update the database is inappropriate. For a read-only export Step, `readOnly` can help if supported by the transaction manager and database.

`readOnly` is not an isolation level and does not create a consistent snapshot by itself. It is a separate transaction attribute whose semantics depend on the transaction manager and database.

## 20. Lock Duration, Chunk Size, and Throughput

Higher isolation can increase lock hold times, lock counts, conflict likelihood, or snapshot retention duration. Chunk size also governs how many items are processed per transaction.

| Chunk size | Typical impact |
|---|---|
| Small | Shorter transactions, more frequent commits, higher commit overhead |
| Large | Fewer commits, longer transactions, potentially longer locks/snapshots and larger rollbacks |

There is no universally optimal chunk size. When using `REPEATABLE_READ`, measure:

- Duration of each chunk transaction.
- Lock counts and lock wait times.
- Deadlocks/serialization failures.
- Connection pool usage.
- Transaction log/MVCC version retention.
- Throughput and retry counts.
- Volume of data replayed after a rollback.

If high isolation causes transactions to wait heavily on one another, reduce chunk size, shorten processor work, optimize indexes/queries, or partition data independently. Never lower isolation if doing so breaks business invariants.

## 21. Deadlocks and Serialization Failures

When multiple transactions hold locks or the database detects a serialization conflict, a transaction may be picked as a deadlock victim or aborted. Spring may translate database errors into `DeadlockLoserDataAccessException`, `CannotSerializeTransactionException`, or related exceptions depending on driver, translator, and version.

For batch steps, retry can be appropriate if the transaction can safely re-execute:

```java
return new StepBuilder("updateAccountsStep", jobRepository)
        .<AccountChange, AccountChange>chunk(100, transactionManager)
        .reader(accountChangeReader)
        .writer(accountChangeWriter)
        .faultTolerant()
        .retry(DeadlockLoserDataAccessException.class)
        .retryLimit(3)
        .build();
```

Exact exception names depend on Spring version and exception translation. You may need to configure retries for the root cause matching your database.

Retry must operate at the right transaction boundary so the entire chunk re-executes cleanly rather than repeating a mid-chunk statement after partial side effects occurred. Writers must be idempotent or fully enrolled in transaction rollback.

Reduce deadlocks by updating rows in consistent order, using proper indexes, keeping transactions short, and avoiding external API calls while holding database locks.

## 22. Isolation and Spring Batch Restart

Restarting creates a new transaction. `REPEATABLE_READ` from a prior transaction no longer holds once that transaction ends or the process stops. On restart, the database creates a new snapshot/lock context for the new transaction.

Example:

1. Chunk 1 reads data in snapshot A and commits.
2. Chunk 2 fails; the Job stops.
3. Another application updates the source table.
4. The Job restarts; the new chunk transaction sees snapshot B.

The reader can resume from the item-count checkpoint, yet subsequent queried data may have changed. Isolation levels do not automatically ensure a restarted Job sees the same snapshot as the earlier run.

For reproducible restarts, pin the input set via batch ID, manifest, watermark, snapshot/version, or staging table. With paging, use stable sort keys and query within fixed boundaries. With cursors, inspect the connection/snapshot lifetime of the cursor itself.

## 23. Isolation and JobRepository

Spring Batch persists `JobExecution`, `StepExecution`, and `ExecutionContext` via `JobRepository`. Chunk transactions can share the repository's transaction if configured on the same `DataSource`/transaction manager in a compatible architecture, or use a separate transaction manager.

This matters because business data and checkpoint metadata must stay consistent. If the writer commits business data in one database while the metadata repository commits in an independent transaction, a failure between the two commits can leave mismatched state that must be handled per repository setup.

Chunk transaction isolation does not automatically apply to `JobRepository` if the repository uses a different `DataSource`/transaction manager. Understand clearly:

- Which `DataSource` serves business data.
- Which `DataSource` serves `JobRepository`.
- Which transaction manager is passed to `chunk(...)`.
- How the repository's transaction manager is configured.
- How metadata and business writes coordinate at commit time.

Never assume all resources share one transaction merely because they are used in the same Step.

## 24. When Should You Choose REPEATABLE_READ?

`REPEATABLE_READ` can fit when a chunk needs to re-read the same row multiple times and must observe the exact same values throughout the transaction. Examples:

- A processor re-reads a configuration row or reference value during the same chunk transaction.
- A reconciliation workflow re-verifies a row before updating it in the same transaction.
- Multiple `SELECT` queries within one transaction must see the same version of already-read rows.
- A business rule is sensitive to non-repeatable reads without requiring serializable semantics across the whole dataset.

Do not pick it merely because it sounds "safer" without identifying the anomaly to prevent. If each item is read once and the writer uses optimistic locking/constraints, `READ_COMMITTED` may suffice. If invariants span predicates or multiple rows, you may need `SERIALIZABLE`, explicit locks, or constraints.

## 25. When Should You Avoid REPEATABLE_READ?

Think carefully when:

- The Step has long transactions or overly large chunk sizes.
- Many Jobs update the same table and lock contention is already high.
- Long-held database snapshots bloat MVCC/undo retention.
- The reader uses a separate connection so chunk isolation does not govern the read query.
- The data source is expected to change chunk by chunk and seeing fresh versions is intentional.
- The business requirement actually calls for a Job-wide snapshot, which chunk-level repeatable read does not provide.

In these scenarios, optimizing queries, fixing inputs with a batch ID, or using staging/versioning solves the real problem better than raising isolation on every chunk.

## 26. Comparing READ_COMMITTED and REPEATABLE_READ

Suppose a processor reads a product price twice inside the same transaction to calculate a discount tier.

With `READ_COMMITTED`:

```text
T1: SELECT price -> 100
T2: UPDATE price = 120; COMMIT
T1: SELECT price -> 120
```

The processor may use two different values within a single processing pass.

With `REPEATABLE_READ`:

```text
T1: SELECT price -> 100
T2: UPDATE price = 120; COMMIT or wait depending on DB
T1: SELECT price -> 100
T1: COMMIT
```

T1 continues using the same row version it read. After T1 commits, new transactions can see the price `120`.

If the processor reads the price only once and computes from it, higher isolation may bring no meaningful benefit. If the writer updates the row, you still need a policy for when prices change before commit and whether optimistic/pessimistic locking is needed.

## 27. Testing Isolation with Two Concurrent Transactions

Do not rely solely on mocked unit tests to validate `REPEATABLE_READ`. Write integration tests with a production-like database/driver and two independent connections.

A non-repeatable read test can run:

1. Transaction A starts at the isolation level under test.
2. A reads a row and records its value.
3. Transaction B updates the same row and commits.
4. A re-reads the same row.
5. Compare the outcome against the database's documented semantics.

To test phantoms:

1. A runs a predicate query and counts rows.
2. B inserts a new row matching the predicate and commits.
3. A re-runs the query.
4. Observe the row count under that specific isolation level and database.

Use `CountDownLatch`, barriers, or transaction test utilities to control ordering rather than arbitrary `sleep()` calls. Tests must ensure each transaction truly uses its own connection rather than accidentally joining the same thread-bound transaction.

Also run Step integration tests to verify:

- The transaction attribute is applied to chunks.
- Reader/writer join the intended `DataSource` transaction.
- Whether cursor readers use a separate connection or a shared connection.
- Retries on deadlock/serialization failures.
- Restarts create new transactions/snapshots and input sources are pinned properly.

## 28. Common Pitfalls

**Assuming REPEATABLE_READ snapshots the entire Job.** Spring Batch usually opens transactions per chunk; each chunk can observe a different snapshot.

**Assuming REPEATABLE_READ prevents phantoms on all databases.** Under the SQL standard, phantoms can still occur; individual databases provide stronger or differing semantics.

**Equating REPEATABLE_READ with SERIALIZABLE.** Snapshot isolation can still allow write skew or serialization anomalies.

**Putting @Transactional on a writer and thinking chunk isolation changed.** Methods usually join an already-open transaction; isolation cannot be upgraded mid-transaction.

**Assuming every JDBC reader uses the chunk connection.** Default `JdbcCursorItemReader` usually opens a separate cursor connection. Verify the actual connection used.

**Assuming isolation alone prevents lost updates.** Check update statements, version columns, locks, and constraints.

**Raising isolation to cure every race condition.** You may need unique constraints, claim patterns, idempotency, or key-based partitioning instead of higher isolation.

**Enabling SERIALIZABLE without preparing retries.** Databases may abort transactions on serialization conflicts; batch jobs need error handling and bounded retries.

## 29. Choosing Isolation for JDBC Processing

Start from the concrete anomaly. If you only need to prevent dirty reads, `READ_COMMITTED` is usually the appropriate baseline. If a transaction must re-read the same row with consistent values, consider `REPEATABLE_READ`. If business rules depend on predicates or multiple rows requiring serial-equivalent behavior, evaluate `SERIALIZABLE`, locking, or constraints.

In Spring Batch, configure isolation on the chunk Step's transaction attribute when chunk transactions are what need protection. Verify whether the reader and writer actually share connections inside that transaction, paying special attention to `JdbcCursorItemReader` opening a separate cursor connection by default. Never mistake a single chunk's transaction for a Step-wide or Job-wide snapshot.

When consistency across multiple chunks and restarts is needed, pin the dataset using a batch ID, watermark, manifest, version, or staging snapshot. Measure lock waits, deadlocks, transaction durations, connection usage, and throughput against the real database. Isolation level is one piece of consistency design; it must work together with transaction boundaries, queries, locking, versioning, and Job restartability.

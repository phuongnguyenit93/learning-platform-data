# rewriteBatchedStatements, Batch DML, and Partial Error Handling

JDBC lets applications group multiple write operations into a batch and send them via `executeBatch()`. With MySQL Connector/J, the `rewriteBatchedStatements` connection property can allow the driver to transform batches into fewer round trips with the server. Used properly, batch DML reduces round-trip overhead and boosts throughput; used without controls, it can produce oversized statements, increase memory pressure, prolong transactions, or make partial error outcomes difficult to determine.

A critical distinction is that **JDBC batches, rewritten SQL, and transactions are three separate concepts**. JDBC defines how the client queues and sends multiple commands; Connector/J decides whether and how a batch can be rewritten; MySQL transactions determine commit/rollback scope. Therefore, enabling `rewriteBatchedStatements=true` does not automatically guarantee that the entire batch is an atomic transaction or that you can determine exactly which individual rows were written.

This lesson focuses on MySQL Connector/J and JDBC. Java examples use `PreparedStatement`, InnoDB, and MySQL 8.0; exact rewrite behavior depends on the Connector/J version, statement type, prepared statement settings, and server configuration. Test with the exact driver deployed.

## Learning Objectives

After this lesson, you will be able to:

- Distinguish `addBatch()`, `executeBatch()`, and transaction commits.
- Explain the purpose and limits of `rewriteBatchedStatements`.
- Understand the difference between rewriting into multi-value INSERTs and sending multiple statements in one exchange.
- Interpret update counts, `BatchUpdateException`, and `SUCCESS_NO_INFO`/`EXECUTE_FAILED` codes.
- Design safe batch sizes, transaction boundaries, and retries.
- Handle partial errors, ambiguous connection failures, and generated keys.
- Measure batch performance without compromising data integrity.

## 1. How Does JDBC Batch DML Work?

JDBC batching allows an application to queue multiple write operations and submit them in a group. With `PreparedStatement`, the application uses one SQL template with multiple parameter sets. Each call to `addBatch()` queues the current parameter set into the batch; `executeBatch()` asks the driver to execute all queued items.

Example of an insert with multiple parameter sets:

```java
String sql = "INSERT INTO inventory (sku, warehouse_id, quantity) "
        + "VALUES (?, ?, ?)";

try (PreparedStatement ps = connection.prepareStatement(sql)) {
    ps.setString(1, "SKU-1001");
    ps.setLong(2, 10L);
    ps.setInt(3, 25);
    ps.addBatch();

    ps.setString(1, "SKU-1002");
    ps.setLong(2, 10L);
    ps.setInt(3, 40);
    ps.addBatch();

    int[] counts = ps.executeBatch();
}
```

In this example, the client queues two batch entries. When `executeBatch()` runs, Connector/J may send them normally or rewrite them if the statement and settings qualify. `addBatch()` does not mean data has been sent to the server, and `executeBatch()` does not mean data has committed.

### 1.1. Statement Batch vs. PreparedStatement Batch

- `Statement.addBatch(String sql)` is used when a batch contains distinct SQL statements. The application must construct SQL manually, making escaping mistakes and SQL injection easy if input data is concatenated.
- `PreparedStatement.addBatch()` uses one SQL statement with multiple parameter sets. This is usually the right choice for batch inserts/updates/deletes sharing the same structure.

Prefer `PreparedStatement` to bind typed parameters, avoid SQL string assembly, and leverage driver/server prepared statement mechanisms when suitable. Never concatenate user values into SQL just to achieve rewriting.

### 1.2. A Batch Is Not a Transaction

A batch is a group of commands sent together by the client. A transaction is a group of data modifications committed or rolled back according to MySQL's storage engine and transaction boundaries.

| Mechanism | Responsibility |
|---|---|
| `addBatch()` | Queues an operation into the JDBC batch |
| `executeBatch()` | Instructs the driver to send/execute the batch and returns update counts or throws an error |
| `setAutoCommit(false)` | Switches the connection to application-managed transaction mode; the transaction begins upon transactional work |
| `commit()` | Commits changes in the current transaction |
| `rollback()` | Reverts uncommitted transactional changes |

If the connection has `autoCommit=true`, each SQL statement executed by the server may commit independently under autocommit rules. When the driver rewrites multiple operations into a single SQL statement, statement boundaries also shift. To control transaction boundaries explicitly, set `autoCommit=false`, decide which batches belong to which transaction, and commit intentionally.

## 2. What Is `rewriteBatchedStatements`?

`rewriteBatchedStatements` is a MySQL Connector/J connection property. When enabled, the driver attempts to rewrite compatible batches to reduce server round trips. For example, multiple inserts of identical structure can be merged into a single multi-value INSERT; other batch forms may use multi-query transmission or another optimization supported by your driver version.

Connection URL example:

```text
jdbc:mysql://db.example:3306/app?rewriteBatchedStatements=true
```

Example using `DriverManager` with the property in the URL:

```java
String url = "jdbc:mysql://db.example:3306/app?rewriteBatchedStatements=true";
Properties properties = new Properties();
properties.setProperty("user", "app_writer");
properties.setProperty("password", readSecret("mysql/app-writer"));
try (Connection connection = DriverManager.getConnection(url, properties)) {
    // Use connection configured with rewriteBatchedStatements.
}
```

For `DataSource` or connection pools, set the same property via that library's configuration mechanism. Never put real passwords into source code, committed URLs, or logs.

### 2.1. Multi-Value INSERT

For eligible insert batches, the driver can combine multiple parameter rows into a single statement like:

```sql
INSERT INTO inventory (sku, warehouse_id, quantity)
VALUES
  ('SKU-1001', 10, 25),
  ('SKU-1002', 10, 40),
  ('SKU-1003', 12, 15);
```

Instead of sending one request per row, the client sends a single SQL statement containing multiple rows. This typically reduces round trips and repeated parse/execute overhead.

### 2.2. Multi-Query and Other Batches

Not every batch can be converted into a multi-value INSERT. For heterogeneous statements or certain forms of updates/deletes, the driver may send multiple statements within a single network exchange. Rewriting behavior depends on statement type, Connector/J version, and connection configuration.

Therefore, do not assume that:

- Every `UPDATE` in a batch is merged into a single update statement.
- Every `PreparedStatement` is rewritten identically.
- Enabling rewrite always yields exactly one round trip for the entire batch.
- Returned update counts always report exact row counts for every original entry.

Check the documentation for your exact version, enable driver logging if possible, and measure in practice. For large batches, the driver may split execution into multiple smaller chunks based on packet limits or internal thresholds.

### 2.3. Enabling Rewrite Is Not Arbitrary Multi-Query

`rewriteBatchedStatements` is an optimization for JDBC-managed batches. It should never be used as an excuse to concatenate input SQL strings or expose an API that executes uncontrolled multi-statement queries. Continue using parameter binding and least-privilege database accounts.

Other properties such as `useServerPrepStmts`, `allowMultiQueries`, `continueBatchOnError`, and `useAffectedRows` serve separate purposes. Their combinations can alter how the driver executes statements or reports counts; never change them simultaneously in production without testing.

## 3. Measuring Benefits and Choosing Batch Size

Batching typically improves throughput by cutting round trips, but larger batches are not always faster. Oversized batches can:

- Produce huge SQL/packets, hitting `max_allowed_packet` or driver limits.
- Increase JVM heap usage to buffer parameters and results.
- Lengthen a single `executeBatch()` call and make timely cancellation harder.
- Hold locks longer when many operations share one transaction.
- Create large transactions, increasing undo/redo, binary logs, and replica lag.
- Make partial failures harder to pinpoint and retries more expensive.

Size batches by both row count and byte size. A batch of 1,000 rows with three integers behaves very differently from 1,000 rows containing large JSON or BLOBs. Start with a moderate size, measure p95/p99 execute latency, memory, packet sizes, lock waits, and replica lag, and tune from there.

For example, 500 or 1,000 rows can be a reasonable starting point for small-row tables, not a universal optimum. Large payloads may require smaller batches; narrow rows over high-latency links may benefit from larger batches.

### 3.1. Measuring Throughput

A valid benchmark compares identical data, schema, and concurrency:

1. Run the batch with `rewriteBatchedStatements=false`.
2. Rerun in an equivalent environment with `rewriteBatchedStatements=true`.
3. Keep batch size, transaction boundaries, connection pool, and worker count constant.
4. Measure rows/second, p95/p99 execute time, CPU, disk I/O, network round trips if observable, lock waits, and replica lag.
5. Verify row counts and data values after each pass.

Do not compare only the duration of a single isolated batch. Concurrent load and transaction commits usually govern overall application throughput.

## 4. Update Counts and Execution Results

`executeBatch()` returns an `int[]` array of update counts. Per JDBC, each entry normally indicates the number of rows affected by the corresponding batch item. However, the driver may return special constants:

| Value | Meaning |
|---|---|
| `1`, `2`, ... | Affected row count reported by the driver |
| `Statement.SUCCESS_NO_INFO` (`-2`) | Item succeeded, but the driver could not determine the exact affected row count |
| `Statement.EXECUTE_FAILED` (`-3`) | Item failed in a batch result reporting per-item error information |

When a batch is rewritten, mapping from a merged SQL statement back to each original batch item may be incomplete. Never rely on update counts as the sole proof that each record wrote as expected. Cross-check using business keys, row counts, batch state, and verification queries.

Example checking results:

```java
int[] counts = ps.executeBatch();

for (int i = 0; i < counts.length; i++) {
    int count = counts[i];
    if (count == Statement.EXECUTE_FAILED) {
        throw new SQLException("Batch item failed at index " + i);
    }
    if (count == Statement.SUCCESS_NO_INFO) {
        // Succeeded without exact row count information.
        continue;
    }
    if (count < 0) {
        throw new SQLException("Unexpected batch update count: " + count);
    }
}
```

If business rules require each command to affect exactly one row, verify whether the driver reports exact counts under your current configuration. A `SUCCESS_NO_INFO` result cannot prove an "exactly one row" invariant per item.

## 5. Handling `BatchUpdateException` and Partial Failures

When a batch element fails, JDBC throws `BatchUpdateException`, a subclass of `SQLException`. You can inspect update counts for items processed by the driver:

```java
try {
    int[] counts = ps.executeBatch();
    // Inspect results when the batch completes.
} catch (BatchUpdateException e) {
    int[] counts = e.getUpdateCounts();

    for (int i = 0; i < counts.length; i++) {
        System.err.printf("item=%d count=%d%n", i, counts[i]);
    }

    System.err.println("SQLState=" + e.getSQLState());
    System.err.println("VendorCode=" + e.getErrorCode());
    throw e;
}
```

The length and meaning of the update counts array depend on how the driver processes batches. The driver may stop on error or continue with remaining items depending on configuration and rewrite behavior. Never assume that items after the failing index definitely did not run, or definitely did run.

### 5.1. `continueBatchOnError`

Connector/J has the `continueBatchOnError` property controlling whether batch processing continues after a command fails when the driver executes items individually. The default is typically `true` in Connector/J, though you should verify your version.

When enabled, the driver may continue running remaining commands after an error and throw `BatchUpdateException` with update counts. When disabled, it may stop at the first failure. However, if the batch was rewritten into a single SQL statement, the server may only return an outcome at that single statement level; the driver cannot guarantee per-record continuation like an independent loop.

Consequently, `continueBatchOnError` does not provide "row-level isolation where a failing row affects only itself." To isolate failures per record, use small batches, pre-validate, use savepoints/transactions, or load into staging tables to classify errors.

### 5.2. Different Error Categories

| Error category | Examples | Handling strategy |
|---|---|---|
| Invalid data | Wrong type, NOT NULL violation, column length overflow | Record failing item, fix source, or route to quarantine table |
| Constraint violation | Duplicate key, foreign key | Check business keys and referenced data; do not retry verbatim |
| Contention errors | Deadlock, lock wait timeout | Retry entire transaction with backoff after verifying rollback state |
| Configuration errors | Missing privileges, wrong schema/table | Fix configuration or grants; do not retry infinitely |
| Connection errors | Socket timeout, connection lost during execute/commit | Outcome may be unknown; verify data state before retrying |
| Resource errors | Packet too large, disk full, server overload | Shrink batch, check packet/disk/load, and rerun in a controlled manner |

## 6. Transaction Boundaries and Atomicity

With InnoDB tables, transactions group multiple modifications into a single commit/rollback unit. JDBC must manage transaction boundaries explicitly:

```java
connection.setAutoCommit(false);
try {
    // Execute one or more executeBatch() calls.
    connection.commit();
} catch (SQLException e) {
    try {
        connection.rollback();
    } catch (SQLException rollbackError) {
        e.addSuppressed(rollbackError);
        // Do not reuse the connection if transaction state is uncertain.
    }
    throw e;
}
```

This snippet is a skeleton for an application-owned connection. For pooled connections, let the pool or transaction manager reset state per its contract. Never unconditionally call `setAutoCommit(true)` in `finally` after an error without a successful rollback: JDBC can commit an open transaction when flipping autocommit back to true. If rollback or connection reset fails, evict the connection using the pool's API instead of reusing a connection with uncertain state.

### 6.1. One Batch in One Transaction

When `autoCommit=false`, executed transactional DML statements remain uncommitted until the application calls `commit()`. If the batch fails, the application can roll back the transaction to undo uncommitted InnoDB changes.

This fits when all rows in a batch must succeed or fail together. However, oversized transactions increase lock hold times, undo/redo volume, binary log size, and replica lag risk. Use a single huge transaction only when business rules strictly demand atomicity at that scale and resources are verified.

### 6.2. Chunked Commits

When importing millions of records, workloads are usually split into chunks, each committed as its own transaction. For example, 500 records are sent in one batch and committed before moving to the next chunk.

Benefits:

- Caps lock hold durations and transaction size.
- Reduces rollback overhead if a chunk fails.
- Simplifies checkpointing and resuming after process restarts.
- Enables throttling based on load and replica lag.

The trade-off is that the overall import is no longer atomic. If chunk 12 fails, earlier chunks have already committed. The application must persist progress and support safe reruns.

### 6.3. Rewriting Can Shift Failure Boundaries

Suppose a batch has 100 inserts. If the driver sends each statement separately with autocommit enabled, earlier inserts may have already committed before a later one fails. If the driver rewrites them into one multi-value INSERT on InnoDB, the server processes it as one statement; a statement error can roll back the entire statement per transactional engine rules. If the driver uses multi-query with multiple statements, each statement can have its own autocommit boundary when autocommit is on.

Inside an explicit transaction on InnoDB, transactional DML executed within that transaction can roll back together. Still, distinguish statement errors, InnoDB deadlock rollbacks of the whole transaction, timeouts, and statements with implicit commits. Never place DDL or implicit-commit operations inside a DML batch assuming rollback will undo everything.

For nontransactional tables, rollback cannot undo written changes like InnoDB. For consistent rollback behavior, prefer InnoDB tables and review any triggers or side effects.

## 7. Chunked Batch Insert Example

The following example uses `PreparedStatement`, a fixed batch size, and per-chunk commits. The goal is bounding transactions, not claiming this batch size fits every workload.

```java
int batchSize = 500;
int pending = 0;
String sql = "INSERT INTO import_orders "
        + "(source_order_id, customer_id, amount) VALUES (?, ?, ?)";

try (Connection connection = dataSource.getConnection()) {
    connection.setAutoCommit(false);

    try (PreparedStatement ps = connection.prepareStatement(sql)) {
        for (OrderRow row : rows) {
            ps.setString(1, row.getSourceOrderId());
            ps.setLong(2, row.getCustomerId());
            ps.setBigDecimal(3, row.getAmount());
            ps.addBatch();
            pending++;

            if (pending == batchSize) {
                ps.executeBatch();
                // Write checkpoint in the same transaction as chunk data.
                connection.commit();
                ps.clearBatch();
                pending = 0;
            }
        }

        if (pending > 0) {
            ps.executeBatch();
            // Write checkpoint in the same transaction as the final chunk data.
            connection.commit();
            ps.clearBatch();
        }
    } catch (SQLException e) {
        try {
            connection.rollback();
        } catch (SQLException rollbackError) {
            e.addSuppressed(rollbackError);
            // Mark connection unsafe for reuse.
        }
        throw e;
    }
}
```

This example assumes the method owns the connection borrowed from `DataSource`; closing it returns it to the pool or closes the physical connection per configuration. If the application uses a transaction manager, let the transaction manager handle commit/rollback and do not mix manual control with it. In production code, also handle update counts and persist checkpoints in the same transaction as chunk data whenever possible. Once a chunk commits, rolling back a later chunk cannot undo earlier chunks.

Never unconditionally call `setAutoCommit(true)` inside `finally` after an error without a successful rollback: JDBC can commit an open transaction when flipping autocommit to true. If rollback or connection reset fails, evict the connection from the pool via the pool's API instead of reusing a connection with unknown state.

With Spring, to avoid accidentally opening an oversized transaction, place transaction boundaries on the service handling each chunk. Watch propagation settings and note that `JdbcTemplate.batchUpdate()` may split batches according to configured batch size; transactions remain managed by Spring's transaction manager.

## 8. Safe Retries and Idempotency

Retries are necessary for transient failures, but blind retries can create duplicates or double-apply effects. A tricky case is losing the connection immediately after sending a batch: the server may have committed while the response never reached the client. The application does not know whether the batch succeeded.

### 8.1. Using an Idempotency Key

If every record has an identifier from the source system, persist that identifier with a unique key:

```sql
CREATE TABLE import_orders (
  source_order_id VARCHAR(80) NOT NULL,
  customer_id BIGINT NOT NULL,
  amount DECIMAL(12, 2) NOT NULL,
  imported_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
  PRIMARY KEY (source_order_id)
) ENGINE = InnoDB;
```

The unique key allows reruns to recognize already-ingested records. You can use `INSERT ... ON DUPLICATE KEY UPDATE` if business rules permit updating existing records; clearly define which columns update and how to avoid overwriting newer data with stale data.

Never use `INSERT IGNORE` or blanket upserts to swallow all errors. Those operations can convert invalid data into silent warnings or unintended updates. Idempotency must reflect business identities and rules, not merely suppress exceptions.

### 8.2. Per-Chunk Checkpoints

An import coordination table can record `batch_id`, source key range, status, expected row count, processed row count, and commit timestamp. Update the checkpoint in the same transaction as the chunk's data whenever possible so the checkpoint never advances ahead of committed data.

When a worker restarts:

1. Read the batch status and last committed checkpoint.
2. Verify the last chunk's data completeness via idempotency keys.
3. Process only incomplete portions.
4. Record failed records separately so they can be repaired and replayed.

If commit state is ambiguous due to connection loss, query by batch ID or source key before rerunning. Never assume a client-side error implies a server-side rollback.

### 8.3. Retrying Deadlocks and Timeouts

InnoDB deadlocks normally pick one transaction as a victim and roll it back. When that happens, retries must re-execute the entire transaction, not just the last statement in the batch. Use bounded retry counts, exponential backoff with jitter, and log SQLState/vendor codes.

Lock wait timeouts normally roll back only the waiting statement under default settings; the transaction may still remain active. The application must decide to roll back the entire transaction before retrying to preserve consistent logic. Never retry infinitely, as that increases load and prolongs contention.

Duplicate key errors, invalid data, or missing privileges rarely resolve on retry. Classify errors before deciding to retry.

## 9. Generated Keys in Batches

If a table uses `AUTO_INCREMENT`, JDBC can request generated keys:

```java
try (PreparedStatement ps = connection.prepareStatement(
        "INSERT INTO customers (email) VALUES (?)",
        Statement.RETURN_GENERATED_KEYS)) {

    ps.setString(1, "a@example.test");
    ps.addBatch();
    ps.setString(1, "b@example.test");
    ps.addBatch();

    ps.executeBatch();

    try (ResultSet keys = ps.getGeneratedKeys()) {
        while (keys.next()) {
            long id = keys.getLong(1);
            // Record returned key.
        }
    }
}
```

When rewriting batch inserts into multi-value INSERTs, Connector/J can optimize generated key retrieval, though applications must verify behavior on their actual driver/server versions. Never extrapolate sequential IDs by taking the first ID and adding row offsets: `AUTO_INCREMENT` can have gaps from rollbacks, concurrency, increment/offset settings, or other operations.

If deterministic mapping from database ID back to each source record is required, use a business/idempotency key and query back by those keys, or thoroughly test `getGeneratedKeys()` under the exact rewrite settings before relying on returned order.

## 10. Connector/J Configuration and Testing

Properties that affect batching:

| Property | Role | Notes |
|---|---|---|
| `rewriteBatchedStatements` | Allows driver to rewrite compatible batches | Usually defaults to `false`; measure before/after and check which statement types rewrite |
| `continueBatchOnError` | Continues processing commands after an error when items execute individually | Does not guarantee per-row isolation when a batch rewrites into one statement |
| `useServerPrepStmts` | Uses server-side prepared statements when supported | Interaction with rewrite depends on driver/server version; test combined config |
| `allowMultiQueries` | Allows client to send multiple separated SQL statements in one statement | Not a substitute for JDBC batching or parameter binding |
| `useAffectedRows` | Affects how MySQL/driver reports affected/found rows on certain UPDATEs | Application must interpret update counts consistently |

Verify applied properties via connection pool config or driver metadata APIs. Never put passwords in URLs if URLs are logged. Prefer a secret manager or environment credential provisioning.

A test matrix should cover:

- Rewrite enabled and disabled.
- `autoCommit=true` and `false`.
- `PreparedStatement` inserts, updates, and deletes.
- Clean batch, duplicate key mid-batch, and data error at end of batch.
- Deadlock, lock wait timeout, and connection drop during execute/commit.
- Batches with generated keys.
- Small and large record sizes approaching packet limits.
- Active replica and production-like concurrency.

After each test case, verify actual database state, update counts, transaction state, logs, and retryability. This establishes the exact failure boundaries of your specific driver.

## 11. Common Errors

| Symptom | Possible cause | Resolution |
|---|---|---|
| Rewrite enabled but speed unchanged | Statement did not rewrite, batch too small, or bottleneck is storage/index | Check SQL type, driver version, and measure round trips/DB load |
| `PacketTooBigException` or oversized packet | Batch contains too much data or large row payloads | Shrink batch size by bytes; check `max_allowed_packet` on server and driver |
| `BatchUpdateException` without clear failing record | Incomplete update counts or rewrite changed failure boundary | Log batch ID, shrink batches to isolate errors, and verify data by source key |
| Partial data present after exception | Autocommit or earlier statements committed before failure | Check state before retrying; use idempotency keys/checkpoints |
| Duplicate key on rerun | Prior batch committed even though client missed the response | Reconcile records by business key and design explicit upsert rules |
| Rising replica lag | Large transactions/chunks generate heavy binlogs or replica applies slowly | Reduce batch/transaction size and throttle based on lag |
| Deadlocks when multiple batch workers run concurrently | Workers update keys in different orders | Sort by key, reduce concurrency, and retry whole transactions |
| Generated keys do not map as expected | Driver rewrite, auto-increment concurrency, or sequential ID assumptions | Test `getGeneratedKeys()` and query back by source key |

## 12. Hands-On Exercise

A Java service uses MySQL Connector/J to ingest 200,000 transactions from a file. Each transaction has a unique `source_txn_id`, `account_id`, `amount`, and `created_at`. Currently the service calls `executeUpdate()` row by row, resulting in low throughput. The team wants to enable `rewriteBatchedStatements=true` and run four parallel workers.

Design the solution and answer:

1. Why is `PreparedStatement.addBatch()` better than concatenating 200,000 SQL strings?
2. Which SQL form can `rewriteBatchedStatements` transform a batch INSERT into? Why can't you assume all DML types rewrite the same way?
3. How would you choose an initial batch size by row count and byte size? Which metrics should you measure?
4. If each chunk commits separately, what happens if a worker fails at chunk 20?
5. Which values can `BatchUpdateException.getUpdateCounts()` contain? Why does `SUCCESS_NO_INFO` not prove exact row counts?
6. Does `continueBatchOnError=true` guarantee the driver continues record by record after a batch has been rewritten? Explain.
7. If the client times out immediately after `executeBatch()` or `commit()`, how do you determine whether data was written before retrying?
8. Design a unique key/idempotency key and checkpoint so reruns never create duplicate transactions.
9. When a deadlock occurs, should you retry the statement or the entire transaction? How does lock wait timeout handling differ?
10. If generated keys are needed per source transaction, how do you verify ID mapping under rewrite configuration?
11. How can four workers cause deadlocks or replica lag? How would you throttle concurrency?

Test on an InnoDB table with sample data containing duplicate keys at the start, middle, and end of a batch; test both autocommit and explicit transactions, with rewrite enabled and disabled. After each run, reconcile record counts by `source_txn_id`, transaction state, and update counts.

## Conclusion

`rewriteBatchedStatements` can reduce round trips by rewriting compatible JDBC batches, especially insert batches that merge into multi-value INSERTs. It does not define transaction boundaries and does not guarantee complete update counts or per-record error reporting. To make batch DML both fast and safe, use `PreparedStatement`, size batches by payload size, manage chunked transactions, inspect `BatchUpdateException`, build idempotency keys/checkpoints, and test failure boundaries on your exact Connector/J version. Whenever commit status is uncertain, check database state by source key before retrying.

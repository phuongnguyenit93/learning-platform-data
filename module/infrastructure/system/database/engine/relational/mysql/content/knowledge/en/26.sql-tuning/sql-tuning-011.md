# Batch DML, Multi-Row INSERT, and Packet Size Limits

When an application needs to write thousands or millions of rows, sending one SQL statement per row generates excessive network round-trips and repeated statement processing. **Batch DML** groups multiple data operations into appropriately sized chunks. In MySQL, you can use multi-row `INSERT`, `INSERT ... SELECT`, batched transactions, or client batch APIs. However, oversized batches can exceed packet limits, hold locks too long, generate heavy undo/redo, and increase rollback duration or replication lag.

This lesson belongs to the **SQL Tuning** section of MySQL. You will choose batching strategies, design multi-row `INSERT`s, handle duplicate keys, partition transactions, estimate payload sizes, check `max_allowed_packet` on both client and server, and build retry workflows that can resume safely after failure.

## 1. Why Batch DML?

Suppose an application needs to insert 10,000 records. Sending 10,000 individual `INSERT` statements incurs statement transmission, parsing, planning, execution, and response overhead on every row. Grouping into multi-row `INSERT` statements or prepared-statement batches cuts down round-trips.

Batch DML can improve:

- **Network round-trips:** reduces how often the client sends commands and waits for responses.
- **Statement overhead:** reduces statement parsing and setup when using multi-row INSERT or proper prepared statements.
- **Transaction overhead:** multiple changes inside one transaction share commit and log-flush overhead.
- **Throughput:** increases rows written per unit of time when batch size matches server capacity and workload.

Batching also expands the blast radius of each failure. A huge batch can hold many row locks, generate large undo records, consume memory, and prolong rollbacks. Therefore, the goal is not making batches as large as possible, but finding a size that balances throughput, latency, recoverability, and resource limits.

## 2. Multi-Row INSERT in a Single Statement

Basic syntax allows inserting multiple value tuples in one statement:

```sql
INSERT INTO import_orders (
    order_id,
    customer_id,
    status,
    total_amount
)
VALUES
    (1001, 501, 'NEW', 125.00),
    (1002, 502, 'PAID', 89.50),
    (1003, 501, 'NEW', 240.00);
```

MySQL processes all three tuples in one statement. Always list columns explicitly so the statement does not rely on physical table column order and stays maintainable as the schema evolves.

Example target table:

```sql
CREATE TABLE import_orders (
    order_id BIGINT NOT NULL,
    customer_id BIGINT NOT NULL,
    status VARCHAR(20) NOT NULL,
    total_amount DECIMAL(12, 2) NOT NULL,
    created_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
    PRIMARY KEY (order_id),
    KEY ix_customer (customer_id)
) ENGINE = InnoDB;
```

Omitting `created_at` tells MySQL to use its default value. Value tuples must supply matching column counts and compatible data types for the column list.

### Multi-Row INSERT vs Multiple INSERT Statements

The two approaches below insert the same data with different statement counts:

```sql
-- Multiple statements
INSERT INTO import_orders (order_id, customer_id, status, total_amount)
VALUES (2001, 501, 'NEW', 10.00);

INSERT INTO import_orders (order_id, customer_id, status, total_amount)
VALUES (2002, 502, 'NEW', 20.00);

-- One multi-row statement
INSERT INTO import_orders (order_id, customer_id, status, total_amount)
VALUES
    (2001, 501, 'NEW', 10.00),
    (2002, 502, 'NEW', 20.00);
```

Multi-row INSERT usually reduces round-trips and statement processing cost. In InnoDB, a multi-row statement is a single statement; if it fails due to a duplicate key or constraint violation, statement behavior depends on error type and engine. In InnoDB, ordinary statement errors fail the statement and roll back its partial changes, while the enclosing transaction may remain open depending on the error.

With `autocommit=1`, each successful statement is committed individually. When sending multiple INSERTs inside an explicit transaction, statements commit together upon `COMMIT`.

## 3. Other Batch Data Loading Approaches

### INSERT ... SELECT

When source data already resides in MySQL, insert query results directly into the target table:

```sql
INSERT INTO archived_orders (
    order_id,
    customer_id,
    status,
    total_amount
)
SELECT
    order_id,
    customer_id,
    status,
    total_amount
FROM orders
WHERE created_at < '2025-01-01';
```

`INSERT ... SELECT` avoids pulling data through the client and sending it back to the server. However, the source query can scan many rows, hold resources long, and create one huge transaction. Inspect `EXPLAIN` for the SELECT portion, filter indexes, and expected row count.

### Range-Based INSERT ... SELECT

To break up data movement, use an ascending key or time range as a checkpoint:

```sql
INSERT INTO archived_orders (
    order_id,
    customer_id,
    status,
    total_amount
)
SELECT
    order_id,
    customer_id,
    status,
    total_amount
FROM orders
WHERE order_id > 100000
  AND order_id <= 110000;
```

After verifying row count and committing, record the last processed boundary. The next batch starts after that watermark. Using explicit key ranges allows a job to resume cleanly after interruption.

### LOAD DATA for Large Files

When the source is a CSV or line-delimited file, `LOAD DATA [LOCAL] INFILE` is usually better than building one giant INSERT statement:

```sql
LOAD DATA LOCAL INFILE '/data/orders.csv'
INTO TABLE import_orders
FIELDS TERMINATED BY ','
OPTIONALLY ENCLOSED BY '"'
LINES TERMINATED BY '\n'
IGNORE 1 LINES
(order_id, customer_id, status, total_amount);
```

`LOCAL` reads the file from the client host; without `LOCAL`, the file is read from the server host and must satisfy server file access settings and privileges. Security behavior and `LOCAL` availability depend on client/server configuration. For very large datasets, verify permissions, encoding, delimiters, newlines, malformed rows, and rollback strategy.

`LOAD DATA` does not eliminate all resource limits, yet it avoids shipping one massive SQL statement containing all data. Benchmark it against multi-row INSERT for your file size and data validation requirements.

## 4. Batch Transactions: Choosing Commit Boundaries

There are two independent decisions:

1. **Statement size:** number of rows or bytes per INSERT/UPDATE/DELETE statement.
2. **Transaction size:** total statements or changes committed together.

A single transaction can contain many small statements. Conversely, a single multi-row INSERT can be one statement and its own transaction when autocommit is enabled.

### One Transaction for the Entire Dataset

```sql
START TRANSACTION;

INSERT INTO import_orders (order_id, customer_id, status, total_amount)
VALUES
    (3001, 501, 'NEW', 10.00),
    (3002, 502, 'NEW', 20.00),
    (3003, 503, 'NEW', 30.00);

INSERT INTO import_orders (order_id, customer_id, status, total_amount)
VALUES
    (3004, 504, 'NEW', 40.00),
    (3005, 505, 'NEW', 50.00);

COMMIT;
```

If the transaction fails before commit, InnoDB can `ROLLBACK` all transactional changes. This fits when business logic demands all-or-nothing atomicity across the entire batch and transaction scale stays within operational limits.

### Commit Per Batch

For very large datasets, split into multiple smaller transactions:

```sql
START TRANSACTION;

INSERT INTO import_orders (order_id, customer_id, status, total_amount)
VALUES
    (4001, 501, 'NEW', 10.00),
    (4002, 502, 'NEW', 20.00);

COMMIT;

START TRANSACTION;

INSERT INTO import_orders (order_id, customer_id, status, total_amount)
VALUES
    (4003, 503, 'NEW', 30.00),
    (4004, 504, 'NEW', 40.00);

COMMIT;
```

Committing per batch bounds lock duration and undo/redo volume per transaction. In return, if batch three fails, the first two batches remain committed. The job needs checkpointing, retry logic, and a way to recognize already-loaded records.

Never open a transaction and hold the connection while waiting on file reads, external APIs, or user input. Prepare data outside the transaction whenever possible, then open the transaction only for the duration needed to write.

## 5. Batch UPDATE and DELETE

Batch DML is not limited to INSERT. When updating or deleting large row counts, split by key ranges or time windows.

### Key-Range UPDATE

```sql
UPDATE orders
SET status = 'EXPIRED'
WHERE order_id > 100000
  AND order_id <= 110000
  AND status = 'PENDING';
```

After checking affected rows, commit and save checkpoint `110000`. The next batch handles the next range. The batching column should be indexed so each batch does not scan the entire table.

### Chunked DELETE

For single-table DELETE, MySQL supports `ORDER BY` and `LIMIT`:

```sql
DELETE FROM audit_events
WHERE created_at < '2024-01-01'
ORDER BY created_at, event_id
LIMIT 1000;
```

Repeat in batches until no matching rows remain. Include a tie-breaker key in `ORDER BY` for deterministic order when multiple rows share timestamps. Monitor rows deleted and duration per batch.

### Using CASE to Update Differing Values

When each key requires a different new value, a single UPDATE can use CASE:

```sql
UPDATE inventory
SET quantity = CASE product_id
    WHEN 101 THEN 25
    WHEN 102 THEN 40
    WHEN 103 THEN 12
    ELSE quantity
END
WHERE product_id IN (101, 102, 103);
```

For very long lists, CASE statements also grow statement size. Chunk batches and measure packet size just like multi-row INSERTs.

## 6. Choosing Batch Size

No single batch size is optimal for every table. The right size depends on:

- Average row size and large payloads such as `TEXT`, `BLOB`, or JSON.
- Number of indexes and constraints to update.
- Triggers, generated columns, and secondary write work.
- Disk I/O, CPU, redo log throughput, and buffer pool capacity.
- Concurrency with other queries and transactions.
- Packet limits on server, client, and driver.
- Acceptable rollback duration and replication lag targets.

Measure both row count and byte size. A 1,000-row batch of tiny integers behaves very differently from 1,000 rows containing hundreds of kilobytes of JSON or megabytes of BLOBs.

### Process for Finding Batch Size

1. Start with a small batch, such as 100 or 500 rows, in a test environment.
2. Measure payload bytes, execution time, commit time, and affected row count.
3. Increase batch size in controlled steps (e.g., doubling) until throughput plateaus or saturation signs appear.
4. Watch p95/p99 latency of other workloads, lock waits, redo log pressure, disk I/O, and replication lag.
5. Pick a size safely below the point where variance spikes to maintain headroom.
6. Re-measure whenever row width, BLOB ratio, or concurrency changes.

Do not treat the largest batch that fits inside a packet as your default operational batch size. Packet limit is merely a technical ceiling; transactions and server resources can overload long before hitting that limit.

## 7. MySQL Packets and max_allowed_packet

Client and server exchange commands and results over the MySQL protocol. A logical **packet** can carry a SQL statement, a data chunk, or a result row. `max_allowed_packet` caps the size of any packet or intermediate string MySQL handles.

If a client sends a statement or payload exceeding server/client limits, MySQL may return `ER_NET_PACKET_TOO_LARGE` (typically error code 1153) and close the connection. Applications must handle closed connections rather than assuming only the statement failed while the connection remains usable.

Check server limits:

```sql
SHOW GLOBAL VARIABLES LIKE 'max_allowed_packet';
SHOW SESSION VARIABLES LIKE 'max_allowed_packet';
```

Displayed values are in bytes. `max_allowed_packet` is the server-side cap; client libraries or CLI tools may also enforce their own limits. Payloads must fit within limits on both ends.

### Changing Server-Side Limits

Where dynamic updates are supported, administrators can adjust the GLOBAL value:

```sql
SET GLOBAL max_allowed_packet = 67108864;
```

This example sets 64 MiB (`64 × 1024 × 1024` bytes). Required privileges depend on MySQL version and administrative grants. Changing GLOBAL does not necessarily update values already cached by existing sessions; verify with a fresh connection and confirm behavior on your MySQL version.

To persist across restarts, configure under `[mysqld]` in the server config file:

```ini
[mysqld]
max_allowed_packet=64M
```

Do not raise the limit to maximum by default. Large packets allocate per-connection buffers and heighten memory risk when many clients send huge payloads concurrently.

### Client-Side Limits

The MySQL command-line client has its own option:

```bash
mysql --max-allowed-packet=64M -u app_user -p app_db
```

For applications, check your driver or connector configuration. Some libraries enforce their own packet settings; not every client automatically adopts the server's setting. If the server accepts 64 MiB while the client caps at 16 MiB, payloads exceeding the client limit still fail before reaching the server.

## 8. How Does max_allowed_packet Differ from net_buffer_length?

`net_buffer_length` is the initial size of the communication buffer; the buffer can grow as needed up to the packet limit. It is not a maximum cap replacing `max_allowed_packet`.

Inspect:

```sql
SHOW VARIABLES LIKE 'net_buffer_length';
SHOW VARIABLES LIKE 'max_allowed_packet';
```

There is no need to increase `net_buffer_length` just for large batches. Determine actual packet size, server/client limits, and memory needs first. Also distinguish packet size from transaction size: a transaction can send many small packets over its lifetime yet still generate huge undo/redo volume.

## 9. Estimating Payload Size and Handling Large Data

Multi-row SQL size depends on row count, data types, string lengths, encoding, and how the client serializes parameters. With literal SQL, quotes and escape characters make the statement longer than raw data. With prepared statements, parameters may travel over the binary protocol, yet payloads must still stay within client/server limits.

A simple approximation:

\[
\text{Batch payload} \approx
\text{statement overhead} +
\sum_{i=1}^{N}\text{encoded row}_i
\]

This is an approximation, not an exact wire-byte formula. Measure actual serialized payload sizes from the client or safe test logs. Never log sensitive values just to measure payload size.

For large BLOBs or JSON:

- Bound batch size by total bytes, not row count alone.
- Consider sending large payloads individually or using streaming/`LOAD DATA` where appropriate.
- Avoid duplicating large payloads across multiple application buffers.
- Ensure client, proxy, and server timeouts accommodate transfer duration.
- Do not raise packet limits when the root issue is unbounded batching.

## 10. Duplicate Keys and Idempotent Reloading

A batch job may be retried after a timeout or dropped connection. If a batch already committed yet the client never received the acknowledgment, resending it can trigger duplicate key errors. Define a clear policy.

### Standard INSERT

```sql
INSERT INTO import_orders (order_id, customer_id, status, total_amount)
VALUES
    (5001, 501, 'NEW', 10.00),
    (5002, 502, 'NEW', 20.00);
```

If the primary key already exists, the statement fails with a duplicate key error. Never retry the same payload blindly without verifying state.

### INSERT IGNORE

```sql
INSERT IGNORE INTO import_orders
    (order_id, customer_id, status, total_amount)
VALUES
    (5001, 501, 'NEW', 10.00),
    (5002, 502, 'NEW', 20.00);
```

`IGNORE` suppresses certain duplicate errors and downgrades certain data errors to warnings or adjusted values depending on context. Some rows may fail to load as expected while the statement still reports success. Inspect warnings and affected row counts; never use `IGNORE` as a blanket tool to hide data bugs.

### INSERT ... ON DUPLICATE KEY UPDATE

If you want to update existing rows:

```sql
INSERT INTO import_orders
    (order_id, customer_id, status, total_amount)
VALUES
    (5001, 501, 'PAID', 10.00),
    (5002, 502, 'PAID', 20.00) AS incoming
ON DUPLICATE KEY UPDATE
    status = incoming.status,
    total_amount = incoming.total_amount;
```

Row aliases in this syntax are supported in newer MySQL 8.0 versions; verify syntax against your target version. Older docs may show `VALUES(column)`, though `VALUES()` inside `ON DUPLICATE KEY UPDATE` was deprecated starting in MySQL 8.0.20.

`ON DUPLICATE KEY UPDATE` triggers on conflict with any unique key. If a table has multiple unique keys, understand which key can conflict and whether the updated row corresponds to the intended business entity. Upserts do not automatically make operations idempotent if the UPDATE branch accumulates counters or causes side effects.

## 11. Batch Checkpointing and Safe Retries

For large data jobs, track progress using a stable key. For example, each batch processes a contiguous range of `order_id`:

```sql
CREATE TABLE import_job_checkpoint (
    job_name VARCHAR(100) PRIMARY KEY,
    last_order_id BIGINT NOT NULL,
    updated_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP
        ON UPDATE CURRENT_TIMESTAMP
) ENGINE = InnoDB;
```

Application workflow:

1. Read the latest committed `last_order_id`.
2. Select the next bounded key range.
3. Within the same transaction, write target rows and update the checkpoint.
4. Commit both data and checkpoint together.
5. If the connection drops, read the checkpoint on a fresh connection and resume from the committed watermark.

If the checkpoint is updated outside the data transaction, two failure states arise: the checkpoint advances ahead of data (skipping rows on resume) or data commits without updating the checkpoint (reloading duplicates). Placing both in the same InnoDB transaction keeps progress state consistent.

If the source lacks an ascending key, use a unique business key or a staging table with processing status. Avoid large `OFFSET` for chunking because later pages must scan and skip many rows; keyset/range pagination on a stable index is usually far more efficient.

## 12. Common Errors When Batches Are Too Large

| Symptom | Possible cause | How to handle |
| --- | --- | --- |
| `ER_NET_PACKET_TOO_LARGE` / connection closed | Packet exceeded server or client limit. | Measure payload, shrink batch, or tune limits carefully on both ends. |
| Duplicate entry | Retried committed batch or duplicate source keys. | Check checkpoint, enforce idempotency keys, and define upsert policy. |
| Lock wait timeout | Batch holds locks too long or contends with other workloads. | Reduce transaction size, add filtering indexes, and adjust scheduling. |
| Deadlock | Concurrent transactions update the same row set in different orders. | Standardize key ordering, keep transactions short, and retry victim transactions. |
| Prolonged rollback | Single transaction modified too many rows. | Split into smaller batches and design checkpoint/resume. |
| Replication lag | Batch generates heavy binlog volume or replica lags behind. | Reduce batch size, monitor lag, and tune load schedule. |
| Throughput stops scaling with larger batches | Bottleneck shifted to I/O, index maintenance, redo, or locks. | Measure CPU/I/O, redo, page flushing, concurrency, and commit time. |
| Client memory spikes | Building entire payload in RAM before sending. | Stream data, bound buffers, and chunk batches by bytes. |

In InnoDB, a deadlock picks one transaction as victim and rolls it back; applications should retry the entire transaction under bounded retry/backoff rules. Never retry a single statement from a rolled-back transaction without rebuilding business state.

## 13. Measuring Batch Performance

Record at least these metrics for each batch size:

- Succeeded rows and skipped/updated rows.
- Payload bytes and statement count sent.
- Transfer time, execution time, and commit time.
- Throughput (rows/second) and p50/p95/p99 latency.
- Rows examined, warnings, duplicate count, and errors.
- CPU, disk I/O, redo log pressure, lock waits, and replication lag.

Example benchmark table:

| Batch rows | Payload bytes | Insert time | Commit time | Rows/sec | p95 latency | Errors |
| ---: | ---: | ---: | ---: | ---: | ---: | --- |
| 100 | Measure actual | Measure actual | Measure actual | Compute from results | Measure across runs | Record |
| 500 | Measure actual | Measure actual | Measure actual | Compute from results | Measure across runs | Record |
| 1,000 | Measure actual | Measure actual | Measure actual | Compute from results | Measure across runs | Record |
| 5,000 | Measure actual | Measure actual | Measure actual | Compute from results | Measure across runs | Record |

Never treat illustrative numbers as performance guarantees. The same 1,000-row batch can perform vastly differently depending on row width, indexes, cache state, hardware, and concurrent transactions.

## 14. Safe Operational Workflow

1. Identify data source, row count, row width, and duplicate-handling requirements.
2. Check `max_allowed_packet` on server and client/driver; verify timeouts and required privileges.
3. Choose multi-row INSERT, `INSERT ... SELECT`, or `LOAD DATA` based on source type.
4. Pick batch size by both row count and total bytes; start small and benchmark.
5. Decide transaction boundaries: all-or-nothing vs commit per batch.
6. Use stable keys/checkpoints to support safe resume after failure.
7. Measure execution and commit time, throughput, tail latency, lock waits, and replication lag.
8. Verify row counts, duplicates, warnings, and business correctness after every batch.
9. Test rollback and resume in a test environment before running long production jobs.

In production, include rate limiting, pause/stop controls, and alerts if latency or replication lag crosses operational thresholds. A bulk data job must never saturate I/O or starve online queries.

## 15. Self-Check Exercises

1. Why is multi-row INSERT usually faster than sending one INSERT per row?
2. Distinguish statement size from transaction size.
3. When is `INSERT ... SELECT` better than routing data through the client?
4. Why is `LOAD DATA` usually well suited for large files?
5. What does `max_allowed_packet` limit? Why must you check both server and client?
6. How does `net_buffer_length` differ from `max_allowed_packet`?
7. Why must batches with large BLOBs/JSON be bounded by bytes rather than row count alone?
8. Compare `INSERT IGNORE` and `INSERT ... ON DUPLICATE KEY UPDATE`.
9. Why should checkpoints be committed inside the same transaction as target data?
10. List metrics to monitor when increasing batch size and explain signs a batch has grown too large.

Batch DML succeeds when it cuts overhead while keeping transactions within resource bounds. Size batches by **row count and byte count**, define clear **commit boundaries**, handle **retries/idempotency**, and measure **throughput, latency, and cross-workload impact** before putting jobs into production.

# Batching, Transaction Control, and Avoiding WAL Spikes in PostgreSQL

## 1. The Problem: Ingesting a Million Rows Is Not Just Running a Million INSERTs

An e-commerce system needs to import orders, synchronize inventory history, patch legacy data, or purge expired records. When data volume is a few hundred rows, a single `INSERT` or `UPDATE` usually finishes quickly. At millions to hundreds of millions of rows, however, an unsuitable design can create severe issues:

- A single transaction holds row locks for too long, forcing other transactions to wait.
- WAL (Write-Ahead Log) grows rapidly, filling the `pg_wal` disk or disrupting archiving and replication.
- Checkpoints and full-page image (FPI) writes generate extra I/O, causing periodic latency spikes.
- Replicas fall behind replaying WAL, making replica reads stale.
- `UPDATE`/`DELETE` leaves dead tuples behind, bloating tables and indexes so autovacuum struggles to keep up.
- Batches that are too small trigger excessive `COMMIT`s, network round trips, and `fsync`s.
- Batches that are too large make rollbacks, recovery, and retries expensive.
- A CSV file with one malformed line fails the entire `COPY` command with no way to restart from a business checkpoint.
- Retry jobs after a failure can duplicate data if unique keys and idempotency are missing.
- Dangerous "optimizations" such as disabling `fsync` or `full_page_writes` compromise data durability and crash recovery.

Therefore, **batching** is not simply slicing data into equal-row-count chunks. It is how you **control cost, resource usage, lock duration, WAL volume, recoverability, and transaction integrity**.

### 1.1. Objectives

After this lesson, you will be able to:

1. Explain the nature of WAL, logging before data pages, and why `INSERT`/`UPDATE`/`DELETE`/`COPY` generate WAL.
2. Distinguish transactions from batches, statements, pages, and checkpoints.
3. Size batches by row count, byte size, execution duration, WAL delta, and live system load.
4. Implement CSV imports via `COPY`/`\copy`, staging, and idempotent merges.
5. Design batched SQL `UPDATE`/`DELETE` statements using CTEs for deterministic key selection since PostgreSQL does not support `UPDATE ... LIMIT` directly.
6. Control `BEGIN`, `COMMIT`, `ROLLBACK`, savepoints, autocommit, and retry boundaries.
7. Observe WAL using `pg_current_wal_lsn()`, `pg_wal_lsn_diff()`, `pg_stat_wal`, and related metrics.
8. Understand the impact of `full_page_writes`, checkpoints, `wal_compression`, `max_wal_size`, replication slots, and archive backlogs.
9. Apply lock/transaction timeouts, MVCC awareness, vacuuming, and replica-lag monitoring during batch jobs.
10. Distinguish `INSERT` vs. `DELETE` optimizations using `UNLOGGED` tables, partition detach/drop, indexing strategies, and `TRUNCATE`.
11. Design resumable imports with checkpoints that preserve consistency and prevent duplicate processing upon worker crashes.
12. Complete hands-on exercises with solutions and build safe operational runbooks.

### 1.2. Target Use Cases

- Importing data from CSV files, ETL/ELT pipelines, and migrations.
- Backfilling columns or performing multi-batch schema transitions.
- Purging retention-expired data or cleaning up large event tables.
- Synchronizing external data sources through staging tables.
- Performing controlled remediation of corrupted data.
- Ingesting high-volume event logs.
- Accelerating ingestion while protecting backups and replication.

> **Safety note:** run examples that execute real DML only in a test database or under an approved change plan. Never run `DROP`/`TRUNCATE`/`ALTER TABLE ... SET UNLOGGED` or weaken durability settings in production solely to reduce WAL. Monitoring queries may require dedicated privileges; never grant superuser privileges to an application role.

---

## 2. End-to-End Architecture: From Input to Commit and Replica

~~~mermaid
flowchart TD
    S["CSV file / batch from application"] --> V["Validate input / select business keys"]
    V --> B["Batch of N rows or N MiB"]
    B --> T["BEGIN transaction"]
    T --> W["COPY/INSERT/UPDATE/DELETE"]
    W --> L["WAL records + data buffers"]
    L --> C{"Statement succeeded?"}
    C -- "No" --> R["ROLLBACK batch, quarantine/retry"]
    C -- "Yes" --> K["COMMIT batch"]
    K --> N["Update ingest checkpoint"]
    N --> M["Measure WAL bytes, lag, latency, locks"]
    M --> P{"More data?"}
    P -- "Yes" --> B
    P -- "No" --> E["Reconcile counts/checksums; complete"]
    L --> A["WAL archive / physical replication"]
    A --> Q["Replica replay / point-in-time recovery"]
~~~

The diagram illustrates dependencies, but the **ingest checkpoint** should be written **in the same transaction as the business changes** whenever atomicity is required. An application that commits to the database and then records file progress in a separate service without a shared transaction can fail between those two steps; idempotent keys and reconciliation are essential.

### 2.1. Four Dimensions to Balance Simultaneously

| Dimension | Risk of overly small batches | Risk of overly large batches |
|---|---|---|
| Throughput (rows/s) | High `COMMIT` and round-trip overhead | Less overhead, but can trigger I/O bursts |
| Latency and locks | Easier resource yielding between batches | Long-held transaction locks hurting OLTP |
| WAL/replication | Steadier WAL stream | Large WAL bursts, spiking replication lag |
| Retry/recovery | Frequent checkpoints, easy resume | Expensive rollback/retry of huge data blocks |

No single batch size fits every table. Tables with large `JSONB` columns, many indexes, triggers, or foreign keys behave very differently in WAL and locking compared to simple tables.

### 2.2. Terminology

- **Batch:** a processing unit chosen by the application or job, such as 5,000 rows.
- **Transaction:** the unit of atomicity that PostgreSQL `COMMIT`s or `ROLLBACK`s.
- **Statement:** a single SQL command, such as `COPY` or `UPDATE`.
- **Chunk:** a slice of the source dataset, file, or key range being processed.
- **Ingest checkpoint:** a business progress position processed and confirmed committed, *distinct* from a PostgreSQL database checkpoint.
- **Database checkpoint:** a PostgreSQL engine operation that flushes eligible dirty pages to establish a crash-recovery baseline in relation to WAL.
- **WAL LSN:** a logical position in the WAL stream used to measure WAL volume and replication progress.

---

## 3. What Is WAL?

### 3.1. Write-Ahead Logging

PostgreSQL follows the principle of logging changes before the corresponding data pages are considered durably written. When a transaction modifies rows, the server writes WAL records describing the changes needed for crash recovery and, when configured, physical replication and archiving.

~~~text
UPDATE / INSERT / DELETE
          |
          v
     Changes in buffers
          |
          +--> WAL records written to WAL buffers
                       |
                       v
                 WAL flushed per durability rules
                       |
                       v
                 COMMIT can be acknowledged
          |
          +--> Dirty data pages flushed to data files later
~~~

Internal details are more intricate than the diagram, but the key point is that **the database does not need to flush every data page immediately at COMMIT** to guarantee durability under standard configuration: WAL provides recovery for all necessary changes.

### 3.2. What Roles Does WAL Serve?

1. **Crash recovery:** replays WAL to restore a consistent state after a failure.
2. **Physical streaming replication:** the primary streams WAL to standbys.
3. **Point-in-time recovery:** combines a base backup with the WAL archive to recover to a specific point in time as configured.
4. **Logical decoding/replication:** interprets changes via logical slots/protocols in suitable environments.

WAL is not a "debug log" that you can delete manually to free disk space.

### 3.3. Why Can Updating a Single Row Write Many Bytes of WAL?

WAL can include:

- Records modifying the heap tuple/page.
- Index updates requiring WAL depending on the operation.
- Full-page images (FPIs) under qualifying conditions.
- Transaction-related records.
- Secondary effects from triggers, foreign keys, partition maintenance, and auxiliary statements.
- Overhead from HOT vs. non-HOT updates, page layout, and vacuum/freeze activity.

Consequently, **row count alone cannot predict WAL bytes**.

### 3.4. WAL vs. Data Files and Archives

| Component | Purpose |
|---|---|
| `pg_wal` | Directory of active WAL segments retained by PostgreSQL for recovery/replication/archiving |
| Data files | Current state of table heap and index pages |
| WAL archive | Archived WAL copies used for backups/PITR via archiving |
| Replica WAL receive/replay | Tracks WAL received and replayed by a physical standby |
| Logical slot | Retains WAL position needed for decoding/consumers; can cause WAL retention |

Never **manually delete files inside `pg_wal`** simply because the directory looks full. Those segments may still be required for crash recovery, replication slots, or archiving.

### 3.5. WAL and Rolled-Back Transactions

DML executed prior to a `ROLLBACK` still generates WAL; rolling back makes **the data logically uncommitted**, but it does not erase the WAL bytes already emitted. Running and rolling back a massive `UPDATE` **is not** a free test with zero disk or WAL cost.

---

## 4. Transaction Boundaries and Batch Size

### 4.1. One Giant Transaction

~~~sql
BEGIN;

-- COPY/INSERT a very large volume of data
-- UPDATE many millions of rows
-- DELETE many millions of rows

COMMIT;
~~~

Advantage: all changes either succeed or roll back together. Trade-offs:

- Holds transactions and locks open for a long time.
- Raises retry cost if an error occurs near the end of the batch.
- Increases WAL retention and replica lag.
- `UPDATE`/`DELETE` creates dead tuples that require vacuuming afterward rather than being incrementally reclaimed across prior commits.
- Long-running jobs affect snapshot/transaction age and lock patterns across the system.
- Provides no application-level checkpoint after each chunk.

### 4.2. Many Smaller Transactions

~~~text
Batch 1: BEGIN -> DML rows 1..5000 -> COMMIT
Batch 2: BEGIN -> DML rows 5001..10000 -> COMMIT
Batch 3: BEGIN -> DML rows 10001..15000 -> COMMIT
...
~~~

Advantages: bounded lock lifetimes, easy pause/resume, smaller rollback scope, and an opportunity to pace WAL bursts.

In return, data commits **incrementally** and the overall job is no longer globally atomic. Readers may observe intermediate states. You must design publication/cutover or staging mechanisms if business rules demand "publish only once everything finishes."

### 4.3. How Can Batch Size Be Measured?

- Row count (e.g., 1,000–10,000).
- Input byte size (e.g., MiB of CSV, especially when row lengths vary widely).
- Execution time per batch (e.g., targeting hundreds of milliseconds to a few seconds depending on SLOs).
- WAL bytes generated per batch.
- Lock waits, replication lag, and p95 latency.
- CPU/I/O load during the job.

These example numbers **are not optimal defaults**. Choose batch sizes through benchmarks and real system guardrails.

### 4.4. One Batch Does Not Necessarily Equal One SQL Statement

A single transaction may include:

~~~sql
BEGIN;
INSERT INTO staging ...;
INSERT INTO destination ... SELECT ... FROM staging ...;
UPDATE import_progress ...;
COMMIT;
~~~

When multiple steps belong to **one business batch**, place them in the same transaction if all-or-nothing semantics are required. Never `COMMIT` after inserting into the destination and then update progress separately if doing so could cause duplicate retries.

---

## 5. ACID When Batching

### 5.1. Per-Batch Atomicity

Once you split a job into 100 transactions, PostgreSQL guarantees atomicity **only per transaction**. If batch 37 fails, the 36 previously committed batches remain durable.

Therefore, the job must support:

- Resuming from a valid checkpoint.
- Idempotent replay.
- End-of-job validation.
- Job states: `pending`, `running`, `failed`, `complete`.
- A safe cutover mechanism if readers must not see partial data.

### 5.2. Consistency and Constraints

Splitting a batch can temporarily leave data business-incomplete. For example, loading `orders` before `order_items` might expose orders without line items to readers. If that is unacceptable, load into **staging**, then publish via a transaction/partition swap or a `dataset_version` flag at the end.

### 5.3. Isolation and Concurrency

Under `READ COMMITTED`, consecutive transactions in a job can observe different data snapshots because of concurrent writers. With explicit keyset pagination predicates and idempotency, that may be intentional. If a job needs a single consistent snapshot of the entire dataset, you must establish appropriate isolation/versioning or writer coordination; a sequence of `READ COMMITTED` transactions does not automatically equal a single snapshot.

### 5.4. Durability

When `COMMIT` is acknowledged under the configured durability settings, PostgreSQL guarantees durability accordingly. Trading off `synchronous_commit` for higher throughput risks losing recent commits upon a crash. Do not disable durability casually.

### 5.5. Commit "Job Complete" With Final Data Verification

In systems requiring end-of-job guarantees, publish the completion state in a transaction only after reconciliation succeeds. Job metadata must reflect actual committed data, not merely "finished reading the input file."

---

## 6. Choosing Batching Strategies for INSERT

### 6.1. Single-Row INSERT with Autocommit

Conceptual example:

~~~sql
INSERT INTO app.events(event_id, payload) VALUES (1, '{}');
INSERT INTO app.events(event_id, payload) VALUES (2, '{}');
INSERT INTO app.events(event_id, payload) VALUES (3, '{}');
~~~

If each statement commits individually, network round trips and commit overhead become prohibitive across millions of rows.

### 6.2. Multi-Row INSERT

~~~sql
INSERT INTO app.events(event_id, payload)
VALUES
  (1, '{"kind":"open"}'),
  (2, '{"kind":"click"}'),
  (3, '{"kind":"close"}');
~~~

One statement inserts multiple rows, cutting SQL round trips. In Java, use bind parameters and batching APIs rather than concatenating untrusted literal strings.

### 6.3. Set-Based INSERT ... SELECT

~~~sql
INSERT INTO app.events_archive(event_id, payload)
SELECT event_id, payload
FROM app.events
WHERE event_id BETWEEN 1000 AND 2000;
~~~

When data already resides inside PostgreSQL, set-based `INSERT ... SELECT` avoids shipping every row through the application tier. It still generates WAL and affects destination indexes, constraints, and triggers.

### 6.4. COPY for Bulk Ingestion

`COPY FROM` is PostgreSQL's optimized bulk-loading path for many workloads. It usually outperforms individual per-row `INSERT`s, particularly when reading from files or streams and deferring SQL transformations until after landing.

**COPY does not commit automatically in chunks:** one `COPY FROM` is a single statement within the current transaction. If you want per-chunk commits, split the file or stream into separate `COPY` commands or SQL batches under separate transaction boundaries.

### 6.5. Very Large Single Statements Still Have Limits

A multi-row `INSERT` with hundreds of thousands of bind parameters can hit driver/protocol parameter limits, memory bounds, parser overhead, or statement-size limits. Do not construct a multi-gigabyte SQL string; use JDBC batching or `COPY` streams and benchmark appropriate chunk sizes.

---

## 7. Self-Contained SQL Lab: Schema and Sample Data

The following examples use the `wal_batch_lab` schema. Run them in a test database where you have `CREATE TABLE`/`CREATE SCHEMA` privileges. Sample names and IDs are synthetic.

### 7.1. Create the schema

~~~sql
CREATE SCHEMA IF NOT EXISTS wal_batch_lab;
~~~

### 7.2. Target table

~~~sql
CREATE TABLE wal_batch_lab.orders (
    order_id bigint PRIMARY KEY,
    customer_id bigint NOT NULL,
    amount numeric(12,2) NOT NULL CHECK (amount >= 0),
    order_status text NOT NULL
      CHECK (order_status IN ('new','paid','cancelled')),
    updated_at timestamptz NOT NULL DEFAULT clock_timestamp()
);

CREATE INDEX ix_wal_batch_orders_status_id
  ON wal_batch_lab.orders(order_status,order_id);
~~~

The status+ID index speeds up queries filtering by status and keyset pagination, though it adds write overhead for `INSERT`s and status `UPDATE`s.

### 7.3. Staging table

~~~sql
CREATE TABLE wal_batch_lab.order_stage (
    import_id bigint NOT NULL,
    source_row_no bigint NOT NULL,
    order_id bigint,
    customer_id bigint,
    amount numeric(12,2),
    order_status text,
    PRIMARY KEY (import_id, source_row_no)
);
~~~

Business columns in staging allow `NULL` so malformed inputs can be captured and validated before publishing. The staging primary key only prevents duplicate `(import_id, source_row_no)` rows; it does not guarantee `order_id` validity.

### 7.4. Job metadata table

~~~sql
CREATE TABLE wal_batch_lab.import_jobs (
    import_id bigint PRIMARY KEY,
    source_label text NOT NULL,
    last_committed_row bigint NOT NULL DEFAULT 0,
    status text NOT NULL DEFAULT 'pending'
      CHECK (status IN ('pending','running','failed','complete')),
    updated_at timestamptz NOT NULL DEFAULT clock_timestamp()
);
~~~

### 7.5. Seed sample rows

~~~sql
INSERT INTO wal_batch_lab.orders
    (order_id,customer_id,amount,order_status)
VALUES
    (101,11,120.00,'new'),
    (102,11, 75.50,'paid'),
    (103,12,250.00,'new'),
    (104,13,400.00,'cancelled'),
    (105,13, 90.00,'new'),
    (106,14, 55.00,'new');

INSERT INTO wal_batch_lab.import_jobs(import_id,source_label,status)
VALUES (9001,'orders-2026-11.csv','pending');
~~~

### 7.6. Inspect baseline data

~~~sql
SELECT order_id,customer_id,amount,order_status
FROM wal_batch_lab.orders
ORDER BY order_id;
~~~

Expected: 6 rows, with `order_status = 'new'` on IDs `101`, `103`, `105`, and `106`.

---

## 8. Practicing an INSERT Batch With a Checkpoint

### 8.1. Use an explicit transaction

~~~sql
BEGIN;

INSERT INTO wal_batch_lab.order_stage
    (import_id,source_row_no,order_id,customer_id,amount,order_status)
VALUES
    (9001,1,201,21,10.00,'new'),
    (9001,2,202,21,20.00,'new'),
    (9001,3,203,22,30.00,'paid');

UPDATE wal_batch_lab.import_jobs
   SET last_committed_row=3,
       status='running',
       updated_at=clock_timestamp()
 WHERE import_id=9001;

COMMIT;
~~~

When `COMMIT` succeeds, both the staging rows and the checkpoint commit in the same transaction. If a failure occurs before `COMMIT` and the transaction rolls back, neither the rows nor the checkpoint advance.

### 8.2. Quick post-commit verification

~~~sql
SELECT import_id,source_row_no,order_id
FROM wal_batch_lab.order_stage
WHERE import_id=9001
ORDER BY source_row_no;

SELECT import_id,last_committed_row,status
FROM wal_batch_lab.import_jobs
WHERE import_id=9001;
~~~

Expected: 3 rows and `last_committed_row = 3`.

### 8.3. Why shouldn't the checkpoint advance before writing rows?

If `last_committed_row = 3` commits first and inserting rows fails afterward, the next run skips rows `1..3` and loses data. When the checkpoint shares the same transaction as the rows, normal transaction semantics prevent a state where "the checkpoint advanced while the rows did not commit."

### 8.4. What if the source has unstable row numbering?

Do not use an unstable file offset as a resume cursor. For message streams, use the source offset/partition paired with an idempotency key. For object-storage files, combine a file checksum/version with the row number to detect file changes. Once a source changes, the old checkpoint is no longer valid.

---

## 9. Importing CSV Files: COPY and \copy

### 9.1. Server-side COPY

~~~sql
COPY wal_batch_lab.order_stage
    (import_id,source_row_no,order_id,customer_id,amount,order_status)
FROM '/server/data/orders-batch-001.csv'
WITH (FORMAT csv, HEADER true);
~~~

This command requires the file to reside **on the PostgreSQL server filesystem** and requires appropriate server-file read privileges (which are highly sensitive). Do not use this in production when the application only holds the file on the client side.

### 9.2. Client-side \copy in psql

~~~text
\copy wal_batch_lab.order_stage (import_id,source_row_no,order_id,customer_id,amount,order_status) FROM '/client/data/orders-batch-001.csv' WITH (FORMAT csv, HEADER true)
~~~

`\copy` is a **psql meta-command** that reads a local file on the client machine running `psql` and streams it via `COPY FROM STDIN`; it is not standalone SQL you can send through a JDBC `Statement`.

### 9.3. COPY FROM STDIN in applications

Client drivers can support streaming `COPY` from an `InputStream` or `Reader`, such as pgJDBC's `CopyManager`. Using the driver's streaming API avoids storing large files on the server or issuing millions of `INSERT` statements.

### 9.4. CSV with HEADER

Sample file:

~~~csv
import_id,source_row_no,order_id,customer_id,amount,order_status
9001,4,204,22,45.00,new
9001,5,205,23,80.50,paid
9001,6,206,24,90.00,new
~~~

`HEADER true` skips the leading header line per CSV `COPY` syntax. Column count and order must match the `COPY` column list; CSV quoting and `NULL` parsing must be configured properly when values contain commas, quotes, or embedded newlines.

### 9.5. COPY is a single statement, not automatic micro-transactions

~~~sql
BEGIN;
COPY ... FROM STDIN ...;
COMMIT;
~~~

If an entire file streams through a single `COPY` in one transaction, an error halfway through fails the whole statement while still having consumed WAL and processing resources for the preceding rows. To make ingestion restartable per segment, split the stream into multiple `COPY` invocations/batches, each with its own transaction and checkpoint.

---

## 10. Handling Errors During COPY

### 10.1. Type mismatches

For example, `amount='not-a-number'` in a `numeric` column fails `COPY`. If the client does not handle the error and leaves the transaction in an aborted state, subsequent SQL statements will fail until `ROLLBACK`.

### 10.2. CSV NULL vs. empty strings

CSV distinguishes empty fields, quoted empty strings, explicit `NULL` markers, and `COPY` options:

- `NULL ''` or another marker per option.
- `FORCE_NULL` / `FORCE_NOT_NULL` per column where supported.
- Quotes and escape characters.

Never assume an empty string means `0`; validate business semantics before merging.

### 10.3. Instead of silently ignoring errors

Many pipelines use `text` columns in a raw staging table to load CSV rows first, then validate and route bad rows out. This preserves rejection reasons instead of letting one bad line abort the entire file. However, text staging alone does not solve encoding issues, CSV quoting, payload size limits, duplicates, or malicious input; you must still validate and bound inputs.

### 10.4. Version-dependent error handling options

Newer PostgreSQL versions include additional `COPY` options to tolerate or log conversion errors in supported cases. Such features are **version-dependent** and do not replace constraints or triggers in every scenario. This lesson uses a portable pattern: land in staging, validate, and reject or route errors through controlled SQL.

### 10.5. Failed COPY commands can leave dead tuples behind

`COPY FROM` may already have inserted tuples before hitting an error; when the statement rolls back, uncommitted tuples are invisible to valid queries yet can still occupy physical heap/index space until `VACUUM` reclaims them under PostgreSQL's storage model. With huge files and frequent failures, space and I/O overhead can be substantial even when zero rows commit.

### 10.6. Operational pattern

1. Split input into chunks with verifiable boundaries.
2. `COPY` a chunk into staging inside a transaction.
3. Validate rows and route rejected/quarantined rows.
4. Merge the batch, or publish only once all rows satisfy policy.
5. Commit data and checkpoint in the same transaction.
6. On failure: roll back the chunk, log error class and sanitized row references, fix or quarantine, and resume per contract.
7. Reconcile total accepted, rejected, and duplicate counts.

---

## 11. Why Importing Into Staging Before Merging Is Safer

### 11.1. Separate validation from production data

Incoming data can contain:

- Non-existent customer IDs.
- Duplicate order IDs.
- Negative amounts.
- Status values outside the allowed set.
- Re-ingested rows from retries.
- Malformed encoding or types.
- Duplicate rows within the same file.

If you `COPY` straight into a production table with multiple indexes, triggers, and constraints, one invalid row or duplicate rolls back the entire statement. Staging lets you inspect, quarantine, and enforce policy cleanly before publishing.

### 11.2. Query to detect invalid rows

~~~sql
SELECT source_row_no,order_id,customer_id,amount,order_status,
       CASE
         WHEN order_id IS NULL THEN 'missing_order_id'
         WHEN customer_id IS NULL THEN 'missing_customer_id'
         WHEN amount IS NULL OR amount < 0 THEN 'invalid_amount'
         WHEN order_status NOT IN ('new','paid','cancelled')
              OR order_status IS NULL THEN 'invalid_status'
         ELSE 'valid'
       END AS validation_status
FROM wal_batch_lab.order_stage
WHERE import_id=9001
ORDER BY source_row_no;
~~~

Because `order_stage` uses typed `numeric`, non-numeric strings in the file still fail `COPY` before any row reaches `order_stage`. Capturing malformed text requires a raw-text staging table prior to casting.

### 11.3. Merging with INSERT ... ON CONFLICT

~~~sql
INSERT INTO wal_batch_lab.orders
    (order_id,customer_id,amount,order_status)
SELECT s.order_id,s.customer_id,s.amount,s.order_status
FROM wal_batch_lab.order_stage AS s
WHERE s.import_id=9001
  AND s.order_id IS NOT NULL
  AND s.customer_id IS NOT NULL
  AND s.amount >= 0
  AND s.order_status IN ('new','paid','cancelled')
ON CONFLICT (order_id) DO NOTHING;
~~~

`ON CONFLICT DO NOTHING` makes the operation retry-safe for duplicate primary keys, **but it can silently hide rows with the same ID and different payloads**. In financial systems or state synchronization pipelines, compare payload/version hashes instead of blindly treating every conflict as a harmless duplicate.

### 11.4. The multi-row same-ID UPSERT trap

`INSERT ... ON CONFLICT DO UPDATE` fails if a single statement tries to affect **the same destination row more than once** due to duplicate keys in the source batch. Before merging, deterministically pick one version using `DISTINCT ON ... ORDER BY` or explicit ranking/aggregation.

### 11.5. Preserve change ordering across batches

If the source emits multiple events for the same order, selecting the latest version must rely on a monotonic source sequence or business version—not merely `source_row_no` if data can arrive out of order. An unconditional `UPSERT` can overwrite newer state with stale data.

---

## 12. Sizing Batches and Setting a WAL Budget

### 12.1. There is no universal formula for every table

A "5,000-row batch" might generate:

- A few megabytes of WAL for narrow rows with few indexes.
- Tens or hundreds of megabytes of WAL if rows carry large `JSONB` payloads, update many indexes, trigger full-page images, or fire cascading triggers.

Always determine batch sizes empirically, then govern them using **row count + duration + bytes/replica lag**.

### 12.2. Illustrative policy tiers

| Tier | Example target | Rationale |
|---|---|---|
| Probing | 500 rows/batch | Measure initial WAL and latency |
| Light load | 2,000 rows/batch | Verify SLO headroom |
| Moderate load | 5,000 rows/batch | Balance throughput and checkpoints |
| Heavy load | 10,000 rows/batch | Use only while metrics stay within bounds |
| Overloaded | Shrink batch or pause | Triggered when replica lag, WAL/disk, or locks cross thresholds |

These numbers are **examples**, not production defaults to copy blindly. Pick thresholds based on live workloads and SLAs.

### 12.3. Do not optimize rows/s in isolation

A job reaching 100,000 rows/s while driving p99 API latency from 100ms to 3s and causing 15 minutes of replication lag is unacceptable. Budget for the whole system, not just ingest speed.

### 12.4. Can a batch contain multiple small transactions?

Yes, but be precise about scope when using the word "batch." This guide favors **one logical batch = one committed transaction** for clean checkpointing. If a large logical batch must span multiple transactions, metadata must track granular chunk state so resumes neither duplicate nor skip records.

---

## 13. Measuring WAL With LSN: pg_current_wal_lsn()

### 13.1. What is an LSN?

A **Log Sequence Number (LSN)** is a logical position in PostgreSQL's WAL stream, typically displayed in hexadecimal such as:

~~~text
0/16B6C50
0/16C4200
~~~

An LSN is neither a raw byte counter nor a timestamp. PostgreSQL provides `pg_wal_lsn_diff(lsn1, lsn2)` to compute the byte distance between two WAL positions in **bytes**.

### 13.2. Measuring before and after a batch

Open a monitoring session or run when no uncommitted transactions remain:

~~~sql
SELECT pg_current_wal_lsn() AS wal_before;
~~~

Run a batch and **COMMIT**:

~~~sql
BEGIN;

INSERT INTO wal_batch_lab.orders
  (order_id,customer_id,amount,order_status)
SELECT
  100000 + g,
  1000 + g % 200,
  ((g % 5000) + 1)::numeric / 10,
  'new'
FROM generate_series(1,2000) AS g
ON CONFLICT (order_id) DO NOTHING;

COMMIT;
~~~

Then capture the ending LSN:

~~~sql
SELECT pg_current_wal_lsn() AS wal_after;
~~~

Plug in the observed LSNs and calculate:

~~~sql
SELECT pg_wal_lsn_diff(
    '0/16C4200'::pg_lsn,
    '0/16B6C50'::pg_lsn
) AS wal_bytes;
~~~

The two LSNs in the final snippet are **illustrative placeholders**, not exact outputs you will see on your machine. Substitute your actual observed values.

### 13.3. What does the LSN delta measure?

The LSN difference reflects WAL generated between two points across the **cluster-wide WAL stream**, which includes concurrent sessions and background activity. It is not exclusively the WAL of your batch whenever other workload runs simultaneously.

### 13.4. Which LSN function should you use?

PostgreSQL exposes several LSN functions:

- `pg_current_wal_lsn()`: current WAL write position per the function's semantics.
- `pg_current_wal_insert_lsn()`: position where WAL records are inserted into WAL buffers.
- `pg_current_wal_flush_lsn()`: current flushed WAL position.

For an interpretable measurement, measure **before the batch, COMMIT, then after the batch**, documenting that it is a cluster-wide delta for the chosen LSN metric. Do not mix insert LSN with flush LSN to infer exact batch WAL.

### 13.5. Open transactions and LSN

Measuring `pg_current_wal_lsn()` while a transaction is still open may omit WAL yet to be emitted—including the `COMMIT` record itself. To compare committed batches, measure after `COMMIT` under relatively steady background load.

### 13.6. Converting bytes to MiB

~~~sql
SELECT
    pg_wal_lsn_diff('0/16C4200'::pg_lsn,
                    '0/16B6C50'::pg_lsn)
      / 1024 / 1024 AS wal_mib;
~~~

For example, `52,428,800` WAL bytes equals **50 MiB** (1 MiB = 1,048,576 bytes).

---

## 14. Measuring With pg_stat_wal

### 14.1. WAL statistics

On modern PostgreSQL versions, `pg_stat_wal` provides counters such as:

~~~sql
SELECT
    wal_records,
    wal_fpi,
    pg_size_pretty(wal_bytes) AS wal_bytes_pretty,
    wal_write,
    wal_sync,
    stats_reset
FROM pg_stat_wal;
~~~

Columns, update timing, snapshot mechanics, and required privileges can vary by major version. If your server lacks this view or certain columns, check your version's documentation rather than assuming identical behavior.

### 14.2. wal_bytes and wal_fpi

- **`wal_bytes`:** total WAL bytes recorded since stats were last reset per PostgreSQL semantics.
- **`wal_fpi`:** number of full-page images written to WAL.
- **`wal_records`:** number of WAL records, not number of SQL statements.

`wal_bytes` is a cluster-wide total, not broken down by table or application. Do not sample it once and attribute it solely to `import_job=9001`.

### 14.3. Measuring deltas

Record counters before and after a batch at two clean checkpoints:

~~~text
Before: wal_bytes = X
After:  wal_bytes = Y
Delta ≈ Y - X
~~~

Always check `stats_reset`: if counters were reset between samples, the delta is invalid. Concurrent sessions may also contribute WAL during the window.

### 14.4. Statistics visibility can lag

Server statistics are accumulated and surfaced with potential buffering/caching lag. Never build a tight loop controller that says "shrink batch if `wal_bytes` didn't jump after 1ms" based on tiny sample intervals.

### 14.5. pg_stat_wal vs. LSN

| Tool | Strength | Limitation |
|---|---|---|
| LSN diff | Exact WAL stream distance between two points | Includes all cluster workload |
| `pg_stat_wal.wal_bytes` delta | Reports bytes, WAL records, and FPI counts | Global counters, subject to resets and lag |
| WAL directory size | Reflects disk pressure | Not equal to WAL generation rate |
| `pg_stat_replication` | Shows sender state and replica lag | Does not directly report WAL bytes generated |
| `pg_stat_archiver` | Shows archive successes and failures | Does not measure import volume alone |

Combine multiple signals rather than treating a single metric as absolute truth.

---

## 15. pg_wal Disk Usage: Generating WAL vs. Retaining WAL

### 15.1. WAL generation vs. WAL retention

These are two distinct phenomena:

1. **WAL generation rate:** bytes of WAL per second written by active workloads.
2. **WAL retention:** WAL segments the server must retain for checkpoint recovery, archiving, replication slots, or other constraints.

A job can generate WAL quickly while archiving and replay keep pace, leaving `pg_wal` stable. Conversely, a moderate job can coincide with a stalled replica or slot, causing retained WAL to grow until disk fills.

### 15.2. max_wal_size is not a strict hard cap

`max_wal_size` is a soft target governing checkpoints and WAL recycling—not a hard quota guaranteeing `pg_wal` stays below X GB. WAL can exceed `max_wal_size` due to replication slots, stalled archiving, `wal_keep_size`, recovery needs, or other retention conditions.

### 15.3. Never manually delete WAL files

If `pg_wal` fills disk, never remove files by timestamp or segment name—doing so can destroy crash recovery, break standbys, or corrupt your PITR chain.

Instead, inspect:

- WAL generation rate.
- `pg_stat_archiver`.
- Replication slots and `restart_lsn`.
- Replica receive and replay lag.
- Checkpoint frequency.
- Backup and archiving health.
- Actual free disk space and growth trajectory.

### 15.4. Inspecting current WAL file usage

PostgreSQL offers administrative functions to inspect the WAL directory with appropriate privileges, and OS metrics monitor the `pg_wal` filesystem. Do not grant filesystem-read privileges to application accounts merely to populate a dashboard; use a proper monitoring agent or role.

### 15.5. WAL segment recycling

PostgreSQL recycles and reuses WAL segments rather than constantly creating and unlinking them. Therefore, the snapshot count or total size of files in `pg_wal` does not equal the WAL generated during a specific interval.

---

## 16. Checkpoints, Full-Page Writes, and WAL Spikes

### 16.1. What does a database checkpoint do?

Checkpoints flush dirty buffers to disk and establish crash-recovery reference points. Relevant settings include:

~~~sql
SHOW checkpoint_timeout;
SHOW max_wal_size;
SHOW min_wal_size;
SHOW checkpoint_completion_target;
SHOW full_page_writes;
SHOW wal_compression;
~~~

Defaults vary across PostgreSQL versions and managed providers. Never copy configuration values from old blog posts without benchmarking.

### 16.2. Why do checkpoints cause periodic WAL spikes?

With `full_page_writes = on` (the standard safe setting), the first modification to a data page after a checkpoint triggers writing a full-page image to WAL (under qualifying conditions) to protect against torn pages. Right after a checkpoint, a batch touching many pages can sharply increase FPIs.

### 16.3. FPIs are far larger than row deltas

A PostgreSQL page is 8 KiB in common builds; full-page images can make WAL dramatically larger than logical row changes alone. Enabling WAL compression and hole removal can shrink stored FPI sizes depending on data and settings.

### 16.4. Never turn off full_page_writes to "save WAL"

`full_page_writes` protects crash recovery against partial page writes. Disabling it risks silent corruption or unrecoverable databases after an OS/power crash. It is a data-safety setting, not a batch throughput knob.

### 16.5. wal_compression

`wal_compression` compresses full-page images in WAL, reducing bytes written at the expense of CPU cycles. Supported compression codecs depend on the PostgreSQL version and build; never assume one specific codec is available across all deployments.

Measure on your actual workload: check WAL size reduction, CPU impact, and replica/recovery overhead.

### 16.6. Overly frequent checkpoints

If WAL growth triggers checkpoints too often, frequent dirty-page flushing and repeated FPI bursts cause erratic throughput. Raising `max_wal_size` within your disk budget can reduce forced checkpoints, **but it will not cure unbounded WAL retention caused by a stuck replication slot**.

### 16.7. checkpoint_completion_target

This setting spreads checkpoint I/O over a larger fraction of the checkpoint interval to smooth bursts. Avoid guessing a number without measuring storage latency, OS writeback behavior, and checkpoint timings.

### 16.8. PostgreSQL version differences

Checkpoint metrics live in `pg_stat_bgwriter` on older versions and `pg_stat_checkpointer` on newer versions. Never hardcode dashboards against unverified view/column names for a given version.

---

## 17. Batching UPDATE: PostgreSQL Has No Direct UPDATE ... LIMIT

### 17.1. Syntax that looks right but is invalid

~~~sql
-- INVALID in PostgreSQL:
UPDATE wal_batch_lab.orders
SET order_status='paid'
WHERE order_status='new'
LIMIT 2;
~~~

PostgreSQL `UPDATE` does not accept `LIMIT` directly. You must select a target key set first, then update.

### 17.2. CTE selecting keys in deterministic order

~~~sql
WITH todo AS (
    SELECT order_id
    FROM wal_batch_lab.orders
    WHERE order_status='new'
    ORDER BY order_id
    LIMIT 2
)
UPDATE wal_batch_lab.orders AS o
   SET order_status='paid',
       updated_at=clock_timestamp()
  FROM todo AS t
 WHERE o.order_id=t.order_id
RETURNING o.order_id, o.order_status;
~~~

With the seed data, the first pass picks IDs `101` and `103`. On the next pass, `WHERE order_status='new'` selects from the remaining eligible rows.

### 17.3. Why is ORDER BY necessary?

`LIMIT 2` without `ORDER BY` lets the planner pick arbitrary rows, making progress unpredictable. A stable primary key order enables tracing and key-based resumption.

### 17.4. Batched UPDATEs still generate substantial WAL

In addition to heap tuple updates, indexes on `order_status` may require maintenance, and FPIs/visibility updates add to WAL. Never assume changing a short status string writes only a few bytes of WAL per row.

### 17.5. "Updated 2 rows" does not mean "two rows actually changed"

Running `UPDATE ... SET col = col` still creates new tuple versions and WAL; PostgreSQL does not automatically skip no-op updates. Add `IS DISTINCT FROM` when business logic only needs to touch rows whose value actually changed.

### 17.6. One batch per transaction

Execute each CTE `UPDATE` under autocommit or an explicit `BEGIN`/`COMMIT` per batch; if multiple statements belong to one batch, wrap them explicitly. Never wrap **an entire loop of hundreds of batches** inside one giant transaction and believe you shortened lock lifetimes.

---

## 18. Parallelizing Batch UPDATEs With SKIP LOCKED

### 18.1. Worker claim pattern

When multiple workers process a queue or table concurrently, prevent them from grabbing the same rows using `FOR UPDATE SKIP LOCKED` inside the CTE:

~~~sql
WITH todo AS (
    SELECT order_id
    FROM wal_batch_lab.orders
    WHERE order_status='new'
    ORDER BY order_id
    LIMIT 2
    FOR UPDATE SKIP LOCKED
)
UPDATE wal_batch_lab.orders AS o
   SET order_status='paid',
       updated_at=clock_timestamp()
  FROM todo AS t
 WHERE o.order_id=t.order_id
   AND o.order_status='new'
RETURNING o.order_id;
~~~

### 18.2. What does SKIP LOCKED mean?

Rows already locked by another transaction are **skipped** instead of blocking. This works well for concurrent task queues, though it yields an **inconsistent view across the global snapshot**, making it unsuitable for general reporting or exact totals.

### 18.3. Do not infer "0 rows returned" means the job is done

If a worker returns 0 rows because all remaining eligible rows are locked by other active workers, 0 rows **does not prove** no work remains. Coordinate job state, poll/retry, or run a reconciliation query after workers drain.

### 18.4. Every worker must COMMIT quickly

`FOR UPDATE SKIP LOCKED` holds row locks until transaction end. If a worker claims 2 rows and then waits 2 minutes on an external API before `COMMIT`, those locks stay held. Decouple external calls from DB transactions using an outbox where possible.

### 18.5. Starvation and fairness

Contended rows can be skipped repeatedly. If every row must eventually finish, run a final sweep without `SKIP LOCKED` or coordinate bounded retries.

### 18.6. Do not use SKIP LOCKED to "patch" unexplained deadlocks

`SKIP LOCKED` fits queue-style task claiming. It is not a substitute for consistent lock ordering, proper indexing, or sound transaction design when a workflow must update a complete target set.

---

## 19. Deleting Data in Batches

### 19.1. One massive DELETE

~~~sql
DELETE FROM wal_batch_lab.orders
WHERE order_status='cancelled';
~~~

On a large table, this holds a long transaction, creates massive dead tuples and WAL, and causes replica lag. In our tiny lab table it is trivial; the danger appears at scale.

### 19.2. Key-based CTE DELETE

~~~sql
WITH doomed AS (
    SELECT order_id
    FROM wal_batch_lab.orders
    WHERE order_status='cancelled'
    ORDER BY order_id
    LIMIT 1000
)
DELETE FROM wal_batch_lab.orders AS o
USING doomed AS d
WHERE o.order_id=d.order_id
RETURNING o.order_id;
~~~

When deleting by a retention timestamp, add an appropriate index and a primary key tie-breaker.

### 19.3. When should the loop stop?

Do not loop blindly "until 0 rows are deleted" if concurrent locks or writes can alter visibility. For a single-worker batch without `SKIP LOCKED`, 0 rows generally means no matching rows remain at that statement snapshot; with concurrent writers or workers, use a cutoff watermark and reconciliation.

### 19.4. DELETE and VACUUM

`DELETE` marks row versions dead under MVCC once no active snapshot needs them; it **does not immediately shrink the data file**. Autovacuum/`VACUUM` reclaims space for internal reuse, but usually does not return disk space to the OS.

### 19.5. Partitioned retention

If retention data is partitioned by day or month, detaching and dropping **an expired partition** is typically far cheaper than row-by-row `DELETE`s, subject to caveats around locks, constraints, dependencies, policies, and removing an entire partition at once.

Never give blanket advice to `DROP PARTITION` when part of a partition must stay or when per-row `DELETE` audit triggers must fire.

### 19.6. TRUNCATE differs from DELETE

`TRUNCATE` is faster than deleting an entire table in many cases, but carries different semantics: statement-level `TRUNCATE` triggers, stricter locking, identity/`CASCADE` behavior, and non-equivalence to per-row FK/audit `DELETE` triggers. It still writes metadata WAL and obeys transaction semantics; **do not assume it is "zero WAL."**

---

## 20. Keyset Pagination to Avoid Large OFFSET

### 20.1. OFFSET becomes expensive

~~~sql
SELECT order_id
FROM wal_batch_lab.orders
ORDER BY order_id
LIMIT 1000 OFFSET 5000000;
~~~

PostgreSQL must scan and discard millions of leading rows before returning the page, making runtime grow with offset. Under concurrent inserts/deletes, `OFFSET` also drifts, causing missed or duplicated rows across pages.

### 20.2. Keyset pagination using the last committed key

~~~sql
SELECT order_id
FROM wal_batch_lab.orders
WHERE order_id > 100000
ORDER BY order_id
LIMIT 1000;
~~~

After each batch, save the highest key processed to fetch the next slice. This advances by key value rather than physical row position.

### 20.3. What if keys have gaps?

Keys do not need to be contiguous. `WHERE order_id > last_id` handles gaps cleanly. However, you need a monotonic/stable key aligned with batch logic; if keys mutate or new rows insert below `last_id`, those rows will be missed.

### 20.4. Syncing a source with concurrent inserts

If a job must process **a fixed point-in-time snapshot** at start time, keyset paging across multiple `READ COMMITTED` transactions does not guarantee a consistent snapshot; you need a watermark, cutoff timestamp, source version, or an appropriate isolation/snapshot design.

### 20.5. Composite ORDER BY keysets

When ordering by `(created_at, order_id)`:

~~~sql
WHERE (created_at,order_id) > ($1,$2)
ORDER BY created_at,order_id
LIMIT 1000;
~~~

Row-value comparisons require compatible types and careful `NULL` handling. To avoid ambiguity, ensure the composite key columns are `NOT NULL` and unique/deterministic.

---

## 21. Decoupling Read Batches From Write Batches

### 21.1. They do not need the same size

An importer can read a file in 1 MiB chunks, buffer 2,000 validated rows, and commit them as a 2,000-row transaction. When rows are wide or carry large JSON payloads, byte-bounded batches are preferable to fixed row counts.

### 21.2. Backpressure

When the downstream database slows down, the producer must not read and queue indefinitely, exhausting RAM and inflating latency. A resilient pipeline uses bounded queues with explicit wait/throttle policies:

~~~text
Producer reads file
     |
     v
Bounded queue [max size]
     |
     v
Workers load batches
     |
     +--> If WAL/disk/lag exceeds budget: pause/throttle
     |
     +--> Once healthy again: resume smoothly
~~~

### 21.3. Mid-batch failure scenarios

- Before transaction start: safe to retry.
- Inside transaction before `COMMIT`: roll back the batch and retry idempotently.
- After `COMMIT` before application acknowledgment: **commit outcome is ambiguous**; check checkpoints and database unique keys before retrying.
- After updating an external checkpoint service: reconcile across both systems.

### 21.4. Keep the "committed watermark" in the database

A progress table with `import_id` and `last_committed_row` cleanly tracks resume points. However, if multiple workers write out of order, you must track **completed ranges** or advance a monotonic watermark only once every prior range is complete; a single high-water mark fails if batch 3 finishes before batch 2.

---

## 22. JDBC Batch Inserts and autoCommit

### 22.1. Statement batching

In Java, `PreparedStatement.addBatch()` and `executeBatch()` reduce per-row round-trip overhead:

~~~java
String sql =
    "INSERT INTO wal_batch_lab.orders " +
    "(order_id, customer_id, amount, order_status) " +
    "VALUES (?, ?, ?, ?) " +
    "ON CONFLICT (order_id) DO NOTHING";

connection.setAutoCommit(false);
try (PreparedStatement ps = connection.prepareStatement(sql)) {
    for (Order order : batch) {
        ps.setLong(1, order.id());
        ps.setLong(2, order.customerId());
        ps.setBigDecimal(3, order.amount());
        ps.setString(4, order.status());
        ps.addBatch();
    }

    ps.executeBatch();
    connection.commit();
} catch (SQLException ex) {
    connection.rollback();
    throw ex;
}
~~~

This snippet illustrates logic requiring the `Order` record, imports, and proper `Connection` lifecycle management—it is not a standalone Java file. On failure, close or return the connection safely, inspect transaction state, and handle retries.

### 22.2. executeBatch does not imply a single SQL statement

The driver may execute the batch as multiple server operations; `executeBatch()` does not guarantee **one** SQL statement or **one** database transaction if `autoCommit` or driver settings are misconfigured.

### 22.3. rewriteBatchedInserts

pgJDBC provides `reWriteBatchedInserts` (check driver docs for exact option casing), which merges compatible `INSERT`s to cut round trips. It has constraints around SQL shape, `RETURNING`, conflict clauses, and driver versions; benchmark instead of assuming enabling it always helps.

### 22.4. Batch update counts

`executeBatch()` returns an array of update counts or special status codes per the JDBC specification. With `ON CONFLICT DO NOTHING`, an `INSERT` may affect 0 rows; never assume every update count equals 1.

### 22.5. Proper transaction scoping

In frameworks or connection pools managing transactions, calling `connection.setAutoCommit(false)` and `commit()` must obey the framework contract; never manually commit a connection managed by Spring `@Transactional`.

### 22.6. Never build raw SQL strings from untrusted input

Use bind parameters; batching does not replace SQL injection defenses. Even when streaming via `COPY`, input values must be properly encoded and quoted per CSV/protocol rules rather than concatenated raw.

---

## 23. Controlling COMMIT in psql, Applications, and Procedures

### 23.1. Default psql autocommit

In `psql`, outside an explicit transaction block with default autocommit enabled, each successful SQL statement runs in an implicit transaction and commits immediately per server/client semantics.

If you run:

~~~sql
INSERT INTO wal_batch_lab.orders (...) VALUES (...);
INSERT INTO wal_batch_lab.orders (...) VALUES (...);
~~~

you are creating **two separate transactions**, not an atomic batch.

### 23.2. Explicit BEGIN/COMMIT

~~~sql
BEGIN;

INSERT INTO wal_batch_lab.orders
    (order_id,customer_id,amount,order_status)
VALUES (301,31,30.00,'new');

INSERT INTO wal_batch_lab.orders
    (order_id,customer_id,amount,order_status)
VALUES (302,31,60.00,'paid');

COMMIT;
~~~

Both statements share one transaction. If the second statement fails, the transaction enters an aborted state; you must roll back or recover via a savepoint before finishing.

### 23.3. A loop inside a DO block does not auto-commit per iteration

~~~sql
DO $$
DECLARE
    i integer;
BEGIN
    FOR i IN 1..100 LOOP
        INSERT INTO wal_batch_lab.orders
            (order_id,customer_id,amount,order_status)
        VALUES
            (400000+i,44,1.00,'new')
        ON CONFLICT (order_id) DO NOTHING;
    END LOOP;
END $$;
~~~

This remains **a single `DO` statement** running inside one transaction. Iteration count does not equal commit count. To split into separate transactions, drive batches from the client or use transaction control inside procedures/`DO` blocks strictly where PostgreSQL permits it.

### 23.4. Stored functions cannot COMMIT at will

A regular PL/pgSQL function invoked from a SQL statement **cannot** call `COMMIT` or `ROLLBACK` to slice batches the way a transaction-controlled procedure can in valid contexts.

If a job runs `SELECT process_everything()` looping over millions of rows, do not assume inserting `COMMIT` every 1,000 rows inside the function will work.

### 23.5. Stored procedures with conditional transaction control

PostgreSQL supports `CALL` procedures with transaction control under specific conditions: `CALL` must execute at top level or within an eligible `CALL`/`DO` chain, must not be wrapped inside a client-started explicit transaction block, and must not sit inside an exception block/subtransaction or other restricted context.

Conceptual example:

~~~sql
CREATE OR REPLACE PROCEDURE wal_batch_lab.demo_commit()
LANGUAGE plpgsql
AS $$
BEGIN
    INSERT INTO wal_batch_lab.orders
        (order_id,customer_id,amount,order_status)
    VALUES (500001,50,5.00,'new')
    ON CONFLICT (order_id) DO NOTHING;

    COMMIT;
END;
$$;
~~~

When invoked via `CALL wal_batch_lab.demo_commit();` at an eligible top level, the procedure can execute transaction control. **Never wrap it in `BEGIN; CALL ...; COMMIT;` and expect internal `COMMIT`s to succeed**.

Certain procedure attributes such as `SECURITY DEFINER` or `SET` clauses also restrict transaction control. For predictable operations, **client-managed batch transactions are usually much easier to administer** than procedures committing internally.

### 23.6. Exception blocks and subtransactions

PL/pgSQL `EXCEPTION` blocks rely on subtransactions. PostgreSQL forbids ending a top-level transaction inside a block containing an exception handler. If per-batch retries are needed, manage transaction boundaries in the caller instead of treating an `EXCEPTION` block as an independent transaction.

### 23.7. Savepoints

~~~sql
BEGIN;
SAVEPOINT before_batch;

-- Run an SQL batch that might fail.

-- When handling a recoverable error:
ROLLBACK TO SAVEPOINT before_batch;

-- Continue with subsequent operations if permitted by contract.
COMMIT;
~~~

Savepoints enable partial rollbacks **within the same transaction**; they do not release transaction-level resources like a full `COMMIT` and do not turn a batch into an independently committed unit. They do not reduce WAL retention or snapshot age on a multi-hour transaction.

---

## 24. Retrying Batches and Resolving Ambiguous Commit Outcomes

### 24.1. Errors before COMMIT

If the database returns an error and the transaction definitively rolled back, the application can retry after classifying the error and verifying preconditions.

Examples:

- `40001` `serialization_failure` -> typically retry **the entire transaction**.
- `40P01` `deadlock_detected` -> typically retry the transaction with backoff.
- `23505` `unique_violation` -> may indicate a data conflict; do not retry blindly forever.
- `23514` `check_violation` -> invalid input or logic bug; quarantine or fix rather than retrying.
- Disk full -> resolve storage/WAL/retention before retrying.

### 24.2. Connection drop during COMMIT

The client sends `COMMIT`, and the server may have committed even though the client lost the response. Never blindly assume "the transaction did not commit." Check committed keys and metadata upon reconnect:

~~~sql
SELECT import_id,last_committed_row,status
FROM wal_batch_lab.import_jobs
WHERE import_id=9001;
~~~

When batch data and checkpoint commit atomically, this status tells you how to resume. If data committed without the checkpoint due to a non-atomic design, you have an inconsistency that must be reconciled.

### 24.3. Idempotency keys and unique constraints

Staging uses `PRIMARY KEY(import_id, source_row_no)`. When retrying the same source row:

~~~sql
INSERT INTO wal_batch_lab.order_stage
    (import_id,source_row_no,order_id,customer_id,amount,order_status)
VALUES (9001,7,207,25,10.00,'new')
ON CONFLICT (import_id,source_row_no) DO NOTHING;
~~~

However, if source row 7 carries a different payload than before, `DO NOTHING` hides data drift. Check source version or payload checksums before treating a conflict as an idempotent retry.

### 24.4. Unbounded retries

An importer retrying every 100ms while the DB disk is full only worsens cluster overload. Use exponential backoff, jitter, max attempt caps, circuit breakers, and human alerting on non-recoverable failures.

### 24.5. Resuming across parallel workers

If multiple workers process ranges out of order, storing only `last_committed_row = 100000` when one worker finishes the highest slice will skip unfinished middle slices. Track **completed ranges** or advance the watermark monotonically only across contiguous completed prefixes.

---

## 25. WAL and Replication Lag

### 25.1. Primary emits WAL, standbys receive and replay it

A primary can generate WAL faster than the network or standby disk/CPU can receive and replay it. During WAL bursts, physical standbys fall behind, degrading:

- Freshness of replica reads.
- Failover readiness against RPO targets.
- Disk headroom from WAL retention.
- Standby CPU and I/O utilization.
- Post-job catch-up duration.

### 25.2. Key LSN fields

On the primary, `pg_stat_replication` reports position fields:

- `sent_lsn`: WAL sent to the standby.
- `write_lsn`: WAL written by the standby as reported back to the sender.
- `flush_lsn`: WAL flushed to disk by the standby.
- `replay_lsn`: WAL replayed by the standby.
- `write_lag`, `flush_lag`, `replay_lag`: estimated lag durations with specific semantics depending on replication state.

### 25.3. Querying on the primary

~~~sql
SELECT
    application_name,
    client_addr,
    state,
    sync_state,
    sent_lsn,
    write_lsn,
    flush_lsn,
    replay_lsn,
    write_lag,
    flush_lag,
    replay_lag
FROM pg_stat_replication;
~~~

If no active streaming replica is connected, this view returns zero rows. Never conclude "replication lag = 0" from **an empty view** if standbys are expected to be connected.

### 25.4. Estimating WAL byte lag

~~~sql
SELECT
    application_name,
    pg_size_pretty(
        pg_wal_lsn_diff(pg_current_wal_lsn(), replay_lsn)::bigint
    ) AS approx_replay_bytes_behind
FROM pg_stat_replication
WHERE replay_lsn IS NOT NULL;
~~~

This measures distance in the WAL stream—**not** lagged business rows and not directly equivalent to time lag. It compares against the moving `pg_current_wal_lsn()` while workloads continue changing.

### 25.5. Inspecting from the standby

On a physical standby:

~~~sql
SELECT
    pg_is_in_recovery() AS is_standby,
    pg_last_wal_receive_lsn() AS received_lsn,
    pg_last_wal_replay_lsn() AS replayed_lsn,
    pg_last_xact_replay_timestamp() AS last_replay_commit_timestamp;
~~~

`pg_last_xact_replay_timestamp()` can be `NULL` or stale when the primary has no recent write transactions; never treat wall-clock minus that timestamp as absolute lag when the primary is idle.

### 25.6. Replica lag throttling thresholds

A batch controller can:

- Shrink rows per batch when replay byte lag rises.
- Reduce concurrent workers.
- Pause briefly so standbys can catch up.
- Abort with an alert if lag or disk crosses critical thresholds.
- Ramp back up conservatively after lag stabilizes.

Base thresholds on RPO/RTO and live workloads; never hardcode "sleep 1s if lag > 1 GiB" across all systems.

### 25.7. Synchronous replication

With synchronous standbys configured, commit latency incorporates standby acknowledgment per `synchronous_commit` and synchronous replication settings. Large batches still induce heavy I/O pressure; never assume "having a sync standby" eliminates all lag or data-loss scenarios under every failure mode.

---

## 26. Replication Slots Retaining WAL

### 26.1. What are slots for?

Physical and logical replication slots tell PostgreSQL to retain WAL needed by a standby or consumer from its tracked position. When a consumer slows down or goes offline, the primary must retain WAL longer.

### 26.2. Inspecting slots

~~~sql
SELECT
    slot_name,
    slot_type,
    active,
    restart_lsn,
    confirmed_flush_lsn,
    wal_status
FROM pg_replication_slots;
~~~

Columns such as `wal_status` depend on PostgreSQL version. `confirmed_flush_lsn` applies primarily to logical slots and is not meaningful on physical slots.

### 26.3. Estimating per-slot backlog

~~~sql
SELECT
    slot_name,
    slot_type,
    active,
    pg_size_pretty(
        pg_wal_lsn_diff(pg_current_wal_lsn(), restart_lsn)::bigint
    ) AS wal_retained_from_restart
FROM pg_replication_slots
WHERE restart_lsn IS NOT NULL;
~~~

This computes LSN offset differences; because multiple slots and retention rules share WAL segments, **never simply sum all slot backlogs** to predict exact `pg_wal` disk consumption.

### 26.4. max_slot_wal_keep_size

Supported PostgreSQL versions provide `max_slot_wal_keep_size` to cap WAL retained by slots. Enforcement obeys specific checkpoint semantics; setting it too low can invalidate lagging standbys/consumers if required WAL is recycled, forcing full reinitialization.

Never set it just to mask chronically broken consumers. Monitor slot health and maintain a proper recovery plan.

### 26.5. An "inactive slot" should not be dropped reflexively

An inactive logical replication slot might belong to a connector paused for maintenance; dropping it breaks consumer continuity. Before dropping any slot:

1. Identify the owner and consumer.
2. Verify its state and replication purpose.
3. Measure backlog and disk headroom.
4. Decide whether to resume, resync, or drop under an approved runbook.

### 26.6. Batch ingestion and slot backlogs

If an importer writes 200 MiB/s of WAL while a logical decoder processes 20 MiB/s, the backlog grows at roughly 180 MiB/s. Shrinking batch size while maintaining total ingest throughput will not relieve the backlog; you must throttle **total ingest rate** or scale the consumer.

---

## 27. WAL Archiving and PITR

### 27.1. Why archive WAL?

With `archive_mode` and `archive_command` (or archive libraries), completed WAL segments are shipped to archive storage for backups and PITR. If archiving fails, PostgreSQL retains unarchived segments, driving up disk usage.

### 27.2. Inspecting archiving settings

~~~sql
SHOW archive_mode;
SHOW archive_command;
SHOW wal_level;
~~~

Managed database platforms often hide or control these settings at the provider level; do not expect superuser workarounds to modify them.

### 27.3. pg_stat_archiver

~~~sql
SELECT
    archived_count,
    last_archived_wal,
    last_archived_time,
    failed_count,
    last_failed_wal,
    last_failed_time,
    stats_reset
FROM pg_stat_archiver;
~~~

Never conclude archiving is healthy merely because `archived_count` is high. Inspect recent archive timestamps, `failed_count`, backlog, and archive destination health. When a database is idle, no new WAL segments are archived; always correlate with WAL generation.

### 27.4. Archive backlogs during imports

A job emitting 500 GiB of WAL over a few hours can exceed archive network or object-storage bandwidth, causing retained WAL to pile up. Before running migrations, benchmark WAL bytes/row in a lab and ensure sufficient archive throughput, disk headroom, and recovery margins.

### 27.5. wal_level is not an "import fast-mode toggle"

`wal_level` determines what information goes into WAL for replication and logical decoding. Lowering it casually can break replication/backups and requires restarts; never downgrade it solely to dodge WAL if production needs PITR or replicas.

### 27.6. Do not break the recovery chain

Never manually purge archived WAL within the retention window or force uncoordinated cleanups. Govern WAL archive expiration strictly through backup retention policies backed by tested restores, never a size-based cron deletion script.

---

## 28. MVCC, Dead Tuples, and VACUUM Under Bulk UPDATE/DELETE

### 28.1. PostgreSQL UPDATEs create new row versions

Under MVCC, `UPDATE` creates a new tuple version while the old version becomes dead once no active transaction snapshot needs it. `DELETE` likewise hides rows from newer snapshots without immediately shrinking the underlying data file.

### 28.2. How does batching help?

Splitting work across short transactions caps lock duration and lets old tuple versions become reclaimable incrementally as snapshots advance. However, the total modified row versions still require storage reclamation; batching **does not** convert `UPDATE` into a zero-WAL in-place overwrite.

### 28.3. HOT updates

Qualifying `UPDATE`s can execute as **HOT (Heap-Only Tuple)** updates when no indexed columns change and sufficient free space exists on the same heap page, avoiding index updates. However, updating a non-indexed column does not guarantee HOT: pages may lack free space, or expression/partial indexes may prevent it.

### 28.4. Dead tuple counters

~~~sql
SELECT
    schemaname,
    relname,
    n_live_tup,
    n_dead_tup,
    n_tup_ins,
    n_tup_upd,
    n_tup_del,
    n_tup_hot_upd,
    last_autovacuum,
    last_analyze
FROM pg_stat_user_tables
WHERE schemaname='wal_batch_lab'
ORDER BY relname;
~~~

These numbers are statistics estimates, not exact MVCC snapshot counts. Column availability depends on PostgreSQL version; consult version docs if a column differs.

### 28.5. Vacuum and analyze

After bulk changes, you may need:

~~~sql
VACUUM (ANALYZE) wal_batch_lab.orders;
~~~

Run with appropriate privileges and maintenance timing. Regular `VACUUM` reclaims dead tuple space for reuse and updates visibility maps; `ANALYZE` refreshes planner statistics. Never force `VACUUM FULL` routinely after every batch: it rewrites the entire table under an exclusive lock with heavy disk and WAL cost.

### 28.6. Autovacuum is not an optional optimization

Autovacuum prevents table/index bloat and transaction ID wraparound. Never disable autovacuum cluster-wide to save I/O during an import without strict safeguards. Monitor backlog and tune autovacuum capacity appropriately.

### 28.7. Index bloat

Updating indexed columns or deleting large numbers of rows causes index maintenance and bloat. Reindexing has lock, disk, and WAL trade-offs (with `REINDEX CONCURRENTLY` available in supported scenarios). Never trigger mass reindexing just because WAL is growing without diagnosing the cause.

---

## 29. Indexes, Constraints, Triggers, and Write Amplification

### 29.1. Every index adds write cost

Inserting rows requires updating table indexes; updating indexed or key columns updates indexes; deleting rows leaves dead index entries to clean up.

A table with 12 indexes has radically different ingestion costs than a table with only a primary key, even for identical rows.

### 29.2. Should you drop indexes for faster bulk loading?

Only in tightly controlled bulk loads after verifying:

- Whether concurrent read/write traffic exists.
- Which indexes enforce `UNIQUE`/`PRIMARY KEY` constraints.
- Whether rebuilding indexes fits within time, disk, and WAL budgets.
- Whether DDL locks and downtime are acceptable.
- Whether WAL/archive bandwidth handles the index-build burst.
- Whether backup and rollback plans are ready.

**Never casually drop PK/`UNIQUE` indexes or disable FKs** just to speed up ingestion—doing so risks admitting invalid or duplicate data.

### 29.3. Index rebuilds also generate I/O and WAL

Deferring index creation during `COPY` does not eliminate the total work; rebuilding indexes afterward produces its own I/O and WAL burst. Benchmark the full end-to-end pipeline, not just the `COPY` step.

### 29.4. Triggers multiply write volume

An `INSERT` into a business table may fire triggers that write audit logs, maintain summary tables, or populate an outbox. If every source row triggers three extra DML operations, real WAL and lock pressure far exceed a simple `INSERT`.

### 29.5. Foreign keys

Foreign key checks require appropriate indexes on referenced columns in many workloads; when bulk-loading relational tables, load in dependency order or validate via staging/publication rather than permanently removing foreign keys.

### 29.6. Batch size and lock contention

When multiple workers concurrently `INSERT`/`UPSERT` hot unique keys or update shared aggregate rows, lock contention spikes regardless of small batch sizes. Reducing concurrency or partitioning work by key range is often far more effective than shrinking batch size alone.

---

## 30. UNLOGGED and TEMP: Trading Durability for Less WAL

### 30.1. UNLOGGED tables

~~~sql
CREATE UNLOGGED TABLE wal_batch_lab.raw_stage_unlogged (
    source_row_no bigint,
    raw_payload text
);
~~~

`UNLOGGED` tables skip WAL logging for **table heap/index data** in qualifying workloads, carrying major trade-offs:

- They are not crash-safe; following an unclean shutdown, PostgreSQL truncates them automatically.
- They are not replicated via physical streaming replication to standbys.
- Their indexes are also unlogged.
- Catalog and related metadata operations still emit WAL; do not describe them as "completely zero WAL."
- Unsuitable for critical ingest checkpoints or authoritative business records.

### 30.2. When does UNLOGGED make sense?

When a raw staging cache can be reloaded completely from durable source files, does not need to be queried on standbys, and has an automated reload runbook after crashes—while authoritative checkpoints and final destinations remain logged tables.

### 30.3. When is UNLOGGED inappropriate?

- Authoritative payment or order tables.
- Progress tables (`import_progress`) serving as the sole source of resume truth.
- Tables queried on physical standbys.
- Zero-RPO systems or sources that cannot be re-extracted.
- Unsupervised jobs where losing staging means unrecoverable data loss.

### 30.4. TEMP tables

~~~sql
CREATE TEMP TABLE temp_stage (
    order_id bigint,
    amount numeric(12,2)
) ON COMMIT DROP;
~~~

Temporary tables are scoped to a session or transaction (via `ON COMMIT`) and differ in logging and durability from regular tables. They are useful for small intermediate scratchpads, though they do not eliminate WAL when merging into logged destination tables and remain constrained by temp disk/memory, connection pooling, and session state.

### 30.5. Never switch production tables to UNLOGGED casually

Running `ALTER TABLE ... SET UNLOGGED` triggers heavy table rewrites, locking, replication consequences, and durability loss depending on version. Never use it as an unapproved shortcut to accelerate imports.

---

## 31. synchronous_commit and Durability Trade-Offs

### 31.1. A commonly misunderstood name

`synchronous_commit` governs when `COMMIT` returns success relative to WAL flushing and synchronous standby acknowledgments. Setting `synchronous_commit = off` can lower commit latency for workloads willing to lose a narrow window of recently acknowledged transactions in a crash.

### 31.2. It does not "disable WAL"

Even with `synchronous_commit = off`, PostgreSQL still writes WAL records; what changes is the flush wait before acknowledging `COMMIT`. Never toggle this setting to solve a full `pg_wal` filesystem.

### 31.3. Acceptable for reloadable data?

Temporary or test ingestion pipelines where every record can be cleanly replayed may accept relaxed commit latency under explicit policy—provided engineers understand the failure model, potential loss of recent commits, side-effect consistency, and resume logic.

### 31.4. Never apply casually to financial transactions

For money movement, order confirmations, or strict durability requirements, altering `synchronous_commit` requires formal DBA, security, and business sign-off. Higher throughput never justifies unexpected data loss.

### 31.5. fsync and full_page_writes

`fsync = off` and `full_page_writes = off` expose the database to severe corruption on crashes. Never propose toggling them temporarily in production to suppress WAL spikes. Throttle batches, review indexes/triggers, tune checkpoints, and ensure archive/replica capacity first.

---

## 32. Adaptive Batching and Rate Limiting

### 32.1. Do not chase maximum rows/s blindly

A controller can tune batches dynamically against live DB health:

~~~text
Start with N=1,000 rows, concurrency=2
          |
          v
Execute batch + COMMIT
          |
          v
Measure latency, WAL delta, replica lag, disk, locks
          |
          +-- Healthy across multiple cycles: increase N or workers slightly
          |
          +-- Near thresholds: hold N, reduce concurrency if needed
          |
          +-- Exceeded thresholds: shrink N / pause / backoff
          |
          +-- Critical error: stop, alert, resume from checkpoint
~~~

### 32.2. Useful control signals

- p95/p99 latency of critical APIs.
- Batch execution + `COMMIT` duration.
- WAL bytes/second and WAL bytes/batch.
- Free space in `pg_wal` and archive backlog.
- Replica replay lag and receive lag.
- Checkpoint frequency, FPIs, and write I/O.
- Lock waits, deadlocks, and long active transactions.
- Autovacuum backlog and dead tuple counts.
- Errors, retries, and duplicate conflicts.

### 32.3. AIMD (additive increase / multiplicative decrease)

A straightforward control loop:

- After several healthy cycles: add 500 rows to batch size.
- Near warning thresholds: halve batch size.
- Enforce min/max bounds and cooldown windows.
- Commit progress checkpoints after every batch.

This illustrates the pattern rather than fixed optimal constants. Because metrics lag and fluctuate, build damping to avoid oscillating controllers.

### 32.4. Batch size and worker count are two different levers

Dropping batch size from 10,000 to 2,000 rows while scaling workers from 2 to 10 can keep WAL generation rate flat or push it higher. When **total WAL throughput exceeds replica or archive capacity**, throttle aggregate write rate rather than shrinking rows per transaction alone.

### 32.5. Safe pausing

An importer should pause cleanly at **a post-COMMIT boundary**, never mid-transaction without cleanup. If forced cancellation occurs, the caller must roll back, release locks, and update job state accurately.

---

## 33. Exporting Large Datasets: COPY TO and Streaming

### 33.1. COPY TO STDOUT

Data exports can use:

~~~sql
COPY (
    SELECT order_id,customer_id,amount,order_status
    FROM wal_batch_lab.orders
    WHERE order_id BETWEEN 100 AND 100000
    ORDER BY order_id
)
TO STDOUT
WITH (FORMAT csv, HEADER true);
~~~

`COPY TO STDOUT` streams rows directly over the client protocol; in `psql`, `\copy` conveniently writes them to a local file.

### 33.2. \copy (SELECT ...) TO file

~~~text
\copy (SELECT order_id,customer_id,amount,order_status FROM wal_batch_lab.orders ORDER BY order_id) TO '/client/export/orders.csv' WITH (FORMAT csv, HEADER true)
~~~

The output path refers to **the client machine running `psql`**, not the PostgreSQL server. The client user must have local filesystem write access.

### 33.3. How COPY TO differs from COPY FROM regarding WAL

A read-only export does not generate WAL from modifying destination rows; however, the query consumes CPU/I/O, holds snapshots/locks, may spill temp files, and runs alongside other cluster WAL generators. Never assume exporting files guarantees zero cluster WAL activity.

### 33.4. Streaming to bound RAM

For multi-gigabyte exports, never buffer the entire result set into memory before writing to disk. Stream via `COPY TO STDOUT` or a properly configured server-side cursor / driver `fetchSize` with backpressure.

### 33.5. Are multi-transaction exports consistent?

Running multiple `SELECT`/`COPY` chunks across separate `READ COMMITTED` transactions exposes changing data from concurrent writers between chunks. Keyset pagination eliminates `OFFSET` drift **but does not provide a single consistent snapshot across the entire export**.

When point-in-time export consistency is required, use an explicit snapshot transaction design while balancing the vacuum cost of holding snapshots across multi-hour exports.

### 33.6. pg_dump is not a DIY CSV COPY script

For full database or schema backups, use `pg_dump` or your backup tool rather than `SELECT`ing tables manually. `pg_dump` captures schemas, indexes, constraints, sequences, extensions, roles, and snapshot consistency; CSV exports only hold **table data**, omitting DDL and database objects.

---

## 34. Keyset Exports and Snapshot Consistency

### 34.1. Keyset pagination in exports

~~~sql
SELECT order_id,customer_id,amount
FROM wal_batch_lab.orders
WHERE order_id > 0
ORDER BY order_id
LIMIT 1000;
~~~

Then pass the last returned `order_id` to fetch the next page:

~~~sql
SELECT order_id,customer_id,amount
FROM wal_batch_lab.orders
WHERE order_id > 1000
ORDER BY order_id
LIMIT 1000;
~~~

The value `1000` in the second query is illustrative; always pass **the actual last key returned**. Keyset paging handles key gaps cleanly.

### 34.2. Snapshot drift across pages

Under `READ COMMITTED`, if a concurrent writer inserts a new row with `order_id < last_key`, that row will be missed. This may be acceptable for "export historical rows up to a watermark," provided the semantics are documented explicitly.

### 34.3. Cutoff watermark

To export rows stabilized before a cutoff time, filter `created_at < cutoff` paired with composite keyset `(created_at, id)`. Even then, backdated inserts or concurrent updates require source version invariants to ensure full consistency.

### 34.4. Long-running REPEATABLE READ transactions

A `REPEATABLE READ` transaction provides a consistent snapshot across its queries, yet holding it open for hours while slowly exporting hundreds of gigabytes stalls dead-tuple cleanup in `VACUUM`. For massive consistent dumps, use dedicated backup/snapshot mechanisms or managed export architectures.

### 34.5. Do not confuse "splitting output files" with "splitting input transactions"

A client can stream **one single query** and chunk its output into 1 GiB files locally. That splits the output files, **not** the server SQL transaction or snapshot. Conversely, running separate queries opens separate snapshots. Be explicit about which boundary is being partitioned.

---

## 35. Partitioning Data to Reduce Retention DELETE Overhead

### 35.1. Time-based partitioning

A multi-billion-row event table with 90-day retention can be partitioned by day, week, or month:

~~~text
events (partitioned parent)
    |
    +-- events_2026_08
    +-- events_2026_09
    +-- events_2026_10
    +-- events_2026_11
~~~

Once an entire partition ages past retention, detaching and dropping it per runbook avoids row-by-row `DELETE`s, dead tuples, and massive row-level WAL.

### 35.2. Metadata operations are not completely free

Detaching or dropping a partition still acquires catalog/table locks, updates metadata, affects foreign-key dependencies and replicas, and generates catalog WAL. `DETACH PARTITION CONCURRENTLY` comes with its own constraints, requirements, and version caveats.

### 35.3. Do not silently bypass per-row auditing

If an `ON DELETE FOR EACH ROW` trigger writes compliance audit records, `DROP TABLE` on a partition will not invoke millions of row-level delete triggers. Align retention and audit policies intentionally rather than dropping compliance trails for speed.

### 35.4. Partitions also assist ingestion

Loading data into targeted partitions improves index locality, retention drops, and partition pruning. Avoid creating excessive tiny partitions (e.g., one per few hundred rows), which inflates planner and catalog overhead.

### 35.5. Swapping an entire partition

Workflows can build a new dataset in a standalone table, validate it, index it, and attach it as a partition under PostgreSQL rules. Check constraints, FKs, locking, replication, and version specifics first; never treat `ATTACH PARTITION` as unconditionally zero-downtime.

---

## 36. Data Transformations and Backfills: When Bulk UPDATE Isn't Best

### 36.1. Adding a computed column example

Suppose a large table gains a `normalized_email` column. Updating every row in a single statement causes:

- Heavy heap and index WAL.
- Dead tuples and bloat.
- Long transactions and locks.
- Replica lag.
- Sustained I/O bursts.

### 36.2. Primary-key batching

~~~sql
WITH ids AS (
    SELECT user_id
    FROM app.users
    WHERE normalized_email IS NULL
      AND user_id > 0
    ORDER BY user_id
    LIMIT 2000
)
UPDATE app.users AS u
SET normalized_email = lower(btrim(u.email))
FROM ids
WHERE u.user_id=ids.user_id
  AND u.normalized_email IS NULL;
~~~

This example assumes `app.users` and those columns exist; **do not run verbatim** on a different schema. Keep the `IS NULL` recheck predicate so the backfill stays idempotent and skips already-updated rows.

### 36.3. Concurrent writers

If the application updates `email` while the backfill runs, ensure writes also populate `normalized_email` (via application dual-write or a trigger) before/during the backfill, or follow up with a reconciliation sweep.

### 36.4. Key-based batching needs state rechecks

Between selecting IDs and applying `UPDATE`, another transaction might change the row. Re-check the target condition in the `UPDATE` predicate or coordinate locking properly. In multi-worker jobs, use claiming, `SKIP LOCKED`, and reconciliation.

### 36.5. Sometimes rewriting into a new table is better

When nearly every row in a huge table must change, creating **a new table**, transforming via `INSERT ... SELECT` or `COPY`, building indexes, validating, and cutting over can beat in-place `UPDATE`s. However, table cutovers carry significant complexity around FKs, sequences, triggers, privileges, replication, concurrent writes, and locks. Decide based on maintenance windows and operational readiness, not solely WAL reduction.

### 36.6. Phased schema migration

A standard safe progression:

1. Add the nullable column.
2. Deploy code dual-writing the new column on live mutations.
3. Backfill in throttled batches.
4. Reconcile data completeness.
5. Add/validate constraints and concurrent indexes as appropriate.
6. Switch read paths.
7. Retire legacy logic after verification.

This is the "expand -> migrate -> contract" pattern, avoiding big-bang DDL/DML under production load.

---

## 37. Isolation and Lock Timeouts for Batch Jobs

### 37.1. lock_timeout

~~~sql
BEGIN;
SET LOCAL lock_timeout='2s';

WITH ids AS (
    SELECT order_id
    FROM wal_batch_lab.orders
    WHERE order_status='new'
    ORDER BY order_id
    LIMIT 500
)
UPDATE wal_batch_lab.orders AS o
SET order_status='paid'
FROM ids
WHERE o.order_id=ids.order_id;

COMMIT;
~~~

If acquiring a lock exceeds `2s`, the statement aborts and fails the transaction; the client rolls back and retries. `lock_timeout` bounds lock waiting, not total DML execution time.

### 37.2. statement_timeout

~~~sql
BEGIN;
SET LOCAL statement_timeout='10s';
-- One batch SQL operation
COMMIT;
~~~

Pick a duration generous enough for normal batches yet short enough to prevent runaway stalls. Always inspect transaction state and retry rules upon timeouts.

### 37.3. idle_in_transaction_session_timeout

Terminates sessions that hold transactions open without executing SQL for too long. It is a safety net rather than a substitute for clean connection management; when triggered, the connection closes and pools must recover.

### 37.4. Deadlocks

Two workers updating rows in opposite key orders can deadlock. Enforcing deterministic key ordering and short transactions minimizes deadlocks without eliminating them entirely. PostgreSQL detects deadlocks and aborts one transaction; applications must retry per policy.

### 37.5. Never turn timeouts into "skip row"

If a batch hits `lock_timeout`, never advance the checkpoint or discard rows. The failure handler must roll back and leave that range unfinished.

### 37.6. Serializable retries

Under `SERIALIZABLE` isolation, `serialization_failure (40001)` requires retrying the entire transaction (including re-reading inputs and recomputing decisions). Never replay only the failed final statement against stale reads from an aborted transaction.

---

## 38. Budgeting WAL Bursts and Storage Capacity

### 38.1. An illustrative budget calculation

Suppose lab testing shows an average `UPDATE` generates roughly **2 KiB of WAL** per row for a given schema. Updating 5 million rows implies:

- Expected total WAL ≈ 10,000,000 KiB ≈ 9.54 GiB.
- Over a 10-minute run, average WAL generation is roughly 16.3 MiB/s.
- Instantaneous spikes will exceed the average due to checkpoints, FPIs, and batch concurrency.

These are **synthetic numbers**. WAL bytes per row are never fixed; always benchmark on a representative dataset before sizing disk headroom.

### 38.2. Budget across the entire topology

Do not size `pg_wal` disk in isolation:

- Primary free disk and IOPS.
- WAL archive bandwidth and destination capacity.
- Standby network and replay capacity.
- Logical decoding consumers.
- Base backup and PITR retention.
- Temp file usage for sorts and hashes.
- Heap and index bloat from `UPDATE`/`DELETE`.
- Rollback and retry overhead.
- Raw and staging storage footprint.

### 38.3. Headroom for incidents

A 2-hour migration needs safety headroom in case archiving stalls, a standby drops offline, or batches retry. Never run right up against disk limits assuming `max_wal_size` will automatically prevent growth.

### 38.4. Live monitoring during the job

Track these metrics on a dashboard:

| Metric | Meaning | Action if degraded |
|---|---|---|
| WAL MiB/s | Write generation rate | Throttle ingest rate / reduce workers |
| WAL retained / free disk | Disk-exhaustion risk | Inspect slots/archive, pause safely |
| Replica replay lag bytes | Standby catch-up gap | Throttle job, investigate standby |
| Archive failures/backlog | PITR/retention risk | Repair archive pipeline |
| Checkpoint frequency/FPI | Write amplification | Measure/tune storage and WAL config |
| `n_dead_tup`/autovacuum lag | Bloat pressure | Reclaim/tune between transactions |
| API p95/p99 latency | Customer-facing impact | Reduce concurrency/batch size |
| Transaction age/locks | Contention and blocking | Shorten transactions, clear blockers |

### 38.5. Thresholds must tie to actions

Alerts only matter when backed by a runbook: who can pause the job, when to halt immediately, how to inspect slots and archiving, where to resume, and when rollbacks or cutovers are unsafe.

---

## 39. End-to-End Staging -> Validate -> Publish Workflow

### 39.1. Safe processing flow

~~~mermaid
flowchart TD
    A["Immutable source data + checksum"] --> B["Split chunks with stable IDs"]
    B --> C["COPY chunk into staging"]
    C --> D{"Validate & deduplicate"}
    D -- "Disallowed errors" --> E["ROLLBACK chunk; quarantine"]
    D -- "Passed" --> F["Merge into logged table"]
    F --> G["Record checkpoint in same transaction"]
    G --> H["COMMIT"]
    H --> I["Measure WAL, lag, latency, disk"]
    I --> J{"Thresholds healthy?"}
    J -- "No" --> K["Pause / shrink batch / alert"]
    K --> I
    J -- "Yes" --> L{"More chunks?"}
    L -- "Yes" --> B
    L -- "No" --> M["Reconcile accepted/rejected/duplicates"]
    M --> N["Publish dataset version / mark complete"]
~~~

### 39.2. Deciding between job-wide atomicity and chunk-level atomicity

- **Chunk-level atomic:** target rows commit incrementally, exposing partial progress. Ideal for event ingestion with per-batch visibility.
- **Job-wide atomic:** load into staging first, then publish via a metadata version flag or partition swap in a short transaction. Requires matching schema and reader-routing design.
- **Entity-atomic:** commit complete entities or customer key ranges rather than arbitrary row counts when invariants forbid half-loaded entities.

### 39.3. Raw data vs. normalized data

Keeping immutable raw inputs with checksums enables verification and reprocessing. Target tables should retain business keys, batch identifiers, and source versions where needed for auditing. Never mark an event complete solely because the network stream closed.

### 39.4. Job state machine

Suggested state machine:

~~~text
pending -> running -> complete
             |
             v
            failed -> running (resume)
             |
             v
           cancelled (per policy)
~~~

If a job fails at batch 37, data from batches `1..36` has already committed. Job metadata must accurately report what was processed rather than pretending the entire job rolled back.

### 39.5. Job cancellation

When an operator requests cancellation:

1. Stop picking up new batches.
2. Allow the active batch to cleanly `COMMIT` or `ROLLBACK`.
3. Close or return database connections.
4. Persist accurate status and checkpoints.
5. Retain raw source data, rejected rows, and logs/counters.
6. Report committed progress—not merely rows buffered in RAM.

---

## 40. Runbook for Sudden WAL Spikes

### 40.1. Recognizing symptoms

- Rapidly shrinking free space on the `pg_wal` filesystem.
- Rising replica replay lag.
- Increasing `pg_stat_archiver.failed_count` or stalled archiving.
- Spiking `pg_stat_wal.wal_bytes` deltas.
- Surging checkpoint and write I/O.
- Rising API latency and lock waits.

### 40.2. Step 1: Capture baseline metrics (without adding heavy load)

~~~sql
SELECT
    pg_current_wal_lsn() AS current_lsn,
    pg_is_in_recovery() AS is_standby;

SELECT wal_records,wal_fpi,wal_bytes,stats_reset
FROM pg_stat_wal;

SELECT slot_name,slot_type,active,restart_lsn
FROM pg_replication_slots;

SELECT application_name,state,sync_state,replay_lsn
FROM pg_stat_replication;

SELECT archived_count,failed_count,
       last_archived_time,last_failed_time
FROM pg_stat_archiver;
~~~

Certain views and columns depend on PostgreSQL major version and privileges. Do not alter permissions indiscriminately just for a dashboard.

### 40.3. Step 2: Distinguish WAL generation from WAL retention

- If WAL bytes/s spiked alongside a new importer: investigate write rate and worker concurrency.
- If WAL bytes/s is normal while `pg_wal` keeps growing: inspect replication slots, archive failures, and WAL retention config.
- If both are elevated: a bursty job is overwhelming consumers or archiving.

### 40.4. Step 3: Throttle at a batch boundary

Reduce worker count or bytes/s, and pause cleanly after `COMMIT` or `ROLLBACK`. Avoid abruptly killing a backend holding a massive open transaction without weighing rollback and recovery costs; follow incident severity and runbook guidance.

### 40.5. Step 4: Investigate archiving and slots

If a stale logical slot is retaining WAL, contact the consumer owner before dropping it. If the archive destination is full or unreachable, fix the archive pipeline rather than deleting unarchived WAL files.

### 40.6. Step 5: Evaluate checkpoints and storage

If FPI/checkpoint pressure is high, verify whether checkpoint frequency and settings fit your disk budget. Never disable `fsync` or `full_page_writes` as an emergency workaround.

### 40.7. Step 6: Reconcile job state

After pausing, inspect checkpoints, source checksums, and target row counts/keys to confirm which batches committed. Never blindly restart the whole file if duplicates could occur without idempotency.

### 40.8. Step 7: Controlled recovery

Resume with smaller batches and lower concurrency across multiple observation cycles, prioritizing RPO/replicas, API latency, and disk safety. Ramp up gradually only after backlogs recede.

### 40.9. Step 8: Postmortem

Record observed WAL bytes/row, archive/replication bottlenecks, checkpoint metrics, retries, failed batches, and latency impact. Update capacity plans and staging tests to prevent recurrence.

---

## 41. Inspection and Monitoring: Sample Queries

### 41.1. Sessions holding long transactions

~~~sql
SELECT
    pid,usename,application_name,state,
    clock_timestamp()-xact_start AS transaction_age,
    wait_event_type,wait_event
FROM pg_stat_activity
WHERE xact_start IS NOT NULL
ORDER BY xact_start
LIMIT 30;
~~~

### 41.2. Staging and target table activity

~~~sql
SELECT
    relname,
    n_live_tup,n_dead_tup,
    n_tup_ins,n_tup_upd,n_tup_del,
    last_autovacuum,last_analyze
FROM pg_stat_user_tables
WHERE schemaname='wal_batch_lab'
ORDER BY relname;
~~~

### 41.3. WAL statistics

~~~sql
SELECT
    wal_records,wal_fpi,
    pg_size_pretty(wal_bytes::bigint) AS wal_volume,
    wal_write,wal_sync,stats_reset
FROM pg_stat_wal;
~~~

### 41.4. Physical replication

~~~sql
SELECT
    application_name,state,sync_state,
    sent_lsn,write_lsn,flush_lsn,replay_lsn,
    replay_lag
FROM pg_stat_replication;
~~~

### 41.5. Slot backlog

~~~sql
SELECT
    slot_name,active,
    restart_lsn,
    pg_wal_lsn_diff(
        pg_current_wal_lsn(),
        restart_lsn
    ) AS bytes_from_restart
FROM pg_replication_slots
WHERE restart_lsn IS NOT NULL;
~~~

### 41.6. Do not wrap monitoring SELECTs inside a long transaction

If a monitoring dashboard holds one transaction open for tens of minutes while polling metrics, it can cause snapshot bloat and connection pressure itself. Run monitoring queries in short sessions under least-privilege roles.

---

## 42. Common Mistakes

| Mistake | Consequence | Correct approach |
|---|---|---|
| "10,000 rows per batch is always fine" | WAL bytes/row varies; bursts still spike | Benchmark + enforce resource budgets |
| "A 100-iteration LOOP commits 100 times" | A function/`DO` runs in one transaction | Control `COMMIT` at valid boundaries |
| "COPY auto-commits per row" | One `COPY` is one statement | Split stream into multiple `COPY`s/transactions |
| "A failed mid-file COPY uses no WAL/storage" | WAL already emitted; aborted tuples need `VACUUM` | Chunk + validate beforehand |
| "`\copy` is server-side SQL" | It is a client-side `psql` meta-command | Use `psql` or driver `COPY` streaming APIs |
| "Passing a DB server path to `\copy`" | `\copy` reads local files on the `psql` host | Distinguish `COPY` vs. `\copy` |
| "Job-wide COMMIT and per-batch COMMIT match" | Atomicity scope differs completely | Design explicit publish strategy |
| "Saving checkpoint after COMMIT is always safe" | Crash window exists between commits | Record checkpoint inside the same transaction |
| "`ON CONFLICT DO NOTHING` is always safe" | Masks differing payloads sharing the same key | Verify key + checksum/version |
| "Retrying a batch can never duplicate" | Ambiguous commit outcomes can duplicate writes | Idempotency + reconciliation |
| "Small batch size guarantees low WAL rate" | Adding workers restores or raises write rate | Throttle aggregate bytes/s |
| "PostgreSQL supports `UPDATE ... LIMIT`" | Syntax error | Use a CTE to select keys, then `UPDATE` |
| "`LIMIT` without `ORDER BY` works for resume" | Non-deterministic selection | Use keyset / `ORDER BY` stable PK |
| "Large `OFFSET` is efficient for paging" | Heavy scans and drift under concurrent writes | Keyset pagination |
| "`SKIP LOCKED` returning 0 rows means all done" | Remaining rows may be locked | Retry + final reconciliation |
| "`UPDATE status=status` generates zero WAL" | Still updates heap tuples | Guard with `IS DISTINCT FROM` |
| "`DELETE` returns disk space to the OS at once" | MVCC leaves dead tuples/bloat | `VACUUM` / partition drops |
| "Running `VACUUM FULL` after every batch" | Rewrites table with heavy locks and WAL | Rely on autovacuum / normal `VACUUM` first |
| "`max_wal_size` is a hard disk cap" | Slots and archiving can retain WAL beyond it | Monitor retention causes |
| "Deleting `pg_wal` segments when disk fills" | Breaks crash recovery and PITR | Fix slots/archiving/capacity |
| "WAL delta equals only my batch's WAL" | Other cluster activity also writes WAL | Isolate tests and contextualize metrics |
| "`wal_bytes` equals inserted row size" | Includes record headers, indexes, and FPIs | Measure bytes/row empirically |
| "An LSN is a timestamp" | It is a WAL stream byte offset | Use `pg_wal_lsn_diff` |
| "Disabling `full_page_writes` is harmless" | Severe crash-recovery corruption risk | Keep `full_page_writes = on` |
| "`fsync=off` is safe for fast production loads" | Risk of corruption and durability loss | Keep durability settings enabled |
| "`synchronous_commit=off` writes zero WAL" | WAL is still written | Distinguish flush ACK vs. WAL generation |
| "`UNLOGGED` behaves like logged tables" | Truncated on crash, not physically replicated | Use only for reloadable staging |
| "Dropping indexes has zero rebuild cost" | Rebuilding generates WAL, I/O, and locks | Measure full end-to-end cost |
| "Fast networks eliminate replica lag" | Standby replay/disk/CPU can still bottleneck | Monitor `replay_lag` |
| "Drop any inactive slot immediately" | Breaks consumer continuity | Identify owner and recovery plan |
| "Archiving does not affect imports" | Slow archiving retains WAL on primary | Capacity-plan archive throughput |
| "`TRUNCATE` fires row-level `DELETE` triggers" | Different trigger semantics | Review event and audit requirements |
| "Multiple `READ COMMITTED` batches share a snapshot" | Each transaction sees fresh changes | Use watermarks or snapshot design |
| "`statement_timeout` alone is enough" | Misses lock waits, pools, and replicas | Configure timeouts at every layer |
| "Rolled-back tests emit zero WAL" | DML before `ROLLBACK` still generates WAL | Test in isolated lab environments |
| "`COPY TO` exports emit WAL like `INSERT`s" | Read-only exports emit no row-change WAL | Separate I/O/snapshot cost from WAL |
| "More workers always run faster" | Lock and I/O contention increases | Benchmark concurrency levels |
| "Finishing file read means data committed" | Batches/chunks may remain unpublished | Checkpoint + reconcile |
| "Swallowing errors with `WHEN OTHERS`" | Loses data and corrupts checkpoints | Catch explicitly / rethrow |
| "Dropping a partition never skips audit logic" | Bypasses per-row `DELETE` triggers | Check compliance and runbook rules |

---

## 43. Pre-Flight Checklist Before Multi-Million-Row Imports

### 43.1. Data and schema

- [ ] Source data is immutable or tagged with checksums/versions.
- [ ] Dedupe keys are well-defined and job/import IDs are stable.
- [ ] Staging can capture invalid inputs and route rejections/quarantine.
- [ ] Target tables enforce appropriate PK, `UNIQUE`, `FK`, and `CHECK` constraints.
- [ ] Trigger/index overhead and write amplification are estimated.
- [ ] Indexes support keyset/`WHERE` predicates for batched updates/deletes.

### 43.2. Transaction correctness

- [ ] Each batch has an explicit transaction boundary.
- [ ] Progress checkpoints commit in the same transaction as business data where required.
- [ ] Retries and idempotency handle ambiguous post-`COMMIT` outcomes.
- [ ] Failed or cancelled jobs maintain state and clean resume logic.
- [ ] Entire multi-million-row jobs are not stuffed into one endless transaction.
- [ ] If job-wide atomicity is required, a staging + publish-version cutover strategy exists.
- [ ] Concurrent writers and isolation levels have been reviewed.

### 43.3. WAL and disk

- [ ] WAL bytes/row and WAL bytes/batch benchmarked on representative data.
- [ ] Sufficient disk headroom across `pg_wal`, data, indexes, and temp files.
- [ ] Checkpoints/FPIs monitored without disabling durability guarantees.
- [ ] Archive bandwidth and replica replay capacity verified.
- [ ] Replication slot owners and backlogs monitored.
- [ ] Not relying on `max_wal_size` as a hard disk cap.
- [ ] Pause policy defined when retained WAL breaches budget.

### 43.4. Performance and locking

- [ ] Batch size and worker concurrency tuned against API p95 latency.
- [ ] DML runs in stable PK order with selective predicates.
- [ ] No deep `OFFSET` scans in long jobs.
- [ ] `SKIP LOCKED` used only where inconsistent views are acceptable.
- [ ] Appropriate `lock_timeout` and `statement_timeout` configured.
- [ ] Autovacuum remains enabled and unblocked.
- [ ] Post-job `ANALYZE` and reconciliation plan ready.

### 43.5. Operations

- [ ] Cancel/rollback plan operates cleanly at batch boundaries.
- [ ] Dashboard tracks WAL rate, disk, lag, locks, and retries.
- [ ] Alerts and on-call ownership assigned.
- [ ] Raw payloads containing passwords or PII are never dumped freely to logs.
- [ ] Partial failures and ambiguous commits tested.
- [ ] Expected counts and checksums documented.
- [ ] Small canary run executed before full migration.

---

## 44. Practice Exercises

Exercises use the `wal_batch_lab` schema unless stated otherwise. Several prompts contain intentionally invalid SQL or ask you to evaluate configuration changes—**never run them in production**. When practicing DML, wrap tests in transactions with `ROLLBACK` or refresh your lab dataset to preserve initial state.

### Exercise 1 — What is WAL?

Explain why PostgreSQL writes WAL and how data pages not yet flushed to disk at `COMMIT` can still be recovered after a crash under standard durability rules.

### Exercise 2 — WAL and rollbacks

A transaction `INSERT`s 1 million rows and then issues `ROLLBACK`. Can you conclude zero WAL was generated because zero rows committed? Why or why not?

### Exercise 3 — Batching levels

Distinguish batch, statement, transaction, and database checkpoint. Does a loop of 100 `INSERT`s inside a `DO` block automatically produce 100 commits?

### Exercise 4 — Single transaction vs. multiple batches

Given a 2-million-row file, list at least four benefits and three risks/trade-offs of splitting it into 200 batches × 10,000 rows committed separately.

### Exercise 5 — Job-wide atomicity

An import spans 200 batches; batch 156 fails. Business requirement: users must only see the new dataset version once the entire file succeeds. Propose a safe publication design instead of writing live batches directly into the serving table.

### Exercise 6 — Choosing batch size

Why can't 10,000 rows/batch serve as a universal default for every table? Name at least six metrics used to tune batch size.

### Exercise 7 — COMMIT inside procedures

Function `SELECT process_all_rows()` loops over millions of rows and wants to `COMMIT` every 1,000 rows. Does that work? Where should transaction control move? If using a procedure, state one constraint on the caller.

### Exercise 8 — Server-side COPY vs. client-side \copy

A CSV resides on a laptop while PostgreSQL runs in the cloud. Why does `COPY ... FROM '/home/user/orders.csv'` fail on the server? Write the appropriate `\copy` command.

### Exercise 9 — Does COPY split transactions automatically?

A `COPY FROM STDIN` loads 500,000 rows and fails at line 300,000. Were the earlier rows automatically committed? How do you checkpoint every 10,000 rows?

### Exercise 10 — Invalid numeric CSV values

Staging has column `amount numeric`, but the CSV contains `not-a-number`. Can you load normally and then validate with `WHERE amount ~ ...`? Propose an appropriate raw staging model.

### Exercise 11 — Staging import and checkpoint

Write a transaction inserting 2 rows into `wal_batch_lab.order_stage` with `import_id = 9001`, `source_row_no = 10, 11`, and updating `import_jobs.last_committed_row = 11` in the same transaction.

### Exercise 12 — Out-of-order checkpointing

An app commits `last_committed_row = 50000` before inserting rows `40001..50000`. If the `INSERT` fails, what happens on resume? Show the correct design.

### Exercise 13 — Retries and unique keys

A batch loses its `COMMIT` response. Explain how `PRIMARY KEY(import_id, source_row_no)` helps retries, and when `ON CONFLICT DO NOTHING` could mask a bug.

### Exercise 14 — Payload conflicts

Staging row `(9001, 25)` has `amount = 100`. A retry sends the same key with `amount = 200`. Should you ignore it? Design a check that catches non-equivalent conflicts.

### Exercise 15 — ON CONFLICT DO UPDATE with duplicate IDs

A staging batch contains two source rows with `order_id = 401`. Why can `INSERT ... ON CONFLICT DO UPDATE` fail? How do you deduplicate before merging?

### Exercise 16 — Measuring WAL with LSNs

Suppose pre- and post-job WAL LSNs are stored in `v_before` and `v_after`. Write SQL to compute WAL bytes and MiB, and explain why this delta is not strictly exclusive to the job under concurrent load.

### Exercise 17 — WAL statistics

Using `pg_stat_wal`, read `wal_bytes`, `wal_fpi`, and `wal_records`. When sampling twice to compute a delta, which column must you check to ensure stats weren't reset in between?

### Exercise 18 — Full pg_wal directory

The server is low on disk because `pg_wal` grew large. Should you delete a few WAL segments using OS commands? List at least four WAL retention causes to check.

### Exercise 19 — max_wal_size

A DBA sets `max_wal_size = 8GB`, yet `pg_wal` uses 30GB. Does that prove PostgreSQL has a bug? Why isn't it a hard cap?

### Exercise 20 — Full-page images

Explain why WAL spikes right after checkpoints. Is `full_page_writes = off` a sound solution to shrink WAL?

### Exercise 21 — wal_compression

Which workloads see WAL reductions from `wal_compression`? What is the main trade-off? Does every `UPDATE` shrink equally?

### Exercise 22 — UPDATE LIMIT

Fix this invalid SQL:

~~~sql
UPDATE wal_batch_lab.orders
SET order_status='paid'
WHERE order_status='new'
LIMIT 2;
~~~

Use a CTE to select the two lowest `order_id` values and update exactly those two rows.

### Exercise 23 — SKIP LOCKED

Two workers concurrently update `new` orders. Write a `FOR UPDATE SKIP LOCKED` CTE and explain why returning 0 rows does not guarantee all work is complete.

### Exercise 24 — UPDATE setting the same value

Can `UPDATE orders SET order_status = order_status` generate WAL and dead tuples? Write a predicate updating only when the value truly differs from `'paid'`.

### Exercise 25 — Batched DELETE

Write a `DELETE` removing at most 1,000 `cancelled` orders ordered by ID. Why doesn't `DELETE` shrink the data file right away?

### Exercise 26 — Partitioned retention

An event table is partitioned monthly; all data older than 2 years must be purged. Why is dropping an old partition often superior to row-by-row `DELETE`? Which risks must be reviewed?

### Exercise 27 — Keyset vs. OFFSET

Why is `LIMIT 1000 OFFSET 5000000` inefficient? Write the next-page query using `order_id > last_id`.

### Exercise 28 — Concurrency and keyset

While a job has progressed to `order_id = 1000`, another transaction inserts a row with `order_id = 900`. Will the job pick up that new row? What pattern is needed if a fixed snapshot is required?

### Exercise 29 — WAL and replica lag

Write a query inspecting `sent_lsn`, `write_lsn`, `flush_lsn`, and `replay_lsn` from `pg_stat_replication`. List three throttling measures if replay lag climbs during a job.

### Exercise 30 — Time lag vs. byte lag

Why is `pg_last_xact_replay_timestamp()` on a standby unreliable as an absolute lag indicator when the primary is idle? What metrics should supplement it?

### Exercise 31 — Replication slot retention

Write SQL calculating WAL bytes between `pg_current_wal_lsn()` and each slot's `restart_lsn`. Why shouldn't an inactive slot always be dropped immediately?

### Exercise 32 — Archive backlog

`pg_stat_archiver.failed_count` climbs during an import. What causes this, and why is merely shrinking batch size not always enough?

### Exercise 33 — UNLOGGED staging

A staging table can be reloaded from an immutable source. When is `UNLOGGED` appropriate? Name three scenarios where `UNLOGGED` must not be used.

### Exercise 34 — synchronous_commit

Does `synchronous_commit = off` stop PostgreSQL from writing WAL? What are the primary risks around commit acknowledgment and crashes? Why avoid using it lightly for payments?

### Exercise 35 — Autovacuum

A batch `DELETE` of 30 million rows committed. Why didn't the data file shrink immediately? How does `VACUUM ANALYZE` help, and what trade-offs accompany `VACUUM FULL`?

### Exercise 36 — Index write amplification

A table has 15 indexes and an importer inserts 10 million rows. Describe the WAL and I/O impact. Should you drop all indexes and FKs to go faster?

### Exercise 37 — JDBC batching

Write Java pseudocode using `PreparedStatement.addBatch`/`executeBatch` inside one transaction per 2,000 rows, rolling back on errors. State what `executeBatch` does not guarantee.

### Exercise 38 — Rate limiting

A worker shrinks batch size from 10,000 to 2,000 rows while scaling concurrency from 2 to 10 workers. Is WAL bytes/s guaranteed to drop? Design a throttling policy based on WAL rate and replica lag.

### Exercise 39 — Timeouts

Distinguish `lock_timeout`, `statement_timeout`, and `idle_in_transaction_session_timeout`. If a batch times out, should the checkpoint advance?

### Exercise 40 — WAL LSN vs. wal_bytes

Contrast `pg_wal_lsn_diff` with `pg_stat_wal.wal_bytes` deltas. Why shouldn't either be attributed exclusively to the import job when other sessions are active?

### Exercise 41 — COPY TO and consistency

You export a 500-million-row table using 500 separate keyset queries, each committing individually. Does that guarantee a consistent snapshot? Compare with a long `REPEATABLE READ` transaction and dedicated backup methods.

### Exercise 42 — pg_dump vs. CSV export

A team plans to use `\copy (SELECT * FROM orders) TO orders.csv` as a complete backup of a schema containing FKs, indexes, triggers, sequences, and grants. Why is this insufficient?

### Exercise 43 — Lock contention

A backfill runs `UPDATE ... FOR UPDATE SKIP LOCKED` with multiple workers, yet API p95 latency spikes. List at least five signals to inspect and ways to relieve pressure.

### Exercise 44 — Crash after batch 72

A job processes 1 million rows in 100 batches. After batch 72, the connection drops at `COMMIT`, and the checkpoint reads `710,000`. Can you assume you should resume from row `710,001`? Outline the verification steps before resuming.

### Exercise 45 — Safe maintenance

An engineer proposes disabling `fsync`, `full_page_writes`, `wal_level`, and autovacuum to speed up ingestion. Explain the risks and propose safer optimization alternatives.

### Exercise 46 — WAL growing while job rate stays flat

The importer stays steady at 5 MiB/s, yet retained `pg_wal` climbs rapidly, a replication slot is inactive, and archive failures rise. Prioritize remediation steps. Should you increase `max_wal_size` indefinitely?

### Exercise 47 — End-to-end import design

You receive a 100 GiB CSV of order events with unique `source_event_id`s that must be validated, deduplicated, stored in a logged destination with replicas, and resumable after crashes. Sketch the pipeline, metadata schema, commit boundaries, monitoring, and error handling.

### Exercise 48 — Large-scale retention deletion design

A multi-billion-row event table with 90-day retention runs under 24/7 OLTP traffic with tight primary disk space and replica lag. Compare batched `DELETE` against partition lifecycle management and lay out a safe migration plan with monitoring, rollback, and a checklist.

### Exercise 49 — Ambiguous commit and external side effects

After each batch `COMMIT`, a job invokes an HTTP webhook, and the connection drops right at `COMMIT`. How do you prevent duplicate webhooks or firing webhooks for uncommitted data?

### Exercise 50 — Comprehensive incident runbook

During peak traffic, a 20-million-row backfill drives WAL to 300 MiB/s, the archiver fails, slot lag hits 100 GiB, API p99 jumps from 200ms to 5s, and autovacuum falls behind reclaiming dead tuples. Write a safety-first runbook restoring stability and resuming without corrupting data.

---

## 45. Solutions — Exercises 1 to 25

### Exercise 1 — WAL and crash recovery

PostgreSQL logs WAL so committed changes under configured durability rules can always be recovered even if modified data pages have not yet flushed to disk. WAL records flush ahead of commit guarantees. Upon restarting after a crash, PostgreSQL replays the required WAL stream to restore heap and index files to a consistent state.

WAL also drives physical streaming replication, archiving, and logical decoding. Never confuse WAL with disposable application logs.

### Exercise 2 — WAL after ROLLBACK

No. DML executed before `ROLLBACK` still generates WAL records, dirty buffers, and aborted tuple versions. `ROLLBACK` ensures changes **are not committed**, but it does not erase already-emitted WAL bytes from the log stream.

This is why you should never "test 100 million `UPDATE`s and roll back" during peak traffic thinking it has zero cost.

### Exercise 3 — Batch/transaction scope

- Batch: job-chosen processing slice.
- Statement: individual SQL command.
- Transaction: atomic `COMMIT`/`ROLLBACK` scope.
- Database checkpoint: engine buffer-flushing and crash-recovery baseline operation.

A `DO` block running a 100-`INSERT` loop executes as one SQL statement inside a single transaction. **It does not commit per iteration**.

### Exercise 4 — Splitting into 200 batches

Benefits:

1. Shorter transactions and lock lifetimes.
2. Easy pause/resume from checkpoints.
3. Rollbacks and retries stay scoped to the failing batch.
4. WAL generation can be paced between batches.
5. Readers and standbys get breathing room to catch up between commits.

Trade-offs:

1. No global job-wide atomicity; readers may see intermediate state.
2. Higher total `COMMIT`, round-trip, and metadata overhead.
3. Requires idempotency, reconciliation, and progress tracking.
4. Exposed to concurrent mutations between transactions if a single global snapshot was assumed.

There is no guarantee 10,000 rows/batch is optimal; benchmark it.

### Exercise 5 — Job-wide atomicity

Use staging plus dataset versioning:

1. Load batches across multiple transactions into staging tagged with `import_id`/`dataset_version`.
2. Validate per chunk and end-of-job.
3. Reconcile row counts, duplicates, source checksums, FKs, and business invariants.
4. Only once verified, update `published_version` metadata or execute the designed cutover in one short transaction.
5. Readers query only `published_version`, hiding unpublished rows.

Never use one gigantic transaction for the entire load if lock/snapshot/WAL budgets forbid it. Verify cutover metadata and reader snapshots so sessions never mix versions.

### Exercise 6 — Tuning batches via metrics

Row counts cannot serve as the sole proxy because row widths, indexes, `JSONB`, triggers, and FPIs vary dramatically. Measure:

- WAL bytes/batch and WAL MiB/s.
- Batch duration and `COMMIT` latency.
- API p95/p99 latency.
- Replica receive and replay lag.
- Archive backlog and retained WAL disk.
- Lock waits and deadlocks.
- CPU, I/O, dirty writes, and checkpoints.
- Autovacuum backlog and dead tuples.
- Connection pool usage and waits.

Size batches and concurrency so both live business traffic and ingestion stay within budget.

### Exercise 7 — COMMIT inside functions

Regular PL/pgSQL functions cannot call `COMMIT`/`ROLLBACK` mid-loop. Move transaction boundaries to **the caller** (Java/`psql`/script) or use a procedure with transaction control in a valid context.

If using a procedure, `CALL` must run at top level or in an eligible call chain; **never wrap `CALL` inside an explicit `BEGIN` transaction block** expecting internal `COMMIT`s to work. Also mind `EXCEPTION` blocks, procedure attributes, and version rules.

### Exercise 8 — COPY vs. \copy

`COPY ... FROM '/home/user/orders.csv'` looks for the file **on the PostgreSQL server filesystem**, not the client laptop; the role may also lack server-file read privileges.

In `psql` on the laptop, use:

~~~text
\copy wal_batch_lab.order_stage (import_id,source_row_no,order_id,customer_id,amount,order_status) FROM '/home/user/orders.csv' WITH (FORMAT csv, HEADER true)
~~~

The path refers to the local client filesystem. `\copy` is a `psql` meta-command and cannot be passed directly to a JDBC `Statement`.

### Exercise 9 — COPY failing mid-file

A single `COPY` is one statement within a transaction; rows loaded before the error **do not commit per row**. When the statement/transaction aborts, uncommitted tuples do not become visible rows, yet generated WAL and dead storage may still need `VACUUM`.

To checkpoint every 10,000 rows, split the input into 10,000-row chunks, run one `COPY` per chunk in its own transaction, and update import progress **in that same transaction**.

### Exercise 10 — Raw staging for malformed numeric CSV inputs

No. Because the staging column is `numeric`, `COPY` tries to cast `'not-a-number'` and aborts **before any row reaches the table for querying**. To inspect malformed inputs, create a raw text staging table:

~~~sql
CREATE TABLE wal_batch_lab.raw_order_stage (
    import_id bigint,
    source_row_no bigint,
    order_id_text text,
    amount_text text,
    status_text text
);
~~~

Then validate formats, safely cast, and quarantine invalid rows before promoting to typed staging. Avoid naive regexes assuming they catch every overflow or numeric edge case; combine validation and controlled error handling.

### Exercise 11 — Transaction with checkpoint

~~~sql
BEGIN;

INSERT INTO wal_batch_lab.order_stage
    (import_id,source_row_no,order_id,customer_id,amount,order_status)
VALUES
    (9001,10,210,21,10.00,'new'),
    (9001,11,211,22,20.00,'paid')
ON CONFLICT (import_id,source_row_no) DO NOTHING;

UPDATE wal_batch_lab.import_jobs
SET last_committed_row=11,
    status='running',
    updated_at=clock_timestamp()
WHERE import_id=9001;

COMMIT;
~~~

Ensure source rows `1..11` have all succeeded before advancing a sequential watermark so gaps aren't skipped. On retries, pair `DO NOTHING` with payload consistency verification.

### Exercise 12 — Checkpoint advancing ahead of data

If metadata commits row `50000` before rows `40001..50000` insert and the `INSERT` fails, resuming skips that missing range -> **data loss**. Correct pattern:

~~~sql
BEGIN;
-- INSERT/COPY chunk and validate/merge.
UPDATE wal_batch_lab.import_jobs SET last_committed_row=50000
WHERE import_id=9001;
COMMIT;
~~~

If anything fails, roll back both the chunk and the checkpoint. With parallel out-of-order workers, track completed ranges before advancing the watermark.

### Exercise 13 — Retrying after an ambiguous commit

The staging primary key `(import_id, source_row_no)` prevents saving the same logical row twice. Upon reconnecting, check progress and row presence, then retry idempotently.

However, `ON CONFLICT DO NOTHING` masks cases where the source row changed, mappings broke, or an `import_id` was reused for a different file. Store checksums/file versions and compare payloads to distinguish safe replays from conflicts.

### Exercise 14 — Payload conflicts

Never ignore it silently. If `(9001, 25)` stored `amount = 100` and a retry supplies `200`, the retry is not equivalent. Remedies:

- Persist `source_checksum` per file/row.
- Query existing payload on conflict.
- Raise a conflict/rejection if hashes or values diverge.
- Assign a distinct `import_id` per immutable source object/version.
- Check business versions to determine whether an update is authorized.

`ON CONFLICT DO NOTHING` is only acceptable when the contract explicitly permits ignoring duplicate keys regardless of payload differences—rarely safe for monetary data.

### Exercise 15 — Multiple source rows sharing one destination key

`INSERT ... ON CONFLICT DO UPDATE` fails with a cardinality violation if one statement tries to update the same target row multiple times.

Deduplicate first:

~~~sql
WITH dedup AS (
    SELECT DISTINCT ON (order_id)
        order_id,customer_id,amount,order_status
    FROM wal_batch_lab.order_stage
    WHERE import_id=9001
      AND order_id IS NOT NULL
    ORDER BY order_id,source_row_no DESC
)
INSERT INTO wal_batch_lab.orders
    (order_id,customer_id,amount,order_status)
SELECT order_id,customer_id,amount,order_status
FROM dedup
WHERE customer_id IS NOT NULL
  AND amount >= 0
  AND order_status IN ('new','paid','cancelled')
ON CONFLICT (order_id) DO UPDATE
SET
    customer_id=EXCLUDED.customer_id,
    amount=EXCLUDED.amount,
    order_status=EXCLUDED.order_status;
~~~

Here, picking the highest `source_row_no` follows an **assumed ordering rule**. If file order does not define freshness, use a source version or event timestamp with a deterministic tie-breaker and concurrency checks.

### Exercise 16 — LSN delta

~~~sql
SELECT
    pg_wal_lsn_diff(v_after::pg_lsn, v_before::pg_lsn) AS wal_bytes,
    pg_wal_lsn_diff(v_after::pg_lsn, v_before::pg_lsn)
        / 1024 / 1024 AS wal_mib;
~~~

`v_before` and `v_after` are placeholders for observed LSNs, not runnable verbatim without variable bindings. Measure immediately before and right after `COMMIT`. The delta reflects **cluster-wide WAL** between both points, including concurrent sessions, background tasks, and commit records.

### Exercise 17 — pg_stat_wal

~~~sql
SELECT wal_bytes,wal_fpi,wal_records,stats_reset
FROM pg_stat_wal;
~~~

When computing a delta across two snapshots, confirm `stats_reset` stayed unchanged. If `stats_reset` changed, the baseline shifted and `Y - X` is invalid. You may also need sufficiently long intervals to smooth stats reporting lag and noise.

### Exercise 18 — Full pg_wal

**Never manually delete WAL segments.** Inspect:

1. Replication slots holding back `restart_lsn`.
2. Physical standby receive/replay lag.
3. Archive failures or backlogs.
4. High WAL generation from a new job.
5. Checkpoint/retention parameters such as `wal_keep_size` and `max_wal_size`.
6. Offline backup or replication consumers.

Pause or throttle ingestion safely at a batch boundary, fix the retention root cause, and maintain adequate disk headroom.

### Exercise 19 — max_wal_size is not a hard cap

Not necessarily a bug. `max_wal_size` guides checkpoints and WAL recycling—it is not a hard disk quota. Pending archiving, active/stale replication slots, `wal_keep_size`, and recovery requirements can all retain WAL past that target. Diagnose the retention cause before raising configuration limits.

### Exercise 20 — FPIs and checkpoints

With `full_page_writes = on`, the first modification to each page after a checkpoint writes a full-page image to WAL under qualifying conditions to guard against torn writes. Touching many pages right after a checkpoint makes `wal_fpi` and `wal_bytes` surge periodically.

**Never disable `full_page_writes` casually**: it compromises crash recovery and risks corruption. Measure checkpoint cadence, FPIs, WAL compression, storage I/O, and batch rate instead.

### Exercise 21 — wal_compression

`wal_compression` compresses full-page images when workloads emit heavy FPIs, reducing WAL bytes, network traffic, archive volume, and replication overhead at the cost of compression/decompression CPU (varying by data, codec, and PostgreSQL version).

Not every `UPDATE` shrinks equally: workloads dominated by small logical WAL records or incompressible payloads gain little. Benchmark end-to-end.

### Exercise 22 — UPDATE up to two rows

~~~sql
WITH todo AS (
    SELECT order_id
    FROM wal_batch_lab.orders
    WHERE order_status='new'
    ORDER BY order_id
    LIMIT 2
)
UPDATE wal_batch_lab.orders AS o
SET order_status='paid',
    updated_at=clock_timestamp()
FROM todo AS t
WHERE o.order_id=t.order_id
RETURNING o.order_id,o.order_status;
~~~

PostgreSQL does not accept `UPDATE ... LIMIT` directly. With concurrent workers, add `FOR UPDATE SKIP LOCKED` and re-check predicates inside the `UPDATE`.

### Exercise 23 — SKIP LOCKED

~~~sql
WITH todo AS (
    SELECT order_id
    FROM wal_batch_lab.orders
    WHERE order_status='new'
    ORDER BY order_id
    LIMIT 2
    FOR UPDATE SKIP LOCKED
)
UPDATE wal_batch_lab.orders AS o
SET order_status='paid'
FROM todo AS t
WHERE o.order_id=t.order_id
  AND o.order_status='new'
RETURNING o.order_id;
~~~

If all remaining rows are currently locked by other transactions, the CTE returns 0 rows even though unfinished work remains. Workers must poll/retry, coordinate state, and reconcile upon completion. `SKIP LOCKED` yields inconsistent snapshot views and is unsuitable for general reporting.

### Exercise 24 — Updating to the same value

Yes. Even `SET status = status` can write new heap tuple versions, generate WAL, and touch indexes. When only rows differing from `'paid'` should change:

~~~sql
UPDATE wal_batch_lab.orders
SET order_status='paid',
    updated_at=clock_timestamp()
WHERE order_id=101
  AND order_status IS DISTINCT FROM 'paid';
~~~

`IS DISTINCT FROM` is `NULL`-safe, even though `order_status` is `NOT NULL` in this lab.

### Exercise 25 — Deleting up to 1,000 rows

~~~sql
WITH doomed AS (
    SELECT order_id
    FROM wal_batch_lab.orders
    WHERE order_status='cancelled'
    ORDER BY order_id
    LIMIT 1000
)
DELETE FROM wal_batch_lab.orders AS o
USING doomed AS d
WHERE o.order_id=d.order_id
RETURNING o.order_id;
~~~

Under MVCC, `DELETE` does not shrink data files immediately. Dead tuple versions become reclaimable once active snapshots pass; autovacuum/`VACUUM` reuses space internally without necessarily returning disk blocks to the OS. At huge retention scale, partitioned drops are often better.

---

## 46. Solutions — Exercises 26 to 50

### Exercise 26 — Retention via partitions

When an entire partition holds expired rows, detaching and dropping it avoids row-by-row `DELETE` DML and millions of dead tuples needing `VACUUM`. Always review:

- Foreign keys, constraints, and dependencies.
- Locks during `DETACH`/`DROP`.
- Per-row `DELETE` audit triggers that will not fire.
- Replicas, PITR, and schema dependencies.
- Backup/restore requirements for retained data.
- Whether partition boundaries match retention dates cleanly.
- Cutover steps, privileges, and rollback plans.

Never drop a partition that still holds non-expired records.

### Exercise 27 — Keyset instead of deep OFFSET

`OFFSET 5000000` must scan and skip millions of rows and breaks under concurrent inserts/deletes. Keyset alternative:

~~~sql
SELECT order_id,customer_id,amount
FROM wal_batch_lab.orders
WHERE order_id > 5000000
ORDER BY order_id
LIMIT 1000;
~~~

Here `5000000` represents **the actual `last_id` returned**, not a physical offset. Advance `last_id` to the last committed/exported ID, leveraging the primary-key index.

### Exercise 28 — Concurrent inserts below the watermark

Once the job passes ID `1000`, a newly inserted row at ID `900` will not appear in `WHERE id > 1000`. If a point-in-time snapshot is required, use an immutable source snapshot, a `created_at`/version watermark, or a `REPEATABLE READ` snapshot transaction (weighing vacuum cost). To capture concurrent changes continuously, use CDC/change capture or a reconciliation sweep rather than basic keyset paging alone.

### Exercise 29 — Replica monitoring

~~~sql
SELECT
    application_name,
    state,
    sent_lsn,
    write_lsn,
    flush_lsn,
    replay_lsn,
    replay_lag
FROM pg_stat_replication;
~~~

When replay lag rises:

1. Reduce workers and aggregate WAL MiB/s.
2. Shrink batch size or pause at commit boundaries so standbys catch up.
3. Inspect standby CPU, I/O, network, and archive/slot backlogs.
4. Route read-your-writes traffic away from lagging replicas if SLAs are breached.
5. If `pg_stat_replication` returns zero rows when standbys should exist, check connection/replication health instead of assuming zero lag.

### Exercise 30 — Time lag is not absolute

`pg_last_xact_replay_timestamp()` records the commit time of the last replayed transaction. If the primary sits idle for hours, an old timestamp **does not mean the standby is hours behind**. Also query:

~~~sql
SELECT pg_last_wal_receive_lsn(),
       pg_last_wal_replay_lsn();
~~~

On the primary, check `pg_stat_replication` and LSN byte gaps, combined with heartbeat monitoring. Never rely solely on timestamp differences.

### Exercise 31 — Replication slot backlogs

~~~sql
SELECT
    slot_name,
    slot_type,
    active,
    restart_lsn,
    pg_wal_lsn_diff(
        pg_current_wal_lsn(),
        restart_lsn
    ) AS wal_bytes_from_restart
FROM pg_replication_slots
WHERE restart_lsn IS NOT NULL;
~~~

An inactive slot may belong to a connector paused for maintenance. Dropping it prematurely breaks consumer continuity from its previous LSN. Identify the owner, target, expected downtime, and resync plan first.

### Exercise 32 — Archive backlogs

Root causes include:

- Full or unreachable archive destination.
- Network or object-storage latency.
- Broken permissions or syntax in `archive_command`.
- Archive throughput slower than WAL production rate.
- Stalled retry pipelines or destination errors.

Shrinking batch size only smooths bursts; if total WAL MiB/s still exceeds archive bandwidth, the backlog continues growing. Reduce **aggregate ingest rate**, repair the archive pipeline, and ensure disk headroom. Never delete WAL required for PITR.

### Exercise 33 — Conditional suitability of UNLOGGED

Appropriate when:

- Raw staging is a cache fully reloadable from an immutable source.
- Physical standbys do not need to read staging.
- Losing staging in a crash never corrupts published destinations or checkpoints.
- An automated reload runbook exists post-crash.

Inappropriate for:

1. Authoritative payment or order tables.
2. Checkpoints/progress tables needing durability.
3. Tables requiring physical replication.
4. Non-replayable data.
5. SLOs/RPOs forbidding staging loss.

`UNLOGGED` lowers table-data WAL writes where applicable, but is never "zero WAL for everything."

### Exercise 34 — synchronous_commit

`synchronous_commit = off` **does not** stop WAL generation. It weakens flush/ack guarantees at `COMMIT`, risking loss of recently acknowledged commits during a crash.

For payments or business transactions requiring strict durability, never flip this as a harmless optimization. Review RPO, replication guarantees, ambiguous commit handling, idempotency, and failure modes first.

### Exercise 35 — DELETE and VACUUM

Under MVCC, `DELETE` leaves dead row versions and index entries until cleanup is safe. Files do not shrink immediately; space becomes reusable internally after `VACUUM`.

~~~sql
VACUUM (ANALYZE) wal_batch_lab.orders;
~~~

Run this as a separate maintenance command in test labs or maintenance windows to reclaim dead tuples and refresh planner stats. `VACUUM FULL` rewrites the table under strict locks with heavy storage and WAL cost; never run it after every batch unnecessarily.

### Exercise 36 — Index amplification

Every `INSERT` updates all applicable indexes, multiplying WAL records, buffer writes, CPU, and lock contention. Having 15 indexes dramatically raises cost compared to a PK-only table.

Never drop all indexes and FKs recklessly because:

- Indexes enforce `PRIMARY KEY` and `UNIQUE` guarantees.
- Foreign keys preserve referential integrity.
- Rebuilding indexes afterward still consumes heavy WAL, I/O, disk, and locks.
- Live queries degrade without indexes.
- Invalid or duplicate data can sneak in while constraints are absent.

Keep only necessary indexes, plan staging/cutovers carefully, and benchmark end-to-end.

### Exercise 37 — JDBC batching

Pseudocode:

~~~java
String sql =
    "INSERT INTO wal_batch_lab.orders " +
    "(order_id, customer_id, amount, order_status) " +
    "VALUES (?, ?, ?, ?) " +
    "ON CONFLICT (order_id) DO NOTHING";

boolean previousAutoCommit = connection.getAutoCommit();
try {
    connection.setAutoCommit(false);

    try (PreparedStatement ps = connection.prepareStatement(sql)) {
        int count = 0;
        for (Order row : rows) {
            ps.setLong(1, row.id());
            ps.setLong(2, row.customerId());
            ps.setBigDecimal(3, row.amount());
            ps.setString(4, row.status());
            ps.addBatch();

            count++;
            if (count == 2000) {
                ps.executeBatch();
                connection.commit();
                count = 0;
            }
        }

        if (count > 0) {
            ps.executeBatch();
            connection.commit();
        }
    }
} catch (SQLException ex) {
    connection.rollback();
    throw ex;
} finally {
    connection.setAutoCommit(previousAutoCommit);
}
~~~

This is **logic pseudocode**, not production-ready Java: call `clearBatch()` after `executeBatch()` per driver API, handle closing/rollbacks safely on broken connections, and commit **a chunk checkpoint inside each chunk transaction**. Avoid resetting `autoCommit` blindly on broken connections or fighting framework transaction managers.

`executeBatch()` does not guarantee **a single server SQL statement** or transaction if `autoCommit` scope is misconfigured. Always maintain explicit transaction ownership and idempotent retries.

### Exercise 38 — Shrinking batch size while raising concurrency

WAL rate is not guaranteed to drop. Before: 2 workers × 10,000 rows/batch; after: 10 workers × 2,000 rows/batch. Concurrent row throughput remains comparable or increases.

Policy:

- Track rolling 30–60s WAL bytes/s, replica replay lag, and API latency.
- When lag, disk, or latency crosses thresholds, **cut total concurrency** or cap rows/s.
- Keep batch sizes small to shorten lock/transaction lifetimes.
- Ramp up slowly only after metrics remain healthy over multiple intervals.
- Enforce a hard stop when `pg_wal` nears disk exhaustion.
- Apply backoff with jitter and avoid conflicting control loops.

### Exercise 39 — Timeouts

| Setting | Scope |
|---|---|
| `lock_timeout` | Time spent waiting to acquire a lock |
| `statement_timeout` | Total statement execution duration |
| `idle_in_transaction_session_timeout` | Duration a session stays idle inside an open transaction |

If a batch times out and fails, **never advance the checkpoint**. The caller rolls back, classifies the error, and retries if eligible. If the checkpoint already committed in a prior separate transaction before DML, the design is buggy.

### Exercise 40 — LSN vs. pg_stat_wal

- `pg_wal_lsn_diff()` measures byte distance between two WAL stream positions.
- `pg_stat_wal.wal_bytes` reports accumulated WAL bytes subject to stats resets/lag alongside FPI and record counters.

Both observe **cluster-wide WAL**, not per-job totals. Under live traffic, measure across controlled windows, mark boundaries clearly, and treat bytes/batch as an estimate subject to concurrent noise.

### Exercise 41 — Export consistency

Separate `READ COMMITTED` transactions see different snapshots as concurrent inserts, updates, and deletes occur between chunks. Keyset paging stops `OFFSET` drift without creating a global snapshot.

A single `REPEATABLE READ` transaction preserves one snapshot across queries, though multi-hour exports stall `VACUUM` cleanup and tie up resources. For huge consistent database backups, use `pg_dump` or snapshot-aware backup tooling instead of 500 uncoordinated `SELECT`s.

### Exercise 42 — CSV is not a complete backup

A single-table CSV export omits:

- Schema DDL.
- Indexes.
- PK/FK/`CHECK` constraints.
- Triggers and functions.
- Sequences and current sequence values.
- Privileges and ownership.
- Extensions, settings, and cluster/database-wide objects.
- Multi-table transactional consistency.

Use `pg_dump` or tested backup strategies for disaster recovery; CSV suits data exchange, not full backups.

### Exercise 43 — Lock and API latency during backfill

Signals to check:

1. API p95/p99 latency and throughput.
2. Lock waits and `pg_stat_activity.wait_event`.
3. Batch duration and transaction age.
4. Rows/s, WAL MiB/s, and checkpoints/FPIs.
5. Index scans and query plans.
6. Autovacuum activity and dead tuples.
7. Replica lag, archive backlog, and free disk.
8. Worker concurrency, pool pressure, and hot rows.

Reduce workers, shrink batch sizes, pause between boundaries, partition work into low-contention key ranges, and enforce `lock_timeout`/`statement_timeout`. If SLOs still suffer, pause and reschedule off-peak or switch to build-and-cutover.

### Exercise 44 — Crash after batch 72

The checkpoint reads `710,000`, whereas 72 batches × 10,000 = `720,000`. **Never blindly resume** at `710,001` or `720,001` before inspecting commit state.

Steps:

1. Reconnect and read the authoritative DB checkpoint.
2. Check whether batch 72's target keys/rows exist in the database.
3. Verify atomicity: was the checkpoint designed to commit in **the same transaction** as batch 72?
4. Compare checksums, source versions, and batch boundaries.
5. If checkpoint is `710,000` and batch 72 data is absent, retry idempotently.
6. If batch 72 data exists without the checkpoint update, metadata design is non-atomic or broken; reconcile and repair before continuing.
7. Prevent duplicate external side effects or outbox events.
8. Resume only after confirming the committed boundary.

### Exercise 45 — Proposal to disable durability and autovacuum

Risks:

- `fsync=off`: crashes or power loss can corrupt data.
- `full_page_writes=off`: removes torn-page protection during crash recovery.
- Lowering `wal_level`: breaks physical/logical replication or PITR and requires restarts.
- Disabling autovacuum: triggers bloat, wraparound risk, and lost space reclamation.

Safer alternatives:

1. Chunked `COPY` / `INSERT ... SELECT` and key-ordered DML.
2. Short batch transaction boundaries.
3. Smart staging (`UNLOGGED` only when fully reloadable).
4. Dropping truly non-essential indexes only under an approved plan.
5. Metric-driven checkpoint and WAL compression tuning.
6. Throttling aggregate write rate and worker concurrency.
7. Ensuring archive/standby bandwidth and disk headroom.
8. Reconciling and running `VACUUM`/`ANALYZE` post-load.

### Exercise 46 — Retained WAL growing despite steady ingest rate

Priority actions:

1. Pause or throttle the importer if free disk is critically low.
2. Inspect archive failures and fix archive destination, config, or permissions.
3. Identify replication slot owners/consumers and why the slot went inactive.
4. Measure `restart_lsn` backlog and standby health.
5. Protect disk headroom during recovery without deleting WAL manually.
6. Resume only after archiving and consumers catch up and retention pressure drops.

Increasing `max_wal_size` endlessly does not fix stuck slots or broken archiving; it only delays exhaustion or alters checkpoint pacing. Temporary disk expansion may buy time, never replacing root-cause repair.

### Exercise 47 — Designing a 100 GiB CSV ingestion pipeline

Recommended design:

1. Store immutable source files with version/checksum in secure object storage.
2. Maintain `import_jobs(import_id, source_uri, checksum, status, ...)` and `import_chunks(import_id, chunk_id, start_offset, end_offset, checksum, status)`.
3. Read bounded chunks; normalize encoding/CSV, stream `COPY` to staging (logged, or unlogged **only with a reload plan**).
4. Validate required fields, types, and rules; quarantine bad rows with sanitized line references.
5. Deduplicate by `source_event_id` enforced `UNIQUE` on destination; compare payload/version on conflicts.
6. Per chunk transaction: merge valid rows, record accepted/rejected counts, and mark chunk status committed in the same transaction.
7. On lost `COMMIT` responses, check chunk status and destination keys before retrying—never blind-replay.
8. Reconcile total source rows = accepted + rejected + duplicates per policy; tolerate zero silent drops.
9. Monitor WAL bytes/batch, MiB/s, `pg_wal` disk, slots/archive, replica lag, locks, API latency, and dead tuples.
10. Throttle concurrency/batches within budget and pause at boundaries when disk/lag threaten SLOs.
11. If publication must be atomic job-wide, flip a dataset-version publish flag in the final transaction.
12. Run `ANALYZE`, full reconciliation, and retain reports and rollback plans afterward.

### Exercise 48 — Multi-billion-row retention deletion

**Batched DELETE**:

- Works immediately on unpartitioned tables without prior redesign.
- Throttling batches keeps lock durations short.
- However, total `DELETE` volume emits massive WAL, dead tuples, index churn, and replica lag at multi-billion-row scale.
- Requires ongoing vacuuming and does not immediately shrink OS files.

**Partition lifecycle**:

- Ideal when rows align cleanly with a retention key and expired partitions can drop wholesale.
- Detach/drop avoids row-level DML cost, though DDL locks, dependencies, and audit triggers require care.
- Needs an online migration (dual-write/cutover, validation, capacity plan) from unpartitioned to partitioned tables.

Runbook:

1. Measure table size, WAL bytes/row, indexes/triggers/constraints, and current replica lag.
2. Confirm retention, legal holds, and audit obligations.
3. Short term (while unpartitioned): run small keyset `DELETE` batches throttled by WAL, disk, and latency.
4. Plan partitioning via a dedicated maintenance or online migration.
5. Monitor dead tuples/autovacuum, archiving/slots, and p99 latency.
6. Validate expired data, backups/restores, and cutover/rollback plans.
7. Never drop a partition containing still-active data.
8. Post-migration, automate partition lifecycle with approvals, alerts, and staging rehearsals.

### Exercise 49 — Ambiguous COMMIT and webhooks

Never fire an HTTP webhook blindly "after `COMMIT`" solely based on a client response that can drop. Use a **transactional outbox**:

~~~sql
BEGIN;

-- Business DML.
-- INSERT INTO outbox(event_id unique, payload, status='pending');
-- UPDATE import chunk checkpoint.

COMMIT;
~~~

A separate relay reads only **committed** outbox rows and dispatches webhooks. Receivers deduplicate using `event_id`/idempotency keys; workers retry missed responses and route failures to dead-letter reconciliation. On ambiguous `COMMIT` outcomes, reconnect and inspect outbox + progress instead of emitting fresh webhooks immediately. This binds "DB state + intent to send" atomically, while external delivery still uses at-least-once + idempotency rather than magic exactly-once.

### Exercise 50 — Runbook for 300 MiB/s WAL and cascading failures

Prioritize safety:

1. **Declare an incident** and assess API impact, free disk, replica RPO/RTO, and archive status.
2. **Pause the importer at a commit boundary** or slash worker concurrency immediately; do not keep pushing 300 MiB/s while archiving and replication stall.
3. Capture monitoring snapshots: `pg_stat_wal`, current LSN, `pg_stat_replication`, `pg_replication_slots`, `pg_stat_archiver`, `pg_stat_activity`, and checkpoint/I/O metrics.
4. Separate **WAL generation pressure** from **retention pressure**; both may be happening together.
5. Repair the archive destination, command, network, or throughput; verify `last_archived_wal`/`last_archived_time` advances.
6. Identify the slot owner, why lag reached 100 GiB, and recovery feasibility; **never drop the slot** without a plan.
7. Protect disk headroom without deleting `pg_wal` manually; expand disk temporarily per runbook if needed.
8. Inspect long transactions, lock waits, and customer p99; if cancelling/rolling back the offending batch, account for commit state rather than killing backends recklessly.
9. Let autovacuum reclaim dead tuples between commits and evaluate `ANALYZE`; never run `VACUUM FULL` during peak load just to free disk.
10. Reconcile batch checkpoints, keys, and source checksums after pausing; resolve ambiguous `COMMIT`s idempotently.
11. Resume with a small canary, lower batch sizes/concurrency, and strict WAL MiB/s, replica-lag, and disk guardrails.
12. Ramp up gradually only once archive, slot, and replica backlogs drop and API p99 stabilizes.
13. Run full post-job reconciliation, verify counts/versions, and archive the report.
14. Postmortem: measure write amplification, checkpoints/FPIs, capacity/monitoring gaps, and update migration playbooks.

Never "put out the fire" by turning off `fsync`/`full_page_writes`, downgrading `wal_level`, dropping slots, or deleting WAL files without proven recovery safety.

---

## 47. Quick Decision Matrix

| Problem | Preferred pattern | Key constraints to evaluate |
|---|---|---|
| Import a 50 GiB CSV file | Chunked `COPY` -> staging -> validate -> merge | Transactions/checkpoints, `COPY` errors, WAL |
| Update 20 million rows | Keyset/CTE `UPDATE` in batches | Locks, WAL, dead tuples, concurrent writers |
| Purge expired data | Partition detach/drop when scope is clean | DDL locks, audit semantics, dependencies |
| Export 200 GiB | `COPY TO STDOUT` streaming / `pg_dump` per goal | Snapshot consistency, file storage |
| Job-wide dataset atomicity | Staging + publish dataset version | Reader routing, cutover, constraints |
| Multi-worker jobs | `FOR UPDATE SKIP LOCKED` or partitioned ranges | Inconsistent view, starvation, reconciliation |
| High WAL pressure | Throttle total write rate & fix retention bottleneck | Archive/slots/disk/checkpoints |
| Crash recovery retries | Unique business IDs + atomic checkpoints | Ambiguous `COMMIT`, payload mismatches |
| Emitting external events | Transactional outbox + idempotent relay | At-least-once delivery, consumer dedup |
| Rebuilding large tables | Build new table + validate + cutover if feasible | FKs/triggers/privileges/DDL locks |

---

## 48. PostgreSQL Reference Documentation

When implementing against a specific PostgreSQL major version, cross-check the official documentation for that exact version rather than assuming `/current/` examples match unchanged:

- [PostgreSQL — Populate a Database](https://www.postgresql.org/docs/current/populate.html): bulk-loading strategies, `COPY`, and indexes.
- [PostgreSQL — COPY](https://www.postgresql.org/docs/current/sql-copy.html): `COPY FROM`/`TO`, CSV, `STDIN`, options, and restrictions.
- [PostgreSQL — psql](https://www.postgresql.org/docs/current/app-psql.html): `\copy` and autocommit.
- [PostgreSQL — INSERT](https://www.postgresql.org/docs/current/sql-insert.html): multi-row `INSERT`, `ON CONFLICT`, `RETURNING`.
- [PostgreSQL — UPDATE](https://www.postgresql.org/docs/current/sql-update.html): `UPDATE FROM` and subquery/CTE batching.
- [PostgreSQL — DELETE](https://www.postgresql.org/docs/current/sql-delete.html): `DELETE USING` and subqueries.
- [PostgreSQL — Transactions](https://www.postgresql.org/docs/current/tutorial-transactions.html): `BEGIN`/`COMMIT`/`ROLLBACK`/savepoints.
- [PostgreSQL — PL/pgSQL Transaction Management](https://www.postgresql.org/docs/current/plpgsql-transactions.html): `CALL`/`DO`/procedure transaction control.
- [PostgreSQL — Write-Ahead Log](https://www.postgresql.org/docs/current/wal.html): WAL purpose and crash recovery.
- [PostgreSQL — WAL Configuration](https://www.postgresql.org/docs/current/wal-configuration.html): checkpoints and WAL tuning.
- [PostgreSQL — WAL Runtime Configuration](https://www.postgresql.org/docs/current/runtime-config-wal.html): `wal_level`, `full_page_writes`, `wal_compression`, `max_wal_size`, `synchronous_commit`.
- [PostgreSQL — pg_stat_wal](https://www.postgresql.org/docs/current/monitoring-stats.html): WAL statistics and monitoring views.
- [PostgreSQL — WAL Functions](https://www.postgresql.org/docs/current/functions-admin.html): `pg_current_wal_lsn` and `pg_wal_lsn_diff`.
- [PostgreSQL — Streaming Replication](https://www.postgresql.org/docs/current/warm-standby.html): replication, replay, and WAL streaming.
- [PostgreSQL — Replication Slots](https://www.postgresql.org/docs/current/warm-standby.html#STREAMING-REPLICATION-SLOTS): slot-based WAL retention.
- [PostgreSQL — Continuous Archiving/PITR](https://www.postgresql.org/docs/current/continuous-archiving.html): archiving and recovery chains.
- [PostgreSQL — VACUUM](https://www.postgresql.org/docs/current/sql-vacuum.html): dead tuple cleanup and `ANALYZE`.
- [PostgreSQL — Routine Vacuuming](https://www.postgresql.org/docs/current/routine-vacuuming.html): autovacuum and transaction wraparound.
- [PostgreSQL — Table Partitioning](https://www.postgresql.org/docs/current/ddl-partitioning.html): partition lifecycle management.
- [PostgreSQL — UNLOGGED Table](https://www.postgresql.org/docs/current/sql-createtable.html): durability and replication trade-offs.
- [PostgreSQL — Locking](https://www.postgresql.org/docs/current/explicit-locking.html): row locks, blocking, and deadlocks.
- [PostgreSQL JDBC Driver — Documentation](https://jdbc.postgresql.org/documentation/): JDBC batches, `CopyManager`, and transaction handling.

Settings, catalog columns, SQL options, and replication capabilities change across PostgreSQL and driver versions. Always verify behavior in your target deployment environment.

---

## 49. Summary

**Effective batching means picking a unit of work large enough to amortize overhead yet small enough to protect the database, replication, and crash recovery.** Key principles:

1. **WAL is not a disposable log you can delete for disk space.** It underpins crash recovery, backups/PITR, and replication; never delete `pg_wal` files manually.
2. **COPY does not auto-commit per row.** A `COPY` statement shares transaction scope like any other SQL command. Split streams into separate `COPY`s and commit intentionally to checkpoint chunks.
3. **Batch and transaction are distinct.** A SQL loop inside a function/`DO` block does not `COMMIT` per iteration; standard stored functions cannot freely manage transactions.
4. **Separate batch commits provide atomicity only per batch.** When the whole dataset must appear atomically, load into staging and cut over via metadata versioning.
5. **Commit checkpoints in the same transaction as data** when correctness requires it; use idempotency keys and source checksums to recover safely from ambiguous `COMMIT` outcomes.
6. **Measure WAL via LSNs or `pg_stat_wal`**, remembering both capture cluster-wide WAL mixed with other workloads. Pair them with WAL MiB/s, disk, API latency, and replica lag.
7. **Look beyond row counts.** Indexed `UPDATE`s, triggers, `JSONB`, FPIs, and checkpoints vary WAL bytes/row dramatically.
8. **Checkpoints and full-page writes** cause periodic WAL surges. Never disable `full_page_writes` or `fsync` casually.
9. **`max_wal_size` is not a hard cap.** Slots, archive failures, and replication lag can push retained WAL well past it; diagnose retention before raising disk or limits.
10. **Batched `UPDATE`/`DELETE`** uses CTEs selecting PKs with `ORDER BY`/`LIMIT`; PostgreSQL lacks direct `UPDATE ... LIMIT`.
11. **`SKIP LOCKED`** helps competing workers avoid blocking, yet 0 rows returned does not prove work is finished; always reconcile.
12. **Keyset pagination** avoids deep `OFFSET` scans, but does not by itself create a consistent snapshot across concurrent writes.
13. **`UPDATE`/`DELETE` leave MVCC row versions** requiring autovacuum/`VACUUM`; smart partitioning makes retention purges far cheaper than row-by-row `DELETE`.
14. **Use `UNLOGGED`/`TEMP`** only when their durability/replication trade-offs are acceptable and reloadable from source; never substitute them for logged business tables.
15. **Control WAL bursts by throttling total write rate** and worker count, not merely shrinking rows/batch while multiplying concurrency.
16. **External side effects** need an outbox + idempotency; a lost `COMMIT` response never proves a transaction rolled back.
17. **Operate by runbook:** monitor archiving, slots, replicas, locks, and latency; pause cleanly at boundaries; reconcile checkpoints; and resume with a small canary.

Action blueprint: **analyze source & invariants -> pick staging/publish strategy -> benchmark WAL/bytes/batch -> establish transactions/checkpoints/idempotency -> keyset-batch COPY/INSERT/UPDATE/DELETE -> measure WAL/lag/locks after every batch -> throttle concurrency and pause as needed -> reconcile/publish -> VACUUM/ANALYZE and verify recovery readiness**.

# Choosing an engine by integrity, concurrency, durability, and query needs

The storage engine determines how MySQL stores and accesses each table's data. Choosing an engine therefore directly affects transactions, locking, concurrency control, crash recovery, index types, and workload performance. An appropriate choice must stem from data requirements and how the application queries the data, not solely from an isolated speed benchmark.

In the **DATABASE_MYSQL** module, table design, data types, keys, SQL, indexes, transactions, and operations all connect to the storage engine. For instance, InnoDB provides transactions and foreign keys for relational data; other engines may suit temporary data, compressed archival data, or specialized cluster systems. This lesson establishes an evaluation and selection approach across four groups of criteria: **data integrity, concurrency, durability, and query needs**.

## 1. Starting from workload requirements

Before choosing an engine, describe the data and how the application uses it. The following four questions serve as the starting point.

### 1.1. Data integrity

Does the data require atomic transactions? Does a workflow update multiple rows or multiple tables and need all of them to succeed or fail together? Are foreign keys needed to protect relationships between tables? Does the application need to roll back when a business step fails?

If the answer is yes, the engine must support transactions and the necessary constraints. For typical relational transactional systems, InnoDB is the reasonable default choice.

### 1.2. Concurrency

How many clients read and write simultaneously? Can multiple transactions update the same row, the same group of rows, or overlapping key ranges? Does the system run long read queries while data is being written?

Examine the engine's locking mechanism, isolation levels, MVCC, and conflict-handling capabilities. Row-level locking can reduce contention scope compared to table locking, but it does not mean every operation locks only a single row. Indexes and execution plans can change how many records or index ranges are locked.

### 1.3. Durability and recovery

When the server or operating system fails, to what extent must committed data be protected? Can the system tolerate losing a brief window of data, or must commit confirmation wait until logs are flushed under durable settings? Is point-in-time recovery using backups and binary logs required?

An engine has its own recovery mechanisms, yet ultimate durability still depends on server configuration, operating system, storage hardware, and backup procedures. Selecting InnoDB does not automatically replace configuring durability and testing restores.

### 1.4. Query needs

Does the application mainly perform reads, append-only writes, frequent updates, full-text search, analytics, or store rarely changing data? Do queries require joins, multi-column filtering, sorting, aggregation, or index lookups?

Document critical queries and their execution frequency. The engine and index types must support real access patterns; an engine fast at sequential writes may not fit an application requiring transactions, joins, and concurrent updates.

## 2. InnoDB: the foundational choice for transactional data

InnoDB is MySQL's default storage engine in modern versions. It is built for transactional workloads and provides the capabilities needed by most applications managing relational data.

### 2.1. Integrity and transactions

InnoDB supports ACID transactions, covering:

- **Atomicity:** changes within a transaction are committed as a unit or rolled back via the transaction mechanism.
- **Consistency:** the application and enforced constraints move data from one valid state to another.
- **Isolation:** transactions are coordinated according to isolation levels and concurrency control mechanisms.
- **Durability:** committed changes are protected according to redo log, binlog, OS, and storage device configuration.

InnoDB supports foreign keys, allowing parent-child relationships between tables to be enforced at the database level. For example:

```sql
CREATE TABLE customers (
    customer_id BIGINT NOT NULL,
    full_name VARCHAR(150) NOT NULL,
    PRIMARY KEY (customer_id)
) ENGINE = InnoDB;

CREATE TABLE orders (
    order_id BIGINT NOT NULL,
    customer_id BIGINT NOT NULL,
    total_amount DECIMAL(12, 2) NOT NULL,
    PRIMARY KEY (order_id),
    KEY idx_orders_customer (customer_id),
    CONSTRAINT fk_orders_customer
        FOREIGN KEY (customer_id)
        REFERENCES customers (customer_id)
) ENGINE = InnoDB;
```

With this structure, InnoDB rejects inserting an order referencing a non-existent customer and blocks deleting a customer if dependent relationships remain per the declared constraint action. This helps protect data even across multiple applications or write paths.

Transactions also allow grouping multiple operations into one business unit:

```sql
START TRANSACTION;

UPDATE accounts
SET balance = balance - 500000
WHERE account_id = 101;

UPDATE accounts
SET balance = balance + 500000
WHERE account_id = 202;

COMMIT;
```

A real application must check affected row counts, balances, and business conditions before committing. If any condition fails, the application calls ROLLBACK. This transaction guarantees atomicity only for transactional changes on the participating tables.

### 2.2. Concurrency and MVCC

InnoDB uses MVCC to provide consistent reads for many regular queries. In many situations, a transaction reads a snapshot without blocking another transaction writing the same data. Write operations still require locks to prevent conflicting updates.

InnoDB supports row-level locking alongside index-record locks and range locks such as next-key locks when needed. Lock scope depends on:

- Whether the statement is a plain read, locking read, UPDATE, or DELETE.
- The transaction's isolation level.
- The index used and filter predicates.
- The execution plan and actual data.

For example, the following query requests locks on matching records so the application can process updates within the same transaction:

```sql
START TRANSACTION;

SELECT balance
FROM accounts
WHERE account_id = 101
FOR UPDATE;

-- Application checks business conditions here.
UPDATE accounts
SET balance = balance - 100000
WHERE account_id = 101;

COMMIT;
```

Filtering on the primary key helps InnoDB locate the record efficiently. If a query lacks a suitable index, the engine may have to scan more index records and lock a broader scope than intended. Index design therefore affects not just speed, but also concurrency.

### 2.3. Indexes and storage structure

InnoDB organizes row data in a clustered index. If the table has a primary key, the primary key is the clustered index; if no suitable primary key exists, InnoDB selects a suitable unique NOT NULL index or generates an internal row key.

Secondary indexes store the index key alongside the primary key value to locate rows in the clustered index. Consequently, a wide primary key causes secondary indexes to consume extra space as well. For tables with many indexes, primary key selection can significantly affect storage size and I/O.

InnoDB supports index types and features suited to transactional applications, including B-tree, full-text, and spatial indexes subject to version support. Choose indexes based on real queries and verify with EXPLAIN.

### 2.4. Recovery and durability

InnoDB uses the redo log to recover data page changes after a crash and the undo log for rollbacks and MVCC support. The buffer pool caches data and index pages in memory; dirty pages are written to storage by the engine's flushing mechanisms.

Commit durability is influenced by configuration, especially:

- **innodb_flush_log_at_trx_commit:** controls when the redo log is written and flushed. A value of 1 is commonly used when high durability is required: the redo log is written and flushed at every commit. Values of 0 or 2 reduce flush frequency to the storage device, risking loss of recent transactions during an OS or host crash.
- **sync_binlog:** controls binary log synchronization. When strict per-transaction binlog protection is needed, 1 is typically chosen to synchronize after every commit.

You can view current settings:

```sql
SHOW VARIABLES
WHERE Variable_name IN (
    'innodb_flush_log_at_trx_commit',
    'sync_binlog',
    'innodb_doublewrite'
);
```

Durability values must be chosen according to RPO/RTO targets, write load, and storage hardware capabilities. Even when settings request flushing, actual durability depends on whether the OS, controller, and storage device honor flush commands faithfully. Redo logs and doublewrite do not replace independent backups.

## 3. Other engines and their scope of use

MySQL supports a pluggable storage engine architecture. Engines can differ in feature sets, and not every engine is installed or enabled in every distribution.

| Engine | Key characteristics | Scenarios to consider | Limitations to remember |
|---|---|---|---|
| InnoDB | Transactions, MVCC, foreign keys, crash recovery, transactional indexes | OLTP applications, relational data, most production systems | Requires index, transaction, and durability configuration design |
| MyISAM | No InnoDB-style transactions; table locking; full-text support | Legacy compatibility or specialized workloads not needing transactions | No rollback; table locks can limit write concurrency; limited recoverability |
| MEMORY | Table data resides in RAM; supports HASH and BTREE indexes | Temporary data, small regenerable lookup tables | Data lost on server restart; RAM capacity limits; do not use for durable storage |
| ARCHIVE | Focused on compressed storage, suited for append-and-read data | Historical or append/read archival data when feature set suffices | Restricted updates, indexing, and queries; must check version support |
| NDB Cluster | Distributed engine targeting high availability and data distributed across nodes | Systems actually deploying MySQL NDB Cluster with distribution needs | Requires NDB Cluster infrastructure and operations; differs from InnoDB in features and tuning |

The table above is a selection guide, not an exhaustive list or a guarantee that every engine is available. Check SHOW ENGINES on your actual server and consult documentation for your deployed version.

### 3.1. MyISAM: accounting for transaction and table-lock limits

MyISAM does not support transactions and rollback like InnoDB. It uses table-level locking, so a write operation can block other operations on the same table according to the engine's locking rules.

This makes MyISAM unsuitable for workflows requiring multi-step atomic updates, foreign keys, or high write concurrency. When an application calls ROLLBACK, changes already applied to a MyISAM table are not undone as they are with InnoDB.

A legacy system may still retain MyISAM tables for historical reasons or compatibility. Before migrating to InnoDB, assess schemas, indexes, storage size, conversion duration, and a rollback plan.

### 3.2. MEMORY: regenerable temporary data

MEMORY stores table data in RAM. It can be useful for small, temporary datasets that can be regenerated after server startup. Contents of a MEMORY table do not survive a restart.

Example:

```sql
CREATE TABLE current_job_cache (
    job_id BIGINT NOT NULL,
    worker_name VARCHAR(100) NOT NULL,
    status VARCHAR(20) NOT NULL,
    PRIMARY KEY (job_id),
    KEY idx_job_status USING HASH (status)
) ENGINE = MEMORY;
```

This example only illustrates specifying the engine and index; verify supported index syntax and data types in your running version. Do not store sole business state in MEMORY if the application lacks another durable data source.

### 3.3. ARCHIVE and NDB Cluster: specialized needs

ARCHIVE is designed for compressed storage and append-and-read workloads. It can reduce storage footprint for historical data, but should not be selected before verifying the SQL operations, indexes, and queries the application requires.

NDB Cluster is a cluster architecture with the NDB storage engine, targeting distributed data and high availability. NDB requires dedicated cluster components and operational procedures. A standalone MySQL Server does not become an NDB Cluster merely by specifying ENGINE=NDB.

## 4. Engine selection matrix by requirement

You can use the following matrix for initial screening:

| Requirement | InnoDB | MyISAM | MEMORY | ARCHIVE | NDB Cluster |
|---|---|---|---|---|---|
| Transactions and rollback | Yes | No | No | No | Supports transactions per NDB model |
| Foreign keys | Yes | No | No | No | Do not assume InnoDB equivalence; verify feature support |
| MVCC | Yes | No | No | No | NDB's transaction mechanism has distinct traits |
| Durable data on disk | Yes | Yes | No for table contents | Yes | Storage configurable per cluster model |
| Row-level concurrency | Yes, via InnoDB locking | Table locking | Table locking | Limited per engine capabilities | Dedicated locking and distribution mechanism |
| Specialized compressed storage | Not primary goal | Not primary goal | No | Yes | Not primary goal |
| Distributed data across cluster | No | No | No | No | Yes |

This matrix is for guidance only. Exact capabilities, engine limits, and server integration vary by version. When a requirement is mandatory, check the documentation and test on the exact target distribution.

### 4.1. Example selection scenarios

**E-commerce application:** orders, payments, inventory, and customers are interrelated and require atomic updates. Choose InnoDB for transactions, foreign keys, and appropriate locking.

**Regenerable cache table:** data is loaded from a durable source, small in size, and needs RAM access. MEMORY can be considered if losing data on restart is acceptable and size is controlled.

**Legacy system using MyISAM:** first identify why the table still uses MyISAM, whether it relies on full-text or legacy behaviors, and which maintenance window permits conversion. For new transactional data, prefer InnoDB.

**Infrequently updated historical store:** if the pattern is mainly append/read and query needs fit, evaluate ARCHIVE or another storage solution. Benchmark real queries and check reporting needs.

**Distributed cluster system:** choose NDB only when the overall architecture genuinely requires NDB Cluster and the team has the skills to deploy, monitor, back up, and recover the cluster.

## 5. Query needs and indexing must accompany engine choice

An engine cannot compensate for a poorly designed schema or indexes. When choosing an engine, list critical queries:

- Lookups by primary key or unique key.
- Filtering on one or more columns.
- Joining related tables.
- Range scans by time or ordering.
- Aggregations and reporting.
- Full-text or spatial searches if required by the application.
- Concurrent writes to the same data.

With InnoDB, choose a stable and reasonably compact primary key, then create secondary indexes matching access patterns. For example:

```sql
CREATE INDEX idx_orders_status_created
    ON orders (status, created_at);

EXPLAIN
SELECT order_id, customer_id, total_amount
FROM orders
WHERE status = 'PAID'
  AND created_at >= '2026-01-01'
ORDER BY created_at;
```

Column order in a composite index matters. An index starting with status can support filtering by status and a range on created_at, though actual effectiveness depends on selectivity, data distribution, sort order, and the optimizer. Inspect EXPLAIN and measure on production-like data.

An engine may provide different index methods or restrict index types. Do not assume every engine offers identical behavior just because CREATE INDEX syntax looks similar.

## 6. Durability configuration is part of the engine decision

Durability is a system requirement, not just a checkbox in an engine name. With InnoDB, define maximum acceptable data loss after a failure and balance it against write performance.

### 6.1. Understanding the impact of key variables

- **innodb_flush_log_at_trx_commit = 1:** InnoDB writes and flushes the redo log on every commit. This is typically the appropriate setting when prioritizing transaction durability.
- **innodb_flush_log_at_trx_commit = 2:** the redo log is written to the OS on every commit but flushed to the storage device periodically. During an OS or host crash, recent unflushed transactions can be lost.
- **innodb_flush_log_at_trx_commit = 0:** writing and flushing the redo log happen periodically; risk of losing recent transactions is higher.
- **sync_binlog = 1:** synchronizes the binlog per commit, commonly chosen when durable binlogs are needed for replication and point-in-time recovery.

The periodic interval is typically around one second, though not a strict real-time guarantee. Specific configuration must follow requirements and version documentation.

### 6.2. Durability does not replace backups

The redo log recovers InnoDB state after a crash; the binary log records change events for replicas and point-in-time recovery. A backup is a restorable copy for data loss, hardware failure, or administrative mistakes.

A sound operational process requires:

1. Defining RPO (maximum acceptable data loss) and RTO (target recovery time).
2. Selecting redo/binlog settings aligned with RPO and performance needs.
3. Taking scheduled backups and protecting copies from faults affecting the server location.
4. Retaining and managing binary logs matching the required point-in-time recovery window.
5. Regularly testing restores in an isolated environment and measuring recovery time.
6. Verifying data consistency and application functionality after restore.

Never treat a successful backup job as proof that recovery works. Perform restore tests and document the results.

## 7. Mixing multiple storage engines in one transaction

MySQL allows a database to contain tables using different engines, but that does not mean operations across those tables share the same transaction semantics.

Example:

```sql
CREATE TABLE payment_records (
    payment_id BIGINT PRIMARY KEY,
    amount DECIMAL(12, 2) NOT NULL
) ENGINE = InnoDB;

CREATE TABLE legacy_audit (
    audit_id BIGINT PRIMARY KEY,
    message VARCHAR(255) NOT NULL
) ENGINE = MyISAM;
```

If a transaction updates the InnoDB table and then writes to the MyISAM table, the InnoDB operation can roll back while the applied MyISAM change is not undone. Thus, a transaction that appears to span two tables does not guarantee atomicity across both.

Practical rules:

- Keep tables belonging to the same business unit in a compatible transactional engine, usually InnoDB.
- Do not rely on ROLLBACK to reverse changes on non-transactional tables.
- If legacy integration is unavoidable, design compensating mechanisms or appropriate event logging.
- Check each table's engine before concluding anything about business atomicity.

## 8. Pre-deployment engine evaluation workflow

Follow these steps for each critical workload:

1. **Describe business logic and data.** Identify relationships, constraints, transaction boundaries, and consistency requirements.
2. **Describe concurrency.** Estimate client counts, read/write ratios, hot spots, and long-running transactions.
3. **Set durability targets.** Define RPO/RTO, commit guarantees, backups, and recovery expectations.
4. **List critical queries.** Gather real queries, frequencies, inputs, and expected outputs.
5. **Verify engine capabilities.** Confirm transactions, foreign keys, index methods, data types, and limits on the target version.
6. **Design schema and indexes.** Choose primary keys, secondary indexes, and constraints to match the workload.
7. **Run controlled benchmarks.** Use production-like dataset sizes and concurrency; measure latency, throughput, I/O, memory, lock waits, and disk usage.
8. **Test failures and recovery.** Test restarts, relevant crash scenarios, backup/restore, and replication if present.
9. **Document the decision.** Record the selected engine, rationale, accepted limits, and operational monitoring plan.

Do not pick an engine based on a trivial benchmark with a handful of rows. Larger datasets, different distributions, different indexes, and high concurrency can reverse results.

## 9. Checking engines on MySQL Server

Before creating tables or evaluating an environment, verify whether the engine is supported.

### 9.1. Viewing server-supported engines

```sql
SHOW ENGINES;
```

Check the default engine:

```sql
SELECT @@default_storage_engine;
```

Or query engine properties:

```sql
SELECT
    ENGINE,
    SUPPORT,
    TRANSACTIONS,
    XA,
    SAVEPOINTS
FROM INFORMATION_SCHEMA.ENGINES
ORDER BY ENGINE;
```

Support status and properties are reported by the active server. If an engine is unavailable or disabled, a table creation statement specifying that engine may fail or behave according to related server settings. Inspect actual messages rather than making assumptions.

### 9.2. Specifying an engine when creating a table

```sql
CREATE TABLE event_log (
    event_id BIGINT NOT NULL AUTO_INCREMENT,
    event_type VARCHAR(50) NOT NULL,
    created_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
    PRIMARY KEY (event_id),
    KEY idx_event_created (created_at)
) ENGINE = InnoDB;
```

Explicitly declare ENGINE in DDL for important tables so the choice is visible in schemas and reviews. If ENGINE is omitted, MySQL uses the server's current default_storage_engine value.

### 9.3. Checking the actual engine of tables

```sql
SELECT
    TABLE_SCHEMA,
    TABLE_NAME,
    ENGINE
FROM INFORMATION_SCHEMA.TABLES
WHERE TABLE_SCHEMA = DATABASE()
ORDER BY TABLE_NAME;
```

Inspect a specific table with SHOW CREATE TABLE:

```sql
SHOW CREATE TABLE event_log;
```

Metadata helps catch tables accidentally created with the wrong engine across environments or tables whose engine changed during migrations.

### 9.4. Converting engines

You can convert an engine with ALTER TABLE:

```sql
ALTER TABLE event_log ENGINE = InnoDB;
```

Conversion can rebuild the table and indexes, consuming I/O, temporary space, and time. Locking impact and online capability depend on version, change type, source/target engines, and table size. Before converting in production, you must:

- Verify features and constraints are compatible with the target engine.
- Estimate required space and conversion duration.
- Evaluate locks, write-blocking duration, and replication lag.
- Create a restorable backup and test in staging first.
- Prepare a maintenance window along with a rollback plan.

Do not treat ALTER TABLE engine conversion as instantaneous or always lock-free.

## 10. Common mistakes

| Mistake | Consequence | Mitigation |
|---|---|---|
| Choosing an engine solely from a fast benchmark | Real workload may be slow or lack required features | Measure real queries, transactions, and concurrency |
| Using a non-transactional engine for multi-step workflows | Cannot fully roll back on error | Use InnoDB for tables participating in transactions |
| Assuming every engine has foreign keys and MVCC | Constraints or isolation do not work as expected | Verify feature support per engine |
| Assuming InnoDB guarantees zero data loss in all failures | Flush settings, binlog, and hardware affect durability | Set RPO/RTO, verify settings, and test restores |
| Using MEMORY as the sole data source | Data lost after restart | Use only for regenerable temporary data |
| Ignoring the actual engine of individual tables | A transaction may mix tables with different semantics | Check INFORMATION_SCHEMA.TABLES |
| Changing engine directly in production without assessment | Locks, long conversion times, or disk exhaustion | Test in staging, back up, and plan migration |

## 11. Takeaways

- Choose an engine based on workload requirements for integrity, concurrency, durability, and queries.
- InnoDB is the appropriate default for most transactional applications because it provides transactions, MVCC, foreign keys, suitable locking, and crash recovery.
- MyISAM lacks InnoDB-style transactions and uses table locking; MEMORY keeps table contents in RAM and loses data on restart.
- ARCHIVE and NDB Cluster serve specialized needs; check feature sets, versions, and infrastructure before adopting them.
- InnoDB durability also depends on redo/binlog configuration, operating system, storage hardware, and backup/restore.
- Indexes and execution plans affect both performance and lock scope, so evaluate queries alongside the engine.
- Mixing engines within a transaction can break atomicity on non-transactional tables.
- Verify engines using SHOW ENGINES, @@default_storage_engine, and INFORMATION_SCHEMA.TABLES; specify ENGINE explicitly in important DDL.

With systematic evaluation, you can select an engine that satisfies current business needs, anticipate its limits, and build appropriate testing, deployment, backup, and recovery plans for MySQL.

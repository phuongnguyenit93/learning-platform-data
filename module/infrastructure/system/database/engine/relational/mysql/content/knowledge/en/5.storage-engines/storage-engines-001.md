# What is a storage engine and why does it affect SQL behavior

MySQL can store and manage data using multiple storage engines. A storage engine is the component responsible for performing table-level storage operations such as reading, writing, index management, locking, and data recovery. The MySQL server provides a common SQL layer for applications to submit statements, while the storage engine determines many important characteristics of how those statements are executed.

Therefore, two tables with the same structure queried with identical SQL can still differ in rollback capability, foreign keys, concurrency levels, data locking behavior, crash recovery, and performance. In MySQL Community Server 8.4, InnoDB is the default storage engine and is the suitable choice for most relational applications that require transactions, integrity constraints, and recoverability.

This lesson belongs to the `DATABASE_MYSQL` module, which covers table design, data types, keys, SQL querying, indexes, transactions, concurrency control, reading execution plans, query optimization, privilege management, and relational database operations. Understanding storage engines helps you predict SQL behavior, choose the right storage characteristics, and avoid assuming that every table in MySQL shares the same capabilities.

After this lesson, you will be able to:

- Explain what a storage engine does in the MySQL architecture.
- Check available engines and the engine of individual tables.
- Compare InnoDB with MyISAM, MEMORY, CSV, and NDB at a high level.
- Explain how an engine affects transactions, locking, foreign keys, indexes, and recovery.
- Specify an engine when creating a table and convert the engine of an existing table.
- Select an appropriate engine based on data requirements and workload.

## 1. Storage engines in the MySQL architecture

When an application sends an SQL statement, the MySQL server accepts the connection, parses the syntax, checks privileges, optimizes the query, and coordinates execution. When it needs to read or write data from a table, the server interacts with the storage engine bound to that table through the storage engine interface layer.

```text
Application / MySQL client
          |
          v
  MySQL Server layer
  - Connections and authentication
  - Parser and SQL execution
  - Optimizer and privilege checks
          |
          v
   Storage engine interface
          |
    +-----+------+-------+
    |            |       |
    v            v       v
  InnoDB       MyISAM  MEMORY ...
    |            |       |
    v            v       v
  Data,        Data,   RAM-backed
  indexes,     indexes, table data
  logs         files
```

A storage engine is typically bound per table, rather than being a single choice strictly enforced across the entire server. One database can contain multiple tables using different engines. For example, business tables can use InnoDB while a temporary table serving a special task uses MEMORY.

The server still provides a common SQL syntax, but an engine may or may not support certain features. The engine also determines how data is stored, how indexes are organized, how locks are acquired, how transactions are handled, and how recovery works when the process or server encounters a failure.

Do not assume that a storage engine replaces the parser or optimizer. MySQL's optimizer chooses how to execute a query based on information such as indexes, statistics, and capabilities exposed by the engine; the engine performs the concrete read/write operations according to its storage model.

## 2. Checking storage engines on the server

### 2.1. Listing supported engines

Log in to MySQL and run:

```sql
SHOW ENGINES;
```

The output includes these key columns:

| Column | Meaning |
| --- | --- |
| `Engine` | Name of the storage engine |
| `Support` | Support status on the current server |
| `Comment` | Brief description |
| `Transactions` | Whether the engine supports transactions |
| `XA` | Whether the engine supports XA transactions |
| `Savepoints` | Whether the engine supports savepoints |

Common `Support` values include `DEFAULT` (default engine), `YES` (supported), `NO` (unsupported), and `DISABLED` (present in the build but currently disabled). The actual list depends on the version, build, and server configuration. Do not assume all engines exist in every installation.

You can filter this information using `INFORMATION_SCHEMA.ENGINES`:

```sql
SELECT
    ENGINE,
    SUPPORT,
    TRANSACTIONS,
    XA,
    SAVEPOINTS,
    COMMENT
FROM INFORMATION_SCHEMA.ENGINES
ORDER BY ENGINE;
```

### 2.2. Checking the default engine

```sql
SHOW VARIABLES LIKE 'default_storage_engine';
```

In MySQL 8.4, the default value is typically `InnoDB`. If a `CREATE TABLE` statement does not specify `ENGINE`, MySQL uses the default engine at the time the table is created.

Changing the default engine only affects tables created afterward that do not explicitly specify an engine. It does not automatically convert existing tables.

### 2.3. Checking a table's engine

In the current database:

```sql
SELECT
    TABLE_SCHEMA,
    TABLE_NAME,
    ENGINE,
    TABLE_ROWS
FROM INFORMATION_SCHEMA.TABLES
WHERE TABLE_SCHEMA = DATABASE()
  AND TABLE_TYPE = 'BASE TABLE'
ORDER BY TABLE_NAME;
```

Or inspect a specific table:

```sql
SHOW TABLE STATUS LIKE 'orders'\G
SHOW CREATE TABLE orders\G
```

`SHOW CREATE TABLE` is especially useful because it shows the table definition and the `ENGINE` option stored by MySQL.

Note: `TABLE_ROWS` in `INFORMATION_SCHEMA.TABLES` and `SHOW TABLE STATUS` may only be an estimate for InnoDB. If you need an exact row count, use `SELECT COUNT(*)` and consider the scanning cost on large tables.

## 3. Common storage engines

The engines below illustrate differences in storage characteristics. Actual support status must be verified with `SHOW ENGINES` on the target server.

| Engine | Transactions | Locking and integrity | Storage and common use cases |
| --- | --- | --- | --- |
| InnoDB | Yes, supports ACID and rollback | Record/index-level locking, MVCC, foreign keys supported | Default engine for most transactional/business tables |
| MyISAM | No | Table-level locking, does not enforce foreign keys | Legacy systems or specific read workloads; unsuitable for data requiring transactions |
| MEMORY | No | Table-level locking; supports hash and B-tree indexes | Table data resides in RAM, suitable for temporary data that can be recreated |
| CSV | No | No standard indexes, no foreign keys supported | Simple CSV data exchange in certain straightforward cases |
| NDB | Has NDB Cluster transaction mechanism | Distributed and replicated per NDB Cluster architecture | MySQL NDB Cluster systems; not a drop-in replacement for InnoDB in standard single-node setups |

### 3.1. InnoDB

InnoDB is the default choice for transactional applications. Key characteristics:

- **Transactions and ACID:** supports `START TRANSACTION`, `COMMIT`, `ROLLBACK`, and savepoints. Committed changes are protected by InnoDB's durability mechanisms.
- **MVCC:** multiple transactions can read consistent versions of data without blocking all write operations. This mechanism improves concurrency.
- **Record/index-level locking:** InnoDB can lock only the necessary records or index ranges. Depending on the isolation level and query type, the engine also uses record locks, gap locks, or next-key locks.
- **Foreign keys:** supports declaring and enforcing referential constraints between InnoDB tables.
- **Recovery:** uses redo logs, undo logs, and internal mechanisms to recover after an abnormal server shutdown.
- **Indexes:** uses a clustered index; table data is organized by the primary key. InnoDB secondary indexes store the primary key value to locate the record.

Example of creating business tables:

```sql
CREATE TABLE customers (
    customer_id BIGINT UNSIGNED NOT NULL AUTO_INCREMENT,
    full_name VARCHAR(150) NOT NULL,
    email VARCHAR(255) NOT NULL,
    created_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
    PRIMARY KEY (customer_id),
    UNIQUE KEY uk_customers_email (email)
) ENGINE = InnoDB;

CREATE TABLE orders (
    order_id BIGINT UNSIGNED NOT NULL AUTO_INCREMENT,
    customer_id BIGINT UNSIGNED NOT NULL,
    total_amount DECIMAL(12, 2) NOT NULL,
    created_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
    PRIMARY KEY (order_id),
    KEY idx_orders_customer_created (customer_id, created_at),
    CONSTRAINT fk_orders_customer
        FOREIGN KEY (customer_id)
        REFERENCES customers (customer_id)
) ENGINE = InnoDB;
```

In this example, `orders` references `customers` via a foreign key. Both tables use InnoDB, so MySQL can validate referential constraints and coordinate changes within a transaction.

### 3.2. MyISAM

MyISAM is an older engine that may still be encountered in legacy systems. It can fit certain specialized read workloads, but it has significant limitations:

- Does not support transactions. `ROLLBACK` does not undo changes made to a MyISAM table.
- Uses table-level locking on writes, so write operations can force other operations on the same table to wait.
- Does not enforce foreign keys.
- Crash recovery lacks the transactional guarantees of InnoDB; tables may require checking or repair after an unexpected shutdown.

Example of creating a MyISAM table to observe differences in a lab:

```sql
CREATE TABLE legacy_counter (
    id BIGINT NOT NULL AUTO_INCREMENT,
    label VARCHAR(80) NOT NULL,
    PRIMARY KEY (id)
) ENGINE = MyISAM;
```

Do not choose MyISAM just because a single benchmark shows it is faster in one scenario. You must consider transactions, locking, recovery, integrity, and the application's concurrent workload. For business tables requiring correctness under concurrent operations, InnoDB is usually the safer choice.

### 3.3. MEMORY

MEMORY stores table rows in RAM. This enables fast access for some tasks, but table data is lost when the server restarts. The table definition may remain, while its contents must be recreated or reloaded.

```sql
CREATE TABLE session_lookup (
    session_key VARCHAR(64) NOT NULL,
    user_id BIGINT UNSIGNED NOT NULL,
    expires_at DATETIME NOT NULL,
    PRIMARY KEY (session_key),
    KEY idx_session_user (user_id)
) ENGINE = MEMORY;
```

MEMORY is suitable for temporary, regenerable data of controlled size. Do not use it as the sole storage location for data that must persist across restarts. You must monitor memory limits and index structures; MEMORY does not support transactions like InnoDB.

### 3.4. CSV

CSV stores data in comma-separated plain-text format. This engine is useful in some simple data exchange workflows, but it lacks indexes, transactions, and constraints like InnoDB.

```sql
CREATE TABLE import_preview (
    code VARCHAR(30),
    description VARCHAR(255),
    quantity INT
) ENGINE = CSV;
```

CSV is not a choice for business tables requiring complex queries or concurrent access. If the goal is simply importing/exporting CSV, tools like `LOAD DATA` and `SELECT ... INTO OUTFILE` may be more appropriate depending on privileges and operational procedures.

### 3.5. NDB Cluster

NDB is the storage engine tied to MySQL NDB Cluster, a shared-nothing distributed database architecture. NDB is designed for server clusters with data nodes and dedicated replication and data distribution mechanisms. It is not like a local engine that can simply be enabled in any standard MySQL Community Server installation.

If a system requires NDB, the entire NDB Cluster must be designed and operated, including topology, management nodes, data nodes, client nodes, and supported deployment characteristics. Do not choose NDB merely by changing `ENGINE=NDB` on a standalone MySQL server.

## 4. How storage engines affect transactions

A transaction groups multiple changes into a single logical unit. With InnoDB, you can commit all changes or roll them back if an error occurs before committing.

```sql
CREATE TABLE account_innodb (
    account_id BIGINT PRIMARY KEY,
    balance DECIMAL(12, 2) NOT NULL
) ENGINE = InnoDB;

INSERT INTO account_innodb (account_id, balance)
VALUES (1, 1000.00), (2, 500.00);

START TRANSACTION;

UPDATE account_innodb
SET balance = balance - 100.00
WHERE account_id = 1;

UPDATE account_innodb
SET balance = balance + 100.00
WHERE account_id = 2;

ROLLBACK;

SELECT * FROM account_innodb ORDER BY account_id;
```

After `ROLLBACK`, the balances return to their pre-transaction values. If `ROLLBACK` is replaced with `COMMIT`, both changes are saved as one InnoDB transactional unit.

Compare with a MyISAM table:

```sql
CREATE TABLE account_myisam (
    account_id BIGINT PRIMARY KEY,
    balance DECIMAL(12, 2) NOT NULL
) ENGINE = MyISAM;

INSERT INTO account_myisam (account_id, balance)
VALUES (1, 1000.00), (2, 500.00);

START TRANSACTION;

UPDATE account_myisam
SET balance = balance - 100.00
WHERE account_id = 1;

ROLLBACK;

SELECT * FROM account_myisam ORDER BY account_id;
```

Changes on a MyISAM table are not undone by `ROLLBACK`. The transaction statements may still be accepted by the server, but the engine cannot roll back the table's data. This difference directly affects business correctness.

Note: DDL statements such as `CREATE TABLE`, `ALTER TABLE`, and `DROP TABLE` follow implicit commit rules in MySQL. Do not use DDL to demonstrate a rollbackable DML transaction. Transaction examples should focus on `INSERT`, `UPDATE`, and `DELETE` on transactional tables.

If a transaction updates multiple tables using different engines, do not assume all changes can be rolled back atomically. Changes on non-transactional tables may persist even if the InnoDB transaction rolls back. For data requiring cross-table integrity, prefer using the same transactional engine such as InnoDB.

## 5. Impact on locking and concurrency control

The storage engine determines how data is protected when multiple sessions read or write concurrently.

### 5.1. InnoDB: record locking and MVCC

InnoDB supports multiple concurrent transactions. Update operations typically lock the relevant records/indexes rather than locking the entire table. Standard read queries can use MVCC-based consistent reads to observe a snapshot appropriate for the isolation level.

Example using a locking read:

```sql
START TRANSACTION;

SELECT balance
FROM account_innodb
WHERE account_id = 1
FOR UPDATE;

UPDATE account_innodb
SET balance = balance - 25.00
WHERE account_id = 1;

COMMIT;
```

`SELECT ... FOR UPDATE` acquires the necessary locks so the transaction can safely update the record before committing. If another session tries to update the same record, it may have to wait until the lock is released. Actual locks depend on indexes, query predicates, and isolation level; range queries may involve gap locks or next-key locks.

To observe this, open two MySQL connections:

| Session A | Session B |
| --- | --- |
| `START TRANSACTION;` | |
| `SELECT balance FROM account_innodb WHERE account_id = 1 FOR UPDATE;` | |
| | `UPDATE account_innodb SET balance = balance - 10 WHERE account_id = 1;` |
| `COMMIT;` | Session B can proceed after the lock is released |

### 5.2. MyISAM: table locking

MyISAM uses table-level locking. When a write operation occurs, other operations on the table may have to wait depending on lock types and queue state. This can reduce write concurrency when multiple clients update the same table simultaneously.

Table locking can be simple and low-overhead for certain workloads, but it does not provide InnoDB's transaction model or row-level locking. Consider the number of writers, query duration, and contention levels before selecting an engine.

## 6. Impact on foreign keys and data integrity

InnoDB supports foreign keys and validates referential constraints on insert, update, or delete. For example, the `orders` table in section 3 cannot insert an order referencing a non-existent `customer_id` while the constraint is enabled.

MyISAM does not enforce foreign keys. Writing a table definition with a `FOREIGN KEY` clause on an unsupported engine does not create the same integrity guarantees as InnoDB; do not rely on syntax appearing in DDL to conclude that a constraint is being enforced.

Inspect definitions and constraints:

```sql
SHOW CREATE TABLE orders\G

SELECT
    CONSTRAINT_NAME,
    TABLE_NAME,
    REFERENCED_TABLE_NAME
FROM INFORMATION_SCHEMA.KEY_COLUMN_USAGE
WHERE TABLE_SCHEMA = DATABASE()
  AND REFERENCED_TABLE_NAME IS NOT NULL;
```

If an application needs parent-child relationship guarantees at the database level, use InnoDB for the related tables and declare foreign keys explicitly. Also verify the data types, sizes, signedness, and indexes of referenced columns for compatible design.

## 7. Impact on indexes and execution plans

The storage engine determines how indexes are organized and accessed. InnoDB uses a clustered index: row data is stored ordered by the primary key. If a table does not declare a suitable primary key, InnoDB selects an appropriate unique index or generates an internal row identifier. InnoDB secondary indexes contain the primary key, so a long primary key can make secondary indexes larger.

Therefore, primary key design impacts storage footprint and query efficiency. A stable, compact primary key aligned with access patterns generally benefits InnoDB tables. This does not mean every table must use the same ID type; choose based on identification requirements and workload.

The optimizer may choose different plans across engines due to how each engine provides indexes, statistics, and data access capabilities. When performance differs, inspect all of the following:

- The actual engine of the table.
- Indexes and column order in composite indexes.
- Table statistics and data distribution.
- Filter conditions, joins, sorts, and estimated rows.
- Lock contention levels and I/O activity.

Example of inspecting an execution plan:

```sql
EXPLAIN
SELECT order_id, total_amount
FROM orders
WHERE customer_id = 10
ORDER BY created_at DESC;
```

Do not conclude that one engine is always faster than another solely from the engine name. Measure on realistic data and workloads, inspect `EXPLAIN`, monitor execution time, rows read, and concurrency levels. An engine with proper transactions and constraints can reduce the cost of fixing data corruption, even if a simple microbenchmark does not reflect that benefit.

## 8. Impact on recovery and data durability

InnoDB uses mechanisms such as redo logs, undo logs, and crash recovery to bring data back to a consistent state after a failure. When the server restarts abnormally, InnoDB can replay necessary logged changes and roll back uncommitted transactions.

MyISAM does not provide transactions or crash recovery at the same level as InnoDB. After an unexpected shutdown, tables may be marked as needing checking or repair. That increases operational risk and effort if critical data is stored in MyISAM.

Actual durability also depends on log configuration, filesystem, storage devices, and how the operating system acknowledges writes. Do not assume that simply choosing InnoDB eliminates the need for backups. Every environment that must retain data still needs tested restorable backups and a proper recovery plan.

## 9. Choosing an engine when creating or converting tables

### 9.1. Specifying an engine when creating a table

Explicitly specify the engine in important DDL so readers and deployment environments clearly understand the requirement:

```sql
CREATE TABLE payment_transactions (
    transaction_id BIGINT UNSIGNED NOT NULL AUTO_INCREMENT,
    reference_code VARCHAR(64) NOT NULL,
    amount DECIMAL(14, 2) NOT NULL,
    created_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
    PRIMARY KEY (transaction_id),
    UNIQUE KEY uk_payment_reference (reference_code)
) ENGINE = InnoDB;
```

To check the default engine before creating a table:

```sql
SHOW VARIABLES LIKE 'default_storage_engine';
```

In the server configuration, the default engine can be specified in the `[mysqld]` section of the option file:

```ini
[mysqld]
default_storage_engine=InnoDB
```

The option file path depends on the operating system and installation method. After modifying static configuration, follow the appropriate restart procedure and verify the variable again. Even though InnoDB is already the default in MySQL 8.4, declaring it explicitly in DDL prevents relying on configuration differences across environments.

### 9.2. Converting the engine of an existing table

You can convert a table using `ALTER TABLE`:

```sql
ALTER TABLE legacy_counter ENGINE = InnoDB;
```

This operation may rebuild the table, recreate indexes, and require additional temporary disk space. For large tables, it can consume heavy I/O, affect response times, or lock the table during part of the process depending on the version and change type. Constraints or options unsupported by the target engine may cause the operation to fail or alter behavior.

Before converting an engine:

1. Check the current engine, table size, indexes, constraints, triggers, and dependent applications.
2. Back up the data and verify it can be restored.
3. Verify compatibility of the target engine with features currently in use.
4. Test the conversion on a replica or staging environment.
5. Schedule a maintenance window if necessary, and monitor disk space, duration, and I/O load.
6. After conversion, verify `SHOW CREATE TABLE`, row counts, indexes, foreign keys, and critical queries.

Do not change an engine in production just to experiment. Define requirements for transactions, locking, integrity, recovery, and workload before planning a migration.

## 10. Choosing a storage engine by requirement

| Requirement | Typically suitable choice | Reason |
| --- | --- | --- |
| Orders, payments, accounts, inventory | InnoDB | Transactions, foreign keys, MVCC, and crash recovery |
| Many concurrent read/write sessions | InnoDB | Record/index-level locking control and MVCC |
| Temporary tables in RAM, regenerable data | MEMORY | RAM data access; must accept data loss on restart |
| Simple CSV data exchange | CSV or import/export tools | Easy-to-exchange file format, but lacks indexes and transactions |
| Read-only legacy systems with specific requirements | Evaluate MyISAM by workload | May maintain compatibility, but must accept transaction and locking limits |
| Distributed MySQL cluster using NDB Cluster | NDB | Dedicated cluster architecture and data distribution mechanism |

For new relational applications, start with InnoDB unless specific technical requirements prove another engine is more suitable. Performance optimization typically starts with schema, indexes, queries, statistics, and server resources before considering changing engines.

## 11. Practice exercises

1. Run `SHOW ENGINES` and record which engines have `DEFAULT`, `YES`, `NO`, or `DISABLED` status on your machine.
2. Create two tables with similar structures, one InnoDB table and one MyISAM table. Inspect the results using `SHOW CREATE TABLE`.
3. Run the transaction example with InnoDB, then run the similar example with MyISAM. Explain why `ROLLBACK` produces different results.
4. Create two InnoDB tables with a parent-child relationship via a foreign key. Try inserting a non-existent foreign key value and record the error.
5. Create a MEMORY table, insert data, verify the data, and then restart the lab environment if possible. Confirm that the table definition and data have different lifecycles.
6. Run `EXPLAIN` for a query on an InnoDB table. Add or adjust a suitable index and compare the execution plans.
7. Convert a test table from MyISAM to InnoDB. Verify the row count, indexes, and engine after conversion.
8. Write a short paragraph explaining the engine choice for an e-commerce orders table, covering requirements for transactions, foreign keys, concurrency, and recovery.

## 12. Completion criteria

You have completed this lesson when you can explain the role of storage engines in the MySQL architecture, identify the engine of a table, describe key differences between InnoDB and common engines, demonstrate an engine's impact on rollback and foreign keys, and select an engine based on business requirements. You should also know how to perform a controlled engine conversion and verify the results afterward.

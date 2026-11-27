# MyISAM, its locking mechanism, and transaction limitations

MySQL can store data using multiple storage engines. The storage engine determines how a table is stored, how data is accessed, the locking mechanism, recoverability, and transaction support. **MyISAM** is a legacy MySQL engine that was once widely used for read-heavy tables with infrequent updates. The most important point to understand when working with MyISAM is that it uses table-level locking and does not support transactions.

This directly impacts how multiple connections read and write concurrently, how applications handle mid-flight errors, and how safe data is when the server encounters a failure. MyISAM may still appear in legacy systems or specific workloads, but for new applications requiring transactions, foreign keys, and strong recoverability, InnoDB is generally the more appropriate choice.

## Learning objectives

After this lesson, you will be able to:

- Explain the role of storage engines and identify MyISAM tables in MySQL.
- Describe how MyISAM uses table locks for reads and writes.
- Analyze how table locking affects concurrent connections and wait times.
- Explain why `COMMIT` and `ROLLBACK` do not provide atomicity for MyISAM data.
- Recognize MyISAM's limitations regarding foreign keys, crash recovery, and multi-table operations.
- Inspect the engine of existing tables and make informed decisions about retaining or migrating MyISAM tables.

## 1. Where do storage engines sit in MySQL?

MySQL Server accepts SQL statements, checks privileges, parses syntax, and optimizes queries. When it needs to read or write a table's data, the server interacts with the storage engine assigned to that table. Consequently, two tables in the same database can use different engines and exhibit different behaviors regarding locking, transactions, or storage.

Some common engines:

| Engine | Key characteristics | Common use cases |
|---|---|---|
| InnoDB | Transactions, row-level locking combined with index locks, foreign keys, crash recovery | Most transactional applications and new systems |
| MyISAM | No transactions, table-level locking, indexes stored separately from data | Legacy systems, read-heavy tables, or specific evaluated workloads |
| MEMORY | Table data stored in memory; data is lost when the server restarts | Temporary data or short-lived lookups where data loss is acceptable |
| CSV | Stores data as CSV text with limited SQL access capabilities | Data exchange or specialized integration scenarios |

Do not choose an engine solely by name or assume one engine is always faster. You must evaluate workload, consistency, concurrency, storage size, backups, and recoverability. This lesson focuses on MyISAM and the consequences of its table-locking design.

## 2. How MyISAM stores and serves data

MyISAM stores row data and indexes in separate structures. On traditional filesystems, you typically see a `.MYD` data file and a `.MYI` index file corresponding to the table. Table metadata is managed by MySQL; file-level details depend on version and deployment.

MyISAM supports primary keys, unique keys, and several index types such as B-tree; the engine also supports FULLTEXT and SPATIAL indexes in applicable cases. However, having indexes does not mean the engine supports row locking or transactions. Indexes help locate rows faster, whereas table locking governs how concurrent connections are allowed to read and write.

Check the engines of tables in the current database:

```sql
SELECT
    TABLE_NAME,
    ENGINE,
    TABLE_ROWS,
    DATA_LENGTH,
    INDEX_LENGTH
FROM information_schema.tables
WHERE TABLE_SCHEMA = DATABASE()
ORDER BY TABLE_NAME;
```

`TABLE_ROWS` depends on the storage engine: with MyISAM, the row count is typically stored and reported accurately; with InnoDB, it is usually an estimate. If you need a consistent check across multiple engines or need to verify actual data, use `SELECT COUNT(*)` while considering query cost.

Inspect an individual table:

```sql
SHOW TABLE STATUS LIKE 'myisam_inventory';
SHOW CREATE TABLE myisam_inventory;
```

In the output, the `Engine` field indicates the storage engine in use. `SHOW CREATE TABLE` shows the engine along with the column, index, and constraint definitions stored by MySQL.

## 3. Creating a MyISAM table for observation

Practice in a sandbox database. The following example creates a simple inventory table:

```sql
CREATE TABLE myisam_inventory (
    product_id BIGINT UNSIGNED NOT NULL AUTO_INCREMENT,
    sku VARCHAR(40) NOT NULL,
    product_name VARCHAR(120) NOT NULL,
    quantity INT UNSIGNED NOT NULL DEFAULT 0,
    updated_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP
        ON UPDATE CURRENT_TIMESTAMP,
    PRIMARY KEY (product_id),
    UNIQUE KEY uq_myisam_inventory_sku (sku),
    KEY idx_myisam_inventory_quantity (quantity)
) ENGINE = MyISAM
  DEFAULT CHARACTER SET = utf8mb4
  COLLATE = utf8mb4_unicode_ci;

INSERT INTO myisam_inventory (sku, product_name, quantity)
VALUES
    ('KB-001', 'Keyboard', 20),
    ('MS-001', 'Mouse', 35),
    ('MN-001', 'Monitor', 8);

SHOW CREATE TABLE myisam_inventory;
SELECT * FROM myisam_inventory ORDER BY product_id;
```

The `ENGINE = MyISAM` clause instructs MySQL to create the table using this engine. If the engine is unavailable or disabled in the distribution being used, table creation will fail. Check supported engines rather than assuming every server has the same configuration.

MyISAM can store indexes and enforce certain constraints at the server layer, such as `PRIMARY KEY` and `UNIQUE`. However, the engine provides no mechanism to enforce foreign keys like InnoDB does. Do not design applications assuming MyISAM will enforce referential relationships between tables.

## 4. MyISAM's table-locking mechanism

MyISAM uses table-level locking: the unit of locking is the entire table. When a statement needs to read or write a table, MySQL acquires the appropriate lock to coordinate access across connections.

| Lock type | Connection holding the lock | Other connections |
|---|---|---|
| Read lock | Can read the table | Can also read concurrently; write requests must wait |
| Write lock | Can read and write the table | Read or write requests must wait until the lock is released |

A standard `SELECT` query acquires a read lock for the duration needed. Data-modifying statements such as `INSERT`, `UPDATE`, and `DELETE` require a write lock. In MyISAM, the write lock applies to the whole table, even if an `UPDATE` modifies only a single row. This is a key difference from InnoDB, where row and index locks allow multiple independent operations on different rows to run concurrently in many scenarios.

### 4.1. Multiple reads can run concurrently

When connections only read a MyISAM table, they can share read locks simultaneously. For example, multiple users opening a product catalog page can read the same table without waiting in line just because another read query is running.

### 4.2. Writes can block the entire table

When a connection holds a write lock, other connections cannot read from or write to the table until the lock is released. If an `UPDATE` takes a long time, catalog read requests may also have to wait, even if they only need rows unrelated to the row being updated.

Illustrative example:

```sql
UPDATE myisam_inventory
SET quantity = quantity - 1
WHERE sku = 'KB-001';
```

The `WHERE` clause identifies which row to modify, but it does not shrink MyISAM's lock scope to a single row. The engine still uses a table-level write lock.

### 4.3. Concurrent inserts are conditional

MyISAM can allow certain inserts at the end of the data file to run concurrently with read queries, depending on table state and configuration. This capability is commonly called concurrent insert. If the table has free blocks from deleted rows or the operation does not meet the conditions, inserts may have to wait for read locks to be released.

Do not treat concurrent inserts as row-level locking or assume every `INSERT` always runs in parallel with `SELECT`. When designing for concurrent write loads, test with realistic data patterns and operation sequences.

## 5. Observing explicit locks with two sessions

MySQL provides `LOCK TABLES` and `UNLOCK TABLES` so a session can explicitly lock tables. The following examples require two separate connections, called **Session A** and **Session B**. Use the `myisam_inventory` sandbox table created earlier.

### 5.1. Read lock

In Session A:

```sql
LOCK TABLES myisam_inventory READ;

SELECT *
FROM myisam_inventory
ORDER BY product_id;
```

While Session A holds the read lock, try the following statements in Session B:

```sql
SELECT *
FROM myisam_inventory;

UPDATE myisam_inventory
SET quantity = quantity + 1
WHERE sku = 'KB-001';
```

The read query in Session B can execute; the write statement must wait until Session A releases the read lock. Switch back to Session A and run:

```sql
UNLOCK TABLES;
```

After the lock is released, the waiting `UPDATE` in Session B can proceed. Confirm with a new `SELECT` query.

### 5.2. Write lock

In Session A:

```sql
LOCK TABLES myisam_inventory WRITE;

UPDATE myisam_inventory
SET quantity = quantity + 5
WHERE sku = 'MS-001';
```

In Session B, try reading or writing:

```sql
SELECT * FROM myisam_inventory;

UPDATE myisam_inventory
SET quantity = quantity - 1
WHERE sku = 'MS-001';
```

The statements in Session B must wait for the write lock to be released. Session A can read and write the locked table. After testing, release the lock in Session A:

```sql
UNLOCK TABLES;
```

**Practice note:** do not leave a session holding a lock and forget to release it. If Session A keeps holding a lock, other connections may hang waiting and make the service appear slow. In labs, proactively release locks immediately after observing them; to stop an experiment, closing the connection holding the lock also terminates the lock state tied to that session.

`LOCK TABLES` is a table-access coordination mechanism, not a transaction. Do not use it to replace `COMMIT`/`ROLLBACK`, and check the implicit commit rules for locking statements in your MySQL version before combining them with transactions on other engines.

## 6. MyISAM does not support transactions

A transaction groups multiple data operations into one logical unit. With a transactional engine like InnoDB, an application can confirm changes with `COMMIT` or discard uncommitted changes with `ROLLBACK`. MyISAM has no such transaction capability.

Write operations on a MyISAM table execute non-transactionally. When a statement succeeds, its changes are applied directly; if a subsequent statement fails, MySQL cannot use `ROLLBACK` to undo the MyISAM changes already made.

### 6.1. Testing rollback on MyISAM

In the sandbox database, run:

```sql
START TRANSACTION;

UPDATE myisam_inventory
SET quantity = quantity + 10
WHERE sku = 'KB-001';

SELECT sku, quantity
FROM myisam_inventory
WHERE sku = 'KB-001';

ROLLBACK;

SELECT sku, quantity
FROM myisam_inventory
WHERE sku = 'KB-001';
```

The `quantity` value after `ROLLBACK` still retains the added 10. `START TRANSACTION` does not turn a MyISAM table into a transactional table. Record the initial quantity if you want to restore it manually after the exercise.

### 6.2. Why is this dangerous for multi-step business workflows?

Suppose a payment operation needs to:

1. Create an order record.
2. Deduct inventory quantity.
3. Record the payment.
4. Update the order status.

If all tables use InnoDB, the application can group the related changes into a single transaction and roll back if one step fails, provided all operations belong to the same transaction and have no external side effects.

If the tables use MyISAM, the first and second operations may already be persisted when the third step fails. The application must implement its own compensating or data-repair logic, yet compensating logic can also fail and must be designed and audited separately. You cannot rely on `ROLLBACK` to restore the entire workflow to its initial state.

## 7. Do not mix MyISAM and InnoDB in one business transaction

MySQL allows a database to contain multiple engines, and even a single statement or transaction can touch multiple tables with different engines. However, atomicity is guaranteed only for data belonging to the transactional engine and within the scope of that transaction. Changes to a MyISAM table are not rolled back alongside InnoDB.

Illustrative example in the sandbox:

```sql
CREATE TABLE transaction_demo_innodb (
    id INT NOT NULL PRIMARY KEY,
    amount INT NOT NULL
) ENGINE = InnoDB;

CREATE TABLE transaction_demo_myisam (
    id INT NOT NULL PRIMARY KEY,
    amount INT NOT NULL
) ENGINE = MyISAM;

INSERT INTO transaction_demo_innodb VALUES (1, 100);
INSERT INTO transaction_demo_myisam VALUES (1, 100);

START TRANSACTION;

UPDATE transaction_demo_innodb
SET amount = amount + 50
WHERE id = 1;

UPDATE transaction_demo_myisam
SET amount = amount + 50
WHERE id = 1;

ROLLBACK;

SELECT * FROM transaction_demo_innodb;
SELECT * FROM transaction_demo_myisam;
```

After `ROLLBACK`, the InnoDB table returns to `amount = 100`; the MyISAM table still has `amount = 150`. This example demonstrates that a transaction involving a MyISAM table does not provide atomicity across all tables.

When designing business logic that requires consistent multi-table changes, use the same suitable transactional engine, usually InnoDB, for all participating tables. If a legacy system forces non-transactional integration, you must design separate compensation workflows, idempotency, reconciliation, and error logging.

## 8. Foreign key and data integrity limitations

MyISAM does not enforce foreign key constraints. A MyISAM table can store a column named `customer_id`, but the engine does not guarantee that the value exists in the customers table. An application can inadvertently write invalid references if it relies solely on the engine for enforcement.

For example, suppose there is a MyISAM orders table:

```sql
CREATE TABLE myisam_order_reference (
    order_id BIGINT UNSIGNED NOT NULL PRIMARY KEY,
    customer_id BIGINT UNSIGNED NOT NULL,
    order_total DECIMAL(12,2) NOT NULL,
    KEY idx_myisam_order_customer (customer_id)
) ENGINE = MyISAM;
```

The index on `customer_id` only assists queries. It does not verify that the customer exists. To ensure referential integrity, you need application-layer validation and synchronization/reconciliation processes, or you must migrate the table to an engine that supports foreign keys such as InnoDB.

Even if the application checks for the customer before inserting, concurrent requests can still create a race condition between the check and the write. Foreign key constraints in a transactional engine are a stronger database-layer safeguard for data relationships.

## 9. Recoverability and maintenance

Because MyISAM lacks transaction logs and crash-safe recovery mechanisms like InnoDB, a server or OS crash can leave tables marked as corrupted or leave indexes out of sync with data. MyISAM provides tools to check and repair tables, but repair is no substitute for backups and does not guarantee recovery of all recent changes.

Some check/maintenance commands:

```sql
CHECK TABLE myisam_inventory;

-- Only run after assessing table condition and ensuring an appropriate backup
REPAIR TABLE myisam_inventory;

ANALYZE TABLE myisam_inventory;
```

- `CHECK TABLE` inspects the table and reports any detected issues.
- `REPAIR TABLE` attempts to fix a corrupted MyISAM table. This is a maintenance operation that can take a long time and carries risk; back up critical data before running it.
- `ANALYZE TABLE` updates index statistics so the query optimizer has better information.

With MyISAM, you need an appropriate backup schedule, backup verification procedures, and a rehearsed recovery plan. When copying data files at the filesystem level, ensure tables are in a consistent state and follow MySQL backup procedures; never arbitrarily copy files that are actively being written to.

## 10. Comparing MyISAM and InnoDB

| Criterion | MyISAM | InnoDB |
|---|---|---|
| Transactions | Not supported | Supports `COMMIT` and `ROLLBACK` |
| Lock granularity | Table locking | Primarily row and index locking; metadata/table locks still occur in certain situations |
| Concurrent reads | Multiple readers can read concurrently | Strong concurrent read support, including consistent reads |
| Concurrent writes | Writes can block access to the entire table | Multiple transactions can modify different rows concurrently |
| Foreign keys | Not enforced | Supported |
| Crash recovery | May require checking/repairing tables | Crash recovery mechanism based on redo/undo logs |
| Best suited for | Legacy tables, read-heavy, infrequent updates, and no transaction need | Transactional applications, relational data, and new systems |

InnoDB can still experience lock contention, deadlocks, or metadata lock waits. Row-level locking does not mean every operation is always independent. However, InnoDB's transactional model and finer-grained locking are generally much better suited for applications with concurrent writes.

## 11. When to keep or convert MyISAM?

Do not convert an engine simply upon seeing `ENGINE=MyISAM`. First determine what function the table serves, how much write traffic it receives, whether transactions or foreign keys are needed, and whether applications depend on its current behavior.

MyISAM may be kept temporarily when:

- The table belongs to a legacy system operating stably with proper backup and verification procedures.
- The data is nearly read-only with rare updates, and the team has measured table lock impact.
- A MyISAM-specific feature is in use and a clear replacement plan exists.

Prioritize planning a migration to InnoDB when:

- The application needs `COMMIT`/`ROLLBACK` across related changes.
- Multiple connections write concurrently and table locks cause significant wait times.
- Foreign keys are needed to protect data relationships.
- Higher crash recovery, availability, and data reliability are required.
- The table participates in payments, inventory, orders, or flows requiring atomicity.

Before converting, check disk space, data types, indexes, constraints, queries, dependent applications, table lock duration, and deployment windows. Example conversion syntax:

```sql
ALTER TABLE myisam_inventory ENGINE = InnoDB;
```

This statement may rebuild the table, generate significant I/O load, and hold locks for a period depending on data size, version, and deployment setup. Test on a production-like replica, back up first, measure duration, verify the application after conversion, and prepare a suitable rollback plan. Do not run this command on a production table just to experiment.

## 12. Checklist for operating MyISAM tables

- Confirmed the table actually uses MyISAM via `SHOW TABLE STATUS` or `information_schema.tables`.
- Understood that every write operation can lock the entire table and make other queries wait.
- Measured lock hold times and wait times under realistic load.
- Verified the application does not rely on `ROLLBACK` to undo MyISAM data.
- Checked referential relationships via application logic or reconciliation processes since MyISAM does not enforce foreign keys.
- Put backups, restore verification, and a table check/repair runbook in place.
- Evaluated the impact of mixing MyISAM and InnoDB within a single business workflow.
- Documented a specific technical reason for keeping MyISAM or established a tested migration plan.

MyISAM clearly illustrates how a storage engine directly affects data concurrency and integrity. Table locking causes writes to block the whole table; lack of transaction support prevents changes from being rolled back; and the absence of foreign key enforcement along with limited recovery requires additional operational controls. Understanding these limitations helps you spot risks in legacy systems and choose the right engine for each MySQL workload.

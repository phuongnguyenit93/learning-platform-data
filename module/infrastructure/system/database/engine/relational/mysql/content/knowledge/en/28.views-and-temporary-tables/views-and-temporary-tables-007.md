# CREATE TEMPORARY TABLE and Connection-Scoped Visibility

MySQL allows creating temporary tables using `CREATE TEMPORARY TABLE`. This table exists within the scope of a single session (one MySQL connection); only the session that created it can see and use it. When the connection closes, MySQL automatically drops the temporary table. Therefore, two connections can create temporary tables with the same name without seeing each other's data.

Temporary tables are useful when you need to store intermediate results across multiple SQL statements, break a large processing step into stages, prepare a key set for joining, or hold report results during a working session. However, a temporary table's lifecycle is tied to the physical connection, not necessarily to an application request. This is especially important when an application uses a connection pool: connections can be reused after a request finishes, leaving temporary tables and stale data behind.

This lesson belongs to the `DATABASE_MYSQL` module, focusing on table design, data types, keys, SQL queries, indexes, transactions, concurrency control, reading execution plans, query optimization, and relational database operations. The goal is to create, use, and clean up temporary tables according to their proper lifecycle; understand connection-scoped visibility; and avoid confusing user-created temporary tables with internal temporary tables created by the optimizer during query execution.

After this lesson, you will be able to:

- Create and drop temporary tables using `CREATE TEMPORARY TABLE` and `DROP TEMPORARY TABLE`.
- Explain why temporary tables are visible only to the connection that created them.
- Distinguish session scope from database scope and transaction scope.
- Understand how a temporary table shadows a regular table with the same name in the current session.
- Use `LIKE`, `AS SELECT`, or explicit schema declarations to create temporary tables.
- Choose a storage engine suitable for the data and transaction requirements.
- Understand the `CREATE TEMPORARY TABLES` privilege and important limitations.
- Safely manage temporary tables when applications use connection pools.
- Inspect lifecycle and visibility using `CONNECTION_ID()`.

## 1. What Is a Temporary Table?

A temporary table is a table created with the `TEMPORARY` keyword:

```sql
CREATE TEMPORARY TABLE tmp_customer_ids (
    customer_id BIGINT UNSIGNED NOT NULL PRIMARY KEY
) ENGINE = InnoDB;
```

Core differences compared to a regular table:

| Attribute | Regular Table | User-Created Temporary Table |
| --- | --- | --- |
| Visibility scope | Sessions with appropriate privileges | Only the creating session |
| Lifecycle | Exists until explicitly DROPped | Automatically DROPped when session ends, or manually DROPped |
| Table name | Must be unique in the schema | Can share the name of a regular table; can share temp table names across other sessions |
| Data across connections | Shareable according to privileges | Not shared across connections |
| Common purpose | Store persistent business data | Store intermediate data within a processing session |

`TEMPORARY` does not mean data must reside entirely in RAM. The chosen storage engine determines how data is stored and its transaction characteristics. In the example above using InnoDB, data can be managed on InnoDB storage and supports transactions according to the engine.

## 2. Visibility Scope Is Connection, Not Database

A MySQL session corresponds to a connection to the server. A temporary table is created in the current session and only that session can access it.

Check the connection ID:

```sql
SELECT CONNECTION_ID();
```

Create and load data in Session A:

```sql
CREATE TEMPORARY TABLE tmp_work_items (
    item_id BIGINT UNSIGNED NOT NULL PRIMARY KEY,
    item_status VARCHAR(20) NOT NULL
) ENGINE = InnoDB;

INSERT INTO tmp_work_items (item_id, item_status)
VALUES (101, 'READY'), (102, 'READY');

SELECT * FROM tmp_work_items ORDER BY item_id;
```

Within Session A itself, subsequent SELECT, INSERT, UPDATE, DELETE, and JOIN statements can use `tmp_work_items` like a normal table.

Open another connection, Session B, and run:

```sql
SELECT CONNECTION_ID();
SELECT * FROM tmp_work_items;
```

If there is no regular table with the same name, Session B receives a table-not-found error. Data in Session A's temporary table is not shared with Session B. If Session B has a regular table named `tmp_work_items`, the query in Session B references that regular table, not Session A's temporary table.

### 2.1. Two Sessions Can Use the Same Name

Session A:

```sql
CREATE TEMPORARY TABLE tmp_stage (
    id INT PRIMARY KEY,
    note VARCHAR(40) NOT NULL
);

INSERT INTO tmp_stage VALUES (1, 'session A');
```

Session B:

```sql
CREATE TEMPORARY TABLE tmp_stage (
    id INT PRIMARY KEY,
    note VARCHAR(40) NOT NULL
);

INSERT INTO tmp_stage VALUES (1, 'session B');
```

Both sessions can create `tmp_stage`. When Session A runs SELECT, it sees only `session A`; Session B sees only `session B`. A temporary table name is not a schema-wide shared name.

### 2.2. Do Not Confuse Session with Transaction

A temporary table does not automatically disappear on `COMMIT` or `ROLLBACK`. Its lifetime scope is the connection. A transaction only controls the atomicity of data changes according to the storage engine; it is not a mechanism for ending a temporary table's lifecycle.

```sql
CREATE TEMPORARY TABLE tmp_numbers (
    n INT PRIMARY KEY
) ENGINE = InnoDB;

START TRANSACTION;
INSERT INTO tmp_numbers VALUES (10), (20);
COMMIT;

SELECT * FROM tmp_numbers;
```

After COMMIT, the table still exists in the session and its rows can still be queried. To end its lifecycle before closing the connection, use `DROP TEMPORARY TABLE`.

## 3. Temporary Tables Shadow Regular Tables with the Same Name

MySQL allows a session to create a temporary table with the same name as a regular table in the same schema. In that session, the name resolves to the temporary table; the regular table is shadowed until the temporary table is dropped.

Create a regular table in the lab schema:

```sql
CREATE TABLE customer_work (
    customer_id BIGINT UNSIGNED NOT NULL PRIMARY KEY,
    customer_name VARCHAR(100) NOT NULL
) ENGINE = InnoDB;

INSERT INTO customer_work VALUES (1, 'Permanent customer');
```

In Session A:

```sql
CREATE TEMPORARY TABLE customer_work (
    customer_id BIGINT UNSIGNED NOT NULL PRIMARY KEY,
    customer_name VARCHAR(100) NOT NULL
) ENGINE = InnoDB;

INSERT INTO customer_work VALUES (1, 'Temporary customer');

SELECT * FROM customer_work;
```

The result in Session A is `Temporary customer`. Session B still queries the regular table and sees `Permanent customer`:

```sql
SELECT * FROM customer_work;
```

When Session A runs:

```sql
DROP TEMPORARY TABLE customer_work;
```

the name `customer_work` in Session A resolves back to the regular table. Note: the regular table is not dropped by `DROP TEMPORARY TABLE`.

Name shadowing is useful for certain workflows, but it can also cause confusion during debugging. Use a consistent prefix such as `tmp_`, `work_`, or a purpose-based name to reduce the risk of accidentally operating on a temporary table shadowing a regular table.

## 4. Creating Temporary Tables in Different Ways

### 4.1. Explicit Schema Declaration

This is appropriate when you need control over data types, NULLs, keys, and indexes:

```sql
CREATE TEMPORARY TABLE tmp_order_summary (
    customer_id BIGINT UNSIGNED NOT NULL,
    order_count BIGINT UNSIGNED NOT NULL,
    total_amount DECIMAL(14, 2) NOT NULL,
    PRIMARY KEY (customer_id),
    KEY idx_tmp_order_summary_total (total_amount)
) ENGINE = InnoDB;
```

Then load data with INSERT ... SELECT:

```sql
INSERT INTO tmp_order_summary
    (customer_id, order_count, total_amount)
SELECT
    customer_id,
    COUNT(*) AS order_count,
    SUM(total_amount) AS total_amount
FROM orders
WHERE order_status = 'PAID'
GROUP BY customer_id;
```

The advantage is an explicitly defined schema, the ability to add needed indexes before or after loading data, and straightforward compatibility verification with downstream queries.

### 4.2. Creating from Another Table's Structure Using LIKE

`CREATE TEMPORARY TABLE ... LIKE ...` creates an empty temporary table matching the structure of a source table:

```sql
CREATE TEMPORARY TABLE tmp_orders LIKE orders;
```

This is useful when you need the same column and index definitions to run a separate processing step. The created table does not automatically copy rows from the source table. If data is needed, load it separately with INSERT ... SELECT.

```sql
INSERT INTO tmp_orders
SELECT *
FROM orders
WHERE order_date >= '2026-11-01'
  AND order_date < '2026-12-01';
```

`LIKE` should not be understood as a full copy of every relationship of the source table. Inspect `SHOW CREATE TABLE` on the temporary table to confirm the exact columns, indexes, and attributes created; foreign key constraints are not copied as active relationships on temporary tables.

### 4.3. Creating and Loading Data Using AS SELECT

You can create a temporary table from a query result:

```sql
CREATE TEMPORARY TABLE tmp_recent_orders
ENGINE = InnoDB
AS
SELECT
    order_id,
    customer_id,
    order_date,
    total_amount
FROM orders
WHERE order_date >= '2026-11-01'
  AND order_date < '2026-12-01';
```

MySQL infers columns from the select list and populates the result into the new table. This is concise when you need an intermediate data snapshot. However, do not assume indexes, primary keys, unique constraints, or all attributes of the source table are copied. If subsequent queries need indexes, create them explicitly:

```sql
ALTER TABLE tmp_recent_orders
ADD PRIMARY KEY (order_id),
ADD KEY idx_tmp_recent_customer (customer_id);
```

For large datasets, consider declaring the schema explicitly first, then using INSERT ... SELECT to control data types, lengths, and indexes from the start.

## 5. Using Temporary Tables for Multi-Step Workflows

A common scenario is computing a set of customers meeting revenue criteria and then reusing that set across multiple queries.

Assume the regular table `orders` has columns `order_id`, `customer_id`, `order_status`, `order_date`, and `total_amount`.

Create a temporary table holding qualified customers:

```sql
DROP TEMPORARY TABLE IF EXISTS tmp_qualified_customers;

CREATE TEMPORARY TABLE tmp_qualified_customers (
    customer_id BIGINT UNSIGNED NOT NULL PRIMARY KEY,
    paid_total DECIMAL(14, 2) NOT NULL,
    paid_order_count BIGINT UNSIGNED NOT NULL
) ENGINE = InnoDB;

INSERT INTO tmp_qualified_customers
    (customer_id, paid_total, paid_order_count)
SELECT
    customer_id,
    SUM(total_amount),
    COUNT(*)
FROM orders
WHERE order_status = 'PAID'
  AND order_date >= '2026-11-01'
  AND order_date < '2026-12-01'
GROUP BY customer_id
HAVING SUM(total_amount) >= 1000;
```

Then use the intermediate set across multiple queries:

```sql
SELECT customer_id, paid_total
FROM tmp_qualified_customers
ORDER BY paid_total DESC;

SELECT COUNT(*) AS qualified_customer_count
FROM tmp_qualified_customers;

SELECT o.order_id, o.customer_id, o.total_amount
FROM orders AS o
JOIN tmp_qualified_customers AS q
    ON q.customer_id = o.customer_id
WHERE o.order_status = 'PAID';
```

The benefit is that the aggregation step is saved in the session and can be reused. However, temporary tables also consume space and read/write time. If the result is only used once, a CTE or derived table may be simpler; measure the workload instead of assuming temporary tables are always faster.

## 6. Storage Engine and Transactions

User-created temporary tables can specify a storage engine. Choose an engine based on data requirements:

| Engine | Characteristics to Consider |
| --- | --- |
| InnoDB | Supports transactions, DML rollback, row-level locking, and suits intermediate sets needing consistency |
| MEMORY | Stores data in RAM, typically suited for small sets; data is lost on server restart and bounded by memory settings; lacks full InnoDB transaction semantics |

InnoDB example:

```sql
CREATE TEMPORARY TABLE tmp_balance_check (
    account_id BIGINT UNSIGNED NOT NULL PRIMARY KEY,
    calculated_balance DECIMAL(18, 2) NOT NULL
) ENGINE = InnoDB;
```

### 6.1. Temporary Table DDL and Implicit Commit

In MySQL, `CREATE TEMPORARY TABLE` and `DROP TEMPORARY TABLE` do not trigger an implicit commit like CREATE/DROP on regular tables. Nevertheless, creating or dropping a temporary table definition is not rolled back like an ordinary DML change.

Example:

```sql
START TRANSACTION;

CREATE TEMPORARY TABLE tmp_txn_demo (
    id INT PRIMARY KEY
) ENGINE = InnoDB;

INSERT INTO tmp_txn_demo VALUES (1);
ROLLBACK;

SHOW CREATE TABLE tmp_txn_demo;
SELECT * FROM tmp_txn_demo;
```

After ROLLBACK, the temporary table definition still exists in the session because `CREATE TEMPORARY TABLE` is not rolled back. With InnoDB, the row INSERTed inside the rolled-back transaction is gone. This example illustrates two different lifecycles: the temporary table definition is bound to the session, whereas InnoDB data changes are subject to the transaction.

Do not rely on `ROLLBACK` to remove a temporary table that was created. Use `DROP TEMPORARY TABLE` when cleanup is needed.

### 6.2. DML on Temporary Tables Still Depends on Engine

With InnoDB temporary tables, INSERT/UPDATE/DELETE participate in the current transaction. With non-transactional engines, you cannot expect rollback to undo data changes. Explicitly specify `ENGINE` when transaction semantics matter instead of relying on the server's default engine.

## 7. Privileges to Create Temporary Tables

To create a temporary table in a schema, an account needs the `CREATE TEMPORARY TABLES` privilege on that schema. Illustrative example:

```sql
GRANT CREATE TEMPORARY TABLES
ON reporting_db.*
TO 'report_user'@'localhost';
```

Once a temporary table is created successfully, MySQL does not perform additional normal privilege checks on that temporary table itself for the rest of the session. Therefore, the privilege to create temporary tables should be granted intentionally to application and reporting accounts.

This privilege does not turn temporary tables into shared data. Another session still cannot see the temporary table. At the same time, when a temporary table shadows a regular table of the same name, the session that created the temporary table operates on the temporary table until DROP or session end.

Check current privileges:

```sql
SHOW GRANTS FOR CURRENT_USER();
```

Do not grant broader privileges than needed merely to avoid temporary table creation errors. In environments where multiple applications share an account, clearly define which applications are permitted to create temporary tables and enforce proper cleanup rules.

## 8. Lifecycle and Cleanup

A temporary table ends its lifecycle in one of two ways:

1. The session explicitly drops the table using `DROP TEMPORARY TABLE`.
2. The connection closes; MySQL automatically drops temporary tables belonging to that session.

Explicit drop command:

```sql
DROP TEMPORARY TABLE IF EXISTS tmp_qualified_customers;
```

You can drop multiple temporary tables:

```sql
DROP TEMPORARY TABLE IF EXISTS
    tmp_qualified_customers,
    tmp_recent_orders,
    tmp_order_summary;
```

`IF EXISTS` makes cleanup safe when a branch did not create the table or the table was already dropped. Do not use a plain `DROP TABLE` in cleanup scripts when the exact target is a temporary table; `DROP TEMPORARY TABLE` states intent clearly and protects any regular table of the same name.

### 8.1. CREATE TEMPORARY TABLE IF NOT EXISTS

This syntax avoids an error if the temporary table already exists:

```sql
CREATE TEMPORARY TABLE IF NOT EXISTS tmp_stage (
    id BIGINT UNSIGNED NOT NULL PRIMARY KEY
) ENGINE = InnoDB;
```

If a temporary table with the same name already exists in the session, MySQL does not replace its structure or clear old data from that table. Thus, `IF NOT EXISTS` is not a way to reset state. When a clean schema is required, explicitly DROP then CREATE:

```sql
DROP TEMPORARY TABLE IF EXISTS tmp_stage;

CREATE TEMPORARY TABLE tmp_stage (
    id BIGINT UNSIGNED NOT NULL PRIMARY KEY
) ENGINE = InnoDB;
```

### 8.2. Inspecting Temporary Tables in Use

In the current session, standard commands can be used:

```sql
SHOW CREATE TABLE tmp_stage;
DESCRIBE tmp_stage;
SELECT COUNT(*) FROM tmp_stage;
```

`SHOW CREATE TABLE` and `DESCRIBE` help verify the actual schema. Do not rely on a query from another session to inspect a temporary table, as other sessions have no visibility into that object.

## 9. Connection Pools: A Common Lifecycle Bug in Applications

In backend applications, a connection pool keeps several physical connections open and lends them sequentially to multiple requests. When a request returns a connection to the pool, the MySQL connection often stays open. Because temporary tables are tied to the physical connection, temporary tables persist across request boundaries if the application fails to DROP them.

A failure scenario:

1. Request A borrows connection 42.
2. Request A creates `tmp_report_rows`, loads data, and returns the connection to the pool forgetting to DROP it.
3. Request B later borrows connection 42.
4. Request B runs `CREATE TEMPORARY TABLE tmp_report_rows ...` and hits a table-already-exists error, or `IF NOT EXISTS` causes stale data/schema to be reused.

Another request borrowing connection 57 does not see connection 42's table, so the bug may manifest intermittently depending on which connection the pool hands out.

### 9.1. Safe Implementation Rules

- Give temporary tables a clear prefix and scope them to a single workflow.
- Use `DROP TEMPORARY TABLE IF EXISTS` before initialization when a clean state is needed.
- Always clean up in a `finally` block or equivalent mechanism, even if an intermediate SQL statement fails.
- Do not return the connection to the pool before cleanup completes.
- Do not assume ending a transaction or HTTP request automatically removes temporary tables.
- If a connection breaks or errors out, let the pool discard the broken connection; when the server closes the session, temporary tables are cleaned up automatically.
- Avoid storing sensitive data in temporary tables longer than necessary.

Illustrative pseudocode:

```text
connection = pool.borrow()
try:
    DROP TEMPORARY TABLE IF EXISTS tmp_request_rows
    CREATE TEMPORARY TABLE tmp_request_rows (...)
    INSERT INTO tmp_request_rows ...
    run_queries_using_tmp_request_rows(connection)
finally:
    try:
        DROP TEMPORARY TABLE IF EXISTS tmp_request_rows
        pool.release(connection)
    catch cleanup_error:
        pool.invalidate(connection)
```

The crucial point is that cleanup and release must use the exact same physical connection that created the temporary table. Return the connection to the pool only when cleanup succeeds; if you cannot confirm the temporary table was dropped, invalidate and discard the connection from the pool instead of reusing it. Do not run DROP on another connection and assume the original connection's table was dropped.

## 10. Limitations and Common Errors

### 10.1. Cannot Reopen the Same Temporary Table Multiple Times in One Query

MySQL has a limitation when referencing the same temporary table more than once within the same query. The following example can raise the `Can't reopen table` error:

```sql
SELECT a.id, b.id
FROM tmp_stage AS a
JOIN tmp_stage AS b
    ON b.id = a.id + 1;
```

This is a limitation on reopening the same temporary table under multiple aliases in one query block. If you need to self-join temporary data, consider creating a second temporary copy with a different name, or rewriting the logic with an appropriate query structure.

```sql
CREATE TEMPORARY TABLE tmp_stage_copy LIKE tmp_stage;
INSERT INTO tmp_stage_copy SELECT * FROM tmp_stage;

SELECT a.id, b.id
FROM tmp_stage AS a
JOIN tmp_stage_copy AS b
    ON b.id = a.id + 1;
```

### 10.2. Temporary Tables Do Not Support Foreign Keys

Do not design a temporary table as a relational table with foreign key constraints referencing regular tables. Temporary tables do not support foreign key constraints; integrity checks must be enforced via queries, application logic, or appropriate regular tables.

### 10.3. Stale Data Caused by Connection Reuse

If you do not DROP a temporary table or clear old data before reloading, subsequent requests can read data left over from an earlier request. Use explicit cleanup and design data loading operations to be safely repeatable.

### 10.4. Confusing User Temporary Tables with Internal Temporary Tables

MySQL can create internal temporary tables while executing queries involving GROUP BY, DISTINCT, UNION, or derived table processing. These are internal objects managed by the server; applications do not create them and do not need to DROP them via SQL.

`CREATE TEMPORARY TABLE` in this lesson refers to temporary tables explicitly created and managed per session by the user. The two concepts are distinct despite sharing the word "temporary".

### 10.5. Choosing an Inappropriate Engine or Data Type

A large temporary table with many VARCHAR/TEXT/BLOB columns can consume substantial space. MEMORY has its own limits and storage characteristics; InnoDB is more suitable if transactions are needed or datasets can grow large. Choose data types, indexes, and engines according to actual workloads.

## 11. Observing Session Scope with Two SQL Windows

Perform the following lab using two independent connections.

**Session A**

```sql
SELECT CONNECTION_ID() AS session_a_id;

CREATE TEMPORARY TABLE tmp_visibility (
    marker VARCHAR(30) NOT NULL
) ENGINE = InnoDB;

INSERT INTO tmp_visibility VALUES ('created in A');
SELECT * FROM tmp_visibility;
```

**Session B**

```sql
SELECT CONNECTION_ID() AS session_b_id;
SELECT * FROM tmp_visibility;
```

If no regular table named `tmp_visibility` exists, the SELECT in Session B reports table not found. Return to Session A and run:

```sql
DROP TEMPORARY TABLE tmp_visibility;
```

Then close Session A. The temporary table was explicitly dropped; if DROP is skipped, MySQL still cleans it up automatically when Session A actually terminates.

## 12. Recommended Workflow for Using Temporary Tables

1. Identify the intermediate dataset and how long it needs to be kept.
2. Choose a temporary table name with a distinct prefix to avoid colliding with business tables.
3. Choose an appropriate engine, data types, keys, and indexes.
4. Create the table on the connection that will execute the entire workflow.
5. Load data and verify row counts/representative values.
6. Use the temporary table in JOIN, UPDATE, or reporting statements on that same connection.
7. Verify results before writing final data into regular tables.
8. DROP the temporary table during cleanup before returning the connection to the pool.
9. If the connection terminates abnormally, confirm the pool discards that connection; the server cleans up temporary tables when the session ends.

Do not use temporary tables to replace persistent storage mechanisms. Data that must be shared across sessions, survive restarts, or be managed as business data belongs in regular tables with appropriate privileges and retention policies.

## 13. Common Mistakes

| Error | Cause | How to Handle |
| --- | --- | --- |
| Session B cannot see Session A's temporary table | Temporary tables belong to the creating session | Run all operations on the same connection |
| Subsequent request reports table already exists | Connection pool reuses a session still holding the temporary table | DROP before creating and clean up before releasing |
| Another request reads stale data | Temporary table still holds data from a previous connection lease | Clear/reload data per workflow and clean up in finally |
| Regular table of the same name is shadowed | Session temporary table has higher name-resolution priority | Use a distinct prefix; DROP TEMPORARY TABLE after use |
| ROLLBACK leaves temporary table intact | Temporary table definitions do not roll back like DML | Explicitly run DROP TEMPORARY TABLE |
| `CREATE TEMPORARY TABLE IF NOT EXISTS` keeps old schema | Statement does not replace an existing table | DROP first then CREATE when a clean schema is required |
| `Can't reopen table` | Same temporary table referenced multiple times in one query | Use a temporary copy with a different name or rewrite the query |
| Cannot create temporary table | Missing CREATE TEMPORARY TABLES privilege | Request the right privilege on the needed schema |
| Expecting foreign keys to work | Temporary tables do not support foreign key constraints | Enforce integrity by other means |
| Temporary table too large or out of memory | Inappropriate engine/data type choice | Evaluate InnoDB, data size, and indexes |

## 14. Hands-on Exercises

1. Open two connections. Create the same name `tmp_visibility` in both and demonstrate that each session sees only its own data.
2. Create a regular table `customer_work`, then create a temporary table with the same name in Session A. Compare SELECT results in Session A and Session B.
3. DROP the temporary table and confirm Session A sees the regular table again.
4. Use `CREATE TEMPORARY TABLE ... LIKE ...`; inspect the schema with `SHOW CREATE TABLE` and confirm the new table is empty.
5. Use `CREATE TEMPORARY TABLE ... AS SELECT`; inspect columns/indexes and add necessary indexes manually.
6. Create an InnoDB temporary table, INSERT inside a transaction, and ROLLBACK. Confirm the table definition remains while the newly INSERTed row is gone.
7. Run `CREATE TEMPORARY TABLE IF NOT EXISTS` twice with different definitions. Observe why the command does not replace the existing schema.
8. Create two temporary tables with different names and perform a self-join between them; compare against referencing one temp table under two aliases.
9. Use `SHOW GRANTS FOR CURRENT_USER()` to check privileges and try creating a temporary table in a granted schema.
10. Simulate a connection pool: create a temporary table, keep the connection open, end the transaction, and re-run the workflow. Check whether the table still exists and write proper cleanup.
11. Write a multi-step reporting workflow where a temporary table is created, populated, joined, verified, and DROPped before the connection is returned to the pool.

## 15. Checklist Before Using Temporary Tables in Applications

- [ ] The temporary table only needs to be used within a single connection.
- [ ] All SQL statements in the workflow use the exact physical connection that created the table.
- [ ] The table name uses a distinct prefix and does not accidentally shadow business tables.
- [ ] The engine suits the data size and transaction requirements.
- [ ] Data types, primary key, and secondary indexes are defined.
- [ ] `CREATE TEMPORARY TABLES` privileges have been verified.
- [ ] Do not assume CREATE/DROP of temporary tables can be rolled back.
- [ ] Aware of the `Can't reopen table` limit and lack of foreign key support.
- [ ] DROP is included in cleanup even when the workflow errors out.
- [ ] Connections are returned to the pool only after cleanup completes.
- [ ] Tested behavior when a subsequent request reuses the same connection.
- [ ] Not using temporary tables for data needing sharing or persistent storage.

## 16. Completion Criteria

You have completed this lesson when you can create and drop temporary tables, demonstrate visibility is restricted to the creating connection, explain name shadowing, distinguish session scope from transaction scope, choose how to create tables from schemas or SELECTs, handle cleanup with connection pools, and recognize limitations such as `Can't reopen table` and lack of foreign key support. You should also know when temporary tables are appropriate for intermediate data and when a regular table or a CTE/derived table query is better.

## References

- [MySQL 8.4 Reference Manual — CREATE TEMPORARY TABLE Statement](https://dev.mysql.com/doc/refman/8.4/en/create-table.html)
- [MySQL 8.4 Reference Manual — TEMPORARY Table Problems](https://dev.mysql.com/doc/refman/8.4/en/temporary-table-problems.html)
- [MySQL 8.4 Reference Manual — DROP TABLE Statement](https://dev.mysql.com/doc/refman/8.4/en/drop-table.html)
- [MySQL 8.4 Reference Manual — Statements That Cause an Implicit Commit](https://dev.mysql.com/doc/refman/8.4/en/implicit-commit.html)
- [MySQL 8.4 Reference Manual — GRANT Statement](https://dev.mysql.com/doc/refman/8.4/en/grant.html)

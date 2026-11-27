# TempTable and distinguishing internal temporary tables from user-created temporary tables

In MySQL, the phrase "temporary table" can refer to two different mechanisms. The server may automatically create an *internal temporary table* while optimizing and executing a query. A developer may also explicitly create a *user-created temporary table* using `CREATE TEMPORARY TABLE`. Both serve temporary data, yet their control, lifecycle, observability, and storage engines differ.

TempTable is the MySQL storage engine used for certain in-memory internal temporary tables. It is a server implementation detail, not an engine name an application chooses to create its own temporary tables. A user-created temporary table is an SQL object scoped to the current session; you can name it, index it, write data to it, query it, and explicitly drop it.

This lesson belongs to the `DATABASE_MYSQL` module, which covers table design, data types, keys, SQL querying, indexes, transactions, concurrency control, reading execution plans, query optimization, privilege management, and relational database operations. Understanding both types of temporary tables helps you read `EXPLAIN`, investigate query costs, and manage intermediate data with the proper lifecycle.

After this lesson, you will be able to:

- Distinguish internal temporary tables from tables created with `CREATE TEMPORARY TABLE`.
- Explain where TempTable is used during query execution.
- Identify common scenarios where the optimizer may materialize data into an internal temporary table.
- Inspect configuration and metrics related to internal temporary tables.
- Create, use, verify session scope for, and drop user-created temporary tables.
- Avoid confusing in-memory temporary tables, on-disk temporary tables, and optimizer internal temporary tables.

## 1. Two concepts sharing a name but serving different roles

| Criterion | Internal temporary table | User-created temporary table |
| --- | --- | --- |
| Who creates it? | MySQL Server/optimizer automatically when needed for query processing | Application or user executing `CREATE TEMPORARY TABLE` |
| Purpose | Materialize intermediate data to execute part of a query plan | Store intermediate data explicitly managed by the application across multiple SQL statements |
| Table name | Internal, not a user-chosen SQL object name | Named by the creator |
| Scope | Managed by the server per execution or materialization | Visible only to the session that created it |
| How it is removed | Lifecycle managed automatically by the server | `DROP TEMPORARY TABLE` or session termination |
| Engine | TempTable for in-memory internal tables; may spill to InnoDB on disk | Uses a supported engine specified in DDL, such as InnoDB or MEMORY |
| Observability | Observed indirectly via `EXPLAIN` and status counters | Directly queryable in the creating session; not listed as a regular table in `SHOW TABLES` |

Key takeaway: **TempTable is the engine serving one kind of internal temporary table; `CREATE TEMPORARY TABLE` is the statement that creates a session-scoped temporary table.** Do not use these two terms interchangeably.

## 2. When is an internal temporary table created?

MySQL may need to hold intermediate results while executing a query. Rather than recomputing or streaming all data directly through every step, the optimizer can materialize part of the result into an internal temporary table and read from it subsequently.

Some situations that may require an internal temporary table:

- Processing certain forms of `UNION`, especially when deduplicating rows as in `UNION DISTINCT`.
- Materializing a derived table or common table expression (CTE) when the optimizer chooses materialization over merging.
- Certain `GROUP BY`, `DISTINCT`, or `ORDER BY` queries that cannot be satisfied directly by a suitable index.
- Certain window function computations or complex queries requiring intermediate result storage.
- Other execution strategies that require storing a result set for use in a later step.

These are cases that *may* use a temporary table, not a rule that every `GROUP BY`, `DISTINCT`, `ORDER BY`, or CTE always causes MySQL to create one. The optimizer can use an index, merge a derived table, reorder processing, or select another strategy depending on query structure, statistics, data, and server version.

Aggregation query example:

```sql
CREATE TABLE sales_demo (
    sale_id BIGINT UNSIGNED NOT NULL AUTO_INCREMENT,
    customer_id BIGINT UNSIGNED NOT NULL,
    amount DECIMAL(12, 2) NOT NULL,
    sold_at DATETIME NOT NULL,
    PRIMARY KEY (sale_id),
    KEY idx_sales_customer (customer_id)
) ENGINE = InnoDB;

INSERT INTO sales_demo (customer_id, amount, sold_at) VALUES
(1, 120.00, '2026-01-05 10:00:00'),
(1, 80.00,  '2026-01-07 11:00:00'),
(2, 250.00, '2026-01-08 09:30:00'),
(3, 60.00,  '2026-01-10 14:15:00'),
(2, 90.00,  '2026-01-11 16:20:00');

EXPLAIN
SELECT customer_id, SUM(amount) AS total_amount
FROM sales_demo
GROUP BY customer_id
ORDER BY total_amount DESC;
```

This query groups data by customer, computes sums, and sorts by the summed total. Depending on the execution plan, MySQL may need an intermediate structure to group or sort results. Check the `Extra` column of `EXPLAIN` for indicators like `Using temporary` or `Using filesort`; do not immediately assume data was written to disk.

## 3. TempTable in MySQL

In MySQL 8.4, the `TempTable` engine is the default choice for in-memory internal temporary tables. Prior to MySQL 8.0.16, the `MEMORY` engine was used by default for this type of internal temporary table. The active configuration can be inspected directly rather than guessed from version numbers.

TempTable is designed for server intermediate data. It supports variable-length row formats and data types such as `VARCHAR`, `VARBINARY`, `TEXT`, and `BLOB` in internal temporary tables. This differs from the traditional MEMORY engine, which has limitations on data types and row layout.

### 3.1. From memory to on-disk storage

Not every internal temporary table remains entirely in RAM throughout query execution. MySQL governs memory usage via configuration limits. When thresholds are exceeded, data can spill into a memory-mapped file region; if that limit is also reached, the internal temporary table can transition to an on-disk form using InnoDB.

```text
Query requires intermediate data
              |
              v
      Internal temporary table
              |
              v
      TempTable in RAM
              |
       exceeds RAM limit
              v
    Memory-mapped file (if allowed)
              |
   exceeds mmap limit / mmap disabled
              v
      Internal InnoDB on disk
```

The diagram depicts the high-level path. Transition details depend on configuration variables, version, and query type. Having an internal temporary table in a query does not automatically mean it causes disk I/O; conversely, a query can consume significant memory or I/O without printing a simple log line saying "temporary table".

### 3.2. How do MEMORY and TempTable differ?

`MEMORY` is a storage engine that can be used to create user tables via `ENGINE=MEMORY`. It stores rows in RAM and has specific constraints, such as not supporting `BLOB` and `TEXT` types like InnoDB; its row layout has fixed-length characteristics. Table contents are lost when the server restarts.

`TempTable` is used for MySQL-managed internal temporary tables. Applications should not treat it as a regular engine to specify in `CREATE TABLE` or `CREATE TEMPORARY TABLE`. When you need a temporary table you manage yourself, choose a supported user-table engine such as InnoDB or MEMORY.

## 4. Configuring internal temporary tables

The variables below control how MySQL creates and stores internal temporary tables. Current names and values should be verified on the specific server.

```sql
SHOW VARIABLES LIKE 'internal_tmp_mem_storage_engine';
SHOW VARIABLES LIKE 'temptable_max_ram';
SHOW VARIABLES LIKE 'temptable_max_mmap';
SHOW VARIABLES LIKE 'tmp_table_size';
SHOW VARIABLES LIKE 'max_heap_table_size';
SHOW VARIABLES LIKE 'tmpdir';
```

| Variable | General role |
| --- | --- |
| `internal_tmp_mem_storage_engine` | Selects the engine for in-memory internal temporary tables; MySQL 8.4 typically defaults to `TempTable`, configurable to `MEMORY` |
| `temptable_max_ram` | Limits the RAM the TempTable engine uses before another storage mechanism is needed |
| `temptable_max_mmap` | Limits the memory-mapped file space TempTable can use before spilling to an on-disk internal temporary table |
| `tmp_table_size` | Limits the size of certain internal in-memory temporary tables; exact semantics depend on engine and version |
| `max_heap_table_size` | Limits the size of MEMORY-engine tables; when MEMORY is chosen for internal temporary tables, evaluate alongside `tmp_table_size` |
| `tmpdir` | Server temporary directory, used for certain temporary files and related operations |

`temptable_max_ram` and `temptable_max_mmap` govern TempTable resource thresholds. Once RAM reaches its limit, TempTable can use a memory-mapped file region if capacity permits. Once that region hits its limit or is disabled, internal temporary table data can spill to InnoDB on disk.

Do not raise all limits to huge values just to eliminate `Using temporary` notices. Raising thresholds can let many concurrent sessions consume excessive RAM or temporary disk space, putting pressure on the server. Before making changes, measure actual load, check concurrent session counts, available memory, temporary directory location, and disk space.

## 5. Observing internal temporary tables

### 5.1. Reading EXPLAIN

Run `EXPLAIN` on the query to analyze:

```sql
EXPLAIN
SELECT customer_id, SUM(amount) AS total_amount
FROM sales_demo
GROUP BY customer_id
ORDER BY total_amount DESC;
```

In traditional format, the `Extra` column can show `Using temporary` when the plan uses an internal temporary table. `Using filesort` indicates MySQL needs a sorting step not resolved directly by index order; this label does not mean every case writes a file to disk.

`Using temporary` alone does not tell you whether the temporary table sits in RAM, a memory-mapped file, or InnoDB on disk. Nor does it prove by itself that a query is slow. Examine estimated rows, access type, indexes, execution time, and data volume processed.

You can use `EXPLAIN FORMAT=JSON` to inspect the plan structure in greater detail:

```sql
EXPLAIN FORMAT=JSON
SELECT customer_id, SUM(amount) AS total_amount
FROM sales_demo
GROUP BY customer_id
ORDER BY total_amount DESC;
```

`EXPLAIN ANALYZE` executes the read query and reports actual timings and row counts per iterator. Only run it when executing the query and its resulting load are acceptable; avoid running very heavy read queries in production without evaluating impact first.

### 5.2. Tracking status counters

MySQL provides counters related to internal temporary tables:

```sql
SHOW SESSION STATUS LIKE 'Created_tmp%';
```

Commonly inspected names:

- `Created_tmp_tables`: number of internal temporary tables created in the measured scope.
- `Created_tmp_disk_tables`: number of on-disk internal temporary tables created in the measured scope.

You can read the counters before and after a query to observe the delta in the current session. If server-wide figures are needed, use `SHOW GLOBAL STATUS`, keeping in mind that global counters reflect activity from many other sessions and queries.

Counters do not capture every way TempTable consumes resources. In particular, TempTable's memory-mapped file area is not necessarily reflected identically to an on-disk internal temporary table in `Created_tmp_disk_tables`. Therefore, do not rely on a single counter to deduce the exact RAM or disk I/O caused by a query.

### 5.3. Optimization directions when seeing Using temporary

When a query requires an internal temporary table, consider:

1. Do indexes support the filter predicates, grouping order, or sort order?
2. Can row counts be reduced before grouping or sorting?
3. Are unnecessary columns being selected, inflating intermediate row width?
4. Can a derived table or CTE be merged instead of materialized, and does merging actually help the query?
5. Do intermediate row counts and row widths far exceed what the output needs?
6. Are many concurrent sessions creating temporary tables simultaneously, pressuring RAM or `tmpdir`?

For example, a composite index can help certain queries that filter and group by `customer_id`, but no single index optimizes every combination of `WHERE`, `GROUP BY`, and `ORDER BY`. Test changes on representative data, re-run `EXPLAIN`, and measure actual runtime before drawing conclusions.

## 6. User-created temporary tables

When an application needs to retain an intermediate dataset across multiple SQL statements within the same session, you can create an explicit temporary table:

```sql
CREATE TEMPORARY TABLE tmp_customer_totals (
    customer_id BIGINT UNSIGNED NOT NULL,
    total_amount DECIMAL(14, 2) NOT NULL,
    PRIMARY KEY (customer_id)
) ENGINE = InnoDB;

INSERT INTO tmp_customer_totals (customer_id, total_amount)
SELECT customer_id, SUM(amount)
FROM sales_demo
GROUP BY customer_id;

SELECT customer_id, total_amount
FROM tmp_customer_totals
ORDER BY total_amount DESC;

DROP TEMPORARY TABLE tmp_customer_totals;
```

Unlike internal temporary tables, you explicitly control the name, schema, creation time, and drop time. You can also reference the table across subsequent SQL statements in the same session.

### 6.1. Session scope and lifecycle

A user temporary table is visible only inside the session that created it. Another connection cannot query that table, even when using the same username and database. When the session ends, MySQL automatically drops all temporary tables belonging to that session.

For example, open two connections:

**Session A:**

```sql
CREATE TEMPORARY TABLE tmp_session_demo (
    id INT PRIMARY KEY,
    note VARCHAR(100)
) ENGINE = InnoDB;

INSERT INTO tmp_session_demo VALUES (1, 'Visible only in session A');
SELECT * FROM tmp_session_demo;
```

**Session B:**

```sql
SELECT * FROM tmp_session_demo;
```

Session B receives a table-not-found error because the table exists only in Session A. When Session A closes, the temporary table is dropped automatically.

### 6.2. Temporary tables can shadow regular tables of the same name

MySQL allows a session to create a temporary table with the same name as a regular table. Within that session, the table name resolves to the temporary table and shadows the regular table of the same name until the temporary table is dropped or the session ends.

This can be useful in certain testing workflows, but it easily causes confusion during debugging. Before creating a temporary table, use an easily recognizable prefix like `tmp_` and avoid colliding with business table names.

### 6.3. Choosing an engine for user temporary tables

You can specify an engine explicitly in DDL:

```sql
CREATE TEMPORARY TABLE tmp_memory_lookup (
    lookup_key VARCHAR(64) NOT NULL,
    lookup_value VARCHAR(255) NOT NULL,
    PRIMARY KEY (lookup_key)
) ENGINE = MEMORY;

CREATE TEMPORARY TABLE tmp_innodb_stage (
    row_id BIGINT NOT NULL,
    payload TEXT,
    PRIMARY KEY (row_id)
) ENGINE = InnoDB;
```

`MEMORY` keeps data in RAM and does not preserve contents across server restarts. With a regular MEMORY table, the table definition can persist while row data is lost; with a user temporary MEMORY table, the object itself is also dropped when the session ends. InnoDB is more suitable when you need types like `TEXT`, larger intermediate datasets, or transactional features. User temporary tables use the engine chosen in their own DDL; do not infer a table's engine solely from the keyword `TEMPORARY`.

### 6.4. Privileges and limitations

To create temporary tables, an account needs the `CREATE TEMPORARY TABLES` privilege on the appropriate database. Check privileges with:

```sql
SHOW GRANTS FOR CURRENT_USER();
```

Key points to remember:

- User temporary tables do not support foreign key constraints like regular InnoDB tables.
- MySQL has a restriction when the same query references a temporary table multiple times; this can trigger a `Can't reopen table` error.
- `CREATE TEMPORARY TABLE` and `DROP TEMPORARY TABLE` do not cause an implicit commit like DDL statements for regular tables, though the creation/drop of the temporary table itself is not rolled back to restore a prior state.
- Temporary tables are bound to a connection, not to an HTTP request or an application transaction.

If an application uses a connection pool, the physical connection may be returned to the pool rather than actually closed. A temporary table can remain when another request borrows that same connection. Proactively run `DROP TEMPORARY TABLE` in a cleanup block or ensure every connection borrow has a clear initialization and cleanup procedure.

## 7. Comparison through a practical scenario

Suppose a report needs total revenue per customer. There are two approaches:

**Approach A: let the optimizer create an intermediate structure automatically.**

```sql
SELECT customer_id, SUM(amount) AS total_amount
FROM sales_demo
GROUP BY customer_id
ORDER BY total_amount DESC;
```

You send only one query. If the plan needs materialization, MySQL automatically creates an internal temporary table, manages its engine, and releases resources upon completion. The application does not know the internal table name and cannot query it directly.

**Approach B: the application explicitly creates a temporary table.**

```sql
CREATE TEMPORARY TABLE tmp_report_totals (
    customer_id BIGINT UNSIGNED NOT NULL,
    total_amount DECIMAL(14, 2) NOT NULL,
    PRIMARY KEY (customer_id)
) ENGINE = InnoDB;

INSERT INTO tmp_report_totals
SELECT customer_id, SUM(amount)
FROM sales_demo
GROUP BY customer_id;

SELECT * FROM tmp_report_totals ORDER BY total_amount DESC;
```

The application can reuse the intermediate result across multiple statements, add indexes, or join with other data, but must manage the table's name and lifecycle. User temporary tables consume resources and do not automatically make queries faster. Measure and choose the approach suited to the processing requirement.

## 8. Common misconceptions

| Misconception | Reality |
| --- | --- |
| Seeing `Using temporary` means MySQL wrote to disk | It only indicates the plan uses an internal temporary table; storage may be RAM, a memory-mapped file, or InnoDB on disk |
| `TempTable` is an engine to declare in `CREATE TEMPORARY TABLE` | TempTable serves internal temporary tables; user-created tables must pick an engine supported for user DDL |
| `CREATE TEMPORARY TABLE` is auto-generated by the optimizer | It is a statement explicitly executed by the application or user |
| User temporary tables are visible from all connections | They are visible only within the session that created them |
| Closing a transaction deletes temporary tables | Table lifecycle is tied to the session; transaction commit/rollback does not drop them |
| `Created_tmp_disk_tables` captures all TempTable data that left RAM | The counter has tracking limits, especially with memory-mapped files; additional metrics and resource monitoring are needed |
| Every `GROUP BY` creates an internal temporary table | The optimizer may use an index or another strategy; always inspect the actual plan |

## 9. Practice exercises

1. Run the aggregation query in section 2 and inspect `EXPLAIN`. Note `Using temporary` and `Using filesort` if they appear.
2. Before and after the query, check `SHOW SESSION STATUS LIKE 'Created_tmp%';`. Compare the delta and explain the counter's limitations.
3. Inspect `internal_tmp_mem_storage_engine`, `temptable_max_ram`, `temptable_max_mmap`, and `tmp_table_size` on the server. Record current values without changing settings unless you have a measurement goal.
4. Create `tmp_customer_totals` using InnoDB, populate it with aggregated results, and query it with another SQL statement.
5. Open two sessions to demonstrate that Session B cannot see a temporary table created in Session A.
6. Create a temporary table with the same name as a regular table in the lab database. Observe which table is referenced in the creating session, then drop the temporary table and check again.
7. Use a connection pool or simulate connection reuse. Test why an undropped temporary table can affect a subsequent request.
8. Write a short note comparing when to let the optimizer use an internal temporary table versus when the application should create a user temporary table.

## 10. Completion criteria

You have completed this lesson when you can explain that TempTable is the engine serving MySQL's internal temporary tables, distinguish it from tables created by `CREATE TEMPORARY TABLE`, read temporary table indicators in `EXPLAIN` and status counters, understand the path from RAM to temporary storage, and create and manage session-scoped temporary tables. You should also know how to clean up temporary tables when using connection pools and avoid falsely concluding that `Using temporary` always means disk writes.

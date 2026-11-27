# Limitations of Views and Storing Report Results in Dedicated Tables

This lesson belongs to the **Views and Temporary Tables** chapter of the **DATABASE_MYSQL** module. The module aims to master MySQL from table design, data types, keys, and SQL queries to indexes, transactions, concurrency control, reading execution plans, query optimization, authorization, backup, and handling relational database operational issues. Views help name a query and provide a unified data interface, yet MySQL does not store view results like an auto-refreshing materialized view. When reports need precomputed data, fast access, sharing across sessions, or point-in-time snapshots, you need to design a dedicated result table and refresh process.

After this lesson, you will be able to identify view limitations in MySQL, distinguish MERGE from TEMPTABLE, understand why views lack their own indexes and cannot reference temporary tables, choose between views and reporting tables, design snapshot/summary tables, perform full or incremental refreshes, safely publish new data, and track report freshness.

## 1. What Is a View and Where Is Data Stored?

A view is a database object storing a SELECT definition. When an application queries a view, MySQL processes that definition to produce a result set from underlying tables or views.

Example:

~~~sql
CREATE TABLE orders (
    order_id BIGINT UNSIGNED NOT NULL PRIMARY KEY,
    customer_id BIGINT UNSIGNED NOT NULL,
    status VARCHAR(20) NOT NULL,
    total_amount DECIMAL(12,2) NOT NULL,
    created_at DATETIME(6) NOT NULL
) ENGINE=InnoDB;

CREATE VIEW v_paid_orders AS
SELECT
    order_id,
    customer_id,
    total_amount,
    created_at
FROM orders
WHERE status = 'PAID';
~~~

The view v_paid_orders stores the SELECT statement and view metadata. It does not store a persistent copy of PAID rows.

When the orders table changes, the next query on the view sees data reflecting the current state and transaction isolation of the underlying tables. No refresh command is needed for a regular view.

You can check:

~~~sql
SELECT *
FROM v_paid_orders
ORDER BY created_at DESC, order_id DESC;
~~~

The query still has to read data from the underlying table. If the table has millions of rows, a view does not automatically turn the query into reading a precomputed result table.

### A View Is Not a Materialized View

Some database management systems have materialized views, which store query results and provide a refresh mechanism. MySQL does not offer an equivalent native materialized view object with CREATE MATERIALIZED VIEW syntax.

In MySQL, distinguish between:

| Mechanism | Stores Results Persistently? | Who Updates It? | Shared Across Multiple Sessions? |
|---|---|---|---|
| Regular view | No | MySQL executes SELECT when called | Yes |
| View using ALGORITHM=TEMPTABLE | Only a temporary table serving the statement | MySQL during statement execution | Not a shared result cache |
| Temporary table | Yes, within session scope | Application or stored program | No, only the session that created the table |
| Reporting/snapshot table | Yes | Job, application, or ETL pipeline | Yes |

ALGORITHM=TEMPTABLE does not turn a view into a materialized view. The temporary table is created to process a single execution; that data is not persistent report storage for subsequent calls.

## 2. Two View Processing Algorithms: MERGE and TEMPTABLE

MySQL supports three ALGORITHM values in CREATE VIEW or ALTER VIEW:

- MERGE
- TEMPTABLE
- UNDEFINED

### MERGE

With MERGE, MySQL incorporates the view definition into the query referencing the view. Columns, conditions, and expressions of the view are brought into the outer query.

Example:

~~~sql
CREATE ALGORITHM = MERGE VIEW v_paid_orders AS
SELECT
    order_id,
    customer_id,
    total_amount,
    created_at
FROM orders
WHERE status = 'PAID';
~~~

Query:

~~~sql
SELECT
    order_id,
    total_amount
FROM v_paid_orders
WHERE customer_id = 42;
~~~

Conceptually, MySQL can process this as:

~~~sql
SELECT
    order_id,
    total_amount
FROM orders
WHERE status = 'PAID'
  AND customer_id = 42;
~~~

Thanks to MERGE, the optimizer has the opportunity to push outer query conditions down to underlying tables, use underlying table indexes, and optimize the overall plan.

MERGE is usually effective when a view is just a naming, filtering, or projection layer over underlying tables.

### TEMPTABLE

With TEMPTABLE, MySQL materializes the view's results into an internal temporary table, then uses that temporary table to complete the statement.

Example:

~~~sql
CREATE ALGORITHM = TEMPTABLE VIEW v_customer_totals AS
SELECT
    customer_id,
    COUNT(*) AS order_count,
    SUM(total_amount) AS total_amount
FROM orders
WHERE status = 'PAID'
GROUP BY customer_id;
~~~

When querying:

~~~sql
SELECT *
FROM v_customer_totals
WHERE total_amount >= 10000;
~~~

MySQL needs to compute the grouped results of the view and then use the temporary result for the outer query. This is a materialization step during statement execution, not data stored persistently after the statement ends.

One reason to choose TEMPTABLE is that MySQL can release locks on underlying tables once the temporary table is built, before continuing to process the rest of the statement. This can sometimes reduce how long locks are held on underlying tables.

### UNDEFINED

UNDEFINED lets MySQL choose the algorithm automatically. When possible, MySQL prefers MERGE because it is usually more efficient, and views processed via temporary tables cannot be updated.

If ALGORITHM is omitted, the default algorithm also depends on optimizer configuration, including the derived_merge flag in optimizer_switch.

Check:

~~~sql
SELECT @@optimizer_switch;
~~~

Do not hardcode TEMPTABLE or MERGE based solely on the name. Use EXPLAIN to see how the view is processed and measure on real queries.

### When Cannot MERGE Be Applied?

Certain constructs prevent a view from being merged, for example:

- DISTINCT.
- GROUP BY.
- HAVING.
- Aggregate functions.
- Certain queries with LIMIT.
- UNION or other constructs requiring materialization.

When MERGE is unavailable, MySQL falls back to temporary table processing. If ALGORITHM=MERGE is declared on a view that can only be processed via a temporary table, MySQL issues a warning and sets the algorithm to UNDEFINED.

## 3. Critical Limitation: Views Have No Own Indexes

Indexes cannot be created directly on a view in MySQL.

The following example is invalid:

~~~sql
CREATE INDEX idx_v_paid_customer
ON v_paid_orders (customer_id);
~~~

Indexes must be created on underlying tables:

~~~sql
CREATE INDEX idx_orders_status_customer
ON orders (status, customer_id);
~~~

With a view using MERGE, the optimizer can use indexes on underlying tables as if the query directly referenced that table.

With a view using TEMPTABLE, view results are materialized into an internal temporary table. This kind of view cannot leverage underlying table indexes to access the temporary result in the same way as MERGE; indexes may be used while building the temporary table, but there are no user-defined indexes directly on the view.

This leads to two conclusions:

1. Views do not replace index design on underlying tables.
2. If a report needs fast reads of an aggregated result set, a dedicated reporting table with appropriate indexes can be more useful than recomputing a view every time.

### Views Can Make Queries Harder to Optimize

A complex view can contain JOINs, GROUP BY, DISTINCT, or multiple nested view layers. In that case, querying the view can trigger materialization, sorts, or large intermediate steps.

Check with:

~~~sql
EXPLAIN FORMAT=TREE
SELECT *
FROM v_customer_totals
WHERE total_amount >= 10000;
~~~

If the version/EXPLAIN display does not support TREE for a specific case, use default EXPLAIN or FORMAT=JSON.

Look for signs of:

- Materialize.
- Temporary table.
- Aggregate.
- Sort.
- Full scans on underlying tables.
- Large row estimates at intermediate iterators.

Do not conclude all views are slow. Simple MERGE views are often just an abstraction over the underlying query and can have plans equivalent to directly written SQL.

## 4. Views Are Not Always Updatable

Some views allow INSERT, UPDATE, or DELETE through the view to modify underlying tables. However, this is only valid when MySQL can determine a one-to-one relationship between view rows and underlying table rows, and the view satisfies updatability conditions.

Constructs that typically make a view non-updatable:

- Aggregates such as SUM, COUNT, MIN, MAX.
- Window functions.
- DISTINCT.
- GROUP BY.
- HAVING.
- UNION or UNION ALL.
- Subqueries in the select list.
- Certain types of JOINs.
- Referencing a non-updatable view in FROM.
- ALGORITHM=TEMPTABLE.
- Selecting only literals without an underlying table.

Aggregate view example:

~~~sql
CREATE VIEW v_customer_order_summary AS
SELECT
    customer_id,
    COUNT(*) AS order_count,
    SUM(total_amount) AS total_amount
FROM orders
GROUP BY customer_id;
~~~

You cannot update an aggregated row as if it were a specific orders row:

~~~sql
UPDATE v_customer_order_summary
SET total_amount = 1000
WHERE customer_id = 42;
~~~

MySQL rejects it because an aggregated value does not map one-to-one to a base row.

Check status:

~~~sql
SELECT
    TABLE_NAME,
    IS_UPDATABLE,
    CHECK_OPTION,
    SECURITY_TYPE
FROM INFORMATION_SCHEMA.VIEWS
WHERE TABLE_SCHEMA = DATABASE();
~~~

IS_UPDATABLE shows the updatability flag determined when the view was created. An updatable view may still not be insertable if required columns are missing or view columns are expressions.

Do not design aggregated reporting views expecting users to edit totals and have MySQL automatically deduce how to update source rows.

## 5. Views Can Become Invalid When Underlying Table Schemas Change

A view definition is fixed at CREATE VIEW time. Example:

~~~sql
CREATE VIEW v_order_basic AS
SELECT *
FROM orders;
~~~

If a new column is later added to orders, the new column does not automatically appear in the view. SELECT * was expanded into a column list at the time the view was created.

If a column referenced by the view is DROPped or altered incompatibly, querying the view can fail.

MySQL does not necessarily warn immediately when ALTER/DROP on an underlying table invalidates a view. Errors may only surface when the view is used.

Check with:

~~~sql
CHECK TABLE v_order_basic;
~~~

Retrieve definition:

~~~sql
SHOW CREATE VIEW v_order_basic;
~~~

Design rules:

- Avoid SELECT * in long-lived views.
- List columns explicitly.
- After underlying table migrations, inspect dependent views.
- Update views within the same schema release plan.
- Do not treat a successful ALTER TABLE as proof that all views remain valid.

## 6. Other Syntax and Dependency Limitations

MySQL enforces several specific restrictions on view definitions:

- SELECT in a view cannot reference system variables or user-defined variables.
- Inside a stored program, a view cannot reference parameters or local variables of the program.
- Prepared statement parameters cannot be referenced in a view definition.
- Every referenced table/view must exist when the view is created.
- A view definition cannot reference a TEMPORARY table.
- A TEMPORARY view cannot be created.
- Triggers cannot be attached directly to a view.
- A view can reference at most 61 tables in its definition.

Example showing a view cannot be based on a temporary table:

~~~sql
CREATE TEMPORARY TABLE tmp_daily_orders (
    order_id BIGINT NOT NULL,
    total_amount DECIMAL(12,2) NOT NULL
) ENGINE=InnoDB;

CREATE VIEW v_tmp_daily_orders AS
SELECT *
FROM tmp_daily_orders;
~~~

The CREATE VIEW statement fails because a view definition cannot reference a temporary table.

Additionally, a temporary table exists only in the session that created it. Another session cannot use that temporary table name to query results.

### ORDER BY and LIMIT Inside Views

ORDER BY is allowed in a view definition, but if the outer query has its own ORDER BY, the ordering inside the view is ignored.

Example:

~~~sql
CREATE VIEW v_recent_orders AS
SELECT
    order_id,
    created_at
FROM orders
ORDER BY created_at DESC;
~~~

Query:

~~~sql
SELECT *
FROM v_recent_orders
ORDER BY order_id;
~~~

Results are sorted by the outer query's order_id.

Do not rely on ORDER BY inside a view to guarantee ordering for every query using the view. If results require deterministic order, put ORDER BY in the final SELECT statement.

Do not place LIMIT inside a view and then add another LIMIT in the outer query. MySQL documents the effect of clauses such as LIMIT in both layers as undefined; place the limit at the query layer that accurately expresses the business requirement.

## 7. Views and Data Access Privileges

A view can serve as a security interface layer, but you must choose the right SQL SECURITY mode.

- SQL SECURITY DEFINER: checks access privileges on underlying tables using the view's DEFINER account.
- SQL SECURITY INVOKER: checks privileges using the account calling the view.

Example:

~~~sql
CREATE DEFINER = 'report_owner'@'localhost'
SQL SECURITY DEFINER
VIEW v_public_order_report AS
SELECT
    order_id,
    created_at,
    total_amount
FROM orders
WHERE status = 'PAID';
~~~

Applications can be granted SELECT on the view without being granted direct SELECT on the entire orders table, depending on privilege policies.

Check:

~~~sql
SHOW CREATE VIEW v_public_order_report;
~~~

You must manage the DEFINER account, privileges on underlying tables, and account lifecycles. If DEFINER no longer exists or loses required privileges, the view may not work as expected.

A view does not by itself guarantee sensitive data is hidden if users are still granted direct access privileges on underlying tables.

## 8. When Should You Use a View?

Views are suitable when:

- A SELECT statement needs to be reused.
- You want to hide repeated JOINs or filter conditions.
- You want to provide a stable column interface to applications.
- You want to restrict readable columns/rows via appropriate SQL SECURITY.
- Results need to reflect current data on every query.
- Query computation cost is low enough.

Simple view example:

~~~sql
CREATE ALGORITHM = MERGE
SQL SECURITY INVOKER
VIEW v_customer_paid_orders AS
SELECT
    order_id,
    customer_id,
    total_amount,
    created_at
FROM orders
WHERE status = 'PAID';
~~~

This view fits applications needing to query the latest PAID orders per customer. Applications can still combine WHERE, ORDER BY, and LIMIT on top of the view.

## 9. When Should You Store Report Results in a Dedicated Table?

Consider a reporting table when one or more of the following apply:

- Heavy aggregated reports are accessed repeatedly by many users.
- Snapshots must be retained by day, month, period close, or run timestamp.
- Dedicated indexes are needed for report results.
- Results must be stored for reconciliation or auditing.
- Data freshness needs to be controlled on a schedule.
- Recomputing multi-way JOIN/GROUP BY over large transactional tables must be avoided.
- Reporting load needs to be separated from transactional workloads.

Consider a revenue report by day and product. If every dashboard request must JOIN orders, order_items, and products and GROUP BY over tens of millions of rows, recomputation can consume CPU and I/O and impact transactions.

A summary table pre-storing daily order counts and revenue lets dashboards read far fewer rows.

### Snapshot Tables and Summary Tables

| Table Type | What Does It Store? | Example | Goal |
|---|---|---|---|
| Snapshot | State of data at a point in time | End-of-day account balance | Reconciliation, history, period-end reporting |
| Summary/Aggregate | Grouped/aggregated values | Revenue by day, product, region | Dashboards, fast analytics |
| Report cache | Query results saved for re-reading | Weekly top products list | Reduce repeated computation |
| Staging table | Data being built prior to publishing | New daily summary batch | Separate computation from publish step |

A reporting table is separately managed data. It does not automatically update when source tables change; a refresh process is required.

## 10. Designing a Reporting Table with an Explicit Schema

Do not casually create reporting tables using only CREATE TABLE ... SELECT and assume they retain all characteristics of source tables.

CREATE TABLE ... SELECT can create columns from SELECT expressions, yet some attributes are not preserved as expected. For example, AUTO_INCREMENT is not preserved as in a normal schema copy; VARCHAR may be converted to CHAR depending on expressions and type inference.

Declare the target schema explicitly:

~~~sql
CREATE TABLE report_daily_sales (
    report_date DATE NOT NULL,
    product_id BIGINT UNSIGNED NOT NULL,
    order_count BIGINT UNSIGNED NOT NULL,
    quantity_sold DECIMAL(18,3) NOT NULL,
    revenue DECIMAL(18,2) NOT NULL,
    refreshed_at DATETIME(6) NOT NULL,
    PRIMARY KEY (report_date, product_id),
    KEY idx_report_product_date (product_id, report_date)
) ENGINE=InnoDB;
~~~

Decisions to make:

- Grain: does one row represent a day, a product, or a day + product?
- Primary key: which combination uniquely identifies a row?
- Data types: sufficient precision for totals and quantities?
- Indexes: do dashboards filter primarily by date or by product?
- Time: use DATE, DATETIME, or timestamps according to the business timezone?
- Freshness: up to what point in time is the data updated?
- Retention: how long are snapshots kept?
- Rebuild: can it be regenerated from source data?

The grain must be clear. If one row represents day + product, the appropriate primary key is (report_date, product_id). You cannot use product_id alone if a product appears across multiple days.

## 11. Building a Summary Table from Source Data

Suppose there are three tables:

~~~sql
CREATE TABLE customers (
    customer_id BIGINT UNSIGNED NOT NULL PRIMARY KEY,
    customer_name VARCHAR(150) NOT NULL
) ENGINE=InnoDB;

CREATE TABLE products (
    product_id BIGINT UNSIGNED NOT NULL PRIMARY KEY,
    product_name VARCHAR(150) NOT NULL
) ENGINE=InnoDB;

CREATE TABLE order_items (
    order_item_id BIGINT UNSIGNED NOT NULL PRIMARY KEY,
    order_id BIGINT UNSIGNED NOT NULL,
    product_id BIGINT UNSIGNED NOT NULL,
    quantity DECIMAL(18,3) NOT NULL,
    unit_price DECIMAL(18,2) NOT NULL,
    KEY idx_items_order (order_id),
    KEY idx_items_product (product_id)
) ENGINE=InnoDB;
~~~

The orders table already has status and created_at as in the previous section.

Create summary by day and product:

~~~sql
INSERT INTO report_daily_sales (
    report_date,
    product_id,
    order_count,
    quantity_sold,
    revenue,
    refreshed_at
)
SELECT
    DATE(o.created_at) AS report_date,
    oi.product_id,
    COUNT(DISTINCT o.order_id) AS order_count,
    SUM(oi.quantity) AS quantity_sold,
    SUM(oi.quantity * oi.unit_price) AS revenue,
    CURRENT_TIMESTAMP(6) AS refreshed_at
FROM orders AS o
JOIN order_items AS oi
    ON oi.order_id = o.order_id
WHERE o.status = 'PAID'
GROUP BY
    DATE(o.created_at),
    oi.product_id;
~~~

This is an illustrative example. In real systems, define exact revenue rules:

- Use price at order time or current product price?
- Deduct discounts at the order level or order-item level?
- How are refunds and cancellations handled?
- Are taxes and shipping fees included?
- How are orders that change status after aggregation handled?

If business logic includes refunds or post-payment adjustments, the summary table must reflect accounting/business rules rather than merely SUM(quantity * unit_price).

## 12. Full Reporting Table Refresh with DELETE + INSERT

A straightforward approach is deleting existing data and re-inserting within a single InnoDB transaction:

~~~sql
START TRANSACTION;

DELETE FROM report_daily_sales;

INSERT INTO report_daily_sales (
    report_date,
    product_id,
    order_count,
    quantity_sold,
    revenue,
    refreshed_at
)
SELECT
    DATE(o.created_at),
    oi.product_id,
    COUNT(DISTINCT o.order_id),
    SUM(oi.quantity),
    SUM(oi.quantity * oi.unit_price),
    CURRENT_TIMESTAMP(6)
FROM orders AS o
JOIN order_items AS oi
    ON oi.order_id = o.order_id
WHERE o.status = 'PAID'
GROUP BY
    DATE(o.created_at),
    oi.product_id;

COMMIT;
~~~

With InnoDB, DELETE and INSERT changes only become visible as one committed transaction. Readers running under MVCC can continue reading the previously committed version while the refresh is in progress; after COMMIT, readers see the new data.

Pros:

- Easy to implement.
- Can roll back completely if INSERT fails.
- Prevents readers from seeing an empty table mid-transaction.

Cons:

- Deleting many rows generates undo and redo logs.
- Long transactions hold resources and can impact purge and replication.
- Requires sufficient undo/log space and acceptable lock durations.
- For large reports, rebuild transactions can cause I/O pressure.

This is a suitable option when the reporting table is moderate in size and rebuild time is acceptable.

## 13. Why Not Use TRUNCATE Then INSERT in the Same Transaction?

TRUNCATE TABLE is faster than deleting all rows in many cases, yet TRUNCATE is DDL and causes an implicit commit.

Example:

~~~sql
START TRANSACTION;

TRUNCATE TABLE report_daily_sales;

INSERT INTO report_daily_sales (...)
SELECT ...;

ROLLBACK;
~~~

Do not expect ROLLBACK to restore old data. TRUNCATE triggers an implicit commit and cannot be rolled back like DML. If the subsequent INSERT fails, the reporting table may remain empty or contain partial data depending on error handling.

TRUNCATE also:

- Does not fire DELETE triggers.
- Requires the DROP privilege.
- Has restrictions when referenced by foreign keys from another table.
- Resets AUTO_INCREMENT to the starting value.
- Is written to the binary log as DDL.

Use TRUNCATE only when its DDL semantics are explicitly accepted and a safe publishing strategy is in place. Do not combine TRUNCATE with INSERT in a transaction believing ROLLBACK will protect old data.

## 14. Safe Refresh Using a Staging Table and RENAME TABLE

For large reporting tables, you can build the new version in a staging table and then rename tables to publish.

Flow:

1. Keep report_current serving readers.
2. Prepare report_next with the same schema.
3. Clear old data in report_next.
4. Compute all new data into report_next.
5. Verify row counts, totals, date ranges, and quality checks.
6. Use a single multi-table RENAME TABLE statement to swap current and next.
7. The old table becomes report_next for the next refresh.

### Creating the Staging Table

If the reporting table has no foreign keys to copy:

~~~sql
CREATE TABLE report_next LIKE report_current;
~~~

CREATE TABLE ... LIKE copies columns and indexes along with some schema attributes, but does not copy foreign key definitions. If the table has CHECK constraints, MySQL generates new constraint names. Verify other properties such as triggers, partitions, tablespace options, and privileges before using this approach in production.

If report_next already exists from the previous run, you can empty staging before loading:

~~~sql
TRUNCATE TABLE report_next;
~~~

This is a DDL operation on the staging table, not the current table. It still causes an implicit commit in the session, so run it outside any other business transaction.

### Loading New Data

~~~sql
INSERT INTO report_next (
    report_date,
    product_id,
    order_count,
    quantity_sold,
    revenue,
    refreshed_at
)
SELECT
    DATE(o.created_at),
    oi.product_id,
    COUNT(DISTINCT o.order_id),
    SUM(oi.quantity),
    SUM(oi.quantity * oi.unit_price),
    CURRENT_TIMESTAMP(6)
FROM orders AS o
JOIN order_items AS oi
    ON oi.order_id = o.order_id
WHERE o.status = 'PAID'
GROUP BY
    DATE(o.created_at),
    oi.product_id;
~~~

### Checking Before Publishing

~~~sql
SELECT
    COUNT(*) AS report_rows,
    MIN(report_date) AS first_report_date,
    MAX(report_date) AS last_report_date,
    SUM(revenue) AS total_revenue
FROM report_next;
~~~

Compare against reconciliation queries or independent control figures. Do not publish if staging is incomplete or totals mismatch.

### Swapping Table Names

Assuming both report_current and report_next are InnoDB and report_previous does not exist:

~~~sql
RENAME TABLE
    report_current TO report_previous,
    report_next TO report_current,
    report_previous TO report_next;
~~~

Renames execute left to right within the same statement. Upon completion:

- report_current holds the new data.
- report_next holds the old version.
- Readers querying report_current see the newly published table.

With InnoDB, multi-table RENAME TABLE is atomic DDL when all involved tables use storage engines supporting atomic DDL. Atomic DDL preserves the atomicity of the DDL operation, but DDL still causes an implicit commit; it does not become a rollbackable part of an application transaction.

### Points to Verify Before Using Rename Swap

- All participating tables use storage engines supporting atomic DDL.
- The name report_previous is not already taken.
- Readers may experience metadata locks during the rename.
- Views, foreign keys, triggers, grants, and applications depending on table names have been evaluated.
- Post-publish rollback procedures have been rehearsed.
- The old table is retained long enough for reconciliation before deletion or reuse.
- Refresh jobs use coordination locks so two runs do not overlap.

RENAME TABLE can affect objects depending on table names. Do not assume all views or foreign keys will automatically update as desired after renaming. Check SHOW CREATE VIEW, metadata, and test migrations in staging.

## 15. Incremental Refresh

If source tables are very large, recomputing the entire report every time can be expensive. Incremental refresh recomputes only the affected subset of data.

Example refreshing only recent days:

~~~sql
DELETE FROM report_daily_sales
WHERE report_date >= CURRENT_DATE - INTERVAL 7 DAY;

INSERT INTO report_daily_sales (
    report_date,
    product_id,
    order_count,
    quantity_sold,
    revenue,
    refreshed_at
)
SELECT
    DATE(o.created_at),
    oi.product_id,
    COUNT(DISTINCT o.order_id),
    SUM(oi.quantity),
    SUM(oi.quantity * oi.unit_price),
    CURRENT_TIMESTAMP(6)
FROM orders AS o
JOIN order_items AS oi
    ON oi.order_id = o.order_id
WHERE o.status = 'PAID'
  AND o.created_at >= CURRENT_DATE - INTERVAL 7 DAY
GROUP BY
    DATE(o.created_at),
    oi.product_id;
~~~

Run both DML steps in the same transaction if readers must see either old data or new data without seeing a gap between them.

### Why Must a Time Range Be Recomputed?

If an older order transitions from PENDING to PAID, it can change the report for the order's creation date. If an order is refunded, canceled, has quantities edited, or prices adjusted, older dates' data must also be updated.

An incremental refresh that only reads new orders by created_at can miss changes occurring on older data.

Ways to identify affected subsets:

- Use updated_at to locate modified records.
- Use a change log or event table.
- Record dates/groups needing rebuild when business updates occur.
- Recompute a recent lookback window to handle late-arriving data.
- Run periodic reconciliation jobs to detect discrepancies.

If data can be modified months later, a seven-day window is insufficient. You need a change-tracking mechanism or rebuilds by business keys.

### UPSERT into a Summary Table

With a unique key on date + product:

~~~sql
INSERT INTO report_daily_sales (
    report_date,
    product_id,
    order_count,
    quantity_sold,
    revenue,
    refreshed_at
)
VALUES
    ('2026-11-18', 100, 12, 25.000, 5000.00, CURRENT_TIMESTAMP(6))
AS new
ON DUPLICATE KEY UPDATE
    order_count = new.order_count,
    quantity_sold = new.quantity_sold,
    revenue = new.revenue,
    refreshed_at = new.refreshed_at;
~~~

The row alias syntax after VALUES is available in modern MySQL versions. If an application supports older versions, use syntax compatible with the target deployment version and test beforehand.

UPSERT only updates groups present in the new source data. If a group previously had data but now has zero source rows, UPSERT does not automatically delete the stale group. You must delete/rebuild the affected range or run a reconciliation process.

## 16. Ensuring Reports Reflect a Clear Data Point in Time

A reporting table must answer the question: "As of what point in time are these numbers accurate?"

Store refresh metadata:

~~~sql
CREATE TABLE report_refresh_state (
    report_name VARCHAR(100) NOT NULL PRIMARY KEY,
    refresh_started_at DATETIME(6) NULL,
    refresh_completed_at DATETIME(6) NULL,
    source_watermark DATETIME(6) NULL,
    row_count BIGINT UNSIGNED NULL,
    status ENUM('RUNNING', 'SUCCEEDED', 'FAILED') NOT NULL,
    error_message VARCHAR(1000) NULL
) ENGINE=InnoDB;
~~~

These fields help dashboards or operators know:

- Whether the job is running or finished.
- The most recent successful refresh.
- Up to what watermark source data has been processed.
- How many rows were generated.
- Why the latest run failed.

Do not update status to SUCCEEDED before data has been successfully published. If using staging + rename, update metadata after the publish step using a short DML transaction on the state table.

### Point-in-Time Snapshots

If you need an "end-of-day 2026-11-18" report, do not store only the date without defining the timezone and cutoff time.

For example:

- Business date in Asia/Ho_Chi_Minh.
- Cutoff at 23:59:59 in that timezone.
- Source data processed up to a specific watermark.
- Rules for handling late orders or post-cutoff adjustments.

Store refresh timestamps as DATETIME(6) using UTC or a consistent system-wide convention. Do not mix local and UTC timestamps in the same report.

### Consistency When Reading Multiple Source Tables

Reports frequently JOIN multiple tables. Decide whether all source tables must be read from the exact same snapshot or whether data changing mid-job is acceptable.

With InnoDB, consistent read and isolation levels affect visibility of concurrent changes. Long-running transactions can hold read views open and put pressure on undo/purge. For very large reports, consider running on an appropriate read replica, building watermarked snapshots, or batching with clear rules.

Do not keep transactions open for hours without measuring impact on purge, replication lag, and undo space.

## 17. Temporary Tables Do Not Replace Shared Reporting Tables

Temporary tables are useful for storing intermediate data within a single session:

~~~sql
CREATE TEMPORARY TABLE tmp_customer_totals (
    customer_id BIGINT UNSIGNED NOT NULL PRIMARY KEY,
    total_amount DECIMAL(18,2) NOT NULL
) ENGINE=InnoDB;
~~~

Then:

~~~sql
INSERT INTO tmp_customer_totals (customer_id, total_amount)
SELECT
    customer_id,
    SUM(total_amount)
FROM orders
WHERE status = 'PAID'
GROUP BY customer_id;
~~~

Temporary tables fit:

- Multi-step processing within the same session.
- Intermediate datasets for a single request/job.
- Breaking complex queries into inspectable steps.
- Avoiding recomputing an intermediate set multiple times within the same session.

However, temporary tables have limitations:

- Only the session that created the table can see it.
- The table disappears automatically when the session ends.
- Another session cannot read the results.
- A temporary table cannot be referenced in a view definition.
- A TEMPORARY view cannot be created.
- The same temporary table cannot be referenced multiple times in a single query; you may hit the Can't reopen table error.
- Temporary tables are not a place for persistent report snapshots.

If an application uses a connection pool, a temporary table may outlive a request until the connection closes or the table is DROPped. Actively clean up before returning connections to the pool so subsequent requests do not accidentally read stale data.

## 18. Choosing Between Views, Temporary Tables, and Reporting Tables

| Criterion | View | Temporary Table | Reporting Table |
|---|---|---|---|
| Stores results persistently | No | No | Yes |
| Scope of use | Multiple sessions | Creating session | Multiple sessions |
| Automatically reflects new source data | Yes, on each query | No, unless reloaded | No, requires refresh |
| Has own indexes | No | Can create indexes | Yes |
| Used to store snapshots | No | Only within session | Yes |
| Suitable for repeated heavy reports | Depends on query and optimizer | Depends on single job/session | Often suitable |
| Freshness management | Current source data | Time of temp table load | Watermark/refresh metadata |
| Shared by multiple readers | Yes | No | Yes |

An application can combine all three:

1. Views provide a live data interface.
2. Temporary tables assist intermediate processing inside a job.
3. Reporting tables store aggregated results for multiple readers.

## 19. Hands-on Practice: Moving a Heavy Report from a View to a Dedicated Table

This lab creates a revenue aggregation view, then persists results into an indexed reporting table.

### Step 1: Create the Lab Database

~~~sql
CREATE DATABASE IF NOT EXISTS mysql_report_table_lab;
USE mysql_report_table_lab;

CREATE TABLE orders (
    order_id BIGINT UNSIGNED NOT NULL PRIMARY KEY,
    status VARCHAR(20) NOT NULL,
    created_at DATETIME NOT NULL
) ENGINE=InnoDB;

CREATE TABLE order_items (
    order_item_id BIGINT UNSIGNED NOT NULL PRIMARY KEY,
    order_id BIGINT UNSIGNED NOT NULL,
    product_id BIGINT UNSIGNED NOT NULL,
    quantity DECIMAL(12,3) NOT NULL,
    unit_price DECIMAL(12,2) NOT NULL,
    KEY idx_items_order (order_id),
    KEY idx_items_product (product_id)
) ENGINE=InnoDB;
~~~

### Step 2: Load Sample Data

~~~sql
INSERT INTO orders (order_id, status, created_at)
VALUES
    (1, 'PAID', '2026-11-18 09:00:00'),
    (2, 'PAID', '2026-11-18 10:00:00'),
    (3, 'PENDING', '2026-11-18 11:00:00'),
    (4, 'PAID', '2026-11-19 08:00:00');

INSERT INTO order_items
    (order_item_id, order_id, product_id, quantity, unit_price)
VALUES
    (101, 1, 10, 2.000, 100.00),
    (102, 1, 20, 1.000, 250.00),
    (103, 2, 10, 3.000, 100.00),
    (104, 3, 20, 2.000, 250.00),
    (105, 4, 10, 1.000, 100.00);
~~~

### Step 3: Create the Reporting View

~~~sql
CREATE ALGORITHM = TEMPTABLE VIEW v_daily_product_sales AS
SELECT
    DATE(o.created_at) AS report_date,
    oi.product_id,
    COUNT(DISTINCT o.order_id) AS order_count,
    SUM(oi.quantity) AS quantity_sold,
    SUM(oi.quantity * oi.unit_price) AS revenue
FROM orders AS o
JOIN order_items AS oi
    ON oi.order_id = o.order_id
WHERE o.status = 'PAID'
GROUP BY
    DATE(o.created_at),
    oi.product_id;
~~~

Read the view:

~~~sql
SELECT *
FROM v_daily_product_sales
ORDER BY report_date, product_id;
~~~

On every SELECT, MySQL must run the aggregation query to produce the statement's result.

### Step 4: Create the Reporting Table

~~~sql
CREATE TABLE report_daily_product_sales (
    report_date DATE NOT NULL,
    product_id BIGINT UNSIGNED NOT NULL,
    order_count BIGINT UNSIGNED NOT NULL,
    quantity_sold DECIMAL(18,3) NOT NULL,
    revenue DECIMAL(18,2) NOT NULL,
    refreshed_at DATETIME(6) NOT NULL,
    PRIMARY KEY (report_date, product_id),
    KEY idx_report_product_date (product_id, report_date)
) ENGINE=InnoDB;
~~~

### Step 5: Load Results

~~~sql
INSERT INTO report_daily_product_sales (
    report_date,
    product_id,
    order_count,
    quantity_sold,
    revenue,
    refreshed_at
)
SELECT
    report_date,
    product_id,
    order_count,
    quantity_sold,
    revenue,
    CURRENT_TIMESTAMP(6)
FROM v_daily_product_sales;
~~~

The reporting table now stores computed results. Dashboard queries can use a dedicated index:

~~~sql
SELECT
    report_date,
    product_id,
    revenue
FROM report_daily_product_sales
WHERE product_id = 10
  AND report_date >= '2026-11-18'
ORDER BY report_date DESC;
~~~

### Step 6: Compare Plans

~~~sql
EXPLAIN
SELECT *
FROM v_daily_product_sales
WHERE product_id = 10;

EXPLAIN
SELECT *
FROM report_daily_product_sales
WHERE product_id = 10;
~~~

With the view, the optimizer executes the aggregation query from underlying tables. With the reporting table, the query can use index idx_report_product_date to read pre-aggregated rows.

The lab dataset is small, so timing differences have no benchmark value. The goal is to observe plan structures and the difference between recomputing versus reading pre-stored results.

### Step 7: Refresh the Reporting Table in a Transaction

~~~sql
START TRANSACTION;

DELETE FROM report_daily_product_sales;

INSERT INTO report_daily_product_sales (
    report_date,
    product_id,
    order_count,
    quantity_sold,
    revenue,
    refreshed_at
)
SELECT
    report_date,
    product_id,
    order_count,
    quantity_sold,
    revenue,
    CURRENT_TIMESTAMP(6)
FROM v_daily_product_sales;

COMMIT;
~~~

If INSERT fails before COMMIT, the application can ROLLBACK to preserve the previously committed report version.

### Step 8: Verify Figures

~~~sql
SELECT
    COUNT(*) AS report_rows,
    SUM(revenue) AS total_revenue,
    MAX(refreshed_at) AS refreshed_at
FROM report_daily_product_sales;
~~~

Cross-check against:

~~~sql
SELECT
    SUM(revenue) AS view_revenue
FROM v_daily_product_sales;
~~~

Both revenue totals must match if source data did not change between computations and the same business rules apply.

### Cleanup

~~~sql
DROP DATABASE mysql_report_table_lab;
~~~

Only run DROP DATABASE on the lab database just created.

## 20. Common Mistakes and Fixes

| Symptom | Cause | How to Handle |
|---|---|---|
| View queries are slow | Each call must recompute large JOIN/GROUP BY | Check EXPLAIN; consider a summary table for repeated reports |
| Cannot create index on view | MySQL does not support indexes directly on views | Create indexes on underlying tables or store results in a separate table |
| View is not updatable | Contains GROUP BY, aggregates, DISTINCT, UNION, window functions, or TEMPTABLE | Check IS_UPDATABLE and redesign operations on underlying tables |
| View does not show new column | SELECT * was expanded at CREATE VIEW time | ALTER/CREATE OR REPLACE VIEW with an explicit column list |
| View fails after ALTER/DROP on base table | View definition references an invalid column or table | CHECK TABLE, SHOW CREATE VIEW, and fix dependencies |
| Cannot create view from temporary table | MySQL forbids view definitions from referencing TEMPORARY tables | Use a regular table or suitable CTE |
| Other sessions cannot see temporary table | Temporary tables are session-scoped | Use a regular table if sharing is required |
| Report appears empty during refresh | Using TRUNCATE/DELETE then INSERT across separate commits | Use a DELETE+INSERT transaction or staging + rename |
| ROLLBACK does not restore after TRUNCATE | TRUNCATE causes implicit commit and cannot be rolled back | Use DELETE in a transaction or a staging table |
| Summary table misses updates to older orders | Incremental refresh only reads new data | Track updated_at/change logs or rebuild affected ranges |
| Total revenue does not match | Refunds, discounts, statuses, or late-arriving data unaccounted for | Define grain and business rules, add reconciliation |
| Two refresh jobs overlap | No coordination mechanism | Use scheduler locks, job registry, or coordination locks |
| Staging table lacks indexes/constraints | CREATE TABLE ... SELECT omits schema attributes; CREATE TABLE LIKE omits foreign keys | Declare schema explicitly and verify metadata before publishing |
| Rename swap breaks views | Views/dependencies reference old table or schema names | Check dependencies and test in staging before renaming |
| Dashboard shows stale data | Refresh timestamps are not tracked | Store refreshed_at, watermark, and job status |

## 21. Checklist for Choosing Between Views and Reporting Tables

- [ ] Determined whether data must reflect live state or a point-in-time snapshot.
- [ ] Evaluated report access frequency and recomputation cost.
- [ ] Checked whether the view uses MERGE or TEMPTABLE.
- [ ] Understood that views do not have their own indexes.
- [ ] Checked updatability limitations.
- [ ] Avoided SELECT * in long-lived views.
- [ ] Checked dependencies after schema migrations.
- [ ] Intentionally chosen SQL SECURITY DEFINER or INVOKER.
- [ ] If using a reporting table, defined grain and unique key.
- [ ] Designed data types, precision, and indexes for dashboard queries.
- [ ] Defined rules for revenue, refunds, discounts, and late-arriving orders.
- [ ] Chosen between full refresh and incremental refresh.
- [ ] Defined how new data is published without exposing intermediate states to readers.
- [ ] Do not use TRUNCATE like rollbackable DML.
- [ ] Prepared staging validation and recovery plans if using rename swap.
- [ ] Included watermark, refreshed_at, and job status tracking.
- [ ] Put mechanisms in place to prevent overlapping refresh jobs.
- [ ] Established reconciliation between source numbers and reporting tables.
- [ ] Evaluated long transactions, undo, purge, replication lag, and staging capacity.
- [ ] Tested in staging with data close to production scale.

## 22. Key Principles to Remember

1. Views store SELECT definitions, not persistent report results.
2. MySQL does not provide native materialized views; persisting results requires managing a dedicated reporting table.
3. MERGE incorporates the view definition into the outer query; TEMPTABLE materializes temporary results for the statement.
4. Views have no own indexes; MERGE can use underlying table indexes.
5. TEMPTABLE does not turn a view into a persistent cache table, and TEMPTABLE views are not updatable.
6. Aggregates, GROUP BY, DISTINCT, HAVING, UNION, and window functions typically make views non-updatable.
7. View definitions cannot reference temporary tables; temporary views or triggers on views cannot be created.
8. ORDER BY inside a view does not guarantee ordering for outer queries.
9. SELECT * in a view does not automatically expand when columns are added to underlying tables.
10. Reporting tables must have explicitly designed grain, keys, data types, and indexes.
11. DELETE + INSERT within the same InnoDB transaction can publish new results atomically to readers.
12. TRUNCATE is DDL, causes an implicit commit, and cannot be rolled back like DELETE.
13. Staging + RENAME TABLE can publish new snapshots quickly; check atomic DDL, metadata locks, and dependencies.
14. Incremental refresh must handle older modified, deleted, refunded, or late-arriving data.
15. Every reporting table needs refresh timestamp and watermark metadata so readers understand freshness.
16. Temporary tables are session-scoped; they do not replace reporting tables shared across multiple users.

## Official References

Behaviors in this lesson are verified against the **MySQL 9.7 Reference Manual**:

1. [Using Views](https://dev.mysql.com/doc/refman/9.7/en/views.html): view concepts, creation, and usage.
2. [View Processing Algorithms](https://dev.mysql.com/doc/refman/9.7/en/view-algorithms.html): MERGE, TEMPTABLE, UNDEFINED, and materialization.
3. [Restrictions on Views](https://dev.mysql.com/doc/refman/9.7/en/view-restrictions.html): index restrictions, table limits, dependencies, and index hints.
4. [Updatable and Insertable Views](https://dev.mysql.com/doc/refman/9.7/en/view-updatability.html): updatability conditions and non-updatable constructs.
5. [CREATE VIEW Statement](https://dev.mysql.com/doc/refman/9.7/en/create-view.html): view definition, SQL SECURITY, temporary table restrictions, and ORDER BY/LIMIT behavior.
6. [CREATE TABLE ... SELECT Statement](https://dev.mysql.com/doc/refman/9.7/en/create-table-select.html): creating tables from SELECT and attributes not preserved.
7. [CREATE TABLE ... LIKE Statement](https://dev.mysql.com/doc/refman/9.7/en/create-table-like.html): copying schemas and uncopied attributes such as foreign keys.
8. [TRUNCATE TABLE Statement](https://dev.mysql.com/doc/refman/9.7/en/truncate-table.html): implicit commit, no rollback, trigger, and foreign key restrictions.
9. [Atomic DDL Statement Support](https://dev.mysql.com/doc/refman/9.7/en/atomic-ddl.html): atomic DDL and limits distinguishing it from transactional DDL.
10. [RENAME TABLE Statement](https://dev.mysql.com/doc/refman/9.7/en/rename-table.html): renaming multiple tables in one statement and execution order.
11. [Statements That Cause an Implicit Commit](https://dev.mysql.com/doc/refman/9.7/en/implicit-commit.html): DDL statements causing implicit commits.
12. [INFORMATION_SCHEMA VIEWS Table](https://dev.mysql.com/doc/refman/9.7/en/information-schema-views-table.html): metadata on IS_UPDATABLE, CHECK_OPTION, DEFINER, and SECURITY_TYPE.
13. [Temporary Table Problems](https://dev.mysql.com/doc/refman/9.7/en/temporary-table-problems.html): session scope limits and the Can't reopen table error.

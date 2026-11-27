# Complete Refresh, Fast Refresh, and Materialized View Logs in Oracle

A materialized view (MV) stores the results of a query as physical data so it can be read back faster, reducing repeated computation costs for reports or aggregate queries. Because source data can change after the MV is created, Oracle needs a **refresh** mechanism to synchronize materialized view contents with the base tables.

Oracle provides two primary refresh strategies:

- **Complete refresh:** recomputes the entire MV defining query and replaces the stored contents.
- **Fast refresh:** applies only the changes since the previous refresh, using change records stored in a materialized view log or another supporting mechanism such as Partition Change Tracking (PCT).

For fast refresh to work, the MV query must belong to a supported class in Oracle and master tables must have appropriate logs. A materialized view log records the necessary details about INSERT, UPDATE, and DELETE changes on source tables. An incomplete log design can cause FAST refresh to fail or force the system to use complete refresh.

This lesson explains how both methods work, configuring ON DEMAND/ON COMMIT, creating logs, verifying fast-refresh capability, calling DBMS_MVIEW.REFRESH, monitoring status, and troubleshooting common issues.

## 1. Materialized Views and the Need for Refresh

A standard view stores a query rather than pre-storing a result set. Each time a view is queried, Oracle executes the query against current data in the source tables (subject to optimizer and execution plan).

A materialized view stores the query results at build/refresh time. For instance, a revenue-by-product report might join multiple tables and compute SUM across millions of transactions. If multiple reports read the same aggregation, an MV can avoid recomputing the entire result for every request.

~~~sql
CREATE MATERIALIZED VIEW sales_by_product_mv
BUILD IMMEDIATE
REFRESH COMPLETE ON DEMAND
AS
SELECT product_id,
       SUM(amount) AS total_amount
FROM sales
GROUP BY product_id;
~~~

After creation, the MV holds the computed results. If new transactions arrive in the SALES table, the MV's data does not automatically change while in ON DEMAND mode; it requires a scheduled or manual refresh.

### 1.1. Terms to Distinguish

| Term | Meaning |
|---|---|
| Materialized view | Schema object storing query results |
| Master table/detail table | Source table referenced by the MV query |
| Materialized view log | Object storing change records on a master table to support fast refresh |
| Complete refresh | Recomputes the entire contents of the MV |
| Fast refresh | Applies incremental changes since the previous refresh |
| Refresh mode | When to refresh: ON DEMAND or ON COMMIT |
| Refresh method | How to refresh: COMPLETE, FAST, FORCE |
| Staleness | How fresh or stale MV contents are relative to master tables |
| PCT | Partition Change Tracking, a mechanism that can support incremental refresh in certain partitioned MVs |

### 1.2. Refresh Is Data Synchronization, Not Query Rewrite

Refresh updates the data stored inside the MV. Query rewrite is the optimizer's ability to substitute a query on source tables with an equivalent read from an MV when conditions fit.

The two capabilities are related but distinct:

- An MV can refresh successfully without the optimizer using it to rewrite queries.
- An MV can be configured for rewrite, yet if its data is stale, usage depends on freshness/consistency settings and rewrite policies.
- DBMS_MVIEW.REFRESH performs refreshes; DBMS_MVIEW.EXPLAIN_REWRITE helps analyze rewrite capability and does not replace fast-refresh verification.

## 2. Complete Refresh

**Complete refresh** re-runs the materialized view's defining query to rebuild the entire result set. It does not need a materialized view log to identify incremental changes.

~~~sql
BEGIN
    DBMS_MVIEW.REFRESH(
        list   => 'SALES_BY_PRODUCT_MV',
        method => 'C'
    );
END;
/
~~~

C is the method code for complete refresh.

### 2.1. High-Level Flow

~~~text
Master table changes
        |
        v
Complete refresh requested
        |
        v
Oracle re-executes the MV defining query
        |
        v
Regenerate entire MV result
        |
        v
MV content reflects source data at refresh time
~~~

Complete refresh must read and process the entire dataset required by the MV query. For an aggregate MV over a large table, the cost can approach running the original reporting query again.

### 2.2. Advantages

- Does not depend on having a complete change log.
- Works for many MV definitions that do not qualify for fast refresh.
- Suitable when source data is small, the defining query is simple, or refreshes are infrequent.
- Can be used to rebuild contents after definition changes or when full synchronization is required.

### 2.3. Disadvantages

- May have to read, join, group, and recompute a large volume of data.
- Refresh duration typically grows with source data size and query complexity.
- Can consume significant CPU, I/O, TEMP, and undo/redo depending on execution method and atomic options.
- If refreshes run too frequently, full recomputation load can affect transactional workloads.

### 2.4. Complete Refresh Does Not Require an MV Log

If an MV lacks an MV log or its definition does not support fast refresh, complete refresh can still run provided the defining query is valid and other requirements are met.

This makes complete refresh simple and broadly applicable. However, do not choose complete merely because it is easy to configure if data volumes are huge and frequent refreshes are required.

## 3. Fast Refresh

**Fast refresh** updates an MV by applying only the changes from master tables since the previous refresh, instead of re-running the entire query like complete refresh.

For log-based fast refresh, Oracle reads change data from the materialized view log. In certain cases, Oracle can use another mechanism such as Partition Change Tracking if the MV and partition operations qualify.

~~~sql
BEGIN
    DBMS_MVIEW.REFRESH(
        list   => 'SALES_BY_PRODUCT_MV',
        method => 'F'
    );
END;
/
~~~

F requests a fast refresh. If the MV is ineligible or lacks required log information, the call can fail; Oracle does not automatically fall back to complete just because F was specified.

### 3.1. What Does Fast Refresh Do?

Suppose an MV stores revenue by product:

| Product | Total amount |
|---|---:|
| P01 | 1000 |
| P02 | 700 |

Then the source table receives a new transaction for P01 worth 100 and a new transaction for P03 worth 250.

Fast refresh can apply the delta to bring the MV to:

| Product | Total amount |
|---|---:|
| P01 | 1100 |
| P02 | 700 |
| P03 | 250 |

Instead of rescanning the entire transaction history to recompute every product, Oracle uses the change records and an algorithm tailored to the MV definition.

### 3.2. Advantages

- Typically reduces the amount of data processed when the change rate is small relative to total data.
- Well suited for large MVs needing frequent refreshes.
- Keeps reports closer to source data without running a complete refresh every time.
- When designed properly, refresh cost mainly tracks delta size and log maintenance overhead.

### 3.3. Disadvantages and Prerequisites

- Not all queries support fast refresh.
- Requires a materialized view log with the right keys/columns/metadata, or an eligible PCT mechanism.
- MV logs increase DML cost on master tables and consume extra storage.
- Queries with joins, aggregates, analytic functions, set operators, or complex constructs may face restrictions depending on MV type and Oracle version.
- Whenever the MV definition or source tables change, fast-refresh eligibility must be re-verified.

### 3.4. Fast Refresh Does Not Mean Reading Only the Exact Changed Row Count

A single change on a master table can affect multiple groups or multiple MV rows. For example, updating a product from category A to B can alter two aggregate groups. Fast refresh must accurately recompute affected portions; the work involved is not necessarily equal to the raw DML row count on the source table.

## 4. FORCE Refresh and Choosing a Method

Oracle supports the common refresh methods:

| Method | Meaning |
|---|---|
| COMPLETE (C) | Always requires a complete refresh |
| FAST (F) | Requires a fast refresh; raises an error if ineligible |
| FORCE (?) | Attempts fast refresh if possible; otherwise falls back to complete refresh |

Example:

~~~sql
BEGIN
    DBMS_MVIEW.REFRESH(
        list   => 'SALES_BY_PRODUCT_MV',
        method => '?'
    );
END;
/
~~~

FORCE is convenient when you want Oracle to pick an available option, but note an operational caveat: a refresh can silently fall back to complete and take longer than expected. Inspect LAST_REFRESH_TYPE after execution to see which method actually ran.

If SLAs require short refresh times and only fast refresh is acceptable, explicitly request FAST and monitor for errors. If complete refresh is an acceptable fallback, use FORCE while tracking actual duration and refresh type.

## 5. Comparing COMPLETE, FAST, and FORCE

| Criterion | COMPLETE | FAST | FORCE |
|---|---|---|---|
| Approach | Recomputes full query | Applies incremental changes | Tries FAST, falls back to COMPLETE |
| Requires MV log | Not required | Usually required for log-based fast refresh; PCT can apply in supported cases | Required only if FAST path is chosen |
| Query eligibility | Broader | Must satisfy fast refresh capability | Accepts both; outcome depends on capability |
| Cost | Can be high on large datasets | Typically lower for small deltas, though workload-dependent | Variable |
| Behavior when FAST is unavailable | N/A | Raises error | Runs COMPLETE |
| Best suited for | Small MVs, infrequent refreshes, complex definitions | Large MVs, incremental changes, suitable log/PCT | Wanting automatic fallback and tolerating runtime variance |

There is no single best method for every system. Benchmark on real or representative simulated data, measuring refresh duration, log-induced DML overhead, and report freshness requirements.

## 6. What Is a Materialized View Log?

A **materialized view log** is an Oracle object created on a master table to record the change details required for fast refresh of dependent materialized views.

Each master table can have a single materialized view log shared among eligible dependent MVs. The log is not a full copy of the table; it stores only the metadata/columns Oracle needs to identify and apply changes.

### 6.1. Logs Record DML Changes

Operations recorded can include:

- INSERT: newly added rows.
- UPDATE: modified rows; may require old/new values or referenced columns.
- DELETE: removed rows.
- Certain data load or partition operations have dedicated support mechanisms.

Specific stored details depend on how the log is created, such as ROWID, PRIMARY KEY, SEQUENCE, column list, and INCLUDING NEW VALUES.

### 6.2. Logs Do Not Automatically Refresh Materialized Views

Creating an MV log does not make the MV automatically update right after every DML statement. The log merely records changes. The MV still needs to be refreshed via one of:

- REFRESH ON DEMAND: refreshes when invoked by an application, DBA, or scheduler.
- REFRESH ON COMMIT: refreshes when a transaction modifying the master table commits, if supported for the MV type.
- Scheduled refresh via jobs or DBMS_SCHEDULER.

### 6.3. MV Logs Increase Data Write Costs

Every DML operation on the master table may need to write additional entries to the MV log. Thus, logs can increase:

- redo/undo and I/O;
- storage space usage;
- DML/commit duration;
- log purge work after refreshes.

Before creating a log on a high-throughput transactional table, evaluate the write overhead against actual fast-refresh needs.

## 7. Creating a Materialized View Log

General syntax:

~~~sql
CREATE MATERIALIZED VIEW LOG ON master_table
    [WITH [PRIMARY KEY] [ROWID] [SEQUENCE] [(column_list)]]
    [INCLUDING NEW VALUES];
~~~

Common components:

- PRIMARY KEY: records primary key values to identify changed rows.
- ROWID: records the ROWID of master rows.
- SEQUENCE: records sequence information to distinguish the ordering of changes in certain fast-refresh scenarios.
- (column_list): specifies additional columns to log.
- INCLUDING NEW VALUES: instructs the log to store new values, often needed for fast refresh of aggregate MVs and definitions requiring new values.

There is no single log configuration right for every MV. Base it on the query definition, MV type, master keys, aggregates, joins, and the capabilities Oracle reports.

### 7.1. Primary-Key-Based Log

~~~sql
CREATE MATERIALIZED VIEW LOG ON products
WITH PRIMARY KEY;
~~~

The log stores primary key information for the PRODUCTS table. This suits MVs using primary-key identification when the definition supports it.

The master table must have a valid primary key if the configuration requires primary keys. Without a primary key, do not assume WITH PRIMARY KEY will work as intended.

### 7.2. ROWID-Based Log

~~~sql
CREATE MATERIALIZED VIEW LOG ON sales
WITH ROWID;
~~~

ROWID identifies physical rows in the master table. Rowid-based materialized views can use this log in Oracle-supported scenarios.

ROWID is not a stable business key for applications to store long term. It is an Oracle-managed row identifier that can change during data movement/reorganization operations. Use ROWID only as required for Oracle refresh, not as a business key.

### 7.3. Log with SEQUENCE

~~~sql
CREATE MATERIALIZED VIEW LOG ON sales
WITH ROWID, SEQUENCE;
~~~

SEQUENCE adds change-ordering information. It can be necessary when fast refresh must distinguish multiple operations on the same row or handle complex DML scenarios required by the refresh algorithm.

Not every MV requires SEQUENCE; verify via documentation and EXPLAIN_MVIEW for your exact definition.

### 7.4. Log Recording Referenced Columns

~~~sql
CREATE MATERIALIZED VIEW LOG ON sales
WITH ROWID, SEQUENCE
    (product_id, sale_date, amount)
INCLUDING NEW VALUES;
~~~

This example logs ROWID, sequence, and the columns PRODUCT_ID, SALE_DATE, and AMOUNT, along with new values.

The column list should cover columns referenced by the MV definition, including columns in the select list, filters, joins, group by, and aggregates. A log missing a required column can prevent fast refresh.

### 7.5. Multiple Dependent MVs Sharing One Master Table

Multiple materialized views can depend on the same master table and share a single MV log. Do not create a separate log per MV. When adding a new MV, check whether the existing log already captures enough information for all dependent MVs.

If columns or log attributes must be added, use Oracle-supported MV log management syntax and check the impact on existing MVs. Modifying a log can affect refreshes of dependent MVs; do not alter it casually in production.

## 8. INCLUDING NEW VALUES and Aggregate Materialized Views

Aggregate MVs typically require more information than simple row-selection MVs. For example:

~~~sql
SELECT product_id,
       SUM(amount) AS total_amount
FROM sales
GROUP BY product_id;
~~~

When a transaction changes amount or product, Oracle must know the impact on both the old group and the new group. On updates, storing only changed row identifiers without sufficient values may not be enough to update aggregates accurately.

INCLUDING NEW VALUES lets the log record new values where needed for fast refresh. When designing aggregate MVs, consider:

- All columns in GROUP BY.
- Columns used in aggregate expressions.
- Columns in filter conditions.
- Join columns if the query contains joins.
- COUNT(*) and counting expressions needed to handle inserts/deletes/updates.
- SUM and supporting components needed to maintain AVG.

An aggregate MV example might declare:

~~~sql
CREATE MATERIALIZED VIEW LOG ON sales
WITH ROWID, SEQUENCE
    (product_id, amount)
INCLUDING NEW VALUES;
~~~

This is an illustrative pattern; the final log configuration must be verified against your MV definition and Oracle release.

## 9. Fast Refresh with Aggregates: Why Are COUNT and SUM Needed?

Suppose an MV stores:

~~~sql
SELECT product_id,
       SUM(amount) AS total_amount,
       AVG(amount) AS average_amount
FROM sales
GROUP BY product_id;
~~~

To maintain aggregates after inserts, deletes, or updates, Oracle needs enough information to update totals and counts.

AVG(amount) can be expressed mathematically as:

~~~text
AVG(amount) = SUM(amount) / COUNT(amount)
~~~

Consequently, a fast-refreshable aggregate MV typically needs to store supporting aggregate components, for example:

~~~sql
SELECT product_id,
       COUNT(*) AS row_count,
       COUNT(amount) AS amount_count,
       SUM(amount) AS total_amount,
       SUM(amount * amount) AS sum_amount_squared
FROM sales
GROUP BY product_id;
~~~

The required aggregate list depends on the functions used and capabilities. Do not guess that simply adding SUM is enough for every AVG, variance, or other aggregate. Run DBMS_MVIEW.EXPLAIN_MVIEW to verify precisely.

### 9.1. COUNT(*) and COUNT(column)

These two expressions differ:

- COUNT(*): counts all rows.
- COUNT(amount): counts only rows where AMOUNT is non-null.

If the aggregated column allows nulls, Oracle must distinguish total row count from valid value count. This is why aggregate MVs may require both.

### 9.2. AVG Requires Supporting Components

Mathematically:

~~~text
AVG(amount) = SUM(amount) / COUNT(amount)
~~~

When a row is deleted, knowing only the new sum without knowing the remaining value count makes it impossible to recompute the average accurately. Therefore, fast-refresh aggregates require appropriate supporting components.

## 10. Complete Example: Source Table, Log, and Aggregate MV

The following example illustrates an aggregate MV on a transaction table. Run this in a DEV/TEST schema rather than on real production business tables.

### 10.1. Create the Source Table

~~~sql
CREATE TABLE lab_sales (
    sale_id    NUMBER PRIMARY KEY,
    product_id NUMBER NOT NULL,
    sale_date  DATE NOT NULL,
    amount     NUMBER(12, 2)
);

INSERT ALL
    INTO lab_sales VALUES (1, 101, DATE '2026-01-01', 100)
    INTO lab_sales VALUES (2, 101, DATE '2026-01-02', 150)
    INTO lab_sales VALUES (3, 102, DATE '2026-01-01', 200)
    INTO lab_sales VALUES (4, 102, DATE '2026-01-03', 50)
SELECT 1 FROM dual;

COMMIT;
~~~

### 10.2. Create the Materialized View Log

~~~sql
CREATE MATERIALIZED VIEW LOG ON lab_sales
WITH ROWID, SEQUENCE
    (product_id, sale_date, amount)
INCLUDING NEW VALUES;
~~~

The log records changes on LAB_SALES. The listed columns support the aggregate MV definition below.

### 10.3. Create the Aggregate MV

~~~sql
CREATE MATERIALIZED VIEW lab_sales_by_product_mv
BUILD IMMEDIATE
REFRESH FAST ON DEMAND
AS
SELECT product_id,
       COUNT(*) AS row_count,
       COUNT(amount) AS amount_count,
       SUM(amount) AS total_amount,
       AVG(amount) AS average_amount
FROM lab_sales
GROUP BY product_id;
~~~

This is an illustrative fast-refreshable aggregate MV pattern. Actual fast-refresh eligibility still depends on release, syntax, logs, aggregates, and other constraints; run EXPLAIN_MVIEW before deploying to operations.

### 10.4. View Initial MV Data

~~~sql
SELECT product_id,
       row_count,
       amount_count,
       total_amount,
       average_amount
FROM lab_sales_by_product_mv
ORDER BY product_id;
~~~

Initial output:

| Product | Row count | Amount count | Total amount | Average amount |
|---:|---:|---:|---:|---:|
| 101 | 2 | 2 | 250 | 125 |
| 102 | 2 | 2 | 250 | 125 |

### 10.5. Modify the Source Table

~~~sql
INSERT INTO lab_sales
    (sale_id, product_id, sale_date, amount)
VALUES
    (5, 101, DATE '2026-01-04', 50);

UPDATE lab_sales
SET amount = 100
WHERE sale_id = 3;

COMMIT;
~~~

After commit, an MV in ON DEMAND mode is not automatically updated. MV contents remain stale until refreshed.

### 10.6. Run Fast Refresh

~~~sql
BEGIN
    DBMS_MVIEW.REFRESH(
        list   => 'LAB_SALES_BY_PRODUCT_MV',
        method => 'F'
    );
END;
/
~~~

Read again:

~~~sql
SELECT product_id,
       row_count,
       amount_count,
       total_amount,
       average_amount
FROM lab_sales_by_product_mv
ORDER BY product_id;
~~~

Expected output after refresh:

| Product | Row count | Amount count | Total amount | Average amount |
|---:|---:|---:|---:|---:|
| 101 | 3 | 3 | 300 | 100 |
| 102 | 2 | 2 | 150 | 75 |

### 10.7. Run Complete Refresh for Comparison

~~~sql
BEGIN
    DBMS_MVIEW.REFRESH(
        list   => 'LAB_SALES_BY_PRODUCT_MV',
        method => 'C'
    );
END;
/
~~~

The final output should reflect source data identically to fast refresh if both methods run successfully against the same point-in-time data. The difference lies in how Oracle recomputes the contents, not in query result semantics.

## 11. ON DEMAND and ON COMMIT

Refresh method (FAST, COMPLETE, FORCE) answers **how to refresh**. Refresh mode (ON DEMAND, ON COMMIT) answers **when to refresh**.

### 11.1. ON DEMAND

~~~sql
CREATE MATERIALIZED VIEW sales_by_product_mv
BUILD IMMEDIATE
REFRESH FAST ON DEMAND
AS
SELECT product_id,
       COUNT(*) AS row_count,
       SUM(amount) AS total_amount
FROM sales
GROUP BY product_id;
~~~

The MV refreshes when explicitly invoked or via a scheduled job. This is the common choice for reports tolerating minutes or hours of data lag.

It can be scheduled using DBMS_SCHEDULER or an appropriate system scheduler. Use a controlled schedule, monitor failures, and prevent overlapping refreshes.

### 11.2. ON COMMIT

~~~sql
CREATE MATERIALIZED VIEW sales_by_product_mv
BUILD IMMEDIATE
REFRESH FAST ON COMMIT
AS
SELECT product_id,
       COUNT(*) AS row_count,
       SUM(amount) AS total_amount
FROM sales
GROUP BY product_id;
~~~

When a transaction modifying the master table commits, Oracle refreshes the MV per the declared mode if the definition supports it.

Advantages:
- The MV is synchronized immediately at transaction commit (when refresh succeeds).
- Applications do not need to schedule separate refreshes after each batch of changes.

Disadvantages:
- Master transaction commits can take longer.
- DML throughput can suffer from MV maintenance overhead.
- Not suitable for every MV definition or workload.
- A transaction updating multiple tables/groups can make commit-time refresh heavy.

Do not choose ON COMMIT solely because you want data "always fresh." Evaluate commit latency, DML volume, MV complexity, and fast-refresh restrictions.

### 11.3. ON DEMAND Combined with a Scheduler

For reporting systems, one option is periodic refresh:

~~~sql
BEGIN
    DBMS_SCHEDULER.CREATE_JOB(
        job_name        => 'REFRESH_SALES_MV_JOB',
        job_type        => 'PLSQL_BLOCK',
        job_action      => q'[
            BEGIN
                DBMS_MVIEW.REFRESH(
                    list   => 'SALES_BY_PRODUCT_MV',
                    method => 'F'
                );
            END;
        ]',
        start_date      => SYSTIMESTAMP,
        repeat_interval => 'FREQ=MINUTELY;INTERVAL=15',
        enabled         => TRUE
    );
END;
/
~~~

This example creates a job every 15 minutes. Adjust repeat_interval, privileges, and scheduling per your environment. Before creating a production job, check whether a job with the same name already exists, operational policies, refresh duration, and whether a prior run might still be executing when the next trigger fires.

## 12. BUILD IMMEDIATE and BUILD DEFERRED

Besides refresh mode, MV creation offers build options:

- BUILD IMMEDIATE: executes the query right away to populate initial data.
- BUILD DEFERRED: creates MV metadata first; contents are populated on a later refresh.

Example:

~~~sql
CREATE MATERIALIZED VIEW sales_by_product_mv
BUILD DEFERRED
REFRESH FAST ON DEMAND
AS
SELECT product_id,
       COUNT(*) AS row_count,
       SUM(amount) AS total_amount
FROM sales
GROUP BY product_id;
~~~

Afterward, you can invoke refresh to populate data if the definition supports the chosen method:

~~~sql
BEGIN
    DBMS_MVIEW.REFRESH(
        list   => 'SALES_BY_PRODUCT_MV',
        method => '?'
    );
END;
/
~~~

BUILD DEFERRED does not mean the MV immediately holds usable results. Before the first refresh, the MV may have no data; applications must manage readiness state.

## 13. Checking FAST REFRESH Capability with EXPLAIN_MVIEW

Do not guess whether fast refresh is supported just because MV creation succeeds. Oracle provides DBMS_MVIEW.EXPLAIN_MVIEW to analyze the refresh capabilities of a materialized view or query definition.

### 13.1. Prepare the Capability Table

In many environments, you must create MV_CAPABILITIES_TABLE using Oracle's utlxmv.sql script from the Oracle Home admin directory. Running this script requires appropriate privileges and governance; do not run admin scripts in production without DBA approval.

Once the table exists, call:

~~~sql
BEGIN
    DBMS_MVIEW.EXPLAIN_MVIEW('LAB_SALES_BY_PRODUCT_MV');
END;
/
~~~

### 13.2. Read the Results

~~~sql
SELECT capability_name,
       possible,
       related_text,
       msgtxt
FROM mv_capabilities_table
ORDER BY seq;
~~~

Key columns:

- CAPABILITY_NAME: the capability Oracle is analyzing.
- POSSIBLE: Y or N, indicating whether that capability is supported in the analyzed context.
- RELATED_TEXT: the relevant query component, if any.
- MSGTXT: explanation or reason why the capability is unavailable.

The result set can contain many rows for different capabilities, not just one FAST row. Read all rows relating to fast refresh, joins, aggregates, and PCT.

### 13.3. Analyze a Definition Before Creating the MV

EXPLAIN_MVIEW can also accept a query/DDL string via documented overloads. This is useful when designing an MV before creating the object. Check your release's package signature and execution privileges on DBMS_MVIEW.

### 13.4. EXPLAIN_MVIEW Does Not Replace Refresh Testing

Capability analysis tells you whether Oracle assesses the definition as eligible under current conditions. After creating the MV and log, still test realistic DML patterns (INSERT, UPDATE, DELETE, join key changes, nulls, multiple DMLs on one row), run fast refresh, and verify results.

## 14. Monitoring Materialized View Status

Useful data dictionary views:

- USER_MVIEWS: materialized views owned by the current schema.
- ALL_MVIEWS: materialized views accessible to the user.
- DBA_MVIEWS: all MVs in the database, requiring DBA privileges.
- USER_MVIEW_LOGS/ALL_MVIEW_LOGS/DBA_MVIEW_LOGS: materialized view log metadata.
- USER_MVIEW_DETAIL_RELATIONS: detail/master relationship metadata for MVs, depending on privileges and version.

### 14.1. View Configured Method and Last Refresh

~~~sql
SELECT mview_name,
       refresh_mode,
       refresh_method,
       last_refresh_type,
       last_refresh_date,
       staleness,
       compile_state
FROM user_mviews
ORDER BY mview_name;
~~~

These columns identify:
- Which refresh mode the MV is configured with.
- Configured refresh method.
- Actual method used by the most recent refresh.
- Refresh timestamp.
- Fresh/stale status.
- Compilation state of the MV.

Displayed column names can vary by release or dictionary view; inspect your database's dictionary views.

### 14.2. View Materialized View Logs

~~~sql
SELECT log_table,
       master,
       rowids,
       primary_key,
       sequence,
       include_new_values
FROM user_mview_logs
ORDER BY master;
~~~

This view shows key log attributes, helping DBAs verify logs were created as intended.

### 14.3. Check Freshness

An MV may be reported as FRESH, STALE, or another state depending on metadata and Oracle's evaluation. Do not rely solely on refresh timestamp to conclude data is fresh; master tables may have changed after the refresh.

Applications must define freshness requirements:
- Financial reports may require successful refresh up to a specific watermark.
- Operational dashboards may tolerate 5–15 minutes of data lag.
- Reference lookup data may tolerate longer delays.

Freshness is a business requirement, not just a status column.

## 15. ATOMIC_REFRESH and Its Impact on Availability

DBMS_MVIEW.REFRESH accepts the atomic_refresh parameter. This parameter controls how Oracle performs refreshes and atomicity when refreshing one or more MVs.

Example:

~~~sql
BEGIN
    DBMS_MVIEW.REFRESH(
        list           => 'LAB_SALES_BY_PRODUCT_MV',
        method         => 'C',
        atomic_refresh => TRUE
    );
END;
/
~~~

### 15.1. Atomic Refresh = TRUE

When atomic refresh is requested, Oracle maintains transactional atomicity of the refresh operation within API scope. For complete refresh, execution typically uses DML operations to replace contents rather than a truncate that cannot roll back like DML.

Advantages:
- Reduces the risk of readers seeing an empty MV mid-complete-refresh.
- If refresh fails, Oracle can roll back refresh changes within the transaction per supported mechanics.
- When refreshing multiple MVs in one call, maintains atomic consistency within supported scope.

Disadvantages:
- Can consume extra undo/redo and resources.
- Complete refresh can be slower than the non-atomic path.

### 15.2. Atomic Refresh = FALSE

For complete refresh, Oracle can use TRUNCATE followed by reload to speed execution. Because truncate is DDL with an implicit commit in Oracle, it cannot be rolled back like a regular DELETE.

Advantages:
- Can reduce overhead compared to row-by-row DML deletes.
- Suitable when an MV is huge and an unavailability window is acceptable.

Risks:
- Refresh is no longer atomic as with TRUE.
- If the reload fails after old contents are truncated, the MV may lack complete data until a refresh succeeds again.
- When refreshing multiple MVs, readers can observe inconsistent states across MVs.

Do not set atomic_refresh => FALSE solely for speed without assessing reader impact and recovery plans.

### 15.3. Atomic Refresh Differs from JDBC Autocommit

ATOMIC_REFRESH is an Oracle refresh API parameter; Connection.setAutoCommit controls the transaction state of a JDBC connection. Both relate to transaction boundaries, but they are not the same concept. When calling DBMS_MVIEW.REFRESH from JDBC, understand Oracle's refresh API and transaction behavior rather than assuming setAutoCommit(false) turns a non-atomic DDL/refresh into an atomic one.

## 16. PCT: Partition Change Tracking

With partitioned master tables and materialized views meeting the right criteria, Oracle can use **Partition Change Tracking (PCT)** to fast-refresh based on modified partitions.

PCT is not simply another materialized view log. It relies on partition relationships between detail tables and the MV, along with Oracle-supported partitioning and query definition rules.

PCT can be useful when:
- Data is loaded or modified by partition.
- Certain partitions are replaced/exchanged while others remain untouched.
- The MV structure allows Oracle to determine which result subsets are affected by partition changes.

Operations like TRUNCATE PARTITION, EXCHANGE PARTITION, and DROP PARTITION can affect MV refreshability and freshness. Do not assume every partition maintenance operation automatically supports fast refresh. Run EXPLAIN_MVIEW, review PCT documentation for your release, and test partition maintenance procedures in the target environment.

## 17. Materialized View Logs and Change Data Lifecycle

An MV log must retain enough changes so dependent MVs can refresh. Once an MV refreshes successfully, Oracle manages log purging based on the status of dependent MVs and related configuration.

Do not manually delete or truncate Oracle's internal log tables to "reclaim space." Manage logs using supported materialized view log statements and inspect dependent MVs.

### 17.1. Continuous DML and Log Growth

If a master table receives heavy DML while an MV does not refresh for a long period, the log can accumulate many change rows. Consequences:
- Consumes storage.
- Fast refresh after a long gap may have to process a huge backlog of changes.
- Refresh times increase.
- DML continues incurring log-writing overhead.

Typical solutions are proper refresh schedules, space monitoring, and cleaning up abandoned dependent MVs.

### 17.2. Multiple MVs Sharing One Log

If a master table has multiple dependent MVs, the log must retain entries for all of them. One MV finishing its refresh does not mean all entries can be purged if another MV has not yet refreshed. When an old MV is neglected, the log may be forced to retain more changes.

### 17.3. Dropping a Materialized View Log

Once you are sure no MVs still require the log and have assessed the impact, you can run:

~~~sql
DROP MATERIALIZED VIEW LOG ON sales;
~~~

This is DDL that affects the fast-refresh capability of dependent MVs. After dropping the log, dependent MVs may require a complete refresh or recreating an appropriate log before fast refresh can resume. Never drop a log to free space without checking dependencies first.

## 18. Master Table Changes and Impact on Fast Refresh

Schema changes or special data operations can cause an MV to lose fast-refresh capability or require a full refresh.

Examples:
- Modifying columns referenced by the MV.
- Changing primary/unique keys.
- Changing the query definition.
- Altering partitioning or performing partition maintenance.
- Certain direct-path loads or bulk operations.
- Dropping/recreating logs or altering log attributes.

After changes, you should:
1. Check MV and log status.
2. Run EXPLAIN_MVIEW.
3. Test fast refresh in DEV/TEST.
4. If fast refresh is unavailable, evaluate complete refresh and required duration.
5. Plan refresh/availability windows before applying to production.

## 19. Choosing a Refresh Strategy by Workload

| Scenario | Strategy Typically Considered |
|---|---|
| Small MV, infrequent source changes | COMPLETE ON DEMAND |
| Large MV, low change rate, eligible query | FAST ON DEMAND |
| MV must update with source commit, moderate DML | FAST ON COMMIT if supported and benchmarked |
| MV supports fast refresh but needs fallback | FORCE ON DEMAND with LAST_REFRESH_TYPE monitoring |
| Partition-loaded data, MV supports PCT | Evaluate PCT/fast refresh |
| Scheduled bulk imports | FAST or COMPLETE based on capability and delta ratio; run post-batch |
| Report tolerates 15-minute lag | Scheduled ON DEMAND |
| OLTP system with strict commit latency | Consider avoiding ON COMMIT if refresh increases commit times |

A practical way to choose a method:
- Estimate master row counts and delta percentage between refreshes.
- Measure complete refresh runtime.
- Measure fast refresh runtime across representative DML patterns.
- Measure MV log overhead on write workloads.
- Define freshness SLAs and maintenance windows.
- Choose atomic refresh aligned with availability needs.
- Monitor refresh duration, failures, and staleness post-deployment.

## 20. Common Errors and Troubleshooting

| Symptom | Possible Cause | Resolution |
|---|---|---|
| FAST refresh fails | MV definition does not support fast refresh | Run EXPLAIN_MVIEW, read capabilities and messages |
| FAST refresh reports missing log | Master table lacks an MV log or log misses details | Create/augment log matching MV definition |
| FORCE refresh runs unexpectedly long | Oracle fell back to COMPLETE | Check LAST_REFRESH_TYPE, logs, and fast-refresh capability |
| MV stays stale after DML | ON DEMAND mode has not been refreshed | Invoke refresh or check scheduler |
| ON COMMIT slows commits | Refresh work executes during master commit | Benchmark workload; consider ON DEMAND |
| MV shows wrong results after data changes | Definition/refresh capability or log does not cover pattern | Check DML patterns, logs, refresh, and reconcile with source query |
| MV log grows large | Infrequent refreshes or unrefreshed dependent MV | Check dependencies and refresh schedule |
| Complete refresh causes temporary MV unavailability | Atomic refresh false using truncate/reload | Evaluate atomic refresh true or appropriate out-of-place strategy |
| Fast refresh unavailable after DDL | Schema/definition changes altered capability | Run EXPLAIN_MVIEW and complete refresh if needed |
| Scheduler job does not run | Job disabled, credential/privilege or schedule issue | Inspect USER_SCHEDULER_JOBS, USER_SCHEDULER_JOB_RUN_DETAILS |
| One MV refreshes while another stays stale | MVs have separate schedules or refresh runs | Track individual MVs and dependencies |
| Unsure if actual refresh was FAST or COMPLETE | Looking only at configured REFRESH_METHOD | Inspect LAST_REFRESH_TYPE and job history |

## 21. Querying Scheduler Job Monitoring

If using DBMS_SCHEDULER, you can inspect the job and recent runs:

~~~sql
SELECT job_name,
       enabled,
       state,
       repeat_interval,
       last_start_date,
       next_run_date
FROM user_scheduler_jobs
WHERE job_name = 'REFRESH_SALES_MV_JOB';
~~~

View history:

~~~sql
SELECT log_date,
       status,
       error#,
       actual_start_date,
       run_duration,
       additional_info
FROM user_scheduler_job_run_details
WHERE job_name = 'REFRESH_SALES_MV_JOB'
ORDER BY log_date DESC;
~~~

If the job calls a refresh procedure, log refresh errors, actual duration, and refresh method used. Do not rely solely on job status SUCCEEDED: the procedure may finish after choosing FORCE fallback to complete; inspect MV metadata.

## 22. Deployment Workflow for a Fast-Refresh Materialized View

A deployment workflow should follow these steps:

1. **Define the MV query:** list master tables, joins, filters, group by, and aggregates.
2. **Check capability:** run DBMS_MVIEW.EXPLAIN_MVIEW on the proposed definition.
3. **Design the MV log:** choose primary key/rowid, columns, sequence, and including new values per capabilities.
4. **Create logs:** on each required master table.
5. **Create the MV:** choose BUILD IMMEDIATE or BUILD DEFERRED, REFRESH FAST, and appropriate mode.
6. **Test DML:** inserts/updates/deletes, join key updates, nulls, multiple DMLs in a single transaction.
7. **Refresh and reconcile:** compare MV results against the base query after each DML scenario.
8. **Measure overhead:** refresh time, log write overhead, log storage, commit latency.
9. **Set up monitoring:** last refresh type/date, staleness, job history, and errors.
10. **Prepare fallback:** complete refresh or rebuild procedure if fast refresh becomes unavailable.

## 23. Checklist Before Choosing FAST REFRESH

- Does your Oracle release support fast refresh for the MV query?
- Do all master tables requiring logs have them?
- Does the log use the right identifier type (PRIMARY KEY/ROWID)?
- Are columns needed for select, filter, join, group by, and aggregates included in the log?
- Are SEQUENCE or INCLUDING NEW VALUES required?
- Does an aggregate MV include supporting aggregates like COUNT(*) and COUNT(expr)?
- Are real-world DML patterns supported?
- Do any partition maintenance or direct-path load operations interfere?
- Is the refresh mode ON DEMAND or ON COMMIT? Has commit latency been measured?
- Does ATOMIC_REFRESH align with availability requirements?
- Are LAST_REFRESH_TYPE, STALENESS, duration, and job failures monitored?
- Is there a complete refresh plan if fast refresh becomes unavailable?

## 24. Controlled Hands-On Exercises

Exercises use LAB_SALES and LAB_SALES_BY_PRODUCT_MV created in Section 10. Run only in an authorized DEV/TEST schema and the right PDB/service. Never create logs, MVs, or run refreshes on production business tables without an approved plan.

### Exercise 1 — Observe ON DEMAND

1. Create the source table, log, and MV per Section 10.
2. Query the MV to record initial results.
3. Insert a new transaction into the source table and commit.
4. Query the MV before refreshing.
5. Call DBMS_MVIEW.REFRESH(..., method => 'F').
6. Re-query the MV and compare.

Explain why committing DML does not automatically update the MV when using ON DEMAND.

### Exercise 2 — Compare FAST and COMPLETE

With data populated:
1. Insert/update/delete several source rows.
2. Run FAST refresh.
3. Record runtime and results.
4. Modify source data again.
5. Run COMPLETE refresh.
6. Reconcile MV contents with a direct aggregate query on the source table.

Do not focus solely on timing over a few lab rows; the primary goal is understanding method differences.

### Exercise 3 — Test FORCE

Call:

~~~sql
BEGIN
    DBMS_MVIEW.REFRESH(
        list   => 'LAB_SALES_BY_PRODUCT_MV',
        method => '?'
    );
END;
/
~~~

Then inspect:

~~~sql
SELECT mview_name, last_refresh_type, last_refresh_date, staleness
FROM user_mviews
WHERE mview_name = 'LAB_SALES_BY_PRODUCT_MV';
~~~

Identify whether the actual refresh used FAST or COMPLETE.

### Exercise 4 — EXPLAIN_MVIEW

1. Confirm MV_CAPABILITIES_TABLE was prepared by a DBA or the Oracle Home script.
2. Run DBMS_MVIEW.EXPLAIN_MVIEW.
3. Read capabilities related to FAST and aggregates.
4. Locate rows with POSSIBLE = 'N' and explanatory messages.
5. Note any changes needed for the query or log.

### Exercise 5 — Check Log and DML Overhead

1. Query USER_MVIEW_LOGS.
2. Perform multiple inserts/updates/deletes on the source table.
3. Refresh the MV.
4. Observe DML and refresh durations.
5. Discuss the trade-off between log-writing overhead and complete refresh runtime.

### Exercise 6 — Compare ON COMMIT and ON DEMAND

In a dedicated lab schema, create two MVs suited to the two modes or recreate the MV under each configuration. Measure commit duration while updating the source table. Explain why ON COMMIT can increase commit latency and why not all MVs support this mode.

### Clean Up Lab Data

Only once you verify the objects were created by you in DEV/TEST and no one else uses them:

~~~sql
DROP MATERIALIZED VIEW lab_sales_by_product_mv;
DROP MATERIALIZED VIEW LOG ON lab_sales;
DROP TABLE lab_sales PURGE;
~~~

This order drops the MV first, then the log on the master table, and finally the lab table. DDL operations perform an implicit commit; never run in production or on any object outside practice scope.

## 25. Review Questions

**Question 1.** How does complete refresh differ from fast refresh?

**Answer:** Complete refresh re-runs the entire MV defining query; fast refresh applies incremental changes since the previous refresh using an MV log or supporting mechanism like PCT.

**Question 2.** Does complete refresh require a materialized view log?

**Answer:** No. MV logs primarily support log-based fast refresh.

**Question 3.** Which method code specifies FAST refresh in DBMS_MVIEW.REFRESH?

**Answer:** F.

**Question 4.** What does FORCE refresh do when fast refresh is unavailable?

**Answer:** Oracle can fall back to complete refresh; check LAST_REFRESH_TYPE to see the actual method used.

**Question 5.** What does a materialized view log store?

**Answer:** Change information on the master table required for fast refresh, such as primary key/ROWID, referenced columns, sequence, and new values depending on configuration.

**Question 6.** What is the purpose of INCLUDING NEW VALUES?

**Answer:** Instructs the log to store new values of changed columns where needed for fast refresh, especially for certain aggregate MVs.

**Question 7.** Why might an aggregate MV need COUNT(*) and COUNT(expression)?

**Answer:** To accurately maintain total row counts and non-null value counts across inserts/deletes/updates; these components help recompute aggregates like AVG.

**Question 8.** How does ON DEMAND differ from ON COMMIT?

**Answer:** ON DEMAND refreshes when invoked or scheduled; ON COMMIT refreshes along with the master transaction commit if the definition supports it.

**Question 9.** What can ATOMIC_REFRESH => FALSE affect?

**Answer:** Oracle can use truncate/reload for complete refresh to speed execution; refresh is no longer atomic as with TRUE, and the MV may lack full data if reload fails.

**Question 10.** How do you check whether an MV supports fast refresh?

**Answer:** Use DBMS_MVIEW.EXPLAIN_MVIEW, read MV_CAPABILITIES_TABLE, and test refreshes in the target environment.

**Question 11.** If a master table has multiple dependent MVs, do you need to create a separate log for each MV?

**Answer:** No. Eligible MVs can share one MV log on the master table; the log must contain enough information for all dependent MVs.

**Question 12.** Does a successful refresh mean the optimizer will use the MV to rewrite every query?

**Answer:** No. Refresh and query rewrite are separate features; rewrite also depends on query equivalence, configuration, and freshness policies.

## Conclusion

**Complete refresh** recomputes the entire MV defining query and does not require a materialized view log. **Fast refresh** applies incremental changes, typically relying on master table logs or PCT; it works only when the MV definition, logs, and DML patterns meet Oracle's criteria. FORCE tries fast refresh and may fall back to complete, so monitor LAST_REFRESH_TYPE to avoid runtime surprises.

Materialized view logs record change details such as PRIMARY KEY, ROWID, SEQUENCE, column lists, and INCLUDING NEW VALUES. Logs enable fast refresh at the expense of extra DML overhead and storage. ON DEMAND supports scheduled or explicit refreshes; ON COMMIT keeps MVs closer to source data while adding work to the commit path. ATOMIC_REFRESH is a separate choice governing atomicity and how MV contents are replaced, not a refresh method.

Before deploying, check capabilities with DBMS_MVIEW.EXPLAIN_MVIEW, test realistic inserts/updates/deletes, measure refresh time and log overhead, verify post-refresh freshness, and set up monitoring along with a complete-refresh fallback when fast refresh is no longer viable.

## Oracle Reference Documentation

- [Oracle Database 19c Data Warehousing Guide — Refreshing Materialized Views](https://docs.oracle.com/en/database/oracle/oracle-database/19/dwhsg/refreshing-materialized-views.html): complete/fast refresh, refresh modes, PCT, and operational considerations.
- [Oracle Database 19c SQL Reference — CREATE MATERIALIZED VIEW](https://docs.oracle.com/en/database/oracle/oracle-database/19/sqlrf/CREATE-MATERIALIZED-VIEW.html): MV creation syntax, build modes, and refresh clauses.
- [Oracle Database 19c SQL Reference — CREATE MATERIALIZED VIEW LOG](https://docs.oracle.com/en/database/oracle/oracle-database/19/sqlrf/CREATE-MATERIALIZED-VIEW-LOG.html): log syntax, primary key, ROWID, sequence, and new values.
- [Oracle Database 19c PL/SQL Packages — DBMS_MVIEW](https://docs.oracle.com/en/database/oracle/oracle-database/19/arpls/DBMS_MVIEW.html): REFRESH, EXPLAIN_MVIEW, and MV management procedures.
- [Oracle Database 19c Reference — USER_MVIEWS](https://docs.oracle.com/en/database/oracle/oracle-database/19/refrn/USER_MVIEWS.html): materialized view refresh and staleness metadata.
- [Oracle Database 19c Reference — USER_MVIEW_LOGS](https://docs.oracle.com/en/database/oracle/oracle-database/19/refrn/USER_MVIEW_LOGS.html): materialized view log metadata.

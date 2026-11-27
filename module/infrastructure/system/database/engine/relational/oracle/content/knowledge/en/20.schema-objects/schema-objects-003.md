# Materialized Views and Choosing ON DEMAND vs. ON COMMIT in Oracle Database

In a reporting system, a query might have to aggregate millions of transaction rows every time a user opens a dashboard. If the aggregated results do not need to be recomputed from scratch on every request, Oracle Database can pre-store those results as a **materialized view (MV)**. When source data changes, the materialized view must be refreshed to stay synchronized with the underlying tables.

When creating a materialized view, an important decision is **when to refresh**:

- **ON DEMAND:** refreshes when requested by an application, DBA, or scheduler. Data in the MV can become stale between refreshes.
- **ON COMMIT:** refreshes automatically when a transaction modifying the underlying tables commits. Data is updated at the commit boundary, but the refresh cost is placed on the data-write path.

This choice affects report freshness, COMMIT latency, system load, fault tolerance, and operations. No single option is best for every workload. You need to understand what a materialized view stores, how FAST/COMPLETE/FORCE refreshes work, how materialized view logs support them, and how much staleness reporting queries can tolerate.

## 1. How Do Views and Materialized Views Differ?

### 1.1 Standard Views

A view stores a query definition; it does not store query results as a physical copy:

~~~sql
CREATE OR REPLACE VIEW v_sales_by_region AS
SELECT region_id,
       SUM(amount) AS total_amount
FROM sales
GROUP BY region_id;
~~~

When querying:

~~~sql
SELECT *
FROM v_sales_by_region;
~~~

Oracle executes a query plan based on the source tables. A view encapsulates logic and promotes SQL reuse; the view itself is not a pre-stored snapshot of results.

### 1.2 Materialized Views

A materialized view stores query results as physical data in the database. For example:

~~~sql
CREATE MATERIALIZED VIEW mv_sales_by_region
BUILD IMMEDIATE
REFRESH COMPLETE ON DEMAND
AS
SELECT region_id,
       SUM(amount) AS total_amount
FROM sales
GROUP BY region_id;
~~~

Oracle executes the defining query to populate initial data in the MV. When querying:

~~~sql
SELECT *
FROM mv_sales_by_region;
~~~

the application reads the materialized data. An MV can reduce repeated computation costs, especially when aggregate queries are expensive and source data changes less frequently than it is read.

### 1.3 Comparison

| Criterion | View | Materialized View |
|---|---|---|
| Stores SQL definition | Yes | Yes |
| Stores physical result data | Not as a result copy | Yes |
| When queried | Computed from source data and execution plan | Reads materialized results; may be used by optimizer via query rewrite |
| Updating results | Reflects source data per query | Requires refresh per policy |
| Storage cost | Primarily metadata | Requires segment, indexes, and metadata |
| Source write overhead | No MV refresh | May incur log/refresh overhead |
| Best suited for | Logic encapsulation, flexible querying | Reports/aggregations needing result reuse |

A materialized view is not automatically faster than a view. If an MV requires frequent COMPLETE refreshes, grows too large, or the source query is already inexpensive, the combined storage and refresh costs may not be worthwhile.

## 2. Components of a Materialized View

An MV typically consists of:

1. **Defining query:** the SELECT specifying what data is stored.
2. **Detail/base tables:** the source tables read by the defining query.
3. **Materialized view segment:** where Oracle stores the result rows.
4. **Refresh method:** how results are synchronized, such as FAST or COMPLETE.
5. **Refresh mode:** when refreshes occur, such as ON DEMAND or ON COMMIT.
6. **Materialized view log:** metadata/change records on base tables, when required for fast refresh.
7. **Indexes and statistics:** support direct queries on the MV and the optimizer.

Example flow:

~~~text
SALES (transaction table)
        |
        v
Defining query: GROUP BY REGION
        |
        v
MV_SALES_BY_REGION (physically stored results)
        |
        +--> Dashboard reads results
        |
        +--> Optimizer can consider query rewrite
~~~

A materialized view is a schema object that can be queried like a table or view. However, applications should normally treat it as derived data and let Oracle refresh it per policy; do not arbitrarily update MV rows directly as if it were an authoritative business table.

## 3. Creating a Basic Materialized View

### 3.1 Create Sample Source Table

In a dedicated lab schema:

~~~sql
CREATE TABLE sales (
    sale_id   NUMBER PRIMARY KEY,
    region_id NUMBER NOT NULL,
    sale_date DATE NOT NULL,
    amount    NUMBER(12,2)
);
~~~

Load a few rows:

~~~sql
INSERT INTO sales VALUES (1, 10, DATE '2026-01-05', 100);
INSERT INTO sales VALUES (2, 10, DATE '2026-01-06', 150);
INSERT INTO sales VALUES (3, 20, DATE '2026-01-07', 200);
INSERT INTO sales VALUES (4, 20, DATE '2026-01-08', 50);
COMMIT;
~~~

### 3.2 Create an On-Demand MV

~~~sql
CREATE MATERIALIZED VIEW mv_sales_by_region
BUILD IMMEDIATE
REFRESH COMPLETE ON DEMAND
AS
SELECT region_id,
       COUNT(*) AS sale_count,
       COUNT(amount) AS known_amount_count,
       SUM(amount) AS total_amount
FROM sales
GROUP BY region_id;
~~~

Options:

- BUILD IMMEDIATE: runs the defining query immediately upon creation to populate initial data.
- REFRESH COMPLETE: on every refresh, recomputes the entire result set from the defining query.
- ON DEMAND: does not automatically refresh on every commit to source tables; refreshes when invoked or scheduled.

Query the MV:

~~~sql
SELECT *
FROM mv_sales_by_region
ORDER BY region_id;
~~~

Initial results:

| REGION_ID | SALE_COUNT | KNOWN_AMOUNT_COUNT | TOTAL_AMOUNT |
|---:|---:|---:|---:|
| 10 | 2 | 2 | 250 |
| 20 | 2 | 2 | 250 |

### 3.3 BUILD IMMEDIATE and BUILD DEFERRED

- BUILD IMMEDIATE: creates the MV and populates initial data right away.
- BUILD DEFERRED: creates metadata first without populating data until the first refresh.

If using BUILD DEFERRED, schedule an initial refresh before applications depend on the MV. Do not assume a newly created MV already contains data before it is populated.

### 3.4 Declare Refresh Mode Explicitly

Oracle typically defaults to ON DEMAND refresh mode if ON COMMIT is not specified. However, production DDL should state the mode explicitly so readers do not rely on defaults:

~~~sql
REFRESH COMPLETE ON DEMAND
~~~

Explicit syntax makes code reviews and migration operations easier.

## 4. Two Refresh Mode Options: ON DEMAND and ON COMMIT

### 4.1 ON DEMAND

ON DEMAND means the MV is refreshed when requested. Requests can come from:

- A DBA or operator calling DBMS_MVIEW.REFRESH.
- An application invoking a refresh procedure on a business schedule.
- DBMS_SCHEDULER running a periodic job.
- A batch pipeline refreshing after loading source data.

Between refreshes, the MV can enter a STALE state relative to base tables. This is acceptable when reports can tolerate latency.

### 4.2 ON COMMIT

ON COMMIT means Oracle refreshes the MV when a transaction modifying the underlying tables commits. The refresh is tied to that transaction's commit path.

This reduces the window during which MV data is stale after a source transaction commits, but it can slow down application commits because the database must perform the associated refresh work.

In write-heavy workloads, a transaction may update multiple rows/base tables and trigger MV refreshes. If multiple ON COMMIT MVs depend on the same source, write overhead can grow significantly.

### 4.3 Comparison Table

| Criterion | ON DEMAND | ON COMMIT |
|---|---|---|
| Refresh timing | When invoked or scheduled | When a transaction modifying base tables commits |
| Data freshness | Has delay based on schedule/request | Refreshed at commit boundary if refresh succeeds |
| Impact on source table COMMIT | Usually decoupled from data write commit | Can increase commit latency |
| Timing control | Flexible | Automatic on commit |
| Ability to batch changes | Can batch multiple changes into one refresh | Refresh tied to each relevant transaction commit |
| Best suited for | Periodic reports, batch jobs, lag-tolerant dashboards | Small/eligible MVs requiring near-immediate freshness |
| Operations | Requires scheduler/trigger to invoke refresh and schedule monitoring | Requires monitoring direct impact on write path |

### 4.4 Neither Option Is Always Better

Choosing ON COMMIT merely to keep "data always fresh" can increase transaction latency in an OLTP system. Choosing ON DEMAND for a report requiring immediate post-transaction figures can expose stale numbers to users.

The decision should be based on:

- Maximum acceptable data staleness.
- Frequency and volume of DML on base tables.
- Number of dependent MVs.
- Fast-refresh eligibility of the defining query.
- Read-path and write-path SLAs.
- Refresh windows, resources, and recovery mechanisms.

## 5. Refresh Methods: FAST, COMPLETE, and FORCE

Refresh mode answers **when** to refresh; refresh method answers **how** to refresh.

### 5.1 COMPLETE Refresh

COMPLETE refresh re-executes the defining query to recompute the entire MV dataset:

~~~sql
BEGIN
    DBMS_MVIEW.REFRESH(
        list   => 'MV_SALES_BY_REGION',
        method => 'C'
    );
END;
/
~~~

'C' is the method code for COMPLETE in DBMS_MVIEW. This refresh approach does not depend on computing deltas from an MV log, but it can be resource-intensive if the source query is large.

Suitable when:

- The MV is small or the defining query does not support fast refresh.
- Refresh frequency is low.
- Recomputing the full result simplifies operations.
- Source or structural changes make fast refresh infeasible.

### 5.2 FAST Refresh

FAST refresh updates the MV using recorded changes on base tables rather than recomputing the entire result set. For many MV types, Oracle requires a materialized view log on base tables, and the defining query must meet fast-refresh criteria.

~~~sql
BEGIN
    DBMS_MVIEW.REFRESH(
        list   => 'MV_SALES_BY_REGION',
        method => 'F'
    );
END;
/
~~~

FAST refresh typically reduces the amount of data processed when changes are small relative to the full table. However, it adds log-writing, storage, and refresh-capability management overhead.

Not every SELECT is fast-refreshable. Factors such as GROUP BY, aggregates, DISTINCT, UNION, joins, expressions, subqueries, and DML patterns on source tables affect eligibility. Use the capability checker instead of guessing from syntax alone.

### 5.3 FORCE Refresh

FORCE asks Oracle to attempt a FAST refresh if possible; otherwise, Oracle can perform a COMPLETE refresh:

~~~sql
BEGIN
    DBMS_MVIEW.REFRESH(
        list   => 'MV_SALES_BY_REGION',
        method => '?'
    );
END;
/
~~~

The question mark is the FORCE code in the DBMS_MVIEW API. This option is flexible, though execution costs can vary across runs: FAST one time, COMPLETE another. If SLAs depend on refresh duration, monitor and verify which method is actually used.

### 5.4 Distinguishing Mode and Method

| Concept | Examples | Question Answered |
|---|---|---|
| Refresh mode | ON DEMAND, ON COMMIT | When is the MV refreshed? |
| Refresh method | FAST, COMPLETE, FORCE | How is the refresh performed? |

Example:

~~~sql
REFRESH FAST ON DEMAND
~~~

means refresh on demand, using the FAST method if the defining query meets eligibility requirements.

~~~sql
REFRESH FAST ON COMMIT
~~~

means requesting a fast refresh whenever a transaction modifying base tables commits. You must verify that the MV is eligible for fast refresh and meets restrictions for your Oracle version.

## 6. Materialized View Logs and FAST Refresh

### 6.1 Why Is a Materialized View Log Needed?

To perform a fast refresh, Oracle needs to know what changes occurred on base tables since the previous refresh. A materialized view log records those change details to support this process.

Illustrative example:

~~~sql
CREATE MATERIALIZED VIEW LOG ON sales
WITH ROWID, SEQUENCE (region_id, sale_date, amount)
INCLUDING NEW VALUES;
~~~

The MV log is created on the SALES base table. Log options depend on the defining query type and desired fast refresh behavior:

- PRIMARY KEY or ROWID determines how source rows are identified.
- Logged columns must satisfy the needs of the defining query.
- SEQUENCE may be required in scenarios needing change ordering preserved.
- INCLUDING NEW VALUES stores new value information required for certain fast refreshes, especially with aggregates.

This is an illustrative example, not a universal recipe for every MV. Exact columns and options must be determined from query capabilities and your Oracle version.

### 6.2 MV Logs Increase Write Overhead

When INSERT, UPDATE, or DELETE occurs on a base table, Oracle may need to write additional entries to the MV log. This increases:

- Storage consumption.
- Associated redo/undo and I/O.
- DML work on base tables.
- Log purging work after corresponding refreshes.

FAST refresh reduces MV recomputation cost in some workloads, but it is not free. Measure total read, write, refresh, and storage costs.

### 6.3 One Table Can Have a Log Serving Multiple MVs

A single materialized view log on a base table can support multiple dependent MVs if its configuration satisfies all of their requirements. If a new MV requires unlogged columns or missing options, the log may need modification. Do not drop a log simply because one MV was dropped if other MVs still depend on it.

### 6.4 Checking FAST Refresh Capability

Oracle provides DBMS_MVIEW.EXPLAIN_MVIEW to analyze the refresh and query rewrite capabilities of an MV or defining query.

In a privileged schema, create the capability table using the Oracle-supplied script, typically utlxmv.sql in the database admin directory:

~~~sql
@?/rdbms/admin/utlxmv.sql
~~~

Then:

~~~sql
BEGIN
    DBMS_MVIEW.EXPLAIN_MVIEW(
        mv           => 'MV_SALES_BY_REGION',
        statement_id => 'CHECK_SALES_MV'
    );
END;
/
~~~

Inspect the results:

~~~sql
SELECT capability_name,
       possible,
       related_text,
       msgtxt
FROM mv_capabilities_table
WHERE statement_id = 'CHECK_SALES_MV'
ORDER BY seq;
~~~

Capability rows explain FAST refresh eligibility, PCT refresh, query rewrite, and unmet conditions. Refer to the utlxmv.sql script accompanying your database version for exact output column names.

### 6.5 Run EXPLAIN_MVIEW Before Choosing ON COMMIT

If you plan to use ON COMMIT, verify fast-refresh capability before deploying. ON COMMIT puts refresh on the commit path, so an ineligible MV or heavy refresh can make operations unsustainable.

Beyond capability checks, test realistic DML in a test environment to measure commit latency and evaluate triggers, foreign keys, concurrency, and the number of dependent MVs.

## 7. FAST Refresh Example for an Aggregate MV

The following example illustrates an MV aggregating sales by region. Actual fast-refresh eligibility must be confirmed with EXPLAIN_MVIEW on your specific Oracle version and defining query.

### 7.1 Create the MV Log

~~~sql
CREATE MATERIALIZED VIEW LOG ON sales
WITH ROWID, SEQUENCE (region_id, amount)
INCLUDING NEW VALUES;
~~~

### 7.2 Create an MV with Refresh-Supporting Aggregates

~~~sql
CREATE MATERIALIZED VIEW mv_sales_fast
BUILD IMMEDIATE
REFRESH FAST ON DEMAND
AS
SELECT region_id,
       COUNT(*) AS row_count,
       COUNT(amount) AS amount_count,
       SUM(amount) AS total_amount
FROM sales
GROUP BY region_id;
~~~

For aggregate MVs, additional aggregates such as COUNT(*) and COUNT(measure) may be required so Oracle can maintain results across INSERT/UPDATE/DELETE. Exact prerequisites depend on aggregate type and defining query.

### 7.3 Modify the Source Table

~~~sql
INSERT INTO sales (
    sale_id,
    region_id,
    sale_date,
    amount
)
VALUES (
    5,
    10,
    DATE '2026-01-10',
    75
);

COMMIT;
~~~

Because the MV is ON DEMAND, it has not been instructed to refresh merely because the source transaction committed. Querying the MV before refresh can still return old figures.

### 7.4 Invoke FAST Refresh

~~~sql
BEGIN
    DBMS_MVIEW.REFRESH(
        list   => 'MV_SALES_FAST',
        method => 'F'
    );
END;
/
~~~

After the refresh, querying the MV reflects the change according to refresh capabilities and semantics. If FAST is not feasible, a command explicitly requesting FAST may fail; do not assume Oracle will automatically fall back to COMPLETE when method is explicitly set to F.

### 7.5 Compare with COMPLETE

~~~sql
BEGIN
    DBMS_MVIEW.REFRESH(
        list   => 'MV_SALES_FAST',
        method => 'C'
    );
END;
/
~~~

COMPLETE recomputes the entire result per the defining query. It is a fallback when fast refresh is unsuitable, though runtime, I/O, and workload impact must be evaluated.

## 8. ON DEMAND: Manual or Scheduled Refresh

### 8.1 Manual Refresh

~~~sql
BEGIN
    DBMS_MVIEW.REFRESH(
        list   => 'MV_SALES_BY_REGION',
        method => 'C'
    );
END;
/
~~~

An application or DBA can invoke refresh after a data load batch finishes. For eligible MVs, use F to request FAST; use a question mark to request FORCE.

### 8.2 Scheduling with DBMS_SCHEDULER

Example hourly refresh:

~~~sql
BEGIN
    DBMS_SCHEDULER.CREATE_JOB(
        job_name        => 'JOB_REFRESH_MV_SALES',
        job_type        => 'PLSQL_BLOCK',
        job_action      =>
            'BEGIN DBMS_MVIEW.REFRESH(''MV_SALES_BY_REGION'', ''F''); END;',
        start_date      => SYSTIMESTAMP,
        repeat_interval => 'FREQ=HOURLY;INTERVAL=1',
        enabled         => TRUE,
        comments        => 'Refresh sales materialized view hourly'
    );
END;
/
~~~

The job runs on the declared schedule. Ensure the owner has proper privileges, the defining query and MV log are ready, refresh schedules do not excessively overlap, and completion time fits within operational windows.

### 8.3 A Refresh Schedule Does Not Guarantee Strict Hourly Freshness

If a job fails, is disabled, lacks resources, or takes longer than its interval, the MV may remain stale longer than expected. Operations must monitor:

- Most recent successful refresh.
- Stale status.
- Execution duration and failure count.
- Whether the job is currently running or delayed.
- Actual data lag against SLA.

### 8.4 Refresh After Batch Load

If ETL loads data once nightly, the MV can be refreshed after ETL and validation finish. This avoids refreshing repeatedly while source data is loaded incrementally.

A typical workflow:

~~~text
Load source data
       |
       v
Validate / reconcile
       |
       v
COMMIT source batch
       |
       v
Refresh MV
       |
       v
Verify results and mark batch complete
~~~

If the refresh fails, keep the state indicating the batch is loaded while the MV is un-updated, and allow refresh retries per policy. Do not blindly rerun ETL if the source batch has already committed.

## 9. ON COMMIT: Refreshing in the Commit Path

### 9.1 Create an ON COMMIT MV

Illustrative example:

~~~sql
CREATE MATERIALIZED VIEW mv_sales_on_commit
BUILD IMMEDIATE
REFRESH FAST ON COMMIT
AS
SELECT region_id,
       COUNT(*) AS row_count,
       COUNT(amount) AS amount_count,
       SUM(amount) AS total_amount
FROM sales
GROUP BY region_id;
~~~

For this pattern to work, the defining query must qualify for FAST refresh and base tables need appropriate MV logs. ON COMMIT imposes restrictions on query structure and source objects; check capabilities and the SQL Language Reference for your Oracle version.

### 9.2 What Happens When a Source Transaction COMMITs?

Example:

~~~sql
INSERT INTO sales (
    sale_id,
    region_id,
    sale_date,
    amount
)
VALUES (
    6,
    10,
    DATE '2026-01-11',
    25
);

COMMIT;
~~~

When the transaction modifying SALES commits, Oracle performs the ON COMMIT refresh for the dependent MV per configured mechanics. Refresh work is attached to commit, so COMMIT duration can increase.

### 9.3 ON COMMIT Does Not Refresh After Every Individual DML Statement

If a transaction runs:

~~~sql
INSERT INTO sales VALUES (7, 10, DATE '2026-01-12', 40);
UPDATE sales SET amount = 45 WHERE sale_id = 7;
DELETE FROM sales WHERE sale_id = 7;

COMMIT;
~~~

ON COMMIT ties the refresh to the moment the transaction commits, rather than refreshing separately after each INSERT, UPDATE, and DELETE statement. This lets Oracle process the transaction's changes as a single refresh unit.

### 9.4 Impact on Latency and Throughput

ON COMMIT can work well when changes are small and commit frequency is moderate. In OLTP systems with many short transactions, each transaction updating a base table can trigger a refresh. Consequences:

- Commit latency increases.
- CPU and I/O increase on the write path.
- MV logs and refresh consume resources.
- Multiple dependent MVs can amplify overhead.
- Transactions can encounter errors if the refresh fails to complete as required.

Measure p50/p95/p99 commit latency and transaction throughput, not just SELECT latency on the MV.

### 9.5 ON COMMIT Is Not a Cross-System Synchronization Mechanism

ON COMMIT updates MVs within the same Oracle database according to base table relationships. It does not guarantee that external services, caches, search indexes, or other BI systems have received the data. Those systems require their own synchronization mechanisms.

## 10. Data Freshness and STALE Status

### 10.1 MVs Can Become Stale

With ON DEMAND, after base tables change but before the next refresh, an MV can contain stale results. Oracle maintains metadata indicating freshness/staleness status.

### 10.2 Checking MV Status

In the MV-owning schema:

~~~sql
SELECT mview_name,
       staleness,
       last_refresh_type,
       last_refresh_date,
       compile_state
FROM user_mviews
ORDER BY mview_name;
~~~

These columns help operations inspect:

- STALENESS: freshness/staleness state per Oracle metadata.
- LAST_REFRESH_TYPE: most recent refresh type.
- LAST_REFRESH_DATE: timestamp of the most recent refresh.
- COMPILE_STATE: compilation state of the MV.

Metadata names/columns can vary by version or dictionary view used; inspect USER_MVIEWS/ALL_MVIEWS/DBA_MVIEWS on your system.

### 10.3 STALE Does Not Necessarily Mean Data Is Wrong for Every Purpose

If a dashboard tolerates 15-minute-old data, a 5-minute-stale MV may still meet requirements. Conversely, an account balance screen requiring immediate updates may not tolerate staleness even for a few seconds.

Define freshness via business requirements, for example:

- Executive dashboard: at most 15 minutes.
- End-of-day report: refreshed after batch ETL completes.
- Reconciliation report: read only after confirming successful refresh.
- Transactional flow: read source tables or use an appropriate synchronization mechanism if stale MV data is unacceptable.

### 10.4 Query Rewrite and Freshness

If query rewrite is enabled for an MV, Oracle may use the MV instead of querying source tables when conditions fit. Whether a stale MV is used also depends on QUERY_REWRITE_INTEGRITY and freshness policy. Never assume query rewrite always uses the freshest data or always chooses the MV.

## 11. Query Rewrite: The Optimizer Using Materialized Views

### 11.1 Purpose

Query rewrite lets the optimizer substitute a query against source tables with an equivalent query against an MV when the MV contains sufficient data and semantic conditions are met.

Example aggregate MV:

~~~sql
CREATE MATERIALIZED VIEW mv_sales_region_qr
BUILD IMMEDIATE
REFRESH COMPLETE ON DEMAND
ENABLE QUERY REWRITE
AS
SELECT region_id,
       SUM(amount) AS total_amount
FROM sales
GROUP BY region_id;
~~~

An application can run:

~~~sql
SELECT region_id,
       SUM(amount)
FROM sales
GROUP BY region_id;
~~~

Oracle can consider rewriting to the MV if query rewrite is enabled, privileges and metadata align, the MV qualifies, and the optimizer sees a cost benefit. This is not a guarantee that every similar query will always read the MV.

### 11.2 Enabling Query Rewrite at Session/Database Level

Relevant system/session parameter:

~~~sql
ALTER SESSION SET QUERY_REWRITE_ENABLED = TRUE;
~~~

Permission to alter parameters depends on the environment. DBAs can configure this system-wide; developers may need appropriate privileges to set it at the session level.

### 11.3 QUERY_REWRITE_INTEGRITY

Common levels:

- ENFORCED: requires constraints/conditions guaranteeing correctness to be strictly enforced per policy.
- TRUSTED: lets the optimizer rely on certain declared/trusted constraints and relationships.
- STALE_TOLERATED: allows using stale MVs within permitted policy boundaries.

Do not pick STALE_TOLERATED merely for speed if reports require current data. Query rewrite integrity is a decision about result correctness, not just a performance tuning knob.

### 11.4 Checking Query Rewrite

Inspect the execution plan:

~~~sql
EXPLAIN PLAN FOR
SELECT region_id,
       SUM(amount)
FROM sales
GROUP BY region_id;

SELECT *
FROM TABLE(DBMS_XPLAN.DISPLAY);
~~~

If the plan shows access to the MV, the optimizer selected the MV for that query. If not, possible reasons include disabled query rewrite, MV ineligibility, freshness/integrity settings, statistics, cost, or expression differences.

## 12. Choosing ON DEMAND vs. ON COMMIT by Workload

### 12.1 ON DEMAND Fits When

- Reports tolerate scheduled data lag.
- Source tables experience continuous writes and you want to avoid adding refresh work to every commit.
- Multiple changes can be batched into a single refresh.
- The MV is large or COMPLETE refresh must run within a batch window.
- The system has an ETL pipeline and clear checkpoints.
- You want proactive control over refresh timing, load, and windows.

Examples: a sales summary dashboard refreshed every 15 minutes, or an executive report after an end-of-day batch.

### 12.2 ON COMMIT Fits When

- The MV must reflect changes as soon as source transactions commit.
- Change volume is small or incremental refresh is very lightweight.
- The defining query meets fast-refresh requirements and ON COMMIT restrictions.
- Write workload budgets accommodate the extra refresh cost.
- Operations have measured commit latency and configured appropriate alerting.

Example: a small summary table powering an admin screen that must reflect committed transactions nearly immediately.

### 12.3 Decision Table

| Question | If Answer Is "Yes" | Consideration |
|---|---|---|
| Do reports tolerate minutes/hours of staleness? | Yes | ON DEMAND |
| Is there a scheduled batch load? | Yes | ON DEMAND after batch |
| Is OLTP commit volume high and low latency required? | Yes | Avoid adding refresh to every commit; consider ON DEMAND |
| Must the MV update immediately upon commit? | Yes | Evaluate ON COMMIT |
| Is the defining query ineligible for fast refresh? | Yes | ON DEMAND with COMPLETE/FORCE or redesign MV |
| Do base tables change infrequently and is the MV small? | Yes | ON COMMIT may fit if eligible |
| Do multiple MVs depend on the same table? | Yes | Measure total refresh cost and consider scheduled batching |
| Is exact control over refresh timing required? | Yes | ON DEMAND |

## 13. Refresh Options and Operational Controls

### 13.1 DBMS_MVIEW.REFRESH

Refresh a single MV:

~~~sql
BEGIN
    DBMS_MVIEW.REFRESH(
        list   => 'MV_SALES_BY_REGION',
        method => 'F'
    );
END;
/
~~~

Refresh multiple MVs:

~~~sql
BEGIN
    DBMS_MVIEW.REFRESH(
        list   => 'MV_SALES_BY_REGION,MV_SALES_BY_PRODUCT',
        method => 'C'
    );
END;
/
~~~

MVs with dependencies or ordering requirements must be designed properly. Do not simply concatenate names into a string while ignoring relationships among nested MVs.

### 13.2 Atomic Refresh

DBMS_MVIEW.REFRESH accepts the atomic_refresh parameter. When appropriate, atomic refresh refreshes a group of MVs more atomically; if a refresh fails, the refresh changes can roll back according to API semantics. Setting atomic_refresh to FALSE can enable a different refresh strategy and better performance in some cases, but requires understanding intermediate visibility states, recoverability, and version-specific DDL/refresh limitations.

Do not change atomic_refresh just to make refreshes faster without testing on representative data. It is an operational and consistency choice.

### 13.3 COMPLETE Refresh Can Be Resource-Intensive

For large MVs, COMPLETE refresh can re-read large amounts of source data and generate significant I/O, CPU, TEMP, and redo/undo depending on the refresh mechanism. Schedule it during suitable load windows and check capacity and impact on concurrent queries.

### 13.4 FORCE Refresh Can Vary in Runtime

FORCE uses FAST if feasible, otherwise COMPLETE. Thus the same job can exhibit different runtimes after schema, log, or defining query changes. Monitor LAST_REFRESH_TYPE and runtime rather than looking only at job success status.

## 14. Restrictions and Pre-Deployment Checks

Materialized views and refreshes are governed by many rules depending on Oracle version, defining query type, and source objects. Before deploying, verify at least:

- Is the defining query eligible for FAST refresh?
- Do source tables have MV logs with the right columns/options?
- Are there remote tables/database links? Certain refresh modes, especially ON COMMIT, have restrictions with remote detail tables.
- Does the MV use joins, aggregates, DISTINCT, UNION, analytic functions, subqueries, or complex expressions?
- Does it use objects/views or functions affecting determinism?
- Are primary keys/ROWIDs/sequences/new values required in the log?
- Is ON COMMIT supported for the specific query structure?
- Are there nested MVs or multiple MVs depending on the same base table?
- Does refresh conflict with batch loads, partition maintenance, or DDL?
- Are log capacity and change retention sufficient for the refresh schedule?

Do not infer FAST eligibility merely because a SELECT statement runs. A valid SELECT does not imply a materialized view can fast-refresh.

## 15. Monitoring Materialized Views and Refresh Jobs

### 15.1 List MVs in a Schema

~~~sql
SELECT mview_name,
       refresh_mode,
       refresh_method,
       staleness,
       last_refresh_type,
       last_refresh_date
FROM user_mviews
ORDER BY mview_name;
~~~

These columns show configured mode, method, and most recent refresh status. Metadata may have additions or differences by version; check your database's dictionary views.

### 15.2 Inspect Materialized View Logs

~~~sql
SELECT log_table,
       master,
       rowids,
       primary_key,
       include_new_values
FROM user_mview_logs
ORDER BY master;
~~~

USER_MVIEW_LOGS shows logs attached to base tables in the schema. Use corresponding ALL_/DBA_ views for greater detail when privileged.

### 15.3 Inspect Refresh Jobs

~~~sql
SELECT job_name,
       enabled,
       state,
       last_start_date,
       next_run_date,
       run_count,
       failure_count
FROM user_scheduler_jobs
WHERE job_name = 'JOB_REFRESH_MV_SALES';
~~~

Job history:

~~~sql
SELECT log_date,
       status,
       error#,
       actual_start_date,
       run_duration,
       additional_info
FROM user_scheduler_job_run_details
WHERE job_name = 'JOB_REFRESH_MV_SALES'
ORDER BY log_date DESC;
~~~

Monitoring jobs and monitoring freshness are two distinct tasks. A job can report SUCCESS while the MV still misses its freshness SLA if the schedule is too infrequent or source data continues changing.

### 15.4 Reconciliation Data Checks

You can compare MV aggregates with source queries during a verification window:

~~~sql
SELECT region_id,
       SUM(amount) AS source_total
FROM sales
GROUP BY region_id;
~~~

and:

~~~sql
SELECT region_id,
       total_amount
FROM mv_sales_by_region;
~~~

In production, reconciliation may require a consistent snapshot, matching cutoff/batch ID, or matching point-in-time data. If source tables keep changing between two SELECT statements, differing totals do not necessarily prove the MV refreshed incorrectly.

## 16. Modifying Defining Queries and Refresh Setup

### 16.1 CREATE OR REPLACE Is Not a Universal MV Alteration Method

A materialized view has its own metadata and stored segment data. Do not mechanically apply CREATE OR REPLACE VIEW habits to materialized views. When changing a defining query, follow an appropriate process such as DROP/CREATE or Oracle-supported MV operations, evaluating dependencies, privileges, indexes, logs, and downtime.

### 16.2 Modifying Base Tables

ALTER TABLE on detail tables can affect defining queries, MV logs, or refresh capability. Before migration:

1. List MVs depending on the table.
2. Check logs and refresh capability.
3. Determine whether DDL invalidates MVs or alters query semantics.
4. Plan refresh/recreate steps and post-deployment verification.

Oracle DDL issues an implicit commit, so do not put schema changes in the same transaction as backfill DML expecting a full rollback if refresh fails.

### 16.3 Drop MV Logs Only When No Dependencies Remain

~~~sql
DROP MATERIALIZED VIEW LOG ON sales;
~~~

Drop a log only after confirming no remaining MVs depend on it for fast refresh. If dependent MVs still exist, their fast refreshes may fail or require switching to an alternative method.

## 17. Materialized Views and Query Rewrite in Reporting Architecture

### 17.1 MVs as a Reporting Layer

One architecture pattern:

~~~text
OLTP tables
    |
    v
MV logs / refresh process
    |
    v
Materialized views (summary layer)
    |
    +--> Dashboard
    +--> BI reports
    +--> Query rewrite
~~~

MVs help isolate reporting read workloads from repeated aggregation over transactional tables. However, they still consume database resources and require a freshness policy.

### 17.2 Choose Mode Based on Read and Write SLAs

If write SLAs prioritize fast commits, ON DEMAND is usually preferable since refreshes run separately. If read SLAs demand immediate post-commit updates and refresh is lightweight, ON COMMIT can make sense.

Ask not only "How fresh does the report need to be?" but also "Can source transactions afford the extra refresh cost?".

### 17.3 Query Rewrite Does Not Replace an API Contract

Applications should not depend on the optimizer definitely rewriting every query to an MV. If an application needs to read a specific MV, it can query the MV directly and manage freshness explicitly; if relying on automatic optimizer rewrite, accept that it is a cost-based decision and verify execution plans.

## 18. Lab Exercise: Comparing ON DEMAND and ON COMMIT

Statements in this section are for a dedicated practice schema with appropriate privileges to create MVs, MV logs, jobs, and quota. Do not run test DDL/DML on production schemas. Oracle DDL performs an implicit commit.

### 18.1 Create Source Table and Data

~~~sql
CREATE TABLE lab_sales (
    sale_id   NUMBER PRIMARY KEY,
    region_id NUMBER NOT NULL,
    amount    NUMBER(12,2)
);

INSERT INTO lab_sales VALUES (1, 10, 100);
INSERT INTO lab_sales VALUES (2, 10, 150);
INSERT INTO lab_sales VALUES (3, 20, 200);
COMMIT;
~~~

### 18.2 Create an ON DEMAND MV

~~~sql
CREATE MATERIALIZED VIEW lab_mv_sales_demand
BUILD IMMEDIATE
REFRESH COMPLETE ON DEMAND
AS
SELECT region_id,
       COUNT(*) AS row_count,
       SUM(amount) AS total_amount
FROM lab_sales
GROUP BY region_id;
~~~

Verify:

~~~sql
SELECT *
FROM lab_mv_sales_demand
ORDER BY region_id;
~~~

### 18.3 Modify the Source Table

~~~sql
INSERT INTO lab_sales VALUES (4, 10, 50);
COMMIT;
~~~

Query the ON DEMAND MV:

~~~sql
SELECT *
FROM lab_mv_sales_demand
ORDER BY region_id;
~~~

The MV does not yet reflect the new row because no refresh has been invoked.

### 18.4 Refresh on Demand

~~~sql
BEGIN
    DBMS_MVIEW.REFRESH(
        list   => 'LAB_MV_SALES_DEMAND',
        method => 'C'
    );
END;
/
~~~

Re-query and observe that TOTAL_AMOUNT for REGION_ID=10 increased from 250 to 300.

### 18.5 Create an MV Log for FAST Testing

~~~sql
CREATE MATERIALIZED VIEW LOG ON lab_sales
WITH ROWID, SEQUENCE (region_id, amount)
INCLUDING NEW VALUES;
~~~

Create the test MV:

~~~sql
CREATE MATERIALIZED VIEW lab_mv_sales_fast
BUILD IMMEDIATE
REFRESH FAST ON DEMAND
AS
SELECT region_id,
       COUNT(*) AS row_count,
       COUNT(amount) AS amount_count,
       SUM(amount) AS total_amount
FROM lab_sales
GROUP BY region_id;
~~~

If CREATE or FAST refresh is unsupported under your configuration/version, run DBMS_MVIEW.EXPLAIN_MVIEW to inspect capabilities and messages. Never ignore errors and assume FAST refresh works.

### 18.6 Modify Source and Run FAST Refresh

~~~sql
INSERT INTO lab_sales VALUES (5, 20, 75);
COMMIT;

BEGIN
    DBMS_MVIEW.REFRESH(
        list   => 'LAB_MV_SALES_FAST',
        method => 'F'
    );
END;
/
~~~

Compare MV totals with the source table after refresh.

### 18.7 Test ON COMMIT on an Eligible MV

Run this only after confirming capabilities and understanding your Oracle version's limitations:

~~~sql
CREATE MATERIALIZED VIEW lab_mv_sales_commit
BUILD IMMEDIATE
REFRESH FAST ON COMMIT
AS
SELECT region_id,
       COUNT(*) AS row_count,
       COUNT(amount) AS amount_count,
       SUM(amount) AS total_amount
FROM lab_sales
GROUP BY region_id;
~~~

Test:

~~~sql
INSERT INTO lab_sales VALUES (6, 10, 25);

-- Before COMMIT, the current session has not ended the source transaction.
SELECT *
FROM lab_mv_sales_commit
WHERE region_id = 10;

COMMIT;

-- After a successful COMMIT, inspect the MV.
SELECT *
FROM lab_mv_sales_commit
WHERE region_id = 10;
~~~

Observe COMMIT duration and post-commit results. Do not benchmark latency from a single run; test multiple iterations with representative row counts and concurrency.

### 18.8 Inspect Metadata

~~~sql
SELECT mview_name,
       refresh_mode,
       refresh_method,
       staleness,
       last_refresh_type,
       last_refresh_date
FROM user_mviews
WHERE mview_name LIKE 'LAB_MV_%'
ORDER BY mview_name;
~~~

### 18.9 Clean Up Lab Tables

Drop only MVs, logs, and tables you created in the practice schema once you confirm the data is no longer needed. DDL triggers an implicit commit:

~~~sql
DROP MATERIALIZED VIEW lab_mv_sales_commit;
DROP MATERIALIZED VIEW lab_mv_sales_fast;
DROP MATERIALIZED VIEW lab_mv_sales_demand;
DROP MATERIALIZED VIEW LOG ON lab_sales;
DROP TABLE lab_sales;
~~~

Do not run DROP on objects outside your lab. If an MV failed to create, skip its corresponding DROP rather than swallowing all errors.

## 19. Common Errors and Misconceptions

| Error/Misconception | Reality | How to Handle |
|---|---|---|
| MVs are like standard views | MVs store physical results | Manage storage and refresh |
| ON DEMAND is always fresh | MVs can be stale between refreshes | Monitor freshness and SLAs |
| ON COMMIT is free | Refresh executes on the commit path | Measure commit latency and throughput |
| FAST refresh is always supported | Defining query and log must meet criteria | Use EXPLAIN_MVIEW |
| FORCE is always as fast as FAST | FORCE can fall back to COMPLETE | Monitor LAST_REFRESH_TYPE |
| MV logs have no overhead | Logs increase storage, redo/undo, and DML cost | Measure overall workload |
| ON COMMIT refreshes after every DML statement | Refresh is tied to transaction commit | Understand transaction boundaries |
| Newly created MVs always have data | BUILD DEFERRED starts unpopulated | Perform initial refresh |
| Query rewrite always uses the MV | Optimizer decides based on cost and eligibility | Inspect execution plans |
| STALE is always an error | May be acceptable under SLA | Define freshness clearly |
| ON COMMIT suits all dashboards | Can slow down OLTP commits | Consider ON DEMAND |
| Dropping an MV log doesn't affect other MVs | Multiple MVs can share one log | Check dependencies first |
| ROLLBACK undoes CREATE/ALTER MV | DDL issues implicit commit | Use compensating DDL or recovery plan |
| Job SUCCESS means MV meets freshness SLA | Job may succeed on an overly sparse schedule | Monitor freshness too |

## 20. Selection and Deployment Checklist

Before creating a materialized view:

1. Is the source query heavy enough or frequent enough to justify materializing?
2. Are grouping and measures defined at the right data granularity?
3. How much staleness can reports tolerate?
4. Can ON DEMAND meet SLAs via scheduling or post-batch refreshes?
5. If ON COMMIT is needed, is the defining query eligible and the refresh lightweight enough?
6. Is FAST refresh required, or is COMPLETE sufficient?
7. Does the MV log need PRIMARY KEY, ROWID, SEQUENCE, specific columns, and INCLUDING NEW VALUES?
8. Have EXPLAIN_MVIEW and realistic DML tests been executed?
9. Will log and refresh overhead degrade write throughput?
10. Do multiple MVs depend on the same source table?
11. Is query rewrite needed? Has appropriate QUERY_REWRITE_INTEGRITY been selected?
12. Are refresh schedules, ownership, privileges, and job monitoring in place?
13. Is the MV reconciled against source data using consistent snapshots/batches?
14. Is there a plan for failed refreshes or delayed jobs?
15. Do schema migrations handle DDL implicit commits and MV dependencies?
16. Are STALENESS, LAST_REFRESH_DATE, runtime, and errors monitored?

## 21. Summary

A materialized view stores the results of a query as physical data for reuse in reporting or read workloads. MVs must be refreshed when underlying table data changes.

- **ON DEMAND** refreshes when invoked or scheduled. It decouples refresh work from source transaction commits, enables batching changes, and suits lag-tolerant reports.
- **ON COMMIT** refreshes when a transaction modifying underlying tables commits. It keeps MV data updated at the commit boundary, but can increase commit latency and write workload overhead.
- **FAST** applies incremental changes when the defining query and MV log satisfy eligibility rules.
- **COMPLETE** recomputes the entire defining query.
- **FORCE** attempts FAST, falling back to COMPLETE if infeasible.
- Materialized view logs enable fast refresh at the cost of extra write overhead and storage.
- EXPLAIN_MVIEW, USER_MVIEWS, scheduler history, and execution plans help verify capabilities, state, and operations.
- Query rewrite allows the optimizer to consider using an MV in place of source queries; it depends on configuration, correctness, freshness, and cost.

Choose ON DEMAND or ON COMMIT based on the data lag the business tolerates and the overhead the write path can sustain. An MV is only valuable when its data is fresh enough for its purpose, refreshes operate reliably, and overall read/write/storage costs genuinely outperform querying directly.

# Choosing Between a Table, View, Materialized View, or Direct Query Results

> **Topic:** Database Engine Relational Oracle  
> **Chapter:** Schema Objects  
> **Objective:** Choose the right storage and retrieval form in Oracle: table, view, materialized view, or direct query results. Distinguish physical data from query definitions; understand updatability, data freshness, indexes, refresh, query rewrite, access privileges, and operational costs; and apply a decision process grounded in real requirements.

## 1. Four Ways to Represent Data, Four Different Purposes

When building a reporting or business feature, you often start with a SQL query returning data. The next question is whether to:

- Store the data as a **table** to manage it as business data.
- Encapsulate the SQL logic in a **view** for reuse.
- Pre-store the query results in a **materialized view** for faster reads or analytics.
- Write a **direct query** (SELECT, inline view, or CTE) right where it is used.

All four options return rows and columns, yet they differ in where data is stored, when computation occurs, data freshness, write capability, and synchronization cost.

| Option | Stores Result Data? | When Is It Computed? | Primary Strength |
|---|---|---|---|
| Table | Yes, stores business data | During INSERT/UPDATE/DELETE or data loads | Data management, constraints, indexes, transactions |
| View | Does not store result rows | When a query against the view executes | SQL reuse, logic standardization, column/row control |
| Materialized view | Yes, stores query results | At creation and on each refresh | Fast reads of expensive aggregations or joins |
| Direct query | Not stored as a schema object | Every time the SQL runs | Flexible, local, no intermediate schema object |

An initial rule of thumb:

- If the data is the source of truth needing INSERT/UPDATE/DELETE, use a table.
- If a logical name is needed to reuse a SELECT, consider a view.
- If computation is expensive and a refresh policy is acceptable, consider a materialized view.
- If logic is used in one place or needs ad-hoc flexibility, use a direct SELECT/CTE/inline view.

Do not pick an object based solely on its name or assume views are always slow and materialized views are always fast. Examine workload, freshness, optimizer plans, and maintenance requirements.

## 2. Tables: Authoritative Data Storage

A table is a schema data-storage object. Data is organized in segments and blocks using Oracle's storage structures. A table can have:

- PRIMARY KEY, UNIQUE, FOREIGN KEY, CHECK, and NOT NULL constraints.
- B-tree, bitmap, or function-based indexes depending on workload.
- Triggers, partitioning, compression, and storage attributes.
- Transactional DML, undo, redo, and locking.
- SELECT/INSERT/UPDATE/DELETE privileges granted as needed.

Example:

~~~sql
CREATE TABLE orders (
    order_id NUMBER CONSTRAINT pk_orders PRIMARY KEY,
    customer_id NUMBER NOT NULL,
    order_date TIMESTAMP(6) WITH TIME ZONE NOT NULL,
    status VARCHAR2(20 CHAR) NOT NULL,
    total_amount NUMBER(14,2) NOT NULL,
    CONSTRAINT ck_orders_amount CHECK (total_amount >= 0)
);
~~~

This is where authoritative order data lives. Applications can insert, update, and delete rows according to business rules.

### 2.1. When Is a Table the Right Choice?

Use a table when:

- Data must persist independently of any specific SELECT query.
- Users or systems modify the data.
- Transactions are needed so multiple changes commit or roll back together.
- Constraints are needed to enforce integrity.
- History, state, events, or business snapshots must be stored.
- Data lifecycle, backups, partitioning, retention, and access control must be managed.

A staging table is also a table, though it usually has a different lifecycle than core business tables: load raw data, validate, transform, and move into target tables. Do not use a view instead of a table merely because the initial data originates from a query.

### 2.2. Should Aggregated Data Be Stored in a Table?

Aggregated results can be stored in a table if they are managed by a dedicated pipeline with batches/versions, update rules, and auditing. For example, an end-of-day revenue snapshot table can be an official data product of an ETL pipeline.

However, if aggregated data can be recomputed from source tables and automated synchronization via Oracle policies is desired, a materialized view may fit better. Distinguish application-managed summary tables from materialized views with defining queries and refresh metadata.

## 3. Views: Storing SQL Definitions, Not Result Rows

A view is a schema object containing a query definition. When querying a view, Oracle uses the defining SELECT to produce results at execution time.

Example:

~~~sql
CREATE OR REPLACE VIEW active_orders_v AS
SELECT order_id,
       customer_id,
       order_date,
       total_amount
FROM orders
WHERE status = 'OPEN';
~~~

Read the view:

~~~sql
SELECT order_id, customer_id, total_amount
FROM active_orders_v
WHERE customer_id = :p_customer_id;
~~~

The view does not create a copy of OPEN rows. It reads data from the underlying table per statement read consistency. If an order changes from OPEN to CLOSED and the transaction commits, the next query on the view reflects the newly committed state.

### 3.1. Views Enable Logic Reuse

A view can encapsulate:

- Multi-table JOINs.
- Row-filtering predicates.
- Data normalization expressions.
- Computed columns.
- Categorizations or value mappings.
- A stable interface for applications.

Example:

~~~sql
CREATE OR REPLACE VIEW order_customer_v AS
SELECT o.order_id,
       o.order_date,
       o.status,
       o.total_amount,
       c.customer_id,
       c.customer_name,
       c.region_code
FROM orders o
JOIN customers c
  ON c.customer_id = o.customer_id;
~~~

Multiple applications can share one definition instead of duplicating JOINs and conditions in many places. When logic changes, the owner updates the view through schema change management.

Views can also expose only selected columns—for instance hiding internal columns or letting users read data only within permitted scope. A view is a data interface layer; privileges on views must be designed carefully and do not replace all other security controls.

### 3.2. Views Do Not Guarantee Row Ordering

Do not rely on ordering inside a view definition. When ordered output is required, put ORDER BY in the query consuming the view:

~~~sql
SELECT order_id, order_date
FROM active_orders_v
ORDER BY order_date DESC, order_id DESC;
~~~

This is a general SQL rule: result ordering is guaranteed only when the outermost query includes an appropriate ORDER BY.

### 3.3. Views Do Not Necessarily Slow Queries Down

The optimizer can merge the view query block into the outer query, push predicates down to base tables (predicate pushing), and choose suitable access paths. Therefore, simple views usually act purely as SQL organization without necessarily introducing a separate physical execution step.

However, complex views containing DISTINCT, GROUP BY, analytic functions, UNION, outer joins, or certain expressions can restrict some transformations. Deeply nested views can also make SQL harder to read and optimize without clear structure.

Evaluate using execution plans and runtime statistics rather than assuming views always add overhead.

## 4. Are Views Updatable?

A view can permit INSERT, UPDATE, or DELETE through the view if Oracle can unambiguously map changes back to base table rows and DML rules are satisfied.

### 4.1. Simple Views Can Be Updatable

~~~sql
CREATE OR REPLACE VIEW employees_basic_v AS
SELECT employee_id,
       employee_name,
       department_id,
       salary
FROM employees;
~~~

Update through the view:

~~~sql
UPDATE employees_basic_v
SET salary = salary + 500
WHERE employee_id = 100;
~~~

Oracle updates the corresponding row in EMPLOYEES. The view has no separate data segment receiving changes.

### 4.2. Constructs That Restrict DML Capability

A view may not be automatically updatable, or may allow DML only on specific columns/rows, when it contains:

- Aggregates such as SUM, COUNT, AVG.
- GROUP BY or HAVING.
- DISTINCT.
- Set operators such as UNION/UNION ALL, INTERSECT, or MINUS.
- Certain expressions, subqueries, or complex joins.
- Computed columns instead of direct mappings to table columns.

Example of an aggregate view:

~~~sql
CREATE OR REPLACE VIEW department_salary_v AS
SELECT department_id,
       COUNT(*) AS employee_count,
       AVG(salary) AS average_salary
FROM employees
GROUP BY department_id;
~~~

You cannot simply UPDATE AVERAGE_SALARY and expect Oracle to know how to distribute the new value across individual employees.

### 4.3. Checking Updatability with USER_UPDATABLE_COLUMNS

Oracle provides a dictionary view showing which view columns can be inserted/updated/deleted through the view:

~~~sql
SELECT table_name,
       column_name,
       updatable,
       insertable,
       deletable
FROM user_updatable_columns
WHERE table_name = 'EMPLOYEES_BASIC_V'
ORDER BY column_name;
~~~

Values depend on view structure and Oracle rules. This is a useful metadata check before designing a DML API over a view.

### 4.4. WITH CHECK OPTION

If a view filters STATUS = OPEN, you want to prevent DML through the view from creating or updating a row such that it silently ceases to satisfy the predicate.

~~~sql
CREATE OR REPLACE VIEW open_orders_v AS
SELECT order_id, customer_id, status, total_amount
FROM orders
WHERE status = 'OPEN'
WITH CHECK OPTION CONSTRAINT ck_open_orders_view;
~~~

WITH CHECK OPTION requires rows inserted or updated through the view to continue satisfying the view's condition. It is useful when a view represents a well-defined rule-bound data subset.

It does not turn a view into a separate table and does not replace business constraints on base tables.

### 4.5. WITH READ ONLY

If a view is intended strictly for reading, declare:

~~~sql
CREATE OR REPLACE VIEW order_summary_read_v AS
SELECT customer_id,
       COUNT(*) AS order_count,
       SUM(total_amount) AS total_amount
FROM orders
GROUP BY customer_id
WITH READ ONLY;
~~~

WITH READ ONLY blocks DML through the view. Users can still query results with appropriate privileges.

### 4.6. INSTEAD OF Triggers

For complex views or join views that are not natively updatable, an INSTEAD OF trigger can define how DML translates into changes on base tables.

Illustrative view joining departments and employees:

~~~sql
CREATE OR REPLACE VIEW employee_department_v AS
SELECT e.employee_id,
       e.employee_name,
       e.department_id,
       d.department_name
FROM employees e
JOIN departments d
  ON d.department_id = e.department_id;
~~~

An INSTEAD OF trigger can define how operations on the view are handled:

~~~sql
CREATE OR REPLACE TRIGGER employee_department_v_upd
INSTEAD OF UPDATE ON employee_department_v
FOR EACH ROW
BEGIN
    UPDATE employees
    SET employee_name = :NEW.employee_name,
        department_id = :NEW.department_id
    WHERE employee_id = :OLD.employee_id;
END;
/
~~~

This trigger only illustrates updating certain columns in EMPLOYEES. If DEPARTMENT_NAME also needs updating, define rules for updating DEPARTMENTS explicitly; never assume one joined row maps to a one-to-one update across both tables.

INSTEAD OF triggers increase flexibility but also add responsibility: handling keys, validation, privileges, errors, concurrency, and exact affected row counts.

## 5. Materialized Views: Pre-Storing Query Results

A materialized view (MV) stores the results of a query inside the database. Unlike a standard view, an MV holds physically stored data and must be refreshed to reflect changes from source tables.

Example revenue-by-customer report:

~~~sql
CREATE MATERIALIZED VIEW mv_customer_sales
BUILD IMMEDIATE
REFRESH COMPLETE ON DEMAND
AS
SELECT customer_id,
       COUNT(*) AS order_count,
       SUM(total_amount) AS total_sales
FROM orders
WHERE status = 'CLOSED'
GROUP BY customer_id;
~~~

BUILD IMMEDIATE creates and populates data immediately upon MV creation. REFRESH COMPLETE ON DEMAND means that whenever refreshed on request, Oracle recomputes the entire MV result from its defining query.

Read the MV:

~~~sql
SELECT customer_id, order_count, total_sales
FROM mv_customer_sales
WHERE total_sales > :p_min_sales;
~~~

The query reads materialized data. If ORDERS changes after the last refresh, the MV does not yet reflect those changes.

### 5.1. When Do MVs Fit?

Materialized views are typically valuable when:

- Source queries involve expensive JOINs or GROUP BYs.
- Many users read the same aggregated results.
- Workloads are read-heavy rather than write-heavy.
- Data staleness within a refresh cycle is acceptable.
- Dashboards, reports, or analytical queries need acceleration.
- Storage, refresh costs, and sync schedules can be managed.

MVs do not automatically fit every reporting table. If refresh costs exceed direct query costs, or if data must be up to the second after every commit, the trade-off may not pay off.

### 5.2. MVs Have Their Own Indexes

Because an MV stores physical data, indexes can be created on the MV:

~~~sql
CREATE INDEX ix_mv_customer_sales_total
ON mv_customer_sales(total_sales);
~~~

This index can speed up queries filtering on TOTAL_SALES. MV indexes also consume storage and must be maintained during MV refreshes.

Do not create indexes out of habit; examine predicates, selectivity, and execution plans of queries reading the MV.

## 6. Refreshing Materialized Views

MVs must stay synchronized with source data via refreshes. Oracle supports multiple refresh methods and timing modes.

### 6.1. COMPLETE Refresh

COMPLETE refresh recomputes the entire result set from the defining query. It is simple and works for many MVs, though cost scales with source and result data volume.

~~~sql
BEGIN
    DBMS_MVIEW.REFRESH(
        list           => 'MV_CUSTOMER_SALES',
        method         => 'C'
    );
END;
/
~~~

Use COMPLETE when the query does not meet fast-refresh rules, when large percentages of data change, or when full recomputation cost remains acceptable.

### 6.2. FAST Refresh

FAST refresh applies incremental changes using required change tracking recorded by Oracle, typically involving materialized view logs on master tables and query eligibility.

Example creating an MV log:

~~~sql
CREATE MATERIALIZED VIEW LOG ON orders
WITH ROWID, SEQUENCE (customer_id, status, total_amount)
INCLUDING NEW VALUES;
~~~

Then the MV can be created with FAST refresh if the query satisfies requirements:

~~~sql
CREATE MATERIALIZED VIEW mv_customer_sales_fast
BUILD IMMEDIATE
REFRESH FAST ON DEMAND
AS
SELECT customer_id,
       COUNT(*) AS order_count,
       SUM(total_amount) AS total_sales
FROM orders
WHERE status = 'CLOSED'
GROUP BY customer_id;
~~~

This is an illustrative example, not a guarantee that every version/configuration accepts this exact query and log. FAST refresh eligibility depends on query structure, aggregates, joins, expressions, keys, materialized view logs, and Oracle release.

You can use DBMS_MVIEW.EXPLAIN_MVIEW to inspect refresh capabilities:

~~~sql
-- The MV_CAPABILITIES_TABLE table must be created using the utlxmv.sql script
-- in the appropriate Oracle home before calling the procedure.
DELETE FROM mv_capabilities_table;

BEGIN
    DBMS_MVIEW.EXPLAIN_MVIEW('MV_CUSTOMER_SALES_FAST');
END;
/

SELECT capability_name,
       possible,
       related_text,
       msgtxt
FROM mv_capabilities_table
ORDER BY seq;
~~~

DBMS_MVIEW.EXPLAIN_MVIEW reveals which capabilities are supported and why others are unsupported. Match scripts and package signatures to your running Oracle release.

### 6.3. FORCE Refresh

FORCE lets Oracle choose FAST if possible, otherwise COMPLETE. It is flexible, though it does not guarantee refreshes are always incremental.

Example refresh call:

~~~sql
BEGIN
    DBMS_MVIEW.REFRESH(
        list   => 'MV_CUSTOMER_SALES',
        method => '?'
    );
END;
/
~~~

When predictable runtimes are required, verify actual capabilities and refresh methods rather than assuming FORCE will always stay fast.

### 6.4. ON DEMAND and ON COMMIT

| Mode | Update Timing | Characteristics |
|---|---|---|
| ON DEMAND | When refresh is invoked or a job runs | Proactive timing control, tolerates staleness |
| ON COMMIT | When a transaction modifying source tables commits | MV updates synchronously with commit, increasing commit work |

ON COMMIT can suit small MVs with fast-refreshable queries and strict freshness needs. However, it adds overhead to source write transactions; commits can slow down because MV updates run on the commit path.

ON DEMAND usually fits scheduled reports or lag-tolerant workloads.

### 6.5. Refresh Schedules

Scheduler jobs can automate periodic refreshes. Example job creation:

~~~sql
BEGIN
    DBMS_SCHEDULER.CREATE_JOB(
        job_name        => 'JOB_REFRESH_CUSTOMER_SALES',
        job_type        => 'PLSQL_BLOCK',
        job_action      => q'[
            BEGIN
                DBMS_MVIEW.REFRESH(
                    list   => 'MV_CUSTOMER_SALES',
                    method => 'C'
                );
            END;
        ]',
        start_date      => SYSTIMESTAMP,
        repeat_interval => 'FREQ=HOURLY;INTERVAL=1',
        enabled         => TRUE
    );
END;
/
~~~

Jobs require appropriate owner/privileges, non-overlapping schedules, and error handling. Monitor last successful refresh time, runtime duration, and data lag. Never allow a refresh job to overlap uncontrollably with itself or heavy source batches.

## 7. Data Freshness and Consistency

This is the single most important difference between a view and a materialized view.

- A view reads source tables as of the current SELECT statement's snapshot.
- A materialized view reads data stored at the most recent refresh.
- An ETL/application-managed summary table has freshness governed by its own pipeline.
- A direct query reads a snapshot as of when the statement begins.

Example:

1. 10:00, MV refreshes.
2. 10:05, a new order is inserted into ORDERS and committed.
3. 10:06, querying a view directly sees the committed row under the new snapshot.
4. 10:06, querying the MV does not yet show the order because the MV has not refreshed.
5. 11:00, MV refresh succeeds; querying the MV now reflects that order.

An MV is not an automatically synchronized cache on every change unless explicitly configured for corresponding refreshes. Applications must understand and accept this latency.

### 7.1. Tracking Status and Refresh Timestamps

Inspect metadata:

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

These fields display mode/method, freshness status, and most recent refresh timestamp. Verify exact column names and meanings for your Oracle release.

Common staleness states:

- FRESH: MV reflects source data per Oracle metadata.
- STALE: source data changed and the MV has not yet refreshed accordingly.
- NEEDS_COMPILE or other states: may indicate definitions/metadata needing attention.

Do not rely solely on the status name; check refresh jobs, errors, logs, and defining queries.

## 8. Query Rewrite: Oracle Using an MV Instead of Source Queries

Materialized views can participate in query rewrite: the optimizer can substitute part of a query against base tables with reading an MV if the MV holds enough information to answer the query and rewrite conditions are satisfied.

For example, a user runs:

~~~sql
SELECT customer_id,
       COUNT(*) AS order_count,
       SUM(total_amount) AS total_sales
FROM orders
WHERE status = 'CLOSED'
GROUP BY customer_id;
~~~

If a matching MV exists and query rewrite is enabled and configured appropriately, Oracle can use the MV instead of recomputing from ORDERS.

Enable query rewrite on an MV:

~~~sql
ALTER MATERIALIZED VIEW mv_customer_sales
ENABLE QUERY REWRITE;
~~~

Whether the optimizer rewrites depends on:

- QUERY_REWRITE_ENABLED and related parameters.
- Whether the MV contains sufficient data/columns to answer the query.
- Freshness/staleness and rewrite integrity policies.
- Constraints and metadata trusted by the optimizer.
- SQL structure and MV capabilities.
- Statistics and cost estimates.

Inspect the execution plan to confirm whether the optimizer actually reads the MV. Never assume that merely creating an MV causes all similar queries to use it automatically.

## 9. Direct Queries, Inline Views, and CTEs

When logic is used in only one place or varies per request, write a direct query.

### 9.1. Direct SELECT

~~~sql
SELECT order_id,
       customer_id,
       order_date,
       total_amount
FROM orders
WHERE status = :p_status
  AND order_date >= :p_from_date
ORDER BY order_date DESC, order_id DESC;
~~~

The advantage is keeping logic visible right at the call site without creating schema objects. The drawback is that if multiple applications copy the same logic, definitions can drift apart.

### 9.2. Inline Views

An inline view is a subquery in the FROM clause:

~~~sql
SELECT x.customer_id,
       x.total_sales
FROM (
    SELECT customer_id,
           SUM(total_amount) AS total_sales
    FROM orders
    WHERE status = 'CLOSED'
    GROUP BY customer_id
) x
WHERE x.total_sales >= :p_min_sales;
~~~

Inline views work well for structuring a query into local logical layers. They are not schema views and do not exist after the statement finishes.

### 9.3. Common Table Expressions (CTEs)

The WITH clause names a query block for readability and reuse within the same statement:

~~~sql
WITH customer_sales AS (
    SELECT customer_id,
           SUM(total_amount) AS total_sales
    FROM orders
    WHERE status = 'CLOSED'
    GROUP BY customer_id
),
high_value_customers AS (
    SELECT customer_id, total_sales
    FROM customer_sales
    WHERE total_sales >= :p_min_sales
)
SELECT customer_id, total_sales
FROM high_value_customers
ORDER BY total_sales DESC;
~~~

CTEs break complex logic into named steps. Oracle can inline/merge query blocks or choose another execution strategy; CTEs are not physical temporary tables by default.

### 9.4. When Is a CTE Better Than a View?

CTEs generally fit when:

- The query is used in only one statement.
- Transformation layers carry only local meaning.
- Naming intermediate results improves readability.
- Creating and managing a schema object for one query is unnecessary.

Views fit when multiple queries or multiple applications need the same stable logic. For widely reused logic, views reduce the risk of each consumer maintaining a divergent variant.

## 10. Comparing Costs and DML Capabilities

| Criterion | Table | View | Materialized View | SELECT/CTE |
|---|---|---|---|---|
| Stores result rows | Yes | No | Yes | No |
| Stores query definition | Not its primary purpose | Yes | Yes | Within the SQL statement |
| Data freshness | Tracks DML on table | Reads current source tables | As of last refresh | Per statement snapshot |
| Direct DML | Yes | Depends on updatability/triggers | Restricted, depends on type and config | DML on underlying targets |
| Dedicated indexes | Yes | No direct indexes on standard views | Yes | No |
| Dedicated constraints | Yes | Not like an independent table | Some metadata/constraints by type, does not replace source | No |
| Refresh | No | No | Yes | No |
| Query rewrite | Not applicable as MV | Not an MV rewrite target | Possible | Optimizer optimizes query directly |
| Storage | Data and indexes | Definition/metadata | Results and indexes | No schema object stored |
| Maintenance | DML/schema/backup | Definition/dependency changes | Refresh/logs/jobs/storage | Maintaining SQL in code |

Note: while an MV stores query results, it should not be treated like a standard business table freely updated in arbitrary ways. MV DML behavior depends on definition, refresh method, and Oracle release; MV contents are normally managed through refresh.

## 11. Decision Tree

~~~text
Is this data the source of truth to store and update?
                    |
             +------+------+
             |             |
            Yes            No
             |             |
           TABLE      Need to reuse SQL
                      logic in multiple places?
                           |
                     +-----+-----+
                     |           |
                    Yes          No
                     |           |
                    VIEW     Need to pre-store results
                             to speed up reads?
                                  |
                            +-----+-----+
                            |           |
                           Yes          No
                            |           |
                    MATERIALIZED     SELECT / CTE /
                       VIEW          INLINE VIEW
                            |
                  Can refresh lag be tolerated?
                            |
                  Evaluate FAST/COMPLETE,
                  ON DEMAND/ON COMMIT,
                  storage, and query rewrite
~~~

This decision tree is only a starting point. A system often combines multiple types: source tables, views as logical interfaces, materialized views for reports, and CTEs for local query steps.

## 12. Example: Designing an Order Reporting Feature

Suppose an application has three needs:

1. An order details screen needing current status.
2. Multiple features sharing the same order-customer JOIN.
3. A dashboard displaying 12-month revenue per customer, updated hourly.

A suitable design might use:

### 12.1. Tables for Authoritative Data

ORDERS and CUSTOMERS hold the source of truth with appropriate PK/FK/constraints/indexes.

### 12.2. View for Shared Detail Interface

~~~sql
CREATE OR REPLACE VIEW order_detail_v AS
SELECT o.order_id,
       o.order_date,
       o.status,
       o.total_amount,
       c.customer_id,
       c.customer_name,
       c.region_code
FROM orders o
JOIN customers c
  ON c.customer_id = o.customer_id;
~~~

Features share one JOIN definition and consistent column names.

### 12.3. Materialized View for the Dashboard

~~~sql
CREATE MATERIALIZED VIEW mv_customer_month_sales
BUILD IMMEDIATE
REFRESH COMPLETE ON DEMAND
AS
SELECT customer_id,
       TRUNC(order_date, 'MM') AS sales_month,
       COUNT(*) AS order_count,
       SUM(total_amount) AS total_sales
FROM orders
WHERE status = 'CLOSED'
GROUP BY customer_id, TRUNC(order_date, 'MM');
~~~

A refresh job runs hourly. The dashboard tolerates lag up to the refresh interval and displays the latest refresh timestamp.

### 12.4. CTE for an Ad-Hoc Analytical Report

If a one-off report analyzes top customers within a user-selected date range, a CTE works well without creating a new view:

~~~sql
WITH sales_by_customer AS (
    SELECT customer_id,
           SUM(total_amount) AS total_sales
    FROM orders
    WHERE status = 'CLOSED'
      AND order_date >= :p_from_date
      AND order_date < :p_to_date
    GROUP BY customer_id
)
SELECT customer_id, total_sales
FROM sales_by_customer
WHERE total_sales >= :p_min_sales
ORDER BY total_sales DESC;
~~~

Each construct serves a clear need; there is no reason to force every piece of logic into one object type.

## 13. Security and Access Privileges

Tables, views, and materialized views are all schema objects, yet how privileges and data are exposed requires careful consideration.

### 13.1. Views as a Data Publication Layer

For example, exposing only selected columns:

~~~sql
CREATE OR REPLACE VIEW customer_public_v AS
SELECT customer_id,
       customer_name,
       region_code
FROM customers
WHERE customer_status = 'ACTIVE';
~~~

SELECT on the view can be granted to an appropriate role instead of granting direct read access on the entire base table:

~~~sql
GRANT SELECT ON customer_public_v TO reporting_role;
~~~

Views help restrict columns and rows in the data interface, but you must evaluate underlying object privileges, view owner, definer/invoker rights of calling PL/SQL, VPD/RLS, and alternate access paths. Never rely on a view as the sole security measure for sensitive data.

### 13.2. MVs Are Physical Copies of Data

An MV stores results as of refresh time. When granted read privilege on an MV, users can read the materialized data without directly querying source tables in each statement, depending on privilege and refresh-owner design.

Protect all of the following:

- Data inside the MV.
- Refresh privileges and source table access.
- Job credentials/owners.
- Logs or intermediate staging tables.
- Refresh policies after privilege or sensitive data changes.

If a view filters rows per user while an MV stores a broader dataset, ensure queries reading the MV still enforce the right privilege boundaries. Never materialize multi-tenant data and grant direct read access without proper tenant isolation mechanisms.

## 14. Dependencies and Schema Changes

Views and MVs depend on tables, columns, functions, and other objects in their query definitions.

If a source column is renamed or dropped, a view can become INVALID and require recompilation or definition updates. Check status:

~~~sql
SELECT object_name,
       object_type,
       status
FROM user_objects
WHERE object_type IN ('VIEW', 'MATERIALIZED VIEW')
ORDER BY object_type, object_name;
~~~

Inspect view compile errors:

~~~sql
SELECT name,
       type,
       line,
       position,
       text
FROM user_errors
WHERE type = 'VIEW'
ORDER BY name, sequence;
~~~

When modifying schemas, review dependencies and deploy in order: tables/columns, views, MVs, triggers, packages, grants, and dependent applications.

Do not assume CREATE OR REPLACE VIEW preserves all behavior or stays compatible with every consumer if column order or structure changes.

## 15. Monitoring Materialized Views

Useful metadata views:

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

Inspect refresh jobs:

~~~sql
SELECT job_name,
       enabled,
       state,
       last_start_date,
       last_run_duration,
       next_run_date
FROM user_scheduler_jobs
WHERE job_name LIKE 'JOB_REFRESH_%'
ORDER BY job_name;
~~~

Inspect job history:

~~~sql
SELECT log_date,
       job_name,
       status,
       run_duration,
       error#,
       additional_info
FROM user_scheduler_job_run_details
WHERE job_name = 'JOB_REFRESH_CUSTOMER_SALES'
ORDER BY log_date DESC;
~~~

Monitor:

- Whether the most recent refresh succeeded.
- Whether the MV is FRESH or STALE.
- Refresh duration and schedule lag.
- Volume of changes on source tables.
- MV and index storage growth.
- Whether refreshes contend with source batch DML.
- Whether jobs overlap or fail repeatedly.

Do not monitor only read queries; refreshes themselves are a database workload requiring capacity and operational scheduling.

## 16. Common Pitfalls

| Pitfall | Consequence | Resolution |
|---|---|---|
| Using a view expecting pre-stored results | Queries still read/compute from source tables | Use an MV if materialization is needed |
| Using an MV when real-time data is required | Users read stale data | Use a view/table or an appropriate refresh strategy |
| Assuming views are always slower than tables | Ignores optimizer query transformations | Compare execution plans and runtime metrics |
| Creating an MV without a refresh plan | Results grow increasingly stale | Choose ON DEMAND/ON COMMIT and monitor |
| Assuming FAST refresh always works | Creation/refresh fails or requires complete | Run EXPLAIN_MVIEW and check logs/capabilities |
| Using ON COMMIT for large MVs | Source DML commits incur heavy overhead | Evaluate ON DEMAND or alternative designs |
| Treating CTEs as physical temp tables | Misunderstands storage and lifetime | CTEs live only for a single statement |
| Assuming all views are updatable | DML errors or ambiguous mappings | Check USER_UPDATABLE_COLUMNS and triggers |
| Using DISTINCT/GROUP BY and expecting automatic UPDATE mapping | No unambiguous DML mapping exists | Use base tables, INSTEAD OF triggers, or dedicated APIs |
| Relying on views as the sole security layer | Other access paths may remain open | Design grants, VPD/RLS, and system privileges |
| Indexing MVs without checking queries | Increases refresh and storage cost | Index according to actual predicates |
| Skipping dependency checks on table changes | Views/MVs turn INVALID or break silently | Check USER_OBJECTS/USER_ERRORS and deploy in order |

## 17. Lab Exercises on a Practice Schema

The examples below use dedicated practice tables. Run only in an authorized schema and never alter production business tables.

### 17.1. Create the Source Table

~~~sql
CREATE TABLE lab_sales (
    sale_id NUMBER CONSTRAINT pk_lab_sales PRIMARY KEY,
    customer_id NUMBER NOT NULL,
    sale_date DATE NOT NULL,
    status VARCHAR2(20 CHAR) NOT NULL,
    amount NUMBER(12,2) NOT NULL
);

INSERT INTO lab_sales VALUES (1, 10, DATE '2026-01-10', 'CLOSED', 100);
INSERT INTO lab_sales VALUES (2, 10, DATE '2026-01-15', 'CLOSED', 150);
INSERT INTO lab_sales VALUES (3, 20, DATE '2026-01-20', 'OPEN', 200);
COMMIT;
~~~

### 17.2. Create a View

~~~sql
CREATE OR REPLACE VIEW lab_closed_sales_v AS
SELECT sale_id, customer_id, sale_date, amount
FROM lab_sales
WHERE status = 'CLOSED';
~~~

Query:

~~~sql
SELECT *
FROM lab_closed_sales_v
ORDER BY sale_id;
~~~

Modify a source row and commit:

~~~sql
UPDATE lab_sales
SET status = 'OPEN'
WHERE sale_id = 1;

COMMIT;
~~~

Subsequent queries against the view no longer show sale_id 1 because the view recomputes from the source table.

### 17.3. Create a Materialized View

~~~sql
CREATE MATERIALIZED VIEW lab_customer_sales_mv
BUILD IMMEDIATE
REFRESH COMPLETE ON DEMAND
AS
SELECT customer_id,
       COUNT(*) AS sale_count,
       SUM(amount) AS total_amount
FROM lab_sales
WHERE status = 'CLOSED'
GROUP BY customer_id;
~~~

Query results:

~~~sql
SELECT *
FROM lab_customer_sales_mv
ORDER BY customer_id;
~~~

Modify source data again and COMMIT:

~~~sql
INSERT INTO lab_sales VALUES (
    4, 10, DATE '2026-02-01', 'CLOSED', 250
);
COMMIT;
~~~

The direct view reflects the new row. The MV retains the old result until refreshed:

~~~sql
BEGIN
    DBMS_MVIEW.REFRESH(
        list   => 'LAB_CUSTOMER_SALES_MV',
        method => 'C'
    );
END;
/
~~~

After refresh, querying the MV reflects the updated total.

### 17.4. Use a CTE for Local Results

~~~sql
WITH customer_totals AS (
    SELECT customer_id,
           SUM(amount) AS total_amount
    FROM lab_sales
    WHERE status = 'CLOSED'
    GROUP BY customer_id
)
SELECT customer_id, total_amount
FROM customer_totals
WHERE total_amount >= 200;
~~~

The CTE exists only for this statement; no CUSTOMER_TOTALS object is created in the schema.

### 17.5. Clean Up Lab Objects

Once finished and data is no longer needed:

~~~sql
DROP MATERIALIZED VIEW lab_customer_sales_mv;
DROP VIEW lab_closed_sales_v;
DROP TABLE lab_sales PURGE;
~~~

Drop only lab objects you created. Oracle DDL performs an implicit commit in normal contexts; do not run DROP while practice transactions remain open.

## 18. Selection Workflow Before Creating an Object

Before creating a table/view/MV, answer in order:

1. **Is the data the source of truth?** If yes, store it in a table with explicit keys and constraints.
2. **Will the logic be reused in multiple places?** If yes, consider a view.
3. **Are results expensive to compute and frequently read?** If yes, consider a materialized view.
4. **What is the maximum acceptable data lag?** If real-time freshness is required, a view usually fits better than an ON DEMAND MV.
5. **Can FAST refresh be supported?** Check the query, logs, and EXPLAIN_MVIEW.
6. **Is DML through a view needed?** Assess updatability, CHECK OPTION, or INSTEAD OF triggers.
7. **Is the logic used in a single statement?** A CTE or inline view may suffice.
8. **Are dedicated indexes needed on the results?** Tables/MVs can have indexes; standard views/CTEs do not have their own index segments.
9. **Who reads and refreshes?** Design grants, owners, jobs, and data protection.
10. **Who owns freshness and dependencies?** Establish refresh schedules, monitoring, and schema deployment workflows.

## 19. Core Takeaways

- **Tables** store authoritative data and support DML, constraints, indexes, and transactions.
- **Views** store SQL definitions rather than result rows; querying a view reads source data under the current snapshot.
- **Materialized views** pre-store query results; they require a refresh strategy and accept data freshness governed by that policy.
- **SELECT/CTE/inline views** handle statement-local logic without creating persistent schema objects.
- Views are not slow by default; the optimizer can merge views and push predicates down to source tables.
- Views are updatable only when Oracle can map DML cleanly; aggregates, GROUP BY, DISTINCT, and complex constructs restrict DML.
- WITH CHECK OPTION ensures DML through a view keeps rows satisfying the view's predicate; WITH READ ONLY forbids DML through the view.
- INSTEAD OF triggers can define DML on complex views at the cost of extra implementation responsibility.
- MVs can use COMPLETE, FAST, or FORCE refresh; FAST eligibility depends on query structure and materialized view logs.
- ON COMMIT lowers latency at the expense of source transaction commit cost; ON DEMAND provides proactive refresh scheduling.
- Query rewrite lets the optimizer substitute MVs for source queries when eligible; verify via execution plans.
- The right choice depends on source-of-truth ownership, freshness requirements, read/write ratio, query cost, storage, privileges, and operational overhead.

### Recommended Oracle Documentation

- [Oracle Database SQL Language Reference](https://docs.oracle.com/en/database/) — CREATE VIEW, CREATE MATERIALIZED VIEW, SELECT, WITH clause, and DML through views.
- [Oracle Database Data Warehousing Guide](https://docs.oracle.com/en/database/) — Materialized views, refresh, and query rewrite.
- [Oracle Database Administrator's Guide](https://docs.oracle.com/en/database/) — Managing tables, views, indexes, and schema objects.
- [Oracle Database PL/SQL Packages and Types Reference](https://docs.oracle.com/en/database/) — DBMS_MVIEW and DBMS_SCHEDULER.
- [Oracle Database Reference](https://docs.oracle.com/en/database/) — USER_MVIEWS, USER_UPDATABLE_COLUMNS, USER_OBJECTS, and scheduler views.

Updatability, fast refresh, query rewrite, and certain syntax limits depend on Oracle version and query definition. Verify metadata/capabilities on your actual release, inspect execution plans, and measure both read cost and refresh cost before choosing a production design.

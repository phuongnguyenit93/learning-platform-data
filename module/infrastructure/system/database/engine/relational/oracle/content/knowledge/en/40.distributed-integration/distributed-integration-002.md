# Predicate Pushdown, Reducing Data Transfer, and Reading Distributed Query Plans

In a distributed Oracle system, a single SQL statement can access tables in the current database and tables in another database via a database link. When executing the query, Oracle splits the statement into parts that can run at each site. The remote database executes the SQL portion sent to it, returns results over the network, and then the local database continues joining, filtering, aggregating, or processing the remainder before returning data to the application.

Therefore, distributed query performance does not depend solely on indexes or the execution plan at a single database. It also depends on **the number of rows sent over the network, the number of columns transferred, the number of remote calls, where joins/aggregations are executed, network latency, optimizer statistics, and the load on each database**.

The most important tuning principle is to let data be filtered and processed where it is stored, and then transfer only the necessary result set back to the query execution site. Oracle calls a key technique for this goal **collocated inline views**: grouping tables located on the same remote database into an inline view so the remote site performs joins and filters locally. When needed, `NO_MERGE` can be used to preserve inline view boundaries and `DRIVING_SITE` can specify the query execution site. All changes must be verified with execution plans and actual metrics.

This lesson belongs to the **Distributed Integration** group of Database Engine Relational Oracle. The content focuses on predicate pushdown, projection pushdown, reducing data transfer, collocated inline views, cost-based optimization, hints, database links, and reading distributed query execution plans.

After this lesson, you will be able to:

- Explain how Oracle splits a distributed query into local and remote SQL.
- Identify network costs in a query using a database link.
- Push `WHERE` conditions down to the remote site when they can be evaluated there.
- Select only necessary columns instead of `SELECT *`.
- Execute joins and aggregations at the remote site using collocated inline views.
- Use `NO_MERGE` to preserve an inline view when there is a clear tuning reason.
- Use `DRIVING_SITE` to control the execution site when appropriate.
- Understand the role of optimizer statistics in both local and remote databases.
- Read the `REMOTE` operation and the SQL sent to the remote database in the execution plan.
- Compare estimated rows/bytes against execution metrics and SQL*Net statistics.
- Distinguish between `EXPLAIN PLAN` and the actual execution plan.
- Recognize cases where predicates cannot or should not be pushed down to remote.
- Evaluate the impact of database links, bind variables, NLS, and network latency.
- Establish a before/after benchmark process when rewriting distributed SQL.

> **Example Scope:** Examples mainly follow Oracle Database 19c. Assume the current database is LOCALDB and the remote database is accessed via database link SALES_LINK. Schema, table, column, service, and link names are illustrative only. Replace them with actual objects in your lab environment. Tuning distributed queries requires comparing result data, execution plans, rows/bytes transferred, and execution time; do not draw conclusions from a single hint or cost alone.

## 1. How Do Distributed Queries Work?

A distributed query is a SQL statement referencing data across multiple databases. Oracle uses a database link to create a remote session and send SQL to the remote database.

### 1.1. Simple Example

~~~sql
SELECT
    employee_id,
    first_name,
    salary
FROM employees@sales_link
WHERE department_id = 50;
~~~

In this example:

- The SQL is issued from LOCALDB.
- EMPLOYEES resides in the remote database.
- SALES_LINK provides the connection to the remote database.
- The remote database can filter `DEPARTMENT_ID = 50`.
- Only the resulting rows are sent back to the local site.

If the remote database has a suitable index, the remote optimizer can use the index to locate matching rows before transferring results.

### 1.2. Multi-Site Query

~~~sql
SELECT
    l.region_name,
    r.customer_name,
    r.total_amount
FROM local_regions l
JOIN (
    SELECT
        c.region_id,
        c.customer_name,
        SUM(o.amount) AS total_amount
    FROM customers@sales_link c
    JOIN orders@sales_link o
      ON o.customer_id = c.customer_id
    WHERE o.order_date >= DATE '2026-01-01'
      AND o.order_date <  DATE '2026-02-01'
    GROUP BY c.region_id, c.customer_name
) r
  ON r.region_id = l.region_id
WHERE l.is_active = 'Y';
~~~

The remote database holds CUSTOMERS and ORDERS. The local database holds LOCAL_REGIONS. Oracle can:

1. Send SQL to SALES_LINK so the remote site joins CUSTOMERS with ORDERS, filters by date, and aggregates.
2. Receive the reduced result set.
3. Join that result with LOCAL_REGIONS at the local site.

This is usually a good approach because the two remote tables are processed at the same database, and the data returned is already reduced.

### 1.3. Roles of Local and Remote Sites

| Term | Meaning |
| --- | --- |
| Local site | The database where the client issues the SQL statement |
| Remote site | The database accessed via a database link |
| Remote query | The SQL portion sent to the remote database |
| Query execution site | The site performing the main processing of the distributed query |
| Database link | A connection allowing access to objects in another database |
| Collocated tables | Tables residing in the same database |

The local site does not necessarily have to perform every join. The optimizer can push processing portions to the remote site or choose the remote site as the query execution site.

### 1.4. A Remote Session Can Be Reused

When a local user session accesses a database link for the first time, Oracle creates a corresponding remote session. The remote connection/session can persist for the duration of the local user session unless explicitly closed or the local session ends.

Thus, a distributed query does not always create a new TCP connection for every remote table read. Still, every remote call and data exchange carries a cost.

## 2. Why Are Distributed Queries Prone to Being Slow?

A local query can read data from local memory or storage. A distributed query must also send requests and data over the network.

### 2.1. Cost Components

Total execution time can be affected by:

- SQL parse and optimization time on the local database.
- Remote SQL parse and optimization time.
- CPU and I/O at the local database.
- CPU and I/O at the remote database.
- Network round trips.
- Bytes transferred from remote to local.
- Bytes transferred from local to remote.
- Database link latency.
- Time spent waiting for remote database processing.
- Remaining joins, sorts, group bys, or filters at the local site.

A query can be very fast on the remote database yet still slow locally because millions of rows are transferred over the network before local filtering.

### 2.2. Data Transfer Cost

Suppose a remote table has 10 million rows, averaging 200 bytes per row. If local only needs 5,000 rows and 3 columns, transferring the entire table is a massive waste.

Illustrative example:

| Approach | Rows Transferred | Average Row Size | Approximate Data |
| --- | ---: | ---: | ---: |
| Fetch entire remote table | 10,000,000 | 200 bytes | 2,000 MB |
| Filter at remote | 5,000 | 200 bytes | 1 MB |
| Filter and select only 3 columns | 5,000 | 40 bytes | 0.2 MB |

Figures are illustrative only. Actual sizes depend on data types, encoding, protocol, and fetch behavior.

### 2.3. Network Round Trips

Beyond bytes, the number of round trips also matters. If an application or execution plan performs many small remote calls, total time can be dominated by network latency.

Example:

- One remote query returns 1 million rows in a few fetch batches.
- Another plan invokes a remote query repeatedly thousands of times, fetching one row per call.

Even with equivalent total bytes, the plan with many round trips typically has much higher latency.

### 2.4. Joining at the Wrong Site

If a large table resides on the remote side but the local site pulls its data over before joining with another table, the transferred data volume can be huge.

Conversely, if the remote site only has a small table and the local site holds most of the data to process, pulling the small table to local may make more sense. The goal is not always to run joins at remote, but to choose the site that minimizes total cost.

## 3. What Is Predicate Pushdown?

Predicate pushdown means moving filtering conditions close to where the data is stored to eliminate unnecessary rows before network transfer.

### 3.1. Unoptimized Example

~~~sql
SELECT
    customer_id,
    customer_name,
    status,
    region_id
FROM customers@sales_link;
~~~

If local only needs ACTIVE customers in region 10, fetching the entire table and filtering locally transfers a lot of unnecessary data.

### 3.2. Putting Conditions into the Remote Query

~~~sql
SELECT
    customer_id,
    customer_name,
    status,
    region_id
FROM customers@sales_link
WHERE status = 'ACTIVE'
  AND region_id = 10;
~~~

Oracle can send the predicates to the remote database. The remote optimizer filters rows before returning results.

### 3.3. Filtering by Date/Time

Prefer range predicates on date columns:

~~~sql
SELECT
    order_id,
    customer_id,
    amount
FROM orders@sales_link
WHERE order_date >= DATE '2026-01-01'
  AND order_date <  DATE '2026-02-01';
~~~

Half-open intervals cover the entire last day without relying on `23:59:59`. They also avoid wrapping the column with `TRUNC` in the predicate, allowing the remote optimizer to use index/range access if a suitable index exists.

### 3.4. Avoid Wrapping Columns in Functions Unnecessarily

Example:

~~~sql
WHERE TRUNC(order_date) = DATE '2026-01-15'
~~~

This style can hinder using a normal index on `ORDER_DATE`. Rewrite as:

~~~sql
WHERE order_date >= DATE '2026-01-15'
  AND order_date <  DATE '2026-01-16'
~~~

Predicate pushdown and index access are related but distinct issues:

- Predicate pushdown decides which site runs the filter.
- Index access decides how the remote database finds matching rows.

A predicate pushed down to remote may still result in a full scan if the optimizer considers that the better plan.

### 3.5. Conditions Combining Local and Remote

Suppose conditions depend only on remote columns:

~~~sql
WHERE c.status = 'ACTIVE'
  AND o.order_date >= :from_date
~~~

Both conditions can be applied at the remote site because all columns reside remotely.

If a condition depends on a local table:

~~~sql
WHERE c.region_id = l.region_id
  AND l.enabled = 'Y'
~~~

Conditions involving `LOCAL_REGIONS` cannot be evaluated independently on the remote site if remote lacks that data. The optimizer may have to send a set of keys from local to remote, pull data back to local, or choose another execution site.

## 4. Projection Pushdown: Selecting Only Needed Columns

Projection pushdown means selecting only the columns needed in the final output or in joins/filters/aggregations.

### 4.1. Avoid SELECT *

Do not write:

~~~sql
SELECT *
FROM orders@sales_link
WHERE order_date >= DATE '2026-01-01';
~~~

If the application only needs `ORDER_ID`, `CUSTOMER_ID`, and `AMOUNT`:

~~~sql
SELECT
    order_id,
    customer_id,
    amount
FROM orders@sales_link
WHERE order_date >= DATE '2026-01-01';
~~~

`CLOB`, `BLOB`, `XMLTYPE`, or large text columns can drastically inflate transferred bytes. Do not select those columns if the query does not need them.

### 4.2. Columns Used for Joins/Filters Must Still Be Retained

If the outer query needs to join on `CUSTOMER_ID`, the remote inline view must return `CUSTOMER_ID` even if that column does not appear in the final output.

~~~sql
SELECT
    r.customer_name,
    l.region_name
FROM (
    SELECT
        customer_id,
        customer_name,
        region_id
    FROM customers@sales_link
    WHERE status = 'ACTIVE'
) r
JOIN local_regions l
  ON l.region_id = r.region_id;
~~~

Do not drop join key columns when optimizing projection.

### 4.3. Projection Reduces Bytes, Not Necessarily Row Count

If 1 million rows are still returned but 10 large columns are dropped, network bytes can drop significantly. Therefore, monitor all of:

- Number of rows returned.
- Number of columns.
- Column data width.
- Bytes transferred.

## 5. Reducing Data with Aggregation, DISTINCT, and Semi-Joins

Beyond `WHERE` and column lists, data can be reduced by performing aggregations at the remote site.

### 5.1. Aggregating at Remote

Suboptimal or unverified:

~~~sql
SELECT
    region_id,
    SUM(amount)
FROM orders@sales_link
WHERE order_date >= DATE '2026-01-01'
  AND order_date <  DATE '2026-02-01'
GROUP BY region_id;
~~~

The optimizer may already push `GROUP BY` down to remote. However, when queries grow complex, inspect the execution plan rather than assuming.

If you need to explicitly write the remote query block:

~~~sql
SELECT
    r.region_id,
    r.total_amount
FROM (
    SELECT
        region_id,
        SUM(amount) AS total_amount
    FROM orders@sales_link
    WHERE order_date >= DATE '2026-01-01'
      AND order_date <  DATE '2026-02-01'
    GROUP BY region_id
) r;
~~~

The remote site only needs to return one row per region rather than every order.

### 5.2. DISTINCT at the Appropriate Place

If local only needs a list of distinct customer IDs:

~~~sql
SELECT customer_id
FROM (
    SELECT DISTINCT customer_id
    FROM orders@sales_link
    WHERE order_date >= DATE '2026-01-01'
);
~~~

`DISTINCT` at remote can sharply reduce transferred rows. However, if individual orders must be preserved or `DISTINCT` semantics depend on data types/collation, ensure equivalent results.

### 5.3. EXISTS and Semi-Joins

When only checking existence, avoid pulling all data from the child table:

~~~sql
SELECT c.customer_id, c.customer_name
FROM customers@sales_link c
WHERE c.status = 'ACTIVE'
  AND EXISTS (
      SELECT 1
      FROM orders@sales_link o
      WHERE o.customer_id = c.customer_id
        AND o.order_date >= DATE '2026-01-01'
  );
~~~

Since both tables are on the same remote site, Oracle has the opportunity to execute a semi-join at the remote database. The execution plan should confirm the operation is actually pushed down.

### 5.4. COUNT Instead of Transferring Rows

If the application only needs a count:

~~~sql
SELECT COUNT(*)
FROM orders@sales_link
WHERE order_date >= DATE '2026-01-01'
  AND order_date <  DATE '2026-02-01';
~~~

The remote database can compute `COUNT` and return just one value instead of transferring all order rows.

### 5.5. Top-N and Pagination

If only the top 20 results are needed:

~~~sql
SELECT
    order_id,
    order_date,
    amount
FROM orders@sales_link
WHERE status = 'OPEN'
ORDER BY order_date DESC, order_id DESC
FETCH FIRST 20 ROWS ONLY;
~~~

Placing `ORDER BY` and `FETCH FIRST` inside the remote query block helps the remote site return only the needed rows. Use a deterministic ordering, such as adding `ORDER_ID` as a tie-breaker, so results are stable.

For multi-page pagination, keyset pagination often avoids the high cost of `OFFSET`:

~~~sql
SELECT
    order_id,
    order_date,
    amount
FROM orders@sales_link
WHERE status = 'OPEN'
  AND (
       order_date < :last_order_date
       OR (
           order_date = :last_order_date
           AND order_id < :last_order_id
       )
  )
ORDER BY order_date DESC, order_id DESC
FETCH FIRST 20 ROWS ONLY;
~~~

Only use this approach when the ordering and comparison conditions match business requirements.

## 6. Collocated Inline Views

Oracle recommends grouping tables residing on the same database into an inline view so the remote database executes joins and filters locally. This technique is called a collocated inline view.

### 6.1. What Does Collocated Mean?

Two or more tables are collocated when they reside in the same database.

Example:

- ORDERS resides in the SALES database.
- CUSTOMERS also resides in the SALES database.
- LOCAL_CAMPAIGN_RULES resides in LOCALDB.

ORDERS and CUSTOMERS can be joined at the SALES database. LOCAL_CAMPAIGN_RULES is not collocated with those two tables.

### 6.2. What Is an Inline View?

An inline view is a `SELECT` inside a `FROM` clause treated like a table in the parent query.

~~~sql
SELECT x.customer_id, x.total_amount
FROM (
    SELECT customer_id, SUM(amount) AS total_amount
    FROM orders@sales_link
    GROUP BY customer_id
) x;
~~~

### 6.3. What Is a Collocated Inline View?

An inline view that accesses only tables belonging to the same remote database. The remote database can join, filter, group, and return a reduced result.

### 6.4. Example with Multiple Remote Tables and One Local Table

Suppose:

- SALES_LINK points to the remote database.
- ORDERS and CUSTOMERS are both on remote.
- LOCAL_CAMPAIGN_RULES is on local.
- Each `CAMPAIGN_CODE`/`REGION_ID` pair in the local table is unique.

Query:

~~~sql
SELECT
    r.segment,
    SUM(r.order_count) AS order_count,
    SUM(r.revenue) AS revenue
FROM (
    SELECT /*+ NO_MERGE */
        c.region_id,
        c.segment,
        COUNT(*) AS order_count,
        SUM(o.amount) AS revenue
    FROM orders@sales_link o
    JOIN customers@sales_link c
      ON c.customer_id = o.customer_id
    WHERE o.order_date >= :from_date
      AND o.order_date <  :to_date
      AND c.status = 'ACTIVE'
    GROUP BY c.region_id, c.segment
) r
JOIN (
    SELECT DISTINCT region_id
    FROM local_campaign_rules
    WHERE campaign_code = :campaign_code
      AND enabled = 'Y'
) p
  ON p.region_id = r.region_id
GROUP BY r.segment;
~~~

The contents of the first inline view can be executed at the SALES database:

1. Filter ORDERS by date.
2. Filter CUSTOMERS by status.
3. Join the two remote tables on `CUSTOMER_ID`.
4. Aggregate by `REGION_ID` and `SEGMENT`.
5. Return the reduced result to local.

The local site only needs to join that result with the allowed region list.

The `DISTINCT` on `LOCAL_CAMPAIGN_RULES` prevents multiplying results if a region has multiple duplicate rules for the same campaign. If business logic allows multiple rule rows and requires preserving multiplicity, redesign the join/aggregation to preserve exact semantics.

### 6.5. Why Is This Technique Effective?

Suppose ORDERS has 50 million rows and CUSTOMERS has 2 million rows, but after filtering and grouping only 30 region/segment combinations remain. The remote database returns just a few dozen aggregated rows to local instead of millions of order/customer rows.

Benefits come from:

- Fewer rows over the network.
- Fewer bytes over the network.
- Fewer remote accesses.
- Utilizing CPU, memory, and indexes at the remote site.
- Reducing join/sort/aggregate workload at the local site.

### 6.6. The Optimizer Can Rewrite Automatically

Oracle's cost-based optimizer can automatically rewrite many distributed queries to leverage collocated inline views. Manually writing inline views is not always necessary.

However, Oracle 19c documentation notes that CBO distributed query rewrite does not perform well in certain cases involving aggregates, subqueries, or complex SQL. In those cases, you can write a collocated inline view and use `NO_MERGE` to prevent the view from being merged into a non-collocated query block.

## 7. NO_MERGE Hint

`NO_MERGE` instructs the optimizer not to merge the specified inline view into the parent query block.

### 7.1. Why Is NO_MERGE Needed?

When writing a collocated inline view, the goal is to keep tables from the same remote site inside one query block so the remote database processes them together.

If the optimizer merges the view into the parent query, the query may turn into a more complex distributed statement and lose the benefit of grouping the remote tables.

### 7.2. Using the Inline View Alias

~~~sql
SELECT /*+ NO_MERGE(r) */
    l.region_name,
    r.total_amount
FROM local_regions l
JOIN (
    SELECT
        region_id,
        SUM(amount) AS total_amount
    FROM orders@sales_link
    WHERE order_date >= :from_date
      AND order_date <  :to_date
    GROUP BY region_id
) r
  ON r.region_id = l.region_id;
~~~

The hint is placed in the parent query block and references alias `R` of the inline view.

### 7.3. Placing the Hint Inside the Inline View Query Block

~~~sql
SELECT
    l.region_name,
    r.total_amount
FROM local_regions l
JOIN (
    SELECT /*+ NO_MERGE */
        region_id,
        SUM(amount) AS total_amount
    FROM orders@sales_link
    WHERE order_date >= :from_date
      AND order_date <  :to_date
    GROUP BY region_id
) r
  ON r.region_id = l.region_id;
~~~

Both ways illustrate how to place `NO_MERGE`. Only use hints after understanding query transformations and verifying the plan.

### 7.4. NO_MERGE Does Not Force Every Predicate to Push Down

`NO_MERGE` only controls merging of the inline view. It does not automatically guarantee:

- All predicates are pushed down to remote.
- All joins execute remotely.
- The remote database uses an index.
- Transferred bytes decrease.

You must inspect the actual remote SQL and plan after adding the hint.

### 7.5. Do Not Use NO_MERGE on Every Inline View

Keeping a view unmerged can limit the optimizer's ability to combine predicates or pick a better join order. If the view is already automatically optimized with a good plan, adding `NO_MERGE` can make the query slower.

## 8. DRIVING_SITE Hint

`DRIVING_SITE` specifies the site where Oracle should execute the query. By default, the cost-based optimizer chooses the execution site based on estimated cost. This hint lets a DBA override that choice.

### 8.1. Example

~~~sql
SELECT /*+ DRIVING_SITE(d) */
    e.employee_id,
    e.last_name,
    d.department_name
FROM employees e
JOIN departments@sales_link d
  ON d.department_id = e.department_id;
~~~

In this example, the hint specifies the site associated with alias `D` as the driving site. When executed at the remote site, local rows can be sent to remote for joining; the final result is returned to local.

### 8.2. When Is It Beneficial?

`DRIVING_SITE` can be useful when:

- Most of the data resides in the remote database.
- The remote database has better indexes/statistics for the required join.
- The final result is much smaller than the initial remote dataset.
- The cost of sending local inputs to remote is lower than pulling remote data to local.

### 8.3. When Can It Be Harmful?

Avoid forcing the remote site if:

- The local table is very large.
- The remote database is overloaded.
- Network latency from local to remote is high.
- The query must send many local rows to remote.
- The remote site lacks required objects or privileges to perform the needed processing.
- The optimizer already picked the local site better based on accurate statistics.

### 8.4. DRIVING_SITE Is Not the Same as Predicate Pushdown

`DRIVING_SITE` chooses where to execute the query. Predicate pushdown moves filtering conditions to the site storing the data. The two techniques can complement each other, but they are not the same thing.

### 8.5. Never Assume a Hint Will Be Honored as Expected

A hint can be ignored due to a wrong alias, query transformations, SQL structure, or distributed query restrictions. Always check the plan and remote SQL after adding a hint.

## 9. Cost-Based Optimization for Distributed Queries

The optimizer uses statistics and cost estimates to select how to execute distributed SQL.

### 9.1. What Does the CBO Do?

Oracle can:

1. Merge mergeable views.
2. Check which query blocks contain collocated tables.
3. Rewrite the query into collocated inline views.
4. Choose where to execute joins/filters.
5. Estimate the number of rows and bytes to transfer.
6. Choose the remote or local execution site.

### 9.2. Statistics Must Be Accurate at Each Site

For the CBO to choose a good plan:

- Gather table/index statistics in the local database for local objects.
- Connect to the remote database and gather statistics for remote objects at the remote site itself.
- Check for stale statistics.
- Consider histograms when data distribution is skewed.
- Refresh statistics after bulk loads or major data changes.

Example gathering statistics at the remote database:

~~~sql
BEGIN
    DBMS_STATS.GATHER_TABLE_STATS(
        ownname => 'SALES',
        tabname => 'ORDERS',
        cascade => TRUE
    );
END;
/
~~~

You must connect directly to the remote database to gather statistics for remote tables. Do not gather only local schema statistics and expect it to update statistics for objects across a database link.

### 9.3. The Optimizer Does Not Know All Network Fluctuations

The cost model may not accurately reflect:

- Network latency changing over time.
- Bandwidth shared with other workloads.
- Remote server CPU contention.
- Storage latency fluctuations.
- Throttled connections or packet loss.

Therefore, a plan with a lower cost does not necessarily have a lower elapsed time at all times.

### 9.4. Bind Variables and Cardinality

Bind variables reduce hard parses and improve cursor reuse. However, if data distribution is heavily skewed by bind value, estimated cardinality may not represent all values.

In distributed queries, misestimated cardinality can cause the optimizer to pick the wrong:

- Driving site.
- Join order.
- Join method.
- Number of rows transferred over the database link.

Check actual rows and bind behavior on both local and remote sides when queries have highly varying data profiles.

## 10. Reading Distributed Query Execution Plans

An execution plan shows which operations Oracle performs at the local site and which parts are sent to the remote database.

### 10.1. EXPLAIN PLAN

~~~sql
EXPLAIN PLAN
    SET STATEMENT_ID = 'DIST_QUERY_01'
FOR
SELECT
    c.customer_id,
    c.customer_name
FROM customers@sales_link c
WHERE c.status = 'ACTIVE'
  AND c.region_id = 10;
~~~

View the plan:

~~~sql
SELECT *
FROM TABLE(
    DBMS_XPLAN.DISPLAY(
        NULL,
        'DIST_QUERY_01',
        'ALL'
    )
);
~~~

Or use the SQL*Plus script:

~~~text
SQL> @?/rdbms/admin/utlxpls.sql
~~~

### 10.2. The REMOTE Operation

A distributed execution plan typically contains a `REMOTE` operation. This represents the portion of the query executed at the remote site.

Illustrative example:

~~~text
--------------------------------------------------------------------------------
| Id | Operation          | Name       | Rows | Bytes | Cost |
--------------------------------------------------------------------------------
|  0 | SELECT STATEMENT   |            |      |       |      |
|  1 |  REMOTE            |            |  500 | 25000 |  120 |
--------------------------------------------------------------------------------
~~~

`Rows` and `Bytes` on `REMOTE` are optimizer estimates, not actual transferred figures. Compare them with actual execution statistics and SQL*Net counters.

### 10.3. Reading the SQL Sent to the Remote Database

Oracle stores the remote SQL in the `OTHER` column of `PLAN_TABLE` for the `REMOTE` operation.

~~~sql
SET LONG 1000000
SET LONGCHUNKSIZE 1000000

SELECT
    id,
    operation,
    options,
    other
FROM plan_table
WHERE statement_id = 'DIST_QUERY_01'
  AND operation = 'REMOTE'
ORDER BY id;
~~~

Read the `OTHER` contents to determine:

- Are predicates sent to remote?
- Does the remote query select only needed columns?
- Do remote table joins happen at the remote site?
- Are `GROUP BY`/`COUNT`/`SUM` executed remotely?
- Does the local site still receive too many rows?

### 10.4. Example of Remote SQL with Pushed-Down Filters

Good remote SQL might look like:

~~~sql
SELECT
    customer_id,
    customer_name
FROM customers
WHERE status = 'ACTIVE'
  AND region_id = 10
~~~

If `OTHER` only contains:

~~~sql
SELECT customer_id, customer_name, status, region_id
FROM customers
~~~

then predicates may not have been pushed down as intended. Inspect query transformations, the remote plan, and remaining filters on local.

### 10.5. Viewing Full Contents of OTHER

If SQL*Plus truncates the output:

~~~text
SQL> SET LONG 1000000
SQL> SET LONGCHUNKSIZE 1000000
~~~

Then query `PLAN_TABLE.OTHER` again.

### 10.6. Reading Operations Around REMOTE

Operations above `REMOTE` show what the local site still performs after receiving data:

- `HASH JOIN` or `NESTED LOOPS`: further joining locally.
- `SORT GROUP BY`: aggregating/sorting locally.
- `FILTER`: predicates still evaluated locally.
- `VIEW`: processing through an inline view.
- `REMOTE`: retrieving data from the remote site.

Having a `REMOTE` operation does not mean a plan is bad. What matters is how many rows/bytes the remote operation returns and what work remains locally.

## 11. EXPLAIN PLAN vs. Actual Execution Plan

`EXPLAIN PLAN` generates an estimated plan for a SQL statement. It does not execute the query and provides no actual rows or elapsed time.

### 11.1. Limitations of EXPLAIN PLAN

The output may differ from the runtime execution plan due to:

- Bind values.
- Bind peeking/adaptive cursor sharing.
- Session parameters.
- Changed statistics.
- Different object metadata at execution time.
- SQL executed in a different environment.

### 11.2. Gathering the Actual Plan

You can add `GATHER_PLAN_STATISTICS`:

~~~sql
SELECT /*+ GATHER_PLAN_STATISTICS */
    c.customer_id,
    c.customer_name
FROM customers@sales_link c
WHERE c.status = 'ACTIVE'
  AND c.region_id = 10;
~~~

Immediately after running the query in the same session:

~~~sql
SELECT *
FROM TABLE(
    DBMS_XPLAN.DISPLAY_CURSOR(
        NULL,
        NULL,
        'ALLSTATS LAST'
    )
);
~~~

Depending on execution and version, remote SQL details may appear in the Remote SQL Information section of the plan. If not shown completely, use `EXPLAIN PLAN` and `PLAN_TABLE.OTHER` to read the remote SQL.

### 11.3. Columns to Watch

| Column | Meaning |
| --- | --- |
| E-Rows | Optimizer-estimated rows |
| A-Rows | Actual rows |
| Starts | Number of times the operation was started |
| Buffers | Logical I/O |
| Reads | Physical reads |
| A-Time | Operation elapsed time |
| OMem/1Mem | Estimated or used memory for certain operations |

If the `REMOTE` operation has `A-Rows` much larger than the final output, the local site may be receiving excessive data before filtering/joining.

### 11.4. Starts Is Critical

If the `REMOTE` operation has a high `STARTS` count, the remote SQL may be invoked repeatedly. A nested loops plan can call the remote side for every outer input row.

Example:

- Local outer rows: 100,000.
- Remote lookup: once per outer row.
- `Starts` on remote: nearly 100,000.

In this situation, even if each remote call returns little data, network round trips can make the query very slow. Consider changing the join strategy, using a collocated query, or choosing an appropriate driving site.

## 12. Measuring Network Traffic and Round Trips

To prove a query rewrite is effective, measure the data actually crossing the database link.

### 12.1. Session Statistics

Run the query in a dedicated session, recording values before and after execution:

~~~sql
SELECT
    n.name,
    m.value
FROM v$mystat m
JOIN v$statname n
  ON n.statistic# = m.statistic#
WHERE n.name IN (
    'bytes sent via SQL*Net to dblink',
    'bytes received via SQL*Net from dblink',
    'SQL*Net roundtrips to/from dblink'
)
ORDER BY n.name;
~~~

Calculate the delta between the two readings to estimate bytes and round trips generated by the query. Ensure the session runs no other workload between measurements.

### 12.2. Statistics to Understand

| Statistic | Meaning |
| --- | --- |
| bytes sent via SQL*Net to dblink | Bytes local sent over the database link |
| bytes received via SQL*Net from dblink | Bytes local received over the database link |
| SQL*Net roundtrips to/from dblink | Number of request/response exchanges over the database link |

### 12.3. Deltas Instead of Cumulative Totals

Statistics in `V$MYSTAT` are session-cumulative counters. Never compare raw values from two sessions of different ages directly. Take before/after snapshots and compute the delta.

### 12.4. Wait Events

You can observe related wait events:

- `SQL*Net message to dblink`.
- `SQL*Net message from dblink`.

These waits help understand time the session spent waiting on communication with the remote database. A large wait event alone does not prove the network is the sole cause; remote CPU, remote I/O, fetch patterns, and application behavior can also contribute.

### 12.5. SQL Trace

SQL trace/TKPROF can help inspect execute/fetch counts and wait times. In production environments, only enable tracing for a specific session or SQL for a short duration, controlling disk space and trace file access permissions.

### 12.6. Do Not Use AWR/ASH Without Confirmed Licensing

AWR/ASH and certain SQL Monitoring features may require the Oracle Diagnostics Pack or Tuning Pack depending on the feature. Verify your organization's licenses before using them. You can use `V$SESSION`, `V$MYSTAT`, `V$SESSTAT`, `V$SQL`, SQL Trace, and TKPROF per authorized privileges and configuration.

## 13. End-to-End Tuning Example

Suppose LOCALDB has table `LOCAL_REGION_FILTER`, while `SALES_LINK` points to a database containing `ORDERS` and `CUSTOMERS`.

Goal: calculate revenue by segment over a date range, including only regions enabled for the current campaign.

### 13.1. Initial Query

~~~sql
SELECT
    c.segment,
    c.region_id,
    SUM(o.amount) AS revenue
FROM orders@sales_link o
JOIN customers@sales_link c
  ON c.customer_id = o.customer_id
JOIN local_region_filter f
  ON f.region_id = c.region_id
WHERE o.order_date >= :from_date
  AND o.order_date <  :to_date
  AND c.status = 'ACTIVE'
  AND f.campaign_code = :campaign_code
  AND f.enabled = 'Y'
GROUP BY c.segment, c.region_id;
~~~

The optimizer might automatically collocate the two remote tables and filter remotely. However, because the query includes a local table, an aggregate, and multiple predicates, inspect the plan to see what actually happens.

### 13.2. Rewriting as a Remote Collocated View

~~~sql
SELECT
    r.segment,
    r.region_id,
    r.revenue
FROM (
    SELECT /*+ NO_MERGE */
        c.segment,
        c.region_id,
        SUM(o.amount) AS revenue
    FROM orders@sales_link o
    JOIN customers@sales_link c
      ON c.customer_id = o.customer_id
    WHERE o.order_date >= :from_date
      AND o.order_date <  :to_date
      AND c.status = 'ACTIVE'
    GROUP BY c.segment, c.region_id
) r
JOIN (
    SELECT DISTINCT region_id
    FROM local_region_filter
    WHERE campaign_code = :campaign_code
      AND enabled = 'Y'
) f
  ON f.region_id = r.region_id;
~~~

The remote site performs the join, date/status filtering, and aggregation. The local site only joins the reduced result set with the region list.

### 13.3. Checking Semantics

Before benchmarking, verify:

- Whether `LOCAL_REGION_FILTER` can have duplicate `REGION_ID` values.
- If duplicates exist, whether `DISTINCT` matches business logic.
- Whether `NULL` values in join keys have compatible semantics.
- Whether `SUM`/`COUNT` calculations could be multiplied by the join.
- Whether date ranges share the same timezone/business meaning.
- That results before and after rewriting match.

### 13.4. Inspecting the Execution Plan

~~~sql
EXPLAIN PLAN
    SET STATEMENT_ID = 'DIST_BEFORE'
FOR
SELECT
    c.segment,
    c.region_id,
    SUM(o.amount) AS revenue
FROM orders@sales_link o
JOIN customers@sales_link c
  ON c.customer_id = o.customer_id
JOIN local_region_filter f
  ON f.region_id = c.region_id
WHERE o.order_date >= DATE '2026-01-01'
  AND o.order_date <  DATE '2026-02-01'
  AND c.status = 'ACTIVE'
  AND f.campaign_code = 'JAN26'
  AND f.enabled = 'Y'
GROUP BY c.segment, c.region_id;
~~~

Then explain the rewritten query using a different `STATEMENT_ID`. Compare:

- Number of `REMOTE` operations.
- Rows/Bytes at `REMOTE`.
- Predicates in the remote SQL.
- Whether the join between `ORDERS` and `CUSTOMERS` is inside the remote SQL.
- Whether aggregation is performed remotely.
- `STARTS` count of the remote operation.
- Remaining joins/sorts locally.

### 13.5. Measuring Actual Execution

Run each query in its own session:

1. Snapshot `V$MYSTAT` before the query.
2. Execute the query with identical bind values.
3. Fetch the entire result set.
4. Snapshot `V$MYSTAT` after the query.
5. Calculate delta bytes and round trips.
6. Record elapsed time, CPU, buffer gets, and actual rows.
7. Repeat multiple times under comparable conditions.

Do not fetch only the first few rows and conclude the query is fast; fetch the entire result set if the real workload also requires all rows.

## 14. Multiple Remote Databases

A distributed query can reference multiple database links.

### 14.1. Tables on the Same Remote Site

~~~sql
SELECT *
FROM orders@sales_link o
JOIN customers@sales_link c
  ON c.customer_id = o.customer_id;
~~~

Both tables reside in the same remote database and can therefore be joined at the remote site.

### 14.2. Tables on Two Different Remote Sites

~~~sql
SELECT *
FROM orders@sales_link o
JOIN exchange_rates@finance_link x
  ON x.currency_code = o.currency_code;
~~~

`ORDERS` and `EXCHANGE_RATES` are not collocated. Oracle must coordinate exchanges between the sites and the query execution site. Depending on the data, options include:

- Fetching filtered data from SALES to local, then joining with FINANCE.
- Fetching filtered data from FINANCE to local, then joining with SALES.
- Choosing one remote site as the driving site if possible and sensible.
- Introducing a staging/materialization step if the query is overly complex and runs frequently.

### 14.3. Grouping Processing at Each Site

If each site has multiple related tables, create one collocated inline view per site:

~~~sql
SELECT
    s.customer_id,
    s.sales_total,
    f.rate
FROM (
    SELECT /*+ NO_MERGE */
        o.customer_id,
        o.currency_code,
        SUM(o.amount) AS sales_total
    FROM orders@sales_link o
    WHERE o.order_date >= :from_date
      AND o.order_date <  :to_date
    GROUP BY o.customer_id, o.currency_code
) s
JOIN (
    SELECT /*+ NO_MERGE */
        currency_code,
        rate
    FROM exchange_rates@finance_link
    WHERE rate_date = :rate_date
) f
  ON f.currency_code = s.currency_code;
~~~

Each remote site returns only the filtered/aggregated data needed for the final join. Inspect the plan to confirm query blocks actually run at the intended sites.

### 14.4. Do Not Create Arbitrary Remote-to-Remote Dependencies

If remote site A has to open a further database link to remote site B, the architecture incurs additional dependencies, authentication, and network paths. Never assume a remote database can access the local database's links or a third database. Explicitly design which site executes each portion of the query.

## 15. When Predicates Cannot or Should Not Be Pushed Down

Not every condition can be pushed down to remote.

### 15.1. Conditions Depending on Local Tables

A predicate referencing a local column cannot be evaluated at the remote site if remote lacks that data. Choose between sending a key list, pulling results to local, or changing the driving site.

### 15.2. Functions or Expressions Unavailable on Remote

If a query invokes a function that exists only on the local database, the remote site cannot execute it directly. The function must be supported/available remotely, or processing must happen locally.

### 15.3. User-Defined Functions

A local PL/SQL function may not be pushed down to remote because the remote database lacks the function or has non-equivalent execution semantics. Do not assume a function in `WHERE` always executes where the table resides.

### 15.4. Data Types and Conversions

Data types or expressions with different conversions across databases can restrict remote execution:

- `CLOB`/`BLOB`.
- Object types.
- User-defined types.
- NLS-sensitive conversions.
- Implicit conversion between character and number/date.
- Functions whose semantics vary by character set/timezone.

### 15.5. Subqueries, Aggregates, and Complex SQL

Oracle 19c documentation notes that cost-based distributed query rewrite does not perform well for certain queries with aggregates, subqueries, or complex SQL. In such cases, consider collocated inline views and `NO_MERGE`, then verify the plan.

### 15.6. Outer Joins and NULL Semantics

When rewriting outer joins, placing a predicate in `ON` versus `WHERE` can yield different results. Example:

~~~sql
SELECT *
FROM local_customers l
LEFT JOIN remote_orders@sales_link r
  ON r.customer_id = l.customer_id
 AND r.status = 'OPEN';
~~~

Moving `R.STATUS = 'OPEN'` down to the outer query's `WHERE` clause can filter out rows without remote orders, turning the `LEFT JOIN` into an `INNER JOIN`.

Always verify semantics before pushing predicates or changing join order.

## 16. Database Links and Session Behavior

Distributed queries are also affected by connection and transaction lifecycles.

### 16.1. Remote Sessions Persist Within the Local Session

Oracle can reuse a remote connection created via a database link throughout the local session. Thus, multiple SQL statements using the same link can share the remote session.

### 16.2. Closing a Database Link

When the remote connection is no longer needed:

~~~sql
ALTER SESSION CLOSE DATABASE LINK sales_link;
~~~

Before closing:

- Close cursors using the link.
- End transactions that used the link via `COMMIT` or `ROLLBACK`.
- `ALTER SESSION` privilege is required.

Do not close a link while the application still has open cursors or transactions depending on it.

### 16.3. SELECT Over a Database Link and Transactions

Oracle documentation notes that when performing a `SELECT` over a database link, a transaction lock is placed on undo segments; releasing the segment requires `COMMIT` or `ROLLBACK`.

In applications, do not keep distributed transactions open longer than necessary. Holding remote connections and long-running transactions increases resource usage and complicates network error handling.

### 16.4. Distributed Transactions

If a transaction updates data across multiple databases, Oracle may use a distributed transaction/two-phase commit. Tuning `SELECT` differs from tuning distributed DML. When part of a distributed update fails, you must handle transaction outcomes and rollbacks per procedure—not just optimize predicates.

## 17. Bind Variables and Remote Data

Bind variables reduce hard parses and protect SQL from unsafe string concatenation. For distributed queries, examine bind values and remote cursor behavior.

### 17.1. Using Bind Variables

~~~sql
SELECT
    order_id,
    amount
FROM orders@sales_link
WHERE order_date >= :from_date
  AND order_date <  :to_date
  AND status = :status;
~~~

Binds enable SQL reuse and lower parse overhead.

### 17.2. Bind Skew

If one `STATUS` value returns 100 rows and another returns 10 million rows, the same plan may not suit both. Check cardinality and actual rows with representative bind values.

### 17.3. Do Not Concatenate Literals into SQL

Avoid generating distinct SQL per value via string concatenation unless truly necessary. This increases hard parses and introduces SQL injection risks.

### 17.4. Inspecting Remote SQL

SQL in `PLAN_TABLE.OTHER` helps verify which binds/predicates are sent to the remote site. For deeper investigation, inspect the corresponding cursor on the remote database by `SQL_ID` or SQL text per authorized privileges.

## 18. NLS, Timezones, and Semantics During Rewrites

Distributed SQL may run across databases with different NLS settings, timezones, or character sets.

### 18.1. Avoid Implicit Conversions

Avoid:

~~~sql
WHERE order_date = '01/02/2026'
~~~

Strings can parse differently depending on `NLS_DATE_FORMAT`. Use a `DATE` literal or `DATE` bind:

~~~sql
WHERE order_date >= DATE '2026-02-01'
  AND order_date <  DATE '2026-02-02'
~~~

### 18.2. Timestamp with Time Zone

If a query filters `TIMESTAMP WITH TIME ZONE`, clearly establish the business timezone. Never alter a predicate solely to achieve pushdown if doing so changes the selected time range.

### 18.3. Character Comparisons

Collation, character set, and `NLS_COMP`/`NLS_SORT` can affect string comparisons. When local and remote have differing settings, verify results before and after rewriting using accented characters, mixed case, and special characters.

### 18.4. Guarantee Equivalent Results

Distributed query optimization must preserve:

- `NULL` semantics.
- Duplicate rows.
- Outer join behavior.
- Aggregate behavior.
- Timezone conversions.
- Character comparisons.
- Numeric precision/rounding.

## 19. SQL Plan Management and Distributed Queries

SQL Profiles, SQL Plan Baselines, SQL Patches, and stored outlines may not behave as expected for queries referencing remote tables via database links.

For example, a local SQL plan baseline cannot guarantee the remote portion uses the exact remote plan that existed when the baseline was created.

Therefore:

- Inspect plans at the local execution site.
- Inspect the remote SQL and plan at the remote database.
- Do not assume a local baseline locks every remote execution choice.
- Gather statistics at the remote site.
- Benchmark after changing queries, hints, or remote indexes.

This is a major difference compared to tuning SQL confined to a single database.

## 20. Distributed Query Tuning Checklist

**Understand the query**

- Which tables are local?
- Which tables are remote?
- How many database links are involved?
- Which table is largest?
- How many rows/columns are needed in the final result?
- Which conditions depend solely on remote columns?
- Which conditions depend on local data?

**Reduce data**

- Is `SELECT *` used?
- Are remote predicates sent down to remote?
- Can data be aggregated before transfer?
- Can `DISTINCT`/`EXISTS`/semi-join run remotely?
- Can Top-N be limited remotely?
- Are join keys fully preserved?

**Choose execution site**

- Are remote tables collocated?
- Can a collocated inline view be used?
- Is `NO_MERGE` genuinely necessary?
- Does `DRIVING_SITE` help given current data distribution?
- Does the remote database have enough CPU/I/O?

**Read plan and measure**

- Is there a `REMOTE` operation?
- Does the SQL in `PLAN_TABLE.OTHER` contain the needed predicates?
- How many `E-Rows`/`A-Rows` does the remote operation return?
- Are `REMOTE` `Starts` too high?
- How many bytes are sent/received over the database link?
- How do network round trips change?
- Did actual elapsed time improve?

**Preserve semantics**

- Are outer join and `NULL` behaviors still correct?
- Have duplicate rows changed?
- Are aggregates multiplied by a join?
- Are date/timezone conversions identical to before?
- Do results before and after rewrite match?

## 21. Comprehensive Hands-On Lab

This lab simulates a distributed query with data on a remote database and a local database. Two Oracle databases or a lab environment supporting database links are required.

### Step 1 — Create a Database Link

Example created by a DBA in the lab schema:

~~~sql
CREATE DATABASE LINK sales_link
CONNECT TO sales_user
IDENTIFIED BY "Replace_With_Lab_Secret"
USING 'SALESDB';
~~~

Do not store real passwords in repositories or shared scripts. Use private/public database links per lab policy.

### Step 2 — Verify Remote Connection

~~~sql
SELECT
    name,
    db_unique_name,
    database_role
FROM v$database@sales_link;
~~~

### Step 3 — Run the Unoptimized Query

~~~sql
SELECT *
FROM orders@sales_link
WHERE order_date >= DATE '2026-01-01';
~~~

Record row counts and SQL*Net statistics before/after.

### Step 4 — Reduce Projection and Push Filters

~~~sql
SELECT
    order_id,
    customer_id,
    amount
FROM orders@sales_link
WHERE order_date >= DATE '2026-01-01'
  AND order_date <  DATE '2026-02-01';
~~~

Compare bytes received over the database link.

### Step 5 — Create a Remote Join

~~~sql
SELECT
    c.region_id,
    COUNT(*) AS order_count,
    SUM(o.amount) AS revenue
FROM orders@sales_link o
JOIN customers@sales_link c
  ON c.customer_id = o.customer_id
WHERE o.order_date >= DATE '2026-01-01'
  AND o.order_date <  DATE '2026-02-01'
  AND c.status = 'ACTIVE'
GROUP BY c.region_id;
~~~

### Step 6 — Write a Collocated Inline View

~~~sql
SELECT /*+ NO_MERGE(r) */
    r.region_id,
    r.order_count,
    r.revenue
FROM (
    SELECT
        c.region_id,
        COUNT(*) AS order_count,
        SUM(o.amount) AS revenue
    FROM orders@sales_link o
    JOIN customers@sales_link c
      ON c.customer_id = o.customer_id
    WHERE o.order_date >= DATE '2026-01-01'
      AND o.order_date <  DATE '2026-02-01'
      AND c.status = 'ACTIVE'
    GROUP BY c.region_id
) r;
~~~

Compare remote SQL in the plan and row/byte counts.

### Step 7 — Try DRIVING_SITE

If a local table is available to join:

~~~sql
SELECT /*+ DRIVING_SITE(r) */
    r.region_id,
    r.revenue,
    l.region_name
FROM (
    SELECT
        c.region_id,
        SUM(o.amount) AS revenue
    FROM orders@sales_link o
    JOIN customers@sales_link c
      ON c.customer_id = o.customer_id
    WHERE o.order_date >= DATE '2026-01-01'
      AND o.order_date <  DATE '2026-02-01'
    GROUP BY c.region_id
) r
JOIN local_regions l
  ON l.region_id = r.region_id;
~~~

Check whether the hint is applied and how much local input is sent over.

### Step 8 — Explain Plan

~~~sql
EXPLAIN PLAN
    SET STATEMENT_ID = 'LAB_DISTRIBUTED'
FOR
SELECT
    order_id,
    customer_id,
    amount
FROM orders@sales_link
WHERE order_date >= DATE '2026-01-01'
  AND order_date <  DATE '2026-02-01';

SELECT *
FROM TABLE(
    DBMS_XPLAN.DISPLAY(
        NULL,
        'LAB_DISTRIBUTED',
        'ALL'
    )
);
~~~

### Step 9 — Read Remote SQL

~~~sql
SET LONG 1000000

SELECT id, operation, other
FROM plan_table
WHERE statement_id = 'LAB_DISTRIBUTED'
  AND operation = 'REMOTE';
~~~

### Step 10 — Measure SQL*Net

Snapshot `V$MYSTAT` before and after the query. Compute deltas for bytes sent, bytes received, and round trips.

### Step 11 — Compare Results

| Metric | Original Query | Rewritten Query |
| --- | ---: | ---: |
| Rows returned |  |  |
| Bytes received from dblink |  |  |
| Bytes sent to dblink |  |  |
| Round trips |  |  |
| Elapsed time |  |  |
| CPU time |  |  |
| REMOTE Starts |  |  |
| Remote estimated rows |  |  |

### Step 12 — Verify Correctness

Compare row counts, aggregate values, NULLs, and duplicate rows between the two queries. Accept a rewrite only when results are equivalent and metrics demonstrate improvement.

## 22. Self-Check Questions

1. What is a distributed query?
2. How do local site and remote site differ?
3. Into which parts does Oracle split a distributed query?
4. What is the goal of predicate pushdown?
5. Which costs does projection pushdown reduce?
6. Why is `SELECT *` usually unsuitable for large remote tables?
7. What are collocated tables?
8. What is a collocated inline view?
9. Why should remote tables on the same site be joined before transferring data?
10. What is `NO_MERGE` used for?
11. Does `NO_MERGE` guarantee all predicates are pushed down?
12. What does `DRIVING_SITE` choose?
13. When can `DRIVING_SITE` be harmful?
14. How can the cost-based optimizer rewrite distributed queries?
15. Which SQL constructs can limit automatic distributed query rewrite?
16. Why are statistics needed in the remote database?
17. What does the `REMOTE` operation in a plan mean?
18. What information does the `OTHER` column in `PLAN_TABLE` contain?
19. How do `E-Rows` and `A-Rows` differ?
20. Why can a high `REMOTE` `Starts` count be a problem?
21. Which SQL*Net statistics help measure transferred data?
22. Why must you take before/after deltas of the query?
23. How does `EXPLAIN PLAN` differ from the actual execution plan?
24. Why do outer joins require care when moving predicates?
25. Why use date ranges instead of `TRUNC(date_column)`?
26. How do multiple remote database links affect a query?
27. Why should you not assume a remote site can access another database link?
28. Where should `DBMS_STATS` for a remote table be run?
29. Does a local SQL Plan Baseline guarantee the remote portion keeps the same plan?
30. What conditions are required to accept a query rewrite?

**Answer Hints:**

1. SQL accessing data across multiple databases.
2. Local is where SQL is issued; remote is the database accessed via a link.
3. Local SQL, remote SQL, and post-processing at the execution site.
4. Filtering data where it is stored before transferring it back.
5. Number of columns and bytes transferred.
6. Because it transfers unnecessary columns, especially LOB/large columns.
7. Tables residing in the same database.
8. An inline view accessing only tables in the same database.
9. The remote site can join/filter/aggregate locally and return a smaller result.
10. Prevents the optimizer from merging an inline view into the parent query block.
11. No; you must inspect the remote SQL and execution plan.
12. The site where the query is executed.
13. When large local data must be sent to remote or remote is overloaded/network is slow.
14. Merges views, checks collocation, then rewrites into collocated inline views.
15. Aggregates, subqueries, and complex SQL can restrict rewrite.
16. The optimizer needs accurate cardinality/selectivity/cost at the site storing the table.
17. The portion of the query executed at the remote database.
18. The SQL statement sent to the remote site.
19. `E-Rows` is estimated; `A-Rows` is actual.
20. It may mean the remote query is invoked repeatedly, increasing network round trips.
21. `bytes sent/received via SQL*Net to/from dblink` and `roundtrips to/from dblink`.
22. Because statistics are cumulative session counters.
23. `EXPLAIN PLAN` only estimates; the actual plan includes runtime statistics.
24. Because predicates in `WHERE` can eliminate NULL-extended rows and convert an outer join into an inner join.
25. To create a range predicate that can easily use indexes without losing time-of-day portions.
26. With multiple remote sites, the query must coordinate exchanges and choose join locations.
27. Because remote links, credentials, and network paths are not automatically shared.
28. Directly connected to the remote database.
29. No; the remote portion may use a different plan.
30. Results must be equivalent, and measurable reductions in bytes/round trips or elapsed time must be observed on a representative workload.

## Oracle Reference Documentation

- [Oracle Database 19c Administrator's Guide — Tuning Distributed Queries](https://docs.oracle.com/en/database/oracle/oracle-database/19/admin/developing-applications-for-a-distributed-database-system.html): collocated inline views, cost-based optimization, hints, and execution plan analysis.
- [Oracle Database 19c Administrator's Guide — Using Collocated Inline Views](https://docs.oracle.com/en/database/oracle/oracle-database/19/admin/developing-applications-for-a-distributed-database-system.html): grouping tables at the same remote site to reduce network traffic.
- [Oracle Database 19c SQL Language Reference — DRIVING_SITE Hint](https://docs.oracle.com/en/database/oracle/oracle-database/19/sqlrf/Comments.html): controlling the distributed query execution site.
- [Oracle Database 19c SQL Tuning Guide — SQL Tuning Concepts and Execution Plans](https://docs.oracle.com/en/database/oracle/oracle-database/19/tgsql/introduction-to-sql-tuning.html): reading and analyzing execution plans.
- [Oracle Database 19c Database Reference — V$MYSTAT](https://docs.oracle.com/en/database/oracle/oracle-database/19/refrn/V-MYSTAT.html): current session statistics.
- [Oracle Database 19c Database Reference — V$SESSTAT](https://docs.oracle.com/en/database/oracle/oracle-database/19/refrn/V-SESSTAT.html): per-session usage statistics.
- [Oracle Database 19c SQL Language Reference — ALTER SESSION](https://docs.oracle.com/en/database/oracle/oracle-database/19/sqlrf/ALTER-SESSION.html): closing a database link in a session.

**Key Takeaway:** Distributed queries are fast when the remote database performs as much appropriate work as possible where the data resides and sends only the necessary results back to local. Push predicates down, narrow projections, aggregate at remote, and group same-site tables with collocated inline views. `NO_MERGE` preserves inline views when needed; `DRIVING_SITE` controls execution location when backed by evidence. Read the `REMOTE` operation and SQL in `PLAN_TABLE.OTHER`, measure rows/bytes/round trips using execution statistics and SQL*Net counters, and compare results before and after rewriting. Never accept a hint simply because the plan looks pretty; preserve semantics and prove improvement with real metrics.
